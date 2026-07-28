import type {
  ApiChildDirectoryEnrollment,
  ApiChildDirectoryRecord,
  ApiChildProfile,
  ChildDirectoryCareLane,
  ChildDirectoryCounts,
  ChildDirectoryPlacementState,
} from './childrenApi';

export type CareLane = 'Daycare' | 'OSC' | 'Unassigned' | 'Needs review';
export type PlacementLabel = 'Current' | 'Reserved' | 'Unassigned' | 'Needs review';

export interface ChildListItem {
  id: string;
  familyId: string;
  familyName: string;
  firstName: string;
  middleName: string | null;
  lastName: string;
  fullName: string;
  initials: string;
  dateOfBirth: string;
  enrollmentDate: string | null;
  openEnrollment: ApiChildDirectoryEnrollment | null;
  ageGroup: string;
  careLane: CareLane;
  placementState: ChildDirectoryPlacementState;
  placementLabel: PlacementLabel;
  status: 'active' | 'inactive';
  profilePhotoUrl: string | null;
  profilePhotoUpdatedAt: string | null;
}

const OSC_LABELS = new Set(['osc', 'schoolage', 'outofschool', 'outofschoolcare']);

function normalizedLabel(value: string | null): string {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function displayAgeGroup(value: string | null): string {
  const normalized = normalizedLabel(value);
  if (OSC_LABELS.has(normalized)) return 'School-Age';
  if (normalized === 'infant') return 'Infant';
  if (normalized === 'toddler') return 'Toddler';
  if (normalized === 'preschool') return 'Preschool';
  if (normalized === 'daycare' || normalized === 'fulltime') return 'Daycare';
  return value?.trim() || 'Not recorded';
}

function initials(firstName: string, lastName: string): string {
  return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
}

export function careLaneLabel(value: ChildDirectoryCareLane): CareLane {
  if (value === 'daycare') return 'Daycare';
  if (value === 'out_of_school_care') return 'OSC';
  if (value === 'unassigned') return 'Unassigned';
  return 'Needs review';
}

export function placementLabel(value: ChildDirectoryPlacementState): PlacementLabel {
  if (value === 'current') return 'Current';
  if (value === 'reserved') return 'Reserved';
  if (value === 'unassigned') return 'Unassigned';
  return 'Needs review';
}

export function toChildListItem(record: ApiChildDirectoryRecord): ChildListItem {
  const nameParts = [record.first_name, record.middle_name, record.last_name].filter(Boolean);
  const placementState = record.open_enrollment?.placement_state || 'unassigned';
  return {
    id: record.id,
    familyId: record.family_id,
    familyName: record.family_name,
    firstName: record.first_name,
    middleName: record.middle_name,
    lastName: record.last_name,
    fullName: nameParts.join(' '),
    initials: initials(record.first_name, record.last_name),
    dateOfBirth: record.date_of_birth,
    enrollmentDate: record.open_enrollment?.start_date || null,
    openEnrollment: record.open_enrollment,
    ageGroup: displayAgeGroup(record.age_group),
    careLane: careLaneLabel(record.care_lane),
    placementState,
    placementLabel: placementLabel(placementState),
    status: record.is_active ? 'active' : 'inactive',
    profilePhotoUrl: record.profile_photo_url,
    profilePhotoUpdatedAt: record.profile_photo_updated_at,
  };
}

/** Build editor identity from a canonical profile without pretending it is a directory page. */
export function childListIdentityFromProfile(profile: ApiChildProfile): ChildListItem {
  const enrollment = profile.current_enrollment;
  const programType = enrollment?.program_type === 'daycare' || enrollment?.program_type === 'out_of_school_care'
    ? enrollment.program_type
    : null;
  const hasPlacement = Boolean(enrollment?.program_id && enrollment.room_id && enrollment.placement_effective_date && programType);
  const careLane: ChildDirectoryCareLane = !enrollment || (!enrollment.program_id && !enrollment.room_id)
    ? 'unassigned'
    : hasPlacement && programType
      ? programType
      : 'needs_review';
  const placementState: ChildDirectoryPlacementState = !enrollment || (!enrollment.program_id && !enrollment.room_id)
    ? 'unassigned'
    : hasPlacement
      ? 'current'
      : 'needs_review';
  return {
    id: profile.id,
    familyId: profile.family_id,
    familyName: profile.family.name,
    firstName: profile.first_name,
    middleName: profile.middle_name,
    lastName: profile.last_name,
    fullName: [profile.first_name, profile.middle_name, profile.last_name].filter(Boolean).join(' '),
    initials: initials(profile.first_name, profile.last_name),
    dateOfBirth: profile.date_of_birth,
    enrollmentDate: enrollment?.start_date || null,
    openEnrollment: null,
    ageGroup: displayAgeGroup(profile.age_group),
    careLane: careLaneLabel(careLane),
    placementState,
    placementLabel: placementLabel(placementState),
    status: profile.is_active ? 'active' : 'inactive',
    profilePhotoUrl: profile.profile_photo_url,
    profilePhotoUpdatedAt: profile.profile_photo_updated_at,
  };
}

export function formatRosterDate(value: string | null): string {
  if (!value) return 'Not enrolled';
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return 'Not recorded';
  return parsed.toLocaleDateString('en-CA', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function rosterSummary(counts: ChildDirectoryCounts) {
  return {
    total: counts.total,
    active: counts.active,
    inactive: counts.inactive,
    daycare: counts.daycare,
    osc: counts.out_of_school_care,
    unassigned: counts.unassigned,
    reserved: counts.reserved,
    needsReview: counts.needs_review,
  };
}
