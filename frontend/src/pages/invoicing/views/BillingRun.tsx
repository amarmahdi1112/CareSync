import React, { useMemo, useState } from 'react';
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';
import { useNotifications } from '../../../components/ui/NotificationContainer';
import type { Family, FundingSource } from '../types';
import { formatCurrencyIntl } from '../utils/formatters';

interface PreviewChild {
  child_id: string;
  child_name: string;
  age_group?: string;
  full_rate: number;
  subsidy: number;
  parent_portion: number;
  funding_sources: string[];
}

interface PreviewFamily {
  family_id: string;
  family_name: string;
  guardian_name?: string;
  guardian_email?: string;
  children: PreviewChild[];
  total_full_rate: number;
  total_subsidy: number;
  total_parent_portion: number;
  existing_invoice?: { id: string; invoice_number: string; status: string };
  warnings: string[];
  ready: boolean;
}

interface BillingPreview {
  items: PreviewFamily[];
  summary: {
    families: number;
    ready: number;
    needs_attention: number;
    existing: number;
    total_full_rate: number;
    total_subsidy: number;
    total_parent_portion: number;
  };
}

interface GenerateResult {
  generated: number;
  items: Array<{ id: string; invoice_number: string }>;
  skipped: Array<{ family_name: string; invoice_number: string }>;
  errors: string[];
}

function monthDefaults() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const start = `${year}-${String(month + 1).padStart(2, '0')}-01`;
  const end = `${year}-${String(month + 1).padStart(2, '0')}-${String(new Date(year, month + 1, 0).getDate()).padStart(2, '0')}`;
  const issue = now.toISOString().slice(0, 10);
  const due = new Date(now.getTime() + 30 * 86400000).toISOString().slice(0, 10);
  return { start, end, issue, due };
}

const BillingRun: React.FC = () => {
  const { addNotification } = useNotifications();
  const defaults = useMemo(monthDefaults, []);
  const [periodStart, setPeriodStart] = useState(defaults.start);
  const [periodEnd, setPeriodEnd] = useState(defaults.end);
  const [issueDate, setIssueDate] = useState(defaults.issue);
  const [dueDate, setDueDate] = useState(defaults.due);
  const [recipientId, setRecipientId] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [preview, setPreview] = useState<BillingPreview | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);

  const { data: families = [], loading } = useApiQuery<Family[]>('/families', { limit: 1000 });
  const { data: fundingRows = [] } = useApiQuery<FundingSource[]>('/resources/funding_sources', { limit: 1000 });
  const activeFamilies = useMemo(() => families.filter(family => family.status === 'active'), [families]);
  const filteredFamilies = useMemo(() => {
    const term = search.trim().toLowerCase();
    return activeFamilies.filter(family => !term || family.name.toLowerCase().includes(term) || family.guardian_email?.toLowerCase().includes(term));
  }, [activeFamilies, search]);

  const invalidatePreview = () => {
    setPreview(null);
    setResult(null);
  };

  const toggleFamily = (id: string) => {
    setSelected(current => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    invalidatePreview();
  };

  const selectAllVisible = () => {
    setSelected(current => {
      const next = new Set(current);
      const allSelected = filteredFamilies.every(family => next.has(family.id));
      filteredFamilies.forEach(family => allSelected ? next.delete(family.id) : next.add(family.id));
      return next;
    });
    invalidatePreview();
  };

  const selectRecurring = () => {
    setSelected(new Set(activeFamilies.filter(family => family.is_recurring_billing).map(family => family.id)));
    invalidatePreview();
  };

  const requestPayload = {
    family_ids: Array.from(selected),
    recipient_id: recipientId || undefined,
    issue_date: issueDate,
    due_date: dueDate,
    period_start: periodStart,
    period_end: periodEnd,
  };

  const handlePreview = async (preserveResult = false) => {
    if (!selected.size) {
      addNotification({ type: 'warning', title: 'Choose Families', message: 'Select at least one family for this billing run.' });
      return;
    }
    setLoadingPreview(true);
    try {
      setPreview(await api.post<BillingPreview>('/invoicing/billing-runs/preview', requestPayload));
      if (!preserveResult) setResult(null);
    } catch (error) {
      addNotification({ type: 'error', title: 'Preview Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleGenerate = async () => {
    if (!preview) return;
    const readyIds = preview.items.filter(item => item.ready).map(item => item.family_id);
    if (!readyIds.length) {
      addNotification({ type: 'warning', title: 'Nothing Ready', message: 'Resolve the highlighted billing issues first.' });
      return;
    }
    setGenerating(true);
    try {
      const generated = await api.post<GenerateResult>('/invoicing/invoices/bulk-generate', {
        ...requestPayload,
        family_ids: readyIds,
        skip_existing: true,
      });
      setResult(generated);
      addNotification({
        type: generated.errors.length ? 'warning' : 'success',
        title: 'Billing Run Complete',
        message: `${generated.generated} draft invoice${generated.generated === 1 ? '' : 's'} created safely.`,
      });
      await handlePreview(true);
    } catch (error) {
      addNotification({ type: 'error', title: 'Generation Failed', message: error instanceof Error ? error.message : 'Request failed' });
    } finally {
      setGenerating(false);
    }
  };

  const dateInput = (label: string, value: string, setValue: (value: string) => void) => (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1.5">{label}</span>
      <input
        type="date"
        value={value}
        onChange={event => { setValue(event.target.value); invalidatePreview(); }}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
      />
    </label>
  );

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 text-white shadow-xl">
        <div className="grid gap-6 px-6 py-7 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-indigo-100">
              <ShieldCheckIcon className="h-4 w-4" /> Safe billing workflow
            </div>
            <h2 className="text-2xl font-bold tracking-tight">Monthly Billing Run</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              Review rates, subsidies, parent portions, missing information, and duplicate invoices before creating drafts.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <span className="rounded-full bg-indigo-500 px-3 py-1.5 text-white">1 Configure</span>
            <span>→</span><span>2 Review</span><span>→</span><span>3 Create drafts</span>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-3">
          <div className="rounded-xl bg-indigo-50 p-2.5"><CalendarDaysIcon className="h-5 w-5 text-indigo-600" /></div>
          <div><h3 className="font-semibold text-slate-900">Billing details</h3><p className="text-sm text-slate-500">One controlled run for one billing period</p></div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {dateInput('Period start', periodStart, setPeriodStart)}
          {dateInput('Period end', periodEnd, setPeriodEnd)}
          {dateInput('Issue date', issueDate, setIssueDate)}
          {dateInput('Due date', dueDate, setDueDate)}
          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1.5">Recipient</span>
            <select value={recipientId} onChange={event => { setRecipientId(event.target.value); invalidatePreview(); }} className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100">
              <option value="">Parent / direct billing</option>
              {fundingRows.filter(source => source.is_active).map(source => <option key={source.id} value={source.id}>{source.name}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-100 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div><h3 className="font-semibold text-slate-900">Families</h3><p className="text-sm text-slate-500">{selected.size} of {activeFamilies.length} active families selected</p></div>
          <div className="flex flex-wrap gap-2">
            <button onClick={selectRecurring} className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"><SparklesIcon className="mr-1.5 inline h-4 w-4" />Recurring families</button>
            <button onClick={selectAllVisible} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">Select visible</button>
            <button onClick={() => { setSelected(new Set()); invalidatePreview(); }} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50">Clear</button>
          </div>
        </div>
        <div className="border-b border-slate-100 p-4">
          <div className="relative max-w-md"><MagnifyingGlassIcon className="absolute left-3 top-2.5 h-5 w-5 text-slate-400" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search family or guardian email" className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-3 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" /></div>
        </div>
        <div className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
          {loading ? <div className="p-8 text-center text-sm text-slate-500">Loading families…</div> : filteredFamilies.map(family => {
            const guardianEmail = family.guardian_email || family.guardians?.[0]?.email;
            return <label key={family.id} className={`flex cursor-pointer items-center gap-4 px-5 py-3.5 transition ${selected.has(family.id) ? 'bg-indigo-50/70' : 'hover:bg-slate-50'}`}>
              <input type="checkbox" checked={selected.has(family.id)} onChange={() => toggleFamily(family.id)} className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-900">{family.name}</p><p className="truncate text-xs text-slate-500">{guardianEmail || 'No guardian email'}</p></div>
              <div className="text-right"><p className="text-xs font-medium text-slate-600">{family.children?.length || 0} child{family.children?.length === 1 ? '' : 'ren'}</p>{family.is_recurring_billing && <span className="text-[11px] font-semibold text-indigo-600">Recurring</span>}</div>
            </label>;
          })}
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50/70 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-600">Previewing never writes to the database.</p>
          <button onClick={() => void handlePreview()} disabled={!selected.size || loadingPreview} className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
            {loadingPreview ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <ShieldCheckIcon className="h-4 w-4" />}
            Review billing run
          </button>
        </div>
      </section>

      {preview && (
        <section className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              ['Families reviewed', preview.summary.families, 'text-slate-900'],
              ['Ready to bill', preview.summary.ready, 'text-emerald-600'],
              ['Needs attention', preview.summary.needs_attention, 'text-amber-600'],
              ['Already billed', preview.summary.existing, 'text-blue-600'],
              ['Draft total', formatCurrencyIntl(Number(preview.summary.total_parent_portion)), 'text-indigo-600'],
            ].map(([label, value, color]) => <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p><p className={`mt-2 text-2xl font-bold ${color}`}>{value}</p></div>)}
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-5"><h3 className="font-semibold text-slate-900">Preflight review</h3><p className="text-sm text-slate-500">Click a family to inspect child-level calculations.</p></div>
            <div className="divide-y divide-slate-100">
              {preview.items.map(item => {
                const isExpanded = expanded.has(item.family_id);
                return <div key={item.family_id}>
                  <button onClick={() => setExpanded(current => { const next = new Set(current); if (next.has(item.family_id)) next.delete(item.family_id); else next.add(item.family_id); return next; })} className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-5 py-4 text-left hover:bg-slate-50 lg:grid-cols-[auto_1fr_180px_150px]">
                    {isExpanded ? <ChevronDownIcon className="h-4 w-4 text-slate-400" /> : <ChevronRightIcon className="h-4 w-4 text-slate-400" />}
                    <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="truncate text-sm font-semibold text-slate-900">{item.family_name}</p>{item.existing_invoice ? <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-semibold text-blue-700">Already billed</span> : item.ready ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">Ready</span> : <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700">Review</span>}</div><p className="truncate text-xs text-slate-500">{item.guardian_name || 'No guardian'} · {item.guardian_email || 'No email'}</p></div>
                    <div className="hidden text-sm text-slate-500 lg:block">{item.children.length} child{item.children.length === 1 ? '' : 'ren'}</div>
                    <div className="text-right"><p className="text-sm font-bold text-slate-900">{formatCurrencyIntl(Number(item.total_parent_portion))}</p><p className="text-[11px] text-slate-500">parent portion</p></div>
                  </button>
                  {isExpanded && <div className="border-t border-slate-100 bg-slate-50/70 px-5 py-4 lg:pl-12">
                    {item.warnings.length > 0 && <div className="mb-3 flex flex-wrap gap-2">{item.warnings.map(warning => <span key={warning} className="inline-flex items-center gap-1 rounded-lg bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800"><ExclamationTriangleIcon className="h-3.5 w-3.5" />{warning}</span>)}</div>}
                    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wide text-slate-500"><th className="pb-2">Child</th><th className="pb-2">Rate</th><th className="pb-2">Funding</th><th className="pb-2 text-right">Subsidy</th><th className="pb-2 text-right">Parent portion</th></tr></thead><tbody>{item.children.map(child => <tr key={child.child_id} className="border-t border-slate-200"><td className="py-2.5 font-medium text-slate-900">{child.child_name}<span className="ml-2 text-xs text-slate-400">{child.age_group}</span></td><td>{formatCurrencyIntl(Number(child.full_rate))}</td><td className="text-slate-500">{child.funding_sources.join(', ') || 'None'}</td><td className="text-right text-emerald-700">−{formatCurrencyIntl(Number(child.subsidy))}</td><td className="text-right font-semibold">{formatCurrencyIntl(Number(child.parent_portion))}</td></tr>)}</tbody></table></div>
                  </div>}
                </div>;
              })}
            </div>
            <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-950 p-5 text-white sm:flex-row sm:items-center sm:justify-between">
              <div><p className="font-semibold">Create {preview.summary.ready} protected draft invoices</p><p className="text-sm text-slate-400">Existing invoices and families without valid rates are automatically skipped.</p></div>
              <button onClick={handleGenerate} disabled={!preview.summary.ready || generating} className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50">{generating ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <CheckCircleIcon className="h-4 w-4" />}Create drafts</button>
            </div>
          </div>
        </section>
      )}

      {result && <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div className="flex gap-3"><CheckCircleIcon className="h-6 w-6 text-emerald-600" /><div><h3 className="font-semibold text-emerald-950">Billing run completed</h3><p className="text-sm text-emerald-800">{result.generated} drafts created, {result.skipped.length} duplicates skipped, and {result.errors.length} errors.</p></div></div></div>}

      <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600"><UserGroupIcon className="h-5 w-5 text-slate-400" />Your historical invoices, payments, credits, and funding records are never rewritten by a billing run.</div>
    </div>
  );
};

export default BillingRun;
