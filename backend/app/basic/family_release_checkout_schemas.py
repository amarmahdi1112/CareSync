"""Strict public contracts for normal verified child release checkout.

The command contains only stable identifiers, optimistic expectations, and one
bounded verification tuple.  It deliberately contains no names, relationship
text, document facts, evidence identifiers, notes, override material, or a
client-authored checkout timestamp. ``requested_at`` is copied from the
server-authored 0029B context evaluation instant for exact intent and freshness
binding; the device clock never supplies it, and it is never the authoritative
release time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.basic.family_authority_schemas import (
    EvidenceAssessedEpistemicStatus,
    EvidenceKind,
)
from app.basic.family_release_context_schemas import (
    ExecutableVerificationPolicyCode,
    Sha256Hex,
    UtcDateTime,
    VerificationMethod,
)

RELEASE_CHECKOUT_COMMAND_SCHEMA_VERSION = "release-checkout-command-v1"
RELEASE_CHECKOUT_SCHEMA_VERSION = "release-checkout-v1"
RELEASE_CHECKOUT_ERROR_SCHEMA_VERSION = "release-checkout-error-v1"
RELEASE_CHECKOUT_DECISION_POLICY_VERSION = "release-context-v1"
RELEASE_CHECKOUT_COMMAND_TYPE = "attendance.release.checkout"
RELEASE_CHECKOUT_TARGET_TYPE = "attendance_release"
RELEASE_EVIDENCE_SCHEMA_VERSION = "release-evidence-v1"

VerificationResult = Literal["verified", "documented_familiarity"]
ReleaseCheckoutErrorCode = Literal[
    "release_checkout_verification_pair_invalid",
    "release_checkout_verification_policy_unavailable",
    "release_checkout_verification_policy_mismatch",
    "release_checkout_response_mismatch",
]
ReleaseCheckoutRecoveryAction = Literal[
    "correct_verification",
    "manager_process",
    "refresh_release_context",
    "reconcile_operation",
]

VERIFICATION_RESULT_BY_METHOD: dict[str, str] = {
    "government_photo_id": "verified",
    "documented_familiarity": "documented_familiarity",
}

ERROR_PRESENTATION: dict[str, tuple[str, str]] = {
    "release_checkout_verification_pair_invalid": (
        "Select one supported release verification outcome.",
        "correct_verification",
    ),
    "release_checkout_verification_policy_unavailable": (
        "This release requires a verification workflow that is not available.",
        "manager_process",
    ),
    "release_checkout_verification_policy_mismatch": (
        "The selected verification method is no longer allowed.",
        "refresh_release_context",
    ),
    "release_checkout_response_mismatch": (
        "The checkout response did not match the submitted command.",
        "reconcile_operation",
    ),
}


class ReleaseCheckoutSchema(BaseModel):
    """Fail-closed parsing shared by every C contract boundary."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ReleaseEvidenceDigestInput(ReleaseCheckoutSchema):
    """Exact immutable evidence facts sealed into a normal-release snapshot."""

    schema_version: Literal["release-evidence-v1"]
    evidence_id: UUID
    evidence_kind: EvidenceKind
    evidence_object_id: UUID | None
    content_sha256: Sha256Hex | None
    expires_at: UtcDateTime | None
    evidence_assessment_id: UUID
    evidence_assessment_version: Literal[2]
    decision: Literal["reviewed"]
    assessed_epistemic_status: EvidenceAssessedEpistemicStatus

    @field_serializer("expires_at", when_used="json")
    def serialize_expires_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @model_validator(mode="after")
    def require_object_content_pair(self):
        if (self.evidence_object_id is None) != (self.content_sha256 is None):
            raise ValueError("evidence object and content digest must be present together")
        return self


class ReleaseCheckoutCommand(ReleaseCheckoutSchema):
    """One exact normal-release intent submitted by an online staff client."""

    schema_version: Literal["release-checkout-command-v1"]
    client_operation_id: UUID
    requested_at: UtcDateTime
    child_id: UUID
    facility_id: UUID
    expected_room_id: UUID
    expected_attendance_day_id: UUID
    expected_attendance_interval_id: UUID
    expected_staff_shift_id: UUID
    recipient_person_id: UUID
    recipient_person_version_id: UUID
    authorization_id: UUID
    authorization_version: int = Field(ge=1)
    expected_authority_revision: int = Field(ge=1)
    expected_restriction_digest_sha256: Sha256Hex
    expected_decision_policy_version: Literal["release-context-v1"]
    verification_method: VerificationMethod
    verification_result: VerificationResult

    @field_serializer("requested_at", when_used="json")
    def serialize_requested_at(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @model_validator(mode="after")
    def require_exact_verification_pair(self):
        if self.verification_result != VERIFICATION_RESULT_BY_METHOD[self.verification_method]:
            raise ValueError("verification method/result pair is invalid")
        return self


class ReleaseCheckoutResource(ReleaseCheckoutSchema):
    """Immutable minimum-necessary projection of a committed normal release."""

    release_id: UUID
    organization_id: UUID
    facility_id: UUID
    room_id: UUID
    child_id: UUID
    attendance_day_id: UUID
    attendance_interval_id: UUID
    attendance_day_version: int = Field(ge=1)
    checkout_event_id: UUID
    staff_shift_id: UUID
    actor_user_id: UUID
    actor_membership_id: UUID
    recipient_person_id: UUID
    recipient_person_version_id: UUID
    recipient_display_name: str = Field(min_length=1, max_length=302)
    recipient_relationship: str = Field(min_length=1, max_length=120)
    authorization_id: UUID
    authorization_version: int = Field(ge=1)
    authority_revision: int = Field(ge=1)
    restriction_digest_sha256: Sha256Hex
    verification_policy_code: ExecutableVerificationPolicyCode
    verification_method: VerificationMethod
    verification_result: VerificationResult
    decision_policy_version: Literal["release-context-v1"]
    requested_at: UtcDateTime
    checked_out_at: UtcDateTime
    committed_at: UtcDateTime
    client_operation_id: UUID
    request_hash: Sha256Hex
    release_mode: Literal["normal"]

    @field_validator("recipient_display_name", "recipient_relationship")
    @classmethod
    def normalize_visible_recipient_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("visible recipient text must not be blank")
        return normalized

    @field_serializer(
        "requested_at",
        "checked_out_at",
        "committed_at",
        when_used="json",
    )
    def serialize_resource_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @model_validator(mode="after")
    def require_coherent_committed_release(self):
        if self.verification_result != VERIFICATION_RESULT_BY_METHOD[self.verification_method]:
            raise ValueError("verification method/result pair is invalid")
        allowed_methods: dict[str, set[str]] = {
            "government_photo_id": {"government_photo_id"},
            "documented_familiarity": {"documented_familiarity"},
            "government_photo_id_or_documented_familiarity": {
                "government_photo_id",
                "documented_familiarity",
            },
        }
        if self.verification_method not in allowed_methods[self.verification_policy_code]:
            raise ValueError("verification method does not match verification policy")
        if self.checked_out_at != self.committed_at:
            raise ValueError("checked_out_at must equal the authoritative commit timestamp")
        if self.requested_at > self.checked_out_at:
            raise ValueError("requested_at must not be later than checked_out_at")
        return self


class ReleaseCheckoutReceipt(ReleaseCheckoutSchema):
    """Minimum non-sensitive receipt for exact replay reconciliation."""

    organization_id: UUID
    client_operation_id: UUID
    command_type: Literal["attendance.release.checkout"]
    target_type: Literal["attendance_release"]
    target_id: UUID
    committed_version: Literal[1]
    committed_at: UtcDateTime
    facility_id: UUID
    action_route: str = Field(min_length=1, max_length=500)

    @field_serializer("committed_at", when_used="json")
    def serialize_committed_at(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @model_validator(mode="after")
    def require_exact_action_route(self):
        if self.action_route != f"/attendance/releases/{self.target_id}":
            raise ValueError("action_route does not match the release target")
        return self


class ReleaseCheckoutResponse(ReleaseCheckoutSchema):
    """Exact committed resource and receipt, whether first response or replay."""

    schema_version: Literal["release-checkout-v1"]
    resource: ReleaseCheckoutResource
    receipt: ReleaseCheckoutReceipt
    replayed: bool

    @model_validator(mode="after")
    def require_resource_receipt_echoes(self):
        resource = self.resource
        receipt = self.receipt
        if (
            receipt.organization_id != resource.organization_id
            or receipt.facility_id != resource.facility_id
            or receipt.client_operation_id != resource.client_operation_id
            or receipt.target_id != resource.release_id
            or receipt.committed_at != resource.committed_at
        ):
            raise ValueError("receipt does not echo the committed release resource")
        return self


class ReleaseCheckoutErrorResponse(ReleaseCheckoutSchema):
    """Bounded presentation contract for pure checkout contract failures."""

    schema_version: Literal["release-checkout-error-v1"]
    code: ReleaseCheckoutErrorCode
    message: str = Field(min_length=1, max_length=160)
    recovery_action: ReleaseCheckoutRecoveryAction

    @model_validator(mode="after")
    def require_fixed_presentation(self):
        expected_message, expected_action = ERROR_PRESENTATION[self.code]
        if self.message != expected_message or self.recovery_action != expected_action:
            raise ValueError("error presentation does not match its bounded code")
        return self
