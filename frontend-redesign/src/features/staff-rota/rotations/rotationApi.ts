import { ApiError, apiRequest } from '../../../api/client';
import { scheduleServiceDate } from '../rotaModel';
import { copySlot, validateRotationInput } from './rotationModel';
import type {
  RotationGenerationReceipt,
  RotationOccurrence,
  RotationPattern,
  RotationPatternInput,
  RotationPreview,
  RotationPreviewIssue,
  RotationSlot,
  RotationSlotInput,
} from './rotationTypes';

export const ROTATION_ENDPOINT = '/staff-exchange/rotations';

export class RotationApiError extends Error {
  constructor(message: string) { super(message); this.name = 'RotationApiError'; }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const text = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim()) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableText = (value: unknown, label: string): string | null => value == null ? null : text(value, label);
const digest = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (!/^[a-f\d]{64}$/i.test(result)) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return result;
};
const nullableDigest = (value: unknown, label: string): string | null => value == null ? null : digest(value, label);
const integer = (value: unknown, label: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number => {
  if (!Number.isInteger(value) || Number(value) < minimum || Number(value) > maximum) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return Number(value);
};
const boolean = (value: unknown, label: string): boolean => {
  if (typeof value !== 'boolean') throw new RotationApiError(`The server returned an invalid ${label}.`);
  return value;
};
const timestamp = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (Number.isNaN(Date.parse(result))) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return result;
};
const nullableTimestamp = (value: unknown, label: string): string | null => value == null ? null : timestamp(value, label);
const isoDate = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || Number.isNaN(Date.parse(`${result}T12:00:00Z`))) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return result;
};
const localTime = (value: unknown, label: string): string => {
  const result = text(value, label);
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result)) throw new RotationApiError(`The server returned an invalid ${label}.`);
  return result;
};
const timeZone = (value: unknown, label: string): string => {
  const result = text(value, label);
  try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new RotationApiError(`The server returned an invalid ${label}.`); }
  return result;
};
const choice = <T extends string>(value: unknown, label: string, values: readonly T[]): T => {
  const result = text(value, label);
  if (!values.includes(result as T)) throw new RotationApiError(`The server returned an unsupported ${label}.`);
  return result as T;
};
const array = <T,>(value: unknown, label: string, parser: (item: unknown) => T): T[] => {
  if (!Array.isArray(value)) throw new RotationApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};

function parseSlot(value: unknown): RotationSlot {
  const row = object(value, 'rotation slot');
  return {
    slot_id: text(row.slot_id, 'rotation slot id'),
    membership_id: text(row.membership_id, 'rotation slot membership id'),
    cycle_week: integer(row.cycle_week, 'rotation cycle week', 0, 7),
    weekday: integer(row.weekday, 'rotation weekday', 0, 6),
    staff_user_id: text(row.staff_user_id, 'rotation staff user id'),
    room_id: nullableText(row.room_id, 'rotation room id'),
    start_local: localTime(row.start_local, 'rotation start'),
    end_local: localTime(row.end_local, 'rotation end'),
    notes: nullableText(row.notes, 'rotation slot notes'),
  };
}

export function parseRotationPattern(value: unknown): RotationPattern {
  const row = object(value, 'rotation pattern');
  const result: RotationPattern = {
    id: text(row.id, 'rotation id'), organization_id: text(row.organization_id, 'rotation organization id'),
    facility_id: text(row.facility_id, 'rotation facility id'), facility_name: text(row.facility_name, 'rotation facility name'), facility_timezone: timeZone(row.facility_timezone, 'rotation facility timezone'),
    name: text(row.name, 'rotation name'), version: integer(row.version, 'rotation version', 1), anchor_date: isoDate(row.anchor_date, 'rotation anchor date'), cycle_weeks: integer(row.cycle_weeks, 'rotation cycle length', 1, 8),
    slots: array(row.slots, 'rotation slots', parseSlot), status: choice(row.status, 'rotation status', ['draft', 'active', 'retired'] as const), snapshot_digest: nullableDigest(row.snapshot_digest, 'rotation snapshot digest'),
    recorded_create_operation_id: text(row.recorded_create_operation_id, 'rotation create receipt'), recorded_last_operation_id: text(row.recorded_last_operation_id, 'rotation action receipt'),
    created_by_user_id: text(row.created_by_user_id, 'rotation creator id'), activated_at: nullableTimestamp(row.activated_at, 'rotation activation time'), activated_by_user_id: nullableText(row.activated_by_user_id, 'rotation activation actor'),
    retired_at: nullableTimestamp(row.retired_at, 'rotation retirement time'), retired_by_user_id: nullableText(row.retired_by_user_id, 'rotation retirement actor'), retirement_reason: nullableText(row.retirement_reason, 'rotation retirement reason'),
    created_at: timestamp(row.created_at, 'rotation creation time'), updated_at: timestamp(row.updated_at, 'rotation update time'),
    can_edit: boolean(row.can_edit, 'rotation edit capability'), can_activate: boolean(row.can_activate, 'rotation activation capability'), can_retire: boolean(row.can_retire, 'rotation retirement capability'),
    can_preview: boolean(row.can_preview, 'rotation preview capability'), can_generate: boolean(row.can_generate, 'rotation generation capability'),
  };
  if (new Set(result.slots.map((slot) => slot.slot_id)).size !== result.slots.length) throw new RotationApiError('The server returned duplicate rotation slot identifiers.');
  const errors = validateRotationInput({ facility_id: result.facility_id, name: result.name, anchor_date: result.anchor_date, cycle_weeks: result.cycle_weeks, slots: result.slots });
  if (errors.length) throw new RotationApiError(`The server returned an invalid rotation. ${errors[0]}`);
  const activationComplete = result.activated_at !== null && result.activated_by_user_id !== null;
  const retirementComplete = result.retired_at !== null && result.retired_by_user_id !== null;
  if (result.activated_at == null !== (result.activated_by_user_id == null) || result.retired_at == null !== (result.retired_by_user_id == null)
    || result.status === 'draft' && (activationComplete || retirementComplete || result.snapshot_digest !== null || result.retirement_reason !== null)
    || result.status === 'active' && (!activationComplete || retirementComplete || result.snapshot_digest === null || result.retirement_reason !== null)
    || result.status === 'retired' && (!activationComplete || !retirementComplete || result.snapshot_digest === null || result.retirement_reason === null)
    || result.status === 'draft' && (!result.can_edit || !result.can_activate || result.can_retire || result.can_preview || result.can_generate)
    || result.status === 'active' && (result.can_edit || result.can_activate || !result.can_retire || !result.can_preview || !result.can_generate)
    || result.status === 'retired' && (result.can_edit || result.can_activate || result.can_retire || result.can_preview || result.can_generate)) throw new RotationApiError('The server returned an inconsistent rotation lifecycle.');
  return result;
}

function parseIssue(value: unknown): RotationPreviewIssue {
  const row = object(value, 'rotation preview issue');
  return { code: text(row.code, 'preview issue code'), message: text(row.message, 'preview issue message'), occurrence_key: nullableText(row.occurrence_key, 'preview issue occurrence'), slot_id: nullableText(row.slot_id, 'preview issue slot'), service_date: row.service_date == null ? null : isoDate(row.service_date, 'preview issue date') };
}

function parseOccurrence(value: unknown): RotationOccurrence {
  const row = object(value, 'rotation occurrence');
  const result: RotationOccurrence = {
    occurrence_key: text(row.occurrence_key, 'rotation occurrence key'), slot_id: text(row.slot_id, 'rotation occurrence slot'), service_date: isoDate(row.service_date, 'rotation occurrence date'),
    staff_user_id: text(row.staff_user_id, 'rotation occurrence staff user'), membership_id: text(row.membership_id, 'rotation occurrence membership'), staff_display_name: text(row.staff_display_name, 'rotation occurrence staff name'),
    room_id: nullableText(row.room_id, 'rotation occurrence room id'), room_name: nullableText(row.room_name, 'rotation occurrence room name'), scheduled_start_at: timestamp(row.scheduled_start_at, 'rotation occurrence start'), scheduled_end_at: timestamp(row.scheduled_end_at, 'rotation occurrence end'), notes: nullableText(row.notes, 'rotation occurrence notes'),
  };
  if (result.room_id == null !== (result.room_name == null) || Date.parse(result.scheduled_end_at) <= Date.parse(result.scheduled_start_at)) throw new RotationApiError('The server returned an inconsistent rotation occurrence.');
  return result;
}

function inclusiveDateCount(startDate: string, endDate: string): number {
  return Math.round((Date.parse(`${endDate}T12:00:00Z`) - Date.parse(`${startDate}T12:00:00Z`)) / 86_400_000) + 1;
}

export function parseRotationPreview(value: unknown, pattern: RotationPattern, range: { startDate: string; endDate: string }): RotationPreview {
  const row = object(value, 'rotation preview');
  const result: RotationPreview = {
    pattern_id: text(row.pattern_id, 'preview pattern id'), snapshot_digest: digest(row.snapshot_digest, 'preview snapshot digest'), start_date: isoDate(row.start_date, 'preview start date'), end_date: isoDate(row.end_date, 'preview end date'),
    occurrences: array(row.occurrences, 'rotation preview occurrences', parseOccurrence), total: integer(row.total, 'rotation preview total', 0, 500), issues: array(row.issues, 'rotation preview issues', parseIssue), can_generate: boolean(row.can_generate, 'rotation preview generation capability'), generated_at: timestamp(row.generated_at, 'rotation preview generation time'),
  };
  if (result.pattern_id !== pattern.id || result.start_date !== range.startDate || result.end_date !== range.endDate) throw new RotationApiError('The rotation preview crossed the selected pattern or date range.');
  if (inclusiveDateCount(result.start_date, result.end_date) < 1 || inclusiveDateCount(result.start_date, result.end_date) > 84) throw new RotationApiError('The rotation preview exceeded its bounded date range.');
  if (result.total !== result.occurrences.length || new Set(result.occurrences.map((item) => item.occurrence_key)).size !== result.occurrences.length) throw new RotationApiError('The rotation preview returned inconsistent or duplicate occurrences.');
  const slotById = new Map(pattern.slots.map((slot) => [slot.slot_id, slot]));
  result.occurrences.forEach((occurrence) => {
    const slot = slotById.get(occurrence.slot_id);
    if (!slot || slot.staff_user_id !== occurrence.staff_user_id || slot.room_id !== occurrence.room_id || occurrence.service_date < result.start_date || occurrence.service_date > result.end_date) throw new RotationApiError('A rotation occurrence crossed its pattern boundary.');
    const scheduleLike = { scheduled_start_at: occurrence.scheduled_start_at, facility_timezone: pattern.facility_timezone } as never;
    if (scheduleServiceDate(scheduleLike) !== occurrence.service_date) throw new RotationApiError('A rotation occurrence crossed its facility service date.');
  });
  if (result.can_generate !== (result.issues.length === 0)) throw new RotationApiError('The rotation preview returned inconsistent generation readiness.');
  return result;
}

function parseGeneration(value: unknown, pattern: RotationPattern, preview: RotationPreview, operationId: string): RotationGenerationReceipt {
  const row = object(value, 'rotation generation receipt');
  const result: RotationGenerationReceipt = {
    pattern_id: text(row.pattern_id, 'generation pattern id'), snapshot_digest: digest(row.snapshot_digest, 'generation snapshot digest'), schedule_ids: array(row.schedule_ids, 'generated schedule ids', (item) => text(item, 'generated schedule id')),
    total: integer(row.total, 'generated schedule total', 0, 500), recorded_operation_id: text(row.recorded_operation_id, 'generation operation receipt'), generated_at: timestamp(row.generated_at, 'generation time'),
  };
  if (result.pattern_id !== pattern.id || result.snapshot_digest !== preview.snapshot_digest || result.recorded_operation_id !== operationId || result.total !== result.schedule_ids.length || new Set(result.schedule_ids).size !== result.schedule_ids.length || result.total !== preview.occurrences.length) throw new RotationApiError('The server receipt did not match the exact rotation generation.');
  return result;
}

function parseList(value: unknown, organizationId: string, facilityId: string): { items: RotationPattern[]; total: number; generated_at: string } {
  const row = object(value, 'rotation list');
  const result = { items: array(row.items, 'rotations', parseRotationPattern), total: integer(row.total, 'rotation total'), generated_at: timestamp(row.generated_at, 'rotation list generation time') };
  if (result.total !== result.items.length || new Set(result.items.map((item) => item.id)).size !== result.items.length) throw new RotationApiError('The rotation list returned inconsistent totals or duplicate rows.');
  if (result.items.some((item) => item.organization_id !== organizationId || item.facility_id !== facilityId)) throw new RotationApiError('A rotation crossed the active organization or facility boundary.');
  return result;
}

const canonicalSlots = (slots: readonly RotationSlotInput[]) => slots.map(copySlot).sort((left, right) => left.slot_id.localeCompare(right.slot_id));
const sameInput = (pattern: RotationPattern, input: RotationPatternInput) => pattern.facility_id === input.facility_id && pattern.name === input.name && pattern.anchor_date === input.anchor_date && pattern.cycle_weeks === input.cycle_weeks && JSON.stringify(canonicalSlots(pattern.slots)) === JSON.stringify(canonicalSlots(input.slots));

export const rotationApi = {
  list: async (organizationId: string, facilityId: string, includeRetired = true, signal?: AbortSignal) => parseList(await apiRequest<unknown>(`${ROTATION_ENDPOINT}?facility_id=${encodeURIComponent(facilityId)}&include_retired=${includeRetired}`, { signal }), organizationId, facilityId),
  create: async (organizationId: string, input: RotationPatternInput, operationId: string) => {
    const result = parseRotationPattern(await apiRequest<unknown>(ROTATION_ENDPOINT, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, facility_id: input.facility_id, name: input.name, anchor_date: input.anchor_date, cycle_weeks: input.cycle_weeks, slots: input.slots.map(copySlot) }) }));
    if (result.organization_id !== organizationId || result.status !== 'draft' || result.recorded_create_operation_id !== operationId || result.recorded_last_operation_id !== operationId || !sameInput(result, input)) throw new RotationApiError('The server receipt did not match the rotation that was created.');
    return result;
  },
  update: async (organizationId: string, pattern: RotationPattern, input: RotationPatternInput, operationId: string) => {
    const result = parseRotationPattern(await apiRequest<unknown>(`${ROTATION_ENDPOINT}/${encodeURIComponent(pattern.id)}`, { method: 'PATCH', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: pattern.updated_at, name: input.name, anchor_date: input.anchor_date, cycle_weeks: input.cycle_weeks, slots: input.slots.map(copySlot) }) }));
    if (result.id !== pattern.id || result.organization_id !== organizationId || result.status !== 'draft' || result.recorded_last_operation_id !== operationId || !sameInput(result, input) || Date.parse(result.updated_at) < Date.parse(pattern.updated_at)) throw new RotationApiError('The server receipt did not match the rotation update.');
    return result;
  },
  activate: async (organizationId: string, pattern: RotationPattern, operationId: string) => {
    const result = parseRotationPattern(await apiRequest<unknown>(`${ROTATION_ENDPOINT}/${encodeURIComponent(pattern.id)}/activate`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: pattern.updated_at }) }));
    if (result.id !== pattern.id || result.organization_id !== organizationId || result.status !== 'active' || result.recorded_last_operation_id !== operationId || !result.activated_at) throw new RotationApiError('The server did not confirm exact rotation activation.');
    return result;
  },
  retire: async (organizationId: string, pattern: RotationPattern, operationId: string, reason: string) => {
    const result = parseRotationPattern(await apiRequest<unknown>(`${ROTATION_ENDPOINT}/${encodeURIComponent(pattern.id)}/retire`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: pattern.updated_at, reason }) }));
    if (result.id !== pattern.id || result.organization_id !== organizationId || result.status !== 'retired' || result.recorded_last_operation_id !== operationId || !result.retired_at || result.retirement_reason !== reason) throw new RotationApiError('The server did not confirm exact rotation retirement.');
    return result;
  },
  preview: async (pattern: RotationPattern, range: { startDate: string; endDate: string }, signal?: AbortSignal) => {
    const count = inclusiveDateCount(range.startDate, range.endDate);
    if (count < 1 || count > 84) throw new RotationApiError('Choose a preview range between 1 and 84 dates.');
    return parseRotationPreview(await apiRequest<unknown>(`${ROTATION_ENDPOINT}/${encodeURIComponent(pattern.id)}/preview`, { method: 'POST', body: JSON.stringify({ start_date: range.startDate, end_date: range.endDate }), signal }), pattern, range);
  },
  generate: async (pattern: RotationPattern, preview: RotationPreview, operationId: string) => parseGeneration(await apiRequest<unknown>(`${ROTATION_ENDPOINT}/${encodeURIComponent(pattern.id)}/generate`, { method: 'POST', body: JSON.stringify({ client_operation_id: operationId, expected_updated_at: pattern.updated_at, start_date: preview.start_date, end_date: preview.end_date, preview_digest: preview.snapshot_digest }) }), pattern, preview, operationId),
};

export function rotationErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== 'object') return null;
  const row = error.details as Record<string, unknown>;
  const detail = row.detail && typeof row.detail === 'object' ? row.detail as Record<string, unknown> : row;
  return typeof detail.code === 'string' ? detail.code : null;
}

export function rotationErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Recurring rotations could not be loaded. Try again.';
}
