import { describe, expect, it } from 'vitest';
import { resolveFamilyOrganizationBoundary } from './familyOrganizationBoundary';

const resolve = (overrides: Partial<Parameters<typeof resolveFamilyOrganizationBoundary>[0]> = {}) => (
  resolveFamilyOrganizationBoundary({
    sessionStatus: 'authenticated',
    identityOrganizationId: 'org-a',
    loadedOrganizationId: 'org-a',
    organizationUnavailable: false,
    ...overrides,
  })
);

describe('family organization boundary', () => {
  it('is ready only when authenticated identity and loaded organization agree', () => {
    expect(resolve()).toBe('ready');
    expect(resolve({ loadedOrganizationId: null })).toBe('organization-loading');
    expect(resolve({ loadedOrganizationId: 'org-b' })).toBe('organization-mismatch');
  });

  it('blocks unavailable session and organization metadata', () => {
    expect(resolve({ sessionStatus: 'unavailable' })).toBe('session-unavailable');
    expect(resolve({ organizationUnavailable: true })).toBe('organization-unavailable');
  });
});
