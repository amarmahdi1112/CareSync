import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  PrinterIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import {
  createGlobalStyle,
  styled,
} from "styled-components";
import {
  ActionButton,
  IconButton,
} from "../../components/ui/Primitives";
import { billingApi, BillingApiError } from "./billingApi";
import {
  formatCadMinor,
  formatDateOnly,
  formatDateTime,
  titleCase,
} from "./billingModel";
import {
  billingInvoiceDocumentEffectCount,
  billingInvoiceDocumentPrintTitle,
} from "./billingInvoiceDocumentModel";
import type {
  BillingInvoiceDocumentPreview,
  BillingProvenanceLabel,
} from "./types";

const WATERMARKS = Array.from({ length: 24 }, (_, index) => index);

const PrintBoundary = createGlobalStyle`
  @media print {
    @page {
      size: A4 portrait;
      margin: 10mm;
    }

    body > *:not(.billing-invoice-preview-portal) {
      display: none !important;
    }

    body > .billing-invoice-preview-portal {
      display: block !important;
      position: static !important;
    }

    .billing-invoice-preview-backdrop,
    .billing-invoice-preview-surface,
    .billing-invoice-preview-scroll {
      position: static !important;
      display: block !important;
      width: auto !important;
      height: auto !important;
      max-width: none !important;
      max-height: none !important;
      overflow: visible !important;
      padding: 0 !important;
      border: 0 !important;
      border-radius: 0 !important;
      background: transparent !important;
      box-shadow: none !important;
    }

    .billing-invoice-preview-chrome {
      display: none !important;
    }

    .billing-invoice-document {
      width: 190mm !important;
      min-height: 277mm !important;
      margin: 0 auto !important;
      border: 0 !important;
      border-radius: 0 !important;
      box-shadow: none !important;
      print-color-adjust: exact;
      -webkit-print-color-adjust: exact;
    }
  }
`;

const Document = styled.article`
  position: relative;
  isolation: isolate;
  box-sizing: border-box;
  width: min(210mm, 100%);
  min-height: 297mm;
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  padding: clamp(24px, 5vw, 52px);
  color: #132033;
  background: #fff;
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.24);
  font-family:
    Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;

  h1,
  h2,
  h3,
  p {
    margin: 0;
  }

  strong {
    font-weight: 680;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 9px 7px;
    border-bottom: 1px solid #dbe4ee;
    text-align: left;
    vertical-align: top;
    font-size: 0.68rem;
    line-height: 1.45;
  }

  th {
    color: #42526a;
    background: #f0f5f9;
    font-size: 0.58rem;
    font-weight: 720;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .money {
    text-align: right;
    white-space: nowrap;
  }

  @media (max-width: 720px) {
    padding: 24px 18px;
    table {
      min-width: 650px;
    }
  }
`;

const WatermarkLayer = styled.div`
  position: absolute;
  z-index: -1;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: 122px;
  align-content: stretch;
  overflow: hidden;
  pointer-events: none;
  opacity: 0.052;
  transform: rotate(-25deg) scale(1.18);
`;

const Watermark = styled.span`
  display: grid;
  place-items: center;
  color: #8b1d1d;
  font-size: 0.68rem;
  font-weight: 850;
  letter-spacing: 0.16em;
  text-align: center;
  text-transform: uppercase;
`;

const DocumentHeader = styled.header`
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 28px;
  align-items: start;
  padding-bottom: 20px;
  border-bottom: 3px solid #17324d;
`;

const OrganizationName = styled.h1`
  color: #10243b;
  font-size: clamp(1.15rem, 3vw, 1.65rem);
  font-weight: 690;
  letter-spacing: -0.025em;
`;

const LegalName = styled.p`
  margin-top: 4px !important;
  color: #53657a;
  font-size: 0.7rem;
  line-height: 1.55;
`;

const DocumentIdentity = styled.div`
  text-align: right;
  h2 {
    color: #10243b;
    font-size: 1rem;
    font-weight: 760;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 5px;
    font-size: 0.78rem;
  }
  span {
    color: #5b6b7f;
    font-size: 0.64rem;
  }
`;

const SyntheticBanner = styled.section`
  margin: 18px 0;
  border: 2px solid #9f3030;
  padding: 12px 14px;
  color: #771c1c;
  background: #fff3f1;
  text-align: center;
  h2 {
    font-size: 0.82rem;
    font-weight: 850;
    letter-spacing: 0.08em;
  }
  p {
    margin-top: 5px;
    font-size: 0.64rem;
    line-height: 1.5;
  }
`;

const Facts = styled.section`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 24px;
  margin: 20px 0 22px;
`;

const Fact = styled.div`
  min-width: 0;
  span {
    display: block;
    color: #5b6b7f;
    font-size: 0.56rem;
    font-weight: 720;
    letter-spacing: 0.075em;
    text-transform: uppercase;
  }
  strong,
  p {
    display: block;
    margin-top: 4px;
    overflow-wrap: anywhere;
    font-size: 0.72rem;
    line-height: 1.5;
    white-space: pre-line;
  }
`;

const Section = styled.section`
  margin-top: 22px;
  break-inside: avoid;
  h2 {
    margin-bottom: 9px;
    color: #17324d;
    font-size: 0.72rem;
    font-weight: 760;
    letter-spacing: 0.075em;
    text-transform: uppercase;
  }
`;

const Totals = styled.dl`
  width: min(300px, 100%);
  margin: 18px 0 0 auto;
  font-size: 0.7rem;
  div {
    display: flex;
    justify-content: space-between;
    gap: 20px;
    padding: 6px 0;
    border-bottom: 1px solid #dbe4ee;
  }
  dt,
  dd {
    margin: 0;
  }
  dd {
    font-variant-numeric: tabular-nums;
  }
  div:last-child {
    border-top: 2px solid #17324d;
    border-bottom: 0;
    color: #10243b;
    font-size: 0.82rem;
    font-weight: 780;
  }
`;

const SettlementGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  > div {
    border: 1px solid #d7e0ea;
    padding: 10px;
    background: #f7fafc;
  }
  span {
    display: block;
    color: #5b6b7f;
    font-size: 0.54rem;
    font-weight: 720;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 4px;
    font-size: 0.78rem;
  }
  @media (max-width: 620px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
`;

const EmptyEffects = styled.p`
  border: 1px dashed #bdc9d5;
  padding: 12px;
  color: #53657a;
  background: #f8fafc;
  font-size: 0.66rem;
`;

const DocumentFooter = styled.footer`
  margin-top: 30px;
  border-top: 1px solid #cfd9e3;
  padding-top: 13px;
  color: #4c5d71;
  font-size: 0.58rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
  h2 {
    margin-bottom: 5px;
    color: #771c1c;
    font-size: 0.64rem;
    font-weight: 800;
    letter-spacing: 0.055em;
    text-transform: uppercase;
  }
  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.54rem;
  }
`;

const PreviewBackdrop = styled.div`
  position: fixed;
  z-index: 1100;
  inset: 0;
  display: grid;
  place-items: center;
  padding: max(14px, env(safe-area-inset-top))
    max(12px, env(safe-area-inset-right))
    max(14px, env(safe-area-inset-bottom))
    max(12px, env(safe-area-inset-left));
  background: rgba(2, 8, 18, 0.84);
  backdrop-filter: blur(10px);
`;

const PreviewSurface = styled.section`
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: min(1120px, 100%);
  height: min(940px, calc(100dvh - 28px));
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 18px 7px 18px 7px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.6);
`;

const PreviewHeader = styled.header`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid ${({ theme }) => theme.color.divider};
  h2 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 620;
  }
  p {
    margin: 3px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    line-height: 1.45;
  }
`;

const PreviewActions = styled.div`
  display: flex;
  flex: none;
  gap: 8px;
`;

const PreviewScroll = styled.div`
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: clamp(14px, 3vw, 34px);
  background: #273344;
`;

const PreviewState = styled.div`
  display: grid;
  place-items: center;
  min-height: 320px;
  color: #e7eef7;
  text-align: center;
  svg {
    width: 30px;
    margin-bottom: 12px;
  }
  h3 {
    margin: 0 0 7px;
    font-size: 0.95rem;
  }
  p {
    max-width: 500px;
    margin: 0;
    color: #b6c5d7;
    font-size: 0.72rem;
    line-height: 1.6;
  }
`;

function EffectRows({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Effect</th>
          <th>Recorded</th>
          <th>Reference</th>
          <th className="money">Amount</th>
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export function BillingInvoiceDocument({
  preview,
}: {
  preview: BillingInvoiceDocumentPreview;
}) {
  const { invoice, settlement } = preview;
  const effectsPresent = billingInvoiceDocumentEffectCount(preview) > 0;
  const manual = preview.billing_mode === "manual";
  return (
    <Document
      className="billing-invoice-document"
      aria-label={
        manual
          ? `Generated private manual record of invoice ${invoice.invoice_number}`
          : `Generated synthetic preview of invoice ${invoice.invoice_number}`
      }
      data-document-version={preview.document_version}
      data-document-digest={preview.canonical_sha256}
      data-read-only={preview.read_only}
      data-download-enabled={preview.download_enabled}
      data-delivery-enabled={preview.delivery_enabled}
    >
      {!manual && (
        <WatermarkLayer aria-hidden="true">
          {WATERMARKS.map((index) => (
            <Watermark key={index}>TEST / SYNTHETIC</Watermark>
          ))}
        </WatermarkLayer>
      )}

      <DocumentHeader>
        <div>
          <OrganizationName>{preview.organization.display_name}</OrganizationName>
          {preview.organization.legal_name &&
            preview.organization.legal_name !==
              preview.organization.display_name && (
              <LegalName>{preview.organization.legal_name}</LegalName>
            )}
          <LegalName>
            {[preview.organization.email, preview.organization.phone]
              .filter(Boolean)
              .join(" · ") ||
              (manual
                ? "Organization contact not recorded"
                : "Synthetic organization contact not recorded")}
          </LegalName>
        </div>
        <DocumentIdentity>
          <h2>{manual ? "Private manual invoice record" : "Invoice preview"}</h2>
          <strong>{invoice.invoice_number}</strong>
          <span>Generated {formatDateTime(preview.generated_at)}</span>
        </DocumentIdentity>
      </DocumentHeader>

      <SyntheticBanner
        aria-label={
          manual
            ? "Private manual document boundary"
            : "Synthetic document warning"
        }
      >
        <h2>{preview.provenance_label}</h2>
        {manual ? (
          <p>
            Private, read-only off-platform record. CareSync has not delivered
            this document, processed a payment, moved money, or provided tax
            advice. Recorded settlement facts must reflect actions completed
            elsewhere.
          </p>
        ) : (
          <p>
            Generated read-only preview only. This has not been delivered, is
            not a tax-valid or real invoice, and does not prove payment or money
            movement.
          </p>
        )}
      </SyntheticBanner>

      <Facts aria-label="Invoice and payer details">
        <Fact>
          <span>Bill to — immutable payer snapshot</span>
          <strong>{preview.payer_snapshot.name}</strong>
          <p>
            {[preview.payer_snapshot.email, preview.payer_snapshot.address]
              .filter(Boolean)
              .join("\n") || "No payer contact details recorded"}
          </p>
        </Fact>
        <Fact>
          <span>Family</span>
          <strong>{invoice.family_name}</strong>
        </Fact>
        <Fact>
          <span>Service period</span>
          <strong>
            {formatDateOnly(invoice.service_period_start)} –{" "}
            {formatDateOnly(invoice.service_period_end)}
          </strong>
        </Fact>
        <Fact>
          <span>Issue and due dates</span>
          <strong>
            Issued {formatDateOnly(invoice.issue_date)}
            <br />
            Due {formatDateOnly(invoice.due_date)}
          </strong>
        </Fact>
      </Facts>

      <Section aria-labelledby="document-line-items">
        <h2 id="document-line-items">Care and funding detail</h2>
        <div role="region" aria-label="Invoice line items" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Child & service</th>
                <th>Period</th>
                <th className="money">Gross</th>
                <th className="money">Funding</th>
                <th className="money">Family</th>
                <th className="money">Tax</th>
                <th className="money">Total</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.id}>
                  <td>
                    <strong>{line.child_name}</strong>
                    <br />
                    {line.description} · {titleCase(line.billing_unit)} · qty{" "}
                    {line.quantity}
                  </td>
                  <td>
                    {formatDateOnly(line.service_period_start)}
                    <br />
                    through {formatDateOnly(line.service_period_end)}
                  </td>
                  <td className="money">
                    {formatCadMinor(line.gross_subtotal_minor)}
                  </td>
                  <td className="money">
                    {formatCadMinor(line.funding_minor)}
                  </td>
                  <td className="money">
                    {formatCadMinor(line.subtotal_minor)}
                  </td>
                  <td className="money">{formatCadMinor(line.tax_minor)}</td>
                  <td className="money">{formatCadMinor(line.total_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Totals aria-label="Invoice amount totals">
          <div>
            <dt>Gross care</dt>
            <dd>{formatCadMinor(invoice.gross_subtotal_minor)}</dd>
          </div>
          <div>
            <dt>Funding projection</dt>
            <dd>− {formatCadMinor(invoice.funding_minor)}</dd>
          </div>
          <div>
            <dt>Family subtotal</dt>
            <dd>{formatCadMinor(invoice.subtotal_minor)}</dd>
          </div>
          <div>
            <dt>Tax</dt>
            <dd>{formatCadMinor(invoice.tax_minor)}</dd>
          </div>
          <div>
            <dt>{manual ? "Invoice total" : "Synthetic invoice total"}</dt>
            <dd>{formatCadMinor(invoice.total_minor)}</dd>
          </div>
        </Totals>
      </Section>

      <Section aria-labelledby="document-settlement">
        <h2 id="document-settlement">Current canonical settlement projection</h2>
        <SettlementGrid>
          <div>
            <span>Total</span>
            <strong>{formatCadMinor(settlement.total_minor)}</strong>
          </div>
          <div>
            <span>Allocated</span>
            <strong>{formatCadMinor(settlement.allocated_minor)}</strong>
          </div>
          <div>
            <span>Credits</span>
            <strong>{formatCadMinor(settlement.credits_minor)}</strong>
          </div>
          <div>
            <span>Outstanding</span>
            <strong>{formatCadMinor(settlement.outstanding_minor)}</strong>
          </div>
        </SettlementGrid>
      </Section>

      <Section aria-labelledby="document-effects">
        <h2 id="document-effects">Immutable allocation and credit effects</h2>
        {effectsPresent ? (
          <EffectRows>
            {preview.allocations.map((allocation) => (
              <tr key={allocation.id}>
                <td>Payment allocation</td>
                <td>{formatDateTime(allocation.allocated_at)}</td>
                <td>{allocation.payment_id}</td>
                <td className="money">
                  {formatCadMinor(allocation.amount_minor)}
                </td>
              </tr>
            ))}
            {preview.credits.map((credit) => (
              <tr key={credit.id}>
                <td>
                  Credit · {titleCase(credit.reason_code)}
                  {credit.note ? ` · ${credit.note}` : ""}
                </td>
                <td>{formatDateTime(credit.issued_at)}</td>
                <td>{credit.id}</td>
                <td className="money">{formatCadMinor(credit.amount_minor)}</td>
              </tr>
            ))}
          </EffectRows>
        ) : (
          <EmptyEffects>No allocation or credit effects were present.</EmptyEffects>
        )}
      </Section>

      <DocumentFooter>
        <h2>
          {manual
            ? "Private manual record — not delivered by CareSync"
            : "Generated preview — not delivered and not tax-valid"}
        </h2>
        {manual ? (
          <p>
            This read-only private manual rendering was generated from canonical
            organization records through {formatDateTime(preview.data_through_at)}{" "}
            at realtime sequence {preview.data_through_realtime_sequence}.
            Printing or choosing “Save as PDF” in the browser creates a local
            copy. CareSync does not send, automatically issue, deliver, process,
            or move money through this action, and this record is not tax
            advice.
          </p>
        ) : (
          <p>
            This read-only synthetic rendering was generated from canonical
            sandbox data through {formatDateTime(preview.data_through_at)} at
            realtime sequence {preview.data_through_realtime_sequence}. Printing
            or choosing “Save as PDF” in the browser creates a local copy of this
            preview; CareSync does not download, send, issue, or deliver a real
            document through this action.
          </p>
        )}
        <p>
          Canonical preview digest:{" "}
          <code>{preview.canonical_sha256}</code>
        </p>
        <p>
          Invoice record <code>{invoice.id}</code> · payer version{" "}
          <code>{preview.payer_snapshot.payer_version_id}</code>
        </p>
      </DocumentFooter>
    </Document>
  );
}

export function BillingInvoicePreviewDialog({
  organizationId,
  invoiceId,
  invoiceNumber,
  provenanceLabel,
  onClose,
}: {
  organizationId: string;
  invoiceId: string;
  invoiceNumber: string;
  provenanceLabel: BillingProvenanceLabel;
  onClose: () => void;
}) {
  const [preview, setPreview] =
    useState<BillingInvoiceDocumentPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const surfaceRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    surfaceRef.current?.focus({ preventScroll: true });
    return () => {
      document.body.style.overflow = previousOverflow;
      openerRef.current?.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setPreview(null);
    setError(null);
    billingApi
      .invoiceDocumentPreview(organizationId, invoiceId, controller.signal)
      .then((next) => {
        if (next.provenance_label !== provenanceLabel)
          throw new BillingApiError(
            "The generated invoice record did not match the loaded billing boundary.",
            409,
          );
        setPreview(next);
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setError(
          caught instanceof BillingApiError || caught instanceof Error
            ? caught.message
            : "The generated invoice preview could not be loaded.",
        );
      });
    return () => {
      controller.abort();
    };
  }, [invoiceId, organizationId, provenanceLabel]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !surfaceRef.current) return;
      const controls = [
        ...surfaceRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
        ),
      ];
      if (!controls.length) return;
      const first = controls[0];
      const last = controls.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const content = (
    <>
      <PrintBoundary />
      <PreviewBackdrop
        className="billing-invoice-preview-backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <PreviewSurface
          ref={surfaceRef}
          className="billing-invoice-preview-surface"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          aria-busy={!preview && !error}
          tabIndex={-1}
        >
          <PreviewHeader className="billing-invoice-preview-chrome">
            <div>
              <h2 id={titleId}>
                {provenanceLabel ===
                "PRIVATE/MANUAL — OFF-PLATFORM RECORD"
                  ? "Private manual invoice record"
                  : "Generated invoice preview"}{" "}
                · {invoiceNumber}
              </h2>
              <p id={descriptionId}>
                {provenanceLabel}. CareSync does not deliver this document,
                process a payment, or move money through this local preview.
              </p>
            </div>
            <PreviewActions>
              <ActionButton
                type="button"
                $variant="primary"
                disabled={!preview}
                onClick={() => {
                  if (!preview) return;
                  const previousTitle = document.title;
                  document.title = billingInvoiceDocumentPrintTitle(preview);
                  try {
                    window.print();
                  } finally {
                    document.title = previousTitle;
                  }
                }}
              >
                <PrinterIcon aria-hidden="true" />
                Print / Save PDF
              </ActionButton>
              <IconButton
                type="button"
                aria-label="Close generated invoice preview"
                onClick={onClose}
              >
                <XMarkIcon aria-hidden="true" />
              </IconButton>
            </PreviewActions>
          </PreviewHeader>
          <PreviewScroll className="billing-invoice-preview-scroll">
            {preview ? (
              <BillingInvoiceDocument preview={preview} />
            ) : error ? (
              <PreviewState role="alert">
                <div>
                  <ExclamationTriangleIcon aria-hidden="true" />
                  <h3>Invoice preview unavailable</h3>
                  <p>{error}</p>
                  <p>No partial or unverified document was rendered.</p>
                </div>
              </PreviewState>
            ) : (
              <PreviewState role="status" aria-live="polite">
                <div>
                  <ArrowPathIcon aria-hidden="true" />
                  <h3>Generating canonical preview</h3>
                  <p>
                    Loading the immutable invoice snapshot and its current
                    allocation and credit effects.
                  </p>
                </div>
              </PreviewState>
            )}
          </PreviewScroll>
        </PreviewSurface>
      </PreviewBackdrop>
    </>
  );

  return createPortal(
    <div className="billing-invoice-preview-portal">{content}</div>,
    document.body,
  );
}
