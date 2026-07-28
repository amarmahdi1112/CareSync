export interface RegisterDraft {
  firstName: string;
  lastName: string;
  organizationName: string;
  email: string;
  password: string;
  confirmPassword: string;
  acceptedTerms: boolean;
}

export type RegisterErrors = Partial<Record<keyof RegisterDraft, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateRegisterDraft(input: RegisterDraft): RegisterErrors {
  const errors: RegisterErrors = {};
  if (!input.firstName.trim()) errors.firstName = 'Enter your first name.';
  if (!input.lastName.trim()) errors.lastName = 'Enter your last name.';
  if (input.organizationName.trim().length > 255) errors.organizationName = 'Use 255 characters or fewer.';
  if (!EMAIL.test(input.email.trim())) errors.email = 'Enter a complete email address.';
  if (input.password.length < 10) errors.password = 'Use at least 10 characters.';
  else if (!/[A-Za-z]/.test(input.password) || !/\d/.test(input.password)) {
    errors.password = 'Include at least one letter and one number.';
  }
  if (!input.confirmPassword) errors.confirmPassword = 'Confirm your password.';
  else if (input.confirmPassword !== input.password) errors.confirmPassword = 'The passwords do not match.';
  if (!input.acceptedTerms) errors.acceptedTerms = 'Accept the terms and privacy notice to continue.';
  return errors;
}
