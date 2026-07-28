import { createClientOperationId } from '../../api/childcareCommand';

export interface TransportOperationScope {
  actorUserId: string;
  organizationId: string;
}

interface StoredTransportOperation {
  schema_version: 1;
  actor_user_id: string;
  organization_id: string;
  lane: string;
  fingerprint: string;
  operation_id: string;
  created_at: string;
}

export interface PreparedTransportOperation {
  operationId: string;
  exactRetry: boolean;
}

export class TransportOperationJournalError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = 'TransportOperationJournalError';
  }
}

export class TransportOperationPendingError extends TransportOperationJournalError {
  constructor(
    public readonly lane: string,
    public readonly operationId: string,
    public readonly createdAt: string,
  ) {
    super('A different command is already saved in this lane. Retry its original values, or explicitly discard that saved retry before replacing it.');
    this.name = 'TransportOperationPendingError';
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const LANE = /^[a-z0-9][a-z0-9:._-]{0,180}$/i;
const PREFIX = 'caresync:transport-operation:v1:';

function normalizeScope(scope: TransportOperationScope): TransportOperationScope {
  if (!UUID.test(scope.actorUserId) || !UUID.test(scope.organizationId)) {
    throw new TransportOperationJournalError('The transport command identity is invalid.');
  }
  return { actorUserId: scope.actorUserId.toLowerCase(), organizationId: scope.organizationId.toLowerCase() };
}

function normalizeLane(lane: string): string {
  if (!LANE.test(lane)) throw new TransportOperationJournalError('The transport command lane is invalid.');
  return lane.toLowerCase();
}

function key(scope: TransportOperationScope, lane: string): string {
  const normalized = normalizeScope(scope);
  return `${PREFIX}${normalized.actorUserId}:${normalized.organizationId}:${normalizeLane(lane)}`;
}

function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .filter(([, child]) => child !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, child]) => `${JSON.stringify(name)}:${canonical(child)}`)
    .join(',')}}`;
}

async function sha256(value: string | ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new TransportOperationJournalError('Secure transport command hashing is unavailable in this browser.');
  const bytes = typeof value === 'string' ? new TextEncoder().encode(value) : value;
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, '0')).join('');
}

export async function transportIntentFingerprint(intent: unknown, file?: File): Promise<string> {
  const intentHash = await sha256(canonical(intent));
  if (!file) return intentHash;
  const fileHash = await sha256(await file.arrayBuffer());
  const originalFilename = file.name.normalize('NFC');
  return sha256(`${intentHash}:${fileHash}:${file.size}:${file.type}:${originalFilename}`);
}

function parse(value: string, expectedScope: TransportOperationScope, expectedLane: string): StoredTransportOperation {
  let raw: unknown;
  try { raw = JSON.parse(value); } catch (caught) {
    throw new TransportOperationJournalError('The saved transport retry record is corrupted.', caught);
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new TransportOperationJournalError('The saved transport retry record is invalid.');
  const row = raw as Record<string, unknown>;
  const keys = Object.keys(row).sort();
  const expected = ['actor_user_id', 'created_at', 'fingerprint', 'lane', 'operation_id', 'organization_id', 'schema_version'].sort();
  if (keys.length !== expected.length || keys.some((item, index) => item !== expected[index])) throw new TransportOperationJournalError('The saved transport retry record has an unsupported shape.');
  const scope = normalizeScope(expectedScope);
  const lane = normalizeLane(expectedLane);
  if (
    row.schema_version !== 1
    || row.actor_user_id !== scope.actorUserId
    || row.organization_id !== scope.organizationId
    || row.lane !== lane
    || typeof row.fingerprint !== 'string'
    || !/^[0-9a-f]{64}$/.test(row.fingerprint)
    || typeof row.operation_id !== 'string'
    || !UUID.test(row.operation_id)
    || typeof row.created_at !== 'string'
    || !RFC3339.test(row.created_at)
    || !Number.isFinite(Date.parse(row.created_at))
  ) throw new TransportOperationJournalError('The saved transport retry record failed identity validation.');
  return row as unknown as StoredTransportOperation;
}

export function clearTransportOperation(scope: TransportOperationScope, lane: string, operationId?: string, storage: Pick<Storage, 'getItem' | 'removeItem'> = localStorage): void {
  const storageKey = key(scope, lane);
  if (operationId) {
    const value = storage.getItem(storageKey);
    if (!value) return;
    const existing = parse(value, scope, lane);
    if (existing.operation_id.toLowerCase() !== operationId.toLowerCase()) return;
  }
  storage.removeItem(storageKey);
}

export function prepareTransportOperation(
  scope: TransportOperationScope,
  lane: string,
  fingerprint: string,
  storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage,
  now = () => new Date(),
): PreparedTransportOperation {
  if (!/^[0-9a-f]{64}$/.test(fingerprint)) throw new TransportOperationJournalError('The transport command fingerprint is invalid.');
  const normalizedScope = normalizeScope(scope);
  const normalizedLane = normalizeLane(lane);
  const storageKey = key(normalizedScope, normalizedLane);
  try {
    const saved = storage.getItem(storageKey);
    if (saved) {
      const existing = parse(saved, normalizedScope, normalizedLane);
      if (existing.fingerprint === fingerprint) return { operationId: existing.operation_id, exactRetry: true };
      throw new TransportOperationPendingError(normalizedLane, existing.operation_id, existing.created_at);
    }
    const operationId = createClientOperationId().toLowerCase();
    const entry: StoredTransportOperation = {
      schema_version: 1,
      actor_user_id: normalizedScope.actorUserId,
      organization_id: normalizedScope.organizationId,
      lane: normalizedLane,
      fingerprint,
      operation_id: operationId,
      created_at: now().toISOString(),
    };
    storage.setItem(storageKey, JSON.stringify(entry));
    return { operationId, exactRetry: false };
  } catch (caught) {
    if (caught instanceof TransportOperationJournalError) throw caught;
    throw new TransportOperationJournalError('The transport command could not be durably prepared. No request was sent.', caught);
  }
}

export async function withTransportOperation<T extends { client_operation_id: string }>(options: {
  scope: TransportOperationScope;
  lane: string;
  intent: unknown;
  file?: File;
  send: (operationId: string) => Promise<T>;
}): Promise<T> {
  const fingerprint = await transportIntentFingerprint(options.intent, options.file);
  const prepared = prepareTransportOperation(options.scope, options.lane, fingerprint);
  const result = await options.send(prepared.operationId);
  if (result.client_operation_id.toLowerCase() !== prepared.operationId) {
    throw new TransportOperationJournalError('The transport command receipt did not match its durable operation.');
  }
  clearTransportOperation(options.scope, options.lane, prepared.operationId);
  return result;
}
