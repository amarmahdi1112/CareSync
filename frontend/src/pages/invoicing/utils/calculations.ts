// ============================================
// Invoicing Module - Calculations
// ============================================

import type { LineItem, LineItemType, InvoiceTemplate, RecurringSchedule, TemplateLineItem } from '../types';

/**
 * Generate a unique ID
 */
export const generateId = (): string => Math.random().toString(36).substr(2, 9);

/**
 * Calculate the amount for a single line item based on its type
 */
export const calculateLineItemAmount = (item: LineItem | TemplateLineItem): number => {
  const itemType = item.item_type;
  
  switch (itemType) {
    case 'daycare_subsidy':
      return (item.full_rate || 0) - (item.subsidy_amount || 0);
    case 'service_hourly':
      return (item.hours || 0) * (item.hourly_rate || 0);
    case 'product':
      return (item.quantity || 1) * (item.unit_price || 0);
    case 'service_flat':
    default:
      return item.amount || 0;
  }
};

/**
 * Calculate invoice totals
 */
export interface InvoiceTotals {
  subtotal: number;
  discount: number;
  afterDiscount: number;
  taxAmount: number;
  total: number;
}

export const calculateInvoiceTotals = (
  lineItems: LineItem[],
  discountType: 'amount' | 'percentage',
  discountValue: number,
  taxRate: number
): InvoiceTotals => {
  const subtotal = lineItems.reduce((sum, item) => sum + calculateLineItemAmount(item), 0);
  const discount = discountType === 'percentage' 
    ? subtotal * (discountValue / 100)
    : discountValue;
  const afterDiscount = subtotal - discount;
  const taxAmount = afterDiscount * (taxRate / 100);
  const total = afterDiscount + taxAmount;
  
  return { subtotal, discount, afterDiscount, taxAmount, total };
};

/**
 * Calculate total for a template
 */
export const calculateTemplateTotal = (template: InvoiceTemplate): number => {
  return (template.line_items || []).reduce((sum, item) => sum + calculateLineItemAmount(item), 0);
};

/**
 * Calculate total for a recurring schedule
 */
export const calculateScheduleAmount = (schedule: RecurringSchedule): number => {
  return (schedule.line_items || []).reduce((sum, item) => sum + (item.amount || 0), 0);
};

/**
 * Calculate estimated monthly revenue from a recurring schedule
 */
export const calculateMonthlyRevenue = (schedule: RecurringSchedule): number => {
  const amount = calculateScheduleAmount(schedule);
  
  switch (schedule.frequency) {
    case 'weekly':
      return amount * 4;
    case 'bi_weekly':
      return amount * 2;
    case 'monthly':
      return amount;
    case 'quarterly':
      return amount / 3;
    case 'yearly':
      return amount / 12;
    default:
      return amount;
  }
};

/**
 * Create an empty line item
 */
export const createEmptyLineItem = (type: LineItemType = 'service_flat'): LineItem => ({
  id: generateId(),
  item_type: type,
  description: '',
  quantity: 1,
  amount: 0,
});

/**
 * Calculate family total based on children's monthly rates
 */
export const calculateFamilyTotal = (children: Array<{ monthly_rate?: number }> = []): number => {
  return children.reduce((sum, child) => sum + (child.monthly_rate || 0), 0);
};

/**
 * Check if a family needs an invoice (hasn't been invoiced in the last month)
 */
export const needsInvoice = (lastInvoiceDate: string | undefined | null): boolean => {
  if (!lastInvoiceDate) return true;
  // Safeguard against timezone rollback on date-only strings
  const safeStr = /^\d{4}-\d{2}-\d{2}$/.test(lastInvoiceDate) ? `${lastInvoiceDate}T12:00:00` : lastInvoiceDate;
  const lastDate = new Date(safeStr);
  const oneMonthAgo = new Date();
  oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);
  return lastDate < oneMonthAgo;
};
