import { describe, expect, it } from 'vitest';
import type { AttendanceRosterRow } from '../features/attendance/attendanceApi';
import { loadAttendanceSummary, serviceDateValue } from './useCommandData';

function rosterRow(childId: string): AttendanceRosterRow {
  return {
    child_id: childId,
    child_name: `Child ${childId}`,
    profile_photo_url: null,
    enrollment_id: `enrollment-${childId}`,
    room_id: null,
    room_name: null,
    program_name: null,
    attendance_day: null,
  };
}

describe('dashboard service date', () => {
  it('uses the organization timezone instead of the browser calendar', () => {
    const instant = new Date('2026-07-15T05:30:00.000Z');
    expect(serviceDateValue(instant, 'America/Edmonton')).toBe('2026-07-14');
    expect(serviceDateValue(instant, 'America/Toronto')).toBe('2026-07-15');
  });

  it('tracks daylight-saving boundaries through Intl timezone rules', () => {
    expect(serviceDateValue(new Date('2026-03-08T06:30:00.000Z'), 'America/Edmonton')).toBe('2026-03-07');
    expect(serviceDateValue(new Date('2026-03-08T08:30:00.000Z'), 'America/Edmonton')).toBe('2026-03-08');
  });

  it('preserves successful facility totals when one realtime roster refresh fails', async () => {
    const result = await loadAttendanceSummary(
      '2026-07-16',
      ['north', 'south'],
      async (facilityId) => {
        if (facilityId === 'south') throw new Error('south unavailable');
        return [rosterRow('one'), rosterRow('two')];
      },
      () => '2026-07-16T18:00:00.000Z',
    );

    expect(result.summary).toMatchObject({
      serviceDate: '2026-07-16',
      refreshedAt: '2026-07-16T18:00:00.000Z',
      facilityCount: 2,
      facilityFailures: 1,
      enrolled: 2,
      pending: 2,
    });
    expect(result.message).toBe('1 of 2 facility rosters are current; 1 unavailable.');
  });

  it('fails closed when no configured facility roster can refresh', async () => {
    await expect(loadAttendanceSummary(
      '2026-07-16',
      ['north', 'south'],
      async () => { throw new Error('all unavailable'); },
    )).rejects.toThrow('all unavailable');
  });
});
