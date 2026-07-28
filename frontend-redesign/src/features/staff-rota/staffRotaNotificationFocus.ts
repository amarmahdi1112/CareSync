import { apiRequest } from '../../api/client';
import { isSafeNotificationTargetId } from '../notifications/notificationTarget';

export const STAFF_ROTA_FOCUS_ENTITY_TYPES = [
  'staff_availability',
  'staff_time_off',
  'staff_rotation_pattern',
  'staff_open_shift',
  'staff_open_shift_engagement',
  'staff_substitute_profile',
  'staff_shift_swap',
] as const;

export type StaffRotaFocusEntityType = (typeof STAFF_ROTA_FOCUS_ENTITY_TYPES)[number];

export interface StaffRotaNotificationRequest {
  entityType: StaffRotaFocusEntityType;
  entityId: string;
}

export interface StaffRotaActionTarget extends StaffRotaNotificationRequest {
  organizationId: string;
  facilityId: string;
  startsAt: string | null;
  parentEntityId: string | null;
  membershipId: string | null;
  visible: boolean;
}

export type StaffRotaNotificationRequestResult =
  | { status: 'none'; request: null }
  | { status: 'invalid'; request: null }
  | { status: 'available'; request: StaffRotaNotificationRequest };

const entityTypes = new Set<string>(STAFF_ROTA_FOCUS_ENTITY_TYPES);
const ACTION_TARGET_KEYS = new Set([
  'organization_id',
  'entity_type',
  'entity_id',
  'facility_id',
  'starts_at',
  'parent_entity_id',
  'membership_id',
  'visible',
]);

export function parseStaffRotaNotificationRequest(
  searchParams: URLSearchParams,
): StaffRotaNotificationRequestResult {
  const focusValues = searchParams.getAll('focus');
  const recordValues = searchParams.getAll('record');
  if (!focusValues.length && !recordValues.length) return { status: 'none', request: null };
  if (focusValues.length !== 1 || recordValues.length !== 1) return { status: 'invalid', request: null };
  const entityType = focusValues[0]!;
  const entityId = recordValues[0]!;
  if (!entityTypes.has(entityType) || !isSafeNotificationTargetId(entityId)) {
    return { status: 'invalid', request: null };
  }
  return {
    status: 'available',
    request: { entityType: entityType as StaffRotaFocusEntityType, entityId },
  };
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The server returned an invalid staff-rota action target.');
  }
  const row = value as Record<string, unknown>;
  const keys = Object.keys(row);
  if (
    keys.length !== ACTION_TARGET_KEYS.size ||
    keys.some((key) => !ACTION_TARGET_KEYS.has(key)) ||
    [...ACTION_TARGET_KEYS].some((key) => !Object.hasOwn(row, key))
  ) {
    throw new Error('The server returned an invalid staff-rota action target.');
  }
  return row;
}

function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || !isSafeNotificationTargetId(value)) {
    throw new Error(`The server returned an invalid ${label}.`);
  }
  return value;
}

function nullableText(value: unknown, label: string): string | null {
  return value == null ? null : text(value, label);
}

function nullableTimestamp(value: unknown): string | null {
  const result = nullableText(value, 'staff-rota target time');
  if (result && Number.isNaN(Date.parse(result))) throw new Error('The server returned an invalid staff-rota target time.');
  return result;
}

export function parseStaffRotaActionTarget(
  value: unknown,
  request: StaffRotaNotificationRequest,
  organizationId: string,
): StaffRotaActionTarget {
  const row = object(value);
  const entityType = text(row.entity_type, 'staff-rota target entity type');
  const entityId = text(row.entity_id, 'staff-rota target entity id');
  const targetOrganizationId = text(row.organization_id, 'staff-rota target organization id');
  const visible = row.visible;
  if (!entityTypes.has(entityType) || typeof visible !== 'boolean') {
    throw new Error('The server returned an unsupported staff-rota action target.');
  }
  const result: StaffRotaActionTarget = {
    entityType: entityType as StaffRotaFocusEntityType,
    entityId,
    organizationId: targetOrganizationId,
    facilityId: text(row.facility_id, 'staff-rota target facility id'),
    startsAt: nullableTimestamp(row.starts_at),
    parentEntityId: nullableText(row.parent_entity_id, 'staff-rota parent target id'),
    membershipId: nullableText(row.membership_id, 'staff-rota membership target id'),
    visible,
  };
  if (
    result.organizationId !== organizationId ||
    result.entityType !== request.entityType ||
    result.entityId !== request.entityId
  ) {
    throw new Error('The staff-rota action target crossed its requested tenant or record boundary.');
  }
  if (
    (result.entityType === 'staff_open_shift_engagement' && (!result.parentEntityId || !result.membershipId || !result.startsAt)) ||
    (result.entityType === 'staff_substitute_profile' && !result.membershipId) ||
    (['staff_availability', 'staff_time_off'].includes(result.entityType) && !result.membershipId) ||
    (['staff_time_off', 'staff_open_shift', 'staff_shift_swap'].includes(result.entityType) && !result.startsAt) ||
    (result.entityType !== 'staff_open_shift_engagement' && result.parentEntityId !== null)
  ) {
    throw new Error('The server returned incomplete or inconsistent staff-rota target linkage.');
  }
  return result;
}

export async function resolveStaffRotaActionTarget(
  request: StaffRotaNotificationRequest,
  organizationId: string,
  signal?: AbortSignal,
): Promise<StaffRotaActionTarget> {
  const value = await apiRequest<unknown>(
    `/staff-workforce/action-target/${encodeURIComponent(request.entityType)}/${encodeURIComponent(request.entityId)}`,
    { signal },
  );
  return parseStaffRotaActionTarget(value, request, organizationId);
}
