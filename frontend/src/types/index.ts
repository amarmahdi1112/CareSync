export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  role: string;
  organizationId?: string;
}

export interface Organization {
  id: string;
  name: string;
  organization_type: 'daycare' | 'osc' | 'both';
  status: string;
  
  // Contact
  primary_contact_name?: string;
  email: string;
  phone: string;
  
  // Address
  street_address?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  country?: string;
  
  // License & Capacity
  license_number?: string;
  licensed_capacity?: number;
  
  // Hours
  opening_time?: string;
  closing_time?: string;
  age_groups_served?: string[];
  
  // Optional
  logo_url?: string;
  website?: string;
  secondary_contact_name?: string;
  secondary_contact_phone?: string;
  secondary_contact_email?: string;
  business_number?: string;
  description?: string;
  programs_offered?: string[];
  billing_email?: string;
  timezone?: string;
  
  // Subscription
  subscription_plan?: string;
  trial_ends_at?: string;
  
  // Verification
  email_verified?: boolean;
  license_verified?: boolean;
}

export interface Child {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  familyId: string;
}

export interface Family {
  id: string;
  name: string;
  children: Child[];
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
}

export interface UIState {
  theme: 'light' | 'dark';
  sidebarOpen: boolean;
}

export interface RouteInfo {
  path: string;
  title: string;
  requiresAuth?: boolean;
  layout?: 'default' | 'auth';
}
