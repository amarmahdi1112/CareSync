import type { FacilityPatch, OrganizationPatch } from './settingsApi';

export interface OrganizationDraft {
  name: string;
  legal_name: string;
  email: string;
  phone: string;
  timezone: string;
}

export interface FacilityDraft {
  name: string;
  license_number: string;
  email: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  timezone: string;
  licensed_capacity: string;
  opening_time: string;
  closing_time: string;
  status: string;
}

export interface ProfileDraft { first_name: string; last_name: string; email: string }
export interface PasswordDraft { current: string; next: string; confirm: string }

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const optional = (value: string): string | null => value.trim() || null;

export function validateOrganizationDraft(draft: OrganizationDraft): string[] {
  const errors: string[] = [];
  if (!draft.name.trim()) errors.push('Organization name is required.');
  if (!draft.timezone.trim()) errors.push('Organization timezone is required.');
  if (draft.email && !EMAIL.test(draft.email.trim())) errors.push('Organization email is invalid.');
  return errors;
}

export function organizationPatch(draft: OrganizationDraft): OrganizationPatch {
  return {
    name: draft.name.trim(),
    legal_name: optional(draft.legal_name),
    email: optional(draft.email),
    phone: optional(draft.phone),
    timezone: draft.timezone.trim(),
  };
}

export function validateFacilityDraft(draft: FacilityDraft): string[] {
  const errors: string[] = [];
  if (!draft.name.trim()) errors.push('Facility name is required.');
  if (!draft.province.trim()) errors.push('Province is required.');
  if (!draft.timezone.trim()) errors.push('Facility timezone is required.');
  if (!draft.status.trim()) errors.push('Facility status is required.');
  if (draft.email && !EMAIL.test(draft.email.trim())) errors.push('Facility email is invalid.');
  const capacity = Number(draft.licensed_capacity);
  if (draft.licensed_capacity.trim() === '' || !Number.isInteger(capacity) || capacity < 0) {
    errors.push('Licensed capacity must be a non-negative whole number.');
  }
  if (draft.opening_time && draft.closing_time && draft.opening_time >= draft.closing_time) {
    errors.push('Closing time must be later than opening time.');
  }
  return errors;
}

export function facilityPatch(draft: FacilityDraft): FacilityPatch {
  return {
    name: draft.name.trim(),
    license_number: optional(draft.license_number),
    email: optional(draft.email),
    phone: optional(draft.phone),
    street_address: optional(draft.street_address),
    city: optional(draft.city),
    province: draft.province.trim(),
    postal_code: optional(draft.postal_code),
    timezone: draft.timezone.trim(),
    licensed_capacity: Number(draft.licensed_capacity),
    opening_time: optional(draft.opening_time),
    closing_time: optional(draft.closing_time),
    status: draft.status.trim(),
  };
}

export function validateProfileDraft(draft: ProfileDraft): string[] {
  const errors: string[] = [];
  if (!draft.first_name.trim()) errors.push('First name is required.');
  if (!draft.last_name.trim()) errors.push('Last name is required.');
  if (!EMAIL.test(draft.email.trim())) errors.push('A valid email is required.');
  return errors;
}

export function validatePasswordDraft(draft: PasswordDraft): string[] {
  const errors: string[] = [];
  if (!draft.current) errors.push('Current password is required.');
  if (draft.next.length < 10) errors.push('New password must be at least 10 characters.');
  if (draft.next !== draft.confirm) errors.push('New password confirmation does not match.');
  if (draft.current && draft.current === draft.next) errors.push('Choose a new password different from the current password.');
  return errors;
}
