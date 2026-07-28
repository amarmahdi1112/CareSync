// ============================================
// Invoicing Settings View (Refactored)
// ============================================

import React, { useState, useEffect } from 'react';
import {
  CurrencyDollarIcon,
  EnvelopeIcon,
  BanknotesIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { InvoiceSettings, SmtpSettings, FundingSource } from '../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  SettingsSubsection,
  SettingsTabs,
  FormInput,
  FormTextarea,
  FormSelect,
  ToggleCard,
  SettingsLoadingSpinner,
  TestResultBanner,
  FeatureSummary,
  SettingsEmptyState,
} from '../components';

// Constants
import {
  SMTP_ENCRYPTIONS,
  FUNDING_TYPES,
  DEFAULT_INVOICE_SETTINGS_FORM,
  DEFAULT_SMTP_FORM,
  DEFAULT_FUNDING_FORM,
} from '../constants';

type SettingsTab = 'general' | 'email' | 'funding';

const tabs = [
  { id: 'general' as SettingsTab, name: 'General', icon: CurrencyDollarIcon },
  { id: 'email' as SettingsTab, name: 'Email', icon: EnvelopeIcon },
  { id: 'funding' as SettingsTab, name: 'Funding Sources', icon: BanknotesIcon },
];

const Invoicing: React.FC = () => {
  const { addNotification } = useNotifications();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [formData, setFormData] = useState(DEFAULT_INVOICE_SETTINGS_FORM);
  const [smtpData, setSmtpData] = useState(DEFAULT_SMTP_FORM);
  const [testEmail, setTestEmail] = useState('');
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingSmtp, setSavingSmtp] = useState(false);
  const [testingSmtp, setTestingSmtp] = useState(false);

  // Queries
  const { data: settings, loading, refetch: refetchSettings } = useApiQuery<InvoiceSettings | null>('/invoicing/settings');
  const { data: fundingSources = [], refetch: refetchFunding } = useApiQuery<FundingSource[]>('/resources/funding_sources', { limit: 1000 });

  // Funding Source mutations
  const [showFundingForm, setShowFundingForm] = useState(false);
  const [editingFunding, setEditingFunding] = useState<FundingSource | null>(null);
  const [fundingForm, setFundingForm] = useState(DEFAULT_FUNDING_FORM);

  const smtpSettings = settings as SmtpSettings | null | undefined;

  useEffect(() => {
    if (settings) {
      setFormData({
        currency_symbol: settings.currency_symbol || '$',
        invoice_prefix: settings.invoice_prefix || 'INV-',
        default_tax_rate: settings.default_tax_rate || 0,
        tax_name: settings.tax_name || '',
        default_notes: settings.default_notes || '',
        default_terms: settings.default_terms || '',
      });
    }
  }, [settings]);

  useEffect(() => {
    if (smtpSettings) {
      setSmtpData((prev) => ({
        ...prev,
        smtp_enabled: smtpSettings.smtp_enabled || false,
        smtp_host: smtpSettings.smtp_host || '',
        smtp_port: smtpSettings.smtp_port || 587,
        smtp_username: smtpSettings.smtp_username || '',
        smtp_encryption: smtpSettings.smtp_encryption || 'tls',
        smtp_from_email: smtpSettings.smtp_from_email || '',
        smtp_from_name: smtpSettings.smtp_from_name || '',
      }));
    }
  }, [smtpSettings]);

  const resetFundingForm = () => {
    setShowFundingForm(false);
    setEditingFunding(null);
    setFundingForm(DEFAULT_FUNDING_FORM);
  };

  const handleEditFunding = (source: FundingSource) => {
    setEditingFunding(source);
    setFundingForm({
      name: source.name,
      funding_type: source.funding_type,
      description: source.description || '',
      contact_name: source.contact_name || '',
      contact_email: source.contact_email || '',
      contact_phone: source.contact_phone || '',
      billing_address: source.billing_address || '',
    });
    setShowFundingForm(true);
  };

  const handleSaveFunding = async () => {
    if (!fundingForm.name || !fundingForm.contact_email) {
      addNotification({ type: 'error', title: 'Required', message: 'Name and email are required' });
      return;
    }
    try {
      if (editingFunding) {
        await api.resources.update('funding_sources', editingFunding.id, fundingForm);
      } else {
        await api.resources.create('funding_sources', fundingForm);
      }
      addNotification({ type: 'success', title: editingFunding ? 'Updated' : 'Created', message: 'Funding source saved!' });
      await refetchFunding();
      resetFundingForm();
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    }
  };

  const handleDeleteFunding = async (id: string, name: string) => {
    if (confirm(`Delete funding source "${name}"? Invoices linked to this will need a new recipient.`)) {
      try {
        await api.resources.remove('funding_sources', id);
        addNotification({ type: 'success', title: 'Deleted', message: 'Funding source removed!' });
        await refetchFunding();
      } catch (caught) {
        addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.patch('/invoicing/settings', formData);
      await refetchSettings();
      addNotification({ type: 'success', title: 'Saved', message: 'Invoice settings saved successfully!' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setSaving(false);
    }
  };

  const handleSmtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSmtp(true);
    try {
      await api.patch('/invoicing/settings', smtpData);
      await refetchSettings();
      addNotification({ type: 'success', title: 'Saved', message: 'SMTP settings saved!' });
    } catch (caught) {
      addNotification({ type: 'error', title: 'Error', message: caught instanceof Error ? caught.message : 'Request failed' });
    } finally {
      setSavingSmtp(false);
    }
  };

  const handleTestSmtp = async () => {
    if (!testEmail) {
      addNotification({ type: 'error', title: 'Error', message: 'Please enter a test email address' });
      return;
    }
    setTestResult(null);
    setTestingSmtp(true);
    try {
      const result = await api.post<{ success: boolean; message: string }>('/invoicing/settings/test-email', { test_email: testEmail });
      setTestResult(result);
      addNotification({ type: result.success ? 'success' : 'error', title: result.success ? 'Success' : 'Failed', message: result.message });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Request failed';
      setTestResult({ success: false, message });
      addNotification({ type: 'error', title: 'Error', message });
    } finally {
      setTestingSmtp(false);
    }
  };

  if (loading) {
    return (
      <SettingsPageLayout title="Invoicing & Payments" description="Loading...">
        <SettingsLoadingSpinner />
      </SettingsPageLayout>
    );
  }

  return (
    <SettingsPageLayout title="Invoicing & Payments" description="Configure your invoice settings, email, and funding sources">
      <SettingsTabs tabs={tabs} activeTab={activeTab} onTabChange={(id) => setActiveTab(id as SettingsTab)} />

      {/* General Tab */}
      {activeTab === 'general' && (
        <SettingsSection>
          <h3 className="text-lg font-semibold text-gray-900 mb-6">Invoice Settings</h3>

          <FeatureSummary title="Business Information" linkText="Edit" linkHref="/settings/organization">
            {settings && (
              <div className="text-sm text-gray-600">
                <p className="font-medium text-gray-900">{settings.company_name}</p>
                <p>{settings.company_address}, {settings.company_city}, {settings.company_province} {settings.company_postal_code}</p>
                <p>{settings.company_phone} • {settings.company_email}</p>
              </div>
            )}
          </FeatureSummary>

          <form onSubmit={handleSubmit} className="mt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormInput label="Currency Symbol" value={formData.currency_symbol} onChange={(e) => setFormData((p) => ({ ...p, currency_symbol: e.target.value }))} maxLength={5} />
              <FormInput label="Invoice Number Prefix" value={formData.invoice_prefix} onChange={(e) => setFormData((p) => ({ ...p, invoice_prefix: e.target.value }))} placeholder="INV-" />
              <FormInput label="Default Tax Rate (%)" type="number" value={formData.default_tax_rate} onChange={(e) => setFormData((p) => ({ ...p, default_tax_rate: parseFloat(e.target.value) || 0 }))} step="0.01" min="0" max="100" />
              <FormInput label="Tax Name" value={formData.tax_name} onChange={(e) => setFormData((p) => ({ ...p, tax_name: e.target.value }))} placeholder="e.g., GST, HST, VAT" />
            </div>

            <SettingsSubsection title="Default Invoice Text" className="mt-8">
              <div className="space-y-4">
                <FormTextarea label="Default Notes" value={formData.default_notes} onChange={(e) => setFormData((p) => ({ ...p, default_notes: e.target.value }))} rows={3} placeholder="Payment can be made via e-transfer to..." hint="Appears on all new invoices" />
                <FormTextarea label="Default Terms & Conditions" value={formData.default_terms} onChange={(e) => setFormData((p) => ({ ...p, default_terms: e.target.value }))} rows={3} placeholder="Payment is due within 30 days..." />
              </div>
            </SettingsSubsection>

            <div className="flex justify-end mt-6 pt-6 border-t border-gray-200">
              <button type="submit" disabled={saving} className="btn btn-primary">{saving ? 'Saving...' : 'Save Changes'}</button>
            </div>
          </form>
        </SettingsSection>
      )}

      {/* Email Tab */}
      {activeTab === 'email' && (
        <SettingsSection>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-gray-900">Email Configuration (SMTP)</h3>
            {smtpSettings?.smtp_configured && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Configured</span>
            )}
          </div>

          <form onSubmit={handleSmtpSubmit}>
            <ToggleCard enabled={smtpData.smtp_enabled} onChange={(v) => setSmtpData((p) => ({ ...p, smtp_enabled: v }))} title="Enable Email Sending" description="Allow sending invoices via email directly from the app" />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
              <FormInput label="SMTP Host" value={smtpData.smtp_host} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_host: e.target.value }))} placeholder="smtp.gmail.com" required />
              <FormInput label="Port" type="number" value={smtpData.smtp_port} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_port: parseInt(e.target.value) || 587 }))} placeholder="587" required />
              <FormInput label="Username" value={smtpData.smtp_username} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_username: e.target.value }))} placeholder="your-email@gmail.com" required />
              <FormInput label="Password" type="password" value={smtpData.smtp_password} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_password: e.target.value }))} placeholder="••••••••" hint="For Gmail, use an App Password" required />
              <FormSelect label="Encryption" value={smtpData.smtp_encryption} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_encryption: e.target.value }))} options={SMTP_ENCRYPTIONS} />
              <FormInput label="From Email" type="email" value={smtpData.smtp_from_email} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_from_email: e.target.value }))} placeholder="invoices@yourcompany.com" />
              <div className="md:col-span-2">
                <FormInput label="From Name" value={smtpData.smtp_from_name} onChange={(e) => setSmtpData((p) => ({ ...p, smtp_from_name: e.target.value }))} placeholder="Your Company Name" />
              </div>
            </div>

            <SettingsSubsection title="Test Connection" className="mt-8">
              <div className="flex gap-3">
                <input type="email" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} className="input flex-1" placeholder="Enter email to receive test" />
                <button type="button" onClick={handleTestSmtp} disabled={testingSmtp || !smtpData.smtp_host || !smtpData.smtp_username} className="btn btn-secondary">
                  {testingSmtp ? 'Sending...' : 'Send Test'}
                </button>
              </div>
              <TestResultBanner result={testResult} />
            </SettingsSubsection>

            <div className="flex justify-end mt-6 pt-6 border-t border-gray-200">
              <button type="submit" disabled={savingSmtp} className="btn btn-primary">{savingSmtp ? 'Saving...' : 'Save Changes'}</button>
            </div>
          </form>
        </SettingsSection>
      )}

      {/* Funding Sources Tab */}
      {activeTab === 'funding' && (
        <SettingsSection>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-gray-900">Invoice Recipients</h3>
            <button onClick={() => { resetFundingForm(); setShowFundingForm(true); }} className="btn btn-primary">
              <PlusIcon className="w-4 h-4" /> Add Funding Source
            </button>
          </div>

          <p className="text-sm text-gray-500 mb-6">Manage funding agencies like FSCD, Alberta Support, etc. that receive invoices.</p>

          {fundingSources.length === 0 ? (
            <SettingsEmptyState icon={BanknotesIcon} title="No funding sources configured" description="Add FSCD, Alberta Support, or other agencies" action={{ label: 'Add Funding Source', onClick: () => setShowFundingForm(true) }} />
          ) : (
            <div className="space-y-3">
              {fundingSources.map((source) => (
                <div key={source.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">{source.name}</p>
                    <p className="text-sm text-gray-500">{source.contact_email}{source.contact_name && ` • ${source.contact_name}`}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleEditFunding(source)} className="btn btn-ghost btn-sm" title="Edit"><PencilIcon className="w-4 h-4" /></button>
                    <button onClick={() => handleDeleteFunding(source.id, source.name)} className="btn btn-ghost btn-sm text-red-600" title="Delete"><TrashIcon className="w-4 h-4" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {showFundingForm && (
            <SettingsSubsection title={editingFunding ? 'Edit Funding Source' : 'Add New Funding Source'} className="mt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormInput label="Name" value={fundingForm.name} onChange={(e) => setFundingForm((p) => ({ ...p, name: e.target.value }))} placeholder="e.g., FSCD, Alberta Support" required />
                <FormSelect label="Type" value={fundingForm.funding_type} onChange={(e) => setFundingForm((p) => ({ ...p, funding_type: e.target.value }))} options={FUNDING_TYPES} />
                <FormInput label="Email" type="email" value={fundingForm.contact_email} onChange={(e) => setFundingForm((p) => ({ ...p, contact_email: e.target.value }))} placeholder="invoices@agency.gov" required />
                <FormInput label="Contact Name" value={fundingForm.contact_name} onChange={(e) => setFundingForm((p) => ({ ...p, contact_name: e.target.value }))} placeholder="Contact person" />
                <FormInput label="Phone" type="tel" value={fundingForm.contact_phone} onChange={(e) => setFundingForm((p) => ({ ...p, contact_phone: e.target.value }))} placeholder="(403) 555-1234" />
                <FormInput label="Billing Address" value={fundingForm.billing_address} onChange={(e) => setFundingForm((p) => ({ ...p, billing_address: e.target.value }))} placeholder="123 Main St, Calgary, AB" />
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button onClick={resetFundingForm} className="btn btn-secondary">Cancel</button>
                <button onClick={handleSaveFunding} className="btn btn-primary">{editingFunding ? 'Update' : 'Add'} Funding Source</button>
              </div>
            </SettingsSubsection>
          )}
        </SettingsSection>
      )}
    </SettingsPageLayout>
  );
};

export default Invoicing;
