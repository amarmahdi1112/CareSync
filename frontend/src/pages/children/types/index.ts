// ============================================
// Children Module Types
// ============================================

import type { AgeGroup } from '../../../types/family';

export interface ChildListItem {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  ageGroup: AgeGroup;
  familyName: string;
  familyId: string;
  status: 'active' | 'inactive';
  enrollmentDate: string;
}

export interface ChildGraphQL {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  start_date: string;
  gender?: string;
  age_group?: string;
  health_care_number?: string;
  allergies?: string;
  medical_conditions?: string;
  medications?: string;
  immunization_up_to_date?: boolean;
  doctor_name?: string;
  doctor_phone?: string;
  is_active: boolean;
  family_id: string;
}

// Map age group from GraphQL to display format
export const mapAgeGroup = (ageGroup?: string): AgeGroup => {
  if (!ageGroup) return 'Preschool';
  if (ageGroup === 'SchoolAge') return 'School-Age';
  return ageGroup as AgeGroup;
};

// Calculate age from date of birth
export const calculateAge = (dob: string): string => {
  const birth = new Date(dob);
  const today = new Date();
  const years = today.getFullYear() - birth.getFullYear();
  const months = today.getMonth() - birth.getMonth();
  
  if (years < 1) {
    const totalMonths = months + (years * 12);
    return `${totalMonths} month${totalMonths !== 1 ? 's' : ''}`;
  }
  if (months > 0) {
    return `${years} year${years !== 1 ? 's' : ''}, ${months} month${months !== 1 ? 's' : ''}`;
  }
  return `${years} year${years !== 1 ? 's' : ''}`;
};
