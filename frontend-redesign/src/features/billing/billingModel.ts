import type {
  BillingAccountPayerVersion,
  BillingAccountSummary,
  BillingAgreement,
  BillingFamilyOption,
  BillingGuardianOption,
  BillingInvoice,
  BillingPayment,
  BillingRatePlan,
  MinorUnits,
} from "./types";

const CAD = new Intl.NumberFormat("en-CA", {
  style: "currency",
  currency: "CAD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const MONEY_INPUT = /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/;

export type ResolvedBillingAccountPayer =
  | {
      status: "resolved";
      guardian: BillingGuardianOption;
      assignment: BillingAccountPayerVersion;
    }
  | {
      status: "unavailable";
      guardian: null;
      assignment: BillingAccountPayerVersion | null;
    };

/**
 * Resolves the mutable current-account display from the same coherent source
 * snapshot as the account and payer-version chain. A missing or crossed source
 * guardian is never replaced with invoice snapshot text or another guardian.
 */
export function resolveBillingAccountPayer(
  account: BillingAccountSummary,
  families: readonly BillingFamilyOption[],
  payerVersions: readonly BillingAccountPayerVersion[],
): ResolvedBillingAccountPayer {
  const assignment =
    payerVersions.find(
      (candidate) =>
        candidate.id === account.latest_payer_version_id &&
        candidate.billing_account_id === account.id &&
        candidate.family_id === account.family_id &&
        candidate.payer_guardian_id === account.payer_guardian_id &&
        candidate.version_number === account.latest_payer_version_number,
    ) ?? null;
  const family = families.find((candidate) => candidate.id === account.family_id);
  const guardian = family?.guardians.find(
    (candidate) =>
      candidate.id === account.payer_guardian_id &&
      candidate.family_id === account.family_id,
  );
  if (!assignment || !guardian)
    return { status: "unavailable", guardian: null, assignment };
  return { status: "resolved", guardian, assignment };
}

export function asMinorUnits(value: number, label = "amount"): MinorUnits {
  if (!Number.isSafeInteger(value))
    throw new Error(`${label} must be an integer number of cents.`);
  return value as MinorUnits;
}

export function parseMoneyInput(
  value: string,
  options: { allowZero?: boolean; maximumMinor?: number } = {},
): MinorUnits {
  const normalized = value.trim();
  if (!MONEY_INPUT.test(normalized))
    throw new Error(
      "Enter a non-negative amount with no more than two decimal places.",
    );
  const [whole, fraction = ""] = normalized.split(".");
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(minor) || minor > 9_000_000_000_000)
    throw new Error("The amount is too large.");
  if (!options.allowZero && minor === 0)
    throw new Error("The amount must be greater than zero.");
  if (options.maximumMinor !== undefined && minor > options.maximumMinor)
    throw new Error("The amount is greater than the available balance.");
  return asMinorUnits(minor);
}

export interface BillingInvoicePreviewLine {
  agreementId: string;
  agreementVersionId: string;
  childName: string;
  ratePlanName: string;
  ratePlanVersionId: string;
  billingUnit: string;
  grossMinor: MinorUnits;
  fundingMinor: MinorUnits;
  familyMinor: MinorUnits;
  taxMinor: MinorUnits;
  totalMinor: MinorUnits;
}

export interface BillingInvoicePreview {
  lines: BillingInvoicePreviewLine[];
  grossMinor: MinorUnits;
  fundingMinor: MinorUnits;
  familyMinor: MinorUnits;
  taxMinor: MinorUnits;
  totalMinor: MinorUnits;
}

export interface BillingInvoiceServicePeriod {
  start: string;
  end: string;
}

function checkedMinorAdd(label: string, values: readonly number[]): MinorUnits {
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!Number.isSafeInteger(total) || total > 9_000_000_000_000)
    throw new Error(`${label} is outside the supported CAD range.`);
  return asMinorUnits(total, label);
}

function previewTaxMinor(amountMinor: number, basisPoints: number): MinorUnits {
  if (
    !Number.isSafeInteger(amountMinor) ||
    !Number.isSafeInteger(basisPoints) ||
    amountMinor < 0 ||
    basisPoints < 0
  )
    throw new Error("The coherent snapshot contains an invalid tax amount.");
  const rounded =
    (BigInt(amountMinor) * BigInt(basisPoints) + BigInt(5_000)) /
    BigInt(10_000);
  const value = Number(rounded);
  if (!Number.isSafeInteger(value) || value > 9_000_000_000_000)
    throw new Error("The invoice tax preview is outside the supported CAD range.");
  return asMinorUnits(value, "invoice tax preview");
}

function effectiveCoverageLabel(
  effectiveFrom: string,
  effectiveUntil: string | null,
): string {
  return effectiveUntil
    ? `${formatDateOnly(effectiveFrom)} through ${formatDateOnly(effectiveUntil)}`
    : `${formatDateOnly(effectiveFrom)} onward`;
}

function coversFullServicePeriod(
  effectiveFrom: string,
  effectiveUntil: string | null,
  servicePeriod: BillingInvoiceServicePeriod,
): boolean {
  return (
    effectiveFrom <= servicePeriod.start &&
    (!effectiveUntil || effectiveUntil >= servicePeriod.end)
  );
}

/**
 * Proves that every selected immutable agreement version and its exact pinned
 * rate version cover the entire requested service period. Date-only ISO values
 * compare chronologically, so this remains deterministic across device zones.
 */
export function validateInvoiceAgreementServicePeriod(
  agreements: readonly BillingAgreement[],
  ratePlans: readonly BillingRatePlan[],
  servicePeriod: BillingInvoiceServicePeriod,
): string | null {
  const periodError = validatePeriod(servicePeriod.start, servicePeriod.end);
  if (periodError) return periodError;

  for (const agreement of agreements) {
    const agreementVersion = agreement.latest_version;
    if (
      !coversFullServicePeriod(
        agreementVersion.effective_from,
        agreementVersion.effective_until,
        servicePeriod,
      )
    )
      return `${agreement.child_name}'s reviewed agreement does not cover the full ${formatDateOnly(servicePeriod.start)} – ${formatDateOnly(servicePeriod.end)} service period. It is effective ${effectiveCoverageLabel(agreementVersion.effective_from, agreementVersion.effective_until)}. Choose a fully covered period or publish the correct reviewed agreement version first.`;

    const rateVersion = ratePlans
      .flatMap((ratePlan) => ratePlan.versions)
      .find(
        (version) =>
          version.id === agreementVersion.rate_plan_version_id,
      );
    if (!rateVersion)
      return `The coherent snapshot cannot prove the pinned rate version for ${agreement.child_name}. Refresh before review.`;
    if (
      !coversFullServicePeriod(
        rateVersion.effective_from,
        rateVersion.effective_until,
        servicePeriod,
      )
    )
      return `The pinned rate version for ${agreement.child_name} does not cover the full ${formatDateOnly(servicePeriod.start)} – ${formatDateOnly(servicePeriod.end)} service period. It is effective ${effectiveCoverageLabel(rateVersion.effective_from, rateVersion.effective_until)}. Choose a fully covered period or publish the correct rate and agreement versions first.`;
  }
  return null;
}

/**
 * Builds a non-authoritative operator preview from one already-validated,
 * coherent workspace snapshot. The server still revalidates every source and
 * version and owns the immutable committed calculation.
 */
export function previewInvoiceFromAgreements(
  agreements: readonly BillingAgreement[],
  ratePlans: readonly BillingRatePlan[],
  servicePeriod: BillingInvoiceServicePeriod,
): BillingInvoicePreview {
  const eligibilityError = validateInvoiceAgreementServicePeriod(
    agreements,
    ratePlans,
    servicePeriod,
  );
  if (eligibilityError) throw new Error(eligibilityError);

  const lines = agreements.map((agreement): BillingInvoicePreviewLine => {
    const ratePlan = ratePlans.find((candidate) =>
      candidate.versions.some(
        (version) =>
          version.id === agreement.latest_version.rate_plan_version_id,
      ),
    );
    const rateVersion = ratePlan?.versions.find(
      (version) =>
        version.id === agreement.latest_version.rate_plan_version_id,
    );
    if (!ratePlan || !rateVersion)
      throw new Error(
        `The coherent snapshot cannot prove the rate version for ${agreement.child_name}. Refresh before review.`,
      );
    const familyMinor = asMinorUnits(
      agreement.latest_version.family_amount_minor_per_unit,
      "family preview amount",
    );
    const fundingMinor = asMinorUnits(
      agreement.latest_version.funding_amount_minor_per_unit,
      "funding preview amount",
    );
    const grossMinor = checkedMinorAdd("gross preview amount", [
      familyMinor,
      fundingMinor,
    ]);
    if (grossMinor !== rateVersion.unit_amount_minor)
      throw new Error(
        `The coherent snapshot rate and agreement amounts do not reconcile for ${agreement.child_name}. Refresh before review.`,
      );
    const taxMinor = previewTaxMinor(
      familyMinor,
      rateVersion.tax_rate_basis_points,
    );
    return {
      agreementId: agreement.id,
      agreementVersionId: agreement.latest_version.id,
      childName: agreement.child_name,
      ratePlanName: ratePlan.name,
      ratePlanVersionId: rateVersion.id,
      billingUnit: rateVersion.billing_unit,
      grossMinor,
      fundingMinor,
      familyMinor,
      taxMinor,
      totalMinor: checkedMinorAdd("line preview total", [
        familyMinor,
        taxMinor,
      ]),
    };
  });
  return {
    lines,
    grossMinor: checkedMinorAdd(
      "invoice gross preview",
      lines.map((line) => line.grossMinor),
    ),
    fundingMinor: checkedMinorAdd(
      "invoice funding preview",
      lines.map((line) => line.fundingMinor),
    ),
    familyMinor: checkedMinorAdd(
      "invoice family preview",
      lines.map((line) => line.familyMinor),
    ),
    taxMinor: checkedMinorAdd(
      "invoice tax preview",
      lines.map((line) => line.taxMinor),
    ),
    totalMinor: checkedMinorAdd(
      "invoice total preview",
      lines.map((line) => line.totalMinor),
    ),
  };
}

export function previewCreditResult(
  invoice: BillingInvoice,
  creditMinor: MinorUnits,
): MinorUnits {
  if (creditMinor <= 0 || creditMinor > invoice.outstanding_minor)
    throw new Error("The credit must be within the current outstanding balance.");
  return asMinorUnits(
    invoice.outstanding_minor - creditMinor,
    "resulting invoice balance",
  );
}

export function formatCadMinor(value: MinorUnits | number): string {
  return Number.isSafeInteger(value)
    ? CAD.format(value / 100)
    : "Invalid amount";
}

export function isDateOnly(value: string): boolean {
  if (!DATE_ONLY.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export function formatDateOnly(value: string | null): string {
  if (!value || !isDateOnly(value)) return value ? "Invalid date" : "Not set";
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Invalid time"
    : new Intl.DateTimeFormat("en-CA", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

export function localDateOnly(now = new Date()): string {
  return [
    now.getFullYear().toString().padStart(4, "0"),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

function zonedParts(value: Date, timeZone: string): Record<string, number> {
  const result: Record<string, number> = {};
  new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
    .formatToParts(value)
    .forEach((part) => {
      if (part.type !== "literal") result[part.type] = Number(part.value);
    });
  return result;
}

export function organizationDateTimeLocal(
  serverTime: string,
  timeZone: string,
): string {
  const instant = new Date(serverTime);
  if (Number.isNaN(instant.valueOf()))
    throw new Error("The organization clock is invalid.");
  const parts = zonedParts(instant, timeZone);
  return `${parts.year.toString().padStart(4, "0")}-${parts.month.toString().padStart(2, "0")}-${parts.day.toString().padStart(2, "0")}T${parts.hour.toString().padStart(2, "0")}:${parts.minute.toString().padStart(2, "0")}`;
}

export function organizationLocalDateTimeToIso(
  value: string,
  timeZone: string,
): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match)
    throw new Error("Choose a valid organization-local date and time.");
  const target = match.slice(1).map(Number);
  const targetUtc = Date.UTC(
    target[0],
    target[1] - 1,
    target[2],
    target[3],
    target[4],
    0,
  );
  let guess = targetUtc;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    const parts = zonedParts(new Date(guess), timeZone);
    const represented = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      0,
    );
    const delta = targetUtc - represented;
    if (delta === 0) return new Date(guess).toISOString();
    guess += delta;
  }
  const check = zonedParts(new Date(guess), timeZone);
  if (
    [check.year, check.month, check.day, check.hour, check.minute].some(
      (part, index) => part !== target[index],
    )
  )
    throw new Error(
      "That organization-local time does not exist because of a clock change. Choose another time.",
    );
  return new Date(guess).toISOString();
}

export function addDateOnlyDays(value: string, days: number): string {
  if (!isDateOnly(value))
    throw new Error("Choose a valid service-period date.");
  const instant = new Date(`${value}T00:00:00Z`);
  instant.setUTCDate(instant.getUTCDate() + days);
  return instant.toISOString().slice(0, 10);
}

export function billingPeriodForFrequency(
  frequency: "weekly" | "biweekly" | "monthly" | "per_service",
  anchor: string,
): { start: string; end: string } {
  if (!isDateOnly(anchor))
    throw new Error("Choose a valid service-period date.");
  if (frequency === "weekly")
    return { start: anchor, end: addDateOnlyDays(anchor, 6) };
  if (frequency === "biweekly")
    return { start: anchor, end: addDateOnlyDays(anchor, 13) };
  if (frequency === "per_service") return { start: anchor, end: anchor };
  const start = `${anchor.slice(0, 7)}-01`;
  const [year, month] = start.split("-").map(Number);
  const end = new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
  return { start, end };
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function sortAccountsForAction(
  accounts: readonly BillingAccountSummary[],
): BillingAccountSummary[] {
  return [...accounts].sort(
    (left, right) =>
      right.outstanding_minor - left.outstanding_minor ||
      right.unapplied_minor - left.unapplied_minor ||
      left.family_name.localeCompare(right.family_name),
  );
}

export function filterAccounts(
  accounts: readonly BillingAccountSummary[],
  search: string,
): BillingAccountSummary[] {
  const query = search.trim().toLocaleLowerCase("en-CA");
  if (!query) return [...accounts];
  return accounts.filter((account) =>
    [account.family_name, account.account_number].some((value) =>
      value.toLocaleLowerCase("en-CA").includes(query),
    ),
  );
}

export function invoiceOutstanding(invoice: BillingInvoice): boolean {
  return (
    invoice.outstanding_minor > 0 &&
    !["settled_paid", "settled_credited", "settled_mixed"].includes(
      invoice.lifecycle_status,
    )
  );
}
export function paymentAvailable(payment: BillingPayment): boolean {
  return (
    payment.unapplied_minor > 0 &&
    payment.lifecycle_status !== "fully_allocated"
  );
}

export function validatePeriod(start: string, end: string): string | null {
  if (!isDateOnly(start) || !isDateOnly(end))
    return "Choose a valid start and end date.";
  return end < start ? "The end date cannot be before the start date." : null;
}
