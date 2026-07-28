import { describe, expect, it } from 'vitest';
import { memberHasScheduleScope, reconciliationRows, rotaMetrics, rotaWeekDays, scheduleOriginLabel, scheduleServiceDate, validateScheduleDraft } from './rotaModel';
import type { StaffSchedule, StaffScheduleDraft, StaffScheduleReconciliation } from './types';

const draft: StaffScheduleDraft = {
  facility_id: 'facility-1', room_id: 'room-1', staff_user_id: 'user-1',
  scheduled_start_at: '2026-07-20T08:00:00Z', scheduled_end_at: '2026-07-20T16:30:00Z', notes: null,
};
const schedule = (overrides: Partial<StaffSchedule> = {}): StaffSchedule => ({
  id: 'schedule-1', organization_id: 'org-1', membership_id: 'membership-1', ...draft, staff_display_name: 'Ada Care', facility_name: 'North',
  facility_timezone: 'America/Edmonton', room_name: 'Infants', proposed_start_at: null, proposed_end_at: null,
  status: 'published', response_status: 'acknowledged', response_note: null, responded_at: null, actual_shift: null, reconciliation_status: 'upcoming',
  is_late: false, minutes_late: 0, published_at: '2026-07-19T12:00:00Z', cancelled_at: null,
  cancellation_reason: null, availability_override_reason: null, recorded_create_operation_id: 'operation-1', created_by_user_id: 'admin-1',
  origin_type: null, origin_id: null, origin_occurrence_key: null, supersedes_schedule_id: null,
  published_by_user_id: 'admin-1', cancelled_by_user_id: null, created_at: '2026-07-19T10:00:00Z', updated_at: '2026-07-19T12:00:00Z', ...overrides,
});

describe('staff rota model', () => {
  it('constructs a deterministic Monday-through-Sunday week', () => {
    expect(rotaWeekDays('2026-07-20')).toEqual(['2026-07-20', '2026-07-21', '2026-07-22', '2026-07-23', '2026-07-24', '2026-07-25', '2026-07-26']);
  });

  it('groups shifts by facility-local date instead of their UTC date', () => {
    const lateUtc = schedule({ scheduled_start_at: '2026-07-21T05:30:00Z', facility_timezone: 'America/Edmonton' });
    expect(scheduleServiceDate(lateUtc)).toBe('2026-07-20');
  });

  it('labels server-authored schedule provenance without presenting it as work evidence', () => {
    expect(scheduleOriginLabel(schedule({ origin_type: 'rotation', origin_id: 'rotation-1', origin_occurrence_key: 'one' }))).toBe('Rotation draft');
    expect(scheduleOriginLabel(schedule({ origin_type: 'open_shift', origin_id: 'post-1', origin_occurrence_key: 'fill', supersedes_schedule_id: 'old-1' }))).toBe('Coverage replacement');
    expect(scheduleOriginLabel(schedule())).toBeNull();
  });

  it('rejects unsafe or impossible shift drafts', () => {
    expect(validateScheduleDraft({ ...draft, facility_id: '', scheduled_end_at: draft.scheduled_start_at })).toEqual([
      'Choose a facility.', 'Shift end must be after shift start.',
    ]);
    expect(validateScheduleDraft(draft)).toEqual([]);
  });

  it('keeps facility and room assignment scope explicit', () => {
    expect(memberHasScheduleScope({ assigned_facility_ids: ['facility-1'], assigned_room_ids: ['room-1'] }, 'facility-1', 'room-1')).toBe(true);
    expect(memberHasScheduleScope({ assigned_facility_ids: ['facility-1'], assigned_room_ids: ['room-2'] }, 'facility-1', 'room-1')).toBe(false);
    expect(memberHasScheduleScope({ assigned_facility_ids: ['facility-2'], assigned_room_ids: [] }, 'facility-1', null)).toBe(false);
  });

  it('uses canonical reconciliation statuses and preserves unscheduled clock records', () => {
    const value: StaffScheduleReconciliation = {
      scheduled: [
        schedule({ reconciliation_status: 'late', minutes_late: 14, actual_shift: {
          id: 'actual-1', membership_id: 'membership-1', facility_id: 'facility-1', scheduled_shift_id: 'schedule-1', status: 'open',
          clocked_in_at: '2026-07-20T08:14:00Z', clocked_out_at: null,
        } }),
        schedule({ id: 'schedule-2', staff_user_id: 'user-2', reconciliation_status: 'missed' }),
      ],
      unscheduled: [{
        staff_user_id: 'user-3', staff_display_name: 'Sam Care', facility_id: 'facility-1', facility_name: 'North', facility_timezone: 'America/Edmonton',
        reconciliation_status: 'unscheduled',
        actual_shift: { id: 'actual-2', membership_id: 'membership-3', facility_id: 'facility-1', scheduled_shift_id: null, status: 'open', clocked_in_at: '2026-07-20T07:00:00Z', clocked_out_at: null },
      }],
      total_scheduled: 2,
      total_unscheduled: 1,
      generated_at: '2026-07-20T10:00:00Z',
    };
    const rows = reconciliationRows(value);
    expect(rows.map((row) => row.status)).toEqual(['unscheduled', 'late', 'missed']);
    expect(rows[1].minutes_late).toBe(14);
    expect(rotaMetrics(rows, value.scheduled)).toEqual({ scheduled: 2, awaiting: 0, onDuty: 2, attention: 3 });
  });
});
