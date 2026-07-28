import { describe, expect, it } from "vitest";
import pageSource from "./BillingPage.tsx?raw";
import apiSource from "./billingApi.ts?raw";
import capabilitySource from "./billingCapability.tsx?raw";
import dialogSource from "./BillingDialog.tsx?raw";
import operationSource from "./billingOperation.ts?raw";
import setupSource from "./BillingSetupWorkspace.tsx?raw";
import realtimeCoverageSource from "../../realtime/realtimeCoverage.ts?raw";

describe("billing workspace integration boundary", () => {
  it("fails closed behind leadership identity and literal billing grants", () => {
    expect(capabilitySource).toContain("hasExplicitPermission");
    expect(capabilitySource).toContain("ACCESS.billingRead");
    expect(capabilitySource).toContain('session.user?.role?.key === "owner"');
    expect(capabilitySource).toContain(
      'session.user?.role?.key === "administrator"',
    );
    expect(pageSource).toContain("ACCESS.billingManage");
    expect(pageSource).toContain("ACCESS.billingIssue");
    expect(pageSource).toContain("ACCESS.billingPayments");
    expect(pageSource).toContain("ACCESS.billingAdjust");
    expect(pageSource).not.toContain("hasPermission(");
  });

  it("requires authoritative server write readiness for every mutation and recovery path", () => {
    expect(apiSource).toContain("billing write-readiness flag");
    expect(apiSource).toContain("billing write-readiness consistency proof");
    expect(pageSource).toContain(
      "capability.capability.writes_available === true",
    );
    expect(pageSource).toContain("commandWriteAllowed");
    expect(pageSource).toContain("dialogWriteAllowed");
    expect(pageSource).toContain(
      "disabled={busy || !commandWriteAllowed(pending.command_kind)}",
    );
    expect(pageSource).toContain("disabled={busy || !canRecover}");
    expect(pageSource).toContain(
      "disabled={busy || !writeAllowed || invoiceReviewBlocked}",
    );
    expect(pageSource).toContain(
      "Canonical billing is viewable, but financial writes are unavailable",
    );
    expect(pageSource).toContain("Shadow · read only");
    expect(pageSource).toContain("disposable-target attestation");
  });

  it("requires immutable owner review before private manual billing becomes writable", () => {
    expect(apiSource).toContain('"/billing/manual-activation"');
    expect(apiSource).toContain("private_local_manual_billing_v1");
    expect(apiSource).toContain(
      "I reviewed the private manual billing boundary",
    );
    expect(pageSource).toContain("session.user?.role?.key === \"owner\"");
    expect(pageSource).toContain("Private manual billing needs owner activation");
    expect(pageSource).toContain("Exact owner attestation");
    expect(pageSource).toContain("Keep read-only");
    expect(pageSource).toContain("Activate manual billing");
    expect(pageSource).toContain("manual_activated === true");
    expect(pageSource).toContain("No processor, money movement");
  });

  it("renders only a certified coherent workspace with a persistent sandbox boundary", () => {
    expect(pageSource).toContain(
      "billingApi.workspace(organizationId, signal)",
    );
    expect(pageSource).not.toContain("billingApi.overview(organizationId");
    expect(apiSource).toContain("complete !== provesSingleCompletePage");
    expect(apiSource).toContain(
      "assembleBillingWorkspacePages(pages, organizationId)",
    );
    expect(pageSource).toContain(
      "Synthetic sandbox — not real invoices or payments",
    );
    expect(pageSource).toContain("coherent through event");
    expect(pageSource).toContain("dataThroughRealtimeSequence");
    expect(pageSource).toContain(
      "featureIntegrationManifest.billing.realtimeEntities",
    );
  });

  it("uses truthful private-manual terminology without weakening the sandbox boundary", () => {
    expect(apiSource).toContain("parseBillingProvenance");
    expect(apiSource).toContain(
      "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    );
    expect(pageSource).toContain(
      "Private manual records — off-platform billing only",
    );
    expect(pageSource).toContain(
      'snapshot.sandbox ? "synthetic" : "private manual"',
    );
    expect(pageSource).toContain(
      'snapshot.sandbox ? "synthetic" : "private manual"',
    );
  });

  it("maps safe receipt and notification focus to the correct full-page section", () => {
    for (const mapping of [
      'billing_account: "accounts"',
      'billing_invoice: "invoices"',
      'billing_credit: "invoices"',
      'billing_payment: "payments"',
      'billing_allocation: "payments"',
      'billing_rate_plan: "rates"',
      'billing_agreement: "rates"',
    ])
      expect(pageSource).toContain(mapping);
    expect(pageSource).toContain("RECORD_ID.test(rawRecordId)");
    expect(pageSource).toContain("data-focused={item.id === focusedRecordId}");
    expect(pageSource).toContain("data-billing-record={item.id}");
    expect(pageSource).toContain("requestAnimationFrame");
    expect(pageSource).toContain("reference is unavailable");
    expect(pageSource).toContain("cannot prove record");
    expect(pageSource).toContain('destination.pathname.endsWith("/billing")');
  });

  it("disables financial decisions while the projection is refreshing, stale, or locked", () => {
    expect(pageSource).toContain(
      'const commandProjectionReady = refreshState === "current"',
    );
    expect(pageSource.match(/commandProjectionReady/g)?.length).toBeGreaterThan(
      6,
    );
    expect(pageSource).toContain("!pending && !journalError");
    expect(apiSource).toContain("complete assembly proof");
    expect(apiSource).toContain('"payer_versions"');
    expect(apiSource).toContain("payer version ownership proof");
    expect(apiSource).toContain("payer version chain proof");
    expect(apiSource).toContain("latest payer version proof");
    expect(pageSource).toContain("workspaceLoadRef.current");
    expect(pageSource).toContain("acceptedWorkspaceSequenceRef.current");
    expect(pageSource).toContain("setSnapshot(null)");
    expect(pageSource).toContain("throw caught");
    expect(pageSource).not.toContain("billingApi.account(organizationId");
  });

  it("offers durable absence finalization only with the explicit recovery grant", () => {
    expect(pageSource).toContain("ACCESS.billingRecover");
    expect(pageSource).toContain('pendingLookup === "not_found" && canRecover');
    expect(pageSource).toContain("finalizeCommandAbsence");
    expect(pageSource).toContain("The absence claim is committed");
  });

  it("keeps private command fields volatile and uses an accessible portal dialog", () => {
    expect(operationSource).toContain("version: 3");
    expect(operationSource).toContain("volatileInputs");
    expect(operationSource).toContain("purgeVolatileBillingOperationInputs");
    expect(operationSource).not.toContain("input_fingerprint:");
    expect(dialogSource).toContain("createPortal");
    expect(dialogSource).toContain('role="dialog"');
    expect(dialogSource).toContain("aria-modal");
    expect(dialogSource).toContain("aria-describedby");
    expect(dialogSource).toContain("opener.current?.isConnected");
    expect(dialogSource).toContain("<Body disabled={busy}>");
  });

  it("requires an explicit payer and keeps payer identity visible after posting", () => {
    expect(pageSource).not.toContain("guardians[0]");
    expect(pageSource).toContain('set("payer_guardian_id", "")');
    expect(pageSource).toContain("Choose the guardian who actually made this payment");
    expect(pageSource).toContain('<th>Actual payer</th>');
    expect(pageSource).toContain('data-label="Actual payer">{item.payer_name}');
    expect(pageSource).toContain('data-label="Payer">{row.payer}');
    expect(pageSource).toContain("resolveBillingAccountPayer");
    expect(pageSource).toContain("Current payer identity unavailable");
    expect(pageSource).toContain('data-label="Current payer"');
    expect(pageSource).toContain("Assignment v${assignmentVersion}");
    expect(pageSource).toContain('data-payer-resolution={resolved.status}');
  });

  it("explains concurrent payer protection without exposing storage jargon or record ids", () => {
    const normalizedPageSource = pageSource.replace(/\s+/g, " ");
    expect(pageSource).toContain("Your review is protected");
    expect(pageSource).toContain("CareSync will ask");
    expect(normalizedPageSource).toContain(
      "you to refresh instead of overwriting their work",
    );
    expect(normalizedPageSource).toContain(
      "guardian currently responsible for",
    );
    expect(normalizedPageSource).toContain(
      "Choose who should be responsible for future charges on this family account",
    );
    expect(pageSource.toLowerCase()).not.toContain("append-only payer");
    expect(pageSource.toLowerCase()).not.toContain(
      "exact current payer version",
    );
    expect(pageSource).not.toContain(
      "{payerRevision.latest_payer_version_id}",
    );
  });

  it("keeps account and invoice searches independent", () => {
    expect(pageSource).toContain(
      'const [accountSearch, setAccountSearch] = useState("")',
    );
    expect(pageSource).toContain(
      'const [invoiceSearch, setInvoiceSearch] = useState("")',
    );
    expect(pageSource).toContain("search={accountSearch}");
    expect(pageSource).toContain("onSearch={setAccountSearch}");
    expect(pageSource).toContain("search={invoiceSearch}");
    expect(pageSource).toContain("onSearch={setInvoiceSearch}");
    expect(pageSource).not.toContain('const [search, setSearch] = useState("")');
  });

  it("opens canonical invoice detail and previews immutable financial impact", () => {
    expect(pageSource).toContain("function InvoiceDetailDialog");
    expect(pageSource).toContain("Open invoice");
    expect(pageSource).toContain("Contract provenance");
    expect(pageSource).toContain("invoice.lines.map");
    expect(pageSource).toContain("Coherent snapshot amount preview");
    expect(pageSource).toContain("previewInvoiceFromAgreements");
    expect(pageSource).toContain("server revalidates every source");
    expect(pageSource).toContain("Immutable payer provenance");
    expect(pageSource).toContain("invoice.billing_account_payer_version_id");
    expect(pageSource).toContain("invoice.payer_guardian_id");
    expect(pageSource).toContain("snapshot.payerVersions.find");
    expect(pageSource).toContain("do not represent delivery, collection, or");
    expect(pageSource).toContain("Resulting invoice balance preview");
    expect(pageSource).toContain("previewCreditResult");
  });

  it("blocks invoice review until agreement and pinned-rate coverage prove the full service period", () => {
    expect(pageSource).toContain(
      "start: form.service_period_start",
    );
    expect(pageSource).toContain("end: form.service_period_end");
    expect(pageSource).toContain(
      'kind === "invoice" && agreements.length > 0 && !invoicePreview',
    );
    expect(pageSource).toContain(
      "disabled={busy || !writeAllowed || invoiceReviewBlocked}",
    );
    expect(pageSource).toContain("Invoice review is unavailable");
    expect(pageSource).toContain(
      "Review and issue are blocked until every selected",
    );
  });

  it("distinguishes capability probe failure and exposes paged-history truth", () => {
    expect(capabilitySource).toContain('| "error"');
    expect(capabilitySource).toContain("retryRevision");
    expect(capabilitySource).toContain('phase: "error"');
    expect(pageSource).toContain("Billing capability check failed");
    expect(pageSource).toContain("Retry capability check");
    expect(pageSource).toContain("snapshot.canonicalCollectionLimit");
    expect(pageSource).toContain("Canonical history was assembled");
    expect(pageSource).toContain("across every server page");
    expect(pageSource).toContain("fails closed on any page drift");
  });

  it("exposes canonical allocation and credit effects with stable safe detail", () => {
    expect(apiSource).toContain("parseBillingAllocation");
    expect(apiSource).toContain("parseBillingCredit");
    expect(apiSource).toContain("snapshot_token");
    expect(apiSource).toContain("duplicate or overlap proof");
    expect(apiSource).toContain("No partial workspace was accepted");
    expect(pageSource).toContain("function BillingEffectDetailDialog");
    expect(pageSource).toContain("Canonical settlement effects");
    expect(pageSource).toContain("allocated_by_user_id");
    expect(pageSource).toContain("issued_by_user_id");
    expect(pageSource).toContain("client_operation_id");
    expect(pageSource).toContain("request_hash");
    expect(pageSource).toContain('onOpenRecord("billing_invoice"');
    expect(pageSource).toContain('onOpenRecord("billing_payment"');
  });

  it("keeps every current action-queue exception reachable", () => {
    expect(pageSource).toContain("showAllActions");
    expect(pageSource).toContain("visibleWork.map");
    expect(pageSource).toContain("View all ${work.length} actions");
    expect(pageSource).toContain("aria-expanded={showAllActions}");
  });

  it("renders informational readiness and roadmap entries as non-interactive status rows", () => {
    const reports = pageSource.slice(
      pageSource.indexOf("function ReportsTab"),
      pageSource.indexOf("type BillingEffectDetailProps"),
    );
    expect(reports.match(/<StatusRow/g)).toHaveLength(2);
    expect(reports).not.toContain("<WorkRow");
    expect(pageSource).toContain("const StatusRow = styled.div");
  });

  it("keeps setup review current and exposes exact protected-operation recovery", () => {
    expect(setupSource).toContain(
      "snapshotToken: preview.snapshot_token",
    );
    expect(setupSource).toContain(
      "The next reviewed setup proof changed after the last receipt",
    );
    expect(setupSource).toContain('to="/billing?view=overview"');
    expect(setupSource).toContain("Open billing recovery");
    expect(setupSource).toContain(
      "revision_can_resolve_as_of_date",
    );
    expect(realtimeCoverageSource).toContain(
      "'family', 'child', 'enrollment', 'facility', 'facility_program'",
    );
  });
});
