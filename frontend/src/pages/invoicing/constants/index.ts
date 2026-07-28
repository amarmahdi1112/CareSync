// ============================================
// Invoicing Module - Constants
// ============================================

import type { LineItemType, RecurringFrequency, InvoiceStatus, CreditNoteStatus } from '../types';

// -------------------- Labels --------------------

export const FREQUENCY_LABELS: Record<RecurringFrequency, string> = {
  weekly: 'Weekly',
  bi_weekly: 'Bi-Weekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  yearly: 'Yearly',
};

export const DAY_OF_WEEK_LABELS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
];

export const LINE_ITEM_TYPE_LABELS: Record<LineItemType, string> = {
  daycare_subsidy: 'Daycare (Subsidy)',
  service_hourly: 'Service (Hourly)',
  service_flat: 'Service (Flat)',
  product: 'Product',
};

export const LINE_ITEM_TYPE_COLORS: Record<LineItemType, { bg: string; text: string }> = {
  daycare_subsidy: { bg: 'bg-blue-100', text: 'text-blue-700' },
  service_hourly: { bg: 'bg-green-100', text: 'text-green-700' },
  service_flat: { bg: 'bg-purple-100', text: 'text-purple-700' },
  product: { bg: 'bg-orange-100', text: 'text-orange-700' },
};

export const INVOICE_STATUS_CONFIG: Record<InvoiceStatus, { bg: string; text: string; label: string }> = {
  draft: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Draft' },
  sent: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Sent' },
  paid: { bg: 'bg-green-100', text: 'text-green-700', label: 'Paid' },
  overdue: { bg: 'bg-red-100', text: 'text-red-700', label: 'Overdue' },
  cancelled: { bg: 'bg-gray-100', text: 'text-gray-500', label: 'Cancelled' },
};

export const CREDIT_STATUS_CONFIG: Record<CreditNoteStatus, { bg: string; text: string; label: string }> = {
  draft: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Draft' },
  issued: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Issued' },
  partially_applied: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Partially Applied' },
  fully_applied: { bg: 'bg-green-100', text: 'text-green-700', label: 'Fully Applied' },
  void: { bg: 'bg-gray-100', text: 'text-gray-500', label: 'Void' },
};

// -------------------- Default Values --------------------

export const DEFAULT_LINE_ITEM = {
  item_type: 'service_flat' as LineItemType,
  description: '',
  quantity: 1,
  amount: 0,
};

export const DEFAULT_RECURRING_FORM = {
  name: '',
  client_name: '',
  frequency: 'monthly' as RecurringFrequency,
  day_of_period: 1,
  start_date: new Date().toISOString().split('T')[0],
  end_date: '',
  due_days: 30,
  line_items: [{ description: '', item_type: 'service_flat', amount: 0 }],
};

export const DEFAULT_TEMPLATE_FORM = {
  name: '',
  description: '',
  due_days: 30,
  default_tax_rate: 0,
  line_items: [{ description: '', item_type: 'service_flat' as LineItemType, amount: 0 }],
  notes: '',
  terms: '',
};

export const DEFAULT_CREDIT_FORM = {
  client_name: '',
  amount: '',
  reason: '',
  description: '',
};

// -------------------- Period Options --------------------

export const PERIOD_OPTIONS = [
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
] as const;

// -------------------- Pagination --------------------

export const DEFAULT_PAGE_SIZE = 20;

// -------------------- Chart Colors --------------------

export const CHART_COLORS = {
  invoiced: 'bg-blue-500',
  collected: 'bg-green-500',
  outstanding: 'bg-red-500',
  aging: ['bg-green-500', 'bg-yellow-500', 'bg-orange-500', 'bg-red-400', 'bg-red-600'],
};
