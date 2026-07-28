import { describe, expect, it, vi } from 'vitest';
import {
  type ChildcareCommandBroadcastChannel,
  ChildcareCommandLeaseLostError,
  ChildcareCommandJournalCoordinator,
} from './childcareCommandCoordinator';
import {
  createMemoryCommandJournalState,
  MemoryChildcareCommandJournalAdapter,
} from './childcareCommandJournal';

const ACTOR_ID = '10000000-0000-4000-8000-000000000001';
const ORGANIZATION_ID = '20000000-0000-4000-8000-000000000001';
const OPERATION_ID = '30000000-0000-4000-8000-000000000001';
const OWNER_ONE = '40000000-0000-4000-8000-000000000001';
const OWNER_TWO = '40000000-0000-4000-8000-000000000002';

class BroadcastHub {
  readonly channels = new Set<FakeBroadcastChannel>();

  create(): ChildcareCommandBroadcastChannel {
    const channel = new FakeBroadcastChannel(this);
    this.channels.add(channel);
    return channel;
  }
}

class FakeBroadcastChannel implements ChildcareCommandBroadcastChannel {
  private readonly listeners = new Set<(event: MessageEvent<unknown>) => void>();

  constructor(private readonly hub: BroadcastHub) {}

  postMessage(message: unknown): void {
    this.hub.channels.forEach((channel) => {
      if (channel !== this) channel.emit(message);
    });
  }

  private emit(message: unknown): void {
    this.listeners.forEach((listener) => listener({ data: message } as MessageEvent<unknown>));
  }

  addEventListener(_type: 'message', listener: (event: MessageEvent<unknown>) => void): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: 'message', listener: (event: MessageEvent<unknown>) => void): void {
    this.listeners.delete(listener);
  }

  close(): void {
    this.hub.channels.delete(this);
    this.listeners.clear();
  }
}

function input() {
  return {
    actorUserId: ACTOR_ID,
    organizationId: ORGANIZATION_ID,
    clientOperationId: OPERATION_ID,
    commandType: 'family.create' as const,
    targetType: 'family' as const,
    expectedTargetId: null,
    expectedActionOwnerId: null,
    createdAt: '2026-07-17T08:00:00Z',
  };
}

describe('cross-tab childcare command coordination', () => {
  it('broadcasts only a lane invalidation and makes the other tab re-read durable state', async () => {
    const state = createMemoryCommandJournalState();
    const hub = new BroadcastHub();
    const first = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_ONE, broadcastChannelFactory: () => hub.create() },
    );
    const second = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_TWO, broadcastChannelFactory: () => hub.create() },
    );
    const listener = vi.fn();
    second.subscribe(listener);

    await first.prepareNew(input());

    expect(listener).toHaveBeenCalledWith({ actorUserId: ACTOR_ID, organizationId: ORGANIZATION_ID });
    expect(await second.listLane(input())).toHaveLength(1);
    const message = listener.mock.calls[0][0];
    expect(JSON.stringify(message)).not.toContain(OPERATION_ID);
    first.close();
    second.close();
  });

  it('allows only one tab to own the reconciliation lease at a time', async () => {
    const state = createMemoryCommandJournalState();
    const first = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_ONE, leaseTtlMs: 3_000, broadcastChannelFactory: () => null },
    );
    const second = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_TWO, leaseTtlMs: 3_000, broadcastChannelFactory: () => null },
    );

    let releaseFirst!: () => void;
    let announceEntered!: () => void;
    const entered = new Promise<void>((resolve) => { announceEntered = resolve; });
    const hold = new Promise<void>((resolve) => { releaseFirst = resolve; });
    const firstRun = first.runWithReconciliationLease(input(), async () => {
      announceEntered();
      await hold;
      return 'first';
    });
    await entered;

    const secondRun = await second.runWithReconciliationLease(input(), async () => 'second');
    expect(secondRun).toEqual({ acquired: false });

    releaseFirst();
    await expect(firstRun).resolves.toEqual({ acquired: true, value: 'first' });
    await expect(second.runWithReconciliationLease(input(), async () => 'after-release'))
      .resolves.toEqual({ acquired: true, value: 'after-release' });
    first.close();
    second.close();
  });

  it('keeps IndexedDB authoritative when BroadcastChannel is unavailable', async () => {
    const state = createMemoryCommandJournalState();
    const coordinator = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_ONE, broadcastChannelFactory: () => null },
    );
    await coordinator.prepareNew(input());
    expect(await coordinator.listLane(input())).toHaveLength(1);
    coordinator.close();
  });

  it('does not treat overlapping work in one coordinator as a reentrant lease renewal', async () => {
    const coordinator = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(),
      { ownerId: OWNER_ONE, leaseTtlMs: 3_000, broadcastChannelFactory: () => null },
    );
    let release!: () => void;
    let entered!: () => void;
    const hold = new Promise<void>((resolve) => { release = resolve; });
    const started = new Promise<void>((resolve) => { entered = resolve; });
    const first = coordinator.runWithReconciliationLease(input(), async () => {
      entered();
      await hold;
      return 'first';
    });
    await started;

    await expect(coordinator.runWithReconciliationLease(input(), async () => 'overlap'))
      .resolves.toEqual({ acquired: false });
    release();
    await expect(first).resolves.toEqual({ acquired: true, value: 'first' });
    coordinator.close();
  });

  it('fails closed when an expired lease is overtaken before the original task completes', async () => {
    const state = createMemoryCommandJournalState();
    let now = 0;
    const first = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_ONE, leaseTtlMs: 3_000, nowEpochMs: () => now, broadcastChannelFactory: () => null },
    );
    const second = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_TWO, leaseTtlMs: 3_000, nowEpochMs: () => now, broadcastChannelFactory: () => null },
    );
    let releaseFirst!: () => void;
    let firstEntered!: () => void;
    const firstHold = new Promise<void>((resolve) => { releaseFirst = resolve; });
    const firstStarted = new Promise<void>((resolve) => { firstEntered = resolve; });
    const firstRun = first.runWithReconciliationLease(input(), async () => {
      firstEntered();
      await firstHold;
      return 'stale-result';
    });
    await firstStarted;

    now = 3_001;
    let releaseSecond!: () => void;
    let secondEntered!: () => void;
    const secondHold = new Promise<void>((resolve) => { releaseSecond = resolve; });
    const secondStarted = new Promise<void>((resolve) => { secondEntered = resolve; });
    const secondRun = second.runWithReconciliationLease(input(), async () => {
      secondEntered();
      await secondHold;
      return 'new-owner';
    });
    await secondStarted;

    releaseFirst();
    await expect(firstRun).rejects.toBeInstanceOf(ChildcareCommandLeaseLostError);
    releaseSecond();
    await expect(secondRun).resolves.toEqual({ acquired: true, value: 'new-owner' });
    first.close();
    second.close();
  });
});
