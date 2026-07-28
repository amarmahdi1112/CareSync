import type { ComponentType, SVGProps } from 'react';
import {
  BuildingOffice2Icon,
  BriefcaseIcon,
  CalendarDaysIcon,
  ClockIcon,
  Cog6ToothIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  IdentificationIcon,
  ExclamationTriangleIcon,
  TruckIcon,
  BeakerIcon,
  BanknotesIcon,
  Squares2X2Icon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import {
  basicAuthenticatedFeatures,
  runtimeAuthenticatedFeatures,
  runtimeCapabilityOf,
  type FeatureId,
  type ProductFeature,
} from '../config/productFeatures';
import { canAccessFeature } from '../auth/accessModel';
import type { ApiUser } from '../api/client';

export type NavigationIcon = ComponentType<SVGProps<SVGSVGElement>>;

export interface NavigationItem {
  id: FeatureId;
  label: string;
  path: string;
  icon: NavigationIcon;
  description: string;
  keywords?: string[];
  status?: 'live' | 'preview' | 'migrating' | 'planned';
}

export interface NavigationGroup {
  label: string;
  items: NavigationItem[];
}

const iconByFeature: Partial<Record<FeatureId, NavigationIcon>> = {
  dashboard: Squares2X2Icon,
  admissions: ClipboardDocumentCheckIcon,
  today: CalendarDaysIcon,
  families: UserGroupIcon,
  children: UsersIcon,
  rooms: BuildingOffice2Icon,
  attendance: ClockIcon,
  medications: BeakerIcon,
  incidents: ExclamationTriangleIcon,
  staff: IdentificationIcon,
  'staff-rota': ClipboardDocumentListIcon,
  hiring: BriefcaseIcon,
  billing: BanknotesIcon,
  'transport-registry': TruckIcon,
  settings: Cog6ToothIcon,
};

function toNavigationItem(
  feature: ProductFeature,
  status: NavigationItem['status'] = feature.status,
): NavigationItem {
  const icon = iconByFeature[feature.id];
  if (!icon) throw new Error(`Visible CareSync feature is missing a navigation icon: ${feature.id}`);
  return {
    id: feature.id,
    label: feature.label,
    path: feature.path,
    icon,
    description: feature.description,
    keywords: feature.keywords ? [...feature.keywords] : undefined,
    status,
  };
}

const authenticatedFeatureCandidates = [...basicAuthenticatedFeatures, ...runtimeAuthenticatedFeatures];
const primaryFeatures = authenticatedFeatureCandidates.filter((feature) => feature.navigation === 'primary');
const groupOrder: NonNullable<ProductFeature['navigationGroup']>[] = ['Command', 'Care operations', 'Administration'];

export interface AuthorizedNavigation {
  groups: NavigationGroup[];
  utility: NavigationItem[];
  all: NavigationItem[];
}

export function buildNavigation(
  user: ApiUser | null | undefined,
  runtimeCapabilities: ReadonlySet<NonNullable<ProductFeature['runtimeCapability']>> = new Set(),
  runtimeStatuses: Readonly<Partial<Record<FeatureId, NavigationItem['status']>>> = {},
): AuthorizedNavigation {
  const visiblePrimary = primaryFeatures.filter((feature) =>
    canAccessFeature(user, feature.id)
    && (!runtimeCapabilityOf(feature) || runtimeCapabilities.has(runtimeCapabilityOf(feature)!)),
  );
  const groups = groupOrder.map((label) => ({
    label,
    items: visiblePrimary
      .filter((feature) => feature.navigationGroup === label)
      .map((feature) => toNavigationItem(feature, runtimeStatuses[feature.id])),
  }))
  .filter((group) => group.items.length > 0);
  const utility = authenticatedFeatureCandidates
    .filter((feature) => feature.navigation === 'utility'
      && canAccessFeature(user, feature.id)
      && (!runtimeCapabilityOf(feature) || runtimeCapabilities.has(runtimeCapabilityOf(feature)!)))
    .map((feature) => toNavigationItem(feature, runtimeStatuses[feature.id]));
  return { groups, utility, all: [...groups.flatMap((group) => group.items), ...utility] };
}

export const allNavigationItems = basicAuthenticatedFeatures
  .filter((feature) => feature.navigation !== 'none' && !runtimeCapabilityOf(feature))
  .map((feature) => toNavigationItem(feature));

export function findNavigationItem(pathname: string, items: readonly NavigationItem[] = allNavigationItems): NavigationItem | undefined {
  return items.find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`));
}

export function searchNavigation(query: string, items: readonly NavigationItem[] = allNavigationItems): NavigationItem[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [...items];
  return items.filter((item) =>
    `${item.label} ${item.description} ${(item.keywords || []).join(' ')}`.toLowerCase().includes(normalized),
  );
}
