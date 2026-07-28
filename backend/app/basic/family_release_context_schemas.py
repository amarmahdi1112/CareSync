"""Strict internal and public contracts for the 0029B release context.

The internal models are the sole input boundary for the future PostgreSQL and
portable repositories.  They intentionally contain no evidence identifiers,
grantor provenance, contact details, confidential reasons, or storage data.
The public models are the minimum-necessary educator projection locked by the
0029B architecture.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

RELEASE_CONTEXT_SCHEMA_VERSION = "release-context-v1"
RELEASE_CONTEXT_INPUT_VERSION = "release-context-input-v1"
RELEASE_CONTEXT_MAX_TTL_MS = 30_000

ReleaseContextDecision = Literal["recipient_selection_available", "blocked"]
ReleaseContextBlocker = Literal[
    "authority_not_reviewed",
    "release_restricted",
    "manager_review_required",
    "verification_workflow_unavailable",
    "recipient_identity_ambiguous",
    "no_active_release_authorization",
]
VerificationMethod = Literal["government_photo_id", "documented_familiarity"]
VerificationPolicyCode = Literal[
    "government_photo_id",
    "documented_familiarity",
    "government_photo_id_or_documented_familiarity",
    "government_photo_id_and_secondary_check",
]
ExecutableVerificationPolicyCode = Literal[
    "government_photo_id",
    "documented_familiarity",
    "government_photo_id_or_documented_familiarity",
]
ReleaseRuleKind = Literal[
    "deny",
    "supervised_only",
    "named_recipient_only",
    "manager_review",
]
ReleaseRuleScopeKind = Literal["all_recipients", "specific_person"]
ReleaseSafeExplanationCode = Literal[
    "release_restricted",
    "supervision_required",
    "named_recipient_only",
    "manager_review_required",
]
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
AuthorityPersonStatus = Literal["active", "retired"]
EvidenceAssessmentDecision = Literal["reviewed", "rejected", "invalidated", "superseded"]

SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value.astimezone(UTC)


def _normalized_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("text must not be blank")
    return normalized


UtcDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
NormalizedName = Annotated[
    str,
    Field(min_length=1, max_length=100),
    AfterValidator(_normalized_text),
]
Sha256Hex = Annotated[str, Field(pattern=SHA256_PATTERN)]


class ReleaseContextSchema(BaseModel):
    """Fail-closed parsing shared by the internal and public B boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class EffectiveWindowInput(ReleaseContextSchema):
    effective_from: UtcDateTime
    effective_until: UtcDateTime

    @model_validator(mode="after")
    def require_finite_half_open_window(self):
        if self.effective_until <= self.effective_from:
            raise ValueError("effective_until must be later than effective_from")
        return self


class SupportingEvidenceInput(ReleaseContextSchema):
    """Non-identifying evidence currency needed by the pure composer.

    The bound assessment remains the historical assessment used to activate
    the row.  ``bound_assessment_is_latest`` becomes false after a terminal
    assessment and therefore excludes the dependent row without disclosing an
    evidence identifier or terminal reason.
    """

    bound_assessment_decision: EvidenceAssessmentDecision
    bound_assessment_is_latest: bool
    evidence_expires_at: UtcDateTime | None = None
    scope_matches_authority_record: bool


class RecipientPersonVersionInput(ReleaseContextSchema):
    person_version_id: UUID
    first_name: NormalizedName
    middle_name: NormalizedName | None = None
    last_name: NormalizedName
    preferred_name: NormalizedName | None = None
    relationship_kind: RelationshipKind
    relationship_detail: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("relationship_detail")
    @classmethod
    def normalize_relationship_detail(cls, value: str | None) -> str | None:
        return None if value is None else _normalized_text(value)

    @model_validator(mode="after")
    def require_bounded_relationship_detail(self):
        if self.relationship_kind == "other" and self.relationship_detail is None:
            raise ValueError("relationship_detail is required for other relationships")
        if self.relationship_kind != "other" and self.relationship_detail is not None:
            raise ValueError("relationship_detail is only allowed for other relationships")
        return self


class ReleaseRecipientPersonInput(ReleaseContextSchema):
    organization_id: UUID
    family_id: UUID
    person_id: UUID
    status: AuthorityPersonStatus
    current_versions: list[RecipientPersonVersionInput]


class ReleaseAuthorizationInput(EffectiveWindowInput):
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    authorization_id: UUID
    authorization_version: int = Field(ge=1)
    recipient_person_id: UUID
    verification_policy_code: VerificationPolicyCode
    supporting_evidence: SupportingEvidenceInput
    revoked_at: UtcDateTime | None = None


class ReleaseRuleInput(EffectiveWindowInput):
    organization_id: UUID
    family_id: UUID
    child_id: UUID
    rule_id: UUID
    rule_version: int = Field(ge=1)
    rule_kind: ReleaseRuleKind
    scope_kind: ReleaseRuleScopeKind
    scope_person_id: UUID | None = None
    safe_explanation_code: ReleaseSafeExplanationCode
    supporting_evidence: SupportingEvidenceInput
    revoked_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def require_exact_scope_shape(self):
        if self.scope_kind == "all_recipients" and self.scope_person_id is not None:
            raise ValueError("all_recipients scope must not name a person")
        if self.scope_kind == "specific_person" and self.scope_person_id is None:
            raise ValueError("specific_person scope requires a person")
        return self


class ReleaseContextInput(ReleaseContextSchema):
    """Repository output consumed by :func:`compose_release_context`.

    ``authority_revision == 0`` is the exact representation of a missing child
    authority head.  Repositories must provide every authorization and rule
    that can be active now or transition in the future; the composer owns all
    time, evidence-currency, person-currency, policy, and rule filtering.
    """

    input_schema_version: Literal["release-context-input-v1"]
    organization_id: UUID
    family_id: UUID
    facility_id: UUID
    room_id: UUID
    child_id: UUID
    attendance_day_id: UUID
    attendance_interval_id: UUID
    staff_shift_id: UUID
    evaluated_at: UtcDateTime
    authority_revision: int = Field(ge=0)
    people: list[ReleaseRecipientPersonInput]
    authorizations: list[ReleaseAuthorizationInput]
    rules: list[ReleaseRuleInput]


class CanonicalReleaseRestriction(EffectiveWindowInput):
    rule_id: UUID
    rule_kind: Literal["deny", "manager_review"]
    rule_version: int = Field(ge=1)
    safe_explanation_code: Literal["release_restricted", "manager_review_required"]
    scope_kind: ReleaseRuleScopeKind
    scope_person_id: UUID | None = None

    @model_validator(mode="after")
    def require_canonical_rule_shape(self):
        expected_code = {
            "deny": "release_restricted",
            "manager_review": "manager_review_required",
        }[self.rule_kind]
        if self.safe_explanation_code != expected_code:
            raise ValueError("safe_explanation_code does not match rule_kind")
        if self.scope_kind == "all_recipients" and self.scope_person_id is not None:
            raise ValueError("all_recipients scope must not name a person")
        if self.scope_kind == "specific_person" and self.scope_person_id is None:
            raise ValueError("specific_person scope requires a person")
        return self


class EligibleReleaseRecipient(ReleaseContextSchema):
    recipient_person_id: UUID
    recipient_person_version_id: UUID
    display_name: str = Field(min_length=1, max_length=302)
    preferred_name: str | None = Field(default=None, min_length=1, max_length=100)
    relationship_label: str = Field(min_length=1, max_length=120)
    authorization_id: UUID
    authorization_version: int = Field(ge=1)
    verification_policy_code: ExecutableVerificationPolicyCode
    verification_methods: list[VerificationMethod] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def require_exact_verification_projection(self):
        expected: dict[str, list[str]] = {
            "government_photo_id": ["government_photo_id"],
            "documented_familiarity": ["documented_familiarity"],
            "government_photo_id_or_documented_familiarity": [
                "government_photo_id",
                "documented_familiarity",
            ],
        }
        if self.verification_methods != expected[self.verification_policy_code]:
            raise ValueError("verification_methods do not match verification_policy_code")
        return self


class ReleaseContextResponse(ReleaseContextSchema):
    schema_version: Literal["release-context-v1"] = RELEASE_CONTEXT_SCHEMA_VERSION
    decision_policy_version: Literal["release-context-v1"] = RELEASE_CONTEXT_SCHEMA_VERSION
    organization_id: UUID
    facility_id: UUID
    room_id: UUID
    child_id: UUID
    attendance_day_id: UUID
    attendance_interval_id: UUID
    staff_shift_id: UUID
    evaluated_at: UtcDateTime
    expires_at: UtcDateTime
    fresh_for_ms: int = Field(ge=1, le=RELEASE_CONTEXT_MAX_TTL_MS)
    authority_revision: int = Field(ge=0)
    restriction_digest_sha256: Sha256Hex
    decision: ReleaseContextDecision
    blockers: list[ReleaseContextBlocker]
    eligible_recipients: list[EligibleReleaseRecipient]

    @field_serializer("evaluated_at", "expires_at", when_used="json")
    def serialize_public_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @model_validator(mode="after")
    def require_coherent_public_decision(self):
        computed_fresh_for_ms = (self.expires_at - self.evaluated_at) // timedelta(
            milliseconds=1
        )
        if self.expires_at <= self.evaluated_at:
            raise ValueError("expires_at must be later than evaluated_at")
        if self.expires_at > self.evaluated_at + timedelta(milliseconds=RELEASE_CONTEXT_MAX_TTL_MS):
            raise ValueError("expires_at exceeds the release-context TTL cap")
        if self.fresh_for_ms != computed_fresh_for_ms:
            raise ValueError("fresh_for_ms must be the floor of the response lifetime")
        blocker_order = {
            "authority_not_reviewed": 0,
            "release_restricted": 1,
            "manager_review_required": 2,
            "verification_workflow_unavailable": 3,
            "recipient_identity_ambiguous": 4,
            "no_active_release_authorization": 5,
        }
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("blockers must be deduplicated")
        if self.blockers != sorted(self.blockers, key=blocker_order.__getitem__):
            raise ValueError("blockers must use canonical order")
        recipient_ids = [item.recipient_person_id for item in self.eligible_recipients]
        if recipient_ids != sorted(recipient_ids, key=str) or len(recipient_ids) != len(
            set(recipient_ids)
        ):
            raise ValueError("eligible recipients must be unique and canonically ordered")
        visible_identities = [
            tuple(
                unicodedata.normalize("NFKC", part or "").casefold()
                for part in (
                    recipient.display_name,
                    recipient.preferred_name,
                    recipient.relationship_label,
                )
            )
            for recipient in self.eligible_recipients
        ]
        if len(visible_identities) != len(set(visible_identities)):
            raise ValueError("eligible recipient identities must be visibly distinct")
        if self.decision == "recipient_selection_available":
            if self.blockers or not self.eligible_recipients:
                raise ValueError("available decisions require recipients and no blockers")
        elif not self.blockers or self.eligible_recipients:
            raise ValueError("blocked decisions require blockers and no recipients")
        if self.authority_revision == 0 and self.blockers != ["authority_not_reviewed"]:
            raise ValueError("revision zero must project only authority_not_reviewed")
        if self.authority_revision > 0 and "authority_not_reviewed" in self.blockers:
            raise ValueError("authority_not_reviewed requires a missing authority head")
        rule_blockers = {"release_restricted", "manager_review_required"}
        if any(blocker in rule_blockers for blocker in self.blockers):
            if not set(self.blockers).issubset(rule_blockers):
                raise ValueError("safe rule blockers cannot be combined with another blocker lane")
        elif self.blockers not in (
            [],
            ["authority_not_reviewed"],
            ["verification_workflow_unavailable"],
            ["recipient_identity_ambiguous"],
            ["no_active_release_authorization"],
        ):
            raise ValueError("blocker lane is not a bounded release-context outcome")
        return self
