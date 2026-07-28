import { describe, expect, it } from 'vitest';
import { familyStatusReviewChildName, resolveFamilyIntakeStatusFocus, resolveFamilyStatusReview } from './familyStatusReview';
import type { FamilyDetailRecord } from './types';

const family = {
  id: 'family-1', organization_id: 'org-1', name: 'Adem Family', status: 'pending',
  file_number: null, created_at: '2026-07-01T12:00:00Z', updated_at: '2026-07-01T12:00:00Z', version: 1, replayed: false,
  children: [{
    id: 'child-1', organization_id: 'org-1', family_id: 'family-1', first_name: 'Adel', middle_name: 'Kumere', last_name: 'Asefa',
    date_of_birth: '2022-07-18', gender: null, age_group: null, is_active: true,
    created_at: '2026-07-01T12:00:00Z', updated_at: '2026-07-01T12:00:00Z', version: 1, replayed: false,
  }],
  guardians: [], emergency_contacts: [], photo_consent: false, field_trip_consent: false,
  emergency_medical_consent: false, additional_notes: null,
} satisfies FamilyDetailRecord;

describe('family status readiness focus', () => {
  it('rechecks the narrow admissions family-status focus against the canonical family', () => {
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=family-status'), family)).toBe('available');
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=family-status'), { ...family, status: 'active' })).toBe('stale');
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=family-status'), { ...family, status: 'archived' })).toBe('available');
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=guardians'), family)).toBe('invalid');
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=family-status&child_id=child-1'), family)).toBe('invalid');
  });

  it('leaves the existing three-key readiness route to its exact resolver', () => {
    const params = new URLSearchParams('focus=family-status&child_id=child-1&enrollment_id=enrollment-1');
    expect(resolveFamilyIntakeStatusFocus(params, family)).toBe('none');
    expect(resolveFamilyStatusReview(params, family).status).toBe('available');
    expect(resolveFamilyIntakeStatusFocus(new URLSearchParams('focus=family-status&child_id=child-1&enrollment_id=enrollment-1&extra=1'), family)).toBe('invalid');
  });

  it('binds the exact server-authored child and enrollment to the canonical family', () => {
    const resolved = resolveFamilyStatusReview(
      new URLSearchParams('focus=family-status&child_id=child-1&enrollment_id=enrollment-1'),
      family,
    );
    expect(resolved).toMatchObject({ status: 'available', enrollmentId: 'enrollment-1' });
    if (resolved.status === 'available') expect(familyStatusReviewChildName(resolved.child)).toBe('Adel Kumere Asefa');
  });

  it('fails closed for extra, duplicate, invalid, or no-longer-linked targets', () => {
    expect(resolveFamilyStatusReview(new URLSearchParams(), family).status).toBe('none');
    expect(resolveFamilyStatusReview(new URLSearchParams('focus=family-status&child_id=child-1&enrollment_id=enrollment-1&status=active'), family).status).toBe('invalid');
    expect(resolveFamilyStatusReview(new URLSearchParams('focus=family-status&focus=family-status&child_id=child-1&enrollment_id=enrollment-1'), family).status).toBe('invalid');
    expect(resolveFamilyStatusReview(new URLSearchParams('focus=family-status&child_id=%2Fbad&enrollment_id=enrollment-1'), family).status).toBe('invalid');
    expect(resolveFamilyStatusReview(new URLSearchParams('focus=family-status&child_id=child-2&enrollment_id=enrollment-1'), family).status).toBe('stale');
  });
});
