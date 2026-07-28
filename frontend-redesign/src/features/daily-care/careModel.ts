import type { ProgramType } from '../../models/programTypes';
import type { AttendanceState, CareDayChild, CareRecord, CareType, ChildSafetySummary } from './careApi';

export interface CareActionDefinition {
  type: CareType;
  label: string;
  shortLabel: string;
}

const ACTIONS: Record<CareType, CareActionDefinition> = {
  feeding: { type: 'feeding', label: 'Meal or bottle', shortLabel: 'Feeding' },
  diaper: { type: 'diaper', label: 'Diaper change', shortLabel: 'Diaper' },
  toilet: { type: 'toilet', label: 'Toilet visit', shortLabel: 'Toilet' },
  sleep: { type: 'sleep', label: 'Start sleep', shortLabel: 'Sleep' },
  mood: { type: 'mood', label: 'Record mood', shortLabel: 'Mood' },
  activity: { type: 'activity', label: 'Record activity', shortLabel: 'Activity' },
};

export function careActionsForRoom(programType: ProgramType | null | undefined, ageGroup: string | null | undefined): CareActionDefinition[] {
  const actions = (types: CareType[]) => types.map((type) => ACTIONS[type]);
  if (programType === 'out_of_school_care') return actions(['feeding', 'mood', 'activity']);
  const normalized = (ageGroup || '').toLowerCase();
  if (normalized.includes('infant')) return actions(['feeding', 'diaper', 'sleep', 'mood', 'activity']);
  if (normalized.includes('toddler')) return actions(['feeding', 'diaper', 'toilet', 'sleep', 'mood', 'activity']);
  return actions(['feeding', 'toilet', 'sleep', 'mood', 'activity']);
}

export function attendanceLabel(state: AttendanceState): string {
  if (state === 'on_site') return 'On site';
  if (state === 'checked_out') return 'Checked out';
  if (state === 'no_show') return 'No-show';
  return 'Not recorded';
}

export function attendanceTone(state: AttendanceState): 'success' | 'warning' | 'info' | 'neutral' {
  if (state === 'on_site') return 'success';
  if (state === 'checked_out') return 'info';
  if (state === 'no_show') return 'warning';
  return 'neutral';
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

export function careRecordTitle(record: CareRecord): string {
  if (record.care_type === 'feeding') {
    const payload = record.payload as { kind: string; intake: string; volume_ml?: number };
    return payload.kind === 'bottle' ? 'Bottle' : titleCase(payload.kind);
  }
  if (record.care_type === 'diaper') return 'Diaper change';
  if (record.care_type === 'toilet') return 'Toilet visit';
  if (record.care_type === 'sleep') return record.ended_at ? 'Sleep' : 'Sleeping now';
  if (record.care_type === 'mood') return 'Mood';
  return 'Activity';
}

export function careRecordDetail(record: CareRecord): string {
  if (record.care_type === 'feeding') {
    const payload = record.payload as { kind: string; intake: string; volume_ml?: number };
    return `${titleCase(payload.intake)}${payload.volume_ml == null ? '' : ` · ${payload.volume_ml} mL`}`;
  }
  if (record.care_type === 'diaper' || record.care_type === 'toilet') {
    return titleCase((record.payload as { outcome: string }).outcome);
  }
  if (record.care_type === 'mood') return titleCase((record.payload as { value: string }).value);
  if (record.care_type === 'activity') return titleCase((record.payload as { kind: string }).kind);
  if (!record.ended_at) return 'Open interval';
  const minutes = Math.max(0, Math.round((Date.parse(record.ended_at) - Date.parse(record.occurred_at)) / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `${hours}h${remainder ? ` ${remainder}m` : ''}`;
}

export function activeRecords(records: readonly CareRecord[]): CareRecord[] {
  return records.filter((record) => !record.voided_at).slice().sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at));
}

export function openSleep(records: readonly CareRecord[]): CareRecord | null {
  return activeRecords(records).find((record) => record.care_type === 'sleep' && !record.ended_at) || null;
}

export function safetyFlagCount(safety: ChildSafetySummary): number {
  return [safety.allergies, safety.medical_conditions, safety.medication_awareness].filter((value) => Boolean(value?.trim())).length;
}

export function canPresentCurrentSafety(serviceDate: string, facilityToday: string): boolean {
  return serviceDate === facilityToday;
}

export function childNameParts(name: string): { firstName: string; lastName: string } {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return { firstName: parts[0] || 'Child', lastName: parts.slice(1).join(' ') || 'Profile' };
}

export function careDayCounts(children: readonly CareDayChild[]) {
  return children.reduce((counts, child) => {
    counts[child.attendance_state] += 1;
    counts.records += activeRecords(child.records).length;
    counts.safetyFlags += safetyFlagCount(child.safety);
    return counts;
  }, { on_site: 0, checked_out: 0, no_show: 0, not_recorded: 0, records: 0, safetyFlags: 0 });
}

export function canCorrectCareRecord(record: CareRecord, userId: string | null | undefined, canCorrectAny: boolean, canCorrectOwn: boolean): boolean {
  return !record.voided_at && (canCorrectAny || (canCorrectOwn && Boolean(userId) && record.created_by_user_id === userId));
}

function zonedParts(value: Date, timeZone: string): Record<string, string> {
  try {
    return Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(value).map((part) => [part.type, part.value]));
  } catch {
    throw new Error('The facility timezone is not valid.');
  }
}

export function facilityDateTimeInputValue(value: string, timeZone: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const parts = zonedParts(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

/**
 * Converts a wall-clock value in the facility timezone to an absolute instant.
 * Ambiguous or skipped DST wall times are rejected instead of silently using
 * the browser's timezone or guessing an offset.
 */
export function facilityDateTimeToIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error('Enter a complete facility date and time.');
  const [, year, month, day, hour, minute] = match;
  const wallClockUtc = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  const candidates: number[] = [];
  for (let offsetMinutes = -14 * 60; offsetMinutes <= 14 * 60; offsetMinutes += 15) {
    const instant = wallClockUtc - offsetMinutes * 60_000;
    if (facilityDateTimeInputValue(new Date(instant).toISOString(), timeZone) === value) candidates.push(instant);
  }
  const unique = [...new Set(candidates)];
  if (unique.length === 0) throw new Error('That time does not exist in the facility timezone because of a daylight-saving change.');
  if (unique.length > 1) throw new Error('That time occurs twice in the facility timezone. Keep the recorded time or choose an unambiguous time.');
  return new Date(unique[0]).toISOString();
}

export function resolveFacilityDateTime(input: string, originalIso: string, timeZone: string): string {
  return input === facilityDateTimeInputValue(originalIso, timeZone)
    ? originalIso
    : facilityDateTimeToIso(input, timeZone);
}

export function formatCareTime(value: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone, hour: 'numeric', minute: '2-digit' }).format(new Date(value));
  } catch {
    return 'Time unavailable';
  }
}
