import { describe, expect, it } from 'vitest';
import { careLaneLabel, placementLabel, rosterSummary, toChildListItem } from './childrenModel';
import type { ApiChildDirectoryRecord, ChildDirectoryCounts } from './childrenApi';

const record = (overrides: Partial<ApiChildDirectoryRecord> = {}): ApiChildDirectoryRecord => ({
  id: '22222222-2222-4222-8222-222222222222',
  organization_id: '11111111-1111-4111-8111-111111111111',
  family_id: '33333333-3333-4333-8333-333333333333',
  family_name: 'River Family',
  first_name: 'Amina',
  middle_name: null,
  last_name: 'Noor',
  date_of_birth: '2022-03-04',
  age_group: 'Preschool',
  is_active: true,
  version: 2,
  profile_photo_url: null,
  profile_photo_updated_at: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-15T00:00:00Z',
  care_lane: 'daycare',
  open_enrollment: {
    id: '44444444-4444-4444-8444-444444444444',
    organization_id: '11111111-1111-4111-8111-111111111111',
    child_id: '22222222-2222-4222-8222-222222222222',
    facility_id: '55555555-5555-4555-8555-555555555555',
    facility_name: 'North',
    program_id: '66666666-6666-4666-8666-666666666666',
    program_name: 'Daycare',
    program_type: 'daycare',
    room_id: '77777777-7777-4777-8777-777777777777',
    room_name: 'Starlight',
    placement_effective_date: '2026-08-01',
    start_date: '2026-08-01',
    end_date: null,
    status: 'active',
    version: 3,
    placement_state: 'reserved',
  },
  ...overrides,
});

describe('privacy-minimized children directory model', () => {
  it('uses server-authored care and placement states without local reclassification', () => {
    const item = toChildListItem(record());
    expect(item.careLane).toBe('Daycare');
    expect(item.placementLabel).toBe('Reserved');
    expect(item.enrollmentDate).toBe('2026-08-01');
    expect(item).not.toHaveProperty('enrollments');
    expect(item).not.toHaveProperty('healthCareNumber');
  });

  it('keeps current, reserved, unassigned, and review labels distinct', () => {
    expect(careLaneLabel('out_of_school_care')).toBe('OSC');
    expect(placementLabel('current')).toBe('Current');
    expect(placementLabel('reserved')).toBe('Reserved');
    expect(placementLabel('unassigned')).toBe('Unassigned');
    expect(placementLabel('needs_review')).toBe('Needs review');
    expect(toChildListItem(record({ care_lane: 'unassigned', open_enrollment: null })).placementLabel).toBe('Unassigned');
  });

  it('presents only the exact server count projection', () => {
    const counts: ChildDirectoryCounts = {
      total: 203, active: 199, inactive: 4, daycare: 100, out_of_school_care: 90,
      unassigned: 10, reserved: 12, needs_review: 3,
    };
    expect(rosterSummary(counts)).toEqual({
      total: 203, active: 199, inactive: 4, daycare: 100, osc: 90,
      unassigned: 10, reserved: 12, needsReview: 3,
    });
  });
});
