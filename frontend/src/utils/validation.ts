/**
 * Form Validation Utilities
 * Comprehensive validation for form inputs
 */

// Regex patterns
const PATTERNS = {
  // Names: letters, spaces, hyphens, apostrophes only
  name: /^[a-zA-Z\s\-']+$/,
  // Email: standard email format
  email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  // Phone: digits, spaces, dashes, parentheses, plus sign (10+ digits)
  phone: /^[\d\s\-()+ ]{10,}$/,
  // Phone digits only (for counting)
  phoneDigits: /\d/g,
  // Postal code: Canadian format (A1A 1A1) or US ZIP (12345 or 12345-6789)
  postalCodeCA: /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/,
  postalCodeUS: /^\d{5}(-\d{4})?$/,
  // Health care number: alphanumeric
  healthCareNumber: /^[A-Za-z0-9\s-]+$/,
  // Date: YYYY-MM-DD format
  date: /^\d{4}-\d{2}-\d{2}$/,
};

// Validation result type
export interface ValidationResult {
  isValid: boolean;
  error?: string;
}

// ============================================
// NAME VALIDATION
// ============================================

export const validateName = (value: string, fieldName: string = 'Name'): ValidationResult => {
  const trimmed = value.trim();
  
  if (!trimmed) {
    return { isValid: false, error: `${fieldName} is required` };
  }
  
  if (trimmed.length < 2) {
    return { isValid: false, error: `${fieldName} must be at least 2 characters` };
  }
  
  if (trimmed.length > 50) {
    return { isValid: false, error: `${fieldName} must be less than 50 characters` };
  }
  
  if (!PATTERNS.name.test(trimmed)) {
    return { isValid: false, error: `${fieldName} can only contain letters, spaces, hyphens, and apostrophes` };
  }
  
  return { isValid: true };
};

// ============================================
// EMAIL VALIDATION
// ============================================

export const validateEmail = (value: string, required: boolean = true): ValidationResult => {
  const trimmed = value.trim().toLowerCase();
  
  if (!trimmed) {
    if (required) {
      return { isValid: false, error: 'Email is required' };
    }
    return { isValid: true };
  }
  
  if (!PATTERNS.email.test(trimmed)) {
    return { isValid: false, error: 'Please enter a valid email address' };
  }
  
  if (trimmed.length > 100) {
    return { isValid: false, error: 'Email must be less than 100 characters' };
  }
  
  return { isValid: true };
};

// ============================================
// PHONE VALIDATION
// ============================================

export const validatePhone = (value: string, required: boolean = true, fieldName: string = 'Phone'): ValidationResult => {
  const trimmed = value.trim();
  
  if (!trimmed) {
    if (required) {
      return { isValid: false, error: `${fieldName} is required` };
    }
    return { isValid: true };
  }
  
  // Count digits
  const digits = trimmed.match(PATTERNS.phoneDigits);
  const digitCount = digits ? digits.length : 0;
  
  if (digitCount < 10) {
    return { isValid: false, error: `${fieldName} must have at least 10 digits` };
  }
  
  if (digitCount > 15) {
    return { isValid: false, error: `${fieldName} has too many digits` };
  }
  
  // Check for invalid characters
  const validChars = /^[\d\s\-()+ ]+$/;
  if (!validChars.test(trimmed)) {
    return { isValid: false, error: `${fieldName} contains invalid characters` };
  }
  
  return { isValid: true };
};

// Format phone number for display (XXX) XXX-XXXX
export const formatPhoneNumber = (value: string): string => {
  const digits = value.replace(/\D/g, '');
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
};

// ============================================
// DATE VALIDATION
// ============================================

export const validateDate = (value: string, fieldName: string = 'Date', options?: {
  required?: boolean;
  minDate?: Date;
  maxDate?: Date;
  allowFuture?: boolean;
  allowPast?: boolean;
}): ValidationResult => {
  const { required = true, minDate, maxDate, allowFuture = true, allowPast = true } = options || {};
  
  if (!value) {
    if (required) {
      return { isValid: false, error: `${fieldName} is required` };
    }
    return { isValid: true };
  }
  
  if (!PATTERNS.date.test(value)) {
    return { isValid: false, error: `${fieldName} must be in YYYY-MM-DD format` };
  }
  
  const date = new Date(value);
  if (isNaN(date.getTime())) {
    return { isValid: false, error: `${fieldName} is not a valid date` };
  }
  
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  if (!allowFuture && date > today) {
    return { isValid: false, error: `${fieldName} cannot be in the future` };
  }
  
  if (!allowPast && date < today) {
    return { isValid: false, error: `${fieldName} cannot be in the past` };
  }
  
  if (minDate && date < minDate) {
    return { isValid: false, error: `${fieldName} is too early` };
  }
  
  if (maxDate && date > maxDate) {
    return { isValid: false, error: `${fieldName} is too late` };
  }
  
  return { isValid: true };
};

export const validateDateOfBirth = (value: string): ValidationResult => {
  const result = validateDate(value, 'Date of birth', { allowFuture: false });
  if (!result.isValid) return result;
  
  const dob = new Date(value);
  const today = new Date();
  const age = today.getFullYear() - dob.getFullYear();
  
  if (age > 18) {
    return { isValid: false, error: 'Child must be 18 years or younger' };
  }
  
  if (age < 0) {
    return { isValid: false, error: 'Date of birth cannot be in the future' };
  }
  
  return { isValid: true };
};

// ============================================
// POSTAL CODE VALIDATION
// ============================================

export const validatePostalCode = (value: string, required: boolean = false): ValidationResult => {
  const trimmed = value.trim().toUpperCase();
  
  if (!trimmed) {
    if (required) {
      return { isValid: false, error: 'Postal code is required' };
    }
    return { isValid: true };
  }
  
  // Accept Canadian or US format
  if (!PATTERNS.postalCodeCA.test(trimmed) && !PATTERNS.postalCodeUS.test(trimmed)) {
    return { isValid: false, error: 'Please enter a valid postal code (e.g., A1A 1A1 or 12345)' };
  }
  
  return { isValid: true };
};

// ============================================
// GUARDIAN VALIDATION
// ============================================

export interface GuardianValidation {
  firstName: ValidationResult;
  lastName: ValidationResult;
  email: ValidationResult;
  cellPhone: ValidationResult;
  homePhone: ValidationResult;
  workPhone: ValidationResult;
  relationship: ValidationResult;
  postalCode: ValidationResult;
}

export const validateGuardian = (guardian: {
  firstName: string;
  lastName: string;
  email: string;
  cellPhone: string;
  homePhone?: string;
  workPhone?: string;
  relationship: string;
  postalCode?: string;
}, isPrimary: boolean = true): GuardianValidation => {
  return {
    firstName: validateName(guardian.firstName, 'First name'),
    lastName: validateName(guardian.lastName, 'Last name'),
    email: validateEmail(guardian.email, isPrimary),
    cellPhone: validatePhone(guardian.cellPhone, isPrimary, 'Cell phone'),
    homePhone: validatePhone(guardian.homePhone || '', false, 'Home phone'),
    workPhone: validatePhone(guardian.workPhone || '', false, 'Work phone'),
    relationship: guardian.relationship 
      ? { isValid: true } 
      : { isValid: false, error: 'Please select a relationship' },
    postalCode: validatePostalCode(guardian.postalCode || '', false),
  };
};

export const isGuardianValid = (validation: GuardianValidation): boolean => {
  return Object.values(validation).every(v => v.isValid);
};

export const getGuardianErrors = (validation: GuardianValidation): string[] => {
  return Object.values(validation)
    .filter(v => !v.isValid && v.error)
    .map(v => v.error as string);
};

// ============================================
// CHILD VALIDATION
// ============================================

export interface ChildValidation {
  firstName: ValidationResult;
  lastName: ValidationResult;
  dateOfBirth: ValidationResult;
  startDate: ValidationResult;
  healthCareNumber: ValidationResult;
}

export const validateChild = (child: {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  startDate: string;
  healthCareNumber?: string;
}): ChildValidation => {
  return {
    firstName: validateName(child.firstName, 'First name'),
    lastName: validateName(child.lastName, 'Last name'),
    dateOfBirth: validateDateOfBirth(child.dateOfBirth),
    startDate: validateDate(child.startDate, 'Start date', { allowPast: true }),
    healthCareNumber: child.healthCareNumber 
      ? (PATTERNS.healthCareNumber.test(child.healthCareNumber) 
          ? { isValid: true } 
          : { isValid: false, error: 'Health care number contains invalid characters' })
      : { isValid: true },
  };
};

export const isChildValid = (validation: ChildValidation): boolean => {
  return Object.values(validation).every(v => v.isValid);
};

export const getChildErrors = (validation: ChildValidation): string[] => {
  return Object.values(validation)
    .filter(v => !v.isValid && v.error)
    .map(v => v.error as string);
};

// ============================================
// EMERGENCY CONTACT VALIDATION
// ============================================

export interface EmergencyContactValidation {
  firstName: ValidationResult;
  lastName: ValidationResult;
  cellPhone: ValidationResult;
  homePhone: ValidationResult;
  relationship: ValidationResult;
}

export const validateEmergencyContact = (contact: {
  firstName: string;
  lastName: string;
  cellPhone: string;
  homePhone?: string;
  relationship: string;
}): EmergencyContactValidation => {
  return {
    firstName: validateName(contact.firstName, 'First name'),
    lastName: validateName(contact.lastName, 'Last name'),
    cellPhone: validatePhone(contact.cellPhone, true, 'Cell phone'),
    homePhone: validatePhone(contact.homePhone || '', false, 'Home phone'),
    relationship: contact.relationship 
      ? { isValid: true } 
      : { isValid: false, error: 'Please enter relationship' },
  };
};

export const isEmergencyContactValid = (validation: EmergencyContactValidation): boolean => {
  return Object.values(validation).every(v => v.isValid);
};

export const getEmergencyContactErrors = (validation: EmergencyContactValidation): string[] => {
  return Object.values(validation)
    .filter(v => !v.isValid && v.error)
    .map(v => v.error as string);
};

// ============================================
// INPUT SANITIZATION
// ============================================

// Sanitize name input (remove invalid characters as user types)
export const sanitizeName = (value: string): string => {
  return value.replace(/[^a-zA-Z\s\-']/g, '');
};

// Sanitize phone input (keep only digits and formatting chars)
export const sanitizePhone = (value: string): string => {
  return value.replace(/[^\d\s\-()+ ]/g, '');
};

// Sanitize postal code
export const sanitizePostalCode = (value: string): string => {
  return value.toUpperCase().replace(/[^A-Z0-9\s-]/g, '');
};
