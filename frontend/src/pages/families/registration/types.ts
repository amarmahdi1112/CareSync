import type { AgeGroup } from '../../../types/family';

// ============================================
// REGISTRATION TYPES
// ============================================

export interface Guardian {
  id: string;
  firstName: string;
  lastName: string;
  relationship: string;
  address: string;
  city: string;
  postalCode: string;
  homePhone: string;
  workPhone: string;
  cellPhone: string;
  email: string;
}

export interface Child {
  id: string;
  firstName: string;
  middleName: string;
  lastName: string;
  dateOfBirth: string;
  startDate: string;
  gender: string;
  healthCareNumber: string;
  allergies: string;
  medicalConditions: string;
  medications: string;
  immunizationUpToDate: boolean | null;
  doctorName: string;
  doctorPhone: string;
}

export interface EmergencyContact {
  id: string;
  firstName: string;
  lastName: string;
  relationship: string;
  homePhone: string;
  cellPhone: string;
  authorizedPickup: boolean;
}

export interface Consents {
  photoConsent: boolean;
  fieldTripConsent: boolean;
  emergencyMedicalConsent: boolean;
}

export interface RegistrationData {
  primaryGuardian: Guardian;
  secondaryGuardian: Guardian | null;
  children: Child[];
  emergencyContacts: EmergencyContact[];
  consents: Consents;
  additionalNotes: string;
}

// Re-export AgeGroup for convenience
export type { AgeGroup };
