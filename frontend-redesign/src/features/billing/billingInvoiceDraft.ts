import type {
  BillingAgreement,
  BillingAgreementVersion,
  BillingRatePlan,
  BillingRatePlanVersion,
} from "./types";

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

export interface BillingInvoiceDraftPeriod {
  start: string;
  end: string;
}

export type BillingInvoiceDraftErrorCode =
  | "invalid_service_period"
  | "invoice_date_invalid"
  | "organization_date_invalid"
  | "issue_date_not_today"
  | "due_date_before_issue_date"
  | "agreement_version_invalid"
  | "agreement_version_gap"
  | "agreement_version_overlap"
  | "agreement_version_boundary"
  | "rate_version_invalid"
  | "rate_version_missing"
  | "rate_version_gap"
  | "rate_version_overlap"
  | "rate_version_boundary"
  | "rate_version_mismatch";

export class BillingInvoiceDraftError extends Error {
  constructor(
    public readonly code: BillingInvoiceDraftErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "BillingInvoiceDraftError";
  }
}

export interface ResolvedBillingInvoiceDraftAgreement {
  agreement: BillingAgreement;
  agreementVersion: BillingAgreementVersion;
  ratePlan: BillingRatePlan;
  rateVersion: BillingRatePlanVersion;
  selection: {
    agreement_id: string;
    agreement_version_id: string;
  };
}

interface EffectiveVersion {
  id: string;
  version_number: number;
  effective_from: string;
  effective_until: string | null;
}

interface NormalizedVersion<T extends EffectiveVersion> {
  version: T;
  startDay: number;
  endDay: number | null;
}

function dateOnlyDay(value: string): number | null {
  if (!DATE_ONLY.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const timestamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  )
    return null;
  return timestamp / DAY_MS;
}

function dateOnlyFromDay(day: number): string {
  return new Date(day * DAY_MS).toISOString().slice(0, 10);
}

function intersects(
  leftStart: number,
  leftEnd: number | null,
  rightStart: number,
  rightEnd: number,
): boolean {
  return leftStart <= rightEnd && (leftEnd == null || leftEnd >= rightStart);
}

function periodDays(period: BillingInvoiceDraftPeriod): {
  startDay: number;
  endDay: number;
} {
  const startDay = dateOnlyDay(period.start);
  const endDay = dateOnlyDay(period.end);
  if (startDay == null || endDay == null || startDay > endDay)
    throw new BillingInvoiceDraftError(
      "invalid_service_period",
      "Choose a valid inclusive service period whose end is not before its start.",
    );
  return { startDay, endDay };
}

function timelineNoun(kind: "agreement" | "rate"): string {
  return kind === "agreement" ? "reviewed agreement" : "published rate";
}

function timelineErrorCode(
  kind: "agreement" | "rate",
  problem: "invalid" | "gap" | "overlap" | "boundary",
): BillingInvoiceDraftErrorCode {
  return `${kind}_version_${problem}` as BillingInvoiceDraftErrorCode;
}

/**
 * Resolves one immutable version under append-only effective-date semantics.
 *
 * An older open-ended version is implicitly superseded on the day before the
 * next version begins. An explicit end date is not silently rewritten: gaps
 * and explicit overlaps remain blocking data-quality problems.
 */
function resolveTimelineVersion<T extends EffectiveVersion>(
  versions: readonly T[],
  period: BillingInvoiceDraftPeriod,
  kind: "agreement" | "rate",
  subject: string,
): T {
  const { startDay, endDay } = periodDays(period);
  const noun = timelineNoun(kind);
  const sorted = versions
    .map((version) => {
      const versionStart = dateOnlyDay(version.effective_from);
      const versionEnd =
        version.effective_until == null
          ? null
          : dateOnlyDay(version.effective_until);
      if (
        versionStart == null ||
        (version.effective_until != null && versionEnd == null) ||
        (versionEnd != null && versionEnd < versionStart)
      )
        throw new BillingInvoiceDraftError(
          timelineErrorCode(kind, "invalid"),
          `${subject} has an invalid ${noun} version window. Correct the effective dates before issuing an invoice.`,
        );
      return { version, startDay: versionStart, explicitEndDay: versionEnd };
    })
    .sort(
      (left, right) =>
        left.startDay - right.startDay ||
        left.version.version_number - right.version.version_number,
    );

  if (!sorted.length)
    throw new BillingInvoiceDraftError(
      timelineErrorCode(kind, "gap"),
      `${subject} has no ${noun} version for ${period.start} through ${period.end}. Publish and review the missing coverage first.`,
    );

  const normalized: Array<NormalizedVersion<T>> = [];
  for (let index = 0; index < sorted.length; index += 1) {
    const current = sorted[index];
    const next = sorted[index + 1];
    if (next && current.startDay === next.startDay) {
      const duplicateIntersects =
        intersects(
          current.startDay,
          current.explicitEndDay,
          startDay,
          endDay,
        ) ||
        intersects(next.startDay, next.explicitEndDay, startDay, endDay);
      if (duplicateIntersects)
        throw new BillingInvoiceDraftError(
          timelineErrorCode(kind, "overlap"),
          `${subject} has multiple ${noun} versions beginning ${current.version.effective_from}. Resolve the overlap before issuing this period.`,
        );
    }
    if (
      next &&
      current.explicitEndDay != null &&
      current.explicitEndDay >= next.startDay &&
      intersects(
        next.startDay,
        current.explicitEndDay,
        startDay,
        endDay,
      )
    )
      throw new BillingInvoiceDraftError(
        timelineErrorCode(kind, "overlap"),
        `${subject} has overlapping ${noun} versions from ${dateOnlyFromDay(next.startDay)} through ${dateOnlyFromDay(current.explicitEndDay)}. Correct the version dates before issuing this period.`,
      );

    const implicitEndDay = next ? next.startDay - 1 : null;
    const endDayForVersion =
      current.explicitEndDay == null
        ? implicitEndDay
        : implicitEndDay == null
          ? current.explicitEndDay
          : Math.min(current.explicitEndDay, implicitEndDay);
    normalized.push({
      version: current.version,
      startDay: current.startDay,
      endDay: endDayForVersion,
    });
  }

  for (let index = 0; index < normalized.length - 1; index += 1) {
    const current = normalized[index];
    const next = normalized[index + 1];
    if (
      current.endDay != null &&
      current.endDay + 1 < next.startDay &&
      intersects(current.endDay + 1, next.startDay - 1, startDay, endDay)
    )
      throw new BillingInvoiceDraftError(
        timelineErrorCode(kind, "gap"),
        `${subject} has no ${noun} coverage from ${dateOnlyFromDay(current.endDay + 1)} through ${dateOnlyFromDay(next.startDay - 1)}. Fill that gap or choose a fully covered period.`,
      );
  }

  const startVersion = normalized.find(
    (candidate) =>
      candidate.startDay <= startDay &&
      (candidate.endDay == null || candidate.endDay >= startDay),
  );
  const endVersion = normalized.find(
    (candidate) =>
      candidate.startDay <= endDay &&
      (candidate.endDay == null || candidate.endDay >= endDay),
  );
  if (!startVersion || !endVersion)
    throw new BillingInvoiceDraftError(
      timelineErrorCode(kind, "gap"),
      `${subject} does not have continuous ${noun} coverage for ${period.start} through ${period.end}. Add the missing version or choose a covered period.`,
    );
  if (startVersion.version.id !== endVersion.version.id)
    throw new BillingInvoiceDraftError(
      timelineErrorCode(kind, "boundary"),
      `${subject}'s service period crosses a ${noun} revision boundary. Split it into separate invoices at the version change instead of combining two prices or agreements.`,
    );
  if (
    startVersion.startDay > startDay ||
    (startVersion.endDay != null && startVersion.endDay < endDay)
  )
    throw new BillingInvoiceDraftError(
      timelineErrorCode(kind, "gap"),
      `${subject} does not have continuous ${noun} coverage for ${period.start} through ${period.end}. Add the missing version or choose a covered period.`,
    );
  return startVersion.version;
}

/**
 * Resolves historical or current invoice selections without consulting
 * latest_version. The returned IDs are the exact immutable IDs to submit.
 */
export function resolveBillingInvoiceDraftAgreements(
  agreements: readonly BillingAgreement[],
  ratePlans: readonly BillingRatePlan[],
  period: BillingInvoiceDraftPeriod,
): ResolvedBillingInvoiceDraftAgreement[] {
  periodDays(period);
  return agreements.map((agreement) => {
    const subject = agreement.child_name || "This child";
    const agreementVersion = resolveTimelineVersion(
      agreement.versions,
      period,
      "agreement",
      subject,
    );
    const pinnedRateMatches = ratePlans.flatMap((ratePlan) =>
      ratePlan.versions
        .filter(
          (version) => version.id === agreementVersion.rate_plan_version_id,
        )
        .map((version) => ({ ratePlan, version })),
    );
    if (!pinnedRateMatches.length)
      throw new BillingInvoiceDraftError(
        "rate_version_missing",
        `${subject}'s agreement pins a rate version that is missing from the coherent workspace. Refresh before issuing the invoice.`,
      );
    if (pinnedRateMatches.length > 1)
      throw new BillingInvoiceDraftError(
        "rate_version_overlap",
        `${subject}'s pinned rate version appears more than once. Refresh the workspace and resolve the duplicate before issuing.`,
      );
    const { ratePlan, version: pinnedRateVersion } = pinnedRateMatches[0];
    const effectiveRateVersion = resolveTimelineVersion(
      ratePlan.versions,
      period,
      "rate",
      `${subject} · ${ratePlan.name}`,
    );
    if (effectiveRateVersion.id !== pinnedRateVersion.id)
      throw new BillingInvoiceDraftError(
        "rate_version_mismatch",
        `${subject}'s effective agreement pins rate v${pinnedRateVersion.version_number}, but rate v${effectiveRateVersion.version_number} applies to this service period. Publish the matching reviewed agreement revision first.`,
      );
    return {
      agreement,
      agreementVersion,
      ratePlan,
      rateVersion: effectiveRateVersion,
      selection: {
        agreement_id: agreement.id,
        agreement_version_id: agreementVersion.id,
      },
    };
  });
}

export function validateBillingInvoiceDraftDates(input: {
  issueDate: string;
  dueDate: string;
  organizationLocalToday: string;
}): { issueDate: string; dueDate: string } {
  const organizationToday = dateOnlyDay(input.organizationLocalToday);
  if (organizationToday == null)
    throw new BillingInvoiceDraftError(
      "organization_date_invalid",
      "The organization-local billing date is unavailable. Refresh billing readiness before issuing.",
    );
  const issueDay = dateOnlyDay(input.issueDate);
  const dueDay = dateOnlyDay(input.dueDate);
  if (issueDay == null || dueDay == null)
    throw new BillingInvoiceDraftError(
      "invoice_date_invalid",
      "Choose valid issue and due dates before reviewing the invoice.",
    );
  if (issueDay !== organizationToday)
    throw new BillingInvoiceDraftError(
      "issue_date_not_today",
      `Set the issue date to the organization's current date, ${input.organizationLocalToday}, then review again.`,
    );
  if (dueDay < issueDay)
    throw new BillingInvoiceDraftError(
      "due_date_before_issue_date",
      "Set the due date on or after the issue date.",
    );
  return { issueDate: input.issueDate, dueDate: input.dueDate };
}
