// ============================================
// Parent Portion Tracker — Financial Intelligence Dashboard
// ============================================

import React, { useState, useMemo } from 'react';
import {
  CurrencyDollarIcon,
  UserGroupIcon,
  ChartBarIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ShieldExclamationIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  EnvelopeIcon,
  PhoneIcon,
  BanknotesIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
} from '@heroicons/react/24/outline';
import { useApiQuery } from '../../../api/hooks';
import type {
  ParentPortionTracker,
  ParentPortionFamily,
  SmartInsight,
  RiskGrade,
  AnalyticsPeriod,
} from '../types';
import { StatCardWithTrend, StatCardWithProgress, StatsGrid } from '../components/common/StatCard';
import { CenteredLoading } from '../components/common/EmptyState';
import { formatCurrencyIntl, formatDate } from '../utils/formatters';
import { PERIOD_OPTIONS } from '../constants';

// -------------------- Helpers --------------------

function getDateRange(period: AnalyticsPeriod) {
  const now = new Date();
  const toDate = now.toISOString().split('T')[0];
  const from = new Date();
  switch (period) {
    case 'week': from.setDate(from.getDate() - 7); break;
    case 'month': from.setMonth(from.getMonth() - 1); break;
    case 'quarter': from.setMonth(from.getMonth() - 3); break;
    case 'year': from.setFullYear(from.getFullYear() - 1); break;
  }
  return { fromDate: from.toISOString().split('T')[0], toDate };
}

const RISK_CONFIG: Record<RiskGrade, { color: string; bg: string; border: string; label: string }> = {
  A: { color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', label: 'Excellent' },
  B: { color: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-200', label: 'Good' },
  C: { color: 'text-yellow-700', bg: 'bg-yellow-50', border: 'border-yellow-200', label: 'Fair' },
  D: { color: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200', label: 'At Risk' },
  F: { color: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', label: 'Critical' },
};

const AGING_COLORS = ['bg-emerald-500', 'bg-yellow-500', 'bg-orange-500', 'bg-red-500'];

// -------------------- Sub-components --------------------

const RiskBadge: React.FC<{ grade: RiskGrade }> = ({ grade }) => {
  const cfg = RISK_CONFIG[grade];
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${cfg.color} ${cfg.bg} border ${cfg.border}`}>
      {grade} — {cfg.label}
    </span>
  );
};

const DeltaArrow: React.FC<{ current: number; previous: number; suffix?: string }> = ({ current, previous, suffix = '' }) => {
  if (!previous) return null;
  const delta = ((current - previous) / previous) * 100;
  const up = delta >= 0;
  return (
    <span className={`inline-flex items-center text-xs font-medium ${up ? 'text-emerald-600' : 'text-red-600'}`}>
      {up ? <ArrowTrendingUpIcon className="w-3 h-3 mr-0.5" /> : <ArrowTrendingDownIcon className="w-3 h-3 mr-0.5" />}
      {Math.abs(delta).toFixed(1)}%{suffix}
    </span>
  );
};

const InsightBanner: React.FC<{ insight: SmartInsight }> = ({ insight }) => {
  const styles: Record<string, string> = {
    danger: 'bg-red-50 border-red-200 text-red-800',
    warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  };
  return (
    <div className={`flex items-start gap-3 p-3 rounded-lg border ${styles[insight.type] || styles.info}`}>
      <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm">{insight.title}</p>
        <p className="text-xs mt-0.5 opacity-80">{insight.message}</p>
      </div>
      <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-white/60">{insight.affected_count}</span>
    </div>
  );
};

const FamilyRow: React.FC<{ family: ParentPortionFamily }> = ({ family }) => {
  const [open, setOpen] = useState(false);
  const riskCfg = RISK_CONFIG[family.risk_grade];

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${open ? 'shadow-md' : 'shadow-sm'} ${riskCfg.border}`}>
      {/* Header */}
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors text-left">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg ${riskCfg.bg} ${riskCfg.color}`}>
          {family.risk_grade}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{family.family_name}</p>
          <p className="text-xs text-gray-500">{family.children.length} child{family.children.length !== 1 ? 'ren' : ''} · {family.invoices_count} invoices</p>
        </div>
        <div className="text-right hidden sm:block">
          <p className="text-sm font-medium text-gray-900">{formatCurrencyIntl(family.parent_portion_owed)}</p>
          <p className="text-xs text-gray-500">owed</p>
        </div>
        <div className="text-right hidden sm:block">
          <p className="text-sm font-medium text-emerald-600">{formatCurrencyIntl(family.parent_portion_paid)}</p>
          <p className="text-xs text-gray-500">paid</p>
        </div>
        <div className="text-right hidden md:block">
          <p className={`text-sm font-bold ${family.outstanding > 0 ? 'text-red-600' : 'text-gray-400'}`}>
            {family.outstanding > 0 ? formatCurrencyIntl(family.outstanding) : '—'}
          </p>
          <p className="text-xs text-gray-500">outstanding</p>
        </div>
        <RiskBadge grade={family.risk_grade} />
        {open ? <ChevronUpIcon className="w-5 h-5 text-gray-400" /> : <ChevronDownIcon className="w-5 h-5 text-gray-400" />}
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t px-4 pb-4 bg-gray-50/50 space-y-4 animate-in slide-in-from-top-2">
          {/* Contact */}
          <div className="flex flex-wrap gap-4 pt-3 text-sm text-gray-600">
            {family.guardian_name && <span className="flex items-center gap-1"><UserGroupIcon className="w-4 h-4" />{family.guardian_name}</span>}
            {family.guardian_email && <span className="flex items-center gap-1"><EnvelopeIcon className="w-4 h-4" />{family.guardian_email}</span>}
            {family.guardian_phone && <span className="flex items-center gap-1"><PhoneIcon className="w-4 h-4" />{family.guardian_phone}</span>}
          </div>

          {/* Children breakdown */}
          <div>
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Children Breakdown</h4>
            <div className="grid gap-2">
              {family.children.map(c => (
                <div key={c.child_id} className="flex items-center justify-between bg-white rounded-lg p-3 border border-gray-100">
                  <div>
                    <p className="font-medium text-gray-900 text-sm">{c.child_name}</p>
                    {c.age_group && <p className="text-xs text-gray-500">{c.age_group}</p>}
                  </div>
                  <div className="flex gap-4 text-xs text-right">
                    <div><p className="font-medium text-gray-700">{formatCurrencyIntl(c.total_charges)}</p><p className="text-gray-400">charges</p></div>
                    <div><p className="font-medium text-blue-600">{formatCurrencyIntl(c.subsidy_amount)}</p><p className="text-gray-400">subsidy</p></div>
                    <div><p className="font-medium text-orange-600">{formatCurrencyIntl(c.parent_portion)}</p><p className="text-gray-400">parent</p></div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Aging + meta */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="bg-white rounded-lg p-3 border border-gray-100">
              <p className="text-xs text-gray-500">Current</p>
              <p className="font-bold text-emerald-600">{formatCurrencyIntl(family.aging_current)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-gray-100">
              <p className="text-xs text-gray-500">30-Day</p>
              <p className="font-bold text-yellow-600">{formatCurrencyIntl(family.aging_30)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-gray-100">
              <p className="text-xs text-gray-500">60-Day</p>
              <p className="font-bold text-orange-600">{formatCurrencyIntl(family.aging_60)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-gray-100">
              <p className="text-xs text-gray-500">90+ Day</p>
              <p className="font-bold text-red-600">{formatCurrencyIntl(family.aging_90_plus)}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 text-xs text-gray-500">
            <span>Avg days to pay: <strong className="text-gray-700">{family.avg_days_to_pay.toFixed(0)}</strong></span>
            {family.last_payment_date && <span>Last payment: <strong className="text-gray-700">{formatDate(family.last_payment_date)}</strong></span>}
            {family.payment_methods_used.length > 0 && <span>Methods: <strong className="text-gray-700">{family.payment_methods_used.join(', ')}</strong></span>}
            {family.funding_sources.length > 0 && <span>Funding: <strong className="text-gray-700">{family.funding_sources.join(', ')}</strong></span>}
          </div>
        </div>
      )}
    </div>
  );
};

// -------------------- Main Component --------------------

const ParentTracking: React.FC = () => {
  const [period, setPeriod] = useState<AnalyticsPeriod>('month');
  const [sortBy, setSortBy] = useState<'risk' | 'outstanding' | 'name'>('risk');
  const dateRange = useMemo(() => getDateRange(period), [period]);

  const { data: tracker, loading } = useApiQuery<ParentPortionTracker>(
    '/invoicing/parent-portion-tracker',
    { from_date: dateRange.fromDate, to_date: dateRange.toDate },
  );
  const summary = tracker?.summary;
  const families = useMemo(() => {
    if (!tracker?.families) return [];
    const sorted = [...tracker.families];
    switch (sortBy) {
      case 'risk': return sorted.sort((a, b) => b.risk_score - a.risk_score);
      case 'outstanding': return sorted.sort((a, b) => b.outstanding - a.outstanding);
      case 'name': return sorted.sort((a, b) => a.family_name.localeCompare(b.family_name));
    }
  }, [tracker?.families, sortBy]);

  if (loading) return <CenteredLoading />;
  if (!summary) return <div className="text-center py-12 text-gray-500">No data available for this period.</div>;

  const collectionPct = summary.collection_rate;

  return (
    <div className="space-y-6">
      {/* Header + Period */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Parent Portion Tracker</h2>
          <p className="text-sm text-gray-500">Financial intelligence across all families</p>
        </div>
        <div className="flex items-center gap-2">
          {PERIOD_OPTIONS.map(p => (
            <button key={p.value} onClick={() => setPeriod(p.value as AnalyticsPeriod)}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg ${period === p.value ? 'bg-primary-100 text-primary-700' : 'text-gray-500 hover:bg-gray-100'}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row */}
      <StatsGrid columns={5}>
        <StatCardWithTrend
          icon={<CurrencyDollarIcon className="w-5 h-5 text-blue-600" />} iconBg="bg-blue-100"
          label="Total Charges" value={formatCurrencyIntl(summary.total_charges)}
          trend={summary.prev_total_charges ? { value: `${(((summary.total_charges - summary.prev_total_charges) / summary.prev_total_charges) * 100).toFixed(1)}%`, direction: summary.total_charges >= summary.prev_total_charges ? 'up' : 'down', label: 'vs prev' } : undefined}
        />
        <StatCardWithTrend
          icon={<ShieldExclamationIcon className="w-5 h-5 text-indigo-600" />} iconBg="bg-indigo-100"
          label="Subsidy Coverage" value={formatCurrencyIntl(summary.total_subsidy)}
        />
        <StatCardWithTrend
          icon={<BanknotesIcon className="w-5 h-5 text-emerald-600" />} iconBg="bg-emerald-100"
          label="Parent Paid" value={formatCurrencyIntl(summary.total_parent_paid)} valueColor="text-emerald-600"
        />
        <StatCardWithTrend
          icon={<ExclamationTriangleIcon className="w-5 h-5 text-red-600" />} iconBg="bg-red-100"
          label="Outstanding" value={formatCurrencyIntl(summary.total_outstanding)} valueColor="text-red-600"
        />
        <StatCardWithProgress
          icon={<CheckCircleIcon className="w-5 h-5 text-purple-600" />} iconBg="bg-purple-100"
          label="Collection Rate" value={`${collectionPct.toFixed(1)}%`} valueColor="text-purple-600"
          progress={collectionPct} progressColor={collectionPct >= 80 ? 'bg-emerald-500' : collectionPct >= 50 ? 'bg-yellow-500' : 'bg-red-500'}
        />
      </StatsGrid>

      {/* Smart Insights */}
      {summary.smart_insights.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-700">Smart Insights</h3>
          {summary.smart_insights.map((ins, i) => <InsightBanner key={i} insight={ins} />)}
        </div>
      )}

      {/* Middle Row: Waterfall + Aging + Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue Waterfall */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Revenue Waterfall</h3>
          <div className="space-y-3">
            {summary.waterfall.map((step, i) => {
              const maxVal = Math.max(...summary.waterfall.map(s => Math.abs(s.value)), 1);
              const pct = (Math.abs(step.value) / maxVal) * 100;
              const barColor = step.type === 'total' ? 'bg-blue-500' : step.type === 'subtract' ? 'bg-red-400' : 'bg-emerald-500';
              return (
                <div key={i}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">{step.label}</span>
                    <span className={`font-semibold ${step.type === 'subtract' ? 'text-red-600' : 'text-gray-900'}`}>
                      {step.type === 'subtract' ? '−' : ''}{formatCurrencyIntl(Math.abs(step.value))}
                    </span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Aging Buckets */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Aging Buckets</h3>
          <div className="space-y-3">
            {summary.aging_buckets.map((bucket, i) => (
              <div key={i}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-600">{bucket.label}</span>
                  <span className="font-semibold text-gray-900">{formatCurrencyIntl(bucket.amount)} <span className="text-gray-400">({bucket.count})</span></span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full ${AGING_COLORS[i] || 'bg-gray-400'} rounded-full`} style={{ width: `${bucket.percentage}%` }} />
                </div>
              </div>
            ))}
          </div>
          {/* Family status donut-like summary */}
          <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-emerald-500" /><span className="text-gray-600">Fully Paid: <strong>{summary.families_fully_paid}</strong></span></div>
            <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-yellow-500" /><span className="text-gray-600">Partial: <strong>{summary.families_partial}</strong></span></div>
            <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-red-500" /><span className="text-gray-600">Unpaid: <strong>{summary.families_unpaid}</strong></span></div>
            <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-blue-500" /><span className="text-gray-600">Subsidy Only: <strong>{summary.families_subsidy_only}</strong></span></div>
          </div>
        </div>

        {/* Payment Methods + Funding Sources */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Payment Methods</h3>
            {summary.payment_method_breakdown.map((m, i) => (
              <div key={i} className="mb-2">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-600 capitalize">{m.method || 'Unknown'}</span>
                  <span className="font-medium text-gray-900">{formatCurrencyIntl(m.amount)}</span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${m.percentage}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Funding Sources</h3>
            {summary.funding_source_breakdown.map((f, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 text-xs border-b border-gray-50 last:border-0">
                <div>
                  <span className="font-medium text-gray-900">{f.source_name}</span>
                  <span className="text-gray-400 ml-1">({f.source_type})</span>
                </div>
                <div className="text-right">
                  <span className="font-semibold text-gray-900">{formatCurrencyIntl(f.amount)}</span>
                  <span className="text-gray-400 ml-2">{f.families_count}f / {f.children_count}c</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Family List */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">Family Breakdown ({families.length})</h3>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">Sort:</span>
            {(['risk', 'outstanding', 'name'] as const).map(s => (
              <button key={s} onClick={() => setSortBy(s)}
                className={`px-2 py-1 rounded ${sortBy === s ? 'bg-gray-200 font-semibold text-gray-900' : 'text-gray-500 hover:bg-gray-100'}`}>
                {s === 'risk' ? 'Risk' : s === 'outstanding' ? 'Outstanding' : 'Name'}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          {families.map(f => <FamilyRow key={f.family_id} family={f} />)}
        </div>
      </div>

      {/* Bottom stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-5 text-white">
          <ClockIcon className="w-8 h-8 opacity-80 mb-2" />
          <p className="text-white/80 text-sm">Avg Days to Collect</p>
          <p className="text-2xl font-bold">{summary.avg_days_to_collect.toFixed(0)} days</p>
        </div>
        <div className="bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl p-5 text-white">
          <UserGroupIcon className="w-8 h-8 opacity-80 mb-2" />
          <p className="text-white/80 text-sm">Total Families</p>
          <p className="text-2xl font-bold">{summary.families_count}</p>
        </div>
        <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-5 text-white">
          <ChartBarIcon className="w-8 h-8 opacity-80 mb-2" />
          <p className="text-white/80 text-sm">Collection vs Last Period</p>
          <p className="text-2xl font-bold">
            {summary.prev_collection_rate ? <DeltaArrow current={collectionPct} previous={summary.prev_collection_rate} /> : 'N/A'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ParentTracking;
