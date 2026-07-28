import {
  API_URL,
  ApiError,
  addOrganizationHeader,
  apiRequest,
  getSessionToken,
} from '../../api/client';

export const TRANSPORT_REGISTRY_PATH = '/staff/transport-registry' as const;
export const TRANSPORT_REGISTRY_SCHEMA = '0032' as const;
export const MAX_TRANSPORT_EVIDENCE_BYTES = 50 * 1024 * 1024;

export type QualificationType =
  | 'driver_licence'
  | 'driver_abstract'
  | 'police_check'
  | 'vulnerable_sector_search'
  | 'first_aid'
  | 'vehicle_insurance_permission';
export type VehicleEvidenceType = 'registration' | 'insurance' | 'inspection' | 'maintenance';
export type ReviewDecision = 'verified' | 'rejected';
export type AuthorizationDecision = 'needs_review' | 'authorized' | 'denied' | 'revoked';

export interface DriverCapabilityVersion {
  id: string;
  version_number: number;
  status: 'declared' | 'withdrawn';
  willing_to_drive: boolean;
  licence_jurisdiction: string | null;
  licence_class: string | null;
  vehicle_access: 'none' | 'organization_vehicle_only' | 'personal_vehicle' | 'either';
  preferred_service_radius_km: number | null;
  effective_at: string;
}

export interface QualificationVersion {
  id: string;
  qualification_type: QualificationType;
  version_number: number;
  status: 'declared' | 'verified' | 'rejected' | 'expired' | 'revoked';
  jurisdiction: string | null;
  qualification_class: string | null;
  identifier_last4: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  evidence_present: boolean;
  content_path: string | null;
  effective_at: string;
}

export interface QualificationReview {
  id: string;
  source_qualification_version_id: string;
  result_qualification_version_id: string;
  decision: ReviewDecision;
  reason_code: string;
  reviewed_at: string;
}

export interface DriverAuthorization {
  id: string;
  decision_sequence: number;
  capability_version_id: string;
  qualification_version_ids: string[];
  decision: AuthorizationDecision;
  reason_code: string;
  authorization_valid_from: string | null;
  authorization_valid_until: string | null;
  reviewed_at: string;
  operational_driver_ready: false;
  dispatch_authorized: false;
}

export interface DriverReadiness {
  id: string;
  decision_sequence: number;
  decision: 'incomplete' | 'needs_review' | 'blocked';
  reason_codes: string[];
  vehicle_id: string | null;
  evaluated_at: string;
  operational_driver_ready: false;
  dispatch_authorized: false;
}

export interface TransportStaffRecord {
  membership_id: string;
  first_name: string;
  last_name: string;
  capabilities: DriverCapabilityVersion[];
  qualifications: QualificationVersion[];
  qualification_reviews: QualificationReview[];
  authorizations: DriverAuthorization[];
  readiness: DriverReadiness[];
  capabilities_truncated: boolean;
  qualification_types_truncated: QualificationType[];
  qualification_reviews_truncated: boolean;
  authorizations_truncated: boolean;
  readiness_truncated: boolean;
}

export interface VehicleVersion {
  id: string;
  version_number: number;
  make: string;
  model: string;
  model_year: number;
  color: string | null;
  plate_token: string;
  plate_jurisdiction: string;
  passenger_capacity: number;
  child_passenger_capacity: number;
  wheelchair_accessible: boolean;
  effective_at: string;
}

export interface VehicleEvidence {
  id: string;
  vehicle_version_id: string;
  evidence_type: VehicleEvidenceType;
  version_number: number;
  status: 'provided' | 'verified' | 'rejected' | 'expired' | 'revoked';
  issue_date: string | null;
  expiry_date: string | null;
  original_filename: string | null;
  media_type: 'application/pdf' | 'image/png' | 'image/jpeg';
  byte_size: number;
  content_path: string;
  recorded_at: string;
}

export interface VehicleEvidenceReview {
  id: string;
  source_evidence_version_id: string;
  result_evidence_version_id: string;
  decision: ReviewDecision;
  reason_code: string;
  reviewed_at: string;
}

export interface TransportVehicleRecord {
  id: string;
  owner_kind: 'organization' | 'staff_personal';
  staff_owner_membership_id: string | null;
  retired_at: string | null;
  versions: VehicleVersion[];
  evidence: VehicleEvidence[];
  evidence_reviews: VehicleEvidenceReview[];
  versions_truncated: boolean;
  evidence_types_truncated: VehicleEvidenceType[];
  evidence_reviews_truncated: boolean;
}

export interface TransportRegistryWorkspace {
  schema_version: '0032';
  generated_at: string;
  staff: TransportStaffRecord[];
  vehicles: TransportVehicleRecord[];
  staff_truncated: boolean;
  vehicles_truncated: boolean;
  operational_driver_ready: false;
  dispatch_authorized: false;
}

export type TransportCommandKind =
  | 'driver_declaration'
  | 'qualification_evidence'
  | 'qualification_review'
  | 'driver_authorization'
  | 'vehicle_create'
  | 'vehicle_version'
  | 'vehicle_retire'
  | 'vehicle_evidence'
  | 'vehicle_evidence_review'
  | 'readiness_evaluation';

export interface TransportCommandReceipt {
  schema_version: '0032';
  client_operation_id: string;
  command_kind: TransportCommandKind;
  result_kind:
    | 'driver_capability'
    | 'driver_qualification'
    | 'driver_authorization'
    | 'vehicle'
    | 'vehicle_version'
    | 'vehicle_evidence'
    | 'driver_readiness';
  result_id: string;
  committed_at: string;
  exact_retry: boolean;
  operational_driver_ready: false;
  dispatch_authorized: false;
}

export interface VehicleFactsInput {
  make: string;
  model: string;
  model_year: number;
  color: string | null;
  plate_token: string;
  plate_jurisdiction: string;
  passenger_capacity: number;
  child_passenger_capacity: number;
  wheelchair_accessible: boolean;
}

export interface DriverDeclarationInput {
  status: 'declared' | 'withdrawn';
  willing_to_drive: boolean;
  licence_jurisdiction: string | null;
  licence_jurisdiction_other: string | null;
  licence_class: string | null;
  vehicle_access: 'none' | 'organization_vehicle_only' | 'personal_vehicle' | 'either';
  preferred_service_radius_km: number | null;
}

export interface QualificationEvidenceInput {
  qualification_type: QualificationType;
  jurisdiction: string | null;
  qualification_class: string | null;
  identifier_last4: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  file: File;
}

export interface VehicleEvidenceInput {
  evidence_type: VehicleEvidenceType;
  issue_date: string | null;
  expiry_date: string | null;
  file: File;
}

export class TransportRegistryApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TransportRegistryApiError';
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const QUALIFICATION_TYPES: readonly QualificationType[] = ['driver_licence', 'driver_abstract', 'police_check', 'vulnerable_sector_search', 'first_aid', 'vehicle_insurance_permission'];
const VEHICLE_EVIDENCE_TYPES: readonly VehicleEvidenceType[] = ['registration', 'insurance', 'inspection', 'maintenance'];

function invalid(label: string): never {
  throw new TransportRegistryApiError(`The server returned an invalid ${label}.`);
}

function exactObject(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid(label);
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) invalid(`${label} shape`);
  return row;
}

function text(value: unknown, label: string, maximum = 2048): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) invalid(label);
  return value as string;
}

function nullableText(value: unknown, label: string, maximum = 2048): string | null {
  return value == null ? null : text(value, label, maximum);
}

function id(value: unknown, label: string): string {
  const result = text(value, label);
  if (!UUID.test(result)) invalid(label);
  return result.toLowerCase();
}

function validCalendarValue(value: string): boolean {
  if (!DATE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const utc = new Date(Date.UTC(year!, month! - 1, day!));
  return Number.isFinite(utc.getTime()) && utc.toISOString().slice(0, 10) === value;
}

function timestamp(value: unknown, label: string): string {
  const result = text(value, label);
  if (!TIMESTAMP.test(result) || !validCalendarValue(result.slice(0, 10)) || !Number.isFinite(Date.parse(result))) invalid(label);
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function calendarDate(value: unknown, label: string): string {
  const result = text(value, label);
  if (!validCalendarValue(result)) invalid(label);
  return result;
}

function nullableDate(value: unknown, label: string): string | null {
  return value == null ? null : calendarDate(value, label);
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') invalid(label);
  return value as boolean;
}

function integer(value: unknown, label: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(value) || Number(value) < minimum || Number(value) > maximum) invalid(label);
  return Number(value);
}

function nullableInteger(value: unknown, label: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number | null {
  return value == null ? null : integer(value, label, minimum, maximum);
}

function oneOf<const T extends readonly string[]>(value: unknown, values: T, label: string): T[number] {
  if (typeof value !== 'string' || !values.includes(value)) invalid(label);
  return value as T[number];
}

function array<T>(value: unknown, label: string, parser: (item: unknown, index: number) => T): T[] {
  if (!Array.isArray(value)) invalid(label);
  return value.map(parser);
}

function uniqueIds(value: unknown, label: string): string[] {
  const result = array(value, label, (item) => id(item, `${label} id`));
  if (new Set(result).size !== result.length) invalid(`duplicate ${label}`);
  return result;
}

function uniqueEnums<const T extends readonly string[]>(value: unknown, values: T, label: string): T[number][] {
  const result = array(value, label, (item) => oneOf(item, values, label));
  if (new Set(result).size !== result.length) invalid(`duplicate ${label}`);
  return result;
}

function assertUnique(values: readonly string[], label: string): void {
  if (new Set(values).size !== values.length) invalid(`duplicate ${label}`);
}

function assertDescending(values: readonly number[], label: string): void {
  if (values.some((value, index) => index > 0 && value >= values[index - 1]!)) invalid(`${label} order`);
}

const CAPABILITY_KEYS = ['id', 'version_number', 'status', 'willing_to_drive', 'licence_jurisdiction', 'licence_class', 'vehicle_access', 'preferred_service_radius_km', 'effective_at'] as const;
function parseCapability(value: unknown): DriverCapabilityVersion {
  const row = exactObject(value, CAPABILITY_KEYS, 'driver capability');
  return {
    id: id(row.id, 'driver capability id'),
    version_number: integer(row.version_number, 'driver capability version', 1),
    status: oneOf(row.status, ['declared', 'withdrawn'] as const, 'driver capability status'),
    willing_to_drive: boolean(row.willing_to_drive, 'driver willingness'),
    licence_jurisdiction: nullableText(row.licence_jurisdiction, 'licence jurisdiction', 20),
    licence_class: nullableText(row.licence_class, 'licence class', 30),
    vehicle_access: oneOf(row.vehicle_access, ['none', 'organization_vehicle_only', 'personal_vehicle', 'either'] as const, 'vehicle access'),
    preferred_service_radius_km: nullableInteger(row.preferred_service_radius_km, 'service radius', 0, 1000),
    effective_at: timestamp(row.effective_at, 'driver capability time'),
  };
}

function expectedQualificationContentPath(membershipId: string, qualificationId: string): string {
  return `/api/v1/staff/transport-registry/${membershipId}/qualification-evidence/${qualificationId}/content`;
}

const QUALIFICATION_KEYS = ['id', 'qualification_type', 'version_number', 'status', 'jurisdiction', 'qualification_class', 'identifier_last4', 'issue_date', 'expiry_date', 'evidence_present', 'content_path', 'effective_at'] as const;
function parseQualification(value: unknown, membershipId: string): QualificationVersion {
  const row = exactObject(value, QUALIFICATION_KEYS, 'driver qualification');
  const qualificationId = id(row.id, 'qualification id');
  const evidencePresent = boolean(row.evidence_present, 'qualification evidence marker');
  const contentPath = nullableText(row.content_path, 'qualification content path');
  if (evidencePresent !== Boolean(contentPath)) invalid('qualification evidence linkage');
  if (contentPath !== null && contentPath !== expectedQualificationContentPath(membershipId, qualificationId)) invalid('qualification content path');
  return {
    id: qualificationId,
    qualification_type: oneOf(row.qualification_type, QUALIFICATION_TYPES, 'qualification type'),
    version_number: integer(row.version_number, 'qualification version', 1),
    status: oneOf(row.status, ['declared', 'verified', 'rejected', 'expired', 'revoked'] as const, 'qualification status'),
    jurisdiction: nullableText(row.jurisdiction, 'qualification jurisdiction', 20),
    qualification_class: nullableText(row.qualification_class, 'qualification class', 40),
    identifier_last4: nullableText(row.identifier_last4, 'qualification identifier suffix', 8),
    issue_date: nullableDate(row.issue_date, 'qualification issue date'),
    expiry_date: nullableDate(row.expiry_date, 'qualification expiry date'),
    evidence_present: evidencePresent,
    content_path: contentPath,
    effective_at: timestamp(row.effective_at, 'qualification effective time'),
  };
}

const QUALIFICATION_REVIEW_KEYS = ['id', 'source_qualification_version_id', 'result_qualification_version_id', 'decision', 'reason_code', 'reviewed_at'] as const;
function parseQualificationReview(value: unknown): QualificationReview {
  const row = exactObject(value, QUALIFICATION_REVIEW_KEYS, 'qualification review');
  const review = {
    id: id(row.id, 'qualification review id'),
    source_qualification_version_id: id(row.source_qualification_version_id, 'source qualification id'),
    result_qualification_version_id: id(row.result_qualification_version_id, 'result qualification id'),
    decision: oneOf(row.decision, ['verified', 'rejected'] as const, 'qualification review decision'),
    reason_code: text(row.reason_code, 'qualification review reason', 80),
    reviewed_at: timestamp(row.reviewed_at, 'qualification review time'),
  };
  if (review.source_qualification_version_id === review.result_qualification_version_id) invalid('qualification review version identity');
  return review;
}

const AUTHORIZATION_KEYS = ['id', 'decision_sequence', 'capability_version_id', 'qualification_version_ids', 'decision', 'reason_code', 'authorization_valid_from', 'authorization_valid_until', 'reviewed_at', 'operational_driver_ready', 'dispatch_authorized'] as const;
function parseAuthorization(value: unknown): DriverAuthorization {
  const row = exactObject(value, AUTHORIZATION_KEYS, 'driver authorization');
  if (row.operational_driver_ready !== false || row.dispatch_authorized !== false) invalid('driver authorization authority boundary');
  const decision = oneOf(row.decision, ['needs_review', 'authorized', 'denied', 'revoked'] as const, 'authorization decision');
  const validFrom = nullableTimestamp(row.authorization_valid_from, 'authorization start');
  const validUntil = nullableTimestamp(row.authorization_valid_until, 'authorization end');
  const qualificationVersionIds = uniqueIds(row.qualification_version_ids, 'authorization qualifications');
  if (qualificationVersionIds.length < 1 || qualificationVersionIds.length > 20) invalid('authorization qualification count');
  if ((decision === 'authorized') !== Boolean(validFrom && validUntil)) invalid('authorization validity window');
  if (validFrom && validUntil && Date.parse(validUntil) <= Date.parse(validFrom)) invalid('authorization validity order');
  return {
    id: id(row.id, 'authorization id'),
    decision_sequence: integer(row.decision_sequence, 'authorization sequence', 1),
    capability_version_id: id(row.capability_version_id, 'authorization capability id'),
    qualification_version_ids: qualificationVersionIds,
    decision,
    reason_code: text(row.reason_code, 'authorization reason', 80),
    authorization_valid_from: validFrom,
    authorization_valid_until: validUntil,
    reviewed_at: timestamp(row.reviewed_at, 'authorization review time'),
    operational_driver_ready: false,
    dispatch_authorized: false,
  };
}

const READINESS_KEYS = ['id', 'decision_sequence', 'decision', 'reason_codes', 'vehicle_id', 'evaluated_at', 'operational_driver_ready', 'dispatch_authorized'] as const;
function parseReadiness(value: unknown): DriverReadiness {
  const row = exactObject(value, READINESS_KEYS, 'driver readiness');
  if (row.operational_driver_ready !== false || row.dispatch_authorized !== false) invalid('driver readiness authority boundary');
  const reasons = array(row.reason_codes, 'readiness reasons', (item) => text(item, 'readiness reason', 120));
  if (reasons.length > 40) invalid('readiness reason count');
  if (new Set(reasons).size !== reasons.length) invalid('duplicate readiness reason');
  return {
    id: id(row.id, 'readiness id'),
    decision_sequence: integer(row.decision_sequence, 'readiness sequence', 1),
    decision: oneOf(row.decision, ['incomplete', 'needs_review', 'blocked'] as const, 'readiness decision'),
    reason_codes: reasons,
    vehicle_id: row.vehicle_id == null ? null : id(row.vehicle_id, 'readiness vehicle id'),
    evaluated_at: timestamp(row.evaluated_at, 'readiness evaluation time'),
    operational_driver_ready: false,
    dispatch_authorized: false,
  };
}

const STAFF_KEYS = ['membership_id', 'first_name', 'last_name', 'capabilities', 'qualifications', 'qualification_reviews', 'authorizations', 'readiness', 'capabilities_truncated', 'qualification_types_truncated', 'qualification_reviews_truncated', 'authorizations_truncated', 'readiness_truncated'] as const;
function parseStaff(value: unknown): TransportStaffRecord {
  const row = exactObject(value, STAFF_KEYS, 'transport staff record');
  const membershipId = id(row.membership_id, 'transport membership id');
  const capabilitiesTruncated = boolean(row.capabilities_truncated, 'capability truncation marker');
  const qualificationTypesTruncated = uniqueEnums(row.qualification_types_truncated, QUALIFICATION_TYPES, 'qualification truncation types');
  const capabilities = array(row.capabilities, 'driver capabilities', parseCapability);
  const qualifications = array(row.qualifications, 'driver qualifications', (item) => parseQualification(item, membershipId));
  const qualificationReviews = array(row.qualification_reviews, 'qualification reviews', parseQualificationReview);
  const authorizations = array(row.authorizations, 'driver authorizations', parseAuthorization);
  const readiness = array(row.readiness, 'driver readiness history', parseReadiness);
  if ([capabilities, qualifications, qualificationReviews, authorizations, readiness].some((items) => items.length > 20)) invalid('transport history limit');
  assertUnique(capabilities.map((item) => item.id), 'capability id');
  assertUnique(qualifications.map((item) => item.id), 'qualification id');
  assertUnique(qualificationReviews.map((item) => item.id), 'qualification review id');
  assertUnique(authorizations.map((item) => item.id), 'authorization id');
  assertUnique(readiness.map((item) => item.id), 'readiness id');
  assertDescending(capabilities.map((item) => item.version_number), 'capability history');
  assertDescending(authorizations.map((item) => item.decision_sequence), 'authorization history');
  assertDescending(readiness.map((item) => item.decision_sequence), 'readiness history');
  for (const type of QUALIFICATION_TYPES) assertDescending(qualifications.filter((item) => item.qualification_type === type).map((item) => item.version_number), `${type} qualification history`);
  const qualificationIds = new Set(qualifications.map((item) => item.id));
  const capabilityIds = new Set(capabilities.map((item) => item.id));
  if (!qualificationTypesTruncated.length && qualificationReviews.some((item) => {
    const source = qualifications.find((version) => version.id === item.source_qualification_version_id);
    const result = qualifications.find((version) => version.id === item.result_qualification_version_id);
    return !source
      || !result
      || source.qualification_type !== result.qualification_type
      || result.status !== item.decision;
  })) invalid('qualification review linkage');
  if (authorizations.some((item) => (
    (!capabilityIds.has(item.capability_version_id) && !capabilitiesTruncated)
    || (!qualificationTypesTruncated.length && item.qualification_version_ids.some((itemId) => !qualificationIds.has(itemId)))
  ))) invalid('authorization linkage');
  return {
    membership_id: membershipId,
    first_name: text(row.first_name, 'staff first name', 200),
    last_name: text(row.last_name, 'staff last name', 200),
    capabilities,
    qualifications,
    qualification_reviews: qualificationReviews,
    authorizations,
    readiness,
    capabilities_truncated: capabilitiesTruncated,
    qualification_types_truncated: qualificationTypesTruncated,
    qualification_reviews_truncated: boolean(row.qualification_reviews_truncated, 'qualification review truncation marker'),
    authorizations_truncated: boolean(row.authorizations_truncated, 'authorization truncation marker'),
    readiness_truncated: boolean(row.readiness_truncated, 'readiness truncation marker'),
  };
}

const VEHICLE_VERSION_KEYS = ['id', 'version_number', 'make', 'model', 'model_year', 'color', 'plate_token', 'plate_jurisdiction', 'passenger_capacity', 'child_passenger_capacity', 'wheelchair_accessible', 'effective_at'] as const;
function parseVehicleVersion(value: unknown): VehicleVersion {
  const row = exactObject(value, VEHICLE_VERSION_KEYS, 'vehicle version');
  const passengerCapacity = integer(row.passenger_capacity, 'passenger capacity', 1, 30);
  const childCapacity = integer(row.child_passenger_capacity, 'child passenger capacity', 0, 29);
  if (childCapacity >= passengerCapacity) invalid('vehicle capacity relationship');
  return {
    id: id(row.id, 'vehicle version id'),
    version_number: integer(row.version_number, 'vehicle version number', 1),
    make: text(row.make, 'vehicle make', 80),
    model: text(row.model, 'vehicle model', 80),
    model_year: integer(row.model_year, 'vehicle model year', 1900, 2100),
    color: nullableText(row.color, 'vehicle color', 40),
    plate_token: text(row.plate_token, 'vehicle plate', 24),
    plate_jurisdiction: text(row.plate_jurisdiction, 'vehicle plate jurisdiction', 20),
    passenger_capacity: passengerCapacity,
    child_passenger_capacity: childCapacity,
    wheelchair_accessible: boolean(row.wheelchair_accessible, 'wheelchair accessibility'),
    effective_at: timestamp(row.effective_at, 'vehicle version time'),
  };
}

function expectedVehicleContentPath(vehicleId: string, evidenceId: string): string {
  return `/api/v1/staff/transport-registry/vehicles/${vehicleId}/evidence/${evidenceId}/content`;
}

const VEHICLE_EVIDENCE_KEYS = ['id', 'vehicle_version_id', 'evidence_type', 'version_number', 'status', 'issue_date', 'expiry_date', 'original_filename', 'media_type', 'byte_size', 'content_path', 'recorded_at'] as const;
function parseVehicleEvidence(value: unknown, vehicleId: string): VehicleEvidence {
  const row = exactObject(value, VEHICLE_EVIDENCE_KEYS, 'vehicle evidence');
  const evidenceId = id(row.id, 'vehicle evidence id');
  const contentPath = text(row.content_path, 'vehicle evidence content path');
  if (contentPath !== expectedVehicleContentPath(vehicleId, evidenceId)) invalid('vehicle evidence content path');
  return {
    id: evidenceId,
    vehicle_version_id: id(row.vehicle_version_id, 'evidence vehicle version id'),
    evidence_type: oneOf(row.evidence_type, VEHICLE_EVIDENCE_TYPES, 'vehicle evidence type'),
    version_number: integer(row.version_number, 'vehicle evidence version', 1),
    status: oneOf(row.status, ['provided', 'verified', 'rejected', 'expired', 'revoked'] as const, 'vehicle evidence status'),
    issue_date: nullableDate(row.issue_date, 'vehicle evidence issue date'),
    expiry_date: nullableDate(row.expiry_date, 'vehicle evidence expiry date'),
    original_filename: nullableText(row.original_filename, 'vehicle evidence filename', 255),
    media_type: oneOf(row.media_type, ['application/pdf', 'image/png', 'image/jpeg'] as const, 'vehicle evidence media type'),
    byte_size: integer(row.byte_size, 'vehicle evidence byte size', 1, MAX_TRANSPORT_EVIDENCE_BYTES),
    content_path: contentPath,
    recorded_at: timestamp(row.recorded_at, 'vehicle evidence time'),
  };
}

const VEHICLE_REVIEW_KEYS = ['id', 'source_evidence_version_id', 'result_evidence_version_id', 'decision', 'reason_code', 'reviewed_at'] as const;
function parseVehicleReview(value: unknown): VehicleEvidenceReview {
  const row = exactObject(value, VEHICLE_REVIEW_KEYS, 'vehicle evidence review');
  const review = {
    id: id(row.id, 'vehicle evidence review id'),
    source_evidence_version_id: id(row.source_evidence_version_id, 'source vehicle evidence id'),
    result_evidence_version_id: id(row.result_evidence_version_id, 'result vehicle evidence id'),
    decision: oneOf(row.decision, ['verified', 'rejected'] as const, 'vehicle review decision'),
    reason_code: text(row.reason_code, 'vehicle review reason', 80),
    reviewed_at: timestamp(row.reviewed_at, 'vehicle review time'),
  };
  if (review.source_evidence_version_id === review.result_evidence_version_id) invalid('vehicle review version identity');
  return review;
}

const VEHICLE_KEYS = ['id', 'owner_kind', 'staff_owner_membership_id', 'retired_at', 'versions', 'evidence', 'evidence_reviews', 'versions_truncated', 'evidence_types_truncated', 'evidence_reviews_truncated'] as const;
function parseVehicle(value: unknown): TransportVehicleRecord {
  const row = exactObject(value, VEHICLE_KEYS, 'transport vehicle');
  const vehicleId = id(row.id, 'vehicle id');
  const ownerKind = oneOf(row.owner_kind, ['organization', 'staff_personal'] as const, 'vehicle owner kind');
  const ownerId = row.staff_owner_membership_id == null ? null : id(row.staff_owner_membership_id, 'vehicle staff owner id');
  if ((ownerKind === 'organization') !== (ownerId === null)) invalid('vehicle ownership linkage');
  const versionsTruncated = boolean(row.versions_truncated, 'vehicle version truncation marker');
  const evidenceTypesTruncated = uniqueEnums(row.evidence_types_truncated, VEHICLE_EVIDENCE_TYPES, 'vehicle evidence truncation types');
  const versions = array(row.versions, 'vehicle versions', parseVehicleVersion);
  const evidence = array(row.evidence, 'vehicle evidence', (item) => parseVehicleEvidence(item, vehicleId));
  const reviews = array(row.evidence_reviews, 'vehicle evidence reviews', parseVehicleReview);
  if (versions.length > 20 || evidence.length > 80 || reviews.length > 20) invalid('vehicle history limit');
  assertUnique(versions.map((item) => item.id), 'vehicle version id');
  assertUnique(evidence.map((item) => item.id), 'vehicle evidence id');
  assertUnique(reviews.map((item) => item.id), 'vehicle review id');
  assertDescending(versions.map((item) => item.version_number), 'vehicle version history');
  for (const type of VEHICLE_EVIDENCE_TYPES) assertDescending(evidence.filter((item) => item.evidence_type === type).map((item) => item.version_number), `${type} evidence history`);
  const versionIds = new Set(versions.map((item) => item.id));
  const evidenceIds = new Set(evidence.map((item) => item.id));
  if (!versionsTruncated && evidence.some((item) => !versionIds.has(item.vehicle_version_id))) invalid('vehicle evidence linkage');
  if (!evidenceTypesTruncated.length && reviews.some((item) => {
    const source = evidence.find((version) => version.id === item.source_evidence_version_id);
    const result = evidence.find((version) => version.id === item.result_evidence_version_id);
    return !source
      || !result
      || source.evidence_type !== result.evidence_type
      || result.status !== item.decision;
  })) invalid('vehicle review linkage');
  return {
    id: vehicleId,
    owner_kind: ownerKind,
    staff_owner_membership_id: ownerId,
    retired_at: nullableTimestamp(row.retired_at, 'vehicle retirement time'),
    versions,
    evidence,
    evidence_reviews: reviews,
    versions_truncated: versionsTruncated,
    evidence_types_truncated: evidenceTypesTruncated,
    evidence_reviews_truncated: boolean(row.evidence_reviews_truncated, 'vehicle review truncation marker'),
  };
}

const WORKSPACE_KEYS = ['schema_version', 'generated_at', 'staff', 'vehicles', 'staff_truncated', 'vehicles_truncated', 'operational_driver_ready', 'dispatch_authorized'] as const;
export function parseTransportRegistryWorkspace(value: unknown): TransportRegistryWorkspace {
  const row = exactObject(value, WORKSPACE_KEYS, 'transport registry workspace');
  if (row.schema_version !== '0032' || row.operational_driver_ready !== false || row.dispatch_authorized !== false) invalid('transport registry safety boundary');
  const staff = array(row.staff, 'transport staff', parseStaff);
  const vehicles = array(row.vehicles, 'transport vehicles', parseVehicle);
  const staffTruncated = boolean(row.staff_truncated, 'staff truncation marker');
  const vehiclesTruncated = boolean(row.vehicles_truncated, 'vehicle truncation marker');
  if (staff.length > 200 || vehicles.length > 100) invalid('transport workspace result limit');
  assertUnique(staff.map((item) => item.membership_id), 'transport membership id');
  assertUnique(vehicles.map((item) => item.id), 'transport vehicle id');
  const vehicleIds = new Set(vehicles.map((item) => item.id));
  if (!vehiclesTruncated && staff.some((item) => item.readiness.some((decision) => decision.vehicle_id && !vehicleIds.has(decision.vehicle_id)))) invalid('readiness vehicle linkage');
  return {
    schema_version: '0032',
    generated_at: timestamp(row.generated_at, 'workspace generation time'),
    staff,
    vehicles,
    staff_truncated: staffTruncated,
    vehicles_truncated: vehiclesTruncated,
    operational_driver_ready: false,
    dispatch_authorized: false,
  };
}

const RECEIPT_KEYS = ['schema_version', 'client_operation_id', 'command_kind', 'result_kind', 'result_id', 'committed_at', 'exact_retry', 'operational_driver_ready', 'dispatch_authorized'] as const;
const RESULT_KIND_BY_COMMAND: Readonly<Record<TransportCommandKind, TransportCommandReceipt['result_kind']>> = {
  driver_declaration: 'driver_capability',
  qualification_evidence: 'driver_qualification',
  qualification_review: 'driver_qualification',
  driver_authorization: 'driver_authorization',
  vehicle_create: 'vehicle',
  vehicle_version: 'vehicle_version',
  vehicle_retire: 'vehicle',
  vehicle_evidence: 'vehicle_evidence',
  vehicle_evidence_review: 'vehicle_evidence',
  readiness_evaluation: 'driver_readiness',
};
export function parseTransportCommandReceipt(value: unknown, expectedOperationId?: string, expectedKind?: TransportCommandKind): TransportCommandReceipt {
  const row = exactObject(value, RECEIPT_KEYS, 'transport command receipt');
  if (row.schema_version !== '0032' || row.operational_driver_ready !== false || row.dispatch_authorized !== false) invalid('transport command receipt boundary');
  const receipt: TransportCommandReceipt = {
    schema_version: '0032',
    client_operation_id: id(row.client_operation_id, 'receipt operation id'),
    command_kind: oneOf(row.command_kind, ['driver_declaration', 'qualification_evidence', 'qualification_review', 'driver_authorization', 'vehicle_create', 'vehicle_version', 'vehicle_retire', 'vehicle_evidence', 'vehicle_evidence_review', 'readiness_evaluation'] as const, 'transport command kind'),
    result_kind: oneOf(row.result_kind, ['driver_capability', 'driver_qualification', 'driver_authorization', 'vehicle', 'vehicle_version', 'vehicle_evidence', 'driver_readiness'] as const, 'transport result kind'),
    result_id: id(row.result_id, 'transport result id'),
    committed_at: timestamp(row.committed_at, 'transport commit time'),
    exact_retry: boolean(row.exact_retry, 'exact retry marker'),
    operational_driver_ready: false,
    dispatch_authorized: false,
  };
  if (receipt.result_kind !== RESULT_KIND_BY_COMMAND[receipt.command_kind]) invalid('receipt result binding');
  if (expectedOperationId && receipt.client_operation_id !== expectedOperationId.toLowerCase()) invalid('receipt operation binding');
  if (expectedKind && receipt.command_kind !== expectedKind) invalid('receipt command binding');
  return receipt;
}

async function command<Body extends object>(path: string, operationId: string, kind: TransportCommandKind, body: Body): Promise<TransportCommandReceipt> {
  return parseTransportCommandReceipt(await apiRequest<unknown>(path, { method: 'POST', body: JSON.stringify({ operation_id: operationId, ...body }) }), operationId, kind);
}

async function upload(path: string, operationId: string, kind: TransportCommandKind, fields: Record<string, string | null>, file: File): Promise<TransportCommandReceipt> {
  const body = new FormData();
  body.set('operation_id', operationId);
  Object.entries(fields).forEach(([key, value]) => { if (value != null && value !== '') body.set(key, value); });
  body.set('file', file, file.name);
  return parseTransportCommandReceipt(await apiRequest<unknown>(path, { method: 'POST', body }), operationId, kind);
}

export interface PrivateEvidenceContent {
  blob: Blob;
  mediaType: VehicleEvidence['media_type'];
}

export function isSafeManagerEvidencePath(path: string): boolean {
  const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
  return new RegExp(`^/api/v1/staff/transport-registry/(?:${uuid}/qualification-evidence/${uuid}|vehicles/${uuid}/evidence/${uuid})/content$`, 'i').test(path)
    && !path.includes('?')
    && !path.includes('#')
    && !path.includes('..');
}

export async function fetchPrivateEvidence(path: string, organizationId: string, signal?: AbortSignal): Promise<PrivateEvidenceContent> {
  if (!isSafeManagerEvidencePath(path)) throw new TransportRegistryApiError('The evidence destination is outside the private manager boundary.');
  if (!UUID.test(organizationId)) throw new TransportRegistryApiError('The private evidence organization is invalid.');
  const api = new URL(API_URL);
  const url = new URL(path, api.origin);
  if (url.origin !== api.origin || url.pathname !== path || url.search || url.hash) throw new TransportRegistryApiError('The evidence destination crossed the API boundary.');
  const headers = new Headers({ Accept: 'application/pdf,image/png,image/jpeg' });
  const token = getSessionToken();
  if (!token) throw new TransportRegistryApiError('The signed-in session is unavailable.');
  headers.set('Authorization', `Bearer ${token}`);
  addOrganizationHeader(headers, organizationId);
  const response = await fetch(url, { headers, signal, credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(response.status, payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string' ? payload.detail : `Evidence request failed (${response.status})`, payload);
  }
  const mediaType = response.headers.get('content-type')?.split(';')[0]?.trim();
  if (!['application/pdf', 'image/png', 'image/jpeg'].includes(mediaType || '')) throw new TransportRegistryApiError('The server returned an unsupported private evidence type.');
  const blob = await response.blob();
  if (blob.size <= 0 || blob.size > MAX_TRANSPORT_EVIDENCE_BYTES || blob.type.split(';')[0] !== mediaType) throw new TransportRegistryApiError('The server returned invalid private evidence content.');
  return { blob, mediaType: mediaType as PrivateEvidenceContent['mediaType'] };
}

export const transportRegistryApi = {
  workspace: async (signal?: AbortSignal): Promise<TransportRegistryWorkspace> =>
    parseTransportRegistryWorkspace(await apiRequest<unknown>(TRANSPORT_REGISTRY_PATH, { signal })),
  declareSelf: (operationId: string, payload: DriverDeclarationInput) =>
    command('/staff/self/transport-registry/declarations', operationId, 'driver_declaration', payload),
  uploadSelfQualification: (operationId: string, payload: QualificationEvidenceInput) =>
    upload('/staff/self/transport-registry/qualification-evidence', operationId, 'qualification_evidence', {
      qualification_type: payload.qualification_type,
      jurisdiction: payload.jurisdiction,
      qualification_class: payload.qualification_class,
      identifier_last4: payload.identifier_last4,
      issue_date: payload.issue_date,
      expiry_date: payload.expiry_date,
    }, payload.file),
  reviewQualification: (membershipId: string, operationId: string, payload: { source_qualification_version_id: string; decision: ReviewDecision; reason_code: string }) =>
    command(`${TRANSPORT_REGISTRY_PATH}/${encodeURIComponent(membershipId)}/qualification-reviews`, operationId, 'qualification_review', payload),
  authorize: (membershipId: string, operationId: string, payload: { capability_version_id: string; qualification_version_ids: string[]; decision: AuthorizationDecision; reason_code: string; authorization_valid_from: string | null; authorization_valid_until: string | null }) =>
    command(`${TRANSPORT_REGISTRY_PATH}/${encodeURIComponent(membershipId)}/authorizations`, operationId, 'driver_authorization', payload),
  evaluateReadiness: (membershipId: string, operationId: string, vehicleId: string | null) =>
    command(`${TRANSPORT_REGISTRY_PATH}/${encodeURIComponent(membershipId)}/readiness-evaluations`, operationId, 'readiness_evaluation', { vehicle_id: vehicleId }),
  createOrganizationVehicle: (operationId: string, payload: VehicleFactsInput) =>
    command(`${TRANSPORT_REGISTRY_PATH}/vehicles`, operationId, 'vehicle_create', payload),
  versionVehicle: (vehicleId: string, operationId: string, payload: VehicleFactsInput) =>
    command(`${TRANSPORT_REGISTRY_PATH}/vehicles/${encodeURIComponent(vehicleId)}/versions`, operationId, 'vehicle_version', payload),
  retireVehicle: (vehicleId: string, operationId: string, reasonCode: string) =>
    command(`${TRANSPORT_REGISTRY_PATH}/vehicles/${encodeURIComponent(vehicleId)}/retire`, operationId, 'vehicle_retire', { reason_code: reasonCode }),
  uploadVehicleEvidence: (vehicleId: string, operationId: string, payload: VehicleEvidenceInput) =>
    upload(`${TRANSPORT_REGISTRY_PATH}/vehicles/${encodeURIComponent(vehicleId)}/evidence`, operationId, 'vehicle_evidence', {
      evidence_type: payload.evidence_type,
      issue_date: payload.issue_date,
      expiry_date: payload.expiry_date,
    }, payload.file),
  reviewVehicleEvidence: (vehicleId: string, operationId: string, payload: { source_evidence_version_id: string; decision: ReviewDecision; reason_code: string }) =>
    command(`${TRANSPORT_REGISTRY_PATH}/vehicles/${encodeURIComponent(vehicleId)}/evidence-reviews`, operationId, 'vehicle_evidence_review', payload),
};
