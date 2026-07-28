import { apiRequest } from '../../api/client';

export type IncidentCategory = 'injury' | 'illness' | 'missing_child' | 'unauthorized_release' | 'allegation' | 'emergency' | 'other';
export type IncidentSeverity = 'minor' | 'moderate' | 'serious' | 'critical';
export type IncidentStatus = 'draft' | 'under_review' | 'finalized';
export type IncidentAssessment = 'unassessed' | 'not_reportable' | 'other_reportable' | 'critical';
export type ExternalReportStatus = 'not_assessed' | 'not_required' | 'pending' | 'recorded';
export type SubmissionChannel = 'alberta_licensing_portal' | 'child_care_connect_then_portal';
export type MedicalAttention = 'none' | 'first_aid' | 'medical_practitioner' | 'emergency_services';
export type ParentNotificationStatus = 'pending' | 'notified' | 'unable_to_reach' | 'not_applicable';
export type ContactedAuthority = 'emergency_services' | 'police' | 'child_intervention' | 'child_care_connect' | 'other';

export interface IncidentRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string;
  room_name: string;
  attendance_day_id: string | null;
  child_id: string | null;
  child_name: string | null;
  enrollment_id: string | null;
  service_date: string;
  occurred_at: string;
  category: IncidentCategory;
  severity: IncidentSeverity;
  summary: string;
  immediate_actions: string;
  medical_attention: MedicalAttention;
  parent_notification_status: ParentNotificationStatus;
  parent_notified_at: string | null;
  parent_notification_notes: string | null;
  authorities_contacted: ContactedAuthority[];
  staff_present: string[];
  status: IncidentStatus;
  reporting_timeline: 'not_assessed' | 'not_reportable' | 'as_soon_as_possible_no_later_than_24_hours' | 'within_2_business_days';
  reviewer_note: string | null;
  finalized_at: string | null;
  finalized_by_user_id: string | null;
  reportability_assessment: IncidentAssessment;
  external_report_status: ExternalReportStatus;
  external_reported_at: string | null;
  external_confirmation_reference: string | null;
  external_submission_channel: SubmissionChannel | null;
  external_submitted_by_name: string | null;
  external_report_recorded_by_user_id: string | null;
  external_submission_performed_by_caresync: false;
  version: number;
  created_by_user_id: string;
  created_by_name: string;
  last_event_type: 'drafted' | 'updated' | 'submitted_for_review' | 'returned_to_draft' | 'finalized' | 'external_report_recorded';
  created_at: string;
  updated_at: string;
}

export interface IncidentList {
  organization_id: string;
  generated_at: string;
  incidents: IncidentRecord[];
}

export interface IncidentAttendanceOption {
  attendance_day_id: string;
  child_id: string;
  child_name: string;
  attendance_state: 'on_site' | 'checked_out';
}

export interface IncidentRoomContext {
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string;
  room_name: string;
  service_date: string;
  generated_at: string;
  attendance_options: IncidentAttendanceOption[];
}

export interface IncidentAuditEvent {
  id: string;
  incident_record_id: string;
  actor_user_id: string;
  actor_name: string;
  client_operation_id: string;
  event_type: string;
  occurred_at: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface CreateIncidentInput {
  facility_id: string;
  room_id: string;
  attendance_day_id?: string | null;
  occurred_at: string;
  category: IncidentCategory;
  severity: IncidentSeverity;
  summary: string;
  immediate_actions: string;
  medical_attention: MedicalAttention;
  parent_notification_status: ParentNotificationStatus;
  parent_notified_at?: string | null;
  parent_notification_notes?: string | null;
  authorities_contacted: ContactedAuthority[];
  staff_present: string[];
  client_operation_id: string;
}

export interface UpdateIncidentInput extends Omit<CreateIncidentInput, 'facility_id' | 'room_id' | 'attendance_day_id'> {
  expected_version: number;
  reason: string;
}

export class IncidentApiError extends Error {
  constructor(message: string, public readonly status = 0) {
    super(message);
    this.name = 'IncidentApiError';
  }
}

type Row = Record<string, unknown>;

function object(value: unknown, label: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new IncidentApiError(`The server returned an invalid ${label} response.`);
  return value as Row;
}

function noExtraKeys(value: Row, allowed: readonly string[], label: string): void {
  if (Object.keys(value).some((key) => !allowed.includes(key))) throw new IncidentApiError(`The server returned an invalid ${label} payload.`);
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return value;
}

function nullableString(value: unknown, label: string): string | null {
  if (value == null) return null;
  if (typeof value !== 'string') throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return value;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return Number(value);
}

function oneOf<T extends string>(value: unknown, choices: readonly T[], label: string): T {
  if (typeof value !== 'string' || !choices.includes(value as T)) throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return value as T;
}

function date(value: unknown, label: string): string {
  const result = string(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result)) throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return result;
}

function timestamp(value: unknown, label: string): string {
  const result = string(value, label);
  if (Number.isNaN(Date.parse(result)) || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)) throw new IncidentApiError(`The server returned an invalid ${label}.`);
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function timeZone(value: unknown, label: string): string {
  const result = string(value, label);
  try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new IncidentApiError(`The server returned an invalid ${label}.`); }
  return result;
}

function dictionary(value: unknown, label: string): Record<string, unknown> | null {
  return value == null ? null : object(value, label);
}

export function parseIncidentRecord(value: unknown): IncidentRecord {
  const row = object(value, 'incident');
  noExtraKeys(row, [
    'id', 'organization_id', 'facility_id', 'facility_name', 'facility_timezone', 'room_id', 'room_name',
    'attendance_day_id', 'child_id', 'child_name', 'enrollment_id', 'service_date', 'occurred_at',
    'category', 'severity', 'summary', 'immediate_actions', 'medical_attention', 'parent_notification_status',
    'parent_notified_at', 'parent_notification_notes', 'authorities_contacted', 'staff_present', 'status',
    'reportability_assessment', 'reporting_timeline', 'reviewer_note', 'finalized_at', 'finalized_by_user_id',
    'external_report_status', 'external_reported_at', 'external_confirmation_reference',
    'external_submission_channel', 'external_submitted_by_name', 'external_report_recorded_by_user_id',
    'external_submission_performed_by_caresync', 'created_by_user_id', 'created_by_name', 'version',
    'last_event_type', 'created_at', 'updated_at',
  ], 'incident');
  const status = oneOf(row.status, ['draft', 'under_review', 'finalized'] as const, 'incident status');
  const assessment = oneOf(row.reportability_assessment, ['unassessed', 'not_reportable', 'other_reportable', 'critical'] as const, 'incident reportability assessment');
  const reportingTimeline = oneOf(row.reporting_timeline, ['not_assessed', 'not_reportable', 'as_soon_as_possible_no_later_than_24_hours', 'within_2_business_days'] as const, 'incident reporting timeline');
  const externalStatus = oneOf(row.external_report_status, ['not_assessed', 'not_required', 'pending', 'recorded'] as const, 'external report status');
  const finalizedAt = nullableTimestamp(row.finalized_at, 'incident finalization time');
  const finalizedBy = nullableString(row.finalized_by_user_id, 'incident finalizer');
  const reviewerNote = nullableString(row.reviewer_note, 'incident reviewer note');
  if (status !== 'finalized' && (assessment !== 'unassessed' || reportingTimeline !== 'not_assessed' || finalizedAt || finalizedBy || reviewerNote)) throw new IncidentApiError('The incident returned premature finalization evidence.');
  if (assessment === 'unassessed' && externalStatus !== 'not_assessed') throw new IncidentApiError('The unassessed incident returned premature external-report evidence.');
  if (status === 'finalized' && (assessment === 'unassessed' || !finalizedAt || !finalizedBy || !reviewerNote?.trim())) throw new IncidentApiError('The incident returned incomplete finalization evidence.');
  if (assessment === 'not_reportable' && (externalStatus !== 'not_required' || reportingTimeline !== 'not_reportable')) throw new IncidentApiError('The incident returned inconsistent external-report assessment evidence.');
  if (assessment === 'critical' && reportingTimeline !== 'as_soon_as_possible_no_later_than_24_hours') throw new IncidentApiError('The critical incident returned an invalid reporting timeline.');
  if (assessment === 'other_reportable' && reportingTimeline !== 'within_2_business_days') throw new IncidentApiError('The reportable incident returned an invalid reporting timeline.');
  if ((assessment === 'other_reportable' || assessment === 'critical') && !['pending', 'recorded'].includes(externalStatus)) throw new IncidentApiError('The incident returned incomplete external-report tracking.');
  const reportedAt = nullableTimestamp(row.external_reported_at, 'external report time');
  const confirmationReference = nullableString(row.external_confirmation_reference, 'external confirmation reference');
  const submissionChannel = row.external_submission_channel == null ? null : oneOf(row.external_submission_channel, ['alberta_licensing_portal', 'child_care_connect_then_portal'] as const, 'external submission channel');
  const submittedByName = nullableString(row.external_submitted_by_name, 'external submitter name');
  const recordedByUserId = nullableString(row.external_report_recorded_by_user_id, 'external report recorder');
  const hasExternalEvidence = [reportedAt, confirmationReference, submissionChannel, submittedByName, recordedByUserId].every(Boolean);
  if (externalStatus === 'recorded' ? !hasExternalEvidence : [reportedAt, confirmationReference, submissionChannel, submittedByName, recordedByUserId].some(Boolean)) throw new IncidentApiError('The incident returned inconsistent manual external-report evidence.');
  if (row.external_submission_performed_by_caresync !== false) throw new IncidentApiError('The incident response did not prove that CareSync performed no external submission.');
  const attendanceDayId = nullableString(row.attendance_day_id, 'incident attendance day');
  const childId = nullableString(row.child_id, 'incident child');
  const childName = nullableString(row.child_name, 'incident child name');
  const enrollmentId = nullableString(row.enrollment_id, 'incident enrollment');
  if ([attendanceDayId, childId, childName, enrollmentId].some(Boolean) && ![attendanceDayId, childId, childName, enrollmentId].every(Boolean)) throw new IncidentApiError('The incident returned an incomplete child-attendance snapshot.');
  const parentNotificationStatus = oneOf(row.parent_notification_status, ['pending', 'notified', 'unable_to_reach', 'not_applicable'] as const, 'parent notification status');
  const parentNotifiedAt = nullableTimestamp(row.parent_notified_at, 'parent notification time');
  const parentNotificationNotes = nullableString(row.parent_notification_notes, 'parent notification notes');
  if (parentNotificationStatus === 'notified' ? !parentNotifiedAt || !parentNotificationNotes?.trim() : Boolean(parentNotifiedAt)) throw new IncidentApiError('The incident returned inconsistent parent-notification evidence.');
  if (parentNotificationStatus === 'unable_to_reach' && !parentNotificationNotes?.trim()) throw new IncidentApiError('The incident returned an unsuccessful parent contact without details.');
  if ((parentNotificationStatus === 'pending' || parentNotificationStatus === 'not_applicable') && parentNotificationNotes?.trim()) throw new IncidentApiError('The incident returned parent-notification notes for an incompatible status.');
  if (!Array.isArray(row.authorities_contacted)) throw new IncidentApiError('The server returned invalid contacted authorities.');
  const authorities = row.authorities_contacted.map((value) => oneOf(value, ['emergency_services', 'police', 'child_intervention', 'child_care_connect', 'other'] as const, 'contacted authority'));
  if (new Set(authorities).size !== authorities.length) throw new IncidentApiError('The incident returned a contacted authority more than once.');
  if (!Array.isArray(row.staff_present) || row.staff_present.length > 50) throw new IncidentApiError('The server returned invalid staff present.');
  const staffPresent = row.staff_present.map((value) => string(value, 'staff-present name'));
  return {
    id: string(row.id, 'incident id'), organization_id: string(row.organization_id, 'incident organization'), facility_id: string(row.facility_id, 'incident facility'), facility_name: string(row.facility_name, 'incident facility name'), facility_timezone: timeZone(row.facility_timezone, 'incident facility timezone'), room_id: string(row.room_id, 'incident room'), room_name: string(row.room_name, 'incident room name'),
    attendance_day_id: attendanceDayId, child_id: childId, child_name: childName, enrollment_id: enrollmentId, service_date: date(row.service_date, 'incident service date'), occurred_at: timestamp(row.occurred_at, 'incident occurrence time'),
    category: oneOf(row.category, ['injury', 'illness', 'missing_child', 'unauthorized_release', 'allegation', 'emergency', 'other'] as const, 'incident category'), severity: oneOf(row.severity, ['minor', 'moderate', 'serious', 'critical'] as const, 'incident working severity'), summary: string(row.summary, 'incident summary'), immediate_actions: string(row.immediate_actions, 'incident immediate actions'),
    medical_attention: oneOf(row.medical_attention, ['none', 'first_aid', 'medical_practitioner', 'emergency_services'] as const, 'medical attention'), parent_notification_status: parentNotificationStatus, parent_notified_at: parentNotifiedAt, parent_notification_notes: parentNotificationNotes, authorities_contacted: authorities, staff_present: staffPresent,
    status, reportability_assessment: assessment, reporting_timeline: reportingTimeline, reviewer_note: reviewerNote, finalized_at: finalizedAt, finalized_by_user_id: finalizedBy, external_report_status: externalStatus,
    external_reported_at: reportedAt, external_confirmation_reference: confirmationReference, external_submission_channel: submissionChannel, external_submitted_by_name: submittedByName, external_report_recorded_by_user_id: recordedByUserId, external_submission_performed_by_caresync: false,
    version: integer(row.version, 'incident version', 1), created_by_user_id: string(row.created_by_user_id, 'incident creator'), created_by_name: string(row.created_by_name, 'incident creator name'), last_event_type: oneOf(row.last_event_type, ['drafted', 'updated', 'submitted_for_review', 'returned_to_draft', 'finalized', 'external_report_recorded'] as const, 'incident event type'), created_at: timestamp(row.created_at, 'incident creation time'), updated_at: timestamp(row.updated_at, 'incident update time'),
  };
}

export function parseIncidentList(value: unknown): IncidentList {
  const row = object(value, 'incident list');
  noExtraKeys(row, ['organization_id', 'generated_at', 'incidents'], 'incident list');
  const organizationId = string(row.organization_id, 'incident list organization');
  if (!Array.isArray(row.incidents)) throw new IncidentApiError('The server returned an invalid incident list response.');
  const incidents = row.incidents.map(parseIncidentRecord);
  if (new Set(incidents.map((incident) => incident.id)).size !== incidents.length) throw new IncidentApiError('The incident list returned a record more than once.');
  incidents.forEach((incident) => { if (incident.organization_id !== organizationId) throw new IncidentApiError('An incident crossed the selected organization boundary.'); });
  return { organization_id: organizationId, generated_at: timestamp(row.generated_at, 'incident list generation time'), incidents };
}

export function parseIncidentRoomContext(value: unknown): IncidentRoomContext {
  const row = object(value, 'incident room context');
  noExtraKeys(row, ['organization_id', 'facility_id', 'facility_name', 'facility_timezone', 'room_id', 'room_name', 'service_date', 'generated_at', 'attendance_options'], 'incident room context');
  if (!Array.isArray(row.attendance_options)) throw new IncidentApiError('The server returned invalid incident attendance options.');
  const options = row.attendance_options.map((value) => {
    const option = object(value, 'incident attendance option');
    noExtraKeys(option, ['attendance_day_id', 'child_id', 'child_name', 'attendance_state'], 'incident attendance option');
    return { attendance_day_id: string(option.attendance_day_id, 'incident attendance day'), child_id: string(option.child_id, 'incident attendance child'), child_name: string(option.child_name, 'incident attendance child name'), attendance_state: oneOf(option.attendance_state, ['on_site', 'checked_out'] as const, 'incident attendance state') };
  });
  if (new Set(options.map((option) => option.attendance_day_id)).size !== options.length || new Set(options.map((option) => option.child_id)).size !== options.length) throw new IncidentApiError('The incident context returned duplicate attendance options.');
  return { organization_id: string(row.organization_id, 'incident context organization'), facility_id: string(row.facility_id, 'incident context facility'), facility_name: string(row.facility_name, 'incident context facility name'), facility_timezone: timeZone(row.facility_timezone, 'incident context facility timezone'), room_id: string(row.room_id, 'incident context room'), room_name: string(row.room_name, 'incident context room name'), service_date: date(row.service_date, 'incident context date'), generated_at: timestamp(row.generated_at, 'incident context generation time'), attendance_options: options };
}

export function parseIncidentAuditEvent(value: unknown): IncidentAuditEvent {
  const row = object(value, 'incident audit event');
  noExtraKeys(row, ['id', 'incident_record_id', 'actor_user_id', 'actor_name', 'client_operation_id', 'event_type', 'occurred_at', 'reason', 'before', 'after'], 'incident audit event');
  return { id: string(row.id, 'incident event id'), incident_record_id: string(row.incident_record_id, 'incident event record'), actor_user_id: string(row.actor_user_id, 'incident event actor'), actor_name: string(row.actor_name, 'incident event actor name'), client_operation_id: string(row.client_operation_id, 'incident event operation'), event_type: string(row.event_type, 'incident event type'), occurred_at: timestamp(row.occurred_at, 'incident event time'), reason: nullableString(row.reason, 'incident event reason'), before: dictionary(row.before, 'incident event before state'), after: dictionary(row.after, 'incident event after state') };
}

function assertBoundary(incident: IncidentRecord, expected: { organizationId: string; facilityId?: string; roomId?: string; incidentId?: string }): IncidentRecord {
  if (incident.organization_id !== expected.organizationId || (expected.facilityId && incident.facility_id !== expected.facilityId) || (expected.roomId && incident.room_id !== expected.roomId) || (expected.incidentId && incident.id !== expected.incidentId)) throw new IncidentApiError('The incident response crossed the requested record boundary.', 403);
  return incident;
}

export function createIncidentOperationId(): string {
  if (!globalThis.crypto?.randomUUID) throw new IncidentApiError('This browser cannot create a safe incident operation identifier.');
  return globalThis.crypto.randomUUID();
}

export async function fetchIncidents(filters: { facilityId: string; roomId?: string; status?: IncidentStatus }, organizationId: string, signal?: AbortSignal): Promise<IncidentList> {
  const query = new URLSearchParams({ facility_id: filters.facilityId });
  if (filters.roomId) query.set('room_id', filters.roomId);
  if (filters.status) query.set('status', filters.status);
  const list = parseIncidentList(await apiRequest<unknown>(`/incidents?${query}`, { signal }));
  if (list.organization_id !== organizationId || list.incidents.some((incident) => incident.facility_id !== filters.facilityId || (filters.roomId && incident.room_id !== filters.roomId))) throw new IncidentApiError('The incident list crossed the selected organization, facility, or room boundary.', 403);
  return list;
}

export async function fetchIncident(recordId: string, organizationId: string, signal?: AbortSignal): Promise<IncidentRecord> {
  const incident = parseIncidentRecord(
    await apiRequest<unknown>(`/incidents/${encodeURIComponent(recordId)}`, { signal }),
  );
  return assertBoundary(incident, { organizationId, incidentId: recordId });
}

export async function fetchIncidentRoomContext(roomId: string, serviceDate: string, organizationId: string, facilityId: string, signal?: AbortSignal): Promise<IncidentRoomContext> {
  const query = new URLSearchParams({ date: serviceDate });
  const context = parseIncidentRoomContext(await apiRequest<unknown>(`/incidents/rooms/${encodeURIComponent(roomId)}/context?${query}`, { signal }));
  if (context.organization_id !== organizationId || context.facility_id !== facilityId || context.room_id !== roomId || context.service_date !== serviceDate) throw new IncidentApiError('The incident context crossed the selected organization, facility, room, or date boundary.', 403);
  return context;
}

export async function createIncident(input: CreateIncidentInput, organizationId: string): Promise<IncidentRecord> {
  return assertBoundary(parseIncidentRecord(await apiRequest<unknown>('/incidents', { method: 'POST', body: JSON.stringify(input) })), { organizationId, facilityId: input.facility_id, roomId: input.room_id });
}

export async function updateIncident(incident: IncidentRecord, input: UpdateIncidentInput): Promise<IncidentRecord> {
  return assertBoundary(parseIncidentRecord(await apiRequest<unknown>(`/incidents/${encodeURIComponent(incident.id)}`, { method: 'PUT', body: JSON.stringify(input) })), { organizationId: incident.organization_id, facilityId: incident.facility_id, roomId: incident.room_id, incidentId: incident.id });
}

async function transitionIncident(incident: IncidentRecord, action: string, body: Record<string, unknown>): Promise<IncidentRecord> {
  return assertBoundary(parseIncidentRecord(await apiRequest<unknown>(`/incidents/${encodeURIComponent(incident.id)}/${action}`, { method: 'POST', body: JSON.stringify(body) })), { organizationId: incident.organization_id, facilityId: incident.facility_id, roomId: incident.room_id, incidentId: incident.id });
}

export function submitIncidentForReview(incident: IncidentRecord, clientOperationId: string): Promise<IncidentRecord> {
  return transitionIncident(incident, 'submit-review', { expected_version: incident.version, client_operation_id: clientOperationId });
}

export function returnIncidentToDraft(incident: IncidentRecord, reason: string, clientOperationId: string): Promise<IncidentRecord> {
  return transitionIncident(incident, 'return-draft', { reason, expected_version: incident.version, client_operation_id: clientOperationId });
}

export function finalizeIncident(incident: IncidentRecord, assessment: Exclude<IncidentAssessment, 'unassessed'>, reviewerNote: string, clientOperationId: string): Promise<IncidentRecord> {
  return transitionIncident(incident, 'finalize', { reportability_assessment: assessment, reviewer_note: reviewerNote, expected_version: incident.version, client_operation_id: clientOperationId });
}

export function recordExternalReport(incident: IncidentRecord, input: { reported_at: string; confirmation_reference: string; submission_channel: SubmissionChannel; submitted_by_name: string; client_operation_id: string }): Promise<IncidentRecord> {
  return transitionIncident(incident, 'external-report', { ...input, expected_version: incident.version });
}

export async function fetchIncidentHistory(incidentId: string, signal?: AbortSignal): Promise<IncidentAuditEvent[]> {
  const value = await apiRequest<unknown>(`/incidents/${encodeURIComponent(incidentId)}/history`, { signal });
  if (!Array.isArray(value)) throw new IncidentApiError('The server returned an invalid incident history response.');
  const events = value.map(parseIncidentAuditEvent);
  if (events.some((event) => event.incident_record_id !== incidentId) || new Set(events.map((event) => event.id)).size !== events.length || new Set(events.map((event) => event.client_operation_id)).size !== events.length) throw new IncidentApiError('The incident history crossed its record boundary or returned duplicate events.', 403);
  return events;
}
