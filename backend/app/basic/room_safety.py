"""0041 server-confirmed room presence and operational configured-target board.

This module intentionally computes operational evidence only.  It does not
interpret licensing, qualification, group-size, supervision, or regulatory
rules.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.basic.dependencies import BasicContext, refresh_basic_context
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    AuditEvent,
    Facility,
    MembershipRoomAssignment,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    Room,
    RoomOperationalExceptionEvent,
    RoomOperationalExceptionHead,
    ScheduledStaffShift,
    StaffCoverageTargetProfile,
    StaffRoomPresenceEvent,
    StaffRoomPresenceSession,
    StaffShift,
)
from app.basic.notifications import notify_user
from app.basic.room_safety_schemas import (
    ConfiguredTargetProjection,
    CurrentPresenceSummary,
    EligibleRoomSummary,
    ExceptionAcknowledgeReceipt,
    ExceptionAcknowledgeResponse,
    ExceptionActionTarget,
    ExceptionItem,
    ExceptionPage,
    FacilityLiveBoard,
    FacilityLiveSummary,
    OpenShiftSummary,
    PresenceCommandReceipt,
    PresenceCommandResponse,
    ReleaseFacilityReceipt,
    ReleaseReconciliationResponse,
    ReleaseReconciliationStatus,
    RoomLiveRow,
    RoomSafetyCapability,
    StaffPresenceProjection,
    StaffRoomLiveBoard,
)
from app.basic.security import audit
from app.basic.staff_workforce import canonical_stored_coverage_windows

CAPABILITY = "live_room_presence_safety_board"
RELEASE_SCHEMA_VERSION = "0041"
RELEASE_FACILITY_ACTION = "room_safety.release_reconciliation_facility_completed"
RELEASE_ORGANIZATION_ACTION = "room_safety.release_reconciliation_completed"
MAX_EXCEPTION_PAGE = 100
DEFAULT_EXCEPTION_PAGE = 50


def aware_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return False
    return True


def capability_marker() -> RoomSafetyCapability:
    return RoomSafetyCapability()


def foundation_enabled(
    request: Request,
    _session: Session | None = None,
    _organization_id: UUID | None = None,
) -> bool:
    explicit = getattr(
        request.app.state,
        "live_room_presence_safety_board_foundation_enabled",
        None,
    )
    if explicit is not None:
        return bool(explicit)
    # Backward-compatible only for isolated unit fixtures that predate the
    # separate foundation/cutover marker. Production sets the explicit field.
    return bool(
        getattr(request.app.state, "live_room_presence_safety_board_enabled", False)
    )


def capability_enabled(
    request: Request,
    session: Session,
    organization_id: UUID,
) -> bool:
    return foundation_enabled(request) and release_reconciliation_complete(
        session, organization_id
    )


def require_foundation(request: Request) -> None:
    if not foundation_enabled(request):
        raise HTTPException(
            503,
            detail={
                "code": "room_presence_foundation_unavailable",
                "message": "The live room-presence foundation is unavailable.",
            },
        )


def require_capability(
    request: Request,
    session: Session,
    organization_id: UUID,
) -> None:
    require_foundation(request)
    if not release_reconciliation_complete(session, organization_id):
        raise HTTPException(
            503,
            detail={
                "code": "room_presence_release_reconciliation_required",
                "message": (
                    "The notification-suppressed 0041 release reconciliation "
                    "must complete before this capability is advertised."
                ),
                "status_path": "/api/v1/room-safety/release-reconciliation/status",
            },
        )


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized_reason(value: str) -> str:
    return " ".join(value.split())


def presence_intent(
    *,
    context: BasicContext,
    command_kind: Literal["start", "move", "end"],
    operation_id: UUID,
    shift: StaffShift,
    expected_session_id: UUID | None = None,
    expected_version: int | None = None,
    destination_room_id: UUID | None = None,
    room_id: UUID | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "actor_user_id": str(context.user.id),
        "client_operation_id": str(operation_id),
        "command_kind": command_kind,
        "facility_id": str(shift.facility_id),
        "membership_id": str(context.membership.id),
        "organization_id": str(context.organization.id),
        "staff_shift_id": str(shift.id),
    }
    if room_id is not None:
        value["room_id"] = str(room_id)
    if expected_session_id is not None:
        value["expected_session_id"] = str(expected_session_id)
    if expected_version is not None:
        value["expected_version"] = expected_version
    if destination_room_id is not None:
        value["destination_room_id"] = str(destination_room_id)
    if reason is not None:
        value["reason"] = normalized_reason(reason)
    return value


def exception_ack_intent(
    *,
    context: BasicContext,
    operation_id: UUID,
    value: RoomOperationalExceptionHead,
    expected_version: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "actor_user_id": str(context.user.id),
        "client_operation_id": str(operation_id),
        "command_kind": "room_operational_exception_acknowledge",
        "exception_id": str(value.id),
        "expected_version": expected_version,
        "facility_id": str(value.facility_id),
        "organization_id": str(context.organization.id),
        "reason": normalized_reason(reason),
        "room_id": str(value.room_id) if value.room_id else None,
    }


def _set_operation_context(
    session: Session,
    *,
    operation_id: UUID,
    server_derived: bool = False,
) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(
        text(
            "SELECT pg_catalog.set_config("
            "'app.current_room_presence_operation_id',:operation_id,true)"
        ),
        {"operation_id": str(operation_id)},
    )
    session.execute(
        text(
            "SELECT pg_catalog.set_config("
            "'app.current_room_presence_server_derived',:value,true)"
        ),
        {"value": "true" if server_derived else "false"},
    )


def _operation_lock(
    session: Session,
    organization_id: UUID,
    operation_id: UUID,
) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(:key,41))"),
        {"key": f"{organization_id}:{operation_id}"},
    )


def _facility_projection_lock(
    session: Session,
    organization_id: UUID,
    facility_id: UUID,
) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(:key,41))"),
        {"key": f"room-safety:{organization_id}:{facility_id}"},
    )


def _release_facility_set_lock(
    session: Session,
    organization_id: UUID,
) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(:key,41))"),
        {"key": f"room-safety-release-facility-set:{organization_id}"},
    )


def lock_facility_projection(
    session: Session,
    organization_id: UUID,
    facility_id: UUID,
) -> None:
    """Serialize every source write with coherent facility projection reads."""

    _facility_projection_lock(session, organization_id, facility_id)


def lock_release_facility_set(
    session: Session,
    organization_id: UUID,
) -> None:
    """Serialize cutover snapshots with active-facility lifecycle changes."""

    _release_facility_set_lock(session, organization_id)


def _latest_realtime_sequence(session: Session, organization_id: UUID) -> int | None:
    return session.scalar(
        select(func.max(RealtimeEvent.sequence_id)).where(
            RealtimeEvent.organization_id == organization_id
        )
    )


def _eligible_rooms(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    facility_id: UUID | None = None,
) -> list[Room]:
    statement = (
        select(Room)
        .join(
            MembershipRoomAssignment,
            (MembershipRoomAssignment.organization_id == Room.organization_id)
            & (MembershipRoomAssignment.facility_id == Room.facility_id)
            & (MembershipRoomAssignment.room_id == Room.id),
        )
        .join(
            Facility,
            (Facility.organization_id == Room.organization_id)
            & (Facility.id == Room.facility_id),
        )
        .where(
            Room.organization_id == organization_id,
            MembershipRoomAssignment.membership_id == membership_id,
            MembershipRoomAssignment.is_active.is_(True),
            Room.is_active.is_(True),
            Facility.status == "active",
        )
        .order_by(Room.name, Room.id)
    )
    if facility_id is not None:
        statement = statement.where(Room.facility_id == facility_id)
    return list(session.scalars(statement))


def _open_shift(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    lock: bool = False,
) -> StaffShift | None:
    statement = select(StaffShift).where(
        StaffShift.organization_id == organization_id,
        StaffShift.membership_id == membership_id,
        StaffShift.status == "open",
        StaffShift.clocked_out_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    values = list(session.scalars(statement.limit(2)))
    if len(values) > 1:
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "duplicate_open_staff_shifts",
            },
        )
    return values[0] if values else None


def _current_presence(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    lock: bool = False,
) -> StaffRoomPresenceSession | None:
    statement = select(StaffRoomPresenceSession).where(
        StaffRoomPresenceSession.organization_id == organization_id,
        StaffRoomPresenceSession.membership_id == membership_id,
        StaffRoomPresenceSession.ended_at.is_(None),
    ).limit(2)
    if lock:
        statement = statement.with_for_update()
    values = list(session.scalars(statement))
    if len(values) > 1:
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "duplicate_current_room_presence",
            },
        )
    return values[0] if values else None


def _require_valid_nonterminal_shift_source(
    session: Session,
    *,
    organization_id: UUID,
    shift: StaffShift,
    as_of: datetime | None = None,
) -> None:
    """Reject contradictory shift sources before creating or moving presence.

    Terminal commands deliberately do not use this guard: an operator must
    still be able to close a stale or corrupt presence lane safely.
    """

    now = aware_utc(as_of) if as_of is not None else datetime.now(UTC)
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == organization_id,
            Facility.id == shift.facility_id,
        )
    )
    if (
        facility is None
        or facility.status != "active"
        or not _valid_timezone(facility.timezone)
        or aware_utc(shift.clocked_in_at) > now
    ):
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "open_shift_invalid",
            },
        )


def staff_presence_projection(
    session: Session,
    context: BasicContext,
    *,
    generated_at: datetime | None = None,
) -> StaffPresenceProjection:
    now = aware_utc(generated_at) if generated_at is not None else datetime.now(UTC)
    # Discover the bounded facility lock set without claiming it is canonical,
    # then acquire every relevant lane and re-read.  Capturing the realtime
    # cursor before the canonical reads also makes the no-shift case coherent:
    # a later clock-in is either detected as an unlocked source change and the
    # caller retries, or it commits after this response's data-through cursor.
    preliminary_shift = _open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    preliminary_current = _current_presence(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    locked_facility_ids = {
        value
        for value in (
            preliminary_shift.facility_id if preliminary_shift is not None else None,
            (
                preliminary_current.facility_id
                if preliminary_current is not None
                else None
            ),
        )
        if value is not None
    }
    for facility_id in sorted(locked_facility_ids, key=str):
        _facility_projection_lock(
            session,
            context.organization.id,
            facility_id,
        )
    realtime_sequence = _latest_realtime_sequence(
        session, context.organization.id
    )
    shift = _open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    current = _current_presence(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    canonical_facility_ids = {
        value
        for value in (
            shift.facility_id if shift is not None else None,
            current.facility_id if current is not None else None,
        )
        if value is not None
    }
    if not canonical_facility_ids.issubset(locked_facility_ids):
        raise HTTPException(
            409,
            detail={
                "code": "projection_changed_retry",
                "message": "Room-presence facts changed while the view was composed; retry.",
            },
        )
    facility_id = shift.facility_id if shift is not None else None
    shift_facility = (
        session.scalar(
            select(Facility).where(
                Facility.organization_id == context.organization.id,
                Facility.id == facility_id,
            )
        )
        if facility_id is not None
        else None
    )
    shift_source_valid = (
        shift is None
        or (
            shift_facility is not None
            and shift_facility.status == "active"
            and _valid_timezone(shift_facility.timezone)
            and aware_utc(shift.clocked_in_at) <= now
        )
    )
    rooms = (
        _eligible_rooms(
            session,
            organization_id=context.organization.id,
            membership_id=context.membership.id,
            facility_id=facility_id,
        )
        if shift is not None and shift_source_valid
        else []
    )
    room_by_id = {room.id: room for room in rooms}
    if not shift_source_valid or (
        current is not None
        and (
            shift is None
            or current.staff_shift_id != shift.id
            or current.facility_id != shift.facility_id
            or current.room_id not in room_by_id
            or aware_utc(current.started_at) > now
        )
    ):
        current_summary = None
        decision = "source_integrity_unknown"
    elif current is not None:
        room = room_by_id[current.room_id]
        current_summary = CurrentPresenceSummary(
            id=current.id,
            staff_shift_id=current.staff_shift_id,
            facility_id=current.facility_id,
            room_id=current.room_id,
            room_name=room.name,
            source=current.source,
            started_at=aware_utc(current.started_at),
            version=current.version,
        )
        decision = "current_presence_confirmed"
    elif shift is None:
        current_summary = None
        decision = "no_open_shift"
    elif rooms:
        current_summary = None
        decision = "room_selection_required"
    else:
        current_summary = None
        decision = "no_eligible_room"
    return StaffPresenceProjection(
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        generated_at=now,
        data_through_realtime_sequence=realtime_sequence,
        open_shift=(
            OpenShiftSummary(
                id=shift.id,
                facility_id=shift.facility_id,
                scheduled_shift_id=shift.scheduled_shift_id,
                clocked_in_at=aware_utc(shift.clocked_in_at),
            )
            if shift is not None
            else None
        ),
        current_presence=current_summary,
        eligible_rooms=[
            EligibleRoomSummary(id=room.id, facility_id=room.facility_id, name=room.name)
            for room in (
                [] if decision == "source_integrity_unknown" else rooms
            )
        ],
        room_presence_required=(
            decision in {"room_selection_required", "no_eligible_room"}
        ),
        decision_reason=decision,
    )


def _room_assignment(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    facility_id: UUID,
    room_id: UUID,
) -> Room:
    room = session.scalar(
        select(Room)
        .join(
            MembershipRoomAssignment,
            (MembershipRoomAssignment.organization_id == Room.organization_id)
            & (MembershipRoomAssignment.facility_id == Room.facility_id)
            & (MembershipRoomAssignment.room_id == Room.id),
        )
        .join(
            Facility,
            (Facility.organization_id == Room.organization_id)
            & (Facility.id == Room.facility_id),
        )
        .where(
            Room.organization_id == organization_id,
            Room.facility_id == facility_id,
            Room.id == room_id,
            Room.is_active.is_(True),
            Facility.status == "active",
            MembershipRoomAssignment.membership_id == membership_id,
            MembershipRoomAssignment.is_active.is_(True),
        )
    )
    if room is None:
        raise HTTPException(
            409,
            detail={
                "code": "room_assignment_required",
                "message": "Select an active room currently assigned to you.",
            },
        )
    return room


def _presence_event_by_operation(
    session: Session,
    *,
    organization_id: UUID,
    operation_id: UUID,
) -> StaffRoomPresenceEvent | None:
    return session.scalar(
        select(StaffRoomPresenceEvent).where(
            StaffRoomPresenceEvent.organization_id == organization_id,
            StaffRoomPresenceEvent.operation_id == operation_id,
        )
    )


def _receipt_from_event(event: StaffRoomPresenceEvent) -> PresenceCommandReceipt:
    try:
        receipt = PresenceCommandReceipt.model_validate(event.result)
    except (TypeError, ValueError):
        raise HTTPException(
            409, detail={"code": "operation_receipt_invalid"}
        ) from None
    event_type_by_command = {
        "start": "started",
        "move": "moved",
        "end": "ended",
        "clock_in_presence": "clock_started_presence",
        "clock_out_presence": "clock_ended_presence",
        "access_revoked_presence": "access_revoked_presence",
    }
    if (
        receipt.organization_id != event.organization_id
        or receipt.actor_user_id != event.actor_user_id
        or receipt.membership_id != event.membership_id
        or receipt.client_operation_id != event.operation_id
        or receipt.request_sha256 != event.request_sha256
        or receipt.event_type != event.event_type
        or event_type_by_command.get(receipt.command_kind) != event.event_type
        or receipt.staff_shift_id != event.staff_shift_id
        or receipt.facility_id != event.facility_id
        or receipt.from_session_id != event.from_session_id
        or receipt.to_session_id != event.to_session_id
        or request_sha256(dict(event.intent or {})) != event.request_sha256
    ):
        raise HTTPException(
            409, detail={"code": "operation_receipt_invalid"}
        )
    return receipt


def _require_owned_presence_event(
    event: StaffRoomPresenceEvent | None,
    context: BasicContext,
) -> None:
    if event is not None and (
        event.actor_user_id != context.user.id
        or event.membership_id != context.membership.id
    ):
        raise HTTPException(404, "Room presence operation not found")


def _replay_presence(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    digest: str,
) -> PresenceCommandResponse | None:
    event = _presence_event_by_operation(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
    )
    if event is None:
        return None
    if event.actor_user_id != context.user.id or event.membership_id != context.membership.id:
        raise HTTPException(404, "Room presence operation not found")
    if event.request_sha256 != digest:
        raise HTTPException(
            409,
            detail={
                "code": "operation_reused",
                "message": "Operation identifier was already used for a different intent.",
            },
        )
    receipt = _receipt_from_event(event)
    affected_id = receipt.to_session_id or receipt.from_session_id
    assert affected_id is not None
    current_resource_version = session.scalar(
        select(StaffRoomPresenceSession.version).where(
            StaffRoomPresenceSession.organization_id
            == context.organization.id,
            StaffRoomPresenceSession.id == affected_id,
        )
    )
    if current_resource_version is None:
        raise HTTPException(
            409, detail={"code": "operation_receipt_invalid"}
        )
    return PresenceCommandResponse(
        organization_id=context.organization.id,
        client_operation_id=operation_id,
        request_sha256=digest,
        replayed=True,
        receipt=receipt,
        affected_session_id=affected_id,
        current_resource_version=current_resource_version,
        current_presence=staff_presence_projection(session, context),
        generated_at=datetime.now(UTC),
    )


def _early_presence_replay(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    command_kind: Literal["start", "move", "end"],
    expected_fields: dict[str, Any],
) -> PresenceCommandResponse | None:
    """Recover an immutable receipt before evaluating the current lifecycle."""

    event = _presence_event_by_operation(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
    )
    if event is None:
        return None
    if event.actor_user_id != context.user.id or event.membership_id != context.membership.id:
        raise HTTPException(404, "Room presence operation not found")
    stored = dict(event.intent or {})
    required_identity = {
        "actor_user_id": str(context.user.id),
        "client_operation_id": str(operation_id),
        "command_kind": command_kind,
        "membership_id": str(context.membership.id),
        "organization_id": str(context.organization.id),
    }
    if any(stored.get(key) != value for key, value in required_identity.items()) or any(
        stored.get(key) != value for key, value in expected_fields.items()
    ):
        raise HTTPException(409, detail={"code": "operation_reused"})
    digest = request_sha256(stored)
    if digest != event.request_sha256:
        raise HTTPException(
            409,
            detail={
                "code": "operation_receipt_invalid",
                "message": "Stored room-presence receipt integrity check failed.",
            },
        )
    return _replay_presence(
        session,
        context,
        operation_id=operation_id,
        digest=digest,
    )


def _presence_event_scope_room_id(
    session: Session,
    event: StaffRoomPresenceEvent,
) -> UUID:
    receipt = _receipt_from_event(event)
    session_id = (
        receipt.from_session_id
        if receipt.event_type
        in {
            "ended",
            "clock_ended_presence",
            "access_revoked_presence",
        }
        else receipt.to_session_id
    )
    if session_id is None:
        raise HTTPException(
            409, detail={"code": "operation_receipt_invalid"}
        )
    room_id = session.scalar(
        select(StaffRoomPresenceSession.room_id).where(
            StaffRoomPresenceSession.organization_id
            == event.organization_id,
            StaffRoomPresenceSession.id == session_id,
        )
    )
    if room_id is None:
        raise HTTPException(
            409, detail={"code": "operation_receipt_invalid"}
        )
    return room_id


def _emit_presence_realtime(
    session: Session,
    *,
    organization_id: UUID,
    event_type: Literal["started", "moved", "ended"],
    event_id: UUID,
    session_id: UUID,
    facility_id: UUID,
    room_id: UUID | None,
    destination_room_id: UUID | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event_id": str(event_id),
        "facility_id": str(facility_id),
        "room_id": str(room_id) if room_id else None,
        "requires_action": False,
    }
    if destination_room_id is not None:
        payload["destination_room_id"] = str(destination_room_id)
    session.add(
        RealtimeEvent(
            id=uuid4(),
            organization_id=organization_id,
            event_type=f"staff_room_presence.{event_type}",
            entity_type="staff_room_presence",
            entity_id=session_id,
            occurred_at=datetime.now(UTC),
            payload=payload,
        )
    )


def _presence_response(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    digest: str,
    receipt: PresenceCommandReceipt,
    affected: StaffRoomPresenceSession,
) -> PresenceCommandResponse:
    session.flush()
    return PresenceCommandResponse(
        organization_id=context.organization.id,
        client_operation_id=operation_id,
        request_sha256=digest,
        replayed=False,
        receipt=receipt,
        affected_session_id=affected.id,
        current_resource_version=affected.version,
        current_presence=staff_presence_projection(session, context),
        generated_at=datetime.now(UTC),
    )


def _refresh_self_presence_context(
    session: Session,
    context: BasicContext,
    *,
    facility_id: UUID,
    room_id: UUID | None = None,
) -> BasicContext:
    """Re-authorize self presence after winning the facility lane."""

    current = refresh_basic_context(
        session,
        context,
        required_all_permissions=("shift:clock", "care_roster:read"),
        conceal_detail="Room presence resource not found",
    )
    if facility_id not in current.assigned_facility_ids or (
        room_id is not None and room_id not in current.assigned_room_ids
    ):
        raise HTTPException(404, "Room presence resource not found")
    return current


def _refresh_manager_room_safety_context(
    session: Session,
    context: BasicContext,
    *,
    facility_id: UUID,
) -> BasicContext:
    current = refresh_basic_context(
        session,
        context,
        required_all_permissions=(
            "facility:read",
            "care_roster:read",
            "staff:manage_educators",
        ),
        conceal_detail="Room operational exception not found",
    )
    if (
        not current.organization_wide
        and facility_id not in current.assigned_facility_ids
    ):
        raise HTTPException(404, "Room operational exception not found")
    return current


def start_presence(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    shift_id: UUID,
    facility_id: UUID,
    room_id: UUID,
) -> PresenceCommandResponse:
    _operation_lock(session, context.organization.id, operation_id)
    existing_event = _presence_event_by_operation(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
    )
    _require_owned_presence_event(existing_event, context)
    lane_facility_id = (
        existing_event.facility_id
        if existing_event is not None
        else facility_id
    )
    _facility_projection_lock(
        session, context.organization.id, lane_facility_id
    )
    authorization_room_id = (
        _presence_event_scope_room_id(session, existing_event)
        if existing_event is not None
        else room_id
    )
    context = _refresh_self_presence_context(
        session,
        context,
        facility_id=lane_facility_id,
        room_id=authorization_room_id,
    )
    replay = _early_presence_replay(
        session,
        context,
        operation_id=operation_id,
        command_kind="start",
        expected_fields={
            "facility_id": str(facility_id),
            "room_id": str(room_id),
            "staff_shift_id": str(shift_id),
        },
    )
    if replay is not None:
        return replay
    shift = _open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    if shift is None or shift.id != shift_id or shift.facility_id != facility_id:
        raise HTTPException(
            409,
            detail={
                "code": "open_shift_required",
                "message": "An open shift at this facility is required.",
            },
        )
    _require_valid_nonterminal_shift_source(
        session,
        organization_id=context.organization.id,
        shift=shift,
    )
    intent = presence_intent(
        context=context,
        command_kind="start",
        operation_id=operation_id,
        shift=shift,
        room_id=room_id,
    )
    digest = request_sha256(intent)
    if (
        _current_presence(
            session,
            organization_id=context.organization.id,
            membership_id=context.membership.id,
            lock=True,
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "room_presence_already_active"})
    _room_assignment(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=facility_id,
        room_id=room_id,
    )
    _set_operation_context(session, operation_id=operation_id)
    now = datetime.now(UTC)
    value = StaffRoomPresenceSession(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=facility_id,
        room_id=room_id,
        source="staff_selected",
        started_at=now,
        start_operation_id=operation_id,
        started_by_user_id=context.user.id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    event_id = uuid4()
    receipt = PresenceCommandReceipt(
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        command_kind="start",
        client_operation_id=operation_id,
        request_sha256=digest,
        event_type="started",
        staff_shift_id=shift.id,
        facility_id=facility_id,
        from_session_id=None,
        to_session_id=value.id,
        from_room_id=None,
        to_room_id=room_id,
        occurred_at=now,
    )
    session.add(value)
    # The event has an immediate composite FK to this new session.  Flush the
    # command head first; the deferred bundle trigger still verifies the
    # matching event at transaction end.
    session.flush([value])
    event = StaffRoomPresenceEvent(
        id=event_id,
        organization_id=context.organization.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=facility_id,
        event_type="started",
        from_session_id=None,
        to_session_id=value.id,
        request_sha256=digest,
        intent=intent,
        result=receipt.model_dump(mode="json"),
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    session.flush([event])
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_room_presence.started",
        entity_type="staff_room_presence",
        entity_id=value.id,
        facility_id=facility_id,
        details={"operation_id": str(operation_id), "room_id": str(room_id)},
    )
    _emit_presence_realtime(
        session,
        organization_id=context.organization.id,
        event_type="started",
        event_id=event_id,
        session_id=value.id,
        facility_id=facility_id,
        room_id=room_id,
    )
    return _presence_response(
        session,
        context,
        operation_id=operation_id,
        digest=digest,
        receipt=receipt,
        affected=value,
    )


def move_presence(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    expected_session_id: UUID,
    expected_version: int,
    destination_room_id: UUID,
    reason: str,
) -> PresenceCommandResponse:
    _operation_lock(session, context.organization.id, operation_id)
    existing_event = _presence_event_by_operation(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
    )
    _require_owned_presence_event(existing_event, context)
    expected_scope = session.execute(
        select(
            StaffRoomPresenceSession.facility_id,
            StaffRoomPresenceSession.room_id,
        ).where(
            StaffRoomPresenceSession.organization_id
            == context.organization.id,
            StaffRoomPresenceSession.membership_id
            == context.membership.id,
            StaffRoomPresenceSession.id == expected_session_id,
        )
    ).first()
    if existing_event is None and expected_scope is None:
        raise HTTPException(409, detail={"code": "stale_room_presence"})
    expected_facility_id = (
        existing_event.facility_id
        if existing_event is not None
        else expected_scope.facility_id
    )
    _facility_projection_lock(
        session, context.organization.id, expected_facility_id
    )
    authorization_room_id = (
        _presence_event_scope_room_id(session, existing_event)
        if existing_event is not None
        else destination_room_id
    )
    context = _refresh_self_presence_context(
        session,
        context,
        facility_id=expected_facility_id,
        room_id=authorization_room_id,
    )
    replay = _early_presence_replay(
        session,
        context,
        operation_id=operation_id,
        command_kind="move",
        expected_fields={
            "destination_room_id": str(destination_room_id),
            "expected_session_id": str(expected_session_id),
            "expected_version": expected_version,
            "reason": normalized_reason(reason),
        },
    )
    if replay is not None:
        return replay
    shift = _open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    if shift is None:
        raise HTTPException(409, detail={"code": "open_shift_required"})
    _require_valid_nonterminal_shift_source(
        session,
        organization_id=context.organization.id,
        shift=shift,
    )
    intent = presence_intent(
        context=context,
        command_kind="move",
        operation_id=operation_id,
        shift=shift,
        expected_session_id=expected_session_id,
        expected_version=expected_version,
        destination_room_id=destination_room_id,
        reason=reason,
    )
    digest = request_sha256(intent)
    current = _current_presence(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    if (
        current is None
        or current.id != expected_session_id
        or current.version != expected_version
    ):
        raise HTTPException(
            409,
            detail={
                "code": "stale_room_presence",
                "message": "Current room presence changed; refresh before moving.",
            },
        )
    if (
        current.staff_shift_id != shift.id
        or current.facility_id != shift.facility_id
        or aware_utc(current.started_at) > datetime.now(UTC)
    ):
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "current_room_presence_invalid",
            },
        )
    if current.room_id == destination_room_id:
        raise HTTPException(409, detail={"code": "room_presence_same_room"})
    _room_assignment(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=current.facility_id,
        room_id=destination_room_id,
    )
    _set_operation_context(session, operation_id=operation_id)
    now = datetime.now(UTC)
    destination = StaffRoomPresenceSession(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=current.facility_id,
        room_id=destination_room_id,
        source="staff_selected",
        started_at=now,
        start_operation_id=operation_id,
        started_by_user_id=context.user.id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    current.ended_at = now
    current.end_reason = "moved"
    current.end_operation_id = operation_id
    current.ended_by_user_id = context.user.id
    current.version = 2
    current.updated_at = now
    # Release the partial-unique open lane before inserting the destination.
    # PostgreSQL's command bundle trigger is deferred, so the immutable move
    # event can still be inserted later in this same transaction.
    session.flush([current])
    event_id = uuid4()
    receipt = PresenceCommandReceipt(
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        command_kind="move",
        client_operation_id=operation_id,
        request_sha256=digest,
        event_type="moved",
        staff_shift_id=shift.id,
        facility_id=current.facility_id,
        from_session_id=current.id,
        to_session_id=destination.id,
        from_room_id=current.room_id,
        to_room_id=destination_room_id,
        occurred_at=now,
    )
    session.add(destination)
    session.flush([destination])
    event = StaffRoomPresenceEvent(
        id=event_id,
        organization_id=context.organization.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=current.facility_id,
        event_type="moved",
        from_session_id=current.id,
        to_session_id=destination.id,
        request_sha256=digest,
        intent=intent,
        result=receipt.model_dump(mode="json"),
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    session.flush([event])
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_room_presence.moved",
        entity_type="staff_room_presence",
        entity_id=destination.id,
        facility_id=current.facility_id,
        details={
            "operation_id": str(operation_id),
            "from_room_id": str(current.room_id),
            "to_room_id": str(destination_room_id),
            "reason": normalized_reason(reason),
        },
    )
    _emit_presence_realtime(
        session,
        organization_id=context.organization.id,
        event_type="moved",
        event_id=event_id,
        session_id=destination.id,
        facility_id=current.facility_id,
        room_id=current.room_id,
        destination_room_id=destination_room_id,
    )
    return _presence_response(
        session,
        context,
        operation_id=operation_id,
        digest=digest,
        receipt=receipt,
        affected=destination,
    )


def end_presence(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    expected_session_id: UUID,
    expected_version: int,
    reason: str,
) -> PresenceCommandResponse:
    _operation_lock(session, context.organization.id, operation_id)
    existing_event = _presence_event_by_operation(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
    )
    _require_owned_presence_event(existing_event, context)
    expected_scope = session.execute(
        select(
            StaffRoomPresenceSession.facility_id,
            StaffRoomPresenceSession.room_id,
        ).where(
            StaffRoomPresenceSession.organization_id
            == context.organization.id,
            StaffRoomPresenceSession.membership_id
            == context.membership.id,
            StaffRoomPresenceSession.id == expected_session_id,
        )
    ).first()
    if existing_event is None and expected_scope is None:
        raise HTTPException(409, detail={"code": "stale_room_presence"})
    expected_facility_id = (
        existing_event.facility_id
        if existing_event is not None
        else expected_scope.facility_id
    )
    _facility_projection_lock(
        session, context.organization.id, expected_facility_id
    )
    authorization_room_id = (
        _presence_event_scope_room_id(session, existing_event)
        if existing_event is not None
        else expected_scope.room_id
    )
    context = _refresh_self_presence_context(
        session,
        context,
        facility_id=expected_facility_id,
        room_id=authorization_room_id,
    )
    replay = _early_presence_replay(
        session,
        context,
        operation_id=operation_id,
        command_kind="end",
        expected_fields={
            "expected_session_id": str(expected_session_id),
            "expected_version": expected_version,
            "reason": normalized_reason(reason),
        },
    )
    if replay is not None:
        return replay
    shift = _open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    if shift is None:
        raise HTTPException(409, detail={"code": "open_shift_required"})
    intent = presence_intent(
        context=context,
        command_kind="end",
        operation_id=operation_id,
        shift=shift,
        expected_session_id=expected_session_id,
        expected_version=expected_version,
        reason=reason,
    )
    digest = request_sha256(intent)
    current = _current_presence(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    if (
        current is None
        or current.id != expected_session_id
        or current.version != expected_version
    ):
        raise HTTPException(409, detail={"code": "stale_room_presence"})
    _set_operation_context(session, operation_id=operation_id)
    now = datetime.now(UTC)
    current.ended_at = now
    current.end_reason = "staff_ended"
    current.end_operation_id = operation_id
    current.ended_by_user_id = context.user.id
    current.version = 2
    current.updated_at = now
    event_id = uuid4()
    receipt = PresenceCommandReceipt(
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        command_kind="end",
        client_operation_id=operation_id,
        request_sha256=digest,
        event_type="ended",
        staff_shift_id=shift.id,
        facility_id=current.facility_id,
        from_session_id=current.id,
        to_session_id=None,
        from_room_id=current.room_id,
        to_room_id=None,
        occurred_at=now,
    )
    session.add(current)
    session.flush([current])
    event = StaffRoomPresenceEvent(
        id=event_id,
        organization_id=context.organization.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=current.facility_id,
        event_type="ended",
        from_session_id=current.id,
        to_session_id=None,
        request_sha256=digest,
        intent=intent,
        result=receipt.model_dump(mode="json"),
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    session.flush([event])
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_room_presence.ended",
        entity_type="staff_room_presence",
        entity_id=current.id,
        facility_id=current.facility_id,
        details={
            "operation_id": str(operation_id),
            "room_id": str(current.room_id),
            "reason": normalized_reason(reason),
        },
    )
    _emit_presence_realtime(
        session,
        organization_id=context.organization.id,
        event_type="ended",
        event_id=event_id,
        session_id=current.id,
        facility_id=current.facility_id,
        room_id=current.room_id,
    )
    return _presence_response(
        session,
        context,
        operation_id=operation_id,
        digest=digest,
        receipt=receipt,
        affected=current,
    )


def create_clock_in_presence(
    session: Session,
    context: BasicContext,
    *,
    shift: StaffShift,
    operation_id: UUID,
    scheduled_shift: ScheduledStaffShift | None,
    explicit_room_id: UUID | None,
) -> PresenceCommandReceipt | None:
    """Derive at most one eligible room and bind it to the clock transaction."""

    _facility_projection_lock(
        session, context.organization.id, shift.facility_id
    )
    eligible = _eligible_rooms(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=shift.facility_id,
    )
    eligible_by_id = {room.id: room for room in eligible}
    room: Room | None = None
    source: Literal["scheduled_room", "single_assignment", "staff_selected"] | None = None
    if scheduled_shift is not None and scheduled_shift.room_id is not None:
        room = eligible_by_id.get(scheduled_shift.room_id)
        if room is None:
            raise HTTPException(
                409,
                detail={
                    "code": "scheduled_room_not_eligible",
                    "message": (
                        "The acknowledged shift room is not an active assigned room; "
                        "the schedule or room access must be corrected."
                    ),
                },
            )
        source = "scheduled_room"
    elif explicit_room_id is not None:
        room = eligible_by_id.get(explicit_room_id)
        if room is None:
            raise HTTPException(409, detail={"code": "room_assignment_required"})
        source = "staff_selected"
    elif len(eligible) == 1:
        room = eligible[0]
        source = "single_assignment"
    if room is None or source is None:
        return None
    now = aware_utc(shift.clocked_in_at)
    intent = {
        "actor_user_id": str(context.user.id),
        "client_operation_id": str(operation_id),
        "command_kind": "clock_in_presence",
        "facility_id": str(shift.facility_id),
        "membership_id": str(context.membership.id),
        "organization_id": str(context.organization.id),
        "requested_room_id": (
            str(explicit_room_id) if explicit_room_id is not None else None
        ),
        "room_id": str(room.id),
        "source": source,
        "staff_shift_id": str(shift.id),
    }
    digest = request_sha256(intent)
    _set_operation_context(session, operation_id=operation_id)
    value = StaffRoomPresenceSession(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=shift.facility_id,
        room_id=room.id,
        source=source,
        started_at=now,
        start_operation_id=operation_id,
        started_by_user_id=context.user.id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    event_id = uuid4()
    receipt = PresenceCommandReceipt(
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        command_kind="clock_in_presence",
        client_operation_id=operation_id,
        request_sha256=digest,
        event_type="clock_started_presence",
        staff_shift_id=shift.id,
        facility_id=shift.facility_id,
        from_session_id=None,
        to_session_id=value.id,
        from_room_id=None,
        to_room_id=room.id,
        occurred_at=now,
    )
    session.add(value)
    session.flush([value])
    event = StaffRoomPresenceEvent(
        id=event_id,
        organization_id=context.organization.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        membership_id=context.membership.id,
        staff_shift_id=shift.id,
        facility_id=shift.facility_id,
        event_type="clock_started_presence",
        from_session_id=None,
        to_session_id=value.id,
        request_sha256=digest,
        intent=intent,
        result=receipt.model_dump(mode="json"),
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    session.flush([event])
    _emit_presence_realtime(
        session,
        organization_id=context.organization.id,
        event_type="started",
        event_id=event_id,
        session_id=value.id,
        facility_id=shift.facility_id,
        room_id=room.id,
    )
    return receipt


def _terminal_presence_operation_id(
    operation_id: UUID,
    *,
    command_kind: str,
    session_id: UUID,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        (
            "caresync:0041:terminal-presence:"
            f"{command_kind}:{operation_id}:{session_id}"
        ),
    )


def _close_terminal_presences(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    command_kind: Literal[
        "clock_out_presence", "access_revoked_presence"
    ],
    event_type: Literal[
        "clock_ended_presence", "access_revoked_presence"
    ],
    end_reason: Literal["clocked_out", "access_revoked"],
    preferred_shift_id: UUID | None,
    locked_facility_ids: set[UUID] | None,
    audit_access_revocation: bool,
) -> list[PresenceCommandReceipt]:
    preliminary_facility_ids = set(
        session.scalars(
            select(StaffRoomPresenceSession.facility_id).where(
                StaffRoomPresenceSession.organization_id == organization_id,
                StaffRoomPresenceSession.membership_id == membership_id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
        )
    )
    if locked_facility_ids is None:
        locked_facility_ids = set(preliminary_facility_ids)
        for facility_id in sorted(locked_facility_ids, key=str):
            _facility_projection_lock(session, organization_id, facility_id)
    elif not preliminary_facility_ids.issubset(locked_facility_ids):
        raise HTTPException(
            409,
            detail={
                "code": "projection_changed_retry",
                "message": "Current room presence changed; retry the command.",
            },
        )
    values = list(
        session.scalars(
            select(StaffRoomPresenceSession)
            .where(
                StaffRoomPresenceSession.organization_id == organization_id,
                StaffRoomPresenceSession.membership_id == membership_id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
            .order_by(StaffRoomPresenceSession.id)
            .with_for_update()
        )
    )
    canonical_facility_ids = {value.facility_id for value in values}
    if not canonical_facility_ids.issubset(locked_facility_ids):
        raise HTTPException(
            409,
            detail={
                "code": "projection_changed_retry",
                "message": "Current room presence changed; retry the command.",
            },
        )
    values.sort(
        key=lambda value: (
            preferred_shift_id is None
            or value.staff_shift_id != preferred_shift_id,
            str(value.id),
        )
    )
    now = aware_utc(occurred_at)
    receipts: list[PresenceCommandReceipt] = []
    for index, current in enumerate(values):
        event_operation_id = (
            operation_id
            if index == 0
            else _terminal_presence_operation_id(
                operation_id,
                command_kind=command_kind,
                session_id=current.id,
            )
        )
        intent = {
            "actor_user_id": str(actor_user_id),
            "client_operation_id": str(event_operation_id),
            "command_kind": command_kind,
            "facility_id": str(current.facility_id),
            "membership_id": str(membership_id),
            "organization_id": str(organization_id),
            "room_id": str(current.room_id),
            "staff_shift_id": str(current.staff_shift_id),
            "terminal_root_operation_id": str(operation_id),
        }
        digest = request_sha256(intent)
        _set_operation_context(
            session, operation_id=event_operation_id
        )
        current.ended_at = now
        current.end_reason = end_reason
        current.end_operation_id = event_operation_id
        current.ended_by_user_id = actor_user_id
        current.version = 2
        current.updated_at = now
        event_id = uuid4()
        receipt = PresenceCommandReceipt(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            membership_id=membership_id,
            command_kind=command_kind,
            client_operation_id=event_operation_id,
            request_sha256=digest,
            event_type=event_type,
            staff_shift_id=current.staff_shift_id,
            facility_id=current.facility_id,
            from_session_id=current.id,
            to_session_id=None,
            from_room_id=current.room_id,
            to_room_id=None,
            occurred_at=now,
        )
        session.add(current)
        session.flush([current])
        event = StaffRoomPresenceEvent(
            id=event_id,
            organization_id=organization_id,
            operation_id=event_operation_id,
            actor_user_id=actor_user_id,
            membership_id=membership_id,
            staff_shift_id=current.staff_shift_id,
            facility_id=current.facility_id,
            event_type=event_type,
            from_session_id=current.id,
            to_session_id=None,
            request_sha256=digest,
            intent=intent,
            result=receipt.model_dump(mode="json"),
            occurred_at=now,
            created_at=now,
        )
        session.add(event)
        session.flush([event])
        if audit_access_revocation:
            audit(
                session,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="staff_room_presence.access_revoked",
                entity_type="staff_room_presence",
                entity_id=current.id,
                facility_id=current.facility_id,
                details={
                    "operation_id": str(event_operation_id),
                    "terminal_root_operation_id": str(operation_id),
                    "membership_id": str(membership_id),
                    "room_id": str(current.room_id),
                },
            )
        _emit_presence_realtime(
            session,
            organization_id=organization_id,
            event_type="ended",
            event_id=event_id,
            session_id=current.id,
            facility_id=current.facility_id,
            room_id=current.room_id,
        )
        # PostgreSQL immediate guards authenticate the transaction-local
        # operation ID. Flush one complete terminal bundle before switching
        # that context for another corrupt current row.
        session.flush()
        receipts.append(receipt)
    return receipts


def close_presence_for_clock_out(
    session: Session,
    context: BasicContext,
    *,
    shift: StaffShift,
    operation_id: UUID,
    occurred_at: datetime,
    locked_facility_ids: set[UUID] | None = None,
) -> list[PresenceCommandReceipt]:
    """Close every corrupt-or-canonical current presence during clock-out."""

    return _close_terminal_presences(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        actor_user_id=context.user.id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        command_kind="clock_out_presence",
        event_type="clock_ended_presence",
        end_reason="clocked_out",
        preferred_shift_id=shift.id,
        locked_facility_ids=locked_facility_ids,
        audit_access_revocation=False,
    )


def close_presence_for_access_revocation(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
    occurred_at: datetime | None = None,
    locked_facility_ids: set[UUID] | None = None,
) -> list[PresenceCommandReceipt]:
    """Atomically terminate every current target-member presence."""

    return _close_terminal_presences(
        session,
        organization_id=organization_id,
        membership_id=membership_id,
        actor_user_id=actor_user_id,
        operation_id=operation_id,
        occurred_at=occurred_at or datetime.now(UTC),
        command_kind="access_revoked_presence",
        event_type="access_revoked_presence",
        end_reason="access_revoked",
        preferred_shift_id=None,
        locked_facility_ids=locked_facility_ids,
        audit_access_revocation=True,
    )


def _active_target(
    profile: StaffCoverageTargetProfile | None,
    *,
    local_now: datetime,
) -> ConfiguredTargetProjection:
    if profile is None or not profile.is_specified:
        return ConfiguredTargetProjection(
            state="not_configured",
            required_staff=None,
            window_start_local=None,
            window_end_local=None,
        )
    windows = canonical_stored_coverage_windows(profile.windows)
    if windows is None:
        return ConfiguredTargetProjection(
            state="unknown",
            required_staff=None,
            window_start_local=None,
            window_end_local=None,
        )
    for window in windows:
        start = time.fromisoformat(window["start_local"])
        end = time.fromisoformat(window["end_local"])
        required = window["required_staff"]
        weekday = window["weekday"]
        local_time = local_now.timetz().replace(tzinfo=None)
        if weekday == local_now.weekday() and start <= local_time < end:
            return ConfiguredTargetProjection(
                state="target_met",
                required_staff=required,
                window_start_local=start.strftime("%H:%M"),
                window_end_local=end.strftime("%H:%M"),
            )
    return ConfiguredTargetProjection(
        state="outside_configured_window",
        required_staff=None,
        window_start_local=None,
        window_end_local=None,
    )


@dataclass(frozen=True)
class _BoardFacts:
    board: FacilityLiveBoard
    present_without_room: int


def facility_live_board(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    as_of: datetime | None = None,
) -> FacilityLiveBoard:
    _facility_projection_lock(session, organization_id, facility_id)
    now = as_of or datetime.now(UTC)
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == organization_id,
            Facility.id == facility_id,
            Facility.status == "active",
        )
    )
    if facility is None:
        raise HTTPException(404, "Facility not found")
    try:
        zone = ZoneInfo(facility.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(
            409,
            detail={"code": "source_integrity_unknown", "reason": "invalid_facility_timezone"},
        ) from None
    local_now = now.astimezone(zone)
    rooms = list(
        session.scalars(
            select(Room)
            .where(
                Room.organization_id == organization_id,
                Room.facility_id == facility_id,
                Room.is_active.is_(True),
            )
            .order_by(Room.name, Room.id)
        )
    )
    room_by_id = {room.id: room for room in rooms}
    active_intervals = list(
        session.execute(
            select(AttendanceDay, AttendanceInterval)
            .join(
                AttendanceInterval,
                (AttendanceInterval.organization_id == AttendanceDay.organization_id)
                & (AttendanceInterval.attendance_day_id == AttendanceDay.id),
            )
            .where(
                AttendanceDay.organization_id == organization_id,
                AttendanceDay.facility_id == facility_id,
                AttendanceInterval.checked_in_at <= now,
                (
                    AttendanceInterval.checked_out_at.is_(None)
                    | (AttendanceInterval.checked_out_at > now)
                ),
            )
        )
    )
    child_rows: dict[UUID, list[AttendanceDay]] = {}
    for day, _interval in active_intervals:
        if day.status == "present":
            child_rows.setdefault(day.child_id, []).append(day)
    active_interval_status_incoherent = any(
        day.status != "present" for day, _interval in active_intervals
    )
    present_days = list(
        session.scalars(
            select(AttendanceDay).where(
                AttendanceDay.organization_id == organization_id,
                AttendanceDay.facility_id == facility_id,
                AttendanceDay.service_date == local_now.date(),
                AttendanceDay.status == "present",
            )
        )
    )
    interval_day_ids = set(
        session.scalars(
            select(AttendanceInterval.attendance_day_id).where(
                AttendanceInterval.organization_id == organization_id,
                AttendanceInterval.attendance_day_id.in_(
                    [value.id for value in present_days] or [UUID(int=0)]
                ),
            )
        )
    )
    present_day_without_interval = any(
        value.id not in interval_day_ids for value in present_days
    )
    child_unknown = (
        any(len(values) != 1 for values in child_rows.values())
        or present_day_without_interval
        or active_interval_status_incoherent
    )
    child_counts = {room.id: 0 for room in rooms}
    present_without_room = 0
    if not child_unknown:
        for values in child_rows.values():
            day = values[0]
            if day.room_id not in room_by_id:
                present_without_room += 1
            else:
                child_counts[day.room_id] += 1

    shifts = list(
        session.scalars(
            select(StaffShift).where(
                StaffShift.organization_id == organization_id,
                StaffShift.facility_id == facility_id,
                StaffShift.status == "open",
                StaffShift.clocked_in_at <= now,
                StaffShift.clocked_out_at.is_(None),
            )
        )
    )
    shift_by_id = {value.id: value for value in shifts}
    shift_memberships = [value.membership_id for value in shifts]
    duplicate_open_shift = len(shift_memberships) != len(set(shift_memberships))
    presences = list(
        session.scalars(
            select(StaffRoomPresenceSession).where(
                StaffRoomPresenceSession.organization_id == organization_id,
                StaffRoomPresenceSession.facility_id == facility_id,
                StaffRoomPresenceSession.started_at <= now,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
        )
    )
    membership_ids = {
        value.membership_id for value in presences
    } | {value.membership_id for value in shifts}
    memberships = {
        value.id: value
        for value in session.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id.in_(membership_ids or {UUID(int=0)}),
            )
        )
    }
    assignments = {
        (value.membership_id, value.room_id)
        for value in session.scalars(
            select(MembershipRoomAssignment).where(
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.facility_id == facility_id,
                MembershipRoomAssignment.membership_id.in_(
                    membership_ids or {UUID(int=0)}
                ),
                MembershipRoomAssignment.is_active.is_(True),
            )
        )
    }
    valid_presences: list[StaffRoomPresenceSession] = []
    staff_unknown = duplicate_open_shift or any(
        memberships.get(value.membership_id) is None
        or memberships[value.membership_id].status != "active"
        for value in shifts
    )
    seen_memberships: set[UUID] = set()
    for value in presences:
        shift = shift_by_id.get(value.staff_shift_id)
        membership = memberships.get(value.membership_id)
        valid = (
            shift is not None
            and shift.membership_id == value.membership_id
            and value.room_id in room_by_id
            and membership is not None
            and membership.status == "active"
            and (value.membership_id, value.room_id) in assignments
            and value.membership_id not in seen_memberships
        )
        if not valid:
            staff_unknown = True
            continue
        seen_memberships.add(value.membership_id)
        valid_presences.append(value)
    staff_counts = {room.id: 0 for room in rooms}
    for value in valid_presences:
        staff_counts[value.room_id] += 1
    open_shift_staff = len({value.membership_id for value in shifts})
    located_staff = len(seen_memberships)
    if located_staff > open_shift_staff:
        staff_unknown = True
    unlocated_staff = max(open_shift_staff - located_staff, 0)

    profiles = list(
        session.scalars(
            select(StaffCoverageTargetProfile).where(
                StaffCoverageTargetProfile.organization_id == organization_id,
                StaffCoverageTargetProfile.facility_id == facility_id,
                StaffCoverageTargetProfile.is_specified.is_(True),
            )
        )
    )
    facility_profile = next((value for value in profiles if value.room_id is None), None)
    room_profiles = {value.room_id: value for value in profiles if value.room_id is not None}
    facility_target = _active_target(facility_profile, local_now=local_now)
    if facility_target.state == "target_met" and facility_target.required_staff is not None:
        facility_target.state = (
            "unknown"
            if staff_unknown
            else (
                "target_met"
                if open_shift_staff >= facility_target.required_staff
                else "confirmed_staff_below_target"
            )
        )

    unresolved = list(
        session.scalars(
            select(RoomOperationalExceptionHead).where(
                RoomOperationalExceptionHead.organization_id == organization_id,
                RoomOperationalExceptionHead.facility_id == facility_id,
                RoomOperationalExceptionHead.state != "resolved",
            )
        )
    )
    by_room_exception: dict[UUID, list[UUID]] = {}
    for value in unresolved:
        if value.room_id is not None:
            by_room_exception.setdefault(value.room_id, []).append(value.id)
    room_rows: list[RoomLiveRow] = []
    for room in rooms:
        reason_codes: list[str] = []
        confirmed_children = None if child_unknown else child_counts[room.id]
        confirmed_staff = None if staff_unknown else staff_counts[room.id]
        if child_unknown:
            reason_codes.append("attendance_source_incoherent")
        if staff_unknown:
            reason_codes.append("room_presence_source_incoherent")
        capacity_state = (
            "unknown"
            if confirmed_children is None
            else (
                "above_configured_capacity"
                if confirmed_children > room.capacity
                else "within_configured_capacity"
            )
        )
        target = _active_target(room_profiles.get(room.id), local_now=local_now)
        if target.state == "target_met" and target.required_staff is not None:
            target.state = (
                "target_met"
                if confirmed_staff is not None
                and confirmed_staff >= target.required_staff
                else (
                    "unknown"
                    if confirmed_staff is None
                    else "confirmed_staff_below_target"
                )
            )
        attention = (
            capacity_state == "above_configured_capacity"
            or target.state == "confirmed_staff_below_target"
        )
        unknown = (
            bool(reason_codes)
            or capacity_state == "unknown"
            or target.state == "unknown"
        )
        neutral = (
            capacity_state == "within_configured_capacity"
            and target.state in {"not_configured", "outside_configured_window"}
        )
        overall = (
            "attention"
            if attention
            else "unknown"
            if unknown
            else "not_evaluated"
            if neutral
            else "no_active_configured_target_signal"
        )
        room_rows.append(
            RoomLiveRow(
                room_id=room.id,
                room_name=room.name,
                confirmed_children=confirmed_children,
                configured_room_capacity=room.capacity,
                capacity_state=capacity_state,
                confirmed_staff=confirmed_staff,
                configured_target=target,
                overall_state=overall,
                active_exception_ids=sorted(
                    by_room_exception.get(room.id, []), key=str
                ),
                data_quality_reason_codes=sorted(reason_codes),
            )
        )
    facility_reasons: list[str] = []
    if child_unknown:
        facility_reasons.append("attendance_source_incoherent")
    if staff_unknown:
        facility_reasons.append("room_presence_source_incoherent")
    if present_without_room:
        facility_reasons.append("present_child_without_active_room")
    facility_attention = (
        unlocated_staff > 0
        or present_without_room > 0
        or facility_target.state == "confirmed_staff_below_target"
        or any(value.overall_state == "attention" for value in room_rows)
    )
    facility_unknown = child_unknown or staff_unknown
    facility_overall = (
        "attention"
        if facility_attention
        else "unknown"
        if facility_unknown
        else "not_evaluated"
        if facility_target.state in {"not_configured", "outside_configured_window"}
        and all(value.overall_state == "not_evaluated" for value in room_rows)
        else "no_active_configured_target_signal"
    )
    return FacilityLiveBoard(
        organization_id=organization_id,
        facility_id=facility_id,
        facility_timezone=facility.timezone,
        as_of=now,
        generated_at=now,
        data_through_realtime_sequence=_latest_realtime_sequence(
            session, organization_id
        ),
        facility=FacilityLiveSummary(
            confirmed_children=None if child_unknown else len(child_rows),
            present_children_without_active_room=(
                None if child_unknown else present_without_room
            ),
            open_shift_staff=None if staff_unknown else open_shift_staff,
            located_staff=None if staff_unknown else located_staff,
            unlocated_staff=None if staff_unknown else unlocated_staff,
            configured_target=facility_target,
            overall_state=facility_overall,
            active_exception_count=len(unresolved),
            data_quality_reason_codes=sorted(facility_reasons),
        ),
        rooms=room_rows,
    )


def _release_facility_receipt_id(
    organization_id: UUID,
    facility_id: UUID,
    operation_id: UUID,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "caresync:0041:release-reconciliation:"
        f"{organization_id}:{facility_id}:operation:{operation_id}",
    )


def _facility_set_sha256(facility_ids: list[UUID]) -> str:
    return request_sha256(
        {"facility_ids": [str(value) for value in sorted(facility_ids, key=str)]}
    )


def _validate_release_review(
    *,
    expected_facility_ids: list[UUID],
    expected_facility_set_sha256: str,
    expected_active_facility_count: int,
    current_facility_ids: list[UUID] | None = None,
) -> list[UUID]:
    normalized = sorted(expected_facility_ids, key=str)
    if (
        len(normalized) != len(set(normalized))
        or len(normalized) != expected_active_facility_count
        or _facility_set_sha256(normalized) != expected_facility_set_sha256
    ):
        raise HTTPException(
            422,
            detail={"code": "release_reconciliation_review_invalid"},
        )
    if current_facility_ids is not None and normalized != sorted(
        current_facility_ids, key=str
    ):
        raise HTTPException(
            409,
            detail={
                "code": "release_reconciliation_facility_set_changed_retry"
            },
        )
    return normalized


def _release_organization_receipt_id(
    organization_id: UUID,
    facility_set_sha256: str,
    operation_id: UUID,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "caresync:0041:release-reconciliation:"
        f"{organization_id}:facility-set:{facility_set_sha256}:"
        f"operation:{operation_id}",
    )


def _release_facilities(
    session: Session,
    organization_id: UUID,
    *,
    lock: bool = False,
) -> list[Facility]:
    statement = (
        select(Facility)
        .where(
            Facility.organization_id == organization_id,
            Facility.status == "active",
        )
        .order_by(Facility.id)
    )
    if lock:
        statement = statement.with_for_update()
    return list(session.scalars(statement))


def _valid_facility_release_receipt(
    value: AuditEvent | None,
    *,
    organization_id: UUID,
    facility_id: UUID,
) -> bool:
    if value is None:
        return False
    details = value.details or {}
    try:
        operation_id = UUID(str(details["client_operation_id"]))
    except (KeyError, TypeError, ValueError):
        return False
    projection_sha256 = details.get("projection_sha256")
    return (
        value.id
        == _release_facility_receipt_id(
            organization_id, facility_id, operation_id
        )
        and value.organization_id == organization_id
        and value.facility_id == facility_id
        and value.entity_type == "facility"
        and value.entity_id == facility_id
        and value.action == RELEASE_FACILITY_ACTION
        and value.actor_user_id is not None
        and details.get("schema_version") == RELEASE_SCHEMA_VERSION
        and details.get("source") == "release_reconciliation"
        and details.get("notifications_suppressed") is True
        and details.get("organization_id") == str(organization_id)
        and details.get("facility_id") == str(facility_id)
        and isinstance(operation_id, UUID)
        and isinstance(projection_sha256, str)
        and len(projection_sha256) == 64
        and projection_sha256 == projection_sha256.lower()
        and all(character in "0123456789abcdef" for character in projection_sha256)
    )


def _valid_organization_release_receipt(
    value: AuditEvent | None,
    *,
    organization_id: UUID,
    facility_set_sha256: str,
    active_facility_count: int,
) -> bool:
    if value is None:
        return False
    details = value.details or {}
    try:
        operation_id = UUID(str(details["client_operation_id"]))
        facility_ids = [
            UUID(str(facility_id))
            for facility_id in details["facility_ids"]
        ]
    except (KeyError, TypeError, ValueError):
        return False
    if (
        len(facility_ids) != len(set(facility_ids))
        or len(facility_ids) != active_facility_count
        or _facility_set_sha256(facility_ids) != facility_set_sha256
    ):
        return False
    return (
        value.id
        == _release_organization_receipt_id(
            organization_id, facility_set_sha256, operation_id
        )
        and value.organization_id == organization_id
        and value.facility_id is None
        and value.entity_type == "organization"
        and value.entity_id == organization_id
        and value.action == RELEASE_ORGANIZATION_ACTION
        and value.actor_user_id is not None
        and details.get("schema_version") == RELEASE_SCHEMA_VERSION
        and details.get("source") == "release_reconciliation"
        and details.get("notifications_suppressed") is True
        and details.get("organization_id") == str(organization_id)
        and details.get("facility_set_sha256") == facility_set_sha256
        and details.get("active_facility_count") == active_facility_count
    )


def _durable_release_activation_receipt(
    session: Session,
    organization_id: UUID,
) -> AuditEvent | None:
    """Return any valid one-time 0041 activation receipt for the tenant.

    The facility-set digest proves the set reconciled at initial cutover.  It
    is not a lease on the forever-current active-facility set: post-cutover
    facility lifecycle commands are themselves serialized and reconciled.
    """

    values = list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.action == RELEASE_ORGANIZATION_ACTION,
                AuditEvent.entity_type == "organization",
                AuditEvent.entity_id == organization_id,
                AuditEvent.facility_id.is_(None),
            )
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        )
    )
    for value in values:
        details = value.details or {}
        facility_set_sha256 = details.get("facility_set_sha256")
        active_facility_count = details.get("active_facility_count")
        if (
            isinstance(facility_set_sha256, str)
            and len(facility_set_sha256) == 64
            and facility_set_sha256 == facility_set_sha256.lower()
            and all(
                character in "0123456789abcdef"
                for character in facility_set_sha256
            )
            and isinstance(active_facility_count, int)
            and not isinstance(active_facility_count, bool)
            and active_facility_count >= 0
            and _valid_organization_release_receipt(
                value,
                organization_id=organization_id,
                facility_set_sha256=facility_set_sha256,
                active_facility_count=active_facility_count,
            )
        ):
            facility_ids = [
                UUID(str(facility_id))
                for facility_id in details["facility_ids"]
            ]
            receipt_ids = {
                facility_id: _release_facility_receipt_id(
                    organization_id,
                    facility_id,
                    UUID(str(details["client_operation_id"])),
                )
                for facility_id in facility_ids
            }
            receipts = {
                receipt.id: receipt
                for receipt in session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.id.in_(set(receipt_ids.values())),
                    )
                )
            }
            if all(
                _valid_facility_release_receipt(
                    receipts.get(receipt_id),
                    organization_id=organization_id,
                    facility_id=facility_id,
                )
                for facility_id, receipt_id in receipt_ids.items()
            ):
                return value
    return None


def release_reconciliation_status(
    session: Session,
    organization_id: UUID,
    *,
    foundation_available: bool,
) -> ReleaseReconciliationStatus:
    facilities = _release_facilities(session, organization_id)
    facility_ids = [value.id for value in facilities]
    facility_set_sha256 = _facility_set_sha256(facility_ids)
    durable_activation = _durable_release_activation_receipt(
        session, organization_id
    )
    activated = foundation_available and durable_activation is not None
    return ReleaseReconciliationStatus(
        organization_id=organization_id,
        foundation_available=foundation_available,
        complete=activated,
        active_facility_count=len(facility_ids),
        completed_facility_count=len(facility_ids) if activated else 0,
        missing_facility_ids=[] if activated else facility_ids,
        facility_set_sha256=facility_set_sha256,
        organization_receipt_id=(
            durable_activation.id if durable_activation is not None else None
        ),
        generated_at=datetime.now(UTC),
    )


def release_reconciliation_complete(
    session: Session,
    organization_id: UUID,
) -> bool:
    return _durable_release_activation_receipt(session, organization_id) is not None


def _release_replay_bundle(
    session: Session,
    *,
    organization_id: UUID,
    operation_id: UUID,
    actor_user_id: UUID,
) -> tuple[AuditEvent, list[ReleaseFacilityReceipt]] | None:
    organization_receipt = next(
        (
            value
            for value in session.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.action == RELEASE_ORGANIZATION_ACTION,
                    AuditEvent.entity_type == "organization",
                    AuditEvent.entity_id == organization_id,
                    AuditEvent.facility_id.is_(None),
                )
            )
            if (value.details or {}).get("client_operation_id")
            == str(operation_id)
        ),
        None,
    )
    if organization_receipt is None:
        return None
    if organization_receipt.actor_user_id != actor_user_id:
        raise HTTPException(404, "Release reconciliation operation not found")
    details = organization_receipt.details or {}
    try:
        facility_set_sha256 = str(details["facility_set_sha256"])
        facility_ids = [
            UUID(str(facility_id))
            for facility_id in details["facility_ids"]
        ]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            409,
            detail={"code": "release_reconciliation_receipt_incoherent"},
        ) from None
    if not _valid_organization_release_receipt(
        organization_receipt,
        organization_id=organization_id,
        facility_set_sha256=facility_set_sha256,
        active_facility_count=len(facility_ids),
    ):
        raise HTTPException(
            409,
            detail={"code": "release_reconciliation_receipt_incoherent"},
        )
    expected = {
        facility_id: _release_facility_receipt_id(
            organization_id, facility_id, operation_id
        )
        for facility_id in facility_ids
    }
    events = {
        value.id: value
        for value in session.scalars(
            select(AuditEvent).where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.id.in_(set(expected.values())),
            )
        )
    }
    result: list[ReleaseFacilityReceipt] = []
    for facility_id, receipt_id in expected.items():
        value = events.get(receipt_id)
        if not _valid_facility_release_receipt(
            value,
            organization_id=organization_id,
            facility_id=facility_id,
        ) or value.actor_user_id != actor_user_id:
            raise HTTPException(
                409,
                detail={
                    "code": "release_reconciliation_receipt_incoherent",
                    "facility_id": str(facility_id),
                },
            )
        receipt_details = value.details or {}
        result.append(
            ReleaseFacilityReceipt(
                facility_id=facility_id,
                audit_event_id=value.id,
                client_operation_id=operation_id,
                projection_sha256=str(
                    receipt_details["projection_sha256"]
                ),
                reconciled_at=aware_utc(value.occurred_at),
            )
        )
    return organization_receipt, sorted(
        result, key=lambda value: str(value.facility_id)
    )


def run_release_reconciliation(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    expected_facility_ids: list[UUID],
    expected_facility_set_sha256: str,
    expected_active_facility_count: int,
) -> ReleaseReconciliationResponse:
    """Derive current episodes without notifications and seal a durable receipt."""

    expected_facility_ids = _validate_release_review(
        expected_facility_ids=expected_facility_ids,
        expected_facility_set_sha256=expected_facility_set_sha256,
        expected_active_facility_count=expected_active_facility_count,
    )
    _operation_lock(session, context.organization.id, operation_id)
    _release_facility_set_lock(session, context.organization.id)
    context = refresh_basic_context(
        session,
        context,
        required_all_permissions=(
            "facility:read",
            "facility:manage",
            "care_roster:read",
            "staff:manage_educators",
        ),
    )
    if (
        not context.organization_wide
        or context.role.key not in {"owner", "administrator"}
    ):
        raise HTTPException(
            403,
            detail={"code": "release_reconciliation_leader_required"},
        )
    replay = _release_replay_bundle(
        session,
        organization_id=context.organization.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
    )
    if replay is not None:
        organization_receipt, facility_receipts = replay
        details = organization_receipt.details or {}
        if (
            details.get("facility_set_sha256")
            != expected_facility_set_sha256
            or details.get("active_facility_count")
            != expected_active_facility_count
            or sorted(
                (
                    UUID(str(facility_id))
                    for facility_id in details.get("facility_ids", [])
                ),
                key=str,
            )
            != expected_facility_ids
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "release_reconciliation_operation_reused"
                },
            )
        return ReleaseReconciliationResponse(
            organization_id=context.organization.id,
            client_operation_id=operation_id,
            replayed=True,
            complete=True,
            facility_set_sha256=str(details["facility_set_sha256"]),
            organization_receipt_id=organization_receipt.id,
            facility_receipts=facility_receipts,
            generated_at=datetime.now(UTC),
        )
    preliminary_facilities = _release_facilities(
        session, context.organization.id
    )
    preliminary_ids = [value.id for value in preliminary_facilities]
    for facility_id in sorted(preliminary_ids, key=str):
        _facility_projection_lock(
            session, context.organization.id, facility_id
        )
    facilities = _release_facilities(
        session, context.organization.id, lock=True
    )
    facility_ids = [value.id for value in facilities]
    if facility_ids != preliminary_ids:
        raise HTTPException(
            409,
            detail={
                "code": "release_reconciliation_facility_set_changed_retry"
            },
        )
    _validate_release_review(
        expected_facility_ids=expected_facility_ids,
        expected_facility_set_sha256=expected_facility_set_sha256,
        expected_active_facility_count=expected_active_facility_count,
        current_facility_ids=facility_ids,
    )
    durable_activation = _durable_release_activation_receipt(
        session, context.organization.id
    )
    if durable_activation is not None:
        raise HTTPException(
            409,
            detail={"code": "release_reconciliation_already_complete"},
        )
    facility_set_sha256 = _facility_set_sha256(facility_ids)
    facility_receipts: list[ReleaseFacilityReceipt] = []
    for facility in facilities:
        receipt_id = _release_facility_receipt_id(
            context.organization.id, facility.id, operation_id
        )
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            cause_entity_type="release_reconciliation",
            cause_entity_id=operation_id,
            notifications_suppressed=True,
        )
        session.flush()
        board = facility_live_board(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
        )
        projection_sha256 = request_sha256(
            board.model_dump(mode="json")
        )
        now = datetime.now(UTC)
        event = AuditEvent(
            id=receipt_id,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action=RELEASE_FACILITY_ACTION,
            entity_type="facility",
            entity_id=facility.id,
            facility_id=facility.id,
            occurred_at=now,
            details={
                "schema_version": RELEASE_SCHEMA_VERSION,
                "source": "release_reconciliation",
                "notifications_suppressed": True,
                "organization_id": str(context.organization.id),
                "facility_id": str(facility.id),
                "client_operation_id": str(operation_id),
                "projection_sha256": projection_sha256,
            },
        )
        session.add(event)
        facility_receipts.append(
            ReleaseFacilityReceipt(
                facility_id=facility.id,
                audit_event_id=event.id,
                client_operation_id=operation_id,
                projection_sha256=projection_sha256,
                reconciled_at=now,
            )
        )
    organization_receipt_id = _release_organization_receipt_id(
        context.organization.id, facility_set_sha256, operation_id
    )
    now = datetime.now(UTC)
    organization_receipt = AuditEvent(
        id=organization_receipt_id,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=RELEASE_ORGANIZATION_ACTION,
        entity_type="organization",
        entity_id=context.organization.id,
        facility_id=None,
        occurred_at=now,
        details={
            "schema_version": RELEASE_SCHEMA_VERSION,
            "source": "release_reconciliation",
            "notifications_suppressed": True,
            "organization_id": str(context.organization.id),
            "client_operation_id": str(operation_id),
            "facility_set_sha256": facility_set_sha256,
            "active_facility_count": len(facility_ids),
            "facility_ids": [
                str(facility_id)
                for facility_id in sorted(facility_ids, key=str)
            ],
        },
    )
    session.add(organization_receipt)
    session.flush()
    status = release_reconciliation_status(
        session,
        context.organization.id,
        foundation_available=True,
    )
    if not status.complete:
        raise HTTPException(
            409,
            detail={"code": "release_reconciliation_receipt_incomplete"},
        )
    return ReleaseReconciliationResponse(
        organization_id=context.organization.id,
        client_operation_id=operation_id,
        replayed=False,
        complete=True,
        facility_set_sha256=facility_set_sha256,
        organization_receipt_id=organization_receipt.id,
        facility_receipts=sorted(
            facility_receipts, key=lambda value: str(value.facility_id)
        ),
        generated_at=datetime.now(UTC),
    )


def staff_room_live_board(
    session: Session,
    context: BasicContext,
) -> StaffRoomLiveBoard:
    now = datetime.now(UTC)
    presence = staff_presence_projection(session, context, generated_at=now)
    shift_facility_id = (
        presence.open_shift.facility_id
        if presence.open_shift is not None
        else None
    )
    shift_facility_timezone: str | None = None
    shift_facility_active = False
    if shift_facility_id is not None:
        shift_facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == context.organization.id,
                Facility.id == shift_facility_id,
            )
        )
        if shift_facility is not None:
            shift_facility_active = shift_facility.status == "active"
            if _valid_timezone(shift_facility.timezone):
                shift_facility_timezone = shift_facility.timezone
    if presence.decision_reason == "source_integrity_unknown":
        return StaffRoomLiveBoard(
            organization_id=context.organization.id,
            facility_id=shift_facility_id,
            facility_timezone=shift_facility_timezone,
            as_of=now,
            generated_at=now,
            data_through_realtime_sequence=presence.data_through_realtime_sequence,
            current_room=None,
            unavailable_reason="source_integrity_unknown",
        )
    if (
        shift_facility_id is not None
        and (not shift_facility_active or shift_facility_timezone is None)
    ):
        # This is a defensive convergence path.  The presence projection above
        # normally classifies the same invalid source first, but the facility
        # could change between its canonical read and this response assembly.
        return StaffRoomLiveBoard(
            organization_id=context.organization.id,
            facility_id=shift_facility_id,
            facility_timezone=shift_facility_timezone,
            as_of=now,
            generated_at=now,
            data_through_realtime_sequence=presence.data_through_realtime_sequence,
            current_room=None,
            unavailable_reason="source_integrity_unknown",
        )
    if presence.open_shift is None:
        return StaffRoomLiveBoard(
            organization_id=context.organization.id,
            facility_id=None,
            facility_timezone=None,
            as_of=now,
            generated_at=now,
            data_through_realtime_sequence=presence.data_through_realtime_sequence,
            current_room=None,
            unavailable_reason="no_open_shift",
        )
    if presence.current_presence is None:
        return StaffRoomLiveBoard(
            organization_id=context.organization.id,
            facility_id=shift_facility_id,
            facility_timezone=shift_facility_timezone,
            as_of=now,
            generated_at=now,
            data_through_realtime_sequence=presence.data_through_realtime_sequence,
            current_room=None,
            unavailable_reason="room_presence_required",
        )
    board = facility_live_board(
        session,
        organization_id=context.organization.id,
        facility_id=presence.current_presence.facility_id,
        as_of=now,
    )
    row = next(
        (value for value in board.rooms if value.room_id == presence.current_presence.room_id),
        None,
    )
    source_integrity_unknown = row is None or (
        bool(row.data_quality_reason_codes)
        or row.confirmed_children is None
        or row.configured_room_capacity is None
        or row.capacity_state == "unknown"
        or row.confirmed_staff is None
        or row.configured_target.state == "unknown"
    )
    return StaffRoomLiveBoard(
        organization_id=context.organization.id,
        facility_id=board.facility_id,
        facility_timezone=board.facility_timezone,
        as_of=now,
        generated_at=now,
        data_through_realtime_sequence=board.data_through_realtime_sequence,
        current_room=row,
        unavailable_reason=(
            "source_integrity_unknown"
            if source_integrity_unknown
            else None
        ),
    )


def _evidence(
    *,
    observed_value: int | None,
    configured_value: int | None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "configured_value": configured_value,
        "observed_value": observed_value,
        "reason_codes": sorted(reason_codes or []),
    }


def _conditions(board: FacilityLiveBoard) -> dict[tuple[str, UUID, str], dict[str, Any]]:
    result: dict[tuple[str, UUID, str], dict[str, Any]] = {}
    if (
        board.facility.configured_target.state
        == "confirmed_staff_below_target"
    ):
        result[
            (
                "facility",
                board.facility_id,
                "confirmed_staff_below_configured_room_target",
            )
        ] = _evidence(
            observed_value=board.facility.open_shift_staff,
            configured_value=(
                board.facility.configured_target.required_staff
            ),
        )
    if (board.facility.unlocated_staff or 0) > 0:
        result[
            (
                "facility",
                board.facility_id,
                "open_shift_staff_without_current_room",
            )
        ] = _evidence(
            observed_value=board.facility.unlocated_staff,
            configured_value=0,
        )
    if (board.facility.present_children_without_active_room or 0) > 0:
        result[
            (
                "facility",
                board.facility_id,
                "present_child_without_active_room",
            )
        ] = _evidence(
            observed_value=board.facility.present_children_without_active_room,
            configured_value=0,
        )
    facility_integrity_reasons = [
        reason
        for reason in board.facility.data_quality_reason_codes
        if reason != "present_child_without_active_room"
    ]
    if facility_integrity_reasons:
        result[
            ("facility", board.facility_id, "source_integrity_unknown")
        ] = _evidence(
            observed_value=None,
            configured_value=None,
            reason_codes=facility_integrity_reasons,
        )
    for row in board.rooms:
        if row.capacity_state == "above_configured_capacity":
            result[
                (
                    "room",
                    row.room_id,
                    "confirmed_children_above_configured_room_capacity",
                )
            ] = _evidence(
                observed_value=row.confirmed_children,
                configured_value=row.configured_room_capacity,
            )
        if row.configured_target.state == "confirmed_staff_below_target":
            result[
                (
                    "room",
                    row.room_id,
                    "confirmed_staff_below_configured_room_target",
                )
            ] = _evidence(
                observed_value=row.confirmed_staff,
                configured_value=row.configured_target.required_staff,
            )
        if row.data_quality_reason_codes:
            result[
                ("room", row.room_id, "source_integrity_unknown")
            ] = _evidence(
                observed_value=None,
                configured_value=None,
                reason_codes=row.data_quality_reason_codes,
            )
    return result


def _fingerprint(evidence: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(evidence).encode("utf-8")).hexdigest()


def _condition_absence_is_confirmed(
    board: FacilityLiveBoard,
    value: RoomOperationalExceptionHead,
) -> bool:
    """Return whether the current projection can prove an episode cleared.

    An incoherent source is not evidence that a previously confirmed
    operational condition disappeared.  Keep that episode unchanged while
    the parallel source-integrity episode explains why current arithmetic is
    unavailable.  A missing room row is different: the active-room scope no
    longer exists, so the room-scoped condition is no longer applicable.
    """

    room = next(
        (row for row in board.rooms if row.room_id == value.scope_id),
        None,
    )
    if value.condition_code == (
        "confirmed_children_above_configured_room_capacity"
    ):
        return room is None or room.capacity_state != "unknown"
    if value.condition_code == (
        "confirmed_staff_below_configured_room_target"
    ):
        target = (
            board.facility.configured_target
            if value.scope_kind == "facility"
            else room.configured_target if room is not None else None
        )
        return target is None or target.state != "unknown"
    if value.condition_code == "open_shift_staff_without_current_room":
        return board.facility.unlocated_staff is not None
    if value.condition_code == "present_child_without_active_room":
        return board.facility.present_children_without_active_room is not None
    return True


def _next_episode_id(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    scope_kind: str,
    scope_id: UUID,
    condition_code: str,
) -> UUID:
    generation = (
        session.scalar(
            select(func.count(RoomOperationalExceptionHead.id)).where(
                RoomOperationalExceptionHead.organization_id
                == organization_id,
                RoomOperationalExceptionHead.facility_id == facility_id,
                RoomOperationalExceptionHead.scope_kind == scope_kind,
                RoomOperationalExceptionHead.scope_id == scope_id,
                RoomOperationalExceptionHead.condition_code
                == condition_code,
            )
        )
        or 0
    ) + 1
    return uuid5(
        NAMESPACE_URL,
        "caresync:0041:exception-episode:"
        f"{organization_id}:{facility_id}:{scope_kind}:{scope_id}:"
        f"{condition_code}:generation:{generation}",
    )


def _derived_operation_id(
    *,
    cause_entity_type: str,
    cause_entity_id: UUID,
    scope_kind: str,
    scope_id: UUID,
    condition_code: str,
    event_type: str,
    fingerprint: str,
    episode_id: UUID,
    resulting_version: int,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "caresync:0041:"
        f"{cause_entity_type}:{cause_entity_id}:{scope_kind}:{scope_id}:"
        f"{condition_code}:{episode_id}:{resulting_version}:"
        f"{event_type}:{fingerprint}",
    )


def _emit_exception_realtime(
    session: Session,
    value: RoomOperationalExceptionHead,
    *,
    event_type: str,
    event_id: UUID,
    requires_action: bool,
) -> None:
    session.add(
        RealtimeEvent(
            id=uuid4(),
            organization_id=value.organization_id,
            event_type=f"room_operational_exception.{event_type}",
            entity_type="room_operational_exception",
            entity_id=value.id,
            occurred_at=datetime.now(UTC),
            payload={
                "event_id": str(event_id),
                "facility_id": str(value.facility_id),
                "room_id": str(value.room_id) if value.room_id else None,
                "requires_action": requires_action,
            },
        )
    )


def _notify_exception(
    session: Session,
    value: RoomOperationalExceptionHead,
) -> None:
    rows = session.execute(
        select(OrganizationMembership, Role)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == value.organization_id,
            OrganizationMembership.status == "active",
        )
    )
    required = {"facility:read", "care_roster:read", "staff:manage_educators"}
    for membership, role in rows:
        if role.key not in {"owner", "administrator"}:
            continue
        if not required.issubset(set(role.permissions or [])):
            continue
        notify_user(
            session,
            user_id=membership.user_id,
            organization_id=value.organization_id,
            event_key=(
                f"room-operational-exception:{value.id}:"
                f"{value.current_fingerprint_sha256}"
            ),
            category="operations",
            severity="warning",
            title="Room operations need review",
            body="Open CareSync to review a current operational signal.",
            action_path="/rooms",
            action_entity_type="room_operational_exception",
            action_entity_id=value.id,
        )


def reconcile_facility_exceptions(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    cause_entity_type: str,
    cause_entity_id: UUID,
    notifications_suppressed: bool | None = None,
) -> None:
    _facility_projection_lock(session, organization_id, facility_id)
    if notifications_suppressed is None:
        # Foundation writers participate before activation so cutover cannot
        # seal stale state, but only the explicit cutover pass may establish
        # the durable receipt.  Suppress remote wakes until that receipt is
        # valid; post-activation calls retain normal episode notification.
        notifications_suppressed = not release_reconciliation_complete(
            session, organization_id
        )
    # The application session intentionally disables autoflush.  The live
    # projection must nevertheless evaluate the source mutation made by this
    # transaction (for example an interval checkout or a new presence row),
    # not the pre-command database image.
    session.flush()
    board = facility_live_board(
        session,
        organization_id=organization_id,
        facility_id=facility_id,
    )
    current = _conditions(board)
    heads = list(
        session.scalars(
            select(RoomOperationalExceptionHead)
            .where(
                RoomOperationalExceptionHead.organization_id == organization_id,
                RoomOperationalExceptionHead.facility_id == facility_id,
                RoomOperationalExceptionHead.state != "resolved",
            )
            .with_for_update()
        )
    )
    existing = {
        (value.scope_kind, value.scope_id, value.condition_code): value
        for value in heads
    }
    now = datetime.now(UTC)
    for key, evidence in current.items():
        scope_kind, scope_id, condition_code = key
        fingerprint = _fingerprint(evidence)
        value = existing.pop(key, None)
        if value is None:
            event_type = "opened"
            episode_id = _next_episode_id(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                condition_code=condition_code,
            )
            operation_id = _derived_operation_id(
                cause_entity_type=cause_entity_type,
                cause_entity_id=cause_entity_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                condition_code=condition_code,
                event_type=event_type,
                fingerprint=fingerprint,
                episode_id=episode_id,
                resulting_version=1,
            )
            _set_operation_context(
                session, operation_id=operation_id, server_derived=True
            )
            value = RoomOperationalExceptionHead(
                id=episode_id,
                organization_id=organization_id,
                facility_id=facility_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                room_id=scope_id if scope_kind == "room" else None,
                condition_code=condition_code,
                state="open",
                current_fingerprint_sha256=fingerprint,
                current_evidence=evidence,
                opened_at=now,
                last_changed_at=now,
                version=1,
                created_at=now,
                updated_at=now,
            )
            event_id = uuid4()
            session.add(value)
            # The append-only event references this new episode through an
            # immediate composite FK.  Persist the head before its event while
            # leaving the deferred reciprocal bundle check to transaction end.
            session.flush([value])
            event = RoomOperationalExceptionEvent(
                id=event_id,
                organization_id=organization_id,
                exception_id=value.id,
                operation_id=operation_id,
                event_type=event_type,
                actor_user_id=None,
                cause_entity_type=cause_entity_type,
                cause_entity_id=cause_entity_id,
                previous_fingerprint_sha256=None,
                current_fingerprint_sha256=fingerprint,
                evidence=evidence,
                reason=None,
                occurred_at=now,
                created_at=now,
            )
            session.add(event)
            session.flush([event])
            _emit_exception_realtime(
                session,
                value,
                event_type="opened",
                event_id=event_id,
                requires_action=True,
            )
            if not notifications_suppressed:
                _notify_exception(session, value)
            continue
        if value.current_fingerprint_sha256 == fingerprint:
            continue
        previous = value.current_evidence or {}
        observed = evidence.get("observed_value")
        previous_observed = previous.get("observed_value")
        configured = evidence.get("configured_value")
        previous_configured = previous.get("configured_value")
        reason_codes = set(evidence.get("reason_codes") or [])
        previous_reason_codes = set(previous.get("reason_codes") or [])
        worsening = (
            condition_code
            in {
                "confirmed_children_above_configured_room_capacity",
                "open_shift_staff_without_current_room",
                "present_child_without_active_room",
            }
            and isinstance(observed, int)
            and isinstance(previous_observed, int)
            and observed > previous_observed
        ) or (
            condition_code == "confirmed_staff_below_configured_room_target"
            and isinstance(observed, int)
            and isinstance(previous_observed, int)
            and observed < previous_observed
        ) or (
            condition_code
            in {
                "confirmed_children_above_configured_room_capacity",
                "confirmed_staff_below_configured_room_target",
            }
            and isinstance(configured, int)
            and isinstance(previous_configured, int)
            and configured != previous_configured
        ) or (
            condition_code == "source_integrity_unknown"
            and not reason_codes.issubset(previous_reason_codes)
        )
        if not worsening:
            refresh_operation_id = _derived_operation_id(
                cause_entity_type=cause_entity_type,
                cause_entity_id=cause_entity_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                condition_code=condition_code,
                event_type="projection_refreshed",
                fingerprint=fingerprint,
                episode_id=value.id,
                resulting_version=value.version,
            )
            _set_operation_context(
                session,
                operation_id=refresh_operation_id,
                server_derived=True,
            )
            value.current_fingerprint_sha256 = fingerprint
            value.current_evidence = evidence
            value.updated_at = now
            continue
        was_acknowledged = value.state == "acknowledged"
        event_type = "materially_changed"
        operation_id = _derived_operation_id(
            cause_entity_type=cause_entity_type,
            cause_entity_id=cause_entity_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            condition_code=condition_code,
            event_type=event_type,
            fingerprint=fingerprint,
            episode_id=value.id,
            resulting_version=value.version + 1,
        )
        _set_operation_context(session, operation_id=operation_id, server_derived=True)
        previous_fingerprint = value.current_fingerprint_sha256
        value.state = "open"
        value.current_fingerprint_sha256 = fingerprint
        value.current_evidence = evidence
        value.last_changed_at = now
        value.acknowledged_at = None
        value.acknowledged_by_user_id = None
        value.acknowledgement_reason = None
        value.version += 1
        value.updated_at = now
        event_id = uuid4()
        session.flush([value])
        event = RoomOperationalExceptionEvent(
            id=event_id,
            organization_id=organization_id,
            exception_id=value.id,
            operation_id=operation_id,
            event_type=event_type,
            actor_user_id=None,
            cause_entity_type=cause_entity_type,
            cause_entity_id=cause_entity_id,
            previous_fingerprint_sha256=previous_fingerprint,
            current_fingerprint_sha256=fingerprint,
            evidence=evidence,
            reason=None,
            occurred_at=now,
            created_at=now,
        )
        session.add(event)
        session.flush([event])
        _emit_exception_realtime(
            session,
            value,
            event_type="materially_changed",
            event_id=event_id,
            requires_action=True,
        )
        if not notifications_suppressed and was_acknowledged:
            _notify_exception(session, value)
    for value in existing.values():
        if not _condition_absence_is_confirmed(board, value):
            continue
        event_type = "resolved"
        fingerprint = value.current_fingerprint_sha256
        operation_id = _derived_operation_id(
            cause_entity_type=cause_entity_type,
            cause_entity_id=cause_entity_id,
            scope_kind=value.scope_kind,
            scope_id=value.scope_id,
            condition_code=value.condition_code,
            event_type=event_type,
            fingerprint=fingerprint,
            episode_id=value.id,
            resulting_version=value.version + 1,
        )
        _set_operation_context(session, operation_id=operation_id, server_derived=True)
        previous_fingerprint = value.current_fingerprint_sha256
        value.state = "resolved"
        value.resolved_at = now
        value.last_changed_at = now
        value.version += 1
        value.updated_at = now
        event_id = uuid4()
        session.flush([value])
        event = RoomOperationalExceptionEvent(
            id=event_id,
            organization_id=organization_id,
            exception_id=value.id,
            operation_id=operation_id,
            event_type=event_type,
            actor_user_id=None,
            cause_entity_type=cause_entity_type,
            cause_entity_id=cause_entity_id,
            previous_fingerprint_sha256=previous_fingerprint,
            current_fingerprint_sha256=value.current_fingerprint_sha256,
            evidence=value.current_evidence,
            reason=None,
            occurred_at=now,
            created_at=now,
        )
        session.add(event)
        session.flush([event])
        _emit_exception_realtime(
            session,
            value,
            event_type="resolved",
            event_id=event_id,
            requires_action=False,
        )


def resolve_facility_exceptions_for_deactivation(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    cause_entity_id: UUID,
) -> None:
    """Resolve current episodes after a guarded facility deactivation."""

    _facility_projection_lock(session, organization_id, facility_id)
    values = list(
        session.scalars(
            select(RoomOperationalExceptionHead)
            .where(
                RoomOperationalExceptionHead.organization_id
                == organization_id,
                RoomOperationalExceptionHead.facility_id == facility_id,
                RoomOperationalExceptionHead.state != "resolved",
            )
            .with_for_update()
        )
    )
    now = datetime.now(UTC)
    for value in values:
        operation_id = _derived_operation_id(
            cause_entity_type="facility",
            cause_entity_id=cause_entity_id,
            scope_kind=value.scope_kind,
            scope_id=value.scope_id,
            condition_code=value.condition_code,
            event_type="resolved",
            fingerprint=value.current_fingerprint_sha256,
            episode_id=value.id,
            resulting_version=value.version + 1,
        )
        _set_operation_context(
            session, operation_id=operation_id, server_derived=True
        )
        value.state = "resolved"
        value.resolved_at = now
        value.last_changed_at = now
        value.version += 1
        value.updated_at = now
        event_id = uuid4()
        session.flush([value])
        event = RoomOperationalExceptionEvent(
            id=event_id,
            organization_id=organization_id,
            exception_id=value.id,
            operation_id=operation_id,
            event_type="resolved",
            actor_user_id=None,
            cause_entity_type="facility",
            cause_entity_id=cause_entity_id,
            previous_fingerprint_sha256=value.current_fingerprint_sha256,
            current_fingerprint_sha256=value.current_fingerprint_sha256,
            evidence=value.current_evidence,
            reason=None,
            occurred_at=now,
            created_at=now,
        )
        session.add(event)
        session.flush([event])
        _emit_exception_realtime(
            session,
            value,
            event_type="resolved",
            event_id=event_id,
            requires_action=False,
        )


def _materially_changed_at_by_exception_id(
    session: Session,
    *,
    organization_id: UUID,
    exception_ids: list[UUID],
) -> dict[UUID, datetime]:
    if not exception_ids:
        return {}
    return {
        exception_id: aware_utc(occurred_at)
        for exception_id, occurred_at in session.execute(
            select(
                RoomOperationalExceptionEvent.exception_id,
                func.max(RoomOperationalExceptionEvent.occurred_at),
            )
            .where(
                RoomOperationalExceptionEvent.organization_id
                == organization_id,
                RoomOperationalExceptionEvent.exception_id.in_(
                    exception_ids
                ),
                RoomOperationalExceptionEvent.event_type
                == "materially_changed",
            )
            .group_by(RoomOperationalExceptionEvent.exception_id)
        )
    }


def exception_item(
    value: RoomOperationalExceptionHead,
    *,
    materially_changed_at: datetime | None,
) -> ExceptionItem:
    evidence = value.current_evidence or {}
    return ExceptionItem(
        id=value.id,
        facility_id=value.facility_id,
        scope_kind=value.scope_kind,
        scope_id=value.scope_id,
        room_id=value.room_id,
        condition_code=value.condition_code,
        state=value.state,
        version=value.version,
        opened_at=aware_utc(value.opened_at),
        materially_changed_at=materially_changed_at,
        acknowledged_at=(
            aware_utc(value.acknowledged_at) if value.acknowledged_at else None
        ),
        acknowledged_by_user_id=value.acknowledged_by_user_id,
        acknowledgement_reason=value.acknowledgement_reason,
        resolved_at=aware_utc(value.resolved_at) if value.resolved_at else None,
        observed_value=evidence.get("observed_value"),
        configured_value=evidence.get("configured_value"),
        source_integrity_reason_codes=list(evidence.get("reason_codes") or []),
        action_target_path=(
            f"/api/v1/room-safety/exceptions/{value.id}/action-target"
        ),
    )


def _single_exception_item(
    session: Session,
    value: RoomOperationalExceptionHead,
) -> ExceptionItem:
    materially_changed_at = _materially_changed_at_by_exception_id(
        session,
        organization_id=value.organization_id,
        exception_ids=[value.id],
    ).get(value.id)
    return exception_item(
        value, materially_changed_at=materially_changed_at
    )


def encode_exception_cursor(value: RoomOperationalExceptionHead) -> str:
    raw = canonical_json(
        {"id": str(value.id), "last_changed_at": aware_utc(value.last_changed_at).isoformat()}
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_exception_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return datetime.fromisoformat(payload["last_changed_at"]), UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(422, detail={"code": "invalid_exception_cursor"}) from None


def exception_page(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    state_filter: Literal["open", "acknowledged", "resolved", "all"],
    cursor: str | None,
    limit: int,
) -> ExceptionPage:
    statement = select(RoomOperationalExceptionHead).where(
        RoomOperationalExceptionHead.organization_id == organization_id,
        RoomOperationalExceptionHead.facility_id == facility_id,
    )
    if state_filter != "all":
        statement = statement.where(RoomOperationalExceptionHead.state == state_filter)
    if cursor:
        changed_at, value_id = decode_exception_cursor(cursor)
        statement = statement.where(
            (RoomOperationalExceptionHead.last_changed_at < changed_at)
            | (
                (RoomOperationalExceptionHead.last_changed_at == changed_at)
                & (RoomOperationalExceptionHead.id < value_id)
            )
        )
    values = list(
        session.scalars(
            statement.order_by(
                RoomOperationalExceptionHead.last_changed_at.desc(),
                RoomOperationalExceptionHead.id.desc(),
            ).limit(limit + 1)
        )
    )
    page = values[:limit]
    materially_changed_at = _materially_changed_at_by_exception_id(
        session,
        organization_id=organization_id,
        exception_ids=[value.id for value in page],
    )
    return ExceptionPage(
        organization_id=organization_id,
        facility_id=facility_id,
        state_filter=state_filter,
        items=[
            exception_item(
                value,
                materially_changed_at=materially_changed_at.get(value.id),
            )
            for value in page
        ],
        next_cursor=(
            encode_exception_cursor(page[-1]) if len(values) > limit and page else None
        ),
        generated_at=datetime.now(UTC),
    )


def exception_action_target(
    value: RoomOperationalExceptionHead,
) -> ExceptionActionTarget:
    if value.state == "resolved":
        raise HTTPException(
            404,
            detail={
                "code": "exception_action_target_unavailable",
                "message": "This operational exception is already resolved.",
            },
        )
    return ExceptionActionTarget(
        organization_id=value.organization_id,
        facility_id=value.facility_id,
        room_id=value.room_id,
        exception_id=value.id,
        state=value.state,
        version=value.version,
        generated_at=datetime.now(UTC),
    )


def acknowledge_exception(
    session: Session,
    context: BasicContext,
    *,
    exception_id: UUID,
    operation_id: UUID,
    expected_version: int,
    reason: str,
) -> ExceptionAcknowledgeResponse:
    _operation_lock(session, context.organization.id, operation_id)
    existing_event = session.scalar(
        select(RoomOperationalExceptionEvent).where(
            RoomOperationalExceptionEvent.organization_id == context.organization.id,
            RoomOperationalExceptionEvent.operation_id == operation_id,
        )
    )
    canonical_exception_id = (
        existing_event.exception_id
        if existing_event is not None
        else exception_id
    )
    preliminary = session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id
            == context.organization.id,
            RoomOperationalExceptionHead.id == canonical_exception_id,
        )
    )
    if preliminary is None:
        raise HTTPException(404, "Room operational exception not found")
    _facility_projection_lock(
        session, context.organization.id, preliminary.facility_id
    )
    context = _refresh_manager_room_safety_context(
        session,
        context,
        facility_id=preliminary.facility_id,
    )
    value = session.scalar(
        select(RoomOperationalExceptionHead)
        .where(
            RoomOperationalExceptionHead.organization_id == context.organization.id,
            RoomOperationalExceptionHead.id == canonical_exception_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, "Room operational exception not found")
    if existing_event is not None and existing_event.exception_id != exception_id:
        raise HTTPException(409, detail={"code": "operation_reused"})
    intent = exception_ack_intent(
        context=context,
        operation_id=operation_id,
        value=value,
        expected_version=expected_version,
        reason=reason,
    )
    digest = request_sha256(intent)
    if existing_event is not None:
        if existing_event.actor_user_id != context.user.id:
            raise HTTPException(404, "Room operational exception operation not found")
        audit_bindings = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.organization_id == context.organization.id,
                    AuditEvent.actor_user_id == context.user.id,
                    AuditEvent.action
                    == "room_operational_exception.acknowledged",
                    AuditEvent.entity_type == "room_operational_exception",
                    AuditEvent.entity_id == exception_id,
                )
            )
        )
        binding = next(
            (
                dict(item.details or {})
                for item in audit_bindings
                if dict(item.details or {}).get("operation_id")
                == str(operation_id)
            ),
            None,
        )
        if binding is None:
            raise HTTPException(
                409,
                detail={"code": "operation_receipt_incomplete"},
            )
        if (
            binding.get("request_sha256") != digest
            or existing_event.exception_id != exception_id
        ):
            raise HTTPException(409, detail={"code": "operation_reused"})
        try:
            receipt = ExceptionAcknowledgeReceipt(
                organization_id=context.organization.id,
                actor_user_id=context.user.id,
                event_id=existing_event.id,
                client_operation_id=operation_id,
                request_sha256=digest,
                exception_id=exception_id,
                facility_id=value.facility_id,
                room_id=value.room_id,
                expected_version=int(binding["expected_version"]),
                resulting_version=int(binding["resulting_version"]),
                occurred_at=aware_utc(existing_event.occurred_at),
            )
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                409,
                detail={"code": "operation_receipt_incomplete"},
            ) from None
        return ExceptionAcknowledgeResponse(
            organization_id=context.organization.id,
            client_operation_id=operation_id,
            request_sha256=digest,
            replayed=True,
            receipt=receipt,
            exception=_single_exception_item(session, value),
            generated_at=datetime.now(UTC),
        )
    if value.state == "resolved":
        raise HTTPException(409, detail={"code": "exception_resolved"})
    if value.state != "open" or value.version != expected_version:
        raise HTTPException(
            409,
            detail={
                "code": "stale_exception_version",
                "current_version": value.version,
                "current_state": value.state,
            },
        )
    now = datetime.now(UTC)
    event_id = uuid4()
    receipt = ExceptionAcknowledgeReceipt(
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        event_id=event_id,
        client_operation_id=operation_id,
        request_sha256=digest,
        exception_id=value.id,
        facility_id=value.facility_id,
        room_id=value.room_id,
        expected_version=expected_version,
        resulting_version=expected_version + 1,
        occurred_at=now,
    )
    _set_operation_context(session, operation_id=operation_id, server_derived=False)
    value.state = "acknowledged"
    value.acknowledged_at = now
    value.acknowledged_by_user_id = context.user.id
    value.acknowledgement_reason = normalized_reason(reason)
    value.version += 1
    value.updated_at = now
    session.flush([value])
    event = RoomOperationalExceptionEvent(
        id=event_id,
        organization_id=context.organization.id,
        exception_id=value.id,
        operation_id=operation_id,
        event_type="acknowledged",
        actor_user_id=context.user.id,
        cause_entity_type="room_operational_exception",
        cause_entity_id=value.id,
        previous_fingerprint_sha256=value.current_fingerprint_sha256,
        current_fingerprint_sha256=value.current_fingerprint_sha256,
        evidence=value.current_evidence,
        reason=value.acknowledgement_reason,
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    session.flush([event])
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="room_operational_exception.acknowledged",
        entity_type="room_operational_exception",
        entity_id=value.id,
        facility_id=value.facility_id,
        details={
            "operation_id": str(operation_id),
            "request_sha256": digest,
            "expected_version": expected_version,
            "resulting_version": value.version,
            "version": value.version,
        },
    )
    _emit_exception_realtime(
        session,
        value,
        event_type="acknowledged",
        event_id=event_id,
        requires_action=False,
    )
    session.flush()
    return ExceptionAcknowledgeResponse(
        organization_id=context.organization.id,
        client_operation_id=operation_id,
        request_sha256=digest,
        replayed=False,
        receipt=receipt,
        exception=_single_exception_item(session, value),
        generated_at=now,
    )
