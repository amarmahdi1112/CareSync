export interface DomainOption {
  value: string;
  label: string;
}

export const CANADIAN_PROVINCE_OPTIONS: readonly DomainOption[] = [
  { value: 'Alberta', label: 'Alberta' },
  { value: 'British Columbia', label: 'British Columbia' },
  { value: 'Manitoba', label: 'Manitoba' },
  { value: 'New Brunswick', label: 'New Brunswick' },
  { value: 'Newfoundland and Labrador', label: 'Newfoundland and Labrador' },
  { value: 'Northwest Territories', label: 'Northwest Territories' },
  { value: 'Nova Scotia', label: 'Nova Scotia' },
  { value: 'Nunavut', label: 'Nunavut' },
  { value: 'Ontario', label: 'Ontario' },
  { value: 'Prince Edward Island', label: 'Prince Edward Island' },
  { value: 'Quebec', label: 'Quebec' },
  { value: 'Saskatchewan', label: 'Saskatchewan' },
  { value: 'Yukon', label: 'Yukon' },
] as const;

const PROVINCE_ALIASES: Readonly<Record<string, string>> = {
  ab: 'Alberta',
  bc: 'British Columbia',
  mb: 'Manitoba',
  nb: 'New Brunswick',
  nl: 'Newfoundland and Labrador',
  nfl: 'Newfoundland and Labrador',
  nt: 'Northwest Territories',
  nwt: 'Northwest Territories',
  ns: 'Nova Scotia',
  nu: 'Nunavut',
  on: 'Ontario',
  pe: 'Prince Edward Island',
  pei: 'Prince Edward Island',
  qc: 'Quebec',
  pq: 'Quebec',
  sk: 'Saskatchewan',
  yt: 'Yukon',
};

export const CANADIAN_TIMEZONE_OPTIONS: readonly DomainOption[] = [
  { value: 'America/St_Johns', label: 'Newfoundland time' },
  { value: 'America/Halifax', label: 'Atlantic time' },
  { value: 'America/Toronto', label: 'Eastern time' },
  { value: 'America/Winnipeg', label: 'Central time' },
  { value: 'America/Regina', label: 'Saskatchewan time' },
  { value: 'America/Edmonton', label: 'Mountain time · Alberta' },
  { value: 'America/Vancouver', label: 'Pacific time' },
  { value: 'America/Whitehorse', label: 'Yukon time' },
] as const;

export const ROOM_AGE_GROUP_OPTIONS: readonly DomainOption[] = [
  { value: 'Infant', label: 'Infant' },
  { value: 'Toddler', label: 'Toddler' },
  { value: 'Preschool', label: 'Preschool' },
  { value: 'School-Age', label: 'School-Age / OSC' },
  { value: 'Mixed-Age', label: 'Mixed-Age' },
] as const;

export const CHILD_GENDER_OPTIONS: readonly DomainOption[] = [
  { value: 'Female', label: 'Female' },
  { value: 'Male', label: 'Male' },
  { value: 'Non-binary', label: 'Non-binary' },
  { value: 'Two-Spirit', label: 'Two-Spirit' },
  { value: 'Prefer not to say', label: 'Prefer not to say' },
] as const;

function normalizedKey(value: string): string {
  return value.normalize('NFKC').trim().toLocaleLowerCase('en-CA').replace(/[^a-z0-9]+/g, '');
}

export function normalizeCanadianProvince(value: string): string {
  const trimmed = value.normalize('NFKC').trim();
  if (!trimmed) return '';
  const alias = PROVINCE_ALIASES[normalizedKey(trimmed)];
  if (alias) return alias;
  return CANADIAN_PROVINCE_OPTIONS.find((option) => normalizedKey(option.value) === normalizedKey(trimmed))?.value || trimmed;
}

export function normalizeRoomAgeGroup(value: string | null | undefined): string {
  const trimmed = String(value || '').normalize('NFKC').trim();
  if (!trimmed) return '';
  const key = normalizedKey(trimmed);
  if (key === 'schoolage' || key === 'osc' || key === 'outofschoolcare') return 'School-Age';
  if (key === 'mixed' || key === 'mixedage' || key === 'notspecified') return 'Mixed-Age';
  return ROOM_AGE_GROUP_OPTIONS.find((option) => normalizedKey(option.value) === key)?.value || trimmed;
}

export function includesDomainValue(options: readonly DomainOption[], value: string): boolean {
  return options.some((option) => option.value === value);
}

