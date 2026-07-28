import { format, parseISO } from 'date-fns';

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;

export type WeeklyWindow = {
  weekday: number;
  start_local: string;
  end_local: string;
};

export type CoverageWindow = WeeklyWindow & { required_staff: number };

export type CoverageCellLike = {
  starts_at: string;
  ends_at: string;
  required: number;
  published: number;
  acknowledged: number;
  draft: number;
  gap: number;
};

const LOCAL_TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

export function weekdayLabel(value: number): string {
  return WEEKDAYS[value] ?? `Day ${value}`;
}

export function localMinutes(value: string): number | null {
  if (!LOCAL_TIME.test(value)) return null;
  const [hour = 0, minute = 0] = value.split(':').map(Number);
  return hour * 60 + minute;
}

export function validateWeeklyWindows(windows: readonly WeeklyWindow[]): string[] {
  const errors: string[] = [];
  const byDay = new Map<number, Array<{ start: number; end: number }>>();
  windows.forEach((window, index) => {
    const start = localMinutes(window.start_local);
    const end = localMinutes(window.end_local);
    if (!Number.isInteger(window.weekday) || window.weekday < 0 || window.weekday > 6) {
      errors.push(`Window ${index + 1} needs a weekday from Monday through Sunday.`);
      return;
    }
    if (start == null || end == null) {
      errors.push(`${weekdayLabel(window.weekday)} needs complete 24-hour start and end times.`);
      return;
    }
    if (end <= start) {
      errors.push(`${weekdayLabel(window.weekday)} must end after it starts.`);
      return;
    }
    const values = byDay.get(window.weekday) ?? [];
    values.push({ start, end });
    byDay.set(window.weekday, values);
  });
  for (const [weekday, values] of byDay) {
    const ordered = [...values].sort((left, right) => left.start - right.start);
    if (ordered.some((value, index) => index > 0 && value.start < ordered[index - 1]!.end)) {
      errors.push(`${weekdayLabel(weekday)} has overlapping windows.`);
    }
  }
  return [...new Set(errors)];
}

export function validateCoverageWindows(windows: readonly CoverageWindow[]): string[] {
  const errors = validateWeeklyWindows(windows);
  windows.forEach((window) => {
    if (!Number.isInteger(window.required_staff) || window.required_staff < 0 || window.required_staff > 500) {
      errors.push(`${weekdayLabel(window.weekday)} staffing targets must be whole numbers from 0 to 500.`);
    }
    const start = localMinutes(window.start_local);
    const end = localMinutes(window.end_local);
    if (start != null && end != null && (start % 15 !== 0 || end % 15 !== 0)) {
      errors.push(`${weekdayLabel(window.weekday)} coverage times must align to 15-minute intervals.`);
    }
  });
  return [...new Set(errors)];
}

export function coverageTone(cell: CoverageCellLike): 'clear' | 'watch' | 'gap' | 'inactive' {
  if (cell.required === 0) return 'inactive';
  if (cell.gap > 0) return 'gap';
  if (cell.acknowledged < cell.required) return 'watch';
  return 'clear';
}

export function coverageSummary(cells: readonly CoverageCellLike[]) {
  const active = cells.filter((cell) => cell.required > 0);
  const gaps = active.filter((cell) => cell.gap > 0);
  const acknowledgementRisk = active.filter((cell) => cell.gap === 0 && cell.acknowledged < cell.required);
  const maxGap = gaps.reduce((value, cell) => Math.max(value, cell.gap), 0);
  return {
    activeIntervals: active.length,
    gapIntervals: gaps.length,
    acknowledgementRiskIntervals: acknowledgementRisk.length,
    maxGap,
    coveragePercent: active.length
      ? Math.round((active.filter((cell) => cell.gap === 0).length / active.length) * 100)
      : 100,
  };
}

export function coverageDayKey(instant: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(instant));
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? '';
  return `${value('year')}-${value('month')}-${value('day')}`;
}

export function coverageTimeLabel(instant: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    hour: 'numeric', minute: '2-digit',
  }).format(new Date(instant));
}

export function shortDateLabel(value: string): string {
  return format(parseISO(value), 'EEE, MMM d');
}

export const operationalCoverageDisclaimer =
  'Operational staffing target only. This view does not calculate or certify regulatory child-to-staff ratios, licensing compliance, qualifications, or supervision requirements.';

export function workforceRoomBoundaryIds(rooms: readonly { id: string; facility_id: string }[], facilityId: string): Set<string> {
  return new Set(rooms.filter((room) => room.facility_id === facilityId).map((room) => room.id));
}
