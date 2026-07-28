"""Strict HTTP contracts for planned staff rota and clock reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ScheduleStatus = Literal["draft", "published", "cancelled"]
StaffResponseStatus = Literal["pending", "acknowledged", "declined", "alternate_proposed"]
ReconciliationStatus = Literal["upcoming", "active", "completed", "missed", "late", "cancelled"]


class ScheduledShiftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    staff_user_id: UUID
    facility_id: UUID
    room_id: UUID | None = None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    notes: str | None = Field(default=None, max_length=2000)


class ScheduledShiftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    staff_user_id: UUID | None = None
    facility_id: UUID | None = None
    room_id: UUID | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ScheduledShiftAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID


class ScheduledShiftPublish(ScheduledShiftAction):
    availability_override_reason: str | None = Field(default=None, max_length=500)


class ScheduledShiftCancel(ScheduledShiftAction):
    reason: str = Field(min_length=1, max_length=500)


class ScheduledShiftAlternateResolution(ScheduledShiftAction):
    expected_updated_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class StaffScheduledShiftResponseAction(ScheduledShiftAction):
    note: str | None = Field(default=None, max_length=1000)


class StaffScheduledShiftProposal(ScheduledShiftAction):
    proposed_start_at: datetime
    proposed_end_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class ActualStaffShiftResponse(BaseModel):
    id: UUID
    membership_id: UUID
    facility_id: UUID
    scheduled_shift_id: UUID | None
    status: Literal["open", "closed"]
    clocked_in_at: datetime
    clocked_out_at: datetime | None


class ScheduledStaffShiftResponse(BaseModel):
    id: UUID
    organization_id: UUID
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    notes: str | None
    status: ScheduleStatus
    response_status: StaffResponseStatus
    response_note: str | None
    proposed_start_at: datetime | None
    proposed_end_at: datetime | None
    responded_at: datetime | None
    actual_shift: ActualStaffShiftResponse | None
    reconciliation_status: ReconciliationStatus
    is_late: bool
    minutes_late: int
    recorded_create_operation_id: UUID
    created_by_user_id: UUID
    published_at: datetime | None
    published_by_user_id: UUID | None
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason: str | None
    availability_override_reason: str | None
    origin_type: Literal["rotation", "open_shift", "swap"] | None
    origin_id: UUID | None
    origin_occurrence_key: str | None
    supersedes_schedule_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ScheduledStaffShiftListResponse(BaseModel):
    items: list[ScheduledStaffShiftResponse]
    total: int
    generated_at: datetime


class UnscheduledStaffShiftResponse(BaseModel):
    staff_user_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    reconciliation_status: Literal["unscheduled"] = "unscheduled"
    actual_shift: ActualStaffShiftResponse


class StaffShiftReconciliationResponse(BaseModel):
    scheduled: list[ScheduledStaffShiftResponse]
    unscheduled: list[UnscheduledStaffShiftResponse]
    total_scheduled: int
    total_unscheduled: int
    generated_at: datetime
