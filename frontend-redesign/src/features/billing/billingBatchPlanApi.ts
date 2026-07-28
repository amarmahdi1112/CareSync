import {
  ApiError,
  apiRequest,
  getSelectedOrganizationId,
} from "../../api/client";
import { BillingApiError } from "./billingApi";
import {
  BILLING_READINESS_REASON_CODES,
  BILLING_READINESS_STATUSES,
  type BillingReadinessReasonCode,
  type BillingReadinessStatus,
} from "./billingReadinessApi";
import { isDateOnly } from "./billingModel";
import type {
  BillingCommandKind,
  BillingCommandReceipt,
  BillingFrequency,
  BillingUnit,
} from "./types";

export const BILLING_BATCH_WAVES = [
  "account_payer",
  "rate_plan",
  "agreement",
  "ready",
  "manual_review",
] as const;
export const BILLING_BATCH_ACTIONABLE_WAVES = [
  "account_payer",
  "rate_plan",
  "agreement",
] as const;
export const BILLING_BATCH_COMMAND_TYPES = [
  "account_open",
  "account_payer_assign",
  "rate_version_publish",
  "agreement_establish",
] as const;

export type BillingBatchWave = (typeof BILLING_BATCH_WAVES)[number];
export type BillingBatchActionableWave =
  (typeof BILLING_BATCH_ACTIONABLE_WAVES)[number];
export type BillingBatchCommandType =
  (typeof BILLING_BATCH_COMMAND_TYPES)[number];
export type BillingBatchWaveFilter = "all" | BillingBatchWave;

export interface BillingBatchAffectedChild {
  family_id: string;
  family_name: string;
  child_id: string;
  child_name: string;
  enrollment_id: string | null;
}

export interface BillingBatchPayerOption {
  guardian_id: string;
  display_name: string;
  is_primary: boolean;
}

export interface BillingBatchRatePlanOption {
  rate_plan_id: string;
  code: string;
  name: string;
  age_group: string | null;
  latest_version_id: string | null;
  latest_version_number: number | null;
  latest_billing_unit: BillingUnit | null;
  latest_unit_amount_minor: number | null;
  latest_effective_from: string | null;
  latest_effective_until: string | null;
  revision_can_resolve_as_of_date: boolean;
}

export interface BillingBatchPlanGroup {
  group_id: string;
  wave: BillingBatchWave;
  readiness_status: BillingReadinessStatus;
  reason_codes: BillingReadinessReasonCode[];
  actionable: boolean;
  block_code: string | null;
  suggested_command_type: BillingBatchCommandType | null;
  family_id: string | null;
  family_name: string | null;
  billing_account_id: string | null;
  latest_payer_version_id: string | null;
  latest_payer_version_number: number | null;
  facility_id: string | null;
  facility_name: string | null;
  program_id: string | null;
  program_name: string | null;
  program_type: "daycare" | "out_of_school_care" | null;
  age_group: string | null;
  rate_plan_id: string | null;
  rate_plan_version_id: string | null;
  rate_billing_unit: BillingUnit | null;
  rate_unit_amount_minor: number | null;
  rate_effective_from: string | null;
  rate_effective_until: string | null;
  agreement_effective_from_min: string | null;
  agreement_effective_until_max: string | null;
  agreement_effective_until_required: boolean;
  affected_count: number;
  affected_membership_digest: string;
  affected_children: BillingBatchAffectedChild[];
  affected_children_truncated: boolean;
  payer_options: BillingBatchPayerOption[];
  rate_plan_options: BillingBatchRatePlanOption[];
  action_path: string;
}

export interface BillingBatchWaveCounts {
  total: number;
  account_payer: number;
  rate_plan: number;
  agreement: number;
  ready: number;
  manual_review: number;
}

export interface BillingBatchPage {
  offset: number;
  limit: number;
  returned: number;
  total: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface BillingBatchPlan {
  schema_version: "billing-readiness-batch-plan-v1";
  organization_id: string;
  generated_at: string;
  as_of_date: string;
  data_through_realtime_sequence: number;
  snapshot_token: string;
  read_only: true;
  apply_available: boolean;
  manual_activation_required: boolean;
  counts: BillingBatchWaveCounts;
  page: BillingBatchPage;
  items: BillingBatchPlanGroup[];
}

export interface BillingBatchPreviewSelection {
  group_id: string;
  client_operation_id: string;
  payer_guardian_id?: string;
  rate_plan_id?: string;
  code?: string;
  name?: string;
  billing_unit?: BillingUnit;
  unit_amount_minor?: number;
  effective_from?: string;
  effective_until?: string;
  description?: string;
  billing_frequency?: BillingFrequency;
  family_amount_minor_per_unit?: number;
}

export interface BillingBatchPreviewBlock {
  group_id: string;
  code: string;
  message: string;
}

export interface BillingBatchPreviewIntent {
  sequence: number;
  group_id: string;
  label: string;
  command_type: BillingBatchCommandType;
  command_kind: BillingCommandKind;
  client_operation_id: string;
  target_scope: string;
  request_hash: string;
  request_payload: Record<string, unknown>;
  input: Record<string, unknown>;
  execute_path: string;
  affected_count: number;
}

export interface BillingBatchPreview {
  schema_version: "billing-readiness-batch-preview-v1";
  organization_id: string;
  snapshot_token: string;
  wave: BillingBatchActionableWave;
  previewed_at: string;
  data_through_realtime_sequence: number;
  read_only: true;
  apply_available: boolean;
  manual_activation_required: boolean;
  requires_sequential_execution: true;
  requires_canonical_refresh_after_each_intent: true;
  intents: BillingBatchPreviewIntent[];
  blocked: BillingBatchPreviewBlock[];
}

export interface FetchBillingBatchPlanInput {
  wave: BillingBatchWaveFilter;
  status?: BillingReadinessStatus | null;
  query?: string;
  limit?: number;
  offset?: number;
  snapshotToken?: string | null;
}

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const BILLING_UNITS = [
  "weekly_period",
  "biweekly_period",
  "monthly_period",
  "service_event",
] as const;
const BILLING_FREQUENCIES = [
  "weekly",
  "biweekly",
  "monthly",
  "per_service",
] as const;
const MAX_MINOR_UNITS = 9_000_000_000_000;

function invalid(label: string): never {
  throw new BillingApiError(`The server returned invalid ${label}.`);
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

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalid(label);
  return value as Record<string, unknown>;
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

function optionalText(
  value: unknown,
  label: string,
  maximum = 2_048,
): string | null {
  return value === null ? null : text(value, label, maximum);
}

function uuid(value: unknown, label: string): string {
  const parsed = text(value, label, 64);
  if (!UUID.test(parsed)) invalid(label);
  return parsed.toLowerCase();
}

function optionalUuid(value: unknown, label: string): string | null {
  return value === null ? null : uuid(value, label);
}

function sha256(value: unknown, label: string): string {
  const parsed = text(value, label, 64);
  if (!SHA256.test(parsed)) invalid(label);
  return parsed;
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

function optionalDate(value: unknown, label: string): string | null {
  return value === null ? null : date(value, label);
}

function array(
  value: unknown,
  label: string,
  maximum = 10_000,
): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) invalid(label);
  return value;
}

function nullableInteger(
  value: unknown,
  label: string,
  minimum = 0,
): number | null {
  return value === null ? null : integer(value, label, minimum);
}

function localActionPath(value: unknown, label: string): string {
  const parsed = text(value, label, 500);
  if (
    !parsed.startsWith("/") ||
    parsed.startsWith("//") ||
    parsed.includes("\\") ||
    parsed.includes("#") ||
    parsed
      .split("?")[0]
      .split("/")
      .some((segment) => segment === "..") ||
    [...parsed].some((character) => character.charCodeAt(0) < 32)
  )
    invalid(label);
  return parsed;
}

function parseAffectedChild(
  value: unknown,
  organizationFamilyId: string | null,
): BillingBatchAffectedChild {
  const row = exact(
    value,
    ["family_id", "family_name", "child_id", "child_name", "enrollment_id"],
    "billing setup affected child",
  );
  const familyId = uuid(row.family_id, "billing setup child family id");
  if (organizationFamilyId && familyId !== organizationFamilyId)
    invalid("billing setup child family ownership");
  return {
    family_id: familyId,
    family_name: text(row.family_name, "billing setup child family name", 255),
    child_id: uuid(row.child_id, "billing setup child id"),
    child_name: text(row.child_name, "billing setup child name", 255),
    enrollment_id: optionalUuid(
      row.enrollment_id,
      "billing setup child enrollment id",
    ),
  };
}

function parsePayerOption(value: unknown): BillingBatchPayerOption {
  const row = exact(
    value,
    ["guardian_id", "display_name", "is_primary"],
    "billing setup payer option",
  );
  return {
    guardian_id: uuid(row.guardian_id, "billing setup payer guardian id"),
    display_name: text(row.display_name, "billing setup payer name", 201),
    is_primary: boolean(row.is_primary, "billing setup primary payer flag"),
  };
}

function parseRatePlanOption(value: unknown): BillingBatchRatePlanOption {
  const row = exact(
    value,
    [
      "rate_plan_id",
      "code",
      "name",
      "age_group",
      "latest_version_id",
      "latest_version_number",
      "latest_billing_unit",
      "latest_unit_amount_minor",
      "latest_effective_from",
      "latest_effective_until",
      "revision_can_resolve_as_of_date",
    ],
    "billing setup rate option",
  );
  const latestVersionId = optionalUuid(
    row.latest_version_id,
    "billing setup latest rate version id",
  );
  const latestVersionNumber = nullableInteger(
    row.latest_version_number,
    "billing setup latest rate version number",
    1,
  );
  if ((latestVersionId === null) !== (latestVersionNumber === null))
    invalid("billing setup latest rate version pair");
  const latestBillingUnit =
    row.latest_billing_unit === null
      ? null
      : oneOf(
          row.latest_billing_unit,
          BILLING_UNITS,
          "billing setup latest billing unit",
        );
  const latestAmount = nullableInteger(
    row.latest_unit_amount_minor,
    "billing setup latest rate amount",
  );
  const latestEffectiveFrom = optionalDate(
    row.latest_effective_from,
    "billing setup latest rate effective date",
  );
  const latestEffectiveUntil = optionalDate(
    row.latest_effective_until,
    "billing setup latest rate end date",
  );
  if (
    latestVersionId === null
      ? latestBillingUnit !== null ||
        latestAmount !== null ||
        latestEffectiveFrom !== null ||
        latestEffectiveUntil !== null
      : latestBillingUnit === null ||
        latestAmount === null ||
        latestEffectiveFrom === null
  )
    invalid("billing setup latest rate terms");
  return {
    rate_plan_id: uuid(row.rate_plan_id, "billing setup rate plan id"),
    code: text(row.code, "billing setup rate code", 40),
    name: text(row.name, "billing setup rate name", 160),
    age_group: optionalText(row.age_group, "billing setup rate age group", 100),
    latest_version_id: latestVersionId,
    latest_version_number: latestVersionNumber,
    latest_billing_unit: latestBillingUnit,
    latest_unit_amount_minor: latestAmount,
    latest_effective_from: latestEffectiveFrom,
    latest_effective_until: latestEffectiveUntil,
    revision_can_resolve_as_of_date: boolean(
      row.revision_can_resolve_as_of_date,
      "billing setup rate revision availability",
    ),
  };
}

function parsePlanGroup(value: unknown): BillingBatchPlanGroup {
  const row = exact(
    value,
    [
      "group_id",
      "wave",
      "readiness_status",
      "reason_codes",
      "actionable",
      "block_code",
      "suggested_command_type",
      "family_id",
      "family_name",
      "billing_account_id",
      "latest_payer_version_id",
      "latest_payer_version_number",
      "facility_id",
      "facility_name",
      "program_id",
      "program_name",
      "program_type",
      "age_group",
      "rate_plan_id",
      "rate_plan_version_id",
      "rate_billing_unit",
      "rate_unit_amount_minor",
      "rate_effective_from",
      "rate_effective_until",
      "agreement_effective_from_min",
      "agreement_effective_until_max",
      "agreement_effective_until_required",
      "affected_count",
      "affected_membership_digest",
      "affected_children",
      "affected_children_truncated",
      "payer_options",
      "rate_plan_options",
      "action_path",
    ],
    "billing setup group",
  );
  const familyId = optionalUuid(row.family_id, "billing setup group family id");
  const latestPayerVersionId = optionalUuid(
    row.latest_payer_version_id,
    "billing setup latest payer version id",
  );
  const latestPayerVersionNumber = nullableInteger(
    row.latest_payer_version_number,
    "billing setup latest payer version number",
    1,
  );
  if ((latestPayerVersionId === null) !== (latestPayerVersionNumber === null))
    invalid("billing setup latest payer version pair");
  const wave = oneOf(row.wave, BILLING_BATCH_WAVES, "billing setup wave");
  const readinessStatus = oneOf(
    row.readiness_status,
    BILLING_READINESS_STATUSES,
    "billing setup readiness status",
  );
  const reasonCodes = array(
    row.reason_codes,
    "billing setup reason codes",
    1,
  ).map((reason) =>
    oneOf(
      reason,
      BILLING_READINESS_REASON_CODES,
      "billing setup reason code",
    ),
  );
  if (reasonCodes.length !== 1) invalid("billing setup reason code count");
  const actionable = boolean(row.actionable, "billing setup actionable flag");
  const commandType =
    row.suggested_command_type === null
      ? null
      : oneOf(
          row.suggested_command_type,
          BILLING_BATCH_COMMAND_TYPES,
          "billing setup suggested command",
        );
  const blockCode = optionalText(
    row.block_code,
    "billing setup block code",
    80,
  );
  if (
    actionable !== (commandType !== null) ||
    (actionable && blockCode !== null) ||
    (!actionable && wave !== "ready" && blockCode === null)
  )
    invalid("billing setup actionability proof");
  const children = array(
    row.affected_children,
    "billing setup affected children",
    25,
  ).map((child) => parseAffectedChild(child, familyId));
  if (!children.length) invalid("billing setup affected children");
  const affectedCount = integer(
    row.affected_count,
    "billing setup affected count",
    1,
  );
  const affectedChildrenTruncated = boolean(
    row.affected_children_truncated,
    "billing setup affected preview truncation",
  );
  if (
    affectedCount < children.length ||
    affectedChildrenTruncated !== (affectedCount > children.length)
  )
    invalid("billing setup affected preview proof");
  const rateBillingUnit =
    row.rate_billing_unit === null
      ? null
      : oneOf(
          row.rate_billing_unit,
          BILLING_UNITS,
          "billing setup selected rate unit",
        );
  const rateUnitAmount = nullableInteger(
    row.rate_unit_amount_minor,
    "billing setup selected rate amount",
  );
  const rateEffectiveFrom = optionalDate(
    row.rate_effective_from,
    "billing setup selected rate effective date",
  );
  const rateEffectiveUntil = optionalDate(
    row.rate_effective_until,
    "billing setup selected rate end date",
  );
  if (
    [rateBillingUnit, rateUnitAmount, rateEffectiveFrom].some(
      (value) => value !== null,
    ) &&
    [rateBillingUnit, rateUnitAmount, rateEffectiveFrom].some(
      (value) => value === null,
    )
  )
    invalid("billing setup selected rate terms");
  const agreementFrom = optionalDate(
    row.agreement_effective_from_min,
    "billing setup agreement start boundary",
  );
  const agreementUntil = optionalDate(
    row.agreement_effective_until_max,
    "billing setup agreement end boundary",
  );
  const agreementUntilRequired = boolean(
    row.agreement_effective_until_required,
    "billing setup agreement end requirement",
  );
  if (agreementUntilRequired !== (agreementUntil !== null))
    invalid("billing setup agreement end boundary");
  return {
    group_id: sha256(row.group_id, "billing setup group id"),
    wave,
    readiness_status: readinessStatus,
    reason_codes: reasonCodes,
    actionable,
    block_code: blockCode,
    suggested_command_type: commandType,
    family_id: familyId,
    family_name: optionalText(
      row.family_name,
      "billing setup group family name",
      255,
    ),
    billing_account_id: optionalUuid(
      row.billing_account_id,
      "billing setup account id",
    ),
    latest_payer_version_id: latestPayerVersionId,
    latest_payer_version_number: latestPayerVersionNumber,
    facility_id: optionalUuid(row.facility_id, "billing setup facility id"),
    facility_name: optionalText(
      row.facility_name,
      "billing setup facility name",
      255,
    ),
    program_id: optionalUuid(row.program_id, "billing setup program id"),
    program_name: optionalText(
      row.program_name,
      "billing setup program name",
      150,
    ),
    program_type:
      row.program_type === null
        ? null
        : oneOf(
            row.program_type,
            ["daycare", "out_of_school_care"] as const,
            "billing setup program type",
          ),
    age_group: optionalText(row.age_group, "billing setup age group", 100),
    rate_plan_id: optionalUuid(row.rate_plan_id, "billing setup rate plan id"),
    rate_plan_version_id: optionalUuid(
      row.rate_plan_version_id,
      "billing setup rate version id",
    ),
    rate_billing_unit: rateBillingUnit,
    rate_unit_amount_minor: rateUnitAmount,
    rate_effective_from: rateEffectiveFrom,
    rate_effective_until: rateEffectiveUntil,
    agreement_effective_from_min: agreementFrom,
    agreement_effective_until_max: agreementUntil,
    agreement_effective_until_required: agreementUntilRequired,
    affected_count: affectedCount,
    affected_membership_digest: sha256(
      row.affected_membership_digest,
      "billing setup affected membership proof",
    ),
    affected_children: children,
    affected_children_truncated: affectedChildrenTruncated,
    payer_options: array(
      row.payer_options,
      "billing setup payer options",
      50,
    ).map(parsePayerOption),
    rate_plan_options: array(
      row.rate_plan_options,
      "billing setup rate options",
      50,
    ).map(parseRatePlanOption),
    action_path: localActionPath(
      row.action_path,
      "billing setup action path",
    ),
  };
}

function parsePage(value: unknown): BillingBatchPage {
  const row = exact(
    value,
    ["offset", "limit", "returned", "total", "has_more", "next_offset"],
    "billing setup page",
  );
  const result = {
    offset: integer(row.offset, "billing setup page offset", 0, 10_000),
    limit: integer(row.limit, "billing setup page limit", 1, 100),
    returned: integer(row.returned, "billing setup returned count"),
    total: integer(row.total, "billing setup page total"),
    has_more: boolean(row.has_more, "billing setup page continuation flag"),
    next_offset: nullableInteger(
      row.next_offset,
      "billing setup next offset",
    ),
  };
  if (
    result.returned > result.limit ||
    result.offset + result.returned > result.total ||
    result.has_more !== (result.offset + result.returned < result.total) ||
    (result.has_more
      ? result.next_offset !== result.offset + result.returned
      : result.next_offset !== null)
  )
    invalid("billing setup page proof");
  return result;
}

export function parseBillingBatchPlan(
  value: unknown,
  organizationId: string,
): BillingBatchPlan {
  const row = exact(
    value,
    [
      "schema_version",
      "organization_id",
      "generated_at",
      "as_of_date",
      "data_through_realtime_sequence",
      "snapshot_token",
      "read_only",
      "apply_available",
      "manual_activation_required",
      "counts",
      "page",
      "items",
    ],
    "billing setup plan",
  );
  if (row.schema_version !== "billing-readiness-batch-plan-v1")
    invalid("billing setup plan schema version");
  const actualOrganizationId = uuid(
    row.organization_id,
    "billing setup organization id",
  );
  if (actualOrganizationId !== organizationId.toLowerCase())
    throw new BillingApiError(
      "The billing setup plan crossed the selected organization boundary.",
      403,
    );
  if (row.read_only !== true) invalid("billing setup read-only boundary");
  const countsRow = exact(
    row.counts,
    [
      "total",
      "account_payer",
      "rate_plan",
      "agreement",
      "ready",
      "manual_review",
    ],
    "billing setup counts",
  );
  const counts: BillingBatchWaveCounts = {
    total: integer(countsRow.total, "billing setup total"),
    account_payer: integer(
      countsRow.account_payer,
      "billing setup account and payer count",
    ),
    rate_plan: integer(
      countsRow.rate_plan,
      "billing setup rate count",
    ),
    agreement: integer(
      countsRow.agreement,
      "billing setup agreement count",
    ),
    ready: integer(countsRow.ready, "billing setup ready count"),
    manual_review: integer(
      countsRow.manual_review,
      "billing setup manual-review count",
    ),
  };
  if (
    counts.total !==
    counts.account_payer +
      counts.rate_plan +
      counts.agreement +
      counts.ready +
      counts.manual_review
  )
    invalid("billing setup count reconciliation");
  const page = parsePage(row.page);
  const items = array(row.items, "billing setup groups", 100).map(
    parsePlanGroup,
  );
  if (
    items.length !== page.returned ||
    new Set(items.map((item) => item.group_id)).size !== items.length
  )
    invalid("billing setup page group proof");
  return {
    schema_version: "billing-readiness-batch-plan-v1",
    organization_id: actualOrganizationId,
    generated_at: timestamp(row.generated_at, "billing setup generation time"),
    as_of_date: date(row.as_of_date, "billing setup as-of date"),
    data_through_realtime_sequence: integer(
      row.data_through_realtime_sequence,
      "billing setup realtime sequence",
    ),
    snapshot_token: sha256(
      row.snapshot_token,
      "billing setup snapshot token",
    ),
    read_only: true,
    apply_available: boolean(
      row.apply_available,
      "billing setup apply availability",
    ),
    manual_activation_required: boolean(
      row.manual_activation_required,
      "billing setup manual activation requirement",
    ),
    counts,
    page,
    items,
  };
}

const COMMAND_KIND: Record<BillingBatchCommandType, BillingCommandKind> = {
  account_open: "account.create",
  account_payer_assign: "account.payer.assign",
  rate_version_publish: "rate_plan.create",
  agreement_establish: "agreement.create",
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonical(
            (value as Record<string, unknown>)[key],
          )}`,
      )
      .join(",")}}`;
  return JSON.stringify(value);
}

function validatedCommandPayload(
  commandType: BillingBatchCommandType,
  operationId: string,
  payloadValue: unknown,
  executePath: string,
): { payload: Record<string, unknown>; input: Record<string, unknown> } {
  const payload = record(payloadValue, "billing setup command payload");
  if (
    uuid(payload.client_operation_id, "billing setup payload operation id") !==
    operationId
  )
    invalid("billing setup payload operation proof");
  const allowed: Record<BillingBatchCommandType, readonly string[]> = {
    account_open: ["client_operation_id", "family_id", "payer_guardian_id"],
    account_payer_assign: [
      "client_operation_id",
      "account_id",
      "payer_guardian_id",
      "expected_latest_payer_version_id",
      "expected_latest_payer_version_number",
    ],
    rate_version_publish: [
      "client_operation_id",
      "rate_plan_id",
      "expected_latest_version_id",
      "expected_latest_version_number",
      "code",
      "name",
      "program_type",
      "charge_kind",
      "age_group",
      "facility_id",
      "program_id",
      "billing_unit",
      "unit_amount_minor",
      "tax_rate_basis_points",
      "effective_from",
      "effective_until",
      "description",
    ],
    agreement_establish: [
      "client_operation_id",
      "agreement_id",
      "expected_latest_version_id",
      "expected_latest_version_number",
      "account_id",
      "child_id",
      "enrollment_id",
      "rate_plan_version_id",
      "billing_frequency",
      "effective_from",
      "effective_until",
      "family_amount_minor_per_unit",
      "funding_amount_minor_per_unit",
      "reviewed",
    ],
  };
  if (Object.keys(payload).some((key) => !allowed[commandType].includes(key)))
    invalid("billing setup command payload fields");
  const required = (key: string): unknown => {
    if (!(key in payload)) invalid(`billing setup command payload ${key}`);
    return payload[key];
  };
  let expectedPath: string;
  if (commandType === "account_open") {
    uuid(required("family_id"), "billing setup account family id");
    uuid(required("payer_guardian_id"), "billing setup account payer id");
    expectedPath = "/api/v1/billing/accounts";
  } else if (commandType === "account_payer_assign") {
    const accountId = uuid(
      required("account_id"),
      "billing setup payer account id",
    );
    uuid(required("payer_guardian_id"), "billing setup payer guardian id");
    uuid(
      required("expected_latest_payer_version_id"),
      "billing setup expected payer version id",
    );
    integer(
      required("expected_latest_payer_version_number"),
      "billing setup expected payer version",
      1,
    );
    expectedPath = `/api/v1/billing/accounts/${accountId}/payer-assign`;
  } else if (commandType === "rate_version_publish") {
    const ratePlanId =
      payload.rate_plan_id === null
        ? null
        : uuid(
            required("rate_plan_id"),
            "billing setup published rate plan id",
          );
    const expectedVersionId =
      payload.expected_latest_version_id === null
        ? null
        : uuid(
            required("expected_latest_version_id"),
            "billing setup expected rate version id",
          );
    const expectedVersionNumber = nullableInteger(
      required("expected_latest_version_number"),
      "billing setup expected rate version number",
      1,
    );
    if (
      (expectedVersionId === null) !== (expectedVersionNumber === null) ||
      (ratePlanId === null) !== (expectedVersionId === null)
    )
      invalid("billing setup expected rate version proof");
    if (ratePlanId === null) {
      text(required("code"), "billing setup new rate code", 40);
      text(required("name"), "billing setup new rate name", 160);
      oneOf(
        required("program_type"),
        ["daycare", "out_of_school_care"] as const,
        "billing setup new rate program type",
      );
      if (required("charge_kind") !== "core_care")
        invalid("billing setup core-care rate boundary");
      optionalText(
        required("age_group"),
        "billing setup new rate age group",
        100,
      );
      uuid(required("facility_id"), "billing setup new rate facility id");
      uuid(required("program_id"), "billing setup new rate program id");
    } else if (
      payload.code !== null ||
      payload.name !== null ||
      payload.program_type !== null ||
      payload.charge_kind !== null ||
      payload.age_group !== null ||
      payload.facility_id !== null ||
      payload.program_id !== null
    )
      invalid("billing setup immutable rate identity boundary");
    oneOf(
      required("billing_unit"),
      BILLING_UNITS,
      "billing setup billing unit",
    );
    integer(
      required("unit_amount_minor"),
      "billing setup rate amount",
      0,
      MAX_MINOR_UNITS,
    );
    if (required("tax_rate_basis_points") !== 0)
      invalid("billing setup zero-tax boundary");
    const effectiveFrom = date(
      required("effective_from"),
      "billing setup rate effective date",
    );
    const effectiveUntil = optionalDate(
      required("effective_until"),
      "billing setup rate end date",
    );
    if (effectiveUntil && effectiveUntil < effectiveFrom)
      invalid("billing setup rate effective window");
    optionalText(
      required("description"),
      "billing setup rate description",
      500,
    );
    expectedPath = "/api/v1/billing/rate-plans";
  } else {
    if (
      required("agreement_id") !== null ||
      required("expected_latest_version_id") !== null ||
      required("expected_latest_version_number") !== null
    )
      invalid("billing setup agreement establish-only boundary");
    uuid(required("account_id"), "billing setup agreement account id");
    uuid(required("child_id"), "billing setup agreement child id");
    uuid(required("enrollment_id"), "billing setup agreement enrollment id");
    uuid(
      required("rate_plan_version_id"),
      "billing setup agreement rate version id",
    );
    oneOf(
      required("billing_frequency"),
      BILLING_FREQUENCIES,
      "billing setup billing frequency",
    );
    const effectiveFrom = date(
      required("effective_from"),
      "billing setup agreement effective date",
    );
    const effectiveUntil = optionalDate(
      required("effective_until"),
      "billing setup agreement end date",
    );
    if (effectiveUntil && effectiveUntil < effectiveFrom)
      invalid("billing setup agreement effective window");
    integer(
      required("family_amount_minor_per_unit"),
      "billing setup family amount",
      0,
      MAX_MINOR_UNITS,
    );
    if (
      required("funding_amount_minor_per_unit") !== 0 ||
      required("reviewed") !== true
    )
      invalid("billing setup reviewed zero-funding boundary");
    expectedPath = "/api/v1/billing/agreements";
  }
  if (executePath !== expectedPath)
    invalid("billing setup command destination");
  const { client_operation_id: _operationId, ...input } = payload;
  return { payload, input };
}

function parsePreviewIntent(value: unknown): BillingBatchPreviewIntent {
  const row = exact(
    value,
    [
      "sequence",
      "group_id",
      "label",
      "command_type",
      "client_operation_id",
      "target_scope",
      "request_hash",
      "request_payload",
      "prepare_request",
      "execute_path",
      "affected_count",
    ],
    "billing setup preview intent",
  );
  const commandType = oneOf(
    row.command_type,
    BILLING_BATCH_COMMAND_TYPES,
    "billing setup preview command",
  );
  const operationId = uuid(
    row.client_operation_id,
    "billing setup preview operation id",
  );
  const executePath = text(
    row.execute_path,
    "billing setup execute path",
    500,
  );
  if (
    !executePath.startsWith("/api/v1/billing/") ||
    executePath.includes("//") ||
    executePath.includes("\\")
  )
    invalid("billing setup execute path");
  const parsedPayload = validatedCommandPayload(
    commandType,
    operationId,
    row.request_payload,
    executePath,
  );
  const prepare = exact(
    row.prepare_request,
    ["command_type", "request_payload"],
    "billing setup prepare request",
  );
  if (
    prepare.command_type !== commandType ||
    canonical(prepare.request_payload) !== canonical(parsedPayload.payload)
  )
    invalid("billing setup preview prepare proof");
  return {
    sequence: integer(
      row.sequence,
      "billing setup preview sequence",
      1,
      100,
    ),
    group_id: sha256(row.group_id, "billing setup preview group id"),
    label: text(row.label, "billing setup preview label", 255),
    command_type: commandType,
    command_kind: COMMAND_KIND[commandType],
    client_operation_id: operationId,
    target_scope: text(
      row.target_scope,
      "billing setup target scope",
      100,
    ),
    request_hash: sha256(
      row.request_hash,
      "billing setup preview request hash",
    ),
    request_payload: parsedPayload.payload,
    input: parsedPayload.input,
    execute_path: executePath,
    affected_count: integer(
      row.affected_count,
      "billing setup affected count",
      1,
    ),
  };
}

export function parseBillingBatchPreview(
  value: unknown,
  organizationId: string,
  expectedSnapshotToken: string,
  expectedWave: BillingBatchActionableWave,
): BillingBatchPreview {
  const row = exact(
    value,
    [
      "schema_version",
      "organization_id",
      "snapshot_token",
      "wave",
      "previewed_at",
      "data_through_realtime_sequence",
      "read_only",
      "apply_available",
      "manual_activation_required",
      "requires_sequential_execution",
      "requires_canonical_refresh_after_each_intent",
      "intents",
      "blocked",
    ],
    "billing setup preview",
  );
  if (row.schema_version !== "billing-readiness-batch-preview-v1")
    invalid("billing setup preview schema");
  const actualOrganizationId = uuid(
    row.organization_id,
    "billing setup preview organization id",
  );
  if (actualOrganizationId !== organizationId.toLowerCase())
    throw new BillingApiError(
      "The billing setup preview crossed the selected organization boundary.",
      403,
    );
  const snapshotToken = sha256(
    row.snapshot_token,
    "billing setup preview snapshot",
  );
  const wave = oneOf(
    row.wave,
    BILLING_BATCH_ACTIONABLE_WAVES,
    "billing setup preview wave",
  );
  if (snapshotToken !== expectedSnapshotToken || wave !== expectedWave)
    invalid("billing setup preview selection proof");
  if (
    row.read_only !== true ||
    row.requires_sequential_execution !== true ||
    row.requires_canonical_refresh_after_each_intent !== true
  )
    invalid("billing setup preview safety boundary");
  const intents = array(
    row.intents,
    "billing setup preview intents",
    100,
  ).map(parsePreviewIntent);
  const blocked = array(
    row.blocked,
    "billing setup preview blocks",
    100,
  ).map((value) => {
    const block = exact(
      value,
      ["group_id", "code", "message"],
      "billing setup preview block",
    );
    return {
      group_id: sha256(
        block.group_id,
        "billing setup blocked group id",
      ),
      code: text(block.code, "billing setup block code", 80),
      message: text(block.message, "billing setup block message", 255),
    };
  });
  const outcomes = [
    ...intents.map((intent) => intent.group_id),
    ...blocked.map((block) => block.group_id),
  ];
  if (
    !outcomes.length ||
    new Set(outcomes).size !== outcomes.length ||
    intents.some((intent, index) => intent.sequence !== index + 1) ||
    new Set(intents.map((intent) => intent.client_operation_id)).size !==
      intents.length
  )
    invalid("billing setup preview ordering proof");
  return {
    schema_version: "billing-readiness-batch-preview-v1",
    organization_id: actualOrganizationId,
    snapshot_token: snapshotToken,
    wave,
    previewed_at: timestamp(
      row.previewed_at,
      "billing setup preview time",
    ),
    data_through_realtime_sequence: integer(
      row.data_through_realtime_sequence,
      "billing setup preview realtime sequence",
    ),
    read_only: true,
    apply_available: boolean(
      row.apply_available,
      "billing setup preview apply availability",
    ),
    manual_activation_required: boolean(
      row.manual_activation_required,
      "billing setup preview activation requirement",
    ),
    requires_sequential_execution: true,
    requires_canonical_refresh_after_each_intent: true,
    intents,
    blocked,
  };
}

async function request<T>(
  organizationId: string,
  run: () => Promise<T>,
): Promise<T> {
  if (
    !organizationId ||
    getSelectedOrganizationId() !== organizationId
  )
    throw new BillingApiError(
      "The billing setup plan does not match the selected organization.",
    );
  try {
    return await run();
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

export async function fetchBillingBatchPlan(
  organizationId: string,
  input: FetchBillingBatchPlanInput,
  signal?: AbortSignal,
): Promise<BillingBatchPlan> {
  const queryText = input.query?.trim() ?? "";
  if (queryText.length > 80)
    throw new BillingApiError(
      "Billing setup search is limited to 80 characters.",
    );
  const limit = input.limit ?? 25;
  const offset = input.offset ?? 0;
  if (
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    !Number.isInteger(offset) ||
    offset < 0 ||
    offset > 10_000
  )
    throw new BillingApiError("The billing setup page request is invalid.");
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (input.wave !== "all") query.set("wave", input.wave);
  if (input.status) query.set("status", input.status);
  if (queryText) query.set("query", queryText);
  if (input.snapshotToken) {
    if (!SHA256.test(input.snapshotToken))
      throw new BillingApiError("The billing setup snapshot is invalid.");
    query.set("snapshot_token", input.snapshotToken);
  }
  return request(organizationId, async () =>
    parseBillingBatchPlan(
      await apiRequest<unknown>(
        `/billing/readiness/batch-plan?${query.toString()}`,
        { signal },
      ),
      organizationId,
    ),
  );
}

export async function previewBillingBatchWave(
  organizationId: string,
  snapshotToken: string,
  wave: BillingBatchActionableWave,
  selections: BillingBatchPreviewSelection[],
  signal?: AbortSignal,
): Promise<BillingBatchPreview> {
  if (
    !SHA256.test(snapshotToken) ||
    !BILLING_BATCH_ACTIONABLE_WAVES.includes(wave) ||
    !selections.length ||
    selections.length > 100
  )
    throw new BillingApiError("The billing setup preview request is invalid.");
  return request(organizationId, async () =>
    parseBillingBatchPreview(
      await apiRequest<unknown>("/billing/readiness/batch-plan/preview", {
        method: "POST",
        signal,
        body: JSON.stringify({
          snapshot_token: snapshotToken,
          wave,
          selections,
        }),
      }),
      organizationId,
      snapshotToken,
      wave,
    ),
  );
}

export function billingBatchReceiptCommandType(
  commandType: BillingBatchCommandType,
): BillingCommandReceipt["command_type"] {
  return commandType;
}
