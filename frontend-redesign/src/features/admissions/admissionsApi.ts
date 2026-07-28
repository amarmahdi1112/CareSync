import { ApiError, apiRequest, getSelectedOrganizationId } from '../../api/client';

export const ADMISSION_INTAKE_STAGES = [
  'record_conflict',
  'family_contacts',
  'child_record',
  'enrollment_setup',
  'family_review',
  'placement_review',
] as const;

export type AdmissionIntakeStage = typeof ADMISSION_INTAKE_STAGES[number];
export type AdmissionIntakeSeverity = 'critical' | 'warning';

export const ADMISSION_REASON_CODES = [
  'missing_primary_guardian',
  'unreachable_guardian_telephone',
  'missing_emergency_contact',
  'no_child_record',
  'no_open_enrollment_record',
  'pending_family_active_child',
  'pending_family_open_enrollment',
  'duplicate_open_enrollment',
  'family_lifecycle_conflict',
  'inactive_child_open_enrollment',
  'enrollment_date_conflict',
  'facility_unavailable',
  'placement_incomplete',
  'program_unavailable',
  'room_unavailable',
  'placement_effective_date_conflict',
  'room_age_range_missing',
  'child_outside_room_age_range',
  'family_pending_manual_review',
  'pending_enrollment_placement_review',
] as const;

export type AdmissionReasonCode = typeof ADMISSION_REASON_CODES[number];
export type AdmissionEntityType = 'family' | 'child' | 'enrollment' | 'facility' | 'program' | 'room';

export interface AdmissionAction {
  label: string;
  path: string;
}

export interface AdmissionReason {
  code: AdmissionReasonCode;
  stage: AdmissionIntakeStage;
  severity: AdmissionIntakeSeverity;
  title: string;
  instruction: string;
  entity_type: AdmissionEntityType;
  entity_id: string;
  action: AdmissionAction;
}

export interface AdmissionChildReference {
  id: string;
  display_name: string;
  is_active: boolean;
}

export interface AdmissionEnrollmentReference {
  id: string;
  child_id: string;
  facility_id: string;
  facility_name: string | null;
  program_id: string | null;
  program_name: string | null;
  room_id: string | null;
  room_name: string | null;
  placement_effective_date: string | null;
  start_date: string;
  end_date: string | null;
  status: 'pending' | 'active' | 'paused';
}

export interface AdmissionIntakeCase {
  key: string;
  family_id: string;
  family_name: string;
  family_status: 'pending' | 'active' | 'inactive' | 'archived';
  stage: AdmissionIntakeStage;
  severity: AdmissionIntakeSeverity;
  children: AdmissionChildReference[];
  enrollments: AdmissionEnrollmentReference[];
  reasons: AdmissionReason[];
  primary_action: AdmissionAction;
  updated_at: string;
}

export interface AdmissionIntakeCounts {
  total: number;
  critical: number;
  warning: number;
  by_stage: Record<AdmissionIntakeStage, number>;
}

export interface AdmissionIntakeQueue {
  organization_id: string;
  generated_at: string;
  projection_kind: 'derived_current_intake_queue';
  read_only: true;
  waitlist_supported: false;
  compliance_certified: false;
  notice: string;
  items: AdmissionIntakeCase[];
  total: number;
  limit: number;
  offset: number;
  counts: AdmissionIntakeCounts;
}

export interface AdmissionIntakeQuery {
  stage?: AdmissionIntakeStage;
  facilityId?: string;
  limit?: number;
  offset?: number;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ENTITY_TYPES = new Set<AdmissionEntityType>(['family', 'child', 'enrollment', 'facility', 'program', 'room']);

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
}

function exact(value: Record<string, unknown>, keys: readonly string[], label: string): void {
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) {
    throw new ApiError(0, `The server returned unsupported ${label} fields.`);
  }
}

function textValue(value: unknown, label: string, maximum = 2_000): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function nullableText(value: unknown, label: string, maximum = 500): string | null {
  return value === null ? null : textValue(value, label, maximum);
}

function uuid(value: unknown, label: string): string {
  const parsed = textValue(value, label, 36);
  if (!UUID.test(parsed)) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return parsed;
}

function nullableUuid(value: unknown, label: string): string | null {
  return value === null ? null : uuid(value, label);
}

function booleanValue(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new ApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function count(value: unknown, label: string, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > maximum) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return Number(value);
}

function isoDate(value: unknown, label: string): string {
  const parsed = textValue(value, label, 64);
  if (!/^\d{4}-\d{2}-\d{2}T/.test(parsed) || Number.isNaN(Date.parse(parsed))) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return parsed;
}

function calendarDate(value: unknown, label: string): string {
  const parsed = textValue(value, label, 10);
  if (!DATE.test(parsed) || Number.isNaN(Date.parse(`${parsed}T12:00:00Z`))) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return parsed;
}

function nullableDate(value: unknown, label: string): string | null {
  return value === null ? null : calendarDate(value, label);
}

function stage(value: unknown): AdmissionIntakeStage {
  if (typeof value === 'string' && (ADMISSION_INTAKE_STAGES as readonly string[]).includes(value)) return value as AdmissionIntakeStage;
  throw new ApiError(0, 'The server returned an unsupported intake stage.');
}

function severity(value: unknown): AdmissionIntakeSeverity {
  if (value === 'critical' || value === 'warning') return value;
  throw new ApiError(0, 'The server returned an unsupported intake severity.');
}

function actionPath(value: unknown, familyId: string, children: readonly AdmissionChildReference[], enrollments: readonly AdmissionEnrollmentReference[]): string {
  const path = textValue(value, 'intake action path', 240);
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('#')) throw new ApiError(0, 'The server returned an unsafe intake action path.');
  const parsed = new URL(path, 'https://caresync.invalid');
  if (parsed.origin !== 'https://caresync.invalid') throw new ApiError(0, 'The server returned an unsafe intake action path.');

  const familyPath = `/families/${encodeURIComponent(familyId)}`;
  if (parsed.pathname === familyPath) {
    if (parsed.search === '') return parsed.pathname;
    if ([...parsed.searchParams.keys()].length !== 1 || parsed.searchParams.getAll('focus').length !== 1 || parsed.searchParams.get('focus') !== 'family-status') {
      throw new ApiError(0, 'The server returned an unsupported family intake action.');
    }
    return `${parsed.pathname}?${parsed.searchParams.toString()}`;
  }

  const child = children.find((item) => parsed.pathname === `/children/${encodeURIComponent(item.id)}`);
  if (child) {
    if (parsed.search) throw new ApiError(0, 'The server returned an unsupported child intake action.');
    return parsed.pathname;
  }

  if (parsed.pathname === '/rooms') {
    const keys = [...parsed.searchParams.keys()];
    const facilityId = parsed.searchParams.get('facility_id') || '';
    const enrollmentId = parsed.searchParams.get('placement_enrollment_id') || '';
    if (
      keys.length !== 2
      || parsed.searchParams.getAll('facility_id').length !== 1
      || parsed.searchParams.getAll('placement_enrollment_id').length !== 1
      || !enrollments.some((item) => item.id === enrollmentId && item.facility_id === facilityId)
    ) throw new ApiError(0, 'The server returned an unsupported room-placement action.');
    return `${parsed.pathname}?${parsed.searchParams.toString()}`;
  }

  throw new ApiError(0, 'The server returned an intake action outside canonical workflows.');
}

function parseAction(value: unknown, familyId: string, children: readonly AdmissionChildReference[], enrollments: readonly AdmissionEnrollmentReference[]): AdmissionAction {
  const row = record(value, 'intake action');
  exact(row, ['label', 'path'], 'intake action');
  return {
    label: textValue(row.label, 'intake action label', 100),
    path: actionPath(row.path, familyId, children, enrollments),
  };
}

function parseChild(value: unknown): AdmissionChildReference {
  const row = record(value, 'intake child reference');
  exact(row, ['id', 'display_name', 'is_active'], 'intake child reference');
  return {
    id: uuid(row.id, 'intake child id'),
    display_name: textValue(row.display_name, 'intake child name', 160),
    is_active: booleanValue(row.is_active, 'intake child status'),
  };
}

function parseEnrollment(value: unknown): AdmissionEnrollmentReference {
  const row = record(value, 'intake enrollment reference');
  exact(row, [
    'id', 'child_id', 'facility_id', 'facility_name', 'program_id', 'program_name', 'room_id', 'room_name',
    'placement_effective_date', 'start_date', 'end_date', 'status',
  ], 'intake enrollment reference');
  const status = textValue(row.status, 'intake enrollment status', 20);
  if (!['pending', 'active', 'paused'].includes(status)) throw new ApiError(0, 'The server returned an unsupported enrollment status.');
  return {
    id: uuid(row.id, 'intake enrollment id'),
    child_id: uuid(row.child_id, 'intake enrollment child id'),
    facility_id: uuid(row.facility_id, 'intake enrollment facility id'),
    facility_name: nullableText(row.facility_name, 'intake enrollment facility name', 255),
    program_id: nullableUuid(row.program_id, 'intake enrollment program id'),
    program_name: nullableText(row.program_name, 'intake enrollment program name', 150),
    room_id: nullableUuid(row.room_id, 'intake enrollment room id'),
    room_name: nullableText(row.room_name, 'intake enrollment room name', 150),
    placement_effective_date: nullableDate(row.placement_effective_date, 'intake placement date'),
    start_date: calendarDate(row.start_date, 'intake enrollment start date'),
    end_date: nullableDate(row.end_date, 'intake enrollment end date'),
    status: status as AdmissionEnrollmentReference['status'],
  };
}

function reasonCode(value: unknown): AdmissionReasonCode {
  if (typeof value === 'string' && (ADMISSION_REASON_CODES as readonly string[]).includes(value)) return value as AdmissionReasonCode;
  throw new ApiError(0, 'The server returned an unsupported intake reason.');
}

function parseReason(value: unknown, familyId: string, children: readonly AdmissionChildReference[], enrollments: readonly AdmissionEnrollmentReference[]): AdmissionReason {
  const row = record(value, 'intake reason');
  exact(row, ['code', 'stage', 'severity', 'title', 'instruction', 'entity_type', 'entity_id', 'action'], 'intake reason');
  const entityType = textValue(row.entity_type, 'intake reason entity type', 20) as AdmissionEntityType;
  if (!ENTITY_TYPES.has(entityType)) throw new ApiError(0, 'The server returned an unsupported intake reason entity type.');
  const entityId = uuid(row.entity_id, 'intake reason entity id');
  const belongsToCase = entityType === 'family' ? entityId === familyId
    : entityType === 'child' ? children.some((item) => item.id === entityId)
      : entityType === 'enrollment' ? enrollments.some((item) => item.id === entityId)
        : entityType === 'facility' ? enrollments.some((item) => item.facility_id === entityId)
          : entityType === 'program' ? enrollments.some((item) => item.program_id === entityId)
            : enrollments.some((item) => item.room_id === entityId);
  if (!belongsToCase) throw new ApiError(0, 'An intake reason pointed outside its family case.');
  return {
    code: reasonCode(row.code),
    stage: stage(row.stage),
    severity: severity(row.severity),
    title: textValue(row.title, 'intake reason title', 160),
    instruction: textValue(row.instruction, 'intake reason instruction', 500),
    entity_type: entityType,
    entity_id: entityId,
    action: parseAction(row.action, familyId, children, enrollments),
  };
}

function parseCase(value: unknown, requested: AdmissionIntakeQuery): AdmissionIntakeCase {
  const row = record(value, 'intake case');
  exact(row, [
    'key', 'family_id', 'family_name', 'family_status', 'stage', 'severity', 'children', 'enrollments',
    'reasons', 'primary_action', 'updated_at',
  ], 'intake case');
  const familyId = uuid(row.family_id, 'intake family id');
  if (row.key !== `family:${familyId}`) throw new ApiError(0, 'The intake case key did not match its family.');
  if (!Array.isArray(row.children) || !Array.isArray(row.enrollments) || !Array.isArray(row.reasons) || row.reasons.length === 0) {
    throw new ApiError(0, 'The server returned an incomplete intake case.');
  }
  const children = row.children.map(parseChild);
  const enrollments = row.enrollments.map(parseEnrollment);
  if (new Set(children.map((item) => item.id)).size !== children.length || new Set(enrollments.map((item) => item.id)).size !== enrollments.length) {
    throw new ApiError(0, 'The server returned duplicate intake references.');
  }
  if (enrollments.some((item) => !children.some((child) => child.id === item.child_id))) {
    throw new ApiError(0, 'An intake enrollment did not match a child in its family case.');
  }
  const reasons = row.reasons.map((item) => parseReason(item, familyId, children, enrollments));
  const parsedStage = stage(row.stage);
  const parsedSeverity = severity(row.severity);
  if (reasons[0].stage !== parsedStage || reasons[0].severity !== parsedSeverity) throw new ApiError(0, 'The intake case did not match its primary reason.');
  if (parsedSeverity === 'warning' && reasons.some((reason) => reason.severity === 'critical')) {
    throw new ApiError(0, 'A warning intake case contained a higher-severity reason.');
  }
  if (requested.stage && parsedStage !== requested.stage) throw new ApiError(0, 'The intake case crossed the requested stage filter.');
  if (requested.facilityId && !enrollments.some((item) => item.facility_id === requested.facilityId)) {
    throw new ApiError(0, 'The intake case crossed the requested facility filter.');
  }
  const primaryAction = parseAction(row.primary_action, familyId, children, enrollments);
  if (primaryAction.label !== reasons[0].action.label || primaryAction.path !== reasons[0].action.path) {
    throw new ApiError(0, 'The intake primary action did not match its first reason.');
  }
  const familyStatus = textValue(row.family_status, 'intake family status', 20);
  if (!['pending', 'active', 'inactive', 'archived'].includes(familyStatus)) throw new ApiError(0, 'The server returned an unsupported family status.');
  return {
    key: row.key as string,
    family_id: familyId,
    family_name: textValue(row.family_name, 'intake family name', 255),
    family_status: familyStatus as AdmissionIntakeCase['family_status'],
    stage: parsedStage,
    severity: parsedSeverity,
    children,
    enrollments,
    reasons,
    primary_action: primaryAction,
    updated_at: isoDate(row.updated_at, 'intake case update time'),
  };
}

function parseCounts(value: unknown): AdmissionIntakeCounts {
  const row = record(value, 'intake counts');
  exact(row, ['total', 'critical', 'warning', 'by_stage'], 'intake counts');
  const byStageRow = record(row.by_stage, 'intake stage counts');
  exact(byStageRow, [...ADMISSION_INTAKE_STAGES], 'intake stage counts');
  const byStage = Object.fromEntries(ADMISSION_INTAKE_STAGES.map((key) => [key, count(byStageRow[key], `${key} intake count`)])) as Record<AdmissionIntakeStage, number>;
  const result = {
    total: count(row.total, 'intake count total'),
    critical: count(row.critical, 'critical intake count'),
    warning: count(row.warning, 'warning intake count'),
    by_stage: byStage,
  };
  if (result.critical + result.warning !== result.total || Object.values(byStage).reduce((sum, value) => sum + value, 0) !== result.total) {
    throw new ApiError(0, 'The intake counts did not reconcile.');
  }
  return result;
}

export function parseAdmissionIntakeQueue(value: unknown, organizationId: string, requested: AdmissionIntakeQuery = {}): AdmissionIntakeQueue {
  const row = record(value, 'admissions intake queue');
  exact(row, [
    'organization_id', 'generated_at', 'projection_kind', 'read_only', 'waitlist_supported', 'compliance_certified',
    'notice', 'items', 'total', 'limit', 'offset', 'counts',
  ], 'admissions intake queue');
  if (uuid(row.organization_id, 'intake organization id') !== organizationId) throw new ApiError(403, 'The admissions queue crossed the selected organization boundary.');
  if (row.projection_kind !== 'derived_current_intake_queue' || row.read_only !== true || row.waitlist_supported !== false || row.compliance_certified !== false) {
    throw new ApiError(0, 'The server returned unsupported admissions projection claims.');
  }
  if (!Array.isArray(row.items)) throw new ApiError(0, 'The server returned invalid intake cases.');
  const limit = count(row.limit, 'intake limit', 200);
  const offset = count(row.offset, 'intake offset');
  const total = count(row.total, 'intake total');
  const expectedLimit = requested.limit ?? 50;
  const expectedOffset = requested.offset ?? 0;
  if (limit !== expectedLimit || offset !== expectedOffset || row.items.length !== Math.min(limit, Math.max(0, total - offset))) {
    throw new ApiError(0, 'The admissions queue did not match its requested page.');
  }
  const counts = parseCounts(row.counts);
  if (counts.total !== total) throw new ApiError(0, 'The admissions queue total did not match its filtered counts.');
  const items = row.items.map((item) => parseCase(item, requested));
  if (new Set(items.map((item) => item.key)).size !== items.length || new Set(items.map((item) => item.family_id)).size !== items.length) {
    throw new ApiError(0, 'The server returned duplicate family intake cases.');
  }
  return {
    organization_id: organizationId,
    generated_at: isoDate(row.generated_at, 'intake generation time'),
    projection_kind: 'derived_current_intake_queue',
    read_only: true,
    waitlist_supported: false,
    compliance_certified: false,
    notice: textValue(row.notice, 'intake projection notice', 500),
    items,
    total,
    limit,
    offset,
    counts,
  };
}

export function buildAdmissionIntakeQueuePath(query: AdmissionIntakeQuery = {}): string {
  const limit = query.limit ?? 50;
  const offset = query.offset ?? 0;
  if (!Number.isInteger(limit) || limit < 1 || limit > 200) throw new ApiError(0, 'Intake page size must be between 1 and 200.');
  if (!Number.isInteger(offset) || offset < 0) throw new ApiError(0, 'Intake page offset cannot be negative.');
  if (query.stage && !(ADMISSION_INTAKE_STAGES as readonly string[]).includes(query.stage)) throw new ApiError(0, 'Choose a supported intake stage.');
  if (query.facilityId && !UUID.test(query.facilityId)) throw new ApiError(0, 'Choose a valid intake facility.');
  const values = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.stage) values.set('stage', query.stage);
  if (query.facilityId) values.set('facility_id', query.facilityId);
  return `/admissions/intake-queue?${values.toString()}`;
}

export async function fetchAdmissionIntakeQueue(organizationId: string, query: AdmissionIntakeQuery = {}, signal?: AbortSignal): Promise<AdmissionIntakeQueue> {
  if (!UUID.test(organizationId) || getSelectedOrganizationId() !== organizationId) throw new ApiError(403, 'Admissions records do not match the selected organization workspace.');
  return parseAdmissionIntakeQueue(await apiRequest<unknown>(buildAdmissionIntakeQueuePath(query), { signal, cache: 'no-store' }), organizationId, query);
}
