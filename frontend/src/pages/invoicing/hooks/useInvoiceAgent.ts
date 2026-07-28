// ============================================
// Invoice Agent Hook - Manages AI chat state
// ============================================

import { useState, useCallback, useEffect, useRef } from 'react';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';
import { generatePrintableInvoice } from '../components/invoice/InvoicePrintTemplate';
import type { Invoice, InvoiceSettings } from '../types';
import JSZip from 'jszip';

const STORAGE_KEY = 'caresync_agent_chat_history';

export interface ParsedLineItem {
  item_type: string;
  description: string;
  child_name?: string;
  full_rate?: number;
  subsidy_amount?: number;
  hours?: number;
  hourly_rate?: number;
  quantity?: number;
  unit_price?: number;
  amount: number;
}

export interface ParsedInvoice {
  family_name?: string;
  client_name?: string;
  client_email?: string;
  children?: string[];
  line_items: ParsedLineItem[];
  issue_date?: string;
  due_date?: string;
  period_start?: string;
  period_end?: string;
  notes?: string;
  total_estimate?: number;
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  invoices?: ParsedInvoice[];
  confidence?: number;
  needs_clarification?: boolean;
  timestamp: Date;
  actions?: AgentAction[];
  // IDs of invoices created from this message's bulk action
  createdInvoiceIds?: string[];
}

export interface AgentAction {
  id: string;
  label: string;
  description: string;
  type: 'bulk_generate' | 'send_message';
  payload?: any;
  icon: string;
}

// Types from existing queries
interface FamilyClient {
  id: string;
  name: string;
  is_recurring_billing: boolean;
  recurring_funding_source_id?: string;
  guardians: Array<{ id: string; first_name: string; last_name: string; email?: string }>;
  children: Array<{ id: string; first_name: string; last_name: string }>;
  last_invoice_date?: string;
  status?: string;
}

interface FundingSourceData {
  id: string;
  name: string;
  funding_type: string;
  is_active: boolean;
}

interface InvoiceItem {
  id: string;
  invoice_number: string;
  client_name?: string;
  family?: { id: string; name: string };
  recipient?: { id: string; name: string };
  status: string;
  total_amount: number;
  balance_due: number;
  issue_date: string;
  due_date: string;
  period_start?: string;
  period_end?: string;
}

interface InvoiceAgentResult {
  message: string;
  invoices: ParsedInvoice[];
  confidence: number;
  needs_clarification: boolean;
  created_invoice_ids?: string[];
}

interface InvoiceListResult {
  items: InvoiceItem[];
  total: number;
}

interface BulkInvoiceResult {
  items: Invoice[];
  generated: number;
  errors: string[];
}

// ---- LocalStorage helpers ----
function saveHistory(messages: AgentMessage[]) {
  try {
    // Only save non-system messages to keep it lightweight
    const toSave = messages
      .filter(m => m.role !== 'system')
      .map(m => ({
        ...m,
        timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
      }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch { /* quota exceeded or unavailable */ }
}

function loadHistory(): AgentMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return (parsed as any[]).map(m => ({
      ...m,
      timestamp: new Date(m.timestamp),
    }));
  } catch {
    return [];
  }
}

export function useInvoiceAgent() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [createdInvoiceIds, setCreatedInvoiceIds] = useState<Set<number>>(new Set());
  const [contextLoaded, setContextLoaded] = useState(false);
  const hasInitialized = useRef(false);

  // Load system context data
  const { data: clientsData = [], loading: loadingClients, refetch: refetchClients } = useApiQuery<FamilyClient[]>('/families', { limit: 1000 });
  const { data: fundingData = [], loading: loadingFunding } = useApiQuery<FundingSourceData[]>('/resources/funding_sources', { limit: 1000 });
  const { data: invoicesData, loading: loadingInvoices, refetch: refetchInvoices } = useApiQuery<InvoiceListResult>(
    '/invoicing/invoices',
    { limit: 50, status: 'draft' },
  );
  const { data: settings = null } = useApiQuery<InvoiceSettings | null>('/invoicing/settings');

  const families = clientsData;
  const fundingSources = fundingData.filter(fs => fs.is_active);
  const draftInvoices = invoicesData?.items || [];

  const isLoading = loadingClients || loadingFunding || loadingInvoices;

  // Persist messages whenever they change (skip system msgs)
  useEffect(() => {
    if (messages.length > 0) {
      saveHistory(messages);
    }
  }, [messages]);

  // Build the initial context message once data is loaded
  useEffect(() => {
    if (isLoading || contextLoaded || hasInitialized.current) return;
    hasInitialized.current = true;

    const activeFamilies = families.filter(f => f.status === 'active' || !f.status);
    const recurringFamilies = families.filter(f => f.is_recurring_billing);

    // Group recurring families by funding source
    const fundingGroups: Record<string, { source: FundingSourceData; families: FamilyClient[] }> = {};
    for (const family of recurringFamilies) {
      const fsId = family.recurring_funding_source_id;
      if (!fsId) continue;
      const source = fundingSources.find(fs => fs.id === fsId);
      if (!source) continue;
      if (!fundingGroups[fsId]) {
        fundingGroups[fsId] = { source, families: [] };
      }
      fundingGroups[fsId].families.push(family);
    }

    // Check which families might need invoices
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const familiesWithRecentInvoice = new Set(
      draftInvoices
        .filter(inv => inv.issue_date?.startsWith(currentMonth))
        .map(inv => inv.family?.id)
        .filter(Boolean)
    );
    const familiesNeedingInvoice = activeFamilies.filter(f => !familiesWithRecentInvoice.has(f.id));

    // Build the context summary message
    const lines: string[] = [];
    lines.push(`👋 I've analyzed your invoicing data. Here's what I found:\n`);
    lines.push(`**📊 Overview**`);
    lines.push(`- **${activeFamilies.length}** active families with **${activeFamilies.reduce((sum, f) => sum + (f.children?.length || 0), 0)}** children`);
    lines.push(`- **${fundingSources.length}** funding sources configured`);
    lines.push(`- **${draftInvoices.length}** draft invoices pending`);
    if (familiesNeedingInvoice.length > 0) {
      lines.push(`- **${familiesNeedingInvoice.length}** families may need invoices this month`);
    }
    lines.push('');

    if (Object.keys(fundingGroups).length > 0) {
      lines.push(`**💰 Funding Sources with Recurring Families:**`);
      for (const [, group] of Object.entries(fundingGroups)) {
        const childCount = group.families.reduce((sum, f) => sum + (f.children?.length || 0), 0);
        lines.push(`- **${group.source.name}** (${group.source.funding_type}) — ${group.families.length} families, ${childCount} children`);
      }
      lines.push('');
    }

    if (draftInvoices.length > 0) {
      lines.push(`**📄 Existing Draft Invoices:**`);
      for (const inv of draftInvoices.slice(0, 8)) {
        lines.push(`- ${inv.invoice_number} — ${inv.client_name || inv.family?.name || 'Unknown'} — $${Number(inv.total_amount || 0).toFixed(2)}`);
      }
      if (draftInvoices.length > 8) {
        lines.push(`- _...and ${draftInvoices.length - 8} more_`);
      }
      lines.push('');
    }

    lines.push(`**What would you like to do?** You can:`);
    lines.push(`1. Paste emails and I'll generate invoices from them`);
    lines.push(`2. Click a quick action below to generate bulk invoices`);
    lines.push(`3. Ask me anything about your invoicing data`);

    // Build action suggestions
    const actions: AgentAction[] = [];
    for (const [fsId, group] of Object.entries(fundingGroups)) {
      actions.push({
        id: `bulk_${fsId}`,
        label: `Generate ${group.source.name} invoices`,
        description: `${group.families.length} families, ${group.families.reduce((s, f) => s + (f.children?.length || 0), 0)} children`,
        type: 'bulk_generate',
        payload: {
          funding_source_id: fsId,
          funding_source_name: group.source.name,
          family_ids: group.families.map(f => f.id),
        },
        icon: group.source.name === 'EMCN' ? '🔵' : '🟢',
      });
    }
    if (familiesNeedingInvoice.length > 0) {
      actions.push({
        id: 'bulk_all_needing',
        label: `Invoice all ${familiesNeedingInvoice.length} families needing invoices`,
        description: `Families without an invoice this month`,
        type: 'bulk_generate',
        payload: { family_ids: familiesNeedingInvoice.map(f => f.id) },
        icon: '⚡',
      });
    }

    const contextMsg: AgentMessage = {
      id: 'context-' + Date.now(),
      role: 'system',
      content: lines.join('\n'),
      timestamp: new Date(),
      actions,
    };

    // Restore saved chat history and prepend context message
    const savedHistory = loadHistory();
    setMessages([contextMsg, ...savedHistory]);
    setContextLoaded(true);
  }, [isLoading, contextLoaded, families, fundingSources, draftInvoices]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isProcessing) return;

    const userMsg: AgentMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsProcessing(true);

    try {
      const history = messages
        .filter(m => m.role !== 'system')
        .map(m => ({ role: m.role as string, content: m.content }));

      const result = await api.post<InvoiceAgentResult>('/ai/invoice-agent', {
        message: text,
        conversation_history: history,
      });

      if (result) {
        const assistantMsg: AgentMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: result.message,
          invoices: result.invoices?.length ? result.invoices : undefined,
          confidence: result.confidence,
          needs_clarification: result.needs_clarification,
          timestamp: new Date(),
          createdInvoiceIds: result.created_invoice_ids?.length ? result.created_invoice_ids : undefined,
        };
        setMessages(prev => [...prev, assistantMsg]);
      }
    } catch (error) {
      const errorMsg: AgentMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Sorry, I encountered an error processing your request. Please try again.\n\nError: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsProcessing(false);
    }
  }, [messages, isProcessing]);

  const executeBulkAction = useCallback(async (action: AgentAction) => {
    if (action.type !== 'bulk_generate') return;
    setIsProcessing(true);

    const actionMsg: AgentMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: `${action.icon} ${action.label}`,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, actionMsg]);

    try {
      const now = new Date();
      const y = now.getFullYear();
      const m = now.getMonth();
      const firstDay = `${y}-${String(m + 1).padStart(2, '0')}-01`;
      const lastDay = new Date(y, m + 1, 0).getDate();
      const lastDate = `${y}-${String(m + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
      const today = now.toISOString().substring(0, 10);
      const dueDate = new Date(Date.now() + 30 * 86400000).toISOString().substring(0, 10);

      const bulkResult = await api.post<BulkInvoiceResult>('/invoicing/invoices/bulk-generate', {
        family_ids: action.payload.family_ids,
        recipient_id: action.payload.funding_source_id || undefined,
        issue_date: today,
        due_date: dueDate,
        period_start: firstDay,
        period_end: lastDate,
      });

      const generated = bulkResult.items || [];
      const count = bulkResult.generated || generated.length;
      const invoiceIds = generated.map(inv => inv.id);
      await Promise.all([refetchInvoices(), refetchClients()]);

      const successMsg: AgentMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `✅ **Done!** I generated **${count} invoice(s)** as drafts${action.payload.funding_source_name ? ` for **${action.payload.funding_source_name}**` : ''}.\n\n- Period: ${firstDay} → ${lastDate}\n- Issue date: ${today}\n- Due date: ${dueDate}\n- Status: Draft (ready for review)\n\nUse the **Print** or **Download** buttons below to get them. You can also find them in the **Overview** tab.`,
        timestamp: new Date(),
        createdInvoiceIds: invoiceIds,
      };
      setMessages(prev => [...prev, successMsg]);
    } catch (error) {
      const errorMsg: AgentMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `❌ Failed to generate invoices: ${error instanceof Error ? error.message : 'Unknown error'}\n\nWould you like me to try again?`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsProcessing(false);
    }
  }, [refetchClients, refetchInvoices]);

  // ---- Print / Download created invoices ----
  const printCreatedInvoices = useCallback(async (invoiceIds: string[]) => {
    if (invoiceIds.length === 0) return;

    const fullInvoices: Invoice[] = [];
    for (const id of invoiceIds) {
      try {
        fullInvoices.push(await api.get<Invoice>(`/invoicing/invoices/${id}`));
      } catch { /* skip */ }
    }

    if (fullInvoices.length === 0) return;

    const allHtml = fullInvoices
      .map(inv => generatePrintableInvoice(inv, settings))
      .join('<div style="page-break-after: always;"></div>');

    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(allHtml);
      printWindow.document.close();
      printWindow.onload = () => printWindow.print();
    }
  }, [settings]);

  const downloadCreatedInvoices = useCallback(async (invoiceIds: string[]) => {
    if (invoiceIds.length === 0) return;

    const fullInvoices: Invoice[] = [];
    for (const id of invoiceIds) {
      try {
        fullInvoices.push(await api.get<Invoice>(`/invoicing/invoices/${id}`));
      } catch { /* skip */ }
    }

    if (fullInvoices.length === 0) return;

    // Build CSV
    const headers = ['Invoice Number', 'Client', 'Issue Date', 'Due Date', 'Total', 'Status'];
    const rows = fullInvoices.map(inv => [
      inv.invoice_number,
      inv.client_name || inv.family?.name || '',
      inv.issue_date || '',
      inv.due_date || '',
      Number(inv.total_amount || 0).toFixed(2),
      inv.status,
    ]);

    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `agent_invoices_${new Date().toISOString().substring(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

  const downloadInvoicesAsZip = useCallback(async (invoiceIds: string[]) => {
    if (invoiceIds.length === 0) return;

    const fullInvoices: Invoice[] = [];
    for (const id of invoiceIds) {
      try {
        fullInvoices.push(await api.get<Invoice>(`/invoicing/invoices/${id}`));
      } catch { /* skip */ }
    }

    if (fullInvoices.length === 0) return;

    const zip = new JSZip();

    // Add each invoice as an individual HTML file
    for (const inv of fullInvoices) {
      const html = generatePrintableInvoice(inv, settings);
      const fileName = `${inv.invoice_number || 'invoice'}_${(inv.client_name || inv.family?.name || 'client').replace(/[^a-zA-Z0-9]/g, '_')}.html`;
      zip.file(fileName, html);
    }

    // Also add a summary CSV
    const headers = ['Invoice Number', 'Client', 'Issue Date', 'Due Date', 'Total', 'Status'];
    const rows = fullInvoices.map(inv => [
      inv.invoice_number,
      inv.client_name || inv.family?.name || '',
      inv.issue_date || '',
      inv.due_date || '',
      Number(inv.total_amount || 0).toFixed(2),
      inv.status,
    ]);
    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    zip.file('summary.csv', csvContent);

    // Generate and download
    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `invoices_${new Date().toISOString().substring(0, 10)}.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [settings]);

  const createInvoiceFromParsed = useCallback(async (invoice: ParsedInvoice, messageIndex: number, invoiceIndex: number) => {
    const key = messageIndex * 1000 + invoiceIndex;
    if (createdInvoiceIds.has(key)) return { success: false, error: 'Already created' };

    try {
      const lineItems = invoice.line_items.map(item => ({
        item_type: item.item_type,
        description: item.description,
        child_name: item.child_name || undefined,
        full_rate: item.full_rate,
        subsidy_amount: item.subsidy_amount,
        hours: item.hours,
        hourly_rate: item.hourly_rate,
        quantity: item.quantity,
        unit_price: item.unit_price,
        amount: item.amount,
      }));

      const input = {
        client_name: invoice.client_name || invoice.family_name || '',
        client_email: invoice.client_email || '',
        issue_date: invoice.issue_date || new Date().toISOString().substring(0, 10),
        due_date: invoice.due_date || new Date(Date.now() + 30 * 86400000).toISOString().substring(0, 10),
        period_start: invoice.period_start || undefined,
        period_end: invoice.period_end || undefined,
        line_items: lineItems,
        notes: invoice.notes || undefined,
        status: 'draft',
      };

      const created = await api.post<Invoice>('/invoicing/invoices', input);
      if (created) {
        setCreatedInvoiceIds(prev => new Set([...prev, key]));
        await Promise.all([refetchInvoices(), refetchClients()]);
        return { success: true, invoiceNumber: created.invoice_number, invoiceId: created.id };
      }
      return { success: false, error: 'No data returned' };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }, [createdInvoiceIds, refetchClients, refetchInvoices]);

  const createAllInvoices = useCallback(async (invoices: ParsedInvoice[], messageIndex: number) => {
    const results = [];
    for (let i = 0; i < invoices.length; i++) {
      const key = messageIndex * 1000 + i;
      if (!createdInvoiceIds.has(key)) {
        const result = await createInvoiceFromParsed(invoices[i], messageIndex, i);
        results.push({ index: i, ...result });
      }
    }
    return results;
  }, [createInvoiceFromParsed, createdInvoiceIds]);

  const clearConversation = useCallback(() => {
    setMessages([]);
    setCreatedInvoiceIds(new Set());
    setContextLoaded(false);
    hasInitialized.current = false;
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const isInvoiceCreated = useCallback((messageIndex: number, invoiceIndex: number) => {
    return createdInvoiceIds.has(messageIndex * 1000 + invoiceIndex);
  }, [createdInvoiceIds]);

  return {
    messages,
    isProcessing,
    isLoading,
    sendMessage,
    executeBulkAction,
    createInvoiceFromParsed,
    createAllInvoices,
    clearConversation,
    isInvoiceCreated,
    printCreatedInvoices,
    downloadCreatedInvoices,
    downloadInvoicesAsZip,
    families,
    fundingSources,
    draftInvoices,
  };
}
