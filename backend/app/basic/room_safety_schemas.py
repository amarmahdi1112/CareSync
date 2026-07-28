"""Strict public schemas for the 0041 live room operations slice."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _readable_reason(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) < 5:
        raise ValueError("reason must contain at least five non-whitespace characters")
    if len(normalized) > 500:
        raise ValueError("reason must contain at most 500 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError("reason cannot contain control characters")
    return normalized


class PresenceStartIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    staff_shift_id: UUID
    facility_id: UUID
    room_id: UUID


class PresenceMoveIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_session_id: UUID
    expected_version: int = Field(ge=1)
    destination_room_id: UUID
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _readable_reason(value)


class PresenceEndIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_session_id: UUID
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _readable_reason(value)


class ExceptionAcknowledgeIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _readable_reason(value)


class ReleaseReconciliationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_active_facility_count: int = Field(ge=0)
    expected_facility_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_facility_ids: list[UUID]

    @model_validator(mode="after")
    def validate_expected_facility_set(self) -> ReleaseReconciliationIntent:
        if len(self.expected_facility_ids) != len(
            set(self.expected_facility_ids)
        ):
            raise ValueError("expected_facility_ids must be unique")
        if self.expected_active_facility_count != len(
            self.expected_facility_ids
        ):
            raise ValueError(
                "expected_active_facility_count must match "
                "expected_facility_ids"
            )
        self.expected_facility_ids = sorted(
            self.expected_facility_ids, key=str
        )
        return self


PresenceSource = Literal["scheduled_room", "single_assignment", "staff_selected"]
PresenceDecisionReason = Literal[
    "no_open_shift",
    "current_presence_confirmed",
    "room_selection_required",
    "no_eligible_room",
    "source_integrity_unknown",
]
BoardState = Literal[
    "attention",
    "unknown",
    "no_active_configured_target_signal",
    "not_evaluated",
]
CapacityState = Literal[
    "within_configured_capacity",
    "above_configured_capacity",
    "unknown",
]
TargetState = Literal[
    "target_met",
    "confirmed_staff_below_target",
    "outside_configured_window",
    "not_configured",
    "unknown",
]
ExceptionState = Literal["open", "acknowledged", "resolved"]
ExceptionCondition = Literal[
    "confirmed_children_above_configured_room_capacity",
    "confirmed_staff_below_configured_room_target",
    "open_shift_staff_without_current_room",
    "present_child_without_active_room",
    "source_integrity_unknown",
]


class OpenShiftSummary(BaseModel):
    id: UUID
    facility_id: UUID
    scheduled_shift_id: UUID | None
    clocked_in_at: datetime


class CurrentPresenceSummary(BaseModel):
    id: UUID
    staff_shift_id: UUID
    facility_id: UUID
    room_id: UUID
    room_name: str
    source: PresenceSource
    started_at: datetime
    version: int


class EligibleRoomSummary(BaseModel):
    id: UUID
    facility_id: UUID
    name: str


class StaffPresenceProjection(BaseModel):
    schema_version: Literal["staff-room-presence-v1"] = "staff-room-presence-v1"
    organization_id: UUID
    membership_id: UUID
    generated_at: datetime
    data_through_realtime_sequence: int | None
    open_shift: OpenShiftSummary | None
    current_presence: CurrentPresenceSummary | None
    eligible_rooms: list[EligibleRoomSummary]
    room_presence_required: bool
    decision_reason: PresenceDecisionReason


STANDING_OPERATIONAL_BOUNDARY = (
    "Operational configured-target evidence only. CareSync does not calculate "
    "or certify regulatory ratios, qualifications, group-size rules, licensing "
    "compliance or adequate supervision."
)


class RoomSafetyCapability(BaseModel):
    schema_version: Literal["0041"] = "0041"
    capability: Literal[
        "live_room_presence_safety_board"
    ] = "live_room_presence_safety_board"
    runtime_available: Literal[True] = True
    self_presence_read_path: Literal[
        "/api/v1/staff/self/room-presence"
    ] = "/api/v1/staff/self/room-presence"
    self_live_board_path: Literal[
        "/api/v1/staff/self/room-safety/live"
    ] = "/api/v1/staff/self/room-safety/live"
    start_path: Literal[
        "/api/v1/staff/self/room-presence/start"
    ] = "/api/v1/staff/self/room-presence/start"
    move_path: Literal[
        "/api/v1/staff/self/room-presence/move"
    ] = "/api/v1/staff/self/room-presence/move"
    end_path: Literal[
        "/api/v1/staff/self/room-presence/end"
    ] = "/api/v1/staff/self/room-presence/end"
    manager_live_board_path: Literal[
        "/api/v1/room-safety/live"
    ] = "/api/v1/room-safety/live"
    manager_exceptions_path: Literal[
        "/api/v1/room-safety/exceptions"
    ] = "/api/v1/room-safety/exceptions"
    manager_action_target_path_template: Literal[
        "/api/v1/room-safety/exceptions/{exception_id}/action-target"
    ] = "/api/v1/room-safety/exceptions/{exception_id}/action-target"
    manager_acknowledge_path_template: Literal[
        "/api/v1/room-safety/exceptions/{exception_id}/acknowledge"
    ] = "/api/v1/room-safety/exceptions/{exception_id}/acknowledge"
    online_only: Literal[True] = True
    operational_configured_target_only: Literal[True] = True
    regulatory_compliance_certified: Literal[False] = False


class ConfiguredTargetProjection(BaseModel):
    state: TargetState
    required_staff: int | None
    window_start_local: str | None
    window_end_local: str | None


class RoomLiveRow(BaseModel):
    room_id: UUID
    room_name: str
    confirmed_children: int | None
    configured_room_capacity: int | None
    capacity_state: CapacityState
    confirmed_staff: int | None
    configured_target: ConfiguredTargetProjection
    overall_state: BoardState
    active_exception_ids: list[UUID]
    data_quality_reason_codes: list[str]


class FacilityLiveSummary(BaseModel):
    confirmed_children: int | None
    present_children_without_active_room: int | None
    open_shift_staff: int | None
    located_staff: int | None
    unlocated_staff: int | None
    configured_target: ConfiguredTargetProjection
    overall_state: BoardState
    active_exception_count: int
    data_quality_reason_codes: list[str]


class FacilityLiveBoard(BaseModel):
    schema_version: Literal["live-room-safety-v1"] = "live-room-safety-v1"
    organization_id: UUID
    facility_id: UUID
    facility_timezone: str
    view_scope: Literal["facility"] = "facility"
    as_of: datetime
    generated_at: datetime
    data_through_realtime_sequence: int | None
    operational_configured_target_only: Literal[True] = True
    regulatory_compliance_certified: Literal[False] = False
    standing_boundary: str = STANDING_OPERATIONAL_BOUNDARY
    facility: FacilityLiveSummary
    rooms: list[RoomLiveRow]


class StaffRoomLiveBoard(BaseModel):
    schema_version: Literal["live-room-safety-v1"] = "live-room-safety-v1"
    organization_id: UUID
    facility_id: UUID | None
    facility_timezone: str | None
    view_scope: Literal["current_room"] = "current_room"
    as_of: datetime
    generated_at: datetime
    data_through_realtime_sequence: int | None
    operational_configured_target_only: Literal[True] = True
    regulatory_compliance_certified: Literal[False] = False
    standing_boundary: str = STANDING_OPERATIONAL_BOUNDARY
    current_room: RoomLiveRow | None
    unavailable_reason: Literal[
        "no_open_shift", "room_presence_required", "source_integrity_unknown"
    ] | None


class ExceptionItem(BaseModel):
    id: UUID
    facility_id: UUID
    scope_kind: Literal["facility", "room"]
    scope_id: UUID
    room_id: UUID | None
    condition_code: ExceptionCondition
    state: ExceptionState
    version: int
    opened_at: datetime
    materially_changed_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by_user_id: UUID | None
    acknowledgement_reason: str | None
    resolved_at: datetime | None
    observed_value: int | None
    configured_value: int | None
    source_integrity_reason_codes: list[str]
    action_target_path: str


class ExceptionPage(BaseModel):
    schema_version: Literal[
        "room-operational-exceptions-v1"
    ] = "room-operational-exceptions-v1"
    organization_id: UUID
    facility_id: UUID
    state_filter: Literal["open", "acknowledged", "resolved", "all"]
    items: list[ExceptionItem]
    next_cursor: str | None
    generated_at: datetime


class ExceptionActionTarget(BaseModel):
    schema_version: Literal[
        "room-operational-exception-action-target-v1"
    ] = "room-operational-exception-action-target-v1"
    organization_id: UUID
    facility_id: UUID
    room_id: UUID | None
    exception_id: UUID
    state: ExceptionState
    version: int
    visible: Literal[True] = True
    action_path: Literal["/rooms"] = "/rooms"
    generated_at: datetime


PresenceCommandKind = Literal[
    "start",
    "move",
    "end",
    "clock_in_presence",
    "clock_out_presence",
    "access_revoked_presence",
]
PresenceEventType = Literal[
    "started",
    "moved",
    "ended",
    "clock_started_presence",
    "clock_ended_presence",
    "access_revoked_presence",
]


class PresenceCommandReceipt(BaseModel):
    organization_id: UUID
    actor_user_id: UUID
    membership_id: UUID
    command_kind: PresenceCommandKind
    client_operation_id: UUID
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_type: PresenceEventType
    staff_shift_id: UUID
    facility_id: UUID
    from_session_id: UUID | None
    to_session_id: UUID | None
    from_room_id: UUID | None
    to_room_id: UUID | None
    occurred_at: datetime


class PresenceCommandResponse(BaseModel):
    organization_id: UUID
    client_operation_id: UUID
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool
    receipt: PresenceCommandReceipt
    affected_session_id: UUID
    current_resource_version: int | None
    current_presence: StaffPresenceProjection
    generated_at: datetime


class ExceptionAcknowledgeReceipt(BaseModel):
    organization_id: UUID
    actor_user_id: UUID
    event_id: UUID
    command_kind: Literal[
        "room_operational_exception_acknowledge"
    ] = "room_operational_exception_acknowledge"
    event_type: Literal["acknowledged"] = "acknowledged"
    client_operation_id: UUID
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exception_id: UUID
    facility_id: UUID
    room_id: UUID | None
    expected_version: int
    resulting_version: int
    occurred_at: datetime


class ExceptionAcknowledgeResponse(BaseModel):
    organization_id: UUID
    client_operation_id: UUID
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool
    receipt: ExceptionAcknowledgeReceipt
    exception: ExceptionItem
    generated_at: datetime


class ReleaseFacilityReceipt(BaseModel):
    facility_id: UUID
    audit_event_id: UUID
    client_operation_id: UUID
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconciled_at: datetime


class ReleaseReconciliationStatus(BaseModel):
    schema_version: Literal["0041"] = "0041"
    organization_id: UUID
    foundation_available: bool
    complete: bool
    active_facility_count: int
    completed_facility_count: int
    missing_facility_ids: list[UUID]
    facility_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    organization_receipt_id: UUID | None
    generated_at: datetime


class ReleaseReconciliationResponse(BaseModel):
    schema_version: Literal["0041"] = "0041"
    organization_id: UUID
    client_operation_id: UUID
    replayed: bool
    complete: Literal[True] = True
    facility_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    organization_receipt_id: UUID
    facility_receipts: list[ReleaseFacilityReceipt]
    generated_at: datetime
