export type ChildrenOrganizationBoundary =
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

/** Prevent roster reads until identity and organization metadata agree exactly. */
export function resolveChildrenOrganizationBoundary({
  sessionStatus,
  identityOrganizationId,
  loadedOrganizationId,
  organizationUnavailable,
}: BoundaryInput): ChildrenOrganizationBoundary {
  if (sessionStatus === 'checking') return 'checking-session';
  if (sessionStatus === 'unavailable') return 'session-unavailable';
  if (sessionStatus === 'anonymous') return 'anonymous';
  if (!identityOrganizationId) return 'organization-required';
  if (organizationUnavailable) return 'organization-unavailable';
  if (!loadedOrganizationId) return 'organization-loading';
  if (loadedOrganizationId !== identityOrganizationId) return 'organization-mismatch';
  return 'ready';
}
