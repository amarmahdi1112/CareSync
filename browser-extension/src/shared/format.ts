const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_24 = /^([01]\d|2[0-3]):([0-5]\d)$/;

export function assertIsoDate(value: string): string {
  if (!ISO_DATE.test(value)) throw new Error(`Invalid attendance date: ${value}`);
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw new Error(`Invalid attendance date: ${value}`);
  }
  return value;
}

export function assertTime24(value: string): string {
  if (!TIME_24.test(value)) throw new Error(`Invalid attendance time: ${value}`);
  return value;
}

export function minutesSinceMidnight(value: string): number {
  assertTime24(value);
  const [hours, minutes] = value.split(':').map(Number);
  return hours * 60 + minutes;
}

export function formatPortalDate(isoDate: string): string {
  assertIsoDate(isoDate);
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long', year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function toPortalTime(value: string): string {
  assertTime24(value);
  const [rawHours, minutes] = value.split(':').map(Number);
  const suffix = rawHours >= 12 ? 'pm' : 'am';
  const hours = rawHours % 12 || 12;
  return `${hours}:${String(minutes).padStart(2, '0')} ${suffix}`;
}

export function normalizePortalTime(value: string): string | null {
  const normalized = value.trim().toLowerCase().replace(/\s+/g, ' ');
  const match = normalized.match(/^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$/);
  if (!match) return TIME_24.test(normalized) ? normalized : null;
  let hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 1 || hours > 12 || minutes > 59) return null;
  if (match[3] === 'p' && hours !== 12) hours += 12;
  if (match[3] === 'a' && hours === 12) hours = 0;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

export function samePortalTime(portalValue: string, expected24: string): boolean {
  return normalizePortalTime(portalValue) === assertTime24(expected24);
}
