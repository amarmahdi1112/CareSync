// ============================================
// Settings Module - Centralized Types
// ============================================

// -------------------- Settings Category Types --------------------

export interface SettingsCategory {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  path: string;
  status: 'active' | 'coming_soon';
  badge?: string;
}

// -------------------- Organization Types --------------------

export interface OrganizationDetails {
  id: string;
  name: string;
  organization_type: string;
  status: string;
  primary_contact_name: string;
  email: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
  license_number: string;
  licensed_capacity: number;
  opening_time: string;
  closing_time: string;
  age_groups_served: string[];
  logo_url?: string;
  website?: string;
  secondary_contact_name?: string;
  secondary_contact_phone?: string;
  secondary_contact_email?: string;
  business_number?: string;
  description?: string;
  programs_offered: string[];
  billing_email?: string;
  timezone?: string;
  subscription_plan: string;
  trial_ends_at?: string;
  email_verified: boolean;
  license_verified: boolean;
}

export interface OrganizationFormData {
  name: string;
  primary_contact_name: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
  opening_time: string;
  closing_time: string;
  website: string;
  secondary_contact_name: string;
  secondary_contact_phone: string;
  secondary_contact_email: string;
  description: string;
  billing_email: string;
}

// -------------------- Invoice Settings Types --------------------

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

export interface SmtpSettings {
  smtp_enabled: boolean;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_encryption?: string;
  smtp_from_email?: string;
  smtp_from_name?: string;
  smtp_configured: boolean;
}

export interface FundingSource {
  id: string;
  name: string;
  funding_type: string;
  description?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  billing_address?: string;
  is_active: boolean;
}

// -------------------- Notification Types --------------------

export interface NotificationChannel {
  email: boolean;
  push: boolean;
  sms: boolean;
}

export interface NotificationCategoryPrefs {
  child_checkin?: NotificationChannel;
  late_pickup?: NotificationChannel;
  absence?: NotificationChannel;
  invoice_created?: NotificationChannel;
  payment_received?: NotificationChannel;
  payment_overdue?: NotificationChannel;
  new_registration?: NotificationChannel;
  enrollment_change?: NotificationChannel;
  document_uploaded?: NotificationChannel;
  new_login?: NotificationChannel;
  password_changed?: NotificationChannel;
  user_invited?: NotificationChannel;
}

export interface NotificationPreferences {
  [categoryId: string]: {
    [settingId: string]: NotificationChannel;
  };
}

export interface NotificationSetting {
  id: string;
  label: string;
  description: string;
  email: boolean;
  push: boolean;
  sms: boolean;
}

export interface NotificationCategory {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  settings: NotificationSetting[];
}

// -------------------- System Preferences Types --------------------

export interface SystemPreferences {
  theme: 'light' | 'dark' | 'system';
  timezone: string;
  dateFormat: string;
  timeFormat: '12h' | '24h';
  language: string;
  currency: string;
  weekStartsOn: 'sunday' | 'monday';
  compactMode: boolean;
  animationsEnabled: boolean;
}

// -------------------- Security Types --------------------

export interface PasswordForm {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

export interface PasswordStrength {
  strength: number;
  label: string;
  color: string;
}

// -------------------- Billing Types --------------------

export interface Plan {
  id: string;
  name: string;
  price: number;
  description: string;
  features: string[];
  popular?: boolean;
  maxChildren?: number;
  maxStaff?: number;
}

// -------------------- User Management Types --------------------

export interface TeamMember {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  status: 'active' | 'pending' | 'inactive';
  invited_at?: string;
  last_login?: string;
  avatar_url?: string;
}

export interface InviteFormData {
  email: string;
  role: string;
  first_name?: string;
  last_name?: string;
}

// -------------------- Common Option Types --------------------

export interface SelectOption {
  value: string;
  label: string;
}
