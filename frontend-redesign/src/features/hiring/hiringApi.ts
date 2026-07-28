import { apiRequest } from "../../api/client";

export type ListingStatus = "draft" | "open" | "paused" | "closed";
export type CandidateStage =
  | "invited"
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn"
  | "hired";
export type EvidenceProvenance = "manual" | "local_ocr";
export type ScreeningSchemaVersion = "0030" | null;
export type CandidatePathway =
  | "educator"
  | "student_educator"
  | "driver"
  | "educator_driver";
export type PositionShape = "educator_only" | "driver_only" | "educator_driver";
export type DrivingRequirement = "not_applicable" | "preferred" | "required";
export type VehicleExpectation =
  | "none"
  | "organization_vehicle"
  | "personal_vehicle"
  | "either";
export type ServiceWeekday =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday"
  | "saturday"
  | "sunday";
export interface AtsServiceWindow {
  days: ServiceWeekday[];
  start_time: string;
  end_time: string;
  timezone: string;
}
export interface StructuredRoleTerms {
  position_shape: PositionShape;
  driving_requirement: DrivingRequirement;
  vehicle_expectation: VehicleExpectation;
  required_licence_jurisdiction: string | null;
  required_licence_jurisdiction_other: string | null;
  required_licence_class: string | null;
  minimum_driving_experience_months: number;
  service_area: string | null;
  service_windows: AtsServiceWindow[];
  mileage_policy: string | null;
  driving_time_paid: boolean;
  screening_conditions: string[];
}
export interface CandidateDriverDeclaration {
  willing_to_drive: boolean;
  licence_jurisdiction: string | null;
  licence_jurisdiction_other: string | null;
  licence_class: string | null;
  vehicle_access:
    | "none"
    | "organization_vehicle_only"
    | "personal_vehicle"
    | "either";
  preferred_service_radius_km: number | null;
  candidate_provided: true;
}
export interface JobListing {
  id: string;
  organization_id: string;
  facility_id: string | null;
  title: string;
  location: string;
  employment_type: string;
  status: ListingStatus;
  summary: string;
  requirements: string[];
  openings: number;
  applicant_count: number;
  version: number;
  created_at: string;
  updated_at: string;
  structured_terms: StructuredRoleTerms;
}
export interface WorkHistoryItem {
  employer: string;
  [key: string]: unknown;
}
export interface Candidate {
  id: string;
  organization_id: string;
  listing_id: string;
  candidate_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  notes: string | null;
  profile_status: "prospect" | "active" | "withdrawn" | "archived";
  onboarding_status: "not_started" | "in_progress" | "submitted" | "complete";
  candidate_type: "certified_educator" | "student" | null;
  pathway: CandidatePathway | null;
  driver_declaration: CandidateDriverDeclaration | null;
  institution: string | null;
  program: string | null;
  expected_graduation_date: string | null;
  certification_type: string | null;
  certification_number: string | null;
  certification_expiry_date: string | null;
  certification_verification_status:
    "unverified" | "pending" | "verified" | "rejected";
  certification_verified_at: string | null;
  certification_review_note: string | null;
  certification_provenance: EvidenceProvenance | null;
  certification_candidate_confirmed_at: string | null;
  work_history: WorkHistoryItem[];
  work_history_provenance: EvidenceProvenance | null;
  work_history_candidate_confirmed_at: string | null;
  source:
    "private_invitation" | "marketplace_application" | "employer_interest";
  candidate_consent_status: "requested" | "accepted" | "declined";
  stage: CandidateStage;
  version: number;
  updated_at: string;
}
export interface OfferVersion {
  id: string;
  organization_id: string;
  application_id: string;
  client_operation_id: string | null;
  version: number;
  status:
    "draft" | "sent" | "accepted" | "declined" | "withdrawn" | "superseded";
  position_title: string;
  compensation: string | null;
  start_date: string | null;
  notes: string;
  expires_at: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  terminal_at: string | null;
  created_at: string;
  updated_at: string;
  terms_digest: string | null;
  structured_terms: StructuredRoleTerms;
}
export interface CandidateOffer {
  candidate_id: string;
  versions: OfferVersion[];
}
export interface InterviewRecord {
  id: string;
  organization_id: string;
  application_id: string;
  scheduled_at: string;
  timezone: string;
  location_or_link: string;
  status:
    | "requested"
    | "confirmed"
    | "declined"
    | "cancelled"
    | "candidate_proposed"
    | "proposal_declined";
  candidate_proposed_at: string | null;
  candidate_proposal_note: string | null;
  created_at: string;
  updated_at: string;
}
export interface HiringWorkspace {
  organization_id: string;
  generated_at: string;
  screening_schema_version: ScreeningSchemaVersion;
  listings: JobListing[];
  candidates: Candidate[];
  offers: CandidateOffer[];
  interviews: InterviewRecord[];
}
export interface ListingInput {
  title: string;
  description: string;
  employment_type: string;
  facility_id?: string | null;
  location?: string | null;
  requirements: string[];
  position_shape?: PositionShape;
  driving_requirement?: DrivingRequirement;
  vehicle_expectation?: VehicleExpectation;
  required_licence_class?: string | null;
  required_licence_jurisdiction?: string | null;
  required_licence_jurisdiction_other?: string | null;
  minimum_driving_experience_months?: number;
  service_area?: string | null;
  service_windows?: AtsServiceWindow[];
  mileage_policy?: string | null;
  driving_time_paid?: boolean;
  screening_conditions?: string[];
}
export interface OfferInput {
  position_title: string;
  compensation?: string;
  start_date?: string;
  terms: string;
  expires_at?: string;
  expected_application_version: number;
  position_shape?: PositionShape;
  driving_requirement?: DrivingRequirement;
  vehicle_expectation?: VehicleExpectation;
  required_licence_class?: string | null;
  required_licence_jurisdiction?: string | null;
  required_licence_jurisdiction_other?: string | null;
  minimum_driving_experience_months?: number;
  service_area?: string | null;
  service_windows?: AtsServiceWindow[];
  mileage_policy?: string | null;
  driving_time_paid?: boolean;
  screening_conditions?: string[];
}

const screeningTermKeys = [
  "position_shape",
  "driving_requirement",
  "vehicle_expectation",
  "required_licence_jurisdiction",
  "required_licence_jurisdiction_other",
  "required_licence_class",
  "minimum_driving_experience_months",
  "service_area",
  "service_windows",
  "mileage_policy",
  "driving_time_paid",
  "screening_conditions",
] as const;

/** Fail closed whenever the server does not explicitly advertise the 0030 contract. */
export function payloadForScreeningSchema<T extends Record<string, unknown>>(
  payload: T,
  schemaVersion: ScreeningSchemaVersion,
): T {
  const safe = { ...payload };
  if (schemaVersion !== "0030")
    screeningTermKeys.forEach((key) => delete safe[key]);
  return safe;
}
export interface ProvisionStaffResult {
  application_id: string;
  membership_id: string;
  membership_created: boolean;
  role_key: "educator";
  assigned_room_ids: string[];
  provisioning_id: string;
}
export class HiringApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HiringApiError";
  }
}
const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new HiringApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const string = (value: unknown, label: string) => {
  if (typeof value !== "string" || !value.trim())
    throw new HiringApiError(`The server returned an invalid ${label}.`);
  return value;
};
const optionalString = (value: unknown, label: string) =>
  value == null ? null : string(value, label);
const integer = (value: unknown, label: string, minimum = 0) => {
  if (!Number.isInteger(value) || Number(value) < minimum)
    throw new HiringApiError(`The server returned an invalid ${label}.`);
  return Number(value);
};
const optionalInteger = (value: unknown, label: string, minimum = 0) =>
  value == null ? null : integer(value, label, minimum);
const oneOf = <T extends string>(
  value: unknown,
  allowed: readonly T[],
  label: string,
): T => {
  const result = string(value, label);
  if (!allowed.includes(result as T))
    throw new HiringApiError(`The server returned an unsupported ${label}.`);
  return result as T;
};
const nullableOneOf = <T extends string>(
  value: unknown,
  allowed: readonly T[],
  label: string,
): T | null => (value == null ? null : oneOf(value, allowed, label));
const array = <T>(
  value: unknown,
  label: string,
  parser: (item: unknown) => T,
): T[] => {
  if (!Array.isArray(value))
    throw new HiringApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};
const strings = (value: unknown, label: string) =>
  array(value, label, (item) => string(item, label));
const optionalStrings = (value: unknown, label: string) =>
  value == null ? [] : strings(value, label);
const optionalBoolean = (value: unknown, label: string): boolean | null => {
  if (value == null) return null;
  if (typeof value !== "boolean")
    throw new HiringApiError(`The server returned an invalid ${label}.`);
  return value;
};
const parseServiceWindow = (value: unknown): AtsServiceWindow => {
  const row = object(value, "service window");
  return {
    days: array(row.days, "service window days", (day) =>
      oneOf(day, ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const, "service window day"),
    ),
    start_time: string(row.start_time, "service window start time"),
    end_time: string(row.end_time, "service window end time"),
    timezone: string(row.timezone, "service window timezone"),
  };
};
export const parseStructuredRoleTerms = (
  row: Record<string, unknown>,
  requireComplete = false,
): StructuredRoleTerms => {
  const source = row.structured_terms == null
    ? row
    : object(row.structured_terms, "structured role terms");
  if (
    requireComplete &&
    screeningTermKeys.some(
      (key) => !Object.prototype.hasOwnProperty.call(source, key),
    )
  )
    throw new HiringApiError(
      "The server returned incomplete versioned role terms.",
    );
  return ({
  position_shape: source.position_shape == null
    ? "educator_only"
    : oneOf(source.position_shape, ["educator_only", "driver_only", "educator_driver"] as const, "position shape"),
  driving_requirement: source.driving_requirement == null
    ? "not_applicable"
    : oneOf(source.driving_requirement, ["not_applicable", "preferred", "required"] as const, "driving requirement"),
  vehicle_expectation: source.vehicle_expectation == null
    ? "none"
    : oneOf(source.vehicle_expectation, ["none", "organization_vehicle", "personal_vehicle", "either"] as const, "vehicle expectation"),
  required_licence_jurisdiction: optionalString(source.required_licence_jurisdiction, "required licence jurisdiction"),
  required_licence_jurisdiction_other: optionalString(source.required_licence_jurisdiction_other, "other required licence jurisdiction"),
  required_licence_class: optionalString(source.required_licence_class, "required licence class"),
  minimum_driving_experience_months: source.minimum_driving_experience_months == null ? 0 : integer(source.minimum_driving_experience_months, "minimum driving experience"),
  service_area: optionalString(source.service_area, "service area"),
  service_windows: source.service_windows == null ? [] : array(source.service_windows, "service windows", parseServiceWindow),
  mileage_policy: optionalString(source.mileage_policy, "mileage policy"),
  driving_time_paid: optionalBoolean(source.driving_time_paid, "paid driving-time value") ?? false,
  screening_conditions: optionalStrings(source.screening_conditions, "screening conditions"),
});
};
const parseDriverDeclaration = (value: unknown): CandidateDriverDeclaration | null => {
  if (value == null) return null;
  const row = object(value, "candidate driver declaration");
  if (typeof row.willing_to_drive !== "boolean" || row.candidate_provided !== true)
    throw new HiringApiError("The server returned an invalid candidate driver declaration.");
  const radius = row.preferred_service_radius_km;
  if (radius != null && (!Number.isFinite(radius) || Number(radius) < 0))
    throw new HiringApiError("The server returned an invalid candidate service radius.");
  return {
    willing_to_drive: row.willing_to_drive,
    licence_jurisdiction: optionalString(row.licence_jurisdiction, "candidate licence jurisdiction"),
    licence_jurisdiction_other: optionalString(row.licence_jurisdiction_other, "other candidate licence jurisdiction"),
    licence_class: optionalString(row.licence_class, "candidate licence class"),
    vehicle_access: oneOf(row.vehicle_access, ["none", "organization_vehicle_only", "personal_vehicle", "either"] as const, "candidate vehicle access"),
    preferred_service_radius_km: radius == null ? null : Number(radius),
    candidate_provided: true,
  };
};

type RawCandidate = {
  id: string;
  organization_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  notes: string | null;
  status: "prospect" | "active" | "withdrawn" | "archived";
  onboarding_status: Candidate["onboarding_status"];
  candidate_type: Candidate["candidate_type"];
  pathway: CandidatePathway | null;
  driver_declaration: CandidateDriverDeclaration | null;
  institution: string | null;
  program: string | null;
  expected_graduation_date: string | null;
  certification_type: string | null;
  certification_number: string | null;
  certification_expiry_date: string | null;
  certification_verification_status: Candidate["certification_verification_status"];
  certification_verified_at: string | null;
  certification_review_note: string | null;
  certification_provenance: EvidenceProvenance | null;
  certification_candidate_confirmed_at: string | null;
  work_history: WorkHistoryItem[];
  work_history_provenance: EvidenceProvenance | null;
  work_history_candidate_confirmed_at: string | null;
};
type RawApplication = {
  id: string;
  organization_id: string;
  job_id: string;
  candidate_id: string;
  status: CandidateStage;
  source: Candidate["source"];
  candidate_consent_status: Candidate["candidate_consent_status"];
  version: number;
  updated_at: string;
};
const parseWorkHistory = (value: unknown): WorkHistoryItem[] =>
  array(value, "candidate work history", (item) => {
    const row = object(item, "work history item");
    return { ...row, employer: string(row.employer, "work history employer") };
  });
const parseRawCandidate = (value: unknown): RawCandidate => {
  const row = object(value, "candidate");
  return {
    id: string(row.id, "candidate id"),
    organization_id: string(row.organization_id, "candidate organization"),
    first_name: string(row.first_name, "candidate first name"),
    last_name: string(row.last_name, "candidate last name"),
    email: string(row.email, "candidate email"),
    phone: optionalString(row.phone, "candidate phone"),
    notes: optionalString(row.notes, "candidate notes"),
    status: oneOf(
      row.status,
      ["prospect", "active", "withdrawn", "archived"] as const,
      "candidate status",
    ),
    onboarding_status: oneOf(
      row.onboarding_status,
      ["not_started", "in_progress", "submitted", "complete"] as const,
      "candidate onboarding status",
    ),
    candidate_type: nullableOneOf(
      row.candidate_type,
      ["certified_educator", "student"] as const,
      "candidate type",
    ),
    pathway: row.pathway == null
      ? null
      : oneOf(row.pathway, ["educator", "student_educator", "driver", "educator_driver"] as const, "candidate pathway"),
    driver_declaration: parseDriverDeclaration(row.driver_declaration),
    institution: optionalString(row.institution, "candidate institution"),
    program: optionalString(row.program, "candidate program"),
    expected_graduation_date: optionalString(
      row.expected_graduation_date,
      "expected graduation date",
    ),
    certification_type: optionalString(
      row.certification_type,
      "certification type",
    ),
    certification_number: optionalString(
      row.certification_number,
      "certification number",
    ),
    certification_expiry_date: optionalString(
      row.certification_expiry_date,
      "certification expiry",
    ),
    certification_verification_status: oneOf(
      row.certification_verification_status,
      ["unverified", "pending", "verified", "rejected"] as const,
      "certification verification status",
    ),
    certification_verified_at: optionalString(
      row.certification_verified_at,
      "certification verification time",
    ),
    certification_review_note: optionalString(
      row.certification_review_note,
      "certification review note",
    ),
    certification_provenance: nullableOneOf(
      row.certification_provenance,
      ["manual", "local_ocr"] as const,
      "certification provenance",
    ),
    certification_candidate_confirmed_at: optionalString(
      row.certification_candidate_confirmed_at,
      "certification candidate confirmation time",
    ),
    work_history: parseWorkHistory(row.work_history),
    work_history_provenance: nullableOneOf(
      row.work_history_provenance,
      ["manual", "local_ocr"] as const,
      "work history provenance",
    ),
    work_history_candidate_confirmed_at: optionalString(
      row.work_history_candidate_confirmed_at,
      "work history candidate confirmation time",
    ),
  };
};
const parseRawApplication = (value: unknown): RawApplication => {
  const row = object(value, "application");
  return {
    id: string(row.id, "application id"),
    organization_id: string(row.organization_id, "application organization"),
    job_id: string(row.job_id, "application job"),
    candidate_id: string(row.candidate_id, "application candidate"),
    status: oneOf(
      row.status,
      [
        "invited",
        "applied",
        "screening",
        "interview",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "hired",
      ] as const,
      "application status",
    ),
    source: oneOf(
      row.source,
      [
        "private_invitation",
        "marketplace_application",
        "employer_interest",
      ] as const,
      "application source",
    ),
    candidate_consent_status: oneOf(
      row.candidate_consent_status,
      ["requested", "accepted", "declined"] as const,
      "candidate consent status",
    ),
    version: integer(row.version, "application version", 1),
    updated_at: string(row.updated_at, "application update time"),
  };
};
const parseRawJob = (
  value: unknown,
  requireScreeningContract = false,
): Omit<JobListing, "applicant_count"> => {
  const row = object(value, "job");
  return {
    id: string(row.id, "job id"),
    organization_id: string(row.organization_id, "job organization"),
    facility_id: optionalString(row.facility_id, "job facility"),
    title: string(row.title, "job title"),
    location: optionalString(row.location, "job location") || "Not specified",
    employment_type: string(row.employment_type, "employment type"),
    status: oneOf(
      row.status,
      ["draft", "open", "paused", "closed"] as const,
      "job status",
    ),
    summary: string(row.description, "job description"),
    requirements: strings(row.requirements, "job requirements"),
    openings: integer(row.openings, "job openings", 1),
    version: integer(row.version, "job version", 1),
    created_at: string(row.created_at, "job creation time"),
    updated_at: string(row.updated_at, "job update time"),
    structured_terms: parseStructuredRoleTerms(row, requireScreeningContract),
  };
};
export function parseOfferVersion(
  value: unknown,
  requireScreeningContract = false,
): OfferVersion {
  const row = object(value, "offer");
  const result: OfferVersion = {
    id: string(row.id, "offer id"),
    organization_id: string(row.organization_id, "offer organization"),
    application_id: string(row.application_id, "offer application"),
    client_operation_id: optionalString(row.client_operation_id, "offer client operation"),
    version: integer(row.version, "offer version", 1),
    status: oneOf(
      row.status,
      [
        "draft",
        "sent",
        "accepted",
        "declined",
        "withdrawn",
        "superseded",
      ] as const,
      "offer status",
    ),
    position_title: string(row.position_title, "offer position"),
    compensation: optionalString(row.compensation, "offer compensation"),
    start_date: optionalString(row.start_date, "offer start date"),
    notes: string(row.terms, "offer terms"),
    expires_at: optionalString(row.expires_at, "offer expiry"),
    sent_at: optionalString(row.sent_at, "offer sent time"),
    accepted_at: optionalString(row.accepted_at, "offer acceptance time"),
    terminal_at: optionalString(row.terminal_at, "offer terminal time"),
    created_at: string(row.created_at, "offer creation time"),
    updated_at: string(row.updated_at, "offer update time"),
    terms_digest: optionalString(row.terms_digest, "offer terms digest"),
    structured_terms: parseStructuredRoleTerms(row, requireScreeningContract),
  };
  if (['sent', 'accepted', 'declined', 'withdrawn'].includes(result.status) && !result.sent_at) throw new HiringApiError('The server returned an offer without sent evidence.');
  if (result.status === 'accepted' && !result.accepted_at) throw new HiringApiError('The server returned an accepted offer without acceptance evidence.');
  if (['declined', 'withdrawn', 'superseded'].includes(result.status) && !result.terminal_at) throw new HiringApiError('The server returned a terminal offer without terminal evidence.');
  if (
    requireScreeningContract &&
    result.status !== 'draft' &&
    !/^[0-9a-f]{64}$/.test(result.terms_digest ?? '')
  )
    throw new HiringApiError(
      'The server returned a sent offer without exact terms evidence.',
    );
  return result;
}
const parseInterview = (value: unknown): InterviewRecord => {
  const row = object(value, "interview");
  return {
    id: string(row.id, "interview id"),
    organization_id: string(row.organization_id, "interview organization"),
    application_id: string(row.application_id, "interview application"),
    scheduled_at: string(row.scheduled_at, "interview time"),
    timezone: string(row.timezone, "interview timezone"),
    location_or_link: string(row.location_or_link, "interview location"),
    status: oneOf(
      row.status,
      [
        "requested",
        "confirmed",
        "declined",
        "cancelled",
        "candidate_proposed",
        "proposal_declined",
      ] as const,
      "interview status",
    ),
    candidate_proposed_at: optionalString(
      row.candidate_proposed_at,
      "candidate proposed time",
    ),
    candidate_proposal_note: optionalString(
      row.candidate_proposal_note,
      "candidate proposal note",
    ),
    created_at: string(row.created_at, "interview creation time"),
    updated_at: string(row.updated_at, "interview update time"),
  };
};
export function parseProvisionStaff(
  value: unknown,
  organizationId: string,
): ProvisionStaffResult {
  const row = object(value, "staff provisioning");
  const application = object(row.application, "provisioned application");
  if (application.organization_id !== organizationId)
    throw new HiringApiError(
      "The staff provisioning crossed the active organization boundary.",
    );
  if (
    typeof row.membership_created !== "boolean" ||
    row.role_key !== "educator"
  )
    throw new HiringApiError(
      "The server returned an invalid educator provisioning result.",
    );
  const rooms = strings(row.assigned_room_ids, "provisioned room ids");
  if (rooms.length)
    throw new HiringApiError(
      "The server assigned room access during ATS provisioning.",
    );
  return {
    application_id: string(application.id, "provisioned application id"),
    membership_id: string(row.membership_id, "provisioned membership id"),
    membership_created: row.membership_created,
    role_key: "educator",
    assigned_room_ids: rooms,
    provisioning_id: string(row.provisioning_id, "staff provisioning id"),
  };
}

export function parseHiringWorkspace(
  value: unknown,
  organizationId: string,
): HiringWorkspace {
  const row = object(value, "ATS workspace");
  const screeningSchemaVersion =
    row.screening_schema_version === "0030" ? "0030" : null;
  const requireScreeningContract = screeningSchemaVersion === "0030";
  const jobs = array(row.jobs, "jobs", (item) =>
    parseRawJob(item, requireScreeningContract),
  );
  const people = array(row.candidates, "candidates", parseRawCandidate);
  const applications = array(
    row.applications,
    "applications",
    parseRawApplication,
  );
  const rawOffers = array(row.offers, "offers", (item) =>
    parseOfferVersion(item, requireScreeningContract),
  );
  const interviews = array(row.interviews, "interviews", parseInterview);
  if (
    [...jobs, ...people, ...applications, ...rawOffers, ...interviews].some(
      (item) => item.organization_id !== organizationId,
    )
  )
    throw new HiringApiError(
      "The hiring workspace crossed the active organization boundary.",
    );
  const jobsById = new Map(jobs.map((item) => [item.id, item]));
  const peopleById = new Map(people.map((item) => [item.id, item]));
  const applicationsById = new Map(applications.map((item) => [item.id, item]));
  if (
    jobsById.size !== jobs.length ||
    peopleById.size !== people.length ||
    applicationsById.size !== applications.length ||
    applications.some(
      (item) =>
        !jobsById.has(item.job_id) || !peopleById.has(item.candidate_id),
    ) ||
    rawOffers.some((item) => !applicationsById.has(item.application_id)) ||
    interviews.some((item) => !applicationsById.has(item.application_id))
  )
    throw new HiringApiError(
      "The hiring workspace returned inconsistent record references.",
    );
  const listings = jobs.map((job) => ({
    ...job,
    applicant_count: applications.filter((item) => item.job_id === job.id)
      .length,
  }));
  const candidates = applications.map((application) => {
    const person = peopleById.get(application.candidate_id)!;
    return {
      id: application.id,
      organization_id: application.organization_id,
      listing_id: application.job_id,
      candidate_id: person.id,
      first_name: person.first_name,
      last_name: person.last_name,
      email: person.email,
      phone:
        application.candidate_consent_status === "accepted"
          ? person.phone
          : null,
      notes: person.notes,
      profile_status: person.status,
      onboarding_status: person.onboarding_status,
      candidate_type: person.candidate_type,
      pathway: person.pathway,
      driver_declaration: person.driver_declaration,
      institution: person.institution,
      program: person.program,
      expected_graduation_date: person.expected_graduation_date,
      certification_type: person.certification_type,
      certification_number: person.certification_number,
      certification_expiry_date: person.certification_expiry_date,
      certification_verification_status:
        person.certification_verification_status,
      certification_verified_at: person.certification_verified_at,
      certification_review_note: person.certification_review_note,
      certification_provenance: person.certification_provenance,
      certification_candidate_confirmed_at:
        person.certification_candidate_confirmed_at,
      work_history: person.work_history,
      work_history_provenance: person.work_history_provenance,
      work_history_candidate_confirmed_at:
        person.work_history_candidate_confirmed_at,
      source: application.source,
      candidate_consent_status: application.candidate_consent_status,
      stage: application.status,
      version: application.version,
      updated_at: application.updated_at,
    };
  });
  const offers = applications.map((application) => ({
    candidate_id: application.id,
    versions: rawOffers
      .filter((item) => item.application_id === application.id)
      .sort((a, b) => b.version - a.version),
  }));
  return {
    organization_id: organizationId,
    generated_at: new Date().toISOString(),
    screening_schema_version: screeningSchemaVersion,
    listings,
    candidates,
    offers,
    interviews,
  };
}

const jobTransitionMap: Record<ListingStatus, ListingStatus[]> = {
  draft: ["open", "closed"],
  open: ["paused", "closed"],
  paused: ["open", "closed"],
  closed: [],
};
// Candidate-owned apply, withdraw, accept, and decline actions are intentionally
// omitted even when the server state machine can represent them.
const candidateTransitionMap: Record<CandidateStage, CandidateStage[]> = {
  invited: [],
  applied: ["screening", "rejected"],
  screening: ["interview", "rejected"],
  interview: ["screening", "rejected"],
  offer: ["rejected"],
  accepted: [],
  rejected: [],
  withdrawn: [],
  hired: [],
};
export const jobTransitions = (status: ListingStatus): ListingStatus[] =>
  jobTransitionMap[status];
export const candidateTransitions = (stage: CandidateStage): CandidateStage[] =>
  candidateTransitionMap[stage];

export const hiringApi = {
  workspace: async (organizationId: string, signal?: AbortSignal) =>
    parseHiringWorkspace(
      await apiRequest<unknown>("/ats/workspace", { signal }),
      organizationId,
    ),
  createListing: (
    payload: ListingInput,
    schemaVersion: ScreeningSchemaVersion = null,
  ) =>
    apiRequest("/ats/jobs", {
      method: "POST",
      body: JSON.stringify(
        payloadForScreeningSchema(
          payload as unknown as Record<string, unknown>,
          schemaVersion,
        ),
      ),
    }),
  setListingStatus: (listing: JobListing, status: ListingStatus) =>
    apiRequest(`/ats/jobs/${encodeURIComponent(listing.id)}/status`, {
      method: "POST",
      body: JSON.stringify({
        status,
        expected_version: listing.version,
        reason: "Employer changed listing status",
      }),
    }),
  moveCandidate: (candidate: Candidate, status: CandidateStage) =>
    apiRequest(`/ats/applications/${encodeURIComponent(candidate.id)}/stage`, {
      method: "POST",
      body: JSON.stringify({
        status,
        expected_version: candidate.version,
        reason: "Employer pipeline action",
      }),
    }),
  createAndSendOffer: async (
    applicationId: string,
    payload: OfferInput & { client_operation_id: string },
    schemaVersion: ScreeningSchemaVersion = null,
  ) =>
    parseOfferVersion(
      await apiRequest<unknown>(
        `/ats/applications/${encodeURIComponent(applicationId)}/offers/send`,
        {
          method: "POST",
          body: JSON.stringify(
            payloadForScreeningSchema(
              payload as unknown as Record<string, unknown>,
              schemaVersion,
            ),
          ),
        },
      ),
      schemaVersion === "0030",
    ),
  withdrawOffer: async (offerId: string, reason: string) =>
    parseOfferVersion(await apiRequest<unknown>(`/ats/offers/${encodeURIComponent(offerId)}/decision`, { method: "POST", body: JSON.stringify({ decision: "withdrawn", reason }) })),
  provisionCandidate: async (
    candidate: Candidate,
    operationId: string,
    organizationId: string,
  ) =>
    parseProvisionStaff(
      await apiRequest<unknown>(
        `/ats/applications/${encodeURIComponent(candidate.id)}/provision-staff`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_version: candidate.version,
            operation_id: operationId,
          }),
        },
      ),
      organizationId,
    ),
  reviewCertification: (
    candidateId: string,
    status: "pending" | "verified" | "rejected",
    reason: string,
  ) =>
    apiRequest(
      `/ats/candidates/${encodeURIComponent(candidateId)}/certification-review`,
      { method: "POST", body: JSON.stringify({ status, reason }) },
    ),
};
