import { describe, expect, it } from 'vitest';
import { parseChildRecordReadiness } from './readinessApi';

function response(overrides: Record<string, unknown> = {}) {
  return {
    items: [{
      key: 'open-unassigned:enrollment-1',
      code: 'open_unassigned_enrollment',
      severity: 'warning',
      family_id: 'family-1',
      child_id: 'child-1',
      enrollment_id: 'enrollment-1',
      facility_id: 'facility-1',
      title: 'Placement needed',
      message: 'The open enrollment has no approved room.',
      action_route: '/rooms?facility_id=facility-1&placement_enrollment_id=enrollment-1',
    }],
    total: 1,
    limit: 8,
    offset: 0,
    counts: { critical: 0, warning: 1, info: 0 },
    ...overrides,
  };
}

describe('child-record readiness parser', () => {
  it('accepts a bounded, internally linked readiness page', () => {
    const parsed = parseChildRecordReadiness(response());
    expect(parsed.items[0]).toMatchObject({
      child_id: 'child-1',
      severity: 'warning',
      action_route: '/rooms?facility_id=facility-1&placement_enrollment_id=enrollment-1',
    });
  });

  it('rejects an action route that crosses the affected record', () => {
    const value = response();
    (value.items[0] as Record<string, unknown>).action_route = '/children/another-child';
    expect(() => parseChildRecordReadiness(value)).toThrow('did not match');
  });

  it('accepts only the exact family-status focus for a pending-family enrollment blocker', () => {
    const value = response();
    (value.items[0] as Record<string, unknown>).action_route = '/families/family-1?focus=family-status&child_id=child-1&enrollment_id=enrollment-1';
    expect(parseChildRecordReadiness(value).items[0]?.action_route).toBe(
      '/families/family-1?focus=family-status&child_id=child-1&enrollment_id=enrollment-1',
    );

    const crossedChild = response();
    (crossedChild.items[0] as Record<string, unknown>).action_route = '/families/family-1?focus=family-status&child_id=another-child&enrollment_id=enrollment-1';
    expect(() => parseChildRecordReadiness(crossedChild)).toThrow('did not match');

    const extraField = response();
    (extraField.items[0] as Record<string, unknown>).action_route = '/families/family-1?focus=family-status&child_id=child-1&enrollment_id=enrollment-1&status=active';
    expect(() => parseChildRecordReadiness(extraField)).toThrow('unsupported focus fields');
  });

  it('rejects duplicate keys and severity totals that cannot reconcile', () => {
    const duplicate = response({
      items: [response().items[0], response().items[0]],
      total: 2,
      counts: { critical: 0, warning: 2, info: 0 },
    });
    expect(() => parseChildRecordReadiness(duplicate)).toThrow('duplicate');
    expect(() => parseChildRecordReadiness(response({ counts: { critical: 0, warning: 0, info: 0 } }))).toThrow('reconcile');
  });
});
