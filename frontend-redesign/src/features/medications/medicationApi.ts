import { apiRequest } from '../../api/client';

export type MedicationRoute = 'oral' | 'topical' | 'inhaled' | 'injected' | 'other';
export type MedicationKind = 'non_emergency' | 'emergency';
export type MedicationStorageMethod = 'locked_inaccessible' | 'emergency_accessible_per_plan';
export type MedicationPlanStatus = 'draft' | 'active' | 'archived';
export type AuthorizationStatus = 'not_recorded' | 'verified' | 'revoked';
export type MedicationOutcome = 'administered' | 'refused' | 'omitted';
export type MedicationAttendanceState = 'not_recorded' | 'on_site' | 'checked_out' | 'no_show';

export interface MedicationGuardianOption {
  id: string;
  name: string;
  relationship: string | null;
}

export interface MedicationPlan {
  id: string;
  organization_id: string;
  facility_id: string;
  child_id: string;
  child_name: string;
  medication_name: string;
  dosage: string;
  route: MedicationRoute;
  label_directions: string;
  scheduled_times: string[];
  as_needed: boolean;
  start_date: string;
  end_date: string | null;
  medication_kind: MedicationKind;
  storage_method: MedicationStorageMethod;
  storage_instructions: string;
  emergency_plan_reference: string | null;
  status: MedicationPlanStatus;
  authorization_status: AuthorizationStatus;
  authorization_is_current: boolean;
  signed_authorization_reference: string | null;
  authorization_guardian_id: string | null;
  authorization_guardian_name: string | null;
  authorization_signed_at: string | null;
  authorization_valid_until: string | null;
  authorization_verified_at: string | null;
  authorization_verified_by_user_id: string | null;
  authorization_revoked_at: string | null;
  authorization_revocation_reason: string | null;
  original_labelled_container_verified_at: string | null;
  label_directions_verified_at: string | null;
  created_by_user_id: string;
  created_by_name: string;
  eligible_guardians: MedicationGuardianOption[];
  signed_authorization_required: true;
  version: number;
  archived_at: string | null;
  archive_reason: string | null;
  last_event_type: 'created' | 'updated' | 'authorization_verified' | 'authorization_revoked' | 'activated' | 'archived';
  created_at: string;
  updated_at: string;
}

export interface MedicationPlanSnapshot {
  medication_name: string;
  dosage: string;
  route: MedicationRoute;
  label_directions: string;
  scheduled_times: string[];
  as_needed: boolean;
  medication_kind: MedicationKind;
  storage_method: MedicationStorageMethod;
  authorization_status: AuthorizationStatus;
  signed_authorization_reference: string;
  authorization_guardian_name: string;
  authorization_signed_at: string;
  authorization_valid_until: string | null;
  plan_version: number;
}

export interface MedicationAdministration {
  id: string;
  organization_id: string;
  facility_id: string;
  room_id: string;
  child_id: string;
  enrollment_id: string;
  attendance_day_id: string;
  medication_plan_id: string;
  plan_version: number;
  service_date: string;
  outcome: MedicationOutcome;
  scheduled_for: string | null;
  occurred_at: string;
  amount: string | null;
  reason: string | null;
  note: string | null;
  plan_snapshot: MedicationPlanSnapshot;
  staff_name_snapshot: string;
  staff_initials_snapshot: string;
  created_by_user_id: string;
  created_by_name: string;
  version: number;
  voided_at: string | null;
  voided_by_user_id: string | null;
  void_reason: string | null;
  last_event_type: 'recorded' | 'corrected' | 'voided';
  was_corrected: boolean;
  created_at: string;
  updated_at: string;
}

export interface MedicationDayChild {
  child_id: string;
  child_name: string;
  profile_photo_url: string | null;
  enrollment_id: string;
  attendance_day_id: string | null;
  attendance_state: MedicationAttendanceState;
  eligible_guardians: MedicationGuardianOption[];
  plans: MedicationPlan[];
  administrations: MedicationAdministration[];
}

export interface MedicationRoomDay {
  organization_id: string;
  facility_id: string;
  facility_name: string;
  facility_timezone: string;
  room_id: string;
  room_name: string;
  service_date: string;
  generated_at: string;
  children: MedicationDayChild[];
}

export interface MedicationPlanEvent {
  id: string;
  medication_plan_id: string;
  actor_user_id: string;
  actor_name: string;
  client_operation_id: string;
  event_type: MedicationPlan['last_event_type'];
  occurred_at: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface MedicationAdministrationEvent {
  id: string;
  medication_administration_id: string;
  actor_user_id: string;
  actor_name: string;
  client_operation_id: string;
  event_type: MedicationAdministration['last_event_type'];
  occurred_at: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface CreateMedicationPlanInput {
  facility_id: string;
  child_id: string;
  medication_name: string;
  dosage: string;
  route: MedicationRoute;
  label_directions: string;
  scheduled_times: string[];
  as_needed: boolean;
  start_date: string;
  end_date?: string | null;
  medication_kind: MedicationKind;
  storage_method: MedicationStorageMethod;
  storage_instructions: string;
  emergency_plan_reference?: string | null;
  client_operation_id: string;
}

export interface UpdateMedicationPlanInput extends CreateMedicationPlanInput {
  expected_version: number;
  reason: string;
}

export interface RecordAuthorizationInput {
  guardian_id: string;
  signed_authorization_reference: string;
  authorization_signed_at: string;
  valid_until?: string | null;
  expected_version: number;
  client_operation_id: string;
}

export interface RecordMedicationAdministrationInput {
  medication_plan_id: string;
  attendance_day_id: string;
  outcome: MedicationOutcome;
  scheduled_for: string | null;
  occurred_at: string;
  amount?: string | null;
  reason?: string | null;
  note?: string | null;
  client_operation_id: string;
}

export interface CorrectMedicationAdministrationInput extends RecordMedicationAdministrationInput {
  correction_reason: string;
  expected_version: number;
}

export class MedicationApiError extends Error {
  constructor(message: string, public readonly status = 0) {
    super(message);
    this.name = 'MedicationApiError';
  }
}

type Row = Record<string, unknown>;

function object(value: unknown, label: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MedicationApiError(`The server returned an invalid ${label} response.`);
  return value as Row;
}

function noExtraKeys(value: Row, allowed: readonly string[], label: string): void {
  if (Object.keys(value).some((key) => !allowed.includes(key))) throw new MedicationApiError(`The server returned an invalid ${label} payload.`);
}

function string(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return value;
}

function nullableString(value: unknown, label: string): string | null {
  if (value == null) return null;
  if (typeof value !== 'string') throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return value;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return value;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return Number(value);
}

function oneOf<T extends string>(value: unknown, choices: readonly T[], label: string): T {
  if (typeof value !== 'string' || !choices.includes(value as T)) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return value as T;
}

function array<T>(value: unknown, label: string, parser: (item: unknown, index: number) => T): T[] {
  if (!Array.isArray(value)) throw new MedicationApiError(`The server returned an invalid ${label} response.`);
  return value.map(parser);
}

function date(value: unknown, label: string): string {
  const result = string(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result)) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return result;
}

function time(value: unknown, label: string): string {
  const result = string(value, label);
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result)) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return result;
}

function timestamp(value: unknown, label: string): string {
  const result = string(value, label);
  if (Number.isNaN(Date.parse(result)) || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)) throw new MedicationApiError(`The server returned an invalid ${label}.`);
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function timeZone(value: unknown, label: string): string {
  const result = string(value, label);
  try { new Intl.DateTimeFormat('en-CA', { timeZone: result }).format(new Date(0)); } catch { throw new MedicationApiError(`The server returned an invalid ${label}.`); }
  return result;
}

function photoUrl(value: unknown, childId: string): string | null {
  const result = nullableString(value, 'medication child photo');
  if (result !== null && result !== `/api/v1/children/${encodeURIComponent(childId)}/photo`) throw new MedicationApiError('The server returned an invalid medication child photo.');
  return result;
}

function parseGuardian(value: unknown): MedicationGuardianOption {
  const row = object(value, 'medication guardian');
  noExtraKeys(row, ['id', 'name', 'relationship'], 'medication guardian');
  return { id: string(row.id, 'medication guardian id'), name: string(row.name, 'medication guardian name'), relationship: nullableString(row.relationship, 'medication guardian relationship') };
}

export function parseMedicationPlan(value: unknown): MedicationPlan {
  const row = object(value, 'medication plan');
  noExtraKeys(row, [
    'id', 'organization_id', 'facility_id', 'child_id', 'child_name', 'medication_name', 'dosage', 'route',
    'label_directions', 'scheduled_times', 'as_needed', 'start_date', 'end_date', 'medication_kind',
    'storage_method', 'storage_instructions', 'emergency_plan_reference', 'status', 'authorization_status', 'authorization_is_current',
    'signed_authorization_reference', 'authorization_guardian_id', 'authorization_guardian_name',
    'authorization_signed_at', 'authorization_valid_until', 'authorization_verified_at',
    'authorization_verified_by_user_id', 'authorization_revoked_at', 'authorization_revocation_reason',
    'original_labelled_container_verified_at', 'label_directions_verified_at', 'created_by_user_id',
    'created_by_name', 'eligible_guardians', 'signed_authorization_required', 'version', 'archived_at',
    'archive_reason', 'last_event_type', 'created_at', 'updated_at',
  ], 'medication plan');
  const scheduledTimes = array(row.scheduled_times, 'medication scheduled times', (item) => time(item, 'medication scheduled time'));
  if (new Set(scheduledTimes).size !== scheduledTimes.length) throw new MedicationApiError('The medication plan returned a scheduled time more than once.');
  const status = oneOf(row.status, ['draft', 'active', 'archived'] as const, 'medication plan status');
  const authorizationStatus = oneOf(row.authorization_status, ['not_recorded', 'verified', 'revoked'] as const, 'medication authorization evidence status');
  const signedReference = nullableString(row.signed_authorization_reference, 'signed authorization reference');
  const guardianId = nullableString(row.authorization_guardian_id, 'authorization guardian id');
  const guardianName = nullableString(row.authorization_guardian_name, 'authorization guardian name');
  const signedAt = nullableTimestamp(row.authorization_signed_at, 'authorization signature time');
  const validUntil = row.authorization_valid_until == null ? null : date(row.authorization_valid_until, 'authorization valid until date');
  const verifiedAt = nullableTimestamp(row.authorization_verified_at, 'authorization evidence verification time');
  const verifiedBy = nullableString(row.authorization_verified_by_user_id, 'authorization verifier');
  const authorizationIsCurrent = boolean(row.authorization_is_current, 'current signed authorization evidence marker');
  const revokedAt = nullableTimestamp(row.authorization_revoked_at, 'authorization revocation time');
  const revocationReason = nullableString(row.authorization_revocation_reason, 'authorization revocation reason');
  const hasEvidence = [signedReference, guardianId, guardianName, signedAt, verifiedAt, verifiedBy].every(Boolean);
  if (authorizationStatus === 'verified' && !hasEvidence) throw new MedicationApiError('The medication plan returned incomplete signed authorization evidence.');
  if (authorizationStatus === 'not_recorded' && [signedReference, guardianId, guardianName, signedAt, validUntil, verifiedAt, verifiedBy].some(Boolean)) throw new MedicationApiError('The medication plan returned authorization evidence marked as not recorded.');
  if (authorizationStatus === 'revoked' ? !hasEvidence || !revokedAt || !revocationReason?.trim() : Boolean(revokedAt) || Boolean(revocationReason?.trim())) throw new MedicationApiError('The medication plan returned inconsistent authorization-revocation evidence.');
  if (authorizationIsCurrent && authorizationStatus !== 'verified') throw new MedicationApiError('The medication plan marked non-verified consent evidence as current.');
  const endDate = row.end_date == null ? null : date(row.end_date, 'medication plan end date');
  const startDate = date(row.start_date, 'medication plan start date');
  if (endDate && endDate < startDate) throw new MedicationApiError('The medication plan returned an invalid date range.');
  const medicationKind = oneOf(row.medication_kind, ['non_emergency', 'emergency'] as const, 'medication kind');
  const storageMethod = oneOf(row.storage_method, ['locked_inaccessible', 'emergency_accessible_per_plan'] as const, 'medication storage method');
  const emergencyReference = nullableString(row.emergency_plan_reference, 'emergency medication plan reference');
  if (medicationKind === 'emergency' && (storageMethod !== 'emergency_accessible_per_plan' || !emergencyReference?.trim())) throw new MedicationApiError('The emergency medication plan returned incomplete emergency-plan evidence.');
  if (medicationKind === 'non_emergency' && storageMethod !== 'locked_inaccessible') throw new MedicationApiError('The non-emergency medication plan returned an unsafe storage method.');
  const signedAuthorizationRequired = boolean(row.signed_authorization_required, 'signed authorization requirement');
  if (!signedAuthorizationRequired) throw new MedicationApiError('The medication plan did not require signed authorization evidence.');
  const containerVerifiedAt = nullableTimestamp(row.original_labelled_container_verified_at, 'original labelled container verification time');
  const directionsVerifiedAt = nullableTimestamp(row.label_directions_verified_at, 'label directions verification time');
  if (status === 'active' ? authorizationStatus !== 'verified' || !containerVerifiedAt || !directionsVerifiedAt : Boolean(containerVerifiedAt) !== Boolean(directionsVerifiedAt)) throw new MedicationApiError('The medication plan returned inconsistent activation evidence.');
  const eligibleGuardians = array(row.eligible_guardians, 'eligible medication guardians', parseGuardian);
  if (new Set(eligibleGuardians.map((item) => item.id)).size !== eligibleGuardians.length) throw new MedicationApiError('The medication plan returned an eligible guardian more than once.');
  const archivedAt = nullableTimestamp(row.archived_at, 'medication plan archive time');
  const archiveReason = nullableString(row.archive_reason, 'medication plan archive reason');
  if (status === 'archived' ? !archivedAt || !archiveReason?.trim() : Boolean(archivedAt) || Boolean(archiveReason?.trim())) throw new MedicationApiError('The medication plan returned inconsistent archive evidence.');
  const lastEventType = oneOf(row.last_event_type, ['created', 'updated', 'authorization_verified', 'authorization_revoked', 'activated', 'archived'] as const, 'medication plan event type');
  if ((lastEventType === 'archived') !== (status === 'archived')) throw new MedicationApiError('The medication plan returned inconsistent last-event evidence.');
  return {
    id: string(row.id, 'medication plan id'), organization_id: string(row.organization_id, 'medication organization'), facility_id: string(row.facility_id, 'medication facility'), child_id: string(row.child_id, 'medication child'), child_name: string(row.child_name, 'medication child name'),
    medication_name: string(row.medication_name, 'medication name'), dosage: string(row.dosage, 'medication dosage'), route: oneOf(row.route, ['oral', 'topical', 'inhaled', 'injected', 'other'] as const, 'medication route'),
    label_directions: string(row.label_directions, 'label directions'), scheduled_times: scheduledTimes, as_needed: boolean(row.as_needed, 'as-needed marker'), start_date: startDate, end_date: endDate,
    medication_kind: medicationKind, storage_method: storageMethod, storage_instructions: string(row.storage_instructions, 'medication storage instructions'), emergency_plan_reference: emergencyReference,
    status, authorization_status: authorizationStatus, authorization_is_current: authorizationIsCurrent, signed_authorization_reference: signedReference, authorization_guardian_id: guardianId, authorization_guardian_name: guardianName,
    authorization_signed_at: signedAt, authorization_valid_until: validUntil, authorization_verified_at: verifiedAt, authorization_verified_by_user_id: verifiedBy,
    authorization_revoked_at: revokedAt, authorization_revocation_reason: revocationReason, original_labelled_container_verified_at: containerVerifiedAt, label_directions_verified_at: directionsVerifiedAt,
    created_by_user_id: string(row.created_by_user_id, 'medication plan creator'), created_by_name: string(row.created_by_name, 'medication plan creator name'), eligible_guardians: eligibleGuardians,
    signed_authorization_required: true, version: integer(row.version, 'medication plan version', 1), archived_at: archivedAt, archive_reason: archiveReason, last_event_type: lastEventType, created_at: timestamp(row.created_at, 'medication plan creation time'), updated_at: timestamp(row.updated_at, 'medication plan update time'),
  };
}

function parsePlanSnapshot(value: unknown): MedicationPlanSnapshot {
  const row = object(value, 'medication plan snapshot');
  noExtraKeys(row, ['medication_name', 'dosage', 'route', 'label_directions', 'scheduled_times', 'as_needed', 'medication_kind', 'storage_method', 'authorization_status', 'signed_authorization_reference', 'authorization_guardian_name', 'authorization_signed_at', 'authorization_valid_until', 'plan_version'], 'medication plan snapshot');
  const scheduledTimes = array(row.scheduled_times, 'snapshot medication scheduled times', (item) => time(item, 'snapshot medication scheduled time'));
  return {
    medication_name: string(row.medication_name, 'snapshot medication name'), dosage: string(row.dosage, 'snapshot medication dosage'), route: oneOf(row.route, ['oral', 'topical', 'inhaled', 'injected', 'other'] as const, 'snapshot medication route'),
    label_directions: string(row.label_directions, 'snapshot label directions'), scheduled_times: scheduledTimes, as_needed: boolean(row.as_needed, 'snapshot as-needed marker'), medication_kind: oneOf(row.medication_kind, ['non_emergency', 'emergency'] as const, 'snapshot medication kind'), storage_method: oneOf(row.storage_method, ['locked_inaccessible', 'emergency_accessible_per_plan'] as const, 'snapshot storage method'),
    authorization_status: oneOf(row.authorization_status, ['not_recorded', 'verified', 'revoked'] as const, 'snapshot authorization status'), signed_authorization_reference: string(row.signed_authorization_reference, 'snapshot authorization reference'), authorization_guardian_name: string(row.authorization_guardian_name, 'snapshot authorization guardian'), authorization_signed_at: timestamp(row.authorization_signed_at, 'snapshot authorization signature time'), authorization_valid_until: row.authorization_valid_until == null ? null : date(row.authorization_valid_until, 'snapshot authorization validity'), plan_version: integer(row.plan_version, 'snapshot plan version', 1),
  };
}

export function parseMedicationAdministration(value: unknown): MedicationAdministration {
  const row = object(value, 'medication administration');
  noExtraKeys(row, [
    'id', 'organization_id', 'facility_id', 'room_id', 'child_id', 'enrollment_id', 'attendance_day_id',
    'service_date', 'medication_plan_id', 'plan_version', 'plan_snapshot', 'outcome', 'scheduled_for', 'occurred_at', 'amount', 'reason', 'note', 'staff_name_snapshot', 'staff_initials_snapshot',
    'created_by_user_id', 'created_by_name', 'version', 'voided_at', 'voided_by_user_id', 'void_reason',
    'last_event_type', 'was_corrected', 'created_at', 'updated_at',
  ], 'medication administration');
  const outcome = oneOf(row.outcome, ['administered', 'refused', 'omitted'] as const, 'medication administration outcome');
  const amount = nullableString(row.amount, 'medication administration amount');
  const reason = nullableString(row.reason, 'medication administration reason');
  if (outcome === 'administered' ? !amount?.trim() || Boolean(reason?.trim()) : Boolean(amount?.trim()) || !reason?.trim()) throw new MedicationApiError('The medication administration returned inconsistent outcome evidence.');
  const voidedAt = nullableTimestamp(row.voided_at, 'medication administration void time');
  const voidedBy = nullableString(row.voided_by_user_id, 'medication administration void actor');
  const voidReason = nullableString(row.void_reason, 'medication administration void reason');
  if (Boolean(voidedAt) !== Boolean(voidedBy) || Boolean(voidedAt) !== Boolean(voidReason?.trim())) throw new MedicationApiError('The medication administration returned incomplete void evidence.');
  const lastEventType = oneOf(row.last_event_type, ['recorded', 'corrected', 'voided'] as const, 'medication administration event type');
  const wasCorrected = boolean(row.was_corrected, 'medication correction marker');
  if ((lastEventType === 'voided') !== Boolean(voidedAt) || (lastEventType === 'corrected' && !wasCorrected)) throw new MedicationApiError('The medication administration returned inconsistent audit evidence.');
  const snapshot = parsePlanSnapshot(row.plan_snapshot);
  const scheduledFor = row.scheduled_for == null ? null : time(row.scheduled_for, 'medication scheduled slot');
  if (scheduledFor === null ? !snapshot.as_needed : !snapshot.scheduled_times.includes(scheduledFor)) throw new MedicationApiError('The medication administration returned a schedule slot outside its immutable plan snapshot.');
  const planVersion = integer(row.plan_version, 'medication administration plan version', 1);
  if (snapshot.plan_version !== planVersion || snapshot.authorization_status !== 'verified') throw new MedicationApiError('The medication administration returned inconsistent immutable plan evidence.');
  return {
    id: string(row.id, 'medication administration id'), organization_id: string(row.organization_id, 'medication administration organization'), facility_id: string(row.facility_id, 'medication administration facility'), room_id: string(row.room_id, 'medication administration room'), child_id: string(row.child_id, 'medication administration child'), enrollment_id: string(row.enrollment_id, 'medication administration enrollment'), attendance_day_id: string(row.attendance_day_id, 'medication administration attendance day'), medication_plan_id: string(row.medication_plan_id, 'medication administration plan'), plan_version: planVersion, service_date: date(row.service_date, 'medication administration service date'),
    outcome, scheduled_for: scheduledFor, occurred_at: timestamp(row.occurred_at, 'medication administration time'), amount, reason, note: nullableString(row.note, 'medication administration note'), plan_snapshot: snapshot, staff_name_snapshot: string(row.staff_name_snapshot, 'administering staff name snapshot'), staff_initials_snapshot: string(row.staff_initials_snapshot, 'administering staff initials snapshot'),
    created_by_user_id: string(row.created_by_user_id, 'medication administration actor'), created_by_name: string(row.created_by_name, 'medication administration actor name'), version: integer(row.version, 'medication administration version', 1),
    voided_at: voidedAt, voided_by_user_id: voidedBy, void_reason: voidReason, last_event_type: lastEventType, was_corrected: wasCorrected, created_at: timestamp(row.created_at, 'medication administration creation time'), updated_at: timestamp(row.updated_at, 'medication administration update time'),
  };
}

function parseMedicationPlanEvent(value: unknown): MedicationPlanEvent {
  const row = object(value, 'medication plan event');
  noExtraKeys(row, ['id', 'medication_plan_id', 'actor_user_id', 'actor_name', 'client_operation_id', 'event_type', 'occurred_at', 'reason', 'before', 'after'], 'medication plan event');
  const dictionary = (item: unknown, label: string) => item == null ? null : object(item, label);
  return { id: string(row.id, 'medication plan event id'), medication_plan_id: string(row.medication_plan_id, 'medication plan event record'), actor_user_id: string(row.actor_user_id, 'medication plan event actor'), actor_name: string(row.actor_name, 'medication plan event actor name'), client_operation_id: string(row.client_operation_id, 'medication plan event operation'), event_type: oneOf(row.event_type, ['created', 'updated', 'authorization_verified', 'authorization_revoked', 'activated', 'archived'] as const, 'medication plan event type'), occurred_at: timestamp(row.occurred_at, 'medication plan event time'), reason: nullableString(row.reason, 'medication plan event reason'), before: dictionary(row.before, 'medication plan event before state'), after: dictionary(row.after, 'medication plan event after state') };
}

function parseMedicationAdministrationEvent(value: unknown): MedicationAdministrationEvent {
  const row = object(value, 'medication administration event');
  noExtraKeys(row, ['id', 'medication_administration_id', 'actor_user_id', 'actor_name', 'client_operation_id', 'event_type', 'occurred_at', 'reason', 'before', 'after'], 'medication administration event');
  const dictionary = (item: unknown, label: string) => item == null ? null : object(item, label);
  return { id: string(row.id, 'medication administration event id'), medication_administration_id: string(row.medication_administration_id, 'medication administration event record'), actor_user_id: string(row.actor_user_id, 'medication administration event actor'), actor_name: string(row.actor_name, 'medication administration event actor name'), client_operation_id: string(row.client_operation_id, 'medication administration event operation'), event_type: oneOf(row.event_type, ['recorded', 'corrected', 'voided'] as const, 'medication administration event type'), occurred_at: timestamp(row.occurred_at, 'medication administration event time'), reason: nullableString(row.reason, 'medication administration event reason'), before: dictionary(row.before, 'medication administration event before state'), after: dictionary(row.after, 'medication administration event after state') };
}

export function parseMedicationRoomDay(value: unknown): MedicationRoomDay {
  const row = object(value, 'medication room day');
  noExtraKeys(row, ['organization_id', 'facility_id', 'facility_name', 'facility_timezone', 'room_id', 'room_name', 'service_date', 'generated_at', 'children'], 'medication room day');
  const organizationId = string(row.organization_id, 'medication day organization');
  const facilityId = string(row.facility_id, 'medication day facility');
  const roomId = string(row.room_id, 'medication day room');
  const serviceDate = date(row.service_date, 'medication service date');
  const children = array(row.children, 'medication day children', (value) => {
    const child = object(value, 'medication day child');
    noExtraKeys(child, ['child_id', 'child_name', 'profile_photo_url', 'enrollment_id', 'attendance_day_id', 'attendance_state', 'eligible_guardians', 'plans', 'administrations'], 'medication day child');
    const childId = string(child.child_id, 'medication child id');
    const attendanceDayId = nullableString(child.attendance_day_id, 'medication attendance day');
    const attendanceState = oneOf(child.attendance_state, ['not_recorded', 'on_site', 'checked_out', 'no_show'] as const, 'medication attendance state');
    if ((attendanceDayId === null) !== (attendanceState === 'not_recorded')) throw new MedicationApiError('The medication day returned inconsistent attendance evidence.');
    const guardians = array(child.eligible_guardians, 'medication guardians', parseGuardian);
    const plans = array(child.plans, 'medication plans', parseMedicationPlan);
    const administrations = array(child.administrations, 'medication administrations', parseMedicationAdministration);
    if (new Set(guardians.map((item) => item.id)).size !== guardians.length || new Set(plans.map((item) => item.id)).size !== plans.length || new Set(administrations.map((item) => item.id)).size !== administrations.length) throw new MedicationApiError('The medication day returned duplicate records.');
    plans.forEach((plan) => { if (plan.organization_id !== organizationId || plan.facility_id !== facilityId || plan.child_id !== childId) throw new MedicationApiError('A medication plan crossed the selected organization, facility, or child boundary.'); });
    administrations.forEach((item) => { if (item.organization_id !== organizationId || item.facility_id !== facilityId || item.room_id !== roomId || item.child_id !== childId || item.attendance_day_id !== attendanceDayId || item.service_date !== serviceDate || !plans.some((plan) => plan.id === item.medication_plan_id)) throw new MedicationApiError('A medication administration crossed the selected room, child, attendance, plan, or date boundary.'); });
    return { child_id: childId, child_name: string(child.child_name, 'medication child name'), profile_photo_url: photoUrl(child.profile_photo_url, childId), enrollment_id: string(child.enrollment_id, 'medication enrollment'), attendance_day_id: attendanceDayId, attendance_state: attendanceState, eligible_guardians: guardians, plans, administrations };
  });
  if (new Set(children.map((child) => child.child_id)).size !== children.length) throw new MedicationApiError('The medication day returned a child more than once.');
  return { organization_id: organizationId, facility_id: facilityId, facility_name: string(row.facility_name, 'medication facility name'), facility_timezone: timeZone(row.facility_timezone, 'medication facility timezone'), room_id: roomId, room_name: string(row.room_name, 'medication room name'), service_date: serviceDate, generated_at: timestamp(row.generated_at, 'medication day generation time'), children };
}

function assertPlanBoundary(plan: MedicationPlan, organizationId: string, planId?: string, facilityId?: string, childId?: string): MedicationPlan {
  if (plan.organization_id !== organizationId || (planId && plan.id !== planId) || (facilityId && plan.facility_id !== facilityId) || (childId && plan.child_id !== childId)) throw new MedicationApiError('The medication plan crossed the requested record boundary.', 403);
  return plan;
}

export function createMedicationOperationId(): string {
  if (!globalThis.crypto?.randomUUID) throw new MedicationApiError('This browser cannot create a safe medication operation identifier.');
  return globalThis.crypto.randomUUID();
}

export async function fetchMedicationRoomDay(roomId: string, serviceDate: string, organizationId: string, facilityId: string, signal?: AbortSignal): Promise<MedicationRoomDay> {
  const query = new URLSearchParams({ date: serviceDate });
  const day = parseMedicationRoomDay(await apiRequest<unknown>(`/medications/rooms/${encodeURIComponent(roomId)}/day?${query}`, { signal }));
  if (day.organization_id !== organizationId || day.facility_id !== facilityId || day.room_id !== roomId || day.service_date !== serviceDate) throw new MedicationApiError('The medication day crossed the selected organization, facility, room, or date boundary.', 403);
  return day;
}

export async function fetchMedicationPlan(
  planId: string,
  organizationId: string,
  signal?: AbortSignal,
): Promise<MedicationPlan> {
  return assertPlanBoundary(
    parseMedicationPlan(
      await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(planId)}`, { signal }),
    ),
    organizationId,
    planId,
  );
}

export async function createMedicationPlan(input: CreateMedicationPlanInput, organizationId: string): Promise<MedicationPlan> {
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>('/medications/plans', { method: 'POST', body: JSON.stringify(input) })), organizationId, undefined, input.facility_id, input.child_id);
}

export async function updateMedicationPlan(planId: string, input: UpdateMedicationPlanInput, organizationId: string, facilityId: string, childId: string): Promise<MedicationPlan> {
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(planId)}`, { method: 'PUT', body: JSON.stringify(input) })), organizationId, planId, facilityId, childId);
}

export async function recordMedicationAuthorization(plan: MedicationPlan, input: RecordAuthorizationInput): Promise<MedicationPlan> {
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(plan.id)}/authorization`, { method: 'POST', body: JSON.stringify(input) })), plan.organization_id, plan.id, plan.facility_id, plan.child_id);
}

export async function activateMedicationPlan(plan: MedicationPlan, clientOperationId: string): Promise<MedicationPlan> {
  const body = { original_labelled_container_confirmed: true, label_directions_confirmed: true, expected_version: plan.version, client_operation_id: clientOperationId };
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(plan.id)}/activate`, { method: 'POST', body: JSON.stringify(body) })), plan.organization_id, plan.id, plan.facility_id, plan.child_id);
}

export async function archiveMedicationPlan(plan: MedicationPlan, reason: string, clientOperationId: string): Promise<MedicationPlan> {
  const body = { reason, expected_version: plan.version, client_operation_id: clientOperationId };
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(plan.id)}/archive`, { method: 'POST', body: JSON.stringify(body) })), plan.organization_id, plan.id, plan.facility_id, plan.child_id);
}

export async function recordMedicationAdministration(input: RecordMedicationAdministrationInput, boundary: { organizationId: string; facilityId: string; roomId: string; childId: string; attendanceDayId: string; serviceDate: string }): Promise<MedicationAdministration> {
  const record = parseMedicationAdministration(await apiRequest<unknown>('/medications/administrations', { method: 'POST', body: JSON.stringify(input) }));
  if (record.organization_id !== boundary.organizationId || record.facility_id !== boundary.facilityId || record.room_id !== boundary.roomId || record.child_id !== boundary.childId || record.attendance_day_id !== boundary.attendanceDayId || record.service_date !== boundary.serviceDate || record.medication_plan_id !== input.medication_plan_id) throw new MedicationApiError('The medication administration crossed the requested record boundary.', 403);
  return record;
}

export async function revokeMedicationAuthorization(plan: MedicationPlan, reason: string, clientOperationId: string): Promise<MedicationPlan> {
  const body = { reason, expected_version: plan.version, client_operation_id: clientOperationId };
  return assertPlanBoundary(parseMedicationPlan(await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(plan.id)}/revoke-authorization`, { method: 'POST', body: JSON.stringify(body) })), plan.organization_id, plan.id, plan.facility_id, plan.child_id);
}

export async function correctMedicationAdministration(record: MedicationAdministration, input: CorrectMedicationAdministrationInput): Promise<MedicationAdministration> {
  const next = parseMedicationAdministration(await apiRequest<unknown>(`/medications/administrations/${encodeURIComponent(record.id)}/correction`, { method: 'PUT', body: JSON.stringify(input) }));
  if (next.id !== record.id || next.organization_id !== record.organization_id || next.facility_id !== record.facility_id || next.room_id !== record.room_id || next.child_id !== record.child_id || next.attendance_day_id !== record.attendance_day_id || next.medication_plan_id !== record.medication_plan_id || next.service_date !== record.service_date) throw new MedicationApiError('The medication correction crossed its immutable record boundary.', 403);
  return next;
}

export async function voidMedicationAdministration(record: MedicationAdministration, reason: string, clientOperationId: string): Promise<MedicationAdministration> {
  const body = { reason, expected_version: record.version, client_operation_id: clientOperationId };
  const next = parseMedicationAdministration(await apiRequest<unknown>(`/medications/administrations/${encodeURIComponent(record.id)}/void`, { method: 'POST', body: JSON.stringify(body) }));
  if (next.id !== record.id || next.organization_id !== record.organization_id || next.attendance_day_id !== record.attendance_day_id) throw new MedicationApiError('The medication void crossed its immutable record boundary.', 403);
  return next;
}

export async function fetchMedicationPlanHistory(planId: string, signal?: AbortSignal): Promise<MedicationPlanEvent[]> {
  const value = await apiRequest<unknown>(`/medications/plans/${encodeURIComponent(planId)}/history`, { signal });
  const events = array(value, 'medication plan history', parseMedicationPlanEvent);
  if (events.some((event) => event.medication_plan_id !== planId) || new Set(events.map((event) => event.id)).size !== events.length || new Set(events.map((event) => event.client_operation_id)).size !== events.length) throw new MedicationApiError('Medication plan history crossed its record boundary or returned duplicate events.', 403);
  return events;
}

export async function fetchMedicationAdministrationHistory(recordId: string, signal?: AbortSignal): Promise<MedicationAdministrationEvent[]> {
  const value = await apiRequest<unknown>(`/medications/administrations/${encodeURIComponent(recordId)}/history`, { signal });
  const events = array(value, 'medication administration history', parseMedicationAdministrationEvent);
  if (events.some((event) => event.medication_administration_id !== recordId) || new Set(events.map((event) => event.id)).size !== events.length || new Set(events.map((event) => event.client_operation_id)).size !== events.length) throw new MedicationApiError('Medication administration history crossed its record boundary or returned duplicate events.', 403);
  return events;
}
