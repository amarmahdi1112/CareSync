"""Strict contracts for recurring rota and the staff exchange."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.basic.staff_workforce_schemas import LOCAL_TIME_PATTERN

RotationStatus = Literal["draft", "active", "retired"]
OpenShiftStatus = Literal["draft", "open", "filled", "cancelled"]
EngagementKind = Literal["interest", "offer"]
EngagementStatus = Literal[
    "pending", "withdrawn", "rejected", "converted", "superseded", "accepted", "declined"
]
SwapKind = Literal["cover", "trade"]
SwapStatus = Literal[
    "pending_counterparty", "pending_manager", "approved", "declined", "cancelled", "rejected"
]


class RotationSlotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: UUID
    cycle_week: int = Field(ge=0, le=7)
    weekday: int = Field(ge=0, le=6)
    staff_user_id: UUID
    room_id: UUID | None = None
    start_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    end_local: str = Field(pattern=LOCAL_TIME_PATTERN)
    notes: str | None = Field(default=None, max_length=1000)


class RotationSlotResponse(RotationSlotInput):
    membership_id: UUID


class RotationPatternCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    facility_id: UUID
    name: str = Field(min_length=1, max_length=150)
    anchor_date: date
    cycle_weeks: int = Field(ge=1, le=8)
    slots: list[RotationSlotInput] = Field(min_length=1, max_length=500)


class RotationPatternPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    name: str | None = Field(default=None, min_length=1, max_length=150)
    anchor_date: date | None = None
    cycle_weeks: int | None = Field(default=None, ge=1, le=8)
    slots: list[RotationSlotInput] | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for field in ("name", "anchor_date", "cycle_weeks", "slots"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ExchangeOptimisticAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime


class RotationRetireAction(ExchangeOptimisticAction):
    reason: str = Field(min_length=1, max_length=1000)


class RotationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date


class RotationGenerateRequest(ExchangeOptimisticAction):
    start_date: date
    end_date: date
    preview_digest: str = Field(min_length=64, max_length=64)


class RotationPatternResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    name: str
    version: int = Field(ge=1)
    anchor_date: date
    cycle_weeks: int = Field(ge=1, le=8)
    slots: list[RotationSlotResponse]
    status: RotationStatus
    snapshot_digest: str | None
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    created_by_user_id: UUID
    activated_at: datetime | None
    activated_by_user_id: UUID | None
    retired_at: datetime | None
    retired_by_user_id: UUID | None
    retirement_reason: str | None
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    can_activate: bool
    can_retire: bool
    can_preview: bool
    can_generate: bool


class RotationPatternList(BaseModel):
    items: list[RotationPatternResponse]
    total: int
    generated_at: datetime


class RotationIssue(BaseModel):
    code: str
    message: str
    slot_id: UUID | None = None
    occurrence_key: str | None = None
    service_date: date | None = None


class RotationOccurrence(BaseModel):
    occurrence_key: str
    slot_id: UUID
    service_date: date
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    room_id: UUID | None
    room_name: str | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    notes: str | None


class RotationPreviewResponse(BaseModel):
    pattern_id: UUID
    snapshot_digest: str
    start_date: date
    end_date: date
    occurrences: list[RotationOccurrence]
    total: int
    issues: list[RotationIssue]
    can_generate: bool
    generated_at: datetime


class RotationGenerateResponse(BaseModel):
    pattern_id: UUID
    snapshot_digest: str
    schedule_ids: list[UUID]
    total: int
    recorded_operation_id: UUID
    generated_at: datetime


class OpenShiftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    facility_id: UUID
    room_id: UUID | None = None
    source_schedule_id: UUID | None = None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    public_note: str | None = Field(default=None, max_length=1000)


class OpenShiftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    facility_id: UUID | None = None
    room_id: UUID | None = None
    source_schedule_id: UUID | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    public_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for field in ("facility_id", "scheduled_start_at", "scheduled_end_at"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class OpenShiftCancelAction(ExchangeOptimisticAction):
    reason: str = Field(min_length=1, max_length=1000)


class EngagementAction(ExchangeOptimisticAction):
    note: str | None = Field(default=None, max_length=1000)


class ExpressInterest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class ManagerOfferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    staff_user_id: UUID
    source_interest_id: UUID | None = None
    note: str | None = Field(default=None, max_length=1000)
    expires_at: datetime


class OpenShiftEngagementResponse(BaseModel):
    id: UUID
    organization_id: UUID
    open_shift_id: UUID
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    kind: EngagementKind
    status: EngagementStatus
    note: str | None
    response_note: str | None
    source_interest_id: UUID | None
    converted_offer_id: UUID | None
    expires_at: datetime | None
    is_expired: bool
    resulting_schedule_id: UUID | None
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    can_withdraw: bool
    can_accept: bool
    can_decline: bool
    created_at: datetime
    updated_at: datetime


class OpenShiftEngagementList(BaseModel):
    items: list[OpenShiftEngagementResponse]
    total: int
    generated_at: datetime


class OpenShiftResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    source_schedule_id: UUID | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: OpenShiftStatus
    public_note: str | None
    is_replacement: bool
    eligibility_reasons: list[str]
    can_express_interest: bool
    my_engagement: OpenShiftEngagementResponse | None
    my_engagements: list[OpenShiftEngagementResponse]
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    created_by_user_id: UUID
    posted_at: datetime | None
    posted_by_user_id: UUID | None
    filled_at: datetime | None
    filled_engagement_id: UUID | None
    filled_schedule_id: UUID | None
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    can_post: bool
    can_cancel: bool


class SelfOpenShiftResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    source_schedule_id: UUID | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: OpenShiftStatus
    public_note: str | None
    is_replacement: bool
    eligibility_reasons: list[str]
    can_express_interest: bool
    my_engagement: OpenShiftEngagementResponse | None
    my_engagements: list[OpenShiftEngagementResponse]
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    created_at: datetime
    updated_at: datetime


class OpenShiftList(BaseModel):
    items: list[OpenShiftResponse]
    total: int
    generated_at: datetime


class SelfOpenShiftList(BaseModel):
    items: list[SelfOpenShiftResponse]
    total: int
    generated_at: datetime


class OpenShiftCandidateResponse(BaseModel):
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    substitute_opted_in: bool
    eligibility: Literal["eligible", "warning", "ineligible"]
    eligibility_reasons: list[str]


class OpenShiftCandidateList(BaseModel):
    items: list[OpenShiftCandidateResponse]
    total: int
    generated_at: datetime


class SubstituteProfileReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_updated_at: datetime | None
    active: Literal[True] = True
    note: str | None = Field(default=None, max_length=1000)


class SubstituteProfileResponse(BaseModel):
    id: UUID
    organization_id: UUID
    membership_id: UUID
    staff_user_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    active: bool
    note: str | None
    recorded_operation_id: UUID
    created_at: datetime
    updated_at: datetime


class SubstituteProfileList(BaseModel):
    items: list[SubstituteProfileResponse]
    total: int
    generated_at: datetime


class SubstituteManagerResponse(BaseModel):
    membership_id: UUID
    staff_user_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    substitute_opted_in: Literal[True] = True
    eligibility: Literal["eligible", "warning", "ineligible"]
    eligibility_reasons: list[str]


class SubstituteManagerList(BaseModel):
    items: list[SubstituteManagerResponse]
    total: int
    generated_at: datetime


class ExchangeScheduleSummary(BaseModel):
    id: UUID
    membership_id: UUID
    staff_display_name: str
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID | None
    room_name: str | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    updated_at: datetime


class SwapRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    kind: SwapKind
    requester_schedule_id: UUID
    counterparty_membership_id: UUID
    counterparty_schedule_id: UUID | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "trade" and self.counterparty_schedule_id is None:
            raise ValueError("counterparty_schedule_id is required for a trade")
        if self.kind == "cover" and self.counterparty_schedule_id is not None:
            raise ValueError("counterparty_schedule_id is unavailable for a cover")
        return self


class SwapResponseAction(ExchangeOptimisticAction):
    note: str | None = Field(default=None, max_length=1000)


class SwapRejectAction(ExchangeOptimisticAction):
    reason: str = Field(min_length=1, max_length=1000)


class ShiftSwapResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    kind: SwapKind
    status: SwapStatus
    requester_membership_id: UUID
    requester_staff_user_id: UUID
    requester_display_name: str
    counterparty_membership_id: UUID
    counterparty_staff_user_id: UUID
    counterparty_display_name: str
    requester_schedule_id: UUID
    counterparty_schedule_id: UUID | None
    requester_schedule: ExchangeScheduleSummary
    counterparty_schedule: ExchangeScheduleSummary | None
    note: str | None
    counterparty_response_note: str | None
    manager_decision_reason: str | None
    cancellation_reason: str | None
    requester_replacement_schedule_id: UUID | None
    counterparty_replacement_schedule_id: UUID | None
    recorded_create_operation_id: UUID
    recorded_last_operation_id: UUID
    counterparty_responded_at: datetime | None
    manager_decided_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    can_counterparty_accept: bool
    can_counterparty_decline: bool
    can_cancel: bool
    can_approve: bool
    can_reject: bool


class ShiftSwapList(BaseModel):
    items: list[ShiftSwapResponse]
    total: int
    generated_at: datetime


class SwapCandidateResponse(BaseModel):
    candidate_key: str
    kind: SwapKind
    counterparty_membership_id: UUID
    counterparty_staff_user_id: UUID
    counterparty_display_name: str
    counterparty_schedule_id: UUID | None
    counterparty_schedule: ExchangeScheduleSummary | None
    eligibility_reasons: list[str]
    can_propose: bool


class SwapCandidateList(BaseModel):
    items: list[SwapCandidateResponse]
    total: int
    generated_at: datetime
