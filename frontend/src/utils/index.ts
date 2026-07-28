// Date utilities
export { 
  calculateAge, 
  formatDate, 
  formatDateTime, 
  getRelativeTime,
} from './date';

// Validation utilities
export {
  validateName,
  validateEmail,
  validatePhone,
  validateDate,
  validateDateOfBirth,
  validatePostalCode,
  validateGuardian,
  validateChild,
  validateEmergencyContact,
  isGuardianValid,
  isChildValid,
  isEmergencyContactValid,
  getGuardianErrors,
  getChildErrors,
  getEmergencyContactErrors,
  formatPhoneNumber,
  sanitizeName,
  sanitizePhone,
  sanitizePostalCode,
} from './validation';

export type {
  ValidationResult,
  GuardianValidation,
  ChildValidation,
  EmergencyContactValidation,
} from './validation';
