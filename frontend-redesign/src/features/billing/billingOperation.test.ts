import { beforeEach, describe, expect, it } from "vitest";
import { BillingApiError } from "./billingApi";
import {
  BillingOperationConcurrencyError,
  BillingOperationOutcomeUnknownError,
  BillingOperationRecoveryError,
  billingOperationStorageKey,
  executeProtectedBillingCommand,
  purgeVolatileBillingOperationInputs,
  readPendingBillingOperation,
  readVolatileBillingOperationInput,
  type BillingLockManager,
} from "./billingOperation";
import type { BillingCommandPreparation, BillingCommandReceipt } from "./types";

const organizationId = "11111111-1111-4111-8111-111111111111";
const actorId = "22222222-2222-4222-8222-222222222222";
const operationId = "33333333-3333-4333-8333-333333333333";
const accountId = "44444444-4444-4444-8444-444444444444";
const hash = "a".repeat(64);

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
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

const lockManager: BillingLockManager = {
  request: async (_name, _options, callback) => callback({}),
};

function preparation(): BillingCommandPreparation {
  return {
    schema_version: "0033",
    organization_id: organizationId,
    billing_mode: "sandbox",
    sandbox: true,
    provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    client_operation_id: operationId,
    command_type: "payment_record",
    target_scope: accountId,
    request_hash: hash,
    prepared_at: "2026-07-22T18:30:00Z",
    exact_retry: false,
  };
}

function receipt(requestHash = hash): BillingCommandReceipt {
  return {
    schema_version: "0033",
    organization_id: organizationId,
    billing_mode: "sandbox",
    sandbox: true,
    provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    client_operation_id: operationId,
    request_hash: requestHash,
    command_type: "payment_record",
    result_kind: "billing_payment",
    result_id: "55555555-5555-4555-8555-555555555555",
    committed_at: "2026-07-22T18:30:01Z",
    exact_retry: false,
    action_path:
      "/billing?focus=billing_payment&record=55555555-5555-4555-8555-555555555555",
  };
}

const privateInput = {
  account_id: accountId,
  payer_guardian_id: "66666666-6666-4666-8666-666666666666",
  amount_minor: 12_345,
  method: "cash",
  received_at: "2026-07-22T18:30:00.000Z",
  external_reference: "CASH-2026-0001",
  memo: "private family memo must never enter storage",
  operator_confirmation_note: "operator saw the cash receipt",
};

beforeEach(() => purgeVolatileBillingOperationInputs());

describe("redacted exact-operation journal", () => {
  it("prepares before dispatch and stores no command input or free text", async () => {
    const storage = new MemoryStorage();
    let inspected = false;
    const result = await executeProtectedBillingCommand({
      organizationId,
      actorId,
      commandKind: "payment.record",
      input: privateInput,
      storage,
      lockManager,
      uuid: () => operationId,
      prepare: async () => preparation(),
      execute: async () => {
        const raw = storage.getItem(
          billingOperationStorageKey(organizationId, actorId),
        );
        expect(raw).toBeTruthy();
        expect(raw).not.toContain("private family memo");
        expect(raw).not.toContain("operator saw the cash receipt");
        expect(raw).not.toContain('"input"');
        inspected = true;
        return receipt();
      },
    });
    expect(inspected).toBe(true);
    expect(result.request_hash).toBe(hash);
    expect(storage.length).toBe(0);
  });

  it("pins an immutable preview proof before prepare and rejects proof drift without dispatch", async () => {
    const storage = new MemoryStorage();
    let inspectedBeforePrepare = false;
    let dispatched = false;
    await expect(
      executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: "payment.record",
        input: privateInput,
        storage,
        lockManager,
        approvedProof: {
          client_operation_id: operationId,
          command_type: "payment_record",
          target_scope: accountId,
          request_hash: hash,
        },
        prepare: async () => {
          const pending = readPendingBillingOperation(
            organizationId,
            actorId,
            storage,
          );
          expect(pending).toMatchObject({
            client_operation_id: operationId,
            command_kind: "payment.record",
            target_scope: accountId,
            request_hash: hash,
          });
          expect(
            storage.getItem(
              billingOperationStorageKey(organizationId, actorId),
            ),
          ).not.toContain("private family memo");
          inspectedBeforePrepare = true;
          return { ...preparation(), request_hash: "b".repeat(64) };
        },
        execute: async () => {
          dispatched = true;
          return receipt();
        },
      }),
    ).rejects.toThrow("changed after review");
    expect(inspectedBeforePrepare).toBe(true);
    expect(dispatched).toBe(false);
    expect(storage.length).toBe(0);
  });

  it("keeps only the redacted proof when dispatch outcome is unknown", async () => {
    const storage = new MemoryStorage();
    await expect(
      executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: "payment.record",
        input: privateInput,
        storage,
        lockManager,
        uuid: () => operationId,
        prepare: async () => preparation(),
        execute: async () => {
          throw new TypeError("connection lost");
        },
      }),
    ).rejects.toBeInstanceOf(BillingOperationOutcomeUnknownError);
    const pending = readPendingBillingOperation(
      organizationId,
      actorId,
      storage,
    );
    expect(pending?.request_hash).toBe(hash);
    expect(readVolatileBillingOperationInput(pending!)).toEqual(privateInput);
    const raw = storage.getItem(
      billingOperationStorageKey(organizationId, actorId),
    )!;
    expect(raw).not.toContain("memo");
    expect(raw).not.toContain("operator_confirmation_note");
    purgeVolatileBillingOperationInputs(organizationId, actorId);
    expect(readVolatileBillingOperationInput(pending!)).toBeNull();
  });

  it("treats a mismatched 2xx receipt and operation reuse as outcome unknown", async () => {
    for (const execute of [
      async () => receipt("b".repeat(64)),
      async () => {
        throw new BillingApiError("reused", 409, {
          detail: { code: "billing_operation_reused" },
        });
      },
    ]) {
      const storage = new MemoryStorage();
      await expect(
        executeProtectedBillingCommand({
          organizationId,
          actorId,
          commandKind: "payment.record",
          input: privateInput,
          storage,
          lockManager,
          uuid: () => operationId,
          prepare: async () => preparation(),
          execute,
        }),
      ).rejects.toBeInstanceOf(BillingOperationOutcomeUnknownError);
      expect(
        readPendingBillingOperation(organizationId, actorId, storage),
      ).not.toBeNull();
    }
  });

  it("clears a prepared proof after a proven pre-commit validation rejection", async () => {
    const storage = new MemoryStorage();
    await expect(
      executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: "payment.record",
        input: privateInput,
        storage,
        lockManager,
        uuid: () => operationId,
        prepare: async () => preparation(),
        execute: async () => {
          throw new BillingApiError("invalid", 422, {
            detail: [{ loc: ["body", "amount_minor"], msg: "invalid" }],
          });
        },
      }),
    ).rejects.toBeInstanceOf(BillingApiError);
    expect(storage.length).toBe(0);
  });

  it("clears a prepared proof when a duplicate durable payment reference is rejected", async () => {
    const storage = new MemoryStorage();
    await expect(
      executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: "payment.record",
        input: privateInput,
        storage,
        lockManager,
        uuid: () => operationId,
        prepare: async () => preparation(),
        execute: async () => {
          throw new BillingApiError("duplicate receipt reference", 409, {
            detail: { code: "billing_payment_reference_reused" },
          });
        },
      }),
    ).rejects.toBeInstanceOf(BillingApiError);
    expect(storage.length).toBe(0);
  });

  it("redacts legacy input-bearing journals while remaining fail-closed", () => {
    const storage = new MemoryStorage();
    const legacyKey = `caresync:billing-command:v1:${organizationId}:${actorId}`;
    storage.setItem(
      legacyKey,
      JSON.stringify({ input: privateInput, input_fingerprint: "secret" }),
    );
    expect(() =>
      readPendingBillingOperation(organizationId, actorId, storage),
    ).toThrow(BillingOperationRecoveryError);
    expect(storage.getItem(legacyKey)).toBeNull();
    const redacted = storage.getItem(
      billingOperationStorageKey(organizationId, actorId),
    )!;
    expect(redacted).not.toContain("private family memo");
    expect(() =>
      readPendingBillingOperation(organizationId, actorId, storage),
    ).toThrow(BillingOperationRecoveryError);
  });

  it("redacts unknown fields from a malformed v3 proof and remains fail-closed", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      billingOperationStorageKey(organizationId, actorId),
      JSON.stringify({
        version: 3,
        organization_id: organizationId,
        actor_id: actorId,
        client_operation_id: operationId,
        command_kind: "payment.record",
        command_type: "payment_record",
        target_scope: accountId,
        request_hash: hash,
        started_at: "2026-07-22T18:30:00Z",
        memo: "private value that is not part of the proof contract",
      }),
    );
    expect(() =>
      readPendingBillingOperation(organizationId, actorId, storage),
    ).toThrow(BillingOperationRecoveryError);
    const redacted = storage.getItem(
      billingOperationStorageKey(organizationId, actorId),
    )!;
    expect(redacted).not.toContain("private value");
    expect(redacted).toContain("redacted_recovery_required");
  });

  it("refuses to dispatch when the origin-wide lock is unavailable", async () => {
    await expect(
      executeProtectedBillingCommand({
        organizationId,
        actorId,
        commandKind: "payment.record",
        input: privateInput,
        storage: new MemoryStorage(),
        lockManager: null,
        uuid: () => operationId,
        prepare: async () => preparation(),
        execute: async () => receipt(),
      }),
    ).rejects.toBeInstanceOf(BillingOperationConcurrencyError);
  });
});
