import { describe, expect, it, vi } from 'vitest';
import { ApiError } from './client';
import { CommandRejectedBeforeCommitError } from './childcareCommand';
import {
  ChildcareCommandJournalCoordinator,
  ChildcareCommandLeaseLostError,
} from './childcareCommandCoordinator';
import {
  createMemoryCommandJournalState,
  MemoryChildcareCommandJournalAdapter,
  type MemoryCommandJournalState,
} from './childcareCommandJournal';
import {
  ChildcareCommandRecoveryService,
  ChildcareCommandLeaseUnavailableError,
  ChildcareCommandReceiptMismatchError,
} from './childcareCommandRecovery';
import type { ChildcareCommandReceipt } from './childcareCommandReceipt';

const ACTOR_ID = '10000000-0000-4000-8000-000000000001';
const OTHER_ACTOR_ID = '10000000-0000-4000-8000-000000000002';
const ORGANIZATION_ID = '20000000-0000-4000-8000-000000000001';
const OTHER_ORGANIZATION_ID = '20000000-0000-4000-8000-000000000002';
const OPERATION_ID = '30000000-0000-4000-8000-000000000001';
const TARGET_ID = '40000000-0000-4000-8000-000000000001';
const OWNER_ONE = '50000000-0000-4000-8000-000000000001';
const OWNER_TWO = '50000000-0000-4000-8000-000000000002';

function input() {
  return {
    actorUserId: ACTOR_ID,
    organizationId: ORGANIZATION_ID,
    clientOperationId: OPERATION_ID,
    commandType: 'family.update' as const,
    targetType: 'family' as const,
    expectedTargetId: TARGET_ID,
    expectedActionOwnerId: null,
    createdAt: '2026-07-17T09:00:00Z',
  };
}

function receipt(overrides: Partial<ChildcareCommandReceipt> = {}): ChildcareCommandReceipt {
  return {
    organizationId: ORGANIZATION_ID,
    clientOperationId: OPERATION_ID,
    commandType: 'family.update',
    targetType: 'family',
    targetId: TARGET_ID,
    committedVersion: 7,
    committedAt: '2026-07-17T09:01:00Z',
    facilityId: null,
    actionRoute: `/families/${TARGET_ID}`,
    ...overrides,
  };
}

function finalAbsenceError(detailOverrides: Record<string, unknown> = {}): ApiError {
  return new ApiError(404, 'The command was finalized without a commit.', {
    detail: {
      code: 'operation_finalized_absent',
      message: 'No command receipt exists; this operation id is now terminal.',
      actor_user_id: ACTOR_ID,
      client_operation_id: OPERATION_ID,
      organization_id: ORGANIZATION_ID,
      ...detailOverrides,
    },
  });
}

function coordinator(state: MemoryCommandJournalState, ownerId: string) {
  return new ChildcareCommandJournalCoordinator(
    new MemoryChildcareCommandJournalAdapter(state),
    { ownerId, leaseTtlMs: 3_000, broadcastChannelFactory: () => null },
  );
}

describe('childcare command recovery state machine', () => {
  it('reconciles admission offer receipts only to the journaled owning application', async () => {
    const admissionInput = {
      ...input(),
      commandType: 'admission.offer.withdraw' as const,
      targetType: 'admission_offer' as const,
      expectedActionOwnerId: OWNER_ONE,
    };
    const matchingReceipt = receipt({
      commandType: 'admission.offer.withdraw',
      targetType: 'admission_offer',
      actionRoute: `/admissions/applications/${OWNER_ONE}`,
    });
    const matchingCoordinator = coordinator(createMemoryCommandJournalState(), OWNER_TWO);
    await matchingCoordinator.prepareNew(admissionInput);
    await expect(new ChildcareCommandRecoveryService(
      matchingCoordinator,
      async () => matchingReceipt,
    ).reconcile(admissionInput)).resolves.toMatchObject({
      kind: 'committed_needs_refresh',
      receipt: { targetType: 'admission_offer' },
    });
    matchingCoordinator.close();

    const mismatchedCoordinator = coordinator(createMemoryCommandJournalState(), OWNER_TWO);
    await mismatchedCoordinator.prepareNew(admissionInput);
    await expect(new ChildcareCommandRecoveryService(
      mismatchedCoordinator,
      async () => ({
        ...matchingReceipt,
        actionRoute: `/admissions/applications/${OWNER_TWO}`,
      }),
    ).reconcile(admissionInput)).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'receipt_mismatch',
    });
    mismatchedCoordinator.close();
  });

  it('retires a historical nested admission receipt after refreshing its owning application', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_TWO);
    const historicalOfferId = '60000000-0000-4000-8000-000000000001';
    const admissionInput = {
      ...input(),
      commandType: 'admission.offer.issue' as const,
      targetType: 'admission_offer' as const,
      expectedTargetId: null,
      expectedActionOwnerId: OWNER_ONE,
    };
    const historicalReceipt = receipt({
      commandType: 'admission.offer.issue',
      targetType: 'admission_offer',
      targetId: historicalOfferId,
      committedVersion: 1,
      actionRoute: `/admissions/applications/${OWNER_ONE}`,
    });
    await journalCoordinator.prepareNew(admissionInput);
    const service = new ChildcareCommandRecoveryService(
      journalCoordinator,
      async () => historicalReceipt,
    );
    const result = await service.reconcile(admissionInput);
    if (result.kind !== 'committed_needs_refresh') throw new Error('unexpected test state');

    await expect(service.acknowledgeCanonicalRefresh(admissionInput, result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'admission_offer',
      targetId: historicalOfferId,
      version: 9,
    })).rejects.toBeInstanceOf(ChildcareCommandReceiptMismatchError);
    expect(await journalCoordinator.get(admissionInput)).not.toBeNull();

    await expect(service.acknowledgeCanonicalRefresh(admissionInput, result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'admission_application',
      targetId: OWNER_TWO,
      version: 12,
    })).rejects.toBeInstanceOf(ChildcareCommandReceiptMismatchError);
    expect(await journalCoordinator.get(admissionInput)).not.toBeNull();

    await service.acknowledgeCanonicalRefresh(admissionInput, result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'admission_application',
      targetId: OWNER_ONE,
      version: 12,
    });
    expect(await journalCoordinator.get(admissionInput)).toBeNull();
    journalCoordinator.close();
  });

  it('uses the same owning-application refresh gate for a superseded waitlist receipt', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_TWO);
    const historicalWaitlistId = '60000000-0000-4000-8000-000000000002';
    const admissionInput = {
      ...input(),
      commandType: 'admission.waitlist.enter' as const,
      targetType: 'admission_waitlist' as const,
      expectedTargetId: null,
      expectedActionOwnerId: OWNER_ONE,
    };
    const service = new ChildcareCommandRecoveryService(
      journalCoordinator,
      async () => receipt({
        commandType: 'admission.waitlist.enter',
        targetType: 'admission_waitlist',
        targetId: historicalWaitlistId,
        committedVersion: 1,
        actionRoute: `/admissions/applications/${OWNER_ONE}`,
      }),
    );
    await journalCoordinator.prepareNew(admissionInput);
    const result = await service.reconcile(admissionInput);
    if (result.kind !== 'committed_needs_refresh') throw new Error('unexpected test state');
    await service.acknowledgeCanonicalRefresh(admissionInput, result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'admission_application',
      targetId: OWNER_ONE,
      version: 7,
    });
    expect(await journalCoordinator.get(admissionInput)).toBeNull();
    journalCoordinator.close();
  });

  it('re-inspects a row cleared by another tab without interpreting disappearance as success', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    const entry = await journalCoordinator.prepareNew(input());
    const committed = new ChildcareCommandRecoveryService(journalCoordinator, async () => receipt());
    const absent = new ChildcareCommandRecoveryService(journalCoordinator, async () => { throw finalAbsenceError(); });
    const mismatched = new ChildcareCommandRecoveryService(
      journalCoordinator,
      async () => receipt({ organizationId: OTHER_ORGANIZATION_ID }),
    );

    await expect(committed.inspectFinalizedOperation(entry)).resolves.toMatchObject({
      kind: 'committed',
      actionRoute: `/families/${TARGET_ID}`,
      receipt: { clientOperationId: OPERATION_ID },
    });
    await expect(absent.inspectFinalizedOperation(entry)).resolves.toEqual({
      kind: 'absent_final',
      clientOperationId: OPERATION_ID,
    });
    await journalCoordinator.transition(input(), ['prepared'], 'committed_needs_refresh');
    const committedEntry = await journalCoordinator.get(input());
    if (!committedEntry) throw new Error('Expected committed journal evidence.');
    await expect(absent.inspectFinalizedOperation(committedEntry)).resolves.toEqual({
      kind: 'blocked',
      reason: 'receipt_disappeared_after_commit',
    });
    await expect(mismatched.inspectFinalizedOperation(entry)).resolves.toEqual({
      kind: 'blocked',
      reason: 'receipt_mismatch',
    });
    journalCoordinator.close();
  });

  it('persists before send, retains the row after a crash-like failure, and restores it after reload', async () => {
    const state = createMemoryCommandJournalState();
    const firstCoordinator = coordinator(state, OWNER_ONE);
    const service = new ChildcareCommandRecoveryService(firstCoordinator, async () => receipt());
    const onPrepared = vi.fn();
    const send = vi.fn(async () => {
      expect(onPrepared).toHaveBeenCalledWith(expect.objectContaining({ status: 'prepared' }));
      expect(await firstCoordinator.get(input())).toMatchObject({ status: 'prepared' });
      throw new TypeError('connection reset after write');
    });

    await expect(service.persistBeforeSend(input(), send, onPrepared)).rejects.toThrow('connection reset');
    expect(send).toHaveBeenCalledWith(OPERATION_ID);

    const reloadedCoordinator = coordinator(state, OWNER_TWO);
    expect(await reloadedCoordinator.get(input())).toMatchObject({
      clientOperationId: OPERATION_ID,
      status: 'blocked',
    });
    firstCoordinator.close();
    reloadedCoordinator.close();
  });

  it('retires only the prepared row after an authoritative server no-commit response', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    const receiptLoader = vi.fn(async () => receipt());
    const service = new ChildcareCommandRecoveryService(journalCoordinator, receiptLoader);
    const rejection = new CommandRejectedBeforeCommitError(
      'The document scanner is unavailable. The document stays quarantined and can be scanned again.',
      new ApiError(503, 'scanner unavailable', { detail: { code: 'malware_scanner_unavailable' } }),
    );

    await expect(service.persistBeforeSend(input(), async () => { throw rejection; }))
      .rejects.toBe(rejection);
    expect(await journalCoordinator.listLane(input())).toEqual([]);
    expect(receiptLoader).not.toHaveBeenCalled();

    const retry = { ...input(), clientOperationId: '30000000-0000-4000-8000-000000000002' };
    await expect(service.persistBeforeSend(retry, async () => ({ accepted: true })))
      .resolves.toMatchObject({ response: { accepted: true } });
    journalCoordinator.close();
  });

  it('never calls send if durable persistence fails', async () => {
    const send = vi.fn();
    const brokenAdapter = new MemoryChildcareCommandJournalAdapter();
    await brokenAdapter.createPrepared(input());
    const service = new ChildcareCommandRecoveryService(
      new ChildcareCommandJournalCoordinator(brokenAdapter, {
        ownerId: OWNER_ONE,
        broadcastChannelFactory: () => null,
      }),
      async () => receipt(),
    );
    await expect(service.persistBeforeSend({ ...input(), clientOperationId: '30000000-0000-4000-8000-000000000002' }, send))
      .rejects.toThrow('previous childcare command');
    expect(send).not.toHaveBeenCalled();
  });

  it('models POST-before-GET ordering by holding the lane lease until send settles', async () => {
    const state = createMemoryCommandJournalState();
    const sendingCoordinator = coordinator(state, OWNER_ONE);
    const reconcilingCoordinator = coordinator(state, OWNER_TWO);
    const receiptLoader = vi.fn(async () => receipt());
    const sender = new ChildcareCommandRecoveryService(sendingCoordinator, receiptLoader);
    const reconciler = new ChildcareCommandRecoveryService(reconcilingCoordinator, receiptLoader);

    let finishSend!: () => void;
    let sendStarted!: () => void;
    const started = new Promise<void>((resolve) => { sendStarted = resolve; });
    const pendingSend = new Promise<void>((resolve) => { finishSend = resolve; });
    const sending = sender.persistBeforeSend(input(), async () => {
      sendStarted();
      await pendingSend;
      return { validated: true };
    });
    await started;

    await expect(reconciler.reconcile(input())).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'lease_held_by_another_tab',
    });
    expect(receiptLoader).not.toHaveBeenCalled();

    finishSend();
    await sending;
    await expect(reconciler.reconcile(input())).resolves.toMatchObject({ kind: 'committed_needs_refresh' });
    expect(receiptLoader).toHaveBeenCalledTimes(1);
    sendingCoordinator.close();
    reconcilingCoordinator.close();
  });

  it('does not make a stale status transition after its lease is overtaken mid-send', async () => {
    const state = createMemoryCommandJournalState();
    let now = 0;
    const firstCoordinator = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_ONE, leaseTtlMs: 3_000, nowEpochMs: () => now, broadcastChannelFactory: () => null },
    );
    const secondCoordinator = new ChildcareCommandJournalCoordinator(
      new MemoryChildcareCommandJournalAdapter(state),
      { ownerId: OWNER_TWO, leaseTtlMs: 3_000, nowEpochMs: () => now, broadcastChannelFactory: () => null },
    );
    const service = new ChildcareCommandRecoveryService(firstCoordinator, async () => receipt());
    let finishSend!: () => void;
    let sendEntered!: () => void;
    const sendHold = new Promise<void>((resolve) => { finishSend = resolve; });
    const sendStarted = new Promise<void>((resolve) => { sendEntered = resolve; });
    const sending = service.persistBeforeSend(input(), async () => {
      sendEntered();
      await sendHold;
      return { accepted: true };
    });
    await sendStarted;

    now = 3_001;
    let releaseSecond!: () => void;
    let secondEntered!: () => void;
    const secondHold = new Promise<void>((resolve) => { releaseSecond = resolve; });
    const secondStarted = new Promise<void>((resolve) => { secondEntered = resolve; });
    const secondLease = secondCoordinator.runWithReconciliationLease(input(), async () => {
      secondEntered();
      await secondHold;
    });
    await secondStarted;

    finishSend();
    await expect(sending).rejects.toBeInstanceOf(ChildcareCommandLeaseLostError);
    expect(await secondCoordinator.get(input())).toMatchObject({ status: 'prepared' });
    releaseSecond();
    await secondLease;
    firstCoordinator.close();
    secondCoordinator.close();
  });

  it('marks a matching receipt committed but clears only after a matching canonical refresh', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    await journalCoordinator.prepareNew(input());
    const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => receipt());

    const result = await service.reconcile(input());
    expect(result).toMatchObject({
      kind: 'committed_needs_refresh',
      actionRoute: `/families/${TARGET_ID}`,
      entry: { status: 'committed_needs_refresh' },
    });
    expect(await journalCoordinator.get(input())).not.toBeNull();
    if (result.kind !== 'committed_needs_refresh') throw new Error('unexpected test state');

    await expect(service.acknowledgeCanonicalRefresh(input(), result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'family',
      targetId: TARGET_ID,
      version: 6,
    })).rejects.toBeInstanceOf(ChildcareCommandReceiptMismatchError);
    expect(await journalCoordinator.get(input())).not.toBeNull();

    await service.acknowledgeCanonicalRefresh(input(), result.receipt, {
      organizationId: ORGANIZATION_ID,
      targetType: 'family',
      targetId: TARGET_ID,
      version: 8,
    });
    expect(await journalCoordinator.get(input())).toBeNull();
    journalCoordinator.close();
  });

  it('accepts only an exact actor/org/op-bound tombstone proof and requires operator retirement before a new UUID', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    await journalCoordinator.prepareNew(input());
    const service = new ChildcareCommandRecoveryService(
      journalCoordinator,
      async () => { throw finalAbsenceError(); },
    );

    await expect(service.reconcile(input())).resolves.toMatchObject({
      kind: 'absent_final',
      clientOperationId: OPERATION_ID,
      newOperationRequired: true,
      entry: { status: 'absent_final' },
    });
    await expect(journalCoordinator.clearCommittedAfterRefresh(input())).rejects.toThrow('Only a committed command');
    await expect(service.acknowledgeFinalAbsence(input(), {
      reviewed: true,
      newOperationRequired: true,
    })).resolves.toBeUndefined();
    expect(await journalCoordinator.get(input())).toBeNull();

    const newOperation = { ...input(), clientOperationId: '30000000-0000-4000-8000-000000000002' };
    const send = vi.fn(async (operationId: string) => ({ operationId }));
    await expect(service.persistBeforeSend(newOperation, send)).resolves.toMatchObject({
      entry: { status: 'prepared', clientOperationId: newOperation.clientOperationId },
      response: { operationId: newOperation.clientOperationId },
    });
    expect(send).toHaveBeenCalledWith(newOperation.clientOperationId);
    journalCoordinator.close();
  });

  it('does not retire a terminal-absence row while another tab owns the lane lease', async () => {
    const state = createMemoryCommandJournalState();
    const firstCoordinator = coordinator(state, OWNER_ONE);
    const secondCoordinator = coordinator(state, OWNER_TWO);
    await firstCoordinator.prepareNew(input());
    await firstCoordinator.transition(input(), ['prepared'], 'absent_final');
    let release!: () => void;
    let entered!: () => void;
    const hold = new Promise<void>((resolve) => { release = resolve; });
    const started = new Promise<void>((resolve) => { entered = resolve; });
    const lease = firstCoordinator.runWithReconciliationLease(input(), async () => {
      entered();
      await hold;
    });
    await started;
    const service = new ChildcareCommandRecoveryService(secondCoordinator, async () => receipt());

    await expect(service.acknowledgeFinalAbsence(input(), {
      reviewed: true,
      newOperationRequired: true,
    })).rejects.toBeInstanceOf(ChildcareCommandLeaseUnavailableError);
    expect(await secondCoordinator.get(input())).toMatchObject({ status: 'absent_final' });

    release();
    await lease;
    firstCoordinator.close();
    secondCoordinator.close();
  });

  it.each([
    ['plain 404', new ApiError(404, 'not found')],
    ['wrong code', finalAbsenceError({ code: 'operation_absent_final' })],
    ['wrong operation', finalAbsenceError({ client_operation_id: '30000000-0000-4000-8000-000000000099' })],
    ['wrong actor', finalAbsenceError({ actor_user_id: OTHER_ACTOR_ID })],
    ['wrong organization', finalAbsenceError({ organization_id: OTHER_ORGANIZATION_ID })],
    ['missing actor', new ApiError(404, 'not found', { detail: { code: 'operation_finalized_absent', message: 'terminal', client_operation_id: OPERATION_ID, organization_id: ORGANIZATION_ID } })],
    ['missing message', new ApiError(404, 'not found', { detail: { code: 'operation_finalized_absent', actor_user_id: ACTOR_ID, client_operation_id: OPERATION_ID, organization_id: ORGANIZATION_ID } })],
    ['extra proof field', finalAbsenceError({ proof_version: 1 })],
  ])('keeps %s unresolved instead of treating it as terminal absence', async (_label, failure) => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    await journalCoordinator.prepareNew(input());
    const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => { throw failure; });

    await expect(service.reconcile(input())).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'absence_not_finalized',
      entry: { status: 'blocked' },
    });
    expect(await journalCoordinator.get(input())).not.toBeNull();
    journalCoordinator.close();
  });

  it.each([
    ['authentication_required', new ApiError(401, 'Sign in')],
    ['permission_denied', new ApiError(403, 'Forbidden')],
    ['server_unavailable', new ApiError(503, 'Unavailable')],
    ['offline', new TypeError('Failed to fetch')],
    ['protocol_failure', new ApiError(409, 'Invalid receipt')],
  ] as const)('retains the lane for %s failures', async (reason, failure) => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    await journalCoordinator.prepareNew(input());
    const service = new ChildcareCommandRecoveryService(
      journalCoordinator,
      async () => { throw failure; },
    );

    await expect(service.reconcile(input())).resolves.toMatchObject({
      kind: 'blocked',
      reason,
      entry: { status: 'blocked' },
    });
    expect(await journalCoordinator.listLane(input())).toHaveLength(1);
    journalCoordinator.close();
  });

  it('blocks organization, command, target, and action-route mismatches without clearing', async () => {
    for (const mismatchedReceipt of [
      receipt({ organizationId: OTHER_ORGANIZATION_ID }),
      receipt({ commandType: 'family.create' }),
      receipt({ targetId: '40000000-0000-4000-8000-000000000002', actionRoute: '/families/40000000-0000-4000-8000-000000000002' }),
      receipt({ actionRoute: '/families/40000000-0000-4000-8000-000000000002' }),
    ]) {
      const state = createMemoryCommandJournalState();
      const journalCoordinator = coordinator(state, OWNER_ONE);
      await journalCoordinator.prepareNew(input());
      const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => mismatchedReceipt);

      await expect(service.reconcile(input())).resolves.toMatchObject({
        kind: 'blocked',
        entry: { status: 'blocked' },
      });
      expect(await journalCoordinator.get(input())).not.toBeNull();
      journalCoordinator.close();
    }
  });

  it('rejects an enrollment receipt whose action route belongs to a different child', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    const enrollmentId = '60000000-0000-4000-8000-000000000001';
    const owningChildId = '70000000-0000-4000-8000-000000000001';
    const foreignChildId = '70000000-0000-4000-8000-000000000002';
    const enrollmentInput = {
      ...input(),
      commandType: 'enrollment.update' as const,
      targetType: 'enrollment' as const,
      expectedTargetId: enrollmentId,
      expectedActionOwnerId: owningChildId,
    };
    await journalCoordinator.prepareNew(enrollmentInput);
    const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => receipt({
      commandType: 'enrollment.update',
      targetType: 'enrollment',
      targetId: enrollmentId,
      actionRoute: `/children/${foreignChildId}?enrollment_id=${enrollmentId}`,
    }));

    await expect(service.reconcile(enrollmentInput)).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'receipt_mismatch',
      entry: { status: 'blocked' },
    });
    expect(await journalCoordinator.get(enrollmentInput)).not.toBeNull();
    journalCoordinator.close();
  });

  it('rejects a child-authority receipt whose action route belongs to a different child', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    const authorizationId = '60000000-0000-4000-8000-000000000001';
    const owningChildId = '70000000-0000-4000-8000-000000000001';
    const foreignChildId = '70000000-0000-4000-8000-000000000002';
    const authorizationInput = {
      ...input(),
      commandType: 'child.release.authorization.revoke' as const,
      targetType: 'release_authorization' as const,
      expectedTargetId: authorizationId,
      expectedActionOwnerId: owningChildId,
    };
    await journalCoordinator.prepareNew(authorizationInput);
    const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => receipt({
      commandType: 'child.release.authorization.revoke',
      targetType: 'release_authorization',
      targetId: authorizationId,
      actionRoute: `/children/${foreignChildId}?release_authorization_id=${authorizationId}`,
    }));

    await expect(service.reconcile(authorizationInput)).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'receipt_mismatch',
      entry: { status: 'blocked' },
    });
    expect(await journalCoordinator.get(authorizationInput)).not.toBeNull();
    journalCoordinator.close();
  });

  it('never downgrades previously observed commit evidence when a later receipt read returns 404', async () => {
    const state = createMemoryCommandJournalState();
    const journalCoordinator = coordinator(state, OWNER_ONE);
    await journalCoordinator.prepareNew(input());
    let found = true;
    const service = new ChildcareCommandRecoveryService(journalCoordinator, async () => {
      if (!found) throw new ApiError(404, 'not found');
      return receipt();
    });
    await service.reconcile(input());
    found = false;

    await expect(service.reconcile(input())).resolves.toMatchObject({
      kind: 'blocked',
      reason: 'receipt_disappeared_after_commit',
      entry: { status: 'committed_needs_refresh' },
    });
    expect(await journalCoordinator.get(input())).toMatchObject({ status: 'committed_needs_refresh' });
    journalCoordinator.close();
  });
});
