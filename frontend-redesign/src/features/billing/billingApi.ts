import {
  API_URL,
  ApiError,
  addOrganizationHeader,
  apiRequest,
  getSessionToken,
  notifyAuthorizationDenied,
} from "../../api/client";
import { featureIntegrationManifest } from "../../realtime/featureIntegrationManifest";
import { asMinorUnits, isDateOnly } from "./billingModel";
import { billingCommandType, billingPreparePayload } from "./billingIntent";
import type {
  AllocatePaymentInput,
  AssignBillingAccountPayerInput,
  BillingAccountDetail,
  BillingAccountPayerVersion,
  BillingAccountSummary,
  BillingAgreement,
  BillingAgreementVersion,
  BillingAllocation,
  BillingCapability,
  BillingCommandKind,
  BillingCommandPreparation,
  BillingCommandReceipt,
  BillingFamilyOption,
  BillingFamilyOptions,
  BillingCredit,
  BillingInvoice,
  BillingInvoiceDocumentPreview,
  BillingInvoiceLine,
  BillingManualActivation,
  BillingOverview,
  BillingPageResult,
  BillingPayment,
  BillingProvenance,
  BillingProvenanceLabel,
  BillingRuntimeMode,
  BillingProgramOption,
  BillingRatePlan,
  BillingRatePlanVersion,
  BillingWorkspaceCollection,
  BillingWorkspacePage,
  BillingWorkspaceProjection,
  CreateAgreementInput,
  CreateBillingAccountInput,
  CreateCreditInput,
  CreateRatePlanInput,
  IssueInvoiceInput,
  MinorUnits,
  RecordPaymentInput,
} from "./types";

export const BILLING_CAPABILITY_PATH = "/billing/capability" as const;
export const BILLING_MANUAL_ACTIVATION_PATH =
  "/billing/manual-activation" as const;
export const BILLING_MANUAL_ACTIVATION_POLICY =
  "private_local_manual_billing_v1" as const;
export const BILLING_MANUAL_REVIEW_ATTESTATION =
  "I reviewed the private manual billing boundary and understand that CareSync will only record off-platform payments." as const;
export const BILLING_SYNTHETIC_PROVENANCE =
  "TEST/SYNTHETIC — NOT A REAL INVOICE" as const;
export const BILLING_MANUAL_PROVENANCE =
  "PRIVATE/MANUAL — OFF-PLATFORM RECORD" as const;
export const BILLING_REALTIME_ENTITIES =
  featureIntegrationManifest.billing.realtimeEntities;
const SCHEMA = "0033" as const;
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class BillingApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "BillingApiError";
  }
}

function invalid(label: string): never {
  throw new BillingApiError(`The server returned invalid ${label}.`);
}
function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalid(label);
  return value as Record<string, unknown>;
}
function text(value: unknown, label: string, maximum = 4096): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum)
    invalid(label);
  return value;
}
function optionalText(
  value: unknown,
  label: string,
  maximum = 4096,
): string | null {
  return value == null || value === "" ? null : text(value, label, maximum);
}
function boundedString(value: unknown, label: string, maximum: number): string {
  if (typeof value !== "string" || value.length > maximum) invalid(label);
  return value;
}
function id(value: unknown, label: string): string {
  const result = text(value, label, 64);
  if (!UUID.test(result)) invalid(label);
  return result;
}
function sha256(value: unknown, label: string): string {
  const result = text(value, label, 64);
  if (!/^[0-9a-f]{64}$/.test(result)) invalid(label);
  return result;
}
function integer(
  value: unknown,
  label: string,
  minimum = 0,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  if (
    !Number.isSafeInteger(value) ||
    Number(value) < minimum ||
    Number(value) > maximum
  )
    invalid(label);
  return Number(value);
}
function minor(value: unknown, label: string, positive = false): MinorUnits {
  const amount = integer(
    value,
    `${label}; money must use integer minor units`,
    positive ? 1 : 0,
    9_000_000_000_000,
  );
  return asMinorUnits(amount, label);
}
function checkedAdd(label: string, ...values: number[]): number {
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!Number.isSafeInteger(total) || total > 9_000_000_000_000)
    invalid(`${label} overflow`);
  return total;
}
function checkedMultiply(label: string, left: number, right: number): number {
  const total = left * right;
  if (!Number.isSafeInteger(total) || total > 9_000_000_000_000)
    invalid(`${label} overflow`);
  return total;
}
function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") invalid(label);
  return value;
}
function enumValue<T extends string>(
  value: unknown,
  values: readonly T[],
  label: string,
): T {
  if (typeof value !== "string" || !values.includes(value as T)) invalid(label);
  return value as T;
}
function date(value: unknown, label: string): string {
  const result = text(value, label, 10);
  if (!isDateOnly(result)) invalid(label);
  return result;
}
function optionalDate(value: unknown, label: string): string | null {
  return value == null || value === "" ? null : date(value, label);
}
function timestamp(value: unknown, label: string): string {
  const result = text(value, label, 64);
  const parsed = new Date(result);
  if (Number.isNaN(parsed.valueOf()) || !/[zZ]|[+-]\d\d:\d\d$/.test(result))
    invalid(label);
  return result;
}
function schema(row: Record<string, unknown>, label: string): void {
  if (row.schema_version !== SCHEMA) invalid(`${label} schema version`);
}
function currency(value: unknown, label: string): "CAD" {
  if (value !== "CAD") invalid(`${label} currency`);
  return "CAD";
}
function timeZone(value: unknown, label: string): string {
  const result = text(value, label, 100);
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone: result }).format(new Date(0));
  } catch {
    invalid(label);
  }
  return result;
}
function array(value: unknown, label: string, maximum = 10_000): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) invalid(label);
  return value;
}
function organization(
  row: Record<string, unknown>,
  expected: string,
  label: string,
): string {
  const actual = id(row.organization_id, `${label} organization id`);
  if (actual !== expected)
    throw new BillingApiError(
      `The ${label} crossed the authenticated organization boundary.`,
      403,
    );
  return actual;
}

function parseBillingProvenance(
  row: Record<string, unknown>,
  label: string,
): BillingProvenance {
  const billingMode = enumValue(
    row.billing_mode,
    ["shadow", "sandbox", "manual"] as const,
    `${label} billing mode`,
  );
  const sandbox = boolean(row.sandbox, `${label} sandbox boundary`);
  const provenanceLabel = enumValue(
    row.provenance_label,
    [BILLING_SYNTHETIC_PROVENANCE, BILLING_MANUAL_PROVENANCE] as const,
    `${label} provenance label`,
  );
  const manual = billingMode === "manual";
  if (
    sandbox === manual ||
    provenanceLabel !==
      (manual ? BILLING_MANUAL_PROVENANCE : BILLING_SYNTHETIC_PROVENANCE)
  )
    invalid(`${label} mode and provenance consistency proof`);
  return {
    billing_mode: billingMode,
    sandbox,
    provenance_label: provenanceLabel,
  };
}

export function parseBillingCapability(
  value: unknown,
  organizationId: string,
): BillingCapability {
  const row = object(value, "billing capability");
  schema(row, "billing capability");
  const methods = array(
    row.off_platform_payment_methods,
    "billing payment methods",
    10,
  ).map((item) =>
    enumValue(
      item,
      ["cash", "cheque", "e_transfer", "other"] as const,
      "billing payment method",
    ),
  );
  const runtimeAvailable = boolean(
    row.runtime_available,
    "billing runtime flag",
  );
  const billingMode = enumValue(
    row.billing_mode,
    ["disabled", "shadow", "sandbox", "manual"] as const,
    "billing mode",
  );
  const sandbox = boolean(row.sandbox, "billing capability sandbox boundary");
  const provenanceLabel = enumValue(
    row.provenance_label,
    [BILLING_SYNTHETIC_PROVENANCE, BILLING_MANUAL_PROVENANCE] as const,
    "billing capability provenance label",
  );
  const manualActivationRequired = boolean(
    row.manual_activation_required,
    "billing manual-activation-required flag",
  );
  const manualActivated = boolean(
    row.manual_activated,
    "billing manual-activated flag",
  );
  const writesAvailable = boolean(
    row.writes_available,
    "billing write-readiness flag",
  );
  const manual = billingMode === "manual";
  if (
    sandbox === manual ||
    provenanceLabel !==
      (manual ? BILLING_MANUAL_PROVENANCE : BILLING_SYNTHETIC_PROVENANCE) ||
    (manual
      ? manualActivationRequired === manualActivated
      : manualActivationRequired || manualActivated) ||
    (writesAvailable &&
      (!runtimeAvailable ||
        (billingMode !== "sandbox" &&
          !(billingMode === "manual" && manualActivated))))
  )
    invalid("billing write-readiness consistency proof");
  return {
    schema_version: SCHEMA,
    organization_id: organization(row, organizationId, "billing capability"),
    sandbox,
    provenance_label: provenanceLabel,
    runtime_available: runtimeAvailable,
    billing_mode: billingMode,
    manual_activation_required: manualActivationRequired,
    manual_activated: manualActivated,
    writes_available: writesAvailable,
    currency: currency(row.currency, "billing capability"),
    organization_timezone: timeZone(
      row.organization_timezone,
      "billing organization timezone",
    ),
    organization_local_date: date(
      row.organization_local_date,
      "billing organization date",
    ),
    server_time: timestamp(row.server_time, "billing server time"),
    processor_enabled:
      row.processor_enabled === false
        ? false
        : invalid("billing processor boundary"),
    money_movement_enabled:
      row.money_movement_enabled === false
        ? false
        : invalid("billing money-movement boundary"),
    automatic_issue_enabled:
      row.automatic_issue_enabled === false
        ? false
        : invalid("billing automatic-issue boundary"),
    tax_advice_enabled:
      row.tax_advice_enabled === false
        ? false
        : invalid("billing tax-advice boundary"),
    off_platform_payment_methods: methods,
    reason_code: optionalText(
      row.reason_code,
      "billing capability reason code",
      200,
    ),
  };
}

export function parseBillingManualActivation(
  value: unknown,
  organizationId: string,
): BillingManualActivation {
  const row = object(value, "manual billing activation");
  if (row.schema_version !== "0036")
    invalid("manual billing activation schema version");
  const activated = boolean(row.activated, "manual billing activation flag");
  const policy =
    row.activation_policy_version == null
      ? null
      : enumValue(
          row.activation_policy_version,
          [BILLING_MANUAL_ACTIVATION_POLICY] as const,
          "manual billing activation policy",
        );
  const actor =
    row.activated_by_user_id == null
      ? null
      : id(row.activated_by_user_id, "manual billing activation actor");
  const activatedAt =
    row.activated_at == null
      ? null
      : timestamp(row.activated_at, "manual billing activation time");
  if (
    (activated && (!policy || !actor || !activatedAt)) ||
    (!activated && (policy !== null || actor !== null || activatedAt !== null))
  )
    invalid("manual billing activation lifecycle proof");
  return {
    schema_version: "0036",
    organization_id: organization(
      row,
      organizationId,
      "manual billing activation",
    ),
    billing_mode:
      row.billing_mode === "manual"
        ? "manual"
        : invalid("manual billing activation mode"),
    server_attested: boolean(
      row.server_attested,
      "manual billing server attestation",
    ),
    organization_allowlisted: boolean(
      row.organization_allowlisted,
      "manual billing organization allowlist",
    ),
    activated,
    activation_policy_version: policy,
    activated_by_user_id: actor,
    activated_at: activatedAt,
    immutable:
      row.immutable === true
        ? true
        : invalid("manual billing immutable boundary"),
    processor_enabled:
      row.processor_enabled === false
        ? false
        : invalid("manual billing processor boundary"),
    money_movement_enabled:
      row.money_movement_enabled === false
        ? false
        : invalid("manual billing money-movement boundary"),
    automatic_issue_enabled:
      row.automatic_issue_enabled === false
        ? false
        : invalid("manual billing automatic-issue boundary"),
    delivery_enabled:
      row.delivery_enabled === false
        ? false
        : invalid("manual billing delivery boundary"),
    tax_advice_enabled:
      row.tax_advice_enabled === false
        ? false
        : invalid("manual billing tax-advice boundary"),
  };
}

export function parseBillingOverview(
  value: unknown,
  organizationId: string,
): BillingOverview {
  const row = object(value, "billing overview");
  schema(row, "billing overview");
  return {
    schema_version: SCHEMA,
    organization_id: organization(row, organizationId, "billing overview"),
    currency: currency(row.currency, "billing overview"),
    as_of: timestamp(row.as_of, "billing overview time"),
    account_count: integer(row.account_count, "account count"),
    open_account_count: integer(row.open_account_count, "open account count"),
    issued_invoice_count: integer(
      row.issued_invoice_count,
      "issued invoice count",
    ),
    outstanding_minor: minor(row.outstanding_minor, "outstanding amount"),
    settled_payments_minor: minor(
      row.settled_payments_minor,
      "settled payments",
    ),
    unapplied_payments_minor: minor(
      row.unapplied_payments_minor,
      "unapplied payments",
    ),
    credits_minor: minor(row.credits_minor, "credits"),
  };
}

export function parseBillingAccount(
  value: unknown,
  organizationId: string,
): BillingAccountSummary {
  const row = object(value, "billing account");
  return {
    organization_id: organization(row, organizationId, "billing account"),
    id: id(row.id, "billing account id"),
    family_id: id(row.family_id, "billing account family id"),
    payer_guardian_id: id(
      row.payer_guardian_id,
      "billing account payer guardian id",
    ),
    latest_payer_version_id: id(
      row.latest_payer_version_id,
      "billing account latest payer version id",
    ),
    latest_payer_version_number: integer(
      row.latest_payer_version_number,
      "billing account latest payer version number",
      1,
    ),
    family_name: text(row.family_name, "billing account family name", 300),
    account_number: text(row.account_number, "billing account number", 100),
    status: enumValue(row.status, ["open"] as const, "billing account status"),
    currency: currency(row.currency, "billing account"),
    opened_at: timestamp(row.opened_at, "billing account opening time"),
    invoiced_minor: minor(row.invoiced_minor, "account invoiced amount"),
    allocated_minor: minor(row.allocated_minor, "account allocated amount"),
    credits_minor: minor(row.credits_minor, "account credits"),
    outstanding_minor: minor(
      row.outstanding_minor,
      "account outstanding amount",
    ),
    unapplied_minor: minor(row.unapplied_minor, "account unapplied amount"),
  };
}

export function parseBillingAccountPayerVersion(
  value: unknown,
  organizationId: string,
): BillingAccountPayerVersion {
  const row = object(value, "billing account payer version");
  return {
    organization_id: organization(
      row,
      organizationId,
      "billing account payer version",
    ),
    id: id(row.id, "billing account payer version id"),
    billing_account_id: id(
      row.billing_account_id,
      "payer version account id",
    ),
    family_id: id(row.family_id, "payer version family id"),
    payer_guardian_id: id(
      row.payer_guardian_id,
      "payer version guardian id",
    ),
    version_number: integer(
      row.version_number,
      "payer version number",
      1,
    ),
    assigned_by_user_id: id(
      row.assigned_by_user_id,
      "payer version assigning actor id",
    ),
    assigned_at: timestamp(row.assigned_at, "payer version assignment time"),
  };
}

function parseInvoiceLine(
  value: unknown,
  organizationId: string,
): BillingInvoiceLine {
  const row = object(value, "invoice line");
  const quantity = integer(row.quantity, "invoice quantity", 1, 1);
  const line: BillingInvoiceLine = {
    organization_id: organization(row, organizationId, "invoice line"),
    id: id(row.id, "invoice line id"),
    agreement_version_id: id(
      row.agreement_version_id,
      "invoice agreement version id",
    ),
    child_id: id(row.child_id, "invoice child id"),
    line_number: integer(row.line_number, "invoice line number", 1),
    description: text(row.description, "invoice line description", 500),
    child_name: text(row.child_name, "invoice child name", 300),
    rate_plan_name: text(row.rate_plan_name, "invoice rate plan name", 300),
    billing_unit: enumValue(
      row.billing_unit,
      [
        "weekly_period",
        "biweekly_period",
        "monthly_period",
        "service_event",
      ] as const,
      "invoice billing unit",
    ),
    service_period_start: date(
      row.service_period_start,
      "invoice line period start",
    ),
    service_period_end: date(row.service_period_end, "invoice line period end"),
    quantity,
    gross_unit_amount_minor: minor(
      row.gross_unit_amount_minor,
      "gross unit amount",
    ),
    funding_unit_amount_minor: minor(
      row.funding_unit_amount_minor,
      "funding unit amount",
    ),
    unit_amount_minor: minor(row.unit_amount_minor, "family unit amount"),
    tax_rate_basis_points: integer(
      row.tax_rate_basis_points,
      "tax rate basis points",
      0,
      10_000,
    ),
    gross_subtotal_minor: minor(row.gross_subtotal_minor, "gross subtotal"),
    funding_minor: minor(row.funding_minor, "funding amount"),
    subtotal_minor: minor(row.subtotal_minor, "family subtotal"),
    tax_minor: minor(row.tax_minor, "tax amount"),
    total_minor: minor(row.total_minor, "line total"),
  };
  if (
    checkedAdd(
      "invoice gross unit amount",
      line.unit_amount_minor,
      line.funding_unit_amount_minor,
    ) !== line.gross_unit_amount_minor ||
    checkedMultiply(
      "invoice gross subtotal",
      line.gross_unit_amount_minor,
      line.quantity,
    ) !== line.gross_subtotal_minor ||
    checkedMultiply(
      "invoice funding subtotal",
      line.funding_unit_amount_minor,
      line.quantity,
    ) !== line.funding_minor ||
    checkedMultiply(
      "invoice family subtotal",
      line.unit_amount_minor,
      line.quantity,
    ) !== line.subtotal_minor ||
    Number(
      (BigInt(line.subtotal_minor) * BigInt(line.tax_rate_basis_points) +
        5_000n) /
        10_000n,
    ) !== line.tax_minor ||
    checkedAdd("invoice line total", line.subtotal_minor, line.tax_minor) !==
      line.total_minor
  )
    invalid("invoice line amount reconciliation");
  return line;
}

export function parseBillingInvoice(
  value: unknown,
  organizationId: string,
): BillingInvoice {
  const row = object(value, "billing invoice");
  const provenance = parseBillingProvenance(row, "billing invoice");
  const documentLabel = enumValue(
    row.document_label,
    [BILLING_SYNTHETIC_PROVENANCE, BILLING_MANUAL_PROVENANCE] as const,
    "billing invoice document label",
  );
  if (documentLabel !== provenance.provenance_label)
    invalid("billing invoice document provenance proof");
  const total = minor(row.total_minor, "invoice total", true);
  const allocated = minor(row.allocated_minor, "invoice allocated");
  const credits = minor(row.credits_minor, "invoice credits");
  const outstanding = minor(row.outstanding_minor, "invoice outstanding");
  const lines = array(row.lines, "invoice lines", 500).map((item) =>
    parseInvoiceLine(item, organizationId),
  );
  const grossSubtotal = minor(
    row.gross_subtotal_minor,
    "invoice gross subtotal",
  );
  const funding = minor(row.funding_minor, "invoice funding");
  const subtotal = minor(row.subtotal_minor, "invoice subtotal");
  const tax = minor(row.tax_minor, "invoice tax");
  const sum = (label: string, values: number[]) =>
    values.reduce((current, value) => checkedAdd(label, current, value), 0);
  if (
    checkedAdd("invoice settlement", allocated, credits, outstanding) !==
      total ||
    checkedAdd("invoice gross amount", funding, subtotal) !== grossSubtotal ||
    checkedAdd("invoice total", subtotal, tax) !== total ||
    sum(
      "invoice gross line sum",
      lines.map((line) => line.gross_subtotal_minor),
    ) !== grossSubtotal ||
    sum(
      "invoice funding line sum",
      lines.map((line) => line.funding_minor),
    ) !== funding ||
    sum(
      "invoice subtotal line sum",
      lines.map((line) => line.subtotal_minor),
    ) !== subtotal ||
    sum(
      "invoice tax line sum",
      lines.map((line) => line.tax_minor),
    ) !== tax ||
    sum(
      "invoice total line sum",
      lines.map((line) => line.total_minor),
    ) !== total ||
    new Set(lines.map((line) => line.id)).size !== lines.length ||
    new Set(lines.map((line) => line.agreement_version_id)).size !==
      lines.length ||
    lines.some((line, index) => line.line_number !== index + 1)
  )
    invalid("invoice amount reconciliation");
  return {
    ...provenance,
    organization_id: organization(row, organizationId, "billing invoice"),
    document_label: documentLabel,
    id: id(row.id, "invoice id"),
    billing_account_id: id(row.billing_account_id, "invoice account id"),
    family_id: id(row.family_id, "invoice family id"),
    billing_account_payer_version_id: id(
      row.billing_account_payer_version_id,
      "invoice payer version id",
    ),
    payer_guardian_id: id(
      row.payer_guardian_id,
      "invoice payer guardian id",
    ),
    invoice_number: text(row.invoice_number, "invoice number", 100),
    lifecycle_status: enumValue(
      row.lifecycle_status,
      [
        "open",
        "partially_settled",
        "settled_paid",
        "settled_credited",
        "settled_mixed",
      ] as const,
      "invoice status",
    ),
    currency: currency(row.currency, "invoice"),
    issue_date: date(row.issue_date, "invoice issue date"),
    due_date: date(row.due_date, "invoice due date"),
    service_period_start: date(
      row.service_period_start,
      "invoice period start",
    ),
    service_period_end: date(row.service_period_end, "invoice period end"),
    family_name: text(row.family_name, "invoice family name", 300),
    payer_name: text(row.payer_name, "invoice payer name", 300),
    payer_email: optionalText(row.payer_email, "invoice payer email", 320),
    payer_address: optionalText(
      row.payer_address,
      "invoice payer address",
      500,
    ),
    gross_subtotal_minor: grossSubtotal,
    funding_minor: funding,
    subtotal_minor: subtotal,
    tax_minor: tax,
    total_minor: total,
    allocated_minor: allocated,
    credits_minor: credits,
    outstanding_minor: outstanding,
    issued_at: timestamp(row.issued_at, "invoice issue time"),
    lines,
  };
}

export function parseBillingInvoiceDocumentPreview(
  value: unknown,
  organizationId: string,
  expectedInvoiceId?: string,
): BillingInvoiceDocumentPreview {
  const row = object(value, "billing invoice document preview");
  schema(row, "billing invoice document preview");
  const previewOrganizationId = organization(
    row,
    organizationId,
    "billing invoice document preview",
  );
  const invoiceId = id(row.invoice_id, "document preview invoice id");
  if (expectedInvoiceId && invoiceId !== expectedInvoiceId)
    throw new BillingApiError(
      "The generated invoice preview did not match the requested invoice.",
      409,
    );
  const organizationRow = object(
    row.organization,
    "document preview organization",
  );
  const organizationBlockId = id(
    organizationRow.id,
    "document preview organization id",
  );
  if (organizationBlockId !== previewOrganizationId)
    invalid("document preview organization identity proof");

  const invoiceRow = object(row.invoice, "document preview invoice");
  const documentInvoiceOrganizationId = organization(
    invoiceRow,
    organizationId,
    "document preview invoice",
  );
  const documentInvoiceId = id(invoiceRow.id, "document invoice id");
  if (documentInvoiceId !== invoiceId)
    invalid("document preview invoice identity proof");
  const lines = array(invoiceRow.lines, "document invoice lines", 500).map(
    (item) => parseInvoiceLine(item, organizationId),
  );
  const grossSubtotal = minor(
    invoiceRow.gross_subtotal_minor,
    "document invoice gross subtotal",
  );
  const funding = minor(
    invoiceRow.funding_minor,
    "document invoice funding",
  );
  const subtotal = minor(
    invoiceRow.subtotal_minor,
    "document invoice subtotal",
  );
  const tax = minor(invoiceRow.tax_minor, "document invoice tax");
  const total = minor(invoiceRow.total_minor, "document invoice total", true);
  const sum = (label: string, values: number[]) =>
    values.reduce((current, amount) => checkedAdd(label, current, amount), 0);
  if (
    checkedAdd("document invoice gross amount", funding, subtotal) !==
      grossSubtotal ||
    checkedAdd("document invoice total", subtotal, tax) !== total ||
    sum(
      "document invoice gross line sum",
      lines.map((line) => line.gross_subtotal_minor),
    ) !== grossSubtotal ||
    sum(
      "document invoice funding line sum",
      lines.map((line) => line.funding_minor),
    ) !== funding ||
    sum(
      "document invoice subtotal line sum",
      lines.map((line) => line.subtotal_minor),
    ) !== subtotal ||
    sum(
      "document invoice tax line sum",
      lines.map((line) => line.tax_minor),
    ) !== tax ||
    sum(
      "document invoice total line sum",
      lines.map((line) => line.total_minor),
    ) !== total ||
    new Set(lines.map((line) => line.id)).size !== lines.length ||
    new Set(lines.map((line) => line.agreement_version_id)).size !==
      lines.length ||
    lines.some((line, index) => line.line_number !== index + 1)
  )
    invalid("document invoice amount reconciliation");

  const payerRow = object(
    row.payer_snapshot,
    "document invoice payer snapshot",
  );
  const payerVersionId = id(
    payerRow.payer_version_id,
    "document payer version id",
  );
  const guardianId = id(payerRow.guardian_id, "document payer guardian id");
  const invoicePayerVersionId = id(
    invoiceRow.billing_account_payer_version_id,
    "document invoice payer version id",
  );
  const invoiceGuardianId = id(
    invoiceRow.payer_guardian_id,
    "document invoice payer guardian id",
  );
  if (
    payerVersionId !== invoicePayerVersionId ||
    guardianId !== invoiceGuardianId
  )
    invalid("document invoice immutable payer proof");

  const allocations = array(
    row.allocations,
    "document invoice allocations",
    10_000,
  ).map((item) => {
    const allocation = object(item, "document invoice allocation");
    return {
      id: id(allocation.id, "document allocation id"),
      payment_id: id(allocation.payment_id, "document allocation payment id"),
      amount_minor: minor(
        allocation.amount_minor,
        "document allocation amount",
        true,
      ),
      allocated_at: timestamp(
        allocation.allocated_at,
        "document allocation time",
      ),
    };
  });
  const credits = array(
    row.credits,
    "document invoice credits",
    10_000,
  ).map((item) => {
    const credit = object(item, "document invoice credit");
    return {
      id: id(credit.id, "document credit id"),
      amount_minor: minor(
        credit.amount_minor,
        "document credit amount",
        true,
      ),
      reason_code: text(
        credit.reason_code,
        "document credit reason code",
        100,
      ),
      note: optionalText(credit.note, "document credit note", 500),
      issued_at: timestamp(credit.issued_at, "document credit issue time"),
    };
  });
  if (
    new Set(allocations.map((item) => item.id)).size !== allocations.length ||
    new Set(credits.map((item) => item.id)).size !== credits.length
  )
    invalid("document settlement effect identity proof");

  const settlementRow = object(
    row.settlement,
    "document invoice settlement",
  );
  const settlementTotal = minor(
    settlementRow.total_minor,
    "document settlement total",
    true,
  );
  const settlementAllocated = minor(
    settlementRow.allocated_minor,
    "document settlement allocated",
  );
  const settlementCredits = minor(
    settlementRow.credits_minor,
    "document settlement credits",
  );
  const settlementOutstanding = minor(
    settlementRow.outstanding_minor,
    "document settlement outstanding",
  );
  if (
    settlementTotal !== total ||
    sum(
      "document allocation sum",
      allocations.map((item) => item.amount_minor),
    ) !== settlementAllocated ||
    sum(
      "document credit sum",
      credits.map((item) => item.amount_minor),
    ) !== settlementCredits ||
    checkedAdd(
      "document settlement",
      settlementAllocated,
      settlementCredits,
      settlementOutstanding,
    ) !== settlementTotal
  )
    invalid("document settlement reconciliation");

  const issueDate = date(invoiceRow.issue_date, "document invoice issue date");
  const dueDate = date(invoiceRow.due_date, "document invoice due date");
  const servicePeriodStart = date(
    invoiceRow.service_period_start,
    "document invoice period start",
  );
  const servicePeriodEnd = date(
    invoiceRow.service_period_end,
    "document invoice period end",
  );
  if (
    dueDate < issueDate ||
    servicePeriodEnd < servicePeriodStart ||
    lines.some(
      (line) =>
        line.service_period_start < servicePeriodStart ||
        line.service_period_end > servicePeriodEnd,
    )
  )
    invalid("document invoice date range proof");
  const provenance = parseBillingProvenance(
    row,
    "billing invoice document preview",
  );

  return {
    ...provenance,
    schema_version: SCHEMA,
    document_version:
      row.document_version === "billing-invoice-preview-v1"
        ? "billing-invoice-preview-v1"
        : invalid("billing invoice document version"),
    organization_id: previewOrganizationId,
    invoice_id: invoiceId,
    read_only:
      row.read_only === true
        ? true
        : invalid("billing invoice document read-only boundary"),
    download_enabled:
      row.download_enabled === false
        ? false
        : invalid("billing invoice document download boundary"),
    delivery_enabled:
      row.delivery_enabled === false
        ? false
        : invalid("billing invoice document delivery boundary"),
    generated_at: timestamp(
      row.generated_at,
      "billing invoice document generation time",
    ),
    data_through_at: timestamp(
      row.data_through_at,
      "billing invoice document data-through time",
    ),
    data_through_realtime_sequence: integer(
      row.data_through_realtime_sequence,
      "billing invoice document realtime sequence",
    ),
    organization: {
      id: organizationBlockId,
      display_name: text(
        organizationRow.display_name,
        "document organization display name",
        255,
      ),
      legal_name: optionalText(
        organizationRow.legal_name,
        "document organization legal name",
        255,
      ),
      email: optionalText(
        organizationRow.email,
        "document organization email",
        320,
      ),
      phone: optionalText(
        organizationRow.phone,
        "document organization phone",
        50,
      ),
    },
    invoice: {
      organization_id: documentInvoiceOrganizationId,
      id: documentInvoiceId,
      billing_account_id: id(
        invoiceRow.billing_account_id,
        "document invoice account id",
      ),
      family_id: id(invoiceRow.family_id, "document invoice family id"),
      billing_account_payer_version_id: invoicePayerVersionId,
      payer_guardian_id: invoiceGuardianId,
      invoice_number: text(
        invoiceRow.invoice_number,
        "document invoice number",
        100,
      ),
      status: enumValue(
        invoiceRow.status,
        ["issued"] as const,
        "document invoice status",
      ),
      currency: currency(invoiceRow.currency, "document invoice"),
      issue_date: issueDate,
      due_date: dueDate,
      service_period_start: servicePeriodStart,
      service_period_end: servicePeriodEnd,
      family_name: text(
        invoiceRow.family_name,
        "document invoice family name",
        300,
      ),
      gross_subtotal_minor: grossSubtotal,
      funding_minor: funding,
      subtotal_minor: subtotal,
      tax_minor: tax,
      total_minor: total,
      issued_at: timestamp(
        invoiceRow.issued_at,
        "document invoice issue time",
      ),
      lines,
    },
    payer_snapshot: {
      payer_version_id: payerVersionId,
      guardian_id: guardianId,
      name: text(payerRow.name, "document payer name", 300),
      email: optionalText(payerRow.email, "document payer email", 320),
      address: optionalText(payerRow.address, "document payer address", 500),
    },
    allocations,
    credits,
    settlement: {
      currency: currency(
        settlementRow.currency,
        "document invoice settlement",
      ),
      total_minor: settlementTotal,
      allocated_minor: settlementAllocated,
      credits_minor: settlementCredits,
      outstanding_minor: settlementOutstanding,
    },
    canonical_sha256: sha256(
      row.canonical_sha256,
      "billing invoice document canonical digest",
    ),
  };
}

function canonicalJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalJsonValue);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, canonicalJsonValue(item)]),
  );
}

export async function billingInvoiceDocumentCanonicalSha256(
  preview: BillingInvoiceDocumentPreview,
): Promise<string> {
  const { generated_at: _generatedAt, canonical_sha256: _digest, ...payload } =
    preview;
  if (!globalThis.crypto?.subtle)
    throw new BillingApiError(
      "This browser cannot verify the generated invoice preview digest. No unverified document was opened.",
    );
  const canonicalJson = JSON.stringify(canonicalJsonValue(payload));
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalJson),
  );
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyBillingInvoiceDocumentDigest(
  preview: BillingInvoiceDocumentPreview,
): Promise<void> {
  const computed = await billingInvoiceDocumentCanonicalSha256(preview);
  if (computed !== preview.canonical_sha256)
    throw new BillingApiError(
      "The generated invoice preview failed its canonical integrity check. No document was opened.",
      409,
    );
}

export function parseBillingPayment(
  value: unknown,
  organizationId: string,
): BillingPayment {
  const row = object(value, "billing payment");
  const provenance = parseBillingProvenance(row, "billing payment");
  const amount = minor(row.amount_minor, "payment amount", true);
  const allocated = minor(row.allocated_minor, "payment allocated");
  const unapplied = minor(row.unapplied_minor, "payment unapplied");
  if (allocated + unapplied !== amount)
    invalid("payment amount reconciliation");
  return {
    ...provenance,
    organization_id: organization(row, organizationId, "billing payment"),
    id: id(row.id, "payment id"),
    billing_account_id: id(row.billing_account_id, "payment account id"),
    family_id: id(row.family_id, "payment family id"),
    payer_guardian_id: id(row.payer_guardian_id, "payment payer guardian id"),
    payer_name: text(row.payer_name, "payment payer name", 300),
    payer_email: optionalText(row.payer_email, "payment payer email", 320),
    lifecycle_status: enumValue(
      row.lifecycle_status,
      ["settled", "partially_allocated", "fully_allocated"] as const,
      "payment status",
    ),
    method: enumValue(
      row.method,
      ["cash", "cheque", "e_transfer", "other"] as const,
      "payment method",
    ),
    currency: currency(row.currency, "payment"),
    amount_minor: amount,
    allocated_minor: allocated,
    unapplied_minor: unapplied,
    external_reference: text(
      row.external_reference,
      "payment external reference",
      120,
    ),
    memo: optionalText(row.memo, "payment memo", 500),
    operator_confirmation_note: optionalText(
      row.operator_confirmation_note,
      "payment operator confirmation note",
      500,
    ),
    received_at: timestamp(row.received_at, "payment receipt time"),
    recorded_at: timestamp(row.recorded_at, "payment record time"),
  };
}

export function parseBillingAllocation(
  value: unknown,
  organizationId: string,
): BillingAllocation {
  const row = object(value, "billing allocation");
  return {
    organization_id: organization(row, organizationId, "billing allocation"),
    id: id(row.id, "allocation id"),
    billing_account_id: id(
      row.billing_account_id,
      "allocation account id",
    ),
    payment_id: id(row.payment_id, "allocation payment id"),
    invoice_id: id(row.invoice_id, "allocation invoice id"),
    amount_minor: minor(row.amount_minor, "allocation amount", true),
    allocated_by_user_id: id(
      row.allocated_by_user_id,
      "allocation actor id",
    ),
    allocated_at: timestamp(row.allocated_at, "allocation time"),
    client_operation_id: id(
      row.client_operation_id,
      "allocation operation id",
    ),
    request_hash: sha256(row.request_hash, "allocation request hash"),
  };
}

export function parseBillingCredit(
  value: unknown,
  organizationId: string,
): BillingCredit {
  const row = object(value, "billing credit");
  return {
    organization_id: organization(row, organizationId, "billing credit"),
    id: id(row.id, "credit id"),
    billing_account_id: id(row.billing_account_id, "credit account id"),
    invoice_id: id(row.invoice_id, "credit invoice id"),
    status: enumValue(row.status, ["issued"] as const, "credit status"),
    currency: currency(row.currency, "credit"),
    amount_minor: minor(row.amount_minor, "credit amount", true),
    reason_code: text(row.reason_code, "credit reason code", 80),
    note: optionalText(row.note, "credit note", 500),
    issued_by_user_id: id(row.issued_by_user_id, "credit actor id"),
    issued_at: timestamp(row.issued_at, "credit issue time"),
    client_operation_id: id(row.client_operation_id, "credit operation id"),
    request_hash: sha256(row.request_hash, "credit request hash"),
  };
}

function parseRateVersion(
  value: unknown,
  expectedPlanId: string,
  organizationId: string,
): BillingRatePlanVersion {
  const row = object(value, "rate plan version");
  const planId = id(row.rate_plan_id, "rate plan version plan id");
  if (planId !== expectedPlanId) invalid("rate plan version ownership");
  return {
    organization_id: organization(row, organizationId, "rate plan version"),
    id: id(row.id, "rate plan version id"),
    rate_plan_id: planId,
    version_number: integer(row.version_number, "rate version number", 1),
    status: enumValue(
      row.status,
      ["published"] as const,
      "rate version status",
    ),
    billing_unit: enumValue(
      row.billing_unit,
      [
        "weekly_period",
        "biweekly_period",
        "monthly_period",
        "service_event",
      ] as const,
      "rate billing unit",
    ),
    unit_amount_minor: minor(row.unit_amount_minor, "rate unit amount"),
    tax_rate_basis_points: integer(
      row.tax_rate_basis_points,
      "rate tax basis points",
      0,
      10_000,
    ),
    currency: currency(row.currency, "rate plan"),
    effective_from: date(row.effective_from, "rate effective date"),
    effective_until: optionalDate(row.effective_until, "rate end date"),
    description: optionalText(row.description, "rate description", 500),
    published_at: timestamp(row.published_at, "rate publication time"),
  };
}

export function parseBillingRatePlan(
  value: unknown,
  organizationId: string,
): BillingRatePlan {
  const row = object(value, "billing rate plan");
  const planId = id(row.id, "rate plan id");
  const latest = parseRateVersion(row.latest_version, planId, organizationId);
  const versions = array(row.versions ?? [], "rate plan versions", 1000).map(
    (item) => parseRateVersion(item, planId, organizationId),
  );
  const latestInChain = versions.find((version) => version.id === latest.id);
  if (
    versions.length === 0 ||
    new Set(versions.map((version) => version.id)).size !== versions.length ||
    new Set(versions.map((version) => version.version_number)).size !==
      versions.length ||
    !latestInChain ||
    JSON.stringify(latestInChain) !== JSON.stringify(latest) ||
    latest.version_number !==
      Math.max(...versions.map((version) => version.version_number))
  )
    invalid("rate plan version chain proof");
  const program = row.program_type;
  return {
    organization_id: organization(row, organizationId, "billing rate plan"),
    id: planId,
    code: text(row.code, "rate plan code", 40),
    name: text(row.name, "rate plan name", 160),
    program_type: enumValue(
      program,
      ["daycare", "out_of_school_care"] as const,
      "rate program type",
    ),
    charge_kind: enumValue(
      row.charge_kind,
      ["core_care"] as const,
      "rate charge kind",
    ),
    age_group: optionalText(row.age_group, "rate age group", 100),
    facility_id:
      row.facility_id == null ? null : id(row.facility_id, "rate facility id"),
    program_id:
      row.program_id == null ? null : id(row.program_id, "rate program id"),
    created_at: timestamp(row.created_at, "rate plan creation time"),
    latest_version: latest,
    versions,
  };
}

function parseAgreementVersion(
  value: unknown,
  expectedAgreementId: string,
  organizationId: string,
): BillingAgreementVersion {
  const row = object(value, "billing agreement version");
  const agreementId = id(row.agreement_id, "agreement version agreement id");
  if (agreementId !== expectedAgreementId)
    invalid("agreement version ownership");
  return {
    organization_id: organization(
      row,
      organizationId,
      "billing agreement version",
    ),
    id: id(row.id, "agreement version id"),
    agreement_id: agreementId,
    rate_plan_version_id: id(
      row.rate_plan_version_id,
      "agreement rate version id",
    ),
    version_number: integer(row.version_number, "agreement version number", 1),
    billing_frequency: enumValue(
      row.billing_frequency,
      ["weekly", "biweekly", "monthly", "per_service"] as const,
      "billing frequency",
    ),
    family_amount_minor_per_unit: minor(
      row.family_amount_minor_per_unit,
      "agreement family amount",
    ),
    funding_amount_minor_per_unit: minor(
      row.funding_amount_minor_per_unit,
      "agreement funding amount",
    ),
    effective_from: date(row.effective_from, "agreement effective date"),
    effective_until: optionalDate(row.effective_until, "agreement end date"),
    review_status: enumValue(
      row.review_status,
      ["reviewed"] as const,
      "agreement review status",
    ),
    reviewed_at: timestamp(row.reviewed_at, "agreement review time"),
  };
}

export function parseBillingAgreement(
  value: unknown,
  organizationId: string,
): BillingAgreement {
  const row = object(value, "billing agreement");
  const agreementId = id(row.id, "agreement id");
  const latest = parseAgreementVersion(
    row.latest_version,
    agreementId,
    organizationId,
  );
  const versions = array(row.versions ?? [], "agreement versions", 1000).map(
    (item) => parseAgreementVersion(item, agreementId, organizationId),
  );
  const latestInChain = versions.find((version) => version.id === latest.id);
  if (
    versions.length === 0 ||
    new Set(versions.map((version) => version.id)).size !== versions.length ||
    new Set(versions.map((version) => version.version_number)).size !==
      versions.length ||
    !latestInChain ||
    JSON.stringify(latestInChain) !== JSON.stringify(latest) ||
    latest.version_number !==
      Math.max(...versions.map((version) => version.version_number))
  )
    invalid("agreement version chain proof");
  return {
    organization_id: organization(row, organizationId, "billing agreement"),
    id: agreementId,
    billing_account_id: id(row.billing_account_id, "agreement account id"),
    family_id: id(row.family_id, "agreement family id"),
    child_id: id(row.child_id, "agreement child id"),
    child_name: text(row.child_name, "agreement child name", 300),
    enrollment_id:
      row.enrollment_id == null
        ? null
        : id(row.enrollment_id, "agreement enrollment id"),
    facility_id:
      row.facility_id == null
        ? null
        : id(row.facility_id, "agreement facility id"),
    created_at: timestamp(row.created_at, "agreement creation time"),
    latest_version: latest,
    versions,
  };
}

function page<T extends { id: string }>(
  value: unknown,
  organizationId: string,
  label: string,
  parser: (item: unknown, organizationId: string) => T,
  withCurrency = true,
): BillingPageResult<T> {
  const row = object(value, label);
  schema(row, label);
  organization(row, organizationId, label);
  if (withCurrency) currency(row.currency, label);
  const items = array(row.items, `${label} items`).map((item) =>
    parser(item, organizationId),
  );
  if (new Set(items.map((item) => item.id)).size !== items.length)
    invalid(`${label} unique record proof`);
  const total = integer(row.total, `${label} total`);
  if (total < items.length) invalid(`${label} total`);
  return {
    schema_version: SCHEMA,
    organization_id: organizationId,
    ...(withCurrency ? { currency: "CAD" as const } : {}),
    items,
    total,
  };
}
export const parseBillingAccounts = (value: unknown, organizationId: string) =>
  page(value, organizationId, "billing accounts page", parseBillingAccount);
export const parseBillingAccountPayerVersions = (
  value: unknown,
  organizationId: string,
) =>
  page(
    value,
    organizationId,
    "billing account payer versions page",
    parseBillingAccountPayerVersion,
    false,
  );
export const parseBillingInvoices = (value: unknown, organizationId: string) =>
  page(value, organizationId, "billing invoices page", parseBillingInvoice);
export const parseBillingPayments = (value: unknown, organizationId: string) =>
  page(value, organizationId, "billing payments page", parseBillingPayment);
export const parseBillingRatePlans = (value: unknown, organizationId: string) =>
  page(value, organizationId, "billing rate plans page", parseBillingRatePlan);
export const parseBillingAgreements = (
  value: unknown,
  organizationId: string,
) =>
  page(
    value,
    organizationId,
    "billing agreements page",
    parseBillingAgreement,
    false,
  );

export const parseBillingAllocations = (
  value: unknown,
  organizationId: string,
) =>
  offsetPage(
    value,
    organizationId,
    "billing allocations page",
    parseBillingAllocation,
  );
export const parseBillingCredits = (value: unknown, organizationId: string) =>
  offsetPage(
    value,
    organizationId,
    "billing credits page",
    parseBillingCredit,
  );

function offsetPage<T extends { id: string }>(
  value: unknown,
  organizationId: string,
  label: string,
  parser: (item: unknown, organizationId: string) => T,
) {
  const row = object(value, label);
  const result = page(value, organizationId, label, parser);
  return {
    ...result,
    limit: integer(row.limit, `${label} limit`, 1, 500),
    offset: integer(row.offset, `${label} offset`),
  };
}

const WORKSPACE_COLLECTIONS: readonly BillingWorkspaceCollection[] = [
  "accounts",
  "payer_versions",
  "invoices",
  "payments",
  "rate_plans",
  "agreements",
  "allocations",
  "credits",
] as const;

function parseCollectionPage(
  value: unknown,
  label: string,
  collectionLimit: number,
) {
  const row = object(value, `${label} paging`);
  const offset = integer(row.offset, `${label} page offset`);
  const limit = integer(row.limit, `${label} page limit`, 1, 500);
  const returned = integer(row.returned, `${label} returned count`);
  const total = integer(row.total, `${label} total count`);
  const hasMore = boolean(row.has_more, `${label} has-more flag`);
  const nextOffset =
    row.next_offset == null
      ? null
      : integer(row.next_offset, `${label} next offset`);
  if (
    limit !== collectionLimit ||
    returned > limit ||
    offset > total ||
    offset + returned > total ||
    hasMore !== offset + returned < total ||
    (hasMore && (returned === 0 || nextOffset !== offset + returned)) ||
    (!hasMore && nextOffset !== null)
  )
    invalid(`${label} paging proof`);
  return {
    offset,
    limit,
    returned,
    total,
    has_more: hasMore,
    next_offset: nextOffset,
  };
}

export function parseBillingWorkspacePage(
  value: unknown,
  organizationId: string,
): BillingWorkspacePage {
  const row = object(value, "billing workspace");
  schema(row, "billing workspace");
  organization(row, organizationId, "billing workspace");
  const provenance = parseBillingProvenance(row, "billing workspace");
  const canonicalCollectionLimit = integer(
    row.canonical_collection_limit,
    "billing workspace collection limit",
    1,
    500,
  );
  const accounts = parseBillingAccounts(row.accounts, organizationId);
  const payerVersions = parseBillingAccountPayerVersions(
    row.payer_versions,
    organizationId,
  );
  const invoices = parseBillingInvoices(row.invoices, organizationId);
  const payments = parseBillingPayments(row.payments, organizationId);
  const ratePlans = parseBillingRatePlans(row.rate_plans, organizationId);
  const agreements = parseBillingAgreements(row.agreements, organizationId);
  const allocations = parseBillingAllocations(row.allocations, organizationId);
  const credits = parseBillingCredits(row.credits, organizationId);
  const collections = {
    accounts,
    payer_versions: payerVersions,
    invoices,
    payments,
    rate_plans: ratePlans,
    agreements,
    allocations,
    credits,
  };
  const pagingRow = object(row.paging, "billing workspace paging");
  const paging = {
    snapshot_token: sha256(
      pagingRow.snapshot_token,
      "billing workspace snapshot token",
    ),
    accounts: parseCollectionPage(
      pagingRow.accounts,
      "accounts",
      canonicalCollectionLimit,
    ),
    payer_versions: parseCollectionPage(
      pagingRow.payer_versions,
      "payer versions",
      canonicalCollectionLimit,
    ),
    invoices: parseCollectionPage(
      pagingRow.invoices,
      "invoices",
      canonicalCollectionLimit,
    ),
    payments: parseCollectionPage(
      pagingRow.payments,
      "payments",
      canonicalCollectionLimit,
    ),
    rate_plans: parseCollectionPage(
      pagingRow.rate_plans,
      "rate plans",
      canonicalCollectionLimit,
    ),
    agreements: parseCollectionPage(
      pagingRow.agreements,
      "agreements",
      canonicalCollectionLimit,
    ),
    allocations: parseCollectionPage(
      pagingRow.allocations,
      "allocations",
      canonicalCollectionLimit,
    ),
    credits: parseCollectionPage(
      pagingRow.credits,
      "credits",
      canonicalCollectionLimit,
    ),
  };
  for (const name of WORKSPACE_COLLECTIONS) {
    const collection = collections[name];
    const proof = paging[name];
    if (
      collection.total !== proof.total ||
      collection.items.length !== proof.returned ||
      (name === "allocations" &&
        (allocations.offset !== proof.offset ||
          allocations.limit !== proof.limit)) ||
      (name === "credits" &&
        (credits.offset !== proof.offset || credits.limit !== proof.limit))
    )
      invalid(`billing workspace ${name} page proof`);
  }
  const complete = boolean(row.complete, "billing workspace complete flag");
  const provesSingleCompletePage = WORKSPACE_COLLECTIONS.every(
    (name) => paging[name].offset === 0 && !paging[name].has_more,
  );
  if (complete !== provesSingleCompletePage)
    invalid("billing workspace page completeness proof");
  return {
    ...provenance,
    schema_version: SCHEMA,
    organization_id: organizationId,
    complete,
    canonical_collection_limit: canonicalCollectionLimit,
    generated_at: timestamp(
      row.generated_at,
      "billing workspace generation time",
    ),
    data_through_realtime_sequence: integer(
      row.data_through_realtime_sequence,
      "billing workspace realtime sequence",
    ),
    paging,
    overview: parseBillingOverview(row.overview, organizationId),
    accounts,
    payer_versions: payerVersions,
    invoices,
    payments,
    rate_plans: ratePlans,
    agreements,
    allocations,
    credits,
  };
}

function overviewProof(overview: BillingOverview): string {
  return JSON.stringify({
    organization_id: overview.organization_id,
    currency: overview.currency,
    account_count: overview.account_count,
    open_account_count: overview.open_account_count,
    issued_invoice_count: overview.issued_invoice_count,
    outstanding_minor: overview.outstanding_minor,
    settled_payments_minor: overview.settled_payments_minor,
    unapplied_payments_minor: overview.unapplied_payments_minor,
    credits_minor: overview.credits_minor,
  });
}

function collectWorkspacePages<T extends { id: string }>(
  pages: readonly BillingWorkspacePage[],
  name: BillingWorkspaceCollection,
  select: (workspace: BillingWorkspacePage) => { items: T[]; total: number },
  organizationId: string,
): BillingPageResult<T> {
  const expectedTotal = pages[0].paging[name].total;
  const items: T[] = [];
  const seen = new Set<string>();
  let expectedOffset = 0;
  for (const workspace of pages) {
    const proof = workspace.paging[name];
    const collection = select(workspace);
    if (
      proof.offset !== expectedOffset ||
      proof.total !== expectedTotal ||
      collection.total !== expectedTotal
    )
      invalid(`billing workspace ${name} page sequence`);
    for (const item of collection.items) {
      if (seen.has(item.id))
        invalid(`billing workspace ${name} duplicate or overlap proof`);
      seen.add(item.id);
      items.push(item);
    }
    expectedOffset = proof.next_offset ?? expectedTotal;
  }
  const finalProof = pages[pages.length - 1].paging[name];
  if (
    finalProof.has_more ||
    expectedOffset !== expectedTotal ||
    items.length !== expectedTotal
  )
    invalid(`billing workspace ${name} complete assembly proof`);
  return {
    schema_version: SCHEMA,
    organization_id: organizationId,
    ...(name === "agreements" || name === "payer_versions"
      ? {}
      : { currency: "CAD" as const }),
    items,
    total: expectedTotal,
  };
}

export function assembleBillingWorkspacePages(
  pages: readonly BillingWorkspacePage[],
  organizationId: string,
): BillingWorkspaceProjection {
  if (!pages.length) invalid("billing workspace page assembly");
  const first = pages[0];
  const snapshotToken = first.paging.snapshot_token;
  const sequence = first.data_through_realtime_sequence;
  const collectionLimit = first.canonical_collection_limit;
  const stableOverview = overviewProof(first.overview);
  for (const workspace of pages) {
    if (
      workspace.organization_id !== organizationId ||
      workspace.paging.snapshot_token !== snapshotToken ||
      workspace.data_through_realtime_sequence !== sequence ||
      workspace.canonical_collection_limit !== collectionLimit ||
      workspace.billing_mode !== first.billing_mode ||
      workspace.sandbox !== first.sandbox ||
      workspace.provenance_label !== first.provenance_label ||
      overviewProof(workspace.overview) !== stableOverview
    )
      invalid("billing workspace snapshot drift proof");
  }
  const accounts = collectWorkspacePages(
    pages,
    "accounts",
    (page) => page.accounts,
    organizationId,
  );
  const payerVersions = collectWorkspacePages(
    pages,
    "payer_versions",
    (page) => page.payer_versions,
    organizationId,
  );
  const invoices = collectWorkspacePages(
    pages,
    "invoices",
    (page) => page.invoices,
    organizationId,
  );
  const payments = collectWorkspacePages(
    pages,
    "payments",
    (page) => page.payments,
    organizationId,
  );
  const ratePlans = collectWorkspacePages(
    pages,
    "rate_plans",
    (page) => page.rate_plans,
    organizationId,
  );
  const agreements = collectWorkspacePages(
    pages,
    "agreements",
    (page) => page.agreements,
    organizationId,
  );
  const allocations = collectWorkspacePages(
    pages,
    "allocations",
    (page) => page.allocations,
    organizationId,
  );
  const credits = collectWorkspacePages(
    pages,
    "credits",
    (page) => page.credits,
    organizationId,
  );
  if (
    invoices.items.some(
      (item) =>
        item.billing_mode !== first.billing_mode ||
        item.sandbox !== first.sandbox ||
        item.provenance_label !== first.provenance_label ||
        item.document_label !== first.provenance_label,
    ) ||
    payments.items.some(
      (item) =>
        item.billing_mode !== first.billing_mode ||
        item.sandbox !== first.sandbox ||
        item.provenance_label !== first.provenance_label,
    )
  )
    invalid("billing workspace record provenance proof");
  const sum = <T, Key extends keyof T>(items: readonly T[], field: Key) =>
    items.reduce(
      (total, item) =>
        checkedAdd("billing workspace aggregate", total, Number(item[field])),
      0,
    );
  const accountById = new Map(
    accounts.items.map((account) => [account.id, account] as const),
  );
  if (
    new Set(accounts.items.map((account) => account.family_id)).size !==
    accounts.items.length
  )
    invalid("billing workspace account family ownership proof");
  const payerVersionById = new Map<string, BillingAccountPayerVersion>();
  const payerVersionNumbers = new Set<string>();
  const payerVersionsByAccount = new Map<
    string,
    BillingAccountPayerVersion[]
  >();
  for (const version of payerVersions.items) {
    const account = accountById.get(version.billing_account_id);
    const accountVersionKey = `${version.billing_account_id}:${version.version_number}`;
    if (
      !account ||
      account.family_id !== version.family_id ||
      payerVersionById.has(version.id) ||
      payerVersionNumbers.has(accountVersionKey)
    )
      invalid("billing workspace payer version ownership proof");
    payerVersionById.set(version.id, version);
    payerVersionNumbers.add(accountVersionKey);
    const versions = payerVersionsByAccount.get(version.billing_account_id) ?? [];
    versions.push(version);
    payerVersionsByAccount.set(version.billing_account_id, versions);
  }
  for (const account of accounts.items) {
    const versions = payerVersionsByAccount.get(account.id) ?? [];
    const orderedVersions = [...versions].sort(
      (left, right) => left.version_number - right.version_number,
    );
    const latest = payerVersionById.get(account.latest_payer_version_id);
    if (
      !versions.length ||
      orderedVersions.some(
        (version, index) => version.version_number !== index + 1,
      ) ||
      orderedVersions.some(
        (version, index) =>
          index > 0 &&
          new Date(version.assigned_at).valueOf() <
            new Date(orderedVersions[index - 1].assigned_at).valueOf(),
      )
    )
      invalid("billing workspace payer version chain proof");
    if (
      !latest ||
      latest.billing_account_id !== account.id ||
      latest.family_id !== account.family_id ||
      latest.payer_guardian_id !== account.payer_guardian_id ||
      latest.version_number !== account.latest_payer_version_number ||
      latest.version_number !==
        Math.max(...versions.map((version) => version.version_number))
    )
      invalid("billing workspace latest payer version proof");
  }
  const rateVersionOwner = new Map<string, BillingRatePlan>();
  for (const plan of ratePlans.items) {
    for (const version of plan.versions) {
      if (rateVersionOwner.has(version.id))
        invalid("billing workspace rate version identity proof");
      rateVersionOwner.set(version.id, plan);
    }
  }
  const agreementVersionOwner = new Map<string, BillingAgreement>();
  for (const agreement of agreements.items) {
    const account = accountById.get(agreement.billing_account_id);
    if (!account || account.family_id !== agreement.family_id)
      invalid("billing workspace agreement account ownership proof");
    for (const version of agreement.versions) {
      if (
        agreementVersionOwner.has(version.id) ||
        !rateVersionOwner.has(version.rate_plan_version_id)
      )
        invalid("billing workspace agreement rate ownership proof");
      agreementVersionOwner.set(version.id, agreement);
    }
  }
  const invoiceById = new Map(
    invoices.items.map((invoice) => [invoice.id, invoice] as const),
  );
  for (const invoice of invoices.items) {
    const account = accountById.get(invoice.billing_account_id);
    const payerVersion = payerVersionById.get(
      invoice.billing_account_payer_version_id,
    );
    if (
      !account ||
      account.family_id !== invoice.family_id ||
      !payerVersion ||
      payerVersion.billing_account_id !== invoice.billing_account_id ||
      payerVersion.family_id !== invoice.family_id ||
      payerVersion.payer_guardian_id !== invoice.payer_guardian_id
    )
      invalid("billing workspace invoice account ownership proof");
    for (const line of invoice.lines) {
      const agreement = agreementVersionOwner.get(line.agreement_version_id);
      if (
        !agreement ||
        agreement.billing_account_id !== invoice.billing_account_id ||
        agreement.family_id !== invoice.family_id ||
        agreement.child_id !== line.child_id
      )
        invalid("billing workspace invoice line ownership proof");
    }
  }
  const paymentById = new Map(
    payments.items.map((payment) => [payment.id, payment] as const),
  );
  for (const payment of payments.items) {
    const account = accountById.get(payment.billing_account_id);
    if (!account || account.family_id !== payment.family_id)
      invalid("billing workspace payment account ownership proof");
  }
  const operationIds = new Set<string>();
  for (const allocation of allocations.items) {
    const payment = paymentById.get(allocation.payment_id);
    const invoice = invoiceById.get(allocation.invoice_id);
    if (
      !payment ||
      !invoice ||
      !accountById.has(allocation.billing_account_id) ||
      payment.billing_account_id !== allocation.billing_account_id ||
      invoice.billing_account_id !== allocation.billing_account_id ||
      operationIds.has(allocation.client_operation_id)
    )
      invalid("billing workspace allocation ownership proof");
    operationIds.add(allocation.client_operation_id);
  }
  for (const credit of credits.items) {
    const invoice = invoiceById.get(credit.invoice_id);
    if (
      !invoice ||
      !accountById.has(credit.billing_account_id) ||
      invoice.billing_account_id !== credit.billing_account_id ||
      operationIds.has(credit.client_operation_id)
    )
      invalid("billing workspace credit ownership proof");
    operationIds.add(credit.client_operation_id);
  }
  for (const invoice of invoices.items) {
    if (
      invoice.allocated_minor !==
        sum(
          allocations.items.filter((item) => item.invoice_id === invoice.id),
          "amount_minor",
        ) ||
      invoice.credits_minor !==
        sum(
          credits.items.filter((item) => item.invoice_id === invoice.id),
          "amount_minor",
        )
    )
      invalid("billing workspace invoice effect reconciliation proof");
  }
  for (const payment of payments.items) {
    if (
      payment.allocated_minor !==
      sum(
        allocations.items.filter((item) => item.payment_id === payment.id),
        "amount_minor",
      )
    )
      invalid("billing workspace payment effect reconciliation proof");
  }
  for (const account of accounts.items) {
    const accountInvoices = invoices.items.filter(
      (invoice) => invoice.billing_account_id === account.id,
    );
    const accountPayments = payments.items.filter(
      (payment) => payment.billing_account_id === account.id,
    );
    const accountAllocations = allocations.items.filter(
      (allocation) => allocation.billing_account_id === account.id,
    );
    const accountCredits = credits.items.filter(
      (credit) => credit.billing_account_id === account.id,
    );
    if (
      account.invoiced_minor !== sum(accountInvoices, "total_minor") ||
      account.allocated_minor !== sum(accountAllocations, "amount_minor") ||
      account.allocated_minor !== sum(accountInvoices, "allocated_minor") ||
      account.allocated_minor !== sum(accountPayments, "allocated_minor") ||
      account.credits_minor !== sum(accountCredits, "amount_minor") ||
      account.credits_minor !== sum(accountInvoices, "credits_minor") ||
      account.outstanding_minor !== sum(accountInvoices, "outstanding_minor") ||
      account.unapplied_minor !== sum(accountPayments, "unapplied_minor")
    )
      invalid("billing workspace per-account reconciliation proof");
  }
  const overview = first.overview;
  if (
    overview.account_count !== accounts.items.length ||
    overview.open_account_count !==
      accounts.items.filter((account) => account.status === "open").length ||
    overview.issued_invoice_count !== invoices.items.length ||
    overview.outstanding_minor !== sum(accounts.items, "outstanding_minor") ||
    overview.outstanding_minor !== sum(invoices.items, "outstanding_minor") ||
    overview.settled_payments_minor !== sum(payments.items, "amount_minor") ||
    overview.unapplied_payments_minor !==
      sum(payments.items, "unapplied_minor") ||
    overview.credits_minor !== sum(credits.items, "amount_minor") ||
    overview.credits_minor !== sum(invoices.items, "credits_minor")
  )
    invalid("billing workspace overview reconciliation proof");
  return {
    billing_mode: first.billing_mode,
    schema_version: SCHEMA,
    organization_id: organizationId,
    sandbox: first.sandbox,
    provenance_label: first.provenance_label,
    complete: true,
    canonical_collection_limit: collectionLimit,
    generated_at: first.generated_at,
    data_through_realtime_sequence: sequence,
    snapshot_token: snapshotToken,
    overview,
    accounts,
    payer_versions: payerVersions,
    invoices,
    payments,
    rate_plans: ratePlans,
    agreements,
    allocations,
    credits,
  };
}

export function parseBillingWorkspace(
  value: unknown,
  organizationId: string,
): BillingWorkspaceProjection {
  return assembleBillingWorkspacePages(
    [parseBillingWorkspacePage(value, organizationId)],
    organizationId,
  );
}

export function parseBillingAccountDetail(
  value: unknown,
  accountId: string,
  organizationId: string,
): BillingAccountDetail {
  const row = object(value, "billing account detail");
  schema(row, "billing account detail");
  organization(row, organizationId, "billing account detail");
  const account = parseBillingAccount(row.account, organizationId);
  if (account.id !== accountId)
    throw new BillingApiError(
      "The server returned a different billing account than requested.",
      403,
    );
  const invoices = array(row.invoices, "account invoices").map((item) =>
    parseBillingInvoice(item, organizationId),
  );
  const payerVersions = array(
    row.payer_versions,
    "account payer versions",
    10_000,
  ).map((item) => parseBillingAccountPayerVersion(item, organizationId));
  const payments = array(row.payments, "account payments").map((item) =>
    parseBillingPayment(item, organizationId),
  );
  const agreements = array(row.agreements, "account agreements").map((item) =>
    parseBillingAgreement(item, organizationId),
  );
  const orderedPayerVersions = [...payerVersions].sort(
    (left, right) => left.version_number - right.version_number,
  );
  if (
    payerVersions.length === 0 ||
    new Set(payerVersions.map((item) => item.id)).size !==
      payerVersions.length ||
    new Set(payerVersions.map((item) => item.version_number)).size !==
      payerVersions.length ||
    orderedPayerVersions.some(
      (item, index) => item.version_number !== index + 1,
    ) ||
    orderedPayerVersions.some(
      (item, index) =>
        index > 0 &&
        new Date(item.assigned_at).valueOf() <
          new Date(orderedPayerVersions[index - 1].assigned_at).valueOf(),
    ) ||
    payerVersions.some(
      (item) =>
        item.billing_account_id !== accountId ||
        item.family_id !== account.family_id,
    ) ||
    !payerVersions.some(
      (item) =>
        item.id === account.latest_payer_version_id &&
        item.version_number === account.latest_payer_version_number &&
        item.payer_guardian_id === account.payer_guardian_id &&
        item.version_number ===
          Math.max(...payerVersions.map((version) => version.version_number)),
    ) ||
    invoices.some((item) => {
      const payerVersion = payerVersions.find(
        (version) => version.id === item.billing_account_payer_version_id,
      );
      return (
        !payerVersion ||
        payerVersion.billing_account_id !== item.billing_account_id ||
        payerVersion.family_id !== item.family_id ||
        payerVersion.payer_guardian_id !== item.payer_guardian_id
      );
    }) ||
    invoices.some((item) => item.billing_account_id !== accountId) ||
    payments.some((item) => item.billing_account_id !== accountId) ||
    agreements.some((item) => item.billing_account_id !== accountId)
  )
    throw new BillingApiError(
      "A billing record crossed the selected account boundary.",
      403,
    );
  return {
    schema_version: SCHEMA,
    organization_id: organizationId,
    currency: currency(row.currency, "billing account detail"),
    account,
    payer_versions: payerVersions,
    invoices,
    payments,
    agreements,
  };
}

export function parseFamilyBillingOptions(
  value: unknown,
  organizationId: string,
): BillingFamilyOptions {
  const row = object(value, "billing source options");
  schema(row, "billing source options");
  organization(row, organizationId, "billing source options");
  const items = array(row.items, "billing source families", 100).map(
    (entry): BillingFamilyOption => {
      const family = object(entry, "billing source family");
      const familyId = id(family.id, "source family id");
      organization(family, organizationId, "billing source family");
      const guardians = array(
        family.guardians,
        "billing source guardians",
        100,
      ).map((entry) => {
        const guardian = object(entry, "billing source guardian");
        organization(guardian, organizationId, "billing source guardian");
        if (id(guardian.family_id, "guardian family id") !== familyId)
          throw new BillingApiError(
            "A payer option crossed its family boundary.",
            403,
          );
        const first = boundedString(
          guardian.first_name,
          "guardian first name",
          100,
        ).trim();
        const last = boundedString(
          guardian.last_name,
          "guardian last name",
          100,
        ).trim();
        const name = [first, last].filter(Boolean).join(" ");
        if (!name) invalid("guardian name");
        return {
          organization_id: organizationId,
          id: id(guardian.id, "guardian id"),
          family_id: familyId,
          name,
          email: boundedString(guardian.email, "guardian email", 320),
          cell_phone: boundedString(
            guardian.cell_phone,
            "guardian cell phone",
            80,
          ),
        };
      });
      const children = array(
        family.children,
        "billing source children",
        200,
      ).map((entry) => {
        const child = object(entry, "billing source child");
        organization(child, organizationId, "billing source child");
        if (id(child.family_id, "child family id") !== familyId)
          throw new BillingApiError(
            "A child option crossed its family boundary.",
            403,
          );
        const first = text(child.first_name, "child first name", 100);
        const last = text(child.last_name, "child last name", 100);
        return {
          organization_id: organizationId,
          id: id(child.id, "child id"),
          family_id: familyId,
          name: `${first} ${last}`,
          age_group: optionalText(child.age_group, "child age group", 100),
          enrollment_id:
            child.enrollment_id == null
              ? null
              : id(child.enrollment_id, "child enrollment id"),
          facility_id:
            child.facility_id == null
              ? null
              : id(child.facility_id, "child facility id"),
          program_id:
            child.program_id == null
              ? null
              : id(child.program_id, "child program id"),
          program_type:
            child.program_type == null
              ? null
              : enumValue(
                  child.program_type,
                  ["daycare", "out_of_school_care"] as const,
                  "child program type",
                ),
        };
      });
      return {
        organization_id: organizationId,
        id: familyId,
        name: text(family.name, "family name", 300),
        status: enumValue(family.status, ["active"] as const, "family status"),
        guardians,
        children,
      };
    },
  );
  const programs = array(row.programs, "billing source programs", 500).map(
    (entry): BillingProgramOption => {
      const program = object(entry, "billing source program");
      organization(program, organizationId, "billing source program");
      return {
        organization_id: organizationId,
        facility_id: id(program.facility_id, "source program facility id"),
        facility_name: text(
          program.facility_name,
          "source program facility name",
          300,
        ),
        program_id: id(program.program_id, "source program id"),
        program_name: text(program.program_name, "source program name", 300),
        program_type: enumValue(
          program.program_type,
          ["daycare", "out_of_school_care"] as const,
          "source program type",
        ),
        minimum_age_months:
          program.minimum_age_months == null
            ? null
            : integer(program.minimum_age_months, "source program minimum age"),
        maximum_age_months:
          program.maximum_age_months == null
            ? null
            : integer(program.maximum_age_months, "source program maximum age"),
      };
    },
  );
  const total = integer(row.total, "billing source total");
  const limit = integer(row.limit, "billing source limit", 1, 100);
  const offset = integer(row.offset, "billing source offset");
  if (total < items.length) invalid("billing source total");
  return {
    schema_version: SCHEMA,
    organization_id: organizationId,
    items,
    programs,
    total,
    limit,
    offset,
  };
}

const RECEIPT_MAP: Record<
  BillingCommandKind,
  [BillingCommandReceipt["command_type"], BillingCommandReceipt["result_kind"]]
> = {
  "account.create": ["account_open", "billing_account"],
  "account.payer.assign": ["account_payer_assign", "billing_account"],
  "rate_plan.create": ["rate_version_publish", "billing_rate_plan"],
  "agreement.create": ["agreement_establish", "billing_agreement"],
  "invoice.issue": ["invoice_issue", "billing_invoice"],
  "payment.record": ["payment_record", "billing_payment"],
  "payment.allocate": ["payment_allocate", "billing_allocation"],
  "credit.create": ["credit_issue", "billing_credit"],
};
export function parseBillingCommandReceipt(
  value: unknown,
  organizationId: string,
  operationId: string,
  commandKind: BillingCommandKind,
  expectedRequestHash?: string,
): BillingCommandReceipt {
  const row = object(value, "billing command receipt");
  schema(row, "billing command receipt");
  const provenance = parseBillingProvenance(row, "billing command receipt");
  const receipt: BillingCommandReceipt = {
    ...provenance,
    schema_version: SCHEMA,
    organization_id: id(row.organization_id, "receipt organization id"),
    client_operation_id: id(row.client_operation_id, "receipt operation id"),
    request_hash: sha256(row.request_hash, "receipt request hash"),
    command_type: enumValue(
      row.command_type,
      Object.values(RECEIPT_MAP).map(([item]) => item),
      "receipt command type",
    ),
    result_kind: enumValue(
      row.result_kind,
      Object.values(RECEIPT_MAP).map(([, item]) => item),
      "receipt result kind",
    ),
    result_id: id(row.result_id, "receipt result id"),
    committed_at: timestamp(row.committed_at, "receipt commit time"),
    exact_retry: boolean(row.exact_retry, "receipt retry flag"),
    action_path: text(row.action_path, "receipt action path", 500),
  };
  const expected = RECEIPT_MAP[commandKind];
  if (
    receipt.organization_id !== organizationId ||
    receipt.client_operation_id !== operationId ||
    receipt.command_type !== expected[0] ||
    receipt.result_kind !== expected[1] ||
    (expectedRequestHash != null &&
      receipt.request_hash !== expectedRequestHash)
  )
    throw new BillingApiError(
      "The billing receipt did not match the exact submitted operation.",
      null,
    );
  return receipt;
}

export function parseBillingCommandPreparation(
  value: unknown,
  organizationId: string,
  operationId: string,
  commandKind: BillingCommandKind,
): BillingCommandPreparation {
  const row = object(value, "billing command preparation");
  schema(row, "billing command preparation");
  const provenance = parseBillingProvenance(
    row,
    "billing command preparation",
  );
  const preparation: BillingCommandPreparation = {
    ...provenance,
    schema_version: SCHEMA,
    organization_id: organization(
      row,
      organizationId,
      "billing command preparation",
    ),
    client_operation_id: id(
      row.client_operation_id,
      "billing preparation operation id",
    ),
    command_type: enumValue(
      row.command_type,
      Object.values(RECEIPT_MAP).map(([commandType]) => commandType),
      "billing preparation command type",
    ),
    target_scope: text(
      row.target_scope,
      "billing preparation target scope",
      255,
    ),
    request_hash: sha256(row.request_hash, "billing preparation request hash"),
    prepared_at: timestamp(row.prepared_at, "billing preparation timestamp"),
    exact_retry: boolean(row.exact_retry, "billing preparation retry flag"),
  };
  if (
    preparation.client_operation_id !== operationId ||
    preparation.command_type !== billingCommandType(commandKind)
  )
    throw new BillingApiError(
      "The billing preparation did not match the intended command.",
      null,
    );
  return preparation;
}

function commandLookupState(
  error: BillingApiError,
  organizationId: string,
  operationId: string,
): "finalized_absent" | "prepared_not_committed" | "not_found" | null {
  if (
    error.status !== 404 ||
    !error.details ||
    typeof error.details !== "object" ||
    Array.isArray(error.details)
  )
    return null;
  const detail = (error.details as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail))
    return null;
  const row = detail as Record<string, unknown>;
  if (
    row.code === "billing_operation_finalized_absent" &&
    row.organization_id === organizationId &&
    row.client_operation_id === operationId &&
    row.finalized === true
  )
    return "finalized_absent";
  if (
    row.code === "billing_command_prepared_not_committed" &&
    row.organization_id === organizationId &&
    row.client_operation_id === operationId &&
    row.finalized === false
  )
    return "prepared_not_committed";
  if (
    row.code === "billing_command_not_found" &&
    row.organization_id === organizationId &&
    row.client_operation_id === operationId &&
    row.finalized === false
  )
    return "not_found";
  return null;
}

export async function reconcileBillingCommand(
  organizationId: string,
  operationId: string,
  commandKind: BillingCommandKind,
  requestHash: string,
): Promise<
  | BillingCommandReceipt
  | "finalized_absent"
  | "prepared_not_committed"
  | "not_found"
> {
  try {
    return parseBillingCommandReceipt(
      await request(
        `/billing/commands/${encodeURIComponent(operationId)}?request_hash=${encodeURIComponent(requestHash)}`,
        organizationId,
      ),
      organizationId,
      operationId,
      commandKind,
      requestHash,
    );
  } catch (caught) {
    if (caught instanceof BillingApiError) {
      const state = commandLookupState(caught, organizationId, operationId);
      if (state) return state;
    }
    throw caught;
  }
}

export interface BillingAbsenceReceipt {
  schema_version: "0033";
  organization_id: string;
  client_operation_id: string;
  command_type: BillingCommandReceipt["command_type"];
  request_hash: string;
  target_scope: string;
  reason_code: "operator_confirmed_not_committed";
  finalized_at: string;
  exact_retry: boolean;
}

export async function finalizeBillingCommandAbsence(
  organizationId: string,
  operation: {
    client_operation_id: string;
    command_kind: BillingCommandKind;
    command_type: BillingCommandReceipt["command_type"];
    target_scope: string;
    request_hash: string;
  },
): Promise<BillingAbsenceReceipt> {
  const operationId = operation.client_operation_id;
  const row = object(
    await request(
      `/billing/commands/${encodeURIComponent(operationId)}/finalize-absence`,
      organizationId,
      {
        method: "POST",
        body: JSON.stringify({
          expected_request_hash: operation.request_hash,
          reason_code: "operator_confirmed_not_committed",
        }),
      },
    ),
    "billing absence receipt",
  );
  schema(row, "billing absence receipt");
  const receipt: BillingAbsenceReceipt = {
    schema_version: SCHEMA,
    organization_id: organization(
      row,
      organizationId,
      "billing absence receipt",
    ),
    client_operation_id: id(
      row.client_operation_id,
      "absence receipt operation id",
    ),
    command_type: enumValue(
      row.command_type,
      Object.values(RECEIPT_MAP).map(([commandType]) => commandType),
      "absence receipt command type",
    ),
    request_hash: sha256(row.request_hash, "absence receipt request hash"),
    target_scope: text(row.target_scope, "absence receipt target scope", 255),
    reason_code: enumValue(
      row.reason_code,
      ["operator_confirmed_not_committed"] as const,
      "absence receipt reason",
    ),
    finalized_at: timestamp(row.finalized_at, "absence finalization time"),
    exact_retry: boolean(row.exact_retry, "absence receipt retry flag"),
  };
  if (
    receipt.client_operation_id !== operationId ||
    receipt.command_type !== operation.command_type ||
    receipt.request_hash !== operation.request_hash ||
    receipt.target_scope !== operation.target_scope
  )
    throw new BillingApiError(
      "The absence receipt did not match the protected billing operation.",
      null,
    );
  return receipt;
}

function responseMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (
      detail &&
      typeof detail === "object" &&
      !Array.isArray(detail) &&
      typeof (detail as { message?: unknown }).message === "string"
    )
      return String((detail as { message: string }).message);
  }
  if (status === 401)
    return "The secure session expired. Sign in again before continuing.";
  if (status === 403)
    return "This account cannot access billing for the selected organization.";
  if (status === 404)
    return "The billing service is not enabled for this workspace.";
  if (status === 409)
    return "Canonical billing records changed. Refresh before deciding what to do.";
  return `The billing request failed (${status}).`;
}
async function request(
  path: string,
  organizationId: string,
  options: RequestInit = {},
  capabilityProbe = false,
): Promise<unknown> {
  if (!organizationId)
    throw new BillingApiError(
      "A confirmed organization is required for billing.",
    );
  if (capabilityProbe) {
    try {
      return await apiRequest<unknown>(path, {
        ...options,
        suppressAuthorizationRecheck: true,
      });
    } catch (caught) {
      if (caught instanceof ApiError)
        throw new BillingApiError(
          caught.message,
          caught.status,
          caught.details,
        );
      throw caught;
    }
  }
  const token = getSessionToken();
  if (!token)
    throw new BillingApiError("A secure CareSync session is required.");
  const headers = addOrganizationHeader(
    new Headers(options.headers),
    organizationId,
  );
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const payload =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined")
      window.dispatchEvent(new Event("caresync-redesign:unauthorized"));
    if (response.status === 403) notifyAuthorizationDenied();
    throw new BillingApiError(
      responseMessage(payload, response.status),
      response.status,
      payload,
    );
  }
  return payload;
}
async function command<T extends object>(
  path: string,
  organizationId: string,
  operationId: string,
  kind: BillingCommandKind,
  input: T,
): Promise<BillingCommandReceipt> {
  const payload = await request(path, organizationId, {
    method: "POST",
    headers: { "X-Client-Operation-ID": operationId },
    body: JSON.stringify({ client_operation_id: operationId, ...input }),
  });
  return parseBillingCommandReceipt(payload, organizationId, operationId, kind);
}

export const billingApi = {
  capability: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingCapability(
      await request(BILLING_CAPABILITY_PATH, organizationId, { signal }, true),
      organizationId,
    ),
  manualActivation: async (
    organizationId: string,
    signal?: AbortSignal,
  ): Promise<BillingManualActivation> =>
    parseBillingManualActivation(
      await request(BILLING_MANUAL_ACTIVATION_PATH, organizationId, {
        signal,
      }),
      organizationId,
    ),
  activateManualBilling: async (
    organizationId: string,
  ): Promise<BillingManualActivation> =>
    parseBillingManualActivation(
      await request(BILLING_MANUAL_ACTIVATION_PATH, organizationId, {
        method: "POST",
        body: JSON.stringify({
          activation_policy_version: BILLING_MANUAL_ACTIVATION_POLICY,
          review_attestation: BILLING_MANUAL_REVIEW_ATTESTATION,
        }),
      }),
      organizationId,
    ),
  overview: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingOverview(
      await request("/billing/overview", organizationId, { signal }),
      organizationId,
    ),
  workspace: async (
    organizationId: string,
    signal?: AbortSignal,
  ): Promise<BillingWorkspaceProjection> => {
    const pageSize = 500;
    const pages: BillingWorkspacePage[] = [];
    const offsets: Record<BillingWorkspaceCollection, number> = {
      accounts: 0,
      payer_versions: 0,
      invoices: 0,
      payments: 0,
      rate_plans: 0,
      agreements: 0,
      allocations: 0,
      credits: 0,
    };
    let snapshotToken: string | null = null;
    let expectedSequence: number | null = null;
    let expectedTotals: Record<BillingWorkspaceCollection, number> | null =
      null;
    for (let pageNumber = 0; pageNumber < 10_000; pageNumber += 1) {
      const query = new URLSearchParams({ page_size: String(pageSize) });
      if (snapshotToken) query.set("snapshot_token", snapshotToken);
      for (const name of WORKSPACE_COLLECTIONS)
        query.set(`${name}_offset`, String(offsets[name]));
      const page = parseBillingWorkspacePage(
        await request(`/billing/workspace?${query.toString()}`, organizationId, {
          signal,
        }),
        organizationId,
      );
      for (const name of WORKSPACE_COLLECTIONS) {
        if (page.paging[name].offset !== offsets[name])
          throw new BillingApiError(
            `The billing ${name} page overlapped or skipped canonical records. No partial workspace was accepted.`,
          );
      }
      if (snapshotToken == null) {
        snapshotToken = page.paging.snapshot_token;
        expectedSequence = page.data_through_realtime_sequence;
        expectedTotals = Object.fromEntries(
          WORKSPACE_COLLECTIONS.map((name) => [name, page.paging[name].total]),
        ) as Record<BillingWorkspaceCollection, number>;
      } else if (
        page.paging.snapshot_token !== snapshotToken ||
        page.data_through_realtime_sequence !== expectedSequence ||
        WORKSPACE_COLLECTIONS.some(
          (name) => page.paging[name].total !== expectedTotals?.[name],
        )
      )
        throw new BillingApiError(
          "The canonical billing snapshot changed while its pages were loading. No partial workspace was accepted.",
          409,
        );
      pages.push(page);
      if (WORKSPACE_COLLECTIONS.every((name) => !page.paging[name].has_more))
        return assembleBillingWorkspacePages(pages, organizationId);
      for (const name of WORKSPACE_COLLECTIONS) {
        const proof = page.paging[name];
        offsets[name] = proof.next_offset ?? proof.total;
      }
    }
    throw new BillingApiError(
      "The billing workspace exceeded its safe canonical page limit. No partial workspace was accepted.",
    );
  },
  accounts: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingAccounts(
      await request("/billing/accounts", organizationId, { signal }),
      organizationId,
    ),
  account: async (
    organizationId: string,
    accountId: string,
    signal?: AbortSignal,
  ) =>
    parseBillingAccountDetail(
      await request(
        `/billing/accounts/${encodeURIComponent(accountId)}`,
        organizationId,
        { signal },
      ),
      accountId,
      organizationId,
    ),
  invoices: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingInvoices(
      await request("/billing/invoices", organizationId, { signal }),
      organizationId,
    ),
  invoiceDocumentPreview: async (
    organizationId: string,
    invoiceId: string,
    signal?: AbortSignal,
  ): Promise<BillingInvoiceDocumentPreview> => {
    const requestedInvoiceId = id(invoiceId, "requested invoice id");
    const preview = parseBillingInvoiceDocumentPreview(
      await request(
        `/billing/invoices/${encodeURIComponent(requestedInvoiceId)}/document-preview`,
        organizationId,
        { signal },
      ),
      organizationId,
      requestedInvoiceId,
    );
    await verifyBillingInvoiceDocumentDigest(preview);
    return preview;
  },
  payments: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingPayments(
      await request("/billing/payments", organizationId, { signal }),
      organizationId,
    ),
  ratePlans: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingRatePlans(
      await request("/billing/rate-plans", organizationId, { signal }),
      organizationId,
    ),
  agreements: async (organizationId: string, signal?: AbortSignal) =>
    parseBillingAgreements(
      await request("/billing/agreements", organizationId, { signal }),
      organizationId,
    ),
  familyOptions: async (
    organizationId: string,
    signal?: AbortSignal,
    onProgress?: (loaded: number, total: number) => void,
  ): Promise<BillingFamilyOptions> => {
    const items: BillingFamilyOption[] = [];
    let programs: BillingProgramOption[] | null = null;
    let offset = 0;
    let expectedTotal: number | null = null;
    do {
      const page = parseFamilyBillingOptions(
        await request(
          `/billing/source-options?search=&limit=100&offset=${offset}`,
          organizationId,
          { signal },
        ),
        organizationId,
      );
      if (page.offset !== offset)
        throw new BillingApiError(
          "The billing source directory returned a different page than requested.",
        );
      if (expectedTotal == null) expectedTotal = page.total;
      else if (page.total !== expectedTotal)
        throw new BillingApiError(
          "The billing source directory changed while it was loading. Refresh before selecting a family.",
          409,
        );
      items.push(...page.items);
      if (programs == null) programs = page.programs;
      else if (JSON.stringify(programs) !== JSON.stringify(page.programs))
        throw new BillingApiError(
          "The billing program choices changed while the family directory was loading. Refresh before publishing a rate.",
          409,
        );
      if (new Set(items.map((item) => item.id)).size !== items.length)
        throw new BillingApiError(
          "The billing source directory returned duplicate families.",
        );
      offset = items.length;
      onProgress?.(items.length, expectedTotal);
      if (!page.items.length && items.length < expectedTotal)
        throw new BillingApiError(
          "The billing source directory ended before every family was loaded.",
        );
    } while (items.length < (expectedTotal ?? 0));
    return {
      schema_version: SCHEMA,
      organization_id: organizationId,
      items,
      programs: programs ?? [],
      total: expectedTotal ?? 0,
      limit: 100,
      offset: 0,
    };
  },
  prepareCommand: async (
    organizationId: string,
    operationId: string,
    commandKind: BillingCommandKind,
    input: Record<string, unknown>,
  ) =>
    parseBillingCommandPreparation(
      await request("/billing/commands/prepare", organizationId, {
        method: "POST",
        body: JSON.stringify(
          billingPreparePayload(commandKind, operationId, input),
        ),
      }),
      organizationId,
      operationId,
      commandKind,
    ),
  createAccount: (
    organizationId: string,
    operationId: string,
    input: CreateBillingAccountInput,
  ) =>
    command(
      "/billing/accounts",
      organizationId,
      operationId,
      "account.create",
      input,
    ),
  assignAccountPayer: (
    organizationId: string,
    accountId: string,
    operationId: string,
    input: AssignBillingAccountPayerInput,
  ) =>
    command(
      `/billing/accounts/${encodeURIComponent(accountId)}/payer-assign`,
      organizationId,
      operationId,
      "account.payer.assign",
      input,
    ),
  createRatePlan: (
    organizationId: string,
    operationId: string,
    input: CreateRatePlanInput,
  ) =>
    command(
      "/billing/rate-plans",
      organizationId,
      operationId,
      "rate_plan.create",
      input,
    ),
  createAgreement: (
    organizationId: string,
    operationId: string,
    input: CreateAgreementInput,
  ) =>
    command(
      "/billing/agreements",
      organizationId,
      operationId,
      "agreement.create",
      input,
    ),
  issueInvoice: (
    organizationId: string,
    operationId: string,
    input: IssueInvoiceInput,
  ) =>
    command(
      "/billing/invoices/issue",
      organizationId,
      operationId,
      "invoice.issue",
      input,
    ),
  recordPayment: (
    organizationId: string,
    operationId: string,
    input: RecordPaymentInput,
  ) =>
    command(
      "/billing/payments",
      organizationId,
      operationId,
      "payment.record",
      input,
    ),
  allocatePayment: (
    organizationId: string,
    operationId: string,
    input: AllocatePaymentInput,
  ) =>
    command(
      "/billing/allocations",
      organizationId,
      operationId,
      "payment.allocate",
      input,
    ),
  createCredit: (
    organizationId: string,
    operationId: string,
    input: CreateCreditInput,
  ) =>
    command(
      "/billing/credits",
      organizationId,
      operationId,
      "credit.create",
      input,
    ),
  reconcileCommand: reconcileBillingCommand,
  finalizeCommandAbsence: finalizeBillingCommandAbsence,
};
