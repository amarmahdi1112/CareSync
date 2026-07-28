export type FamilyOrganizationBoundary =
  | 'checking-session'
  | 'session-unavailable'
  | 'anonymous'
  | 'organization-required'
  | 'organization-loading'
  | 'organization-unavailable'
  | 'organization-mismatch'
  | 'ready';

interface BoundaryInput {
  sessionStatus: 'checking' | 'anonymous' | 'authenticated' | 'unavailable';
  identityOrganizationId: string | null;
  loadedOrganizationId: string | null;
  organizationUnavailable: boolean;
}

/**
 * A family request is allowed only after both independently loaded identity
 * sources agree on the organization boundary.
 */
export function resolveFamilyOrganizationBoundary({
  sessionStatus,
  identityOrganizationId,
  loadedOrganizationId,
  organizationUnavailable,
}: BoundaryInput): FamilyOrganizationBoundary {
  if (sessionStatus === 'checking') return 'checking-session';
  if (sessionStatus === 'unavailable') return 'session-unavailable';
  if (sessionStatus === 'anonymous') return 'anonymous';
  if (!identityOrganizationId) return 'organization-required';
  if (organizationUnavailable) return 'organization-unavailable';
  if (!loadedOrganizationId) return 'organization-loading';
  if (loadedOrganizationId !== identityOrganizationId) return 'organization-mismatch';
  return 'ready';
}
