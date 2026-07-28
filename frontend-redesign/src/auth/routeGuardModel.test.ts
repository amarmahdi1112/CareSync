import { describe, expect, it } from 'vitest';
import type { OrganizationRecord } from '../api/client';
import { resolveOnboardingState, safeReturnPath } from './routeGuardModel';

const organization = (status: string, onboarding_status?: string): OrganizationRecord => ({
  id: 'org-1',
  name: status === 'active' ? 'Centre' : 'New centre',
  status,
  ...(onboarding_status ? { onboarding_status } : {}),
  verification_status: 'verified',
  verified_at: '2026-07-14T22:30:00Z',
  verification_method: 'temporary_auto_approval',
});

describe('safeReturnPath', () => {
  it('preserves an internal destination including search and hash', () => {
    expect(safeReturnPath('/children?status=active#roster')).toBe('/children?status=active#roster');
  });

  it.each(['https://example.com', '//example.com', '/login', '/register'])('rejects unsafe or recursive destination %s', (value) => {
    expect(safeReturnPath(value)).toBe('/dashboard');
  });
});

describe('resolveOnboardingState', () => {
  it('requires onboarding for a newly registered pending organization', () => {
    expect(resolveOnboardingState('authenticated', organization('pending'), false)).toBe('required');
  });

  it('accepts an active legacy organization or explicit completed onboarding', () => {
    expect(resolveOnboardingState('authenticated', organization('active'), false)).toBe('ready');
    expect(resolveOnboardingState('authenticated', organization('pending', 'complete'), false)).toBe('ready');
  });

  it('does not turn missing organization metadata into an onboarding redirect', () => {
    expect(resolveOnboardingState('authenticated', null, false)).toBe('checking');
    expect(resolveOnboardingState('authenticated', null, true)).toBe('unavailable');
  });
});
