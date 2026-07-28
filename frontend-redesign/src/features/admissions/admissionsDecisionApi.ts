import { ApiError, apiRequest, getSelectedOrganizationId } from '../../api/client';

export const ADMISSION_STATUSES = [
  'draft',
  'submitted',
  'under_review',
  'waitlisted',
  'offered',
  'accepted',
  'declined',
  'withdrawn',
] as const;

export const ADMISSION_ACTIONS = [
  'update',
  'submit',
  'start_review',
  'correct',
  'enter_waitlist',
  'reopen_review',
  'decline',
  'withdraw',
  'issue_offer',
  'withdraw_offer',
  'decline_offer',
  'accept_and_convert',
] as const;

export type AdmissionStatus = typeof ADMISSION_STATUSES[number];
export type AdmissionActionName = typeof ADMISSION_ACTIONS[number];
export type AdmissionOfferStatus = 'open' | 'accepted' | 'declined' | 'withdrawn';
export type AdmissionWaitlistStatus = 'active' | 'offered' | 'closed';
export const ADMISSION_RECEIPT_COMMANDS = [
  'admission.application.create',
  'admission.application.update',
  'admission.application.submit',
  'admission.application.review.start',
  'admission.application.correct',
  'admission.application.decline',
  'admission.application.withdraw',
  'admission.waitlist.enter',
  'admission.waitlist.reopen_review',
  'admission.offer.issue',
  'admission.offer.withdraw',
  'admission.offer.decline',
  'admission.offer.accept_and_convert',
] as const;
export type AdmissionReceiptCommand = typeof ADMISSION_RECEIPT_COMMANDS[number];
export type AdmissionCommandTargetType =
  | 'admission_application'
  | 'admission_waitlist'
  | 'admission_offer';

export interface AdmissionReplayReceipt {
  command_type: AdmissionReceiptCommand;
  target_type: AdmissionCommandTargetType;
  target_id: string;
  committed_version: number;
}

export interface AdmissionListItem {
  id: string;
  reference: string;
  status: AdmissionStatus;
  version: number;
  source: 'administrator_entry';
  preference_count: number;
  submitted_at: string | null;
  updated_at: string;
  current_lane: { facility_id: string; program_id: string } | null;
  offer_status: AdmissionOfferStatus | null;
}

export interface AdmissionWorkspace {
  counts: Record<AdmissionStatus, number>;
  lanes: Array<{ status: AdmissionStatus; count: number; applications: AdmissionListItem[] }>;
  waitlist_lane_count: number;
}

export interface AdmissionApplicationsPage {
  items: AdmissionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdmissionChildInput {
  first_name: string;
  last_name: string;
  date_of_birth: string;
}

export interface AdmissionContactInput {
  first_name: string;
  last_name: string;
  relationship: string;
  email: string | null;
  telephone: string | null;
}

export interface AdmissionPreferenceInput {
  rank: number;
  facility_id: string;
  program_id: string;
  desired_start_date: string;
}

export interface AdmissionCreateInput {
  child: AdmissionChildInput;
  primary_contact: AdmissionContactInput;
  preferences: AdmissionPreferenceInput[];
  internal_note: string | null;
}

export interface AdmissionPreference {
  id: string;
  rank: number;
  facility_id: string;
  facility_name: string;
  program_id: string;
  program_name: string;
  requested_start_date: string;
  application_version: number;
}

export interface AdmissionWaitlist {
  id: string;
  status: AdmissionWaitlistStatus;
  version: number;
  facility_id: string;
  facility_name: string;
  program_id: string;
  program_name: string;
  requested_start_date: string;
  priority_at: string;
  position: number | null;
  closure_reason:
    | 'facts_changed'
    | 'review_reopened'
    | 'application_declined'
    | 'application_withdrawn'
    | 'offer_declined'
    | 'application_accepted'
    | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface AdmissionOffer {
  id: string;
  status: AdmissionOfferStatus;
  version: number;
  facility_id: string;
  facility_name: string;
  program_id: string;
  program_name: string;
  proposed_start_date: string;
  respond_by_date: string | null;
  prior_application_status: 'under_review' | 'waitlisted';
  issued_at: string;
  withdrawn_at: string | null;
  declined_at: string | null;
  accepted_at: string | null;
}

export interface AdmissionConversion {
  id: string;
  resolution_mode: 'create_family_and_child' | 'reuse_family_create_child' | 'reuse_child';
  family_id: string;
  child_id: string;
  enrollment_id: string;
  converted_at: string;
}

export interface AdmissionTimelineItem {
  id: string;
  application_version: number;
  command: string;
  from_status: AdmissionStatus | null;
  to_status: AdmissionStatus;
  reason_code:
    | 'create'
    | 'updated'
    | 'submitted'
    | 'review_started'
    | 'facts_changed'
    | 'waitlisted'
    | 'review_reopened'
    | 'provider_declined'
    | 'family_withdrawn'
    | 'offer_issued'
    | 'offer_withdrawn'
    | 'offer_declined'
    | 'offer_accepted'
    | null;
  actor_user_id: string;
  client_operation_id: string;
  occurred_at: string;
}

export interface AdmissionDetail {
  id: string;
  organization_id: string;
  reference: string;
  source: 'administrator_entry';
  status: AdmissionStatus;
  version: number;
  child: AdmissionChildInput;
  contact: AdmissionContactInput;
  internal_note: string | null;
  preferences: AdmissionPreference[];
  waitlist: AdmissionWaitlist | null;
  offer: AdmissionOffer | null;
  conversion: AdmissionConversion | null;
  timeline: AdmissionTimelineItem[];
  timeline_total: number;
  allowed_actions: AdmissionActionName[];
  committed_versions: { application: number; waitlist: number | null; offer: number | null };
  replayed: boolean;
  replay_receipt: AdmissionReplayReceipt | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  review_started_at: string | null;
  terminal_at: string | null;
}

export interface AdmissionLaneProgram {
  id: string;
  name: string;
  program_type: 'daycare' | 'out_of_school_care';
}

export interface AdmissionLaneFacility {
  id: string;
  name: string;
  programs: AdmissionLaneProgram[];
}

export interface AdmissionLaneDirectory {
  facilities: AdmissionLaneFacility[];
}

export type AdmissionConversionMatchReason =
  | 'child_name_and_date_of_birth'
  | 'primary_contact_email'
  | 'primary_contact_telephone';

export interface AdmissionConversionFamilyCandidate {
  id: string;
  display_label: string;
  version: number;
  status: 'pending' | 'active' | 'inactive' | 'archived';
  match_reasons: AdmissionConversionMatchReason[];
}

export interface AdmissionConversionChildCandidate {
  id: string;
  family_id: string;
  display_label: string;
  version: number;
  is_active: boolean;
  match_reasons: AdmissionConversionMatchReason[];
  has_open_enrollment: boolean;
}

export interface AdmissionConversionCandidateReview {
  application_id: string;
  application_version: number;
  offer_id: string;
  offer_version: number;
  families: AdmissionConversionFamilyCandidate[];
  children: AdmissionConversionChildCandidate[];
  review_token: string;
  expires_at: string;
}

export type AdmissionConversionResolution =
  | {
      resolution_mode: 'create_family_and_child';
      confirmed_distinct_person: boolean;
      distinct_person_reason: string | null;
    }
  | {
      resolution_mode: 'reuse_family_create_child';
      family_id: string;
      expected_family_version: number;
    }
  | {
      resolution_mode: 'reuse_child';
      family_id: string;
      expected_family_version: number;
      child_id: string;
      expected_child_version: number;
    };

export interface AdmissionWaitlistItem {
  entry_id: string;
  application_id: string;
  application_reference: string;
  status: AdmissionWaitlistStatus;
  version: number;
  facility_id: string;
  program_id: string;
  desired_start_date: string;
  priority_at: string;
  position: number;
}

export interface AdmissionWaitlistPage {
  items: AdmissionWaitlistItem[];
  total: number;
  limit: number;
  offset: number;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const STATUS = new Set<string>(ADMISSION_STATUSES);
const ACTION = new Set<string>(ADMISSION_ACTIONS);
const OFFER_STATUS = new Set(['open', 'accepted', 'declined', 'withdrawn']);
const WAITLIST_STATUS = new Set(['active', 'offered', 'closed']);
const ADMISSION_COMMAND_TARGETS = new Set<AdmissionCommandTargetType>([
  'admission_application',
  'admission_waitlist',
  'admission_offer',
]);
const ADMISSION_RECEIPT_COMMAND_SET = new Set<string>(ADMISSION_RECEIPT_COMMANDS);
const CONVERSION_MATCH_REASONS = new Set<AdmissionConversionMatchReason>([
  'child_name_and_date_of_birth',
  'primary_contact_email',
  'primary_contact_telephone',
]);
const WAITLIST_CLOSURE = new Set([
  'facts_changed', 'review_reopened', 'application_declined', 'application_withdrawn',
  'offer_declined', 'application_accepted',
]);
const TIMELINE_REASON = new Set([
  'create', 'updated', 'submitted', 'review_started', 'facts_changed', 'waitlisted',
  'review_reopened', 'provider_declined', 'family_withdrawn', 'offer_issued',
  'offer_withdrawn', 'offer_declined', 'offer_accepted',
]);

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return value as Record<string, unknown>;
}

function exact(row: Record<string, unknown>, keys: readonly string[], label: string): void {
  const actual = Object.keys(row);
  if (actual.length !== keys.length || actual.some((key) => !keys.includes(key))) {
    throw new ApiError(0, `The server returned unsupported ${label} fields.`);
  }
}

function string(value: unknown, label: string, maximum = 500): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return value;
}

function nullableString(value: unknown, label: string, maximum = 500): string | null {
  return value === null ? null : string(value, label, maximum);
}

function sumDigits(value: string): number {
  return [...value].reduce((count, character) => count + (/\d/.test(character) ? 1 : 0), 0);
}

function id(value: unknown, label: string): string {
  const parsed = string(value, label, 36);
  if (!UUID.test(parsed)) throw new ApiError(0, `The server returned an invalid ${label}.`);
  return parsed;
}

function integer(value: unknown, label: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isInteger(value) || Number(value) < minimum || Number(value) > maximum) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return Number(value);
}

function positiveVersion(value: unknown, label: string): number {
  return integer(value, label, 1);
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new ApiError(0, `The server returned an invalid ${label}.`);
  return value;
}

function calendarDate(value: unknown, label: string): string {
  const parsed = string(value, label, 10);
  if (!DATE.test(parsed) || Number.isNaN(Date.parse(`${parsed}T12:00:00Z`))) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return parsed;
}

function nullableDate(value: unknown, label: string): string | null {
  return value === null ? null : calendarDate(value, label);
}

function timestamp(value: unknown, label: string): string {
  const parsed = string(value, label, 64);
  if (!/^\d{4}-\d{2}-\d{2}T/.test(parsed) || Number.isNaN(Date.parse(parsed))) {
    throw new ApiError(0, `The server returned an invalid ${label}.`);
  }
  return parsed;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value === null ? null : timestamp(value, label);
}

function status(value: unknown, label = 'admission status'): AdmissionStatus {
  if (typeof value === 'string' && STATUS.has(value)) return value as AdmissionStatus;
  throw new ApiError(0, `The server returned an unsupported ${label}.`);
}

function ensureOrganization(organizationId: string): void {
  if (!UUID.test(organizationId) || getSelectedOrganizationId() !== organizationId) {
    throw new ApiError(0, 'The admissions request does not match the selected organization workspace.');
  }
}

function queryId(value: string | undefined, label: string): string | undefined {
  if (value === undefined) return undefined;
  if (!UUID.test(value)) throw new ApiError(0, `Choose a valid ${label}.`);
  return value;
}

function parseCurrentLane(value: unknown): AdmissionListItem['current_lane'] {
  if (value === null) return null;
  const row = object(value, 'admission lane');
  exact(row, ['facility_id', 'program_id'], 'admission lane');
  return { facility_id: id(row.facility_id, 'admission lane facility id'), program_id: id(row.program_id, 'admission lane program id') };
}

export function parseAdmissionListItem(value: unknown): AdmissionListItem {
  const row = object(value, 'admission application summary');
  exact(row, [
    'id', 'reference', 'status', 'version', 'source', 'preference_count',
    'submitted_at', 'updated_at', 'current_lane', 'offer_status',
  ], 'admission application summary');
  const source = string(row.source, 'admission source', 40);
  if (source !== 'administrator_entry') throw new ApiError(0, 'The server returned an unsupported admission source.');
  const offerStatus = nullableString(row.offer_status, 'admission offer status', 20);
  if (offerStatus !== null && !OFFER_STATUS.has(offerStatus)) throw new ApiError(0, 'The server returned an unsupported admission offer status.');
  return {
    id: id(row.id, 'admission application id'),
    reference: string(row.reference, 'admission reference', 80),
    status: status(row.status),
    version: positiveVersion(row.version, 'admission version'),
    source: 'administrator_entry',
    preference_count: integer(row.preference_count, 'admission preference count', 0, 20),
    submitted_at: nullableTimestamp(row.submitted_at, 'admission submission time'),
    updated_at: timestamp(row.updated_at, 'admission update time'),
    current_lane: parseCurrentLane(row.current_lane),
    offer_status: offerStatus as AdmissionOfferStatus | null,
  };
}

export function parseAdmissionWorkspace(value: unknown): AdmissionWorkspace {
  const row = object(value, 'admissions workspace');
  exact(row, ['counts', 'lanes', 'waitlist_lane_count'], 'admissions workspace');
  const countsRow = object(row.counts, 'admissions counts');
  exact(countsRow, ADMISSION_STATUSES, 'admissions counts');
  const counts = Object.fromEntries(ADMISSION_STATUSES.map((item) => [
    item, integer(countsRow[item], `${item} admission count`),
  ])) as Record<AdmissionStatus, number>;
  if (!Array.isArray(row.lanes)) throw new ApiError(0, 'The server returned invalid admissions lanes.');
  const seen = new Set<AdmissionStatus>();
  const lanes = row.lanes.map((value) => {
    const lane = object(value, 'admissions lane');
    exact(lane, ['status', 'count', 'applications'], 'admissions lane');
    const laneStatus = status(lane.status, 'admissions lane status');
    if (seen.has(laneStatus)) throw new ApiError(0, 'The server returned duplicate admissions lanes.');
    seen.add(laneStatus);
    if (!Array.isArray(lane.applications)) throw new ApiError(0, 'The server returned invalid admissions lane applications.');
    const applications = lane.applications.map(parseAdmissionListItem);
    const laneCount = integer(lane.count, 'admissions lane count');
    if (applications.some((item) => item.status !== laneStatus) || counts[laneStatus] !== laneCount || applications.length > laneCount) {
      throw new ApiError(0, 'The admissions lane did not reconcile with its canonical count.');
    }
    return { status: laneStatus, count: laneCount, applications };
  });
  if (seen.size !== ADMISSION_STATUSES.length) throw new ApiError(0, 'The server omitted a canonical admissions lane.');
  return {
    counts,
    lanes,
    waitlist_lane_count: integer(row.waitlist_lane_count, 'waitlist lane count'),
  };
}

function parseChild(value: unknown): AdmissionChildInput {
  const row = object(value, 'admission child');
  exact(row, ['first_name', 'last_name', 'date_of_birth'], 'admission child');
  return {
    first_name: string(row.first_name, 'child first name', 100),
    last_name: string(row.last_name, 'child last name', 100),
    date_of_birth: calendarDate(row.date_of_birth, 'child date of birth'),
  };
}

function parseContact(value: unknown): AdmissionContactInput {
  const row = object(value, 'admission contact');
  exact(row, ['first_name', 'last_name', 'relationship', 'email', 'telephone'], 'admission contact');
  const email = nullableString(row.email, 'admission contact email', 320);
  if (email !== null && !EMAIL.test(email)) throw new ApiError(0, 'The server returned an invalid admission contact email.');
  return {
    first_name: string(row.first_name, 'contact first name', 100),
    last_name: string(row.last_name, 'contact last name', 100),
    relationship: string(row.relationship, 'contact relationship', 100),
    email,
    telephone: (() => {
      const telephone = nullableString(row.telephone, 'admission contact telephone', 30);
      if (telephone !== null && sumDigits(telephone) < 7) {
        throw new ApiError(0, 'The server returned an invalid admission contact telephone.');
      }
      return telephone;
    })(),
  };
}

function parsePreference(value: unknown): AdmissionPreference {
  const row = object(value, 'admission preference');
  exact(row, [
    'id', 'rank', 'facility_id', 'facility_name', 'program_id', 'program_name',
    'requested_start_date', 'application_version',
  ], 'admission preference');
  return {
    id: id(row.id, 'admission preference id'),
    rank: integer(row.rank, 'admission preference rank', 1, 20),
    facility_id: id(row.facility_id, 'admission preference facility id'),
    facility_name: string(row.facility_name, 'admission preference facility name', 255),
    program_id: id(row.program_id, 'admission preference program id'),
    program_name: string(row.program_name, 'admission preference program name', 255),
    requested_start_date: calendarDate(row.requested_start_date, 'admission requested start date'),
    application_version: positiveVersion(row.application_version, 'admission preference application version'),
  };
}

function parseWaitlist(value: unknown): AdmissionWaitlist | null {
  if (value === null) return null;
  const row = object(value, 'admission waitlist entry');
  exact(row, [
    'id', 'status', 'version', 'facility_id', 'facility_name', 'program_id', 'program_name',
    'requested_start_date', 'priority_at', 'position', 'closure_reason', 'created_at',
    'updated_at', 'closed_at',
  ], 'admission waitlist entry');
  const itemStatus = string(row.status, 'waitlist status', 20);
  if (!WAITLIST_STATUS.has(itemStatus)) throw new ApiError(0, 'The server returned an unsupported waitlist status.');
  const position = row.position === null ? null : integer(row.position, 'waitlist position', 1);
  if ((itemStatus === 'closed') !== (position === null)) {
    throw new ApiError(0, 'The server returned an incoherent waitlist position.');
  }
  const closureReason = nullableString(row.closure_reason, 'waitlist closure reason', 40);
  if (closureReason !== null && !WAITLIST_CLOSURE.has(closureReason)) throw new ApiError(0, 'The server returned an unsupported waitlist closure reason.');
  return {
    id: id(row.id, 'waitlist id'),
    status: itemStatus as AdmissionWaitlistStatus,
    version: positiveVersion(row.version, 'waitlist version'),
    facility_id: id(row.facility_id, 'waitlist facility id'),
    facility_name: string(row.facility_name, 'waitlist facility name', 255),
    program_id: id(row.program_id, 'waitlist program id'),
    program_name: string(row.program_name, 'waitlist program name', 255),
    requested_start_date: calendarDate(row.requested_start_date, 'waitlist requested start date'),
    priority_at: timestamp(row.priority_at, 'waitlist priority time'),
    position,
    closure_reason: closureReason as AdmissionWaitlist['closure_reason'],
    created_at: timestamp(row.created_at, 'waitlist creation time'),
    updated_at: timestamp(row.updated_at, 'waitlist update time'),
    closed_at: nullableTimestamp(row.closed_at, 'waitlist closure time'),
  };
}

function parseOffer(value: unknown): AdmissionOffer | null {
  if (value === null) return null;
  const row = object(value, 'admission offer');
  exact(row, [
    'id', 'status', 'version', 'facility_id', 'facility_name', 'program_id', 'program_name',
    'proposed_start_date', 'respond_by_date', 'prior_application_status', 'issued_at',
    'withdrawn_at', 'declined_at', 'accepted_at',
  ], 'admission offer');
  const offerStatus = string(row.status, 'admission offer status', 20);
  if (!OFFER_STATUS.has(offerStatus)) throw new ApiError(0, 'The server returned an unsupported admission offer status.');
  const prior = string(row.prior_application_status, 'offer prior application status', 20);
  if (prior !== 'under_review' && prior !== 'waitlisted') throw new ApiError(0, 'The server returned an unsupported offer origin.');
  return {
    id: id(row.id, 'admission offer id'),
    status: offerStatus as AdmissionOfferStatus,
    version: positiveVersion(row.version, 'admission offer version'),
    facility_id: id(row.facility_id, 'admission offer facility id'),
    facility_name: string(row.facility_name, 'admission offer facility name', 255),
    program_id: id(row.program_id, 'admission offer program id'),
    program_name: string(row.program_name, 'admission offer program name', 255),
    proposed_start_date: calendarDate(row.proposed_start_date, 'offer proposed start date'),
    respond_by_date: nullableDate(row.respond_by_date, 'offer response date'),
    prior_application_status: prior,
    issued_at: timestamp(row.issued_at, 'offer issue time'),
    withdrawn_at: nullableTimestamp(row.withdrawn_at, 'offer withdrawal time'),
    declined_at: nullableTimestamp(row.declined_at, 'offer decline time'),
    accepted_at: nullableTimestamp(row.accepted_at, 'offer acceptance time'),
  };
}

function parseConversion(value: unknown): AdmissionConversion | null {
  if (value === null) return null;
  const row = object(value, 'admission conversion');
  exact(row, ['id', 'resolution_mode', 'family_id', 'child_id', 'enrollment_id', 'converted_at'], 'admission conversion');
  const mode = string(row.resolution_mode, 'conversion resolution mode', 40);
  if (!['create_family_and_child', 'reuse_family_create_child', 'reuse_child'].includes(mode)) {
    throw new ApiError(0, 'The server returned an unsupported admission conversion mode.');
  }
  return {
    id: id(row.id, 'conversion id'),
    resolution_mode: mode as AdmissionConversion['resolution_mode'],
    family_id: id(row.family_id, 'conversion family id'),
    child_id: id(row.child_id, 'conversion child id'),
    enrollment_id: id(row.enrollment_id, 'conversion enrollment id'),
    converted_at: timestamp(row.converted_at, 'conversion time'),
  };
}

function parseReplayReceipt(value: unknown): AdmissionReplayReceipt | null {
  if (value === null) return null;
  const row = object(value, 'admission replay receipt');
  exact(row, ['command_type', 'target_type', 'target_id', 'committed_version'], 'admission replay receipt');
  const targetType = string(row.target_type, 'admission receipt target type', 40);
  if (!ADMISSION_COMMAND_TARGETS.has(targetType as AdmissionCommandTargetType)) {
    throw new ApiError(0, 'The server returned an unsupported admission receipt target type.');
  }
  const commandType = string(row.command_type, 'admission receipt command type', 80);
  if (!ADMISSION_RECEIPT_COMMAND_SET.has(commandType)) {
    throw new ApiError(0, 'The server returned an unsupported admission receipt command.');
  }
  const expectedTargetType: AdmissionCommandTargetType = commandType.startsWith('admission.application.')
    ? 'admission_application'
    : commandType.startsWith('admission.waitlist.')
      ? 'admission_waitlist'
      : 'admission_offer';
  if (targetType !== expectedTargetType) {
    throw new ApiError(0, 'The admission replay receipt command did not match its target type.');
  }
  return {
    command_type: commandType as AdmissionReceiptCommand,
    target_type: targetType as AdmissionCommandTargetType,
    target_id: id(row.target_id, 'admission receipt target id'),
    committed_version: positiveVersion(row.committed_version, 'admission receipt committed version'),
  };
}

function parseTimeline(value: unknown): AdmissionTimelineItem {
  const row = object(value, 'admission timeline event');
  exact(row, [
    'id', 'application_version', 'command', 'from_status', 'to_status', 'reason_code',
    'actor_user_id', 'client_operation_id', 'occurred_at',
  ], 'admission timeline event');
  const reason = nullableString(row.reason_code, 'admission event reason', 40);
  if (reason !== null && !TIMELINE_REASON.has(reason)) throw new ApiError(0, 'The server returned an unsupported admission event reason.');
  return {
    id: id(row.id, 'admission event id'),
    application_version: positiveVersion(row.application_version, 'admission event application version'),
    command: string(row.command, 'admission event command', 80),
    from_status: row.from_status === null ? null : status(row.from_status, 'admission event prior status'),
    to_status: status(row.to_status, 'admission event status'),
    reason_code: reason as AdmissionTimelineItem['reason_code'],
    actor_user_id: id(row.actor_user_id, 'admission event actor id'),
    client_operation_id: id(row.client_operation_id, 'admission event operation id'),
    occurred_at: timestamp(row.occurred_at, 'admission event time'),
  };
}

export function parseAdmissionDetail(value: unknown, organizationId: string, expectedId?: string): AdmissionDetail {
  ensureOrganization(organizationId);
  const row = object(value, 'admission application');
  exact(row, [
    'id', 'organization_id', 'reference', 'source', 'status', 'version', 'child', 'contact',
    'internal_note', 'preferences', 'waitlist', 'offer', 'conversion', 'timeline', 'timeline_total',
    'allowed_actions', 'committed_versions', 'replayed', 'created_at', 'updated_at',
    'replay_receipt', 'submitted_at', 'review_started_at', 'terminal_at',
  ], 'admission application');
  const applicationId = id(row.id, 'admission application id');
  if (expectedId && applicationId !== expectedId) throw new ApiError(0, 'The admission response did not match the requested application.');
  if (id(row.organization_id, 'admission organization id') !== organizationId) throw new ApiError(403, 'The admission response crossed the selected organization boundary.');
  if (row.source !== 'administrator_entry') throw new ApiError(0, 'The server returned an unsupported admission source.');
  if (!Array.isArray(row.preferences) || !Array.isArray(row.timeline) || !Array.isArray(row.allowed_actions)) {
    throw new ApiError(0, 'The server returned incomplete admission application collections.');
  }
  const applicationStatus = status(row.status);
  const version = positiveVersion(row.version, 'admission version');
  const preferences = row.preferences.map(parsePreference);
  const waitlist = parseWaitlist(row.waitlist);
  const offer = parseOffer(row.offer);
  const timeline = row.timeline.map(parseTimeline);
  const timelineTotal = integer(row.timeline_total, 'admission timeline total');
  if (timeline.length !== Math.min(timelineTotal, 200)) {
    throw new ApiError(0, 'The admission timeline did not reconcile with its bounded total.');
  }
  if (
    new Set(timeline.map((event) => event.id)).size !== timeline.length
    || timeline.some((event, index) => (
      index > 0 && event.application_version <= timeline[index - 1].application_version
    ))
  ) {
    throw new ApiError(0, 'The admission timeline ordering was invalid.');
  }
  const allowedActions = row.allowed_actions.map((value) => {
    if (typeof value !== 'string' || !ACTION.has(value)) throw new ApiError(0, 'The server returned an unsupported admission action.');
    return value as AdmissionActionName;
  });
  if (new Set(allowedActions).size !== allowedActions.length) throw new ApiError(0, 'The server returned duplicate admission actions.');
  const committed = object(row.committed_versions, 'admission committed versions');
  exact(committed, ['application', 'waitlist', 'offer'], 'admission committed versions');
  const committedVersions = {
    application: positiveVersion(committed.application, 'committed application version'),
    waitlist: committed.waitlist === null ? null : positiveVersion(committed.waitlist, 'committed waitlist version'),
    offer: committed.offer === null ? null : positiveVersion(committed.offer, 'committed offer version'),
  };
  if (
    committedVersions.application !== version
    || committedVersions.waitlist !== (waitlist?.version ?? null)
    || committedVersions.offer !== (offer?.version ?? null)
    || preferences.some((preference) => preference.application_version > version)
    || timeline.some((event) => event.application_version > version)
  ) throw new ApiError(0, 'The admission response versions did not reconcile.');
  const replayed = boolean(row.replayed, 'admission replay marker');
  const replayReceipt = parseReplayReceipt(row.replay_receipt);
  if (replayed !== Boolean(replayReceipt)) {
    throw new ApiError(0, 'The admission replay marker did not reconcile with its receipt.');
  }
  // A replay receipt is immutable evidence for the original command. The
  // application projection may legitimately have advanced, and a later
  // waitlist/offer may have superseded the historical nested target. Keep the
  // receipt strict, but never pretend it describes the latest nested record.
  if (
    replayReceipt?.target_type === 'admission_application'
    && (
      replayReceipt.target_id !== applicationId
      || replayReceipt.committed_version > version
    )
  ) {
    throw new ApiError(0, 'The admission replay receipt did not match its owning application history.');
  }
  return {
    id: applicationId,
    organization_id: organizationId,
    reference: string(row.reference, 'admission reference', 80),
    source: 'administrator_entry',
    status: applicationStatus,
    version,
    child: parseChild(row.child),
    contact: parseContact(row.contact),
    internal_note: nullableString(row.internal_note, 'admission internal note', 2_000),
    preferences,
    waitlist,
    offer,
    conversion: parseConversion(row.conversion),
    timeline,
    timeline_total: timelineTotal,
    allowed_actions: allowedActions,
    committed_versions: committedVersions,
    replayed,
    replay_receipt: replayReceipt,
    created_at: timestamp(row.created_at, 'admission creation time'),
    updated_at: timestamp(row.updated_at, 'admission update time'),
    submitted_at: nullableTimestamp(row.submitted_at, 'admission submission time'),
    review_started_at: nullableTimestamp(row.review_started_at, 'admission review time'),
    terminal_at: nullableTimestamp(row.terminal_at, 'admission terminal time'),
  };
}

export function parseAdmissionLaneDirectory(value: unknown): AdmissionLaneDirectory {
  const row = object(value, 'admission lane directory');
  exact(row, ['facilities'], 'admission lane directory');
  if (!Array.isArray(row.facilities)) throw new ApiError(0, 'The server returned invalid admission facilities.');
  const seenFacilities = new Set<string>();
  const facilities = row.facilities.map((value) => {
    const facility = object(value, 'admission lane facility');
    exact(facility, ['id', 'name', 'programs'], 'admission lane facility');
    const facilityId = id(facility.id, 'admission lane facility id');
    if (seenFacilities.has(facilityId)) throw new ApiError(0, 'The server returned duplicate admission facilities.');
    seenFacilities.add(facilityId);
    if (!Array.isArray(facility.programs)) throw new ApiError(0, 'The server returned invalid admission lane programs.');
    const seenPrograms = new Set<string>();
    const programs = facility.programs.map((value) => {
      const program = object(value, 'admission lane program');
      exact(program, ['id', 'name', 'program_type'], 'admission lane program');
      const programId = id(program.id, 'admission lane program id');
      if (seenPrograms.has(programId)) throw new ApiError(0, 'The server returned duplicate admission lane programs.');
      seenPrograms.add(programId);
      const programType = string(program.program_type, 'admission lane program type', 40);
      if (programType !== 'daycare' && programType !== 'out_of_school_care') {
        throw new ApiError(0, 'The server returned an unsupported admission lane program type.');
      }
      return {
        id: programId,
        name: string(program.name, 'admission lane program name', 255),
        program_type: programType as AdmissionLaneProgram['program_type'],
      };
    });
    if (!programs.length) throw new ApiError(0, 'The server returned an admission facility without an active program.');
    return {
      id: facilityId,
      name: string(facility.name, 'admission lane facility name', 255),
      programs,
    };
  });
  return { facilities };
}

function parseMatchReasons(value: unknown): AdmissionConversionMatchReason[] {
  if (!Array.isArray(value)) throw new ApiError(0, 'The server returned invalid admission match reasons.');
  const reasons = value.map((reason) => {
    if (typeof reason !== 'string' || !CONVERSION_MATCH_REASONS.has(reason as AdmissionConversionMatchReason)) {
      throw new ApiError(0, 'The server returned an unsupported admission match reason.');
    }
    return reason as AdmissionConversionMatchReason;
  });
  if (new Set(reasons).size !== reasons.length) throw new ApiError(0, 'The server returned duplicate admission match reasons.');
  return reasons;
}

export function parseAdmissionConversionCandidates(
  value: unknown,
  organizationId: string,
  application: AdmissionDetail,
): AdmissionConversionCandidateReview {
  ensureOrganization(organizationId);
  const row = object(value, 'admission conversion review');
  exact(row, [
    'application_id', 'application_version', 'offer_id', 'offer_version',
    'families', 'children', 'review_token', 'expires_at',
  ], 'admission conversion review');
  if (!application.offer) throw new ApiError(0, 'The application has no open offer to review.');
  if (
    id(row.application_id, 'conversion application id') !== application.id
    || positiveVersion(row.application_version, 'conversion application version') !== application.version
    || id(row.offer_id, 'conversion offer id') !== application.offer.id
    || positiveVersion(row.offer_version, 'conversion offer version') !== application.offer.version
  ) {
    throw new ApiError(0, 'The conversion review did not match the current application and offer versions.');
  }
  if (!Array.isArray(row.families) || !Array.isArray(row.children)) {
    throw new ApiError(0, 'The server returned incomplete conversion candidates.');
  }
  const families = row.families.map((value) => {
    const candidate = object(value, 'conversion family candidate');
    exact(candidate, ['id', 'display_label', 'version', 'status', 'match_reasons'], 'conversion family candidate');
    const status = string(candidate.status, 'conversion family status', 20);
    if (!['pending', 'active', 'inactive', 'archived'].includes(status)) {
      throw new ApiError(0, 'The server returned an unsupported conversion family status.');
    }
    return {
      id: id(candidate.id, 'conversion family id'),
      display_label: string(candidate.display_label, 'conversion family label', 255),
      version: positiveVersion(candidate.version, 'conversion family version'),
      status: status as AdmissionConversionFamilyCandidate['status'],
      match_reasons: parseMatchReasons(candidate.match_reasons),
    };
  });
  const familyIds = new Set(families.map((candidate) => candidate.id));
  if (familyIds.size !== families.length) throw new ApiError(0, 'The server returned duplicate conversion families.');
  const children = row.children.map((value) => {
    const candidate = object(value, 'conversion child candidate');
    exact(candidate, [
      'id', 'family_id', 'display_label', 'version', 'is_active',
      'match_reasons', 'has_open_enrollment',
    ], 'conversion child candidate');
    const familyId = id(candidate.family_id, 'conversion child family id');
    if (!familyIds.has(familyId)) throw new ApiError(0, 'The conversion child candidate referenced an unavailable family.');
    return {
      id: id(candidate.id, 'conversion child id'),
      family_id: familyId,
      display_label: string(candidate.display_label, 'conversion child label', 255),
      version: positiveVersion(candidate.version, 'conversion child version'),
      is_active: boolean(candidate.is_active, 'conversion child active state'),
      match_reasons: parseMatchReasons(candidate.match_reasons),
      has_open_enrollment: boolean(candidate.has_open_enrollment, 'conversion child enrollment state'),
    };
  });
  if (new Set(children.map((candidate) => candidate.id)).size !== children.length) {
    throw new ApiError(0, 'The server returned duplicate conversion children.');
  }
  return {
    application_id: application.id,
    application_version: application.version,
    offer_id: application.offer.id,
    offer_version: application.offer.version,
    families,
    children,
    review_token: string(row.review_token, 'conversion review token', 4_096),
    expires_at: timestamp(row.expires_at, 'conversion review expiry'),
  };
}

export function parseAdmissionApplicationsPage(value: unknown): AdmissionApplicationsPage {
  const row = object(value, 'admission applications page');
  exact(row, ['items', 'total', 'limit', 'offset'], 'admission applications page');
  if (!Array.isArray(row.items)) throw new ApiError(0, 'The server returned an invalid admission applications page.');
  const items = row.items.map(parseAdmissionListItem);
  const total = integer(row.total, 'admission application total');
  const limit = integer(row.limit, 'admission application page size', 1, 200);
  const offset = integer(row.offset, 'admission application offset');
  if (
    items.length > limit
    || (items.length > 0 && offset + items.length > total)
    || (items.length === 0 && offset < total)
  ) throw new ApiError(0, 'The admission application page did not reconcile.');
  return { items, total, limit, offset };
}

export function parseAdmissionWaitlistPage(value: unknown): AdmissionWaitlistPage {
  const row = object(value, 'admission waitlist page');
  exact(row, ['items', 'total', 'limit', 'offset'], 'admission waitlist page');
  if (!Array.isArray(row.items)) throw new ApiError(0, 'The server returned an invalid admission waitlist page.');
  const items = row.items.map((value) => {
    const item = object(value, 'admission waitlist row');
    exact(item, [
      'entry_id', 'application_id', 'application_reference', 'status', 'version',
      'facility_id', 'program_id', 'desired_start_date', 'priority_at', 'position',
    ], 'admission waitlist row');
    const itemStatus = string(item.status, 'waitlist row status', 20);
    if (!WAITLIST_STATUS.has(itemStatus)) throw new ApiError(0, 'The server returned an unsupported waitlist row status.');
    return {
      entry_id: id(item.entry_id, 'waitlist row id'),
      application_id: id(item.application_id, 'waitlist application id'),
      application_reference: string(item.application_reference, 'waitlist application reference', 80),
      status: itemStatus as AdmissionWaitlistStatus,
      version: positiveVersion(item.version, 'waitlist row version'),
      facility_id: id(item.facility_id, 'waitlist row facility id'),
      program_id: id(item.program_id, 'waitlist row program id'),
      desired_start_date: calendarDate(item.desired_start_date, 'waitlist desired start date'),
      priority_at: timestamp(item.priority_at, 'waitlist priority time'),
      position: integer(item.position, 'waitlist position', 1),
    };
  });
  const total = integer(row.total, 'waitlist total');
  const limit = integer(row.limit, 'waitlist page size', 1, 200);
  const offset = integer(row.offset, 'waitlist offset');
  if (
    items.length > limit
    || (items.length > 0 && offset + items.length > total)
    || (items.length === 0 && offset < total)
  ) throw new ApiError(0, 'The admission waitlist page did not reconcile.');
  return { items, total, limit, offset };
}

function applicationPath(applicationId: string): string {
  if (!UUID.test(applicationId)) throw new ApiError(0, 'Choose a valid admission application.');
  return `/admissions/applications/${encodeURIComponent(applicationId)}`;
}

function commandBody(operationId: string, expectedVersion: number, reasonCode?: string): string {
  if (!UUID.test(operationId)) throw new ApiError(0, 'The admission command requires a valid operation id.');
  return JSON.stringify({
    client_operation_id: operationId,
    expected_application_version: positiveVersion(expectedVersion, 'expected admission version'),
    ...(reasonCode?.trim() ? { reason_code: reasonCode.trim() } : {}),
  });
}

async function detailRequest(
  organizationId: string,
  applicationId: string,
  path: string,
  options: RequestInit,
): Promise<AdmissionDetail> {
  ensureOrganization(organizationId);
  return parseAdmissionDetail(await apiRequest<unknown>(path, options), organizationId, applicationId);
}

export async function fetchAdmissionWorkspace(organizationId: string, signal?: AbortSignal): Promise<AdmissionWorkspace> {
  ensureOrganization(organizationId);
  return parseAdmissionWorkspace(await apiRequest<unknown>('/admissions/workspace', { signal }));
}

export async function fetchAdmissionApplications(
  organizationId: string,
  query: { status?: AdmissionStatus; search?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<AdmissionApplicationsPage> {
  ensureOrganization(organizationId);
  const limit = query.limit ?? 50;
  const offset = query.offset ?? 0;
  integer(limit, 'admission application page size', 1, 200);
  integer(offset, 'admission application offset');
  if (query.status && !STATUS.has(query.status)) throw new ApiError(0, 'Choose a valid admission status.');
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.status) params.set('status', query.status);
  const search = query.search?.trim() ?? '';
  if (search && !/^[A-Za-z0-9-]{1,16}$/.test(search)) {
    throw new ApiError(0, 'Search with 1–16 letters, numbers, or hyphens from the application reference.');
  }
  if (search) params.set('search', search);
  return parseAdmissionApplicationsPage(await apiRequest<unknown>(`/admissions/applications?${params}`, { signal }));
}

export async function fetchAdmissionLaneDirectory(
  organizationId: string,
  signal?: AbortSignal,
): Promise<AdmissionLaneDirectory> {
  ensureOrganization(organizationId);
  return parseAdmissionLaneDirectory(await apiRequest<unknown>('/admissions/lane-directory', { signal, cache: 'no-store' }));
}

export async function fetchAdmissionApplication(
  organizationId: string,
  applicationId: string,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, applicationId, applicationPath(applicationId), { signal, cache: 'no-store' });
}

export async function fetchAdmissionWaitlist(
  organizationId: string,
  query: { facilityId?: string; programId?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<AdmissionWaitlistPage> {
  ensureOrganization(organizationId);
  const limit = query.limit ?? 100;
  const offset = query.offset ?? 0;
  integer(limit, 'waitlist page size', 1, 200);
  integer(offset, 'waitlist offset');
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const facilityId = queryId(query.facilityId, 'waitlist facility');
  const programId = queryId(query.programId, 'waitlist program');
  if (facilityId) params.set('facility_id', facilityId);
  if (programId) params.set('program_id', programId);
  return parseAdmissionWaitlistPage(await apiRequest<unknown>(`/admissions/waitlist?${params}`, { signal }));
}

export async function createAdmissionApplication(
  organizationId: string,
  operationId: string,
  input: AdmissionCreateInput,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  ensureOrganization(organizationId);
  if (!UUID.test(operationId)) throw new ApiError(0, 'The admission command requires a valid operation id.');
  const payload = {
    client_operation_id: operationId,
    child: input.child,
    primary_contact: input.primary_contact,
    preferences: input.preferences,
    ...(input.internal_note?.trim() ? { internal_note: input.internal_note.trim() } : {}),
  };
  const raw = await apiRequest<unknown>('/admissions/applications', { method: 'POST', body: JSON.stringify(payload), signal });
  const candidate = object(raw, 'created admission application');
  const applicationId = id(candidate.id, 'created admission application id');
  return parseAdmissionDetail(raw, organizationId, applicationId);
}

export async function updateAdmissionApplication(
  organizationId: string,
  application: AdmissionDetail,
  operationId: string,
  input: AdmissionCreateInput,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/update`, {
    method: 'POST',
    body: JSON.stringify({
      client_operation_id: operationId,
      expected_application_version: application.version,
      child: input.child,
      primary_contact: input.primary_contact,
      preferences: input.preferences,
      internal_note: input.internal_note,
    }),
    signal,
  });
}

export async function correctAdmissionApplication(
  organizationId: string,
  application: AdmissionDetail,
  operationId: string,
  input: AdmissionCreateInput,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/correct`, {
    method: 'POST',
    body: JSON.stringify({
      client_operation_id: operationId,
      expected_application_version: application.version,
      child: input.child,
      primary_contact: input.primary_contact,
      preferences: input.preferences,
      internal_note: input.internal_note,
    }),
    signal,
  });
}

export async function runAdmissionCommand(
  organizationId: string,
  application: AdmissionDetail,
  command: 'submit' | 'review/start' | 'decline' | 'withdraw',
  operationId: string,
  reasonCode?: string,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/${command}`, {
    method: 'POST',
    body: commandBody(operationId, application.version, reasonCode),
    signal,
  });
}

export async function waitlistAdmissionApplication(
  organizationId: string,
  application: AdmissionDetail,
  operationId: string,
  input: { facility_id: string; program_id: string; desired_start_date: string },
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/waitlist`, {
    method: 'POST',
    body: JSON.stringify({
      client_operation_id: operationId,
      expected_application_version: application.version,
      ...input,
    }),
    signal,
  });
}

export async function reopenAdmissionReview(
  organizationId: string,
  application: AdmissionDetail,
  operationId: string,
  reasonCode?: string,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  if (!application.waitlist) throw new ApiError(0, 'This application does not have a waitlist version to reopen.');
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/waitlist/reopen-review`, {
    method: 'POST',
    body: JSON.stringify({
      client_operation_id: operationId,
      expected_application_version: application.version,
      expected_waitlist_version: application.waitlist.version,
      ...(reasonCode?.trim() ? { reason_code: reasonCode.trim() } : {}),
    }),
    signal,
  });
}

export async function createAdmissionOffer(
  organizationId: string,
  application: AdmissionDetail,
  operationId: string,
  input: { facility_id: string; program_id: string; proposed_start_date: string; respond_by_date: string | null },
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  return detailRequest(organizationId, application.id, `${applicationPath(application.id)}/offers`, {
    method: 'POST',
    body: JSON.stringify({
      client_operation_id: operationId,
      expected_application_version: application.version,
      ...(application.status === 'waitlisted' && application.waitlist
        ? { expected_waitlist_version: application.waitlist.version }
        : {}),
      ...input,
    }),
    signal,
  });
}

export async function fetchAdmissionConversionCandidates(
  organizationId: string,
  application: AdmissionDetail,
  signal?: AbortSignal,
): Promise<AdmissionConversionCandidateReview> {
  return parseAdmissionConversionCandidates(
    await apiRequest<unknown>(`${applicationPath(application.id)}/conversion-candidates`, {
      signal,
      cache: 'no-store',
    }),
    organizationId,
    application,
  );
}

export async function acceptAdmissionOffer(
  organizationId: string,
  application: AdmissionDetail,
  review: AdmissionConversionCandidateReview,
  operationId: string,
  resolution: AdmissionConversionResolution,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  if (!application.offer || application.offer.status !== 'open') {
    throw new ApiError(0, 'This application no longer has an open offer.');
  }
  if (
    review.application_id !== application.id
    || review.application_version !== application.version
    || review.offer_id !== application.offer.id
    || review.offer_version !== application.offer.version
  ) {
    throw new ApiError(0, 'Refresh the duplicate review before accepting this offer.');
  }
  return detailRequest(
    organizationId,
    application.id,
    `${applicationPath(application.id)}/offers/${encodeURIComponent(application.offer.id)}/accept`,
    {
      method: 'POST',
      body: JSON.stringify({
        client_operation_id: operationId,
        expected_application_version: application.version,
        expected_offer_version: application.offer.version,
        review_token: review.review_token,
        ...resolution,
      }),
      signal,
    },
  );
}

export async function runAdmissionOfferCommand(
  organizationId: string,
  application: AdmissionDetail,
  command: 'withdraw' | 'decline',
  operationId: string,
  reasonCode?: string,
  signal?: AbortSignal,
): Promise<AdmissionDetail> {
  if (!application.offer) throw new ApiError(0, 'This application does not have an offer to update.');
  return detailRequest(
    organizationId,
    application.id,
    `${applicationPath(application.id)}/offers/${encodeURIComponent(application.offer.id)}/${command}`,
    {
      method: 'POST',
      body: JSON.stringify({
        client_operation_id: operationId,
        expected_application_version: application.version,
        expected_offer_version: application.offer.version,
        ...(reasonCode?.trim() ? { reason_code: reasonCode.trim() } : {}),
      }),
      signal,
    },
  );
}
