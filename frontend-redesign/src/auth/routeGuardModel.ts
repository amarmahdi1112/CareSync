import type { OrganizationRecord } from '../api/client';

export type GuardSessionStatus = 'checking' | 'anonymous' | 'authenticated' | 'unavailable';

const PUBLIC_AUTH_PATHS = new Set(['/login', '/register']);

/** Accept only same-origin application paths from router state. */
export function safeReturnPath(value: unknown, fallback = '/dashboard'): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return fallback;
  const pathname = value.split(/[?#]/, 1)[0].replace(/\/$/, '') || '/';
  return PUBLIC_AUTH_PATHS.has(pathname) ? fallback : value;
}

export type OnboardingState = 'checking' | 'unavailable' | 'required' | 'ready';

export function resolveOnboardingState(
  status: GuardSessionStatus,
  organization: OrganizationRecord | null,
  organizationUnavailable: boolean,
): OnboardingState {
  if (status === 'checking' || (status === 'authenticated' && !organization && !organizationUnavailable)) {
    return 'checking';
  }
  if (status === 'unavailable' || organizationUnavailable) return 'unavailable';
  if (status !== 'authenticated' || !organization) return 'required';

  const explicitState = typeof organization.onboarding_status === 'string'
    ? organization.onboarding_status.toLowerCase()
    : null;
  if (explicitState) return explicitState === 'complete' ? 'ready' : 'required';

  const organizationStatus = typeof organization.status === 'string'
    ? organization.status.toLowerCase()
    : null;
  return organizationStatus === 'active' ? 'ready' : 'required';
}
