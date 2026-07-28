import {
  CHILDCARE_COMMAND_TYPES,
  type ChildcareCommandTargetType,
  type ChildcareCommandType,
} from './childcareCommandReceipt';

export type ChildcareCommandJournalStatus =
  | 'prepared'
  | 'blocked'
  | 'absent_final'
  | 'committed_needs_refresh';

export interface ChildcareCommandJournalScope {
  readonly actorUserId: string;
  readonly organizationId: string;
}

export interface ChildcareCommandJournalRef extends ChildcareCommandJournalScope {
  readonly clientOperationId: string;
}

export interface PrepareChildcareCommandInput extends ChildcareCommandJournalRef {
  readonly commandType: ChildcareCommandType;
  readonly targetType: ChildcareCommandTargetType;
  readonly expectedTargetId: string | null;
  /** Owning child for enrollment routes or owning family for authority routes. */
  readonly expectedActionOwnerId: string | null;
  readonly createdAt?: string;
}

export interface ChildcareCommandJournalEntry extends ChildcareCommandJournalRef {
  readonly schemaVersion: 2;
  readonly key: string;
  readonly commandType: ChildcareCommandType;
  readonly targetType: ChildcareCommandTargetType;
  readonly expectedTargetId: string | null;
  readonly expectedActionOwnerId: string | null;
  readonly createdAt: string;
  readonly status: ChildcareCommandJournalStatus;
}

interface StoredChildcareCommandJournalEntry {
  readonly schema_version: 2;
  readonly key: string;
  readonly actor_user_id: string;
  readonly organization_id: string;
  readonly client_operation_id: string;
  readonly command_type: ChildcareCommandType;
  readonly target_type: ChildcareCommandTargetType;
  readonly expected_target_id: string | null;
  readonly expected_action_owner_id: string | null;
  readonly created_at: string;
  readonly status: ChildcareCommandJournalStatus;
}

interface StoredCommandJournalLease {
  readonly schema_version: 1;
  readonly lane_key: string;
  readonly owner_id: string;
  readonly expires_at_epoch_ms: number;
}

export class ChildcareCommandJournalUnavailableError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = 'ChildcareCommandJournalUnavailableError';
  }
}

export class ChildcareCommandJournalCorruptionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChildcareCommandJournalCorruptionError';
  }
}

export class ChildcareCommandLaneBlockedError extends Error {
  constructor(public readonly blockingEntry: ChildcareCommandJournalEntry) {
    super('A previous childcare command must be reconciled before another change can be sent.');
    this.name = 'ChildcareCommandLaneBlockedError';
  }
}

export class ChildcareCommandJournalStateError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChildcareCommandJournalStateError';
  }
}

const ENTRY_KEYS = [
  'schema_version',
  'key',
  'actor_user_id',
  'organization_id',
  'client_operation_id',
  'command_type',
  'target_type',
  'expected_target_id',
  'expected_action_owner_id',
  'created_at',
  'status',
] as const;

const LEASE_KEYS = ['schema_version', 'lane_key', 'owner_id', 'expires_at_epoch_ms'] as const;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RFC3339_WITH_OFFSET_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const JOURNAL_STATUSES: readonly ChildcareCommandJournalStatus[] = [
  'prepared',
  'blocked',
  'absent_final',
  'committed_needs_refresh',
];

function corrupt(message: string): never {
  throw new ChildcareCommandJournalCorruptionError(message);
}

function uuid(value: unknown, label: string): string {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
    return corrupt(`The command journal contains an invalid ${label}.`);
  }
  return value.toLowerCase();
}

function commandType(value: unknown): ChildcareCommandType {
  if (!CHILDCARE_COMMAND_TYPES.includes(value as ChildcareCommandType)) {
    return corrupt('The command journal contains an invalid command type.');
  }
  return value as ChildcareCommandType;
}

function targetType(value: unknown): ChildcareCommandTargetType {
  if (![
    'family',
    'child',
    'enrollment',
    'authority_person',
    'authority_evidence',
    'authority_evidence_object',
    'release_authorization',
    'release_rule',
    'consent',
    'admission_application',
    'admission_waitlist',
    'admission_offer',
  ].includes(String(value))) {
    return corrupt('The command journal contains an invalid target type.');
  }
  return value as ChildcareCommandTargetType;
}

function commandRequiresActionOwner(command: ChildcareCommandType, target: ChildcareCommandTargetType): boolean {
  return target === 'enrollment'
    || target === 'admission_waitlist'
    || target === 'admission_offer'
    || target.startsWith('authority_')
    || target === 'release_authorization'
    || target === 'release_rule'
    || (target === 'consent' && command !== 'organization.consent.policy.publish');
}

function timestamp(value: unknown): string {
  if (
    typeof value !== 'string'
    || value.length > 64
    || !RFC3339_WITH_OFFSET_PATTERN.test(value)
    || !Number.isFinite(Date.parse(value))
  ) {
    return corrupt('The command journal contains an invalid creation time.');
  }
  return value;
}

function exactObject(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return corrupt(`The command journal contains an invalid ${label}.`);
  }
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    return corrupt(`The command journal contains an unexpected ${label} shape.`);
  }
  return row;
}

function normalizedScope(scope: ChildcareCommandJournalScope): ChildcareCommandJournalScope {
  return {
    actorUserId: uuid(scope.actorUserId, 'actor'),
    organizationId: uuid(scope.organizationId, 'organization'),
  };
}

export function childcareCommandJournalLaneKey(scope: ChildcareCommandJournalScope): string {
  const normalized = normalizedScope(scope);
  return `v1:${normalized.actorUserId}:${normalized.organizationId}`;
}

export function childcareCommandJournalEntryKey(ref: ChildcareCommandJournalRef): string {
  const scope = normalizedScope(ref);
  return `${childcareCommandJournalLaneKey(scope)}:${uuid(ref.clientOperationId, 'operation')}`;
}

function parseStoredEntry(value: unknown): ChildcareCommandJournalEntry {
  const row = exactObject(value, ENTRY_KEYS, 'entry');
  if (row.schema_version !== 2) {
    return corrupt('The command journal entry uses an unsupported schema and cannot be reconciled automatically.');
  }
  const actorUserId = uuid(row.actor_user_id, 'actor');
  const organizationId = uuid(row.organization_id, 'organization');
  const clientOperationId = uuid(row.client_operation_id, 'operation');
  const expectedKey = childcareCommandJournalEntryKey({ actorUserId, organizationId, clientOperationId });
  if (row.key !== expectedKey) return corrupt('The command journal entry key does not match its identity.');
  const expectedTargetId = row.expected_target_id === null
    ? null
    : uuid(row.expected_target_id, 'expected target');
  const expectedActionOwnerId = row.expected_action_owner_id === null
    ? null
    : uuid(row.expected_action_owner_id, 'expected action owner');
  const parsedTargetType = targetType(row.target_type);
  const parsedCommandType = commandType(row.command_type);
  const requiresActionOwner = commandRequiresActionOwner(parsedCommandType, parsedTargetType);
  if ((requiresActionOwner && expectedActionOwnerId === null) || (!requiresActionOwner && expectedActionOwnerId !== null)) {
    return corrupt('The command journal action owner does not match its target type.');
  }
  if (!JOURNAL_STATUSES.includes(row.status as ChildcareCommandJournalStatus)) {
    return corrupt('The command journal entry contains an invalid status.');
  }
  return Object.freeze({
    schemaVersion: 2,
    key: expectedKey,
    actorUserId,
    organizationId,
    clientOperationId,
    commandType: parsedCommandType,
    targetType: parsedTargetType,
    expectedTargetId,
    expectedActionOwnerId,
    createdAt: timestamp(row.created_at),
    status: row.status as ChildcareCommandJournalStatus,
  });
}

function serializeEntry(entry: ChildcareCommandJournalEntry): StoredChildcareCommandJournalEntry {
  return {
    schema_version: 2,
    key: entry.key,
    actor_user_id: entry.actorUserId,
    organization_id: entry.organizationId,
    client_operation_id: entry.clientOperationId,
    command_type: entry.commandType,
    target_type: entry.targetType,
    expected_target_id: entry.expectedTargetId,
    expected_action_owner_id: entry.expectedActionOwnerId,
    created_at: entry.createdAt,
    status: entry.status,
  };
}

function parseLease(value: unknown): StoredCommandJournalLease {
  const row = exactObject(value, LEASE_KEYS, 'lease');
  if (
    row.schema_version !== 1
    || typeof row.lane_key !== 'string'
    || !row.lane_key.startsWith('v1:')
    || typeof row.owner_id !== 'string'
    || !UUID_PATTERN.test(row.owner_id)
    || !Number.isSafeInteger(row.expires_at_epoch_ms)
    || Number(row.expires_at_epoch_ms) < 0
  ) {
    return corrupt('The command journal contains an invalid lease.');
  }
  return {
    schema_version: 1,
    lane_key: row.lane_key,
    owner_id: row.owner_id.toLowerCase(),
    expires_at_epoch_ms: Number(row.expires_at_epoch_ms),
  };
}

function preparedEntry(input: PrepareChildcareCommandInput, now: () => Date): ChildcareCommandJournalEntry {
  const actorUserId = uuid(input.actorUserId, 'actor');
  const organizationId = uuid(input.organizationId, 'organization');
  const clientOperationId = uuid(input.clientOperationId, 'operation');
  const expectedTargetId = input.expectedTargetId === null
    ? null
    : uuid(input.expectedTargetId, 'expected target');
  const expectedActionOwnerId = input.expectedActionOwnerId === null
    ? null
    : uuid(input.expectedActionOwnerId, 'expected action owner');
  const parsedTargetType = targetType(input.targetType);
  const parsedCommandType = commandType(input.commandType);
  const requiresActionOwner = commandRequiresActionOwner(parsedCommandType, parsedTargetType);
  if ((requiresActionOwner && expectedActionOwnerId === null) || (!requiresActionOwner && expectedActionOwnerId !== null)) {
    throw new ChildcareCommandJournalStateError('Enrollment commands require their owning child, family-authority commands require their owning family; other command targets cannot declare one.');
  }
  const createdAt = timestamp(input.createdAt ?? now().toISOString());
  return Object.freeze({
    schemaVersion: 2,
    key: childcareCommandJournalEntryKey({ actorUserId, organizationId, clientOperationId }),
    actorUserId,
    organizationId,
    clientOperationId,
    commandType: parsedCommandType,
    targetType: parsedTargetType,
    expectedTargetId,
    expectedActionOwnerId,
    createdAt,
    status: 'prepared',
  });
}

function assertSameLane(entry: ChildcareCommandJournalEntry, scope: ChildcareCommandJournalScope): boolean {
  const normalized = normalizedScope(scope);
  return entry.actorUserId === normalized.actorUserId && entry.organizationId === normalized.organizationId;
}

function cloneSerialized<Value>(value: Value): Value {
  return JSON.parse(JSON.stringify(value)) as Value;
}

export interface ChildcareCommandJournalAdapter {
  createPrepared(input: PrepareChildcareCommandInput): Promise<ChildcareCommandJournalEntry>;
  get(ref: ChildcareCommandJournalRef): Promise<ChildcareCommandJournalEntry | null>;
  listLane(scope: ChildcareCommandJournalScope): Promise<readonly ChildcareCommandJournalEntry[]>;
  transition(
    ref: ChildcareCommandJournalRef,
    allowedStatuses: readonly ChildcareCommandJournalStatus[],
    nextStatus: ChildcareCommandJournalStatus,
  ): Promise<ChildcareCommandJournalEntry>;
  deletePreparedAfterAuthoritativeRejection(ref: ChildcareCommandJournalRef): Promise<void>;
  deleteCommittedAfterRefresh(ref: ChildcareCommandJournalRef): Promise<void>;
  deleteFinalAbsenceAfterAcknowledgement(ref: ChildcareCommandJournalRef): Promise<void>;
  acquireLease(scope: ChildcareCommandJournalScope, ownerId: string, nowEpochMs: number, ttlMs: number): Promise<boolean>;
  renewLease(scope: ChildcareCommandJournalScope, ownerId: string, nowEpochMs: number, ttlMs: number): Promise<boolean>;
  releaseLease(scope: ChildcareCommandJournalScope, ownerId: string): Promise<void>;
}

export interface MemoryCommandJournalState {
  readonly entries: Map<string, unknown>;
  readonly leases: Map<string, unknown>;
}

export function createMemoryCommandJournalState(): MemoryCommandJournalState {
  return { entries: new Map(), leases: new Map() };
}

export class MemoryChildcareCommandJournalAdapter implements ChildcareCommandJournalAdapter {
  constructor(
    private readonly state: MemoryCommandJournalState = createMemoryCommandJournalState(),
    private readonly now: () => Date = () => new Date(),
  ) {}

  private allEntries(): ChildcareCommandJournalEntry[] {
    return [...this.state.entries.values()].map((value) => parseStoredEntry(cloneSerialized(value)));
  }

  private allLeases(): StoredCommandJournalLease[] {
    return [...this.state.leases.values()].map((value) => parseLease(cloneSerialized(value)));
  }

  async createPrepared(input: PrepareChildcareCommandInput): Promise<ChildcareCommandJournalEntry> {
    const entry = preparedEntry(input, this.now);
    const existing = this.allEntries().find((item) => assertSameLane(item, entry));
    if (existing) throw new ChildcareCommandLaneBlockedError(existing);
    this.state.entries.set(entry.key, cloneSerialized(serializeEntry(entry)));
    return parseStoredEntry(cloneSerialized(this.state.entries.get(entry.key)));
  }

  async get(ref: ChildcareCommandJournalRef): Promise<ChildcareCommandJournalEntry | null> {
    // Parse every stored row first so a damaged key cannot become invisible.
    const entries = this.allEntries();
    const key = childcareCommandJournalEntryKey(ref);
    return entries.find((entry) => entry.key === key) ?? null;
  }

  async listLane(scope: ChildcareCommandJournalScope): Promise<readonly ChildcareCommandJournalEntry[]> {
    return this.allEntries().filter((entry) => assertSameLane(entry, scope));
  }

  async transition(
    ref: ChildcareCommandJournalRef,
    allowedStatuses: readonly ChildcareCommandJournalStatus[],
    nextStatus: ChildcareCommandJournalStatus,
  ): Promise<ChildcareCommandJournalEntry> {
    if (!JOURNAL_STATUSES.includes(nextStatus)) throw new ChildcareCommandJournalStateError('Invalid journal transition target.');
    const key = childcareCommandJournalEntryKey(ref);
    const current = this.allEntries().find((entry) => entry.key === key) ?? null;
    if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    if (!allowedStatuses.includes(current.status)) throw new ChildcareCommandJournalStateError(`The childcare command cannot move from ${current.status} to ${nextStatus}.`);
    const next = Object.freeze({ ...current, status: nextStatus });
    this.state.entries.set(key, cloneSerialized(serializeEntry(next)));
    return parseStoredEntry(cloneSerialized(this.state.entries.get(key)));
  }

  async deleteCommittedAfterRefresh(ref: ChildcareCommandJournalRef): Promise<void> {
    const key = childcareCommandJournalEntryKey(ref);
    const current = this.allEntries().find((entry) => entry.key === key) ?? null;
    if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    if (current.status !== 'committed_needs_refresh') {
      throw new ChildcareCommandJournalStateError('Only a committed command with refreshed canonical data can be cleared.');
    }
    this.state.entries.delete(key);
  }

  async deletePreparedAfterAuthoritativeRejection(ref: ChildcareCommandJournalRef): Promise<void> {
    const key = childcareCommandJournalEntryKey(ref);
    const current = this.allEntries().find((entry) => entry.key === key) ?? null;
    if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    if (current.status !== 'prepared') {
      throw new ChildcareCommandJournalStateError('Only a prepared command with an authoritative pre-commit rejection can be cleared.');
    }
    this.state.entries.delete(key);
  }

  async deleteFinalAbsenceAfterAcknowledgement(ref: ChildcareCommandJournalRef): Promise<void> {
    const key = childcareCommandJournalEntryKey(ref);
    const current = this.allEntries().find((entry) => entry.key === key) ?? null;
    if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
    if (current.status !== 'absent_final') {
      throw new ChildcareCommandJournalStateError('Only a server-finalized absent command can be retired by operator acknowledgement.');
    }
    this.state.entries.delete(key);
  }

  async acquireLease(
    scope: ChildcareCommandJournalScope,
    ownerIdValue: string,
    nowEpochMs: number,
    ttlMs: number,
  ): Promise<boolean> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    const existing = this.allLeases().find((lease) => lease.lane_key === laneKey) ?? null;
    if (existing && existing.owner_id !== ownerId && existing.expires_at_epoch_ms > nowEpochMs) return false;
    this.state.leases.set(laneKey, cloneSerialized({
      schema_version: 1,
      lane_key: laneKey,
      owner_id: ownerId,
      expires_at_epoch_ms: nowEpochMs + ttlMs,
    } satisfies StoredCommandJournalLease));
    return true;
  }

  async renewLease(
    scope: ChildcareCommandJournalScope,
    ownerIdValue: string,
    nowEpochMs: number,
    ttlMs: number,
  ): Promise<boolean> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    const existing = this.allLeases().find((lease) => lease.lane_key === laneKey) ?? null;
    if (!existing || existing.owner_id !== ownerId) return false;
    this.state.leases.set(laneKey, cloneSerialized({
      ...existing,
      expires_at_epoch_ms: nowEpochMs + ttlMs,
    }));
    return true;
  }

  async releaseLease(scope: ChildcareCommandJournalScope, ownerIdValue: string): Promise<void> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    const existing = this.allLeases().find((lease) => lease.lane_key === laneKey) ?? null;
    if (!existing) return;
    if (existing.owner_id === ownerId) this.state.leases.delete(laneKey);
  }
}

const DATABASE_NAME = 'caresync-childcare-command-recovery';
// Version 2 adds enrollment action-owner binding. Existing schema-v1 rows are
// deliberately retained and rejected by the strict parser rather than guessed.
const DATABASE_VERSION = 2;
const ENTRY_STORE = 'entries';
const LEASE_STORE = 'leases';

function requestResult<Result>(request: IDBRequest<Result>): Promise<Result> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed.'));
  });
}

function transactionCompletion(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction was aborted.'));
    transaction.onerror = () => reject(transaction.error ?? new Error('IndexedDB transaction failed.'));
  });
}

export class IndexedDbChildcareCommandJournalAdapter implements ChildcareCommandJournalAdapter {
  private databasePromise: Promise<IDBDatabase> | null = null;

  constructor(
    private readonly factory: IDBFactory | undefined = typeof indexedDB === 'undefined' ? undefined : indexedDB,
    private readonly now: () => Date = () => new Date(),
  ) {}

  private database(): Promise<IDBDatabase> {
    if (!this.factory) {
      return Promise.reject(new ChildcareCommandJournalUnavailableError('Durable browser storage is unavailable; no command was sent.'));
    }
    if (this.databasePromise) return this.databasePromise;
    this.databasePromise = new Promise((resolve, reject) => {
      let request: IDBOpenDBRequest;
      try {
        request = this.factory!.open(DATABASE_NAME, DATABASE_VERSION);
      } catch (caught) {
        reject(new ChildcareCommandJournalUnavailableError('Durable browser storage could not be opened; no command was sent.', caught));
        return;
      }
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(ENTRY_STORE)) database.createObjectStore(ENTRY_STORE, { keyPath: 'key' });
        if (!database.objectStoreNames.contains(LEASE_STORE)) database.createObjectStore(LEASE_STORE, { keyPath: 'lane_key' });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new ChildcareCommandJournalUnavailableError('Durable browser storage could not be opened; no command was sent.', request.error));
      request.onblocked = () => reject(new ChildcareCommandJournalUnavailableError('Durable browser storage is blocked by another CareSync tab; no command was sent.'));
    });
    return this.databasePromise;
  }

  private async run<Result>(
    stores: readonly string[],
    mode: IDBTransactionMode,
    operation: (transaction: IDBTransaction) => Promise<Result>,
  ): Promise<Result> {
    try {
      const database = await this.database();
      const transaction = database.transaction([...stores], mode);
      const completion = transactionCompletion(transaction);
      try {
        const result = await operation(transaction);
        await completion;
        return result;
      } catch (caught) {
        try { transaction.abort(); } catch { /* already completed */ }
        await completion.catch(() => undefined);
        throw caught;
      }
    } catch (caught) {
      if (
        caught instanceof ChildcareCommandJournalCorruptionError
        || caught instanceof ChildcareCommandLaneBlockedError
        || caught instanceof ChildcareCommandJournalStateError
        || caught instanceof ChildcareCommandJournalUnavailableError
      ) throw caught;
      throw new ChildcareCommandJournalUnavailableError('Durable command storage failed; the mutation lane remains blocked.', caught);
    }
  }

  private async allEntries(transaction: IDBTransaction): Promise<ChildcareCommandJournalEntry[]> {
    const raw = await requestResult(transaction.objectStore(ENTRY_STORE).getAll());
    return raw.map(parseStoredEntry);
  }

  private async allLeases(transaction: IDBTransaction): Promise<StoredCommandJournalLease[]> {
    const raw = await requestResult(transaction.objectStore(LEASE_STORE).getAll());
    return raw.map(parseLease);
  }

  async createPrepared(input: PrepareChildcareCommandInput): Promise<ChildcareCommandJournalEntry> {
    const entry = preparedEntry(input, this.now);
    return this.run([ENTRY_STORE], 'readwrite', async (transaction) => {
      const existing = (await this.allEntries(transaction)).find((item) => assertSameLane(item, entry));
      if (existing) throw new ChildcareCommandLaneBlockedError(existing);
      await requestResult(transaction.objectStore(ENTRY_STORE).add(serializeEntry(entry)));
      return entry;
    });
  }

  async get(ref: ChildcareCommandJournalRef): Promise<ChildcareCommandJournalEntry | null> {
    return this.run([ENTRY_STORE], 'readonly', async (transaction) => {
      const key = childcareCommandJournalEntryKey(ref);
      return (await this.allEntries(transaction)).find((entry) => entry.key === key) ?? null;
    });
  }

  async listLane(scope: ChildcareCommandJournalScope): Promise<readonly ChildcareCommandJournalEntry[]> {
    return this.run([ENTRY_STORE], 'readonly', async (transaction) => (
      (await this.allEntries(transaction)).filter((entry) => assertSameLane(entry, scope))
    ));
  }

  async transition(
    ref: ChildcareCommandJournalRef,
    allowedStatuses: readonly ChildcareCommandJournalStatus[],
    nextStatus: ChildcareCommandJournalStatus,
  ): Promise<ChildcareCommandJournalEntry> {
    if (!JOURNAL_STATUSES.includes(nextStatus)) throw new ChildcareCommandJournalStateError('Invalid journal transition target.');
    return this.run([ENTRY_STORE], 'readwrite', async (transaction) => {
      const key = childcareCommandJournalEntryKey(ref);
      // Scan first so corrupt rows cannot be bypassed by a valid direct key.
      const current = (await this.allEntries(transaction)).find((entry) => entry.key === key);
      if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (!allowedStatuses.includes(current.status)) throw new ChildcareCommandJournalStateError(`The childcare command cannot move from ${current.status} to ${nextStatus}.`);
      const next = Object.freeze({ ...current, status: nextStatus });
      await requestResult(transaction.objectStore(ENTRY_STORE).put(serializeEntry(next)));
      return next;
    });
  }

  async deleteCommittedAfterRefresh(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.run([ENTRY_STORE], 'readwrite', async (transaction) => {
      const key = childcareCommandJournalEntryKey(ref);
      const current = (await this.allEntries(transaction)).find((entry) => entry.key === key);
      if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (current.status !== 'committed_needs_refresh') {
        throw new ChildcareCommandJournalStateError('Only a committed command with refreshed canonical data can be cleared.');
      }
      await requestResult(transaction.objectStore(ENTRY_STORE).delete(key));
    });
  }

  async deletePreparedAfterAuthoritativeRejection(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.run([ENTRY_STORE], 'readwrite', async (transaction) => {
      const key = childcareCommandJournalEntryKey(ref);
      const current = (await this.allEntries(transaction)).find((entry) => entry.key === key);
      if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (current.status !== 'prepared') {
        throw new ChildcareCommandJournalStateError('Only a prepared command with an authoritative pre-commit rejection can be cleared.');
      }
      await requestResult(transaction.objectStore(ENTRY_STORE).delete(key));
    });
  }

  async deleteFinalAbsenceAfterAcknowledgement(ref: ChildcareCommandJournalRef): Promise<void> {
    await this.run([ENTRY_STORE], 'readwrite', async (transaction) => {
      const key = childcareCommandJournalEntryKey(ref);
      const current = (await this.allEntries(transaction)).find((entry) => entry.key === key);
      if (!current) throw new ChildcareCommandJournalStateError('The childcare command journal entry no longer exists.');
      if (current.status !== 'absent_final') {
        throw new ChildcareCommandJournalStateError('Only a server-finalized absent command can be retired by operator acknowledgement.');
      }
      await requestResult(transaction.objectStore(ENTRY_STORE).delete(key));
    });
  }

  async acquireLease(
    scope: ChildcareCommandJournalScope,
    ownerIdValue: string,
    nowEpochMs: number,
    ttlMs: number,
  ): Promise<boolean> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    return this.run([LEASE_STORE], 'readwrite', async (transaction) => {
      const store = transaction.objectStore(LEASE_STORE);
      const existing = (await this.allLeases(transaction)).find((lease) => lease.lane_key === laneKey) ?? null;
      if (existing && existing.owner_id !== ownerId && existing.expires_at_epoch_ms > nowEpochMs) return false;
      await requestResult(store.put({
        schema_version: 1,
        lane_key: laneKey,
        owner_id: ownerId,
        expires_at_epoch_ms: nowEpochMs + ttlMs,
      } satisfies StoredCommandJournalLease));
      return true;
    });
  }

  async renewLease(
    scope: ChildcareCommandJournalScope,
    ownerIdValue: string,
    nowEpochMs: number,
    ttlMs: number,
  ): Promise<boolean> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    return this.run([LEASE_STORE], 'readwrite', async (transaction) => {
      const store = transaction.objectStore(LEASE_STORE);
      const existing = (await this.allLeases(transaction)).find((lease) => lease.lane_key === laneKey) ?? null;
      if (!existing || existing.owner_id !== ownerId) return false;
      await requestResult(store.put({ ...existing, expires_at_epoch_ms: nowEpochMs + ttlMs }));
      return true;
    });
  }

  async releaseLease(scope: ChildcareCommandJournalScope, ownerIdValue: string): Promise<void> {
    const laneKey = childcareCommandJournalLaneKey(scope);
    const ownerId = uuid(ownerIdValue, 'lease owner');
    await this.run([LEASE_STORE], 'readwrite', async (transaction) => {
      const store = transaction.objectStore(LEASE_STORE);
      const existing = (await this.allLeases(transaction)).find((lease) => lease.lane_key === laneKey) ?? null;
      if (!existing) return;
      if (existing.owner_id === ownerId) await requestResult(store.delete(laneKey));
    });
  }
}
