import { describe, expect, it } from 'vitest';
import {
  basicAuthenticatedFeatures,
  deferredAuthenticatedFeatures,
  findFeatureByPath,
  isFeatureEnabled,
  runtimeAuthenticatedFeatures,
} from './productFeatures';

describe('basic product-stage boundary', () => {
  it('exposes only the agreed authenticated foundation', () => {
    expect(basicAuthenticatedFeatures.map((feature) => feature.id)).toEqual([
      'dashboard',
      'admissions',
      'today',
      'families',
      'children',
      'rooms',
      'attendance',
      'medications',
      'incidents',
      'staff',
      'staff-rota',
      'hiring',
      'settings',
    ]);
  });

  it('keeps compiled financial and transport surfaces behind exact runtime capabilities', () => {
    expect(runtimeAuthenticatedFeatures.map((feature) => feature.id)).toEqual(['billing', 'transport-registry']);
    expect(basicAuthenticatedFeatures.some((feature) => feature.id === 'transport-registry')).toBe(false);
    expect(deferredAuthenticatedFeatures.some((feature) => feature.id === 'transport-registry')).toBe(false);
  });

  it.each([
    'support',
    'claims',
    'data-vault',
    'documents',
    'activity',
    'scheduling',
    'ai-assistance',
  ] as const)('keeps %s unavailable during the basic stage', (featureId) => {
    expect(isFeatureEnabled(featureId)).toBe(false);
    expect(deferredAuthenticatedFeatures.some((feature) => feature.id === featureId)).toBe(true);
  });

  it.each(['medications', 'incidents'] as const)('releases %s only through its feature gate', (featureId) => {
    expect(isFeatureEnabled(featureId)).toBe(true);
    expect(deferredAuthenticatedFeatures.some((feature) => feature.id === featureId)).toBe(false);
  });

  it('recognizes nested paths without allowing the root feature to swallow every route', () => {
    expect(findFeatureByPath('/families/household-1')?.id).toBe('families');
    expect(findFeatureByPath('/admissions')?.id).toBe('admissions');
    expect(findFeatureByPath('/scheduling/review')?.id).toBe('scheduling');
    expect(findFeatureByPath('/not-a-feature')).toBeUndefined();
  });
});
