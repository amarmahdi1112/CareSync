import { describe, expect, it } from 'vitest';
import type { CareRecord } from './careApi';
import {
  activeRecords,
  canCorrectCareRecord,
  canPresentCurrentSafety,
  careActionsForRoom,
  careRecordDetail,
  facilityDateTimeInputValue,
  facilityDateTimeToIso,
  openSleep,
  resolveFacilityDateTime,
} from './careModel';

const record = (patch: Partial<CareRecord> = {}): CareRecord => ({
  id: 'record-1', organization_id: 'org-1', facility_id: 'facility-1', room_id: 'room-1', child_id: 'child-1',
  enrollment_id: 'enrollment-1', attendance_day_id: 'day-1', service_date: '2026-07-15', care_type: 'sleep',
  occurred_at: '2026-07-15T16:00:00Z', ended_at: null, payload: {}, note: null, created_by_user_id: 'educator-1',
  created_by_name: 'Amina Educator', version: 1, voided_at: null, voided_by_user_id: null, void_reason: null,
  last_event_type: 'recorded', was_corrected: false, created_at: '2026-07-15T16:00:01Z', updated_at: '2026-07-15T16:00:01Z',
  ...patch,
});

describe('daily care presentation and facility-time rules', () => {
  it('adapts care actions to OSC and early-learning age lanes', () => {
    expect(careActionsForRoom('out_of_school_care', 'School age').map((item) => item.type)).toEqual(['feeding', 'mood', 'activity']);
    expect(careActionsForRoom('daycare', 'Infant').map((item) => item.type)).toEqual(['feeding', 'diaper', 'sleep', 'mood', 'activity']);
    expect(careActionsForRoom('daycare', 'Toddler').map((item) => item.type)).toContain('toilet');
    expect(careActionsForRoom('daycare', 'Preschool').map((item) => item.type)).not.toContain('diaper');
  });

  it('finds only active open sleep and keeps newest active records first', () => {
    const open = record();
    const finished = record({ id: 'record-2', occurred_at: '2026-07-15T15:00:00Z', ended_at: '2026-07-15T15:30:00Z' });
    const voided = record({ id: 'record-3', occurred_at: '2026-07-15T17:00:00Z', voided_at: '2026-07-15T17:01:00Z', voided_by_user_id: 'admin-1', void_reason: 'Duplicate', last_event_type: 'voided' });
    expect(activeRecords([finished, voided, open]).map((item) => item.id)).toEqual(['record-1', 'record-2']);
    expect(openSleep([finished, voided, open])?.id).toBe('record-1');
    expect(careRecordDetail(finished)).toBe('30 min');
  });

  it('allows own-record correction only for its creator unless broad correction is granted', () => {
    expect(canCorrectCareRecord(record(), 'educator-1', false, true)).toBe(true);
    expect(canCorrectCareRecord(record(), 'educator-2', false, true)).toBe(false);
    expect(canCorrectCareRecord(record(), 'administrator', true, false)).toBe(true);
    expect(canCorrectCareRecord(record({ voided_at: '2026-07-15T17:00:00Z', voided_by_user_id: 'admin', void_reason: 'Duplicate' }), 'administrator', true, true)).toBe(false);
  });

  it('never presents current safety as historical safety', () => {
    expect(canPresentCurrentSafety('2026-07-15', '2026-07-15')).toBe(true);
    expect(canPresentCurrentSafety('2026-06-15', '2026-07-15')).toBe(false);
  });

  it('converts facility wall time independently of the browser timezone', () => {
    expect(facilityDateTimeInputValue('2026-07-15T18:30:00Z', 'America/Edmonton')).toBe('2026-07-15T12:30');
    expect(facilityDateTimeToIso('2026-07-15T12:30', 'America/Edmonton')).toBe('2026-07-15T18:30:00.000Z');
  });

  it('rejects skipped and ambiguous Edmonton DST wall times instead of guessing', () => {
    expect(() => facilityDateTimeToIso('2026-03-08T02:30', 'America/Edmonton')).toThrow('does not exist');
    expect(() => facilityDateTimeToIso('2026-11-01T01:30', 'America/Edmonton')).toThrow('occurs twice');
  });

  it('preserves an already-recorded ambiguous instant when the wall value is unchanged', () => {
    const original = '2026-11-01T07:30:00Z';
    const input = facilityDateTimeInputValue(original, 'America/Edmonton');
    expect(input).toBe('2026-11-01T01:30');
    expect(resolveFacilityDateTime(input, original, 'America/Edmonton')).toBe(original);
  });
});
