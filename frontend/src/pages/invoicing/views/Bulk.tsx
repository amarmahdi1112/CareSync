// ============================================
// Bulk Operations View (Refactored)
// ============================================

import React, { useState, useCallback } from 'react';
import {
  DocumentDuplicateIcon,
  EnvelopeIcon,
  PrinterIcon,
  ArrowDownTrayIcon,
  CheckCircleIcon,
  UserGroupIcon,
  CurrencyDollarIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  PlusCircleIcon
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { Family, Invoice, InvoiceSettings, FundingSource } from '../types';

// Components
import { StatCard, StatsGrid } from '../components/common/StatCard';
import { CenteredLoading, ProcessingOverlay } from '../components/common/EmptyState';
import { Modal, ModalButton } from '../components/common/Modal';
import { DateRangePicker } from '../components/forms/ClientSelector';
import { generatePrintableInvoice } from '../components/invoice/InvoicePrintTemplate';

// Utils
import { formatCurrencyIntl, formatDate } from '../utils/formatters';
import { needsInvoice } from '../utils/calculations';
import { getToday, getDateFromNow } from '../utils/formatters';

const Bulk: React.FC = () => {
  const { addNotification } = useNotifications();
  const [selectedFamilies, setSelectedFamilies] = useState<Set<string>>(new Set());
  const [showBatchModal, setShowBatchModal] = useState(false);
  // Default period: 1st of current month → last day of current month
  const [batchPeriod, setBatchPeriod] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth();
    const first = `${y}-${String(m + 1).padStart(2, '0')}-01`;
    const lastDay = new Date(y, m + 1, 0).getDate();
    const last = `${y}-${String(m + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    return { start: first, end: last };
  });
  const [batchDates, setBatchDates] = useState({ issue_date: getToday(), due_date: getDateFromNow(30) });
  const [selectedRecipientId, setSelectedRecipientId] = useState<string>('');
  const [selectedTotal, setSelectedTotal] = useState(0);
  const [isFetchingTotals, setIsFetchingTotals] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processProgress, setProcessProgress] = useState(0);

  const { data: families = [], loading, refetch } = useApiQuery<Family[]>('/families', { limit: 1000 });
  const { data: fundingRows = [] } = useApiQuery<FundingSource[]>('/resources/funding_sources', { limit: 1000 });
  const fundingSources = fundingRows.filter(fs => fs.is_active);

  // Settings for print
  const { data: settings = null } = useApiQuery<InvoiceSettings | null>('/invoicing/settings');

  // Helpers
  const toggleFamily = (id: string) => {
    setSelectedFamilies(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const selectAll = () => {
    if (selectedFamilies.size === families.length) {
      setSelectedFamilies(new Set());
    } else {
      setSelectedFamilies(new Set(families.map(f => f.id)));
    }
  };

  const selectByFundingSource = async (fundingSourceId: string) => {
    const matching = families.filter(f => f.is_recurring_billing && f.recurring_funding_source_id === fundingSourceId);
    if (matching.length === 0) {
      addNotification({ type: 'info', title: 'No Families', message: 'No families found for this funding source.' });
      return;
    }
    setSelectedFamilies(new Set(matching.map(f => f.id)));
    setSelectedRecipientId(fundingSourceId);

    // Fetch real totals from prefilledLineItems
    setIsFetchingTotals(true);
    let total = 0;
    for (const family of matching) {
      try {
        const result = await api.get<{ total_parent_portion: number }>(`/invoicing/prefill/${family.id}`);
        total += result.total_parent_portion || 0;
      } catch { /* skip */ }
    }
    setSelectedTotal(total);
    setIsFetchingTotals(false);
  };

  const calculateSelectedTotal = () => selectedTotal;

  // Helper to fetch the LATEST invoice for each selected family (with full line_items)
  const getInvoicesForSelectedFamilies = useCallback(async (): Promise<Invoice[]> => {
    const allInvoices: Invoice[] = [];
    for (const familyId of Array.from(selectedFamilies)) {
      try {
        // Only get the 1 most recent invoice per family
        const result = await api.get<{ items: Invoice[] }>('/invoicing/invoices', { family_id: familyId, limit: 1 });
        const items = result.items || [];
        if (items.length > 0) {
          // Re-fetch with full line_items for printing
          try {
            const fullResult = await api.get<Invoice>(`/invoicing/invoices/${items[0].id}`);
            allInvoices.push(fullResult || items[0]);
          } catch {
            allInvoices.push(items[0]);
          }
        }
      } catch {
        // Skip families that error
      }
    }
    return allInvoices;
  }, [selectedFamilies]);

  // ---- BULK SEND ----
  const handleBulkSend = async () => {
    if (selectedFamilies.size === 0) {
      addNotification({ type: 'warning', title: 'No Selection', message: 'Please select at least one family.' });
      return;
    }
    setIsProcessing(true);
    try {
      const invoices = await getInvoicesForSelectedFamilies();
      // Only send draft or sent invoices (not already paid/cancelled)
      const sendableIds = invoices
        .filter(inv => inv.status === 'draft' || inv.status === 'sent')
        .map(inv => inv.id);

      if (sendableIds.length === 0) {
        addNotification({ type: 'info', title: 'Nothing to Send', message: 'No draft or sent invoices found for the selected families.' });
        setIsProcessing(false);
        return;
      }

      // First mark drafts as 'sent'
      const draftIds = invoices.filter(inv => inv.status === 'draft').map(inv => inv.id);
      if (draftIds.length > 0) {
        await api.patch('/invoicing/invoices/bulk-status', { invoice_ids: draftIds, status: 'sent' });
      }

      // Then trigger email send
      await api.post('/invoicing/invoices/bulk-email', { invoice_ids: sendableIds });
      addNotification({ type: 'success', title: 'Invoices Sent', message: `${sendableIds.length} invoice(s) sent successfully.` });
    } catch (err: any) {
      addNotification({ type: 'error', title: 'Send Failed', message: err.message });
    } finally {
      setIsProcessing(false);
    }
  };

  // ---- BULK PRINT ----
  const handleBulkPrint = async () => {
    if (selectedFamilies.size === 0) {
      addNotification({ type: 'warning', title: 'No Selection', message: 'Please select at least one family.' });
      return;
    }
    setIsProcessing(true);
    try {
      const invoices = await getInvoicesForSelectedFamilies();
      if (invoices.length === 0) {
        addNotification({ type: 'info', title: 'Nothing to Print', message: 'No invoices found for the selected families.' });
        setIsProcessing(false);
        return;
      }

      // Build combined HTML for all invoices with page breaks
      const allHtml = invoices.map(inv => generatePrintableInvoice(inv, settings)).join(
        '<div style="page-break-after: always;"></div>'
      );

      // Build summary page
      const fundingSourceName = fundingSources.find(fs => fs.id === selectedRecipientId)?.name || '';
      const periodLabel = invoices[0]?.period_start && invoices[0]?.period_end
        ? `${formatDate(invoices[0].period_start)} — ${formatDate(invoices[0].period_end)}`
        : '';

      type SummaryRow = { child: string; family: string; fullRate: number; subsidy: number; parentPortion: number; invoiceNum: string };
      const rows: SummaryRow[] = [];
      for (const inv of invoices) {
        for (const item of (inv.line_items || [])) {
          rows.push({
            child: item.child_name || item.description || '',
            family: inv.client_name || '',
            fullRate: Number(item.full_rate) || 0,
            subsidy: Number(item.subsidy_amount) || 0,
            parentPortion: Number(item.amount) || 0,
            invoiceNum: inv.invoice_number || '',
          });
        }
      }

      const totals = rows.reduce((acc, r) => ({
        fullRate: acc.fullRate + r.fullRate,
        subsidy: acc.subsidy + r.subsidy,
        parentPortion: acc.parentPortion + r.parentPortion,
      }), { fullRate: 0, subsidy: 0, parentPortion: 0 });

      const summaryHtml = `
        <div style="page-break-before: always;"></div>
        <!DOCTYPE html><html><head>
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 48px; max-width: 800px; margin: 0 auto; color: #1f2937; }
          h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
          .subtitle { font-size: 14px; color: #6b7280; margin-bottom: 32px; }
          .badge { display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-left: 10px; vertical-align: middle; }
          .badge-blue { background: #dbeafe; color: #1d4ed8; }
          .badge-green { background: #d1fae5; color: #047857; }
          table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
          th { text-align: left; padding: 12px 12px; border-bottom: 2px solid #d1d5db; font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
          th.num { text-align: right; }
          td { padding: 12px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }
          td.num { text-align: right; font-weight: 500; font-variant-numeric: tabular-nums; }
          td.idx { color: #9ca3af; font-size: 13px; width: 30px; }
          tr.total-row td { border-top: 2px solid #1f2937; border-bottom: none; font-weight: 700; font-size: 15px; padding-top: 14px; }
          .footer { font-size: 12px; color: #9ca3af; margin-top: 24px; }
          @media print { body { padding: 24px; } @page { margin: 0.5in; } }
        </style>
        </head><body>
          <h1>Invoice Summary${fundingSourceName ? `<span class="badge ${fundingSourceName === 'EMCN' ? 'badge-blue' : 'badge-green'}">${fundingSourceName}</span>` : ''}</h1>
          <div class="subtitle">${periodLabel}${periodLabel ? ' · ' : ''}${settings?.company_name || "Discoverers' Daycare"}</div>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Child Name</th>
                <th>Family</th>
                <th class="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((r, i) => `
                <tr>
                  <td class="idx">${i + 1}</td>
                  <td>${r.child}</td>
                  <td>${r.family}</td>
                  <td class="num">${formatCurrencyIntl(r.parentPortion)}</td>
                </tr>
              `).join('')}
              <tr class="total-row">
                <td></td>
                <td colspan="2">Total (${rows.length} children)</td>
                <td class="num">${formatCurrencyIntl(totals.parentPortion)}</td>
              </tr>
            </tbody>
          </table>
          <div class="footer">Generated ${invoices.length} invoice(s) · Printed ${new Date().toLocaleDateString()}</div>
        </body></html>
      `;

      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(allHtml + summaryHtml);
        printWindow.document.close();
        printWindow.onload = () => printWindow.print();
      }

      addNotification({ type: 'success', title: 'Print Ready', message: `${invoices.length} invoice(s) + summary opened for printing.` });
    } catch (err: any) {
      addNotification({ type: 'error', title: 'Print Failed', message: err.message });
    } finally {
      setIsProcessing(false);
    }
  };

  // ---- BULK EXPORT CSV ----
  const handleBulkExport = async () => {
    if (selectedFamilies.size === 0) {
      addNotification({ type: 'warning', title: 'No Selection', message: 'Please select at least one family.' });
      return;
    }
    setIsProcessing(true);
    try {
      const invoices = await getInvoicesForSelectedFamilies();
      if (invoices.length === 0) {
        addNotification({ type: 'info', title: 'Nothing to Export', message: 'No invoices found for the selected families.' });
        setIsProcessing(false);
        return;
      }

      // Build CSV content
      const headers = ['Invoice Number', 'Client', 'Issue Date', 'Due Date', 'Subtotal', 'Tax', 'Discount', 'Total', 'Paid', 'Balance Due', 'Status'];
      const rows = invoices.map(inv => [
        inv.invoice_number,
        inv.client_name || inv.family?.name || '',
        formatDate(inv.issue_date),
        formatDate(inv.due_date),
        inv.subtotal?.toFixed(2) || '0.00',
        inv.tax_amount?.toFixed(2) || '0.00',
        inv.discount_amount?.toFixed(2) || '0.00',
        inv.total_amount?.toFixed(2) || '0.00',
        inv.amount_paid?.toFixed(2) || '0.00',
        inv.balance_due?.toFixed(2) || '0.00',
        inv.status,
      ]);

      const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\n');

      // Trigger download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const fsName = fundingSources.find(fs => fs.id === selectedRecipientId)?.name || 'bulk';
      link.download = `${fsName}_invoices_${getToday()}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      addNotification({ type: 'success', title: 'Export Complete', message: `${invoices.length} invoice(s) exported to CSV.` });
    } catch (err: any) {
      addNotification({ type: 'error', title: 'Export Failed', message: err.message });
    } finally {
      setIsProcessing(false);
    }
  };

  const handleBatchGenerate = async () => {
    setIsProcessing(true);
    setProcessProgress(50);
    try {
      const result = await api.post<{ generated: number }>('/invoicing/invoices/bulk-generate', {
          family_ids: Array.from(selectedFamilies),
          recipient_id: selectedRecipientId || undefined,
          issue_date: batchDates.issue_date,
          due_date: batchDates.due_date,
          period_start: batchPeriod.start,
          period_end: batchPeriod.end,
      });
      setShowBatchModal(false);
      addNotification({ type: 'success', title: 'Invoices Generated', message: `${result.generated} invoices have been created.` });
      await refetch();
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setIsProcessing(false);
      setProcessProgress(100);
    }
  };

  // Stats
  const activeFamilies = families.filter(f => f.status === 'active').length;
  const needsInvoiceCount = families.filter(f => needsInvoice(f.last_invoice_date)).length;

  if (loading) return <CenteredLoading />;

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-semibold text-gray-900">Bulk Operations</h2>
            {selectedFamilies.size > 0 && (
              <span className="px-3 py-1 bg-primary-100 text-primary-700 rounded-full text-sm font-medium">
                {selectedFamilies.size} selected
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowBatchModal(true)}
              disabled={selectedFamilies.size === 0}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PlusCircleIcon className="w-5 h-5" />
              Generate Invoices
            </button>
            <button
              onClick={handleBulkSend}
              disabled={selectedFamilies.size === 0}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <EnvelopeIcon className="w-5 h-5" />
              Send All
            </button>
            <button
              onClick={handleBulkPrint}
              disabled={selectedFamilies.size === 0}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PrinterIcon className="w-5 h-5" />
              Print
            </button>
            <button
              onClick={handleBulkExport}
              disabled={selectedFamilies.size === 0}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ArrowDownTrayIcon className="w-5 h-5" />
              Export
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <StatsGrid columns={4}>
        <StatCard
          icon={<UserGroupIcon className="w-6 h-6 text-blue-600" />}
          iconBg="bg-blue-100"
          label="Active Families"
          value={activeFamilies}
        />
        <StatCard
          icon={<CheckCircleIcon className="w-6 h-6 text-green-600" />}
          iconBg="bg-green-100"
          label="Selected"
          value={selectedFamilies.size}
          valueColor="text-green-600"
        />
        <StatCard
          icon={<CurrencyDollarIcon className="w-6 h-6 text-purple-600" />}
          iconBg="bg-purple-100"
          label="Selected Total"
          value={isFetchingTotals ? 'Calculating...' : formatCurrencyIntl(calculateSelectedTotal())}
          valueColor="text-purple-600"
        />
        <StatCard
          icon={<ExclamationTriangleIcon className="w-6 h-6 text-yellow-600" />}
          iconBg="bg-yellow-100"
          label="Need Invoice"
          value={needsInvoiceCount}
          valueColor="text-yellow-600"
        />
      </StatsGrid>

      {/* Family Selection */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Select Families</h3>
          <div className="flex items-center gap-2">
            {fundingSources.map(fs => {
              const count = families.filter(f => f.recurring_funding_source_id === fs.id).length;
              if (count === 0) return null;
              return (
                <button
                  key={fs.id}
                  onClick={() => selectByFundingSource(fs.id)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg shadow-sm transition-all ${
                    fs.name === 'EMCN'
                      ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white hover:from-blue-600 hover:to-indigo-600'
                      : 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:from-emerald-600 hover:to-teal-600'
                  }`}
                >
                  ⚡ {fs.name} ({count})
                </button>
              );
            })}
            <button onClick={selectAll} className="text-sm text-primary-600 hover:text-primary-700 font-medium ml-2">
              {selectedFamilies.size === families.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>
        </div>

        <div className="divide-y divide-gray-100">
          {[...families]
            .sort((a, b) => (b.is_recurring_billing ? 1 : 0) - (a.is_recurring_billing ? 1 : 0))
            .map((family) => {
            const isSelected = selectedFamilies.has(family.id);
            const needsInv = needsInvoice(family.last_invoice_date);

            return (
              <div
                key={family.id}
                onClick={() => toggleFamily(family.id)}
                className={`p-4 cursor-pointer transition-colors ${isSelected ? 'bg-primary-50' : 'hover:bg-gray-50'}`}
              >
                <div className="flex items-center gap-4">
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                    isSelected ? 'bg-primary-600 border-primary-600' : 'border-gray-300'
                  }`}>
                    {isSelected && <CheckCircleIcon className="w-4 h-4 text-white" />}
                  </div>

                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <p className="font-medium text-gray-900">{family.name}</p>
                      {family.is_recurring_billing && (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                          fundingSources.find(fs => fs.id === family.recurring_funding_source_id)?.name === 'EMCN'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-emerald-100 text-emerald-700'
                        }`}>
                          ⚡ {fundingSources.find(fs => fs.id === family.recurring_funding_source_id)?.name || 'Recurring'}
                        </span>
                      )}
                      {needsInv && (
                        <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-full text-xs font-medium">
                          Needs Invoice
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-500">{family.guardian_email}</p>
                  </div>

                  <div className="text-sm text-gray-600">
                    {(family.children || []).map((child, idx) => (
                      <span key={child.id || idx}>
                        {child.first_name}
                        {idx < (family.children || []).length - 1 && ', '}
                      </span>
                    ))}
                  </div>

                  <div className="text-right">
                    <p className="text-xs text-gray-500">
                      {family.last_invoice_date 
                        ? `Last: ${formatDate(family.last_invoice_date)}` 
                        : 'Never invoiced'}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Automation Promo */}
      <div className="bg-gradient-to-r from-gray-800 to-gray-900 rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-white/10 rounded-lg">
            <ArrowPathIcon className="h-6 w-6 text-white" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-white mb-2">Automate Your Billing</h3>
            <p className="text-gray-300 text-sm mb-4">
              Set up recurring invoices to automatically generate and send invoices to families on a schedule.
            </p>
            <button className="inline-flex items-center px-4 py-2 bg-white text-gray-900 font-medium rounded-lg hover:bg-gray-100 transition-colors text-sm">
              Set Up Recurring Invoices
            </button>
          </div>
        </div>
      </div>

      {/* Batch Generate Modal */}
      <Modal
        isOpen={showBatchModal}
        onClose={() => !isProcessing && setShowBatchModal(false)}
        title="Generate Batch Invoices"
        maxWidth="lg"
        disableClose={isProcessing}
        footer={!isProcessing ? (
          <>
            <ModalButton variant="secondary" onClick={() => setShowBatchModal(false)}>
              Cancel
            </ModalButton>
            <ModalButton onClick={handleBatchGenerate}>
              <DocumentDuplicateIcon className="w-5 h-5 mr-2" />
              Generate {selectedFamilies.size} Invoices
            </ModalButton>
          </>
        ) : undefined}
      >
        {isProcessing ? (
          <ProcessingOverlay
            message="Generating Invoices..."
            progress={processProgress}
            total={selectedFamilies.size}
          />
        ) : (
          <div className="space-y-6">
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-gray-600">Families Selected</span>
                <span className="font-bold text-gray-900">{selectedFamilies.size}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Total Amount</span>
                <span className="font-bold text-primary-600">
                  {isFetchingTotals ? 'Calculating...' : formatCurrencyIntl(calculateSelectedTotal())}
                </span>
              </div>
            </div>

            {/* Funding Source / Recipient */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Invoice Recipient (Funding Source)</label>
              <select
                value={selectedRecipientId}
                onChange={(e) => setSelectedRecipientId(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">— Parent / Direct Billing —</option>
                {fundingSources.map(fs => (
                  <option key={fs.id} value={fs.id}>
                    {fs.name} ({fs.funding_type})
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500">
                Select EMCN, Income Support, or leave blank for parent-direct invoices.
              </p>
            </div>

            <DateRangePicker
              startDate={batchDates.issue_date}
              endDate={batchDates.due_date}
              onStartChange={(v) => setBatchDates(prev => ({ ...prev, issue_date: v }))}
              onEndChange={(v) => setBatchDates(prev => ({ ...prev, due_date: v }))}
              startLabel="Invoice Date"
              endLabel="Due Date"
            />

            <DateRangePicker
              startDate={batchPeriod.start}
              endDate={batchPeriod.end}
              onStartChange={(v) => setBatchPeriod(prev => ({ ...prev, start: v }))}
              onEndChange={(v) => setBatchPeriod(prev => ({ ...prev, end: v }))}
              startLabel="Period Start"
              endLabel="Period End"
            />

            <div className="p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>Note:</strong> Invoices will be created as drafts with rates auto-populated from the rate schedules. You can review and edit them before sending.
              </p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Bulk;
