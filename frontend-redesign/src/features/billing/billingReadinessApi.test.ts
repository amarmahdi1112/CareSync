import { describe, expect, it } from "vitest";
import {
  parseBillingReadiness,
  parseFamilyFinanceSummary,
} from "./billingReadinessApi";

const organizationId = "11111111-1111-4111-8111-111111111111";
const otherOrganizationId = "12121212-1212-4212-8212-121212121212";
const familyId = "22222222-2222-4222-8222-222222222222";
const childId = "33333333-3333-4333-8333-333333333333";
const historicalChildId = "34343434-3434-4434-8434-343434343434";
const enrollmentId = "44444444-4444-4444-8444-444444444444";
const facilityId = "55555555-5555-4555-8555-555555555555";
const programId = "66666666-6666-4666-8666-666666666666";
const accountId = "77777777-7777-4777-8777-777777777777";
const guardianId = "88888888-8888-4888-8888-888888888888";
const ratePlanId = "99999999-9999-4999-8999-999999999999";
const ratePlanVersionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const agreementId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const agreementVersionId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

function readinessItem(overrides: Record<string, unknown> = {}) {
  return {
    family_id: familyId,
    family_name: "Example family",
    child_id: childId,
    child_name: "Example Child",
    enrollment_id: enrollmentId,
    facility_id: facilityId,
    program_id: programId,
    billing_account_id: accountId,
    payer_guardian_id: guardianId,
    rate_plan_id: ratePlanId,
    rate_plan_version_id: ratePlanVersionId,
    agreement_id: agreementId,
    agreement_version_id: agreementVersionId,
    status: "setup_ready",
    reason_codes: ["billing_setup_ready"],
    action_path: `/billing?view=invoices&account=${accountId}`,
    ...overrides,
  };
}

function readinessResponse(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "billing-projection-v1",
    organization_id: organizationId,
    generated_at: "2026-07-22T18:30:00Z",
    as_of_date: "2026-07-22",
    data_through_realtime_sequence: 42,
    currency: "CAD",
    counts: {
      total: 1,
      setup_ready: 1,
      needs_account: 0,
      needs_payer: 0,
      needs_current_enrollment: 0,
      needs_rate_plan: 0,
      needs_agreement: 0,
      agreement_scope_conflict: 0,
      needs_review: 0,
    },
    items: [readinessItem()],
    ...overrides,
  };
}

function childSummary(overrides: Record<string, unknown> = {}) {
  return {
    child_id: childId,
    child_name: "Example Child",
    is_active: true,
    current_enrollment_id: enrollmentId,
    readiness_status: "setup_ready",
    charge_attribution: {
      invoice_count: 1,
      line_count: 1,
      gross_minor: 10_000,
      funding_minor: 0,
      subtotal_minor: 10_000,
      tax_minor: 0,
      total_minor: 10_000,
    },
    ...overrides,
  };
}

function familySummary(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "billing-projection-v1",
    organization_id: organizationId,
    generated_at: "2026-07-22T18:30:00+00:00",
    as_of_date: "2026-07-22",
    data_through_realtime_sequence: 42,
    currency: "CAD",
    family: { id: familyId, name: "Example family", status: "active" },
    account: {
      id: accountId,
      account_number: "BA-2026-0001",
      status: "open",
      payer_guardian_id: guardianId,
      payer_name: "Example Guardian",
    },
    invoice_summary: {
      invoice_count: 1,
      open_invoice_count: 1,
      settled_invoice_count: 0,
      total_minor: 10_000,
      allocated_minor: 2_000,
      credits_minor: 1_000,
      outstanding_minor: 7_000,
    },
    payment_summary: {
      payment_count: 1,
      recorded_minor: 3_000,
      allocated_minor: 2_000,
      unapplied_minor: 1_000,
    },
    children: [childSummary()],
    ...overrides,
  };
}

describe("billing readiness projection parser", () => {
  it("accepts an exact, reconciled readiness projection", () => {
    const parsed = parseBillingReadiness(
      readinessResponse(),
      organizationId,
    );
    expect(parsed.counts).toMatchObject({ total: 1, setup_ready: 1 });
    expect(parsed.items[0]).toMatchObject({
      child_id: childId,
      status: "setup_ready",
      action_path: `/billing?view=invoices&account=${accountId}`,
    });
  });

  it("accepts the exact child-enrollment remediation destination", () => {
    const item = readinessItem({
      status: "needs_current_enrollment",
      enrollment_id: null,
      facility_id: null,
      program_id: null,
      rate_plan_id: null,
      rate_plan_version_id: null,
      agreement_id: null,
      agreement_version_id: null,
      reason_codes: ["current_enrollment_missing"],
      action_path: `/children/${childId}?section=enrollment`,
    });
    const response = readinessResponse({
      items: [item],
      counts: {
        ...readinessResponse().counts,
        setup_ready: 0,
        needs_current_enrollment: 1,
      },
    });
    expect(parseBillingReadiness(response, organizationId).items[0]?.status).toBe(
      "needs_current_enrollment",
    );
  });

  it("keeps a non-active family visible with an exact status-review destination", () => {
    const item = readinessItem({
      status: "needs_review",
      enrollment_id: null,
      facility_id: null,
      program_id: null,
      rate_plan_id: null,
      rate_plan_version_id: null,
      agreement_id: null,
      agreement_version_id: null,
      reason_codes: ["billing_family_not_active"],
      action_path: `/families/${familyId}?focus=family-status`,
    });
    const response = readinessResponse({
      items: [item],
      counts: {
        ...readinessResponse().counts,
        setup_ready: 0,
        needs_review: 1,
      },
    });
    expect(parseBillingReadiness(response, organizationId).items[0]).toMatchObject({
      family_id: familyId,
      status: "needs_review",
      action_path: `/families/${familyId}?focus=family-status`,
    });
  });

  it("rejects crossed organizations, unsupported fields, and unsafe actions", () => {
    expect(() =>
      parseBillingReadiness(
        readinessResponse({ organization_id: otherOrganizationId }),
        organizationId,
      ),
    ).toThrow("organization boundary");

    expect(() =>
      parseBillingReadiness(
        readinessResponse({ unexpected: true }),
        organizationId,
      ),
    ).toThrow("shape");

    expect(() =>
      parseBillingReadiness(
        readinessResponse({
          items: [
            readinessItem({
              action_path: "https://example.test/billing?view=invoices",
            }),
          ],
        }),
        organizationId,
      ),
    ).toThrow("action path");
  });

  it("binds actions to the exact child or account and reconciles status counts", () => {
    expect(() =>
      parseBillingReadiness(
        readinessResponse({
          items: [
            readinessItem({
              action_path:
                "/billing?view=invoices&account=dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            }),
          ],
        }),
        organizationId,
      ),
    ).toThrow("action path");

    expect(() =>
      parseBillingReadiness(
        readinessResponse({
          counts: { ...readinessResponse().counts, setup_ready: 0 },
        }),
        organizationId,
      ),
    ).toThrow("count reconciliation");
  });

  it("rejects partial version identities and duplicate reason codes", () => {
    expect(() =>
      parseBillingReadiness(
        readinessResponse({
          items: [readinessItem({ rate_plan_version_id: null })],
        }),
        organizationId,
      ),
    ).toThrow("rate plan identity");

    expect(() =>
      parseBillingReadiness(
        readinessResponse({
          items: [
            readinessItem({
              reason_codes: ["billing_setup_ready", "billing_setup_ready"],
            }),
          ],
        }),
        organizationId,
      ),
    ).toThrow("duplicate");
  });
});

describe("family finance summary parser", () => {
  it("keeps settlement at family level and exposes child charge attribution", () => {
    const parsed = parseFamilyFinanceSummary(
      familySummary(),
      organizationId,
      familyId,
    );
    expect(parsed.invoice_summary).toMatchObject({
      total_minor: 10_000,
      outstanding_minor: 7_000,
    });
    expect(parsed.children[0]?.charge_attribution.total_minor).toBe(10_000);
    expect(parsed.children[0]).not.toHaveProperty("outstanding_minor");
    expect(parsed.children[0]).not.toHaveProperty("paid_minor");
  });

  it("preserves historical charge attribution without inventing readiness", () => {
    const historical = childSummary({
      child_id: historicalChildId,
      child_name: "Historical Child",
      is_active: false,
      current_enrollment_id: null,
      readiness_status: null,
      charge_attribution: {
        invoice_count: 0,
        line_count: 0,
        gross_minor: 0,
        funding_minor: 0,
        subtotal_minor: 0,
        tax_minor: 0,
        total_minor: 0,
      },
    });
    const parsed = parseFamilyFinanceSummary(
      familySummary({ children: [childSummary(), historical] }),
      organizationId,
      familyId,
    );
    expect(parsed.children[1]).toMatchObject({
      is_active: false,
      readiness_status: null,
    });
  });

  it("accepts a family with no billing account and zero ledger totals", () => {
    const zero = familySummary({
      account: null,
      invoice_summary: {
        invoice_count: 0,
        open_invoice_count: 0,
        settled_invoice_count: 0,
        total_minor: 0,
        allocated_minor: 0,
        credits_minor: 0,
        outstanding_minor: 0,
      },
      payment_summary: {
        payment_count: 0,
        recorded_minor: 0,
        allocated_minor: 0,
        unapplied_minor: 0,
      },
      children: [
        childSummary({
          readiness_status: "needs_account",
          charge_attribution: {
            invoice_count: 0,
            line_count: 0,
            gross_minor: 0,
            funding_minor: 0,
            subtotal_minor: 0,
            tax_minor: 0,
            total_minor: 0,
          },
        }),
      ],
    });
    expect(
      parseFamilyFinanceSummary(zero, organizationId, familyId).account,
    ).toBeNull();
  });

  it("rejects child settlement claims and unreconciled family money", () => {
    const childWithSettlement = childSummary({
      outstanding_minor: 7_000,
    });
    expect(() =>
      parseFamilyFinanceSummary(
        familySummary({ children: [childWithSettlement] }),
        organizationId,
        familyId,
      ),
    ).toThrow("shape");

    expect(() =>
      parseFamilyFinanceSummary(
        familySummary({
          invoice_summary: {
            ...familySummary().invoice_summary,
            outstanding_minor: 7_001,
          },
        }),
        organizationId,
        familyId,
      ),
    ).toThrow("reconciliation");
  });

  it("rejects a family boundary mismatch and child totals that do not roll up", () => {
    expect(() =>
      parseFamilyFinanceSummary(
        familySummary({
          family: {
            id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            name: "Crossed family",
            status: "active",
          },
        }),
        organizationId,
        familyId,
      ),
    ).toThrow("family boundary");

    expect(() =>
      parseFamilyFinanceSummary(
        familySummary({
          children: [
            childSummary({
              charge_attribution: {
                invoice_count: 1,
                line_count: 1,
                gross_minor: 9_000,
                funding_minor: 0,
                subtotal_minor: 9_000,
                tax_minor: 0,
                total_minor: 9_000,
              },
            }),
          ],
        }),
        organizationId,
        familyId,
      ),
    ).toThrow("charge attribution reconciliation");
  });
});
