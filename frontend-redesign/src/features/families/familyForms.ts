import type {
  EmergencyContactInput,
  FamilyDetailRecord,
  FamilyEditInput,
  FamilyRegistrationInput,
  GuardianInput,
} from './types';

export type FamilyValidationErrors = Record<string, string>;

/** Mirrors backend/app/basic/schemas.py string limits for preflight validation and input attributes. */
export const FAMILY_FIELD_LIMITS = {
  name: 255,
  file_number: 80,
  first_name: 100,
  last_name: 100,
  relationship: 100,
  email: 320,
  cell_phone: 30,
  home_phone: 30,
  work_phone: 30,
  address: 255,
  city: 100,
  postal_code: 20,
} as const;

export interface FamilyRegistrationPayload {
  name: string;
  file_number: string | null;
  status: string;
  primary_guardian: Record<string, unknown> | null;
  secondary_guardian: Record<string, unknown> | null;
  emergency_contacts: Array<Record<string, unknown>>;
  consents: FamilyRegistrationInput['consents'];
  additional_notes: string | null;
}

export interface FamilyUpdatePayload {
  name: string;
  status: string;
  file_number: string | null;
  consents: FamilyEditInput['consents'];
  additional_notes: string | null;
  primary_guardian?: Record<string, unknown> | null;
  secondary_guardian?: Record<string, unknown> | null;
  emergency_contacts?: Array<Record<string, unknown>> | null;
}

export type FamilyCoreUpdatePayload = Pick<FamilyUpdatePayload,
  'name' | 'status' | 'file_number' | 'consents' | 'additional_notes'>;

let fallbackSequence = 0;

function clientId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  fallbackSequence += 1;
  return `${prefix}-${Date.now()}-${fallbackSequence}`;
}

export function emptyGuardian(guardianType = 'primary'): GuardianInput {
  return {
    record_id: null,
    first_name: '',
    last_name: '',
    relationship: '',
    guardian_type: guardianType,
    email: '',
    cell_phone: '',
    home_phone: '',
    work_phone: '',
    address: '',
    city: '',
    postal_code: '',
    authorized_pickup: false,
  };
}

export function emptyEmergencyContact(client_id = clientId('contact')): EmergencyContactInput {
  return {
    client_id,
    record_id: null,
    first_name: '',
    last_name: '',
    relationship: '',
    cell_phone: '',
    home_phone: '',
    authorized_pickup: false,
  };
}

export function emptyFamilyRegistration(status: 'active' | 'pending' = 'active'): FamilyRegistrationInput {
  return {
    name: '',
    file_number: '',
    status,
    include_primary_guardian: true,
    primary_guardian: emptyGuardian('primary'),
    include_secondary_guardian: false,
    secondary_guardian: emptyGuardian('secondary'),
    emergency_contacts: [],
    consents: {
      photo_consent: false,
      field_trip_consent: false,
      emergency_medical_consent: false,
    },
    additional_notes: '',
  };
}

function hasText(value: string): boolean {
  return value.trim().length > 0;
}

function emailIsValid(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function phoneIsValid(value: string): boolean {
  return value.replace(/\D/g, '').length >= 7;
}

function tooLong(value: string, limit: number): boolean {
  return value.trim().length > limit;
}

function lengthError(limit: number): string {
  return `Use ${limit} characters or fewer.`;
}

function validateRequiredText(
  value: string,
  path: string,
  requiredMessage: string,
  limit: number,
  errors: FamilyValidationErrors,
): void {
  if (!hasText(value)) errors[path] = requiredMessage;
  else if (tooLong(value, limit)) errors[path] = lengthError(limit);
}

function validateOptionalText(
  value: string,
  path: string,
  limit: number,
  errors: FamilyValidationErrors,
): void {
  if (tooLong(value, limit)) errors[path] = lengthError(limit);
}

function validateGuardian(guardian: GuardianInput, path: string, errors: FamilyValidationErrors): void {
  validateRequiredText(guardian.first_name, `${path}.first_name`, 'First name is required.', FAMILY_FIELD_LIMITS.first_name, errors);
  validateRequiredText(guardian.last_name, `${path}.last_name`, 'Last name is required.', FAMILY_FIELD_LIMITS.last_name, errors);
  validateRequiredText(guardian.relationship, `${path}.relationship`, 'Relationship is required.', FAMILY_FIELD_LIMITS.relationship, errors);
  if (!hasText(guardian.email)) errors[`${path}.email`] = 'Email is required.';
  else if (tooLong(guardian.email, FAMILY_FIELD_LIMITS.email)) errors[`${path}.email`] = lengthError(FAMILY_FIELD_LIMITS.email);
  else if (!emailIsValid(guardian.email)) errors[`${path}.email`] = 'Enter a complete email address.';
  if (!hasText(guardian.cell_phone)) errors[`${path}.cell_phone`] = 'Cell phone is required.';
  else if (tooLong(guardian.cell_phone, FAMILY_FIELD_LIMITS.cell_phone)) errors[`${path}.cell_phone`] = lengthError(FAMILY_FIELD_LIMITS.cell_phone);
  else if (!phoneIsValid(guardian.cell_phone)) errors[`${path}.cell_phone`] = 'Enter at least seven phone digits.';
  validateOptionalText(guardian.home_phone, `${path}.home_phone`, FAMILY_FIELD_LIMITS.home_phone, errors);
  validateOptionalText(guardian.work_phone, `${path}.work_phone`, FAMILY_FIELD_LIMITS.work_phone, errors);
  validateOptionalText(guardian.address, `${path}.address`, FAMILY_FIELD_LIMITS.address, errors);
  validateOptionalText(guardian.city, `${path}.city`, FAMILY_FIELD_LIMITS.city, errors);
  validateOptionalText(guardian.postal_code, `${path}.postal_code`, FAMILY_FIELD_LIMITS.postal_code, errors);
}

function validateEmergencyContact(
  contact: EmergencyContactInput,
  path: string,
  errors: FamilyValidationErrors,
): void {
  validateRequiredText(contact.first_name, `${path}.first_name`, 'First name is required.', FAMILY_FIELD_LIMITS.first_name, errors);
  validateRequiredText(contact.last_name, `${path}.last_name`, 'Last name is required.', FAMILY_FIELD_LIMITS.last_name, errors);
  validateRequiredText(contact.relationship, `${path}.relationship`, 'Relationship is required.', FAMILY_FIELD_LIMITS.relationship, errors);
  if (!hasText(contact.cell_phone)) errors[`${path}.cell_phone`] = 'Cell phone is required.';
  else if (tooLong(contact.cell_phone, FAMILY_FIELD_LIMITS.cell_phone)) errors[`${path}.cell_phone`] = lengthError(FAMILY_FIELD_LIMITS.cell_phone);
  else if (!phoneIsValid(contact.cell_phone)) errors[`${path}.cell_phone`] = 'Enter at least seven phone digits.';
  validateOptionalText(contact.home_phone, `${path}.home_phone`, FAMILY_FIELD_LIMITS.home_phone, errors);
}

export function validateFamilyRegistration(input: FamilyRegistrationInput): FamilyValidationErrors {
  const errors: FamilyValidationErrors = {};
  validateRequiredText(input.name, 'name', 'Family name is required.', FAMILY_FIELD_LIMITS.name, errors);
  validateOptionalText(input.file_number, 'file_number', FAMILY_FIELD_LIMITS.file_number, errors);
  if (!hasText(input.status)) errors.status = 'Status is required.';
  if (input.include_primary_guardian) validateGuardian(input.primary_guardian, 'primary_guardian', errors);
  if (input.include_secondary_guardian) validateGuardian(input.secondary_guardian, 'secondary_guardian', errors);
  input.emergency_contacts.forEach((contact, index) => validateEmergencyContact(contact, `emergency_contacts.${index}`, errors));
  return errors;
}

export function validateFamilyEdit(input: FamilyEditInput): FamilyValidationErrors {
  const errors: FamilyValidationErrors = {};
  validateRequiredText(input.name, 'name', 'Family name is required.', FAMILY_FIELD_LIMITS.name, errors);
  validateOptionalText(input.file_number, 'file_number', FAMILY_FIELD_LIMITS.file_number, errors);
  if (!hasText(input.status)) errors.status = 'Status is required.';
  if (input.primary_guardian) validateGuardian(input.primary_guardian, 'primary_guardian', errors);
  if (input.secondary_guardian) validateGuardian(input.secondary_guardian, 'secondary_guardian', errors);
  input.emergency_contacts?.forEach((contact, index) => validateEmergencyContact(contact, `emergency_contacts.${index}`, errors));
  return errors;
}

function optional(value: string): string | null {
  const cleaned = value.trim();
  return cleaned || null;
}

export function guardianCommandPayload(input: GuardianInput): Record<string, unknown> {
  return {
    first_name: input.first_name.trim(),
    last_name: input.last_name.trim(),
    relationship: input.relationship.trim(),
    email: input.email.trim().toLocaleLowerCase(),
    cell_phone: input.cell_phone.trim(),
    home_phone: optional(input.home_phone),
    work_phone: optional(input.work_phone),
    address: optional(input.address),
    city: optional(input.city),
    postal_code: optional(input.postal_code),
    authorized_pickup: input.authorized_pickup,
  };
}

export function emergencyContactCommandPayload(input: EmergencyContactInput): Record<string, unknown> {
  return {
    first_name: input.first_name.trim(),
    last_name: input.last_name.trim(),
    relationship: input.relationship.trim(),
    cell_phone: input.cell_phone.trim(),
    home_phone: optional(input.home_phone),
    authorized_pickup: input.authorized_pickup,
  };
}

export function toFamilyRegistrationPayload(input: FamilyRegistrationInput): FamilyRegistrationPayload {
  return {
    name: input.name.trim(),
    file_number: optional(input.file_number),
    status: input.status,
    primary_guardian: input.include_primary_guardian
      ? guardianCommandPayload({ ...input.primary_guardian, guardian_type: 'primary' })
      : null,
    secondary_guardian: input.include_secondary_guardian
      ? guardianCommandPayload({ ...input.secondary_guardian, guardian_type: 'secondary' })
      : null,
    emergency_contacts: input.emergency_contacts.map(emergencyContactCommandPayload),
    consents: { ...input.consents },
    additional_notes: optional(input.additional_notes),
  };
}

export function toFamilyEditInput(detail: FamilyDetailRecord): FamilyEditInput {
  const primary = detail.guardians.find((guardian) => guardian.guardian_type.toLowerCase() === 'primary');
  const secondary = detail.guardians.find((guardian) => guardian.guardian_type.toLowerCase() === 'secondary');
  const guardianInput = (
    guardian: FamilyDetailRecord['guardians'][number] | undefined,
    guardianType: 'primary' | 'secondary',
  ): GuardianInput | null => guardian ? {
    record_id: guardian.id,
    first_name: guardian.first_name,
    last_name: guardian.last_name,
    relationship: guardian.relationship || '',
    guardian_type: guardianType,
    email: guardian.email,
    cell_phone: guardian.cell_phone,
    home_phone: guardian.home_phone || '',
    work_phone: guardian.work_phone || '',
    address: guardian.address || '',
    city: guardian.city || '',
    postal_code: guardian.postal_code || '',
    authorized_pickup: guardian.authorized_pickup,
  } : null;

  return {
    name: detail.name,
    status: detail.status,
    file_number: detail.file_number || '',
    consents: {
      photo_consent: detail.photo_consent,
      field_trip_consent: detail.field_trip_consent,
      emergency_medical_consent: detail.emergency_medical_consent,
    },
    additional_notes: detail.additional_notes || '',
    primary_guardian: guardianInput(primary, 'primary'),
    secondary_guardian: guardianInput(secondary, 'secondary'),
    emergency_contacts: detail.emergency_contacts.map((contact) => ({
      client_id: contact.id,
      record_id: contact.id,
      first_name: contact.first_name,
      last_name: contact.last_name,
      relationship: contact.relationship,
      cell_phone: contact.cell_phone,
      home_phone: contact.home_phone || '',
      authorized_pickup: contact.authorized_pickup,
    })),
  };
}

function samePayload(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function toFamilyCoreUpdatePayload(input: FamilyEditInput): FamilyCoreUpdatePayload {
  return {
    name: input.name.trim(),
    status: input.status,
    file_number: optional(input.file_number),
    consents: { ...input.consents },
    additional_notes: optional(input.additional_notes),
  };
}

export function familyCoreChanged(input: FamilyEditInput, baseline: FamilyDetailRecord): boolean {
  return !samePayload(toFamilyCoreUpdatePayload(input), toFamilyCoreUpdatePayload(toFamilyEditInput(baseline)));
}

/**
 * Keeps the full care network in the edit draft, but omits unchanged sections
 * from PATCH so contact IDs are not churned by the server's atomic replacement.
 */
export function toFamilyPatchInput(
  input: FamilyEditInput,
  baselineDetail: FamilyDetailRecord,
): FamilyEditInput {
  const baseline = toFamilyEditInput(baselineDetail);
  const patch: FamilyEditInput = { ...input };

  if (Object.prototype.hasOwnProperty.call(input, 'primary_guardian')) {
    const currentPayload = input.primary_guardian ? guardianCommandPayload(input.primary_guardian) : null;
    const baselinePayload = baseline.primary_guardian ? guardianCommandPayload(baseline.primary_guardian) : null;
    if (samePayload(currentPayload, baselinePayload)) delete patch.primary_guardian;
  }
  if (Object.prototype.hasOwnProperty.call(input, 'secondary_guardian')) {
    const currentPayload = input.secondary_guardian ? guardianCommandPayload(input.secondary_guardian) : null;
    const baselinePayload = baseline.secondary_guardian ? guardianCommandPayload(baseline.secondary_guardian) : null;
    if (samePayload(currentPayload, baselinePayload)) delete patch.secondary_guardian;
  }
  if (Object.prototype.hasOwnProperty.call(input, 'emergency_contacts')) {
    const currentPayload = (input.emergency_contacts || []).map(emergencyContactCommandPayload);
    const baselinePayload = (baseline.emergency_contacts || []).map(emergencyContactCommandPayload);
    if (samePayload(currentPayload, baselinePayload)) delete patch.emergency_contacts;
  }
  return patch;
}

export function toFamilyUpdatePayload(input: FamilyEditInput): FamilyUpdatePayload {
  const payload: FamilyUpdatePayload = toFamilyCoreUpdatePayload(input);

  if (Object.prototype.hasOwnProperty.call(input, 'primary_guardian')) {
    payload.primary_guardian = input.primary_guardian
      ? guardianCommandPayload({ ...input.primary_guardian, guardian_type: 'primary' })
      : null;
  }
  if (Object.prototype.hasOwnProperty.call(input, 'secondary_guardian')) {
    payload.secondary_guardian = input.secondary_guardian
      ? guardianCommandPayload({ ...input.secondary_guardian, guardian_type: 'secondary' })
      : null;
  }
  if (Object.prototype.hasOwnProperty.call(input, 'emergency_contacts')) {
    payload.emergency_contacts = input.emergency_contacts?.map(emergencyContactCommandPayload) ?? null;
  }
  return payload;
}
