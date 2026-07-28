import { describe, expect, it, vi } from 'vitest';
import {
  ChildcareCommandRuntimeOwner,
  ChildcareCommandNotPreparedError,
  ChildcareCommandResolutionRequiredError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareJournalEntryMatchesMutation,
  childcareMutationControlDisabled,
  createChildcareCommandRuntimeFactory,
  isCurrentChildcareRecoveryIdentity,
  readCanonicalChildcareRefresh,
} from './ChildcareCommandRecoveryContext';
import {
  createMemoryCommandJournalState,
  MemoryChildcareCommandJournalAdapter,
} from '../api/childcareCommandJournal';
import type { ChildcareCommandReceipt } from '../api/childcareCommandReceipt';

const ACTOR_ONE = '10000000-0000-4000-8000-000000000001';
const ACTOR_TWO = '10000000-0000-4000-8000-000000000002';
const ORGANIZATION_ONE = '20000000-0000-4000-8000-000000000001';
const ORGANIZATION_TWO = '20000000-0000-4000-8000-000000000002';
const OPERATION_ONE = '30000000-0000-4000-8000-000000000001';
const OPERATION_TWO = '30000000-0000-4000-8000-000000000002';
const ADMISSION_APPLICATION_ID = '40000000-0000-4000-8000-000000000001';
const HISTORICAL_OFFER_ID = '50000000-0000-4000-8000-000000000001';

describe('authenticated childcare command runtime boundary', () => {
  it('creates a fresh coordinator after StrictMode-style setup, cleanup, and setup', async () => {
    const state = createMemoryCommandJournalState();
    const owner = new ChildcareCommandRuntimeOwner(createChildcareCommandRuntimeFactory(
      () => new MemoryChildcareCommandJournalAdapter(state),
    ));
    const identity = `${ACTOR_ONE}:${ORGANIZATION_ONE}`;
    const first = owner.activate(identity);
    const closeFirst = vi.spyOn(first.coordinator, 'close');

    owner.deactivate(first);
    const second = owner.activate(identity);

    expect(closeFirst).toHaveBeenCalledTimes(1);
    expect(second).not.toBe(first);
    expect(second.coordinator).not.toBe(first.coordinator);
    await expect(second.coordinator.listLane(second.scope)).resolves.toEqual([]);
    owner.deactivate(second);
  });

  it('keeps every mutation or confirmation control disabled while the lane is blocked', () => {
    expect(childcareMutationControlDisabled(true)).toBe(true);
    expect(childcareMutationControlDisabled(true, false, false)).toBe(true);
    expect(childcareMutationControlDisabled(false, true)).toBe(true);
    expect(childcareMutationControlDisabled(false, false, false)).toBe(false);
  });

  it('never attributes another tab\'s actor-lane entry to the current mutation', async () => {
    const state = createMemoryCommandJournalState();
    const adapter = new MemoryChildcareCommandJournalAdapter(state);
    const entry = await adapter.createPrepared({
      actorUserId: ACTOR_ONE,
      organizationId: ORGANIZATION_ONE,
      clientOperationId: OPERATION_ONE,
      commandType: 'family.update',
      targetType: 'family',
      expectedTargetId: '40000000-0000-4000-8000-000000000001',
      expectedActionOwnerId: null,
    });

    expect(childcareJournalEntryMatchesMutation(entry, {
      clientOperationId: OPERATION_ONE,
      commandType: 'family.update',
      targetType: 'family',
      expectedTargetId: '40000000-0000-4000-8000-000000000001',
      expectedActionOwnerId: null,
    })).toBe(true);
    expect(childcareJournalEntryMatchesMutation(entry, {
      clientOperationId: OPERATION_TWO,
      commandType: 'family.update',
      targetType: 'family',
      expectedTargetId: '40000000-0000-4000-8000-000000000002',
      expectedActionOwnerId: null,
    })).toBe(false);
    expect(childcareJournalEntryMatchesMutation(entry, {
      clientOperationId: OPERATION_ONE,
      commandType: 'family.emergency_contacts.replace',
      targetType: 'family',
      expectedTargetId: '40000000-0000-4000-8000-000000000001',
      expectedActionOwnerId: null,
    })).toBe(false);
  });

  it('distinguishes an operation that never entered the lane from an unresolved prepared operation', () => {
    const notPrepared = new ChildcareCommandNotPreparedError(OPERATION_ONE, 'blocked before persistence', OPERATION_TWO);
    expect(childcareCommandWasNotPrepared(notPrepared, OPERATION_ONE)).toBe(true);
    expect(childcareCommandWasNotPrepared(notPrepared, OPERATION_TWO)).toBe(false);
    expect(notPrepared.operationPrepared).toBe(false);
    expect(notPrepared.outcomeUnknown).toBe(false);
    expect(notPrepared.blockingOperationId).toBe(OPERATION_TWO);
    expect(childcareCommandWasNotPrepared(new Error('unknown outcome'), OPERATION_ONE)).toBe(false);
    expect(new ChildcareCommandResolutionRequiredError('receipt pending').outcomeUnknown).toBe(true);
  });

  it('unlocks only the local form whose exact terminal-absence operation was acknowledged', () => {
    expect(childcareFinalAbsenceAcknowledged(OPERATION_ONE, OPERATION_ONE)).toBe(true);
    expect(childcareFinalAbsenceAcknowledged(OPERATION_ONE, OPERATION_TWO)).toBe(false);
    expect(childcareFinalAbsenceAcknowledged(null, OPERATION_ONE)).toBe(false);
  });

  it('rejects a delayed old-organization completion after an identity generation changes', async () => {
    let finishOldScan!: () => void;
    const oldScan = new Promise<void>((resolve) => { finishOldScan = resolve; });
    const oldIdentity = `${ACTOR_ONE}:${ORGANIZATION_ONE}`;
    const newIdentity = `${ACTOR_TWO}:${ORGANIZATION_TWO}`;
    let currentIdentity = oldIdentity;
    let currentGeneration = 8;
    let oldResultApplied = false;

    const delayedCompletion = oldScan.then(() => {
      if (isCurrentChildcareRecoveryIdentity(oldIdentity, 8, currentIdentity, currentGeneration)) {
        oldResultApplied = true;
      }
    });
    currentIdentity = newIdentity;
    currentGeneration = 9;
    finishOldScan();
    await delayedCompletion;

    expect(oldResultApplied).toBe(false);
    expect(isCurrentChildcareRecoveryIdentity(newIdentity, 9, currentIdentity, currentGeneration)).toBe(true);
  });

  it('refreshes the admission owner without requiring a superseded nested target to remain current', async () => {
    const receipt: ChildcareCommandReceipt = {
      organizationId: ORGANIZATION_ONE,
      clientOperationId: OPERATION_ONE,
      commandType: 'admission.offer.issue',
      targetType: 'admission_offer',
      targetId: HISTORICAL_OFFER_ID,
      committedVersion: 1,
      committedAt: '2026-07-23T03:00:00Z',
      facilityId: null,
      actionRoute: `/admissions/applications/${ADMISSION_APPLICATION_ID}`,
    };
    const currentOfferId = '50000000-0000-4000-8000-000000000002';
    const loader = vi.fn(async () => ({
      id: ADMISSION_APPLICATION_ID,
      organization_id: ORGANIZATION_ONE,
      version: 12,
      offer: { id: currentOfferId, version: 4 },
      waitlist: null,
    } as any));

    await expect(readCanonicalChildcareRefresh(receipt, loader)).resolves.toEqual({
      organizationId: ORGANIZATION_ONE,
      targetType: 'admission_application',
      targetId: ADMISSION_APPLICATION_ID,
      version: 12,
    });
    expect(loader).toHaveBeenCalledWith(
      ORGANIZATION_ONE,
      ADMISSION_APPLICATION_ID,
    );
    await expect(loader.mock.results[0].value).resolves.toMatchObject({
      offer: { id: currentOfferId },
    });

    const crossedIdentityLoader = vi.fn(async () => ({
      id: ADMISSION_APPLICATION_ID,
      organization_id: ORGANIZATION_TWO,
      version: 12,
    } as any));
    await expect(readCanonicalChildcareRefresh(receipt, crossedIdentityLoader))
      .rejects.toThrow(/identity boundary/i);
  });
});
