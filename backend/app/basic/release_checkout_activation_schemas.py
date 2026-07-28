"""Strict contracts for the irreversible per-facility release-checkout cutover."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

RELEASE_CHECKOUT_ACTIVATION_POLICY = "normal_verified_release_v1"
RELEASE_CHECKOUT_ACTIVATION_CONFIRMATION = "ACTIVATE VERIFIED RELEASE CHECKOUT"


class ReleaseCheckoutActivationSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ReleaseCheckoutActivationPrerequisite(ReleaseCheckoutActivationSchema):
    code: Literal[
        "runtime_available",
        "activation_command_available",
        "database_writable",
        "facility_active",
        "privileged_actor",
        "authority_records_complete",
        "not_already_activated",
    ]
    label: str = Field(min_length=1, max_length=180)
    satisfied: bool


class ReleaseCheckoutActivationStatus(ReleaseCheckoutActivationSchema):
    schema_version: Literal["release-checkout-activation-status-v1"]
    organization_id: UUID
    facility_id: UUID
    facility_name: str = Field(min_length=1, max_length=255)
    runtime_available: bool
    activation_command_available: bool
    database_writable: bool
    actor_authorized: bool
    facility_active: bool
    activated: bool
    legacy_checkout_allowed: bool
    activation_policy_version: Literal["normal_verified_release_v1"] | None
    open_enrollment_children: int = Field(ge=0)
    release_ready_children: int = Field(ge=0)
    children_needing_authority_review: int = Field(ge=0)
    prerequisites: tuple[ReleaseCheckoutActivationPrerequisite, ...]
    can_activate: bool
    confirmation_text: Literal["ACTIVATE VERIFIED RELEASE CHECKOUT"]

    @model_validator(mode="after")
    def require_coherent_status(self):
        if self.release_ready_children > self.open_enrollment_children:
            raise ValueError("release-ready children cannot exceed open enrollment children")
        if (
            self.children_needing_authority_review
            != self.open_enrollment_children - self.release_ready_children
        ):
            raise ValueError("authority-review count is inconsistent")
        if self.activated != (self.activation_policy_version is not None):
            raise ValueError("activation policy must be present exactly when activated")
        if self.activated and self.legacy_checkout_allowed:
            raise ValueError("legacy checkout cannot remain available after activation")
        expected = all(item.satisfied for item in self.prerequisites)
        if self.can_activate != expected:
            raise ValueError("activation eligibility does not match its prerequisites")
        return self


class ReleaseCheckoutActivationCommand(ReleaseCheckoutActivationSchema):
    schema_version: Literal["release-checkout-activation-command-v1"]
    organization_id: UUID
    facility_id: UUID
    client_operation_id: UUID
    activation_policy_version: Literal["normal_verified_release_v1"]
    authority_records_reviewed: Literal[True]
    verification_workflow_reviewed: Literal[True]
    legacy_checkout_closure_understood: Literal[True]
    irreversible_activation_understood: Literal[True]
    confirmation_text: Literal["ACTIVATE VERIFIED RELEASE CHECKOUT"]


class ReleaseCheckoutActivationReceipt(ReleaseCheckoutActivationSchema):
    organization_id: UUID
    facility_id: UUID
    activation_id: UUID
    client_operation_id: UUID
    committed_at: datetime
    action_route: Literal["/settings?section=facility"]

    @field_serializer("committed_at", when_used="json")
    def serialize_committed_at(self, value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ReleaseCheckoutActivationResponse(ReleaseCheckoutActivationSchema):
    schema_version: Literal["release-checkout-activation-v1"]
    status: ReleaseCheckoutActivationStatus
    receipt: ReleaseCheckoutActivationReceipt
    replayed: bool
