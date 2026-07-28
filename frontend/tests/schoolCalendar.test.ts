import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildSchoolCalendarPatch,
  schoolCalendarReadyForGeneration,
  schoolOffDaysWithinOpenDays,
  schoolOffSelectionForMonth,
  type SchoolCalendarData,
} from '../src/pages/scheduling/utils/schoolCalendar.ts';

const calendar: SchoolCalendarData = {
  year: 2026,
  jurisdiction: 'Edmonton, Alberta',
  academicYear: '2025-26',
  source: 'Edmonton regular-school calendars (2025-26) — June ending dates',
  sourceDetail: 'Built-in coverage: June 24-30 weekdays after the last instruction day, June 23, 2026',
  automatic: [
    { date: '2026-06-24', name: 'No classes', kind: 'automatic' },
    { date: '2026-06-25', name: 'Summer break', kind: 'automatic' },
  ],
  custom: [
    { date: '2026-05-08', name: 'PD day', kind: 'custom' },
    { date: '2026-06-12', name: 'PD day', kind: 'custom' },
  ],
  excludedAutomaticDays: ['2026-06-24'],
  effective: [
    { date: '2026-05-08', name: 'PD day', kind: 'custom' },
    { date: '2026-06-12', name: 'PD day', kind: 'custom' },
    { date: '2026-06-25', name: 'Summer break', kind: 'automatic' },
  ],
  hasOfficialDefaults: true,
};

test('hydrates only effective weekdays in the selected month', () => {
  assert.deepEqual(schoolOffSelectionForMonth(calendar, 2026, 6), [
    '2026-06-12',
    '2026-06-25',
  ]);
});

test('generation intersects school-off selection with actual open days', () => {
  assert.deepEqual(
    schoolOffDaysWithinOpenDays(
      ['2026-06-12', '2026-06-25', '2026-06-26'],
      ['2026-06-12', '2026-06-26'],
    ),
    ['2026-06-12', '2026-06-26'],
  );
});

test('generation waits for the requested school-calendar year to resolve', () => {
  assert.equal(schoolCalendarReadyForGeneration({
    calendar,
    requestedYear: 2026,
    loading: true,
    hasError: false,
  }), false);
  assert.equal(schoolCalendarReadyForGeneration({
    calendar,
    requestedYear: 2027,
    loading: false,
    hasError: false,
  }), false);
  assert.equal(schoolCalendarReadyForGeneration({
    calendar,
    requestedYear: 2026,
    loading: false,
    hasError: false,
  }), true);
});

test('an explicit calendar fetch failure permits manual fallback only after loading ends', () => {
  assert.equal(schoolCalendarReadyForGeneration({
    requestedYear: 2027,
    loading: true,
    hasError: true,
  }), false);
  assert.equal(schoolCalendarReadyForGeneration({
    requestedYear: 2027,
    loading: false,
    hasError: true,
  }), true);
});

test('manual selection persists as additions and official-date exceptions', () => {
  const payload = buildSchoolCalendarPatch(
    calendar,
    ['2026-06-24', '2026-06-18'],
    2026,
    6,
  );

  assert.deepEqual(payload, {
    year: 2026,
    customDays: [
      { date: '2026-05-08', name: 'PD day' },
      { date: '2026-06-18', name: 'School off' },
    ],
    excludedAutomaticDays: ['2026-06-25'],
  });
});
