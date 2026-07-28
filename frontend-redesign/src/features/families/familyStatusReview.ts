import type { FamilyChildRecord, FamilyDetailRecord } from './types';

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9:_-]{0,254}$/;

export type FamilyStatusReviewFocus =
  | { status: 'none'; child: null; enrollmentId: null }
  | { status: 'invalid'; child: null; enrollmentId: null }
  | { status: 'stale'; child: null; enrollmentId: string }
  | { status: 'available'; child: FamilyChildRecord; enrollmentId: string };

export type FamilyIntakeStatusFocus = 'none' | 'invalid' | 'stale' | 'available';

/** Resolve the deliberately narrow admissions link after canonical profile reload. */
export function resolveFamilyIntakeStatusFocus(
  searchParams: URLSearchParams,
  family: FamilyDetailRecord,
): FamilyIntakeStatusFocus {
  if (!searchParams.has('focus')) return 'none';
  const readinessKeys = new Set(['focus', 'child_id', 'enrollment_id']);
  if (
    [...searchParams.keys()].length === 3
    && [...searchParams.keys()].every((key) => readinessKeys.has(key))
    && searchParams.getAll('focus').length === 1
    && searchParams.get('focus') === 'family-status'
    && searchParams.getAll('child_id').length === 1
    && searchParams.getAll('enrollment_id').length === 1
    && SAFE_ID.test(searchParams.get('child_id') || '')
    && SAFE_ID.test(searchParams.get('enrollment_id') || '')
  ) return 'none';
  if (
    [...searchParams.keys()].length !== 1
    || searchParams.getAll('focus').length !== 1
    || searchParams.get('focus') !== 'family-status'
  ) return 'invalid';
  return family.status === 'active' ? 'stale' : 'available';
}

/**
 * Resolve only the exact server-authored readiness focus. The family profile is
 * canonical and organization-scoped, so a child that is no longer linked is
 * reported as stale instead of being displayed as the review subject.
 */
export function resolveFamilyStatusReview(
  searchParams: URLSearchParams,
  family: FamilyDetailRecord,
): FamilyStatusReviewFocus {
  if (!searchParams.has('focus')) return { status: 'none', child: null, enrollmentId: null };
  const allowed = new Set(['focus', 'child_id', 'enrollment_id']);
  if (
    [...searchParams.keys()].some((key) => !allowed.has(key))
    || [...searchParams.keys()].length !== 3
    || searchParams.getAll('focus').length !== 1
    || searchParams.get('focus') !== 'family-status'
    || searchParams.getAll('child_id').length !== 1
    || searchParams.getAll('enrollment_id').length !== 1
  ) return { status: 'invalid', child: null, enrollmentId: null };

  const childId = searchParams.get('child_id') || '';
  const enrollmentId = searchParams.get('enrollment_id') || '';
  if (!SAFE_ID.test(childId) || !SAFE_ID.test(enrollmentId)) {
    return { status: 'invalid', child: null, enrollmentId: null };
  }
  const child = family.children.find((item) => item.id === childId) || null;
  return child
    ? { status: 'available', child, enrollmentId }
    : { status: 'stale', child: null, enrollmentId };
}

export function familyStatusReviewChildName(child: FamilyChildRecord): string {
  return [child.first_name, child.middle_name, child.last_name].filter(Boolean).join(' ');
}
