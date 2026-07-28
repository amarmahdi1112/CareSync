import { describe, expect, it } from 'vitest';
import {
  basicAuthenticatedFeatures,
  runtimeAuthenticatedFeatures,
} from '../config/productFeatures';
import {
  crossFeatureDependencies,
  downstreamConsumersFor,
  featureIntegrationManifest,
  portalIntegrationIds,
  type FeatureIntegrationContract,
  type IntegrationId,
} from './featureIntegrationManifest';
import { realtimeRouteCoverage } from './realtimeCoverage';

describe('CareSync feature integration manifest', () => {
  it('covers every enabled authenticated portal surface and onboarding', () => {
    const expected = [
      ...basicAuthenticatedFeatures.map((feature) => feature.id),
      ...runtimeAuthenticatedFeatures.map((feature) => feature.id),
      'onboarding',
      'session-shell',
    ].sort();
    expect([...portalIntegrationIds].sort()).toEqual(expected);
  });

  it('uses the canonical portal invalidation selectors instead of a second entity graph', () => {
    for (const id of portalIntegrationIds) {
      if (id === 'session-shell') continue;
      expect(featureIntegrationManifest[id].realtimeEntities).toBe(
        realtimeRouteCoverage[id].entities,
      );
      expect(featureIntegrationManifest[id].canonicalSources).toBe(
        realtimeRouteCoverage[id].canonicalSources,
      );
    }
  });

  it('routes every authority invalidation vocabulary to the child summary', () => {
    expect(featureIntegrationManifest.children.realtimeEntities).toEqual(
      expect.arrayContaining([
        'release_authorization',
        'release_rule',
        'consent',
        'child_authority_head',
      ]),
    );
  });

  it('keeps every mounted staff room-operation consumer on the 0041 invalidation lane', () => {
    const consumers = [
      'staff-room',
      'staff-attendance',
      'staff-daily-care',
      'staff-medications',
      'staff-incidents',
      'staff-daily-close',
      'staff-clock',
      'staff-rota-view',
    ] as const;
    const canonicalRoomOperationEntities = [
      'attendance_day',
      'staff_shift',
      'staff_schedule',
      'staff_coverage_target',
      'organization_membership',
      'facility',
      'room',
      'staff_room_presence',
      'room_operational_exception',
    ] as const;
    for (const id of consumers) {
      expect(featureIntegrationManifest[id].realtimeEntities, id).toEqual(
        expect.arrayContaining([...canonicalRoomOperationEntities]),
      );
    }
    expect(featureIntegrationManifest['staff-room'].produces).toContain(
      'staff_room_presence',
    );
    expect(featureIntegrationManifest['staff-clock'].produces).toContain(
      'staff_room_presence',
    );
  });

  it('makes every consequential producer-to-consumer edge executable', () => {
    for (const edge of crossFeatureDependencies) {
      expect(edge.reason.length).toBeGreaterThan(30);
      expect(featureIntegrationManifest[edge.producer].produces).toContain(edge.entity);
      for (const consumer of edge.consumers) {
        expect(
          featureIntegrationManifest[consumer].realtimeEntities,
          `${consumer} must canonically refresh after ${edge.producer} changes ${edge.entity}`,
        ).toContain(edge.entity);
      }
      expect(downstreamConsumersFor(edge.entity)).toEqual(
        expect.arrayContaining([...edge.consumers]),
      );
    }
  });

  it('distinguishes quiet synchronization from human-attention work', () => {
    for (const [id, contract] of Object.entries(featureIntegrationManifest) as Array<[
      IntegrationId,
      FeatureIntegrationContract,
    ]>) {
      expect(contract.realtimeEntities.length, `${id} needs canonical invalidations`).toBeGreaterThan(0);
      expect(contract.canonicalSources.length, `${id} needs canonical sources`).toBeGreaterThan(0);
      expect(contract.attention.reasons.length === 0).toBe(
        contract.attention.exactDestinations.length === 0,
      );
      for (const destination of contract.attention.exactDestinations) {
        expect(destination.startsWith('/') || /^[a-z][a-z_]+$/.test(destination)).toBe(true);
        expect(destination).not.toMatch(/^https?:|^\/\//);
      }
    }
  });
});
