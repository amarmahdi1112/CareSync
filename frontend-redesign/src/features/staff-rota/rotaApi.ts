import { ApiError, apiRequest } from '../../api/client';
import type {
  StaffSchedule,
  StaffScheduleActualShift,
  StaffScheduleCreate,
  StaffScheduleList,
  StaffScheduleReconciliation,
  StaffScheduleUpdate,
  UnscheduledStaffShift,
} from './types';

export const ROTA_ENDPOINTS = {
  schedules: '/staff-schedules',
  reconciliation: '/staff-schedules/reconciliation',
} as const;

export class RotaApiError extends Error {
  constructor(message: string) { super(message); this.name = 'RotaApiError'; }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new RotaApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const text = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new RotaApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableText = (value: unknown, label: string): string | null => value == null ? null : text(value, label);
const timestamp = (value: unknown, label: string): string => { const result = text(value, label); if (Number.isNaN(new Date(result).getTime())) throw new RotaApiError(`The server returned an invalid ${label}.`); return result; };
const nullableTimestamp = (value: unknown, label: string): string | null => value == null ? null : timestamp(value, label);
const timeZone = (value: unknown, label: string): string => { const result = text(value, label); try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new RotaApiError(`The server returned an invalid ${label}.`); } return result; };
const boolean = (value: unknown, label: string): boolean => {
  if (typeof value !== 'boolean') throw new RotaApiError(`The server returned an invalid ${label}.`);
  return value;
};
const integerOrNull = (value: unknown, label: string): number | null => {
  if (value == null) return null;
  if (!Number.isInteger(value) || Number(value) < 0) throw new RotaApiError(`The server returned invalid ${label}.`);
  return Number(value);
};
const integer = (value: unknown, label: string): number => {
  const result = integerOrNull(value, label);
  if (result == null) throw new RotaApiError(`The server returned invalid ${label}.`);
  return result;
};
const array = <T,>(value: unknown, label: string, parser: (item: unknown) => T): T[] => {
  if (!Array.isArray(value)) throw new RotaApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};
const choice = <T extends string>(value: unknown, label: string, values: readonly T[]): T => {
  const result = text(value, label);
  if (!values.includes(result as T)) throw new RotaApiError(`The server returned an unsupported ${label}.`);
  return result as T;
};

function parseActualShift(value: unknown): StaffScheduleActualShift {
  const row = object(value, 'actual staff shift');
  return {
    id: text(row.id, 'actual shift id'),
    membership_id: text(row.membership_id, 'actual shift membership id'),
    facility_id: text(row.facility_id, 'actual shift facility id'),
    scheduled_shift_id: nullableText(row.scheduled_shift_id, 'actual shift schedule id'),
    status: choice(row.status, 'actual shift status', ['open', 'closed'] as const),
    clocked_in_at: timestamp(row.clocked_in_at, 'actual shift clock-in time'),
    clocked_out_at: nullableTimestamp(row.clocked_out_at, 'actual shift clock-out time'),
  };
}

export function parseStaffSchedule(value: unknown): StaffSchedule {
  const row = object(value, 'staff schedule');
  const actual = row.actual_shift == null ? null : parseActualShift(row.actual_shift);
  const originType = row.origin_type == null ? null : choice(row.origin_type, 'schedule origin type', ['rotation', 'open_shift', 'swap'] as const);
  const result: StaffSchedule = {
    id: text(row.id, 'schedule id'),
    organization_id: text(row.organization_id, 'schedule organization id'),
    membership_id: text(row.membership_id, 'schedule membership id'),
    staff_user_id: text(row.staff_user_id, 'schedule staff user id'),
    staff_display_name: text(row.staff_display_name, 'schedule staff name'),
    facility_id: text(row.facility_id, 'schedule facility id'),
    facility_name: text(row.facility_name, 'schedule facility name'),
    facility_timezone: timeZone(row.facility_timezone, 'schedule facility timezone'),
    room_id: nullableText(row.room_id, 'schedule room id'),
    room_name: nullableText(row.room_name, 'schedule room name'),
    scheduled_start_at: timestamp(row.scheduled_start_at, 'scheduled start'),
    scheduled_end_at: timestamp(row.scheduled_end_at, 'scheduled end'),
    proposed_start_at: nullableTimestamp(row.proposed_start_at, 'proposed start'),
    proposed_end_at: nullableTimestamp(row.proposed_end_at, 'proposed end'),
    notes: nullableText(row.notes, 'schedule notes'),
    status: choice(row.status, 'schedule status', ['draft', 'published', 'cancelled'] as const),
    response_status: choice(row.response_status, 'schedule response status', ['pending', 'acknowledged', 'declined', 'alternate_proposed'] as const),
    response_note: nullableText(row.response_note, 'schedule response note'),
    responded_at: nullableTimestamp(row.responded_at, 'schedule response time'),
    actual_shift: actual,
    reconciliation_status: choice(row.reconciliation_status, 'schedule reconciliation status', ['upcoming', 'active', 'completed', 'missed', 'late', 'cancelled'] as const),
    is_late: boolean(row.is_late, 'schedule late state'),
    minutes_late: integer(row.minutes_late, 'schedule late minutes'),
    published_at: nullableTimestamp(row.published_at, 'schedule publish time'),
    cancelled_at: nullableTimestamp(row.cancelled_at, 'schedule cancellation time'),
    cancellation_reason: nullableText(row.cancellation_reason, 'schedule cancellation reason'),
    availability_override_reason: nullableText(row.availability_override_reason, 'schedule availability override reason'),
    origin_type: originType,
    origin_id: nullableText(row.origin_id, 'schedule origin id'),
    origin_occurrence_key: nullableText(row.origin_occurrence_key, 'schedule origin occurrence key'),
    supersedes_schedule_id: nullableText(row.supersedes_schedule_id, 'superseded schedule id'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'recorded create operation id'),
    created_by_user_id: text(row.created_by_user_id, 'schedule creator id'),
    published_by_user_id: nullableText(row.published_by_user_id, 'schedule publisher id'),
    cancelled_by_user_id: nullableText(row.cancelled_by_user_id, 'schedule canceller id'),
    created_at: timestamp(row.created_at, 'schedule creation time'),
    updated_at: timestamp(row.updated_at, 'schedule update time'),
  };
  if (actual && (actual.facility_id !== result.facility_id || actual.membership_id !== result.membership_id || actual.scheduled_shift_id !== result.id)) {
    throw new RotaApiError('An actual clock record crossed its planned schedule boundary.');
  }
  const originParts = [result.origin_type, result.origin_id, result.origin_occurrence_key];
  if (originParts.some((part) => part == null) && originParts.some((part) => part != null)) {
    throw new RotaApiError('A staff schedule returned incomplete source provenance.');
  }
  if (result.supersedes_schedule_id === result.id) throw new RotaApiError('A staff schedule cannot supersede itself.');
  if (result.origin_type === 'rotation' && result.supersedes_schedule_id) {
    throw new RotaApiError('A generated rotation occurrence cannot supersede another schedule.');
  }
  if (result.supersedes_schedule_id && !['open_shift', 'swap'].includes(result.origin_type || '')) {
    throw new RotaApiError('A staff schedule returned invalid supersession provenance.');
  }
  if (result.origin_type === 'swap' && !result.supersedes_schedule_id) {
    throw new RotaApiError('A swap replacement did not identify the original schedule.');
  }
  return result;
}

function parseUnscheduledShift(value: unknown): UnscheduledStaffShift {
  const row = object(value, 'unscheduled staff shift');
  const actual = parseActualShift(row.actual_shift);
  if (actual.scheduled_shift_id != null) throw new RotaApiError('An unscheduled clock record points to a planned schedule.');
  return {
    staff_user_id: text(row.staff_user_id, 'unscheduled staff user id'),
    staff_display_name: text(row.staff_display_name, 'unscheduled staff name'),
    facility_id: text(row.facility_id, 'unscheduled facility id'),
    facility_name: text(row.facility_name, 'unscheduled facility name'),
    facility_timezone: timeZone(row.facility_timezone, 'unscheduled facility timezone'),
    reconciliation_status: choice(row.reconciliation_status, 'actual shift reconciliation status', ['unscheduled'] as const),
    actual_shift: actual,
  };
}

function assertOrganization<T extends { organization_id: string }>(value: T, organizationId: string, label: string): T {
  if (value.organization_id !== organizationId) throw new RotaApiError(`A ${label} crossed the active organization boundary.`);
  return value;
}

export function parseStaffSchedules(value: unknown, organizationId: string): StaffScheduleList {
  const row = object(value, 'staff schedule list');
  const result: StaffScheduleList = {
    items: array(row.items, 'staff schedules', parseStaffSchedule),
    total: integer(row.total, 'staff schedule total'),
    generated_at: timestamp(row.generated_at, 'staff schedule generation time'),
  };
  result.items.forEach((schedule) => assertOrganization(schedule, organizationId, 'staff schedule'));
  if (result.total !== result.items.length) throw new RotaApiError('The staff schedule total did not match the returned rows.');
  if (new Set(result.items.map((schedule) => schedule.id)).size !== result.items.length) throw new RotaApiError('The server returned duplicate staff schedules.');
  return result;
}

export function parseReconciliation(value: unknown, organizationId: string): StaffScheduleReconciliation {
  const row = object(value, 'staff schedule reconciliation');
  const result: StaffScheduleReconciliation = {
    scheduled: array(row.scheduled, 'reconciled schedules', parseStaffSchedule),
    unscheduled: array(row.unscheduled, 'unscheduled shifts', parseUnscheduledShift),
    total_scheduled: integer(row.total_scheduled, 'reconciled schedule total'),
    total_unscheduled: integer(row.total_unscheduled, 'unscheduled shift total'),
    generated_at: timestamp(row.generated_at, 'reconciliation generation time'),
  };
  result.scheduled.forEach((schedule) => assertOrganization(schedule, organizationId, 'reconciled schedule'));
  if (result.unscheduled.some((actual) => actual.actual_shift.facility_id !== actual.facility_id)) throw new RotaApiError('An unscheduled clock record crossed its facility boundary.');
  if (result.total_scheduled !== result.scheduled.length || result.total_unscheduled !== result.unscheduled.length) throw new RotaApiError('The reconciliation totals did not match the returned rows.');
  return result;
}

function queryString(filters: { startAt: string; endAt: string; facilityId?: string }): string {
  const query = new URLSearchParams({ start_at: filters.startAt, end_at: filters.endAt });
  if (filters.facilityId) query.set('facility_id', filters.facilityId);
  return query.toString();
}

function assertMutation(schedule: StaffSchedule, organizationId: string, expectedId?: string): StaffSchedule {
  assertOrganization(schedule, organizationId, 'staff schedule mutation');
  if (expectedId && schedule.id !== expectedId) throw new RotaApiError('The server returned a different staff schedule than the one changed.');
  return schedule;
}

const sameInstant = (left: string, right: string) => new Date(left).getTime() === new Date(right).getTime();

async function resolveAlternate(
  decision: 'accept' | 'reject',
  organizationId: string,
  schedule: StaffSchedule,
  clientOperationId: string,
  note: string | null,
): Promise<StaffSchedule> {
  const resolved = assertMutation(parseStaffSchedule(await apiRequest<unknown>(`${ROTA_ENDPOINTS.schedules}/${encodeURIComponent(schedule.id)}/alternate/${decision}`, {
    method: 'POST',
    body: JSON.stringify({ client_operation_id: clientOperationId, expected_updated_at: schedule.updated_at, note }),
  })), organizationId, schedule.id);
  if (resolved.proposed_start_at != null || resolved.proposed_end_at != null) throw new RotaApiError('The server did not clear the resolved alternate time.');
  if (resolved.response_note !== note) throw new RotaApiError('The server did not confirm the alternate-time decision note.');
  if (decision === 'accept') {
    if (resolved.response_status !== 'acknowledged' || !schedule.proposed_start_at || !schedule.proposed_end_at || !sameInstant(resolved.scheduled_start_at, schedule.proposed_start_at) || !sameInstant(resolved.scheduled_end_at, schedule.proposed_end_at)) {
      throw new RotaApiError('The server did not confirm the accepted alternate shift time.');
    }
  } else if (resolved.response_status !== 'pending' || !sameInstant(resolved.scheduled_start_at, schedule.scheduled_start_at) || !sameInstant(resolved.scheduled_end_at, schedule.scheduled_end_at)) {
    throw new RotaApiError('The server did not confirm that the original shift time was retained.');
  }
  return resolved;
}

export const rotaApi = {
  list: async (organizationId: string, filters: { startAt: string; endAt: string; facilityId?: string }, signal?: AbortSignal) => (
    parseStaffSchedules(await apiRequest<unknown>(`${ROTA_ENDPOINTS.schedules}?${queryString(filters)}`, { signal }), organizationId)
  ),
  reconciliation: async (organizationId: string, filters: { startAt: string; endAt: string; facilityId?: string }, signal?: AbortSignal) => (
    parseReconciliation(await apiRequest<unknown>(`${ROTA_ENDPOINTS.reconciliation}?${queryString(filters)}`, { signal }), organizationId)
  ),
  create: async (organizationId: string, payload: StaffScheduleCreate) => {
    const schedule = assertMutation(parseStaffSchedule(await apiRequest<unknown>(ROTA_ENDPOINTS.schedules, { method: 'POST', body: JSON.stringify(payload) })), organizationId);
    if (schedule.status !== 'draft' || schedule.recorded_create_operation_id !== payload.client_operation_id || schedule.staff_user_id !== payload.staff_user_id || schedule.facility_id !== payload.facility_id || schedule.room_id !== payload.room_id || schedule.notes !== payload.notes || !sameInstant(schedule.scheduled_start_at, payload.scheduled_start_at) || !sameInstant(schedule.scheduled_end_at, payload.scheduled_end_at)) {
      throw new RotaApiError('The server receipt did not match the staff schedule that was created.');
    }
    return schedule;
  },
  update: async (organizationId: string, scheduleId: string, payload: StaffScheduleUpdate) => {
    const schedule = assertMutation(parseStaffSchedule(await apiRequest<unknown>(`${ROTA_ENDPOINTS.schedules}/${encodeURIComponent(scheduleId)}`, { method: 'PATCH', body: JSON.stringify(payload) })), organizationId, scheduleId);
    if (schedule.status !== 'draft' || schedule.staff_user_id !== payload.staff_user_id || schedule.facility_id !== payload.facility_id || schedule.room_id !== payload.room_id || schedule.notes !== payload.notes || !sameInstant(schedule.scheduled_start_at, payload.scheduled_start_at) || !sameInstant(schedule.scheduled_end_at, payload.scheduled_end_at)) {
      throw new RotaApiError('The server receipt did not match the staff schedule draft that was updated.');
    }
    return schedule;
  },
  publish: async (organizationId: string, scheduleId: string, clientOperationId: string, availabilityOverrideReason: string | null = null) => {
    const schedule = assertMutation(parseStaffSchedule(await apiRequest<unknown>(`${ROTA_ENDPOINTS.schedules}/${encodeURIComponent(scheduleId)}/publish`, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, availability_override_reason: availabilityOverrideReason }) })), organizationId, scheduleId);
    if (schedule.status !== 'published' || schedule.availability_override_reason !== availabilityOverrideReason) throw new RotaApiError('The server did not confirm that the staff schedule was published with the requested availability decision.');
    return schedule;
  },
  cancel: async (organizationId: string, scheduleId: string, clientOperationId: string, reason: string) => {
    const schedule = assertMutation(parseStaffSchedule(await apiRequest<unknown>(`${ROTA_ENDPOINTS.schedules}/${encodeURIComponent(scheduleId)}/cancel`, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, reason }) })), organizationId, scheduleId);
    if (schedule.status !== 'cancelled' || schedule.cancellation_reason !== reason.trim()) throw new RotaApiError('The server did not confirm that the staff schedule was cancelled with the recorded reason.');
    return schedule;
  },
  acceptAlternate: (organizationId: string, schedule: StaffSchedule, clientOperationId: string, note: string | null) => resolveAlternate('accept', organizationId, schedule, clientOperationId, note),
  rejectAlternate: (organizationId: string, schedule: StaffSchedule, clientOperationId: string, note: string | null) => resolveAlternate('reject', organizationId, schedule, clientOperationId, note),
};

export function rotaErrorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof RotaApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'The staff rota could not be loaded. Try again.';
}
