import { describe, expect, it } from 'vitest';
import { resolveChildrenOrganizationBoundary } from './childrenOrganizationBoundary';

const resolve = (overrides: Partial<Parameters<typeof resolveChildrenOrganizationBoundary>[0]> = {}) => (
  resolveChildrenOrganizationBoundary({
    sessionStatus: 'authenticated',
    identityOrganizationId: 'org-a',
    loadedOrganizationId: 'org-a',
    organizationUnavailable: false,
    ...overrides,
  })
);

describe('children organization boundary', () => {
  it('is ready only for an exact loaded organization match', () => {
    expect(resolve()).toBe('ready');
    expect(resolve({ loadedOrganizationId: null })).toBe('organization-loading');
    expect(resolve({ loadedOrganizationId: 'org-b' })).toBe('organization-mismatch');
  });

  it('blocks all unavailable security metadata states', () => {
    expect(resolve({ sessionStatus: 'unavailable' })).toBe('session-unavailable');
    expect(resolve({ organizationUnavailable: true })).toBe('organization-unavailable');
  });
});
