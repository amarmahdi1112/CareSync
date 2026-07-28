/**
 * Map the program label supplied by CareSync's child/claim records to the
 * scheduler's two hard window types. This deliberately uses exact normalized
 * labels: `Preschool` is daycare and must never be inferred as OSC merely
 * because its spelling contains the word "school".
 */
const OSC_PROGRAM_LABELS = new Set([
  'osc',
  'schoolage',
  'outofschoolcare',
  'outofschool',
]);

const DAYCARE_PROGRAM_LABELS = new Set([
  'daycare',
  'fulltime',
  'infant',
  'toddler',
  'preschool',
]);

const normalizeProgramLabel = (value: unknown): string => String(value ?? '')
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '');

export const schedulerCareType = (...labels: unknown[]): 'OSC' | 'Daycare' => {
  for (const label of labels) {
    const normalized = normalizeProgramLabel(label);
    if (OSC_PROGRAM_LABELS.has(normalized)) return 'OSC';
    if (DAYCARE_PROGRAM_LABELS.has(normalized)) return 'Daycare';
  }
  return 'Daycare';
};
