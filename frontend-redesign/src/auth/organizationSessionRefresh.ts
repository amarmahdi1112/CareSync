import {
  ApiError,
  type ApiUser,
  type OrganizationChoice,
  type OrganizationRecord,
} from '../api/client';

export interface OrganizationSessionFacts {
  organization: OrganizationRecord;
  organizationChoices: OrganizationChoice[];
}

/**
 * Reconcile the two canonical organization reads against the already-confirmed
 * authenticated boundary. A quiet display refresh may update names and other
 * organization facts, but it must never silently change tenant, membership, or
 * role authority.
 */
export function reconcileOrganizationSessionFacts(
  user: ApiUser,
  currentOrganization: OrganizationRecord,
  organizationChoices: readonly OrganizationChoice[],
  refreshedOrganization: OrganizationRecord,
): OrganizationSessionFacts {
  const expectedOrganizationId = user.organization_id;
  if (!expectedOrganizationId || currentOrganization.id !== expectedOrganizationId) {
    throw new ApiError(403, 'The authenticated organization boundary is not confirmed.');
  }
  if (refreshedOrganization.id !== expectedOrganizationId) {
    throw new ApiError(403, 'The organization refresh crossed the authenticated boundary.');
  }

  const activeChoice = organizationChoices.find(
    (choice) => choice.organization_id === expectedOrganizationId,
  );
  if (!activeChoice) {
    throw new ApiError(403, 'The active organization is no longer available to this identity.');
  }
  if (
    activeChoice.membership_id !== user.membership_id
    || activeChoice.role_key !== user.role.key
  ) {
    throw new ApiError(403, 'Organization authority changed and must be authenticated again.');
  }

  return {
    organization: refreshedOrganization,
    organizationChoices: organizationChoices.map((choice) => (
      choice.organization_id === expectedOrganizationId
        ? { ...choice, organization_name: refreshedOrganization.name }
        : { ...choice }
    )),
  };
}

export function isOrganizationSessionBoundaryError(error: unknown): boolean {
  return error instanceof ApiError && [401, 403, 409].includes(error.status);
}
