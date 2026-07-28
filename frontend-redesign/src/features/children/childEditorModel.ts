import type { ApiChildDetails, ChildMutationInput } from './childrenApi';

export type ImmunizationValue = 'unknown' | 'yes' | 'no';

export interface ChildEditorValues {
  familyId: string;
  firstName: string;
  middleName: string;
  lastName: string;
  dateOfBirth: string;
  gender: string;
  ageGroup: string;
  isActive: boolean;
  healthCareNumber: string;
  allergies: string;
  medicalConditions: string;
  medications: string;
  immunization: ImmunizationValue;
  doctorName: string;
  doctorPhone: string;
}

export type ChildEditorErrors = Partial<Record<keyof ChildEditorValues, string>>;

export const EMPTY_CHILD_EDITOR_VALUES: ChildEditorValues = {
  familyId: '',
  firstName: '',
  middleName: '',
  lastName: '',
  dateOfBirth: '',
  gender: '',
  ageGroup: '',
  isActive: true,
  healthCareNumber: '',
  allergies: '',
  medicalConditions: '',
  medications: '',
  immunization: 'unknown',
  doctorName: '',
  doctorPhone: '',
};

export const CHILD_EDITOR_FIELD_LIMITS = {
  firstName: 100,
  middleName: 100,
  lastName: 100,
  gender: 20,
  healthCareNumber: 100,
  doctorName: 255,
  doctorPhone: 30,
} as const satisfies Partial<Record<keyof ChildEditorValues, number>>;

/** System-managed age band using the same completed-month thresholds as the backend. */
export function ageGroupFromDateOfBirth(dateOfBirth: string, asOf = new Date()): string {
  if (!validIsoDate(dateOfBirth)) return '';
  const [year, month, day] = dateOfBirth.split('-').map(Number);
  let completedMonths = (asOf.getFullYear() - year) * 12 + (asOf.getMonth() + 1 - month);
  if (asOf.getDate() < day) completedMonths -= 1;
  if (completedMonths < 0) return '';
  if (completedMonths <= 19) return 'Infant';
  if (completedMonths <= 36) return 'Toddler';
  if (completedMonths <= 77) return 'Preschool';
  return 'School-Age';
}

function validIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function todayIso(now: Date): string {
  return [
    now.getFullYear().toString().padStart(4, '0'),
    (now.getMonth() + 1).toString().padStart(2, '0'),
    now.getDate().toString().padStart(2, '0'),
  ].join('-');
}

export function validateChildEditor(
  values: ChildEditorValues,
  allowedFamilyIds: ReadonlySet<string>,
  now = new Date(),
): ChildEditorErrors {
  const errors: ChildEditorErrors = {};
  if (!values.familyId) errors.familyId = 'Select the child’s family.';
  else if (!allowedFamilyIds.has(values.familyId)) errors.familyId = 'Select a family from this organization.';

  if (!values.firstName.trim()) errors.firstName = 'Enter the first name.';
  if (!values.lastName.trim()) errors.lastName = 'Enter the last name.';

  (Object.entries(CHILD_EDITOR_FIELD_LIMITS) as Array<[keyof ChildEditorValues, number]>).forEach(([field, maximum]) => {
    const value = values[field];
    if (typeof value === 'string' && value.trim().length > maximum) {
      errors[field] = `Use ${maximum} characters or fewer.`;
    }
  });

  if (!values.dateOfBirth) errors.dateOfBirth = 'Enter the date of birth.';
  else if (!validIsoDate(values.dateOfBirth)) errors.dateOfBirth = 'Enter a valid date of birth.';
  else if (values.dateOfBirth > todayIso(now)) errors.dateOfBirth = 'Date of birth cannot be in the future.';

  return errors;
}

export function childEditorValuesFromDetails(child: ApiChildDetails): ChildEditorValues {
  return {
    familyId: child.family_id,
    firstName: child.first_name,
    middleName: child.middle_name || '',
    lastName: child.last_name,
    dateOfBirth: child.date_of_birth.slice(0, 10),
    gender: child.gender || '',
    ageGroup: child.age_group || '',
    isActive: child.is_active,
    healthCareNumber: child.health_care_number || '',
    allergies: child.allergies || '',
    medicalConditions: child.medical_conditions || '',
    medications: child.medications || '',
    immunization: child.immunization_up_to_date === true
      ? 'yes'
      : child.immunization_up_to_date === false
        ? 'no'
        : 'unknown',
    doctorName: child.doctor_name || '',
    doctorPhone: child.doctor_phone || '',
  };
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export function childMutationInput(values: ChildEditorValues, asOf = new Date()): ChildMutationInput {
  return {
    family_id: values.familyId,
    first_name: values.firstName.trim(),
    middle_name: optional(values.middleName),
    last_name: values.lastName.trim(),
    date_of_birth: values.dateOfBirth,
    gender: optional(values.gender),
    age_group: optional(ageGroupFromDateOfBirth(values.dateOfBirth, asOf)),
    is_active: values.isActive,
    health_care_number: optional(values.healthCareNumber),
    allergies: optional(values.allergies),
    medical_conditions: optional(values.medicalConditions),
    medications: optional(values.medications),
    immunization_up_to_date: values.immunization === 'unknown' ? null : values.immunization === 'yes',
    doctor_name: optional(values.doctorName),
    doctor_phone: optional(values.doctorPhone),
  };
}
