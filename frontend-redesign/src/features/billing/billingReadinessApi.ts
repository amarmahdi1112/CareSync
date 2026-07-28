import {
  ApiError,
  apiRequest,
  getSelectedOrganizationId,
} from "../../api/client";
import { asMinorUnits, isDateOnly } from "./billingModel";
import type { MinorUnits } from "./types";

export const BILLING_PROJECTION_SCHEMA = "billing-projection-v1" as const;
export const BILLING_READINESS_STATUSES = [
  "setup_ready",
  "needs_account",
  "needs_payer",
  "needs_current_enrollment",
  "needs_rate_plan",
  "needs_agreement",
  "agreement_scope_conflict",
  "needs_review",
] as const;

export type BillingReadinessStatus =
  (typeof BILLING_READINESS_STATUSES)[number];
export const BILLING_READINESS_REASON_CODES = [
  "billing_setup_ready",
  "billing_family_not_active",
  "billing_account_missing",
  "billing_payer_missing",
  "current_enrollment_missing",
  "applicable_rate_plan_missing",
  "billing_agreement_missing",
  "billing_agreement_enrollment_conflict",
  "billing_agreement_review_required",
  "billing_projection_inconsistent",
  "multiple_applicable_rate_plans",
] as const;
export type BillingReadinessReasonCode =
  (typeof BILLING_READINESS_REASON_CODES)[number];
const STATUS_REASON_CODES: Record<
  BillingReadinessStatus,
  readonly BillingReadinessReasonCode[]
> = {
  setup_ready: ["billing_setup_ready"],
  needs_account: ["billing_account_missing"],
  needs_payer: ["billing_payer_missing"],
  needs_current_enrollment: ["current_enrollment_missing"],
  needs_rate_plan: ["applicable_rate_plan_missing"],
  needs_agreement: ["billing_agreement_missing"],
  agreement_scope_conflict: ["billing_agreement_enrollment_conflict"],
  needs_review: [
    "billing_family_not_active",
    "billing_agreement_review_required",
    "billing_projection_inconsistent",
    "multiple_applicable_rate_plans",
  ],
};

export interface BillingReadinessCounts {
  total: number;
  setup_ready: number;
  needs_account: number;
  needs_payer: number;
  needs_current_enrollment: number;
  needs_rate_plan: number;
  needs_agreement: number;
  agreement_scope_conflict: number;
  needs_review: number;
}

export interface BillingReadinessItem {
  family_id: string;
  family_name: string;
  child_id: string;
  child_name: string;
  enrollment_id: string | null;
  facility_id: string | null;
  program_id: string | null;
  billing_account_id: string | null;
  payer_guardian_id: string | null;
  rate_plan_id: string | null;
  rate_plan_version_id: string | null;
  agreement_id: string | null;
  agreement_version_id: string | null;
  status: BillingReadinessStatus;
  reason_codes: BillingReadinessReasonCode[];
  action_path: string;
}

interface BillingProjectionEnvelope {
  schema_version: typeof BILLING_PROJECTION_SCHEMA;
  organization_id: string;
  generated_at: string;
  as_of_date: string;
  data_through_realtime_sequence: number;
  currency: "CAD";
}

export interface BillingReadinessResponse extends BillingProjectionEnvelope {
  counts: BillingReadinessCounts;
  items: BillingReadinessItem[];
}

export interface FamilyFinanceFamily {
  id: string;
  name: string;
  status: "pending" | "active" | "inactive" | "archived";
}

export interface FamilyFinanceAccount {
  id: string;
  account_number: string;
  status: "open";
  payer_guardian_id: string;
  payer_name: string;
}

export interface FamilyInvoiceSummary {
  invoice_count: number;
  open_invoice_count: number;
  settled_invoice_count: number;
  total_minor: MinorUnits;
  allocated_minor: MinorUnits;
  credits_minor: MinorUnits;
  outstanding_minor: MinorUnits;
}

export interface FamilyPaymentSummary {
  payment_count: number;
  recorded_minor: MinorUnits;
  allocated_minor: MinorUnits;
  unapplied_minor: MinorUnits;
}

export interface ChildChargeAttribution {
  invoice_count: number;
  line_count: number;
  gross_minor: MinorUnits;
  funding_minor: MinorUnits;
  subtotal_minor: MinorUnits;
  tax_minor: MinorUnits;
  total_minor: MinorUnits;
}

/**
 * Child finance deliberately contains charge attribution only. Payments,
 * credits, outstanding balances, and settlement belong to the family account.
 */
export interface ChildFinanceSummary {
  child_id: string;
  child_name: string;
  is_active: boolean;
  current_enrollment_id: string | null;
  readiness_status: BillingReadinessStatus | null;
  charge_attribution: ChildChargeAttribution;
}

export interface FamilyFinanceSummaryResponse
  extends BillingProjectionEnvelope {
  family: FamilyFinanceFamily;
  account: FamilyFinanceAccount | null;
  invoice_summary: FamilyInvoiceSummary;
  payment_summary: FamilyPaymentSummary;
  children: ChildFinanceSummary[];
}

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_MINOR_UNITS = 9_000_000_000_000;

function invalid(label: string): never {
  throw new ApiError(0, `The server returned invalid ${label}.`);
}

function exact(
  value: unknown,
  keys: readonly string[],
  label: string,
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalid(label);
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (
    actual.length !== expected.length ||
    actual.some((key, index) => key !== expected[index])
  )
    invalid(`${label} shape`);
  return row;
}

function text(value: unknown, label: string, maximum = 2_048): string {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > maximum
  )
    invalid(label);
  return value;
}

function uuid(value: unknown, label: string): string {
  const parsed = text(value, label, 64);
  if (!UUID.test(parsed)) invalid(label);
  return parsed.toLowerCase();
}

function optionalUuid(value: unknown, label: string): string | null {
  return value === null ? null : uuid(value, label);
}

function integer(
  value: unknown,
  label: string,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  if (
    !Number.isSafeInteger(value) ||
    Number(value) < 0 ||
    Number(value) > maximum
  )
    invalid(label);
  return Number(value);
}

function minor(value: unknown, label: string): MinorUnits {
  return asMinorUnits(
    integer(value, `${label}; money must use integer minor units`, MAX_MINOR_UNITS),
    label,
  );
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") invalid(label);
  return value;
}

function oneOf<Value extends string>(
  value: unknown,
  options: readonly Value[],
  label: string,
): Value {
  if (typeof value !== "string" || !options.includes(value as Value))
    invalid(label);
  return value as Value;
}

function timestamp(value: unknown, label: string): string {
  const parsed = text(value, label, 64);
  if (
    !/[zZ]|[+-]\d\d:\d\d$/.test(parsed) ||
    Number.isNaN(Date.parse(parsed))
  )
    invalid(label);
  return parsed;
}

function date(value: unknown, label: string): string {
  const parsed = text(value, label, 10);
  if (!isDateOnly(parsed)) invalid(label);
  return parsed;
}

function array(
  value: unknown,
  label: string,
  maximum = 10_000,
): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) invalid(label);
  return value;
}

function status(value: unknown, label: string): BillingReadinessStatus {
  return oneOf(value, BILLING_READINESS_STATUSES, label);
}

function reasonCodes(value: unknown): BillingReadinessReasonCode[] {
  const result = array(value, "billing readiness reason codes", 20).map(
    (item) =>
      oneOf(
        item,
        BILLING_READINESS_REASON_CODES,
        "billing readiness reason code",
      ),
  );
  if (!result.length) invalid("billing readiness reason codes");
  if (new Set(result).size !== result.length)
    invalid("duplicate billing readiness reason codes");
  return result;
}

function safeActionPath(
  value: unknown,
  expected: {
    status: BillingReadinessStatus;
    familyId: string;
    childId: string;
    billingAccountId: string | null;
    reasonCode: BillingReadinessReasonCode;
  },
): string {
  const path = text(value, "billing readiness action path", 1_000);
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("#"))
    invalid("billing readiness action path");
  const parsed = new URL(path, "https://caresync.invalid");
  if (parsed.origin !== "https://caresync.invalid")
    invalid("billing readiness action path");
  const keys = [...parsed.searchParams.keys()];
  const uniqueKeys = new Set(keys);
  if (keys.length !== uniqueKeys.size)
    invalid("billing readiness action path");
  if (expected.status === "needs_current_enrollment") {
    if (
      parsed.pathname !== `/children/${encodeURIComponent(expected.childId)}` ||
      keys.length !== 1 ||
      parsed.searchParams.get("section") !== "enrollment"
    )
      invalid("billing readiness action path");
    return `${parsed.pathname}?section=enrollment`;
  }
  if (expected.reasonCode === "billing_family_not_active") {
    if (
      expected.status !== "needs_review" ||
      parsed.pathname !== `/families/${encodeURIComponent(expected.familyId)}` ||
      keys.length !== 1 ||
      parsed.searchParams.get("focus") !== "family-status"
    )
      invalid("billing readiness action path");
    return `${parsed.pathname}?focus=family-status`;
  }
  if (parsed.pathname !== "/billing") invalid("billing readiness action path");
  const expectedView =
    expected.status === "needs_account" || expected.status === "needs_payer"
      ? "accounts"
      : expected.status === "setup_ready"
        ? "invoices"
        : "rates";
  const account = parsed.searchParams.get("account");
  if (
    parsed.searchParams.get("view") !== expectedView ||
    keys.some((key) => key !== "view" && key !== "account") ||
    (account !== null && account.toLowerCase() !== expected.billingAccountId) ||
    (expected.status === "needs_payer" &&
      (!expected.billingAccountId || account === null)) ||
    (expected.status === "setup_ready" &&
      (!expected.billingAccountId || account === null)) ||
    (expected.status === "needs_account" && account !== null)
  )
    invalid("billing readiness action path");
  return `/billing?${parsed.searchParams.toString()}`;
}

function envelope(
  row: Record<string, unknown>,
  organizationId: string,
): BillingProjectionEnvelope {
  if (row.schema_version !== BILLING_PROJECTION_SCHEMA)
    invalid("billing projection schema version");
  const actualOrganizationId = uuid(
    row.organization_id,
    "billing projection organization id",
  );
  if (actualOrganizationId !== organizationId.toLowerCase())
    throw new ApiError(
      403,
      "Billing projections crossed the selected organization boundary.",
    );
  if (row.currency !== "CAD") invalid("billing projection currency");
  return {
    schema_version: BILLING_PROJECTION_SCHEMA,
    organization_id: actualOrganizationId,
    generated_at: timestamp(
      row.generated_at,
      "billing projection generation time",
    ),
    as_of_date: date(row.as_of_date, "billing projection as-of date"),
    data_through_realtime_sequence: integer(
      row.data_through_realtime_sequence,
      "billing projection realtime sequence",
    ),
    currency: "CAD",
  };
}

function parseReadinessItem(value: unknown): BillingReadinessItem {
  const row = exact(
    value,
    [
      "family_id",
      "family_name",
      "child_id",
      "child_name",
      "enrollment_id",
      "facility_id",
      "program_id",
      "billing_account_id",
      "payer_guardian_id",
      "rate_plan_id",
      "rate_plan_version_id",
      "agreement_id",
      "agreement_version_id",
      "status",
      "reason_codes",
      "action_path",
    ],
    "billing readiness item",
  );
  const ratePlanId = optionalUuid(
    row.rate_plan_id,
    "billing readiness rate plan id",
  );
  const ratePlanVersionId = optionalUuid(
    row.rate_plan_version_id,
    "billing readiness rate plan version id",
  );
  const agreementId = optionalUuid(
    row.agreement_id,
    "billing readiness agreement id",
  );
  const agreementVersionId = optionalUuid(
    row.agreement_version_id,
    "billing readiness agreement version id",
  );
  if (Boolean(ratePlanId) !== Boolean(ratePlanVersionId))
    invalid("billing readiness rate plan identity");
  if (Boolean(agreementId) !== Boolean(agreementVersionId))
    invalid("billing readiness agreement identity");
  const parsedStatus = status(row.status, "billing readiness status");
  const familyId = uuid(row.family_id, "billing readiness family id");
  const childId = uuid(row.child_id, "billing readiness child id");
  const billingAccountId = optionalUuid(
    row.billing_account_id,
    "billing readiness account id",
  );
  const parsedReasons = reasonCodes(row.reason_codes);
  if (
    parsedReasons.length !== 1 ||
    !STATUS_REASON_CODES[parsedStatus].includes(parsedReasons[0])
  )
    invalid("billing readiness status and reason consistency");
  return {
    family_id: familyId,
    family_name: text(row.family_name, "billing readiness family name", 300),
    child_id: childId,
    child_name: text(row.child_name, "billing readiness child name", 300),
    enrollment_id: optionalUuid(
      row.enrollment_id,
      "billing readiness enrollment id",
    ),
    facility_id: optionalUuid(
      row.facility_id,
      "billing readiness facility id",
    ),
    program_id: optionalUuid(
      row.program_id,
      "billing readiness program id",
    ),
    billing_account_id: billingAccountId,
    payer_guardian_id: optionalUuid(
      row.payer_guardian_id,
      "billing readiness payer id",
    ),
    rate_plan_id: ratePlanId,
    rate_plan_version_id: ratePlanVersionId,
    agreement_id: agreementId,
    agreement_version_id: agreementVersionId,
    status: parsedStatus,
    reason_codes: parsedReasons,
    action_path: safeActionPath(row.action_path, {
      status: parsedStatus,
      familyId,
      childId,
      billingAccountId,
      reasonCode: parsedReasons[0],
    }),
  };
}

function parseCounts(value: unknown): BillingReadinessCounts {
  const row = exact(
    value,
    ["total", ...BILLING_READINESS_STATUSES],
    "billing readiness counts",
  );
  return {
    total: integer(row.total, "billing readiness total"),
    setup_ready: integer(row.setup_ready, "setup-ready count"),
    needs_account: integer(row.needs_account, "needs-account count"),
    needs_payer: integer(row.needs_payer, "needs-payer count"),
    needs_current_enrollment: integer(
      row.needs_current_enrollment,
      "needs-current-enrollment count",
    ),
    needs_rate_plan: integer(row.needs_rate_plan, "needs-rate-plan count"),
    needs_agreement: integer(
      row.needs_agreement,
      "needs-agreement count",
    ),
    agreement_scope_conflict: integer(
      row.agreement_scope_conflict,
      "agreement-scope-conflict count",
    ),
    needs_review: integer(row.needs_review, "needs-review count"),
  };
}

export function parseBillingReadiness(
  value: unknown,
  organizationId: string,
): BillingReadinessResponse {
  const row = exact(
    value,
    [
      "schema_version",
      "organization_id",
      "generated_at",
      "as_of_date",
      "data_through_realtime_sequence",
      "currency",
      "counts",
      "items",
    ],
    "billing readiness response",
  );
  const items = array(row.items, "billing readiness items").map(
    parseReadinessItem,
  );
  const identities = items.map(
    (item) => `${item.family_id}:${item.child_id}:${item.enrollment_id ?? "-"}`,
  );
  if (new Set(identities).size !== identities.length)
    invalid("duplicate billing readiness items");
  const counts = parseCounts(row.counts);
  const countedTotal = BILLING_READINESS_STATUSES.reduce(
    (total, key) => total + counts[key],
    0,
  );
  if (counts.total !== items.length || counts.total !== countedTotal)
    invalid("billing readiness count reconciliation");
  for (const key of BILLING_READINESS_STATUSES) {
    if (items.filter((item) => item.status === key).length !== counts[key])
      invalid("billing readiness status reconciliation");
  }
  return { ...envelope(row, organizationId), counts, items };
}

function parseFamily(value: unknown, familyId: string): FamilyFinanceFamily {
  const row = exact(value, ["id", "name", "status"], "billing family summary");
  const id = uuid(row.id, "billing family summary id");
  if (id !== familyId.toLowerCase())
    throw new ApiError(
      403,
      "The billing family summary crossed the requested family boundary.",
    );
  return {
    id,
    name: text(row.name, "billing family name", 300),
    status: oneOf(
      row.status,
      ["pending", "active", "inactive", "archived"] as const,
      "billing family status",
    ),
  };
}

function parseAccount(value: unknown): FamilyFinanceAccount | null {
  if (value === null) return null;
  const row = exact(
    value,
    [
      "id",
      "account_number",
      "status",
      "payer_guardian_id",
      "payer_name",
    ],
    "billing account summary",
  );
  return {
    id: uuid(row.id, "billing account id"),
    account_number: text(row.account_number, "billing account number", 80),
    status: oneOf(row.status, ["open"] as const, "billing account status"),
    payer_guardian_id: uuid(
      row.payer_guardian_id,
      "billing account payer id",
    ),
    payer_name: text(row.payer_name, "billing account payer name", 300),
  };
}

function parseInvoiceSummary(value: unknown): FamilyInvoiceSummary {
  const row = exact(
    value,
    [
      "invoice_count",
      "open_invoice_count",
      "settled_invoice_count",
      "total_minor",
      "allocated_minor",
      "credits_minor",
      "outstanding_minor",
    ],
    "family invoice summary",
  );
  const result = {
    invoice_count: integer(row.invoice_count, "family invoice count"),
    open_invoice_count: integer(
      row.open_invoice_count,
      "family open invoice count",
    ),
    settled_invoice_count: integer(
      row.settled_invoice_count,
      "family settled invoice count",
    ),
    total_minor: minor(row.total_minor, "family invoice total"),
    allocated_minor: minor(
      row.allocated_minor,
      "family invoice allocations",
    ),
    credits_minor: minor(row.credits_minor, "family invoice credits"),
    outstanding_minor: minor(
      row.outstanding_minor,
      "family invoice outstanding",
    ),
  };
  if (
    result.open_invoice_count + result.settled_invoice_count !==
      result.invoice_count ||
    result.allocated_minor +
      result.credits_minor +
      result.outstanding_minor !==
      result.total_minor
  )
    invalid("family invoice summary reconciliation");
  return result;
}

function parsePaymentSummary(value: unknown): FamilyPaymentSummary {
  const row = exact(
    value,
    [
      "payment_count",
      "recorded_minor",
      "allocated_minor",
      "unapplied_minor",
    ],
    "family payment summary",
  );
  const result = {
    payment_count: integer(row.payment_count, "family payment count"),
    recorded_minor: minor(row.recorded_minor, "family recorded payments"),
    allocated_minor: minor(
      row.allocated_minor,
      "family allocated payments",
    ),
    unapplied_minor: minor(
      row.unapplied_minor,
      "family unapplied payments",
    ),
  };
  if (result.allocated_minor + result.unapplied_minor !== result.recorded_minor)
    invalid("family payment summary reconciliation");
  return result;
}

function parseChargeAttribution(value: unknown): ChildChargeAttribution {
  const row = exact(
    value,
    [
      "invoice_count",
      "line_count",
      "gross_minor",
      "funding_minor",
      "subtotal_minor",
      "tax_minor",
      "total_minor",
    ],
    "child charge attribution",
  );
  const result = {
    invoice_count: integer(
      row.invoice_count,
      "child attributed invoice count",
    ),
    line_count: integer(row.line_count, "child attributed line count"),
    gross_minor: minor(row.gross_minor, "child gross charge attribution"),
    funding_minor: minor(
      row.funding_minor,
      "child funding charge attribution",
    ),
    subtotal_minor: minor(
      row.subtotal_minor,
      "child subtotal charge attribution",
    ),
    tax_minor: minor(row.tax_minor, "child tax charge attribution"),
    total_minor: minor(row.total_minor, "child total charge attribution"),
  };
  if (
    result.funding_minor > result.gross_minor ||
    result.gross_minor - result.funding_minor !== result.subtotal_minor ||
    result.subtotal_minor + result.tax_minor !== result.total_minor ||
    result.invoice_count > result.line_count
  )
    invalid("child charge attribution reconciliation");
  return result;
}

function parseChild(value: unknown): ChildFinanceSummary {
  const row = exact(
    value,
    [
      "child_id",
      "child_name",
      "is_active",
      "current_enrollment_id",
      "readiness_status",
      "charge_attribution",
    ],
    "child finance summary",
  );
  return {
    child_id: uuid(row.child_id, "child finance id"),
    child_name: text(row.child_name, "child finance name", 300),
    is_active: boolean(row.is_active, "child active state"),
    current_enrollment_id: optionalUuid(
      row.current_enrollment_id,
      "child current enrollment id",
    ),
    readiness_status:
      row.readiness_status === null
        ? null
        : status(row.readiness_status, "child billing readiness status"),
    charge_attribution: parseChargeAttribution(row.charge_attribution),
  };
}

export function parseFamilyFinanceSummary(
  value: unknown,
  organizationId: string,
  familyId: string,
): FamilyFinanceSummaryResponse {
  const row = exact(
    value,
    [
      "schema_version",
      "organization_id",
      "generated_at",
      "as_of_date",
      "data_through_realtime_sequence",
      "currency",
      "family",
      "account",
      "invoice_summary",
      "payment_summary",
      "children",
    ],
    "family finance summary response",
  );
  const children = array(row.children, "family finance children", 500).map(
    parseChild,
  );
  if (new Set(children.map((child) => child.child_id)).size !== children.length)
    invalid("duplicate child finance summaries");
  const invoiceSummary = parseInvoiceSummary(row.invoice_summary);
  const attributedTotals = children.reduce(
    (summary, child) => ({
      gross: summary.gross + child.charge_attribution.gross_minor,
      funding: summary.funding + child.charge_attribution.funding_minor,
      subtotal: summary.subtotal + child.charge_attribution.subtotal_minor,
      tax: summary.tax + child.charge_attribution.tax_minor,
      total: summary.total + child.charge_attribution.total_minor,
    }),
    { gross: 0, funding: 0, subtotal: 0, tax: 0, total: 0 },
  );
  if (
    Object.values(attributedTotals).some(
      (amount) =>
        !Number.isSafeInteger(amount) || amount > MAX_MINOR_UNITS,
    ) ||
    attributedTotals.total !== invoiceSummary.total_minor
  )
    invalid("family child charge attribution reconciliation");
  return {
    ...envelope(row, organizationId),
    family: parseFamily(row.family, familyId),
    account: parseAccount(row.account),
    invoice_summary: invoiceSummary,
    payment_summary: parsePaymentSummary(row.payment_summary),
    children,
  };
}

function assertSelectedOrganization(organizationId: string): void {
  if (
    !UUID.test(organizationId) ||
    getSelectedOrganizationId()?.toLowerCase() !== organizationId.toLowerCase()
  )
    throw new ApiError(
      403,
      "Billing projections do not match the selected organization workspace.",
    );
}

export async function fetchBillingReadiness(
  organizationId: string,
  signal?: AbortSignal,
): Promise<BillingReadinessResponse> {
  assertSelectedOrganization(organizationId);
  return parseBillingReadiness(
    await apiRequest<unknown>("/billing/readiness", { signal }),
    organizationId,
  );
}

export async function fetchFamilyFinanceSummary(
  organizationId: string,
  familyId: string,
  signal?: AbortSignal,
): Promise<FamilyFinanceSummaryResponse> {
  assertSelectedOrganization(organizationId);
  if (!UUID.test(familyId))
    throw new ApiError(0, "A valid family is required for billing.");
  return parseFamilyFinanceSummary(
    await apiRequest<unknown>(
      `/billing/families/${encodeURIComponent(familyId)}/summary`,
      { signal },
    ),
    organizationId,
    familyId,
  );
}

export const billingReadinessApi = {
  readiness: fetchBillingReadiness,
  familySummary: fetchFamilyFinanceSummary,
} as const;
