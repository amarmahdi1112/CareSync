// ============================================
// Credit Notes View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  ReceiptRefundIcon,
  PlusIcon,
  CheckCircleIcon,
  ClockIcon,
  BanknotesIcon
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { CreditNote } from '../types';

// Components
import { StatCard, StatsGrid } from '../components/common/StatCard';
import { EmptyState, CenteredLoading } from '../components/common/EmptyState';
import { CreditStatusBadge } from '../components/common/StatusBadge';
import { Modal, ModalButton } from '../components/common/Modal';

// Utils
import { formatCurrencyIntl, formatDate } from '../utils/formatters';
import { DEFAULT_CREDIT_FORM } from '../constants';

// Minimal invoice type for apply credit modal
interface OutstandingInvoice {
  id: string;
  invoice_number: string;
  client_name?: string;
  total_amount: number;
  balance_due: number;
  status: string;
}

const Credits: React.FC = () => {
  const { addNotification } = useNotifications();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [selectedCredit, setSelectedCredit] = useState<CreditNote | null>(null);
  const [applyAmount, setApplyAmount] = useState('');
  const [newCredit, setNewCredit] = useState(DEFAULT_CREDIT_FORM);
  const [creating, setCreating] = useState(false);
  const [applying, setApplying] = useState(false);

  const { data: creditNotes = [], loading, refetch } = useApiQuery<CreditNote[]>('/invoicing/credits');

  // Fetch outstanding invoices for "Apply Credit" modal
  const { data: invoicesData } = useApiQuery<{ items: OutstandingInvoice[] }>('/invoicing/invoices', { status: 'sent', limit: 100 });
  // Combine sent + overdue invoices as "outstanding"
  const { data: overdueData } = useApiQuery<{ items: OutstandingInvoice[] }>('/invoicing/invoices', { status: 'overdue', limit: 100 });
  const outstandingInvoices: OutstandingInvoice[] = [
    ...(invoicesData?.items || []),
    ...(overdueData?.items || []),
  ];

  // Helpers
  const resetForm = () => setNewCredit(DEFAULT_CREDIT_FORM);

  const handleCreateCredit = async () => {
    if (!newCredit.amount || !newCredit.reason) {
      addNotification({ type: 'error', title: 'Missing Fields', message: 'Please fill in all required fields.' });
      return;
    }

    setCreating(true);
    try {
      await api.post('/invoicing/credits', {
          amount: parseFloat(newCredit.amount),
          reason: newCredit.reason,
          description: newCredit.description || undefined,
          client_name: newCredit.client_name || undefined,
          issue_date: new Date().toISOString().split('T')[0],
      });
      await refetch();
      setShowCreateModal(false);
      resetForm();
      addNotification({ type: 'success', title: 'Credit Note Created', message: 'Credit note has been created.' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setCreating(false);
    }
  };

  const setCreditStatus = async (id: string, status: 'issued' | 'void') => {
    try {
      await api.patch(`/invoicing/credits/${id}/status`, { status });
      await refetch();
      addNotification({ type: 'success', title: status === 'issued' ? 'Credit Issued' : 'Credit Voided', message: `Credit note has been ${status}.` });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    }
  };

  const removeCredit = async (id: string) => {
    try {
      await api.delete(`/invoicing/credits/${id}`);
      await refetch();
      addNotification({ type: 'success', title: 'Credit Deleted', message: 'Credit note has been deleted.' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    }
  };

  const handleApplyCredit = async (invoiceId: string, invoiceBalance: number) => {
    if (!selectedCredit) return;
    
    // Determine amount to apply: use custom amount or max possible
    const creditBalance = selectedCredit.balance;
    const amountToApply = applyAmount 
      ? Math.min(parseFloat(applyAmount), creditBalance, invoiceBalance)
      : Math.min(creditBalance, invoiceBalance);
    
    if (amountToApply <= 0) {
      addNotification({ type: 'error', title: 'Invalid Amount', message: 'Amount must be greater than 0.' });
      return;
    }

    setApplying(true);
    try {
      await api.post(`/invoicing/credits/${selectedCredit.id}/apply`, {
          invoice_id: invoiceId,
          amount: amountToApply,
      });
      await refetch();
      setShowApplyModal(false);
      setSelectedCredit(null);
      setApplyAmount('');
      addNotification({ type: 'success', title: 'Credit Applied', message: 'Credit has been applied to the invoice.' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setApplying(false);
    }
  };

  // Stats
  const totalPending = creditNotes.filter(c => c.status === 'draft' || c.status === 'issued').reduce((sum, c) => sum + c.balance, 0);
  const totalApplied = creditNotes.filter(c => c.status === 'partially_applied' || c.status === 'fully_applied').reduce((sum, c) => sum + c.amount_applied, 0);
  const totalBalance = creditNotes.reduce((sum, c) => sum + c.balance, 0);

  if (loading) return <CenteredLoading />;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          icon={<ClockIcon className="w-6 h-6 text-yellow-600" />}
          iconBg="bg-yellow-100"
          label="Pending Credits"
          value={formatCurrencyIntl(totalPending)}
          valueColor="text-yellow-600"
        />
        <StatCard
          icon={<CheckCircleIcon className="w-6 h-6 text-green-600" />}
          iconBg="bg-green-100"
          label="Applied to Invoices"
          value={formatCurrencyIntl(totalApplied)}
          valueColor="text-green-600"
        />
        <StatCard
          icon={<BanknotesIcon className="w-6 h-6 text-blue-600" />}
          iconBg="bg-blue-100"
          label="Available Balance"
          value={formatCurrencyIntl(totalBalance)}
          valueColor="text-blue-600"
        />
        <StatCard
          icon={<ReceiptRefundIcon className="w-6 h-6 text-purple-600" />}
          iconBg="bg-purple-100"
          label="Total Credit Notes"
          value={creditNotes.length}
          valueColor="text-purple-600"
        />
      </StatsGrid>

      {/* Credit Notes List */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="p-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Credit Notes & Refunds</h2>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <PlusIcon className="w-5 h-5" />
            Issue Credit Note
          </button>
        </div>

        {creditNotes.length === 0 ? (
          <EmptyState
            icon={<ReceiptRefundIcon className="w-12 h-12" />}
            title="No Credit Notes"
            description="Issue credit notes for overpayments or refunds."
            action={{
              label: 'Issue Credit Note',
              onClick: () => setShowCreateModal(true),
              icon: <PlusIcon className="w-5 h-5" />,
            }}
          />
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Credit Note</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Client</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Reason</th>
                <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Amount</th>
                <th className="text-center text-xs font-medium text-gray-500 uppercase px-6 py-3">Status</th>
                <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {creditNotes.map((credit) => (
                <tr key={credit.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <p className="font-mono font-medium text-gray-900">{credit.credit_note_number}</p>
                    <p className="text-xs text-gray-500">{formatDate(credit.created_at)}</p>
                    {credit.invoice && (
                      <p className="text-xs text-gray-400">From: {credit.invoice.invoice_number}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-900">{credit.client_name || credit.family?.name || '-'}</td>
                  <td className="px-6 py-4">
                    <p className="text-sm text-gray-600 max-w-xs truncate">{credit.reason || credit.description || '-'}</p>
                    {credit.amount_applied > 0 && (
                      <p className="text-xs text-green-600 mt-1">Applied: {formatCurrencyIntl(credit.amount_applied)}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <p className="font-bold text-gray-900">{formatCurrencyIntl(credit.amount)}</p>
                    {credit.balance < credit.amount && credit.balance > 0 && (
                      <p className="text-xs text-blue-600">Remaining: {formatCurrencyIntl(credit.balance)}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <CreditStatusBadge status={credit.status} />
                  </td>
                  <td className="px-6 py-4">
                    {(credit.status === 'draft' || credit.status === 'issued') && (
                      <div className="flex justify-end gap-1">
                        {credit.status === 'draft' && (
                          <button
                            onClick={() => void setCreditStatus(credit.id, 'issued')}
                            className="px-2 py-1 text-xs bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200"
                          >
                            Issue
                          </button>
                        )}
                        {credit.balance > 0 && (
                          <button
                            onClick={() => { setSelectedCredit(credit); setApplyAmount(''); setShowApplyModal(true); }}
                            className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200"
                          >
                            Apply
                          </button>
                        )}
                        <button
                          onClick={() => { if (confirm(`Void credit note ${credit.credit_note_number}?`)) void setCreditStatus(credit.id, 'void'); }}
                          className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
                        >
                          Void
                        </button>
                        <button
                          onClick={() => { if (confirm(`Delete credit note ${credit.credit_note_number}?`)) void removeCredit(credit.id); }}
                          className="px-2 py-1 text-xs bg-red-100 text-red-600 rounded hover:bg-red-200"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create Credit Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Issue Credit Note"
        maxWidth="lg"
        footer={
          <>
            <ModalButton variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </ModalButton>
            <ModalButton onClick={handleCreateCredit} loading={creating}>
              Issue Credit Note
            </ModalButton>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Client Name *</label>
            <input
              type="text"
              value={newCredit.client_name}
              onChange={(e) => setNewCredit(prev => ({ ...prev, client_name: e.target.value }))}
              className="w-full input"
              placeholder="Enter client name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Amount *</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
              <input
                type="number"
                step="0.01"
                value={newCredit.amount}
                onChange={(e) => setNewCredit(prev => ({ ...prev, amount: e.target.value }))}
                className="w-full pl-8 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                placeholder="0.00"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason *</label>
            <textarea
              value={newCredit.reason}
              onChange={(e) => setNewCredit(prev => ({ ...prev, reason: e.target.value }))}
              rows={3}
              className="w-full input"
              placeholder="Reason for issuing this credit"
            />
          </div>
        </div>
      </Modal>

      {/* Apply Credit Modal — Now using real outstanding invoices */}
      <Modal
        isOpen={showApplyModal && !!selectedCredit}
        onClose={() => { setShowApplyModal(false); setSelectedCredit(null); }}
        title="Apply Credit to Invoice"
        maxWidth="lg"
      >
        {selectedCredit && (
          <div>
            <div className="bg-gray-50 rounded-lg p-4 mb-4">
              <p className="text-sm text-gray-600">Applying credit:</p>
              <p className="text-lg font-bold text-gray-900">{selectedCredit.credit_note_number}</p>
              <div className="flex items-center gap-4 mt-2">
                <div>
                  <p className="text-xs text-gray-500">Total Amount</p>
                  <p className="text-lg font-bold text-gray-900">{formatCurrencyIntl(selectedCredit.amount)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Available Balance</p>
                  <p className="text-2xl font-bold text-green-600">{formatCurrencyIntl(selectedCredit.balance)}</p>
                </div>
              </div>
            </div>

            {/* Custom amount input */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Amount to Apply (leave blank to apply max possible)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
                <input
                  type="number"
                  step="0.01"
                  max={selectedCredit.balance}
                  value={applyAmount}
                  onChange={(e) => setApplyAmount(e.target.value)}
                  className="w-full pl-8 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder={`Up to ${formatCurrencyIntl(selectedCredit.balance)}`}
                />
              </div>
            </div>

            <p className="text-sm text-gray-600 mb-3">Select an invoice to apply this credit to:</p>
            
            {outstandingInvoices.length === 0 ? (
              <div className="text-center py-6 text-gray-500">
                <p className="font-medium">No outstanding invoices</p>
                <p className="text-sm">All invoices are either paid or in draft status.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {outstandingInvoices.map((inv) => {
                  const effectiveAmount = applyAmount 
                    ? Math.min(parseFloat(applyAmount) || 0, selectedCredit.balance, inv.balance_due)
                    : Math.min(selectedCredit.balance, inv.balance_due);
                  
                  return (
                    <button
                      key={inv.id}
                      onClick={() => handleApplyCredit(inv.id, inv.balance_due)}
                      disabled={applying}
                      className="w-full flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-primary-300 transition-colors disabled:opacity-50"
                    >
                      <div className="text-left">
                        <span className="font-medium text-gray-900">{inv.invoice_number}</span>
                        {inv.client_name && (
                          <span className="text-sm text-gray-500 ml-2">— {inv.client_name}</span>
                        )}
                        <p className="text-xs text-gray-400">
                          Balance: {formatCurrencyIntl(inv.balance_due)}
                          {inv.status === 'overdue' && (
                            <span className="ml-2 px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-xs">Overdue</span>
                          )}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-primary-600 font-medium">
                          Apply {formatCurrencyIntl(effectiveAmount)}
                        </span>
                        <span className="text-primary-600 ml-1">→</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Credits;
