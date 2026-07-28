import { SESSION_TOKEN_KEY, addOrganizationHeader, notifyAuthorizationDenied } from '../../api/client';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');

export interface AttendanceIntervalRecord { id: string; sequence: number; checked_in_at: string; checked_out_at: string | null }
export interface AttendanceEventRecord { id: string; event_type: string; occurred_at: string; reason: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null }
export interface AttendanceDayRecord {
  id: string; organization_id: string; facility_id: string; child_id: string; enrollment_id: string; service_date: string; status: 'present' | 'absent'; absence_reason: string | null; notes: string | null; version: number; child_name: string; intervals: AttendanceIntervalRecord[]; events: AttendanceEventRecord[]; created_at: string; updated_at: string;
}
export interface AttendanceRosterRow { child_id: string; child_name: string; profile_photo_url: string | null; enrollment_id: string; room_id: string | null; room_name: string | null; program_name: string | null; attendance_day: AttendanceDayRecord | null }
export interface AttendanceFacility { id: string; organization_id: string; name: string; city: string | null; status: string }
export interface CorrectionMutation { interval_id: string; checked_in_at: string; checked_out_at: string; reason: string }
export type ReleaseCheckoutActivationPrerequisiteCode =
  | 'runtime_available'
  | 'activation_command_available'
  | 'database_writable'
  | 'facility_active'
  | 'privileged_actor'
  | 'authority_records_complete'
  | 'not_already_activated';
export interface AttendanceReleaseCheckoutActivationStatus {
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
  prerequisites: { code: ReleaseCheckoutActivationPrerequisiteCode; label: string; satisfied: boolean }[];
  can_activate: boolean;
  confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT';
}

export class AttendanceApiError extends Error {
  constructor(message: string, public readonly status = 0) { super(message); this.name = 'AttendanceApiError'; }
}

function message(payload: unknown, status: number): string {
  if (status === 401) return 'Your session expired. Sign in again to continue.';
  if (status === 403) return 'Your account cannot change attendance for this organization.';
  if (status === 409) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? (payload as { detail?: unknown }).detail : null;
    return typeof detail === 'string' ? detail : 'Attendance changed in another action. Reload the roster and try again.';
  }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item) => item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)).join('; ');
  }
  return `The attendance request failed (${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token) throw new AttendanceApiError('A signed-in CareSync account is required.', 401);
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json'); headers.set('Authorization', `Bearer ${token}`);
  addOrganizationHeader(headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401) window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    if (response.status === 403) notifyAuthorizationDenied();
    throw new AttendanceApiError(message(payload, response.status), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function object(value: unknown, label: string): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AttendanceApiError(`The server returned an invalid ${label} response.`); return value as Record<string, unknown>; }
function string(value: unknown, label: string): string { if (typeof value !== 'string' || !value) throw new AttendanceApiError(`The server returned an invalid ${label}.`); return value; }
function nullable(value: unknown, label: string): string | null { if (value == null) return null; if (typeof value !== 'string') throw new AttendanceApiError(`The server returned an invalid ${label}.`); return value; }
function integer(value: unknown, label: string, minimum = 0): number { if (!Number.isInteger(value) || Number(value) < minimum) throw new AttendanceApiError(`The server returned an invalid ${label}.`); return Number(value); }
function boolean(value: unknown, label: string): boolean { if (typeof value !== 'boolean') throw new AttendanceApiError(`The server returned an invalid ${label}.`); return value; }
function recordOrNull(value: unknown, label: string): Record<string, unknown> | null { if (value == null) return null; return object(value, label); }
function array<T>(value: unknown, label: string, parser: (item: unknown) => T): T[] { if (!Array.isArray(value)) throw new AttendanceApiError(`The server returned an invalid ${label} response.`); return value.map(parser); }

function parseInterval(value: unknown): AttendanceIntervalRecord {
  const data = object(value, 'attendance interval');
  return { id: string(data.id, 'interval id'), sequence: integer(data.sequence, 'interval sequence', 1), checked_in_at: string(data.checked_in_at, 'check-in time'), checked_out_at: nullable(data.checked_out_at, 'check-out time') };
}
function parseEvent(value: unknown): AttendanceEventRecord {
  const data = object(value, 'attendance event');
  return { id: string(data.id, 'event id'), event_type: string(data.event_type, 'event type'), occurred_at: string(data.occurred_at, 'event time'), reason: nullable(data.reason, 'event reason'), before: recordOrNull(data.before, 'event before state'), after: recordOrNull(data.after, 'event after state') };
}
export function parseAttendanceDay(value: unknown): AttendanceDayRecord {
  const data = object(value, 'attendance day');
  if (data.status !== 'present' && data.status !== 'absent') throw new AttendanceApiError('The server returned an invalid attendance status.');
  return {
    id: string(data.id, 'attendance day id'), organization_id: string(data.organization_id, 'attendance organization'), facility_id: string(data.facility_id, 'attendance facility'), child_id: string(data.child_id, 'attendance child'), enrollment_id: string(data.enrollment_id, 'attendance enrollment'), service_date: string(data.service_date, 'service date'), status: data.status, absence_reason: nullable(data.absence_reason, 'absence reason'), notes: nullable(data.notes, 'attendance notes'), version: integer(data.version, 'attendance version', 1), child_name: string(data.child_name, 'attendance child name'), intervals: array(data.intervals, 'attendance intervals', parseInterval), events: array(data.events, 'attendance events', parseEvent), created_at: string(data.created_at, 'attendance created time'), updated_at: string(data.updated_at, 'attendance updated time'),
  };
}
function parseFacility(value: unknown): AttendanceFacility {
  const data = object(value, 'facility');
  return { id: string(data.id, 'facility id'), organization_id: string(data.organization_id, 'facility organization'), name: string(data.name, 'facility name'), city: nullable(data.city, 'facility city'), status: string(data.status, 'facility status') };
}
export function parseAttendanceRosterRow(value: unknown): AttendanceRosterRow {
  const data = object(value, 'attendance roster row');
  return { child_id: string(data.child_id, 'roster child id'), child_name: string(data.child_name, 'roster child name'), profile_photo_url: nullable(data.profile_photo_url, 'roster child profile photo'), enrollment_id: string(data.enrollment_id, 'roster enrollment id'), room_id: nullable(data.room_id, 'roster room id'), room_name: nullable(data.room_name, 'roster room name'), program_name: nullable(data.program_name, 'roster program name'), attendance_day: data.attendance_day == null ? null : parseAttendanceDay(data.attendance_day) };
}
const RELEASE_ACTIVATION_PREREQUISITES = new Set<ReleaseCheckoutActivationPrerequisiteCode>([
  'runtime_available',
  'activation_command_available',
  'database_writable',
  'facility_active',
  'privileged_actor',
  'authority_records_complete',
  'not_already_activated',
]);

export function parseAttendanceReleaseCheckoutActivationStatus(value: unknown): AttendanceReleaseCheckoutActivationStatus {
  const data = object(value, 'release checkout activation status');
  if (data.schema_version !== 'release-checkout-activation-status-v1') throw new AttendanceApiError('The server returned an unsupported release checkout activation status.');
  if (data.activation_policy_version !== null && data.activation_policy_version !== 'normal_verified_release_v1') throw new AttendanceApiError('The server returned an invalid release checkout activation policy.');
  if (data.confirmation_text !== 'ACTIVATE VERIFIED RELEASE CHECKOUT') throw new AttendanceApiError('The server returned an invalid release checkout confirmation.');
  const prerequisites = array(data.prerequisites, 'release checkout prerequisites', (item) => {
    const prerequisite = object(item, 'release checkout prerequisite');
    const code = string(prerequisite.code, 'release checkout prerequisite code') as ReleaseCheckoutActivationPrerequisiteCode;
    if (!RELEASE_ACTIVATION_PREREQUISITES.has(code)) throw new AttendanceApiError('The server returned an unknown release checkout prerequisite.');
    return {
      code,
      label: string(prerequisite.label, 'release checkout prerequisite label'),
      satisfied: boolean(prerequisite.satisfied, 'release checkout prerequisite state'),
    };
  });
  const prerequisiteCodes = new Set(prerequisites.map((item) => item.code));
  if (prerequisiteCodes.size !== prerequisites.length) throw new AttendanceApiError('The server returned duplicate release checkout prerequisites.');
  if (prerequisiteCodes.size !== RELEASE_ACTIVATION_PREREQUISITES.size || [...RELEASE_ACTIVATION_PREREQUISITES].some((code) => !prerequisiteCodes.has(code))) throw new AttendanceApiError('The server returned incomplete release checkout prerequisites.');
  const status: AttendanceReleaseCheckoutActivationStatus = {
    schema_version: 'release-checkout-activation-status-v1',
    organization_id: string(data.organization_id, 'release checkout organization id'),
    facility_id: string(data.facility_id, 'release checkout facility id'),
    facility_name: string(data.facility_name, 'release checkout facility name'),
    runtime_available: boolean(data.runtime_available, 'release checkout runtime state'),
    activation_command_available: boolean(data.activation_command_available, 'release checkout activation command state'),
    database_writable: boolean(data.database_writable, 'release checkout database state'),
    actor_authorized: boolean(data.actor_authorized, 'release checkout actor state'),
    facility_active: boolean(data.facility_active, 'release checkout facility state'),
    activated: boolean(data.activated, 'release checkout activation state'),
    legacy_checkout_allowed: boolean(data.legacy_checkout_allowed, 'legacy checkout state'),
    activation_policy_version: data.activation_policy_version as AttendanceReleaseCheckoutActivationStatus['activation_policy_version'],
    open_enrollment_children: integer(data.open_enrollment_children, 'open enrollment child count'),
    release_ready_children: integer(data.release_ready_children, 'release-ready child count'),
    children_needing_authority_review: integer(data.children_needing_authority_review, 'authority-review child count'),
    prerequisites,
    can_activate: boolean(data.can_activate, 'release checkout activation eligibility'),
    confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT',
  };
  if (status.release_ready_children > status.open_enrollment_children || status.children_needing_authority_review !== status.open_enrollment_children - status.release_ready_children) throw new AttendanceApiError('The server returned inconsistent release checkout child readiness.');
  if (status.activated !== Boolean(status.activation_policy_version) || (status.activated && status.legacy_checkout_allowed)) throw new AttendanceApiError('The server returned an inconsistent release checkout activation state.');
  if (status.can_activate !== status.prerequisites.every((item) => item.satisfied)) throw new AttendanceApiError('The server returned inconsistent release checkout prerequisites.');
  return status;
}
function assertDay(day: AttendanceDayRecord, expected: { organizationId: string; facilityId?: string; childId?: string; dayId?: string; date?: string }): AttendanceDayRecord {
  if (day.organization_id !== expected.organizationId) throw new AttendanceApiError('Attendance was returned outside the active organization boundary.');
  if (expected.facilityId && day.facility_id !== expected.facilityId) throw new AttendanceApiError('Attendance was returned for a different facility.');
  if (expected.childId && day.child_id !== expected.childId) throw new AttendanceApiError('Attendance was returned for a different child.');
  if (expected.dayId && day.id !== expected.dayId) throw new AttendanceApiError('Attendance was returned for a different day record.');
  if (expected.date && day.service_date !== expected.date) throw new AttendanceApiError('Attendance was returned for a different service date.');
  return day;
}

export async function fetchAttendanceFacilities(organizationId: string, signal?: AbortSignal): Promise<AttendanceFacility[]> {
  if (!organizationId) throw new AttendanceApiError('A confirmed organization context is required.');
  const values = array(await request<unknown>('/facilities', { signal }), 'facilities', parseFacility);
  if (values.some((item) => item.organization_id !== organizationId)) throw new AttendanceApiError('A facility was returned outside the active organization boundary.');
  return values;
}

export async function fetchAttendanceRoster(date: string, facilityId: string, organizationId: string, signal?: AbortSignal): Promise<AttendanceRosterRow[]> {
  const query = new URLSearchParams({ date, facility_id: facilityId });
  const rows = array(await request<unknown>(`/attendance/roster?${query}`, { signal }), 'attendance roster', parseAttendanceRosterRow);
  rows.forEach((row) => {
    if (row.attendance_day) {
      assertDay(row.attendance_day, { organizationId, facilityId, childId: row.child_id, date });
      if (row.attendance_day.enrollment_id !== row.enrollment_id) throw new AttendanceApiError('An attendance record points to a different enrollment.');
    }
  });
  return rows;
}

export async function fetchAttendanceReleaseCheckoutActivation(
  facilityId: string,
  organizationId: string,
  signal?: AbortSignal,
): Promise<AttendanceReleaseCheckoutActivationStatus> {
  if (!facilityId || !organizationId) throw new AttendanceApiError('A confirmed organization and facility context is required.');
  const status = parseAttendanceReleaseCheckoutActivationStatus(
    await request<unknown>(`/facilities/${encodeURIComponent(facilityId)}/release-checkout-activation`, { signal }),
  );
  if (status.organization_id !== organizationId) throw new AttendanceApiError('Release checkout activation was returned outside the active organization boundary.');
  if (status.facility_id !== facilityId) throw new AttendanceApiError('Release checkout activation was returned for a different facility.');
  return status;
}

export function buildAttendanceMutationPayload(childId: string, facilityId: string, clientOperationId: string, occurredAt?: string) {
  if (!clientOperationId.trim()) throw new AttendanceApiError('A client operation id is required before changing attendance.');
  return { child_id: childId, facility_id: facilityId, occurred_at: occurredAt || null, client_operation_id: clientOperationId };
}
export async function checkIn(childId: string, facilityId: string, organizationId: string, clientOperationId: string, occurredAt?: string): Promise<AttendanceDayRecord> {
  return assertDay(parseAttendanceDay(await request<unknown>('/attendance/check-in', { method: 'POST', body: JSON.stringify(buildAttendanceMutationPayload(childId, facilityId, clientOperationId, occurredAt)) })), { organizationId, facilityId, childId });
}
export async function checkOut(childId: string, facilityId: string, organizationId: string, clientOperationId: string, occurredAt?: string): Promise<AttendanceDayRecord> {
  return assertDay(parseAttendanceDay(await request<unknown>('/attendance/check-out', { method: 'POST', body: JSON.stringify(buildAttendanceMutationPayload(childId, facilityId, clientOperationId, occurredAt)) })), { organizationId, facilityId, childId });
}
export async function markAbsent(childId: string, facilityId: string, date: string, reason: string, organizationId: string): Promise<AttendanceDayRecord> {
  return assertDay(parseAttendanceDay(await request<unknown>('/attendance/absence', { method: 'PUT', body: JSON.stringify({ child_id: childId, facility_id: facilityId, date, reason }) })), { organizationId, facilityId, childId, date });
}
export async function correctInterval(dayId: string, payload: CorrectionMutation, organizationId: string): Promise<AttendanceDayRecord> {
  return assertDay(parseAttendanceDay(await request<unknown>(`/attendance/${encodeURIComponent(dayId)}/correction`, { method: 'PUT', body: JSON.stringify(payload) })), { organizationId, dayId });
}
export async function correctAttendanceStatus(dayId: string, status: 'present' | 'absent', reason: string, organizationId: string, absenceReason?: string): Promise<AttendanceDayRecord> {
  return assertDay(parseAttendanceDay(await request<unknown>(`/attendance/${encodeURIComponent(dayId)}/status-correction`, { method: 'PUT', body: JSON.stringify({ status, reason, ...(absenceReason ? { absence_reason: absenceReason } : {}) }) })), { organizationId, dayId });
}
