import type { BillingInvoiceDocumentPreview } from "./types";

const UNSAFE_TITLE_CHARACTERS = /[^A-Z0-9._-]+/g;

/**
 * Gives the browser print dialog a mode-truthful, filesystem-safe title.
 * This is presentation metadata only; it does not create or download a file.
 */
export function billingInvoiceDocumentPrintTitle(
  preview: BillingInvoiceDocumentPreview,
): string {
  const invoiceNumber = preview.invoice.invoice_number
    .trim()
    .toLocaleUpperCase("en-CA")
    .replace(UNSAFE_TITLE_CHARACTERS, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return preview.billing_mode === "manual"
    ? `PRIVATE-MANUAL-INVOICE-RECORD-${invoiceNumber || "DOCUMENT"}`
    : `TEST-SYNTHETIC-INVOICE-PREVIEW-${invoiceNumber || "DOCUMENT"}`;
}

export function billingInvoiceDocumentEffectCount(
  preview: BillingInvoiceDocumentPreview,
): number {
  return preview.allocations.length + preview.credits.length;
}
