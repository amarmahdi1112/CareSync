"""Strict contracts for staff availability, leave, templates, and coverage."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LocalTime = str
LOCAL_TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
MAX_COVERAGE_WINDOWS = 196
TimeOffStatus = Literal["pending", "approved", "declined", "cancelled"]
TimeOffCategory = Literal[
    "vacation", "sick", "personal", "medical", "bereavement", "unpaid", "other"
]
StaffRotaActionEntityType = Literal[
    "staff_availability",
    "staff_time_off",
    "staff_rotation_pattern",
    "staff_open_shift",
    "staff_open_shift_engagement",
    "staff_substitute_profile",
    "staff_shift_swap",
]


class AvailabilityWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    end_local: str = Field(pattern=LOCAL_TIME_PATTERN)


class AvailabilityReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime | None
    windows: list[AvailabilityWindow] = Field(max_length=28)
    note: str | None = Field(default=None, max_length=1000)


class OptimisticRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime


class StaffAvailabilityResponse(BaseModel):
    id: UUID
    organization_id: UUID
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    windows: list[AvailabilityWindow]
    note: str | None
    recorded_operation_id: UUID
    created_at: datetime
    updated_at: datetime


class SelfAvailabilityEnvelope(BaseModel):
    profile: StaffAvailabilityResponse | None
    recorded_operation_id: UUID | None
    generated_at: datetime


class StaffAvailabilityList(BaseModel):
    items: list[StaffAvailabilityResponse]
    total: int
    generated_at: datetime


class TimeOffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    facility_id: UUID
    starts_at: datetime
    ends_at: datetime
    category: TimeOffCategory
    note: str | None = Field(default=None, max_length=2000)


class TimeOffAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class TimeOffCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    reason: str = Field(min_length=1, max_length=1000)


class StaffTimeOffResponse(BaseModel):
    id: UUID
    organization_id: UUID
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    starts_at: datetime
    ends_at: datetime
    category: TimeOffCategory
    note: str | None
    status: TimeOffStatus
    can_cancel: bool
    response_note: str | None
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    decided_at: datetime | None
    decided_by_user_id: UUID | None
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class StaffTimeOffList(BaseModel):
    items: list[StaffTimeOffResponse]
    total: int
    generated_at: datetime


class StaffRotaActionTargetResponse(BaseModel):
    """Minimal canonical locator for a server-authored rota notification action."""

    organization_id: UUID
    entity_type: StaffRotaActionEntityType
    entity_id: UUID
    facility_id: UUID
    starts_at: datetime | None
    parent_entity_id: UUID | None
    membership_id: UUID | None
    visible: bool


class ShiftTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    facility_id: UUID
    room_id: UUID | None = None
    name: str = Field(min_length=1, max_length=150)
    weekday: int = Field(ge=0, le=6)
    start_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    end_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    notes: str | None = Field(default=None, max_length=2000)


class ShiftTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    facility_id: UUID | None = None
    room_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_local: str | None = Field(default=None, pattern=LOCAL_TIME_PATTERN)
    end_local: str | None = Field(default=None, pattern=LOCAL_TIME_PATTERN)
    notes: str | None = Field(default=None, max_length=2000)


class ShiftTemplateDeactivate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime


class ShiftTemplateInstantiate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    staff_user_id: UUID
    service_date: date
    notes: str | None = Field(default=None, max_length=2000)


class StaffShiftTemplateResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    name: str
    weekday: int
    start_local: str
    end_local: str
    notes: str | None
    is_active: bool
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    created_by_user_id: UUID
    deactivated_at: datetime | None
    deactivated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class StaffShiftTemplateList(BaseModel):
    items: list[StaffShiftTemplateResponse]
    total: int
    generated_at: datetime


class CoverageWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    end_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    required_staff: int = Field(ge=0, le=500)


class CoverageTargetReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime | None
    windows: list[CoverageWindow] = Field(max_length=MAX_COVERAGE_WINDOWS)


class StaffCoverageTargetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    windows: list[CoverageWindow]
    recorded_last_operation_id: UUID
    created_at: datetime
    updated_at: datetime


class StaffCoverageTargetList(BaseModel):
    items: list[StaffCoverageTargetResponse]
    total: int
    generated_at: datetime


class CoverageTargetRemoveResponse(BaseModel):
    removed: Literal[True] = True
    recorded_operation_id: UUID
    generated_at: datetime


class CoverageProjectionBucket(BaseModel):
    starts_at: datetime
    ends_at: datetime
    required: int
    published: int
    acknowledged: int
    declined: int
    draft: int
    gap: int
    confirmation_gap: int


class CoverageProjectionResponse(BaseModel):
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    start_date: date
    end_date: date
    interval_minutes: Literal[15] = 15
    buckets: list[CoverageProjectionBucket]
    total_buckets: int
    gap_buckets: int
    generated_at: datetime


class AvailabilityPublishAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    availability_override_reason: str | None = Field(default=None, max_length=500)
