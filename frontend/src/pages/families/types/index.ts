// ============================================
// Families Module - Types
// ============================================

// Status types
export type FamilyStatus = 'active' | 'inactive' | 'pending' | 'archived';
export type AgeGroup = 'Infant' | 'Toddler' | 'Preschool' | 'School-Age';
export type GuardianType = 'primary' | 'secondary';
export type Relationship = 'Mother' | 'Father' | 'Guardian' | 'Grandparent' | 'Other';

// Child
export interface Child {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  start_date: string;
  gender?: string;
  age_group?: AgeGroup;
  is_active: boolean;
  health_care_number?: string;
  allergies?: string;
  medical_conditions?: string;
  medications?: string;
  immunization_up_to_date?: boolean;
  doctor_name?: string;
  doctor_phone?: string;
}

// Guardian
export interface Guardian {
  id: string;
  first_name: string;
  last_name: string;
  relationship: Relationship;
  guardian_type: GuardianType;
  email: string;
  cell_phone: string;
  home_phone?: string;
  work_phone?: string;
  address?: string;
  city?: string;
  postal_code?: string;
}

// Emergency Contact
export interface EmergencyContact {
  id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone?: string;
  authorized_pickup: boolean;
}

// Family (full)
export interface Family {
  id: string;
  name: string;
  status: FamilyStatus;
  additional_notes?: string;
  photo_consent: boolean;
  field_trip_consent: boolean;
  emergency_medical_consent: boolean;
  guardians: Guardian[];
  children: Child[];
  emergency_contacts: EmergencyContact[];
  created_at: string;
  updated_at: string;
}

// Family list item (simplified for lists)
export interface FamilyListItem {
  id: string;
  name: string;
  status: FamilyStatus;
  childCount: number;
  children: {
    id: string;
    firstName: string;
    lastName: string;
    ageGroup: AgeGroup;
    isActive: boolean;
  }[];
  primaryContact: {
    name: string;
    phone: string;
    email: string;
  };
  createdAt: string;
}

// Dashboard stats
export interface FamilyDashboard {
  totalFamilies: number;
  activeFamilies: number;
  pendingFamilies: number;
  totalChildren: number;
  childrenByAgeGroup: {
    infant: number;
    toddler: number;
    preschool: number;
    schoolAge: number;
  };
}

// Filters
export interface FamilyFilters {
  searchTerm: string;
  status: FamilyStatus | 'all';
  ageGroup: AgeGroup | 'all';
}

// Tab types
export type FamilyTabType = 'overview' | 'children' | 'guardians' | 'emergency' | 'documents';
