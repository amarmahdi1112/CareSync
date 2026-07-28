// ============================================
// Invoicing Module - Type Definitions
// ============================================

// -------------------- Enums --------------------

export type LineItemType = 'daycare_subsidy' | 'service_hourly' | 'service_flat' | 'product';

export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled';

export type CreditNoteStatus = 'draft' | 'issued' | 'partially_applied' | 'fully_applied' | 'void';

export type RecurringFrequency = 'weekly' | 'bi_weekly' | 'monthly' | 'quarterly' | 'yearly';

export type RecurringStatus = 'active' | 'paused' | 'cancelled' | 'completed';

export type AnalyticsPeriod = 'week' | 'month' | 'quarter' | 'year';

// -------------------- Base Types --------------------

export interface LineItem {
  id: string;
  item_type: LineItemType;
  description: string;
  child_id?: string;
  child_name?: string;
  full_rate?: number;
  subsidy_amount?: number;
  hours?: number;
  hourly_rate?: number;
  quantity?: number;
  unit_price?: number;
  amount: number;
}

export interface Guardian {
  id: string;
  first_name: string;
  last_name: string;
  email?: string;
  cell_phone?: string;
  address?: string;
  city?: string;
  postal_code?: string;
}

export interface Child {
  id: string;
  first_name: string;
  middle_name?: string;
  last_name: string;
  age_group?: string;
  monthly_rate?: number;
}

export interface Family {
  id: string;
  name: string;
  status: string;
  is_recurring_billing?: boolean;
  recurring_funding_source_id?: string;
  guardians?: Guardian[];
  children?: Child[];
  guardian_email?: string;
  last_invoice_date?: string;
}

export interface FundingSource {
  id: string;
  name: string;
  funding_type: string;
  contact_name?: string;
  contact_email?: string;
  is_active: boolean;
}

// -------------------- Invoice Types --------------------

export interface Invoice {
  id: string;
  invoice_number: string;
  file_number?: string;
  client_name?: string;
  client_email?: string;
  client_address?: string;
  family?: { id: string; name: string };
  recipient_id?: string;
  recipient?: { id: string; name: string; contact_name?: string; contact_email?: string };
  issue_date: string;
  due_date: string;
  period_start?: string;
  period_end?: string;
  subtotal: number;
  discount_amount?: number;
  discount_percentage?: number;
  tax_rate?: number;
  tax_amount?: number;
  total_amount: number;
  amount_paid: number;
  balance_due: number;
  status: InvoiceStatus;
  notes?: string;
  terms?: string;
  line_items: LineItem[];
}

export interface InvoiceData {
  invoice_number: string;
  file_number: string;
  family_id: string;
  guardian_id: string;
  client_name: string;
  client_email: string;
  client_address: string;
  recipient_id: string;
  issue_date: string;
  due_date: string;
  period_start: string;
  period_end: string;
  line_items: LineItem[];
  discount_type: 'amount' | 'percentage';
  discount_value: number;
  tax_rate: number;
  notes: string;
  terms: string;
}

export interface InvoiceSettings {
  company_name: string;
  company_email: string;
  company_phone: string;
  company_address: string;
  company_city: string;
  company_province: string;
  company_postal_code: string;
  company_logo?: string;
  company_website?: string;
  currency_symbol: string;
  invoice_prefix: string;
  next_invoice_number: number;
  default_tax_rate: number;
  tax_name?: string;
  default_notes?: string;
  default_terms?: string;
}

export interface InvoiceDashboard {
  total_overdue: number;
  total_outstanding: number;
  paid_this_month: number;
  invoice_count: number;
}

export interface InvoiceConnection {
  items: Invoice[];
  total: number;
  page: number;
  limit: number;
  hasMore: boolean;
}

// -------------------- Template Types --------------------

export interface TemplateLineItem {
  description: string;
  item_type: LineItemType;
  amount?: number;
  full_rate?: number;
  subsidy_amount?: number;
  hours?: number;
  hourly_rate?: number;
  quantity?: number;
  unit_price?: number;
}

export interface InvoiceTemplate {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  is_active: boolean;
  due_days: number;
  default_tax_rate: number;
  default_discount_amount: number;
  default_discount_percentage?: number;
  line_items?: TemplateLineItem[];
  notes?: string;
  terms?: string;
  created_at: string;
}

// -------------------- Recurring Types --------------------

export interface RecurringSchedule {
  id: string;
  name: string;
  client_name?: string;
  family_id?: string;
  family?: { id: string; name: string };
  frequency: RecurringFrequency;
  day_of_period: number;
  due_days: number;
  next_invoice_date?: string;
  last_invoice_date?: string;
  invoices_generated: number;
  status: RecurringStatus;
  start_date: string;
  end_date?: string;
  line_items?: Array<{
    description: string;
    item_type: string;
    amount?: number;
  }>;
}

// -------------------- Credit Note Types --------------------

export interface CreditNote {
  id: string;
  credit_note_number: string;
  invoice_id?: string;
  invoice?: { id: string; invoice_number: string };
  family_id?: string;
  family?: { id: string; name: string };
  client_name?: string;
  amount: number;
  amount_applied: number;
  balance: number;
  reason?: string;
  description?: string;
  status: CreditNoteStatus;
  issue_date?: string;
  created_at: string;
}

// -------------------- Analytics Types --------------------

export interface MonthlyData {
  month: string;
  invoiced: number;
  collected: number;
  outstanding: number;
}

export interface ClientData {
  name: string;
  total_invoiced: number;
  total_paid: number;
  outstanding: number;
  invoice_count: number;
}

export interface AnalyticsData {
  total_revenue: number;
  total_outstanding: number;
  total_overdue: number;
  average_days_to_pay: number;
  collection_rate: number;
  revenue_by_month: Array<{ month: string; amount: number }>;
  top_clients: ClientData[];
  status_breakdown: Array<{ status: string; count: number; amount: number }>;
}

export interface AgingItem {
  range: string;
  amount: number;
  count: number;
  percentage: number;
}

// -------------------- Form State Types --------------------

export interface RecurringFormData {
  name: string;
  client_name: string;
  frequency: RecurringFrequency;
  day_of_period: number;
  start_date: string;
  end_date: string;
  due_days: number;
  line_items: Array<{ description: string; item_type: string; amount: number }>;
}

export interface TemplateFormData {
  name: string;
  description: string;
  due_days: number;
  default_tax_rate: number;
  line_items: Array<{ description: string; item_type: LineItemType; amount: number }>;
  notes: string;
  terms: string;
}

export interface CreditFormData {
  client_name: string;
  amount: string;
  reason: string;
  description: string;
}

// -------------------- Query Result Types --------------------

export interface LastInvoice {
  id: string;
  file_number?: string;
  client_name?: string;
  client_email?: string;
  client_address?: string;
  discount_amount?: number;
  discount_percentage?: number;
  tax_rate?: number;
  notes?: string;
  terms?: string;
  line_items?: LineItem[];
}

export interface LastInvoiceQueryResult {
  invoices: {
    items: LastInvoice[];
  };
}

// -------------------- Parent Portion Tracker Types --------------------

export type PaymentStatus = 'paid' | 'partial' | 'unpaid' | 'subsidy_only';
export type RiskGrade = 'A' | 'B' | 'C' | 'D' | 'F';

export interface ParentPortionChild {
  child_id: string;
  child_name: string;
  age_group?: string;
  total_charges: number;
  subsidy_amount: number;
  parent_portion: number;
  funding_sources: string[];
}

export interface ParentPortionFamily {
  family_id: string;
  family_name: string;
  guardian_name?: string;
  guardian_email?: string;
  guardian_phone?: string;
  children: ParentPortionChild[];
  total_charges: number;
  subsidy_amount: number;
  parent_portion_owed: number;
  parent_portion_paid: number;
  outstanding: number;
  payment_status: PaymentStatus;
  risk_grade: RiskGrade;
  risk_score: number;
  avg_days_to_pay: number;
  payment_methods_used: string[];
  funding_sources: string[];
  invoices_count: number;
  last_payment_date?: string;
  aging_current: number;
  aging_30: number;
  aging_60: number;
  aging_90_plus: number;
}

export interface PaymentMethodBreakdown {
  method: string;
  amount: number;
  count: number;
  percentage: number;
}

export interface FundingSourceBreakdown {
  source_name: string;
  source_type: string;
  amount: number;
  families_count: number;
  children_count: number;
}

export interface AgingBucket {
  label: string;
  amount: number;
  count: number;
  percentage: number;
}

export interface SmartInsight {
  type: 'warning' | 'danger' | 'info' | 'success';
  title: string;
  message: string;
  action?: string;
  affected_count: number;
}

export interface WaterfallStep {
  label: string;
  value: number;
  cumulative: number;
  type: 'total' | 'subtract' | 'result';
}

export interface ParentPortionSummary {
  total_charges: number;
  total_subsidy: number;
  total_parent_owed: number;
  total_parent_paid: number;
  total_outstanding: number;
  collection_rate: number;
  avg_days_to_collect: number;
  families_count: number;
  families_fully_paid: number;
  families_partial: number;
  families_unpaid: number;
  families_subsidy_only: number;
  prev_total_charges: number;
  prev_total_collected: number;
  prev_collection_rate: number;
  payment_method_breakdown: PaymentMethodBreakdown[];
  funding_source_breakdown: FundingSourceBreakdown[];
  aging_buckets: AgingBucket[];
  smart_insights: SmartInsight[];
  waterfall: WaterfallStep[];
}

export interface ParentPortionTracker {
  families: ParentPortionFamily[];
  summary: ParentPortionSummary;
}
