import { describe, expect, it } from "vitest";
import {
  addDateOnlyDays,
  billingPeriodForFrequency,
  organizationDateTimeLocal,
  organizationLocalDateTimeToIso,
  parseMoneyInput,
  previewCreditResult,
  previewInvoiceFromAgreements,
  resolveBillingAccountPayer,
  validateInvoiceAgreementServicePeriod,
} from "./billingModel";
import type {
  BillingAccountPayerVersion,
  BillingAccountSummary,
  BillingAgreement,
  BillingFamilyOption,
  BillingInvoice,
  BillingRatePlan,
} from "./types";

describe("billing money and organization clock", () => {
  it("accepts exact CAD minor-unit inputs and rejects ambiguous decimals", () => {
    expect(parseMoneyInput("123.45")).toBe(12_345);
    expect(parseMoneyInput("0", { allowZero: true })).toBe(0);
    expect(() => parseMoneyInput("1.005")).toThrow(/two decimal/i);
    expect(() => parseMoneyInput("01.00")).toThrow(/non-negative/i);
    expect(() => parseMoneyInput("10.01", { maximumMinor: 1_000 })).toThrow(
      /available balance/i,
    );
  });

  it("round-trips an Edmonton organization-local time without using device time", () => {
    expect(
      organizationDateTimeLocal("2026-07-22T18:30:00Z", "America/Edmonton"),
    ).toBe("2026-07-22T12:30");
    expect(
      organizationLocalDateTimeToIso("2026-07-22T12:30", "America/Edmonton"),
    ).toBe("2026-07-22T18:30:00.000Z");
  });

  it("rejects a nonexistent local time during the spring clock change", () => {
    expect(() =>
      organizationLocalDateTimeToIso("2026-03-08T02:30", "America/Edmonton"),
    ).toThrow(/does not exist/i);
  });
});

describe("contract period derivation", () => {
  it("derives exact inclusive weekly, biweekly, monthly, and service periods", () => {
    expect(billingPeriodForFrequency("weekly", "2026-07-22")).toEqual({
      start: "2026-07-22",
      end: "2026-07-28",
    });
    expect(billingPeriodForFrequency("biweekly", "2026-07-22")).toEqual({
      start: "2026-07-22",
      end: "2026-08-04",
    });
    expect(billingPeriodForFrequency("monthly", "2028-02-19")).toEqual({
      start: "2028-02-01",
      end: "2028-02-29",
    });
    expect(billingPeriodForFrequency("per_service", "2026-07-22")).toEqual({
      start: "2026-07-22",
      end: "2026-07-22",
    });
    expect(addDateOnlyDays("2026-12-31", 1)).toBe("2027-01-01");
  });
});

describe("current account payer resolution", () => {
  const account = {
    id: "account-1",
    family_id: "family-1",
    payer_guardian_id: "guardian-2",
    latest_payer_version_id: "payer-version-2",
    latest_payer_version_number: 2,
  } as BillingAccountSummary;
  const assignment = {
    id: "payer-version-2",
    billing_account_id: "account-1",
    family_id: "family-1",
    payer_guardian_id: "guardian-2",
    version_number: 2,
  } as BillingAccountPayerVersion;
  const family = {
    id: "family-1",
    guardians: [
      {
        id: "guardian-2",
        family_id: "family-1",
        name: "Current Payer",
        email: "payer@example.test",
        cell_phone: "+1 403 555 0102",
      },
    ],
  } as BillingFamilyOption;

  it("resolves the guardian only through the exact current assignment chain", () => {
    expect(resolveBillingAccountPayer(account, [family], [assignment])).toEqual({
      status: "resolved",
      guardian: family.guardians[0],
      assignment,
    });
  });

  it("fails safely instead of borrowing an unrelated or stale guardian", () => {
    const missingGuardian = resolveBillingAccountPayer(
      account,
      [{ ...family, guardians: [] }],
      [assignment],
    );
    expect(missingGuardian).toEqual({
      status: "unavailable",
      guardian: null,
      assignment,
    });

    const crossedAssignment = resolveBillingAccountPayer(
      account,
      [family],
      [{ ...assignment, family_id: "another-family" }],
    );
    expect(crossedAssignment).toEqual({
      status: "unavailable",
      guardian: null,
      assignment: null,
    });
  });
});

describe("financial impact previews", () => {
  const agreement = {
    id: "agreement-1",
    child_name: "Example Child",
    latest_version: {
      id: "agreement-version-1",
      rate_plan_version_id: "rate-version-1",
      family_amount_minor_per_unit: 32_625,
      funding_amount_minor_per_unit: 7_375,
      effective_from: "2026-07-01",
      effective_until: null,
    },
  } as BillingAgreement;
  const ratePlan = {
    name: "Monthly daycare",
    versions: [
      {
        id: "rate-version-1",
        billing_unit: "monthly_period",
        unit_amount_minor: 40_000,
        tax_rate_basis_points: 0,
        effective_from: "2026-07-01",
        effective_until: null,
      },
    ],
  } as BillingRatePlan;
  const servicePeriod = { start: "2026-07-01", end: "2026-07-31" };

  it("derives line and invoice totals from one coherent agreement/rate snapshot", () => {
    expect(
      previewInvoiceFromAgreements([agreement], [ratePlan], servicePeriod),
    ).toMatchObject({
      grossMinor: 40_000,
      fundingMinor: 7_375,
      familyMinor: 32_625,
      taxMinor: 0,
      totalMinor: 32_625,
      lines: [
        {
          childName: "Example Child",
          ratePlanName: "Monthly daycare",
          agreementVersionId: "agreement-version-1",
          ratePlanVersionId: "rate-version-1",
          totalMinor: 32_625,
        },
      ],
    });
  });

  it("rejects an unprovable or unreconciled preview instead of estimating", () => {
    expect(() =>
      previewInvoiceFromAgreements([agreement], [], servicePeriod),
    ).toThrow(/cannot prove the pinned rate version/i);
    expect(() =>
      previewInvoiceFromAgreements(
        [agreement],
        [
          {
            ...ratePlan,
            versions: [{ ...ratePlan.versions[0], unit_amount_minor: 40_001 }],
          } as BillingRatePlan,
        ],
        servicePeriod,
      ),
    ).toThrow(/do not reconcile/i);
  });

  it("blocks review when the agreement begins after or ends before the service period", () => {
    const startsLate = {
      ...agreement,
      latest_version: {
        ...agreement.latest_version,
        effective_from: "2026-07-15",
      },
    } as BillingAgreement;
    expect(
      validateInvoiceAgreementServicePeriod(
        [startsLate],
        [ratePlan],
        servicePeriod,
      ),
    ).toMatch(/Example Child's reviewed agreement.*does not cover.*Jul 15, 2026 onward/i);

    const endsEarly = {
      ...agreement,
      latest_version: {
        ...agreement.latest_version,
        effective_until: "2026-07-30",
      },
    } as BillingAgreement;
    expect(() =>
      previewInvoiceFromAgreements([endsEarly], [ratePlan], servicePeriod),
    ).toThrow(/agreement does not cover.*Jul 1, 2026.*Jul 31, 2026/i);
  });

  it("blocks review when the exact pinned rate version does not cover the full period", () => {
    const startsLate = {
      ...ratePlan,
      versions: [
        { ...ratePlan.versions[0], effective_from: "2026-07-02" },
      ],
    } as BillingRatePlan;
    expect(() =>
      previewInvoiceFromAgreements([agreement], [startsLate], servicePeriod),
    ).toThrow(/pinned rate version.*does not cover.*Jul 2, 2026 onward/i);

    const endsEarly = {
      ...ratePlan,
      versions: [
        { ...ratePlan.versions[0], effective_until: "2026-07-30" },
      ],
    } as BillingRatePlan;
    expect(
      validateInvoiceAgreementServicePeriod(
        [agreement],
        [endsEarly],
        servicePeriod,
      ),
    ).toMatch(/pinned rate version.*does not cover.*Jul 30, 2026/i);
  });

  it("accepts exact inclusive agreement and rate coverage boundaries", () => {
    const boundedAgreement = {
      ...agreement,
      latest_version: {
        ...agreement.latest_version,
        effective_until: servicePeriod.end,
      },
    } as BillingAgreement;
    const boundedRate = {
      ...ratePlan,
      versions: [
        { ...ratePlan.versions[0], effective_until: servicePeriod.end },
      ],
    } as BillingRatePlan;
    expect(
      validateInvoiceAgreementServicePeriod(
        [boundedAgreement],
        [boundedRate],
        servicePeriod,
      ),
    ).toBeNull();
  });

  it("previews the exact resulting credit balance and rejects excess credit", () => {
    const invoice = { outstanding_minor: 12_000 } as BillingInvoice;
    expect(previewCreditResult(invoice, parseMoneyInput("25.00"))).toBe(9_500);
    expect(() =>
      previewCreditResult(invoice, parseMoneyInput("120.01")),
    ).toThrow(/within the current outstanding/i);
  });
});
