export type AuthorityPersonStatus = 'active' | 'retired';
export type AuthorityRelationshipKind =
  | 'parent'
  | 'legal_guardian'
  | 'foster_parent'
  | 'grandparent'
  | 'adult_sibling'
  | 'aunt_uncle'
  | 'family_friend'
  | 'caseworker'
  | 'transport_provider'
  | 'other';

export type AuthorityEvidenceKind =
  | 'identity_document'
  | 'custody_document'
  | 'court_order'
  | 'guardian_attestation'
  | 'signed_consent'
  | 'signed_release_delegation'
  | 'staff_witness'
  | 'other_document';

export type AuthorityEvidenceLifecycleStatus =
  | 'unreviewed'
  | 'reviewed'
  | 'rejected'
  | 'invalidated'
  | 'superseded';

export type AuthorityEvidenceEffectiveStatus = AuthorityEvidenceLifecycleStatus | 'expired';
export type AuthorityEvidenceAssessmentDecision = 'reviewed' | 'rejected' | 'invalidated' | 'superseded';
export type AuthorityEvidenceEpistemicStatus = 'reported' | 'document_observed';
export type AuthorityEvidenceRejectionReason =
  | 'insufficient_evidence'
  | 'information_mismatch'
  | 'unreadable'
  | 'unsupported'
  | 'entered_in_error'
  | 'other';
export type AuthorityEvidenceInvalidationReason =
  | 'authority_changed'
  | 'document_revoked'
  | 'information_corrected'
  | 'entered_in_error'
  | 'other';

export type AuthorityPersonSource =
  | { kind: 'manual' }
  | { kind: 'guardian'; guardian_id: string }
  | { kind: 'emergency_contact'; emergency_contact_id: string };

export interface AuthorityPersonFacts {
  first_name: string;
  middle_name: string | null;
  last_name: string;
  preferred_name: string | null;
  relationship_kind: AuthorityRelationshipKind;
  relationship_detail: string | null;
  email: string | null;
  primary_phone: string | null;
}

export interface AuthorityPersonVersion {
  id: string;
  person_id: string;
  version_number: number;
  facts: AuthorityPersonFacts;
  closed_at: string | null;
  created_at: string;
}

export interface AuthorityPerson {
  id: string;
  organization_id: string;
  family_id: string;
  version: number;
  status: AuthorityPersonStatus;
  source: AuthorityPersonSource;
  current_version: AuthorityPersonVersion | null;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthorityEvidenceStorage {
  storage_reference: string;
  media_type: string;
  byte_size: number;
  content_sha256: string;
}

export interface AuthorityEvidenceAssessment {
  id: string;
  evidence_id: string;
  version_number: 2 | 3;
  decision: AuthorityEvidenceAssessmentDecision;
  assessed_epistemic_status: AuthorityEvidenceEpistemicStatus | null;
  reason_code: string | null;
  confidential_note: string | null;
  superseded_by_evidence_id: string | null;
  actor_user_id: string;
  created_at: string;
}

export interface AuthorityEvidence {
  id: string;
  organization_id: string;
  family_id: string;
  evidence_kind: AuthorityEvidenceKind;
  source_label: string;
  recorded_by_user_id: string;
  storage: AuthorityEvidenceStorage | null;
  evidence_object_id?: string | null;
  issued_at: string | null;
  captured_at: string | null;
  expires_at: string | null;
  created_at: string;
  version: number;
  lifecycle_status: AuthorityEvidenceLifecycleStatus;
  effective_status: AuthorityEvidenceEffectiveStatus;
  valid_now: boolean;
  evaluated_at: string;
  current_assessment: AuthorityEvidenceAssessment | null;
}

/**
 * Isolated adapter shape for the 0029 evidence-vault slice. The parser is the
 * only place that should change if the backend renames one of these fields.
 */
export interface AuthorityEvidenceObject {
  id: string;
  organization_id: string;
  family_id: string;
  evidence_kind: AuthorityEvidenceKind;
  version: number;
  lifecycle_status: 'quarantined' | 'clean' | 'rejected';
  valid_for_evidence: boolean;
  object_version: 1;
  media_type: 'application/pdf' | 'image/jpeg' | 'image/png';
  byte_size: number;
  content_sha256: string;
  original_filename: string | null;
  uploaded_by_user_id: string;
  created_at: string;
  current_assessment: AuthorityEvidenceObjectAssessment;
}

export interface AuthorityEvidenceObjectAssessment {
  id: string;
  version_number: 1 | 2;
  decision: 'quarantined' | 'clean' | 'rejected';
  scanner_engine: string | null;
  scanner_version: string | null;
  scanner_signature: string | null;
  reason_code: 'malware_detected' | 'invalid_document' | null;
  actor_user_id: string;
  created_at: string;
}

export interface ChildAuthoritySummary {
  child_id: string;
  reviewed: boolean;
  authority_revision: number;
  release_authorizations: ReleaseAuthorization[];
  release_rules: ReleaseRule[];
  consent_decisions: ChildConsentDecision[];
}

export type ReviewedAuthorityBasis =
  | 'guardian_record'
  | 'reviewed_custody_evidence'
  | 'reviewed_delegation_evidence'
  | 'other_reviewed_authority';
export type VerificationPolicyCode =
  | 'government_photo_id'
  | 'documented_familiarity'
  | 'government_photo_id_or_documented_familiarity'
  | 'government_photo_id_and_secondary_check';
export type ReleaseRevocationReason =
  | 'authority_withdrawn'
  | 'safety_change'
  | 'superseded'
  | 'entered_in_error';
export type AuthorityRecordEffectiveStatus =
  | 'scheduled'
  | 'effective'
  | 'expired'
  | 'revoked'
  | 'withdrawn'
  | 'supporting_evidence_unavailable';
export type ReleaseRuleKind = 'deny' | 'supervised_only' | 'named_recipient_only' | 'manager_review';
export type ReleaseSafeExplanationCode =
  | 'release_restricted'
  | 'supervision_required'
  | 'named_recipient_only'
  | 'manager_review_required';
export type ReleaseRuleScope =
  | { kind: 'all_recipients' }
  | { kind: 'specific_person'; person_id: string };

export interface AuthorityPersonVersionReference {
  person_id: string;
  person_version_id: string;
}

export interface ReviewedGrantorReference extends AuthorityPersonVersionReference {
  authority_basis: ReviewedAuthorityBasis;
  basis_evidence_id: string;
  basis_evidence_assessment_id: string;
}

export interface ReleaseAuthorization {
  id: string;
  organization_id: string;
  family_id: string;
  child_id: string;
  recipient_person_id: string;
  verification_policy_code: VerificationPolicyCode;
  grantor: ReviewedGrantorReference;
  effective_from: string;
  effective_until: string;
  version: number;
  revoked_at: string | null;
  revocation_reason_code: ReleaseRevocationReason | null;
  effective_status: AuthorityRecordEffectiveStatus;
  effective_now: boolean;
  evaluated_at: string;
  authority_revision: number;
  created_at: string;
  updated_at: string;
}

export interface ReleaseRule {
  id: string;
  organization_id: string;
  family_id: string;
  child_id: string;
  rule_kind: ReleaseRuleKind;
  scope: ReleaseRuleScope;
  directing_person: AuthorityPersonVersionReference | null;
  authority_basis_code: ReviewedAuthorityBasis;
  basis_evidence_id: string;
  basis_evidence_assessment_id: string;
  safe_explanation_code: ReleaseSafeExplanationCode;
  confidential_reason: string;
  effective_from: string;
  effective_until: string;
  version: number;
  revoked_at: string | null;
  revocation_reason_code: ReleaseRevocationReason | null;
  effective_status: AuthorityRecordEffectiveStatus;
  effective_now: boolean;
  evaluated_at: string;
  authority_revision: number;
  created_at: string;
  updated_at: string;
}

export type ConsentPurposeCode =
  | 'off_site_activity'
  | 'emergency_health_care'
  | 'medication_administration'
  | 'internal_media'
  | 'external_media'
  | 'marketing'
  | 'research'
  | 'optional_service'
  | 'information_sharing';
export type ConsentSignerAuthorityRequirement =
  | 'guardian_record'
  | 'legal_decision_maker'
  | 'specific_reviewed_authority';
export type ConsentDecision = 'granted' | 'declined';
export type ConsentWithdrawalReason = 'signer_withdrew' | 'authority_changed' | 'superseded' | 'entered_in_error';
export type ConsentScope =
  | { kind: 'policy' }
  | { kind: 'facility'; facility_id: string }
  | { kind: 'named_activity'; reference: string };

export interface ConsentSignerReference extends AuthorityPersonVersionReference {
  authority_basis: ReviewedAuthorityBasis;
  authority_evidence_id: string;
  authority_evidence_assessment_id: string;
}

export interface ConsentPolicyVersion {
  id: string;
  organization_id: string;
  purpose_code: ConsentPurposeCode;
  version_number: number;
  title: string;
  content_text: string;
  content_reference: string;
  content_sha256: string;
  signer_authority_requirement: ConsentSignerAuthorityRequirement;
  effective_from: string;
  effective_until: string;
  published_at: string;
}

export interface ChildConsentDecision {
  id: string;
  organization_id: string;
  family_id: string;
  child_id: string;
  purpose_code: ConsentPurposeCode;
  policy_version_id: string;
  signer: ConsentSignerReference;
  evidence_id: string;
  evidence_assessment_id: string;
  decision: ConsentDecision;
  scope: ConsentScope;
  effective_from: string;
  effective_until: string;
  version: number;
  withdrawn_at: string | null;
  withdrawal_reason_code: ConsentWithdrawalReason | null;
  effective_status: AuthorityRecordEffectiveStatus;
  effective_now: boolean;
  evaluated_at: string;
  authority_revision: number;
  created_at: string;
  updated_at: string;
}

export interface FamilyAuthorityWorkspaceRecord {
  organization_id: string;
  family_id: string;
  generated_at: string;
  people: AuthorityPerson[];
  evidence_objects: AuthorityEvidenceObject[];
  evidence: AuthorityEvidence[];
  children: ChildAuthoritySummary[];
}

export interface AuthorityCommandResponse<Resource> {
  resource: Resource;
  receipt: import('../../api/childcareCommandReceipt').ChildcareCommandReceipt;
  replayed: boolean;
}

export interface AuthorityPersonCreateInput {
  source: AuthorityPersonSource;
  facts: AuthorityPersonFacts;
}

export interface AuthorityEvidenceRecordInput {
  evidence_kind: AuthorityEvidenceKind;
  source_label: string;
  evidence_object_id?: string;
  issued_at: string | null;
  captured_at: string | null;
  expires_at: string | null;
}

export interface ReleaseAuthorizationGrantInput {
  expected_authority_revision: number;
  recipient_person_id: string;
  verification_policy_code: VerificationPolicyCode;
  grantor: ReviewedGrantorReference;
  effective_from: string;
  effective_until: string;
}

export interface ReleaseRuleCreateInput {
  expected_authority_revision: number;
  rule_kind: ReleaseRuleKind;
  scope: ReleaseRuleScope;
  directing_person: AuthorityPersonVersionReference | null;
  authority_basis_code: ReviewedAuthorityBasis;
  basis_evidence_id: string;
  basis_evidence_assessment_id: string;
  confidential_reason: string;
  effective_from: string;
  effective_until: string;
}

export interface ConsentPolicyPublishInput {
  purpose_code: ConsentPurposeCode;
  version_number: number;
  title: string;
  content_text: string;
  signer_authority_requirement: ConsentSignerAuthorityRequirement;
  effective_from: string;
  effective_until: string;
}

export interface ChildConsentRecordInput {
  expected_authority_revision: number;
  purpose_code: ConsentPurposeCode;
  policy_version_id: string;
  signer: ConsentSignerReference;
  evidence_id: string;
  evidence_assessment_id: string;
  decision: ConsentDecision;
  scope: ConsentScope;
  effective_from: string;
  effective_until: string;
}
