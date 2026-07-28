// ============================================
// Invoice Analytics View (Fixed - Real Data)
// ============================================

import React, { useState, useMemo } from 'react';
import {
  ChartBarIcon,
  CalendarDaysIcon,
  BanknotesIcon,
  ClockIcon,
  UserGroupIcon,
  DocumentTextIcon,
  ExclamationCircleIcon,
  CheckCircleIcon,
  ArrowDownTrayIcon
} from '@heroicons/react/24/outline';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { AnalyticsPeriod } from '../types';

// Components
import { StatCardWithTrend, StatCardWithProgress, GradientStatCard, StatsGrid } from '../components/common/StatCard';
import { CenteredLoading } from '../components/common/EmptyState';

// Utils
import { formatCurrencyIntl } from '../utils/formatters';
import { PERIOD_OPTIONS } from '../constants';

// Backend return shape
interface RevenueByPeriod {
  period: string;
  revenue: number;
  invoices_count: number;
  payments_count: number;
}

interface TopClient {
  family_id?: string;
  family_name: string;
  total_revenue: number;
  invoices_count: number;
  outstanding: number;
}

interface StatusBreakdown {
  status: string;
  count: number;
  total_amount: number;
}

interface AnalyticsResponse {
  total_revenue: number;
  total_outstanding: number;
  total_overdue: number;
  average_invoice_value: number;
  average_days_to_pay: number;
  revenue_by_month: RevenueByPeriod[];
  top_clients: TopClient[];
  status_breakdown: StatusBreakdown[];
}

// Get date range based on selected period
function getDateRange(period: AnalyticsPeriod): { fromDate: string; toDate: string } {
  const now = new Date();
  const toDate = now.toISOString().split('T')[0];
  
  let from = new Date();
  switch (period) {
    case 'week':
      from.setDate(from.getDate() - 7);
      break;
    case 'month':
      from.setMonth(from.getMonth() - 1);
      break;
    case 'quarter':
      from.setMonth(from.getMonth() - 3);
      break;
    case 'year':
      from.setFullYear(from.getFullYear() - 1);
      break;
    default:
      from = new Date(now.getFullYear(), 0, 1); // YTD
  }
  
  return { fromDate: from.toISOString().split('T')[0], toDate };
}

const Analytics: React.FC = () => {
  const [period, setPeriod] = useState<AnalyticsPeriod>('year');

  // Wire period selector to the query variables
  const dateRange = useMemo(() => getDateRange(period), [period]);

  const { data: analytics, loading } = useApiQuery<AnalyticsResponse>('/invoicing/invoices/analytics', {
    from_date: dateRange.fromDate,
    to_date: dateRange.toDate,
  });

  // Real computed values from backend
  const totalInvoiced = analytics?.total_revenue || 0;
  const totalOutstanding = analytics?.total_outstanding || 0;
  const totalOverdue = analytics?.total_overdue || 0;
  const avgInvoiceValue = analytics?.average_invoice_value || 0;
  const avgDaysToPay = analytics?.average_days_to_pay || 0;

  // Collection rate = paid / (paid + outstanding) * 100
  const totalOwed = totalInvoiced + totalOutstanding;
  const collectionRate = totalOwed > 0 ? ((totalInvoiced / totalOwed) * 100).toFixed(1) : '0';

  // Monthly data from backend (real revenue, real collected based on payments_count)
  const monthlyData = (analytics?.revenue_by_month || []).map(m => ({
    month: m.period.slice(5), // "2026-01" → "01"
    label: new Date(m.period + '-01T12:00:00').toLocaleDateString('en-US', { month: 'short' }),
    invoiced: m.revenue,
    invoiceCount: m.invoices_count,
    paymentCount: m.payments_count,
  }));

  // Top clients from backend
  const topClients = analytics?.top_clients || [];

  // Status breakdown for aging report
  const statusData = analytics?.status_breakdown || [];
  const totalForAging = statusData.reduce((sum, s) => sum + s.total_amount, 0);

  const maxValue = Math.max(...monthlyData.map(m => m.invoiced), 1);

  // Quick stats from real data
  const currentMonthRevenue = monthlyData.length > 0 ? monthlyData[monthlyData.length - 1]?.invoiced || 0 : 0;
  const activeClientsCount = topClients.length;

  if (loading) return <CenteredLoading />;

  return (
    <div className="space-y-6">
      {/* Period Selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Revenue Analytics</h2>
          <p className="text-sm text-gray-500">Track your invoicing performance and trends</p>
        </div>
        <div className="flex items-center gap-2">
          {PERIOD_OPTIONS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value as AnalyticsPeriod)}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                period === p.value
                  ? 'bg-primary-100 text-primary-700'
                  : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {p.label}
            </button>
          ))}
          <button className="ml-2 p-2 text-gray-400 hover:text-gray-600 rounded-lg border border-gray-200">
            <ArrowDownTrayIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* KPI Cards — All from real data */}
      <StatsGrid columns={5}>
        <StatCardWithTrend
          icon={<DocumentTextIcon className="w-5 h-5 text-blue-600" />}
          iconBg="bg-blue-100"
          label="Total Invoiced"
          value={formatCurrencyIntl(totalInvoiced)}
        />
        <StatCardWithTrend
          icon={<ExclamationCircleIcon className="w-5 h-5 text-yellow-600" />}
          iconBg="bg-yellow-100"
          label="Outstanding"
          value={formatCurrencyIntl(totalOutstanding)}
          valueColor="text-yellow-600"
        />
        <StatCardWithTrend
          icon={<ExclamationCircleIcon className="w-5 h-5 text-red-600" />}
          iconBg="bg-red-100"
          label="Overdue"
          value={formatCurrencyIntl(totalOverdue)}
          valueColor="text-red-600"
        />
        <StatCardWithProgress
          icon={<CheckCircleIcon className="w-5 h-5 text-purple-600" />}
          iconBg="bg-purple-100"
          label="Collection Rate"
          value={`${collectionRate}%`}
          valueColor="text-purple-600"
          progress={parseFloat(collectionRate)}
          progressColor="bg-purple-500"
        />
        <StatCardWithTrend
          icon={<ChartBarIcon className="w-5 h-5 text-green-600" />}
          iconBg="bg-green-100"
          label="Avg Invoice"
          value={formatCurrencyIntl(avgInvoiceValue)}
        />
      </StatsGrid>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Chart */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Revenue by Month</h3>
          
          {monthlyData.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <p className="font-medium">No revenue data</p>
              <p className="text-sm">No paid invoices found in this period.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {monthlyData.map((data) => (
                <div key={data.month} className="flex items-center gap-3">
                  <span className="w-10 text-sm text-gray-500 font-medium">{data.label}</span>
                  <div className="flex-1 h-8 bg-gray-100 rounded-lg overflow-hidden flex">
                    <div 
                      className="h-full bg-blue-500 transition-all duration-500"
                      style={{ width: `${(data.invoiced / maxValue) * 100}%` }}
                      title={`${formatCurrencyIntl(data.invoiced)} (${data.invoiceCount} invoices)`}
                    />
                  </div>
                  <span className="w-24 text-right text-sm font-medium text-gray-900">
                    {formatCurrencyIntl(data.invoiced)}
                  </span>
                </div>
              ))}
            </div>
          )}
          
          <div className="flex items-center justify-center gap-6 mt-4 pt-4 border-t border-gray-100">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-blue-500 rounded" />
              <span className="text-sm text-gray-600">Paid Revenue</span>
            </div>
          </div>
        </div>

        {/* Status Breakdown / Aging Report */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Invoice Status Breakdown</h3>
          
          {statusData.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <p className="font-medium">No invoice data</p>
              <p className="text-sm">No invoices found in this period.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {statusData.map((item) => {
                const statusColors: Record<string, string> = {
                  'paid': 'bg-green-500',
                  'sent': 'bg-blue-500',
                  'draft': 'bg-gray-400',
                  'overdue': 'bg-red-500',
                  'cancelled': 'bg-gray-300',
                };
                const color = statusColors[item.status] || 'bg-gray-400';
                const percentage = totalForAging > 0 ? (item.total_amount / totalForAging) * 100 : 0;
                
                return (
                  <div key={item.status}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-700 capitalize">{item.status}</span>
                      <div className="text-right">
                        <span className="text-sm font-bold text-gray-900">{formatCurrencyIntl(item.total_amount)}</span>
                        <span className="text-xs text-gray-500 ml-2">({item.count} invoices)</span>
                      </div>
                    </div>
                    <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${color} transition-all`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Total Value</span>
              <span className="text-lg font-bold text-gray-900">
                {formatCurrencyIntl(totalForAging)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Top Clients */}
      {topClients.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Top Clients by Revenue</h3>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase px-6 py-3">Client</th>
                  <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Revenue</th>
                  <th className="text-right text-xs font-medium text-gray-500 uppercase px-6 py-3">Outstanding</th>
                  <th className="text-center text-xs font-medium text-gray-500 uppercase px-6 py-3">Invoices</th>
                  <th className="text-center text-xs font-medium text-gray-500 uppercase px-6 py-3">Payment Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {topClients.map((client, idx) => {
                  const totalInvoicedForClient = client.total_revenue + client.outstanding;
                  const paymentRate = totalInvoicedForClient > 0 
                    ? ((client.total_revenue / totalInvoicedForClient) * 100).toFixed(0) 
                    : '100';
                  return (
                    <tr key={client.family_id || client.family_name} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm ${
                            idx === 0 ? 'bg-yellow-500' : idx === 1 ? 'bg-gray-400' : idx === 2 ? 'bg-amber-600' : 'bg-gray-300'
                          }`}>
                            {idx + 1}
                          </div>
                          <span className="font-medium text-gray-900">{client.family_name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right font-medium text-green-600">
                        {formatCurrencyIntl(client.total_revenue)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <span className={client.outstanding > 0 ? 'text-red-600 font-medium' : 'text-gray-400'}>
                          {client.outstanding > 0 ? formatCurrencyIntl(client.outstanding) : '-'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center text-gray-600">
                        {client.invoices_count}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-center gap-2">
                          <div className="w-16 h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${
                                parseInt(paymentRate) === 100 ? 'bg-green-500' : 
                                parseInt(paymentRate) >= 80 ? 'bg-yellow-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${paymentRate}%` }}
                            />
                          </div>
                          <span className="text-sm font-medium text-gray-600">{paymentRate}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Quick Stats — All from real data */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <GradientStatCard
          icon={<CalendarDaysIcon className="w-8 h-8" />}
          label="This Period"
          value={formatCurrencyIntl(currentMonthRevenue)}
          gradient="from-blue-500 to-blue-600"
        />
        <GradientStatCard
          icon={<BanknotesIcon className="w-8 h-8" />}
          label="Avg Invoice"
          value={formatCurrencyIntl(avgInvoiceValue)}
          gradient="from-green-500 to-green-600"
        />
        <GradientStatCard
          icon={<UserGroupIcon className="w-8 h-8" />}
          label="Active Clients"
          value={String(activeClientsCount)}
          gradient="from-purple-500 to-purple-600"
        />
        <GradientStatCard
          icon={<ClockIcon className="w-8 h-8" />}
          label="Avg Days to Pay"
          value={avgDaysToPay > 0 ? `${avgDaysToPay.toFixed(0)} days` : 'N/A'}
          gradient="from-orange-500 to-orange-600"
        />
      </div>
    </div>
  );
};

export default Analytics;
