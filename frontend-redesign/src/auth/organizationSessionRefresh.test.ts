import { describe, expect, it } from 'vitest';
import {
  ApiError,
  type ApiUser,
  type OrganizationChoice,
  type OrganizationRecord,
} from '../api/client';
import {
  isOrganizationSessionBoundaryError,
  reconcileOrganizationSessionFacts,
} from './organizationSessionRefresh';

const user: ApiUser = {
  id: 'user-a',
  email: 'owner@example.com',
  first_name: 'Owner',
  last_name: 'One',
  organization_id: 'org-a',
  membership_id: 'membership-a',
  membership_status: 'active',
  role: { id: 'role-a', key: 'owner', name: 'Owner', permissions: ['organization:manage'] },
  assigned_facility_ids: [],
  assigned_room_ids: [],
  is_active: true,
  email_verification_status: 'verified',
  email_verified_at: '2026-07-01T12:00:00Z',
  email_verification_method: 'temporary_auto_approval',
};

const organization = (patch: Partial<OrganizationRecord> = {}): OrganizationRecord => ({
  id: 'org-a',
  name: 'Original Care',
  status: 'active',
  timezone: 'America/Edmonton',
  onboarding_status: 'complete',
  verification_status: 'verified',
  verified_at: '2026-07-01T12:00:00Z',
  verification_method: 'temporary_auto_approval',
  ...patch,
});

const choices: OrganizationChoice[] = [
  {
    organization_id: 'org-a',
    organization_name: 'Original Care',
    membership_id: 'membership-a',
    role_key: 'owner',
  },
  {
    organization_id: 'org-b',
    organization_name: 'Other Care',
    membership_id: 'membership-b',
    role_key: 'administrator',
  },
];

describe('quiet organization session refresh', () => {
  it('updates display facts and choices without changing the authenticated authority', () => {
    const refreshed = organization({ name: 'Aurora Childcare', timezone: 'America/Vancouver' });
    const result = reconcileOrganizationSessionFacts(user, organization(), choices, refreshed);

    expect(result.organization).toBe(refreshed);
    expect(result.organizationChoices).toEqual([
      { ...choices[0], organization_name: 'Aurora Childcare' },
      choices[1],
    ]);
    expect(result.organizationChoices).not.toBe(choices);
    expect(choices[0].organization_name).toBe('Original Care');
  });

  it('fails closed when the organization response crosses the selected tenant', () => {
    expect(() => reconcileOrganizationSessionFacts(
      user,
      organization(),
      choices,
      organization({ id: 'org-b' }),
    )).toThrowError(ApiError);
  });

  it.each([
    ['missing active context', choices.slice(1)],
    ['changed membership', [{ ...choices[0], membership_id: 'membership-replaced' }, choices[1]]],
    ['changed role', [{ ...choices[0], role_key: 'administrator' }, choices[1]]],
  ])('fails closed for %s instead of silently changing authority', (_label, nextChoices) => {
    try {
      reconcileOrganizationSessionFacts(user, organization(), nextChoices, organization());
      throw new Error('Expected reconciliation to reject the changed authority.');
    } catch (caught) {
      expect(caught).toBeInstanceOf(ApiError);
      expect((caught as ApiError).status).toBe(403);
    }
  });

  it('distinguishes terminal boundary failures from retryable connectivity errors', () => {
    expect(isOrganizationSessionBoundaryError(new ApiError(401, 'expired'))).toBe(true);
    expect(isOrganizationSessionBoundaryError(new ApiError(403, 'revoked'))).toBe(true);
    expect(isOrganizationSessionBoundaryError(new ApiError(409, 'selection changed'))).toBe(true);
    expect(isOrganizationSessionBoundaryError(new ApiError(500, 'offline'))).toBe(false);
    expect(isOrganizationSessionBoundaryError(new TypeError('network unavailable'))).toBe(false);
  });
});
