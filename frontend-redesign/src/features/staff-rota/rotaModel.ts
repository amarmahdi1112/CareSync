import { addDays, differenceInMinutes, format, parseISO, startOfWeek } from 'date-fns';
import type {
  RotaMonitorRow,
  StaffSchedule,
  StaffScheduleDraft,
  StaffScheduleReconciliation,
} from './types';

export const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function rotaWeekStart(value: Date = new Date()): string {
  return format(startOfWeek(value, { weekStartsOn: 1 }), 'yyyy-MM-dd');
}

export function rotaWeekDays(weekStart: string): string[] {
  if (!ISO_DATE_PATTERN.test(weekStart)) throw new Error('A valid rota week start is required.');
  const start = parseISO(`${weekStart}T00:00:00`);
  if (Number.isNaN(start.getTime())) throw new Error('A valid rota week start is required.');
  return Array.from({ length: 7 }, (_, index) => format(addDays(start, index), 'yyyy-MM-dd'));
}

export function scheduleServiceDate(schedule: StaffSchedule): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: schedule.facility_timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(schedule.scheduled_start_at));
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value || '';
  return `${value('year')}-${value('month')}-${value('day')}`;
}

export function scheduleOriginLabel(schedule: Pick<StaffSchedule, 'origin_type' | 'supersedes_schedule_id'>): string | null {
  if (schedule.origin_type === 'rotation') return 'Rotation draft';
  if (schedule.origin_type === 'swap') return 'Swap replacement';
  if (schedule.origin_type === 'open_shift') return schedule.supersedes_schedule_id ? 'Coverage replacement' : 'Open shift';
  return null;
}

export function scheduleDurationMinutes(schedule: Pick<StaffScheduleDraft, 'scheduled_start_at' | 'scheduled_end_at'>): number {
  return differenceInMinutes(parseISO(schedule.scheduled_end_at), parseISO(schedule.scheduled_start_at));
}

export function validateScheduleDraft(draft: StaffScheduleDraft): string[] {
  const errors: string[] = [];
  if (!draft.facility_id) errors.push('Choose a facility.');
  if (!draft.staff_user_id) errors.push('Choose a staff member.');
  const start = parseISO(draft.scheduled_start_at);
  const end = parseISO(draft.scheduled_end_at);
  if (!draft.scheduled_start_at || Number.isNaN(start.getTime())) errors.push('Enter a valid shift start.');
  if (!draft.scheduled_end_at || Number.isNaN(end.getTime())) errors.push('Enter a valid shift end.');
  if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
    if (end <= start) errors.push('Shift end must be after shift start.');
    if (differenceInMinutes(end, start) > 24 * 60) errors.push('A shift cannot be longer than 24 hours.');
  }
  if ((draft.notes || '').length > 2000) errors.push('Notes must be 2,000 characters or fewer.');
  return errors;
}

export function memberHasScheduleScope(
  member: { assigned_facility_ids: string[]; assigned_room_ids: string[] },
  facilityId: string,
  roomId: string | null,
): boolean {
  return member.assigned_facility_ids.includes(facilityId)
    && (!roomId || member.assigned_room_ids.length === 0 || member.assigned_room_ids.includes(roomId));
}

export function reconciliationRows(value: StaffScheduleReconciliation): RotaMonitorRow[] {
  const scheduled = value.scheduled.map((schedule) => ({
    key: `scheduled:${schedule.id}`,
    schedule,
    actual: schedule.actual_shift,
    unscheduled: null,
    status: schedule.reconciliation_status,
    minutes_late: schedule.minutes_late,
  } satisfies RotaMonitorRow));
  const unscheduled = value.unscheduled.map((actual) => ({
    key: `unscheduled:${actual.actual_shift.id}`,
    schedule: null,
    actual: actual.actual_shift,
    unscheduled: actual,
    status: 'unscheduled' as const,
    minutes_late: null,
  }));
  return [...scheduled, ...unscheduled].sort((left, right) => {
    const leftTime = left.schedule?.scheduled_start_at || left.actual?.clocked_in_at || '';
    const rightTime = right.schedule?.scheduled_start_at || right.actual?.clocked_in_at || '';
    return leftTime.localeCompare(rightTime);
  });
}

export function rotaMetrics(rows: readonly RotaMonitorRow[], schedules: readonly StaffSchedule[]) {
  return {
    scheduled: schedules.filter((schedule) => schedule.status === 'published').length,
    awaiting: schedules.filter((schedule) => schedule.status === 'published' && schedule.response_status === 'pending').length,
    onDuty: rows.filter((row) => row.actual && !row.actual.clocked_out_at).length,
    attention: rows.filter((row) => ['late', 'missed', 'unscheduled', 'declined'].includes(row.status)
      || row.schedule?.response_status === 'declined'
      || row.schedule?.response_status === 'alternate_proposed').length,
  };
}
