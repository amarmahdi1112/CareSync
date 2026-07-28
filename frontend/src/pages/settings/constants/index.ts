// ============================================
// Settings Module - Constants
// ============================================

import type { SelectOption, NotificationCategory } from '../types';
import {
  CalendarIcon,
  CurrencyDollarIcon,
  UserGroupIcon,
  ExclamationCircleIcon
} from '@heroicons/react/24/outline';

// -------------------- Timezone Options --------------------

export const TIMEZONES: SelectOption[] = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'America/Anchorage', label: 'Alaska Time (AKT)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii Time (HT)' },
  { value: 'America/Toronto', label: 'Eastern Time - Canada' },
  { value: 'America/Edmonton', label: 'Mountain Time - Canada' },
  { value: 'America/Vancouver', label: 'Pacific Time - Canada' },
  { value: 'Europe/London', label: 'Greenwich Mean Time (GMT)' },
  { value: 'Europe/Paris', label: 'Central European Time (CET)' },
  { value: 'UTC', label: 'Coordinated Universal Time (UTC)' },
];

// -------------------- Date Format Options --------------------

export const DATE_FORMATS: SelectOption[] = [
  { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY (12/25/2024)' },
  { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY (25/12/2024)' },
  { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD (2024-12-25)' },
  { value: 'MMM DD, YYYY', label: 'MMM DD, YYYY (Dec 25, 2024)' },
  { value: 'DD MMM YYYY', label: 'DD MMM YYYY (25 Dec 2024)' },
];

// -------------------- Language Options --------------------

export const LANGUAGES: SelectOption[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español (Spanish)' },
  { value: 'fr', label: 'Français (French)' },
];

// -------------------- Currency Options --------------------

export const CURRENCIES: SelectOption[] = [
  { value: 'USD', label: 'USD ($) - US Dollar' },
  { value: 'CAD', label: 'CAD ($) - Canadian Dollar' },
  { value: 'EUR', label: 'EUR (€) - Euro' },
  { value: 'GBP', label: 'GBP (£) - British Pound' },
];

// -------------------- Funding Source Types --------------------

export const FUNDING_TYPES: SelectOption[] = [
  { value: 'subsidy', label: 'Subsidy Program' },
  { value: 'grant', label: 'Grant' },
  { value: 'employer', label: 'Employer' },
  { value: 'other', label: 'Other' },
];

// -------------------- SMTP Encryption Options --------------------

export const SMTP_ENCRYPTIONS: SelectOption[] = [
  { value: 'tls', label: 'TLS (Recommended)' },
  { value: 'ssl', label: 'SSL' },
  { value: 'none', label: 'None' },
];

// -------------------- User Roles --------------------

export const USER_ROLES: SelectOption[] = [
  { value: 'admin', label: 'Administrator' },
  { value: 'manager', label: 'Manager' },
  { value: 'staff', label: 'Staff' },
  { value: 'viewer', label: 'View Only' },
];

// -------------------- Default System Preferences --------------------

export const DEFAULT_SYSTEM_PREFERENCES = {
  theme: 'light' as const,
  timezone: 'America/New_York',
  dateFormat: 'MM/DD/YYYY',
  timeFormat: '12h' as const,
  language: 'en',
  currency: 'USD',
  weekStartsOn: 'sunday' as const,
  compactMode: false,
  animationsEnabled: true,
};

// -------------------- Default Notification Categories --------------------

export const DEFAULT_NOTIFICATION_CATEGORIES: NotificationCategory[] = [
  {
    id: 'attendance',
    name: 'Attendance',
    description: 'Check-in, check-out, and attendance alerts',
    icon: CalendarIcon,
    settings: [
      { id: 'child_checkin', label: 'Child Check-in/Check-out', description: 'When a child is checked in or out', email: true, push: true, sms: false },
      { id: 'late_pickup', label: 'Late Pickup Alerts', description: 'When a child is not picked up on time', email: true, push: true, sms: true },
      { id: 'absence', label: 'Absence Notifications', description: 'When a child is marked absent', email: true, push: false, sms: false },
    ],
  },
  {
    id: 'billing',
    name: 'Billing & Payments',
    description: 'Invoices, payments, and billing reminders',
    icon: CurrencyDollarIcon,
    settings: [
      { id: 'invoice_created', label: 'New Invoice', description: 'When a new invoice is created', email: true, push: true, sms: false },
      { id: 'payment_received', label: 'Payment Received', description: 'When a payment is recorded', email: true, push: true, sms: false },
      { id: 'payment_overdue', label: 'Payment Overdue', description: 'When an invoice becomes overdue', email: true, push: true, sms: true },
    ],
  },
  {
    id: 'families',
    name: 'Families & Enrollment',
    description: 'Family registrations and updates',
    icon: UserGroupIcon,
    settings: [
      { id: 'new_registration', label: 'New Family Registration', description: 'When a new family registers', email: true, push: true, sms: false },
      { id: 'enrollment_change', label: 'Enrollment Changes', description: "When a child's enrollment status changes", email: true, push: false, sms: false },
      { id: 'document_uploaded', label: 'Document Uploaded', description: 'When a family uploads a document', email: true, push: false, sms: false },
    ],
  },
  {
    id: 'system',
    name: 'System & Security',
    description: 'Account activity and security alerts',
    icon: ExclamationCircleIcon,
    settings: [
      { id: 'new_login', label: 'New Login', description: 'When someone logs into your account', email: true, push: true, sms: false },
      { id: 'password_changed', label: 'Password Changed', description: 'When your password is changed', email: true, push: true, sms: true },
      { id: 'user_invited', label: 'Team Member Activity', description: 'When a team member is added or removed', email: true, push: false, sms: false },
    ],
  },
];

// -------------------- Default Invoice Settings Form --------------------

export const DEFAULT_INVOICE_SETTINGS_FORM = {
  currency_symbol: '$',
  invoice_prefix: 'INV-',
  default_tax_rate: 0,
  tax_name: '',
  default_notes: '',
  default_terms: '',
};

// -------------------- Default SMTP Form --------------------

export const DEFAULT_SMTP_FORM = {
  smtp_enabled: false,
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  smtp_encryption: 'tls',
  smtp_from_email: '',
  smtp_from_name: '',
};

// -------------------- Default Funding Source Form --------------------

export const DEFAULT_FUNDING_FORM = {
  name: '',
  funding_type: 'subsidy',
  description: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  billing_address: '',
};
