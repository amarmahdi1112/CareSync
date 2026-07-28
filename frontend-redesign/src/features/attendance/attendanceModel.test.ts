import { describe, expect, it } from 'vitest';
import { attendanceCounts, attendancePresentation, attendanceState, validateCorrection } from './attendanceModel';
import type { AttendanceDayRecord, AttendanceRosterRow } from './attendanceApi';

const row = (attendance_day: AttendanceRosterRow['attendance_day']): AttendanceRosterRow => ({
  child_id: 'child', child_name: 'Test Child', profile_photo_url: null, enrollment_id: 'enrollment', room_id: null, room_name: null, program_name: null, attendance_day,
});

describe('attendance model', () => {
  it('distinguishes pending, on-site, completed, and absent rows', () => {
    const base: Omit<AttendanceDayRecord, 'status' | 'intervals'> = { id: 'day', organization_id: 'org', facility_id: 'facility', child_id: 'child', enrollment_id: 'enrollment', service_date: '2026-07-14', absence_reason: null, notes: null, version: 1, child_name: 'Test Child', events: [], created_at: '', updated_at: '' };
    const rows = [
      row(null),
      row({ ...base, status: 'present', intervals: [{ id: 'one', sequence: 1, checked_in_at: '2026-07-14T08:00:00Z', checked_out_at: null }] }),
      row({ ...base, status: 'present', intervals: [{ id: 'two', sequence: 1, checked_in_at: '2026-07-14T08:00:00Z', checked_out_at: '2026-07-14T16:00:00Z' }] }),
      row({ ...base, status: 'absent', absence_reason: 'Sick', intervals: [] }),
    ];
    expect(rows.map(attendanceState)).toEqual(['pending', 'on-site', 'completed', 'absent']);
    expect(attendanceCounts(rows)).toEqual({ enrolled: 4, pending: 1, onSite: 1, completed: 1, absent: 1 });
  });

  it('requires a reason and chronological correction', () => {
    expect(validateCorrection('2026-07-14T10:00', '2026-07-14T09:00', 'fix')).toHaveLength(2);
  });

  it('presents a completed interval as checked out and an open interval with check out as its primary action', () => {
    expect(attendancePresentation('completed')).toMatchObject({
      label: 'Checked out',
      primaryAction: 'check-in-again',
      secondaryAction: null,
    });
    expect(attendancePresentation('on-site')).toEqual({
      label: 'On site',
      primaryAction: 'check-out',
      primaryLabel: 'Check out',
      secondaryAction: null,
      secondaryLabel: null,
    });
  });

  it('keeps a true no-show distinct from check-out and makes recording it secondary', () => {
    expect(attendancePresentation('absent')).toEqual({
      label: 'No-show',
      primaryAction: null,
      primaryLabel: null,
      secondaryAction: null,
      secondaryLabel: null,
    });
    expect(attendancePresentation('pending')).toMatchObject({
      label: 'Not recorded',
      primaryAction: 'check-in',
      primaryLabel: 'Check in',
      secondaryAction: 'mark-no-show',
      secondaryLabel: 'Mark no-show',
    });
  });
});
