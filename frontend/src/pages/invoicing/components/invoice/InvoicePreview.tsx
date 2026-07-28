// ============================================
// Invoice Preview Component (Live Preview Panel)
// ============================================

import React from 'react';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import type { LineItem, InvoiceSettings } from '../../types';
import type { InvoiceTotals } from '../../utils/calculations';
import { calculateLineItemAmount } from '../../utils/calculations';
import { formatCurrency } from '../../utils/formatters';
import { config } from '../../../../config';

interface InvoicePreviewProps {
  settings: InvoiceSettings | null | undefined;
  clientName: string;
  clientEmail: string;
  clientAddress: string;
  fileNumber: string;
  issueDate: string;
  dueDate: string;
  periodStart?: string;
  periodEnd?: string;
  lineItems: LineItem[];
  totals: InvoiceTotals;
  taxRate: number;
  notes: string;
  terms: string;
  currencySymbol?: string;
}

export const InvoicePreview: React.FC<InvoicePreviewProps> = ({
  settings,
  clientName,
  clientEmail,
  clientAddress,
  fileNumber,
  issueDate,
  dueDate,
  periodStart,
  periodEnd,
  lineItems,
  totals,
  taxRate,
  notes,
  terms,
  currencySymbol = '$',
}) => {
  return (
    <div className="lg:sticky lg:top-8 lg:self-start">
      {/* Mobile Preview Label */}
      <div className="lg:hidden mb-3 flex items-center gap-2 text-sm font-medium text-gray-500">
        <DocumentTextIcon className="w-4 h-4" />
        <span>Preview</span>
      </div>
      
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-4 sm:p-6 lg:p-8">
        {/* Invoice Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start gap-4 sm:gap-2 mb-6 sm:mb-8">
          <div>
            {settings?.company_logo ? (
              <img src={config.getUploadUrl(settings.company_logo)} alt="Logo" className="h-10 sm:h-12 mb-2" />
            ) : (
              <div className="w-10 h-10 sm:w-12 sm:h-12 bg-primary-100 rounded-lg flex items-center justify-center mb-2">
                <DocumentTextIcon className="w-5 h-5 sm:w-6 sm:h-6 text-primary-600" />
              </div>
            )}
            <h3 className="font-bold text-gray-900 text-sm sm:text-base">{settings?.company_name || 'Your Company'}</h3>
            <p className="text-xs sm:text-sm text-gray-500">{settings?.company_address}</p>
            <p className="text-xs sm:text-sm text-gray-500">
              {settings?.company_city}
              {settings?.company_province ? `, ${settings.company_province}` : ''} {settings?.company_postal_code}
            </p>
            <p className="text-xs sm:text-sm text-gray-500">{settings?.company_phone}</p>
            <p className="text-xs sm:text-sm text-gray-500">{settings?.company_email}</p>
          </div>
          <div className="text-left sm:text-right">
            <h2 className="text-xl sm:text-2xl font-bold text-gray-900">INVOICE</h2>
            <p className="text-sm sm:text-lg text-primary-600 font-mono italic">Auto-generated</p>
            {fileNumber && (
              <p className="text-xs sm:text-sm text-gray-500">File #: {fileNumber}</p>
            )}
          </div>
        </div>

        {/* Bill To & Dates */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-8 mb-6 sm:mb-8">
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Bill To</h4>
            <p className="font-medium text-gray-900">{clientName || 'Client Name'}</p>
            <p className="text-sm text-gray-600">{clientEmail}</p>
            <p className="text-sm text-gray-600">{clientAddress}</p>
          </div>
          <div className="text-right">
            <div className="mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase">Invoice Date</span>
              <p className="text-gray-900">{issueDate}</p>
            </div>
            <div className="mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase">Due Date</span>
              <p className="text-gray-900">{dueDate}</p>
            </div>
            {(periodStart || periodEnd) && (
              <div>
                <span className="text-xs font-semibold text-gray-500 uppercase">Period</span>
                <p className="text-gray-900">{periodStart} - {periodEnd}</p>
              </div>
            )}
          </div>
        </div>

        {/* Line Items Table */}
        <table className="w-full mb-6">
          <thead>
            <tr className="border-b-2 border-gray-200">
              <th className="text-left text-xs font-semibold text-gray-500 uppercase pb-2">Description</th>
              <th className="text-right text-xs font-semibold text-gray-500 uppercase pb-2">Amount</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((item) => (
              <tr key={item.id} className="border-b border-gray-100">
                <td className="py-3">
                  <p className="text-gray-900">{item.description || 'Item description'}</p>
                  <p className="text-xs text-gray-500">
                    {item.item_type === 'daycare_subsidy' && item.full_rate && (
                      <>Full: {formatCurrency(item.full_rate, currencySymbol)} - Subsidy: {formatCurrency(item.subsidy_amount || 0, currencySymbol)}</>
                    )}
                    {item.item_type === 'service_hourly' && item.hours && (
                      <>{item.hours} hrs × {formatCurrency(item.hourly_rate || 0, currencySymbol)}/hr</>
                    )}
                    {item.item_type === 'product' && item.quantity && (
                      <>{item.quantity} × {formatCurrency(item.unit_price || 0, currencySymbol)}</>
                    )}
                  </p>
                </td>
                <td className="py-3 text-right font-medium text-gray-900">
                  {formatCurrency(calculateLineItemAmount(item), currencySymbol)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Totals */}
        <div className="border-t-2 border-gray-200 pt-4">
          <div className="flex justify-between mb-1">
            <span className="text-gray-600">Subtotal</span>
            <span className="font-medium">{formatCurrency(totals.subtotal, currencySymbol)}</span>
          </div>
          {totals.discount > 0 && (
            <div className="flex justify-between mb-1 text-green-600">
              <span>Discount</span>
              <span>-{formatCurrency(totals.discount, currencySymbol)}</span>
            </div>
          )}
          {taxRate > 0 && (
            <div className="flex justify-between mb-1">
              <span className="text-gray-600">Tax ({taxRate}%)</span>
              <span className="font-medium">{formatCurrency(totals.taxAmount, currencySymbol)}</span>
            </div>
          )}
          <div className="flex justify-between text-lg font-bold border-t border-gray-200 pt-2 mt-2">
            <span>Total</span>
            <span className="text-primary-600">{formatCurrency(totals.total, currencySymbol)}</span>
          </div>
        </div>

        {/* Notes & Terms */}
        {(notes || terms) && (
          <div className="mt-8 pt-6 border-t border-gray-200">
            {notes && (
              <div className="mb-4">
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Notes</h4>
                <p className="text-sm text-gray-600 whitespace-pre-line">{notes}</p>
              </div>
            )}
            {terms && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Terms & Conditions</h4>
                <p className="text-sm text-gray-600 whitespace-pre-line">{terms}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
