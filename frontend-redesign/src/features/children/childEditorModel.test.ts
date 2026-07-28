import { describe, expect, it } from 'vitest';
import {
  EMPTY_CHILD_EDITOR_VALUES,
  CHILD_EDITOR_FIELD_LIMITS,
  ageGroupFromDateOfBirth,
  childMutationInput,
  validateChildEditor,
} from './childEditorModel';

describe('Basic child editor contract', () => {
  const valid = () => ({
    ...EMPTY_CHILD_EDITOR_VALUES,
    familyId: 'family-a',
    firstName: 'Amina',
    lastName: 'Noor',
    dateOfBirth: '2022-04-12',
  });

  it('rejects family identifiers outside the confirmed organization options', () => {
    expect(validateChildEditor(valid(), new Set(['family-b']), new Date('2026-07-14')).familyId)
      .toContain('this organization');
  });

  it('emits only Basic identity and health fields', () => {
    const payload = childMutationInput(valid(), new Date('2026-07-14'));
    expect(payload).toMatchObject({
      family_id: 'family-a',
      first_name: 'Amina',
      last_name: 'Noor',
      date_of_birth: '2022-04-12',
      is_active: true,
      age_group: 'Preschool',
    });
    expect(payload).not.toHaveProperty('need_invoice');
    expect(payload).not.toHaveProperty('fscd_file_number');
    expect(payload).not.toHaveProperty('schedule_start_time');
    expect(payload).not.toHaveProperty('schedule_end_time');
    expect(payload).not.toHaveProperty('start_date');
  });

  it('derives the system age band from date of birth instead of a typed legacy label', () => {
    expect(ageGroupFromDateOfBirth('2024-12-14', new Date('2026-07-14'))).toBe('Infant');
    expect(ageGroupFromDateOfBirth('2023-07-14', new Date('2026-07-14'))).toBe('Toddler');
    expect(ageGroupFromDateOfBirth('2020-02-14', new Date('2026-07-14'))).toBe('Preschool');
    expect(ageGroupFromDateOfBirth('2019-01-14', new Date('2026-07-14'))).toBe('School-Age');
    expect(childMutationInput({ ...valid(), ageGroup: 'Custom legacy band' }, new Date('2026-07-14')).age_group).toBe('Preschool');
  });

  it('matches the backend name and doctor-phone limits before submission', () => {
    const namesTooLong = validateChildEditor({
      ...valid(),
      firstName: 'a'.repeat(CHILD_EDITOR_FIELD_LIMITS.firstName + 1),
      middleName: 'b'.repeat(CHILD_EDITOR_FIELD_LIMITS.middleName + 1),
      lastName: 'c'.repeat(CHILD_EDITOR_FIELD_LIMITS.lastName + 1),
      doctorPhone: '1'.repeat(CHILD_EDITOR_FIELD_LIMITS.doctorPhone + 1),
    }, new Set(['family-a']), new Date('2026-07-14'));

    expect(CHILD_EDITOR_FIELD_LIMITS).toMatchObject({
      firstName: 100,
      middleName: 100,
      lastName: 100,
      doctorPhone: 30,
    });
    expect(namesTooLong).toMatchObject({
      firstName: 'Use 100 characters or fewer.',
      middleName: 'Use 100 characters or fewer.',
      lastName: 'Use 100 characters or fewer.',
      doctorPhone: 'Use 30 characters or fewer.',
    });
  });
});
