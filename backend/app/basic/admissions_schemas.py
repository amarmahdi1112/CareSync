"""Strict, read-only admissions and intake projection schemas.

Revision 0028 does not contain an admissions application, waitlist, or intake
decision ledger.  These models therefore expose only a derived action queue
over current childcare records and make that limitation machine-readable.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AdmissionIntakeStage = Literal[
    "family_contacts",
    "child_record",
    "enrollment_setup",
    "record_conflict",
    "family_review",
    "placement_review",
]
AdmissionIntakeSeverity = Literal["critical", "warning"]
AdmissionIntakeReasonCode = Literal[
    "missing_primary_guardian",
    "unreachable_guardian_telephone",
    "missing_emergency_contact",
    "no_child_record",
    "no_open_enrollment_record",
    "pending_family_active_child",
    "pending_family_open_enrollment",
    "duplicate_open_enrollment",
    "family_lifecycle_conflict",
    "inactive_child_open_enrollment",
    "enrollment_date_conflict",
    "facility_unavailable",
    "placement_incomplete",
    "program_unavailable",
    "room_unavailable",
    "placement_effective_date_conflict",
    "room_age_range_missing",
    "child_outside_room_age_range",
    "family_pending_manual_review",
    "pending_enrollment_placement_review",
]
AdmissionIntakeEntityType = Literal[
    "family",
    "child",
    "enrollment",
    "facility",
    "program",
    "room",
]

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_SAFE_ACTION_PATHS = (
    re.compile(rf"^/families/{_UUID}(?:\?focus=family-status)?$"),
    re.compile(rf"^/children/{_UUID}$"),
    re.compile(rf"^/rooms\?facility_id={_UUID}&placement_enrollment_id={_UUID}$"),
)


class _ExactProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdmissionIntakeAction(_ExactProjectionModel):
    label: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=240)

    @field_validator("path")
    @classmethod
    def safe_internal_path(cls, value: str) -> str:
        if not any(pattern.fullmatch(value) for pattern in _SAFE_ACTION_PATHS):
            raise ValueError("unsupported admissions action path")
        return value


class AdmissionIntakeReason(_ExactProjectionModel):
    code: AdmissionIntakeReasonCode
    stage: AdmissionIntakeStage
    severity: AdmissionIntakeSeverity
    title: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=500)
    entity_type: AdmissionIntakeEntityType
    entity_id: UUID
    action: AdmissionIntakeAction


class AdmissionIntakeChild(_ExactProjectionModel):
    id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    is_active: bool


class AdmissionIntakeEnrollment(_ExactProjectionModel):
    id: UUID
    child_id: UUID
    facility_id: UUID
    facility_name: str | None = Field(default=None, max_length=255)
    program_id: UUID | None
    program_name: str | None = Field(default=None, max_length=150)
    room_id: UUID | None
    room_name: str | None = Field(default=None, max_length=150)
    placement_effective_date: date | None
    start_date: date
    end_date: date | None
    status: Literal["pending", "active", "paused"]


class AdmissionIntakeCase(_ExactProjectionModel):
    key: str = Field(pattern=r"^family:[0-9a-f-]{36}$", max_length=43)
    family_id: UUID
    family_name: str = Field(min_length=1, max_length=255)
    family_status: Literal["pending", "active", "inactive", "archived"]
    stage: AdmissionIntakeStage
    severity: AdmissionIntakeSeverity
    children: list[AdmissionIntakeChild]
    enrollments: list[AdmissionIntakeEnrollment]
    reasons: list[AdmissionIntakeReason] = Field(min_length=1)
    primary_action: AdmissionIntakeAction
    updated_at: datetime

    @model_validator(mode="after")
    def primary_reason_matches_case(self) -> AdmissionIntakeCase:
        first = self.reasons[0]
        if self.stage != first.stage:
            raise ValueError("case stage must match the first reason stage")
        if self.primary_action != first.action:
            raise ValueError("primary_action must match the first reason action")
        if self.severity == "warning" and any(
            reason.severity == "critical" for reason in self.reasons
        ):
            raise ValueError("case severity cannot hide a critical reason")
        return self


class AdmissionIntakeStageCounts(_ExactProjectionModel):
    family_contacts: int = Field(default=0, ge=0)
    child_record: int = Field(default=0, ge=0)
    enrollment_setup: int = Field(default=0, ge=0)
    record_conflict: int = Field(default=0, ge=0)
    family_review: int = Field(default=0, ge=0)
    placement_review: int = Field(default=0, ge=0)


class AdmissionIntakeCounts(_ExactProjectionModel):
    total: int = Field(default=0, ge=0)
    critical: int = Field(default=0, ge=0)
    warning: int = Field(default=0, ge=0)
    by_stage: AdmissionIntakeStageCounts = Field(default_factory=AdmissionIntakeStageCounts)


class AdmissionIntakeQueueResponse(_ExactProjectionModel):
    organization_id: UUID
    generated_at: datetime
    projection_kind: Literal["derived_current_intake_queue"] = "derived_current_intake_queue"
    read_only: Literal[True] = True
    waitlist_supported: Literal[False] = False
    compliance_certified: Literal[False] = False
    notice: str = Field(min_length=1, max_length=500)
    items: list[AdmissionIntakeCase]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
    counts: AdmissionIntakeCounts

    @model_validator(mode="after")
    def totals_are_consistent(self) -> AdmissionIntakeQueueResponse:
        if self.total != self.counts.total:
            raise ValueError("total must match counts.total")
        if self.counts.critical + self.counts.warning != self.counts.total:
            raise ValueError("case severity counts must match total")
        return self
