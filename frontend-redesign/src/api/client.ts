import {
  parseDaycareVerificationFields,
  parseEmailVerificationFields,
  type DaycareVerificationFields,
  type EmailVerificationFields,
} from '../models/verification';

export const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');
export const SESSION_TOKEN_KEY = 'caresync-redesign-token';
export const SELECTED_ORGANIZATION_KEY = 'caresync-redesign-organization';
export const AUTHORIZATION_RECHECK_EVENT = 'caresync-redesign:authorization-recheck';
export function notifyAuthorizationDenied(): void { if (typeof window !== 'undefined') window.dispatchEvent(new Event(AUTHORIZATION_RECHECK_EVENT)); }
export function isSessionBoundaryStorageKey(key: string | null): boolean { return key === SESSION_TOKEN_KEY || key === SELECTED_ORGANIZATION_KEY; }

export interface OrganizationChoice { organization_id: string; organization_name: string; membership_id: string; role_key: string; }
export interface OrganizationChoicesResponse { organizations: OrganizationChoice[]; selection_required: boolean; }
export class OrganizationSelectionRequiredError extends Error {
  constructor(public readonly organizations: OrganizationChoice[]) { super('Choose the organization workspace you want to open.'); this.name = 'OrganizationSelectionRequiredError'; }
}
export function getSelectedOrganizationId(): string | null { return localStorage.getItem(SELECTED_ORGANIZATION_KEY); }
export function saveSelectedOrganizationId(id: string): void { localStorage.setItem(SELECTED_ORGANIZATION_KEY, id); }
export function clearSelectedOrganizationId(): void { localStorage.removeItem(SELECTED_ORGANIZATION_KEY); }
export function addOrganizationHeader(headers: Headers, expectedOrganizationId?: string): Headers {
  const selected = getSelectedOrganizationId();
  if (expectedOrganizationId && selected !== expectedOrganizationId) throw new ApiError(0, 'The requested records do not match the selected organization workspace.');
  if (selected) headers.set('X-Organization-ID', selected);
  return headers;
}

export interface DatabaseHealth {
  connected: boolean;
  integrity: string;
  database_name: string;
  database_filename: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  database: DatabaseHealth;
}

export interface FamilyStats {
  families: number;
  active_families: number;
  children: number;
  active_children: number;
  pending_families: number;
  by_age_group: Record<string, number>;
}

export interface ApiUser extends EmailVerificationFields {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  organization_id: string | null;
  role: { id: string | number; key: string; name: string; permissions: string[] };
  membership_id: string;
  membership_status: 'invited' | 'active' | 'suspended' | 'revoked';
  assigned_facility_ids: string[];
  assigned_room_ids: string[];
  is_active?: boolean;
}

export interface OrganizationRecord extends DaycareVerificationFields {
  id: string;
  name: string;
  status: string;
  timezone?: string;
  onboarding_status?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: ApiUser;
}

export interface RegisterRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  organization_name?: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function getSessionToken(): string | null {
  return localStorage.getItem(SESSION_TOKEN_KEY);
}

export function saveSessionToken(token: string): void {
  localStorage.setItem(SESSION_TOKEN_KEY, token);
}

export function clearSessionToken(): void {
  localStorage.removeItem(SESSION_TOKEN_KEY);
  clearSelectedOrganizationId();
}

function responseObject(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError(0, `The server returned an invalid ${label} response.`);
  }
  return value as Record<string, unknown>;
}

function responseString(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return value;
}

function responseStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || !item.trim())) {
    throw new ApiError(0, `The server returned invalid ${label}.`);
  }
  return [...new Set(value as string[])];
}

const invalidVerification = (message: string): never => {
  throw new ApiError(0, message);
};

export function parseApiUser(value: unknown): ApiUser {
  const data = responseObject(value, 'user');
  const role = responseObject(data.role, 'user role');
  if (!Array.isArray(role.permissions) || role.permissions.some((permission) => typeof permission !== 'string')) {
    throw new ApiError(0, 'The server returned invalid user permissions.');
  }
  if (typeof data.is_active !== 'boolean') {
    throw new ApiError(0, 'The server returned an invalid user status.');
  }
  const roleId = role.id;
  if ((typeof roleId !== 'string' || !roleId.trim()) && typeof roleId !== 'number') {
    throw new ApiError(0, 'The server returned an invalid user role id.');
  }
  const membershipStatus = responseString(data.membership_status, 'membership status');
  if (!['invited', 'active', 'suspended', 'revoked'].includes(membershipStatus)) {
    throw new ApiError(0, 'The server returned an invalid membership status.');
  }
  return {
    id: responseString(data.id, 'user id'),
    email: responseString(data.email, 'user email'),
    first_name: responseString(data.first_name, 'user first name'),
    last_name: responseString(data.last_name, 'user last name'),
    organization_id: responseString(data.organization_id, 'user organization id'),
    role: {
      id: roleId,
      key: responseString(role.key, 'user role key'),
      name: responseString(role.name, 'user role name'),
      permissions: [...role.permissions] as string[],
    },
    membership_id: responseString(data.membership_id, 'membership id'),
    membership_status: membershipStatus as ApiUser['membership_status'],
    assigned_facility_ids: responseStringArray(data.assigned_facility_ids, 'assigned facility ids'),
    assigned_room_ids: responseStringArray(data.assigned_room_ids, 'assigned room ids'),
    is_active: data.is_active,
    ...parseEmailVerificationFields(data, invalidVerification),
  };
}

export function parseOrganizationRecord(value: unknown): OrganizationRecord {
  const data = responseObject(value, 'organization');
  const onboardingStatus = data.onboarding_status;
  const timezone = data.timezone;
  if (onboardingStatus !== undefined && (typeof onboardingStatus !== 'string' || !onboardingStatus.trim())) {
    throw new ApiError(0, 'The server returned an invalid onboarding status.');
  }
  if (timezone !== undefined && (typeof timezone !== 'string' || !timezone.trim())) {
    throw new ApiError(0, 'The server returned an invalid organization timezone.');
  }
  return {
    id: responseString(data.id, 'organization id'),
    name: responseString(data.name, 'organization name'),
    status: responseString(data.status, 'organization operating status'),
    ...(typeof timezone === 'string' ? { timezone } : {}),
    ...(typeof onboardingStatus === 'string' ? { onboarding_status: onboardingStatus } : {}),
    ...parseDaycareVerificationFields(data, 'organization', invalidVerification),
  };
}

export function parseLoginResponse(value: unknown): LoginResponse {
  const data = responseObject(value, 'authentication');
  const tokenType = responseString(data.token_type, 'authentication token type');
  if (tokenType.toLowerCase() !== 'bearer') {
    throw new ApiError(0, 'The server returned an unsupported authentication token type.');
  }
  return {
    access_token: responseString(data.access_token, 'access token'),
    token_type: tokenType,
    user: parseApiUser(data.user),
  };
}
export function parseOrganizationChoices(value: unknown): OrganizationChoicesResponse {
  const data = responseObject(value, 'organization choices');
  if (!Array.isArray(data.organizations) || typeof data.selection_required !== 'boolean') throw new ApiError(0, 'The server returned invalid organization choices.');
  const organizations = data.organizations.map((value) => { const row = responseObject(value, 'organization choice'); const role = responseObject(row.role, 'organization choice role'); return { organization_id: responseString(row.organization_id, 'organization choice id'), organization_name: responseString(row.organization_name, 'organization choice name'), membership_id: responseString(row.membership_id, 'organization membership id'), role_key: responseString(role.key, 'organization role') }; });
  if (new Set(organizations.map((item) => item.organization_id)).size !== organizations.length) throw new ApiError(0, 'The server returned duplicate organization choices.');
  return { organizations, selection_required: data.selection_required };
}

function formatError(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const structured = detail as { message?: unknown; code?: unknown };
      if (typeof structured.message === 'string' && structured.message.trim()) return structured.message;
      if (typeof structured.code === 'string' && structured.code.trim()) return structured.code.replaceAll('_', ' ');
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (!item || typeof item !== 'object') return String(item);
          const typed = item as { loc?: Array<string | number>; msg?: string };
          const location = typed.loc?.slice(1).join('.') || 'request';
          return `${location}: ${typed.msg || 'invalid value'}`;
        })
        .join('; ');
    }
  }
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const structured = payload as { message?: unknown; code?: unknown };
    if (typeof structured.message === 'string' && structured.message.trim()) return structured.message;
    if (typeof structured.code === 'string' && structured.code.trim()) return structured.code.replaceAll('_', ' ');
  }
  return `Request failed (${status})`;
}

export interface ApiRequestOptions extends RequestInit {
  /** Only for optional, side-effect-free probes where a 403 means the capability is unavailable. */
  suppressAuthorizationRecheck?: true;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { suppressAuthorizationRecheck, ...requestOptions } = options;
  const token = getSessionToken();
  const headers = new Headers(requestOptions.headers);
  headers.set('Accept', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (token) addOrganizationHeader(headers);
  if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_URL}${path.startsWith('/') ? path : `/${path}`}`, {
    ...requestOptions,
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (
      response.status === 401
      && getSessionToken()
      && path !== '/auth/login'
      && !(path === '/auth/me' && (!requestOptions.method || requestOptions.method === 'GET'))
    ) {
      window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    }
    if (
      response.status === 403
      && getSessionToken()
      && !suppressAuthorizationRecheck
      && !['/auth/me', '/auth/organizations'].includes(path)
    ) notifyAuthorizationDenied();
    throw new ApiError(response.status, formatError(payload, response.status), payload);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function parseFamilyStats(value: unknown): FamilyStats {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiError(0, 'The server returned an invalid family statistics response.');
  const data = value as Record<string, unknown>;
  const count = (field: string): number => {
    const result = data[field];
    if (!Number.isInteger(result) || Number(result) < 0) throw new ApiError(0, `The server returned an invalid family statistics field (${field}).`);
    return Number(result);
  };
  if (!data.by_age_group || typeof data.by_age_group !== 'object' || Array.isArray(data.by_age_group)) throw new ApiError(0, 'The server returned invalid family age-group statistics.');
  const byAgeGroup = Object.fromEntries(Object.entries(data.by_age_group as Record<string, unknown>).map(([label, result]) => {
    if (!Number.isInteger(result) || Number(result) < 0) throw new ApiError(0, `The server returned an invalid family age-group count (${label}).`);
    return [label, Number(result)];
  }));
  return { families: count('families'), active_families: count('active_families'), children: count('children'), active_children: count('active_children'), pending_families: count('pending_families'), by_age_group: byAgeGroup };
}

export const api = {
  health: (signal?: AbortSignal) => apiRequest<HealthResponse>('/health', { signal }),
  login: async (email: string, password: string, organizationId?: string, signal?: AbortSignal) => {
    try {
      return parseLoginResponse(await apiRequest<unknown>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password, ...(organizationId ? { organization_id: organizationId } : {}) }), signal }));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        const detail = caught.details && typeof caught.details === 'object' && 'detail' in caught.details ? (caught.details as { detail?: unknown }).detail : null;
        if (detail && typeof detail === 'object' && (detail as { code?: unknown }).code === 'organization_selection_required' && Array.isArray((detail as { organizations?: unknown }).organizations)) {
          const choices = (detail as { organizations: unknown[] }).organizations.map((value) => { if (!value || typeof value !== 'object') throw caught; const row = value as Record<string, unknown>; return { organization_id: responseString(row.organization_id, 'organization choice id'), organization_name: responseString(row.organization_name, 'organization choice name'), membership_id: responseString(row.membership_id, 'organization membership id'), role_key: responseString(row.role_key, 'organization role') }; });
          throw new OrganizationSelectionRequiredError(choices);
        }
      }
      throw caught;
    }
  },
  register: async (payload: RegisterRequest, signal?: AbortSignal) =>
    parseLoginResponse(await apiRequest<unknown>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    })),
  me: async (signal?: AbortSignal) => parseApiUser(await apiRequest<unknown>('/auth/me', { signal })),
  organization: async (signal?: AbortSignal) => parseOrganizationRecord(await apiRequest<unknown>('/organization', { signal })),
  organizations: async (signal?: AbortSignal) => parseOrganizationChoices(await apiRequest<unknown>('/auth/organizations', { signal })),
  familyStats: async (signal?: AbortSignal) => parseFamilyStats(await apiRequest<unknown>('/families/stats', { signal })),
};
