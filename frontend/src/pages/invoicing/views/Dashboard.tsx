// ============================================
// Invoice Dashboard View (Refactored InvoiceList)
// ============================================

import React, { useState } from 'react';
import { 
  PlusIcon,
  DocumentDuplicateIcon,
  ExclamationCircleIcon,
  ClockIcon,
  BanknotesIcon,
} from '@heroicons/react/24/outline';

// Types
import type { Invoice, InvoiceSettings, InvoiceDashboard } from '../types';

import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Layout & Components
import { ModernStatCard, StatsGridLayout, ContentCard, EmptyStateCard } from '../components/layout';
import { LoadingState } from '../components/common/EmptyState';
import { InvoiceTable, TablePagination } from '../components/invoice/InvoiceTable';
import { printInvoice } from '../components/invoice/InvoicePrintTemplate';
import { SendInvoiceModal } from '../components/modals/SendInvoiceModal';

// Utils
import { formatCurrencyIntl } from '../utils/formatters';
import { DEFAULT_PAGE_SIZE } from '../constants';

interface DashboardProps {
  onEditInvoice: (id: string) => void;
  onCreateNew: () => void;
}

interface RestInvoiceConnection {
  items: Invoice[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

const Dashboard: React.FC<DashboardProps> = ({ onEditInvoice, onCreateNew }) => {
  // State
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [sendModalOpen, setSendModalOpen] = useState(false);
  const [sendingInvoice, setSendingInvoice] = useState<Invoice | null>(null);
  const [sendStatus, setSendStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const { data, loading, refetch } = useApiQuery<RestInvoiceConnection>('/invoicing/invoices', {
    page,
    limit: DEFAULT_PAGE_SIZE,
    status: statusFilter || undefined,
  });
  const { data: dashboard } = useApiQuery<InvoiceDashboard>('/invoicing/invoices/dashboard');
  const { data: settingsRows } = useApiQuery<InvoiceSettings[]>('/resources/provider_settings', {
    limit: 1,
  });
  const settings = settingsRows?.[0];
  const [sendingEmail, setSendingEmail] = useState(false);

  // Data
  const invoices: Invoice[] = data?.items || [];
  const total = data?.total || 0;
  const hasMore = data?.has_more ?? false;

  // Handlers
  const handleStatusChange = async (id: string, newStatus: string) => {
    try {
      await api.patch(`/invoicing/invoices/${id}/status`, { status: newStatus });
      await refetch();
    } catch (caught) {
      alert(caught instanceof Error ? caught.message : 'Status update failed');
    }
  };

  const handleDelete = async (id: string, invoiceNumber: string) => {
    if (confirm(`Delete invoice ${invoiceNumber}? This cannot be undone.`)) {
      try {
        await api.delete(`/invoicing/invoices/${id}`);
        await refetch();
      } catch (caught) {
        alert(caught instanceof Error ? caught.message : 'Delete failed');
      }
    }
  };

  const handleDuplicate = async (id: string) => {
    try {
      await api.post(`/invoicing/invoices/${id}/duplicate`, {});
      await refetch();
    } catch (caught) {
      alert(caught instanceof Error ? caught.message : 'Duplicate failed');
    }
  };

  const handleOpenSendModal = (invoice: Invoice) => {
    const recipientEmail = invoice.recipient?.contact_email || invoice.client_email;
    if (!recipientEmail) {
      alert('No recipient email for this invoice. Please select a funding source with an email, or add a client email.');
      return;
    }
    setSendingInvoice(invoice);
    setSendStatus(null);
    setSendModalOpen(true);
  };

  const handleSendEmail = async (invoiceId: string, customMessage?: string) => {
    setSendingEmail(true);
    try {
      const result = await api.post<{ success: boolean; message: string }>(
        `/invoicing/invoices/${invoiceId}/email`,
        { custom_message: customMessage },
      );
      setSendStatus({ type: result.success ? 'success' : 'error', message: result.message });
      if (result.success) {
        await refetch();
        setTimeout(() => {
          setSendModalOpen(false);
          setSendingInvoice(null);
          setSendStatus(null);
        }, 2000);
      }
    } catch (caught) {
      setSendStatus({ type: 'error', message: caught instanceof Error ? caught.message : 'Send failed' });
    } finally {
      setSendingEmail(false);
    }
  };

  const handlePrintInvoice = async (invoice: Invoice) => {
    // The list query doesn't include line_items — fetch the full invoice first
    try {
      const fullInvoice = await api.get<Invoice>(`/invoicing/invoices/${invoice.id}`);
      printInvoice(fullInvoice, settings);
    } catch {
      // Fallback to whatever data we have
      printInvoice(invoice, settings);
    }
  };

  return (
    <div className="space-y-6">
      {/* Dashboard Stats */}
      <StatsGridLayout columns={4}>
        <ModernStatCard
          icon={<ExclamationCircleIcon className="w-5 h-5" />}
          label="Overdue"
          value={formatCurrencyIntl(dashboard?.total_overdue || 0)}
          color="red"
        />
        <ModernStatCard
          icon={<ClockIcon className="w-5 h-5" />}
          label="Outstanding"
          value={formatCurrencyIntl(dashboard?.total_outstanding || 0)}
          color="yellow"
        />
        <ModernStatCard
          icon={<BanknotesIcon className="w-5 h-5" />}
          label="Paid This Month"
          value={formatCurrencyIntl(dashboard?.paid_this_month || 0)}
          color="green"
        />
        <ModernStatCard
          icon={<DocumentDuplicateIcon className="w-5 h-5" />}
          label="Total Invoices"
          value={dashboard?.invoice_count || 0}
          color="blue"
        />
      </StatsGridLayout>

      {/* Invoice List */}
      <ContentCard
        title="Recent Invoices"
        description={`${total} invoice${total !== 1 ? 's' : ''} total`}
        actions={
          <div className="flex items-center gap-3">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-sm bg-white text-gray-700 border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">All Status</option>
              <option value="draft">Draft</option>
              <option value="sent">Sent</option>
              <option value="paid">Paid</option>
              <option value="overdue">Overdue</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        }
        noPadding
      >
        {loading ? (
          <LoadingState message="Loading invoices..." />
        ) : invoices.length === 0 ? (
          <EmptyStateCard
            icon={<DocumentDuplicateIcon className="w-8 h-8 text-gray-400" />}
            title="No Invoices Yet"
            description="Create your first invoice to start tracking payments"
            action={{
              label: 'Create Invoice',
              onClick: onCreateNew,
              icon: <PlusIcon className="w-4 h-4" />,
            }}
          />
        ) : (
          <>
            <InvoiceTable
              invoices={invoices}
              onEdit={onEditInvoice}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
              onStatusChange={handleStatusChange}
              onSend={handleOpenSendModal}
              onPrint={handlePrintInvoice}
            />
            <TablePagination
              page={page}
              pageSize={DEFAULT_PAGE_SIZE}
              total={total}
              hasMore={hasMore}
              onPageChange={setPage}
            />
          </>
        )}
      </ContentCard>

      {/* Send Email Modal */}
      <SendInvoiceModal
        isOpen={sendModalOpen}
        onClose={() => {
          setSendModalOpen(false);
          setSendingInvoice(null);
          setSendStatus(null);
        }}
        invoice={sendingInvoice}
        onSend={handleSendEmail}
        loading={sendingEmail}
        status={sendStatus}
      />
    </div>
  );
};

export default Dashboard;
