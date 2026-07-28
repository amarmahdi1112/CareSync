import {
  API_URL,
  addOrganizationHeader,
  apiRequest,
  getSessionToken,
} from '../../api/client';
import {
  parseStructuredRoleTerms,
  type CandidateDriverDeclaration,
  type CandidatePathway,
  type StructuredRoleTerms,
} from './hiringApi';

export type ScreeningRequirement =
  | 'criminal_record_check'
  | 'vulnerable_sector_search';
export type ScreeningDecision = 'accepted' | 'rejected';
export type ScreeningNameResolution =
  | 'matched'
  | 'candidate_attests_same_person';

export interface ScreeningReview {
  id: string;
  requirement_class: ScreeningRequirement;
  decision: ScreeningDecision;
  reason_code: string;
  note: string | null;
  reviewed_at: string;
  reviewer_user_id: string;
  review_sequence: number;
}

export interface SharedScreeningDocument {
  id: string;
  shared_at: string;
  screening_profile_version: number;
  shared_version: {
    id: string;
    declared_coverage: ScreeningRequirement[];
    version_number: number;
    subject_name: string;
    account_name_snapshot: string;
    subject_name_match: boolean;
    mismatch_resolution: ScreeningNameResolution;
    issue_date: string | null;
    expiry_date: string | null;
    candidate_confirmed_at: string;
    content_url: string;
  };
  reviews: ScreeningReview[];
}

export interface EmployerScreeningProjection {
  screening_schema_version: '0030';
  application_id: string;
  candidate_id: string;
  snapshot: {
    pathway: CandidatePathway;
    screening_profile_version: number;
    job_terms_version: number;
    driver_declaration: CandidateDriverDeclaration;
    job_terms: StructuredRoleTerms;
    candidate_acknowledged_at: string;
  } | null;
  shares: SharedScreeningDocument[];
}

export class ScreeningApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ScreeningApiError';
  }
}

const object = (value: unknown, label: string): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new ScreeningApiError(`The server returned an invalid ${label}.`);
  return value as Record<string, unknown>;
};
const string = (value: unknown, label: string): string => {
  if (typeof value !== 'string' || !value.trim())
    throw new ScreeningApiError(`The server returned an invalid ${label}.`);
  return value;
};
const nullableString = (value: unknown, label: string): string | null =>
  value == null ? null : string(value, label);
const oneOf = <T extends string>(
  value: unknown,
  allowed: readonly T[],
  label: string,
): T => {
  const parsed = string(value, label);
  if (!allowed.includes(parsed as T))
    throw new ScreeningApiError(`The server returned an unsupported ${label}.`);
  return parsed as T;
};
const positiveInteger = (value: unknown, label: string): number => {
  if (!Number.isInteger(value) || Number(value) < 1)
    throw new ScreeningApiError(`The server returned an invalid ${label}.`);
  return Number(value);
};
const array = <T>(value: unknown, label: string, parser: (item: unknown) => T): T[] => {
  if (!Array.isArray(value))
    throw new ScreeningApiError(`The server returned invalid ${label}.`);
  return value.map(parser);
};
const parseRequirement = (value: unknown) =>
  oneOf(
    value,
    ['criminal_record_check', 'vulnerable_sector_search'] as const,
    'screening requirement',
  );
const parseDriverDeclaration = (value: unknown): CandidateDriverDeclaration => {
  const row = object(value, 'candidate driver declaration');
  const radius = row.preferred_service_radius_km;
  if (
    typeof row.willing_to_drive !== 'boolean' ||
    row.candidate_provided !== true ||
    (radius != null && (!Number.isFinite(radius) || Number(radius) < 0))
  )
    throw new ScreeningApiError('The server returned an invalid candidate driver declaration.');
  return {
    willing_to_drive: row.willing_to_drive,
    licence_jurisdiction: nullableString(row.licence_jurisdiction, 'candidate licence jurisdiction'),
    licence_jurisdiction_other: nullableString(row.licence_jurisdiction_other, 'other candidate licence jurisdiction'),
    licence_class: nullableString(row.licence_class, 'candidate licence class'),
    vehicle_access: oneOf(
      row.vehicle_access,
      ['none', 'organization_vehicle_only', 'personal_vehicle', 'either'] as const,
      'candidate vehicle access',
    ),
    preferred_service_radius_km: radius == null ? null : Number(radius),
    candidate_provided: true,
  };
};
const parseReview = (value: unknown): ScreeningReview => {
  const row = object(value, 'screening review');
  return {
    id: string(row.id, 'screening review id'),
    requirement_class: parseRequirement(row.requirement_class),
    decision: oneOf(row.decision, ['accepted', 'rejected'] as const, 'screening decision'),
    reason_code: string(row.reason_code, 'screening review reason'),
    note: nullableString(row.note, 'screening review note'),
    reviewed_at: string(row.reviewed_at, 'screening review time'),
    reviewer_user_id: string(row.reviewer_user_id, 'screening reviewer'),
    review_sequence: positiveInteger(row.review_sequence, 'screening review sequence'),
  };
};
const parseShare = (
  value: unknown,
  applicationId: string,
): SharedScreeningDocument => {
  const row = object(value, 'shared screening document');
  const shareId = string(row.id, 'screening share id');
  const version = object(row.shared_version, 'exact shared screening document version');
  const contentUrl = string(version.content_url, 'shared screening content route');
  const expectedContentUrl = `/api/v1/ats/applications/${encodeURIComponent(applicationId)}/screening-shares/${encodeURIComponent(shareId)}/content`;
  if (contentUrl !== expectedContentUrl)
    throw new ScreeningApiError('The screening source route crossed the exact share boundary.');
  const subjectName = string(version.subject_name, 'screening subject name');
  const accountNameSnapshot = string(
    version.account_name_snapshot,
    'screening account name snapshot',
  );
  if (typeof version.subject_name_match !== 'boolean')
    throw new ScreeningApiError('The server returned an invalid screening subject name match.');
  const mismatchResolution = oneOf(
    version.mismatch_resolution,
    ['matched', 'candidate_attests_same_person'] as const,
    'screening name reconciliation',
  );
  if (
    (version.subject_name_match && mismatchResolution !== 'matched') ||
    (!version.subject_name_match && mismatchResolution !== 'candidate_attests_same_person')
  )
    throw new ScreeningApiError('The server returned inconsistent screening name reconciliation.');
  const reviews = array(row.reviews, 'screening reviews', parseReview);
  const seenSequences = new Set<string>();
  reviews.forEach((review) => {
    const key = `${review.requirement_class}:${review.review_sequence}`;
    if (seenSequences.has(key))
      throw new ScreeningApiError('The server returned duplicate screening review sequence evidence.');
    seenSequences.add(key);
  });
  return {
    id: shareId,
    shared_at: string(row.shared_at, 'screening share time'),
    screening_profile_version: positiveInteger(
      row.screening_profile_version,
      'shared screening profile version',
    ),
    shared_version: {
      id: string(version.id, 'screening document version id'),
      version_number: positiveInteger(version.version_number, 'screening document version'),
      declared_coverage: array(version.declared_coverage, 'screening coverage', parseRequirement),
      subject_name: subjectName,
      account_name_snapshot: accountNameSnapshot,
      subject_name_match: version.subject_name_match,
      mismatch_resolution: mismatchResolution,
      issue_date: nullableString(version.issue_date, 'screening issue date'),
      expiry_date: nullableString(version.expiry_date, 'screening expiry date'),
      candidate_confirmed_at: string(
        version.candidate_confirmed_at,
        'screening candidate confirmation time',
      ),
      content_url: contentUrl,
    },
    reviews,
  };
};

export function latestScreeningDecision(
  share: SharedScreeningDocument,
  requirement: ScreeningRequirement,
): ScreeningReview | null {
  return share.reviews
    .filter((review) => review.requirement_class === requirement)
    .reduce<ScreeningReview | null>(
      (latest, review) =>
        !latest || review.review_sequence > latest.review_sequence ? review : latest,
      null,
    );
}

export function parseEmployerScreeningProjection(
  value: unknown,
  expectedApplicationId: string,
): EmployerScreeningProjection {
  const row = object(value, 'application screening projection');
  const applicationId = string(row.application_id, 'screening application id');
  if (applicationId !== expectedApplicationId)
    throw new ScreeningApiError('The screening response crossed the selected application boundary.');
  if (row.screening_schema_version !== '0030')
    throw new ScreeningApiError('The server returned an unsupported screening projection.');
  const snapshotRow = row.snapshot == null
    ? null
    : object(row.snapshot, 'application screening snapshot');
  return {
    screening_schema_version: '0030',
    application_id: applicationId,
    candidate_id: string(row.candidate_id, 'screening candidate id'),
    snapshot: snapshotRow
      ? {
          pathway: oneOf(
            snapshotRow.pathway,
            ['educator', 'student_educator', 'driver', 'educator_driver'] as const,
            'candidate pathway',
          ),
          screening_profile_version: positiveInteger(
            snapshotRow.screening_profile_version,
            'screening snapshot profile version',
          ),
          job_terms_version: positiveInteger(
            snapshotRow.job_terms_version,
            'screening snapshot job terms version',
          ),
          driver_declaration: parseDriverDeclaration(snapshotRow.driver_declaration),
          job_terms: parseStructuredRoleTerms(
            object(snapshotRow.job_terms, 'screening snapshot job terms'),
            true,
          ),
          candidate_acknowledged_at: string(
            snapshotRow.candidate_acknowledged_at,
            'screening snapshot acknowledgment time',
          ),
        }
      : null,
    shares: array(row.shares, 'screening document shares', (share) =>
      parseShare(share, applicationId),
    ),
  };
}

export type ViewedScreeningSource = {
  blob: Blob;
  media_type: 'application/pdf' | 'image/jpeg' | 'image/png';
  share_id: string;
  document_version_id: string;
};

async function viewExactSource(
  applicationId: string,
  share: SharedScreeningDocument,
  signal?: AbortSignal,
): Promise<ViewedScreeningSource> {
  const token = getSessionToken();
  if (!token) throw new ScreeningApiError('Your session is required to view this source.');
  const headers = addOrganizationHeader(new Headers({
    Accept: 'application/pdf, image/jpeg, image/png',
    Authorization: `Bearer ${token}`,
  }));
  const origin = new URL(API_URL).origin;
  const response = await fetch(`${origin}${share.shared_version.content_url}`, {
    method: 'GET',
    headers,
    cache: 'no-store',
    signal,
  });
  if (!response.ok)
    throw new ScreeningApiError(`The exact shared source could not be opened (${response.status}).`);
  if (!/\bno-store\b/i.test(response.headers.get('Cache-Control') || ''))
    throw new ScreeningApiError('The screening source did not include its no-store boundary.');
  const mediaType = (response.headers.get('Content-Type') || '').split(';')[0]?.trim();
  if (!['application/pdf', 'image/jpeg', 'image/png'].includes(mediaType || ''))
    throw new ScreeningApiError('The screening source returned an unsupported media type.');
  const declaredLength = Number(response.headers.get('Content-Length') || 0);
  if (declaredLength > 50 * 1024 * 1024)
    throw new ScreeningApiError('The screening source is too large for the protected viewer.');
  const blob = await response.blob();
  if (!blob.size || blob.size > 50 * 1024 * 1024)
    throw new ScreeningApiError('The screening source has an invalid protected-viewer size.');
  return {
    blob,
    media_type: mediaType as ViewedScreeningSource['media_type'],
    share_id: share.id,
    document_version_id: share.shared_version.id,
  };
}

export const screeningApi = {
  application: async (applicationId: string, signal?: AbortSignal) =>
    parseEmployerScreeningProjection(
      await apiRequest<unknown>(
        `/ats/applications/${encodeURIComponent(applicationId)}/screening`,
        { signal },
      ),
      applicationId,
    ),
  viewExactSource,
  review: (
    applicationId: string,
    shareId: string,
    input: {
      decision: ScreeningDecision;
      requirement_class: ScreeningRequirement;
      reason_code: string;
      note?: string | null;
    },
  ) =>
    apiRequest(
      `/ats/applications/${encodeURIComponent(applicationId)}/screening-shares/${encodeURIComponent(shareId)}/reviews`,
      { method: 'POST', body: JSON.stringify(input) },
    ),
};
