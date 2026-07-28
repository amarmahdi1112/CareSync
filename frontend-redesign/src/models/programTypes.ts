export const PROGRAM_TYPES = ['daycare', 'out_of_school_care'] as const;

export type ProgramType = (typeof PROGRAM_TYPES)[number];

export const PROGRAM_TYPE_LABELS: Record<ProgramType, string> = {
  daycare: 'Daycare',
  out_of_school_care: 'OSC (Out-of-School Care)',
};

export function isProgramType(value: unknown): value is ProgramType {
  return typeof value === 'string' && PROGRAM_TYPES.includes(value as ProgramType);
}

export function normalizeProgramType(value: unknown): ProgramType | null {
  if (isProgramType(value)) return value;
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (normalized === 'osc' || normalized === 'out_of_school' || normalized === 'school_age') {
    return 'out_of_school_care';
  }
  if (normalized === 'preschool' || normalized === 'child_care' || normalized === 'care') {
    return 'daycare';
  }
  return null;
}

export function formatProgramType(value: unknown, fallback = 'Care program'): string {
  const type = normalizeProgramType(value);
  return type ? PROGRAM_TYPE_LABELS[type] : fallback;
}
