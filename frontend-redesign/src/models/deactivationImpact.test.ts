import { describe, expect, it } from 'vitest';
import { parseDeactivationImpact } from './deactivationImpact';

const impact = {
  organization_id: 'org', entity_type: 'facility', entity_id: 'facility', entity_name: 'Main',
  active_programs: 2, active_rooms: 4, open_enrollments: 12, open_attendance_intervals: 0,
  active_staff_assignments: 5, open_staff_shifts: 0, blockers: [], warnings: ['Assignments will be retained.'],
  can_deactivate: true, confirmation_text: 'Main',
};

describe('deactivation impact contract', () => {
  it('preserves audited counts, warnings, and exact confirmation text', () => {
    expect(parseDeactivationImpact(impact, { organizationId: 'org', entityType: 'facility', entityId: 'facility' })).toEqual(impact);
  });

  it('rejects cross-organization, cross-entity, malformed, and contradictory responses', () => {
    expect(() => parseDeactivationImpact({ ...impact, organization_id: 'other' }, { organizationId: 'org', entityType: 'facility', entityId: 'facility' })).toThrow('boundary');
    expect(() => parseDeactivationImpact({ ...impact, entity_type: 'room' }, { organizationId: 'org', entityType: 'facility', entityId: 'facility' })).toThrow('boundary');
    expect(() => parseDeactivationImpact({ ...impact, warnings: null }, { organizationId: 'org', entityType: 'facility', entityId: 'facility' })).toThrow('warnings');
    expect(() => parseDeactivationImpact({ ...impact, blockers: ['Open interval'], can_deactivate: true }, { organizationId: 'org', entityType: 'facility', entityId: 'facility' })).toThrow('contradicted');
  });
});
