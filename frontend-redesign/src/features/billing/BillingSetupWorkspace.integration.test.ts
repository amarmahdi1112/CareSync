import { describe, expect, it } from "vitest";
import pageSource from "./BillingPage.tsx?raw";
import setupSource from "./BillingSetupWorkspace.tsx?raw";
import apiSource from "./billingBatchPlanApi.ts?raw";
import operationSource from "./billingOperation.ts?raw";

describe("billing setup planner integration boundary", () => {
  it("routes /billing?view=setup to a dedicated full-page workspace", () => {
    expect(pageSource).toContain('params.get("view") === "setup"');
    expect(pageSource).toContain("<BillingSetupWorkspace />");
    expect(pageSource).toContain('["setup", "Setup planner"]');
    expect(setupSource).toContain('to={`/billing?view=${view}`}');
    expect(setupSource).not.toContain("BillingDialog");
  });

  it("uses only paged privacy-bounded plan and read-only preview endpoints", () => {
    expect(apiSource).toContain('"/billing/readiness/batch-plan/preview"');
    expect(apiSource).toContain(
      "`/billing/readiness/batch-plan?${query.toString()}`",
    );
    expect(apiSource).toContain("limit: String(limit)");
    expect(apiSource).toContain("offset: String(offset)");
    expect(setupSource).not.toContain("billingApi.workspace");
    expect(setupSource).not.toContain("billingApi.familyOptions");
    expect(setupSource).toContain("privacy-bounded setup page");
    expect(apiSource).toContain("affected_membership_digest");
    expect(apiSource).toContain("affected_children_truncated");
  });

  it("previews one wave and refuses invoice, payment, credit, activation, or provider actions", () => {
    expect(setupSource).toContain("selectedGroupWave");
    expect(setupSource).toContain("previewBillingBatchWave");
    expect(apiSource).toContain("BILLING_BATCH_ACTIONABLE_WAVES");
    for (const forbidden of [
      "billingApi.issueInvoice",
      "billingApi.recordPayment",
      "billingApi.allocatePayment",
      "billingApi.createCredit",
      "activateManualBilling",
    ])
      expect(setupSource).not.toContain(forbidden);
    expect(setupSource).toContain(
      "This planner cannot issue invoices, record or allocate payments",
    );
  });

  it("pins the immutable approval proof before prepare and refreshes after every receipt", () => {
    expect(operationSource).toContain(
      "approvedProof?: ApprovedBillingCommandProof",
    );
    expect(operationSource).toContain("persistPending(approvedPending, storage)");
    expect(operationSource.indexOf("persistPending(approvedPending, storage)")).toBeLessThan(
      operationSource.indexOf("prepared = await options.prepare(operationId)"),
    );
    expect(setupSource).toContain("approvedProof:");
    expect(setupSource).toContain(
      "prepared.request_hash !== intent.request_hash",
    );
    expect(setupSource).toContain(
      "receipt.client_operation_id !== intent.client_operation_id",
    );
    expect(setupSource).toContain(
      "const refreshed = await loadPlan",
    );
    expect(setupSource).toContain(
      "The remaining sequence was stopped before another command was sent",
    );
  });

  it("derives agreement amount and frequency from canonical rate terms", () => {
    expect(setupSource).toContain("frequencyForUnit");
    expect(setupSource).toContain(
      "family_amount_minor_per_unit: group.rate_unit_amount_minor",
    );
    expect(setupSource).toContain("agreement_effective_from_min");
    expect(setupSource).toContain("agreement_effective_until_max");
    expect(setupSource).toContain("Rate-matched family amount");
  });

  it("keeps Apply disabled until capability, permission, activation, journal, preview, and attestation all agree", () => {
    expect(setupSource).toContain("billingSetupApplyBlockReason");
    expect(setupSource).toContain("capabilityWritesAvailable");
    expect(setupSource).toContain("planApplyAvailable");
    expect(setupSource).toContain("previewApplyAvailable");
    expect(setupSource).toContain("manualActivationRequired");
    expect(setupSource).toContain("hasPendingOperation");
    expect(setupSource).toContain("journalError");
    expect(setupSource).toContain("disabled={applyBlockReason !== null}");
  });
});
