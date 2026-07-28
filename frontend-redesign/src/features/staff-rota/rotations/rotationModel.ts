import type { RotationPattern, RotationPatternInput, RotationPreview, RotationSlotInput } from './rotationTypes';

const LOCAL_TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function localTimeMinutes(value: string): number | null {
  if (!LOCAL_TIME.test(value)) return null;
  const [hours, minutes] = value.split(':').map(Number);
  return (hours ?? 0) * 60 + (minutes ?? 0);
}

export function isFacilityMonday(value: string): boolean {
  return ISO_DATE.test(value) && !Number.isNaN(Date.parse(`${value}T12:00:00Z`))
    && new Date(`${value}T12:00:00Z`).getUTCDay() === 1;
}

export function validateRotationInput(input: RotationPatternInput): string[] {
  const errors: string[] = [];
  if (!input.facility_id) errors.push('Choose a facility.');
  if (!input.name.trim()) errors.push('Give the rotation a name.');
  if (input.name.trim().length > 150) errors.push('Rotation names must be 150 characters or fewer.');
  if (!isFacilityMonday(input.anchor_date)) errors.push('Choose a Monday as the rotation anchor.');
  if (!Number.isInteger(input.cycle_weeks) || input.cycle_weeks < 1 || input.cycle_weeks > 8) errors.push('Cycle length must be between 1 and 8 weeks.');
  if (!input.slots.length) errors.push('Add at least one rotation slot.');
  if (input.slots.length > 500) errors.push('A rotation can contain at most 500 slots.');
  const slotIds = new Set<string>();
  const lanes = new Map<string, Array<{ start: number; end: number; label: string }>>();
  input.slots.forEach((slot, index) => {
    const label = `Slot ${index + 1}`;
    if (!slot.slot_id || slotIds.has(slot.slot_id)) errors.push(`${label} needs a unique identifier.`);
    slotIds.add(slot.slot_id);
    if (!Number.isInteger(slot.cycle_week) || slot.cycle_week < 0 || slot.cycle_week >= input.cycle_weeks) errors.push(`${label} needs a cycle week inside this rotation.`);
    if (!Number.isInteger(slot.weekday) || slot.weekday < 0 || slot.weekday > 6) errors.push(`${label} needs a weekday.`);
    if (!slot.staff_user_id) errors.push(`${label} needs a staff member.`);
    const start = localTimeMinutes(slot.start_local);
    const end = localTimeMinutes(slot.end_local);
    if (start == null || end == null) errors.push(`${label} needs complete 24-hour times.`);
    else if (end <= start) errors.push(`${label} must end after it starts; overnight slots are not supported.`);
    if ((slot.notes || '').length > 1000) errors.push(`${label} notes must be 1,000 characters or fewer.`);
    if (start != null && end != null && end > start && slot.staff_user_id) {
      const lane = `${slot.staff_user_id}:${slot.cycle_week}:${slot.weekday}`;
      const values = lanes.get(lane) ?? [];
      values.push({ start, end, label }); lanes.set(lane, values);
    }
  });
  lanes.forEach((values) => {
    const ordered = [...values].sort((left, right) => left.start - right.start);
    ordered.forEach((value, index) => {
      if (index && value.start < ordered[index - 1]!.end) errors.push(`${value.label} overlaps another slot for the same educator.`);
    });
  });
  return [...new Set(errors)];
}

export function rotationSummary(pattern: RotationPattern): string {
  const people = new Set(pattern.slots.map((slot) => slot.staff_user_id)).size;
  return `${pattern.cycle_weeks}-week cycle · ${pattern.slots.length} slot${pattern.slots.length === 1 ? '' : 's'} · ${people} educator${people === 1 ? '' : 's'}`;
}

export function occurrenceCounts(preview: Pick<RotationPreview, 'occurrences' | 'issues'>) {
  const affected = new Set(preview.issues.map((issue) => issue.occurrence_key).filter((value): value is string => Boolean(value)));
  return {
    ready: preview.occurrences.filter((item) => !affected.has(item.occurrence_key)).length,
    conflicts: affected.size,
    issues: preview.issues.length,
  };
}

export function copySlot(slot: RotationSlotInput): RotationSlotInput {
  return {
    slot_id: slot.slot_id,
    cycle_week: slot.cycle_week,
    weekday: slot.weekday,
    staff_user_id: slot.staff_user_id,
    room_id: slot.room_id,
    start_local: slot.start_local,
    end_local: slot.end_local,
    notes: slot.notes,
  };
}

export function rotationDraftInput(pattern: RotationPattern): RotationPatternInput {
  return {
    facility_id: pattern.facility_id,
    name: pattern.name,
    anchor_date: pattern.anchor_date,
    cycle_weeks: pattern.cycle_weeks,
    slots: pattern.slots.map(copySlot),
  };
}
