// ============================================
// Send Invoice Modal Component
// ============================================

import React, { useState } from 'react';
import { EnvelopeIcon, PaperAirplaneIcon, XMarkIcon } from '@heroicons/react/24/outline';
import type { Invoice } from '../../types';
import { formatCurrencyIntl } from '../../utils/formatters';
import { BaseModal, AlertBanner } from '../common/Modal';

interface SendInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  invoice: Invoice | null;
  onSend: (invoiceId: string, customMessage?: string) => void;
  loading?: boolean;
  status?: { type: 'success' | 'error'; message: string } | null;
}

export const SendInvoiceModal: React.FC<SendInvoiceModalProps> = ({
  isOpen,
  onClose,
  invoice,
  onSend,
  loading = false,
  status = null,
}) => {
  const [customMessage, setCustomMessage] = useState('');

  if (!invoice) return null;

  const recipientEmail = invoice.recipient?.contact_email || invoice.client_email;
  const recipientName = invoice.recipient?.name || invoice.client_name || 'Client';

  const handleSend = () => {
    onSend(invoice.id, customMessage || undefined);
  };

  const handleClose = () => {
    setCustomMessage('');
    onClose();
  };

  return (
    <BaseModal isOpen={isOpen} onClose={handleClose} maxWidth="md">
      <div className="flex items-center justify-between p-6 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-100 rounded-lg">
            <EnvelopeIcon className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Send Invoice</h3>
            <p className="text-sm text-gray-500">{invoice.invoice_number}</p>
          </div>
        </div>
        <button
          onClick={handleClose}
          className="p-2 text-gray-400 hover:text-gray-600 rounded-lg"
        >
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>

      <div className="p-6 space-y-4">
        {status && (
          <AlertBanner type={status.type} message={status.message} />
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Send To</label>
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="font-medium text-gray-900">{recipientName}</p>
            <p className="text-sm text-gray-600">{recipientEmail}</p>
            {invoice.recipient && (
              <p className="text-xs text-primary-600 mt-1">Funding Agency</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Invoice For</label>
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="font-medium text-gray-900">
              {invoice.client_name || invoice.family?.name || 'Client'}
            </p>
            {invoice.file_number && (
              <p className="text-sm text-gray-600">File #: {invoice.file_number}</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Invoice Amount</label>
          <p className="text-2xl font-bold text-primary-600">
            {formatCurrencyIntl(invoice.total_amount)}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Custom Message <span className="text-gray-400">(optional)</span>
          </label>
          <textarea
            value={customMessage}
            onChange={(e) => setCustomMessage(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 resize-none"
            placeholder="Add a personal note to include with the invoice..."
          />
        </div>
      </div>

      <div className="flex gap-3 p-6 border-t border-gray-200">
        <button
          onClick={handleClose}
          className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          onClick={handleSend}
          disabled={loading || status?.type === 'success'}
          className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Sending...
            </>
          ) : (
            <>
              <PaperAirplaneIcon className="w-4 h-4" />
              Send Invoice
            </>
          )}
        </button>
      </div>
    </BaseModal>
  );
};
