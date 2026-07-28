import { ApiError, apiRequest } from '../../api/client';
import { scheduleServiceDate } from './rotaModel';
import { parseStaffSchedule } from './rotaApi';
import type { StaffSchedule } from './types';
import {
  coverageDayKey,
  validateCoverageWindows,
  validateWeeklyWindows,
  type CoverageWindow,
  type WeeklyWindow,
} from './workforceModel';
import type {
  CoverageProjection,
  CoverageProjectionBucket,
  StaffAvailabilityProfile,
  StaffCoverageTarget,
  StaffShiftTemplate,
  StaffTimeOffRequest,
  TimeOffStatus,
  WorkforceList,
} from './workforceTypes';

export const WORKFORCE_ENDPOINTS = {
  root: '/staff-workforce',
  availability: '/staff-workforce/availability',
  timeOff: '/staff-workforce/time-off',
  templates: '/staff-workforce/templates',
  targets: '/staff-workforce/coverage-targets',
  projection: '/staff-workforce/coverage-projection',
} as const;

export class WorkforceApiError extends Error {
  constructor(message: string) { super(message); this.name = 'WorkforceApiError'; }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const text = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableText = (value: unknown, label: string): string | null => value == null ? null : text(value, label);
const boolean = (value: unknown, label: string): boolean => {
  if (typeof value !== 'boolean') throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return value;
};
const integer = (value: unknown, label: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number => {
  if (!Number.isInteger(value) || Number(value) < minimum || Number(value) > maximum) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return Number(value);
};
const timestamp = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (Number.isNaN(new Date(result).getTime())) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return result;
};
const nullableTimestamp = (value: unknown, label: string): string | null => value == null ? null : timestamp(value, label);
const timeZone = (value: unknown, label: string): string => {
  const result = text(value, label);
  try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new WorkforceApiError(`The server returned an invalid ${label}.`); }
  return result;
};
const localTime = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result)) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return result;
};
const isoDate = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || Number.isNaN(new Date(`${result}T00:00:00Z`).getTime())) throw new WorkforceApiError(`The server returned an invalid ${label}.`);
  return result;
};
const facilityClock = (instant: string, zone: string): string => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(instant));
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? '';
  return `${value('hour')}:${value('minute')}`;
};
const choice = <T extends string>(value: unknown, label: string, values: readonly T[]): T => {
  const result = text(value, label);
  if (!values.includes(result as T)) throw new WorkforceApiError(`The server returned an unsupported ${label}.`);
  return result as T;
};
const array = <T,>(value: unknown, label: string, parser: (item: unknown, index: number) => T): T[] => {
  if (!Array.isArray(value)) throw new WorkforceApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};

const assertOrganization = <T extends { organization_id: string }>(value: T, organizationId: string, label: string): T => {
  if (value.organization_id !== organizationId) throw new WorkforceApiError(`A ${label} crossed the active organization boundary.`);
  return value;
};

const assertScope = <T extends { facility_id: string; room_id?: string | null }>(value: T, facilityId?: string, roomId?: string | null, label = 'workforce row'): T => {
  if (facilityId && value.facility_id !== facilityId) throw new WorkforceApiError(`A ${label} crossed the selected facility boundary.`);
  if (roomId !== undefined && value.room_id !== roomId) throw new WorkforceApiError(`A ${label} crossed the selected room boundary.`);
  return value;
};

function parseWeeklyWindow(value: unknown): WeeklyWindow {
  const row = object(value, 'availability window');
  return { weekday: integer(row.weekday, 'availability weekday', 0, 6), start_local: localTime(row.start_local, 'availability start'), end_local: localTime(row.end_local, 'availability end') };
}

function parseCoverageWindow(value: unknown): CoverageWindow {
  const row = object(value, 'coverage target window');
  return { ...parseWeeklyWindow(row), required_staff: integer(row.required_staff, 'required staff', 0, 500) };
}

function assertValidWindows<T extends WeeklyWindow>(values: T[], coverage = false): T[] {
  const errors = coverage ? validateCoverageWindows(values as unknown as CoverageWindow[]) : validateWeeklyWindows(values);
  if (errors.length) throw new WorkforceApiError(`The server returned invalid weekly windows. ${errors[0]}`);
  return values;
}

export function parseAvailability(value: unknown): StaffAvailabilityProfile {
  const row = object(value, 'staff availability profile');
  return {
    id: text(row.id, 'availability id'), organization_id: text(row.organization_id, 'availability organization id'),
    membership_id: text(row.membership_id, 'availability membership id'), staff_user_id: text(row.staff_user_id, 'availability staff user id'),
    staff_display_name: text(row.staff_display_name, 'availability staff name'), facility_id: text(row.facility_id, 'availability facility id'),
    facility_name: text(row.facility_name, 'availability facility name'), facility_timezone: timeZone(row.facility_timezone, 'availability facility timezone'),
    windows: assertValidWindows(array(row.windows, 'availability windows', parseWeeklyWindow)), note: nullableText(row.note, 'availability note'),
    recorded_operation_id: text(row.recorded_operation_id, 'availability operation receipt'), created_at: timestamp(row.created_at, 'availability creation time'),
    updated_at: timestamp(row.updated_at, 'availability update time'),
  };
}

const TIME_OFF_STATUSES = ['pending', 'approved', 'declined', 'cancelled'] as const;
const TIME_OFF_CATEGORIES = ['vacation', 'sick', 'personal', 'medical', 'bereavement', 'unpaid', 'other'] as const;

export function parseTimeOff(value: unknown): StaffTimeOffRequest {
  const row = object(value, 'time-off request');
  const result: StaffTimeOffRequest = {
    id: text(row.id, 'time-off id'), organization_id: text(row.organization_id, 'time-off organization id'),
    membership_id: text(row.membership_id, 'time-off membership id'), staff_user_id: text(row.staff_user_id, 'time-off staff user id'),
    staff_display_name: text(row.staff_display_name, 'time-off staff name'), facility_id: text(row.facility_id, 'time-off facility id'),
    facility_name: text(row.facility_name, 'time-off facility name'), facility_timezone: timeZone(row.facility_timezone, 'time-off facility timezone'),
    starts_at: timestamp(row.starts_at, 'time-off start'), ends_at: timestamp(row.ends_at, 'time-off end'),
    category: choice(row.category, 'time-off category', TIME_OFF_CATEGORIES), note: nullableText(row.note, 'time-off note'),
    status: choice(row.status, 'time-off status', TIME_OFF_STATUSES), can_cancel: boolean(row.can_cancel, 'time-off cancellation permission'),
    response_note: nullableText(row.response_note, 'time-off response note'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'time-off create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'time-off action receipt'),
    decided_at: nullableTimestamp(row.decided_at, 'time-off decision time'), decided_by_user_id: nullableText(row.decided_by_user_id, 'time-off decision actor'),
    cancelled_at: nullableTimestamp(row.cancelled_at, 'time-off cancellation time'), cancelled_by_user_id: nullableText(row.cancelled_by_user_id, 'time-off cancellation actor'),
    cancellation_reason: nullableText(row.cancellation_reason, 'time-off cancellation reason'), created_at: timestamp(row.created_at, 'time-off creation time'), updated_at: timestamp(row.updated_at, 'time-off update time'),
  };
  if (new Date(result.ends_at) <= new Date(result.starts_at)) throw new WorkforceApiError('A time-off request ends before it starts.');
  const hasDecision = result.decided_at !== null || result.decided_by_user_id !== null;
  const completeDecision = result.decided_at !== null && result.decided_by_user_id !== null;
  const hasCancellation = result.cancelled_at !== null || result.cancelled_by_user_id !== null || result.cancellation_reason !== null;
  const completeCancellation = result.cancelled_at !== null && result.cancelled_by_user_id !== null && result.cancellation_reason !== null;
  if (result.status === 'pending' && (hasDecision || hasCancellation || result.response_note !== null || result.recorded_last_operation_id !== result.recorded_create_operation_id)
    || ['approved', 'declined'].includes(result.status) && (!completeDecision || hasCancellation)
    || result.status === 'cancelled' && (!completeCancellation || hasDecision !== completeDecision)) {
    throw new WorkforceApiError('The server returned an inconsistent time-off lifecycle.');
  }
  if (result.can_cancel !== ['pending', 'approved'].includes(result.status)) throw new WorkforceApiError('The server returned inconsistent time-off cancellation permission.');
  return result;
}

export function parseTemplate(value: unknown): StaffShiftTemplate {
  const row = object(value, 'staff shift template');
  const result: StaffShiftTemplate = {
    id: text(row.id, 'template id'), organization_id: text(row.organization_id, 'template organization id'), facility_id: text(row.facility_id, 'template facility id'),
    facility_name: text(row.facility_name, 'template facility name'), facility_timezone: timeZone(row.facility_timezone, 'template facility timezone'),
    room_id: nullableText(row.room_id, 'template room id'), room_name: nullableText(row.room_name, 'template room name'), name: text(row.name, 'template name'),
    weekday: integer(row.weekday, 'template weekday', 0, 6), start_local: localTime(row.start_local, 'template start'), end_local: localTime(row.end_local, 'template end'),
    notes: nullableText(row.notes, 'template notes'), is_active: boolean(row.is_active, 'template active state'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'template create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'template action receipt'),
    created_by_user_id: text(row.created_by_user_id, 'template creator id'), deactivated_at: nullableTimestamp(row.deactivated_at, 'template deactivation time'),
    deactivated_by_user_id: nullableText(row.deactivated_by_user_id, 'template deactivation actor'), created_at: timestamp(row.created_at, 'template creation time'), updated_at: timestamp(row.updated_at, 'template update time'),
  };
  if (result.room_id == null !== (result.room_name == null)) throw new WorkforceApiError('A shift template returned an inconsistent room label.');
  if (validateWeeklyWindows([result]).length) throw new WorkforceApiError('The server returned an invalid shift template interval.');
  if (result.is_active
    ? result.deactivated_at !== null || result.deactivated_by_user_id !== null
    : result.deactivated_at === null || result.deactivated_by_user_id === null) throw new WorkforceApiError('The server returned an inconsistent template lifecycle.');
  return result;
}

export function parseTarget(value: unknown): StaffCoverageTarget {
  const row = object(value, 'coverage target');
  const result: StaffCoverageTarget = {
    id: text(row.id, 'coverage target id'), organization_id: text(row.organization_id, 'coverage target organization id'), facility_id: text(row.facility_id, 'coverage target facility id'),
    facility_name: text(row.facility_name, 'coverage target facility name'), facility_timezone: timeZone(row.facility_timezone, 'coverage target facility timezone'),
    room_id: nullableText(row.room_id, 'coverage target room id'), room_name: nullableText(row.room_name, 'coverage target room name'),
    windows: assertValidWindows(array(row.windows, 'coverage target windows', parseCoverageWindow), true), recorded_last_operation_id: text(row.recorded_last_operation_id, 'coverage target operation receipt'),
    created_at: timestamp(row.created_at, 'coverage target creation time'), updated_at: timestamp(row.updated_at, 'coverage target update time'),
  };
  if (result.room_id == null !== (result.room_name == null)) throw new WorkforceApiError('A coverage target returned an inconsistent room label.');
  return result;
}

function parseProjectionBucket(value: unknown): CoverageProjectionBucket {
  const row = object(value, 'coverage projection bucket');
  const result: CoverageProjectionBucket = {
    starts_at: timestamp(row.starts_at, 'coverage bucket start'), ends_at: timestamp(row.ends_at, 'coverage bucket end'),
    required: integer(row.required, 'coverage required staff'), published: integer(row.published, 'coverage published staff'), acknowledged: integer(row.acknowledged, 'coverage acknowledged staff'),
    declined: integer(row.declined, 'coverage declined staff'), draft: integer(row.draft, 'coverage draft staff'), gap: integer(row.gap, 'coverage gap'), confirmation_gap: integer(row.confirmation_gap, 'coverage confirmation gap'),
  };
  if (new Date(result.ends_at).getTime() - new Date(result.starts_at).getTime() !== 15 * 60_000) throw new WorkforceApiError('A coverage bucket was not exactly 15 minutes.');
  if (result.gap !== Math.max(result.required - (result.published - result.declined), 0) || result.confirmation_gap !== Math.max(result.required - result.acknowledged, 0)) throw new WorkforceApiError('A coverage bucket failed canonical gap arithmetic.');
  if (result.acknowledged > result.published || result.declined > result.published) throw new WorkforceApiError('A coverage bucket returned impossible response counts.');
  if (result.acknowledged + result.declined > result.published) throw new WorkforceApiError('A coverage bucket returned overlapping response counts.');
  return result;
}

export function parseProjection(value: unknown, filters: { facilityId: string; roomId?: string | null; startDate: string; endDate: string }): CoverageProjection {
  const row = object(value, 'coverage projection');
  const result: CoverageProjection = {
    facility_id: text(row.facility_id, 'projection facility id'), facility_name: text(row.facility_name, 'projection facility name'),
    facility_timezone: timeZone(row.facility_timezone, 'projection facility timezone'), room_id: nullableText(row.room_id, 'projection room id'), room_name: nullableText(row.room_name, 'projection room name'),
    start_date: isoDate(row.start_date, 'projection start date'), end_date: isoDate(row.end_date, 'projection end date'), interval_minutes: integer(row.interval_minutes, 'projection interval', 15, 15) as 15,
    buckets: array(row.buckets, 'coverage projection buckets', parseProjectionBucket), total_buckets: integer(row.total_buckets, 'projection bucket total'), gap_buckets: integer(row.gap_buckets, 'projection gap total'), generated_at: timestamp(row.generated_at, 'projection generation time'),
  };
  assertScope(result, filters.facilityId, filters.roomId ?? null, 'coverage projection');
  if (result.start_date !== filters.startDate || result.end_date !== filters.endDate) throw new WorkforceApiError('The coverage projection crossed the requested calendar range.');
  if (result.total_buckets !== result.buckets.length || result.gap_buckets !== result.buckets.filter((bucket) => bucket.gap > 0).length) throw new WorkforceApiError('The coverage projection summary did not match its buckets.');
  if (result.room_id == null !== (result.room_name == null)) throw new WorkforceApiError('The coverage projection returned an inconsistent room label.');
  if (!result.buckets.length) throw new WorkforceApiError('The coverage projection returned no intervals for a non-empty date range.');
  const dayAfterEnd = new Date(`${result.end_date}T12:00:00Z`); dayAfterEnd.setUTCDate(dayAfterEnd.getUTCDate() + 1);
  if (coverageDayKey(result.buckets[0]!.starts_at, result.facility_timezone) !== result.start_date || facilityClock(result.buckets[0]!.starts_at, result.facility_timezone) !== '00:00' || coverageDayKey(result.buckets.at(-1)!.ends_at, result.facility_timezone) !== dayAfterEnd.toISOString().slice(0, 10) || facilityClock(result.buckets.at(-1)!.ends_at, result.facility_timezone) !== '00:00') throw new WorkforceApiError('The coverage projection did not span the complete requested facility calendar range.');
  for (let index = 1; index < result.buckets.length; index += 1) {
    const current = result.buckets[index]!;
    const previous = result.buckets[index - 1]!;
    if (new Date(current.starts_at).getTime() !== new Date(previous.ends_at).getTime()) throw new WorkforceApiError('The coverage projection had a gap, overlap, or duplicate interval.');
  }
  return result;
}

function parseList<T extends { id: string; organization_id: string; facility_id: string }>(value: unknown, label: string, parser: (item: unknown) => T, organizationId: string, facilityId?: string): WorkforceList<T> {
  const row = object(value, `${label} list`);
  const result: WorkforceList<T> = { items: array(row.items, `${label} rows`, parser), total: integer(row.total, `${label} total`), generated_at: timestamp(row.generated_at, `${label} generation time`) };
  result.items.forEach((item) => assertScope(assertOrganization(item, organizationId, label), facilityId, undefined, label));
  if (result.total !== result.items.length) throw new WorkforceApiError(`The ${label} total did not match the returned rows.`);
  if (new Set(result.items.map((item) => item.id)).size !== result.items.length) throw new WorkforceApiError(`The server returned duplicate ${label} rows.`);
  return result;
}

const query = (values: Record<string, string | undefined | null>) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value != null && value !== '') params.set(key, value); });
  return params.toString();
};
const sameWindows = (left: Array<WeeklyWindow & { required_staff?: number }>, right: Array<WeeklyWindow & { required_staff?: number }>) => JSON.stringify(left) === JSON.stringify([...right].sort((a, b) => a.weekday - b.weekday || a.start_local.localeCompare(b.start_local) || a.end_local.localeCompare(b.end_local)));

function assertTimeOffMutation(value: unknown, organizationId: string, request: StaffTimeOffRequest, operationId: string, status: TimeOffStatus): StaffTimeOffRequest {
  const result = assertScope(assertOrganization(parseTimeOff(value), organizationId, 'time-off mutation'), request.facility_id, undefined, 'time-off mutation');
  if (result.id !== request.id || result.status !== status || result.recorded_last_operation_id !== operationId || new Date(result.updated_at) < new Date(request.updated_at)) throw new WorkforceApiError('The server receipt did not match the time-off action.');
  return result;
}

export const workforceApi = {
  listAvailability: async (organizationId: string, filters: { facilityId: string; staffUserId?: string }, signal?: AbortSignal) => parseList(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.availability}?${query({ facility_id: filters.facilityId, staff_user_id: filters.staffUserId })}`, { signal }), 'staff availability', parseAvailability, organizationId, filters.facilityId),
  listTimeOff: async (organizationId: string, filters: { startAt: string; endAt: string; facilityId?: string; staffUserId?: string; status?: TimeOffStatus }, signal?: AbortSignal) => parseList(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.timeOff}?${query({ start_at: filters.startAt, end_at: filters.endAt, facility_id: filters.facilityId, staff_user_id: filters.staffUserId, status: filters.status })}`, { signal }), 'time-off', parseTimeOff, organizationId, filters.facilityId),
  listTemplates: async (organizationId: string, filters: { facilityId?: string; includeInactive?: boolean } = {}, signal?: AbortSignal) => parseList(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.templates}?${query({ facility_id: filters.facilityId, active_only: filters.includeInactive ? 'false' : 'true' })}`, { signal }), 'shift template', parseTemplate, organizationId, filters.facilityId),
  listTargets: async (organizationId: string, facilityId: string, signal?: AbortSignal) => parseList(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.targets}?${query({ facility_id: facilityId })}`, { signal }), 'coverage target', parseTarget, organizationId, facilityId),
  projection: async (filters: { facilityId: string; roomId?: string | null; startDate: string; endDate: string }, signal?: AbortSignal) => parseProjection(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.projection}?${query({ facility_id: filters.facilityId, room_id: filters.roomId, start_date: filters.startDate, end_date: filters.endDate })}`, { signal }), filters),
  approveTimeOff: async (organizationId: string, request: StaffTimeOffRequest, operationId: string, note: string | null) => {
    const result = assertTimeOffMutation(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.timeOff}/${encodeURIComponent(request.id)}/approve`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: request.updated_at, note }) }), organizationId, request, operationId, 'approved');
    if (result.response_note !== note) throw new WorkforceApiError('The server did not retain the time-off approval note.');
    return result;
  },
  declineTimeOff: async (organizationId: string, request: StaffTimeOffRequest, operationId: string, note: string | null) => {
    const result = assertTimeOffMutation(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.timeOff}/${encodeURIComponent(request.id)}/decline`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: request.updated_at, note }) }), organizationId, request, operationId, 'declined');
    if (result.response_note !== note) throw new WorkforceApiError('The server did not retain the time-off decline note.');
    return result;
  },
  cancelTimeOff: async (organizationId: string, request: StaffTimeOffRequest, operationId: string, reason: string) => {
    const result = assertTimeOffMutation(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.timeOff}/${encodeURIComponent(request.id)}/cancel`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: request.updated_at, reason }) }), organizationId, request, operationId, 'cancelled');
    if (result.cancellation_reason !== reason) throw new WorkforceApiError('The server did not retain the time-off cancellation reason.');
    return result;
  },
  createTemplate: async (organizationId: string, payload: { client_operation_id: string; facility_id: string; room_id: string | null; name: string; weekday: number; start_local: string; end_local: string; notes: string | null }) => {
    const result = assertScope(assertOrganization(parseTemplate(await apiRequest<unknown>(WORKFORCE_ENDPOINTS.templates, { method: 'POST', body: JSON.stringify(payload) })), organizationId, 'template mutation'), payload.facility_id, payload.room_id, 'template mutation');
    if (!result.is_active || result.recorded_create_operation_id !== payload.client_operation_id || result.recorded_last_operation_id !== payload.client_operation_id || result.name !== payload.name || result.weekday !== payload.weekday || result.start_local !== payload.start_local || result.end_local !== payload.end_local || result.notes !== payload.notes) throw new WorkforceApiError('The server receipt did not match the template that was created.');
    return result;
  },
  updateTemplate: async (organizationId: string, template: StaffShiftTemplate, operationId: string, payload: { facility_id: string; room_id: string | null; name: string; weekday: number; start_local: string; end_local: string; notes: string | null }) => {
    const result = assertScope(assertOrganization(parseTemplate(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.templates}/${encodeURIComponent(template.id)}`, { method: 'PATCH', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: template.updated_at, ...payload }) })), organizationId, 'template mutation'), payload.facility_id, payload.room_id, 'template mutation');
    if (result.id !== template.id || result.recorded_last_operation_id !== operationId || !result.is_active || result.name !== payload.name || result.weekday !== payload.weekday || result.start_local !== payload.start_local || result.end_local !== payload.end_local || result.notes !== payload.notes || new Date(result.updated_at) < new Date(template.updated_at)) throw new WorkforceApiError('The server receipt did not match the template update.');
    return result;
  },
  deactivateTemplate: async (organizationId: string, template: StaffShiftTemplate, operationId: string) => {
    const result = assertScope(assertOrganization(parseTemplate(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.templates}/${encodeURIComponent(template.id)}/deactivate`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: template.updated_at }) })), organizationId, 'template mutation'), template.facility_id, template.room_id, 'template mutation');
    if (result.id !== template.id || result.recorded_last_operation_id !== operationId || result.is_active || !result.deactivated_at || new Date(result.updated_at) < new Date(template.updated_at)) throw new WorkforceApiError('The server did not confirm template deactivation.');
    return result;
  },
  instantiateTemplate: async (organizationId: string, template: StaffShiftTemplate, operationId: string, staffUserId: string, serviceDate: string, notes: string | null): Promise<StaffSchedule> => {
    const result = parseStaffSchedule(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.templates}/${encodeURIComponent(template.id)}/instantiate`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, staff_user_id: staffUserId, service_date: serviceDate, notes }) }));
    const expectedNotes = notes === null ? template.notes : notes;
    if (result.organization_id !== organizationId || result.status !== 'draft' || result.recorded_create_operation_id !== operationId || result.staff_user_id !== staffUserId || result.facility_id !== template.facility_id || result.room_id !== template.room_id || result.notes !== expectedNotes || scheduleServiceDate(result) !== serviceDate) throw new WorkforceApiError('The server receipt did not match the instantiated draft shift.');
    return result;
  },
  replaceTarget: async (organizationId: string, scope: { facilityId: string; roomId: string | null }, previous: StaffCoverageTarget | null, operationId: string, windows: CoverageWindow[]) => {
    const result = assertScope(assertOrganization(parseTarget(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.targets}/${encodeURIComponent(scope.facilityId)}?${query({ room_id: scope.roomId })}`, { method: 'PUT', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: previous?.updated_at ?? null, windows }) })), organizationId, 'coverage target mutation'), scope.facilityId, scope.roomId, 'coverage target mutation');
    if (result.recorded_last_operation_id !== operationId || !sameWindows(result.windows, windows) || previous && result.id !== previous.id || previous && new Date(result.updated_at) < new Date(previous.updated_at)) throw new WorkforceApiError('The server receipt did not match the coverage target update.');
    return result;
  },
  removeTarget: async (scope: { facilityId: string; roomId: string | null }, previous: StaffCoverageTarget, operationId: string) => {
    if (previous.facility_id !== scope.facilityId || previous.room_id !== scope.roomId) throw new WorkforceApiError('The coverage target removal crossed its selected scope.');
    const row = object(await apiRequest<unknown>(`${WORKFORCE_ENDPOINTS.targets}/${encodeURIComponent(scope.facilityId)}?${query({ room_id: scope.roomId })}`, { method: 'DELETE', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: previous.updated_at }) }), 'coverage target removal receipt');
    if (row.removed !== true || text(row.recorded_operation_id, 'coverage target removal operation') !== operationId) throw new WorkforceApiError('The server did not confirm the exact coverage target removal.');
    return { removed: true as const, recorded_operation_id: operationId, generated_at: timestamp(row.generated_at, 'coverage target removal time') };
  },
};

export function workforceErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== 'object') return null;
  const details = error.details as Record<string, unknown>;
  const detail = details.detail && typeof details.detail === 'object' ? details.detail as Record<string, unknown> : details;
  return typeof detail.code === 'string' ? detail.code : null;
}

export function workforceErrorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof WorkforceApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'Workforce planning could not be loaded. Try again.';
}
