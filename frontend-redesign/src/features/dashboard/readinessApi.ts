import { ApiError, apiRequest, getSelectedOrganizationId } from '../../api/client';

export type ChildRecordReadinessSeverity = 'critical' | 'warning' | 'info';
export const CHILD_RECORD_READINESS_CODES = [
  'missing_primary_guardian',
  'unreachable_guardian_telephone',
  'missing_emergency_contact',
  'inactive_family_active_records',
  'open_unassigned_enrollment',
  'enrollment_placement_incoherent',
  'unknown_immunization_status',
  'duplicate_open_enrollment',
] as const;
export type ChildRecordReadinessCode = typeof CHILD_RECORD_READINESS_CODES[number];

export interface ChildRecordReadinessItem {
  key: string;
  code: ChildRecordReadinessCode;
  severity: ChildRecordReadinessSeverity;
  family_id: string | null;
  child_id: string | null;
  enrollment_id: string | null;
  facility_id: string | null;
  title: string;
  message: string;
  action_route: string;
}

export interface ChildRecordReadinessResponse {
  items: ChildRecordReadinessItem[];
  total: number;
  limit: number;
  offset: number;
  counts: Record<ChildRecordReadinessSeverity, number>;
}

export interface ChildRecordReadinessQuery {
  severity?: ChildRecordReadinessSeverity;
  code?: ChildRecordReadinessCode;
  facilityId?: string;
  limit?: number;
  offset?: number;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return value as Record<string, unknown>;
}

function noExtraKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
  const unexpected = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unexpected.length) throw new ApiError(0, `The server returned unsupported ${label} fields.`);
}

function text(value: unknown, label: string, maximum = 2_000): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return value;
}

function optionalId(value: unknown, label: string): string | null {
  if (value === undefined || value === null) return null;
  return text(value, label, 255);
}

function count(value: unknown, label: string, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > maximum) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return Number(value);
}

function severity(value: unknown): ChildRecordReadinessSeverity {
  if (value === 'critical' || value === 'warning' || value === 'info') return value;
  throw new ApiError(0, 'The server returned an invalid readiness severity.');
}

function readinessCode(value: unknown): ChildRecordReadinessCode {
  if (typeof value === 'string' && (CHILD_RECORD_READINESS_CODES as readonly string[]).includes(value)) {
    return value as ChildRecordReadinessCode;
  }
  throw new ApiError(0, 'The server returned an unsupported readiness code.');
}

function safeActionRoute(
  value: unknown,
  references: Pick<ChildRecordReadinessItem, 'family_id' | 'child_id' | 'enrollment_id' | 'facility_id'>,
): string {
  const route = text(value, 'readiness action route', 1_000);
  if (!route.startsWith('/') || route.startsWith('//') || route.includes('#')) {
    throw new ApiError(0, 'The server returned an unsafe readiness action route.');
  }
  const parsed = new URL(route, 'https://caresync.invalid');
  if (parsed.origin !== 'https://caresync.invalid') {
    throw new ApiError(0, 'The server returned an unsafe readiness action route.');
  }

  const expectedFamily = references.family_id ? `/families/${encodeURIComponent(references.family_id)}` : null;
  const expectedChild = references.child_id ? `/children/${encodeURIComponent(references.child_id)}` : null;
  if (expectedFamily && route === expectedFamily) return route;
  if (expectedChild && route === expectedChild) return route;

  if (
    expectedFamily
    && parsed.pathname === expectedFamily
    && references.child_id
    && references.enrollment_id
  ) {
    const allowed = new Set(['focus', 'child_id', 'enrollment_id']);
    if ([...parsed.searchParams.keys()].some((key) => !allowed.has(key))) {
      throw new ApiError(0, 'The readiness family action contained unsupported focus fields.');
    }
    if (
      parsed.searchParams.getAll('focus').length === 1
      && parsed.searchParams.get('focus') === 'family-status'
      && parsed.searchParams.getAll('child_id').length === 1
      && parsed.searchParams.get('child_id') === references.child_id
      && parsed.searchParams.getAll('enrollment_id').length === 1
      && parsed.searchParams.get('enrollment_id') === references.enrollment_id
      && [...parsed.searchParams.keys()].length === 3
    ) return `${parsed.pathname}?${parsed.searchParams.toString()}`;
  }

  if (parsed.pathname === '/rooms' && references.facility_id && references.enrollment_id) {
    const allowed = new Set(['facility_id', 'placement_enrollment_id']);
    if ([...parsed.searchParams.keys()].some((key) => !allowed.has(key))) {
      throw new ApiError(0, 'The readiness room action contained unsupported filters.');
    }
    if (
      parsed.searchParams.get('facility_id') === references.facility_id
      && parsed.searchParams.get('placement_enrollment_id') === references.enrollment_id
      && [...parsed.searchParams.keys()].length === 2
    ) return `${parsed.pathname}?${parsed.searchParams.toString()}`;
  }

  throw new ApiError(0, 'The readiness action did not match its affected record.');
}

function parseItem(value: unknown, index: number): ChildRecordReadinessItem {
  const row = object(value, `readiness item ${index + 1}`);
  noExtraKeys(row, [
    'key', 'code', 'severity', 'family_id', 'child_id', 'enrollment_id', 'facility_id',
    'title', 'message', 'action_route',
  ], 'readiness item');
  const references = {
    family_id: optionalId(row.family_id, 'readiness family id'),
    child_id: optionalId(row.child_id, 'readiness child id'),
    enrollment_id: optionalId(row.enrollment_id, 'readiness enrollment id'),
    facility_id: optionalId(row.facility_id, 'readiness facility id'),
  };
  if (!references.family_id && !references.child_id && !references.enrollment_id) {
    throw new ApiError(0, 'The readiness item did not identify an affected record.');
  }
  return {
    key: text(row.key, 'readiness key', 500),
    code: readinessCode(row.code),
    severity: severity(row.severity),
    ...references,
    title: text(row.title, 'readiness title', 255),
    message: text(row.message, 'readiness message'),
    action_route: safeActionRoute(row.action_route, references),
  };
}

export function parseChildRecordReadiness(value: unknown): ChildRecordReadinessResponse {
  const row = object(value, 'child-record readiness response');
  noExtraKeys(row, ['items', 'total', 'limit', 'offset', 'counts'], 'readiness response');
  if (!Array.isArray(row.items)) throw new ApiError(0, 'The server returned invalid readiness items.');
  const items = row.items.map(parseItem);
  if (new Set(items.map((item) => item.key)).size !== items.length) {
    throw new ApiError(0, 'The server returned duplicate readiness items.');
  }
  const total = count(row.total, 'readiness total');
  const limit = count(row.limit, 'readiness limit', 200);
  const offset = count(row.offset, 'readiness offset');
  if (items.length > limit || offset + items.length > total) {
    throw new ApiError(0, 'The readiness page did not match its pagination boundary.');
  }
  const countRow = object(row.counts, 'readiness counts');
  noExtraKeys(countRow, ['critical', 'warning', 'info'], 'readiness counts');
  const counts = {
    critical: count(countRow.critical, 'critical readiness count'),
    warning: count(countRow.warning, 'warning readiness count'),
    info: count(countRow.info, 'information readiness count'),
  };
  if (counts.critical + counts.warning + counts.info !== total) {
    throw new ApiError(0, 'The readiness severity counts did not reconcile to the total.');
  }
  return { items, total, limit, offset, counts };
}

function queryString(query: ChildRecordReadinessQuery): string {
  const limit = query.limit ?? 8;
  const offset = query.offset ?? 0;
  if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new ApiError(0, 'Readiness limit must be between 1 and 200.');
  if (!Number.isInteger(offset) || offset < 0) throw new ApiError(0, 'Readiness offset cannot be negative.');
  if (query.code !== undefined && (!query.code.trim() || query.code.length > 100)) throw new ApiError(0, 'Readiness code is invalid.');
  if (query.facilityId !== undefined && (!query.facilityId.trim() || query.facilityId.length > 255)) throw new ApiError(0, 'Readiness facility is invalid.');
  const values = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.severity) values.set('severity', query.severity);
  if (query.code) values.set('code', query.code);
  if (query.facilityId) values.set('facility_id', query.facilityId);
  return values.toString();
}

export async function fetchChildRecordReadiness(
  organizationId: string,
  query: ChildRecordReadinessQuery = {},
  signal?: AbortSignal,
): Promise<ChildRecordReadinessResponse> {
  if (!organizationId.trim() || getSelectedOrganizationId() !== organizationId) {
    throw new ApiError(403, 'Readiness records do not match the selected organization workspace.');
  }
  return parseChildRecordReadiness(await apiRequest<unknown>(`/child-record-readiness?${queryString(query)}`, { signal }));
}
