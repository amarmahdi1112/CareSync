import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "styled-components";
import { describe, expect, it } from "vitest";
import { workspaceTheme } from "../../styles/theme";
import BillingReadinessPanel, {
  billingReadinessActionLabel,
} from "./BillingReadinessPanel";
import ChildFinanceCard from "./ChildFinanceCard";
import FamilyFinanceCard from "./FamilyFinanceCard";
import {
  parseBillingReadiness,
  parseFamilyFinanceSummary,
} from "./billingReadinessApi";

const organizationId = "11111111-1111-4111-8111-111111111111";
const familyId = "22222222-2222-4222-8222-222222222222";
const childId = "33333333-3333-4333-8333-333333333333";
const enrollmentId = "44444444-4444-4444-8444-444444444444";
const facilityId = "55555555-5555-4555-8555-555555555555";
const programId = "66666666-6666-4666-8666-666666666666";
const accountId = "77777777-7777-4777-8777-777777777777";
const guardianId = "88888888-8888-4888-8888-888888888888";
const ratePlanId = "99999999-9999-4999-8999-999999999999";
const rateVersionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const agreementId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const agreementVersionId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

const readiness = parseBillingReadiness(
  {
    schema_version: "billing-projection-v1",
    organization_id: organizationId,
    generated_at: "2026-07-22T18:30:00Z",
    as_of_date: "2026-07-22",
    data_through_realtime_sequence: 72,
    currency: "CAD",
    counts: {
      total: 1,
      setup_ready: 0,
      needs_account: 0,
      needs_payer: 0,
      needs_current_enrollment: 0,
      needs_rate_plan: 0,
      needs_agreement: 1,
      agreement_scope_conflict: 0,
      needs_review: 0,
    },
    items: [
      {
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
        rate_plan_version_id: rateVersionId,
        agreement_id: null,
        agreement_version_id: null,
        status: "needs_agreement",
        reason_codes: ["billing_agreement_missing"],
        action_path: `/billing?view=rates&account=${accountId}`,
      },
    ],
  },
  organizationId,
);

const familySummary = parseFamilyFinanceSummary(
  {
    schema_version: "billing-projection-v1",
    organization_id: organizationId,
    generated_at: "2026-07-22T18:30:00Z",
    as_of_date: "2026-07-22",
    data_through_realtime_sequence: 72,
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
      invoice_count: 2,
      open_invoice_count: 1,
      settled_invoice_count: 1,
      total_minor: 12_500,
      allocated_minor: 5_000,
      credits_minor: 500,
      outstanding_minor: 7_000,
    },
    payment_summary: {
      payment_count: 2,
      recorded_minor: 6_000,
      allocated_minor: 5_000,
      unapplied_minor: 1_000,
    },
    children: [
      {
        child_id: childId,
        child_name: "Example Child",
        is_active: true,
        current_enrollment_id: enrollmentId,
        readiness_status: "needs_agreement",
        charge_attribution: {
          invoice_count: 2,
          line_count: 2,
          gross_minor: 13_500,
          funding_minor: 1_000,
          subtotal_minor: 12_500,
          tax_minor: 0,
          total_minor: 12_500,
        },
      },
    ],
  },
  organizationId,
  familyId,
);

function render(node: ReactNode): string {
  return renderToStaticMarkup(
    createElement(
      ThemeProvider,
      { theme: workspaceTheme },
      createElement(MemoryRouter, null, node),
    ),
  );
}

describe("BillingReadinessPanel", () => {
  it("renders the exact setup destination and explains the missing step", () => {
    const markup = render(
      createElement(BillingReadinessPanel, {
        status: "live",
        data: readiness,
      }),
    );
    expect(markup).toContain("Enrollment to billing readiness");
    expect(markup).toContain("Agreement needed");
    expect(markup).toContain("Create the enrollment agreement");
    expect(markup).toContain(
      `/billing?view=rates&amp;account=${accountId}`,
    );
    expect(markup).toContain("does not certify invoice accuracy");
  });

  it("provides deterministic operator labels for every status", () => {
    expect(
      billingReadinessActionLabel({
        ...readiness.items[0],
        status: "agreement_scope_conflict",
      }),
    ).toBe("Resolve the agreement scope");
    expect(
      billingReadinessActionLabel({
        ...readiness.items[0],
        status: "needs_current_enrollment",
      }),
    ).toBe("Open the child’s enrollment");
    expect(
      billingReadinessActionLabel({
        ...readiness.items[0],
        status: "needs_review",
        reason_codes: ["billing_family_not_active"],
      }),
    ).toBe("Review the family status");
  });

  it("keeps transport failure distinct from a clean empty projection", () => {
    const failed = render(
      createElement(BillingReadinessPanel, {
        status: "error",
        data: null,
        message: "Connection unavailable",
      }),
    );
    const empty = render(
      createElement(BillingReadinessPanel, {
        status: "empty",
        data: {
          ...readiness,
          counts: {
            total: 0,
            setup_ready: 0,
            needs_account: 0,
            needs_payer: 0,
            needs_current_enrollment: 0,
            needs_rate_plan: 0,
            needs_agreement: 0,
            agreement_scope_conflict: 0,
            needs_review: 0,
          },
          items: [],
        },
      }),
    );
    expect(failed).toContain("Billing readiness is unavailable");
    expect(empty).toContain("No active enrollment billing rows");
  });
});

describe("FamilyFinanceCard", () => {
  it("renders settlement only as family-account truth", () => {
    const markup = render(
      createElement(FamilyFinanceCard, {
        status: "live",
        data: familySummary,
      }),
    );
    expect(markup).toContain("Family finance");
    expect(markup).toContain("Family account settlement totals");
    expect(markup).toContain("Outstanding");
    expect(markup).toContain("$70.00");
    expect(markup).toContain("Payments recorded");
    expect(markup).toContain(
      `/billing?view=accounts&amp;account=${accountId}`,
    );
    expect(markup).toContain("Settlement belongs to the family account");
  });
});

describe("ChildFinanceCard", () => {
  it("shows charge attribution without inventing child settlement", () => {
    const markup = render(
      createElement(ChildFinanceCard, {
        status: "live",
        data: familySummary.children[0] ?? null,
      }),
    );
    expect(markup).toContain("Charge attribution");
    expect(markup).toContain("Gross care charges");
    expect(markup).toContain("Funding offset");
    expect(markup).toContain("Attributed total");
    expect(markup).toContain("$125.00");
    expect(markup).toContain("family-account level");
    expect(markup).not.toContain("Outstanding");
    expect(markup).not.toContain("Paid");
  });

  it("labels inactive history without assigning a false readiness state", () => {
    const markup = render(
      createElement(ChildFinanceCard, {
        status: "live",
        data: {
          ...familySummary.children[0]!,
          is_active: false,
          current_enrollment_id: null,
          readiness_status: null,
        },
      }),
    );
    expect(markup).toContain("Historical record");
  });
});
