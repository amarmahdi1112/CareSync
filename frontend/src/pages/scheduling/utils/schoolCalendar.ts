export interface SchoolCalendarDay {
  date: string;
  name: string;
  kind: 'automatic' | 'custom';
}

export interface SchoolCalendarData {
  year: number;
  jurisdiction: string;
  academicYear: string | null;
  source: string;
  sourceDetail: string;
  automatic: SchoolCalendarDay[];
  custom: SchoolCalendarDay[];
  excludedAutomaticDays: string[];
  effective: SchoolCalendarDay[];
  hasOfficialDefaults: boolean;
}

export interface SchoolCalendarPatch {
  year: number;
  customDays: Array<{ date: string; name: string }>;
  excludedAutomaticDays: string[];
}

interface SchoolCalendarReadiness {
  calendar?: SchoolCalendarData;
  requestedYear?: number;
  loading: boolean;
  hasError: boolean;
}

/**
 * A stale calendar must never unlock generation for a newly selected year.
 * After an explicit fetch failure, manual selection remains available so a
 * temporary API problem does not block the scheduler indefinitely.
 */
export const schoolCalendarReadyForGeneration = ({
  calendar,
  requestedYear,
  loading,
  hasError,
}: SchoolCalendarReadiness): boolean => Boolean(
  requestedYear
  && !loading
  && (calendar?.year === requestedYear || hasError),
);

const monthPrefix = (year: number, month: number) =>
  `${year}-${String(month).padStart(2, '0')}-`;

const isWeekday = (value: string) => {
  const weekday = new Date(`${value}T12:00:00`).getDay();
  return weekday >= 1 && weekday <= 5;
};

export const monthWeekdayDates = (year: number, month: number): string[] => {
  const daysInMonth = new Date(year, month, 0).getDate();
  return Array.from({ length: daysInMonth }, (_, index) =>
    `${year}-${String(month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`,
  ).filter(isWeekday);
};

export const schoolOffSelectionForMonth = (
  calendar: SchoolCalendarData,
  year: number,
  month: number,
): string[] => {
  const prefix = monthPrefix(year, month);
  return [...new Set(
    calendar.effective
      .map((item) => item.date)
      .filter((value) => value.startsWith(prefix) && isWeekday(value)),
  )].sort();
};

export const schoolOffDaysWithinOpenDays = (
  selectedDays: string[],
  openDays: string[],
): string[] => {
  const open = new Set(openDays);
  return [...new Set(selectedDays.filter((value) => open.has(value)))].sort();
};

export const buildSchoolCalendarPatch = (
  calendar: SchoolCalendarData,
  selectedDays: string[],
  year: number,
  month: number,
): SchoolCalendarPatch => {
  const prefix = monthPrefix(year, month);
  const selected = new Set(
    selectedDays.filter((value) => value.startsWith(prefix) && isWeekday(value)),
  );
  const automatic = new Set(calendar.automatic.map((item) => item.date));
  const customByDate = new Map(
    calendar.custom
      .filter((item) => !item.date.startsWith(prefix))
      .map((item) => [item.date, { date: item.date, name: item.name }]),
  );
  for (const value of selected) {
    if (!automatic.has(value)) {
      customByDate.set(value, { date: value, name: 'School off' });
    }
  }

  const excluded = new Set(
    calendar.excludedAutomaticDays.filter((value) => !value.startsWith(prefix)),
  );
  for (const value of automatic) {
    if (value.startsWith(prefix) && !selected.has(value)) excluded.add(value);
  }

  return {
    year,
    customDays: [...customByDate.values()].sort((left, right) =>
      left.date.localeCompare(right.date),
    ),
    excludedAutomaticDays: [...excluded].sort(),
  };
};
