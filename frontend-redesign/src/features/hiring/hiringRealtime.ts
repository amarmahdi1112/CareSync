import {
  hiringApi,
  type HiringWorkspace,
} from './hiringApi';
import {
  marketplaceApi,
  type CredentialNotification,
  type DiscoverableCandidate,
} from './marketplaceApi';

export interface HiringRealtimeSnapshot {
  workspace: HiringWorkspace;
  credentialNotifications: CredentialNotification[];
  discoverable: DiscoverableCandidate[] | null;
}

interface HiringRealtimeDependencies {
  workspace: (organizationId: string) => Promise<HiringWorkspace>;
  credentialNotifications: () => Promise<CredentialNotification[]>;
  searchCandidates: (city: string) => Promise<DiscoverableCandidate[]>;
}

const dependencies: HiringRealtimeDependencies = {
  workspace: (organizationId) => hiringApi.workspace(organizationId),
  credentialNotifications: () => marketplaceApi.credentialNotifications(),
  searchCandidates: (city) => marketplaceApi.searchCandidates(city),
};

/**
 * Rebuild the complete mounted employer view before its organization-stream
 * cursor advances. Candidate discovery is conditional because it is a public,
 * consent-based projection rather than part of the tenant ATS workspace.
 */
export async function fetchHiringRealtimeSnapshot(
  organizationId: string,
  discoverCity: string | null,
  load: HiringRealtimeDependencies = dependencies,
): Promise<HiringRealtimeSnapshot> {
  const [workspace, credentialNotifications, discoverable] = await Promise.all([
    load.workspace(organizationId),
    load.credentialNotifications(),
    discoverCity === null
      ? Promise.resolve(null)
      : load.searchCandidates(discoverCity),
  ]);
  return { workspace, credentialNotifications, discoverable };
}
