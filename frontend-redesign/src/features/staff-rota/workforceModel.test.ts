import { describe, expect, it } from 'vitest';
import {
  coverageDayKey,
  coverageSummary,
  coverageTone,
  operationalCoverageDisclaimer,
  validateCoverageWindows,
  validateWeeklyWindows,
  weekdayLabel,
  workforceRoomBoundaryIds,
} from './workforceModel';

describe('workforce planning model', () => {
  it('validates facility-local weekly windows without guessing overlaps', () => {
    expect(validateWeeklyWindows([
      { weekday: 0, start_local: '07:00', end_local: '12:00' },
      { weekday: 0, start_local: '12:00', end_local: '18:00' },
    ])).toEqual([]);
    expect(validateWeeklyWindows([
      { weekday: 0, start_local: '07:00', end_local: '12:00' },
      { weekday: 0, start_local: '11:45', end_local: '18:00' },
      { weekday: 8, start_local: '09:00', end_local: '08:00' },
    ])).toEqual(expect.arrayContaining(['Monday has overlapping windows.', 'Window 3 needs a weekday from Monday through Sunday.']));
  });

  it('requires bounded whole-number operational staffing targets', () => {
    expect(validateCoverageWindows([{ weekday: 2, start_local: '08:00', end_local: '16:00', required_staff: 3 }])).toEqual([]);
    expect(validateCoverageWindows([{ weekday: 2, start_local: '08:00', end_local: '16:00', required_staff: 3.5 }])).toContain('Wednesday staffing targets must be whole numbers from 0 to 500.');
    expect(validateCoverageWindows([{ weekday: 2, start_local: '08:10', end_local: '16:00', required_staff: 3 }])).toContain('Wednesday coverage times must align to 15-minute intervals.');
  });

  it('summarizes canonical 15-minute projection cells', () => {
    const cells = [
      { starts_at: '2026-07-20T14:00:00Z', ends_at: '2026-07-20T14:15:00Z', required: 3, published: 3, acknowledged: 3, draft: 0, gap: 0 },
      { starts_at: '2026-07-20T14:15:00Z', ends_at: '2026-07-20T14:30:00Z', required: 3, published: 3, acknowledged: 2, draft: 1, gap: 0 },
      { starts_at: '2026-07-20T14:30:00Z', ends_at: '2026-07-20T14:45:00Z', required: 3, published: 1, acknowledged: 1, draft: 2, gap: 2 },
      { starts_at: '2026-07-20T14:45:00Z', ends_at: '2026-07-20T15:00:00Z', required: 0, published: 0, acknowledged: 0, draft: 0, gap: 0 },
    ];
    expect(cells.map(coverageTone)).toEqual(['clear', 'watch', 'gap', 'inactive']);
    expect(coverageSummary(cells)).toEqual({ activeIntervals: 3, gapIntervals: 1, acknowledgementRiskIntervals: 1, maxGap: 2, coveragePercent: 67 });
  });

  it('uses the facility calendar and never presents targets as compliance', () => {
    expect(coverageDayKey('2026-07-20T05:30:00Z', 'America/Edmonton')).toBe('2026-07-19');
    expect(weekdayLabel(6)).toBe('Sunday');
    expect(operationalCoverageDisclaimer).toContain('does not calculate or certify regulatory');
  });

  it('keeps inactive historical rooms inside the facility boundary', () => {
    const rooms = [
      { id: 'active-room', facility_id: 'facility-1', is_active: true },
      { id: 'inactive-room', facility_id: 'facility-1', is_active: false },
      { id: 'other-room', facility_id: 'facility-2', is_active: true },
    ];
    expect([...workforceRoomBoundaryIds(rooms, 'facility-1')]).toEqual(['active-room', 'inactive-room']);
  });
});
