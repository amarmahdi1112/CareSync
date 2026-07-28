import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useSession } from '../auth/SessionContext';
import { fetchChildProfile } from '../features/children/childrenApi';
import { fetchFamilyDetail } from '../features/families/familiesApi';
import { fetchConsentPolicies, fetchFamilyAuthorityWorkspace } from '../features/families/familyAuthorityApi';
import { fetchAdmissionApplication } from '../features/admissions/admissionsDecisionApi';
import { ChildcareCommandJournalCoordinator } from '../api/childcareCommandCoordinator';
import { isCommandRejectedBeforeCommit } from '../api/childcareCommand';
import {
  ChildcareCommandJournalUnavailableError,
  ChildcareCommandLaneBlockedError,
  IndexedDbChildcareCommandJournalAdapter,
  type ChildcareCommandJournalAdapter,
  type ChildcareCommandJournalEntry,
  type ChildcareCommandJournalRef,
  type ChildcareCommandJournalScope,
} from '../api/childcareCommandJournal';
import {
  ChildcareCommandRecoveryService,
  ChildcareCommandLeaseUnavailableError,
  type CanonicalChildcareRecordAcknowledgement,
  type ChildcareCommandReconciliationBlockReason,
} from '../api/childcareCommandRecovery';
import type {
  ChildcareCommandReceipt,
  ChildcareCommandTargetType,
  ChildcareCommandType,
} from '../api/childcareCommandReceipt';
import {
  childcareCommandAdmissionOwnerId,
  childcareCommandAuthorityFamilyId,
  childcareCommandChildAuthorityOwnerId,
} from '../api/childcareCommandReceipt';

export interface ChildcareMutationMetadata {
  readonly clientOperationId: string;
  readonly commandType: ChildcareCommandType;
  readonly targetType: ChildcareCommandTargetType;
  readonly expectedTargetId: string | null;
  readonly expectedActionOwnerId: string | null;
}

export interface ResolvedChildcareCommand {
  readonly clientOperationId: string;
  readonly actionRoute: string;
  readonly targetType: ChildcareCommandTargetType;
  readonly targetId: string;
  readonly version: number;
}

export type ChildcareRecoveryBlockReason =
  | ChildcareCommandReconciliationBlockReason
  | 'canonical_refresh_failed'
  | 'durable_storage_unavailable';

export class ChildcareCommandResolutionRequiredError extends Error {
  readonly resolutionRequired = true;
  readonly outcomeUnknown: boolean = true;

  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = 'ChildcareCommandResolutionRequiredError';
  }
}

/** The attempted operation never entered the durable lane and may be rebuilt safely. */
export class ChildcareCommandNotPreparedError extends ChildcareCommandResolutionRequiredError {
  readonly operationPrepared = false;
  override readonly outcomeUnknown: boolean = false;

  constructor(
    public readonly clientOperationId: string,
    message: string,
    public readonly blockingOperationId: string | null = null,
    cause?: unknown,
  ) {
    super(message, cause);
    this.name = 'ChildcareCommandNotPreparedError';
  }
}

export function childcareCommandWasNotPrepared(caught: unknown, clientOperationId: string): boolean {
  return caught instanceof ChildcareCommandNotPreparedError
    && caught.clientOperationId === clientOperationId;
}

export function childcareFinalAbsenceAcknowledged(
  pendingOperationId: string | null,
  acknowledgedOperationId: string | null,
): boolean {
  return Boolean(pendingOperationId && pendingOperationId === acknowledgedOperationId);
}

export class ChildcareCommandRecoveredCommitError extends Error {
  readonly recoveredCommit = true;

  constructor(public readonly resolution: ResolvedChildcareCommand) {
    super('CareSync confirmed that the interrupted change was saved and refreshed the canonical record.');
    this.name = 'ChildcareCommandRecoveredCommitError';
  }
}

export interface ChildcareCommandRuntime {
  readonly identityKey: string;
  readonly scope: ChildcareCommandJournalScope;
  readonly coordinator: ChildcareCommandJournalCoordinator;
  readonly recovery: ChildcareCommandRecoveryService;
}

type RuntimeFactory = (scope: ChildcareCommandJournalScope, identityKey: string) => ChildcareCommandRuntime;

function defaultRuntimeFactory(scope: ChildcareCommandJournalScope, identityKey: string): ChildcareCommandRuntime {
  const coordinator = new ChildcareCommandJournalCoordinator(
    new IndexedDbChildcareCommandJournalAdapter(),
  );
  return { identityKey, scope, coordinator, recovery: new ChildcareCommandRecoveryService(coordinator) };
}

/** Owns effect-scoped runtimes so React StrictMode cleanup can never reuse a closed channel. */
export class ChildcareCommandRuntimeOwner {
  private current: ChildcareCommandRuntime | null = null;

  constructor(private readonly factory: RuntimeFactory = defaultRuntimeFactory) {}

  activate(identityKey: string): ChildcareCommandRuntime {
    const [actorUserId, organizationId, extra] = identityKey.split(':');
    if (!actorUserId || !organizationId || extra !== undefined) throw new Error('A complete actor and organization identity is required.');
    this.current?.coordinator.close();
    const runtime = this.factory({ actorUserId, organizationId }, identityKey);
    this.current = runtime;
    return runtime;
  }

  deactivate(runtime: ChildcareCommandRuntime): void {
    runtime.coordinator.close();
    if (this.current === runtime) this.current = null;
  }
}

export function createChildcareCommandRuntimeFactory(
  adapterFactory: () => ChildcareCommandJournalAdapter,
): RuntimeFactory {
  return (scope, identityKey) => {
    const coordinator = new ChildcareCommandJournalCoordinator(adapterFactory());
    return { identityKey, scope, coordinator, recovery: new ChildcareCommandRecoveryService(coordinator) };
  };
}

export function isCurrentChildcareRecoveryIdentity(
  runtimeIdentityKey: string,
  runtimeGenerationValue: number,
  currentIdentityKey: string,
  currentGenerationValue: number,
): boolean {
  return runtimeIdentityKey === currentIdentityKey && runtimeGenerationValue === currentGenerationValue;
}

/** Mutation/confirmation controls fail closed whenever the shared lane is blocked. */
export function childcareMutationControlDisabled(
  laneBlocked: boolean,
  ...localLocks: readonly boolean[]
): boolean {
  return laneBlocked || localLocks.some(Boolean);
}

/** Never attribute another tab's durable command to the current mutation call. */
export function childcareJournalEntryMatchesMutation(
  entry: ChildcareCommandJournalEntry,
  metadata: ChildcareMutationMetadata,
): boolean {
  return entry.clientOperationId === metadata.clientOperationId
    && entry.commandType === metadata.commandType
    && entry.targetType === metadata.targetType
    && entry.expectedTargetId === metadata.expectedTargetId
    && entry.expectedActionOwnerId === metadata.expectedActionOwnerId;
}

type ResolutionOutcome =
  | { readonly kind: 'resolved'; readonly resolution: ResolvedChildcareCommand }
  | { readonly kind: 'blocked' }
  | { readonly kind: 'absent_final' };

export interface ChildcareCommandRecoveryValue {
  readonly activeEntry: ChildcareCommandJournalEntry | null;
  readonly blockReason: ChildcareRecoveryBlockReason | null;
  readonly checking: boolean;
  readonly ready: boolean;
  readonly laneBlocked: boolean;
  readonly lastResolved: ResolvedChildcareCommand | null;
  readonly lastFinalAbsenceAcknowledgedOperationId: string | null;
  execute<Result>(metadata: ChildcareMutationMetadata, send: (operationId: string) => Promise<Result>): Promise<Result>;
  checkSavedResult(): Promise<void>;
  acknowledgeFinalAbsence(): Promise<void>;
  dismissResolved(): void;
}

export const ChildcareCommandRecoveryContext = createContext<ChildcareCommandRecoveryValue | null>(null);

function journalRef(entry: ChildcareCommandJournalEntry): ChildcareCommandJournalRef {
  return {
    actorUserId: entry.actorUserId,
    organizationId: entry.organizationId,
    clientOperationId: entry.clientOperationId,
  };
}

function enrollmentChildId(receipt: ChildcareCommandReceipt): string {
  const parsed = new URL(receipt.actionRoute, 'https://caresync.invalid');
  const match = /^\/children\/([0-9a-f-]+)$/i.exec(parsed.pathname);
  if (!match) throw new Error('The committed enrollment route did not identify its owning child.');
  return match[1].toLowerCase();
}

type AdmissionApplicationLoader = typeof fetchAdmissionApplication;

function canonicalRefresh(
  receipt: ChildcareCommandReceipt,
  targetType: ChildcareCommandTargetType,
  targetId: string,
  version: number,
): CanonicalChildcareRecordAcknowledgement {
  if (!Number.isInteger(version) || version < 1) {
    throw new Error('The refreshed canonical record returned an invalid version.');
  }
  return {
    organizationId: receipt.organizationId,
    targetType,
    targetId,
    version,
  };
}

/**
 * Refresh the canonical record that proves the receipt's action route is now
 * readable. Historical admission waitlist/offer receipts intentionally refresh
 * their owning application; they do not claim the old nested row is current.
 */
export async function readCanonicalChildcareRefresh(
  receipt: ChildcareCommandReceipt,
  admissionApplicationLoader: AdmissionApplicationLoader = fetchAdmissionApplication,
): Promise<CanonicalChildcareRecordAcknowledgement> {
  if (
    receipt.targetType === 'admission_application'
    || receipt.targetType === 'admission_waitlist'
    || receipt.targetType === 'admission_offer'
  ) {
    const applicationId = receipt.targetType === 'admission_application'
      ? receipt.targetId
      : childcareCommandAdmissionOwnerId(receipt);
    const application = await admissionApplicationLoader(
      receipt.organizationId,
      applicationId,
    );
    if (
      application.id !== applicationId
      || application.organization_id !== receipt.organizationId
    ) {
      throw new Error('The refreshed admission application crossed its receipt identity boundary.');
    }
    return canonicalRefresh(
      receipt,
      'admission_application',
      applicationId,
      application.version,
    );
  }

  if (receipt.targetType === 'family') {
    const family = await fetchFamilyDetail(receipt.targetId, receipt.organizationId);
    return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, family.version);
  }

  if (receipt.targetType === 'authority_person' || receipt.targetType === 'authority_evidence' || receipt.targetType === 'authority_evidence_object') {
    const familyId = childcareCommandAuthorityFamilyId(receipt);
    const workspace = await fetchFamilyAuthorityWorkspace(familyId, receipt.organizationId);
    const resource = receipt.targetType === 'authority_person'
      ? workspace.people.find((candidate) => candidate.id === receipt.targetId)
      : receipt.targetType === 'authority_evidence'
        ? workspace.evidence.find((candidate) => candidate.id === receipt.targetId)
        : workspace.evidence_objects.find((candidate) => candidate.id === receipt.targetId);
    if (!resource) throw new Error('The committed family-authority resource was not present in the refreshed workspace.');
    return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, resource.version);
  }

  if (receipt.targetType === 'consent' && receipt.commandType === 'organization.consent.policy.publish') {
    const policies = await fetchConsentPolicies(receipt.organizationId);
    const policy = policies.find((candidate) => candidate.id === receipt.targetId);
    if (!policy) throw new Error('The committed consent policy was not present in the refreshed policy list.');
    return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, policy.version_number);
  }

  if (receipt.targetType === 'release_authorization' || receipt.targetType === 'release_rule' || receipt.targetType === 'consent') {
    const childId = childcareCommandChildAuthorityOwnerId(receipt);
    const profile = await fetchChildProfile(childId, receipt.organizationId);
    const workspace = await fetchFamilyAuthorityWorkspace(profile.family_id, receipt.organizationId);
    const child = workspace.children.find((candidate) => candidate.child_id === childId);
    const resource = receipt.targetType === 'release_authorization'
      ? child?.release_authorizations.find((candidate) => candidate.id === receipt.targetId)
      : receipt.targetType === 'release_rule'
        ? child?.release_rules.find((candidate) => candidate.id === receipt.targetId)
        : child?.consent_decisions.find((candidate) => candidate.id === receipt.targetId);
    if (!resource) throw new Error('The committed child-authority resource was not present in the refreshed workspace.');
    return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, resource.version);
  }

  const childId = receipt.targetType === 'child' ? receipt.targetId : enrollmentChildId(receipt);
  const profile = await fetchChildProfile(childId, receipt.organizationId);
  if (receipt.targetType === 'child') {
    return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, profile.version);
  }
  const enrollment = profile.enrollments.find((candidate) => candidate.id === receipt.targetId);
  if (!enrollment) throw new Error('The committed enrollment was not present in the refreshed child record.');
  return canonicalRefresh(receipt, receipt.targetType, receipt.targetId, enrollment.version);
}

function resolutionMessage(reason: ChildcareRecoveryBlockReason | null): string {
  if (reason === 'authentication_required') return 'Sign in again before CareSync checks this saved result.';
  if (reason === 'permission_denied') return 'This identity can no longer verify the saved result.';
  if (reason === 'offline') return 'CareSync is offline. The change remains safely held for another check.';
  if (reason === 'server_unavailable') return 'The server is unavailable. The change remains safely held.';
  if (reason === 'lease_held_by_another_tab') return 'Another CareSync tab is checking this change.';
  if (reason === 'canonical_refresh_failed') return 'The commit was found, but the canonical record could not be refreshed.';
  if (reason === 'durable_storage_unavailable') return 'Durable browser storage is unavailable, so no childcare change can be sent.';
  return 'CareSync could not prove the saved result yet. The mutation lane remains blocked.';
}

export function ChildcareCommandRecoveryProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const identityKey = session.status === 'authenticated'
    && session.user?.id
    && session.user.organization_id
    && session.organization?.id === session.user.organization_id
    ? `${session.user.id}:${session.organization.id}`
    : '';
  const identityKeyRef = useRef(identityKey);
  identityKeyRef.current = identityKey;
  const runtimeOwner = useRef(new ChildcareCommandRuntimeOwner());
  const [runtime, setRuntime] = useState<ChildcareCommandRuntime | null>(null);
  const [stateIdentityKey, setStateIdentityKey] = useState('');
  const [activeEntry, setActiveEntry] = useState<ChildcareCommandJournalEntry | null>(null);
  const [blockReason, setBlockReason] = useState<ChildcareRecoveryBlockReason | null>(null);
  const [checking, setChecking] = useState(false);
  const [initialScanComplete, setInitialScanComplete] = useState(false);
  const [lastResolved, setLastResolved] = useState<ResolvedChildcareCommand | null>(null);
  const [lastFinalAbsenceAcknowledgedOperationId, setLastFinalAbsenceAcknowledgedOperationId] = useState<string | null>(null);
  const activeEntryRef = useRef<ChildcareCommandJournalEntry | null>(null);
  const missingEntryRef = useRef<ChildcareCommandJournalEntry | null>(null);
  const runtimeGeneration = useRef(0);
  const resolutionInFlight = useRef<{ entryKey: string; promise: Promise<ResolutionOutcome> } | null>(null);
  const missingInspectionInFlight = useRef<{ entryKey: string; promise: Promise<void> } | null>(null);

  const isCurrent = useCallback((expectedRuntime: ChildcareCommandRuntime, generation: number): boolean => (
    isCurrentChildcareRecoveryIdentity(
      expectedRuntime.identityKey,
      generation,
      identityKeyRef.current,
      runtimeGeneration.current,
    )
  ), []);

  const observeActiveEntry = useCallback((entry: ChildcareCommandJournalEntry | null): void => {
    activeEntryRef.current = entry;
    setActiveEntry(entry);
  }, []);

  const inspectMissingEntry = useCallback(async (
    expectedRuntime: ChildcareCommandRuntime,
    entry: ChildcareCommandJournalEntry,
    generation: number,
  ): Promise<void> => {
    if (missingInspectionInFlight.current?.entryKey === entry.key) {
      return missingInspectionInFlight.current.promise;
    }
    const task = (async () => {
      if (isCurrent(expectedRuntime, generation)) {
        setChecking(true);
        setBlockReason(null);
      }
      try {
        const inspection = await expectedRuntime.recovery.inspectFinalizedOperation(entry);
        if (
          !isCurrent(expectedRuntime, generation)
          || missingEntryRef.current?.key !== entry.key
        ) return;
        if (inspection.kind === 'blocked') {
          setBlockReason(inspection.reason);
          return;
        }
        if (inspection.kind === 'absent_final') {
          missingEntryRef.current = null;
          setBlockReason(null);
          setLastResolved(null);
          setLastFinalAbsenceAcknowledgedOperationId(inspection.clientOperationId);
          return;
        }
        let canonical: CanonicalChildcareRecordAcknowledgement;
        try {
          canonical = await readCanonicalChildcareRefresh(inspection.receipt);
        } catch {
          if (isCurrent(expectedRuntime, generation) && missingEntryRef.current?.key === entry.key) {
            setBlockReason('canonical_refresh_failed');
          }
          return;
        }
        if (
          !isCurrent(expectedRuntime, generation)
          || missingEntryRef.current?.key !== entry.key
        ) return;
        missingEntryRef.current = null;
        setBlockReason(null);
        setLastResolved({
          clientOperationId: entry.clientOperationId,
          actionRoute: inspection.actionRoute,
          targetType: canonical.targetType,
          targetId: canonical.targetId,
          version: canonical.version,
        });
      } finally {
        if (isCurrent(expectedRuntime, generation)) setChecking(false);
      }
    })();
    missingInspectionInFlight.current = { entryKey: entry.key, promise: task };
    try {
      await task;
    } finally {
      if (missingInspectionInFlight.current?.promise === task) missingInspectionInFlight.current = null;
    }
  }, [isCurrent]);

  const loadLane = useCallback(async (
    expectedRuntime: ChildcareCommandRuntime,
    generation: number,
  ): Promise<ChildcareCommandJournalEntry | null> => {
    const entries = await expectedRuntime.coordinator.listLane(expectedRuntime.scope);
    if (entries.length > 1) throw new Error('The durable childcare command lane contains contradictory unresolved entries.');
    const entry = entries[0] ?? null;
    if (isCurrent(expectedRuntime, generation)) {
      const previous = activeEntryRef.current;
      observeActiveEntry(entry);
      if (entry) {
        if (
          previous
          && previous.key !== entry.key
          && resolutionInFlight.current?.entryKey !== previous.key
        ) {
          // The old row may have been finalized and replaced before this tab
          // observed the empty lane. Preserve both facts: inspect the old
          // outcome while the new durable row remains the active lane block.
          missingEntryRef.current = previous;
          void inspectMissingEntry(expectedRuntime, previous, generation);
        } else if (missingEntryRef.current?.key === entry.key) {
          missingEntryRef.current = null;
        }
      } else if (previous?.status === 'absent_final') {
        // This status can be deleted only through the explicit operator gate.
        missingEntryRef.current = null;
        setBlockReason(null);
        setLastResolved(null);
        setLastFinalAbsenceAcknowledgedOperationId(previous.clientOperationId);
      } else if (previous && resolutionInFlight.current?.entryKey !== previous.key) {
        // Another tab may have cleared the row after confirming either a
        // receipt or a terminal-absence proof. Re-inspect; never guess which.
        missingEntryRef.current = previous;
        void inspectMissingEntry(expectedRuntime, previous, generation);
      }
    }
    return entry;
  }, [inspectMissingEntry, isCurrent, observeActiveEntry]);

  const resolveEntry = useCallback(async (
    expectedRuntime: ChildcareCommandRuntime,
    entry: ChildcareCommandJournalEntry,
    generation: number,
  ): Promise<ResolutionOutcome> => {
    if (resolutionInFlight.current?.entryKey === entry.key) {
      return resolutionInFlight.current.promise;
    }
    const task = (async () => {
      if (isCurrent(expectedRuntime, generation)) {
        setChecking(true);
        setBlockReason(null);
      }
      try {
        const result = await expectedRuntime.recovery.reconcile(journalRef(entry));
        if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
        const durableEntry = await loadLane(expectedRuntime, generation);
        if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
        if (!durableEntry || durableEntry.key !== result.entry.key) {
          // Do not let a late completion repaint a row that another tab has
          // already finalized or replaced. Resolve the old operation from its
          // actor-private receipt while preserving any newer active lane row.
          missingEntryRef.current = result.entry;
          await inspectMissingEntry(expectedRuntime, result.entry, generation);
          return { kind: 'blocked' } as const;
        }
        observeActiveEntry(durableEntry);
        if (result.kind === 'blocked') {
          setBlockReason(result.reason);
          return { kind: 'blocked' } as const;
        }
        if (result.kind === 'absent_final') {
          setBlockReason(null);
          return { kind: 'absent_final' } as const;
        }

        let canonical: CanonicalChildcareRecordAcknowledgement;
        try {
          canonical = await readCanonicalChildcareRefresh(result.receipt);
        } catch {
          if (isCurrent(expectedRuntime, generation)) setBlockReason('canonical_refresh_failed');
          return { kind: 'blocked' } as const;
        }
        if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
        const resolution: ResolvedChildcareCommand = {
          clientOperationId: result.entry.clientOperationId,
          actionRoute: result.actionRoute,
          targetType: canonical.targetType,
          targetId: canonical.targetId,
          version: canonical.version,
        };
        let remaining: ChildcareCommandJournalEntry | null;
        try {
          await expectedRuntime.recovery.acknowledgeCanonicalRefresh(
            journalRef(result.entry),
            result.receipt,
            canonical,
          );
          remaining = await loadLane(expectedRuntime, generation);
        } catch (caught) {
          remaining = await loadLane(expectedRuntime, generation);
          if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
          if (remaining?.key === result.entry.key) throw caught;
          // A competing tab passed the same canonical deletion gate first.
        }
        if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
        missingEntryRef.current = null;
        setBlockReason(null);
        setLastResolved(resolution);
        return { kind: 'resolved', resolution } as const;
      } catch (caught) {
        if (!isCurrent(expectedRuntime, generation)) return { kind: 'blocked' } as const;
        setBlockReason(caught instanceof ChildcareCommandJournalUnavailableError
          ? 'durable_storage_unavailable'
          : 'protocol_failure');
        try {
          const remaining = await loadLane(expectedRuntime, generation);
          if (!remaining && isCurrent(expectedRuntime, generation)) {
            missingEntryRef.current = entry;
            await inspectMissingEntry(expectedRuntime, entry, generation);
          }
        } catch {
          // The original failure and durable-storage block remain authoritative.
        }
        return { kind: 'blocked' } as const;
      } finally {
        if (isCurrent(expectedRuntime, generation)) setChecking(false);
      }
    })();
    resolutionInFlight.current = { entryKey: entry.key, promise: task };
    try {
      return await task;
    } finally {
      if (resolutionInFlight.current?.promise === task) resolutionInFlight.current = null;
    }
  }, [inspectMissingEntry, isCurrent, loadLane, observeActiveEntry]);

  const recoverLane = useCallback(async (expectedRuntime: ChildcareCommandRuntime, generation: number): Promise<void> => {
    try {
      const entry = await loadLane(expectedRuntime, generation);
      if (!isCurrent(expectedRuntime, generation)) return;
      setInitialScanComplete(true);
      if (entry) await resolveEntry(expectedRuntime, entry, generation);
      else if (missingEntryRef.current) await inspectMissingEntry(expectedRuntime, missingEntryRef.current, generation);
      else setBlockReason(null);
    } catch (caught) {
      if (!isCurrent(expectedRuntime, generation)) return;
      setInitialScanComplete(true);
      setBlockReason(caught instanceof ChildcareCommandJournalUnavailableError
        ? 'durable_storage_unavailable'
        : 'protocol_failure');
    }
  }, [inspectMissingEntry, isCurrent, loadLane, resolveEntry]);

  useEffect(() => {
    const generation = ++runtimeGeneration.current;
    resolutionInFlight.current = null;
    missingInspectionInFlight.current = null;
    activeEntryRef.current = null;
    missingEntryRef.current = null;
    setStateIdentityKey(identityKey);
    setRuntime(null);
    setActiveEntry(null);
    setBlockReason(null);
    setChecking(false);
    setInitialScanComplete(false);
    setLastResolved(null);
    setLastFinalAbsenceAcknowledgedOperationId(null);
    if (!identityKey) return;
    const nextRuntime = runtimeOwner.current.activate(identityKey);
    setRuntime(nextRuntime);
    void recoverLane(nextRuntime, generation);
    const unsubscribe = nextRuntime.coordinator.subscribe((scope) => {
      if (
        !isCurrent(nextRuntime, generation)
        || scope.actorUserId !== nextRuntime.scope.actorUserId
        || scope.organizationId !== nextRuntime.scope.organizationId
      ) return;
      void loadLane(nextRuntime, generation)
        .then((entry) => {
          // Another tab may have finished and cleared the lane after this tab
          // recorded a transient lease block. Durable emptiness removes it.
          if (isCurrent(nextRuntime, generation) && !entry && !missingEntryRef.current) setBlockReason(null);
        })
        .catch(() => {
          if (isCurrent(nextRuntime, generation)) setBlockReason('protocol_failure');
        });
    });
    const onFocus = () => { if (isCurrent(nextRuntime, generation)) void recoverLane(nextRuntime, generation); };
    window.addEventListener('focus', onFocus);
    return () => {
      unsubscribe();
      window.removeEventListener('focus', onFocus);
      runtimeOwner.current.deactivate(nextRuntime);
    };
  }, [identityKey, isCurrent, loadLane, recoverLane]);

  const execute = useCallback(async <Result,>(
    metadata: ChildcareMutationMetadata,
    send: (operationId: string) => Promise<Result>,
  ): Promise<Result> => {
    const generation = runtimeGeneration.current;
    if (
      !runtime
      || runtime.identityKey !== identityKeyRef.current
      || stateIdentityKey !== identityKeyRef.current
      || !initialScanComplete
      || blockReason !== null
      || missingEntryRef.current !== null
    ) {
      throw new ChildcareCommandNotPreparedError(
        metadata.clientOperationId,
        'CareSync is still checking the durable childcare mutation lane. No change was sent.',
        activeEntry?.clientOperationId ?? null,
      );
    }
    let existing: ChildcareCommandJournalEntry | null;
    try {
      existing = await loadLane(runtime, generation);
    } catch (caught) {
      if (isCurrent(runtime, generation)) {
        setBlockReason(caught instanceof ChildcareCommandJournalUnavailableError
          ? 'durable_storage_unavailable'
          : 'protocol_failure');
      }
      throw new ChildcareCommandNotPreparedError(
        metadata.clientOperationId,
        'CareSync could not verify the durable lane, so this operation was not prepared or sent.',
        activeEntry?.clientOperationId ?? null,
        caught,
      );
    }
    if (!isCurrent(runtime, generation)) {
      throw new ChildcareCommandNotPreparedError(metadata.clientOperationId, 'The organization changed before the command could be sent.');
    }
    if (existing) {
      throw new ChildcareCommandNotPreparedError(
        metadata.clientOperationId,
        'Resolve the previous childcare change before sending another one.',
        existing.clientOperationId,
      );
    }
    const input = {
      ...runtime.scope,
      clientOperationId: metadata.clientOperationId,
      commandType: metadata.commandType,
      targetType: metadata.targetType,
      expectedTargetId: metadata.expectedTargetId,
      expectedActionOwnerId: metadata.expectedActionOwnerId,
    };
    let response: Result;
    let sendFailure: unknown;
    try {
      const persisted = await runtime.recovery.persistBeforeSend(input, send, (entry) => {
        if (isCurrent(runtime, generation)) {
          setLastResolved(null);
          setLastFinalAbsenceAcknowledgedOperationId(null);
          observeActiveEntry(entry);
        }
      });
      response = persisted.response;
    } catch (caught) {
      sendFailure = caught;
      if (!isCurrent(runtime, generation)) {
        throw new ChildcareCommandResolutionRequiredError(
          'The identity changed after this operation may have entered the durable lane. No result was applied to the new organization.',
          caught,
        );
      }
      if (isCommandRejectedBeforeCommit(caught)) {
        try {
          const entries = await runtime.coordinator.listLane(runtime.scope);
          if (!isCurrent(runtime, generation)) {
            throw new ChildcareCommandResolutionRequiredError(
              'The identity changed while CareSync was confirming the rejected operation.',
              caught,
            );
          }
          if (entries.length === 0) {
            // persistBeforeSend passed the dedicated prepared-row deletion
            // gate. Clear the local observation as well so a scanner outage
            // leaves Retry scan available with a new operation id.
            missingEntryRef.current = null;
            observeActiveEntry(null);
            setBlockReason(null);
            setChecking(false);
            throw caught;
          }
        } catch (journalFailure) {
          if (journalFailure === caught || journalFailure instanceof ChildcareCommandResolutionRequiredError) throw journalFailure;
          // A failed durable read cannot prove the lane is empty. Continue into
          // the normal fail-closed reconciliation path below.
        }
      }
      const entry = await loadLane(runtime, generation).catch(() => null);
      if (!isCurrent(runtime, generation)) {
        throw new ChildcareCommandResolutionRequiredError(
          'The identity changed while CareSync was checking this operation. No result was applied to the new organization.',
          caught,
        );
      }
      const definitelyNotPrepared = caught instanceof ChildcareCommandLeaseUnavailableError
        || caught instanceof ChildcareCommandLaneBlockedError
        || caught instanceof ChildcareCommandJournalUnavailableError;
      if (!entry) {
        if (definitelyNotPrepared) {
          if (caught instanceof ChildcareCommandJournalUnavailableError) {
            setBlockReason('durable_storage_unavailable');
          }
          throw new ChildcareCommandNotPreparedError(
            metadata.clientOperationId,
            'Another CareSync operation entered the durable lane first. This operation was not prepared or sent.',
            null,
            caught,
          );
        }
        throw caught;
      }
      if (!childcareJournalEntryMatchesMutation(entry, metadata)) {
        if (definitelyNotPrepared) {
          throw new ChildcareCommandNotPreparedError(
            metadata.clientOperationId,
            'Another CareSync tab owns the durable childcare change in this lane. This operation was not prepared or sent.',
            entry.clientOperationId,
            sendFailure,
          );
        }
        throw new ChildcareCommandResolutionRequiredError(
          'Another CareSync tab owns the durable childcare change in this lane. It was not treated as the result of this operation.',
          sendFailure,
        );
      }
      const outcome = await resolveEntry(runtime, entry, generation);
      if (outcome.kind === 'resolved') {
        if (outcome.resolution.clientOperationId !== metadata.clientOperationId) {
          throw new ChildcareCommandResolutionRequiredError('A foreign operation resolution was rejected. No result was attributed to this command.');
        }
        throw new ChildcareCommandRecoveredCommitError(outcome.resolution);
      }
      throw new ChildcareCommandResolutionRequiredError(
        'CareSync did not resend the change. Check the saved result before reviewing a new operation.',
        sendFailure,
      );
    }
    if (!isCurrent(runtime, generation)) {
      throw new ChildcareCommandResolutionRequiredError(
        'The identity changed after the operation was sent. Its result was not applied to the new organization.',
      );
    }
    const entry = await loadLane(runtime, generation);
    if (!isCurrent(runtime, generation)) {
      throw new ChildcareCommandResolutionRequiredError(
        'The identity changed while the operation result was being reconciled. No result was applied to the new organization.',
      );
    }
    if (!entry) {
      // A successful, validated response plus an empty durable lane means
      // another tab passed one of the journal's explicit deletion gates while
      // this tab was finishing. Apply the response and let the owning feature
      // refresh its canonical record instead of stranding its local form lock.
      setBlockReason(null);
      return response!;
    }
    if (!childcareJournalEntryMatchesMutation(entry, metadata)) {
      throw new ChildcareCommandResolutionRequiredError(
        'The server responded, but another operation occupies the durable childcare lane. No result was attributed to this command.',
      );
    }
    const outcome = await resolveEntry(runtime, entry, generation);
    if (outcome.kind === 'resolved' && outcome.resolution.clientOperationId !== metadata.clientOperationId) {
      throw new ChildcareCommandResolutionRequiredError('A foreign operation resolution was rejected. No result was attributed to this command.');
    }
    if (outcome.kind !== 'resolved') {
      throw new ChildcareCommandResolutionRequiredError(
        'The server response arrived, but CareSync still needs to reconcile the receipt and canonical record.',
      );
    }
    return response!;
  }, [activeEntry, blockReason, initialScanComplete, isCurrent, loadLane, observeActiveEntry, resolveEntry, runtime, stateIdentityKey]);

  const checkSavedResult = useCallback(async () => {
    if (!runtime) return;
    const generation = runtimeGeneration.current;
    try {
      const entry = await loadLane(runtime, generation);
      if (entry && isCurrent(runtime, generation)) await resolveEntry(runtime, entry, generation);
      else if (isCurrent(runtime, generation) && missingEntryRef.current) {
        await inspectMissingEntry(runtime, missingEntryRef.current, generation);
      } else if (isCurrent(runtime, generation)) setBlockReason(null);
    } catch (caught) {
      if (isCurrent(runtime, generation)) setBlockReason(caught instanceof ChildcareCommandJournalUnavailableError
        ? 'durable_storage_unavailable'
        : 'protocol_failure');
    }
  }, [inspectMissingEntry, isCurrent, loadLane, resolveEntry, runtime]);

  const acknowledgeFinalAbsence = useCallback(async () => {
    if (!runtime || !activeEntry || activeEntry.status !== 'absent_final' || checking) return;
    const generation = runtimeGeneration.current;
    const acknowledgedOperationId = activeEntry.clientOperationId;
    setChecking(true);
    try {
      await runtime.recovery.acknowledgeFinalAbsence(journalRef(activeEntry), {
        reviewed: true,
        newOperationRequired: true,
      });
      if (!isCurrent(runtime, generation)) return;
      await loadLane(runtime, generation);
      if (!isCurrent(runtime, generation)) return;
      if (missingEntryRef.current?.key === activeEntry.key) missingEntryRef.current = null;
      setBlockReason(null);
      setLastFinalAbsenceAcknowledgedOperationId(acknowledgedOperationId);
    } catch (caught) {
      if (isCurrent(runtime, generation)) setBlockReason(caught instanceof ChildcareCommandJournalUnavailableError
        ? 'durable_storage_unavailable'
        : 'protocol_failure');
    } finally {
      if (isCurrent(runtime, generation)) setChecking(false);
    }
  }, [activeEntry, checking, isCurrent, loadLane, runtime]);

  const stateCurrent = Boolean(identityKey && stateIdentityKey === identityKey && runtime?.identityKey === identityKey);

  const value = useMemo<ChildcareCommandRecoveryValue>(() => ({
    activeEntry: stateCurrent ? activeEntry : null,
    blockReason: stateCurrent ? blockReason : null,
    checking: stateCurrent ? checking : false,
    ready: stateCurrent && initialScanComplete,
    laneBlocked: !stateCurrent || Boolean(activeEntry) || Boolean(missingEntryRef.current) || Boolean(blockReason) || checking || !initialScanComplete,
    lastResolved: stateCurrent ? lastResolved : null,
    lastFinalAbsenceAcknowledgedOperationId: stateCurrent ? lastFinalAbsenceAcknowledgedOperationId : null,
    execute,
    checkSavedResult,
    acknowledgeFinalAbsence,
    dismissResolved: () => setLastResolved(null),
  }), [activeEntry, acknowledgeFinalAbsence, blockReason, checking, checkSavedResult, execute, initialScanComplete, lastFinalAbsenceAcknowledgedOperationId, lastResolved, stateCurrent]);

  return <ChildcareCommandRecoveryContext.Provider value={value}>{children}</ChildcareCommandRecoveryContext.Provider>;
}

export function useChildcareCommandRecovery(): ChildcareCommandRecoveryValue {
  const value = useContext(ChildcareCommandRecoveryContext);
  if (!value) throw new Error('useChildcareCommandRecovery must be used within ChildcareCommandRecoveryProvider');
  return value;
}

export function childcareRecoveryReasonMessage(reason: ChildcareRecoveryBlockReason | null): string {
  return resolutionMessage(reason);
}
