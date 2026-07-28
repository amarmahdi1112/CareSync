import { describe, expect, it } from 'vitest';

import {
  assertIsoDate,
  assertTime24,
  formatPortalDate,
  minutesSinceMidnight,
  normalizePortalTime,
  samePortalTime,
  toPortalTime,
} from '../src/shared/format';

describe('portal date conversion', () => {
  it('formats an ISO date exactly as the portal date input expects', () => {
    expect(formatPortalDate('2026-07-13')).toBe('Monday, Jul 13, 2026');
  });

  it('accepts a real leap day and rejects impossible calendar dates', () => {
    expect(assertIsoDate('2028-02-29')).toBe('2028-02-29');
    expect(() => assertIsoDate('2026-02-29')).toThrow(/invalid attendance date/i);
    expect(() => assertIsoDate('2026-13-01')).toThrow(/invalid attendance date/i);
  });
});

describe('portal time conversion', () => {
  it.each([
    ['00:00', '12:00 am'],
    ['07:05', '7:05 am'],
    ['12:00', '12:00 pm'],
    ['16:30', '4:30 pm'],
    ['23:59', '11:59 pm'],
  ])('converts %s to %s', (source, expected) => {
    expect(toPortalTime(source)).toBe(expected);
  });

  it('normalizes portal AM/PM variants before comparing them', () => {
    expect(normalizePortalTime(' 7:05 A.M. ')).toBe('07:05');
    expect(normalizePortalTime('12:00 pm')).toBe('12:00');
    expect(normalizePortalTime('12:00 AM')).toBe('00:00');
    expect(samePortalTime('4:30 PM', '16:30')).toBe(true);
    expect(samePortalTime('4:35 PM', '16:30')).toBe(false);
  });

  it('validates strict 24-hour values and computes minutes since midnight', () => {
    expect(assertTime24('06:00')).toBe('06:00');
    expect(minutesSinceMidnight('16:30')).toBe(990);
    expect(() => assertTime24('6:00')).toThrow(/invalid attendance time/i);
    expect(() => assertTime24('24:00')).toThrow(/invalid attendance time/i);
  });
});
