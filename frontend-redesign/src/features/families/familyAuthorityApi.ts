import { addOrganizationHeader, notifyAuthorizationDenied, SESSION_TOKEN_KEY } from '../../api/client';
import { CommandOutcomeUnknownError, CommandRejectedBeforeCommitError } from '../../api/childcareCommand';
import { parseChildcareCommandReceipt } from '../../api/childcareCommandReceipt';
import type {
  AuthorityCommandResponse,
  AuthorityEvidence,
  AuthorityEvidenceAssessment,
  AuthorityEvidenceEpistemicStatus,
  AuthorityEvidenceInvalidationReason,
  AuthorityEvidenceKind,
  AuthorityEvidenceObject,
  AuthorityEvidenceRecordInput,
  AuthorityEvidenceRejectionReason,
  AuthorityPerson,
  AuthorityPersonCreateInput,
  AuthorityPersonFacts,
  AuthorityPersonSource,
  AuthorityPersonVersion,
  ChildConsentDecision,
  ChildConsentRecordInput,
  ChildAuthoritySummary,
  ConsentPolicyPublishInput,
  ConsentPolicyVersion,
  ConsentScope,
  ReleaseAuthorization,
  ReleaseAuthorizationGrantInput,
  ReleaseRule,
  ReleaseRuleCreateInput,
  FamilyAuthorityWorkspaceRecord,
} from './familyAuthorityTypes';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;

type ErrorOrigin = 'http' | 'response' | 'preflight';

export class FamilyAuthorityApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly code: string | null = null,
    public readonly details?: unknown,
    public readonly origin: ErrorOrigin = 'response',
  ) {
    super(message);
    this.name = 'FamilyAuthorityApiError';
  }
}

export function isFamilyAuthorityUnavailable(caught: unknown): boolean {
  return caught instanceof FamilyAuthorityApiError
    && caught.status === 503
    && caught.code === 'family_authority_unavailable';
}

function exact(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  }
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new FamilyAuthorityApiError(`The server returned an unexpected ${label} shape.`);
  }
  return row;
}

function string(value: unknown, label: string, maximum = 2_048): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) {
    throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  }
  return value;
}

function nullableString(value: unknown, label: string, maximum = 2_048): string | null {
  if (value === null) return null;
  return string(value, label, maximum);
}

function uuid(value: unknown, label: string): string {
  const parsed = string(value, label, 64);
  if (!UUID.test(parsed)) throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  return parsed.toLowerCase();
}

function timestamp(value: unknown, label: string): string {
  const parsed = string(value, label, 64);
  if (!TIMESTAMP.test(parsed) || !Number.isFinite(Date.parse(parsed))) {
    throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  }
  return parsed;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value === null ? null : timestamp(value, label);
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) {
    throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  }
  return Number(value);
}

function bool(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  return value;
}

function oneOf<Value extends string>(value: unknown, values: readonly Value[], label: string): Value {
  if (!values.includes(value as Value)) throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  return value as Value;
}

function array<Value>(value: unknown, label: string, parser: (item: unknown, index: number) => Value): Value[] {
  if (!Array.isArray(value)) throw new FamilyAuthorityApiError(`The server returned an invalid ${label}.`);
  return value.map(parser);
}

const RELATIONSHIPS = ['parent', 'legal_guardian', 'foster_parent', 'grandparent', 'adult_sibling', 'aunt_uncle', 'family_friend', 'caseworker', 'transport_provider', 'other'] as const;
const EVIDENCE_KINDS = ['identity_document', 'custody_document', 'court_order', 'guardian_attestation', 'signed_consent', 'signed_release_delegation', 'staff_witness', 'other_document'] as const;
const EVIDENCE_LIFECYCLES = ['unreviewed', 'reviewed', 'rejected', 'invalidated', 'superseded'] as const;
const EVIDENCE_EFFECTIVE = [...EVIDENCE_LIFECYCLES, 'expired'] as const;
const AUTHORITY_BASES = ['guardian_record', 'reviewed_custody_evidence', 'reviewed_delegation_evidence', 'other_reviewed_authority'] as const;
const VERIFICATION_POLICIES = ['government_photo_id', 'documented_familiarity', 'government_photo_id_or_documented_familiarity', 'government_photo_id_and_secondary_check'] as const;
const RELEASE_REVOCATION_REASONS = ['authority_withdrawn', 'safety_change', 'superseded', 'entered_in_error'] as const;
const AUTHORITY_RECORD_EFFECTIVE_STATUSES = ['scheduled', 'effective', 'expired', 'revoked', 'withdrawn', 'supporting_evidence_unavailable'] as const;
const RELEASE_RULE_KINDS = ['deny', 'supervised_only', 'named_recipient_only', 'manager_review'] as const;
const CONSENT_PURPOSES = ['off_site_activity', 'emergency_health_care', 'medication_administration', 'internal_media', 'external_media', 'marketing', 'research', 'optional_service', 'information_sharing'] as const;
const CONSENT_SIGNER_REQUIREMENTS = ['guardian_record', 'legal_decision_maker', 'specific_reviewed_authority'] as const;
const CONSENT_WITHDRAWAL_REASONS = ['signer_withdrew', 'authority_changed', 'superseded', 'entered_in_error'] as const;

function parsePersonSource(value: unknown): AuthorityPersonSource {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new FamilyAuthorityApiError('The server returned an invalid authority-person source.');
  const kind = (value as Record<string, unknown>).kind;
  if (kind === 'manual') {
    exact(value, ['kind'], 'manual authority-person source');
    return { kind };
  }
  if (kind === 'guardian') {
    const row = exact(value, ['kind', 'guardian_id'], 'guardian authority-person source');
    return { kind, guardian_id: uuid(row.guardian_id, 'authority-person guardian') };
  }
  if (kind === 'emergency_contact') {
    const row = exact(value, ['kind', 'emergency_contact_id'], 'emergency-contact authority-person source');
    return { kind, emergency_contact_id: uuid(row.emergency_contact_id, 'authority-person emergency contact') };
  }
  throw new FamilyAuthorityApiError('The server returned an invalid authority-person source kind.');
}

function parseFacts(value: unknown): AuthorityPersonFacts {
  const row = exact(value, ['first_name', 'middle_name', 'last_name', 'preferred_name', 'relationship_kind', 'relationship_detail', 'email', 'primary_phone'], 'authority-person facts');
  const relationshipKind = oneOf(row.relationship_kind, RELATIONSHIPS, 'authority-person relationship');
  const relationshipDetail = nullableString(row.relationship_detail, 'authority-person relationship detail', 120);
  if ((relationshipKind === 'other') !== (relationshipDetail !== null)) {
    throw new FamilyAuthorityApiError('The server returned an incoherent authority-person relationship.');
  }
  return {
    first_name: string(row.first_name, 'authority-person first name', 100),
    middle_name: nullableString(row.middle_name, 'authority-person middle name', 100),
    last_name: string(row.last_name, 'authority-person last name', 100),
    preferred_name: nullableString(row.preferred_name, 'authority-person preferred name', 100),
    relationship_kind: relationshipKind,
    relationship_detail: relationshipDetail,
    email: nullableString(row.email, 'authority-person email', 320),
    primary_phone: nullableString(row.primary_phone, 'authority-person phone', 30),
  };
}

function parsePersonVersion(value: unknown): AuthorityPersonVersion {
  const row = exact(value, ['id', 'person_id', 'version_number', 'facts', 'closed_at', 'created_at'], 'authority-person version');
  return {
    id: uuid(row.id, 'authority-person version id'),
    person_id: uuid(row.person_id, 'authority-person version person'),
    version_number: integer(row.version_number, 'authority-person version number', 1),
    facts: parseFacts(row.facts),
    closed_at: nullableTimestamp(row.closed_at, 'authority-person version closure time'),
    created_at: timestamp(row.created_at, 'authority-person version creation time'),
  };
}

export function parseAuthorityPerson(value: unknown): AuthorityPerson {
  const row = exact(value, ['id', 'organization_id', 'family_id', 'version', 'status', 'source', 'current_version', 'retired_at', 'created_at', 'updated_at'], 'authority person');
  const person: AuthorityPerson = {
    id: uuid(row.id, 'authority-person id'),
    organization_id: uuid(row.organization_id, 'authority-person organization'),
    family_id: uuid(row.family_id, 'authority-person family'),
    version: integer(row.version, 'authority-person version', 1),
    status: oneOf(row.status, ['active', 'retired'] as const, 'authority-person status'),
    source: parsePersonSource(row.source),
    current_version: row.current_version === null ? null : parsePersonVersion(row.current_version),
    retired_at: nullableTimestamp(row.retired_at, 'authority-person retirement time'),
    created_at: timestamp(row.created_at, 'authority-person creation time'),
    updated_at: timestamp(row.updated_at, 'authority-person update time'),
  };
  if (person.status === 'active') {
    if (!person.current_version || person.retired_at || person.current_version.person_id !== person.id || person.current_version.version_number !== person.version || person.current_version.closed_at) {
      throw new FamilyAuthorityApiError('The server returned an incoherent active authority person.');
    }
  } else if (person.current_version || !person.retired_at) {
    throw new FamilyAuthorityApiError('The server returned an incoherent retired authority person.');
  }
  return person;
}

function parseAssessment(value: unknown): AuthorityEvidenceAssessment {
  const row = exact(value, ['id', 'evidence_id', 'version_number', 'decision', 'assessed_epistemic_status', 'reason_code', 'confidential_note', 'superseded_by_evidence_id', 'actor_user_id', 'created_at'], 'authority-evidence assessment');
  const decision = oneOf(row.decision, ['reviewed', 'rejected', 'invalidated', 'superseded'] as const, 'authority-evidence assessment decision');
  const versionNumber = integer(row.version_number, 'authority-evidence assessment version', 2);
  if (versionNumber !== (decision === 'reviewed' || decision === 'rejected' ? 2 : 3)) throw new FamilyAuthorityApiError('The authority-evidence assessment version is incoherent.');
  return {
    id: uuid(row.id, 'authority-evidence assessment id'),
    evidence_id: uuid(row.evidence_id, 'authority-evidence assessment evidence'),
    version_number: versionNumber as 2 | 3,
    decision,
    assessed_epistemic_status: row.assessed_epistemic_status === null ? null : oneOf(row.assessed_epistemic_status, ['reported', 'document_observed'] as const, 'authority-evidence epistemic status'),
    reason_code: nullableString(row.reason_code, 'authority-evidence reason code', 80),
    confidential_note: nullableString(row.confidential_note, 'authority-evidence confidential note', 1_000),
    superseded_by_evidence_id: row.superseded_by_evidence_id === null ? null : uuid(row.superseded_by_evidence_id, 'superseding authority evidence'),
    actor_user_id: uuid(row.actor_user_id, 'authority-evidence assessment actor'),
    created_at: timestamp(row.created_at, 'authority-evidence assessment creation time'),
  };
}

function parseStorage(value: unknown) {
  if (value === null) return null;
  const row = exact(value, ['storage_reference', 'media_type', 'byte_size', 'content_sha256'], 'authority-evidence storage');
  const hash = string(row.content_sha256, 'authority-evidence content hash', 64);
  if (!SHA256.test(hash)) throw new FamilyAuthorityApiError('The server returned an invalid authority-evidence content hash.');
  return {
    storage_reference: string(row.storage_reference, 'authority-evidence storage reference', 500),
    media_type: string(row.media_type, 'authority-evidence media type', 100),
    byte_size: integer(row.byte_size, 'authority-evidence byte size', 1),
    content_sha256: hash,
  };
}

export function parseAuthorityEvidence(value: unknown): AuthorityEvidence {
  const valueRow = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
  const hasObjectId = Boolean(valueRow && Object.prototype.hasOwnProperty.call(valueRow, 'evidence_object_id'));
  const row = exact(value, ['id', 'organization_id', 'family_id', 'evidence_kind', 'source_label', 'recorded_by_user_id', 'storage', ...(hasObjectId ? ['evidence_object_id'] : []), 'issued_at', 'captured_at', 'expires_at', 'created_at', 'version', 'lifecycle_status', 'effective_status', 'valid_now', 'evaluated_at', 'current_assessment'], 'authority evidence');
  const assessment = row.current_assessment === null ? null : parseAssessment(row.current_assessment);
  const evidence: AuthorityEvidence = {
    id: uuid(row.id, 'authority-evidence id'),
    organization_id: uuid(row.organization_id, 'authority-evidence organization'),
    family_id: uuid(row.family_id, 'authority-evidence family'),
    evidence_kind: oneOf(row.evidence_kind, EVIDENCE_KINDS, 'authority-evidence kind'),
    source_label: string(row.source_label, 'authority-evidence source label', 160),
    recorded_by_user_id: uuid(row.recorded_by_user_id, 'authority-evidence recorder'),
    storage: parseStorage(row.storage),
    ...(hasObjectId ? { evidence_object_id: row.evidence_object_id === null ? null : uuid(row.evidence_object_id, 'authority-evidence object') } : {}),
    issued_at: nullableTimestamp(row.issued_at, 'authority-evidence issue time'),
    captured_at: nullableTimestamp(row.captured_at, 'authority-evidence capture time'),
    expires_at: nullableTimestamp(row.expires_at, 'authority-evidence expiry time'),
    created_at: timestamp(row.created_at, 'authority-evidence creation time'),
    version: integer(row.version, 'authority-evidence version', 1),
    lifecycle_status: oneOf(row.lifecycle_status, EVIDENCE_LIFECYCLES, 'authority-evidence lifecycle'),
    effective_status: oneOf(row.effective_status, EVIDENCE_EFFECTIVE, 'authority-evidence effective status'),
    valid_now: bool(row.valid_now, 'authority-evidence validity'),
    evaluated_at: timestamp(row.evaluated_at, 'authority-evidence evaluation time'),
    current_assessment: assessment,
  };
  if (assessment && (assessment.evidence_id !== evidence.id || assessment.version_number !== evidence.version || assessment.decision !== evidence.lifecycle_status)) {
    throw new FamilyAuthorityApiError('The server returned an incoherent authority-evidence assessment.');
  }
  if (!assessment && (evidence.version !== 1 || evidence.lifecycle_status !== 'unreviewed')) throw new FamilyAuthorityApiError('The server returned an incoherent unreviewed authority-evidence asset.');
  if (evidence.valid_now !== (evidence.effective_status === 'reviewed')) throw new FamilyAuthorityApiError('The server returned an incoherent authority-evidence effective status.');
  return evidence;
}

export function parseAuthorityEvidenceObject(value: unknown): AuthorityEvidenceObject {
  const row = exact(value, ['id', 'organization_id', 'family_id', 'evidence_kind', 'version', 'lifecycle_status', 'valid_for_evidence', 'object_version', 'media_type', 'byte_size', 'content_sha256', 'original_filename', 'uploaded_by_user_id', 'created_at', 'current_assessment'], 'authority-evidence object');
  const hash = string(row.content_sha256, 'authority-evidence object content hash', 64);
  if (!SHA256.test(hash)) throw new FamilyAuthorityApiError('The server returned an invalid authority-evidence object content hash.');
  const item = exact(row.current_assessment, ['id', 'version_number', 'decision', 'scanner_engine', 'scanner_version', 'scanner_signature', 'reason_code', 'actor_user_id', 'created_at'], 'authority-evidence object assessment');
  const versionNumber = integer(item.version_number, 'authority-evidence object assessment version', 1);
  if (versionNumber !== 1 && versionNumber !== 2) throw new FamilyAuthorityApiError('The server returned an invalid authority-evidence object assessment version.');
  const decision = oneOf(item.decision, ['quarantined', 'clean', 'rejected'] as const, 'authority-evidence object assessment decision');
  const scannerEngine = nullableString(item.scanner_engine, 'authority-evidence object scan engine', 80);
  const scannerVersion = nullableString(item.scanner_version, 'authority-evidence object scan engine version', 160);
  const scannerSignature = nullableString(item.scanner_signature, 'authority-evidence object scanner signature', 160);
  const reasonCode = item.reason_code === null
    ? null
    : oneOf(item.reason_code, ['malware_detected', 'invalid_document'] as const, 'authority-evidence object reason code');
  if (
    (versionNumber === 1 && (decision !== 'quarantined' || scannerEngine || scannerVersion || scannerSignature || reasonCode))
    || (versionNumber === 2 && decision === 'quarantined')
    || (versionNumber === 2 && decision === 'clean' && (!scannerEngine || !scannerVersion || scannerSignature || reasonCode))
    || (versionNumber === 2 && decision === 'rejected' && (!scannerEngine || !scannerVersion || !reasonCode))
  ) {
    throw new FamilyAuthorityApiError('The server returned incoherent authority-evidence object scan provenance.');
  }
  const assessment = {
    id: uuid(item.id, 'authority-evidence object assessment id'),
    version_number: versionNumber as 1 | 2,
    decision,
    scanner_engine: scannerEngine,
    scanner_version: scannerVersion,
    scanner_signature: scannerSignature,
    reason_code: reasonCode,
    actor_user_id: uuid(item.actor_user_id, 'authority-evidence object assessment actor'),
    created_at: timestamp(item.created_at, 'authority-evidence object assessment creation time'),
  };
  const version = integer(row.version, 'authority-evidence object version', 1);
  const lifecycleStatus = oneOf(row.lifecycle_status, ['quarantined', 'clean', 'rejected'] as const, 'authority-evidence object lifecycle status');
  const validForEvidence = bool(row.valid_for_evidence, 'authority-evidence object evidence validity');
  const objectVersion = integer(row.object_version, 'authority-evidence object storage version', 1);
  if (version !== versionNumber || lifecycleStatus !== decision || validForEvidence !== (lifecycleStatus === 'clean') || objectVersion !== 1) {
    throw new FamilyAuthorityApiError('The server returned an incoherent authority-evidence object projection.');
  }
  return {
    id: uuid(row.id, 'authority-evidence object id'),
    organization_id: uuid(row.organization_id, 'authority-evidence object organization'),
    family_id: uuid(row.family_id, 'authority-evidence object family'),
    evidence_kind: oneOf(row.evidence_kind, EVIDENCE_KINDS, 'authority-evidence object kind'),
    version,
    lifecycle_status: lifecycleStatus,
    valid_for_evidence: validForEvidence,
    object_version: 1,
    media_type: oneOf(row.media_type, ['application/pdf', 'image/jpeg', 'image/png'] as const, 'authority-evidence object media type'),
    byte_size: integer(row.byte_size, 'authority-evidence object size', 1),
    content_sha256: hash,
    original_filename: nullableString(row.original_filename, 'authority-evidence object filename', 255),
    uploaded_by_user_id: uuid(row.uploaded_by_user_id, 'authority-evidence object uploader'),
    created_at: timestamp(row.created_at, 'authority-evidence object creation time'),
    current_assessment: assessment,
  };
}

function effectiveWindow(row: Record<string, unknown>, label: string): { effective_from: string; effective_until: string } {
  const effectiveFrom = timestamp(row.effective_from, `${label} effective start`);
  const effectiveUntil = timestamp(row.effective_until, `${label} effective end`);
  if (Date.parse(effectiveUntil) <= Date.parse(effectiveFrom)) {
    throw new FamilyAuthorityApiError(`The server returned an invalid ${label} effective window.`);
  }
  return { effective_from: effectiveFrom, effective_until: effectiveUntil };
}

function parsePersonVersionReference(value: unknown, label: string) {
  const row = exact(value, ['person_id', 'person_version_id'], label);
  return {
    person_id: uuid(row.person_id, `${label} person`),
    person_version_id: uuid(row.person_version_id, `${label} person version`),
  };
}

function parseReviewedGrantor(value: unknown) {
  const row = exact(value, ['person_id', 'person_version_id', 'authority_basis', 'basis_evidence_id', 'basis_evidence_assessment_id'], 'release-authorization grantor');
  return {
    person_id: uuid(row.person_id, 'release-authorization grantor person'),
    person_version_id: uuid(row.person_version_id, 'release-authorization grantor person version'),
    authority_basis: oneOf(row.authority_basis, AUTHORITY_BASES, 'release-authorization authority basis'),
    basis_evidence_id: uuid(row.basis_evidence_id, 'release-authorization evidence'),
    basis_evidence_assessment_id: uuid(row.basis_evidence_assessment_id, 'release-authorization evidence assessment'),
  };
}

function parseReleaseRuleScope(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new FamilyAuthorityApiError('The server returned an invalid release-rule scope.');
  if ((value as Record<string, unknown>).kind === 'all_recipients') {
    exact(value, ['kind'], 'all-recipients release-rule scope');
    return { kind: 'all_recipients' as const };
  }
  const row = exact(value, ['kind', 'person_id'], 'specific-person release-rule scope');
  if (row.kind !== 'specific_person') throw new FamilyAuthorityApiError('The server returned an invalid release-rule scope kind.');
  return { kind: 'specific_person' as const, person_id: uuid(row.person_id, 'release-rule scope person') };
}

function parseConsentScope(value: unknown): ConsentScope {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new FamilyAuthorityApiError('The server returned an invalid consent scope.');
  const kind = (value as Record<string, unknown>).kind;
  if (kind === 'policy') {
    exact(value, ['kind'], 'policy consent scope');
    return { kind };
  }
  if (kind === 'facility') {
    const row = exact(value, ['kind', 'facility_id'], 'facility consent scope');
    return { kind, facility_id: uuid(row.facility_id, 'consent scope facility') };
  }
  if (kind === 'named_activity') {
    const row = exact(value, ['kind', 'reference'], 'named-activity consent scope');
    return { kind, reference: string(row.reference, 'consent activity reference', 160) };
  }
  throw new FamilyAuthorityApiError('The server returned an invalid consent scope kind.');
}

export function parseReleaseAuthorization(value: unknown): ReleaseAuthorization {
  const row = exact(value, ['id', 'organization_id', 'family_id', 'child_id', 'recipient_person_id', 'verification_policy_code', 'grantor', 'effective_from', 'effective_until', 'version', 'revoked_at', 'revocation_reason_code', 'effective_status', 'effective_now', 'evaluated_at', 'authority_revision', 'created_at', 'updated_at'], 'release authorization');
  const revokedAt = nullableTimestamp(row.revoked_at, 'release-authorization revocation time');
  const reason = row.revocation_reason_code === null ? null : oneOf(row.revocation_reason_code, RELEASE_REVOCATION_REASONS, 'release-authorization revocation reason');
  if ((revokedAt === null) !== (reason === null)) throw new FamilyAuthorityApiError('The server returned an incoherent release-authorization revocation state.');
  const effectiveStatus = oneOf(row.effective_status, AUTHORITY_RECORD_EFFECTIVE_STATUSES, 'release-authorization effective status');
  const effectiveNow = bool(row.effective_now, 'release-authorization effective-now state');
  if ((effectiveStatus === 'revoked') !== (revokedAt !== null) || effectiveStatus === 'withdrawn' || effectiveNow !== (effectiveStatus === 'effective')) throw new FamilyAuthorityApiError('The server returned an incoherent release-authorization effective state.');
  return {
    id: uuid(row.id, 'release-authorization id'),
    organization_id: uuid(row.organization_id, 'release-authorization organization'),
    family_id: uuid(row.family_id, 'release-authorization family'),
    child_id: uuid(row.child_id, 'release-authorization child'),
    recipient_person_id: uuid(row.recipient_person_id, 'release-authorization recipient'),
    verification_policy_code: oneOf(row.verification_policy_code, VERIFICATION_POLICIES, 'release-authorization verification policy'),
    grantor: parseReviewedGrantor(row.grantor),
    ...effectiveWindow(row, 'release authorization'),
    version: integer(row.version, 'release-authorization version', 1),
    revoked_at: revokedAt,
    revocation_reason_code: reason,
    effective_status: effectiveStatus,
    effective_now: effectiveNow,
    evaluated_at: timestamp(row.evaluated_at, 'release-authorization evaluation time'),
    authority_revision: integer(row.authority_revision, 'release-authorization authority revision', 1),
    created_at: timestamp(row.created_at, 'release-authorization creation time'),
    updated_at: timestamp(row.updated_at, 'release-authorization update time'),
  };
}

export function parseReleaseRule(value: unknown): ReleaseRule {
  const row = exact(value, ['id', 'organization_id', 'family_id', 'child_id', 'rule_kind', 'scope', 'directing_person', 'authority_basis_code', 'basis_evidence_id', 'basis_evidence_assessment_id', 'safe_explanation_code', 'confidential_reason', 'effective_from', 'effective_until', 'version', 'revoked_at', 'revocation_reason_code', 'effective_status', 'effective_now', 'evaluated_at', 'authority_revision', 'created_at', 'updated_at'], 'release rule');
  const kind = oneOf(row.rule_kind, RELEASE_RULE_KINDS, 'release-rule kind');
  const scope = parseReleaseRuleScope(row.scope);
  const safeCode = oneOf(row.safe_explanation_code, ['release_restricted', 'supervision_required', 'named_recipient_only', 'manager_review_required'] as const, 'release-rule safe explanation');
  const expectedSafeCode = { deny: 'release_restricted', supervised_only: 'supervision_required', named_recipient_only: 'named_recipient_only', manager_review: 'manager_review_required' }[kind];
  if (safeCode !== expectedSafeCode || (kind === 'named_recipient_only' && scope.kind !== 'specific_person')) throw new FamilyAuthorityApiError('The server returned an incoherent release-rule projection.');
  const revokedAt = nullableTimestamp(row.revoked_at, 'release-rule revocation time');
  const reason = row.revocation_reason_code === null ? null : oneOf(row.revocation_reason_code, RELEASE_REVOCATION_REASONS, 'release-rule revocation reason');
  if ((revokedAt === null) !== (reason === null)) throw new FamilyAuthorityApiError('The server returned an incoherent release-rule revocation state.');
  const effectiveStatus = oneOf(row.effective_status, AUTHORITY_RECORD_EFFECTIVE_STATUSES, 'release-rule effective status');
  const effectiveNow = bool(row.effective_now, 'release-rule effective-now state');
  if ((effectiveStatus === 'revoked') !== (revokedAt !== null) || effectiveStatus === 'withdrawn' || effectiveNow !== (effectiveStatus === 'effective')) throw new FamilyAuthorityApiError('The server returned an incoherent release-rule effective state.');
  return {
    id: uuid(row.id, 'release-rule id'),
    organization_id: uuid(row.organization_id, 'release-rule organization'),
    family_id: uuid(row.family_id, 'release-rule family'),
    child_id: uuid(row.child_id, 'release-rule child'),
    rule_kind: kind,
    scope,
    directing_person: row.directing_person === null ? null : parsePersonVersionReference(row.directing_person, 'release-rule directing person'),
    authority_basis_code: oneOf(row.authority_basis_code, AUTHORITY_BASES, 'release-rule authority basis'),
    basis_evidence_id: uuid(row.basis_evidence_id, 'release-rule evidence'),
    basis_evidence_assessment_id: uuid(row.basis_evidence_assessment_id, 'release-rule evidence assessment'),
    safe_explanation_code: safeCode,
    confidential_reason: string(row.confidential_reason, 'release-rule confidential reason'),
    ...effectiveWindow(row, 'release rule'),
    version: integer(row.version, 'release-rule version', 1),
    revoked_at: revokedAt,
    revocation_reason_code: reason,
    effective_status: effectiveStatus,
    effective_now: effectiveNow,
    evaluated_at: timestamp(row.evaluated_at, 'release-rule evaluation time'),
    authority_revision: integer(row.authority_revision, 'release-rule authority revision', 1),
    created_at: timestamp(row.created_at, 'release-rule creation time'),
    updated_at: timestamp(row.updated_at, 'release-rule update time'),
  };
}

export function parseConsentPolicy(value: unknown): ConsentPolicyVersion {
  const row = exact(value, ['id', 'organization_id', 'purpose_code', 'version_number', 'title', 'content_text', 'content_reference', 'content_sha256', 'signer_authority_requirement', 'effective_from', 'effective_until', 'published_at'], 'consent policy');
  const id = uuid(row.id, 'consent-policy id');
  const versionNumber = integer(row.version_number, 'consent-policy version', 1);
  if (versionNumber > 2_147_483_647) throw new FamilyAuthorityApiError('The server returned an invalid consent-policy version.');
  const hash = string(row.content_sha256, 'consent-policy content hash', 64);
  if (!SHA256.test(hash)) throw new FamilyAuthorityApiError('The server returned an invalid consent-policy content hash.');
  const contentReference = string(row.content_reference, 'consent-policy content reference', 500);
  if (contentReference !== `/consent-policies/${id}`) throw new FamilyAuthorityApiError('The server returned an invalid consent-policy content reference.');
  return {
    id,
    organization_id: uuid(row.organization_id, 'consent-policy organization'),
    purpose_code: oneOf(row.purpose_code, CONSENT_PURPOSES, 'consent-policy purpose'),
    version_number: versionNumber,
    title: string(row.title, 'consent-policy title', 180),
    content_text: string(row.content_text, 'consent-policy content', 20_000),
    content_reference: contentReference,
    content_sha256: hash,
    signer_authority_requirement: oneOf(row.signer_authority_requirement, CONSENT_SIGNER_REQUIREMENTS, 'consent-policy signer requirement'),
    ...effectiveWindow(row, 'consent policy'),
    published_at: timestamp(row.published_at, 'consent-policy publication time'),
  };
}

export function parseChildConsentDecision(value: unknown): ChildConsentDecision {
  const row = exact(value, ['id', 'organization_id', 'family_id', 'child_id', 'purpose_code', 'policy_version_id', 'signer', 'evidence_id', 'evidence_assessment_id', 'decision', 'scope', 'effective_from', 'effective_until', 'version', 'withdrawn_at', 'withdrawal_reason_code', 'effective_status', 'effective_now', 'evaluated_at', 'authority_revision', 'created_at', 'updated_at'], 'child consent decision');
  const signerRow = exact(row.signer, ['person_id', 'person_version_id', 'authority_basis', 'authority_evidence_id', 'authority_evidence_assessment_id'], 'child-consent signer');
  const withdrawnAt = nullableTimestamp(row.withdrawn_at, 'child-consent withdrawal time');
  const reason = row.withdrawal_reason_code === null ? null : oneOf(row.withdrawal_reason_code, CONSENT_WITHDRAWAL_REASONS, 'child-consent withdrawal reason');
  if ((withdrawnAt === null) !== (reason === null)) throw new FamilyAuthorityApiError('The server returned an incoherent child-consent withdrawal state.');
  const effectiveStatus = oneOf(row.effective_status, AUTHORITY_RECORD_EFFECTIVE_STATUSES, 'child-consent effective status');
  const effectiveNow = bool(row.effective_now, 'child-consent effective-now state');
  if ((effectiveStatus === 'withdrawn') !== (withdrawnAt !== null) || effectiveStatus === 'revoked' || effectiveNow !== (effectiveStatus === 'effective')) throw new FamilyAuthorityApiError('The server returned an incoherent child-consent effective state.');
  const authorityEvidenceId = uuid(signerRow.authority_evidence_id, 'child-consent signer authority evidence');
  const decisionEvidenceId = uuid(row.evidence_id, 'child-consent evidence');
  if (authorityEvidenceId === decisionEvidenceId) throw new FamilyAuthorityApiError('The server returned a child-consent decision without distinct authority and consent evidence.');
  return {
    id: uuid(row.id, 'child-consent id'),
    organization_id: uuid(row.organization_id, 'child-consent organization'),
    family_id: uuid(row.family_id, 'child-consent family'),
    child_id: uuid(row.child_id, 'child-consent child'),
    purpose_code: oneOf(row.purpose_code, CONSENT_PURPOSES, 'child-consent purpose'),
    policy_version_id: uuid(row.policy_version_id, 'child-consent policy'),
    signer: {
      person_id: uuid(signerRow.person_id, 'child-consent signer person'),
      person_version_id: uuid(signerRow.person_version_id, 'child-consent signer person version'),
      authority_basis: oneOf(signerRow.authority_basis, AUTHORITY_BASES, 'child-consent signer authority basis'),
      authority_evidence_id: authorityEvidenceId,
      authority_evidence_assessment_id: uuid(signerRow.authority_evidence_assessment_id, 'child-consent signer authority evidence assessment'),
    },
    evidence_id: decisionEvidenceId,
    evidence_assessment_id: uuid(row.evidence_assessment_id, 'child-consent evidence assessment'),
    decision: oneOf(row.decision, ['granted', 'declined'] as const, 'child-consent decision'),
    scope: parseConsentScope(row.scope),
    ...effectiveWindow(row, 'child consent'),
    version: integer(row.version, 'child-consent version', 1),
    withdrawn_at: withdrawnAt,
    withdrawal_reason_code: reason,
    effective_status: effectiveStatus,
    effective_now: effectiveNow,
    evaluated_at: timestamp(row.evaluated_at, 'child-consent evaluation time'),
    authority_revision: integer(row.authority_revision, 'child-consent authority revision', 1),
    created_at: timestamp(row.created_at, 'child-consent creation time'),
    updated_at: timestamp(row.updated_at, 'child-consent update time'),
  };
}

function parseChildSummary(value: unknown): ChildAuthoritySummary {
  const row = exact(value, ['child_id', 'reviewed', 'authority_revision', 'release_authorizations', 'release_rules', 'consent_decisions'], 'child authority summary');
  const revision = integer(row.authority_revision, 'child authority revision');
  const reviewed = bool(row.reviewed, 'child authority review state');
  if (reviewed !== (revision > 0)) throw new FamilyAuthorityApiError('The server returned an incoherent child authority review state.');
  const childId = uuid(row.child_id, 'child authority child');
  const releaseAuthorizations = array(row.release_authorizations, 'release-authorization history', parseReleaseAuthorization);
  const releaseRules = array(row.release_rules, 'release-rule history', parseReleaseRule);
  const consentDecisions = array(row.consent_decisions, 'child-consent history', parseChildConsentDecision);
  if ([...releaseAuthorizations, ...releaseRules, ...consentDecisions].some((item) => item.child_id !== childId || item.authority_revision > revision)) {
    throw new FamilyAuthorityApiError('The server returned child authority history outside its canonical head.');
  }
  return { child_id: childId, reviewed, authority_revision: revision, release_authorizations: releaseAuthorizations, release_rules: releaseRules, consent_decisions: consentDecisions };
}

export function parseFamilyAuthorityWorkspace(value: unknown, organizationId: string, familyId: string): FamilyAuthorityWorkspaceRecord {
  const valueRow = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
  const hasObjects = Boolean(valueRow && Object.prototype.hasOwnProperty.call(valueRow, 'evidence_objects'));
  const row = exact(value, ['organization_id', 'family_id', 'generated_at', 'people', ...(hasObjects ? ['evidence_objects'] : []), 'evidence', 'children'], 'family-authority workspace');
  const workspace: FamilyAuthorityWorkspaceRecord = {
    organization_id: uuid(row.organization_id, 'family-authority organization'),
    family_id: uuid(row.family_id, 'family-authority family'),
    generated_at: timestamp(row.generated_at, 'family-authority generation time'),
    people: array(row.people, 'family-authority people', parseAuthorityPerson),
    evidence_objects: hasObjects ? array(row.evidence_objects, 'family-authority evidence objects', parseAuthorityEvidenceObject) : [],
    evidence: array(row.evidence, 'family-authority evidence', parseAuthorityEvidence),
    children: array(row.children, 'family-authority children', parseChildSummary),
  };
  if (workspace.organization_id !== organizationId.toLowerCase() || workspace.family_id !== familyId.toLowerCase()) throw new FamilyAuthorityApiError('The family-authority workspace crossed the authenticated record boundary.', 403);
  if (workspace.people.some((person) => person.organization_id !== workspace.organization_id || person.family_id !== workspace.family_id)
    || workspace.evidence.some((evidence) => evidence.organization_id !== workspace.organization_id || evidence.family_id !== workspace.family_id)
    || workspace.evidence_objects.some((object) => object.organization_id !== workspace.organization_id || object.family_id !== workspace.family_id)
    || workspace.children.some((child) => [
      ...child.release_authorizations,
      ...child.release_rules,
      ...child.consent_decisions,
    ].some((item) => item.organization_id !== workspace.organization_id || item.family_id !== workspace.family_id || item.child_id !== child.child_id))) {
    throw new FamilyAuthorityApiError('The family-authority workspace contains a cross-boundary record.', 403);
  }
  return workspace;
}

function detail(payload: unknown, status: number): { message: string; code: string | null } {
  const raw = payload && typeof payload === 'object' && !Array.isArray(payload) && 'detail' in payload ? (payload as { detail?: unknown }).detail : null;
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const code = typeof (raw as { code?: unknown }).code === 'string' ? String((raw as { code: string }).code) : null;
    const messages: Record<string, string> = {
      family_authority_unavailable: 'The family-authority kernel is not enabled on this database.',
      family_evidence_vault_unavailable: 'The private family-evidence vault is not enabled on this server. The document stays quarantined and no scan was committed.',
      operation_reused: 'This operation identifier was already used for different authority facts.',
      family_authority_access_revoked: 'This account no longer has authority-administration access.',
      authority_person_inactive: 'This authority person is no longer active.',
      authority_evidence_expired: 'This evidence expired before the assessment could be recorded.',
      authority_evidence_state_changed: 'This evidence changed in another action. Reload before continuing.',
      authority_evidence_not_reviewed: 'Only currently reviewed evidence can receive this terminal action.',
      replacement_evidence_not_current: 'Choose another current, reviewed replacement evidence record.',
      maker_checker_required: 'A different active owner or administrator must review this evidence. The uploader or recorder cannot approve their own submission.',
      evidence_object_required: 'This document evidence is not bound to a clean quarantined upload.',
      evidence_object_not_clean: 'The document has not completed its required safety scan.',
      document_evidence_requires_observed_review: 'Document evidence must be reviewed as document observed.',
      reported_evidence_cannot_be_document_observed: 'Attestations and staff observations must be reviewed as reported evidence.',
      configured_scanner_unavailable: 'The configured document scanner is unavailable. The document stays quarantined and can be scanned again.',
      malware_scanner_unavailable: 'The document scanner is unavailable. The document stays quarantined and can be scanned again.',
      malware_scanner_failed: 'The document scanner did not complete. The document stays quarantined and can be scanned again.',
      malware_scanner_definitions_unverified: 'The document scanner definitions could not be verified. The document stays quarantined and can be scanned again.',
      malware_scanner_definitions_stale: 'The document scanner definitions are stale. The document stays quarantined and can be scanned again after they are updated.',
      family_authority_activation_unavailable: 'Release and consent activation is not enabled on this database.',
      authority_revision_changed: 'Another authority decision changed this child. Reload and review the new revision before continuing.',
      authority_person_not_current: 'The selected authority person or identity version is no longer current.',
      authority_evidence_assessment_not_current: 'The selected evidence assessment is no longer the current reviewed assessment.',
      activation_maker_checker_required: 'The administrator activating this decision must be different from every administrator who reviewed its supporting evidence.',
      authority_basis_not_activatable: 'That evidence kind cannot activate the selected authority basis.',
      release_rule_kind_not_activatable: 'Only deny and manager-review release rules can be activated in this phase.',
      release_authorization_overlap: 'This recipient already has an overlapping release authorization for that child.',
      release_rule_overlap: 'An overlapping release rule already exists for that child and scope.',
      release_authorization_already_revoked: 'This release authorization was already revoked.',
      release_rule_already_revoked: 'This release rule was already revoked.',
      consent_policy_version_exists: 'That consent-policy purpose and version already exists.',
      consent_policy_overlap: 'This policy window overlaps another version for the same purpose.',
      consent_signer_requirement_not_activatable: 'That signer-authority requirement is not enabled in this phase.',
      consent_signer_requirement_mismatch: 'The selected signer authority does not satisfy this policy version.',
      consent_policy_window_mismatch: 'The child decision window must stay inside the selected policy window.',
      consent_decision_overlap: 'An overlapping consent decision already exists for this child, purpose, and scope.',
      consent_already_withdrawn: 'This consent decision was already withdrawn.',
      family_authority_activation_conflict: 'The authority decision conflicted with current canonical state. Reload before continuing.',
    };
    if (code && messages[code]) return { message: messages[code], code };
    return { message: code ? `CareSync rejected this authority change (${code}).` : `The authority request failed (${status}).`, code };
  }
  if (typeof raw === 'string') return { message: raw, code: null };
  if (Array.isArray(raw)) return { message: raw.map((item) => item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)).join('; '), code: null };
  if (status === 401) return { message: 'The secure session expired. Sign in again.', code: null };
  if (status === 403) return { message: 'Only an active organization owner or administrator can manage family authority.', code: null };
  return { message: `The authority request failed (${status}).`, code: null };
}

interface RequestFailurePolicy {
  readonly authoritativeNoCommitCodes?: readonly string[];
}

const ACTIVATION_NO_COMMIT: RequestFailurePolicy = {
  authoritativeNoCommitCodes: ['family_authority_unavailable', 'family_authority_activation_unavailable'],
};

async function request(path: string, organizationId: string, init: RequestInit = {}, signal?: AbortSignal, failurePolicy: RequestFailurePolicy = {}): Promise<unknown> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token) throw new FamilyAuthorityApiError('A secure CareSync session is required.', 401, null, undefined, 'preflight');
  const headers = addOrganizationHeader(new Headers({ Accept: 'application/json', Authorization: `Bearer ${token}`, ...init.headers }), organizationId);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, signal, cache: 'no-store' });
  } catch (caught) {
    throw new CommandOutcomeUnknownError('The connection ended before CareSync could confirm this authority command. Check its saved result; the exact command will not be resent automatically.', caught);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401) window.dispatchEvent(new Event('caresync-redesign:unauthorized'));
    if (response.status === 403) notifyAuthorizationDenied();
    const parsed = detail(payload, response.status);
    const error = new FamilyAuthorityApiError(parsed.message, response.status, parsed.code, payload, 'http');
    if (response.status === 503 && parsed.code && failurePolicy.authoritativeNoCommitCodes?.includes(parsed.code)) {
      throw new CommandRejectedBeforeCommitError(error.message, error);
    }
    if (response.status === 408 || response.status === 425 || response.status >= 500 && !(response.status === 503 && parsed.code === 'family_authority_unavailable')) {
      throw new CommandOutcomeUnknownError(error.message, error);
    }
    throw error;
  }
  if (response.status === 204) return null;
  try {
    return await response.json();
  } catch (caught) {
    throw new CommandOutcomeUnknownError('CareSync responded, but the authority result could not be verified. Check the saved result before continuing.', caught);
  }
}

function parseCommand<Resource>(value: unknown, parser: (resource: unknown) => Resource, expected: { organizationId: string; command: string; target: string }): AuthorityCommandResponse<Resource> {
  const row = exact(value, ['resource', 'receipt', 'replayed'], 'family-authority command response');
  const receipt = parseChildcareCommandReceipt(row.receipt);
  const resource = parser(row.resource);
  if (receipt.organizationId !== expected.organizationId.toLowerCase() || receipt.commandType !== expected.command || receipt.targetType !== expected.target || receipt.targetId !== (resource as { id: string }).id) {
    throw new FamilyAuthorityApiError('The authority receipt did not match the returned canonical resource.');
  }
  return { resource, receipt, replayed: bool(row.replayed, 'family-authority replay flag') };
}

export async function fetchFamilyAuthorityWorkspace(familyId: string, organizationId: string, signal?: AbortSignal): Promise<FamilyAuthorityWorkspaceRecord> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority`, organizationId, { headers: { 'Cache-Control': 'no-store', Pragma: 'no-cache' } }, signal);
  return parseFamilyAuthorityWorkspace(payload, organizationId, familyId);
}

export async function fetchConsentPolicies(organizationId: string, signal?: AbortSignal): Promise<ConsentPolicyVersion[]> {
  const payload = await request('/consent-policies', organizationId, { headers: { 'Cache-Control': 'no-store', Pragma: 'no-cache' } }, signal);
  const policies = array(payload, 'consent-policy list', parseConsentPolicy);
  if (policies.some((policy) => policy.organization_id !== organizationId.toLowerCase())) {
    throw new FamilyAuthorityApiError('The consent-policy list crossed the authenticated organization boundary.', 403);
  }
  return policies;
}

export async function createAuthorityPerson(familyId: string, input: AuthorityPersonCreateInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityPerson>> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/people`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal);
  return parseCommand(payload, parseAuthorityPerson, { organizationId, command: 'family.authority.person.create', target: 'authority_person' });
}

export async function replaceAuthorityPerson(familyId: string, personId: string, expectedVersion: number, facts: AuthorityPersonFacts, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityPerson>> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/people/${encodeURIComponent(personId)}/versions`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion, facts }) }, signal);
  return parseCommand(payload, parseAuthorityPerson, { organizationId, command: 'family.authority.person.replace', target: 'authority_person' });
}

export async function retireAuthorityPerson(familyId: string, personId: string, expectedVersion: number, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityPerson>> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/people/${encodeURIComponent(personId)}/retire`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion }) }, signal);
  return parseCommand(payload, parseAuthorityPerson, { organizationId, command: 'family.authority.person.retire', target: 'authority_person' });
}

export async function uploadAuthorityEvidenceObject(familyId: string, evidenceKind: AuthorityEvidenceKind, file: File, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityEvidenceObject>> {
  const body = new FormData();
  body.append('client_operation_id', clientOperationId);
  body.append('evidence_kind', evidenceKind);
  body.append('file', file, file.name);
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/evidence-objects`, organizationId, { method: 'POST', body }, signal);
  return parseCommand(payload, parseAuthorityEvidenceObject, { organizationId, command: 'family.authority.evidence_object.upload', target: 'authority_evidence_object' });
}

export async function scanAuthorityEvidenceObject(familyId: string, objectId: string, expectedVersion: number, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityEvidenceObject>> {
  const payload = await request(
    `/families/${encodeURIComponent(familyId)}/authority/evidence-objects/${encodeURIComponent(objectId)}/scan`,
    organizationId,
    { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion }) },
    signal,
    {
      authoritativeNoCommitCodes: [
        'configured_scanner_unavailable',
        'malware_scanner_unavailable',
        'malware_scanner_failed',
        'malware_scanner_definitions_unverified',
        'malware_scanner_definitions_stale',
        'family_authority_unavailable',
        'family_evidence_vault_unavailable',
      ],
    },
  );
  return parseCommand(payload, parseAuthorityEvidenceObject, { organizationId, command: 'family.authority.evidence_object.scan', target: 'authority_evidence_object' });
}

export async function fetchAuthorityEvidenceObjectContent(familyId: string, objectId: string, organizationId: string, signal?: AbortSignal): Promise<Blob> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token) throw new FamilyAuthorityApiError('A secure CareSync session is required.', 401, null, undefined, 'preflight');
  const headers = addOrganizationHeader(new Headers({ Authorization: `Bearer ${token}`, Accept: 'application/pdf,image/jpeg,image/png,application/octet-stream' }), organizationId);
  const response = await fetch(`${API_URL}/families/${encodeURIComponent(familyId)}/authority/evidence-objects/${encodeURIComponent(objectId)}/download`, { headers, signal, cache: 'no-store' });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const parsed = detail(payload, response.status);
    throw new FamilyAuthorityApiError(parsed.message, response.status, parsed.code, payload, 'http');
  }
  return response.blob();
}

export async function recordAuthorityEvidence(familyId: string, input: AuthorityEvidenceRecordInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityEvidence>> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/evidence`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal);
  return parseCommand(payload, parseAuthorityEvidence, { organizationId, command: 'family.authority.evidence.record', target: 'authority_evidence' });
}

async function assessEvidence(familyId: string, evidenceId: string, action: string, body: Record<string, unknown>, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<AuthorityEvidence>> {
  const payload = await request(`/families/${encodeURIComponent(familyId)}/authority/evidence/${encodeURIComponent(evidenceId)}/${action}`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...body }) }, signal);
  return parseCommand(payload, parseAuthorityEvidence, { organizationId, command: `family.authority.evidence.${action}`, target: 'authority_evidence' });
}

export const reviewAuthorityEvidence = (familyId: string, evidenceId: string, expectedVersion: number, assessedEpistemicStatus: AuthorityEvidenceEpistemicStatus, organizationId: string, clientOperationId: string, signal?: AbortSignal) => assessEvidence(familyId, evidenceId, 'review', { expected_version: expectedVersion, assessed_epistemic_status: assessedEpistemicStatus }, organizationId, clientOperationId, signal);
export const rejectAuthorityEvidence = (familyId: string, evidenceId: string, expectedVersion: number, reasonCode: AuthorityEvidenceRejectionReason, confidentialNote: string | null, organizationId: string, clientOperationId: string, signal?: AbortSignal) => assessEvidence(familyId, evidenceId, 'reject', { expected_version: expectedVersion, reason_code: reasonCode, confidential_note: confidentialNote }, organizationId, clientOperationId, signal);
export const invalidateAuthorityEvidence = (familyId: string, evidenceId: string, expectedVersion: number, reasonCode: AuthorityEvidenceInvalidationReason, confidentialNote: string | null, organizationId: string, clientOperationId: string, signal?: AbortSignal) => assessEvidence(familyId, evidenceId, 'invalidate', { expected_version: expectedVersion, reason_code: reasonCode, confidential_note: confidentialNote }, organizationId, clientOperationId, signal);
export const supersedeAuthorityEvidence = (familyId: string, evidenceId: string, expectedVersion: number, replacementEvidenceId: string, organizationId: string, clientOperationId: string, signal?: AbortSignal) => assessEvidence(familyId, evidenceId, 'supersede', { expected_version: expectedVersion, replacement_evidence_id: replacementEvidenceId }, organizationId, clientOperationId, signal);

export async function grantReleaseAuthorization(childId: string, input: ReleaseAuthorizationGrantInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ReleaseAuthorization>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/release-authorizations`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseReleaseAuthorization, { organizationId, command: 'child.release.authorization.grant', target: 'release_authorization' });
}

export async function revokeReleaseAuthorization(childId: string, authorizationId: string, expectedVersion: number, expectedAuthorityRevision: number, reasonCode: ReleaseAuthorization['revocation_reason_code'] & string, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ReleaseAuthorization>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/release-authorizations/${encodeURIComponent(authorizationId)}/revoke`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion, expected_authority_revision: expectedAuthorityRevision, reason_code: reasonCode }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseReleaseAuthorization, { organizationId, command: 'child.release.authorization.revoke', target: 'release_authorization' });
}

export async function createReleaseRule(childId: string, input: ReleaseRuleCreateInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ReleaseRule>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/release-rules`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseReleaseRule, { organizationId, command: 'child.release.rule.create', target: 'release_rule' });
}

export async function revokeReleaseRule(childId: string, ruleId: string, expectedVersion: number, expectedAuthorityRevision: number, reasonCode: ReleaseRule['revocation_reason_code'] & string, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ReleaseRule>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/release-rules/${encodeURIComponent(ruleId)}/revoke`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion, expected_authority_revision: expectedAuthorityRevision, reason_code: reasonCode }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseReleaseRule, { organizationId, command: 'child.release.rule.revoke', target: 'release_rule' });
}

export async function publishConsentPolicy(input: ConsentPolicyPublishInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ConsentPolicyVersion>> {
  const payload = await request('/consent-policies', organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseConsentPolicy, { organizationId, command: 'organization.consent.policy.publish', target: 'consent' });
}

export async function recordChildConsent(childId: string, input: ChildConsentRecordInput, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ChildConsentDecision>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/consents`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, ...input }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseChildConsentDecision, { organizationId, command: 'child.consent.record', target: 'consent' });
}

export async function withdrawChildConsent(childId: string, decisionId: string, expectedVersion: number, expectedAuthorityRevision: number, reasonCode: ChildConsentDecision['withdrawal_reason_code'] & string, organizationId: string, clientOperationId: string, signal?: AbortSignal): Promise<AuthorityCommandResponse<ChildConsentDecision>> {
  const payload = await request(`/children/${encodeURIComponent(childId)}/consents/${encodeURIComponent(decisionId)}/withdraw`, organizationId, { method: 'POST', body: JSON.stringify({ client_operation_id: clientOperationId, expected_version: expectedVersion, expected_authority_revision: expectedAuthorityRevision, reason_code: reasonCode }) }, signal, ACTIVATION_NO_COMMIT);
  return parseCommand(payload, parseChildConsentDecision, { organizationId, command: 'child.consent.withdraw', target: 'consent' });
}
