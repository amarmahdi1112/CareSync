// ============================================
// Invoice Print Template (HTML for Print Window)
// ============================================

import type { Invoice, InvoiceSettings, LineItem } from '../../types';
import { formatCurrencyIntl, formatDate } from '../../utils/formatters';
import { config } from '../../../../config';

/**
 * Generate printable HTML for an invoice
 */
export const generatePrintableInvoice = (
  invoice: Invoice,
  settings: InvoiceSettings | null | undefined
): string => {
  const getLineItemDetails = (item: LineItem): string => {
    if (item.item_type === 'daycare_subsidy' && item.full_rate) {
      return `Full: ${formatCurrencyIntl(item.full_rate)} - Subsidy: ${formatCurrencyIntl(item.subsidy_amount || 0)}`;
    }
    if (item.item_type === 'service_hourly' && item.hours) {
      return `${item.hours} hrs × ${formatCurrencyIntl(item.hourly_rate || 0)}/hr`;
    }
    if (item.item_type === 'product' && item.quantity) {
      return `${item.quantity} × ${formatCurrencyIntl(item.unit_price || 0)}`;
    }
    return '';
  };

  return `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Invoice ${invoice.invoice_number}</title>
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 48px; max-width: 800px; margin: 0 auto; color: #1f2937; }
        .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 48px; }
        .company-info { max-width: 300px; }
        .company-logo { width: 48px; height: 48px; background: #e0e7ff; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; font-size: 24px; }
        .company-name { font-weight: 700; font-size: 16px; color: #1f2937; margin-bottom: 4px; }
        .company-detail { font-size: 13px; color: #6b7280; line-height: 1.5; }
        .invoice-meta { text-align: right; }
        .invoice-title { font-size: 28px; font-weight: 700; color: #1f2937; margin-bottom: 4px; }
        .invoice-number { font-size: 18px; color: #4f46e5; font-family: monospace; margin-bottom: 4px; }
        .file-number { font-size: 13px; color: #6b7280; }
        .billing-section { display: grid; grid-template-columns: 1fr 1fr; gap: 48px; margin-bottom: 32px; }
        .section-label { font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .client-name { font-weight: 500; font-size: 15px; color: #1f2937; }
        .client-detail { font-size: 13px; color: #4b5563; line-height: 1.5; }
        .dates { text-align: right; }
        .date-row { margin-bottom: 8px; }
        .date-value { font-weight: 500; color: #1f2937; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
        th { text-align: left; padding: 12px 0; border-bottom: 2px solid #e5e7eb; font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
        th.amount { text-align: right; }
        td { padding: 16px 0; border-bottom: 1px solid #f3f4f6; }
        td.amount { text-align: right; font-weight: 500; }
        .item-description { font-weight: 500; color: #1f2937; }
        .item-details { font-size: 12px; color: #6b7280; margin-top: 2px; }
        .totals { margin-left: auto; width: 280px; border-top: 2px solid #e5e7eb; padding-top: 16px; }
        .total-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; }
        .total-row span:first-child { color: #6b7280; }
        .total-row span:last-child { font-weight: 500; }
        .total-row.discount { color: #059669; }
        .total-row.discount span { color: #059669; }
        .total-row.grand { font-size: 18px; font-weight: 700; border-top: 1px solid #e5e7eb; margin-top: 8px; padding-top: 12px; }
        .total-row.grand span:last-child { color: #4f46e5; }
        .notes-section { margin-top: 40px; padding-top: 24px; border-top: 1px solid #e5e7eb; }
        .notes-title { font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .notes-content { font-size: 13px; color: #4b5563; line-height: 1.6; white-space: pre-line; }
        .notes-block { margin-bottom: 20px; }
        @media print { 
          body { padding: 24px; } 
          @page { margin: 0.5in; }
        }
      </style>
    </head>
    <body>
      <div class="header">
        <div class="company-info">
          ${settings?.company_logo 
            ? `<img src="${config.getUploadUrl(settings.company_logo)}" alt="Logo" style="height: 48px; margin-bottom: 12px;">` 
            : '<div class="company-logo">📄</div>'}
          <div class="company-name">${settings?.company_name || 'Your Company'}</div>
          <div class="company-detail">${settings?.company_address || ''}</div>
          <div class="company-detail">${settings?.company_city || ''}${settings?.company_province ? `, ${settings.company_province}` : ''} ${settings?.company_postal_code || ''}</div>
          <div class="company-detail">${settings?.company_phone || ''}</div>
          <div class="company-detail">${settings?.company_email || ''}</div>
        </div>
        <div class="invoice-meta">
          <div class="invoice-title">INVOICE</div>
          <div class="invoice-number">${invoice.invoice_number}</div>
          ${invoice.file_number ? `<div class="file-number">File #: ${invoice.file_number}</div>` : ''}
        </div>
      </div>

      <div class="billing-section">
        <div>
          <div class="section-label">Bill To</div>
          <div class="client-name">${invoice.client_name || invoice.family?.name || 'Client'}</div>
          ${invoice.client_email ? `<div class="client-detail">${invoice.client_email}</div>` : ''}
          ${invoice.client_address ? `<div class="client-detail">${invoice.client_address}</div>` : ''}
        </div>
        <div class="dates">
          <div class="date-row">
            <div class="section-label">Invoice Date</div>
            <div class="date-value">${formatDate(invoice.issue_date)}</div>
          </div>
          <div class="date-row">
            <div class="section-label">Due Date</div>
            <div class="date-value">${formatDate(invoice.due_date)}</div>
          </div>
          ${invoice.period_start && invoice.period_end ? `
            <div class="date-row">
              <div class="section-label">Period</div>
              <div class="date-value">${formatDate(invoice.period_start)} - ${formatDate(invoice.period_end)}</div>
            </div>
          ` : ''}
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Description</th>
            <th class="amount">Amount</th>
          </tr>
        </thead>
        <tbody>
          ${(invoice.line_items || []).map(item => `
            <tr>
              <td>
                <div class="item-description">${item.description || 'Service'}</div>
                ${getLineItemDetails(item) ? `<div class="item-details">${getLineItemDetails(item)}</div>` : ''}
              </td>
              <td class="amount">${formatCurrencyIntl(item.amount || 0)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>

      <div class="totals">
        <div class="total-row">
          <span>Subtotal</span>
          <span>${formatCurrencyIntl(invoice.subtotal)}</span>
        </div>
        ${(invoice.discount_amount && invoice.discount_amount > 0) ? `
          <div class="total-row discount">
            <span>Discount${invoice.discount_percentage ? ` (${invoice.discount_percentage}%)` : ''}</span>
            <span>-${formatCurrencyIntl(invoice.discount_amount)}</span>
          </div>
        ` : ''}
        ${(invoice.tax_rate && invoice.tax_rate > 0) ? `
          <div class="total-row">
            <span>Tax (${invoice.tax_rate}%)</span>
            <span>${formatCurrencyIntl(invoice.tax_amount || 0)}</span>
          </div>
        ` : ''}
        <div class="total-row grand">
          <span>Total</span>
          <span>${formatCurrencyIntl(invoice.total_amount)}</span>
        </div>
        ${invoice.amount_paid > 0 ? `
          <div class="total-row">
            <span>Amount Paid</span>
            <span>${formatCurrencyIntl(invoice.amount_paid)}</span>
          </div>
          <div class="total-row" style="font-weight: 600;">
            <span>Balance Due</span>
            <span style="color: ${invoice.balance_due > 0 ? '#dc2626' : '#059669'};">${formatCurrencyIntl(invoice.balance_due)}</span>
          </div>
        ` : ''}
      </div>

      ${invoice.notes || invoice.terms ? `
        <div class="notes-section">
          ${invoice.notes ? `
            <div class="notes-block">
              <div class="notes-title">Notes</div>
              <div class="notes-content">${invoice.notes}</div>
            </div>
          ` : ''}
          ${invoice.terms ? `
            <div class="notes-block">
              <div class="notes-title">Terms & Conditions</div>
              <div class="notes-content">${invoice.terms}</div>
            </div>
          ` : ''}
        </div>
      ` : ''}
    </body>
    </html>
  `;
};

/**
 * Open invoice in a new window and print
 */
export const printInvoice = (invoice: Invoice, settings: InvoiceSettings | null | undefined): void => {
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;

  const html = generatePrintableInvoice(invoice, settings);
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.onload = () => {
    printWindow.print();
  };
};
