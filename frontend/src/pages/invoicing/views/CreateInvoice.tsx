/* eslint-disable react-hooks/exhaustive-deps */
// ============================================
// Create Invoice View (Refactored InvoiceGenerator)
// ============================================

import React, { useState, useEffect, useMemo, useCallback } from 'react';

// Types
import type { 
  Family, 
  FundingSource, 
  LineItem, 
  LineItemType,
  InvoiceSettings,
  InvoiceData,
  InvoiceTemplate,
} from '../types';

// Type for edit invoice query response
interface EditInvoiceResponse {
  invoice: {
    id: string;
    invoice_number: string;
    file_number?: string;
    family_id?: string;
    guardian_id?: string;
    client_name?: string;
    client_email?: string;
    client_address?: string;
    recipient_id?: string;
    issue_date: string;
    due_date: string;
    period_start?: string;
    period_end?: string;
    discount_amount?: number;
    discount_percentage?: number;
    tax_rate?: number;
    notes?: string;
    terms?: string;
    line_items?: Array<{
      id?: string;
      item_type: string;
      description?: string;
      child_id?: string;
      child_name?: string;
      full_rate?: number;
      subsidy_amount?: number;
      hours?: number;
      hourly_rate?: number;
      quantity?: number;
      unit_price?: number;
      amount?: number;
    }>;
  };
}

import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Components
import { MultiClientSelector, SelectedClientsSummary, ClientInfoDisplay, FundingSourceSelector, DateRangePicker, DiscountTaxFields, NotesTermsFields } from '../components/forms/ClientSelector';
import { LineItemEditor, AddLineItemButtons } from '../components/forms/LineItemEditor';
import { InvoicePreview } from '../components/invoice/InvoicePreview';

// Utils
import { calculateInvoiceTotals, createEmptyLineItem, calculateLineItemAmount, generateId } from '../utils/calculations';
import { getToday, getDateFromNow } from '../utils/formatters';

interface CreateInvoiceProps {
  invoiceId?: string | null;
  templateData?: InvoiceTemplate | null;
  onSaved: () => void;
  onCancel: () => void;
}

const CreateInvoice: React.FC<CreateInvoiceProps> = ({ invoiceId, templateData, onSaved, onCancel }) => {
  // Initial state
  const [invoice, setInvoice] = useState<InvoiceData>({
    invoice_number: '',
    file_number: '',
    family_id: '',
    guardian_id: '',
    client_name: '',
    client_email: '',
    client_address: '',
    recipient_id: '',
    issue_date: getToday(),
    due_date: getDateFromNow(30),
    period_start: '',
    period_end: '',
    line_items: [createEmptyLineItem()],
    discount_type: 'amount',
    discount_value: 0,
    tax_rate: 0,
    notes: '',
    terms: '',
  });
  
  // Track selected family IDs for multi-select
  const [selectedFamilyIds, setSelectedFamilyIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [prefillingLoading, setPrefillingLoading] = useState(false);

  // Queries
  const { data: clientsData = [] } = useApiQuery<Family[]>('/families', { limit: 1000 });
  const { data: settingsData } = useApiQuery<InvoiceSettings | null>('/invoicing/settings');
  const { data: fundingSourcesData = [] } = useApiQuery<FundingSource[]>('/resources/funding_sources', { limit: 1000 });
  
  // Fetch existing invoice when editing
  const { data: existingInvoiceData, loading: loadingInvoice } = useApiQuery<EditInvoiceResponse['invoice']>(
    `/invoicing/invoices/${invoiceId || ''}`,
    undefined,
    Boolean(invoiceId),
  );
  
  // Show loading state when fetching existing invoice
  const isLoading = loadingInvoice && invoiceId;

  // Data
  const clients: Family[] = clientsData;
  const settings = settingsData;
  const fundingSources: FundingSource[] = fundingSourcesData.filter(f => f.is_active);

  // Load defaults from settings (only for new invoices)
  useEffect(() => {
    if (settings && !invoiceId) {
      setInvoice(prev => ({
        ...prev,
        tax_rate: settings.default_tax_rate || 0,
        notes: settings.default_notes || '',
        terms: settings.default_terms || '',
      }));
    }
  }, [settings, invoiceId]);

  // Load template data when "Use Template" is clicked
  useEffect(() => {
    if (templateData && !invoiceId) {
      const lineItems: LineItem[] = (templateData.line_items || []).map((item) => ({
        id: crypto.randomUUID(),
        item_type: (item.item_type || 'service_flat') as LineItemType,
        description: item.description || '',
        full_rate: item.full_rate,
        subsidy_amount: item.subsidy_amount,
        hours: item.hours,
        hourly_rate: item.hourly_rate,
        quantity: item.quantity || 1,
        unit_price: item.unit_price,
        amount: item.amount || 0,
      }));

      setInvoice(prev => ({
        ...prev,
        line_items: lineItems.length > 0 ? lineItems : [createEmptyLineItem()],
        tax_rate: templateData.default_tax_rate ?? prev.tax_rate,
        discount_type: templateData.default_discount_percentage ? 'percentage' : 'amount',
        discount_value: templateData.default_discount_percentage || templateData.default_discount_amount || 0,
        due_date: getDateFromNow(templateData.due_days || 30),
        notes: templateData.notes || prev.notes,
        terms: templateData.terms || prev.terms,
      }));
    }
  }, [templateData, invoiceId]);

  // Load existing invoice data when editing
  useEffect(() => {
    if (existingInvoiceData && invoiceId) {
      const inv = existingInvoiceData;
      
      // Set selected family
      if (inv.family_id) {
        setSelectedFamilyIds([inv.family_id]);
      }
      
      // Map line items
      const lineItems: LineItem[] = (inv.line_items || []).map((item) => ({
        id: item.id || crypto.randomUUID(),
        item_type: item.item_type as LineItemType,
        description: item.description || '',
        child_id: item.child_id,
        child_name: item.child_name,
        full_rate: item.full_rate,
        subsidy_amount: item.subsidy_amount,
        hours: item.hours,
        hourly_rate: item.hourly_rate,
        quantity: item.quantity || 1,
        unit_price: item.unit_price,
        amount: item.amount || 0,
      }));

      setInvoice({
        invoice_number: inv.invoice_number || '',
        file_number: inv.file_number || '',
        family_id: inv.family_id || '',
        guardian_id: inv.guardian_id || '',
        client_name: inv.client_name || '',
        client_email: inv.client_email || '',
        client_address: inv.client_address || '',
        recipient_id: inv.recipient_id || '',
        issue_date: (inv.issue_date || getToday()).substring(0, 10),
        due_date: (inv.due_date || getDateFromNow(30)).substring(0, 10),
        period_start: inv.period_start ? inv.period_start.substring(0, 10) : '',
        period_end: inv.period_end ? inv.period_end.substring(0, 10) : '',
        line_items: lineItems.length > 0 ? lineItems : [createEmptyLineItem()],
        discount_type: inv.discount_percentage ? 'percentage' : 'amount',
        discount_value: inv.discount_percentage || inv.discount_amount || 0,
        tax_rate: inv.tax_rate ?? 0,
        notes: inv.notes || '',
        terms: inv.terms || '',
      });
    }
  }, [existingInvoiceData, invoiceId]);

  // Calculate totals
  const totals = useMemo(() => {
    return calculateInvoiceTotals(
      invoice.line_items,
      invoice.discount_type,
      invoice.discount_value,
      invoice.tax_rate
    );
  }, [invoice.line_items, invoice.discount_type, invoice.discount_value, invoice.tax_rate]);

  // Handle multi-client selection
  const handleMultiClientSelect = async (familyIds: string[]) => {
    setSelectedFamilyIds(familyIds);
    
    if (familyIds.length === 0) {
      // Clear client info if no families selected
      setInvoice(prev => ({
        ...prev,
        family_id: '',
        guardian_id: '',
        client_name: '',
        client_email: '',
        client_address: '',
        line_items: [createEmptyLineItem()],
      }));
      return;
    }

    // Get selected families and build combined client info
    const selectedFams = clients.filter(f => familyIds.includes(f.id));
    
    // Build combined client name (all guardian names)
    const clientNames = selectedFams.map(family => {
      const guardian = family.guardians?.[0];
      return guardian ? `${guardian.first_name} ${guardian.last_name}` : family.name;
    }).join(', ');

    // Get emails from all guardians
    const clientEmails = selectedFams
      .map(f => f.guardians?.[0]?.email)
      .filter(Boolean)
      .join('; ');

    // Use first family's address (or combine if needed)
    const firstFamily = selectedFams[0];
    const firstGuardian = firstFamily?.guardians?.[0];
    const clientAddress = firstGuardian?.address 
      ? `${firstGuardian.address}${firstGuardian.city ? `, ${firstGuardian.city}` : ''}${firstGuardian.postal_code ? ` ${firstGuardian.postal_code}` : ''}`
      : '';

    // Try to get last invoice from first selected family for defaults
    try {
      const data = await api.get<{ items: EditInvoiceResponse['invoice'][] }>('/invoicing/invoices', {
        family_id: familyIds[0],
        limit: 1,
      });
      const lastInvoice = data.items[0];

      if (lastInvoice) {
        // Import line items from last invoice
        const lineItems: LineItem[] = (lastInvoice.line_items || []).map(item => ({
          id: crypto.randomUUID(),
          item_type: item.item_type as LineItem['item_type'],
          description: item.description || '',
          child_id: item.child_id,
          child_name: item.child_name,
          full_rate: item.full_rate,
          subsidy_amount: item.subsidy_amount,
          hours: item.hours,
          hourly_rate: item.hourly_rate,
          quantity: item.quantity || 1,
          unit_price: item.unit_price,
          amount: item.amount || 0,
        }));

        setInvoice(prev => ({
          ...prev,
          family_id: familyIds[0], // Primary family ID
          guardian_id: firstGuardian?.id || '',
          client_name: clientNames,
          client_email: clientEmails,
          client_address: clientAddress,
          file_number: lastInvoice.file_number || '',
          line_items: lineItems.length > 0 ? lineItems : [createEmptyLineItem()],
          discount_type: lastInvoice.discount_percentage ? 'percentage' : 'amount',
          discount_value: lastInvoice.discount_percentage || lastInvoice.discount_amount || 0,
          tax_rate: lastInvoice.tax_rate ?? prev.tax_rate,
          notes: lastInvoice.notes || prev.notes,
          terms: lastInvoice.terms || prev.terms,
        }));
      } else {
        setInvoice(prev => ({
          ...prev,
          family_id: familyIds[0],
          guardian_id: firstGuardian?.id || '',
          client_name: clientNames,
          client_email: clientEmails,
          client_address: clientAddress,
        }));
      }
    } catch {
      setInvoice(prev => ({
        ...prev,
        family_id: familyIds[0],
        guardian_id: firstGuardian?.id || '',
        client_name: clientNames,
        client_email: clientEmails,
        client_address: clientAddress,
      }));
    }
    
  };

  // Get all children from all selected families for line items
  const children = useMemo(() => {
    const selectedFams = clients.filter(f => selectedFamilyIds.includes(f.id));
    return selectedFams.flatMap(f => f.children || []);
  }, [clients, selectedFamilyIds]);

  // Line item handlers
  const addLineItem = (type: LineItemType) => {
    setInvoice(prev => ({
      ...prev,
      line_items: [...prev.line_items, createEmptyLineItem(type)],
    }));
  };

  const updateLineItem = (id: string, updates: Partial<LineItem>) => {
    setInvoice(prev => ({
      ...prev,
      line_items: prev.line_items.map(item => 
        item.id === id ? { ...item, ...updates } : item
      ),
    }));
  };

  const removeLineItem = (id: string) => {
    setInvoice(prev => ({
      ...prev,
      line_items: prev.line_items.filter(item => item.id !== id),
    }));
  };

  // Pre-fill line items dynamically from rate_schedules + child_funding
  const handlePrefillChildren = useCallback(async () => {
    if (selectedFamilyIds.length === 0) return;
    
    try {
      setPrefillingLoading(true);
      const result = await api.get<{
        children: Array<{
          child_id: string;
          child_name: string;
          age_group: string;
          full_rate: number;
          subsidy: number;
          parent_portion: number;
          funding_sources: string[];
        }>;
      }>(`/invoicing/prefill/${selectedFamilyIds[0]}`);
      
      if (!result || result.children.length === 0) {
        alert('No rate data found. Please configure rate schedules and child funding first.');
        return;
      }

      // Check if any children have $0 rates (no rate schedule configured)
      const missingRates = result.children.filter(c => c.full_rate === 0);
      if (missingRates.length > 0) {
        const names = missingRates.map(c => c.child_name).join(', ');
        alert(`No rate schedule found for: ${names}. Please configure rate schedules for their age groups.`);
      }

      const prefilled: LineItem[] = result.children
        .filter(c => c.full_rate > 0)
        .map(child => ({
          id: generateId(),
          item_type: 'daycare_subsidy' as LineItemType,
          description: `${child.child_name} \u2014 Childcare`,
          child_id: child.child_id,
          child_name: child.child_name,
          full_rate: child.full_rate,
          subsidy_amount: child.subsidy,
          amount: child.parent_portion,
        }));

      if (prefilled.length > 0) {
        setInvoice(prev => ({ ...prev, line_items: prefilled }));
      }
    } catch (err) {
      console.error('Error fetching prefilled line items:', err);
      alert('Error loading rates. Check console for details.');
    } finally {
      setPrefillingLoading(false);
    }
  }, [selectedFamilyIds]);

  // Add an additional flat charge line item
  const handleAddAdditionalCharge = useCallback(() => {
    setInvoice(prev => ({
      ...prev,
      line_items: [
        ...prev.line_items,
        {
          id: generateId(),
          item_type: 'service_flat' as LineItemType,
          description: 'Additional Charge',
          quantity: 1,
          amount: 0,
        },
      ],
    }));
  }, []);


  // Save invoice (create or update)
  const handleSave = async (status: 'draft' | 'sent' = 'draft') => {
    setSaving(true);
    try {
      if (invoiceId) {
        // Update existing invoice - now includes line_items
        const updateInput = {
          client_name: invoice.client_name,
          client_email: invoice.client_email,
          client_address: invoice.client_address,
          recipient_id: invoice.recipient_id || undefined,
          file_number: invoice.file_number || undefined,
          issue_date: invoice.issue_date,
          due_date: invoice.due_date,
          period_start: invoice.period_start || undefined,
          period_end: invoice.period_end || undefined,
          discount_amount: invoice.discount_type === 'amount' ? invoice.discount_value : undefined,
          discount_percentage: invoice.discount_type === 'percentage' ? invoice.discount_value : undefined,
          tax_rate: invoice.tax_rate,
          notes: invoice.notes || undefined,
          terms: invoice.terms || undefined,
          status,
          line_items: invoice.line_items.map(item => ({
            item_type: item.item_type,
            description: item.description,
            child_id: item.child_id || undefined,
            child_name: item.child_name || undefined,
            full_rate: item.full_rate,
            subsidy_amount: item.subsidy_amount,
            hours: item.hours,
            hourly_rate: item.hourly_rate,
            quantity: item.quantity,
            unit_price: item.unit_price,
            amount: calculateLineItemAmount(item),
          })),
        };
        await api.patch(`/invoicing/invoices/${invoiceId}`, updateInput);
      } else {
        // Create new invoice - full input with line_items
        const createInput = {
          family_id: invoice.family_id || undefined,
          guardian_id: invoice.guardian_id || undefined,
          client_name: invoice.client_name,
          client_email: invoice.client_email,
          client_address: invoice.client_address,
          recipient_id: invoice.recipient_id || undefined,
          file_number: invoice.file_number || undefined,
          issue_date: invoice.issue_date,
          due_date: invoice.due_date,
          period_start: invoice.period_start || undefined,
          period_end: invoice.period_end || undefined,
          status,
          line_items: invoice.line_items.map(item => ({
            item_type: item.item_type,
            description: item.description,
            child_id: item.child_id || undefined,
            child_name: item.child_name || undefined,
            full_rate: item.full_rate,
            subsidy_amount: item.subsidy_amount,
            hours: item.hours,
            hourly_rate: item.hourly_rate,
            quantity: item.quantity,
            unit_price: item.unit_price,
            amount: calculateLineItemAmount(item),
          })),
          discount_amount: invoice.discount_type === 'amount' ? invoice.discount_value : undefined,
          discount_percentage: invoice.discount_type === 'percentage' ? invoice.discount_value : undefined,
          tax_rate: invoice.tax_rate,
          notes: invoice.notes || undefined,
          terms: invoice.terms || undefined,
        };
        await api.post('/invoicing/invoices', createInput);
      }
      onSaved();
    } catch (error) {
      console.error('Error saving invoice:', error);
      alert('Error saving invoice');
    } finally {
      setSaving(false);
    }
  };

  // Loading state when fetching existing invoice
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-4"></div>
          <p className="text-gray-500">Loading invoice...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {/* Left Panel: Invoice Form */}
      <div className="space-y-6">
        {/* Invoice Details */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {invoiceId ? 'Edit Invoice' : 'Invoice Details'}
          </h2>
          
          {/* Invoice Number & File Number */}
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Invoice #</label>
              {invoiceId && invoice.invoice_number ? (
                <div className="w-full px-3 py-2 bg-gray-100 text-gray-700 border border-gray-300 rounded-lg font-medium">
                  {invoice.invoice_number}
                </div>
              ) : (
                <div className="w-full px-3 py-2 bg-gray-100 text-gray-500 border border-gray-300 rounded-lg italic">
                  Auto-generated on save
                </div>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">File/Case # (optional)</label>
              <input
                type="text"
                value={invoice.file_number}
                onChange={(e) => setInvoice(prev => ({ ...prev, file_number: e.target.value }))}
                placeholder="e.g., FSCD-12345"
                className="input"
              />
            </div>
          </div>

          {/* Client Selection (Multi-select) */}
          <div className="mb-4">
            <MultiClientSelector
              families={clients}
              selectedFamilyIds={selectedFamilyIds}
              onSelect={handleMultiClientSelect}
            />
          </div>

          {/* Selected Clients Summary */}
          {selectedFamilyIds.length > 0 && (
            <div className="mb-4">
              <SelectedClientsSummary
                families={clients}
                selectedFamilyIds={selectedFamilyIds}
              />
            </div>
          )}

          {/* Client Info (editable) */}
          {selectedFamilyIds.length > 0 && (
            <div className="mb-4">
              <ClientInfoDisplay
                clientName={invoice.client_name}
                fileNumber={invoice.file_number}
                clientAddress={invoice.client_address}
                onNameChange={(v) => setInvoice(prev => ({ ...prev, client_name: v }))}
                onFileNumberChange={(v) => setInvoice(prev => ({ ...prev, file_number: v }))}
                onAddressChange={(v) => setInvoice(prev => ({ ...prev, client_address: v }))}
              />
            </div>
          )}

          {/* Funding Source */}
          <div className="mb-4">
            <FundingSourceSelector
              fundingSources={fundingSources}
              selectedId={invoice.recipient_id}
              onSelect={(id) => setInvoice(prev => ({ ...prev, recipient_id: id }))}
            />
          </div>

          {/* Dates */}
          <div className="mb-4">
            <DateRangePicker
              startDate={invoice.issue_date}
              endDate={invoice.due_date}
              onStartChange={(v) => setInvoice(prev => ({ ...prev, issue_date: v }))}
              onEndChange={(v) => setInvoice(prev => ({ ...prev, due_date: v }))}
              startLabel="Invoice Date"
              endLabel="Due Date"
            />
          </div>

          {/* Period */}
          <DateRangePicker
            startDate={invoice.period_start}
            endDate={invoice.period_end}
            onStartChange={(v) => setInvoice(prev => ({ ...prev, period_start: v }))}
            onEndChange={(v) => setInvoice(prev => ({ ...prev, period_end: v }))}
            startLabel="Period Start"
            endLabel="Period End"
            optional
          />
        </div>

        {/* Line Items */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex flex-wrap justify-between items-center gap-2 mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Line Items</h2>
            <div className="flex items-center gap-2">
              {children.length > 0 && (
                <button
                  type="button"
                  onClick={handlePrefillChildren}
                  disabled={prefillingLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:from-amber-600 hover:to-orange-600 shadow-sm transition-all disabled:opacity-50"
                  title={`Pre-fill ${children.length} child(ren) from rate schedules`}
                >
                  {prefillingLoading ? '...' : '⚡'} Pre-fill ({children.length})
                </button>
              )}
              <button
                type="button"
                onClick={handleAddAdditionalCharge}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-all"
              >
                + Additional Charge
              </button>
              <AddLineItemButtons onAdd={addLineItem} />
            </div>
          </div>

          <div className="space-y-4">
            {invoice.line_items.map((item) => (
              <LineItemEditor
                key={item.id}
                item={item}
                onChange={(updates) => updateLineItem(item.id, updates)}
                onRemove={() => removeLineItem(item.id)}
                canRemove={invoice.line_items.length > 1}
                children={children}
                currencySymbol={settings?.currency_symbol}
              />
            ))}
          </div>
        </div>

        {/* Discount, Tax, Notes */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <DiscountTaxFields
            discountType={invoice.discount_type}
            discountValue={invoice.discount_value}
            taxRate={invoice.tax_rate}
            taxName={settings?.tax_name}
            onDiscountTypeChange={(t) => setInvoice(prev => ({ ...prev, discount_type: t }))}
            onDiscountValueChange={(v) => setInvoice(prev => ({ ...prev, discount_value: v }))}
            onTaxRateChange={(v) => setInvoice(prev => ({ ...prev, tax_rate: v }))}
          />

          <div className="mt-4">
            <NotesTermsFields
              notes={invoice.notes}
              terms={invoice.terms}
              onNotesChange={(v) => setInvoice(prev => ({ ...prev, notes: v }))}
              onTermsChange={(v) => setInvoice(prev => ({ ...prev, terms: v }))}
            />
          </div>
        </div>

        {/* Actions - Sticky on mobile */}
        <div className="sticky bottom-0 bg-white border-t border-gray-200 -mx-6 px-6 py-4 sm:relative sm:border-0 sm:mx-0 sm:px-0 sm:py-0 sm:mt-0">
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
            <button
              onClick={onCancel}
              className="order-3 sm:order-1 px-4 py-2.5 sm:py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 text-sm sm:text-base"
            >
              Cancel
            </button>
            <button
              onClick={() => handleSave('draft')}
              disabled={saving}
              className="order-2 px-4 py-2.5 sm:py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 text-sm sm:text-base"
            >
              Save as Draft
            </button>
            <button
              onClick={() => handleSave('sent')}
              disabled={saving}
              className="order-1 sm:order-3 flex-1 px-4 py-2.5 sm:py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm sm:text-base font-medium"
            >
              {saving ? 'Saving...' : 'Save & Send'}
            </button>
          </div>
        </div>
      </div>

      {/* Right Panel: Live Preview */}
      <InvoicePreview
        settings={settings}
        clientName={invoice.client_name}
        clientEmail={invoice.client_email}
        clientAddress={invoice.client_address}
        fileNumber={invoice.file_number}
        issueDate={invoice.issue_date}
        dueDate={invoice.due_date}
        periodStart={invoice.period_start}
        periodEnd={invoice.period_end}
        lineItems={invoice.line_items}
        totals={totals}
        taxRate={invoice.tax_rate}
        notes={invoice.notes}
        terms={invoice.terms}
        currencySymbol={settings?.currency_symbol}
      />
    </div>
  );
};

export default CreateInvoice;
