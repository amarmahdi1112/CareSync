import { describe, expect, it } from "vitest";
import {
  BillingInvoiceDraftError,
  resolveBillingInvoiceDraftAgreements,
  validateBillingInvoiceDraftDates,
} from "./billingInvoiceDraft";
import type {
  BillingAgreement,
  BillingAgreementVersion,
  BillingRatePlan,
  BillingRatePlanVersion,
} from "./types";

const agreementVersion = (
  id: string,
  versionNumber: number,
  effectiveFrom: string,
  effectiveUntil: string | null,
  rateVersionId: string,
): BillingAgreementVersion =>
  ({
    id,
    version_number: versionNumber,
    effective_from: effectiveFrom,
    effective_until: effectiveUntil,
    rate_plan_version_id: rateVersionId,
  }) as BillingAgreementVersion;

const rateVersion = (
  id: string,
  versionNumber: number,
  effectiveFrom: string,
  effectiveUntil: string | null,
): BillingRatePlanVersion =>
  ({
    id,
    version_number: versionNumber,
    effective_from: effectiveFrom,
    effective_until: effectiveUntil,
  }) as BillingRatePlanVersion;

function fixture(options?: {
  agreementVersions?: BillingAgreementVersion[];
  rateVersions?: BillingRatePlanVersion[];
}) {
  const agreementV1 = agreementVersion(
    "agreement-v1",
    1,
    "2026-01-01",
    null,
    "rate-v1",
  );
  const agreementV2 = agreementVersion(
    "agreement-v2",
    2,
    "2026-08-01",
    null,
    "rate-v2",
  );
  const rateV1 = rateVersion("rate-v1", 1, "2026-01-01", null);
  const rateV2 = rateVersion("rate-v2", 2, "2026-08-01", null);
  const versions = options?.agreementVersions || [agreementV1, agreementV2];
  const rates = options?.rateVersions || [rateV1, rateV2];
  const agreement = {
    id: "agreement",
    child_name: "Avery Synthetic",
    latest_version: versions[versions.length - 1],
    versions,
  } as BillingAgreement;
  const ratePlan = {
    id: "rate-plan",
    name: "Monthly care",
    latest_version: rates[rates.length - 1],
    versions: rates,
  } as BillingRatePlan;
  return { agreement, ratePlan, agreementV1, agreementV2, rateV1, rateV2 };
}

function caughtCode(run: () => unknown): string | null {
  try {
    run();
    return null;
  } catch (caught) {
    return caught instanceof BillingInvoiceDraftError ? caught.code : null;
  }
}

describe("manual invoice draft effective-version resolution", () => {
  it("preserves historical agreement and rate v1 after v2 is published", () => {
    const { agreement, ratePlan } = fixture();
    const [resolved] = resolveBillingInvoiceDraftAgreements(
      [agreement],
      [ratePlan],
      { start: "2026-07-01", end: "2026-07-31" },
    );
    expect(resolved.agreementVersion.id).toBe("agreement-v1");
    expect(resolved.rateVersion.id).toBe("rate-v1");
    expect(resolved.selection).toEqual({
      agreement_id: "agreement",
      agreement_version_id: "agreement-v1",
    });
  });

  it("selects v2 on its exact inclusive start boundary", () => {
    const { agreement, ratePlan } = fixture();
    const [resolved] = resolveBillingInvoiceDraftAgreements(
      [agreement],
      [ratePlan],
      { start: "2026-08-01", end: "2026-08-31" },
    );
    expect(resolved.agreementVersion.id).toBe("agreement-v2");
    expect(resolved.rateVersion.id).toBe("rate-v2");
  });

  it("rejects a service period that spans an agreement revision", () => {
    const { agreement, ratePlan } = fixture();
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements([agreement], [ratePlan], {
          start: "2026-07-15",
          end: "2026-08-14",
        }),
      ),
    ).toBe("agreement_version_boundary");
  });

  it("rejects explicit agreement gaps and overlaps distinctly", () => {
    const gap = fixture({
      agreementVersions: [
        agreementVersion(
          "agreement-v1",
          1,
          "2026-01-01",
          "2026-07-15",
          "rate-v1",
        ),
        agreementVersion(
          "agreement-v2",
          2,
          "2026-08-01",
          null,
          "rate-v2",
        ),
      ],
    });
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements(
          [gap.agreement],
          [gap.ratePlan],
          { start: "2026-07-01", end: "2026-07-31" },
        ),
      ),
    ).toBe("agreement_version_gap");

    const overlap = fixture({
      agreementVersions: [
        agreementVersion(
          "agreement-v1",
          1,
          "2026-01-01",
          "2026-08-15",
          "rate-v1",
        ),
        agreementVersion(
          "agreement-v2",
          2,
          "2026-08-01",
          null,
          "rate-v2",
        ),
      ],
    });
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements(
          [overlap.agreement],
          [overlap.ratePlan],
          { start: "2026-08-01", end: "2026-08-31" },
        ),
      ),
    ).toBe("agreement_version_overlap");
  });

  it("rejects rate gaps, overlaps, and revision-spanning periods distinctly", () => {
    const agreement = {
      ...fixture().agreement,
      latest_version: agreementVersion(
        "agreement-only",
        1,
        "2026-01-01",
        null,
        "rate-v1",
      ),
      versions: [
        agreementVersion(
          "agreement-only",
          1,
          "2026-01-01",
          null,
          "rate-v1",
        ),
      ],
    } as BillingAgreement;
    const gap = fixture({
      rateVersions: [
        rateVersion("rate-v1", 1, "2026-01-01", "2026-07-15"),
        rateVersion("rate-v2", 2, "2026-08-01", null),
      ],
    }).ratePlan;
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements([agreement], [gap], {
          start: "2026-07-01",
          end: "2026-07-31",
        }),
      ),
    ).toBe("rate_version_gap");

    const overlap = fixture({
      rateVersions: [
        rateVersion("rate-v1", 1, "2026-01-01", "2026-08-15"),
        rateVersion("rate-v2", 2, "2026-08-01", null),
      ],
    }).ratePlan;
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements([agreement], [overlap], {
          start: "2026-08-01",
          end: "2026-08-31",
        }),
      ),
    ).toBe("rate_version_overlap");

    const boundary = fixture().ratePlan;
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements([agreement], [boundary], {
          start: "2026-07-15",
          end: "2026-08-14",
        }),
      ),
    ).toBe("rate_version_boundary");
  });

  it("rejects an agreement whose pinned rate is not the effective rate", () => {
    const { ratePlan } = fixture();
    const staleAgreement = {
      ...fixture().agreement,
      latest_version: agreementVersion(
        "agreement-only",
        1,
        "2026-01-01",
        null,
        "rate-v1",
      ),
      versions: [
        agreementVersion(
          "agreement-only",
          1,
          "2026-01-01",
          null,
          "rate-v1",
        ),
      ],
    } as BillingAgreement;
    expect(
      caughtCode(() =>
        resolveBillingInvoiceDraftAgreements(
          [staleAgreement],
          [ratePlan],
          { start: "2026-08-01", end: "2026-08-31" },
        ),
      ),
    ).toBe("rate_version_mismatch");
  });
});

describe("manual invoice draft dates", () => {
  it("accepts organization-local today and a same-day or later due date", () => {
    expect(
      validateBillingInvoiceDraftDates({
        issueDate: "2026-07-22",
        dueDate: "2026-07-22",
        organizationLocalToday: "2026-07-22",
      }),
    ).toEqual({ issueDate: "2026-07-22", dueDate: "2026-07-22" });
    expect(() =>
      validateBillingInvoiceDraftDates({
        issueDate: "2026-07-22",
        dueDate: "2026-08-15",
        organizationLocalToday: "2026-07-22",
      }),
    ).not.toThrow();
  });

  it("rejects a stale issue date and an earlier due date distinctly", () => {
    expect(
      caughtCode(() =>
        validateBillingInvoiceDraftDates({
          issueDate: "2026-07-21",
          dueDate: "2026-08-15",
          organizationLocalToday: "2026-07-22",
        }),
      ),
    ).toBe("issue_date_not_today");
    expect(
      caughtCode(() =>
        validateBillingInvoiceDraftDates({
          issueDate: "2026-07-22",
          dueDate: "2026-07-21",
          organizationLocalToday: "2026-07-22",
        }),
      ),
    ).toBe("due_date_before_issue_date");
  });

  it("rejects invalid invoice dates before comparing them", () => {
    expect(
      caughtCode(() =>
        validateBillingInvoiceDraftDates({
          issueDate: "2026-02-30",
          dueDate: "2026-03-01",
          organizationLocalToday: "2026-02-28",
        }),
      ),
    ).toBe("invoice_date_invalid");
  });
});
