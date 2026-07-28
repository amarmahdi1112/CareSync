import React, { useState } from 'react';
import type { InvoiceTemplate } from './types';
import { 
  PlusIcon, 
  ChartBarIcon,
  ArrowPathIcon,
  PresentationChartLineIcon,
  ShieldCheckIcon,
  RectangleStackIcon,
  ReceiptRefundIcon,
  CurrencyDollarIcon,
  Cog6ToothIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';

// Layout components
import {
  PageContainer,
  PageHeader,
  TabNavigation,
  PageContent,
} from './components/layout';

// Views
import {
  Dashboard,
  BillingRun,
  CreateInvoice,
  Templates,
  Recurring,
  Credits,
  Analytics,
  ParentTracking,
} from './views';

type TabType = 'dashboard' | 'billing-run' | 'create' | 'templates' | 'recurring' | 'credits' | 'analytics' | 'parent-tracking';

const tabs = [
  { id: 'dashboard' as TabType, name: 'Overview', icon: ChartBarIcon },
  { id: 'billing-run' as TabType, name: 'Billing Run', icon: BoltIcon },
  { id: 'create' as TabType, name: 'Custom Invoice', icon: PlusIcon },
  { id: 'recurring' as TabType, name: 'Automation', icon: ArrowPathIcon },
  { id: 'credits' as TabType, name: 'Credits', icon: ReceiptRefundIcon },
  { id: 'parent-tracking' as TabType, name: 'Parent Accounts', icon: ShieldCheckIcon },
  { id: 'analytics' as TabType, name: 'Insights', icon: PresentationChartLineIcon },
  { id: 'templates' as TabType, name: 'Templates', icon: RectangleStackIcon },
];

const InvoicingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [editingInvoiceId, setEditingInvoiceId] = useState<string | null>(null);
  const [templateData, setTemplateData] = useState<InvoiceTemplate | null>(null);

  const handleEditInvoice = (invoiceId: string) => {
    setEditingInvoiceId(invoiceId);
    setActiveTab('create');
  };

  const handleCreateNew = () => {
    setEditingInvoiceId(null);
    setTemplateData(null);
    setActiveTab('create');
  };

  const handleInvoiceSaved = () => {
    setEditingInvoiceId(null);
    setTemplateData(null);
    setActiveTab('dashboard');
  };

  const handleTabChange = (tabId: string) => {
    if (tabId === 'create') {
      handleCreateNew();
    } else {
      setActiveTab(tabId as TabType);
    }
  };

  return (
    <PageContainer>
      {/* Page Header */}
      <PageHeader
        title="Invoicing"
        description="Safe daycare billing, parent portions, funding, and collections"
        icon={<CurrencyDollarIcon className="w-6 h-6 text-white" />}
        actions={
          <div className="flex items-center gap-2 sm:gap-3">
            <Link
              to="/settings/invoicing"
              className="btn btn-secondary p-2 sm:px-4 sm:py-2"
              title="Settings"
            >
              <Cog6ToothIcon className="w-4 h-4 sm:w-5 sm:h-5" />
              <span className="hidden sm:inline ml-2">Settings</span>
            </Link>
            <button
              onClick={() => setActiveTab('billing-run')}
              className="btn btn-primary p-2 sm:px-4 sm:py-2"
              title="Run Monthly Billing"
            >
              <BoltIcon className="w-4 h-4 sm:w-5 sm:h-5" />
              <span className="hidden sm:inline ml-2">Run Billing</span>
            </button>
          </div>
        }
      />

      {/* Tab Navigation */}
      <TabNavigation
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={handleTabChange}
      />

      {/* Content */}
      <PageContent>
        {activeTab === 'dashboard' && (
          <Dashboard 
            onEditInvoice={handleEditInvoice}
            onCreateNew={handleCreateNew}
          />
        )}
        {activeTab === 'billing-run' && <BillingRun />}
        {activeTab === 'create' && (
          <CreateInvoice 
            invoiceId={editingInvoiceId}
            templateData={templateData}
            onSaved={handleInvoiceSaved}
            onCancel={() => setActiveTab('dashboard')}
          />
        )}
        {activeTab === 'templates' && (
          <Templates 
            onUseTemplate={(template) => {
              setEditingInvoiceId(null);
              setTemplateData(template);
              setActiveTab('create');
            }}
          />
        )}
        {activeTab === 'recurring' && <Recurring />}
        {activeTab === 'credits' && <Credits />}
        {activeTab === 'analytics' && <Analytics />}
        {activeTab === 'parent-tracking' && <ParentTracking />}
      </PageContent>
    </PageContainer>
  );
};

export default InvoicingPage;
