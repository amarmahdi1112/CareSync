import { describe, expect, it } from 'vitest';
import { zonedDateTimeToIso } from './zonedDateTime';

describe('organization-local interview time', () => {
  it('converts Edmonton local time to the correct summer and winter UTC instants', () => { expect(zonedDateTimeToIso('2026-07-20T10:00', 'America/Edmonton')).toBe('2026-07-20T16:00:00.000Z'); expect(zonedDateTimeToIso('2026-01-20T10:00', 'America/Edmonton')).toBe('2026-01-20T17:00:00.000Z'); });
  it('rejects nonexistent DST wall time and invalid timezones', () => { expect(() => zonedDateTimeToIso('2026-03-08T02:30', 'America/Edmonton')).toThrow('does not exist'); expect(() => zonedDateTimeToIso('2026-07-20T10:00', 'Mars/Olympus')).toThrow('invalid timezone'); });
});
