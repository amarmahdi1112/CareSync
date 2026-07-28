// ============================================
// Invoicing Module - Formatters
// ============================================

/**
 * Format a number as currency (USD)
 */
export const formatCurrency = (amount: number, symbol: string = '$'): string => {
  return `${symbol}${(amount || 0).toFixed(2)}`;
};

/**
 * Format a number as currency using Intl.NumberFormat
 */
export const formatCurrencyIntl = (amount: number, currency: string = 'USD'): string => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount || 0);
};

/**
 * Format a date string to a readable format
 */
export const formatDate = (dateStr: string | undefined | null): string => {
  if (!dateStr) return '-';
  // Extract just the YYYY-MM-DD portion from any date string format and
  // re-parse at noon local time to prevent timezone rollback.
  // This handles:
  //   "2026-05-01"                    (bare date from <input type="date">)
  //   "2026-05-01T00:00:00.000Z"      (ISO from PostgreSQL date column via GraphQL)
  //   "2026-05-01T12:00:00"           (already-safe strings)
  const dateOnly = dateStr.substring(0, 10); // "YYYY-MM-DD"
  return new Date(`${dateOnly}T12:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

/**
 * Format a date string to ISO format (YYYY-MM-DD)
 */
export const formatDateISO = (date: Date): string => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

/**
 * Get today's date in ISO format
 */
export const getToday = (): string => formatDateISO(new Date());

/**
 * Get a date X days from now in ISO format
 */
export const getDateFromNow = (days: number): string => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return formatDateISO(date);
};

/**
 * Format a percentage value
 */
export const formatPercentage = (value: number, decimals: number = 1): string => {
  return `${(value || 0).toFixed(decimals)}%`;
};

/**
 * Get ordinal suffix for a number (1st, 2nd, 3rd, etc.)
 */
export const getOrdinalSuffix = (num: number): string => {
  const suffixes = ['th', 'st', 'nd', 'rd'];
  const v = num % 100;
  return num + (suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0]);
};

/**
 * Capitalize the first letter of a string
 */
export const capitalize = (str: string): string => {
  return str.charAt(0).toUpperCase() + str.slice(1);
};

/**
 * Format a status string (replace underscores with spaces and capitalize)
 */
export const formatStatus = (status: string): string => {
  return status
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => capitalize(word))
    .join(' ');
};
