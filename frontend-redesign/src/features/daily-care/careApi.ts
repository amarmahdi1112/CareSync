import { apiRequest } from '../../api/client';

export type CareType = 'feeding' | 'diaper' | 'toilet' | 'sleep' | 'mood' | 'activity';
export type AttendanceState = 'not_recorded' | 'on_site' | 'checked_out' | 'no_show';
export type FeedingKind = 'meal' | 'snack' | 'bottle';
export type FeedingIntake = 'none' | 'some' | 'most' | 'all';
export type DiaperOutcome = 'dry' | 'wet' | 'soiled' | 'both';
export type ToiletOutcome = 'attempt' | 'success' | 'accident';
export type MoodValue = 'calm' | 'happy' | 'sad' | 'upset' | 'tired' | 'energetic';
export type ActivityKind = 'indoor' | 'outdoor' | 'learning' | 'creative' | 'physical';
export type CareEventType = 'recorded' | 'sleep_finished' | 'corrected' | 'voided' | 'auto_finished_at_checkout';

export type CarePayload =
  | { kind: FeedingKind; intake: FeedingIntake; volume_ml?: number }
  | { outcome: DiaperOutcome }
  | { outcome: ToiletOutcome }
  | Record<string, never>
  | { value: MoodValue }
  | { kind: ActivityKind };

export interface ChildSafetySummary {
  allergies: string | null;
  medical_conditions: string | null;
  medication_awareness: string | null;
  emergency_medical_consent: boolean;
}

export interface CareRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  room_id: string;
  child_id: string;
  enrollment_id: string;
  attendance_day_id: string;
  service_date: string;
  care_type: CareType;
  occurred_at: string;
  ended_at: string | null;
  payload: CarePayload;
  note: string | null;
  created_by_user_id: string;
  created_by_name: string;
  version: number;
  voided_at: string | null;
  voided_by_user_id: string | null;
  void_reason: string | null;
  last_event_type: CareEventType;
  was_corrected: boolean;
  created_at: string;
  updated_at: string;
}

export interface CareDayChild {
  child_id: string;
  child_name: string;
  profile_photo_url: string | null;
  enrollment_id: string;
  attendance_day_id: string | null;
  attendance_state: AttendanceState;
  safety: ChildSafetySummary;
  records: CareRecord[];
}

export interface CareRoomDay {
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string;
  room_name: string;
  service_date: string;
  safety_as_of: string;
  generated_at: string;
  children: CareDayChild[];
}

export interface SafetyContact {
  id: string;
  contact_type: 'primary_guardian' | 'emergency_contact';
  name: string;
  relationship: string | null;
  phone: string;
  authorized_pickup: boolean;
}

export interface ChildSafetyCard {
  child_id: string;
  child_name: string;
  profile_photo_url: string | null;
  age_group: string | null;
  facility_id: string;
  room_id: string;
  safety: ChildSafetySummary;
  contacts: SafetyContact[];
}

export interface CareRecordEvent {
  id: string;
  care_record_id: string;
  actor_user_id: string;
  actor_name: string;
  client_operation_id: string;
  event_type: CareEventType;
  occurred_at: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface CreateCareRecordInput {
  attendance_day_id: string;
  care_type: CareType;
  occurred_at: string;
  payload: CarePayload;
  note?: string | null;
  client_operation_id: string;
}

export interface CorrectCareRecordInput {
  occurred_at: string;
  ended_at?: string | null;
  payload: CarePayload;
  note?: string | null;
  reason: string;
  expected_version: number;
  client_operation_id: string;
}

export class CareApiError extends Error {
  constructor(message: string, public readonly status = 0) {
    super(message);
    this.name = 'CareApiError';
  }
}

type Row = Record<string, unknown>;

function object(value: unknown, label: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new CareApiError(`The server returned an invalid ${label} response.`);
  }
  return value as Row;
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new CareApiError(`The server returned an invalid ${label}.`);
  return value;
}

function nullableString(value: unknown, label: string): string | null {
  if (value == null) return null;
  if (typeof value !== 'string') throw new CareApiError(`The server returned an invalid ${label}.`);
  return value;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new CareApiError(`The server returned an invalid ${label}.`);
  return value;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) throw new CareApiError(`The server returned an invalid ${label}.`);
  return Number(value);
}

function dateString(value: unknown, label: string): string {
  const result = string(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result)) throw new CareApiError(`The server returned an invalid ${label}.`);
  return result;
}

function timestamp(value: unknown, label: string): string {
  const result = string(value, label);
  if (Number.isNaN(Date.parse(result)) || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)) {
    throw new CareApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

function timeZone(value: unknown, label: string): string {
  const result = string(value, label);
  try {
    new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0));
  } catch {
    throw new CareApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function oneOf<T extends string>(value: unknown, options: readonly T[], label: string): T {
  if (typeof value !== 'string' || !options.includes(value as T)) throw new CareApiError(`The server returned an invalid ${label}.`);
  return value as T;
}

function array<T>(value: unknown, label: string, parser: (item: unknown, index: number) => T): T[] {
  if (!Array.isArray(value)) throw new CareApiError(`The server returned an invalid ${label} response.`);
  return value.map(parser);
}

function noExtraKeys(value: Row, allowed: readonly string[], label: string): void {
  const extras = Object.keys(value).filter((key) => !allowed.includes(key));
  if (extras.length) throw new CareApiError(`The server returned an invalid ${label} payload.`);
}

function parsePayload(value: unknown, careType: CareType): CarePayload {
  const data = object(value, `${careType} care payload`);
  if (careType === 'feeding') {
    noExtraKeys(data, ['kind', 'intake', 'volume_ml'], 'feeding');
    const kind = oneOf(data.kind, ['meal', 'snack', 'bottle'] as const, 'feeding kind');
    const intake = oneOf(data.intake, ['none', 'some', 'most', 'all'] as const, 'feeding intake');
    if (kind !== 'bottle' && data.volume_ml != null) throw new CareApiError('The server returned feeding volume for a non-bottle record.');
    const volume = data.volume_ml == null ? undefined : integer(data.volume_ml, 'bottle volume');
    if (volume !== undefined && volume > 2000) throw new CareApiError('The server returned an invalid bottle volume.');
    return { kind, intake, ...(volume === undefined ? {} : { volume_ml: volume }) };
  }
  if (careType === 'diaper') {
    noExtraKeys(data, ['outcome'], 'diaper');
    return { outcome: oneOf(data.outcome, ['dry', 'wet', 'soiled', 'both'] as const, 'diaper outcome') };
  }
  if (careType === 'toilet') {
    noExtraKeys(data, ['outcome'], 'toilet');
    return { outcome: oneOf(data.outcome, ['attempt', 'success', 'accident'] as const, 'toilet outcome') };
  }
  if (careType === 'sleep') {
    noExtraKeys(data, [], 'sleep');
    return {};
  }
  if (careType === 'mood') {
    noExtraKeys(data, ['value'], 'mood');
    return { value: oneOf(data.value, ['calm', 'happy', 'sad', 'upset', 'tired', 'energetic'] as const, 'mood value') };
  }
  noExtraKeys(data, ['kind'], 'activity');
  return { kind: oneOf(data.kind, ['indoor', 'outdoor', 'learning', 'creative', 'physical'] as const, 'activity kind') };
}

function parseSafetySummary(value: unknown): ChildSafetySummary {
  const data = object(value, 'child safety summary');
  noExtraKeys(data, ['allergies', 'medical_conditions', 'medication_awareness', 'emergency_medical_consent'], 'child safety summary');
  return {
    allergies: nullableString(data.allergies, 'allergy summary'),
    medical_conditions: nullableString(data.medical_conditions, 'medical conditions'),
    medication_awareness: nullableString(data.medication_awareness, 'medication awareness'),
    emergency_medical_consent: boolean(data.emergency_medical_consent, 'emergency medical consent'),
  };
}

function childPhotoUrl(value: unknown, childId: string, label: string): string | null {
  const result = nullableString(value, label);
  if (result !== null && result !== `/api/v1/children/${encodeURIComponent(childId)}/photo`) {
    throw new CareApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

export function parseCareRecord(value: unknown): CareRecord {
  const data = object(value, 'daily care record');
  noExtraKeys(data, [
    'id', 'organization_id', 'facility_id', 'room_id', 'child_id', 'enrollment_id',
    'attendance_day_id', 'service_date', 'care_type', 'occurred_at', 'ended_at',
    'payload', 'note', 'created_by_user_id', 'created_by_name', 'version', 'voided_at',
    'voided_by_user_id', 'void_reason', 'last_event_type', 'was_corrected', 'created_at',
    'updated_at',
  ], 'daily care record');
  const careType = oneOf(data.care_type, ['feeding', 'diaper', 'toilet', 'sleep', 'mood', 'activity'] as const, 'care type');
  const occurredAt = timestamp(data.occurred_at, 'care occurrence time');
  const endedAt = nullableTimestamp(data.ended_at, 'care end time');
  if (endedAt && Date.parse(endedAt) < Date.parse(occurredAt)) throw new CareApiError('The server returned a care record with an invalid time order.');
  if (careType !== 'sleep' && endedAt) throw new CareApiError('The server returned an end time for a non-sleep care record.');
  const voidedAt = nullableTimestamp(data.voided_at, 'care void time');
  const voidedBy = nullableString(data.voided_by_user_id, 'care void actor');
  const voidReason = nullableString(data.void_reason, 'care void reason');
  if (Boolean(voidedAt) !== Boolean(voidedBy) || Boolean(voidedAt) !== Boolean(voidReason?.trim())) {
    throw new CareApiError('The server returned incomplete care void evidence.');
  }
  const lastEventType = oneOf(data.last_event_type, ['recorded', 'sleep_finished', 'corrected', 'voided', 'auto_finished_at_checkout'] as const, 'last care event type');
  const wasCorrected = boolean(data.was_corrected, 'care correction marker');
  if (Boolean(voidedAt) !== (lastEventType === 'voided')) throw new CareApiError('The server returned inconsistent care void evidence.');
  if ((lastEventType === 'sleep_finished' || lastEventType === 'auto_finished_at_checkout') && (careType !== 'sleep' || !endedAt)) {
    throw new CareApiError('The server returned inconsistent sleep completion evidence.');
  }
  if (lastEventType === 'corrected' && !wasCorrected) throw new CareApiError('The server returned inconsistent care correction evidence.');
  return {
    id: string(data.id, 'care record id'),
    organization_id: string(data.organization_id, 'care organization'),
    facility_id: string(data.facility_id, 'care facility'),
    room_id: string(data.room_id, 'care room'),
    child_id: string(data.child_id, 'care child'),
    enrollment_id: string(data.enrollment_id, 'care enrollment'),
    attendance_day_id: string(data.attendance_day_id, 'care attendance day'),
    service_date: dateString(data.service_date, 'care service date'),
    care_type: careType,
    occurred_at: occurredAt,
    ended_at: endedAt,
    payload: parsePayload(data.payload, careType),
    note: nullableString(data.note, 'care note'),
    created_by_user_id: string(data.created_by_user_id, 'care creator'),
    created_by_name: string(data.created_by_name, 'care creator name'),
    version: integer(data.version, 'care version', 1),
    voided_at: voidedAt,
    voided_by_user_id: voidedBy,
    void_reason: voidReason,
    last_event_type: lastEventType,
    was_corrected: wasCorrected,
    created_at: timestamp(data.created_at, 'care creation time'),
    updated_at: timestamp(data.updated_at, 'care update time'),
  };
}

export function parseCareRoomDay(value: unknown): CareRoomDay {
  const data = object(value, 'room care day');
  noExtraKeys(data, ['organization_id', 'facility_id', 'facility_name', 'facility_timezone', 'room_id', 'room_name', 'service_date', 'safety_as_of', 'generated_at', 'children'], 'room care day');
  const organizationId = string(data.organization_id, 'care day organization');
  const facilityId = string(data.facility_id, 'care day facility');
  const roomId = string(data.room_id, 'care day room');
  const serviceDate = dateString(data.service_date, 'care day service date');
  const children = array(data.children, 'care day children', (item) => {
    const child = object(item, 'care day child');
    noExtraKeys(child, ['child_id', 'child_name', 'profile_photo_url', 'enrollment_id', 'attendance_day_id', 'attendance_state', 'safety', 'records'], 'care day child');
    const childId = string(child.child_id, 'care day child id');
    const enrollmentId = string(child.enrollment_id, 'care day enrollment');
    const attendanceDayId = nullableString(child.attendance_day_id, 'care day attendance record');
    const attendanceState = oneOf(child.attendance_state, ['not_recorded', 'on_site', 'checked_out', 'no_show'] as const, 'care attendance state');
    if ((attendanceDayId === null) !== (attendanceState === 'not_recorded')) {
      throw new CareApiError('The care day returned inconsistent attendance evidence.');
    }
    const records = array(child.records, 'child care records', parseCareRecord);
    records.forEach((record) => {
      if (record.organization_id !== organizationId || record.facility_id !== facilityId || record.room_id !== roomId || record.child_id !== childId || record.enrollment_id !== enrollmentId || record.service_date !== serviceDate || record.attendance_day_id !== attendanceDayId) {
        throw new CareApiError('A daily care record crossed the requested room, child, enrollment, or attendance boundary.');
      }
    });
    if (new Set(records.map((record) => record.id)).size !== records.length) throw new CareApiError('The care day returned a record more than once.');
    return {
      child_id: childId,
      child_name: string(child.child_name, 'care day child name'),
      profile_photo_url: childPhotoUrl(child.profile_photo_url, childId, 'care day child photo'),
      enrollment_id: enrollmentId,
      attendance_day_id: attendanceDayId,
      attendance_state: attendanceState,
      safety: parseSafetySummary(child.safety),
      records,
    } satisfies CareDayChild;
  });
  if (new Set(children.map((child) => child.child_id)).size !== children.length) throw new CareApiError('The care day returned a child more than once.');
  return {
    organization_id: organizationId,
    facility_id: facilityId,
    facility_name: string(data.facility_name, 'care day facility name'),
    facility_timezone: timeZone(data.facility_timezone, 'care day facility timezone'),
    room_id: roomId,
    room_name: string(data.room_name, 'care day room name'),
    service_date: serviceDate,
    safety_as_of: timestamp(data.safety_as_of, 'care day safety snapshot time'),
    generated_at: timestamp(data.generated_at, 'care day generation time'),
    children,
  };
}

export function parseChildSafetyCard(value: unknown): ChildSafetyCard {
  const data = object(value, 'child safety card');
  noExtraKeys(data, ['child_id', 'child_name', 'profile_photo_url', 'age_group', 'facility_id', 'room_id', 'safety', 'contacts'], 'child safety card');
  const childId = string(data.child_id, 'safety child');
  const contacts = array(data.contacts, 'safety contacts', (item) => {
    const contact = object(item, 'safety contact');
    noExtraKeys(contact, ['id', 'contact_type', 'name', 'relationship', 'phone', 'authorized_pickup'], 'safety contact');
    return {
      id: string(contact.id, 'safety contact id'),
      contact_type: oneOf(contact.contact_type, ['primary_guardian', 'emergency_contact'] as const, 'safety contact type'),
      name: string(contact.name, 'safety contact name'),
      relationship: nullableString(contact.relationship, 'safety contact relationship'),
      phone: string(contact.phone, 'safety contact phone'),
      authorized_pickup: boolean(contact.authorized_pickup, 'legacy pickup marker'),
    } satisfies SafetyContact;
  });
  if (new Set(contacts.map((contact) => contact.id)).size !== contacts.length) throw new CareApiError('The safety card returned a contact more than once.');
  return {
    child_id: childId,
    child_name: string(data.child_name, 'safety child name'),
    profile_photo_url: childPhotoUrl(data.profile_photo_url, childId, 'safety child photo'),
    age_group: nullableString(data.age_group, 'safety child age group'),
    facility_id: string(data.facility_id, 'safety facility'),
    room_id: string(data.room_id, 'safety room'),
    safety: parseSafetySummary(data.safety),
    contacts,
  };
}

export function parseCareRecordEvent(value: unknown): CareRecordEvent {
  const data = object(value, 'care record event');
  noExtraKeys(data, ['id', 'care_record_id', 'actor_user_id', 'actor_name', 'client_operation_id', 'event_type', 'occurred_at', 'reason', 'before', 'after'], 'care record event');
  const dictionary = (field: unknown, label: string) => field == null ? null : object(field, label);
  return {
    id: string(data.id, 'care event id'),
    care_record_id: string(data.care_record_id, 'care event record'),
    actor_user_id: string(data.actor_user_id, 'care event actor'),
    actor_name: string(data.actor_name, 'care event actor name'),
    client_operation_id: string(data.client_operation_id, 'care event operation'),
    event_type: oneOf(data.event_type, ['recorded', 'sleep_finished', 'corrected', 'voided', 'auto_finished_at_checkout'] as const, 'care event type'),
    occurred_at: timestamp(data.occurred_at, 'care event time'),
    reason: nullableString(data.reason, 'care event reason'),
    before: dictionary(data.before, 'care event before state'),
    after: dictionary(data.after, 'care event after state'),
  };
}

interface RecordBoundary {
  organizationId: string;
  recordId?: string;
  facilityId?: string;
  roomId?: string;
  childId?: string;
  attendanceDayId?: string;
  serviceDate?: string;
}

function assertRecordBoundary(record: CareRecord, expected: RecordBoundary): CareRecord {
  if (record.organization_id !== expected.organizationId
    || (expected.recordId && record.id !== expected.recordId)
    || (expected.facilityId && record.facility_id !== expected.facilityId)
    || (expected.roomId && record.room_id !== expected.roomId)
    || (expected.childId && record.child_id !== expected.childId)
    || (expected.attendanceDayId && record.attendance_day_id !== expected.attendanceDayId)
    || (expected.serviceDate && record.service_date !== expected.serviceDate)) {
    throw new CareApiError('The care response crossed the requested record boundary.', 403);
  }
  return record;
}

export function createCareOperationId(): string {
  if (!globalThis.crypto?.randomUUID) throw new CareApiError('This browser cannot create a safe care operation identifier.');
  return globalThis.crypto.randomUUID();
}

export async function fetchCareRoomDay(roomId: string, serviceDate: string, organizationId: string, expectedFacilityId?: string, signal?: AbortSignal): Promise<CareRoomDay> {
  const query = new URLSearchParams({ date: serviceDate });
  const day = parseCareRoomDay(await apiRequest<unknown>(`/care/rooms/${encodeURIComponent(roomId)}/day?${query}`, { signal }));
  if (day.organization_id !== organizationId || day.room_id !== roomId || day.service_date !== serviceDate || (expectedFacilityId && day.facility_id !== expectedFacilityId)) {
    throw new CareApiError('The care day crossed the selected organization, facility, room, or date boundary.', 403);
  }
  return day;
}

export async function fetchChildSafetyCard(childId: string, facilityId: string, roomId: string, signal?: AbortSignal): Promise<ChildSafetyCard> {
  const query = new URLSearchParams({ facility_id: facilityId });
  const card = parseChildSafetyCard(await apiRequest<unknown>(`/care/children/${encodeURIComponent(childId)}/safety-card?${query}`, { signal }));
  if (card.child_id !== childId || card.facility_id !== facilityId || card.room_id !== roomId) {
    throw new CareApiError('The safety card crossed the selected child, facility, or room boundary.', 403);
  }
  return card;
}

export async function createCareRecord(input: CreateCareRecordInput, boundary: RecordBoundary): Promise<CareRecord> {
  const record = parseCareRecord(await apiRequest<unknown>('/care/records', { method: 'POST', body: JSON.stringify(input) }));
  return assertRecordBoundary(record, { ...boundary, attendanceDayId: input.attendance_day_id });
}

export async function finishSleepRecord(recordId: string, endedAt: string, expectedVersion: number, clientOperationId: string, boundary: RecordBoundary): Promise<CareRecord> {
  const record = parseCareRecord(await apiRequest<unknown>(`/care/records/${encodeURIComponent(recordId)}/finish-sleep`, {
    method: 'POST',
    body: JSON.stringify({ ended_at: endedAt, expected_version: expectedVersion, client_operation_id: clientOperationId }),
  }));
  return assertRecordBoundary(record, { ...boundary, recordId });
}

export async function correctCareRecord(recordId: string, input: CorrectCareRecordInput, boundary: RecordBoundary): Promise<CareRecord> {
  const record = parseCareRecord(await apiRequest<unknown>(`/care/records/${encodeURIComponent(recordId)}/correction`, { method: 'PUT', body: JSON.stringify(input) }));
  return assertRecordBoundary(record, { ...boundary, recordId });
}

export async function voidCareRecord(recordId: string, reason: string, expectedVersion: number, clientOperationId: string, boundary: RecordBoundary): Promise<CareRecord> {
  const record = parseCareRecord(await apiRequest<unknown>(`/care/records/${encodeURIComponent(recordId)}/void`, {
    method: 'POST',
    body: JSON.stringify({ reason, expected_version: expectedVersion, client_operation_id: clientOperationId }),
  }));
  return assertRecordBoundary(record, { ...boundary, recordId });
}

export async function fetchCareRecordHistory(recordId: string, signal?: AbortSignal): Promise<CareRecordEvent[]> {
  const events = array(await apiRequest<unknown>(`/care/records/${encodeURIComponent(recordId)}/history`, { signal }), 'care record history', parseCareRecordEvent);
  if (events.some((event) => event.care_record_id !== recordId)) throw new CareApiError('Care history crossed the requested record boundary.', 403);
  if (new Set(events.map((event) => event.id)).size !== events.length || new Set(events.map((event) => event.client_operation_id)).size !== events.length) {
    throw new CareApiError('Care history returned duplicate events.');
  }
  return events;
}
