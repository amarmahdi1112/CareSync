import type { AttendanceRosterRow } from './attendanceApi';

export type AttendanceState = 'pending' | 'present' | 'on-site' | 'completed' | 'absent';

export type AttendancePrimaryAction = 'check-in' | 'check-out' | 'check-in-again' | null;

export interface AttendancePresentation {
  label: string;
  primaryAction: AttendancePrimaryAction;
  primaryLabel: string | null;
  secondaryAction: 'mark-no-show' | null;
  secondaryLabel: string | null;
}

/**
 * Keeps database states separate from their operator-facing meaning. In
 * particular, an `absent` record is a deliberate no-show record; it must never
 * be presented as a check-out. A check-out is only available while an interval
 * is genuinely open.
 */
export function attendancePresentation(state: AttendanceState): AttendancePresentation {
  switch (state) {
    case 'on-site':
      return { label: 'On site', primaryAction: 'check-out', primaryLabel: 'Check out', secondaryAction: null, secondaryLabel: null };
    case 'completed':
      return { label: 'Checked out', primaryAction: 'check-in-again', primaryLabel: 'Check in again', secondaryAction: null, secondaryLabel: null };
    case 'absent':
      return { label: 'No-show', primaryAction: null, primaryLabel: null, secondaryAction: null, secondaryLabel: null };
    case 'present':
    case 'pending':
      return { label: 'Not recorded', primaryAction: 'check-in', primaryLabel: 'Check in', secondaryAction: 'mark-no-show', secondaryLabel: 'Mark no-show' };
  }
}

export function attendanceState(row: AttendanceRosterRow): AttendanceState {
  const day = row.attendance_day;
  if (!day) return 'pending';
  if (day.status === 'absent') return 'absent';
  if (day.intervals.some((interval) => !interval.checked_out_at)) return 'on-site';
  if (day.intervals.length > 0) return 'completed';
  return 'present';
}

export function attendanceCounts(rows: AttendanceRosterRow[]) {
  const counts = { enrolled: rows.length, pending: 0, onSite: 0, completed: 0, absent: 0 };
  for (const row of rows) {
    const state = attendanceState(row);
    if (state === 'pending' || state === 'present') counts.pending += 1;
    else if (state === 'on-site') counts.onSite += 1;
    else if (state === 'completed') counts.completed += 1;
    else counts.absent += 1;
  }
  return counts;
}

export function validateCorrection(checkIn: string, checkOut: string, reason: string): string[] {
  const errors: string[] = [];
  if (!checkIn || !checkOut) errors.push('Enter both corrected times.');
  if (checkIn && checkOut && new Date(checkOut).getTime() < new Date(checkIn).getTime()) errors.push('Check-out cannot be earlier than check-in.');
  if (reason.trim().length < 5) errors.push('Explain the correction in at least five characters.');
  return errors;
}
