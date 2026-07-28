const localPattern = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

function partsAt(timestamp: number, timezone: string): number[] {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(timestamp));
  const value = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
  return [value('year'), value('month'), value('day'), value('hour'), value('minute'), value('second')];
}

export function zonedDateTimeToIso(local: string, timezone: string): string {
  const match = localPattern.exec(local);
  if (!match) throw new Error('Enter a complete local date and time.');
  try { new Intl.DateTimeFormat('en-CA', { timeZone: timezone }).format(); } catch { throw new Error('The organization returned an invalid timezone.'); }
  const desired = match.slice(1).map((value) => Number(value || 0));
  const desiredUtc = Date.UTC(desired[0], desired[1] - 1, desired[2], desired[3], desired[4], desired[5]);
  let timestamp = desiredUtc;
  for (let index = 0; index < 3; index += 1) { const actual = partsAt(timestamp, timezone); timestamp += desiredUtc - Date.UTC(actual[0], actual[1] - 1, actual[2], actual[3], actual[4], actual[5]); }
  if (partsAt(timestamp, timezone).some((value, index) => value !== desired[index])) throw new Error('That local time does not exist in the selected timezone. Choose another time.');
  return new Date(timestamp).toISOString();
}
