// ============================================
// Invoice Table Component
// ============================================

import React from 'react';
import {
  PencilIcon,
  DocumentDuplicateIcon,
  TrashIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowDownTrayIcon,
  PaperAirplaneIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import type { Invoice } from '../../types';
import { InvoiceStatusBadge } from '../common/StatusBadge';
import { formatCurrencyIntl, formatDate } from '../../utils/formatters';

interface InvoiceTableProps {
  invoices: Invoice[];
  onEdit: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string, invoiceNumber: string) => void;
  onStatusChange: (id: string, status: string) => void;
  onSend: (invoice: Invoice) => void;
  onPrint: (invoice: Invoice) => void;
}

export const InvoiceTable: React.FC<InvoiceTableProps> = ({
  invoices,
  onEdit,
  onDuplicate,
  onDelete,
  onStatusChange,
  onSend,
  onPrint,
}) => {
  return (
    <>
      {/* Desktop Table View */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Status</th>
              <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Invoice #</th>
              <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Client</th>
              <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Date</th>
              <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Amount</th>
              <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Balance</th>
              <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {invoices.map((invoice) => (
              <InvoiceRow
                key={invoice.id}
                invoice={invoice}
                onEdit={onEdit}
                onDuplicate={onDuplicate}
                onDelete={onDelete}
                onStatusChange={onStatusChange}
                onSend={onSend}
                onPrint={onPrint}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden divide-y divide-gray-100">
        {invoices.map((invoice) => (
          <InvoiceCard
            key={invoice.id}
            invoice={invoice}
            onEdit={onEdit}
            onDuplicate={onDuplicate}
            onDelete={onDelete}
            onStatusChange={onStatusChange}
            onSend={onSend}
            onPrint={onPrint}
          />
        ))}
      </div>
    </>
  );
};

// -------------------- Invoice Row --------------------

interface InvoiceRowProps {
  invoice: Invoice;
  onEdit: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string, invoiceNumber: string) => void;
  onStatusChange: (id: string, status: string) => void;
  onSend: (invoice: Invoice) => void;
  onPrint: (invoice: Invoice) => void;
}

const InvoiceRow: React.FC<InvoiceRowProps> = ({
  invoice,
  onEdit,
  onDuplicate,
  onDelete,
  onStatusChange,
  onSend,
  onPrint,
}) => {
  const hasRecipientEmail = invoice.recipient?.contact_email || invoice.client_email;
  const hasInvalidDates = new Date(invoice.due_date) < new Date(invoice.issue_date);

  return (
    <tr className={hasInvalidDates ? 'bg-amber-50/60 hover:bg-amber-50' : 'hover:bg-gray-50'}>
      <td className="px-6 py-4">
        <InvoiceStatusBadge status={invoice.status} />
      </td>
      <td className="px-6 py-4">
        <p className="font-mono font-medium text-gray-900">{invoice.invoice_number}</p>
        {invoice.file_number && (
          <p className="text-xs text-gray-500">File: {invoice.file_number}</p>
        )}
      </td>
      <td className="px-6 py-4">
        <p className="text-gray-900">{invoice.client_name || invoice.family?.name || '-'}</p>
      </td>
      <td className="px-6 py-4">
        <p className="text-gray-900">{formatDate(invoice.issue_date)}</p>
        <p className="text-xs text-gray-500">Due: {formatDate(invoice.due_date)}</p>
        {hasInvalidDates && <p className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-amber-700"><ExclamationTriangleIcon className="h-3.5 w-3.5" />Invalid legacy dates</p>}
      </td>
      <td className="px-6 py-4 text-right">
        <p className="font-medium text-gray-900">{formatCurrencyIntl(invoice.total_amount)}</p>
      </td>
      <td className="px-6 py-4 text-right">
        <p className={`font-medium ${invoice.balance_due > 0 ? 'text-red-600' : 'text-green-600'}`}>
          {formatCurrencyIntl(invoice.balance_due)}
        </p>
      </td>
      <td className="px-6 py-4">
        <div className="flex justify-end gap-1">
          {/* Send Email */}
          <button
            onClick={() => onSend(invoice)}
            className={`p-1.5 rounded ${hasRecipientEmail ? 'text-gray-400 hover:text-primary-600' : 'text-gray-300 cursor-not-allowed'}`}
            title={hasRecipientEmail ? 'Send Invoice' : 'No recipient configured'}
            disabled={!hasRecipientEmail}
          >
            <PaperAirplaneIcon className="w-4 h-4" />
          </button>

          {/* Download/Print */}
          <button
            onClick={() => onPrint(invoice)}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded"
            title="Download PDF"
          >
            <ArrowDownTrayIcon className="w-4 h-4" />
          </button>

          {/* Edit (only draft) */}
          {invoice.status === 'draft' && (
            <button
              onClick={() => onEdit(invoice.id)}
              className="p-1.5 text-gray-400 hover:text-blue-600 rounded"
              title="Edit"
            >
              <PencilIcon className="w-4 h-4" />
            </button>
          )}

          {/* Duplicate */}
          <button
            onClick={() => onDuplicate(invoice.id)}
            className="p-1.5 text-gray-400 hover:text-purple-600 rounded"
            title="Duplicate"
          >
            <DocumentDuplicateIcon className="w-4 h-4" />
          </button>

          {/* Status actions */}
          {invoice.status === 'draft' && (
            <button
              onClick={() => onStatusChange(invoice.id, 'sent')}
              className="p-1.5 text-gray-400 hover:text-blue-600 rounded"
              title="Mark as Sent"
            >
              <ClockIcon className="w-4 h-4" />
            </button>
          )}
          {(invoice.status === 'sent' || invoice.status === 'overdue') && (
            <button
              onClick={() => onStatusChange(invoice.id, 'paid')}
              className="p-1.5 text-gray-400 hover:text-green-600 rounded"
              title="Mark as Paid"
            >
              <CheckCircleIcon className="w-4 h-4" />
            </button>
          )}

          {/* Delete (only draft) */}
          {invoice.status === 'draft' && (
            <button
              onClick={() => onDelete(invoice.id, invoice.invoice_number)}
              className="p-1.5 text-gray-400 hover:text-red-600 rounded"
              title="Delete"
            >
              <TrashIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
};

// -------------------- Mobile Invoice Card --------------------

const InvoiceCard: React.FC<InvoiceRowProps> = ({
  invoice,
  onEdit,
  onDuplicate,
  onDelete,
  onStatusChange,
  onSend,
  onPrint,
}) => {
  const hasRecipientEmail = invoice.recipient?.contact_email || invoice.client_email;
  const hasInvalidDates = new Date(invoice.due_date) < new Date(invoice.issue_date);

  return (
    <div className="p-4 hover:bg-gray-50">
      {/* Top Row: Status + Invoice Number */}
      <div className="flex items-center justify-between mb-2">
        <InvoiceStatusBadge status={invoice.status} />
        <span className="font-mono text-sm font-medium text-gray-900">{invoice.invoice_number}</span>
      </div>

      {/* Client Name */}
      <p className="text-sm font-medium text-gray-900 mb-1 truncate">
        {invoice.client_name || invoice.family?.name || '-'}
      </p>

      {/* Date + Amount Row */}
      <div className="flex items-center justify-between text-sm mb-3">
        <div className="text-gray-500">
          <span>{formatDate(invoice.issue_date)}</span>
          {invoice.file_number && (
            <span className="ml-2 text-xs text-gray-400">File: {invoice.file_number}</span>
          )}
        </div>
        <div className="text-right">
          <p className="font-medium text-gray-900">{formatCurrencyIntl(invoice.total_amount)}</p>
          <p className={`text-xs ${invoice.balance_due > 0 ? 'text-red-600' : 'text-green-600'}`}>
            Bal: {formatCurrencyIntl(invoice.balance_due)}
          </p>
        </div>
      </div>
      {hasInvalidDates && <p className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-amber-700"><ExclamationTriangleIcon className="h-3.5 w-3.5" />Due date is before issue date</p>}

      {/* Actions Row */}
      <div className="flex items-center justify-end gap-2 pt-2 border-t border-gray-100">
        {/* Send Email */}
        <button
          onClick={() => onSend(invoice)}
          className={`p-2 rounded-lg ${hasRecipientEmail ? 'text-gray-600 hover:bg-primary-50 hover:text-primary-600' : 'text-gray-300 cursor-not-allowed'}`}
          title={hasRecipientEmail ? 'Send Invoice' : 'No recipient configured'}
          disabled={!hasRecipientEmail}
        >
          <PaperAirplaneIcon className="w-5 h-5" />
        </button>

        {/* Download/Print */}
        <button
          onClick={() => onPrint(invoice)}
          className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          title="Download PDF"
        >
          <ArrowDownTrayIcon className="w-5 h-5" />
        </button>

        {/* Edit (only draft) */}
        {invoice.status === 'draft' && (
          <button
            onClick={() => onEdit(invoice.id)}
            className="p-2 text-gray-600 hover:bg-blue-50 hover:text-blue-600 rounded-lg"
            title="Edit"
          >
            <PencilIcon className="w-5 h-5" />
          </button>
        )}

        {/* Duplicate */}
        <button
          onClick={() => onDuplicate(invoice.id)}
          className="p-2 text-gray-600 hover:bg-purple-50 hover:text-purple-600 rounded-lg"
          title="Duplicate"
        >
          <DocumentDuplicateIcon className="w-5 h-5" />
        </button>

        {/* Status actions */}
        {invoice.status === 'draft' && (
          <button
            onClick={() => onStatusChange(invoice.id, 'sent')}
            className="p-2 text-gray-600 hover:bg-blue-50 hover:text-blue-600 rounded-lg"
            title="Mark as Sent"
          >
            <ClockIcon className="w-5 h-5" />
          </button>
        )}
        {(invoice.status === 'sent' || invoice.status === 'overdue') && (
          <button
            onClick={() => onStatusChange(invoice.id, 'paid')}
            className="p-2 text-gray-600 hover:bg-green-50 hover:text-green-600 rounded-lg"
            title="Mark as Paid"
          >
            <CheckCircleIcon className="w-5 h-5" />
          </button>
        )}

        {/* Delete (only draft) */}
        {invoice.status === 'draft' && (
          <button
            onClick={() => onDelete(invoice.id, invoice.invoice_number)}
            className="p-2 text-gray-600 hover:bg-red-50 hover:text-red-600 rounded-lg"
            title="Delete"
          >
            <TrashIcon className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
};

// -------------------- Table Pagination --------------------

interface TablePaginationProps {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  onPageChange: (page: number) => void;
}

export const TablePagination: React.FC<TablePaginationProps> = ({
  page,
  pageSize,
  total,
  hasMore,
  onPageChange,
}) => {
  if (total <= pageSize) return null;

  return (
    <div className="p-4 border-t border-gray-200 flex justify-between items-center">
      <p className="text-sm text-gray-500">
        Showing {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, total)} of {total}
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page === 1}
          className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50"
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={!hasMore}
          className="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
};
