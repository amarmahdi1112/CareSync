import { describe, expect, it } from 'vitest';
import { CareApiError, parseCareRecord, parseCareRoomDay, parseChildSafetyCard } from './careApi';

const safety = {
  allergies: 'Peanut',
  medical_conditions: null,
  medication_awareness: 'Inhaler noted',
  emergency_medical_consent: true,
};

const record = {
  id: 'record-1',
  organization_id: 'org-1',
  facility_id: 'facility-1',
  room_id: 'room-1',
  child_id: 'child-1',
  enrollment_id: 'enrollment-1',
  attendance_day_id: 'day-1',
  service_date: '2026-07-15',
  care_type: 'feeding',
  occurred_at: '2026-07-15T16:00:00Z',
  ended_at: null,
  payload: { kind: 'meal', intake: 'most' },
  note: null,
  created_by_user_id: 'user-1',
  created_by_name: 'Amina Educator',
  version: 1,
  voided_at: null,
  voided_by_user_id: null,
  void_reason: null,
  last_event_type: 'recorded',
  was_corrected: false,
  created_at: '2026-07-15T16:00:01Z',
  updated_at: '2026-07-15T16:00:01Z',
};

const roomDay = {
  organization_id: 'org-1',
  facility_id: 'facility-1',
  facility_name: 'Main Centre',
  facility_timezone: 'America/Edmonton',
  room_id: 'room-1',
  room_name: 'Infant North',
  service_date: '2026-07-15',
  safety_as_of: '2026-07-15T18:00:00Z',
  generated_at: '2026-07-15T18:00:00Z',
  children: [{
    child_id: 'child-1', child_name: 'Noor Ali', profile_photo_url: '/api/v1/children/child-1/photo',
    enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', attendance_state: 'on_site', safety, records: [record],
  }],
};

const safetyCard = {
  child_id: 'child-1', child_name: 'Noor Ali', profile_photo_url: '/api/v1/children/child-1/photo',
  age_group: 'Infant', facility_id: 'facility-1', room_id: 'room-1', safety,
  contacts: [{ id: 'guardian-1', contact_type: 'primary_guardian', name: 'Sam Ali', relationship: 'Father', phone: '780-555-0100', authorized_pickup: true }],
};

describe('daily care fail-closed response adapters', () => {
  it('parses the complete room-day projection including safety provenance and event markers', () => {
    const result = parseCareRoomDay(roomDay);
    expect(result.safety_as_of).toBe('2026-07-15T18:00:00Z');
    expect(result.children[0].records[0]).toMatchObject({ last_event_type: 'recorded', was_corrected: false });
  });

  it('rejects records that cross the room-day child or attendance boundary', () => {
    expect(() => parseCareRoomDay({
      ...roomDay,
      children: [{ ...roomDay.children[0], records: [{ ...record, child_id: 'child-elsewhere' }] }],
    })).toThrow('crossed');
    expect(() => parseCareRoomDay({
      ...roomDay,
      children: [{ ...roomDay.children[0], attendance_day_id: null, attendance_state: 'on_site', records: [] }],
    })).toThrow('attendance evidence');
    expect(() => parseCareRoomDay({
      ...roomDay,
      children: [{ ...roomDay.children[0], records: [{ ...record, attendance_day_id: 'day-elsewhere' }] }],
    })).toThrow('crossed');
  });

  it('rejects undeclared safety, contact, and top-level identity fields', () => {
    expect(() => parseChildSafetyCard({ ...safetyCard, health_care_number: '123' })).toThrow(CareApiError);
    expect(() => parseChildSafetyCard({ ...safetyCard, safety: { ...safety, physician: 'Private doctor' } })).toThrow(CareApiError);
    expect(() => parseChildSafetyCard({ ...safetyCard, contacts: [{ ...safetyCard.contacts[0], email: 'private@example.com' }] })).toThrow(CareApiError);
    expect(() => parseCareRoomDay({ ...roomDay, children: [{ ...roomDay.children[0], family_notes: 'private' }] })).toThrow(CareApiError);
  });

  it('accepts only the exact protected photo path for the requested child', () => {
    expect(parseChildSafetyCard(safetyCard).profile_photo_url).toBe('/api/v1/children/child-1/photo');
    expect(() => parseChildSafetyCard({ ...safetyCard, profile_photo_url: '/api/v1/children/child-2/photo' })).toThrow('photo');
    expect(() => parseCareRoomDay({ ...roomDay, children: [{ ...roomDay.children[0], profile_photo_url: 'https://example.com/photo.jpg' }] })).toThrow('photo');
  });

  it('rejects care payloads that do not match their declared type or contain extras', () => {
    expect(() => parseCareRecord({ ...record, care_type: 'sleep', payload: { kind: 'meal' } })).toThrow(CareApiError);
    expect(() => parseCareRecord({ ...record, payload: { kind: 'meal', intake: 'most', calories: 400 } })).toThrow(CareApiError);
    expect(() => parseCareRecord({ ...record, care_type: 'feeding', payload: { kind: 'meal', intake: 'most', volume_ml: 120 } })).toThrow('non-bottle');
  });

  it('requires correction provenance and the backend event projection fields', () => {
    expect(() => parseCareRecord({ ...record, last_event_type: undefined })).toThrow(CareApiError);
    expect(() => parseCareRecord({ ...record, was_corrected: 'yes' })).toThrow(CareApiError);
    expect(parseCareRecord({ ...record, care_type: 'sleep', payload: {}, ended_at: '2026-07-15T17:00:00Z', last_event_type: 'auto_finished_at_checkout' }).last_event_type).toBe('auto_finished_at_checkout');
    expect(() => parseCareRecord({ ...record, last_event_type: 'corrected', was_corrected: false })).toThrow('correction evidence');
    expect(() => parseCareRecord({ ...record, care_type: 'sleep', payload: {}, last_event_type: 'auto_finished_at_checkout' })).toThrow('sleep completion evidence');
  });

  it('rejects invalid facility timezone identifiers at the response boundary', () => {
    expect(() => parseCareRoomDay({ ...roomDay, facility_timezone: 'Not/A_Timezone' })).toThrow('timezone');
  });
});
