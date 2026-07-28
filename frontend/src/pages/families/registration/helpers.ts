import type { Guardian, Child, EmergencyContact, RegistrationData, AgeGroup } from './types';
import {
  validateGuardian,
  validateChild,
  validateEmergencyContact,
  getGuardianErrors,
  getChildErrors,
  getEmergencyContactErrors,
} from '../../../utils';

// ============================================
// FACTORY FUNCTIONS
// ============================================

export const createEmptyGuardian = (): Guardian => ({
  id: crypto.randomUUID(),
  firstName: '',
  lastName: '',
  relationship: '',
  address: '',
  city: '',
  postalCode: '',
  homePhone: '',
  workPhone: '',
  cellPhone: '',
  email: '',
});

export const createEmptyChild = (lastName = ''): Child => ({
  id: crypto.randomUUID(),
  firstName: '',
  middleName: '',
  lastName,
  dateOfBirth: '',
  startDate: '',
  gender: '',
  healthCareNumber: '',
  allergies: '',
  medicalConditions: '',
  medications: '',
  immunizationUpToDate: null,
  doctorName: '',
  doctorPhone: '',
});

export const createEmptyEmergencyContact = (): EmergencyContact => ({
  id: crypto.randomUUID(),
  firstName: '',
  lastName: '',
  relationship: 'Family Friend', // Default relationship
  homePhone: '',
  cellPhone: '',
  authorizedPickup: true,
});

// ============================================
// UTILITIES
// ============================================

/**
 * Calculate age group based on date of birth
 * Infant: 0-19 months
 * Toddler: 20-36 months
 * Preschool: 37-77 months
 * School-Age: 78+ months (6.5+ years)
 */
export const calculateAgeGroup = (dob: string): AgeGroup | null => {
  if (!dob) return null;
  const birth = new Date(dob);
  const today = new Date();
  
  let months = (today.getFullYear() - birth.getFullYear()) * 12 + (today.getMonth() - birth.getMonth());
  if (today.getDate() < birth.getDate()) months--;
  
  if (months <= 19) return 'Infant';
  if (months <= 36) return 'Toddler';
  if (months <= 77) return 'Preschool';
  return 'School-Age';
};

// ============================================
// INITIAL DATA
// ============================================

export const createInitialData = (): RegistrationData => ({
  primaryGuardian: createEmptyGuardian(),
  secondaryGuardian: null,
  children: [createEmptyChild()],
  emergencyContacts: [createEmptyEmergencyContact()],
  consents: {
    photoConsent: false,
    fieldTripConsent: false,
    emergencyMedicalConsent: false,
  },
  additionalNotes: '',
});

// ============================================
// VALIDATION (using comprehensive validators)
// ============================================

export const validateGuardian1 = (guardian: Guardian): string[] => {
  const validation = validateGuardian(guardian, true);
  return getGuardianErrors(validation);
};

export const validateGuardian2 = (guardian: Guardian | null): string[] => {
  if (!guardian) return [];
  // Only validate if they've started filling it out
  const hasStarted = guardian.firstName || guardian.lastName || guardian.email || guardian.cellPhone;
  if (!hasStarted) return [];
  
  const validation = validateGuardian(guardian, false);
  return getGuardianErrors(validation);
};

export const validateChildren = (children: Child[]): string[] => {
  const errors: string[] = [];
  if (children.length === 0) {
    errors.push('At least one child is required');
    return errors;
  }
  
  children.forEach((child, i) => {
    const validation = validateChild(child);
    const childErrors = getChildErrors(validation);
    childErrors.forEach(err => errors.push(`Child ${i + 1}: ${err}`));
  });
  
  return errors;
};

export const validateEmergencyContacts = (contacts: EmergencyContact[]): string[] => {
  const errors: string[] = [];
  if (contacts.length === 0) {
    errors.push('At least one emergency contact is required');
    return errors;
  }
  
  contacts.forEach((ec, i) => {
    const validation = validateEmergencyContact(ec);
    const contactErrors = getEmergencyContactErrors(validation);
    contactErrors.forEach(err => errors.push(`Contact ${i + 1}: ${err}`));
  });
  
  return errors;
};

export const validateConsents = (consents: { emergencyMedicalConsent: boolean }): string[] => {
  const errors: string[] = [];
  if (!consents.emergencyMedicalConsent) {
    errors.push('Emergency medical consent is required');
  }
  return errors;
};
