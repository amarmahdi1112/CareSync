"""Strict API contracts for the 0029A family-authority kernel.

These schemas deliberately stop at the admin-only persistence boundary.  Release
context, checkout and override contracts belong to later milestones.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

AuthorityPersonStatus = Literal["active", "retired"]
RelationshipKind = Literal[
    "parent",
    "legal_guardian",
    "foster_parent",
    "grandparent",
    "adult_sibling",
    "aunt_uncle",
    "family_friend",
    "caseworker",
    "transport_provider",
    "other",
]
EvidenceKind = Literal[
    "identity_document",
    "custody_document",
    "court_order",
    "guardian_attestation",
    "signed_consent",
    "signed_release_delegation",
    "staff_witness",
    "other_document",
]
EvidenceAssessmentDecision = Literal[
    "reviewed",
    "rejected",
    "invalidated",
    "superseded",
]
EvidenceAssessedEpistemicStatus = Literal["reported", "document_observed"]
EvidenceLifecycleStatus = Literal[
    "unreviewed",
    "reviewed",
    "rejected",
    "invalidated",
    "superseded",
]
EvidenceEffectiveStatus = Literal[
    "unreviewed",
    "reviewed",
    "rejected",
    "invalidated",
    "superseded",
    "expired",
]
AuthorityRecordEffectiveStatus = Literal[
    "scheduled",
    "effective",
    "expired",
    "revoked",
    "withdrawn",
    "supporting_evidence_unavailable",
]
EvidenceObjectLifecycleStatus = Literal["quarantined", "clean", "rejected"]
EvidenceObjectAssessmentDecision = Literal["quarantined", "clean", "rejected"]
EvidenceRejectionReasonCode = Literal[
    "insufficient_evidence",
    "information_mismatch",
    "unreadable",
    "unsupported",
    "entered_in_error",
    "other",
]
EvidenceInvalidationReasonCode = Literal[
    "authority_changed",
    "document_revoked",
    "information_corrected",
    "entered_in_error",
    "other",
]
EvidenceAssessmentReasonCode = Literal[
    "insufficient_evidence",
    "information_mismatch",
    "unreadable",
    "unsupported",
    "authority_changed",
    "document_revoked",
    "information_corrected",
    "entered_in_error",
    "other",
    "superseded",
]
VerificationPolicyCode = Literal[
    "government_photo_id",
    "documented_familiarity",
    "government_photo_id_or_documented_familiarity",
    "government_photo_id_and_secondary_check",
]
ReviewedAuthorityBasis = Literal[
    "guardian_record",
    "reviewed_custody_evidence",
    "reviewed_delegation_evidence",
    "other_reviewed_authority",
]
ReleaseRuleKind = Literal[
    "deny",
    "supervised_only",
    "named_recipient_only",
    "manager_review",
]
ReleaseSafeExplanationCode = Literal[
    "release_restricted",
    "supervision_required",
    "named_recipient_only",
    "manager_review_required",
]
ReleaseRevocationReasonCode = Literal[
    "authority_withdrawn",
    "safety_change",
    "superseded",
    "entered_in_error",
]
ConsentPurposeCode = Literal[
    "off_site_activity",
    "emergency_health_care",
    "medication_administration",
    "internal_media",
    "external_media",
    "marketing",
    "research",
    "optional_service",
    "information_sharing",
]
ConsentSignerAuthorityRequirement = Literal[
    "guardian_record",
    "legal_decision_maker",
    "specific_reviewed_authority",
]
ConsentDecision = Literal["granted", "declined"]
ConsentWithdrawalReasonCode = Literal[
    "signer_withdrew",
    "authority_changed",
    "superseded",
    "entered_in_error",
]
FamilyAuthorityCommandType = Literal[
    "family.authority.person.create",
    "family.authority.person.replace",
    "family.authority.person.retire",
    "family.authority.evidence.record",
    "family.authority.evidence.review",
    "family.authority.evidence.reject",
    "family.authority.evidence.invalidate",
    "family.authority.evidence.supersede",
    "family.authority.evidence_object.upload",
    "family.authority.evidence_object.scan",
    "child.release.authorization.grant",
    "child.release.authorization.revoke",
    "child.release.rule.create",
    "child.release.rule.revoke",
    "organization.consent.policy.publish",
    "child.consent.record",
    "child.consent.withdraw",
]
FamilyAuthorityTargetType = Literal[
    "authority_person",
    "authority_evidence",
    "authority_evidence_object",
    "release_authorization",
    "release_rule",
    "consent",
]

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MEDIA_TYPE_PATTERN = r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
OPAQUE_STORAGE_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$"
MAX_EVIDENCE_BYTE_SIZE = 50 * 1024 * 1024
MAX_POLICY_VERSION_NUMBER = 2_147_483_647


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
Sha256Hex = Annotated[str, Field(pattern=SHA256_PATTERN)]


class AuthoritySchema(BaseModel):
    """Shared fail-closed parsing for requests and projections."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class EffectiveWindowSchema(AuthoritySchema):
    effective_from: UtcDateTime
    effective_until: UtcDateTime

    @model_validator(mode="after")
    def require_finite_half_open_window(self):
        if self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be later than effective_from")
        return self


class ManualAuthorityPersonSource(AuthoritySchema):
    kind: Literal["manual"]


class GuardianAuthorityPersonSource(AuthoritySchema):
    kind: Literal["guardian"]
    guardian_id: UUID


class EmergencyContactAuthorityPersonSource(AuthoritySchema):
    kind: Literal["emergency_contact"]
    emergency_contact_id: UUID


AuthorityPersonSource = Annotated[
    ManualAuthorityPersonSource
    | GuardianAuthorityPersonSource
    | EmergencyContactAuthorityPersonSource,
    Field(discriminator="kind"),
]


class AuthorityPersonFacts(AuthoritySchema):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, min_length=1, max_length=100)
    relationship_kind: RelationshipKind
    relationship_detail: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=1, max_length=320)
    primary_phone: str | None = Field(default=None, min_length=1, max_length=30)

    @model_validator(mode="after")
    def require_exact_relationship_detail(self):
        if self.relationship_kind == "other" and self.relationship_detail is None:
            raise ValueError("relationship_detail is required for other relationships")
        if self.relationship_kind != "other" and self.relationship_detail is not None:
            raise ValueError("relationship_detail is only allowed for other relationships")
        return self


class EvidenceStorage(AuthoritySchema):
    storage_reference: str = Field(
        min_length=1,
        max_length=500,
        pattern=OPAQUE_STORAGE_REFERENCE_PATTERN,
    )
    media_type: str = Field(min_length=3, max_length=100, pattern=MEDIA_TYPE_PATTERN)
    byte_size: int = Field(gt=0, le=MAX_EVIDENCE_BYTE_SIZE)
    content_sha256: Sha256Hex

    @field_validator("storage_reference")
    @classmethod
    def require_opaque_storage_reference(cls, value: str) -> str:
        if any(segment in {"", ".", ".."} for segment in value.split("/")):
            raise ValueError("storage_reference must be an opaque relative reference")
        return value


class AuthorityPersonVersionReference(AuthoritySchema):
    person_id: UUID
    person_version_id: UUID


class ReviewedGrantorReference(AuthorityPersonVersionReference):
    authority_basis: ReviewedAuthorityBasis
    basis_evidence_id: UUID
    basis_evidence_assessment_id: UUID


class ConsentSignerReference(AuthorityPersonVersionReference):
    authority_basis: ReviewedAuthorityBasis
    authority_evidence_id: UUID
    authority_evidence_assessment_id: UUID


class AllRecipientsReleaseRuleScope(AuthoritySchema):
    kind: Literal["all_recipients"]


class SpecificPersonReleaseRuleScope(AuthoritySchema):
    kind: Literal["specific_person"]
    person_id: UUID


ReleaseRuleScope = Annotated[
    AllRecipientsReleaseRuleScope | SpecificPersonReleaseRuleScope,
    Field(discriminator="kind"),
]


class PolicyConsentScope(AuthoritySchema):
    kind: Literal["policy"]


class FacilityConsentScope(AuthoritySchema):
    kind: Literal["facility"]
    facility_id: UUID


class NamedActivityConsentScope(AuthoritySchema):
    kind: Literal["named_activity"]
    reference: str = Field(min_length=1, max_length=160)


ConsentScope = Annotated[
    PolicyConsentScope | FacilityConsentScope | NamedActivityConsentScope,
    Field(discriminator="kind"),
]


class AuthorityPersonCreateRequest(AuthoritySchema):
    client_operation_id: UUID
    source: AuthorityPersonSource
    facts: AuthorityPersonFacts


class AuthorityPersonReplaceRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    facts: AuthorityPersonFacts


class AuthorityPersonRetireRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)


class AuthorityEvidenceRecordRequest(AuthoritySchema):
    client_operation_id: UUID
    evidence_kind: EvidenceKind
    source_label: str = Field(min_length=1, max_length=160)
    issued_at: UtcDateTime | None = None
    captured_at: UtcDateTime | None = None
    expires_at: UtcDateTime | None = None
    evidence_object_id: UUID | None = None

    @model_validator(mode="after")
    def require_coherent_evidence_expiry(self):
        if (
            self.issued_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.issued_at
        ):
            raise ValueError("expires_at must be later than issued_at")
        document_kinds = {
            "identity_document",
            "custody_document",
            "court_order",
            "signed_consent",
            "signed_release_delegation",
            "other_document",
        }
        requires_object = self.evidence_kind in document_kinds
        if requires_object != (self.evidence_object_id is not None):
            raise ValueError(
                "document evidence requires one evidence_object_id; "
                "attestation and witness evidence forbid it"
            )
        return self


class AuthorityEvidenceObjectScanRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: Literal[1]


class AuthorityEvidenceReviewRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    assessed_epistemic_status: EvidenceAssessedEpistemicStatus


class AuthorityEvidenceRejectRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    reason_code: EvidenceRejectionReasonCode
    confidential_note: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_exact_rejection_reason(self):
        if (self.reason_code == "other") != (self.confidential_note is not None):
            raise ValueError("confidential_note is required exactly when reason_code is other")
        return self


class AuthorityEvidenceInvalidateRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    reason_code: EvidenceInvalidationReasonCode
    confidential_note: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_exact_invalidation_reason(self):
        if (self.reason_code == "other") != (self.confidential_note is not None):
            raise ValueError("confidential_note is required exactly when reason_code is other")
        return self


class AuthorityEvidenceSupersedeRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    replacement_evidence_id: UUID


class ReleaseAuthorizationGrantRequest(EffectiveWindowSchema):
    client_operation_id: UUID
    expected_authority_revision: int = Field(ge=0)
    recipient_person_id: UUID
    verification_policy_code: VerificationPolicyCode
    grantor: ReviewedGrantorReference


class ReleaseAuthorizationRevokeRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    expected_authority_revision: int = Field(ge=1)
    reason_code: ReleaseRevocationReasonCode


class ReleaseRuleCreateRequest(EffectiveWindowSchema):
    client_operation_id: UUID
    expected_authority_revision: int = Field(ge=0)
    rule_kind: ReleaseRuleKind
    scope: ReleaseRuleScope
    directing_person: AuthorityPersonVersionReference | None = None
    authority_basis_code: ReviewedAuthorityBasis
    basis_evidence_id: UUID
    basis_evidence_assessment_id: UUID
    confidential_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_named_recipient_scope(self):
        if self.rule_kind == "named_recipient_only" and self.scope.kind != "specific_person":
            raise ValueError("named_recipient_only requires a specific_person scope")
        return self


class ReleaseRuleRevokeRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    expected_authority_revision: int = Field(ge=1)
    reason_code: ReleaseRevocationReasonCode


class ConsentPolicyPublishRequest(EffectiveWindowSchema):
    client_operation_id: UUID
    purpose_code: ConsentPurposeCode
    version_number: int = Field(ge=1, le=MAX_POLICY_VERSION_NUMBER)
    title: str = Field(min_length=1, max_length=180)
    content_text: str = Field(min_length=1, max_length=20_000)
    signer_authority_requirement: ConsentSignerAuthorityRequirement


class ChildConsentRecordRequest(EffectiveWindowSchema):
    client_operation_id: UUID
    expected_authority_revision: int = Field(ge=0)
    purpose_code: ConsentPurposeCode
    policy_version_id: UUID
    signer: ConsentSignerReference
    evidence_id: UUID
    evidence_assessment_id: UUID
    decision: ConsentDecision
    scope: ConsentScope

    @model_validator(mode="after")
    def require_separate_decision_and_signer_authority_evidence(self):
        if self.evidence_id == self.signer.authority_evidence_id:
            raise ValueError("decision evidence and signer-authority evidence must be distinct")
        return self


class ChildConsentWithdrawRequest(AuthoritySchema):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    expected_authority_revision: int = Field(ge=1)
    reason_code: ConsentWithdrawalReasonCode


class AuthorityPersonVersionResponse(AuthoritySchema):
    id: UUID
    person_id: UUID
    version_number: int = Field(ge=1)
    facts: AuthorityPersonFacts
    closed_at: UtcDateTime | None
    created_at: UtcDateTime


class AuthorityPersonResponse(AuthoritySchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    version: int = Field(ge=1)
    status: AuthorityPersonStatus
    source: AuthorityPersonSource
    current_version: AuthorityPersonVersionResponse | None
    retired_at: UtcDateTime | None
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def require_exact_person_lifecycle(self):
        if self.status == "active" and (
            self.current_version is None or self.retired_at is not None
        ):
            raise ValueError("active people require a current version and no retirement time")
        if self.status == "retired" and (
            self.current_version is not None or self.retired_at is None
        ):
            raise ValueError("retired people require a retirement time and no current version")
        if self.current_version is not None and (
            self.current_version.person_id != self.id
            or self.current_version.version_number != self.version
            or self.current_version.closed_at is not None
        ):
            raise ValueError("current person version must be exact and open")
        return self


class AuthorityEvidenceAssessmentResponse(AuthoritySchema):
    id: UUID
    evidence_id: UUID
    version_number: Literal[2, 3]
    decision: EvidenceAssessmentDecision
    assessed_epistemic_status: EvidenceAssessedEpistemicStatus | None
    reason_code: EvidenceAssessmentReasonCode | None
    confidential_note: str | None = Field(default=None, min_length=1, max_length=1000)
    superseded_by_evidence_id: UUID | None
    actor_user_id: UUID
    created_at: UtcDateTime

    @model_validator(mode="after")
    def require_exact_assessment_state(self):
        expected_version = 2 if self.decision in {"reviewed", "rejected"} else 3
        if self.version_number != expected_version:
            raise ValueError("assessment version does not match its lifecycle decision")
        if self.decision == "reviewed":
            if (
                self.assessed_epistemic_status is None
                or self.reason_code is not None
                or self.confidential_note is not None
                or self.superseded_by_evidence_id is not None
            ):
                raise ValueError("reviewed assessment has invalid provenance")
            return self
        if self.assessed_epistemic_status is not None or self.reason_code is None:
            raise ValueError("terminal assessment requires a reason and no epistemic status")
        if (self.reason_code == "other") != (self.confidential_note is not None):
            raise ValueError("confidential_note is required exactly when reason_code is other")
        if (self.decision == "superseded") != (self.superseded_by_evidence_id is not None):
            raise ValueError("supersession requires exactly one replacement evidence asset")
        if self.decision == "superseded" and self.reason_code != "superseded":
            raise ValueError("superseded assessment requires its derived reason code")
        rejection_reasons = {
            "insufficient_evidence",
            "information_mismatch",
            "unreadable",
            "unsupported",
            "entered_in_error",
            "other",
        }
        invalidation_reasons = {
            "authority_changed",
            "document_revoked",
            "information_corrected",
            "entered_in_error",
            "other",
        }
        if self.decision == "rejected" and self.reason_code not in rejection_reasons:
            raise ValueError("rejected assessment carries an invalid reason")
        if self.decision == "invalidated" and self.reason_code not in invalidation_reasons:
            raise ValueError("invalidated assessment carries an invalid reason")
        return self


class AuthorityEvidenceResponse(AuthoritySchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    evidence_kind: EvidenceKind
    source_label: str = Field(min_length=1, max_length=160)
    recorded_by_user_id: UUID
    storage: EvidenceStorage | None
    evidence_object_id: UUID | None = None
    issued_at: UtcDateTime | None
    captured_at: UtcDateTime | None
    expires_at: UtcDateTime | None
    created_at: UtcDateTime
    version: int = Field(ge=1, le=3)
    lifecycle_status: EvidenceLifecycleStatus
    effective_status: EvidenceEffectiveStatus
    valid_now: bool
    evaluated_at: UtcDateTime
    current_assessment: AuthorityEvidenceAssessmentResponse | None

    @model_validator(mode="after")
    def require_exact_evidence_projection(self):
        if (
            self.issued_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.issued_at
        ):
            raise ValueError("expires_at must be later than issued_at")
        if (
            self.evidence_kind
            in {
                "identity_document",
                "custody_document",
                "court_order",
                "signed_consent",
                "signed_release_delegation",
                "other_document",
            }
        ) != (self.evidence_object_id is not None):
            raise ValueError("evidence object binding does not match evidence kind")
        if self.current_assessment is None:
            if self.version != 1 or self.lifecycle_status != "unreviewed":
                raise ValueError("unassessed evidence must remain unreviewed at version one")
        elif (
            self.current_assessment.evidence_id != self.id
            or self.current_assessment.version_number != self.version
            or self.current_assessment.decision != self.lifecycle_status
        ):
            raise ValueError("current evidence assessment must be exact")
        expected_effective_status = self.lifecycle_status
        if (
            self.lifecycle_status == "reviewed"
            and self.expires_at is not None
            and self.expires_at <= self.evaluated_at
        ):
            expected_effective_status = "expired"
        if self.effective_status != expected_effective_status:
            raise ValueError("effective status does not match lifecycle and expiry")
        if self.valid_now != (self.effective_status == "reviewed"):
            raise ValueError("valid_now must match the computed effective status")
        return self


class AuthorityEvidenceObjectAssessmentResponse(AuthoritySchema):
    id: UUID
    version_number: Literal[1, 2]
    decision: EvidenceObjectAssessmentDecision
    scanner_engine: str | None = Field(default=None, min_length=1, max_length=80)
    scanner_version: str | None = Field(default=None, min_length=1, max_length=160)
    scanner_signature: str | None = Field(default=None, min_length=1, max_length=160)
    reason_code: Literal["malware_detected", "invalid_document"] | None = None
    actor_user_id: UUID
    created_at: UtcDateTime

    @model_validator(mode="after")
    def require_exact_object_assessment(self):
        if self.version_number == 1:
            if self.decision != "quarantined" or any(
                value is not None
                for value in (
                    self.scanner_engine,
                    self.scanner_version,
                    self.scanner_signature,
                    self.reason_code,
                )
            ):
                raise ValueError("version-one object assessment must be quarantined")
            return self
        if self.decision == "clean":
            if (
                self.scanner_engine is None
                or self.scanner_version is None
                or self.scanner_signature is not None
                or self.reason_code is not None
            ):
                raise ValueError("clean scan assessment has invalid scanner provenance")
            return self
        if (
            self.decision != "rejected"
            or self.scanner_engine is None
            or self.scanner_version is None
            or self.reason_code not in {"malware_detected", "invalid_document"}
        ):
            raise ValueError("rejected scan assessment has invalid scanner provenance")
        return self


class AuthorityEvidenceObjectResponse(AuthoritySchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    evidence_kind: EvidenceKind
    version: Literal[1, 2]
    lifecycle_status: EvidenceObjectLifecycleStatus
    valid_for_evidence: bool
    object_version: Literal[1]
    media_type: Literal["application/pdf", "image/jpeg", "image/png"]
    byte_size: int = Field(gt=0, le=MAX_EVIDENCE_BYTE_SIZE)
    content_sha256: Sha256Hex
    original_filename: str | None = Field(default=None, max_length=255)
    uploaded_by_user_id: UUID
    created_at: UtcDateTime
    current_assessment: AuthorityEvidenceObjectAssessmentResponse

    @model_validator(mode="after")
    def require_exact_object_projection(self):
        if self.version != self.current_assessment.version_number:
            raise ValueError("object version must match current assessment")
        if self.lifecycle_status != self.current_assessment.decision:
            raise ValueError("object lifecycle must match current assessment")
        if self.valid_for_evidence != (self.lifecycle_status == "clean"):
            raise ValueError("valid_for_evidence must match clean state")
        return self


class ChildAuthorityHeadResponse(AuthoritySchema):
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    revision: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ReleaseAuthorizationResponse(EffectiveWindowSchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    recipient_person_id: UUID
    verification_policy_code: VerificationPolicyCode
    grantor: ReviewedGrantorReference
    version: int = Field(ge=1)
    revoked_at: UtcDateTime | None
    revocation_reason_code: ReleaseRevocationReasonCode | None
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    evaluated_at: UtcDateTime
    authority_revision: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def require_exact_revocation_state(self):
        if (self.revoked_at is None) != (self.revocation_reason_code is None):
            raise ValueError("revocation time and reason must be present together")
        if (self.effective_status == "revoked") != (self.revoked_at is not None):
            raise ValueError("effective status must reflect revocation")
        if self.effective_status == "withdrawn":
            raise ValueError("release authorizations cannot be withdrawn")
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


class ReleaseRuleResponse(EffectiveWindowSchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    rule_kind: ReleaseRuleKind
    scope: ReleaseRuleScope
    directing_person: AuthorityPersonVersionReference | None
    authority_basis_code: ReviewedAuthorityBasis
    basis_evidence_id: UUID
    basis_evidence_assessment_id: UUID
    safe_explanation_code: ReleaseSafeExplanationCode
    confidential_reason: str = Field(min_length=1)
    version: int = Field(ge=1)
    revoked_at: UtcDateTime | None
    revocation_reason_code: ReleaseRevocationReasonCode | None
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    evaluated_at: UtcDateTime
    authority_revision: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def require_rule_invariants(self):
        safe_code_by_kind = {
            "deny": "release_restricted",
            "supervised_only": "supervision_required",
            "named_recipient_only": "named_recipient_only",
            "manager_review": "manager_review_required",
        }
        if self.safe_explanation_code != safe_code_by_kind[self.rule_kind]:
            raise ValueError("safe_explanation_code does not match rule_kind")
        if self.rule_kind == "named_recipient_only" and self.scope.kind != "specific_person":
            raise ValueError("named_recipient_only requires a specific_person scope")
        if (self.revoked_at is None) != (self.revocation_reason_code is None):
            raise ValueError("revocation time and reason must be present together")
        if (self.effective_status == "revoked") != (self.revoked_at is not None):
            raise ValueError("effective status must reflect revocation")
        if self.effective_status == "withdrawn":
            raise ValueError("release rules cannot be withdrawn")
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


class ConsentPolicyVersionResponse(EffectiveWindowSchema):
    id: UUID
    organization_id: UUID
    purpose_code: ConsentPurposeCode
    version_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    content_text: str = Field(min_length=1, max_length=20_000)
    content_reference: str = Field(min_length=1, max_length=500)
    content_sha256: Sha256Hex
    signer_authority_requirement: ConsentSignerAuthorityRequirement
    published_at: UtcDateTime


class ChildConsentDecisionResponse(EffectiveWindowSchema):
    id: UUID
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    purpose_code: ConsentPurposeCode
    policy_version_id: UUID
    signer: ConsentSignerReference
    evidence_id: UUID
    evidence_assessment_id: UUID
    decision: ConsentDecision
    scope: ConsentScope
    version: int = Field(ge=1)
    withdrawn_at: UtcDateTime | None
    withdrawal_reason_code: ConsentWithdrawalReasonCode | None
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    evaluated_at: UtcDateTime
    authority_revision: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def require_exact_withdrawal_state(self):
        if (self.withdrawn_at is None) != (self.withdrawal_reason_code is None):
            raise ValueError("withdrawal time and reason must be present together")
        if (self.effective_status == "withdrawn") != (self.withdrawn_at is not None):
            raise ValueError("effective status must reflect withdrawal")
        if self.effective_status == "revoked":
            raise ValueError("consent decisions cannot be revoked")
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


COMMAND_TARGET_TYPES: dict[str, str] = {
    "family.authority.person.create": "authority_person",
    "family.authority.person.replace": "authority_person",
    "family.authority.person.retire": "authority_person",
    "family.authority.evidence.record": "authority_evidence",
    "family.authority.evidence.review": "authority_evidence",
    "family.authority.evidence.reject": "authority_evidence",
    "family.authority.evidence.invalidate": "authority_evidence",
    "family.authority.evidence.supersede": "authority_evidence",
    "family.authority.evidence_object.upload": "authority_evidence_object",
    "family.authority.evidence_object.scan": "authority_evidence_object",
    "child.release.authorization.grant": "release_authorization",
    "child.release.authorization.revoke": "release_authorization",
    "child.release.rule.create": "release_rule",
    "child.release.rule.revoke": "release_rule",
    "organization.consent.policy.publish": "consent",
    "child.consent.record": "consent",
    "child.consent.withdraw": "consent",
}


class FamilyAuthorityCommandReceiptResponse(AuthoritySchema):
    """Minimum non-confidential receipt used for exact-retry reconciliation."""

    organization_id: UUID
    client_operation_id: UUID
    command_type: FamilyAuthorityCommandType
    target_type: FamilyAuthorityTargetType
    target_id: UUID
    committed_version: int = Field(ge=1)
    committed_at: UtcDateTime
    facility_id: UUID | None
    action_route: str = Field(min_length=1, max_length=500)

    @field_validator("action_route")
    @classmethod
    def require_local_action_route(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("action_route must be a local absolute-path reference")
        if "\\" in value or any(ord(character) < 32 for character in value):
            raise ValueError("action_route contains unsafe characters")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise ValueError("action_route must not contain an origin or fragment")
        if any(segment == ".." for segment in parsed.path.split("/")):
            raise ValueError("action_route must not traverse parent paths")
        return value

    @model_validator(mode="after")
    def require_exact_target_type(self):
        if self.target_type != COMMAND_TARGET_TYPES[self.command_type]:
            raise ValueError("target_type does not match command_type")
        return self


class FamilyAuthorityCommandResponse[ResourceT](AuthoritySchema):
    resource: ResourceT
    receipt: FamilyAuthorityCommandReceiptResponse
    replayed: bool = False


AuthorityPersonCommandResponse = FamilyAuthorityCommandResponse[AuthorityPersonResponse]
AuthorityEvidenceCommandResponse = FamilyAuthorityCommandResponse[AuthorityEvidenceResponse]
AuthorityEvidenceObjectCommandResponse = FamilyAuthorityCommandResponse[
    AuthorityEvidenceObjectResponse
]
ReleaseAuthorizationCommandResponse = FamilyAuthorityCommandResponse[ReleaseAuthorizationResponse]
ReleaseRuleCommandResponse = FamilyAuthorityCommandResponse[ReleaseRuleResponse]
ConsentPolicyCommandResponse = FamilyAuthorityCommandResponse[ConsentPolicyVersionResponse]
ChildConsentCommandResponse = FamilyAuthorityCommandResponse[ChildConsentDecisionResponse]


class ChildFamilyAuthorityResponse(AuthoritySchema):
    child_id: UUID
    reviewed: bool
    authority_revision: int = Field(ge=0)
    release_authorizations: list[ReleaseAuthorizationResponse]
    release_rules: list[ReleaseRuleResponse]
    consent_decisions: list[ChildConsentDecisionResponse]

    @model_validator(mode="after")
    def require_reviewed_revision_shape(self):
        if self.reviewed != (self.authority_revision > 0):
            raise ValueError("reviewed must match authority_revision presence")
        return self


ChildAuthoritySummaryFocusKind = Literal[
    "release_authorization",
    "release_rule",
    "consent",
]


class ChildAuthorityPersonSummary(AuthoritySchema):
    """Current, contact-free identity label for an administrative summary."""

    id: UUID
    display_name: str = Field(min_length=1, max_length=305)
    relationship_kind: RelationshipKind
    status: AuthorityPersonStatus


class ChildReleaseAuthorizationSummary(EffectiveWindowSchema):
    record_type: Literal["release_authorization"]
    id: UUID
    child_id: UUID
    recipient: ChildAuthorityPersonSummary
    verification_policy_code: VerificationPolicyCode
    version: int = Field(ge=1)
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    authority_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def require_effective_flag(self):
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


class ChildReleaseRuleSummary(EffectiveWindowSchema):
    record_type: Literal["release_rule"]
    id: UUID
    child_id: UUID
    rule_kind: ReleaseRuleKind
    safe_explanation_code: ReleaseSafeExplanationCode
    scope_kind: Literal["all_recipients", "specific_person"]
    scoped_person: ChildAuthorityPersonSummary | None
    version: int = Field(ge=1)
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    authority_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def require_exact_scope_and_effective_flag(self):
        if (self.scope_kind == "specific_person") != (self.scoped_person is not None):
            raise ValueError("specific-person scope requires exactly one person")
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


class ChildConsentPolicySummary(AuthoritySchema):
    id: UUID
    title: str = Field(min_length=1, max_length=180)
    version_number: int = Field(ge=1)


class ChildConsentDecisionSummary(EffectiveWindowSchema):
    record_type: Literal["consent"]
    id: UUID
    child_id: UUID
    purpose_code: ConsentPurposeCode
    policy: ChildConsentPolicySummary
    decision: ConsentDecision
    scope: ConsentScope
    version: int = Field(ge=1)
    effective_status: AuthorityRecordEffectiveStatus
    effective_now: bool
    authority_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def require_effective_flag(self):
        if self.effective_now != (self.effective_status == "effective"):
            raise ValueError("effective_now must match effective status")
        return self


ChildAuthoritySummaryFocus = Annotated[
    ChildReleaseAuthorizationSummary
    | ChildReleaseRuleSummary
    | ChildConsentDecisionSummary,
    Field(discriminator="record_type"),
]


class ChildAuthoritySummaryResponse(AuthoritySchema):
    """Minimum-necessary child projection; never a checkout authorization."""

    schema_version: Literal["child-authority-summary-v1"]
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    generated_at: UtcDateTime
    reviewed: bool
    authority_revision: int = Field(ge=0)
    release_authorizations: list[ChildReleaseAuthorizationSummary]
    release_rules: list[ChildReleaseRuleSummary]
    consent_decisions: list[ChildConsentDecisionSummary]
    focus: ChildAuthoritySummaryFocus | None

    @model_validator(mode="after")
    def require_identity_bound_projection(self):
        if self.reviewed != (self.authority_revision > 0):
            raise ValueError("reviewed must match authority_revision presence")
        rows = [
            *self.release_authorizations,
            *self.release_rules,
            *self.consent_decisions,
        ]
        if len({(row.record_type, row.id) for row in rows}) != len(rows):
            raise ValueError("summary rows must be unique")
        for row in [*rows, *([self.focus] if self.focus is not None else [])]:
            if row.child_id != self.child_id:
                raise ValueError("summary rows must belong to the requested child")
            if row.authority_revision != self.authority_revision:
                raise ValueError("summary rows must bind to the projected authority revision")
        return self


class FamilyAuthorityWorkspaceResponse(AuthoritySchema):
    organization_id: UUID
    family_id: UUID
    generated_at: UtcDateTime
    people: list[AuthorityPersonResponse]
    evidence_objects: list[AuthorityEvidenceObjectResponse] = Field(default_factory=list)
    evidence: list[AuthorityEvidenceResponse]
    children: list[ChildFamilyAuthorityResponse]
