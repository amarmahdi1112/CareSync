import { describe, expect, it } from 'vitest';
import { basicAuthenticatedFeatures, runtimeAuthenticatedFeatures } from '../config/productFeatures';
import { realtimeRouteCoverage } from './realtimeCoverage';

describe('enabled portal realtime coverage', () => {
  it('documents a canonical invalidation strategy for every enabled authenticated feature', () => {
    const enabled = [...basicAuthenticatedFeatures.map((feature) => feature.id), ...runtimeAuthenticatedFeatures.map((feature) => feature.id), 'onboarding'].sort();
    expect(Object.keys(realtimeRouteCoverage).sort()).toEqual(enabled);
    Object.values(realtimeRouteCoverage).forEach((coverage) => {
      expect(coverage.canonicalSources.length).toBeGreaterThan(0);
      expect(coverage.entities.length).toBeGreaterThan(0);
      expect(coverage.behavior.length).toBeGreaterThan(20);
    });
  });

  it('covers every workforce source that can change the staff rota projection', () => {
    expect(realtimeRouteCoverage['staff-rota'].canonicalSources).toEqual(expect.arrayContaining([
      'staff availability', 'time-off requests', 'shift templates', 'operational coverage targets', '15-minute coverage projection',
      'recurring rotation patterns', 'open-shift postings', 'open-shift engagements', 'substitute discovery profiles', 'peer shift swaps',
    ]));
    expect(realtimeRouteCoverage['staff-rota'].entities).toEqual(expect.arrayContaining([
      'staff_availability', 'staff_time_off', 'staff_shift_template', 'staff_coverage_target',
      'staff_rotation_pattern', 'staff_open_shift', 'staff_open_shift_engagement', 'staff_substitute_profile', 'staff_shift_swap', 'staff_schedule',
    ]));
  });

  it('refreshes both operational child-status views for a verified family release', () => {
    expect(realtimeRouteCoverage.today.entities).toContain('attendance_release');
    expect(realtimeRouteCoverage.attendance.entities).toContain('attendance_release');
  });

  it('keeps the 0032 evidence registry on one canonical non-operational invalidation entity', () => {
    expect(realtimeRouteCoverage['transport-registry']).toMatchObject({
      path: '/transport-registry',
      entities: ['transport_registry'],
    });
    expect(realtimeRouteCoverage['transport-registry'].behavior).toContain('durable retry records are not replaced');
  });
});
