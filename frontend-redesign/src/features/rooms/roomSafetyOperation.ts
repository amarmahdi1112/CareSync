import { ApiError } from "../../api/client";
import { createClientOperationId } from "../../api/childcareCommand";
import {
  RoomSafetyContractError,
  normalizeRoomExceptionAcknowledgementReason,
  roomExceptionAcknowledgementRequestSha256,
  roomSafetyApiErrorCode,
  type RoomExceptionAcknowledgementResponse,
  type RoomOperationalException,
} from "./roomSafetyApi";

export interface RoomSafetyOperationScope {
  organizationId: string;
  actorUserId: string;
}

export interface PendingRoomExceptionAcknowledgement {
  schema_version: 1;
  organization_id: string;
  actor_user_id: string;
  exception_id: string;
  expected_version: number;
  fingerprint: string;
  client_operation_id: string;
  created_at: string;
}

export class RoomSafetyOperationError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "RoomSafetyOperationError";
  }
}

export class RoomSafetyOperationPendingError extends RoomSafetyOperationError {
  constructor(
    public readonly pending: PendingRoomExceptionAcknowledgement,
  ) {
    super(
      "A different acknowledgement is already protected for this exception. Retry its exact version and reason; CareSync will not replace it.",
    );
    this.name = "RoomSafetyOperationPendingError";
  }
}

export class RoomSafetyOperationOutcomeUnknownError extends RoomSafetyOperationError {
  constructor(
    public readonly pending: PendingRoomExceptionAcknowledgement,
    options?: { cause?: unknown },
  ) {
    super(
      "CareSync could not confirm the acknowledgement receipt. The exact operation is protected and must be retried with the same reason.",
      options,
    );
    this.name = "RoomSafetyOperationOutcomeUnknownError";
  }
}

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const RFC3339 =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const PREFIX = "caresync:room-exception-ack:v1:";
const KEYS = [
  "schema_version",
  "organization_id",
  "actor_user_id",
  "exception_id",
  "expected_version",
  "fingerprint",
  "client_operation_id",
  "created_at",
] as const;
const volatileReasons = new Map<
  string,
  {
    organization_id: string;
    actor_user_id: string;
    exception_id: string;
    reason: string;
  }
>();

function normalizeScope(scope: RoomSafetyOperationScope) {
  if (!UUID.test(scope.organizationId) || !UUID.test(scope.actorUserId))
    throw new RoomSafetyOperationError(
      "The acknowledgement identity is invalid.",
    );
  return {
    organizationId: scope.organizationId.toLowerCase(),
    actorUserId: scope.actorUserId.toLowerCase(),
  };
}

function normalizeExceptionId(exceptionId: string): string {
  if (!UUID.test(exceptionId))
    throw new RoomSafetyOperationError(
      "The acknowledgement exception is invalid.",
    );
  return exceptionId.toLowerCase();
}

export function roomSafetyOperationStorageKey(
  scope: RoomSafetyOperationScope,
  exceptionId: string,
): string {
  const normalized = normalizeScope(scope);
  return `${PREFIX}${normalized.organizationId}:${normalized.actorUserId}:${normalizeExceptionId(exceptionId)}`;
}

function parsePending(
  value: string,
  scope: RoomSafetyOperationScope,
  exceptionId: string,
): PendingRoomExceptionAcknowledgement {
  let raw: unknown;
  try {
    raw = JSON.parse(value);
  } catch (cause) {
    throw new RoomSafetyOperationError(
      "The protected acknowledgement record is unreadable.",
      { cause },
    );
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new RoomSafetyOperationError(
      "The protected acknowledgement record is invalid.",
    );
  const row = raw as Record<string, unknown>;
  const keys = Object.keys(row).sort();
  const expectedKeys = [...KEYS].sort();
  const normalized = normalizeScope(scope);
  const expectedExceptionId = normalizeExceptionId(exceptionId);
  if (
    keys.length !== expectedKeys.length ||
    keys.some((key, index) => key !== expectedKeys[index]) ||
    row.schema_version !== 1 ||
    row.organization_id !== normalized.organizationId ||
    row.actor_user_id !== normalized.actorUserId ||
    row.exception_id !== expectedExceptionId ||
    !Number.isSafeInteger(row.expected_version) ||
    Number(row.expected_version) < 1 ||
    typeof row.fingerprint !== "string" ||
    !SHA256.test(row.fingerprint) ||
    typeof row.client_operation_id !== "string" ||
    !UUID.test(row.client_operation_id) ||
    typeof row.created_at !== "string" ||
    !RFC3339.test(row.created_at) ||
    !Number.isFinite(Date.parse(row.created_at))
  )
    throw new RoomSafetyOperationError(
      "The protected acknowledgement record failed identity validation.",
    );
  return row as unknown as PendingRoomExceptionAcknowledgement;
}

export function readPendingRoomExceptionAcknowledgement(
  scope: RoomSafetyOperationScope,
  exceptionId: string,
  storage: Pick<Storage, "getItem"> = localStorage,
): PendingRoomExceptionAcknowledgement | null {
  const value = storage.getItem(
    roomSafetyOperationStorageKey(scope, exceptionId),
  );
  return value ? parsePending(value, scope, exceptionId) : null;
}

export function listPendingRoomExceptionAcknowledgements(
  scope: RoomSafetyOperationScope,
  storage: Pick<Storage, "length" | "key" | "getItem"> = localStorage,
): PendingRoomExceptionAcknowledgement[] {
  const normalized = normalizeScope(scope);
  const prefix = `${PREFIX}${normalized.organizationId}:${normalized.actorUserId}:`;
  const pending: PendingRoomExceptionAcknowledgement[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (!key?.startsWith(prefix)) continue;
    const exceptionId = key.slice(prefix.length);
    const value = storage.getItem(key);
    if (!value) continue;
    pending.push(parsePending(value, normalized, exceptionId));
  }
  return pending.sort((left, right) =>
    left.created_at.localeCompare(right.created_at),
  );
}

export function clearPendingRoomExceptionAcknowledgement(
  scope: RoomSafetyOperationScope,
  exceptionId: string,
  operationId: string,
  storage: Pick<Storage, "getItem" | "removeItem"> = localStorage,
): void {
  const key = roomSafetyOperationStorageKey(scope, exceptionId);
  const value = storage.getItem(key);
  if (!value) return;
  const pending = parsePending(value, scope, exceptionId);
  if (pending.client_operation_id === operationId.toLowerCase()) {
    storage.removeItem(key);
    volatileReasons.delete(pending.client_operation_id);
  }
}

export function readVolatileRoomExceptionAcknowledgementReason(
  scope: RoomSafetyOperationScope,
  pending: PendingRoomExceptionAcknowledgement,
): string | null {
  const normalized = normalizeScope(scope);
  const value = volatileReasons.get(pending.client_operation_id);
  if (
    !value ||
    value.organization_id !== normalized.organizationId ||
    value.actor_user_id !== normalized.actorUserId ||
    value.exception_id !== pending.exception_id
  )
    return null;
  return value.reason;
}

function canonical(value: unknown): string {
  if (value === null || typeof value !== "object")
    return JSON.stringify(value);
  if (Array.isArray(value))
    return `[${value.map((item) => canonical(item)).join(",")}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .filter(([, child]) => child !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`)
    .join(",")}}`;
}

async function sha256(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle)
    throw new RoomSafetyOperationError(
      "Secure acknowledgement hashing is unavailable. No command was sent.",
    );
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return [...new Uint8Array(digest)]
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("");
}

export async function roomExceptionAcknowledgementFingerprint(input: {
  exceptionId: string;
  expectedVersion: number;
  reason: string;
}): Promise<string> {
  return sha256(
    canonical({
      exception_id: normalizeExceptionId(input.exceptionId),
      expected_version: input.expectedVersion,
      reason: normalizeRoomExceptionAcknowledgementReason(input.reason),
    }),
  );
}

async function prepare(input: {
  scope: RoomSafetyOperationScope;
  exceptionId: string;
  expectedVersion: number;
  reason: string;
  storage: Pick<Storage, "getItem" | "setItem">;
  now: () => Date;
  uuid: () => string;
}): Promise<PendingRoomExceptionAcknowledgement> {
  const normalized = normalizeScope(input.scope);
  const exceptionId = normalizeExceptionId(input.exceptionId);
  const fingerprint = await roomExceptionAcknowledgementFingerprint({
    exceptionId,
    expectedVersion: input.expectedVersion,
    reason: input.reason,
  });
  const key = roomSafetyOperationStorageKey(normalized, exceptionId);
  try {
    const saved = input.storage.getItem(key);
    if (saved) {
      const existing = parsePending(saved, normalized, exceptionId);
      if (
        existing.expected_version === input.expectedVersion &&
        existing.fingerprint === fingerprint
      ) {
        volatileReasons.set(existing.client_operation_id, {
          organization_id: normalized.organizationId,
          actor_user_id: normalized.actorUserId,
          exception_id: exceptionId,
          reason: normalizeRoomExceptionAcknowledgementReason(input.reason),
        });
        return existing;
      }
      throw new RoomSafetyOperationPendingError(existing);
    }
    const operationId = input.uuid().toLowerCase();
    if (!UUID.test(operationId))
      throw new RoomSafetyOperationError(
        "A secure acknowledgement operation could not be created.",
      );
    const pending: PendingRoomExceptionAcknowledgement = {
      schema_version: 1,
      organization_id: normalized.organizationId,
      actor_user_id: normalized.actorUserId,
      exception_id: exceptionId,
      expected_version: input.expectedVersion,
      fingerprint,
      client_operation_id: operationId,
      created_at: input.now().toISOString(),
    };
    input.storage.setItem(key, JSON.stringify(pending));
    const confirmed = input.storage.getItem(key);
    if (!confirmed || parsePending(confirmed, normalized, exceptionId).client_operation_id !== operationId)
      throw new RoomSafetyOperationError(
        "CareSync could not confirm the protected acknowledgement record. No command was sent.",
      );
    volatileReasons.set(operationId, {
      organization_id: normalized.organizationId,
      actor_user_id: normalized.actorUserId,
      exception_id: exceptionId,
      reason: normalizeRoomExceptionAcknowledgementReason(input.reason),
    });
    return pending;
  } catch (cause) {
    if (cause instanceof RoomSafetyOperationError) throw cause;
    throw new RoomSafetyOperationError(
      "CareSync could not protect the acknowledgement operation. No command was sent.",
      { cause },
    );
  }
}

function wasDefinitelyRejectedBeforeCommit(caught: unknown): boolean {
  if (!(caught instanceof ApiError)) return false;
  if ([400, 401, 403, 404, 422].includes(caught.status)) return true;
  if (caught.status !== 409) return false;
  return [
    "stale_exception_version",
    "exception_not_active",
    "exception_resolved",
  ].includes(
    roomSafetyApiErrorCode(caught) || "",
  );
}

export async function executeProtectedRoomExceptionAcknowledgement(input: {
  scope: RoomSafetyOperationScope;
  exception: RoomOperationalException;
  reason: string;
  send: (
    operationId: string,
    expectedVersion: number,
    normalizedReason: string,
  ) => Promise<RoomExceptionAcknowledgementResponse>;
  storage?: Storage;
  now?: () => Date;
  uuid?: () => string;
}): Promise<RoomExceptionAcknowledgementResponse> {
  const storage = input.storage ?? localStorage;
  const normalizedReason = normalizeRoomExceptionAcknowledgementReason(
    input.reason,
  );
  const pending = await prepare({
    scope: input.scope,
    exceptionId: input.exception.id,
    expectedVersion: input.exception.version,
    reason: normalizedReason,
    storage,
    now: input.now ?? (() => new Date()),
    uuid: input.uuid ?? createClientOperationId,
  });
  try {
    const response = await input.send(
      pending.client_operation_id,
      pending.expected_version,
      normalizedReason,
    );
    if (
      response.organization_id !== pending.organization_id ||
      response.client_operation_id !== pending.client_operation_id ||
      response.receipt.exception_id !== pending.exception_id ||
      response.receipt.actor_user_id !== pending.actor_user_id
    )
      throw new RoomSafetyContractError(
        "The acknowledgement receipt did not match its protected operation.",
      );
    const canonicalRequestHash =
      await roomExceptionAcknowledgementRequestSha256({
        organizationId: pending.organization_id,
        actorUserId: pending.actor_user_id,
        exceptionId: pending.exception_id,
        facilityId: input.exception.facility_id,
        roomId: input.exception.room_id,
        operationId: pending.client_operation_id,
        expectedVersion: pending.expected_version,
        normalizedReason,
      });
    if (
      response.request_sha256 !== canonicalRequestHash ||
      response.receipt.request_sha256 !== canonicalRequestHash
    )
      throw new RoomSafetyContractError(
        "The acknowledgement receipt digest did not match its protected operation.",
      );
    clearPendingRoomExceptionAcknowledgement(
      input.scope,
      input.exception.id,
      pending.client_operation_id,
      storage,
    );
    return response;
  } catch (cause) {
    if (wasDefinitelyRejectedBeforeCommit(cause)) {
      clearPendingRoomExceptionAcknowledgement(
        input.scope,
        input.exception.id,
        pending.client_operation_id,
        storage,
      );
      throw cause;
    }
    if (cause instanceof RoomSafetyOperationPendingError) throw cause;
    throw new RoomSafetyOperationOutcomeUnknownError(pending, { cause });
  }
}
