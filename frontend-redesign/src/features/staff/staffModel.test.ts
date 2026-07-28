import { describe, expect, it } from 'vitest';
import { absoluteHandoffUrl, oneTimeTokenFromHash, passwordErrors, roomFacilityIds, validateStaffDraft } from './staffModel';
import type { StaffRole, StaffRoom } from './types';

const educator: StaffRole = { id: 'educator-role', key: 'educator', name: 'Educator', description: null, permissions: [] };
const rooms: StaffRoom[] = [
  { id: 'room-a', organization_id: 'organization', facility_id: 'facility-a', name: 'Infants', is_active: true },
  { id: 'room-b', organization_id: 'organization', facility_id: 'facility-a', name: 'Toddlers', is_active: true },
  { id: 'room-inactive', organization_id: 'organization', facility_id: 'facility-b', name: 'Closed', is_active: false },
];

describe('staff access model', () => {
  it('derives unique facility scope from selected rooms', () => {
    expect(roomFacilityIds(['room-a', 'room-b'], rooms)).toEqual(['facility-a']);
  });

  it('requires educator room scope and rejects stale rooms or mismatched facilities', () => {
    const base = { email: 'educator@example.com', first_name: 'Ada', last_name: 'Care', role_id: educator.id, assigned_facility_ids: [] as string[], assigned_room_ids: [] as string[] };
    expect(validateStaffDraft(base, educator, rooms)).toContain('Assign at least one active room to an educator.');
    expect(validateStaffDraft({ ...base, assigned_facility_ids: ['facility-a'], assigned_room_ids: ['room-inactive'] }, educator, rooms)).toContain('One or more selected rooms are unavailable.');
    expect(validateStaffDraft({ ...base, assigned_facility_ids: [], assigned_room_ids: ['room-a'] }, educator, rooms)).toContain('Room and facility assignments do not agree.');
    expect(validateStaffDraft({ ...base, assigned_facility_ids: ['facility-a'], assigned_room_ids: ['room-a'] }, educator, rooms)).toEqual([]);
  });

  it('enforces twelve-character activation and reset passwords', () => {
    expect(passwordErrors('short', 'short')).toContain('Password must contain at least 12 characters.');
    expect(passwordErrors('long-enough-password', 'different-password')).toContain('Password confirmation does not match.');
    expect(passwordErrors('long-enough-password', 'long-enough-password')).toEqual([]);
  });

  it('keeps one-time handoff tokens in fragments and rejects unsafe links', () => {
    expect(oneTimeTokenFromHash('#token=secret')).toBe('secret');
    expect(oneTimeTokenFromHash('#token=first&token=second')).toBe('');
    expect(absoluteHandoffUrl('/activate-staff#token=secret', 'http://127.0.0.1:5174')).toBe('http://127.0.0.1:5174/activate-staff#token=secret');
    expect(() => absoluteHandoffUrl('/activate-staff?token=secret', 'http://127.0.0.1:5174')).toThrow(/unsafe query string/);
    expect(() => absoluteHandoffUrl('https://malicious.example/reset-password#token=secret', 'http://127.0.0.1:5174')).toThrow(/outside this CareSync origin/);
  });
});
