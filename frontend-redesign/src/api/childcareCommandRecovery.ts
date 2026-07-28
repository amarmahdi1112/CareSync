import { ApiError } from './client';
import { isCommandRejectedBeforeCommit } from './childcareCommand';
import {
  ChildcareCommandJournalCoordinator,
  ChildcareCommandLeaseLostError,
  type ChildcareCommandLeaseFence,
} from './childcareCommandCoordinator';
import {
  ChildcareCommandJournalStateError,
  type ChildcareCommandJournalEntry,
  type ChildcareCommandJournalRef,
  type PrepareChildcareCommandInput,
} from './childcareCommandJournal';
import {
  assertChildcareCommandActionRouteBinding,
  childcareCommandAdmissionOwnerId,
  childcareCommandAuthorityFamilyId,
  childcareCommandChildAuthorityOwnerId,
  childcareCommandEnrollmentOwnerId,
  ChildcareCommandReceiptProtocolError,
  fetchChildcareCommandReceipt,
  type ChildcareCommandReceipt,
  type ChildcareCommandTargetType,
} from './childcareCommandReceipt';

export class ChildcareCommandReceiptMismatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChildcareCommandReceiptMismatchError';
  }
}

export class ChildcareCommandLeaseUnavailableError extends Error {
  constructor() {
    super('Another CareSync tab is already sending or reconciling this childcare mutation lane.');
    this.name = 'ChildcareCommandLeaseUnavailableError';
  }
}

export type ChildcareCommandReconciliationBlockReason =
  | 'lease_held_by_another_tab'
  | 'authentication_required'
  | 'permission_denied'
  | 'offline'
  | 'server_unavailable'
  | 'protocol_failure'
  | 'receipt_mismatch'
  | 'absence_not_finalized'
  | 'receipt_disappeared_after_commit';

export type ChildcareCommandReconciliationResult =
  | {
      readonly kind: 'committed_needs_refresh';
      readonly entry: ChildcareCommandJournalEntry;
      readonly receipt: ChildcareCommandReceipt;
      readonly actionRoute: string;
    }
  | {
      readonly kind: 'absent_final';
      readonly entry: ChildcareCommandJournalEntry;
      readonly clientOperationId: string;
      readonly newOperationRequired: true;
    }
  | {
      readonly kind: 'blocked';
      readonly entry: ChildcareCommandJournalEntry;
      readonly reason: ChildcareCommandReconciliationBlockReason;
    };

export type ChildcareCommandFinalizedInspection =
  | {
      readonly kind: 'committed';
      readonly receipt: ChildcareCommandReceipt;
      readonly actionRoute: string;
    }
  | {
      readonly kind: 'absent_final';
      readonly clientOperationId: string;
    }
  | {
      readonly kind: 'blocked';
      readonly reason: ChildcareCommandReconciliationBlockReason;
    };

export interface CanonicalChildcareRecordAcknowledgement {
  readonly organizationId: string;
  /**
   * Usually the receipt target. Historical admission waitlist/offer receipts
   * are instead acknowledged by a fresh read of their owning application,
   * because a newer nested record may have superseded the original target.
   */
  readonly targetType: ChildcareCommandTargetType;
  readonly targetId: string;
  /** The version returned by a fresh primary/canonical record read. */
  readonly version: number;
}

export interface FinalAbsenceOperatorAcknowledgement {
  readonly reviewed: true;
  readonly newOperationRequired: true;
}

export type ChildcareCommandReceiptLoader = (
  clientOperationId: string,
) => Promise<ChildcareCommandReceipt>;

function refFromEntry(entry: ChildcareCommandJournalEntry): ChildcareCommandJournalRef {
  return {
    actorUserId: entry.actorUserId,
    organizationId: entry.organizationId,
    clientOperationId: entry.clientOperationId,
  };
}

function assertReceiptMatchesJournal(
  entry: ChildcareCommandJournalEntry,
  receipt: ChildcareCommandReceipt,
): void {
  assertChildcareCommandActionRouteBinding(receipt);
  if (
    receipt.organizationId !== entry.organizationId
    || receipt.clientOperationId !== entry.clientOperationId
    || receipt.commandType !== entry.commandType
    || receipt.targetType !== entry.targetType
    || (entry.expectedTargetId !== null && receipt.targetId !== entry.expectedTargetId)
    || (receipt.targetType === 'enrollment'
      && childcareCommandEnrollmentOwnerId(receipt) !== entry.expectedActionOwnerId)
    || (receipt.targetType.startsWith('authority_')
      && childcareCommandAuthorityFamilyId(receipt) !== entry.expectedActionOwnerId)
    || ((receipt.targetType === 'admission_waitlist' || receipt.targetType === 'admission_offer')
      && childcareCommandAdmissionOwnerId(receipt) !== entry.expectedActionOwnerId)
    || ((receipt.targetType === 'release_authorization' || receipt.targetType === 'release_rule' || (receipt.targetType === 'consent' && receipt.commandType !== 'organization.consent.policy.publish'))
      && childcareCommandChildAuthorityOwnerId(receipt) !== entry.expectedActionOwnerId)
    || (receipt.targetType !== 'enrollment'
      && !receipt.targetType.startsWith('authority_')
      && receipt.targetType !== 'release_authorization'
      && receipt.targetType !== 'release_rule'
      && receipt.targetType !== 'admission_waitlist'
      && receipt.targetType !== 'admission_offer'
      && !(receipt.targetType === 'consent' && receipt.commandType !== 'organization.consent.policy.publish')
      && entry.expectedActionOwnerId !== null)
  ) {
    throw new ChildcareCommandReceiptMismatchError(
      'The durable command receipt does not match the pending actor, organization, operation, command, or target.',
    );
  }
}

async function retainBlocked(
  coordinator: ChildcareCommandJournalCoordinator,
  entry: ChildcareCommandJournalEntry,
  fence: ChildcareCommandLeaseFence,
): Promise<ChildcareCommandJournalEntry> {
  // Once commit evidence has been observed, a later transport/server problem
  // must never downgrade it to an unresolved or absent command.
  if (entry.status === 'committed_needs_refresh' || entry.status === 'absent_final') return entry;
  await fence.assertOwned();
  const blocked = await coordinator.transition(
    refFromEntry(entry),
    ['prepared', 'blocked'],
    'blocked',
  );
  await fence.assertOwned();
  return blocked;
}

function classifyFailure(caught: unknown): Exclude<ChildcareCommandReconciliationBlockReason, 'lease_held_by_another_tab' | 'receipt_disappeared_after_commit'> {
  if (caught instanceof ChildcareCommandReceiptMismatchError) return 'receipt_mismatch';
  if (caught instanceof ChildcareCommandReceiptProtocolError) return 'protocol_failure';
  if (caught instanceof ApiError) {
    if (caught.status === 401) return 'authentication_required';
    if (caught.status === 403) return 'permission_denied';
    if (caught.status >= 500 || caught.status === 408 || caught.status === 425 || caught.status === 429) {
      return 'server_unavailable';
    }
    return 'protocol_failure';
  }
  if (caught instanceof TypeError || (caught instanceof DOMException && caught.name === 'AbortError')) return 'offline';
  return 'protocol_failure';
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  return actual.length === sortedExpected.length
    && actual.every((key, index) => key === sortedExpected[index]);
}

function isFinalAbsenceProof(error: ApiError, entry: ChildcareCommandJournalEntry): boolean {
  if (error.status !== 404 || !error.details || typeof error.details !== 'object' || Array.isArray(error.details)) return false;
  const payload = error.details as Record<string, unknown>;
  if (!exactKeys(payload, ['detail'])) return false;
  if (!payload.detail || typeof payload.detail !== 'object' || Array.isArray(payload.detail)) return false;
  const detail = payload.detail as Record<string, unknown>;
  return exactKeys(detail, ['code', 'message', 'actor_user_id', 'client_operation_id', 'organization_id'])
    && detail.code === 'operation_finalized_absent'
    && typeof detail.message === 'string'
    && detail.message.trim().length > 0
    && typeof detail.client_operation_id === 'string'
    && detail.client_operation_id.toLowerCase() === entry.clientOperationId
    && typeof detail.actor_user_id === 'string'
    && detail.actor_user_id.toLowerCase() === entry.actorUserId
    && typeof detail.organization_id === 'string'
    && detail.organization_id.toLowerCase() === entry.organizationId;
}

export class ChildcareCommandRecoveryService {
  constructor(
    readonly coordinator: ChildcareCommandJournalCoordinator,
    private readonly receiptLoader: ChildcareCommandReceiptLoader = fetchChildcareCommandReceipt,
  ) {}

  /**
   * Re-inspect a command that this tab observed before another tab passed the
   * durable deletion gate. The actor-private receipt/tombstone remains the
   * authority; disappearance alone is never interpreted as success.
   */
  async inspectFinalizedOperation(
    entry: ChildcareCommandJournalEntry,
  ): Promise<ChildcareCommandFinalizedInspection> {
    try {
      const receipt = await this.receiptLoader(entry.clientOperationId);
      assertReceiptMatchesJournal(entry, receipt);
      return { kind: 'committed', receipt, actionRoute: receipt.actionRoute };
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        if (entry.status === 'committed_needs_refresh') {
          return { kind: 'blocked', reason: 'receipt_disappeared_after_commit' };
        }
        if (isFinalAbsenceProof(caught, entry)) {
          return {
            kind: 'absent_final',
            clientOperationId: entry.clientOperationId,
          };
        }
        return { kind: 'blocked', reason: 'absence_not_finalized' };
      }
      return { kind: 'blocked', reason: classifyFailure(caught) };
    }
  }

  /**
   * The durable write completes before the caller's network closure can run.
   * A validated mutation response still does not clear the journal: the
   * actor-private receipt and canonical record must be reconciled separately.
   */
  async persistBeforeSend<Result>(
    input: PrepareChildcareCommandInput,
    send: (clientOperationId: string) => Promise<Result>,
    onPrepared?: (entry: ChildcareCommandJournalEntry) => void,
  ): Promise<{ readonly entry: ChildcareCommandJournalEntry; readonly response: Result }> {
    const leased = await this.coordinator.runWithReconciliationLease(input, async (fence) => {
      const entry = await this.coordinator.prepareNew(input);
      try {
        onPrepared?.(entry);
        await fence.assertOwned();
        const response = await send(entry.clientOperationId);
        await fence.assertOwned();
        return { entry, response };
      } catch (caught) {
        if (caught instanceof ChildcareCommandLeaseLostError) throw caught;
        if (isCommandRejectedBeforeCommit(caught)) {
          try {
            await fence.assertOwned();
            await this.coordinator.clearPreparedAfterAuthoritativeRejection(refFromEntry(entry));
            throw caught;
          } catch (journalFailure) {
            if (journalFailure === caught) throw caught;
            if (journalFailure instanceof ChildcareCommandLeaseLostError) throw journalFailure;
            // If the dedicated deletion gate fails, retain the durable row and
            // fall through to ordinary receipt reconciliation. A storage
            // failure must never convert a response into permission to retry.
          }
        }
        try {
          await fence.assertOwned();
          await this.coordinator.transition(
            refFromEntry(entry),
            ['prepared'],
            'blocked',
          );
          await fence.assertOwned();
        } catch (journalFailure) {
          if (journalFailure instanceof ChildcareCommandLeaseLostError) throw journalFailure;
          // Preserve the network failure. The durable row remains fail-closed
          // and the provider will re-read its actual state before any retry.
        }
        throw caught;
      }
    });
    if (!leased.acquired) throw new ChildcareCommandLeaseUnavailableError();
    return leased.value!;
  }

  /**
   * Reconcile one persisted command. The receipt endpoint takes the same
   * server operation lock as the writer. Only the strict, durable terminal-
   * absence proof is authoritative; a generic 404 remains unresolved.
   */
  async reconcile(ref: ChildcareCommandJournalRef): Promise<ChildcareCommandReconciliationResult> {
    const initial = await this.coordinator.get(ref);
    if (!initial) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');

    const leased = await this.coordinator.runWithReconciliationLease(initial, async (fence) => {
      const entry = await this.coordinator.get(ref);
      if (!entry) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (entry.status === 'absent_final') {
        return {
          kind: 'absent_final',
          entry,
          clientOperationId: entry.clientOperationId,
          newOperationRequired: true,
        } as const;
      }
      try {
        await fence.assertOwned();
        const receipt = await this.receiptLoader(entry.clientOperationId);
        await fence.assertOwned();
        assertReceiptMatchesJournal(entry, receipt);
        await fence.assertOwned();
        const committed = await this.coordinator.transition(
          refFromEntry(entry),
          ['prepared', 'blocked', 'committed_needs_refresh'],
          'committed_needs_refresh',
        );
        await fence.assertOwned();
        return {
          kind: 'committed_needs_refresh',
          entry: committed,
          receipt,
          actionRoute: receipt.actionRoute,
        } as const;
      } catch (caught) {
        if (caught instanceof ChildcareCommandLeaseLostError) throw caught;
        await fence.assertOwned();
        if (caught instanceof ApiError && caught.status === 404) {
          if (entry.status === 'committed_needs_refresh') {
            return {
              kind: 'blocked',
              entry,
              reason: 'receipt_disappeared_after_commit',
            } as const;
          }
          if (isFinalAbsenceProof(caught, entry)) {
            await fence.assertOwned();
            const absent = await this.coordinator.transition(
              refFromEntry(entry),
              ['prepared', 'blocked'],
              'absent_final',
            );
            await fence.assertOwned();
            return {
              kind: 'absent_final',
              entry: absent,
              clientOperationId: absent.clientOperationId,
              newOperationRequired: true,
            } as const;
          }
          return {
            kind: 'blocked',
            entry: await retainBlocked(this.coordinator, entry, fence),
            reason: 'absence_not_finalized',
          } as const;
        }
        return {
          kind: 'blocked',
          entry: await retainBlocked(this.coordinator, entry, fence),
          reason: classifyFailure(caught),
        } as const;
      }
    });

    if (!leased.acquired) {
      const entry = await this.coordinator.get(ref);
      if (!entry) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      return { kind: 'blocked', entry, reason: 'lease_held_by_another_tab' };
    }
    return leased.value!;
  }

  async acknowledgeFinalAbsence(
    ref: ChildcareCommandJournalRef,
    acknowledgement: FinalAbsenceOperatorAcknowledgement,
  ): Promise<void> {
    if (acknowledgement.reviewed !== true || acknowledgement.newOperationRequired !== true) {
      throw new ChildcareCommandJournalStateError('Final absence requires explicit operator acknowledgement and a reviewed new operation.');
    }
    const initial = await this.coordinator.get(ref);
    if (!initial) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    const leased = await this.coordinator.runWithReconciliationLease(initial, async (fence) => {
      const entry = await this.coordinator.get(ref);
      if (!entry) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (entry.status !== 'absent_final') {
        throw new ChildcareCommandJournalStateError('Only a server-finalized absent command can be retired.');
      }
      await fence.assertOwned();
      await this.coordinator.retireFinalAbsenceAfterAcknowledgement(ref);
      await fence.assertOwned();
    });
    if (!leased.acquired) throw new ChildcareCommandLeaseUnavailableError();
  }

  /**
   * A journal entry is deleted only after the caller confirms a fresh
   * canonical read for the receipt target. A newer version is acceptable;
   * another actor may have committed a later valid command before refresh.
   */
  async acknowledgeCanonicalRefresh(
    ref: ChildcareCommandJournalRef,
    receipt: ChildcareCommandReceipt,
    acknowledgement: CanonicalChildcareRecordAcknowledgement,
  ): Promise<void> {
    const initial = await this.coordinator.get(ref);
    if (!initial) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    const leased = await this.coordinator.runWithReconciliationLease(initial, async (fence) => {
      const entry = await this.coordinator.get(ref);
      if (!entry) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (entry.status !== 'committed_needs_refresh') {
        throw new ChildcareCommandJournalStateError('Canonical refresh cannot clear a command before commit is confirmed.');
      }
      assertReceiptMatchesJournal(entry, receipt);
      const historicalAdmissionTarget = receipt.targetType === 'admission_waitlist'
        || receipt.targetType === 'admission_offer';
      const acknowledgementMatches = historicalAdmissionTarget
        ? acknowledgement.organizationId === receipt.organizationId
          && acknowledgement.targetType === 'admission_application'
          && acknowledgement.targetId === childcareCommandAdmissionOwnerId(receipt)
          && Number.isInteger(acknowledgement.version)
          && acknowledgement.version >= 1
        : acknowledgement.organizationId === receipt.organizationId
          && acknowledgement.targetType === receipt.targetType
          && acknowledgement.targetId === receipt.targetId
          && Number.isInteger(acknowledgement.version)
          && acknowledgement.version >= receipt.committedVersion;
      if (!acknowledgementMatches) {
        throw new ChildcareCommandReceiptMismatchError(
          'The canonical refresh acknowledgement does not match the committed receipt or its canonical action owner.',
        );
      }
      await fence.assertOwned();
      await this.coordinator.clearCommittedAfterRefresh(ref);
      await fence.assertOwned();
    });
    if (!leased.acquired) throw new ChildcareCommandLeaseUnavailableError();
  }
}
