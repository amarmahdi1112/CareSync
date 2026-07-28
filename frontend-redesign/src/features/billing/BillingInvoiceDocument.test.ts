import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ThemeProvider } from "styled-components";
import { describe, expect, it } from "vitest";
import { workspaceTheme } from "../../styles/theme";
import {
  billingInvoiceDocumentCanonicalSha256,
  BillingApiError,
  parseBillingInvoiceDocumentPreview,
  verifyBillingInvoiceDocumentDigest,
} from "./billingApi";
import apiSource from "./billingApi.ts?raw";
import documentSource from "./BillingInvoiceDocument.tsx?raw";
import pageSource from "./BillingPage.tsx?raw";
import { BillingInvoiceDocument } from "./BillingInvoiceDocument";
import {
  billingInvoiceDocumentEffectCount,
  billingInvoiceDocumentPrintTitle,
} from "./billingInvoiceDocumentModel";

const organizationId = "11111111-1111-4111-8111-111111111111";
const invoiceId = "22222222-2222-4222-8222-222222222222";
const accountId = "33333333-3333-4333-8333-333333333333";
const familyId = "44444444-4444-4444-8444-444444444444";
const payerVersionId = "55555555-5555-4555-8555-555555555555";
const guardianId = "66666666-6666-4666-8666-666666666666";
const lineId = "77777777-7777-4777-8777-777777777777";
const agreementVersionId = "88888888-8888-4888-8888-888888888888";
const childId = "99999999-9999-4999-8999-999999999999";
const allocationId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const paymentId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const creditId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const generatedAt = "2026-07-22T20:00:00Z";

function rawPreview() {
  return {
    schema_version: "0033",
    document_version: "billing-invoice-preview-v1",
    organization_id: organizationId,
    invoice_id: invoiceId,
    billing_mode: "sandbox",
    sandbox: true,
    provenance_label: "TEST/SYNTHETIC — NOT A REAL INVOICE",
    read_only: true,
    download_enabled: false,
    delivery_enabled: false,
    generated_at: generatedAt,
    data_through_at: "2026-07-22T19:59:58Z",
    data_through_realtime_sequence: 42,
    organization: {
      id: organizationId,
      display_name: "North Star Child Care",
      legal_name: "North Star Child Care Ltd.",
      email: "billing@northstar.example.test",
      phone: "+1 780 555 0199",
    },
    invoice: {
      organization_id: organizationId,
      id: invoiceId,
      billing_account_id: accountId,
      family_id: familyId,
      billing_account_payer_version_id: payerVersionId,
      payer_guardian_id: guardianId,
      invoice_number: "TEST-INV-202607-ABC",
      status: "issued",
      currency: "CAD",
      issue_date: "2026-07-22",
      due_date: "2026-08-05",
      service_period_start: "2026-07-01",
      service_period_end: "2026-07-31",
      family_name: "Example family",
      gross_subtotal_minor: 10_000,
      funding_minor: 0,
      subtotal_minor: 10_000,
      tax_minor: 0,
      total_minor: 10_000,
      issued_at: "2026-07-22T18:30:00Z",
      lines: [
        {
          organization_id: organizationId,
          id: lineId,
          agreement_version_id: agreementVersionId,
          child_id: childId,
          line_number: 1,
          description: "Monthly care",
          child_name: "Example Child",
          rate_plan_name: "Monthly care",
          billing_unit: "monthly_period",
          service_period_start: "2026-07-01",
          service_period_end: "2026-07-31",
          quantity: 1,
          gross_unit_amount_minor: 10_000,
          funding_unit_amount_minor: 0,
          unit_amount_minor: 10_000,
          tax_rate_basis_points: 0,
          gross_subtotal_minor: 10_000,
          funding_minor: 0,
          subtotal_minor: 10_000,
          tax_minor: 0,
          total_minor: 10_000,
        },
      ],
    },
    payer_snapshot: {
      payer_version_id: payerVersionId,
      guardian_id: guardianId,
      name: "Example Guardian",
      email: "guardian@example.test",
      address: "123 Test Avenue\nEdmonton, AB",
    },
    allocations: [
      {
        id: allocationId,
        payment_id: paymentId,
        amount_minor: 2_000,
        allocated_at: "2026-07-22T19:00:00Z",
      },
    ],
    credits: [
      {
        id: creditId,
        amount_minor: 1_000,
        reason_code: "billing_correction",
        note: "Synthetic adjustment",
        issued_at: "2026-07-22T19:30:00Z",
      },
    ],
    settlement: {
      currency: "CAD",
      total_minor: 10_000,
      allocated_minor: 2_000,
      credits_minor: 1_000,
      outstanding_minor: 7_000,
    },
    canonical_sha256: "a".repeat(64),
  };
}

describe("billing invoice document preview parser", () => {
  it("accepts a coherent synthetic rendering source and preserves exact identity", () => {
    const parsed = parseBillingInvoiceDocumentPreview(
      rawPreview(),
      organizationId,
      invoiceId,
    );
    expect(parsed.invoice.id).toBe(invoiceId);
    expect(parsed.invoice.organization_id).toBe(organizationId);
    expect(parsed.payer_snapshot.payer_version_id).toBe(payerVersionId);
    expect(parsed.settlement.outstanding_minor).toBe(7_000);
    expect(parsed.canonical_sha256).toHaveLength(64);
  });

  it("fails closed on safety-boundary, identity, and settlement tampering", () => {
    const unsafe = { ...rawPreview(), delivery_enabled: true };
    expect(() =>
      parseBillingInvoiceDocumentPreview(unsafe, organizationId, invoiceId),
    ).toThrow(BillingApiError);

    const crossedInvoice = {
      ...rawPreview(),
      invoice: {
        ...rawPreview().invoice,
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      },
    };
    expect(() =>
      parseBillingInvoiceDocumentPreview(
        crossedInvoice,
        organizationId,
        invoiceId,
      ),
    ).toThrow("identity proof");

    const driftedSettlement = {
      ...rawPreview(),
      settlement: { ...rawPreview().settlement, allocated_minor: 2_001 },
    };
    expect(() =>
      parseBillingInvoiceDocumentPreview(
        driftedSettlement,
        organizationId,
        invoiceId,
      ),
    ).toThrow("settlement reconciliation");
  });

  it("rejects the valid document for a different requested invoice", () => {
    expect(() =>
      parseBillingInvoiceDocumentPreview(
        rawPreview(),
        organizationId,
        "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      ),
    ).toThrow("did not match the requested invoice");
  });

  it("recomputes the backend canonical JSON digest and rejects altered proof", async () => {
    const parsed = parseBillingInvoiceDocumentPreview(
      rawPreview(),
      organizationId,
      invoiceId,
    );
    const canonicalDigest =
      await billingInvoiceDocumentCanonicalSha256(parsed);
    const verified = { ...parsed, canonical_sha256: canonicalDigest };
    await expect(
      verifyBillingInvoiceDocumentDigest(verified),
    ).resolves.toBeUndefined();
    await expect(
      verifyBillingInvoiceDocumentDigest(parsed),
    ).rejects.toThrow("canonical integrity check");
  });
});

describe("billing invoice document model and rendering", () => {
  const preview = parseBillingInvoiceDocumentPreview(
    rawPreview(),
    organizationId,
    invoiceId,
  );

  it("uses a filesystem-safe title that cannot be mistaken for a real invoice", () => {
    const modified = {
      ...preview,
      invoice: {
        ...preview.invoice,
        invoice_number: " test / invoice : 27 ",
      },
    };
    expect(billingInvoiceDocumentPrintTitle(modified)).toBe(
      "TEST-SYNTHETIC-INVOICE-PREVIEW-TEST-INVOICE-27",
    );
    expect(billingInvoiceDocumentEffectCount(preview)).toBe(2);
  });

  it("renders an accessible A4 source with repeated warnings and reconciled effects", () => {
    const markup = renderToStaticMarkup(
      createElement(
        ThemeProvider,
        { theme: workspaceTheme },
        createElement(BillingInvoiceDocument, { preview }),
      ),
    );
    expect(markup).toContain(
      'aria-label="Generated synthetic preview of invoice TEST-INV-202607-ABC"',
    );
    expect(markup.match(/TEST \/ SYNTHETIC/g)).toHaveLength(24);
    expect(markup).toContain("TEST/SYNTHETIC — NOT A REAL INVOICE");
    expect(markup).toContain("Generated preview — not delivered and not tax-valid");
    expect(markup).toContain("Print");
    expect(markup).toContain("North Star Child Care");
    expect(markup).toContain("Example Guardian");
    expect(markup).toContain("$70.00");
    expect(markup).toContain("Billing Correction");
    expect(markup).toContain("a".repeat(64));
  });

  it("renders a private manual invoice record without synthetic claims or watermarks", () => {
    const raw = rawPreview();
    Object.assign(raw, {
      billing_mode: "manual",
      sandbox: false,
      provenance_label: "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
    });
    const manual = parseBillingInvoiceDocumentPreview(
      raw,
      organizationId,
      invoiceId,
    );
    const markup = renderToStaticMarkup(
      createElement(
        ThemeProvider,
        { theme: workspaceTheme },
        createElement(BillingInvoiceDocument, { preview: manual }),
      ),
    );
    expect(billingInvoiceDocumentPrintTitle(manual)).toBe(
      "PRIVATE-MANUAL-INVOICE-RECORD-TEST-INV-202607-ABC",
    );
    expect(markup).toContain(
      'aria-label="Generated private manual record of invoice TEST-INV-202607-ABC"',
    );
    expect(markup).toContain("PRIVATE/MANUAL — OFF-PLATFORM RECORD");
    expect(markup).toContain(
      "Private manual record — not delivered by CareSync",
    );
    expect(markup).not.toContain("TEST / SYNTHETIC");
    expect(markup).not.toContain("Synthetic invoice total");
  });
});

describe("billing invoice document source integration", () => {
  it("fetches the canonical endpoint and opens it only from invoice detail", () => {
    expect(apiSource).toContain(
      "/document-preview",
    );
    expect(apiSource).toContain("parseBillingInvoiceDocumentPreview");
    expect(pageSource).toContain("<BillingInvoicePreviewDialog");
    expect(pageSource).toContain("Preview document");
    expect(pageSource).toContain("organizationId={invoice.organization_id}");
  });

  it("keeps browser printing local, synthetic, and visibly separate from delivery", () => {
    expect(documentSource).toContain("@page");
    expect(documentSource).toContain("size: A4 portrait");
    expect(documentSource).toContain("window.print()");
    expect(documentSource).toContain("Print / Save PDF");
    expect(documentSource).toContain("delivery_enabled");
    expect(documentSource).toContain("does not download, send, issue, or deliver");
    expect(documentSource).toContain("No partial or unverified document was rendered");
  });
});
