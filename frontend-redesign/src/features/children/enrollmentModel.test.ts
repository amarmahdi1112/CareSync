import { describe, expect, it } from 'vitest';
import type { ApiChildEnrollment, EnrollmentFacilityOption, EnrollmentPlacementOptions } from './childrenApi';
import {
  currentChildEnrollment,
  enrollmentCreateInput,
  enrollmentPlacementApprovalInput,
  facilityIsoDate,
  placementChanged,
  roomsForProgram,
  validateEnrollmentCreate,
  validateEnrollmentEnd,
  validateEnrollmentPlacement,
  type EnrollmentEditorValues,
} from './enrollmentModel';

const enrollment = (overrides: Partial<ApiChildEnrollment> = {}): ApiChildEnrollment => ({
  id: 'enrollment-1', organization_id: 'org-a', child_id: 'child-1', facility_id: 'facility-1',
  program_id: null, room_id: null, start_date: '2026-07-01', end_date: null, status: 'pending',
  is_active: false, placement_effective_date: null, version: 1, replayed: false, ...overrides,
});

const facilities: EnrollmentFacilityOption[] = [{ id: 'facility-1', organization_id: 'org-a', name: 'North Centre', status: 'active', timezone: 'America/Edmonton' }];
const options: EnrollmentPlacementOptions = {
  programs: [{ id: 'program-1', organization_id: 'org-a', facility_id: 'facility-1', name: 'Preschool', program_type: 'daycare', is_active: true }],
  rooms: [{ id: 'room-1', organization_id: 'org-a', facility_id: 'facility-1', program_id: 'program-1', name: 'Starlight', age_group: 'Preschool', capacity: 12, occupancy: 3, is_active: true }],
};
const values = (overrides: Partial<EnrollmentEditorValues> = {}): EnrollmentEditorValues => ({
  facilityId: 'facility-1', programId: 'program-1', roomId: 'room-1',
  startDate: '2026-07-01', effectiveDate: '2026-07-01', ...overrides,
});

describe('enrollment editor model', () => {
  it('selects an open active record before paused or pending records', () => {
    const ended = enrollment({ id: 'ended', status: 'ended', end_date: '2026-06-30' });
    const paused = enrollment({ id: 'paused', status: 'paused' });
    const live = enrollment({ id: 'live', status: 'active', is_active: true });
    expect(currentChildEnrollment([ended, paused, live], '2026-07-14')?.id).toBe('live');
    expect(currentChildEnrollment([ended, paused], '2026-07-14')?.id).toBe('paused');
    expect(currentChildEnrollment([ended], '2026-07-14')).toBeNull();
  });

  it('creates only a pending enrollment shell', () => {
    expect(validateEnrollmentCreate(values(), facilities)).toEqual({});
    expect(enrollmentCreateInput(values())).toEqual({ facility_id: 'facility-1', start_date: '2026-07-01' });
    expect(validateEnrollmentCreate(values({ facilityId: 'facility-other' }), facilities).facilityId).toContain('organization');
  });

  it('validates and emits an initial room approval with an effective date', () => {
    const pending = enrollment();
    expect(validateEnrollmentPlacement(values(), pending, facilities, options)).toEqual({});
    expect(enrollmentPlacementApprovalInput(values())).toEqual({ room_id: 'room-1', effective_date: '2026-07-01' });
    expect(validateEnrollmentPlacement(values({ effectiveDate: '2026-06-30' }), pending, facilities, options).effectiveDate).toContain('before');
    expect(validateEnrollmentPlacement(values({ roomId: 'other' }), pending, facilities, options).roomId).toContain('facility');
  });

  it('detects placement changes without inventing an unassignment command', () => {
    const assigned = enrollment({ program_id: 'program-1', room_id: 'room-1', placement_effective_date: '2026-07-01', status: 'active', is_active: true });
    expect(placementChanged(values(), assigned)).toBe(false);
    expect(placementChanged(values({ effectiveDate: '2026-07-02' }), assigned)).toBe(true);
  });

  it('allows ending only now or as of a valid past date', () => {
    expect(validateEnrollmentEnd('2026-06-30', enrollment(), '2026-07-17').endDate).toContain('before');
    expect(validateEnrollmentEnd('2026-07-18', enrollment(), '2026-07-17').endDate).toContain('Future departures');
    expect(validateEnrollmentEnd('2026-07-17', enrollment(), '2026-07-17')).toEqual({});
  });

  it('derives the business date from the facility timezone near midnight', () => {
    const instant = new Date('2026-07-18T05:30:00.000Z');
    expect(facilityIsoDate('America/Edmonton', instant)).toBe('2026-07-17');
    expect(facilityIsoDate('Asia/Tokyo', instant)).toBe('2026-07-18');
  });

  it('filters rooms strictly to the selected program', () => {
    const shared = { ...options.rooms[0], id: 'shared-room', program_id: null };
    const other = { ...options.rooms[0], id: 'other-room', program_id: 'program-2' };
    expect(roomsForProgram([options.rooms[0], shared, other], 'program-1').map((room) => room.id)).toEqual(['room-1']);
  });
});
