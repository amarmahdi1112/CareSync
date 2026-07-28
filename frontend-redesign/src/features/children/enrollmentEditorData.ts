import {
  fetchChildProfile,
  fetchEnrollmentFacilities,
  type ApiChildProfile,
  type EnrollmentFacilityOption,
} from './childrenApi';

export interface EnrollmentEditorData {
  profile: ApiChildProfile;
  facilities: EnrollmentFacilityOption[];
}

/** Hydrate enrollment management from canonical detail, never a directory preview. */
export async function loadEnrollmentEditorData(
  childId: string,
  organizationId: string,
  signal: AbortSignal,
): Promise<EnrollmentEditorData> {
  const [facilities, profile] = await Promise.all([
    fetchEnrollmentFacilities(organizationId, signal, true),
    fetchChildProfile(childId, organizationId, signal),
  ]);
  return { profile, facilities };
}
