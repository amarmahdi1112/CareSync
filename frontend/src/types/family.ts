// Age group type (shared with Badge component)
export type AgeGroup = 'Infant' | 'Toddler' | 'Preschool' | 'School-Age';

// Child types
export interface Child {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth?: string;
  ageGroup: AgeGroup;
  enrollmentDate?: string;
  status?: 'active' | 'inactive';
}

// Guardian types
export interface Guardian {
  id: string;
  firstName: string;
  lastName: string;
  relationship: 'Mother' | 'Father' | 'Guardian' | 'Grandparent' | 'Other';
  phone: string;
  email: string;
  isPrimary: boolean;
}

// Emergency Contact
export interface EmergencyContact {
  id: string;
  name: string;
  relationship: string;
  phone: string;
}

// Family status
export type FamilyStatus = 'active' | 'inactive' | 'pending' | 'archived';

// Family list item (for list view)
export interface FamilyListItem {
  id: string;
  name: string;
  status: FamilyStatus;
  children: Child[];
  primaryContact: {
    name: string;
    phone: string;
    email: string;
  };
  createdAt: string;
}

// Family detail (full info)
export interface FamilyDetail extends FamilyListItem {
  address?: string;
  guardians: Guardian[];
  emergencyContacts: EmergencyContact[];
  notes?: string;
}

// Family stats
export interface FamilyStats {
  total: number;
  active: number;
  pending: number;
  inactive: number;
  totalChildren: number;
}

// Form types
export interface CreateFamilyInput {
  name: string;
  address?: string;
  primaryGuardian: Omit<Guardian, 'id' | 'isPrimary'>;
}

export interface UpdateFamilyInput {
  name?: string;
  address?: string;
  status?: FamilyStatus;
  notes?: string;
}

// Filter options
export const FAMILY_STATUS_OPTIONS = [
  { value: 'all', label: 'All Status' },
  { value: 'active', label: 'Active' },
  { value: 'pending', label: 'Pending' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'archived', label: 'Archived' },
];
