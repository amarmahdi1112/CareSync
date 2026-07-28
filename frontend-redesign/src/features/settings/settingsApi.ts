import { SESSION_TOKEN_KEY, addOrganizationHeader, notifyAuthorizationDenied, type ApiUser } from '../../api/client';
import {
  parseDaycareVerificationFields,
  parseEmailVerificationFields,
  type DaycareVerificationFields,
} from '../../models/verification';
import { parseDeactivationImpact, type DeactivationImpact } from '../../models/deactivationImpact';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');

export interface OrganizationSettingsRecord extends DaycareVerificationFields {
  id: string;
  name: string;
  legal_name: string | null;
  status: string;
  email: string | null;
  phone: string | null;
  timezone: string;
  preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface FacilitySettingsRecord extends DaycareVerificationFields {
  id: string;
  organization_id: string;
  name: string;
  license_number: string | null;
  status: string;
  email: string | null;
  phone: string | null;
  street_address: string | null;
  city: string | null;
  province: string;
  postal_code: string | null;
  timezone: string;
  licensed_capacity: number;
  opening_time: string | null;
  closing_time: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationSettingsRecord {
  organization_id: string;
  timezone: string;
  preferences: Record<string, unknown>;
}

export interface ReleaseCheckoutActivationPrerequisite {
  code: 'runtime_available' | 'activation_command_available' | 'database_writable' | 'facility_active' | 'privileged_actor' | 'authority_records_complete' | 'not_already_activated';
  label: string;
  satisfied: boolean;
}

export interface ReleaseCheckoutActivationStatus {
  schema_version: 'release-checkout-activation-status-v1';
  organization_id: string;
  facility_id: string;
  facility_name: string;
  runtime_available: boolean;
  activation_command_available: boolean;
  database_writable: boolean;
  actor_authorized: boolean;
  facility_active: boolean;
  activated: boolean;
  legacy_checkout_allowed: boolean;
  activation_policy_version: 'normal_verified_release_v1' | null;
  open_enrollment_children: number;
  release_ready_children: number;
  children_needing_authority_review: number;
  prerequisites: ReleaseCheckoutActivationPrerequisite[];
  can_activate: boolean;
  confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT';
}

export interface ReleaseCheckoutActivationCommand {
  schema_version: 'release-checkout-activation-command-v1';
  organization_id: string;
  facility_id: string;
  client_operation_id: string;
  activation_policy_version: 'normal_verified_release_v1';
  authority_records_reviewed: true;
  verification_workflow_reviewed: true;
  legacy_checkout_closure_understood: true;
  irreversible_activation_understood: true;
  confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT';
}

export interface ReleaseCheckoutActivationResponse {
  schema_version: 'release-checkout-activation-v1';
  status: ReleaseCheckoutActivationStatus;
  receipt: {
    organization_id: string;
    facility_id: string;
    activation_id: string;
    client_operation_id: string;
    committed_at: string;
    action_route: '/settings?section=facility';
  };
  replayed: boolean;
}

export interface OrganizationPatch {
  name?: string;
  legal_name?: string | null;
  email?: string | null;
  phone?: string | null;
  timezone?: string;
}

export interface FacilityPatch {
  name?: string;
  license_number?: string | null;
  email?: string | null;
  phone?: string | null;
  street_address?: string | null;
  city?: string | null;
  province?: string;
  postal_code?: string | null;
  timezone?: string;
  licensed_capacity?: number;
  opening_time?: string | null;
  closing_time?: string | null;
  status?: string;
  deactivation_confirmation?: string;
  deactivation_reason?: string;
}

export class SettingsApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'SettingsApiError';
  }
}

function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  return detail.map((item) => {
    if (!item || typeof item !== 'object') return String(item);
    const value = item as { loc?: Array<string | number>; msg?: string };
    return `${value.loc?.slice(1).join('.') || 'request'}: ${value.msg || 'invalid value'}`;
  }).join('; ');
}

function errorMessage(payload: unknown, status: number): string {
  const detail = payload && typeof payload === 'object' && 'detail' in payload
    ? (payload as { detail?: unknown }).detail
    : null;
  const code = detail && typeof detail === 'object' && !Array.isArray(detail) && 'code' in detail
    ? String((detail as { code?: unknown }).code || '')
    : '';
  const releaseActivationMessages: Record<string, string> = {
    release_activation_authority_records_incomplete: 'Complete a current supported release authorization for every active or paused enrolled child before activation.',
    release_activation_already_active: 'Verified release checkout is already permanently active for this facility.',
    release_activation_database_read_only: 'Database writes are disabled, so this facility cannot be activated.',
    release_activation_facility_inactive: 'Change the facility to Active before enabling verified release checkout.',
    release_activation_facility_mismatch: 'The activation request did not match the selected facility.',
    release_activation_facility_not_found: 'The selected facility is unavailable in this organization.',
    release_activation_forbidden: 'Only an active owner or administrator can control verified release activation.',
    release_activation_prerequisites_incomplete: 'Resolve every activation prerequisite before continuing.',
    release_activation_scope_mismatch: 'The activation request did not match the selected organization.',
    release_activation_unavailable: 'The verified release activation command is not available in this runtime.',
    operation_reused: 'This activation operation was already used for a different request. Start a fresh activation attempt.',
  };
  if (releaseActivationMessages[code]) return releaseActivationMessages[code];
  if (status === 401) return 'Your session expired. Sign in again to continue.';
  if (status === 403) return 'Your role does not permit this organization or facility change. Profile and password controls remain self-service.';
  if (status === 409) return 'These settings conflict with a newer or existing record. Reload and try again.';
  const validation = validationMessage(detail);
  if (validation) return validation;
  if (typeof detail === 'string') return detail;
  return `Settings request failed (${status}).`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token) throw new SettingsApiError(401, 'A signed-in CareSync account is required.');
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  addOrganizationHeader(headers);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401) window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    if (response.status === 403) notifyAuthorizationDenied();
    throw new SettingsApiError(response.status, errorMessage(payload, response.status));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new SettingsApiError(0, `The server returned an invalid ${label} response.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new SettingsApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string') throw new SettingsApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function requiredBoolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new SettingsApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function nonNegativeInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || Number(value) < 0) throw new SettingsApiError(0, `The server returned an invalid ${label}.`);
  return Number(value);
}

function preferences(value: unknown): Record<string, unknown> {
  return object(value, 'settings preferences');
}

const invalidVerification = (message: string): never => {
  throw new SettingsApiError(0, message);
};

export function parseOrganizationSettings(value: unknown): OrganizationSettingsRecord {
  const data = object(value, 'organization');
  return {
    id: requiredString(data.id, 'organization id'),
    name: requiredString(data.name, 'organization name'),
    legal_name: nullableString(data.legal_name, 'legal name'),
    status: requiredString(data.status, 'organization status'),
    email: nullableString(data.email, 'organization email'),
    phone: nullableString(data.phone, 'organization phone'),
    timezone: requiredString(data.timezone, 'organization timezone'),
    preferences: preferences(data.preferences),
    created_at: requiredString(data.created_at, 'organization created time'),
    updated_at: requiredString(data.updated_at, 'organization updated time'),
    ...parseDaycareVerificationFields(data, 'organization', invalidVerification),
  };
}

export function parseFacilitySettings(value: unknown): FacilitySettingsRecord {
  const data = object(value, 'facility');
  if (!Number.isInteger(data.licensed_capacity) || Number(data.licensed_capacity) < 0) {
    throw new SettingsApiError(0, 'The server returned an invalid licensed capacity.');
  }
  return {
    id: requiredString(data.id, 'facility id'),
    organization_id: requiredString(data.organization_id, 'facility organization id'),
    name: requiredString(data.name, 'facility name'),
    license_number: nullableString(data.license_number, 'facility license number'),
    status: requiredString(data.status, 'facility status'),
    email: nullableString(data.email, 'facility email'),
    phone: nullableString(data.phone, 'facility phone'),
    street_address: nullableString(data.street_address, 'facility street address'),
    city: nullableString(data.city, 'facility city'),
    province: requiredString(data.province, 'facility province'),
    postal_code: nullableString(data.postal_code, 'facility postal code'),
    timezone: requiredString(data.timezone, 'facility timezone'),
    licensed_capacity: Number(data.licensed_capacity),
    opening_time: nullableString(data.opening_time, 'facility opening time'),
    closing_time: nullableString(data.closing_time, 'facility closing time'),
    created_at: requiredString(data.created_at, 'facility created time'),
    updated_at: requiredString(data.updated_at, 'facility updated time'),
    ...parseDaycareVerificationFields(data, 'facility', invalidVerification),
  };
}

export function parseApplicationSettings(value: unknown): ApplicationSettingsRecord {
  const data = object(value, 'application settings');
  return {
    organization_id: requiredString(data.organization_id, 'settings organization id'),
    timezone: requiredString(data.timezone, 'settings timezone'),
    preferences: preferences(data.preferences),
  };
}

const RELEASE_ACTIVATION_PREREQUISITES = new Set([
  'runtime_available',
  'activation_command_available',
  'database_writable',
  'facility_active',
  'privileged_actor',
  'authority_records_complete',
  'not_already_activated',
]);

export function parseReleaseCheckoutActivationStatus(value: unknown): ReleaseCheckoutActivationStatus {
  const data = object(value, 'release checkout activation status');
  if (data.schema_version !== 'release-checkout-activation-status-v1') throw new SettingsApiError(0, 'The server returned an unsupported release checkout activation status.');
  if (data.activation_policy_version !== null && data.activation_policy_version !== 'normal_verified_release_v1') throw new SettingsApiError(0, 'The server returned an invalid release checkout activation policy.');
  if (data.confirmation_text !== 'ACTIVATE VERIFIED RELEASE CHECKOUT') throw new SettingsApiError(0, 'The server returned an invalid release checkout confirmation.');
  if (!Array.isArray(data.prerequisites)) throw new SettingsApiError(0, 'The server returned invalid release checkout prerequisites.');
  const prerequisites = data.prerequisites.map((item) => {
    const prerequisite = object(item, 'release checkout prerequisite');
    const code = requiredString(prerequisite.code, 'release checkout prerequisite code');
    if (!RELEASE_ACTIVATION_PREREQUISITES.has(code)) throw new SettingsApiError(0, 'The server returned an unknown release checkout prerequisite.');
    return {
      code: code as ReleaseCheckoutActivationPrerequisite['code'],
      label: requiredString(prerequisite.label, 'release checkout prerequisite label'),
      satisfied: requiredBoolean(prerequisite.satisfied, 'release checkout prerequisite state'),
    };
  });
  if (new Set(prerequisites.map((item) => item.code)).size !== prerequisites.length) throw new SettingsApiError(0, 'The server returned duplicate release checkout prerequisites.');
  const status: ReleaseCheckoutActivationStatus = {
    schema_version: 'release-checkout-activation-status-v1',
    organization_id: requiredString(data.organization_id, 'release checkout organization id'),
    facility_id: requiredString(data.facility_id, 'release checkout facility id'),
    facility_name: requiredString(data.facility_name, 'release checkout facility name'),
    runtime_available: requiredBoolean(data.runtime_available, 'release checkout runtime state'),
    activation_command_available: requiredBoolean(data.activation_command_available, 'release checkout activation command state'),
    database_writable: requiredBoolean(data.database_writable, 'release checkout database state'),
    actor_authorized: requiredBoolean(data.actor_authorized, 'release checkout actor state'),
    facility_active: requiredBoolean(data.facility_active, 'release checkout facility state'),
    activated: requiredBoolean(data.activated, 'release checkout activation state'),
    legacy_checkout_allowed: requiredBoolean(data.legacy_checkout_allowed, 'legacy checkout state'),
    activation_policy_version: data.activation_policy_version as ReleaseCheckoutActivationStatus['activation_policy_version'],
    open_enrollment_children: nonNegativeInteger(data.open_enrollment_children, 'open enrollment child count'),
    release_ready_children: nonNegativeInteger(data.release_ready_children, 'release-ready child count'),
    children_needing_authority_review: nonNegativeInteger(data.children_needing_authority_review, 'authority-review child count'),
    prerequisites,
    can_activate: requiredBoolean(data.can_activate, 'release checkout activation eligibility'),
    confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT',
  };
  if (status.release_ready_children > status.open_enrollment_children || status.children_needing_authority_review !== status.open_enrollment_children - status.release_ready_children) throw new SettingsApiError(0, 'The server returned inconsistent release checkout child readiness.');
  if (status.activated !== Boolean(status.activation_policy_version) || (status.activated && status.legacy_checkout_allowed)) throw new SettingsApiError(0, 'The server returned an inconsistent release checkout activation state.');
  if (status.can_activate !== status.prerequisites.every((item) => item.satisfied)) throw new SettingsApiError(0, 'The server returned inconsistent release checkout prerequisites.');
  return status;
}

export function parseReleaseCheckoutActivationResponse(value: unknown): ReleaseCheckoutActivationResponse {
  const data = object(value, 'release checkout activation');
  if (data.schema_version !== 'release-checkout-activation-v1') throw new SettingsApiError(0, 'The server returned an unsupported release checkout activation response.');
  const receipt = object(data.receipt, 'release checkout activation receipt');
  if (receipt.action_route !== '/settings?section=facility') throw new SettingsApiError(0, 'The server returned an unsafe release checkout activation destination.');
  if (typeof data.replayed !== 'boolean') throw new SettingsApiError(0, 'The server returned an invalid release checkout replay state.');
  const result: ReleaseCheckoutActivationResponse = {
    schema_version: 'release-checkout-activation-v1',
    status: parseReleaseCheckoutActivationStatus(data.status),
    receipt: {
      organization_id: requiredString(receipt.organization_id, 'release checkout receipt organization id'),
      facility_id: requiredString(receipt.facility_id, 'release checkout receipt facility id'),
      activation_id: requiredString(receipt.activation_id, 'release checkout activation id'),
      client_operation_id: requiredString(receipt.client_operation_id, 'release checkout operation id'),
      committed_at: requiredString(receipt.committed_at, 'release checkout activation time'),
      action_route: '/settings?section=facility',
    },
    replayed: data.replayed,
  };
  if (result.receipt.organization_id !== result.status.organization_id || result.receipt.facility_id !== result.status.facility_id || !result.status.activated) throw new SettingsApiError(0, 'The server returned an inconsistent release checkout activation receipt.');
  return result;
}

export function parseProfile(value: unknown): ApiUser {
  const data = object(value, 'profile');
  const role = object(data.role, 'profile role');
  if (!Array.isArray(role.permissions) || role.permissions.some((item) => typeof item !== 'string')) {
    throw new SettingsApiError(0, 'The server returned invalid profile permissions.');
  }
  if (typeof data.is_active !== 'boolean') throw new SettingsApiError(0, 'The server returned an invalid profile status.');
  const membershipStatus = requiredString(data.membership_status, 'profile membership status');
  if (!['invited', 'active', 'suspended', 'revoked'].includes(membershipStatus)) throw new SettingsApiError(0, 'The server returned an invalid profile membership status.');
  const assignedFacilityIds = data.assigned_facility_ids;
  const assignedRoomIds = data.assigned_room_ids;
  if (!Array.isArray(assignedFacilityIds) || assignedFacilityIds.some((item) => typeof item !== 'string' || !item.trim())) throw new SettingsApiError(0, 'The server returned invalid profile facility assignments.');
  if (!Array.isArray(assignedRoomIds) || assignedRoomIds.some((item) => typeof item !== 'string' || !item.trim())) throw new SettingsApiError(0, 'The server returned invalid profile room assignments.');
  return {
    id: requiredString(data.id, 'profile id'),
    email: requiredString(data.email, 'profile email'),
    first_name: requiredString(data.first_name, 'profile first name'),
    last_name: requiredString(data.last_name, 'profile last name'),
    organization_id: requiredString(data.organization_id, 'profile organization id'),
    role: { id: requiredString(role.id, 'profile role id'), key: requiredString(role.key, 'profile role key'), name: requiredString(role.name, 'profile role name'), permissions: [...role.permissions] as string[] },
    membership_id: requiredString(data.membership_id, 'profile membership id'),
    membership_status: membershipStatus as ApiUser['membership_status'],
    assigned_facility_ids: [...new Set(assignedFacilityIds as string[])],
    assigned_room_ids: [...new Set(assignedRoomIds as string[])],
    is_active: data.is_active,
    ...parseEmailVerificationFields(data, invalidVerification),
  };
}

function assertOrganizationId(actual: string, expected: string, label: string): void {
  if (actual !== expected) throw new SettingsApiError(0, `${label} was returned outside the active organization boundary.`);
}

async function facilities(signal?: AbortSignal): Promise<FacilitySettingsRecord[]> {
  const value = await request<unknown>('/facilities', { signal });
  if (!Array.isArray(value)) throw new SettingsApiError(0, 'The server returned an invalid facilities response.');
  return value.map(parseFacilitySettings);
}

export const settingsApi = {
  organization: async (signal?: AbortSignal) => parseOrganizationSettings(await request<unknown>('/organization', { signal })),
  updateOrganization: async (payload: OrganizationPatch, organizationId: string) => {
    const value = parseOrganizationSettings(await request<unknown>('/organization', { method: 'PATCH', body: JSON.stringify(payload) }));
    assertOrganizationId(value.id, organizationId, 'Organization settings');
    return value;
  },
  facilities,
  facility: async (id: string, organizationId: string, signal?: AbortSignal) => {
    const value = parseFacilitySettings(await request<unknown>(`/facilities/${encodeURIComponent(id)}`, { signal }));
    assertOrganizationId(value.organization_id, organizationId, 'The facility');
    if (value.id !== id) throw new SettingsApiError(0, 'The server returned a different facility.');
    return value;
  },
  facilityDeactivationImpact: async (id: string, organizationId: string, signal?: AbortSignal): Promise<DeactivationImpact> => parseDeactivationImpact(
    await request<unknown>(`/facilities/${encodeURIComponent(id)}/deactivation-impact`, { signal }),
    { organizationId, entityType: 'facility', entityId: id },
  ),
  updateFacility: async (id: string, payload: FacilityPatch, organizationId: string) => {
    const value = parseFacilitySettings(await request<unknown>(`/facilities/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) }));
    assertOrganizationId(value.organization_id, organizationId, 'The facility');
    if (value.id !== id) throw new SettingsApiError(0, 'The server returned a different facility.');
    return value;
  },
  settings: async (signal?: AbortSignal) => parseApplicationSettings(await request<unknown>('/settings', { signal })),
  updateSettings: async (payload: { timezone: string; preferences: Record<string, unknown> }, organizationId: string) => {
    const value = parseApplicationSettings(await request<unknown>('/settings', { method: 'PATCH', body: JSON.stringify(payload) }));
    assertOrganizationId(value.organization_id, organizationId, 'Application settings');
    return value;
  },
  updateProfile: async (payload: { first_name: string; last_name: string; email: string }, organizationId: string) => {
    const value = parseProfile(await request<unknown>('/auth/me', { method: 'PATCH', body: JSON.stringify(payload) }));
    assertOrganizationId(value.organization_id || '', organizationId, 'The profile');
    return value;
  },
  profile: async (signal?: AbortSignal) => parseProfile(await request<unknown>('/auth/me', { signal })),
  changePassword: (payload: { current_password: string; new_password: string }) => request<void>('/auth/change-password', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  releaseCheckoutActivationStatus: async (facilityId: string, organizationId: string, signal?: AbortSignal) => {
    const value = parseReleaseCheckoutActivationStatus(await request<unknown>(`/facilities/${encodeURIComponent(facilityId)}/release-checkout-activation`, { signal }));
    assertOrganizationId(value.organization_id, organizationId, 'Release checkout activation');
    if (value.facility_id !== facilityId) throw new SettingsApiError(0, 'The server returned release checkout activation for a different facility.');
    return value;
  },
  activateReleaseCheckout: async (facilityId: string, payload: ReleaseCheckoutActivationCommand, organizationId: string) => {
    const value = parseReleaseCheckoutActivationResponse(await request<unknown>(`/facilities/${encodeURIComponent(facilityId)}/release-checkout-activation`, { method: 'POST', body: JSON.stringify(payload) }));
    assertOrganizationId(value.status.organization_id, organizationId, 'Release checkout activation');
    if (value.status.facility_id !== facilityId || value.receipt.facility_id !== facilityId || value.receipt.client_operation_id !== payload.client_operation_id) throw new SettingsApiError(0, 'The server returned release checkout activation for a different request.');
    return value;
  },
};
