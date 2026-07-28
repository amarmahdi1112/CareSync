import { describe, expect, it } from 'vitest';
import { isFacilityMonday, occurrenceCounts, rotationDraftInput, validateRotationInput } from './rotationModel';
import type { RotationPatternInput } from './rotationTypes';

const input = (): RotationPatternInput => ({
  facility_id: 'facility-1', name: 'Infant rotation', anchor_date: '2026-07-20', cycle_weeks: 2,
  slots: [{ slot_id: 'slot-1', cycle_week: 0, weekday: 0, staff_user_id: 'user-1', room_id: 'room-1', start_local: '08:00', end_local: '16:00', notes: null }],
});

describe('rotation model', () => {
  it('requires a facility-local Monday anchor and bounded cycle', () => {
    expect(isFacilityMonday('2026-07-20')).toBe(true);
    expect(isFacilityMonday('2026-07-21')).toBe(false);
    expect(validateRotationInput(input())).toEqual([]);
    expect(validateRotationInput({ ...input(), anchor_date: '2026-07-21', cycle_weeks: 0 })).toEqual(expect.arrayContaining([
      'Choose a Monday as the rotation anchor.', 'Cycle length must be between 1 and 8 weeks.',
    ]));
  });

  it('rejects overnight and overlapping educator slots', () => {
    const first = input().slots[0]!;
    const value = input();
    value.slots = [first, { ...first, slot_id: 'slot-2', start_local: '15:30', end_local: '17:00' }];
    expect(validateRotationInput(value)).toContain('Slot 2 overlaps another slot for the same educator.');
    expect(validateRotationInput({ ...input(), slots: [{ ...first, start_local: '20:00', end_local: '06:00' }] })).toContain('Slot 1 must end after it starts; overnight slots are not supported.');
  });

  it('caps one rotation at 500 slots', () => {
    const value = input();
    expect(validateRotationInput({ ...value, slots: Array.from({ length: 501 }, (_, index) => ({ ...value.slots[0]!, slot_id: `slot-${index}`, staff_user_id: `staff-${index}` })) })).toContain('A rotation can contain at most 500 slots.');
  });

  it('summarizes explicit preview states without treating conflicts as generated', () => {
    expect(occurrenceCounts({
      occurrences: [{ occurrence_key: 'one' }, { occurrence_key: 'two' }, { occurrence_key: 'three' }],
      issues: [{ occurrence_key: 'two' }, { occurrence_key: 'two' }, { occurrence_key: null }],
    } as never)).toEqual({ ready: 2, conflicts: 1, issues: 3 });
  });

  it('copies an immutable snapshot into a detached draft input', () => {
    const source = { ...input(), id: 'pattern-1', version: 3, status: 'active' } as never;
    const copied = rotationDraftInput(source);
    expect(copied).toEqual(input());
    expect(copied.slots).not.toBe((source as { slots: unknown[] }).slots);
    expect(copied.slots[0]).not.toBe((source as { slots: unknown[] }).slots[0]);
  });
});
