import { addOrganizationHeader, notifyAuthorizationDenied } from '../../api/client';
import {
  CommandOutcomeUnknownError,
  createExactChildcareCommand,
  exactChildcareCommandBody,
  type ExactChildcareCommand,
} from '../../api/childcareCommand';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');
const TOKEN_KEY = 'caresync-redesign-token';
const FAMILY_OPTION_PAGE_SIZE = 200;
export const CHILD_DIRECTORY_PAGE_SIZE = 50;

type ChildrenApiErrorOrigin = 'http' | 'response' | 'preflight';

export interface ApiChildRecord {
  id: string;
  organization_id: string;
  family_id: string;
  family_name: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  date_of_birth: string;
  start_date: string | null;
  gender: string | null;
  age_group: string | null;
  is_active: boolean;
  profile_photo_url: string | null;
  profile_photo_updated_at: string | null;
  enrollments: ApiChildEnrollment[];
  created_at: string;
  updated_at: string;
  version: number;
  replayed: boolean;
}

export type ChildDirectoryCareLane = 'daycare' | 'out_of_school_care' | 'unassigned' | 'needs_review';
export type ChildDirectoryPlacementState = 'current' | 'reserved' | 'unassigned' | 'needs_review';
export type ChildDirectoryStatusFilter = 'all' | 'active' | 'inactive';
export type ChildDirectoryCareLaneFilter = 'all' | ChildDirectoryCareLane;

export interface ApiChildDirectoryEnrollment {
  id: string;
  organization_id: string;
  child_id: string;
  facility_id: string;
  facility_name: string;
  program_id: string | null;
  program_name: string | null;
  program_type: 'daycare' | 'out_of_school_care' | null;
  room_id: string | null;
  room_name: string | null;
  placement_effective_date: string | null;
  start_date: string;
  end_date: string | null;
  status: Exclude<EnrollmentStatus, 'ended'>;
  version: number;
  placement_state: ChildDirectoryPlacementState;
}

export interface ApiChildDirectoryRecord {
  id: string;
  organization_id: string;
  family_id: string;
  family_name: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  date_of_birth: string;
  age_group: string | null;
  is_active: boolean;
  version: number;
  profile_photo_url: string | null;
  profile_photo_updated_at: string | null;
  created_at: string;
  updated_at: string;
  care_lane: ChildDirectoryCareLane;
  open_enrollment: ApiChildDirectoryEnrollment | null;
}

export interface ChildDirectoryCounts {
  total: number;
  active: number;
  inactive: number;
  daycare: number;
  out_of_school_care: number;
  unassigned: number;
  reserved: number;
  needs_review: number;
}

export interface ChildDirectoryPage {
  items: ApiChildDirectoryRecord[];
  total: number;
  limit: number;
  offset: number;
  counts: ChildDirectoryCounts;
}

export interface ChildDirectoryQuery {
  search: string;
  status: ChildDirectoryStatusFilter;
  careLane: ChildDirectoryCareLaneFilter;
  familyId: string | null;
  limit: number;
  offset: number;
}

export interface ApiChildEnrollment {
  id: string;
  organization_id: string;
  child_id: string;
  facility_id: string;
  program_id: string | null;
  room_id: string | null;
  start_date: string;
  end_date: string | null;
  status: EnrollmentStatus;
  is_active: boolean;
  placement_effective_date: string | null;
  version: number;
  replayed: boolean;
}

export type EnrollmentStatus = 'pending' | 'active' | 'paused' | 'ended';

export interface EnrollmentFacilityOption {
  id: string;
  organization_id: string;
  name: string;
  status: string;
  timezone: string;
}

export interface EnrollmentProgramOption {
  id: string;
  organization_id: string;
  facility_id: string;
  name: string;
  program_type: string | null;
  is_active: boolean;
}

export interface EnrollmentRoomOption {
  id: string;
  organization_id: string;
  facility_id: string;
  program_id: string | null;
  name: string;
  age_group: string | null;
  capacity: number;
  occupancy: number;
  is_active: boolean;
}

export interface EnrollmentPlacementOptions {
  programs: EnrollmentProgramOption[];
  rooms: EnrollmentRoomOption[];
}

export interface EnrollmentCreateInput {
  facility_id: string;
  start_date: string;
}

export interface EnrollmentPlacementApprovalInput {
  room_id: string;
  effective_date: string;
}

export interface ApiChildDetails extends Omit<ApiChildRecord, 'family_name'> {
  health_care_number: string | null;
  allergies: string | null;
  medical_conditions: string | null;
  medications: string | null;
  immunization_up_to_date: boolean | null;
  doctor_name: string | null;
  doctor_phone: string | null;
}

export interface ChildProfileGuardian {
  id: string;
  family_id: string;
  first_name: string;
  last_name: string;
  relationship: string | null;
  guardian_type: string;
  email: string;
  cell_phone: string;
  home_phone: string | null;
  work_phone: string | null;
  address: string | null;
  city: string | null;
  postal_code: string | null;
  authorized_pickup: boolean;
}

export interface ChildProfileEmergencyContact {
  id: string;
  family_id: string;
  first_name: string;
  last_name: string;
  relationship: string;
  cell_phone: string;
  home_phone: string | null;
  authorized_pickup: boolean;
}

export interface ChildProfileFamily {
  id: string;
  organization_id: string;
  name: string;
  file_number: string | null;
  status: string;
  additional_notes: string | null;
  photo_consent: boolean;
  field_trip_consent: boolean;
  emergency_medical_consent: boolean;
  guardians: ChildProfileGuardian[];
  emergency_contacts: ChildProfileEmergencyContact[];
  version: number;
  replayed: false;
}

export interface ChildProfileEnrollment extends ApiChildEnrollment {
  facility_name: string;
  program_name: string | null;
  program_type: string | null;
  room_name: string | null;
}

export interface ApiChildProfile extends Omit<ApiChildDetails, 'enrollments'> {
  family: ChildProfileFamily;
  current_enrollment: ChildProfileEnrollment | null;
  enrollments: ChildProfileEnrollment[];
}

export interface ChildPhotoMetadata {
  child_id: string;
  url: string;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  sha256: string;
  original_filename: string | null;
  updated_at: string;
}

export interface ChildFamilyOption {
  id: string;
  organization_id: string;
  name: string;
  status: string;
}

/** Basic child fields accepted by the dedicated transactional children routes. */
export interface ChildMutationInput {
  family_id: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  date_of_birth: string;
  gender: string | null;
  age_group: string | null;
  is_active: boolean;
  health_care_number: string | null;
  allergies: string | null;
  medical_conditions: string | null;
  medications: string | null;
  immunization_up_to_date: boolean | null;
  doctor_name: string | null;
  doctor_phone: string | null;
}

export type ChildCreateCommand = ExactChildcareCommand<ChildMutationInput>;
export type ChildUpdateCommand = ExactChildcareCommand<ChildMutationInput>;
export type ChildActiveStateCommand = ExactChildcareCommand<{ is_active: boolean }>;
export type EnrollmentCreateCommand = ExactChildcareCommand<EnrollmentCreateInput>;
export type EnrollmentPlacementApprovalCommand = ExactChildcareCommand<EnrollmentPlacementApprovalInput>;
export type EnrollmentLifecycleCommand = ExactChildcareCommand<{ status: EnrollmentStatus; end_date?: string | null }>;

export class ChildrenApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: unknown,
    public readonly origin: ChildrenApiErrorOrigin = 'response',
  ) {
    super(message);
    this.name = 'ChildrenApiError';
  }
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const structured = detail as { code?: unknown; resource_type?: unknown; current_version?: unknown };
      if (structured.code === 'stale_childcare_resource') {
        const target = typeof structured.resource_type === 'string' ? structured.resource_type.replaceAll('_', ' ') : 'record';
        return `This ${target} changed in another action${Number.isInteger(structured.current_version) ? ` (current version ${structured.current_version})` : ''}. Reload before making a new change.`;
      }
      if (structured.code === 'operation_reused') return 'This operation identifier was already used for a different child-record change.';
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (!item || typeof item !== 'object') return String(item);
          const typed = item as { loc?: Array<string | number>; msg?: string };
          const location = typed.loc?.slice(1).join('.') || 'request';
          return `${location}: ${typed.msg || 'invalid value'}`;
        })
        .join('; ');
    }
  }
  if (status === 401) return 'The secure session expired. Reconnect and try again.';
  if (status === 403) return 'This identity cannot access that organization record.';
  if (status === 409) return 'The change conflicts with the current database state.';
  return `The children request failed (${status}).`;
}

function requiredString(value: unknown, field: string, context: string): string {
  if (typeof value === 'string' && value.trim()) return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function requiredBoolean(value: unknown, field: string, context: string): boolean {
  if (typeof value === 'boolean') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
}

function requiredInteger(value: unknown, field: string, context: string, minimum = 0): number {
  if (Number.isInteger(value) && Number(value) >= minimum) return Number(value);
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

function requiredUuid(value: unknown, field: string, context: string): string {
  const parsed = requiredString(value, field, context);
  if (!UUID_PATTERN.test(parsed)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
  }
  return parsed;
}

function nullableUuid(value: unknown, field: string, context: string): string | null {
  if (value === null) return null;
  return requiredUuid(value, field, context);
}

function nullableNonemptyString(value: unknown, field: string, context: string): string | null {
  if (value === null) return null;
  return requiredString(value, field, context);
}

function requiredIsoDate(value: unknown, field: string, context: string): string {
  const parsed = requiredString(value, field, context);
  const match = ISO_DATE_PATTERN.exec(parsed);
  if (!match) throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
  }
  return parsed;
}

function nullableIsoDate(value: unknown, field: string, context: string): string | null {
  if (value === null) return null;
  return requiredIsoDate(value, field, context);
}

function requiredIsoTimestamp(value: unknown, field: string, context: string): string {
  const parsed = requiredString(value, field, context);
  const timestamp = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
  const match = timestamp.exec(parsed);
  if (!match || !Number.isFinite(Date.parse(parsed))) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context} (${field}).`);
  }
  requiredIsoDate(match[1], field, context);
  return parsed;
}

function nullableIsoTimestamp(value: unknown, field: string, context: string): string | null {
  if (value === null) return null;
  return requiredIsoTimestamp(value, field, context);
}

function directoryCareLane(value: unknown, context: string): ChildDirectoryCareLane {
  if (value === 'daycare' || value === 'out_of_school_care' || value === 'unassigned' || value === 'needs_review') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (care_lane).`);
}

function directoryPlacementState(value: unknown, context: string): ChildDirectoryPlacementState {
  if (value === 'current' || value === 'reserved' || value === 'unassigned' || value === 'needs_review') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (placement_state).`);
}

function directoryProgramType(value: unknown, context: string): 'daycare' | 'out_of_school_care' | null {
  if (value === null || value === 'daycare' || value === 'out_of_school_care') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (program_type).`);
}

function openEnrollmentStatus(value: unknown, context: string): Exclude<EnrollmentStatus, 'ended'> {
  if (value === 'pending' || value === 'active' || value === 'paused') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (status).`);
}

function enrollmentStatus(value: unknown, context: string): EnrollmentStatus {
  if (value === 'pending' || value === 'active' || value === 'paused' || value === 'ended') return value;
  throw new ChildrenApiError(0, `The server returned an invalid ${context} (status).`);
}

function parseChildCore(value: unknown, context: string): Omit<ApiChildRecord, 'family_name'> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  if (typeof row.is_active !== 'boolean') {
    throw new ChildrenApiError(0, `The server returned an invalid ${context} (is_active).`);
  }
  const id = requiredString(row.id, 'id', context);
  const organizationId = requiredString(row.organization_id, 'organization_id', context);
  if (!Array.isArray(row.enrollments)) {
    throw new ChildrenApiError(0, `The server returned an incomplete ${context} (enrollments).`);
  }
  const enrollments = row.enrollments
    .map((enrollment, index) => parseEnrollment(enrollment, `${context} enrollment ${index + 1}`));
  if (enrollments.some((enrollment) => enrollment.child_id !== id || enrollment.organization_id !== organizationId)) {
    throw new ChildrenApiError(403, `The server returned an enrollment outside the ${context} boundary.`);
  }
  if (new Set(enrollments.map((enrollment) => enrollment.id)).size !== enrollments.length) {
    throw new ChildrenApiError(0, `The server returned duplicate enrollments in the ${context}.`);
  }
  const savedStartDate = nullableString(row.start_date);
  const activeEnrollment = enrollments.find((enrollment) => enrollment.status === 'active' && enrollment.is_active)
    || enrollments.find((enrollment) => enrollment.status !== 'ended')
    || enrollments[0];

  return {
    id,
    organization_id: organizationId,
    family_id: requiredString(row.family_id, 'family_id', context),
    first_name: requiredString(row.first_name, 'first_name', context),
    middle_name: nullableString(row.middle_name),
    last_name: requiredString(row.last_name, 'last_name', context),
    date_of_birth: requiredString(row.date_of_birth, 'date_of_birth', context),
    start_date: activeEnrollment?.start_date || savedStartDate,
    gender: nullableString(row.gender),
    age_group: nullableString(row.age_group),
    is_active: row.is_active,
    profile_photo_url: nullableString(row.profile_photo_url),
    profile_photo_updated_at: nullableString(row.profile_photo_updated_at),
    enrollments,
    created_at: typeof row.created_at === 'string' ? row.created_at : '',
    updated_at: typeof row.updated_at === 'string' ? row.updated_at : '',
    version: requiredInteger(row.version, 'version', context, 1),
    replayed: requiredBoolean(row.replayed, 'replayed', context),
  };
}

function parseEnrollment(value: unknown, context: string): ApiChildEnrollment {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  return {
    id: requiredString(row.id, 'id', context),
    organization_id: requiredString(row.organization_id, 'organization_id', context),
    child_id: requiredString(row.child_id, 'child_id', context),
    facility_id: requiredString(row.facility_id, 'facility_id', context),
    program_id: nullableString(row.program_id),
    room_id: nullableString(row.room_id),
    start_date: requiredString(row.start_date, 'start_date', context),
    end_date: nullableString(row.end_date),
    status: enrollmentStatus(row.status, context),
    is_active: requiredBoolean(row.is_active, 'is_active', context),
    placement_effective_date: nullableString(row.placement_effective_date),
    version: requiredInteger(row.version, 'version', context, 1),
    replayed: requiredBoolean(row.replayed, 'replayed', context),
  };
}

function parseFacility(value: unknown, index: number): EnrollmentFacilityOption {
  const context = `facility record at row ${index + 1}`;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  return {
    id: requiredString(row.id, 'id', context),
    organization_id: requiredString(row.organization_id, 'organization_id', context),
    name: requiredString(row.name, 'name', context),
    status: requiredString(row.status, 'status', context),
    timezone: requiredString(row.timezone, 'timezone', context),
  };
}

function parseProgram(value: unknown, index: number): EnrollmentProgramOption {
  const context = `program record at row ${index + 1}`;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  return {
    id: requiredString(row.id, 'id', context),
    organization_id: requiredString(row.organization_id, 'organization_id', context),
    facility_id: requiredString(row.facility_id, 'facility_id', context),
    name: requiredString(row.name, 'name', context),
    program_type: nullableString(row.program_type),
    is_active: requiredBoolean(row.is_active, 'is_active', context),
  };
}

function parseRoom(value: unknown, index: number): EnrollmentRoomOption {
  const context = `room record at row ${index + 1}`;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  return {
    id: requiredString(row.id, 'id', context),
    organization_id: requiredString(row.organization_id, 'organization_id', context),
    facility_id: requiredString(row.facility_id, 'facility_id', context),
    program_id: nullableString(row.program_id),
    name: requiredString(row.name, 'name', context),
    age_group: nullableString(row.age_group),
    capacity: requiredInteger(row.capacity, 'capacity', context, 1),
    occupancy: 0,
    is_active: requiredBoolean(row.is_active, 'is_active', context),
  };
}

function parseRoomRosterOptions(value: unknown, facilityId: string): Map<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, 'The server returned an invalid room roster workspace.');
  }
  const workspace = value as Record<string, unknown>;
  if (requiredString(workspace.facility_id, 'facility_id', 'room roster workspace') !== facilityId) {
    throw new ChildrenApiError(403, 'The room roster crossed the selected facility boundary.');
  }
  if (!Array.isArray(workspace.rooms)) throw new ChildrenApiError(0, 'The server returned an invalid room roster directory.');
  const result = new Map<string, number>();
  workspace.rooms.forEach((value, index) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new ChildrenApiError(0, `The server returned an invalid room roster row ${index + 1}.`);
    }
    const row = value as Record<string, unknown>;
    const context = `room roster row ${index + 1}`;
    const roomId = requiredString(row.room_id, 'room_id', context);
    if (requiredString(row.facility_id, 'facility_id', context) !== facilityId) {
      throw new ChildrenApiError(403, 'A room roster row crossed the selected facility boundary.');
    }
    if (result.has(roomId)) throw new ChildrenApiError(0, 'The room roster returned a room more than once.');
    result.set(roomId, requiredInteger(row.occupancy, 'occupancy', context));
  });
  return result;
}

function parseChildDetails(value: unknown): ApiChildDetails {
  const core = parseChildCore(value, 'child detail record');
  const row = value as Record<string, unknown>;
  const immunization = row.immunization_up_to_date;
  if (immunization !== null && immunization !== undefined && typeof immunization !== 'boolean') {
    throw new ChildrenApiError(0, 'The server returned an invalid child detail record (immunization_up_to_date).');
  }
  return {
    ...core,
    health_care_number: nullableString(row.health_care_number),
    allergies: nullableString(row.allergies),
    medical_conditions: nullableString(row.medical_conditions),
    medications: nullableString(row.medications),
    immunization_up_to_date: typeof immunization === 'boolean' ? immunization : null,
    doctor_name: nullableString(row.doctor_name),
    doctor_phone: nullableString(row.doctor_phone),
  };
}

function parseProfileGuardian(value: unknown, familyId: string, index: number): ChildProfileGuardian {
  const context = `profile guardian ${index + 1}`;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  const guardianFamilyId = requiredString(row.family_id, 'family_id', context);
  if (guardianFamilyId !== familyId) throw new ChildrenApiError(403, 'A guardian crossed the child family boundary.');
  return {
    id: requiredString(row.id, 'id', context),
    family_id: guardianFamilyId,
    first_name: requiredString(row.first_name, 'first_name', context),
    last_name: requiredString(row.last_name, 'last_name', context),
    relationship: nullableString(row.relationship),
    guardian_type: requiredString(row.guardian_type, 'guardian_type', context),
    email: typeof row.email === 'string' ? row.email : '',
    cell_phone: typeof row.cell_phone === 'string' ? row.cell_phone : '',
    home_phone: nullableString(row.home_phone),
    work_phone: nullableString(row.work_phone),
    address: nullableString(row.address),
    city: nullableString(row.city),
    postal_code: nullableString(row.postal_code),
    authorized_pickup: requiredBoolean(row.authorized_pickup, 'authorized_pickup', context),
  };
}

function parseProfileEmergencyContact(value: unknown, familyId: string, index: number): ChildProfileEmergencyContact {
  const context = `profile emergency contact ${index + 1}`;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  const contactFamilyId = requiredString(row.family_id, 'family_id', context);
  if (contactFamilyId !== familyId) throw new ChildrenApiError(403, 'An emergency contact crossed the child family boundary.');
  return {
    id: requiredString(row.id, 'id', context),
    family_id: contactFamilyId,
    first_name: requiredString(row.first_name, 'first_name', context),
    last_name: requiredString(row.last_name, 'last_name', context),
    relationship: requiredString(row.relationship, 'relationship', context),
    cell_phone: typeof row.cell_phone === 'string' ? row.cell_phone : '',
    home_phone: nullableString(row.home_phone),
    authorized_pickup: requiredBoolean(row.authorized_pickup, 'authorized_pickup', context),
  };
}

function parseProfileEnrollment(value: unknown, childId: string, organizationId: string, index: number): ChildProfileEnrollment {
  const parsed = parseEnrollment(value, `profile enrollment ${index + 1}`);
  if (parsed.replayed) throw new ChildrenApiError(0, 'A nested enrollment cannot be marked as a command replay.');
  if (parsed.child_id !== childId || parsed.organization_id !== organizationId) {
    throw new ChildrenApiError(403, 'An enrollment crossed the child profile boundary.');
  }
  const row = value as Record<string, unknown>;
  return {
    ...parsed,
    facility_name: requiredString(row.facility_name, 'facility_name', `profile enrollment ${index + 1}`),
    program_name: nullableString(row.program_name),
    program_type: nullableString(row.program_type),
    room_name: nullableString(row.room_name),
  };
}

function parseChildProfile(value: unknown): ApiChildProfile {
  const child = parseChildDetails(value);
  const row = value as Record<string, unknown>;
  if (!row.family || typeof row.family !== 'object' || Array.isArray(row.family)) {
    throw new ChildrenApiError(0, 'The server returned an invalid child profile family.');
  }
  const familyRow = row.family as Record<string, unknown>;
  const familyId = requiredString(familyRow.id, 'id', 'child profile family');
  const organizationId = requiredString(familyRow.organization_id, 'organization_id', 'child profile family');
  if (familyId !== child.family_id || organizationId !== child.organization_id) {
    throw new ChildrenApiError(403, 'The child profile family crossed the authenticated record boundary.');
  }
  if (!Array.isArray(familyRow.guardians) || !Array.isArray(familyRow.emergency_contacts)) {
    throw new ChildrenApiError(0, 'The server returned an incomplete child care network.');
  }
  if (!Array.isArray(row.enrollments)) {
    throw new ChildrenApiError(0, 'The server returned an invalid child profile enrollment history.');
  }
  const enrollments = row.enrollments.map((item, index) => parseProfileEnrollment(item, child.id, child.organization_id, index));
  const currentEnrollmentId = row.current_enrollment && typeof row.current_enrollment === 'object' && !Array.isArray(row.current_enrollment)
    ? requiredString((row.current_enrollment as Record<string, unknown>).id, 'id', 'current enrollment')
    : null;
  const currentEnrollment = currentEnrollmentId
    ? enrollments.find((enrollment) => enrollment.id === currentEnrollmentId) || null
    : null;
  if (currentEnrollmentId && !currentEnrollment) {
    throw new ChildrenApiError(0, 'The current enrollment did not match the child enrollment history.');
  }
  return {
    ...child,
    enrollments,
    current_enrollment: currentEnrollment,
    family: {
      id: familyId,
      organization_id: organizationId,
      name: requiredString(familyRow.name, 'name', 'child profile family'),
      file_number: nullableString(familyRow.file_number),
      status: requiredString(familyRow.status, 'status', 'child profile family'),
      additional_notes: nullableString(familyRow.additional_notes),
      photo_consent: requiredBoolean(familyRow.photo_consent, 'photo_consent', 'child profile family'),
      field_trip_consent: requiredBoolean(familyRow.field_trip_consent, 'field_trip_consent', 'child profile family'),
      emergency_medical_consent: requiredBoolean(familyRow.emergency_medical_consent, 'emergency_medical_consent', 'child profile family'),
      guardians: familyRow.guardians.map((item, index) => parseProfileGuardian(item, familyId, index)),
      emergency_contacts: familyRow.emergency_contacts.map((item, index) => parseProfileEmergencyContact(item, familyId, index)),
      version: requiredInteger(familyRow.version, 'version', 'child profile family', 1),
      replayed: (() => {
        const replayed = requiredBoolean(familyRow.replayed, 'replayed', 'child profile family');
        if (replayed) throw new ChildrenApiError(0, 'A nested child profile family cannot be marked as a command replay.');
        return false as const;
      })(),
    },
  };
}

function parseFamily(value: unknown, index: number): ChildFamilyOption {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || !hasExactKeys(value as Record<string, unknown>, ['id', 'organization_id', 'name', 'status'])) {
    throw new ChildrenApiError(0, `The server returned an invalid family record at row ${index + 1}.`);
  }
  const row = value as Record<string, unknown>;
  return {
    id: requiredString(row.id, 'id', `family record at row ${index + 1}`),
    organization_id: requiredString(row.organization_id, 'organization_id', `family record at row ${index + 1}`),
    name: requiredString(row.name, 'name', `family record at row ${index + 1}`),
    status: requiredString(row.status, 'status', `family record at row ${index + 1}`),
  };
}

function sessionToken(): string {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) throw new ChildrenApiError(401, 'No redesign session token is available.', undefined, 'preflight');
  return token;
}

function resolveApiResourceUrl(path: string): string {
  const api = new URL(API_URL, typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1');
  const apiPrefix = api.pathname.replace(/\/+$/, '');
  const candidate = /^https?:\/\//i.test(path)
    ? new URL(path)
    : path.startsWith('/api/')
      ? new URL(path, api.origin)
      : new URL(`${apiPrefix}/${path.replace(/^\/+/, '')}`, api.origin);
  const insideApi = candidate.pathname === apiPrefix || candidate.pathname.startsWith(`${apiPrefix}/`);
  if (
    candidate.origin !== api.origin
    || !insideApi
    || candidate.username
    || candidate.password
    || candidate.hash
  ) {
    throw new ChildrenApiError(403, 'The child photo URL is outside the configured CareSync API boundary.');
  }
  return candidate.toString();
}

function resolveChildPhotoUrl(path: string): string {
  const resolved = resolveApiResourceUrl(path);
  const api = new URL(API_URL, typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1');
  const apiPrefix = api.pathname.replace(/\/+$/, '');
  const suffix = new URL(resolved).pathname.slice(apiPrefix.length);
  const candidate = new URL(resolved);
  if (candidate.search || candidate.hash || !/^\/children\/[^/]+\/photo$/.test(suffix)) {
    throw new ChildrenApiError(403, 'The child photo URL does not match a CareSync child photo endpoint.');
  }
  return resolved;
}

async function authorizedRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const url = resolveApiResourceUrl(path);
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${sessionToken()}`);
  addOrganizationHeader(headers);
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    }
    if (response.status === 403) notifyAuthorizationDenied();
    throw new ChildrenApiError(response.status, errorMessage(payload, response.status), payload, 'http');
  }
  return response;
}

async function requestJson(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) headers.set('Content-Type', 'application/json');
  const response = await authorizedRequest(path, { ...init, headers });
  if (response.status === 204) return null;
  return response.json();
}

function parseProtectedDirectoryPhotoUrl(value: unknown, childId: string, context: string): string | null {
  if (value === null) return null;
  const original = requiredString(value, 'profile_photo_url', context);
  const resolved = resolveChildPhotoUrl(original);
  const api = new URL(API_URL, typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1');
  const apiPrefix = api.pathname.replace(/\/+$/, '');
  if (new URL(resolved).pathname !== `${apiPrefix}/children/${encodeURIComponent(childId)}/photo`) {
    throw new ChildrenApiError(403, 'A child-directory photo crossed the requested child boundary.');
  }
  return original;
}

function parseDirectoryEnrollment(
  value: unknown,
  childId: string,
  organizationId: string,
  careLane: ChildDirectoryCareLane,
  context: string,
): ApiChildDirectoryEnrollment | null {
  if (value === null) {
    if (careLane !== 'unassigned') {
      throw new ChildrenApiError(0, `The server returned an invalid ${context} (missing open enrollment).`);
    }
    return null;
  }
  const keys = [
    'id', 'organization_id', 'child_id', 'facility_id', 'facility_name', 'program_id', 'program_name',
    'program_type', 'room_id', 'room_name', 'placement_effective_date', 'start_date', 'end_date',
    'status', 'version', 'placement_state',
  ] as const;
  if (!isObject(value) || !hasExactKeys(value, keys)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const enrollmentOrganizationId = requiredUuid(value.organization_id, 'organization_id', context);
  const enrollmentChildId = requiredUuid(value.child_id, 'child_id', context);
  if (enrollmentOrganizationId !== organizationId || enrollmentChildId !== childId) {
    throw new ChildrenApiError(403, 'A child-directory enrollment crossed the authenticated child boundary.');
  }
  const placementState = directoryPlacementState(value.placement_state, context);
  const programId = nullableUuid(value.program_id, 'program_id', context);
  const programName = nullableNonemptyString(value.program_name, 'program_name', context);
  const programType = directoryProgramType(value.program_type, context);
  const roomId = nullableUuid(value.room_id, 'room_id', context);
  const roomName = nullableNonemptyString(value.room_name, 'room_name', context);
  const placementEffectiveDate = nullableIsoDate(value.placement_effective_date, 'placement_effective_date', context);
  const startDate = requiredIsoDate(value.start_date, 'start_date', context);
  const endDate = nullableIsoDate(value.end_date, 'end_date', context);

  if (placementState === 'unassigned') {
    if (careLane !== 'unassigned' || programId || programName || programType || roomId || roomName || placementEffectiveDate) {
      throw new ChildrenApiError(0, `The server returned an incoherent ${context} (unassigned placement).`);
    }
  } else if (placementState === 'current' || placementState === 'reserved') {
    if (!programId || !programName || !programType || !roomId || !roomName || !placementEffectiveDate || careLane !== programType) {
      throw new ChildrenApiError(0, `The server returned an incoherent ${context} (${placementState} placement).`);
    }
  } else if (careLane !== 'needs_review') {
    throw new ChildrenApiError(0, `The server returned an incoherent ${context} (review placement).`);
  }
  if ((endDate && endDate < startDate) || (placementEffectiveDate && placementEffectiveDate < startDate)) {
    throw new ChildrenApiError(0, `The server returned an incoherent ${context} (date interval).`);
  }

  return {
    id: requiredUuid(value.id, 'id', context),
    organization_id: enrollmentOrganizationId,
    child_id: enrollmentChildId,
    facility_id: requiredUuid(value.facility_id, 'facility_id', context),
    facility_name: requiredString(value.facility_name, 'facility_name', context),
    program_id: programId,
    program_name: programName,
    program_type: programType,
    room_id: roomId,
    room_name: roomName,
    placement_effective_date: placementEffectiveDate,
    start_date: startDate,
    end_date: endDate,
    status: openEnrollmentStatus(value.status, context),
    version: requiredInteger(value.version, 'version', context, 1),
    placement_state: placementState,
  };
}

function parseDirectoryRecord(
  value: unknown,
  index: number,
  authenticatedOrganizationId: string,
  query: ChildDirectoryQuery,
): ApiChildDirectoryRecord {
  const context = `child-directory item at row ${index + 1}`;
  const keys = [
    'id', 'organization_id', 'family_id', 'family_name', 'first_name', 'middle_name', 'last_name',
    'date_of_birth', 'age_group', 'is_active', 'version', 'profile_photo_url',
    'profile_photo_updated_at', 'created_at', 'updated_at', 'care_lane', 'open_enrollment',
  ] as const;
  if (!isObject(value) || !hasExactKeys(value, keys)) {
    throw new ChildrenApiError(0, `The server returned an invalid ${context}.`);
  }
  const id = requiredUuid(value.id, 'id', context);
  const organizationId = requiredUuid(value.organization_id, 'organization_id', context);
  const familyId = requiredUuid(value.family_id, 'family_id', context);
  if (organizationId !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The child directory crossed the authenticated organization boundary.');
  }
  if (query.familyId && familyId !== query.familyId) {
    throw new ChildrenApiError(403, 'The child directory crossed the requested family boundary.');
  }
  const careLane = directoryCareLane(value.care_lane, context);
  const isActive = requiredBoolean(value.is_active, 'is_active', context);
  if ((query.status === 'active' && !isActive) || (query.status === 'inactive' && isActive)) {
    throw new ChildrenApiError(0, 'The child-directory item did not match the requested status filter.');
  }
  if (query.careLane !== 'all' && careLane !== query.careLane) {
    throw new ChildrenApiError(0, 'The child-directory item did not match the requested care-lane filter.');
  }
  const photoUrl = parseProtectedDirectoryPhotoUrl(value.profile_photo_url, id, context);
  const photoUpdatedAt = nullableIsoTimestamp(value.profile_photo_updated_at, 'profile_photo_updated_at', context);
  if (Boolean(photoUrl) !== Boolean(photoUpdatedAt)) {
    throw new ChildrenApiError(0, `The server returned an incoherent ${context} (profile photo metadata).`);
  }
  return {
    id,
    organization_id: organizationId,
    family_id: familyId,
    family_name: requiredString(value.family_name, 'family_name', context),
    first_name: requiredString(value.first_name, 'first_name', context),
    middle_name: nullableNonemptyString(value.middle_name, 'middle_name', context),
    last_name: requiredString(value.last_name, 'last_name', context),
    date_of_birth: requiredIsoDate(value.date_of_birth, 'date_of_birth', context),
    age_group: nullableNonemptyString(value.age_group, 'age_group', context),
    is_active: isActive,
    version: requiredInteger(value.version, 'version', context, 1),
    profile_photo_url: photoUrl,
    profile_photo_updated_at: photoUpdatedAt,
    created_at: requiredIsoTimestamp(value.created_at, 'created_at', context),
    updated_at: requiredIsoTimestamp(value.updated_at, 'updated_at', context),
    care_lane: careLane,
    open_enrollment: parseDirectoryEnrollment(value.open_enrollment, id, organizationId, careLane, `${context} open enrollment`),
  };
}

function parseDirectoryCounts(value: unknown): ChildDirectoryCounts {
  const keys = ['total', 'active', 'inactive', 'daycare', 'out_of_school_care', 'unassigned', 'reserved', 'needs_review'] as const;
  if (!isObject(value) || !hasExactKeys(value, keys)) {
    throw new ChildrenApiError(0, 'The server returned invalid child-directory counts.');
  }
  const counts: ChildDirectoryCounts = {
    total: requiredInteger(value.total, 'total', 'child-directory counts'),
    active: requiredInteger(value.active, 'active', 'child-directory counts'),
    inactive: requiredInteger(value.inactive, 'inactive', 'child-directory counts'),
    daycare: requiredInteger(value.daycare, 'daycare', 'child-directory counts'),
    out_of_school_care: requiredInteger(value.out_of_school_care, 'out_of_school_care', 'child-directory counts'),
    unassigned: requiredInteger(value.unassigned, 'unassigned', 'child-directory counts'),
    reserved: requiredInteger(value.reserved, 'reserved', 'child-directory counts'),
    needs_review: requiredInteger(value.needs_review, 'needs_review', 'child-directory counts'),
  };
  if (
    counts.active + counts.inactive !== counts.total
    || counts.daycare + counts.out_of_school_care + counts.unassigned + counts.needs_review !== counts.total
    || counts.reserved > counts.daycare + counts.out_of_school_care
  ) {
    throw new ChildrenApiError(0, 'The server returned internally inconsistent child-directory counts.');
  }
  return counts;
}

function normalizeChildDirectoryQuery(query: Partial<ChildDirectoryQuery>): ChildDirectoryQuery {
  const search = query.search?.trim() || '';
  const status = query.status ?? 'all';
  const careLane = query.careLane ?? 'all';
  const familyId = query.familyId || null;
  const limit = query.limit ?? CHILD_DIRECTORY_PAGE_SIZE;
  const offset = query.offset ?? 0;
  if (search.length > 200) throw new ChildrenApiError(422, 'Child directory search is limited to 200 characters.', undefined, 'preflight');
  if (status !== 'all' && status !== 'active' && status !== 'inactive') {
    throw new ChildrenApiError(422, 'Choose a supported child status filter.', undefined, 'preflight');
  }
  if (careLane !== 'all' && careLane !== 'daycare' && careLane !== 'out_of_school_care' && careLane !== 'unassigned' && careLane !== 'needs_review') {
    throw new ChildrenApiError(422, 'Choose a supported child care-lane filter.', undefined, 'preflight');
  }
  if (familyId && !UUID_PATTERN.test(familyId)) {
    throw new ChildrenApiError(422, 'Choose a valid family before filtering the child directory.', undefined, 'preflight');
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > CHILD_DIRECTORY_PAGE_SIZE) {
    throw new ChildrenApiError(422, `Child directory page size must be between 1 and ${CHILD_DIRECTORY_PAGE_SIZE}.`, undefined, 'preflight');
  }
  if (!Number.isInteger(offset) || offset < 0) {
    throw new ChildrenApiError(422, 'Child directory offset must be a non-negative integer.', undefined, 'preflight');
  }
  return { search, status, careLane, familyId, limit, offset };
}

function expectedFilteredTotal(counts: ChildDirectoryCounts, query: ChildDirectoryQuery): number | null {
  const statusCount = query.status === 'active' ? counts.active : query.status === 'inactive' ? counts.inactive : counts.total;
  const laneCount = query.careLane === 'all' ? counts.total : counts[query.careLane];
  if (query.status === 'all') return laneCount;
  if (query.careLane === 'all') return statusCount;
  return null;
}

/** Load one privacy-minimized, server-filtered child-directory window. */
export async function fetchChildDirectoryPage(
  authenticatedOrganizationId: string,
  query: Partial<ChildDirectoryQuery> = {},
  signal?: AbortSignal,
): Promise<ChildDirectoryPage> {
  if (!UUID_PATTERN.test(authenticatedOrganizationId)) {
    throw new ChildrenApiError(403, 'An authenticated organization is required before loading children.', undefined, 'preflight');
  }
  const normalized = normalizeChildDirectoryQuery(query);
  const search = new URLSearchParams({
    search: normalized.search,
    status: normalized.status,
    care_lane: normalized.careLane,
    limit: String(normalized.limit),
    offset: String(normalized.offset),
  });
  if (normalized.familyId) search.set('family_id', normalized.familyId);
  const payload = await requestJson(`/children/directory?${search}`, { signal });
  if (!isObject(payload) || !hasExactKeys(payload, ['items', 'total', 'limit', 'offset', 'counts']) || !Array.isArray(payload.items)) {
    throw new ChildrenApiError(0, 'The server returned an invalid child-directory page.');
  }
  const total = requiredInteger(payload.total, 'total', 'child-directory page');
  const limit = requiredInteger(payload.limit, 'limit', 'child-directory page', 1);
  const offset = requiredInteger(payload.offset, 'offset', 'child-directory page');
  const counts = parseDirectoryCounts(payload.counts);
  const expectedLength = Math.min(limit, Math.max(0, total - offset));
  if (limit !== normalized.limit || offset !== normalized.offset || payload.items.length !== expectedLength) {
    throw new ChildrenApiError(0, 'The child-directory page did not match the requested window.');
  }
  const exactTotal = expectedFilteredTotal(counts, normalized);
  if ((exactTotal !== null && total !== exactTotal) || (exactTotal === null && total > Math.min(
    normalized.status === 'active' ? counts.active : counts.inactive,
    counts[normalized.careLane as ChildDirectoryCareLane],
  ))) {
    throw new ChildrenApiError(0, 'The child-directory total did not reconcile with its filters and counts.');
  }
  const items = payload.items.map((item, index) => parseDirectoryRecord(item, index, authenticatedOrganizationId, normalized));
  if (new Set(items.map((item) => item.id)).size !== items.length) {
    throw new ChildrenApiError(0, 'The child-directory page returned duplicate child IDs.');
  }
  const enrollmentIds = items.flatMap((item) => item.open_enrollment ? [item.open_enrollment.id] : []);
  if (new Set(enrollmentIds).size !== enrollmentIds.length) {
    throw new ChildrenApiError(0, 'The child-directory page returned duplicate enrollment IDs.');
  }
  const pageActive = items.filter((item) => item.is_active).length;
  const pageReserved = items.filter((item) => item.open_enrollment?.placement_state === 'reserved').length;
  const pageCareLanes = {
    daycare: items.filter((item) => item.care_lane === 'daycare').length,
    out_of_school_care: items.filter((item) => item.care_lane === 'out_of_school_care').length,
    unassigned: items.filter((item) => item.care_lane === 'unassigned').length,
    needs_review: items.filter((item) => item.care_lane === 'needs_review').length,
  };
  if (
    pageActive > counts.active
    || items.length - pageActive > counts.inactive
    || pageReserved > counts.reserved
    || pageCareLanes.daycare > counts.daycare
    || pageCareLanes.out_of_school_care > counts.out_of_school_care
    || pageCareLanes.unassigned > counts.unassigned
    || pageCareLanes.needs_review > counts.needs_review
  ) {
    throw new ChildrenApiError(0, 'The child-directory page items exceeded their declared counts.');
  }
  return { items, total, limit, offset, counts };
}

function parseFamilyOptionsPage(
  payload: unknown,
  authenticatedOrganizationId: string,
  requestedLimit: number,
  requestedOffset: number,
): { items: ChildFamilyOption[]; total: number } {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)
    || !hasExactKeys(payload as Record<string, unknown>, ['items', 'total', 'limit', 'offset'])) {
    throw new ChildrenApiError(0, 'The server returned an invalid family-options page.');
  }
  const page = payload as Record<string, unknown>;
  if (!Array.isArray(page.items)) throw new ChildrenApiError(0, 'The server returned an invalid family-options item list.');
  const total = requiredInteger(page.total, 'total', 'family-options page');
  const limit = requiredInteger(page.limit, 'limit', 'family-options page', 1);
  const offset = requiredInteger(page.offset, 'offset', 'family-options page');
  if (limit !== requestedLimit || offset !== requestedOffset) {
    throw new ChildrenApiError(0, 'The family-options page did not match the requested window.');
  }
  const expectedLength = Math.min(limit, Math.max(0, total - offset));
  if (page.items.length !== expectedLength) {
    throw new ChildrenApiError(0, 'The family-options page was incomplete for its declared total.');
  }
  const items = page.items.map(parseFamily);
  if (items.some((family) => family.organization_id !== authenticatedOrganizationId)) {
    throw new ChildrenApiError(403, 'The family options crossed the authenticated organization boundary.');
  }
  if (new Set(items.map((family) => family.id)).size !== items.length) {
    throw new ChildrenApiError(0, 'The family-options page returned duplicate family IDs.');
  }
  return { items, total };
}

/** Page through the privacy-minimized family selector, never full family records. */
export async function fetchChildFamilies(
  authenticatedOrganizationId: string,
  signal: AbortSignal,
  search = '',
): Promise<ChildFamilyOption[]> {
  if (!authenticatedOrganizationId.trim()) {
    throw new ChildrenApiError(403, 'An authenticated organization is required before loading families.');
  }
  const records = new Map<string, ChildFamilyOption>();
  let declaredTotal: number | null = null;
  for (let offset = 0; ; offset += FAMILY_OPTION_PAGE_SIZE) {
    const query = new URLSearchParams({
      search: search.trim(),
      limit: String(FAMILY_OPTION_PAGE_SIZE),
      offset: String(offset),
    });
    const payload = await requestJson(`/families/options?${query}`, { signal });
    const page = parseFamilyOptionsPage(payload, authenticatedOrganizationId, FAMILY_OPTION_PAGE_SIZE, offset);
    if (declaredTotal === null) declaredTotal = page.total;
    else if (page.total !== declaredTotal) throw new ChildrenApiError(0, 'The family-options total changed while paging.');
    page.items.forEach((family) => {
      if (records.has(family.id)) throw new ChildrenApiError(0, 'The family-options response repeated a family across pages.');
      records.set(family.id, family);
    });
    if (offset + page.items.length >= page.total) break;
  }
  return [...records.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function ensureOrganizationId(organizationId: string): void {
  if (!organizationId.trim()) {
    throw new ChildrenApiError(403, 'An authenticated organization is required before managing enrollment.');
  }
}

function ensureFacilityChoice(
  facilityId: string,
  facilities: readonly EnrollmentFacilityOption[],
): EnrollmentFacilityOption {
  const facility = facilities.find((option) => option.id === facilityId && option.status === 'active');
  if (!facility) {
    throw new ChildrenApiError(403, 'Select an active facility returned for this organization.');
  }
  return facility;
}

function ensureEnrollmentBoundary(
  enrollment: ApiChildEnrollment,
  organizationId: string,
  childId: string,
  enrollmentId?: string,
): void {
  if (enrollment.organization_id !== organizationId || enrollment.child_id !== childId) {
    throw new ChildrenApiError(403, 'The enrollment response crossed the authenticated child boundary.');
  }
  if (enrollmentId && enrollment.id !== enrollmentId) {
    throw new ChildrenApiError(0, 'The enrollment response did not match the requested record.');
  }
}

/** Load active organization facilities from the dedicated Basic facilities endpoint. */
export async function fetchEnrollmentFacilities(
  authenticatedOrganizationId: string,
  signal?: AbortSignal,
  includeInactive = false,
): Promise<EnrollmentFacilityOption[]> {
  ensureOrganizationId(authenticatedOrganizationId);
  const payload = await requestJson('/facilities', { signal });
  if (!Array.isArray(payload)) throw new ChildrenApiError(0, 'The server returned an invalid facility directory.');
  const facilities = payload.map(parseFacility);
  if (facilities.some((facility) => facility.organization_id !== authenticatedOrganizationId)) {
    throw new ChildrenApiError(403, 'The facility response crossed the authenticated organization boundary.');
  }
  return facilities
    .filter((facility) => includeInactive || facility.status === 'active')
    .sort((left, right) => left.name.localeCompare(right.name));
}

/** Load active programs and rooms for one verified facility from their dedicated endpoints. */
export async function fetchEnrollmentPlacementOptions(
  authenticatedOrganizationId: string,
  facilityId: string,
  facilities: readonly EnrollmentFacilityOption[],
  signal?: AbortSignal,
): Promise<EnrollmentPlacementOptions> {
  ensureOrganizationId(authenticatedOrganizationId);
  const facility = ensureFacilityChoice(facilityId, facilities);
  if (facility.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The selected facility is outside the authenticated organization.');
  }
  const query = `facility_id=${encodeURIComponent(facilityId)}`;
  const [programPayload, roomPayload, rosterPayload] = await Promise.all([
    requestJson(`/programs?${query}`, { signal }),
    requestJson(`/rooms?${query}`, { signal }),
    requestJson(`/room-rosters?${query}`, { signal }),
  ]);
  if (!Array.isArray(programPayload)) throw new ChildrenApiError(0, 'The server returned an invalid program directory.');
  if (!Array.isArray(roomPayload)) throw new ChildrenApiError(0, 'The server returned an invalid room directory.');
  const programs = programPayload.map(parseProgram);
  const rooms = roomPayload.map(parseRoom);
  const occupancy = parseRoomRosterOptions(rosterPayload, facilityId);
  if (programs.some((program) => program.organization_id !== authenticatedOrganizationId || program.facility_id !== facilityId)) {
    throw new ChildrenApiError(403, 'The program response crossed the selected facility boundary.');
  }
  if (rooms.some((room) => room.organization_id !== authenticatedOrganizationId || room.facility_id !== facilityId)) {
    throw new ChildrenApiError(403, 'The room response crossed the selected facility boundary.');
  }
  if (rooms.some((room) => !occupancy.has(room.id)) || occupancy.size !== rooms.length) {
    throw new ChildrenApiError(0, 'The room roster did not match the verified room directory.');
  }
  return {
    programs: programs.filter((program) => program.is_active).sort((left, right) => left.name.localeCompare(right.name)),
    rooms: rooms
      .filter((room) => room.is_active)
      .map((room) => ({ ...room, occupancy: occupancy.get(room.id)! }))
      .sort((left, right) => left.name.localeCompare(right.name)),
  };
}

function ensureAllowedFamily(familyId: string, allowedFamilyIds: ReadonlySet<string>): void {
  if (!allowedFamilyIds.has(familyId)) {
    throw new ChildrenApiError(403, 'The selected family is outside the confirmed organization directory.');
  }
}

export async function fetchChildDetails(
  childId: string,
  allowedFamilyIds: ReadonlySet<string>,
  authenticatedOrganizationId: string,
  signal: AbortSignal,
): Promise<ApiChildDetails> {
  ensureOrganizationId(authenticatedOrganizationId);
  const payload = await requestJson(`/children/${encodeURIComponent(childId)}`, { signal, cache: 'no-store' });
  const child = parseChildDetails(payload);
  if (child.id !== childId) throw new ChildrenApiError(0, 'The child detail response did not match the requested record.');
  if (child.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The child detail crossed the authenticated organization boundary.');
  }
  ensureAllowedFamily(child.family_id, allowedFamilyIds);
  return child;
}

export async function fetchChildProfile(
  childId: string,
  authenticatedOrganizationId: string,
  signal?: AbortSignal,
): Promise<ApiChildProfile> {
  ensureOrganizationId(authenticatedOrganizationId);
  const payload = await requestJson(`/children/${encodeURIComponent(childId)}`, { signal, cache: 'no-store' });
  const child = parseChildProfile(payload);
  if (child.id !== childId) throw new ChildrenApiError(0, 'The child profile did not match the requested record.');
  if (child.organization_id !== authenticatedOrganizationId || child.family.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The child profile crossed the authenticated organization boundary.');
  }
  return child;
}

function parsePhotoMetadata(value: unknown, childId: string): ChildPhotoMetadata {
  const context = 'child photo metadata';
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChildrenApiError(0, `The server returned invalid ${context}.`);
  }
  const row = value as Record<string, unknown>;
  const returnedChildId = requiredString(row.child_id, 'child_id', context);
  if (returnedChildId !== childId) throw new ChildrenApiError(403, 'The uploaded photo crossed the requested child boundary.');
  return {
    child_id: returnedChildId,
    url: requiredString(row.url, 'url', context),
    content_type: requiredString(row.content_type, 'content_type', context),
    size_bytes: requiredInteger(row.size_bytes, 'size_bytes', context, 1),
    width: requiredInteger(row.width, 'width', context, 1),
    height: requiredInteger(row.height, 'height', context, 1),
    sha256: requiredString(row.sha256, 'sha256', context),
    original_filename: nullableString(row.original_filename),
    updated_at: requiredString(row.updated_at, 'updated_at', context),
  };
}

export async function fetchChildPhoto(
  photoUrl: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await authorizedRequest(resolveChildPhotoUrl(photoUrl), {
    headers: { Accept: 'image/jpeg,image/webp' },
    cache: 'no-cache',
    signal,
  });
  const blob = await response.blob();
  if (!blob.type.startsWith('image/')) {
    throw new ChildrenApiError(0, 'The server returned a non-image child photo.');
  }
  return blob;
}

export async function uploadChildPhoto(
  childId: string,
  file: File,
  signal?: AbortSignal,
): Promise<ChildPhotoMetadata> {
  const form = new FormData();
  form.set('file', file);
  const response = await authorizedRequest(`/children/${encodeURIComponent(childId)}/photo`, {
    method: 'PUT',
    headers: { Accept: 'application/json' },
    body: form,
    signal,
  });
  return parsePhotoMetadata(await response.json(), childId);
}

export async function deleteChildPhoto(
  childId: string,
  signal?: AbortSignal,
): Promise<void> {
  await authorizedRequest(`/children/${encodeURIComponent(childId)}/photo`, {
    method: 'DELETE',
    signal,
  });
}

function unknownCommandOutcome(caught: unknown, label: string): never {
  if (caught instanceof CommandOutcomeUnknownError) throw caught;
  if (
    caught instanceof TypeError
    || caught instanceof SyntaxError
    || (caught instanceof Error && caught.name === 'AbortError')
    || (caught instanceof ChildrenApiError && (
      caught.origin === 'response'
      || (caught.origin === 'http' && (
        caught.status === 408
        || caught.status === 425
        || caught.status >= 500
      ))
    ))
  ) {
    throw new CommandOutcomeUnknownError(`The connection ended before CareSync could confirm this ${label}. Check the saved result; CareSync will not resend it automatically.`, caught);
  }
  throw caught;
}

function assertChildMutation(
  payload: unknown,
  allowedFamilyIds: ReadonlySet<string>,
  authenticatedOrganizationId: string,
  childId?: string,
  expectedVersion?: number,
): ApiChildDetails {
  const child = parseChildDetails(payload);
  if (childId && child.id !== childId) throw new ChildrenApiError(0, 'The saved child response did not match the requested record.');
  if (child.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The saved child response crossed the authenticated organization boundary.');
  }
  ensureAllowedFamily(child.family_id, allowedFamilyIds);
  if (expectedVersion !== undefined && (
    (!child.replayed && child.version !== expectedVersion + 1)
    || (child.replayed && child.version <= expectedVersion)
  )) {
    throw new ChildrenApiError(0, 'The saved child response did not confirm the exact expected version transition.');
  }
  return child;
}

export function buildChildCreateCommand(input: ChildMutationInput): ChildCreateCommand {
  return createExactChildcareCommand(input);
}

export function buildChildUpdateCommand(input: ChildMutationInput, expectedVersion: number): ChildUpdateCommand {
  return createExactChildcareCommand(input, expectedVersion);
}

export function buildChildActiveStateCommand(isActive: boolean, expectedVersion: number): ChildActiveStateCommand {
  return createExactChildcareCommand({ is_active: isActive }, expectedVersion);
}

export async function createChild(
  command: ChildCreateCommand,
  allowedFamilyIds: ReadonlySet<string>,
  authenticatedOrganizationId: string,
  signal?: AbortSignal,
): Promise<ApiChildDetails> {
  ensureOrganizationId(authenticatedOrganizationId);
  ensureAllowedFamily(command.intent.family_id, allowedFamilyIds);
  try {
    const payload = await requestJson('/children', {
      method: 'POST',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    return assertChildMutation(payload, allowedFamilyIds, authenticatedOrganizationId);
  } catch (caught) {
    unknownCommandOutcome(caught, 'child creation');
  }
}

export async function updateChild(
  childId: string,
  command: ChildUpdateCommand,
  allowedFamilyIds: ReadonlySet<string>,
  authenticatedOrganizationId: string,
  signal?: AbortSignal,
): Promise<ApiChildDetails> {
  ensureOrganizationId(authenticatedOrganizationId);
  ensureAllowedFamily(command.intent.family_id, allowedFamilyIds);
  try {
    const payload = await requestJson(`/children/${encodeURIComponent(childId)}`, {
      method: 'PATCH',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    return assertChildMutation(payload, allowedFamilyIds, authenticatedOrganizationId, childId, command.expectedVersion);
  } catch (caught) {
    unknownCommandOutcome(caught, 'child update');
  }
}

export async function archiveChild(
  childId: string,
  familyId: string,
  command: ChildActiveStateCommand,
  allowedFamilyIds: ReadonlySet<string>,
  authenticatedOrganizationId: string,
  signal?: AbortSignal,
): Promise<ApiChildDetails> {
  ensureOrganizationId(authenticatedOrganizationId);
  ensureAllowedFamily(familyId, allowedFamilyIds);
  if (command.intent.is_active) throw new ChildrenApiError(0, 'The archive command must deactivate the child.');
  try {
    const payload = await requestJson(`/children/${encodeURIComponent(childId)}`, {
      method: 'PATCH',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    const child = assertChildMutation(payload, allowedFamilyIds, authenticatedOrganizationId, childId, command.expectedVersion);
    // A replay returns the current canonical projection. The child may have
    // legitimately been reactivated after this exact archive command was first
    // committed, so only a fresh response must still be inactive.
    if (!child.replayed && child.is_active) {
      throw new ChildrenApiError(0, 'The server did not confirm that the child was archived.');
    }
    return child;
  } catch (caught) {
    unknownCommandOutcome(caught, 'child archive');
  }
}

export function buildEnrollmentCreateCommand(input: EnrollmentCreateInput): EnrollmentCreateCommand {
  return createExactChildcareCommand(input);
}

export function buildEnrollmentPlacementApprovalCommand(
  input: EnrollmentPlacementApprovalInput,
  expectedVersion: number,
): EnrollmentPlacementApprovalCommand {
  return createExactChildcareCommand(input, expectedVersion);
}

export function buildEnrollmentEndCommand(endDate: string, expectedVersion: number): EnrollmentLifecycleCommand {
  return createExactChildcareCommand({ status: 'ended', end_date: endDate }, expectedVersion);
}

/** Create a pending, unassigned enrollment. Placement is a separate approval command. */
export async function createChildEnrollment(
  childId: string,
  authenticatedOrganizationId: string,
  command: EnrollmentCreateCommand,
  facilities: readonly EnrollmentFacilityOption[],
  signal?: AbortSignal,
): Promise<ApiChildEnrollment> {
  ensureOrganizationId(authenticatedOrganizationId);
  if (!childId.trim()) throw new ChildrenApiError(0, 'A child is required before creating enrollment.');
  const facility = ensureFacilityChoice(command.intent.facility_id, facilities);
  if (facility.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The selected facility is outside the authenticated organization.');
  }
  try {
    const payload = await requestJson(`/children/${encodeURIComponent(childId)}/enrollments`, {
      method: 'POST',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    const enrollment = parseEnrollment(payload, 'created enrollment');
    ensureEnrollmentBoundary(enrollment, authenticatedOrganizationId, childId);
    if (
      enrollment.facility_id !== command.intent.facility_id
      || enrollment.start_date.slice(0, 10) !== command.intent.start_date
      || (!enrollment.replayed && (
        enrollment.status !== 'pending'
        || enrollment.program_id !== null
        || enrollment.room_id !== null
        || enrollment.placement_effective_date !== null
      ))
    ) {
      throw new ChildrenApiError(0, 'The created enrollment did not confirm the pending, unassigned command.');
    }
    return enrollment;
  } catch (caught) {
    unknownCommandOutcome(caught, 'enrollment creation');
  }
}

/** Approve one DOB/capacity-validated room placement inside the enrollment facility. */
export async function approveChildEnrollmentPlacement(
  enrollment: ApiChildEnrollment,
  authenticatedOrganizationId: string,
  command: EnrollmentPlacementApprovalCommand,
  facilities: readonly EnrollmentFacilityOption[],
  options: EnrollmentPlacementOptions,
  signal?: AbortSignal,
): Promise<ApiChildEnrollment> {
  ensureOrganizationId(authenticatedOrganizationId);
  ensureEnrollmentBoundary(enrollment, authenticatedOrganizationId, enrollment.child_id);
  if (
    enrollment.status === 'ended'
    || enrollment.program_id !== null
    || enrollment.room_id !== null
    || enrollment.placement_effective_date !== null
  ) {
    throw new ChildrenApiError(409, 'Initial placement approval is available only for a pending, unassigned enrollment. Use the later placement-history workflow for transfers.');
  }
  if (command.expectedVersion !== enrollment.version) {
    throw new ChildrenApiError(409, 'The enrollment version changed. Reload before approving placement.');
  }
  const facility = ensureFacilityChoice(enrollment.facility_id, facilities);
  if (facility.organization_id !== authenticatedOrganizationId) {
    throw new ChildrenApiError(403, 'The enrollment facility is outside the authenticated organization.');
  }
  const room = options.rooms.find((candidate) => candidate.id === command.intent.room_id && candidate.is_active);
  if (!room || room.facility_id !== enrollment.facility_id || !room.program_id) {
    throw new ChildrenApiError(403, 'Select an active room returned for the enrollment facility.');
  }
  if (room.occupancy >= room.capacity && room.id !== enrollment.room_id) {
    throw new ChildrenApiError(422, `${room.name} has reached its enrollment capacity.`);
  }
  try {
    const payload = await requestJson(`/enrollments/${encodeURIComponent(enrollment.id)}/placement-approval`, {
      method: 'POST',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    const saved = parseEnrollment(payload, 'approved enrollment placement');
    ensureEnrollmentBoundary(saved, authenticatedOrganizationId, enrollment.child_id, enrollment.id);
    if (
      saved.facility_id !== enrollment.facility_id
      || saved.room_id !== command.intent.room_id
      || saved.program_id !== room.program_id
      || saved.placement_effective_date !== command.intent.effective_date
      || (!saved.replayed && saved.status !== 'active')
      || (!saved.replayed && saved.version !== (command.expectedVersion || 0) + 1)
      || (saved.replayed && saved.version <= (command.expectedVersion || 0))
    ) {
      throw new ChildrenApiError(0, 'The server did not confirm the approved enrollment placement.');
    }
    return saved;
  } catch (caught) {
    unknownCommandOutcome(caught, 'enrollment placement approval');
  }
}

/** End one enrollment atomically; this never creates a replacement enrollment. */
export async function endChildEnrollment(
  enrollment: ApiChildEnrollment,
  authenticatedOrganizationId: string,
  command: EnrollmentLifecycleCommand,
  signal?: AbortSignal,
): Promise<ApiChildEnrollment> {
  ensureOrganizationId(authenticatedOrganizationId);
  ensureEnrollmentBoundary(enrollment, authenticatedOrganizationId, enrollment.child_id);
  if (command.expectedVersion !== enrollment.version) {
    throw new ChildrenApiError(409, 'The enrollment version changed. Reload before ending enrollment.');
  }
  if (command.intent.status !== 'ended' || !command.intent.end_date) {
    throw new ChildrenApiError(0, 'An end date is required for the enrollment end command.');
  }
  try {
    const payload = await requestJson(`/enrollments/${encodeURIComponent(enrollment.id)}`, {
      method: 'PATCH',
      body: JSON.stringify(exactChildcareCommandBody(command)),
      signal,
    });
    const saved = parseEnrollment(payload, 'ended enrollment');
    ensureEnrollmentBoundary(saved, authenticatedOrganizationId, enrollment.child_id, enrollment.id);
    if (
      (!saved.replayed && (saved.status !== 'ended' || saved.end_date !== command.intent.end_date || saved.is_active))
      || (!saved.replayed && saved.version !== (command.expectedVersion || 0) + 1)
      || (saved.replayed && saved.version <= (command.expectedVersion || 0))
    ) {
      throw new ChildrenApiError(0, 'The server did not confirm that enrollment ended.');
    }
    return saved;
  } catch (caught) {
    unknownCommandOutcome(caught, 'enrollment lifecycle change');
  }
}
