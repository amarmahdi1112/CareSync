import type {
  FamilyDirectoryPage,
  FamilyDirectoryPrimaryContact,
  FamilyDirectoryQuery,
  FamilyDirectoryRecord,
  FamiliesSnapshot,
  FamilyDetailRecord,
  FamilyEditInput,
  FamilyRegistrationInput,
  FamilyStatsRecord,
  FamilySummaryRecord,
} from './types';
import { addOrganizationHeader, notifyAuthorizationDenied } from '../../api/client';
import {
  CommandOutcomeUnknownError,
  createExactChildcareCommand,
  exactChildcareCommandBody,
  type ExactChildcareCommand,
} from '../../api/childcareCommand';
import {
  emergencyContactCommandPayload,
  guardianCommandPayload,
  toFamilyCoreUpdatePayload,
  toFamilyRegistrationPayload,
  type FamilyCoreUpdatePayload,
  type FamilyRegistrationPayload,
} from './familyForms';
import type { EmergencyContactInput, GuardianInput } from './types';

export type FamilyCreateCommand = ExactChildcareCommand<FamilyRegistrationPayload>;
export type FamilyCoreUpdateCommand = ExactChildcareCommand<FamilyCoreUpdatePayload>;
export type FamilyGuardianReplacementCommand = ExactChildcareCommand<{ guardian: Record<string, unknown> | null }>;
export type FamilyEmergencyContactsReplacementCommand = ExactChildcareCommand<{ emergency_contacts: Array<Record<string, unknown>> }>;

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');
const TOKEN_KEY = 'caresync-redesign-token';
export const FAMILY_DIRECTORY_PAGE_SIZE = 50;

type FamiliesApiErrorOrigin = 'http' | 'response' | 'preflight';

export class FamiliesApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly details?: unknown,
    public readonly origin: FamiliesApiErrorOrigin = 'response',
  ) {
    super(message);
    this.name = 'FamiliesApiError';
  }
}

function detailMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const structured = detail as { code?: unknown; current_version?: unknown };
      if (structured.code === 'stale_childcare_resource') {
        return `This family changed in another action${Number.isInteger(structured.current_version) ? ` (current version ${structured.current_version})` : ''}. Reload before making a new change.`;
      }
      if (structured.code === 'operation_reused') return 'This operation identifier was already used for a different family change.';
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
  if (status === 401) return 'The secure session expired. Reconnect and try again.';
  if (status === 403) return 'This identity cannot read the requested organization records.';
  return `The family directory request failed (${status}).`;
}

async function requestJson(
  path: string,
  organizationId: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  if (!organizationId) {
    throw new FamiliesApiError('An organization identity is required before family records can be requested.', 403, undefined, 'preflight');
  }

  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    throw new FamiliesApiError('A secure CareSync redesign session is required.', 401, undefined, 'preflight');
  }

  const headers = addOrganizationHeader(new Headers({
    Accept: 'application/json', Authorization: `Bearer ${token}`,
    ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers,
  }), organizationId);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    signal,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    }
    if (response.status === 403) notifyAuthorizationDenied();
    throw new FamiliesApiError(detailMessage(payload, response.status), response.status, payload, 'http');
  }

  if (response.status === 204) return null;
  return response.json();
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === 'string' || value === null;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function directoryString(value: unknown, label: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && !value.trim())) {
    throw new FamiliesApiError(`The server returned an invalid family-directory ${label}.`);
  }
  return value;
}

function directoryInteger(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) {
    throw new FamiliesApiError(`The server returned an invalid family-directory ${label}.`);
  }
  return Number(value);
}

function parseDirectoryPrimaryContact(value: unknown): FamilyDirectoryPrimaryContact | null {
  if (value === null) return null;
  if (!isObject(value) || !hasExactKeys(value, ['id', 'first_name', 'last_name', 'email', 'cell_phone'])) {
    throw new FamiliesApiError('The server returned an invalid family-directory primary contact.');
  }
  return {
    id: directoryString(value.id, 'primary contact id'),
    // Imported guardian records may have only one recorded name. The Basic API
    // contract guarantees strings here, but does not require both parts.
    first_name: directoryString(value.first_name, 'primary contact first name', true),
    last_name: directoryString(value.last_name, 'primary contact last name', true),
    email: directoryString(value.email, 'primary contact email', true),
    cell_phone: directoryString(value.cell_phone, 'primary contact phone', true),
  };
}

function parseDirectoryRecord(value: unknown, index: number, organizationId: string): FamilyDirectoryRecord {
  if (!isObject(value) || !hasExactKeys(value, [
    'id', 'organization_id', 'name', 'file_number', 'status', 'version', 'created_at', 'updated_at',
    'primary_contact', 'active_children', 'active_child_count',
  ])) {
    throw new FamiliesApiError(`The server returned an invalid family-directory item at row ${index + 1}.`);
  }
  const returnedOrganizationId = directoryString(value.organization_id, `organization at row ${index + 1}`);
  if (returnedOrganizationId !== organizationId) {
    throw new FamiliesApiError('The family directory crossed the authenticated organization boundary.', 403);
  }
  if (!Array.isArray(value.active_children) || value.active_children.length > 4) {
    throw new FamiliesApiError(`The server returned an invalid active-child preview at row ${index + 1}.`);
  }
  const activeChildren = value.active_children.map((child, childIndex) => {
    if (!isObject(child) || !hasExactKeys(child, ['id', 'first_name', 'last_name', 'age_group'])) {
      throw new FamiliesApiError(`The server returned an invalid active-child preview at row ${index + 1}, child ${childIndex + 1}.`);
    }
    if (!isNullableString(child.age_group)) {
      throw new FamiliesApiError(`The server returned an invalid active-child age group at row ${index + 1}.`);
    }
    return {
      id: directoryString(child.id, 'active child id'),
      first_name: directoryString(child.first_name, 'active child first name'),
      last_name: directoryString(child.last_name, 'active child last name'),
      age_group: child.age_group,
    };
  });
  if (new Set(activeChildren.map((child) => child.id)).size !== activeChildren.length) {
    throw new FamiliesApiError(`The server returned duplicate active-child previews at row ${index + 1}.`);
  }
  const activeChildCount = directoryInteger(value.active_child_count, `active child count at row ${index + 1}`);
  if (activeChildCount < activeChildren.length) {
    throw new FamiliesApiError(`The server returned an active-child count smaller than its preview at row ${index + 1}.`);
  }
  if (!isNullableString(value.file_number)) {
    throw new FamiliesApiError(`The server returned an invalid family-directory file number at row ${index + 1}.`);
  }
  return {
    id: directoryString(value.id, `id at row ${index + 1}`),
    organization_id: returnedOrganizationId,
    name: directoryString(value.name, `name at row ${index + 1}`),
    file_number: value.file_number,
    status: directoryString(value.status, `status at row ${index + 1}`),
    version: directoryInteger(value.version, `version at row ${index + 1}`, 1),
    created_at: directoryString(value.created_at, `created_at at row ${index + 1}`),
    updated_at: directoryString(value.updated_at, `updated_at at row ${index + 1}`),
    primary_contact: parseDirectoryPrimaryContact(value.primary_contact),
    active_children: activeChildren,
    active_child_count: activeChildCount,
  };
}

function normalizeDirectoryQuery(query: Partial<FamilyDirectoryQuery>): FamilyDirectoryQuery {
  const limit = query.limit ?? FAMILY_DIRECTORY_PAGE_SIZE;
  const offset = query.offset ?? 0;
  if (!Number.isInteger(limit) || limit < 1 || limit > FAMILY_DIRECTORY_PAGE_SIZE) {
    throw new FamiliesApiError(`Family directory page size must be between 1 and ${FAMILY_DIRECTORY_PAGE_SIZE}.`, 422, undefined, 'preflight');
  }
  if (!Number.isInteger(offset) || offset < 0) {
    throw new FamiliesApiError('Family directory offset must be a non-negative integer.', 422, undefined, 'preflight');
  }
  return {
    search: query.search?.trim() || '',
    status: query.status?.trim() || '',
    limit,
    offset,
  };
}

export async function fetchFamilyDirectoryPage(
  organizationId: string,
  query: Partial<FamilyDirectoryQuery> = {},
  signal?: AbortSignal,
): Promise<FamilyDirectoryPage> {
  const normalized = normalizeDirectoryQuery(query);
  const search = new URLSearchParams({
    search: normalized.search,
    limit: String(normalized.limit),
    offset: String(normalized.offset),
  });
  if (normalized.status) search.set('status', normalized.status);
  const payload = await requestJson(`/families/directory?${search}`, organizationId, {}, signal);
  if (!isObject(payload) || !hasExactKeys(payload, ['items', 'total', 'limit', 'offset']) || !Array.isArray(payload.items)) {
    throw new FamiliesApiError('The server returned an invalid family-directory page.');
  }
  const total = directoryInteger(payload.total, 'total');
  const limit = directoryInteger(payload.limit, 'limit', 1);
  const offset = directoryInteger(payload.offset, 'offset');
  const expectedLength = Math.min(limit, Math.max(0, total - offset));
  if (limit !== normalized.limit || offset !== normalized.offset || payload.items.length !== expectedLength) {
    throw new FamiliesApiError('The family-directory page did not match the requested window.');
  }
  const items = payload.items.map((item, index) => parseDirectoryRecord(item, index, organizationId));
  if (new Set(items.map((item) => item.id)).size !== items.length) {
    throw new FamiliesApiError('The family-directory page returned duplicate family IDs.');
  }
  return { items, total, limit, offset };
}

function isProtectedChildPhotoUrl(value: unknown, childId: string): boolean {
  if (value === null) return true;
  if (typeof value !== 'string' || !value) return false;
  try {
    const api = new URL(API_URL, typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1');
    const apiPrefix = api.pathname.replace(/\/+$/, '');
    const candidate = /^https?:\/\//i.test(value)
      ? new URL(value)
      : value.startsWith('/api/')
        ? new URL(value, api.origin)
        : new URL(`${apiPrefix}/${value.replace(/^\/+/, '')}`, api.origin);
    return candidate.origin === api.origin
      && !candidate.username
      && !candidate.password
      && !candidate.search
      && !candidate.hash
      && candidate.pathname === `${apiPrefix}/children/${encodeURIComponent(childId)}/photo`;
  } catch {
    return false;
  }
}

function isFamilyChild(value: unknown, familyId: string, organizationId: string): boolean {
  if (!isObject(value)) return false;
  return typeof value.id === 'string'
    && value.organization_id === organizationId
    && value.family_id === familyId
    && typeof value.first_name === 'string'
    && typeof value.last_name === 'string'
    && typeof value.is_active === 'boolean'
    && Number.isInteger(value.version) && Number(value.version) >= 1
    && value.replayed === false
    && (typeof value.age_group === 'string' || value.age_group === null)
    && isProtectedChildPhotoUrl(value.profile_photo_url, value.id)
    && (typeof value.profile_photo_updated_at === 'string' || value.profile_photo_updated_at === null);
}

function isFamilyGuardian(value: unknown, familyId: string): boolean {
  if (!isObject(value)) return false;
  return typeof value.id === 'string'
    && value.family_id === familyId
    && typeof value.first_name === 'string'
    && typeof value.last_name === 'string'
    && typeof value.guardian_type === 'string'
    && typeof value.email === 'string'
    && typeof value.cell_phone === 'string'
    && isNullableString(value.relationship)
    && isNullableString(value.home_phone)
    && isNullableString(value.work_phone)
    && isNullableString(value.address)
    && isNullableString(value.city)
    && isNullableString(value.postal_code)
    && typeof value.authorized_pickup === 'boolean';
}

function isFamilySummary(value: unknown): value is FamilySummaryRecord {
  if (!isObject(value)) return false;
  if (typeof value.id !== 'string' || typeof value.organization_id !== 'string') return false;
  return typeof value.id === 'string'
    && typeof value.organization_id === 'string'
    && typeof value.name === 'string'
    && typeof value.status === 'string'
    && typeof value.created_at === 'string'
    && typeof value.updated_at === 'string'
    && Number.isInteger(value.version) && Number(value.version) >= 1
    && typeof value.replayed === 'boolean'
    && Array.isArray(value.children)
    && value.children.every((child) => isFamilyChild(child, value.id as string, value.organization_id as string))
    && Array.isArray(value.guardians)
    && value.guardians.every((guardian) => isFamilyGuardian(guardian, value.id as string));
}

function isEmergencyContact(value: unknown, familyId: string): boolean {
  if (!isObject(value)) return false;
  return typeof value.id === 'string'
    && value.family_id === familyId
    && typeof value.first_name === 'string'
    && typeof value.last_name === 'string'
    && typeof value.relationship === 'string'
    && typeof value.cell_phone === 'string'
    && isNullableString(value.home_phone)
    && typeof value.authorized_pickup === 'boolean';
}

function isFamilyDetail(value: unknown): value is FamilyDetailRecord {
  if (!isFamilySummary(value)) return false;
  const detail = value as FamilySummaryRecord & Record<string, unknown>;
  return typeof detail.photo_consent === 'boolean'
    && typeof detail.field_trip_consent === 'boolean'
    && typeof detail.emergency_medical_consent === 'boolean'
    && (typeof detail.additional_notes === 'string' || detail.additional_notes === null)
    && Array.isArray(detail.emergency_contacts)
    && detail.emergency_contacts.every((contact) => isEmergencyContact(contact, detail.id));
}

function isFamilyStats(value: unknown): value is FamilyStatsRecord {
  if (!isObject(value)) return false;
  return typeof value.families === 'number'
    && typeof value.active_families === 'number'
    && typeof value.children === 'number'
    && typeof value.active_children === 'number'
    && typeof value.pending_families === 'number'
    && isObject(value.by_age_group);
}

export async function fetchFamiliesSnapshot(
  organizationId: string,
  query: Partial<FamilyDirectoryQuery> = {},
  signal?: AbortSignal,
): Promise<FamiliesSnapshot> {
  const statsRequest = requestJson('/families/stats', organizationId, {}, signal)
    .then((payload): FamilyStatsRecord | null => {
      if (!isFamilyStats(payload)) {
        throw new FamiliesApiError('The server returned an unexpected family-summary response.');
      }
      return payload;
    })
    .catch((caught: unknown): FamilyStatsRecord | null => {
      // Aborts and authorization failures are session/boundary events, not an
      // optional-metric outage. Preserve their existing fail-closed behavior.
      if (caught instanceof Error && caught.name === 'AbortError') throw caught;
      if (caught instanceof FamiliesApiError && (caught.status === 401 || caught.status === 403)) {
        throw caught;
      }
      return null;
    });

  const [directory, stats] = await Promise.all([
    fetchFamilyDirectoryPage(organizationId, query, signal),
    statsRequest,
  ]);

  return {
    directory,
    stats,
  };
}

function assertFamilyDetail(payload: unknown, organizationId: string): FamilyDetailRecord {
  if (!isFamilyDetail(payload)) {
    throw new FamiliesApiError('The server returned an unexpected family-detail response.');
  }
  if (payload.organization_id !== organizationId) {
    throw new FamiliesApiError('The family response did not match the authenticated organization boundary.', 403);
  }
  return payload;
}

function assertFamilyMutation(
  payload: unknown,
  organizationId: string,
  familyId?: string,
  expectedVersion?: number,
): FamilyDetailRecord {
  const family = assertFamilyDetail(payload, organizationId);
  if (familyId && family.id !== familyId) {
    throw new FamiliesApiError('The saved family response did not match the requested record.');
  }
  if (expectedVersion !== undefined && (
    (!family.replayed && family.version !== expectedVersion + 1)
    || (family.replayed && family.version <= expectedVersion)
  )) {
    throw new FamiliesApiError('The saved family response did not confirm the exact expected version transition.');
  }
  return family;
}

function unknownOutcome(caught: unknown): never {
  if (caught instanceof CommandOutcomeUnknownError) throw caught;
  if (
    caught instanceof TypeError
    || caught instanceof SyntaxError
    || (caught instanceof Error && caught.name === 'AbortError')
    || (caught instanceof FamiliesApiError && (
      caught.origin === 'response'
      || (caught.origin === 'http' && (
        caught.status === 408
        || caught.status === 425
        || (caught.status !== null && caught.status >= 500)
      ))
    ))
  ) {
    throw new CommandOutcomeUnknownError('The connection ended before CareSync could confirm this family command. Check the saved result; CareSync will not resend it automatically.', caught);
  }
  throw caught;
}

export async function fetchFamilyDetail(
  familyId: string,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  const payload = await requestJson(`/families/${encodeURIComponent(familyId)}`, organizationId, { cache: 'no-store' }, signal);
  return assertFamilyDetail(payload, organizationId);
}

export function buildFamilyCreateCommand(input: FamilyRegistrationInput): FamilyCreateCommand {
  return createExactChildcareCommand(toFamilyRegistrationPayload(input));
}

export function buildFamilyCoreUpdateCommand(input: FamilyEditInput, expectedVersion: number): FamilyCoreUpdateCommand {
  return createExactChildcareCommand(toFamilyCoreUpdatePayload(input), expectedVersion);
}

export function buildFamilyGuardianReplacementCommand(
  guardian: GuardianInput | null,
  expectedVersion: number,
): FamilyGuardianReplacementCommand {
  return createExactChildcareCommand({ guardian: guardian ? guardianCommandPayload(guardian) : null }, expectedVersion);
}

export function buildFamilyEmergencyContactsReplacementCommand(
  emergencyContacts: readonly EmergencyContactInput[],
  expectedVersion: number,
): FamilyEmergencyContactsReplacementCommand {
  return createExactChildcareCommand({ emergency_contacts: emergencyContacts.map(emergencyContactCommandPayload) }, expectedVersion);
}

export async function createFamily(
  command: FamilyCreateCommand,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  try {
    const payload = await requestJson('/families', organizationId, {
      method: 'POST',
      body: JSON.stringify(exactChildcareCommandBody(command)),
    }, signal);
    return assertFamilyMutation(payload, organizationId);
  } catch (caught) {
    unknownOutcome(caught);
  }
}

export async function updateFamily(
  familyId: string,
  command: FamilyCoreUpdateCommand,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  try {
    const payload = await requestJson(`/families/${encodeURIComponent(familyId)}`, organizationId, {
      method: 'PATCH',
      body: JSON.stringify(exactChildcareCommandBody(command)),
    }, signal);
    return assertFamilyMutation(payload, organizationId, familyId, command.expectedVersion);
  } catch (caught) {
    unknownOutcome(caught);
  }
}

export async function replaceFamilyGuardian(
  familyId: string,
  slot: 'primary' | 'secondary',
  command: FamilyGuardianReplacementCommand,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  try {
    const payload = await requestJson(`/families/${encodeURIComponent(familyId)}/guardians/${slot}`, organizationId, {
      method: 'PUT',
      body: JSON.stringify(exactChildcareCommandBody(command)),
    }, signal);
    return assertFamilyMutation(payload, organizationId, familyId, command.expectedVersion);
  } catch (caught) {
    unknownOutcome(caught);
  }
}

export async function replaceFamilyEmergencyContacts(
  familyId: string,
  command: FamilyEmergencyContactsReplacementCommand,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  try {
    const payload = await requestJson(`/families/${encodeURIComponent(familyId)}/emergency-contacts`, organizationId, {
      method: 'PUT',
      body: JSON.stringify(exactChildcareCommandBody(command)),
    }, signal);
    return assertFamilyMutation(payload, organizationId, familyId, command.expectedVersion);
  } catch (caught) {
    unknownOutcome(caught);
  }
}

export function buildFamilyArchiveCommand(detail: FamilyDetailRecord): FamilyCoreUpdateCommand {
  return buildFamilyCoreUpdateCommand({
    name: detail.name,
    status: 'archived',
    file_number: detail.file_number || '',
    consents: {
      photo_consent: detail.photo_consent,
      field_trip_consent: detail.field_trip_consent,
      emergency_medical_consent: detail.emergency_medical_consent,
    },
    additional_notes: detail.additional_notes || '',
  }, detail.version);
}

export async function archiveFamily(
  detail: FamilyDetailRecord,
  command: FamilyCoreUpdateCommand,
  organizationId: string,
  signal?: AbortSignal,
): Promise<FamilyDetailRecord> {
  return updateFamily(detail.id, command, organizationId, signal);
}
