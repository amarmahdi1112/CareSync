import type { ApiUser } from '../api/client';
import { getFeature, isFeatureEnabled, type FeatureId } from '../config/productFeatures';

export const ACCESS = {
  organizationManage: 'organization:manage',
  facilityRead: 'facility:read',
  facilityManage: 'facility:manage',
  childcareRead: 'childcare:read',
  childcareManage: 'childcare:manage',
  admissionsRead: 'admissions:read',
  admissionsManage: 'admissions:manage',
  admissionsDecide: 'admissions:decide',
  careRosterRead: 'care_roster:read',
  careRead: 'care:read',
  careRecord: 'care:record',
  careCorrect: 'care:correct',
  careCorrectOwn: 'care:correct_own',
  careVoid: 'care:void',
  childSafetyRead: 'child_safety:read',
  attendanceRead: 'attendance:read',
  attendanceRecord: 'attendance:record',
  attendanceCorrect: 'attendance:correct',
  attendanceManage: 'attendance:manage',
  medicationRead: 'medication:read',
  medicationManage: 'medication:manage',
  medicationRecord: 'medication:record',
  medicationCorrect: 'medication:correct',
  medicationCorrectOwn: 'medication:correct_own',
  medicationVoid: 'medication:void',
  incidentRead: 'incident:read',
  incidentCreate: 'incident:create',
  incidentUpdate: 'incident:update',
  incidentUpdateOwn: 'incident:update_own',
  incidentReview: 'incident:review',
  incidentExternalReport: 'incident:external_report',
  staffManage: 'staff:manage',
  staffManageEducators: 'staff:manage_educators',
  atsRead: 'ats:read',
  atsManage: 'ats:manage',
  atsHire: 'ats:hire',
  billingRead: 'billing:read',
  billingManage: 'billing:manage',
  billingIssue: 'billing:issue',
  billingPayments: 'billing:payments',
  billingAdjust: 'billing:adjust',
  billingClose: 'billing:close',
  billingRecover: 'billing:recover',
  transportRead: 'transport:read',
  transportManage: 'transport:manage',
  settingsManage: 'settings:manage',
} as const;

export type AccessPermission = typeof ACCESS[keyof typeof ACCESS];

export function permissionSet(user: ApiUser | null | undefined): ReadonlySet<string> {
  return new Set(user?.role?.permissions || []);
}

export function hasExplicitPermission(
  user: ApiUser | null | undefined,
  permission: string,
): boolean {
  return Boolean(
    user
    && user.membership_status === 'active'
    && permissionSet(user).has(permission),
  );
}

export function hasPermission(user: ApiUser | null | undefined, permission: string): boolean {
  if (!user || user.membership_status !== 'active') return false;
  if (user.role?.key === 'owner') return true;
  const permissions = permissionSet(user);
  if (permissions.has(permission)) return true;
  if (permission.endsWith(':read') && permissions.has(permission.replace(/:read$/, ':manage'))) return true;
  if (permission === ACCESS.attendanceRecord && permissions.has(ACCESS.attendanceManage)) return true;
  if (permission === ACCESS.attendanceCorrect && permissions.has(ACCESS.attendanceManage)) return true;
  return false;
}

export function hasAnyPermission(user: ApiUser | null | undefined, permissions: readonly string[]): boolean {
  return permissions.some((permission) => hasPermission(user, permission));
}

/**
 * Family-authority records are deliberately narrower than ordinary childcare
 * management. Permission aliases must not widen this boundary: only an active
 * organization owner or administrator may even mount the private workspace.
 */
export function canAdministerFamilyAuthority(user: ApiUser | null | undefined): boolean {
  return Boolean(
    user
    && user.membership_status === 'active'
    && (user.role?.key === 'owner' || user.role?.key === 'administrator'),
  );
}

export function canAccessFeature(user: ApiUser | null | undefined, featureId: FeatureId): boolean {
  if (!isFeatureEnabled(featureId)) return false;
  if (featureId === 'billing' && user?.role?.key !== 'owner' && user?.role?.key !== 'administrator') {
    return false;
  }
  const feature = getFeature(featureId);
  // Finance permissions are intentionally literal on both sides of the API.
  // The general owner convenience bypass must never expose a ledger capability
  // that the server has not explicitly granted and certified for this role.
  if (featureId === 'billing') {
    if (!user || user.membership_status !== 'active') return false;
    return Boolean(
      feature.requiredPermissions?.length
      && feature.requiredPermissions.every((permission) => hasExplicitPermission(user, permission)),
    );
  }
  if (!feature.requiredPermissions?.length) return Boolean(user && user.membership_status === 'active');
  if (feature.requiredPermissionMode === 'all') {
    return feature.requiredPermissions.every((permission) => hasPermission(user, permission));
  }
  return hasAnyPermission(user, feature.requiredPermissions);
}

export function isAssignedToFacility(user: ApiUser | null | undefined, facilityId: string): boolean {
  if (!user || user.membership_status !== 'active') return false;
  if (user.role?.key === 'owner' || user.role?.key === 'administrator') return true;
  return user.assigned_facility_ids.includes(facilityId);
}

export function isAssignedToRoom(user: ApiUser | null | undefined, roomId: string): boolean {
  if (!user || user.membership_status !== 'active') return false;
  if (user.role?.key === 'owner' || user.role?.key === 'administrator') return true;
  return user.assigned_room_ids.includes(roomId);
}
