import { describe, expect, it } from "vitest";
import {
  billingErrorMessage,
  billingServerErrorCode,
  presentBillingError,
} from "./billingErrorPresentation";

function serverError(
  code: string,
  extra: Record<string, unknown> = {},
): Error & { details: unknown } {
  return Object.assign(new Error("Canonical billing records changed."), {
    details: { detail: { code, ...extra } },
  });
}

describe("billing server error presentation", () => {
  it("extracts nested and direct structured server codes", () => {
    expect(
      billingServerErrorCode(serverError("billing_agreement_version_stale")),
    ).toBe("billing_agreement_version_stale");
    expect(
      billingServerErrorCode({
        details: { code: "billing_payment_reference_reused" },
      }),
    ).toBe("billing_payment_reference_reused");
    expect(billingServerErrorCode(new Error("offline"))).toBeNull();
  });

  it("turns invoice-cycle codes into distinct actionable guidance", () => {
    const codes = [
      "billing_agreement_period_already_invoiced",
      "billing_agreement_version_stale",
      "billing_agreement_not_effective_for_period",
      "billing_agreement_rate_drift",
      "billing_service_period_frequency_mismatch",
      "billing_mixed_agreement_frequencies",
      "billing_account_payer_needs_review",
    ];
    const presentations = codes.map((code) =>
      presentBillingError(serverError(code)),
    );
    expect(new Set(presentations.map((item) => item.message)).size).toBe(
      codes.length,
    );
    expect(presentations.every((item) => item.code)).toBe(true);
    expect(
      presentations.every((item) =>
        ["edit", "refresh", "review_setup"].includes(item.recovery),
      ),
    ).toBe(true);
    expect(presentations[0].message).toMatch(/existing invoice/i);
    expect(presentations[1].message).toMatch(/exact historical version/i);
    expect(presentations[4].message).toMatch(/exact weekly.*monthly/i);
  });

  it("uses the server organization date in issue-date guidance", () => {
    expect(
      presentBillingError(
        serverError("billing_invoice_issue_date_must_be_today", {
          organization_local_date: "2026-07-22",
        }),
      ),
    ).toEqual({
      code: "billing_invoice_issue_date_must_be_today",
      message:
        "Set the issue date to the organization's current date, 2026-07-22, then review the invoice again.",
      recovery: "edit",
    });
  });

  it("distinguishes access, refresh, edit, and protected reconciliation paths", () => {
    expect(
      presentBillingError(serverError("billing_permission_required")).recovery,
    ).toBe("request_access");
    expect(
      presentBillingError(serverError("billing_workspace_snapshot_advanced"))
        .recovery,
    ).toBe("refresh");
    expect(
      presentBillingError(
        serverError("billing_readiness_batch_snapshot_advanced"),
      ).recovery,
    ).toBe("refresh");
    expect(
      presentBillingError(serverError("billing_credit_exceeds_outstanding"))
        .recovery,
    ).toBe("edit");
    expect(
      presentBillingError(serverError("billing_operation_already_committed"))
        .recovery,
    ).toBe("reconcile");
    expect(
      presentBillingError(
        serverError("billing_manual_activation_requires_empty_ledger"),
      ).recovery,
    ).toBe("review_setup");
    expect(
      presentBillingError(
        serverError("billing_manual_organization_not_allowlisted"),
      ).recovery,
    ).toBe("request_access");
  });

  it("preserves explicit local errors and safely labels unknown server codes", () => {
    expect(billingErrorMessage(new Error("Choose a family account."))).toBe(
      "Choose a family account.",
    );
    expect(
      billingErrorMessage({
        details: { detail: { code: "billing_new_future_code" } },
      }),
    ).toMatch(/billing_new_future_code/i);
  });
});
