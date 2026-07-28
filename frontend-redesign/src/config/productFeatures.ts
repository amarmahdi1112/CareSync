/**
 * CareSync's product-stage boundary.
 *
 * A feature stays in this catalog when it is deferred so its source code and
 * eventual release stage remain explicit. `availability` is the release
 * switch; changing navigation alone can never accidentally expose a module.
 */
export type ProductStage = 'basic' | 'intermediate' | 'advanced';
export type FeatureAudience = 'public' | 'authenticated';
export type FeatureAvailability = 'enabled' | 'planned' | 'deferred';
export type NavigationPlacement = 'primary' | 'utility' | 'none';

export type FeatureId =
  | 'landing'
  | 'login'
  | 'registration'
  | 'onboarding'
  | 'dashboard'
  | 'admissions'
  | 'today'
  | 'families'
  | 'children'
  | 'rooms'
  | 'attendance'
  | 'medications'
  | 'incidents'
  | 'staff'
  | 'staff-rota'
  | 'hiring'
  | 'billing'
  | 'transport-registry'
  | 'settings'
  | 'support'
  | 'claims'
  | 'data-vault'
  | 'documents'
  | 'activity'
  | 'scheduling'
  | 'ai-assistance';

export interface ProductFeature {
  id: FeatureId;
  label: string;
  path: string;
  stage: ProductStage;
  audience: FeatureAudience;
  availability: FeatureAvailability;
  navigation: NavigationPlacement;
  navigationGroup?: 'Command' | 'Care operations' | 'Administration';
  description: string;
  keywords?: string[];
  requiredPermissions?: readonly string[];
  requiredPermissionMode?: 'any' | 'all';
  /** Runtime-controlled features stay absent until their server capability is confirmed. */
  runtimeCapability?: 'transport_registry' | 'billing_ledger';
  status: 'live' | 'preview' | 'migrating' | 'planned';
}

export const ACTIVE_PRODUCT_STAGE: ProductStage = 'basic';

export const productFeatures = [
  { id: 'landing', label: 'CareSync', path: '/', stage: 'basic', audience: 'public', availability: 'enabled', navigation: 'none', description: 'Public product website', status: 'live' },
  { id: 'login', label: 'Sign in', path: '/login', stage: 'basic', audience: 'public', availability: 'enabled', navigation: 'none', description: 'Secure organization access', status: 'live' },
  { id: 'registration', label: 'Register organization', path: '/register', stage: 'basic', audience: 'public', availability: 'enabled', navigation: 'none', description: 'Create a CareSync organization', status: 'live' },
  { id: 'onboarding', label: 'Organization setup', path: '/onboarding', stage: 'basic', audience: 'public', availability: 'enabled', navigation: 'none', description: 'Guided organization onboarding', status: 'live' },

  { id: 'dashboard', label: 'Dashboard', path: '/dashboard', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Command', description: 'Operational overview', keywords: ['home', 'overview'], status: 'live' },
  { id: 'admissions', label: 'Admissions & intake', path: '/admissions', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Command', description: 'Application decisions, waitlist, offers, conversion, and record remediation', keywords: ['admission', 'application', 'intake', 'waitlist', 'offer', 'enrollment', 'placement', 'readiness'], requiredPermissions: ['admissions:read'], status: 'live' },
  { id: 'today', label: 'Today', path: '/today', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Command', description: 'Assigned-room care daybook', keywords: ['care', 'daybook', 'meal', 'bottle', 'nap', 'sleep', 'diaper', 'toilet', 'mood', 'activity'], requiredPermissions: ['care:read', 'child_safety:read'], requiredPermissionMode: 'all', status: 'live' },
  { id: 'families', label: 'Families', path: '/families', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Guardian and household directory', keywords: ['family', 'guardian', 'parent', 'household'], requiredPermissions: ['childcare:read', 'childcare:manage'], status: 'live' },
  { id: 'children', label: 'Children', path: '/children', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Enrollment and child profiles', keywords: ['child', 'student', 'enrollment'], requiredPermissions: ['childcare:read', 'childcare:manage'], status: 'live' },
  { id: 'rooms', label: 'Rooms', path: '/rooms', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Assigned rooms and licensed care capacity', keywords: ['facility', 'program', 'room', 'capacity'], requiredPermissions: ['facility:read', 'facility:manage'], status: 'live' },
  { id: 'attendance', label: 'Attendance', path: '/attendance', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Daily arrivals, departures, and records', keywords: ['check in', 'check out', 'daily', 'presence'], requiredPermissions: ['attendance:read', 'attendance:record', 'attendance:manage'], status: 'live' },
  { id: 'medications', label: 'Medication', path: '/medications', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Consent-evidenced medication plans and administration records', keywords: ['medicine', 'consent', 'dose', 'administration', 'refusal', 'omission'], requiredPermissions: ['medication:read'], status: 'live' },
  { id: 'incidents', label: 'Incidents', path: '/incidents', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Care operations', description: 'Internal incident drafting, review, and external-status tracking', keywords: ['injury', 'illness', 'critical', 'report', 'review'], requiredPermissions: ['incident:read'], status: 'live' },
  { id: 'staff', label: 'Staff & access', path: '/staff', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Administration', description: 'Educator accounts, roles, and room access', keywords: ['team', 'educator', 'invite', 'permission', 'access'], requiredPermissions: ['staff:manage', 'staff:manage_educators'], status: 'live' },
  { id: 'staff-rota', label: 'Staff rota', path: '/staff-rota', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Administration', description: 'Plan staff shifts and reconcile scheduled time with actual clock records', keywords: ['shift', 'schedule', 'rota', 'coverage', 'late', 'clock'], requiredPermissions: ['staff:manage', 'staff:manage_educators'], status: 'live' },
  { id: 'hiring', label: 'Jobs & hiring', path: '/jobs', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Administration', description: 'Listings, applicants, talent discovery, and provisioning', keywords: ['jobs', 'recruiting', 'candidate', 'offer', 'applicant'], requiredPermissions: ['ats:read'], status: 'live' },
  { id: 'billing', label: 'Billing & finance', path: '/billing', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Administration', description: 'Family accounts, invoices, payments, rates, and reconciliation', keywords: ['billing', 'invoice', 'payments', 'receivables', 'rates', 'statements'], requiredPermissions: ['billing:read'], runtimeCapability: 'billing_ledger', status: 'preview' },
  { id: 'transport-registry', label: 'Driver & vehicle registry', path: '/transport-registry', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'primary', navigationGroup: 'Administration', description: 'Evidence and compliance review workspace', keywords: ['driver', 'vehicle', 'licence', 'insurance', 'readiness', 'expiry'], requiredPermissions: ['transport:manage'], runtimeCapability: 'transport_registry', status: 'preview' },
  { id: 'settings', label: 'Settings', path: '/settings', stage: 'basic', audience: 'authenticated', availability: 'enabled', navigation: 'utility', description: 'Organization and account controls', keywords: ['organization', 'profile', 'security'], status: 'live' },

  { id: 'support', label: 'Support', path: '/support', stage: 'intermediate', audience: 'authenticated', availability: 'deferred', navigation: 'utility', description: 'Help and diagnostics', status: 'planned' },
  { id: 'claims', label: 'Claims', path: '/claims', stage: 'intermediate', audience: 'authenticated', availability: 'deferred', navigation: 'primary', navigationGroup: 'Administration', description: 'Funding claim operations', status: 'planned' },
  { id: 'data-vault', label: 'Data vault', path: '/files', stage: 'intermediate', audience: 'authenticated', availability: 'deferred', navigation: 'primary', navigationGroup: 'Administration', description: 'Imports and source files', keywords: ['imports', 'csv', 'pdf', 'files'], status: 'planned' },
  { id: 'documents', label: 'Documents', path: '/letterhead', stage: 'intermediate', audience: 'authenticated', availability: 'deferred', navigation: 'primary', navigationGroup: 'Administration', description: 'Document and letterhead studio', status: 'planned' },
  { id: 'activity', label: 'Activity log', path: '/activity', stage: 'intermediate', audience: 'authenticated', availability: 'deferred', navigation: 'primary', navigationGroup: 'Administration', description: 'Organization audit timeline', keywords: ['audit', 'history'], status: 'planned' },

  { id: 'scheduling', label: 'Scheduling analyzer', path: '/scheduling', stage: 'advanced', audience: 'authenticated', availability: 'deferred', navigation: 'primary', navigationGroup: 'Command', description: 'Advanced attendance and capacity analysis', keywords: ['scheduler', 'v3', 'analyzer'], status: 'preview' },
  { id: 'ai-assistance', label: 'AI assistance', path: '/ai', stage: 'advanced', audience: 'authenticated', availability: 'deferred', navigation: 'none', description: 'Assisted operational workflows', status: 'planned' },
] as const satisfies readonly ProductFeature[];

const stageRank: Record<ProductStage, number> = { basic: 0, intermediate: 1, advanced: 2 };

export function getFeature(featureId: FeatureId): ProductFeature {
  const feature = productFeatures.find((candidate) => candidate.id === featureId);
  if (!feature) throw new Error(`Unknown CareSync feature: ${featureId}`);
  return feature;
}

export function isFeatureEnabled(
  featureId: FeatureId,
  activeStage: ProductStage = ACTIVE_PRODUCT_STAGE,
): boolean {
  const feature = getFeature(featureId);
  return feature.availability === 'enabled' && stageRank[feature.stage] <= stageRank[activeStage];
}

export function findFeatureByPath(pathname: string): ProductFeature | undefined {
  const normalized = pathname !== '/' ? pathname.replace(/\/+$/, '') : pathname;
  return [...productFeatures]
    .sort((left, right) => right.path.length - left.path.length)
    .find((feature) => normalized === feature.path || (feature.path !== '/' && normalized.startsWith(`${feature.path}/`)));
}

export function runtimeCapabilityOf(feature: ProductFeature): ProductFeature['runtimeCapability'] {
  return feature.runtimeCapability;
}

export const basicAuthenticatedFeatures = productFeatures.filter(
  (feature) => feature.audience === 'authenticated' && isFeatureEnabled(feature.id) && !runtimeCapabilityOf(feature),
);

export const runtimeAuthenticatedFeatures = productFeatures.filter(
  (feature) => feature.audience === 'authenticated' && isFeatureEnabled(feature.id) && Boolean(runtimeCapabilityOf(feature)),
);

export const deferredAuthenticatedFeatures = productFeatures.filter(
  (feature) => feature.audience === 'authenticated' && !isFeatureEnabled(feature.id),
);
