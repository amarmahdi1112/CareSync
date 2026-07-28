import { BillingApiError } from "./billingApi";
import { billingCommandType } from "./billingIntent";
import type {
  BillingCommandKind,
  BillingCommandPreparation,
  BillingCommandReceipt,
} from "./types";

export interface PendingBillingOperation {
  version: 3;
  organization_id: string;
  actor_id: string;
  client_operation_id: string;
  command_kind: BillingCommandKind;
  command_type: BillingCommandReceipt["command_type"];
  target_scope: string;
  request_hash: string;
  started_at: string;
}

export class BillingOperationLockedError extends Error {
  constructor(public readonly pending: PendingBillingOperation) {
    super(
      "Another billing command has an unresolved outcome. Reconcile that protected command before making another financial change.",
    );
    this.name = "BillingOperationLockedError";
  }
}

export class BillingOperationOutcomeUnknownError extends Error {
  constructor(
    public readonly pending: PendingBillingOperation,
    options?: { cause?: unknown },
  ) {
    super(
      "The server may have committed this command, but its receipt was not confirmed. Its redacted operation proof remains protected for reconciliation.",
      options,
    );
    this.name = "BillingOperationOutcomeUnknownError";
  }
}

export class BillingOperationRecoveryError extends Error {
  constructor(
    message = "The protected billing recovery record is unreadable. Financial changes are locked in this browser profile until the record is reconciled safely.",
    options?: { cause?: unknown },
  ) {
    super(message, options);
    this.name = "BillingOperationRecoveryError";
  }
}

export class BillingOperationConcurrencyError extends Error {
  constructor(
    message = "CareSync could not acquire the browser-profile billing lock. No financial command was sent.",
  ) {
    super(message);
    this.name = "BillingOperationConcurrencyError";
  }
}

export interface BillingLockManager {
  request<T>(
    name: string,
    options: { mode: "exclusive"; ifAvailable: true },
    callback: (lock: unknown | null) => Promise<T>,
  ): Promise<T>;
}

export interface ApprovedBillingCommandProof {
  client_operation_id: string;
  command_type: BillingCommandReceipt["command_type"];
  target_scope: string;
  request_hash: string;
}

const COMMAND_KINDS: readonly BillingCommandKind[] = [
  "account.create",
  "account.payer.assign",
  "rate_plan.create",
  "agreement.create",
  "invoice.issue",
  "payment.record",
  "payment.allocate",
  "credit.create",
];
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const PENDING_KEYS = [
  "actor_id",
  "client_operation_id",
  "command_kind",
  "command_type",
  "organization_id",
  "request_hash",
  "started_at",
  "target_scope",
  "version",
] as const;
const volatileInputs = new Map<
  string,
  {
    organization_id: string;
    actor_id: string;
    input: Record<string, unknown>;
  }
>();

export function billingOperationStorageKey(
  organizationId: string,
  actorId: string,
): string {
  return `caresync:billing-command:v3:${organizationId}:${actorId}`;
}

function redactLegacyJournal(
  organizationId: string,
  actorId: string,
  storage: Storage,
): void {
  const legacyKeys = [
    `caresync:billing-command:v1:${organizationId}:${actorId}`,
    `caresync:billing-command:v2:${organizationId}:${actorId}`,
  ];
  const found = legacyKeys.filter((key) => storage.getItem(key) != null);
  if (!found.length) return;
  storage.setItem(
    billingOperationStorageKey(organizationId, actorId),
    JSON.stringify({
      version: 3,
      organization_id: organizationId,
      actor_id: actorId,
      legacy_redacted_recovery_required: true,
    }),
  );
  found.forEach((key) => storage.removeItem(key));
  throw new BillingOperationRecoveryError(
    "A legacy billing journal was redacted because it could contain private form values. Financial commands remain locked until support reconciles the earlier operation.",
  );
}

function isPending(
  value: unknown,
  organizationId: string,
  actorId: string,
): value is PendingBillingOperation {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return (
    Object.keys(row).sort().join("|") === [...PENDING_KEYS].sort().join("|") &&
    row.version === 3 &&
    row.organization_id === organizationId &&
    row.actor_id === actorId &&
    typeof row.client_operation_id === "string" &&
    UUID.test(row.client_operation_id) &&
    typeof row.command_kind === "string" &&
    COMMAND_KINDS.includes(row.command_kind as BillingCommandKind) &&
    row.command_type ===
      billingCommandType(row.command_kind as BillingCommandKind) &&
    typeof row.target_scope === "string" &&
    row.target_scope.length > 0 &&
    row.target_scope.length <= 255 &&
    typeof row.request_hash === "string" &&
    SHA256.test(row.request_hash) &&
    typeof row.started_at === "string" &&
    !Number.isNaN(Date.parse(row.started_at))
  );
}

export function readPendingBillingOperation(
  organizationId: string,
  actorId: string,
  storage: Storage = window.localStorage,
): PendingBillingOperation | null {
  try {
    redactLegacyJournal(organizationId, actorId, storage);
    const raw = storage.getItem(
      billingOperationStorageKey(organizationId, actorId),
    );
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isPending(parsed, organizationId, actorId)) {
      storage.setItem(
        billingOperationStorageKey(organizationId, actorId),
        JSON.stringify({
          version: 3,
          organization_id: organizationId,
          actor_id: actorId,
          redacted_recovery_required: true,
        }),
      );
      throw new BillingOperationRecoveryError();
    }
    return parsed;
  } catch (cause) {
    if (cause instanceof BillingOperationRecoveryError) throw cause;
    throw new BillingOperationRecoveryError(undefined, { cause });
  }
}

function persistPending(
  operation: PendingBillingOperation,
  storage: Storage,
): void {
  try {
    storage.setItem(
      billingOperationStorageKey(operation.organization_id, operation.actor_id),
      JSON.stringify(operation),
    );
  } catch (cause) {
    throw new Error(
      "CareSync could not protect the redacted billing operation proof. No financial command was sent.",
      { cause },
    );
  }
}

export function clearPendingBillingOperation(
  operation: PendingBillingOperation,
  storage: Storage = window.localStorage,
): void {
  const current = readPendingBillingOperation(
    operation.organization_id,
    operation.actor_id,
    storage,
  );
  if (current?.client_operation_id === operation.client_operation_id) {
    storage.removeItem(
      billingOperationStorageKey(operation.organization_id, operation.actor_id),
    );
    volatileInputs.delete(operation.client_operation_id);
  }
}

export function readVolatileBillingOperationInput(
  operation: PendingBillingOperation,
): Record<string, unknown> | null {
  const entry = volatileInputs.get(operation.client_operation_id);
  return entry?.organization_id === operation.organization_id &&
    entry.actor_id === operation.actor_id
    ? entry.input
    : null;
}

export function purgeVolatileBillingOperationInputs(
  organizationId?: string,
  actorId?: string,
): void {
  if (!organizationId || !actorId) {
    volatileInputs.clear();
    return;
  }
  volatileInputs.forEach((entry, operationId) => {
    if (entry.organization_id === organizationId && entry.actor_id === actorId)
      volatileInputs.delete(operationId);
  });
}

function billingErrorCode(details: unknown): string | null {
  if (!details || typeof details !== "object" || Array.isArray(details))
    return null;
  const detail = (details as { detail?: unknown }).detail;
  return detail &&
    typeof detail === "object" &&
    !Array.isArray(detail) &&
    typeof (detail as { code?: unknown }).code === "string"
    ? String((detail as { code: string }).code)
    : null;
}

const NO_COMMIT_CODES = new Set([
  "billing_account_already_exists",
  "billing_account_missing",
  "billing_account_not_found",
  "billing_account_payer_history_missing",
  "billing_account_payer_needs_review",
  "billing_account_payer_unchanged",
  "billing_account_payer_version_stale",
  "billing_agreement_account_or_child_not_found",
  "billing_agreement_already_exists_for_child",
  "billing_agreement_child_missing",
  "billing_agreement_has_no_version",
  "billing_agreement_immutable_scope_mismatch",
  "billing_agreement_not_effective_for_period",
  "billing_agreement_not_found",
  "billing_agreement_not_reviewed",
  "billing_agreement_period_already_invoiced",
  "billing_agreement_portion_drift",
  "billing_agreement_rate_drift",
  "billing_agreement_rate_portions_do_not_balance",
  "billing_agreement_version_effective_order_invalid",
  "billing_agreement_version_stale",
  "billing_allocation_account_mismatch",
  "billing_allocation_projection_stale",
  "billing_allocation_source_drift",
  "billing_credit_exceeds_outstanding",
  "billing_credit_projection_stale",
  "billing_credit_source_drift",
  "billing_current_enrollment_required",
  "billing_enrollment_not_billable_for_period",
  "billing_enrollment_not_current_for_agreement",
  "billing_enrollment_not_found",
  "billing_enrollment_program_inactive",
  "billing_enrollment_program_scope_drift",
  "billing_family_or_payer_not_found",
  "billing_funding_rules_unavailable",
  "billing_invoice_has_no_family_charge",
  "billing_invoice_issue_date_must_be_today",
  "billing_invoice_not_found",
  "billing_invoice_overallocated",
  "billing_mixed_agreement_frequencies",
  "billing_money_limit_exceeded",
  "billing_payer_guardian_not_found",
  "billing_payment_or_invoice_not_found",
  "billing_payment_overallocated",
  "billing_payment_payer_not_found",
  "billing_payment_received_at_in_future",
  "billing_payment_reference_reused",
  "billing_permission_required",
  "billing_rate_age_group_mismatch",
  "billing_rate_enrollment_scope_mismatch",
  "billing_rate_not_effective_for_agreement",
  "billing_rate_plan_has_no_version",
  "billing_rate_plan_not_found",
  "billing_rate_program_scope_mismatch",
  "billing_rate_program_type_mismatch",
  "billing_rate_unit_frequency_mismatch",
  "billing_rate_version_effective_order_invalid",
  "billing_rate_version_not_found",
  "billing_rate_version_stale",
  "billing_sandbox_writes_disabled",
  "billing_service_period_frequency_mismatch",
]);

export function billingOutcomeIsUnknown(caught: unknown): boolean {
  if (caught instanceof BillingApiError) {
    if (
      caught.status == null ||
      caught.status === 408 ||
      caught.status === 425 ||
      caught.status === 429 ||
      caught.status >= 500
    )
      return true;
    const code = billingErrorCode(caught.details);
    if (
      [
        "billing_operation_reused",
        "billing_operation_already_committed",
        "billing_operation_finalized_absent",
        "billing_command_conflict",
        "billing_operation_reconciliation_conflict",
        "billing_command_receipt_not_found",
      ].includes(code || "")
    )
      return true;
    if (code && NO_COMMIT_CODES.has(code)) return false;
    if (
      caught.status === 422 &&
      caught.details &&
      typeof caught.details === "object" &&
      Array.isArray((caught.details as { detail?: unknown }).detail)
    )
      return false;
    return true;
  }
  return caught instanceof TypeError || caught instanceof DOMException;
}

export async function withBillingOperationLock<T>(options: {
  organizationId: string;
  actorId: string;
  run: () => Promise<T>;
  lockManager?: BillingLockManager | null;
}): Promise<T> {
  const lockManager =
    options.lockManager === undefined
      ? typeof navigator !== "undefined" && navigator.locks
        ? (navigator.locks as unknown as BillingLockManager)
        : null
      : options.lockManager;
  if (!lockManager) throw new BillingOperationConcurrencyError();
  const lockName = `caresync:billing-command:${options.organizationId}:${options.actorId}`;
  return lockManager.request(
    lockName,
    { mode: "exclusive", ifAvailable: true },
    async (lock) => {
      if (!lock)
        throw new BillingOperationConcurrencyError(
          "Another CareSync tab is currently protecting a billing command. No financial command was sent here.",
        );
      return options.run();
    },
  );
}

export async function executeProtectedBillingCommand(options: {
  organizationId: string;
  actorId: string;
  commandKind: BillingCommandKind;
  input: Record<string, unknown>;
  approvedProof?: ApprovedBillingCommandProof;
  prepare: (operationId: string) => Promise<BillingCommandPreparation>;
  execute: (operationId: string) => Promise<BillingCommandReceipt>;
  storage?: Storage;
  now?: () => Date;
  uuid?: () => string;
  lockManager?: BillingLockManager | null;
}): Promise<BillingCommandReceipt> {
  const storage = options.storage ?? window.localStorage;
  return withBillingOperationLock({
    organizationId: options.organizationId,
    actorId: options.actorId,
    lockManager: options.lockManager,
    run: async () => {
      const existing = readPendingBillingOperation(
        options.organizationId,
        options.actorId,
        storage,
      );
      if (
        existing &&
        (existing.command_kind !== options.commandKind ||
          (options.approvedProof &&
            existing.client_operation_id !==
              options.approvedProof.client_operation_id))
      )
        throw new BillingOperationLockedError(existing);
      const operationId =
        existing?.client_operation_id ??
        options.approvedProof?.client_operation_id ??
        (options.uuid ?? (() => crypto.randomUUID()))();
      const expectedCommandType = billingCommandType(options.commandKind);
      if (
        options.approvedProof &&
        (options.approvedProof.client_operation_id !== operationId ||
          options.approvedProof.command_type !== expectedCommandType ||
          !options.approvedProof.target_scope ||
          !SHA256.test(options.approvedProof.request_hash))
      )
        throw new BillingOperationRecoveryError(
          "The reviewed billing approval proof did not match this command. No financial command was sent.",
        );
      const approvedPending: PendingBillingOperation | null =
        !existing && options.approvedProof
          ? {
              version: 3,
              organization_id: options.organizationId,
              actor_id: options.actorId,
              client_operation_id: operationId,
              command_kind: options.commandKind,
              command_type: options.approvedProof.command_type,
              target_scope: options.approvedProof.target_scope,
              request_hash: options.approvedProof.request_hash,
              started_at: (options.now ?? (() => new Date()))().toISOString(),
            }
          : null;
      if (approvedPending) {
        persistPending(approvedPending, storage);
        volatileInputs.set(operationId, {
          organization_id: options.organizationId,
          actor_id: options.actorId,
          input: options.input,
        });
      }
      let prepared: BillingCommandPreparation;
      try {
        prepared = await options.prepare(operationId);
      } catch (caught) {
        if (approvedPending) clearPendingBillingOperation(approvedPending, storage);
        throw caught;
      }
      if (
        prepared.organization_id !== options.organizationId ||
        prepared.client_operation_id !== operationId ||
        prepared.command_type !== expectedCommandType ||
        !prepared.target_scope ||
        !SHA256.test(prepared.request_hash)
      ) {
        if (approvedPending) clearPendingBillingOperation(approvedPending, storage);
        throw new BillingOperationRecoveryError(
          "The server preparation proof did not match this billing command. No financial command was sent.",
        );
      }
      if (
        options.approvedProof &&
        (prepared.command_type !== options.approvedProof.command_type ||
          prepared.target_scope !== options.approvedProof.target_scope ||
          prepared.request_hash !== options.approvedProof.request_hash)
      ) {
        if (approvedPending) clearPendingBillingOperation(approvedPending, storage);
        throw new BillingOperationRecoveryError(
          "The server preparation proof changed after review. No financial command was sent.",
        );
      }
      if (
        existing &&
        (existing.command_type !== prepared.command_type ||
          existing.target_scope !== prepared.target_scope ||
          existing.request_hash !== prepared.request_hash)
      )
        throw new BillingOperationLockedError(existing);
      const pending: PendingBillingOperation = existing ?? approvedPending ?? {
        version: 3,
        organization_id: options.organizationId,
        actor_id: options.actorId,
        client_operation_id: operationId,
        command_kind: options.commandKind,
        command_type: prepared.command_type,
        target_scope: prepared.target_scope,
        request_hash: prepared.request_hash,
        started_at: (options.now ?? (() => new Date()))().toISOString(),
      };
      persistPending(pending, storage);
      volatileInputs.set(operationId, {
        organization_id: options.organizationId,
        actor_id: options.actorId,
        input: options.input,
      });
      try {
        const receipt = await options.execute(operationId);
        if (receipt.request_hash !== pending.request_hash)
          throw new BillingOperationOutcomeUnknownError(pending, {
            cause: new Error(
              "The committed receipt hash did not match the server-prepared billing proof.",
            ),
          });
        clearPendingBillingOperation(pending, storage);
        return receipt;
      } catch (caught) {
        if (caught instanceof BillingOperationOutcomeUnknownError) throw caught;
        if (billingOutcomeIsUnknown(caught))
          throw new BillingOperationOutcomeUnknownError(pending, {
            cause: caught,
          });
        clearPendingBillingOperation(pending, storage);
        throw caught;
      }
    },
  });
}
