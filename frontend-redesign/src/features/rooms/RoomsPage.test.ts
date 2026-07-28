import { describe, expect, it } from 'vitest';
import { resolvePlacementDeepLink } from './RoomsPage';
import type { RoomRoster, RoomWorkspace } from './roomsApi';

const workspace: RoomWorkspace = {
  facilities: [{
    id: 'facility-1', organization_id: 'org-1', name: 'North', license_number: null,
    licensed_capacity: 40, city: 'Edmonton', province: 'AB', timezone: 'America/Edmonton', status: 'active',
  }],
  programs: [],
  rooms: [],
};

const roster: RoomRoster = {
  facility_id: 'facility-1',
  facility_date: '2026-07-17',
  rooms: [],
  unassigned_children: [{
    child_id: 'child-1', enrollment_id: 'enrollment-1', family_id: 'family-1', family_name: 'Noor',
    first_name: 'Amina', middle_name: null, last_name: 'Noor', date_of_birth: '2022-04-12', age_group: 'Preschool',
    child_is_active: true, profile_photo_url: null, facility_id: 'facility-1', program_id: null, room_id: null,
    enrollment_status: 'pending', enrollment_version: 1, start_date: '2026-07-01', placement_effective_date: null, end_date: null,
  }],
};

describe('placement readiness deep-link resolution', () => {
  it('accepts only the exact unassigned enrollment inside the loaded facility', () => {
    expect(resolvePlacementDeepLink('facility-1', 'enrollment-1', workspace, roster)).toEqual({
      state: 'valid', facilityId: 'facility-1', enrollmentId: 'enrollment-1',
    });
  });

  it('waits for the requested facility roster, then rejects stale or cross-boundary IDs', () => {
    expect(resolvePlacementDeepLink('facility-1', 'enrollment-1', workspace, null)).toEqual({ state: 'wait' });
    expect(resolvePlacementDeepLink('facility-other', 'enrollment-1', workspace, roster)).toMatchObject({ state: 'invalid' });
    expect(resolvePlacementDeepLink('facility-1', 'enrollment-stale', workspace, roster)).toMatchObject({ state: 'invalid' });
  });
});
