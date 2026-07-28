import { createClientOperationId } from './childcareCommand';
import {
  type ChildcareCommandJournalAdapter,
  type ChildcareCommandJournalEntry,
  type ChildcareCommandJournalRef,
  type ChildcareCommandJournalScope,
  type ChildcareCommandJournalStatus,
  type PrepareChildcareCommandInput,
} from './childcareCommandJournal';

interface JournalBroadcastMessage {
  readonly schema_version: 1;
  readonly type: 'lane_changed';
  readonly actor_user_id: string;
  readonly organization_id: string;
}

export interface ChildcareCommandBroadcastChannel {
  postMessage(message: unknown): void;
  addEventListener(type: 'message', listener: (event: MessageEvent<unknown>) => void): void;
  removeEventListener(type: 'message', listener: (event: MessageEvent<unknown>) => void): void;
  close(): void;
}

export interface ChildcareCommandCoordinatorOptions {
  readonly ownerId?: string;
  readonly leaseTtlMs?: number;
  readonly nowEpochMs?: () => number;
  readonly broadcastChannelFactory?: (name: string) => ChildcareCommandBroadcastChannel | null;
}

export interface ChildcareCommandLeaseResult<Result> {
  readonly acquired: boolean;
  readonly value?: Result;
}

export class ChildcareCommandLeaseLostError extends Error {
  constructor() {
    super('This CareSync tab lost ownership of the childcare command lane before the task completed.');
    this.name = 'ChildcareCommandLeaseLostError';
  }
}

export interface ChildcareCommandLeaseFence {
  /** Renew and prove this exact coordinator still owns the lane. */
  assertOwned(): Promise<void>;
}

type LaneChangeListener = (scope: ChildcareCommandJournalScope) => void;

const BROADCAST_NAME = 'caresync-childcare-command-recovery-v1';

function defaultBroadcastFactory(name: string): ChildcareCommandBroadcastChannel | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  try {
    return new BroadcastChannel(name) as ChildcareCommandBroadcastChannel;
  } catch {
    return null;
  }
}

function parseMessage(value: unknown): ChildcareCommandJournalScope | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const keys = Object.keys(row).sort();
  if (
    keys.join('|') !== 'actor_user_id|organization_id|schema_version|type'
    || row.schema_version !== 1
    || row.type !== 'lane_changed'
    || typeof row.actor_user_id !== 'string'
    || typeof row.organization_id !== 'string'
  ) return null;
  return { actorUserId: row.actor_user_id, organizationId: row.organization_id };
}

/**
 * IndexedDB transactions are the authority. BroadcastChannel is only a prompt
 * for other tabs to re-read that durable state; correctness never depends on a
 * broadcast being delivered.
 */
export class ChildcareCommandJournalCoordinator {
  readonly ownerId: string;
  private readonly leaseTtlMs: number;
  private readonly nowEpochMs: () => number;
  private readonly channel: ChildcareCommandBroadcastChannel | null;
  private readonly listeners = new Set<LaneChangeListener>();
  private taskInFlight = false;
  private closed = false;

  private readonly onMessage = (event: MessageEvent<unknown>): void => {
    const scope = parseMessage(event.data);
    if (!scope) return;
    this.listeners.forEach((listener) => listener(scope));
  };

  constructor(
    readonly adapter: ChildcareCommandJournalAdapter,
    options: ChildcareCommandCoordinatorOptions = {},
  ) {
    this.ownerId = options.ownerId ?? createClientOperationId();
    this.leaseTtlMs = options.leaseTtlMs ?? 30_000;
    this.nowEpochMs = options.nowEpochMs ?? (() => Date.now());
    if (!Number.isSafeInteger(this.leaseTtlMs) || this.leaseTtlMs < 300) {
      throw new Error('The childcare command coordination lease must be at least 300 milliseconds.');
    }
    const factory = options.broadcastChannelFactory ?? defaultBroadcastFactory;
    this.channel = factory(BROADCAST_NAME);
    this.channel?.addEventListener('message', this.onMessage);
  }

  private broadcast(scope: ChildcareCommandJournalScope): void {
    try {
      this.channel?.postMessage({
        schema_version: 1,
        type: 'lane_changed',
        actor_user_id: scope.actorUserId,
        organization_id: scope.organizationId,
      } satisfies JournalBroadcastMessage);
    } catch {
      // IndexedDB remains authoritative when browser broadcast is unavailable.
    }
    this.listeners.forEach((listener) => listener(scope));
  }

  subscribe(listener: LaneChangeListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async prepareNew(input: PrepareChildcareCommandInput): Promise<ChildcareCommandJournalEntry> {
    const entry = await this.adapter.createPrepared(input);
    this.broadcast(entry);
    return entry;
  }

  get(ref: ChildcareCommandJournalRef): Promise<ChildcareCommandJournalEntry | null> {
    return this.adapter.get(ref);
  }

  listLane(scope: ChildcareCommandJournalScope): Promise<readonly ChildcareCommandJournalEntry[]> {
    return this.adapter.listLane(scope);
  }

  async transition(
    ref: ChildcareCommandJournalRef,
    allowedStatuses: readonly ChildcareCommandJournalStatus[],
    nextStatus: ChildcareCommandJournalStatus,
  ): Promise<ChildcareCommandJournalEntry> {
    const entry = await this.adapter.transition(ref, allowedStatuses, nextStatus);
    this.broadcast(entry);
    return entry;
  }

  async clearCommittedAfterRefresh(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.adapter.deleteCommittedAfterRefresh(ref);
    this.broadcast(ref);
  }

  async clearPreparedAfterAuthoritativeRejection(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.adapter.deletePreparedAfterAuthoritativeRejection(ref);
    this.broadcast(ref);
  }

  async retireFinalAbsenceAfterAcknowledgement(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.adapter.deleteFinalAbsenceAfterAcknowledgement(ref);
    this.broadcast(ref);
  }

  async runWithReconciliationLease<Result>(
    scope: ChildcareCommandJournalScope,
    task: (fence: ChildcareCommandLeaseFence) => Promise<Result>,
  ): Promise<ChildcareCommandLeaseResult<Result>> {
    // An IndexedDB lease is shared by tabs; this local guard also prevents two
    // overlapping calls in one React runtime from being mistaken for a reentrant
    // renewal merely because they share the coordinator owner ID.
    if (this.closed || this.taskInFlight) return { acquired: false };
    this.taskInFlight = true;
    let acquired = false;
    let leaseLost = false;
    let heartbeat: ReturnType<typeof globalThis.setInterval> | null = null;
    const renew = async (): Promise<boolean> => {
      if (this.closed || leaseLost) return false;
      try {
        const retained = await this.adapter.renewLease(
          scope,
          this.ownerId,
          this.nowEpochMs(),
          this.leaseTtlMs,
        );
        if (!retained) leaseLost = true;
        return retained;
      } catch {
        leaseLost = true;
        return false;
      }
    };
    const fence: ChildcareCommandLeaseFence = {
      assertOwned: async () => {
        if (!(await renew())) throw new ChildcareCommandLeaseLostError();
      },
    };

    try {
      acquired = await this.adapter.acquireLease(
        scope,
        this.ownerId,
        this.nowEpochMs(),
        this.leaseTtlMs,
      );
      if (!acquired) return { acquired: false };
      heartbeat = globalThis.setInterval(() => { void renew(); }, Math.max(100, Math.floor(this.leaseTtlMs / 3)));
      const value = await task(fence);
      await fence.assertOwned();
      return { acquired: true, value };
    } finally {
      if (heartbeat !== null) globalThis.clearInterval(heartbeat);
      if (acquired) await this.adapter.releaseLease(scope, this.ownerId).catch(() => undefined);
      this.taskInFlight = false;
    }
  }

  close(): void {
    this.closed = true;
    this.channel?.removeEventListener('message', this.onMessage);
    this.channel?.close();
    this.listeners.clear();
  }
}
