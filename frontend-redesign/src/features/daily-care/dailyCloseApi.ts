import { apiRequest } from '../../api/client';
import type { AttendanceState, CareType } from './careApi';

export type DailyCloseAttentionFlag =
  | 'open_sleep'
  | 'medication_refused'
  | 'medication_omitted'
  | 'incident_draft'
  | 'incident_under_review';

export type DailyCloseCareCounts = Record<CareType, number>;

export interface DailyCloseMedicationCounts {
  administered: number;
  refused: number;
  omitted: number;
}

export interface DailyCloseIncidentCounts {
  draft: number;
  under_review: number;
  finalized: number;
}

export interface DailyCloseAttendanceCounts {
  not_recorded: number;
  on_site: number;
  checked_out: number;
  no_show: number;
}

export type DailyCloseAttentionCounts = Record<DailyCloseAttentionFlag, number>;

export interface DailyCloseChild {
  child_id: string;
  child_name: string;
  profile_photo_url: string | null;
  enrollment_id: string;
  attendance_day_id: string | null;
  attendance_state: AttendanceState;
  first_check_in_at: string | null;
  last_checkout_at: string | null;
  accumulated_minutes: number;
  currently_on_site: boolean;
  care_counts: DailyCloseCareCounts;
  open_sleep: boolean;
  most_recent_care_at: string | null;
  medication_administration_counts: DailyCloseMedicationCounts;
  most_recent_medication_at: string | null;
  incident_status_counts: DailyCloseIncidentCounts;
  most_recent_incident_at: string | null;
  attention_flags: DailyCloseAttentionFlag[];
}

export interface DailyCloseTotals {
  child_count: number;
  attendance_state_counts: DailyCloseAttendanceCounts;
  accumulated_minutes: number;
  currently_on_site: number;
  care_counts: DailyCloseCareCounts;
  open_sleep: number;
  medication_administration_counts: DailyCloseMedicationCounts;
  incident_status_counts: DailyCloseIncidentCounts;
  attention_flag_counts: DailyCloseAttentionCounts;
}

export interface RoomDailyClosePreview {
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string;
  room_name: string;
  service_date: string;
  generated_at: string;
  totals: DailyCloseTotals;
  children: DailyCloseChild[];
}

export class DailyCloseApiError extends Error {
  constructor(message: string, public readonly status = 0) {
    super(message);
    this.name = 'DailyCloseApiError';
  }
}

type Row = Record<string, unknown>;

export const DAILY_CLOSE_CARE_TYPES = [
  'feeding',
  'diaper',
  'toilet',
  'sleep',
  'mood',
  'activity',
] as const satisfies readonly CareType[];

export const DAILY_CLOSE_ATTENTION_FLAGS = [
  'open_sleep',
  'medication_refused',
  'medication_omitted',
  'incident_draft',
  'incident_under_review',
] as const satisfies readonly DailyCloseAttentionFlag[];

const ATTENDANCE_STATES = ['not_recorded', 'on_site', 'checked_out', 'no_show'] as const;
const MEDICATION_OUTCOMES = ['administered', 'refused', 'omitted'] as const;
const INCIDENT_STATUSES = ['draft', 'under_review', 'finalized'] as const;

function object(value: unknown, label: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new DailyCloseApiError(`The server returned an invalid ${label} response.`);
  }
  return value as Row;
}

function noExtraKeys(value: Row, allowed: readonly string[], label: string): void {
  const keys = Object.keys(value);
  if (keys.length !== allowed.length
    || keys.some((key) => !allowed.includes(key))
    || allowed.some((key) => !(key in value))) {
    throw new DailyCloseApiError(`The server returned an invalid ${label} payload.`);
  }
}

function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return value;
}

function nullableText(value: unknown, label: string): string | null {
  return value == null ? null : text(value, label);
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return value;
}

function nonNegativeInteger(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return Number(value);
}

function dateString(value: unknown, label: string): string {
  const result = text(value, label);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(result);
  if (!match) throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  const parsed = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  if (parsed.toISOString().slice(0, 10) !== result) {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

function timestamp(value: unknown, label: string): string {
  const result = text(value, label);
  if (Number.isNaN(Date.parse(result)) || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)) {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function timeZone(value: unknown, label: string): string {
  const result = text(value, label);
  try {
    new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0));
  } catch {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return result;
}

function oneOf<T extends string>(value: unknown, options: readonly T[], label: string): T {
  if (typeof value !== 'string' || !options.includes(value as T)) {
    throw new DailyCloseApiError(`The server returned an invalid ${label}.`);
  }
  return value as T;
}

function countRecord<K extends string>(value: unknown, keys: readonly K[], label: string): Record<K, number> {
  const row = object(value, label);
  noExtraKeys(row, keys, label);
  return Object.fromEntries(
    keys.map((key) => [key, nonNegativeInteger(row[key], `${label} ${key.replaceAll('_', ' ')}`)]),
  ) as Record<K, number>;
}

function childPhotoUrl(value: unknown, childId: string): string | null {
  const result = nullableText(value, 'daily close child photo');
  if (result !== null && result !== `/api/v1/children/${encodeURIComponent(childId)}/photo`) {
    throw new DailyCloseApiError('The server returned an invalid daily close child photo.');
  }
  return result;
}

function total(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function expectedAttentionFlags(child: Pick<DailyCloseChild, 'open_sleep' | 'medication_administration_counts' | 'incident_status_counts'>): DailyCloseAttentionFlag[] {
  return DAILY_CLOSE_ATTENTION_FLAGS.filter((flag) => {
    if (flag === 'open_sleep') return child.open_sleep;
    if (flag === 'medication_refused') return child.medication_administration_counts.refused > 0;
    if (flag === 'medication_omitted') return child.medication_administration_counts.omitted > 0;
    if (flag === 'incident_draft') return child.incident_status_counts.draft > 0;
    return child.incident_status_counts.under_review > 0;
  });
}

function parseChild(value: unknown): DailyCloseChild {
  const row = object(value, 'daily close child');
  noExtraKeys(row, [
    'child_id', 'child_name', 'profile_photo_url', 'enrollment_id', 'attendance_day_id',
    'attendance_state', 'first_check_in_at', 'last_checkout_at', 'accumulated_minutes',
    'currently_on_site', 'care_counts', 'open_sleep', 'most_recent_care_at',
    'medication_administration_counts', 'most_recent_medication_at',
    'incident_status_counts', 'most_recent_incident_at', 'attention_flags',
  ], 'daily close child');
  const childId = text(row.child_id, 'daily close child id');
  const attendanceDayId = nullableText(row.attendance_day_id, 'daily close attendance day');
  const attendanceState = oneOf(row.attendance_state, ATTENDANCE_STATES, 'daily close attendance state');
  const firstCheckInAt = nullableTimestamp(row.first_check_in_at, 'daily close first check-in');
  const lastCheckoutAt = nullableTimestamp(row.last_checkout_at, 'daily close last checkout');
  const accumulatedMinutes = nonNegativeInteger(row.accumulated_minutes, 'daily close accumulated minutes');
  const currentlyOnSite = boolean(row.currently_on_site, 'daily close on-site state');
  if (!attendanceDayId && (attendanceState !== 'not_recorded' || firstCheckInAt || lastCheckoutAt || accumulatedMinutes !== 0 || currentlyOnSite)) {
    throw new DailyCloseApiError('The daily close child returned attendance facts without an attendance-day boundary.');
  }
  if (attendanceState !== 'not_recorded' && !attendanceDayId) {
    throw new DailyCloseApiError('The daily close child returned incomplete attendance evidence.');
  }
  if (currentlyOnSite !== (attendanceState === 'on_site')) {
    throw new DailyCloseApiError('The daily close child returned inconsistent on-site evidence.');
  }
  if (attendanceState === 'on_site' && !firstCheckInAt) {
    throw new DailyCloseApiError('The daily close child returned on-site attendance without a check-in.');
  }
  if (attendanceState === 'checked_out' && (!firstCheckInAt || !lastCheckoutAt)) {
    throw new DailyCloseApiError('The daily close child returned checkout attendance without a complete interval.');
  }
  if (attendanceState === 'no_show' && (firstCheckInAt || lastCheckoutAt || accumulatedMinutes !== 0)) {
    throw new DailyCloseApiError('The daily close child returned interval facts for a no-show.');
  }
  if (lastCheckoutAt && (!firstCheckInAt || Date.parse(lastCheckoutAt) < Date.parse(firstCheckInAt))) {
    throw new DailyCloseApiError('The daily close child returned an invalid attendance time order.');
  }
  const careCounts = countRecord(row.care_counts, DAILY_CLOSE_CARE_TYPES, 'daily close care counts');
  const medicationCounts = countRecord(row.medication_administration_counts, MEDICATION_OUTCOMES, 'daily close medication counts');
  const incidentCounts = countRecord(row.incident_status_counts, INCIDENT_STATUSES, 'daily close incident counts');
  const openSleep = boolean(row.open_sleep, 'daily close open sleep');
  if (openSleep && careCounts.sleep === 0) {
    throw new DailyCloseApiError('The daily close child returned open sleep without a sleep record.');
  }
  const mostRecentCareAt = nullableTimestamp(row.most_recent_care_at, 'daily close most recent care time');
  const mostRecentMedicationAt = nullableTimestamp(row.most_recent_medication_at, 'daily close most recent medication time');
  const mostRecentIncidentAt = nullableTimestamp(row.most_recent_incident_at, 'daily close most recent incident time');
  if ((total(careCounts) > 0) !== Boolean(mostRecentCareAt)
    || (total(medicationCounts) > 0) !== Boolean(mostRecentMedicationAt)
    || (total(incidentCounts) > 0) !== Boolean(mostRecentIncidentAt)) {
    throw new DailyCloseApiError('The daily close child returned inconsistent most-recent fact evidence.');
  }
  if (!Array.isArray(row.attention_flags)) {
    throw new DailyCloseApiError('The server returned an invalid daily close attention flags response.');
  }
  const attentionFlags = row.attention_flags.map((flag) => oneOf(flag, DAILY_CLOSE_ATTENTION_FLAGS, 'daily close attention flag'));
  const expectedFlags = expectedAttentionFlags({ open_sleep: openSleep, medication_administration_counts: medicationCounts, incident_status_counts: incidentCounts });
  if (attentionFlags.length !== expectedFlags.length || attentionFlags.some((flag, index) => flag !== expectedFlags[index])) {
    throw new DailyCloseApiError('The daily close child returned attention flags that do not match its factual counts.');
  }
  return {
    child_id: childId,
    child_name: text(row.child_name, 'daily close child name'),
    profile_photo_url: childPhotoUrl(row.profile_photo_url, childId),
    enrollment_id: text(row.enrollment_id, 'daily close enrollment id'),
    attendance_day_id: attendanceDayId,
    attendance_state: attendanceState,
    first_check_in_at: firstCheckInAt,
    last_checkout_at: lastCheckoutAt,
    accumulated_minutes: accumulatedMinutes,
    currently_on_site: currentlyOnSite,
    care_counts: careCounts,
    open_sleep: openSleep,
    most_recent_care_at: mostRecentCareAt,
    medication_administration_counts: medicationCounts,
    most_recent_medication_at: mostRecentMedicationAt,
    incident_status_counts: incidentCounts,
    most_recent_incident_at: mostRecentIncidentAt,
    attention_flags: attentionFlags,
  };
}

function countsMatch(left: object, right: object): boolean {
  const leftEntries = Object.entries(left);
  const rightValues = new Map(Object.entries(right));
  return leftEntries.length === rightValues.size
    && leftEntries.every(([key, value]) => rightValues.get(key) === value);
}

export function parseRoomDailyClosePreview(value: unknown): RoomDailyClosePreview {
  const row = object(value, 'room daily close preview');
  noExtraKeys(row, [
    'organization_id', 'facility_id', 'facility_name', 'facility_timezone', 'room_id',
    'room_name', 'service_date', 'generated_at', 'totals', 'children',
  ], 'room daily close preview');
  const generatedAt = timestamp(row.generated_at, 'daily close generation time');
  if (!Array.isArray(row.children)) {
    throw new DailyCloseApiError('The server returned an invalid daily close children response.');
  }
  const children = row.children.map(parseChild);
  if (new Set(children.map((child) => child.child_id)).size !== children.length
    || new Set(children.map((child) => child.enrollment_id)).size !== children.length) {
    throw new DailyCloseApiError('The daily close preview returned a child or enrollment more than once.');
  }
  const totalsRow = object(row.totals, 'daily close totals');
  noExtraKeys(totalsRow, [
    'child_count', 'attendance_state_counts', 'accumulated_minutes', 'currently_on_site',
    'care_counts', 'open_sleep', 'medication_administration_counts',
    'incident_status_counts', 'attention_flag_counts',
  ], 'daily close totals');
  const totals: DailyCloseTotals = {
    child_count: nonNegativeInteger(totalsRow.child_count, 'daily close child total'),
    attendance_state_counts: countRecord(totalsRow.attendance_state_counts, ATTENDANCE_STATES, 'daily close attendance totals'),
    accumulated_minutes: nonNegativeInteger(totalsRow.accumulated_minutes, 'daily close accumulated-minute total'),
    currently_on_site: nonNegativeInteger(totalsRow.currently_on_site, 'daily close on-site total'),
    care_counts: countRecord(totalsRow.care_counts, DAILY_CLOSE_CARE_TYPES, 'daily close care totals'),
    open_sleep: nonNegativeInteger(totalsRow.open_sleep, 'daily close open-sleep total'),
    medication_administration_counts: countRecord(totalsRow.medication_administration_counts, MEDICATION_OUTCOMES, 'daily close medication totals'),
    incident_status_counts: countRecord(totalsRow.incident_status_counts, INCIDENT_STATUSES, 'daily close incident totals'),
    attention_flag_counts: countRecord(totalsRow.attention_flag_counts, DAILY_CLOSE_ATTENTION_FLAGS, 'daily close attention totals'),
  };
  const expectedAttendance = Object.fromEntries(ATTENDANCE_STATES.map((state) => [state, children.filter((child) => child.attendance_state === state).length]));
  const expectedCare = Object.fromEntries(DAILY_CLOSE_CARE_TYPES.map((kind) => [kind, children.reduce((sum, child) => sum + child.care_counts[kind], 0)]));
  const expectedMedication = Object.fromEntries(MEDICATION_OUTCOMES.map((outcome) => [outcome, children.reduce((sum, child) => sum + child.medication_administration_counts[outcome], 0)]));
  const expectedIncidents = Object.fromEntries(INCIDENT_STATUSES.map((status) => [status, children.reduce((sum, child) => sum + child.incident_status_counts[status], 0)]));
  const expectedAttention = Object.fromEntries(DAILY_CLOSE_ATTENTION_FLAGS.map((flag) => [flag, children.filter((child) => child.attention_flags.includes(flag)).length]));
  if (totals.child_count !== children.length
    || totals.accumulated_minutes !== children.reduce((sum, child) => sum + child.accumulated_minutes, 0)
    || totals.currently_on_site !== children.filter((child) => child.currently_on_site).length
    || totals.open_sleep !== children.filter((child) => child.open_sleep).length
    || !countsMatch(totals.attendance_state_counts, expectedAttendance)
    || !countsMatch(totals.care_counts, expectedCare)
    || !countsMatch(totals.medication_administration_counts, expectedMedication)
    || !countsMatch(totals.incident_status_counts, expectedIncidents)
    || !countsMatch(totals.attention_flag_counts, expectedAttention)) {
    throw new DailyCloseApiError('The daily close room totals do not match the bounded child facts.');
  }
  return {
    organization_id: text(row.organization_id, 'daily close organization id'),
    facility_id: text(row.facility_id, 'daily close facility id'),
    facility_name: text(row.facility_name, 'daily close facility name'),
    facility_timezone: timeZone(row.facility_timezone, 'daily close facility timezone'),
    room_id: text(row.room_id, 'daily close room id'),
    room_name: text(row.room_name, 'daily close room name'),
    service_date: dateString(row.service_date, 'daily close service date'),
    generated_at: generatedAt,
    totals,
    children,
  };
}

export async function fetchRoomDailyClosePreview(
  roomId: string,
  serviceDate: string,
  organizationId: string,
  facilityId: string,
  signal?: AbortSignal,
): Promise<RoomDailyClosePreview> {
  const requestedRoomId = text(roomId, 'requested daily close room id');
  const requestedDate = dateString(serviceDate, 'requested daily close service date');
  const requestedOrganizationId = text(organizationId, 'requested daily close organization id');
  const requestedFacilityId = text(facilityId, 'requested daily close facility id');
  const query = new URLSearchParams({ date: requestedDate });
  const preview = parseRoomDailyClosePreview(
    await apiRequest<unknown>(`/care/rooms/${encodeURIComponent(requestedRoomId)}/daily-close-preview?${query}`, { signal }),
  );
  if (preview.organization_id !== requestedOrganizationId
    || preview.facility_id !== requestedFacilityId
    || preview.room_id !== requestedRoomId
    || preview.service_date !== requestedDate) {
    throw new DailyCloseApiError(
      'The daily close preview crossed the selected organization, facility, room, or date boundary.',
      403,
    );
  }
  return preview;
}
