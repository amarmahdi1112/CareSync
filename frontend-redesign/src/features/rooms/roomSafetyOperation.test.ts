import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type {
  RoomExceptionAcknowledgementResponse,
  RoomOperationalException,
} from "./roomSafetyApi";
import { roomExceptionAcknowledgementRequestSha256 } from "./roomSafetyApi";
import {
  executeProtectedRoomExceptionAcknowledgement,
  readPendingRoomExceptionAcknowledgement,
  readVolatileRoomExceptionAcknowledgementReason,
  RoomSafetyOperationOutcomeUnknownError,
  RoomSafetyOperationPendingError,
} from "./roomSafetyOperation";

const organizationId = "11111111-1111-4111-8111-111111111111";
const actorUserId = "22222222-2222-4222-8222-222222222222";
const facilityId = "33333333-3333-4333-8333-333333333333";
const roomId = "44444444-4444-4444-8444-444444444444";
const exceptionId = "55555555-5555-4555-8555-555555555555";
const operationId = "66666666-6666-4666-8666-666666666666";
const eventId = "77777777-7777-4777-8777-777777777777";
const now = "2026-07-23T18:00:00.000Z";
const reason = "Coverage call is in progress";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() {
    return this.values.size;
  }
  clear() {
    this.values.clear();
  }
  getItem(key: string) {
    return this.values.get(key) ?? null;
  }
  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.values.delete(key);
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const exception: RoomOperationalException = {
  id: exceptionId,
  facility_id: facilityId,
  scope_kind: "room",
  scope_id: roomId,
  room_id: roomId,
  condition_code: "confirmed_staff_below_configured_room_target",
  state: "open",
  version: 1,
  opened_at: "2026-07-23T17:00:00Z",
  materially_changed_at: null,
  acknowledged_at: null,
  acknowledged_by_user_id: null,
  acknowledgement_reason: null,
  resolved_at: null,
  observed_value: 1,
  configured_value: 2,
  source_integrity_reason_codes: [],
  action_target_path: `/api/v1/room-safety/exceptions/${exceptionId}/action-target`,
};
const scope = { organizationId, actorUserId };

async function response(
  clientOperationId: string,
  digestReason = reason,
): Promise<RoomExceptionAcknowledgementResponse> {
  const requestSha256 = await roomExceptionAcknowledgementRequestSha256({
    organizationId,
    actorUserId,
    exceptionId,
    facilityId,
    roomId,
    operationId: clientOperationId,
    expectedVersion: 1,
    normalizedReason: digestReason,
  });
  return {
    organization_id: organizationId,
    client_operation_id: clientOperationId,
    request_sha256: requestSha256,
    replayed: false,
    receipt: {
      organization_id: organizationId,
      actor_user_id: actorUserId,
      event_id: eventId,
      command_kind: "room_operational_exception_acknowledge",
      event_type: "acknowledged",
      client_operation_id: clientOperationId,
      request_sha256: requestSha256,
      exception_id: exceptionId,
      facility_id: facilityId,
      room_id: roomId,
      expected_version: 1,
      resulting_version: 2,
      occurred_at: now,
    },
    exception: {
      ...exception,
      state: "acknowledged",
      version: 2,
      acknowledged_at: now,
      acknowledged_by_user_id: actorUserId,
      acknowledgement_reason: reason,
    },
    generated_at: now,
  };
}

describe("protected room operational acknowledgement", () => {
  it("stores before send, verifies the actor-bound receipt, and clears only after success", async () => {
    const storage = new MemoryStorage();
    const send = vi.fn(async (id: string) => {
      expect(
        readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage)
          ?.client_operation_id,
      ).toBe(operationId);
      return response(id);
    });
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send,
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).resolves.toMatchObject({ client_operation_id: operationId });
    expect(send).toHaveBeenCalledTimes(1);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage),
    ).toBeNull();
  });

  it("retains an ambiguous result and retries the exact same operation id", async () => {
    const storage = new MemoryStorage();
    const first = vi.fn(async () => {
      throw new Error("connection closed");
    });
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: first,
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).rejects.toBeInstanceOf(RoomSafetyOperationOutcomeUnknownError);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage)
        ?.client_operation_id,
    ).toBe(operationId);
    expect(storage.getItem(storage.key(0)!)).not.toContain(reason);
    const pending = readPendingRoomExceptionAcknowledgement(
      scope,
      exceptionId,
      storage,
    );
    expect(
      pending &&
        readVolatileRoomExceptionAcknowledgementReason(scope, pending),
    ).toBe(reason);

    const retry = vi.fn(async (id: string) => response(id));
    await executeProtectedRoomExceptionAcknowledgement({
      scope,
      exception,
      reason,
      send: retry,
      storage,
      now: () => new Date(now),
      uuid: () => "88888888-8888-4888-8888-888888888888",
    });
    expect(retry).toHaveBeenCalledWith(operationId, 1, reason);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage),
    ).toBeNull();
  });

  it("will not replace a protected acknowledgement with a changed reason", async () => {
    const storage = new MemoryStorage();
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: async () => {
          throw new Error("timeout");
        },
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).rejects.toBeInstanceOf(RoomSafetyOperationOutcomeUnknownError);
    const send = vi.fn();
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason: "A different manager note",
        send,
        storage,
        now: () => new Date(now),
        uuid: () => "88888888-8888-4888-8888-888888888888",
      }),
    ).rejects.toBeInstanceOf(RoomSafetyOperationPendingError);
    expect(send).not.toHaveBeenCalled();
  });

  it("retains the protected operation when matching response digests bind a different reason", async () => {
    const storage = new MemoryStorage();
    const wrongReasonResponse = await response(
      operationId,
      "A different canonical reason",
    );
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: async () => wrongReasonResponse,
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).rejects.toBeInstanceOf(RoomSafetyOperationOutcomeUnknownError);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage)
        ?.client_operation_id,
    ).toBe(operationId);
  });

  it("retains the protected operation when outer and receipt carry the same arbitrary digest", async () => {
    const storage = new MemoryStorage();
    const arbitrary = await response(operationId);
    arbitrary.request_sha256 = "a".repeat(64);
    arbitrary.receipt.request_sha256 = "a".repeat(64);
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: async () => arbitrary,
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).rejects.toBeInstanceOf(RoomSafetyOperationOutcomeUnknownError);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage)
        ?.client_operation_id,
    ).toBe(operationId);
  });

  it("clears a command that the server definitely rejected before commit", async () => {
    const storage = new MemoryStorage();
    await expect(
      executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: async () => {
          throw new ApiError(409, "stale", {
            detail: { code: "stale_exception_version" },
          });
        },
        storage,
        now: () => new Date(now),
        uuid: () => operationId,
      }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(
      readPendingRoomExceptionAcknowledgement(scope, exceptionId, storage),
    ).toBeNull();
  });
});
