"""Focused portable proofs for the 0041 live room-operations contract.

These tests intentionally use an isolated in-memory SQLite database.  They
exercise the service boundary directly so the 0041 behavior remains testable
without a retained database, external services, or application startup state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import app.basic.room_safety as room_safety_module
import app.basic.shift_guards as shift_guards_module
from app.api.basic.dependencies import BasicContext
from app.api.basic.room_safety import _manager_access, _manager_scope
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    AuditEvent,
    BasicBase,
    Facility,
    MembershipRoomAssignment,
    Organization,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    Room,
    RoomOperationalExceptionEvent,
    RoomOperationalExceptionHead,
    StaffCoverageTargetProfile,
    StaffRoomPresenceSession,
    StaffShift,
    User,
    UserNotification,
)
from app.basic.room_safety import (
    _active_target,
    acknowledge_exception,
    aware_utc,
    capability_enabled,
    capability_marker,
    close_presence_for_access_revocation,
    close_presence_for_clock_out,
    create_clock_in_presence,
    end_presence,
    exception_page,
    facility_live_board,
    move_presence,
    reconcile_facility_exceptions,
    release_reconciliation_status,
    require_capability,
    run_release_reconciliation,
    staff_presence_projection,
    staff_room_live_board,
    start_presence,
)
from app.basic.room_safety_schemas import (
    STANDING_OPERATIONAL_BOUNDARY,
    RoomSafetyCapability,
)
from app.basic.shift_guards import require_open_shift

FIXED_FACILITY_LOCAL_NOW = datetime(
    2026,
    6,
    15,
    12,
    0,
    tzinfo=ZoneInfo("America/Edmonton"),
)
FIXED_NOW = FIXED_FACILITY_LOCAL_NOW.astimezone(UTC)


class _FixedRoomSafetyDateTime(datetime):
    """Keep defaults in one facility-local minute with deterministic ordering."""

    _next = FIXED_NOW

    @classmethod
    def reset(cls) -> None:
        cls._next = FIXED_NOW

    @classmethod
    def now(cls, tz=None):
        value = cls._next
        cls._next += timedelta(seconds=1)
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)


@dataclass
class World:
    session: Session
    context: BasicContext
    organization: Organization
    user: User
    role: Role
    membership: OrganizationMembership
    facility: Facility
    room_one: Room
    room_two: Room
    assignment_one: MembershipRoomAssignment
    assignment_two: MembershipRoomAssignment
    shift: StaffShift
    now: datetime


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    _FixedRoomSafetyDateTime.reset()
    monkeypatch.setattr(room_safety_module, "datetime", _FixedRoomSafetyDateTime)
    monkeypatch.setattr(shift_guards_module, "datetime", _FixedRoomSafetyDateTime)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BasicBase.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    now = FIXED_NOW
    organization = Organization(
        id=uuid4(),
        name="0041 Portable Centre",
        status="active",
        timezone="America/Edmonton",
    )
    user = User(
        id=uuid4(),
        email=f"room-safety-{uuid4()}@example.test",
        password_hash="test-only",
        first_name="Room",
        last_name="Operator",
        is_active=True,
    )
    role = Role(
        id=uuid4(),
        organization_id=organization.id,
        key="owner",
        name="Owner",
        permissions=[
            "facility:read",
            "facility:manage",
            "care_roster:read",
            "staff:manage_educators",
            "shift:clock",
            "child_safety:read",
        ],
    )
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        role_id=role.id,
        status="active",
        joined_at=now,
    )
    facility = Facility(
        id=uuid4(),
        organization_id=organization.id,
        name="0041 Main",
        status="active",
        timezone="America/Edmonton",
        licensed_capacity=20,
    )
    room_one = Room(
        id=uuid4(),
        organization_id=organization.id,
        facility_id=facility.id,
        program_id=None,
        name="Infant North",
        capacity=1,
        is_active=True,
    )
    room_two = Room(
        id=uuid4(),
        organization_id=organization.id,
        facility_id=facility.id,
        program_id=None,
        name="Preschool South",
        capacity=4,
        is_active=True,
    )
    assignment_one = MembershipRoomAssignment(
        id=uuid4(),
        organization_id=organization.id,
        membership_id=membership.id,
        facility_id=facility.id,
        room_id=room_one.id,
        is_active=True,
        created_by_user_id=user.id,
    )
    assignment_two = MembershipRoomAssignment(
        id=uuid4(),
        organization_id=organization.id,
        membership_id=membership.id,
        facility_id=facility.id,
        room_id=room_two.id,
        is_active=True,
        created_by_user_id=user.id,
    )
    shift = StaffShift(
        id=uuid4(),
        organization_id=organization.id,
        membership_id=membership.id,
        facility_id=facility.id,
        scheduled_shift_id=None,
        status="open",
        clocked_in_at=now - timedelta(hours=1),
        clocked_out_at=None,
    )
    session.add_all(
        [
            organization,
            user,
            role,
            membership,
            facility,
            room_one,
            room_two,
            assignment_one,
            assignment_two,
            shift,
        ]
    )
    session.flush()
    context = BasicContext(
        user=user,
        organization=organization,
        membership=membership,
        role=role,
        assigned_facility_ids=(facility.id,),
        assigned_room_ids=(room_one.id, room_two.id),
    )
    value = World(
        session=session,
        context=context,
        organization=organization,
        user=user,
        role=role,
        membership=membership,
        facility=facility,
        room_one=room_one,
        room_two=room_two,
        assignment_one=assignment_one,
        assignment_two=assignment_two,
        shift=shift,
        now=now,
    )
    try:
        yield value
    finally:
        session.close()
        engine.dispose()


def _request(*, foundation_enabled: bool) -> Request:
    application = SimpleNamespace(
        state=SimpleNamespace(live_room_presence_safety_board_foundation_enabled=foundation_enabled)
    )
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/room-safety/capability",
            "raw_path": b"/api/v1/room-safety/capability",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
            "app": application,
        }
    )


def _error_code(error: pytest.ExceptionInfo[HTTPException]) -> str:
    assert isinstance(error.value.detail, dict)
    return str(error.value.detail["code"])


def _as_of(world: World) -> datetime:
    return world.now + timedelta(minutes=5)


def _add_target(
    world: World,
    *,
    room: Room | None,
    required_staff: int,
) -> StaffCoverageTargetProfile:
    local = _as_of(world).astimezone(ZoneInfo(world.facility.timezone))
    value = StaffCoverageTargetProfile(
        id=uuid4(),
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        room_id=room.id if room is not None else None,
        windows=[
            {
                "weekday": local.weekday(),
                "start_local": "00:00",
                "end_local": "23:45",
                "required_staff": required_staff,
            }
        ],
        is_specified=True,
        last_operation_id=uuid4(),
    )
    world.session.add(value)
    world.session.flush()
    return value


def _add_present_child(
    world: World,
    *,
    room: Room | None,
    with_interval: bool = True,
) -> AttendanceDay:
    day = AttendanceDay(
        id=uuid4(),
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        child_id=uuid4(),
        enrollment_id=uuid4(),
        room_id=room.id if room is not None else None,
        service_date=_as_of(world).astimezone(ZoneInfo(world.facility.timezone)).date(),
        status="present",
        version=1,
    )
    world.session.add(day)
    if with_interval:
        world.session.add(
            AttendanceInterval(
                id=uuid4(),
                organization_id=world.organization.id,
                attendance_day_id=day.id,
                sequence=1,
                checked_in_at=world.now - timedelta(minutes=30),
                checked_out_at=None,
            )
        )
    world.session.flush()
    return day


def _start_in_room_one(world: World):
    return start_presence(
        world.session,
        world.context,
        operation_id=uuid4(),
        shift_id=world.shift.id,
        facility_id=world.facility.id,
        room_id=world.room_one.id,
    )


def _scope_as_educator(world: World) -> None:
    world.role.key = "educator"
    world.role.name = "Educator"
    world.role.permissions = [
        "facility:read",
        "care_roster:read",
        "shift:clock",
    ]
    world.session.flush()
    assert world.context.organization_wide is False


def test_capability_is_absent_before_0041_cutover_and_present_after_receipts(
    world: World,
) -> None:
    request = _request(foundation_enabled=False)
    with pytest.raises(HTTPException) as unavailable:
        require_capability(request, world.session, world.organization.id)
    assert unavailable.value.status_code == 503
    assert _error_code(unavailable) == "room_presence_foundation_unavailable"
    assert capability_enabled(request, world.session, world.organization.id) is False

    request.app.state.live_room_presence_safety_board_foundation_enabled = True
    with pytest.raises(HTTPException) as unreconciled:
        require_capability(request, world.session, world.organization.id)
    assert unreconciled.value.status_code == 503
    assert _error_code(unreconciled) == "room_presence_release_reconciliation_required"

    reviewed = release_reconciliation_status(
        world.session,
        world.organization.id,
        foundation_available=True,
    )
    response = run_release_reconciliation(
        world.session,
        world.context,
        operation_id=uuid4(),
        expected_facility_ids=reviewed.missing_facility_ids,
        expected_facility_set_sha256=reviewed.facility_set_sha256,
        expected_active_facility_count=reviewed.active_facility_count,
    )
    assert response.complete is True
    assert response.replayed is False
    assert [item.facility_id for item in response.facility_receipts] == [world.facility.id]
    require_capability(request, world.session, world.organization.id)
    assert capability_enabled(request, world.session, world.organization.id) is True
    assert capability_marker() == RoomSafetyCapability()


def test_0041_schema_and_operational_copy_are_closed(world: World) -> None:
    marker = capability_marker().model_dump(mode="json")
    assert set(marker) == {
        "schema_version",
        "capability",
        "runtime_available",
        "self_presence_read_path",
        "self_live_board_path",
        "start_path",
        "move_path",
        "end_path",
        "manager_live_board_path",
        "manager_exceptions_path",
        "manager_action_target_path_template",
        "manager_acknowledge_path_template",
        "online_only",
        "operational_configured_target_only",
        "regulatory_compliance_certified",
    }
    assert marker["schema_version"] == "0041"
    assert marker["runtime_available"] is True
    assert marker["online_only"] is True
    assert marker["operational_configured_target_only"] is True
    assert marker["regulatory_compliance_certified"] is False
    assert (
        marker["manager_action_target_path_template"]
        == "/api/v1/room-safety/exceptions/{exception_id}/action-target"
    )
    with pytest.raises(ValidationError):
        RoomSafetyCapability(schema_version="0040")

    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    assert board.schema_version == "live-room-safety-v1"
    assert board.standing_boundary == STANDING_OPERATIONAL_BOUNDARY
    assert board.operational_configured_target_only is True
    assert board.regulatory_compliance_certified is False


def test_open_shift_without_eligible_room_still_requires_presence(
    world: World,
) -> None:
    _scope_as_educator(world)
    world.assignment_one.is_active = False
    world.assignment_two.is_active = False
    world.session.flush()
    projection = staff_presence_projection(world.session, world.context)
    assert projection.open_shift is not None
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is True
    assert projection.decision_reason == "no_eligible_room"


def test_organization_wide_presence_is_coherent_without_access_assignments(
    world: World,
) -> None:
    world.assignment_one.is_active = False
    world.assignment_two.is_active = False
    world.session.flush()

    roomless = staff_presence_projection(
        world.session,
        world.context,
        generated_at=world.now,
    )
    assert roomless.current_presence is None
    assert {value.id for value in roomless.eligible_rooms} == {
        world.room_one.id,
        world.room_two.id,
    }
    assert roomless.decision_reason == "room_selection_required"

    started = create_clock_in_presence(
        world.session,
        world.context,
        shift=world.shift,
        operation_id=uuid4(),
        scheduled_shift=None,
        explicit_room_id=world.room_one.id,
    )
    assert started is not None
    world.session.flush()
    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    room = next(value for value in board.rooms if value.room_id == world.room_one.id)
    assert board.facility.open_shift_staff == 1
    assert board.facility.located_staff == 1
    assert board.facility.unlocated_staff == 0
    assert "room_presence_source_incoherent" not in (board.facility.data_quality_reason_codes)
    assert room.confirmed_staff == 1

    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    assert (
        world.session.scalar(
            select(func.count(RoomOperationalExceptionHead.id)).where(
                RoomOperationalExceptionHead.organization_id == world.organization.id,
                RoomOperationalExceptionHead.facility_id == world.facility.id,
                RoomOperationalExceptionHead.condition_code == "source_integrity_unknown",
                RoomOperationalExceptionHead.state != "resolved",
            )
        )
        == 0
    )


def test_inactive_shift_facility_fails_closed_and_retains_authorized_identity(
    world: World,
) -> None:
    world.facility.status = "inactive"
    world.session.flush()

    projection = staff_presence_projection(
        world.session,
        world.context,
        generated_at=world.now,
    )
    assert projection.open_shift is not None
    assert projection.open_shift.facility_id == world.facility.id
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    board = staff_room_live_board(world.session, world.context)
    assert board.facility_id == world.facility.id
    assert board.facility_timezone == "America/Edmonton"
    assert board.current_room is None
    assert board.unavailable_reason == "source_integrity_unknown"


def test_future_open_shift_fails_closed_without_exposing_room_choices(
    world: World,
) -> None:
    world.shift.clocked_in_at = world.now + timedelta(minutes=1)
    world.session.flush()

    projection = staff_presence_projection(
        world.session,
        world.context,
        generated_at=world.now,
    )
    assert projection.open_shift is not None
    assert projection.open_shift.facility_id == world.facility.id
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    board = staff_room_live_board(world.session, world.context)
    assert board.facility_id == world.facility.id
    assert board.facility_timezone == "America/Edmonton"
    assert board.current_room is None
    assert board.unavailable_reason == "source_integrity_unknown"

    with pytest.raises(HTTPException) as rejected:
        start_presence(
            world.session,
            world.context,
            operation_id=uuid4(),
            shift_id=world.shift.id,
            facility_id=world.facility.id,
            room_id=world.room_one.id,
        )
    assert rejected.value.status_code == 409
    assert _error_code(rejected) == "source_integrity_unknown"
    assert rejected.value.detail["reason"] == "open_shift_invalid"
    assert (
        world.session.scalar(
            select(func.count())
            .select_from(StaffRoomPresenceSession)
            .where(StaffRoomPresenceSession.organization_id == world.organization.id)
        )
        == 0
    )


def test_future_current_presence_is_unknown_and_cannot_be_moved(
    world: World,
) -> None:
    started = _start_in_room_one(world)
    current = world.session.get(
        StaffRoomPresenceSession,
        started.affected_session_id,
    )
    assert current is not None
    current.started_at = world.now + timedelta(minutes=2)
    world.session.flush()

    projection = staff_presence_projection(
        world.session,
        world.context,
        generated_at=world.now,
    )
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    with pytest.raises(HTTPException) as rejected:
        move_presence(
            world.session,
            world.context,
            operation_id=uuid4(),
            expected_session_id=current.id,
            expected_version=current.version,
            destination_room_id=world.room_two.id,
            reason="planned_room_change",
        )
    assert rejected.value.status_code == 409
    assert _error_code(rejected) == "source_integrity_unknown"
    assert rejected.value.detail["reason"] == "current_room_presence_invalid"


def test_invalid_shift_facility_timezone_is_nullable_only_on_unknown_board(
    world: World,
) -> None:
    world.facility.timezone = "not/a-real-timezone"
    world.session.flush()

    projection = staff_presence_projection(world.session, world.context)
    assert projection.open_shift is not None
    assert projection.open_shift.facility_id == world.facility.id
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    board = staff_room_live_board(world.session, world.context)

    assert board.facility_id == world.facility.id
    assert board.facility_timezone is None
    assert board.current_room is None
    assert board.unavailable_reason == "source_integrity_unknown"


def test_invalid_current_room_assignment_is_fail_visible_without_room_choices(
    world: World,
) -> None:
    _scope_as_educator(world)
    started = _start_in_room_one(world)
    world.assignment_one.is_active = False
    world.session.flush()

    projection = staff_presence_projection(world.session, world.context)
    assert projection.open_shift is not None
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    board = staff_room_live_board(world.session, world.context)
    assert board.facility_id == world.facility.id
    assert board.current_room is None
    assert board.unavailable_reason == "source_integrity_unknown"

    terminal_receipts = close_presence_for_clock_out(
        world.session,
        world.context,
        shift=world.shift,
        operation_id=uuid4(),
        occurred_at=world.now + timedelta(minutes=30),
    )
    assert [item.from_session_id for item in terminal_receipts] == [started.affected_session_id]


def test_current_presence_shift_mismatch_is_not_reported_as_a_room_selection(
    world: World,
) -> None:
    started = _start_in_room_one(world)
    world.shift.status = "closed"
    world.shift.clocked_out_at = world.now
    replacement_shift = StaffShift(
        id=uuid4(),
        organization_id=world.organization.id,
        membership_id=world.membership.id,
        facility_id=world.facility.id,
        scheduled_shift_id=None,
        status="open",
        clocked_in_at=world.now,
        clocked_out_at=None,
    )
    world.session.add(replacement_shift)
    world.session.flush()

    projection = staff_presence_projection(world.session, world.context)
    assert projection.open_shift is not None
    assert projection.open_shift.id == replacement_shift.id
    assert projection.current_presence is None
    assert projection.eligible_rooms == []
    assert projection.room_presence_required is False
    assert projection.decision_reason == "source_integrity_unknown"

    board = staff_room_live_board(world.session, world.context)
    assert board.current_room is None
    assert board.unavailable_reason == "source_integrity_unknown"

    terminal_receipts = close_presence_for_clock_out(
        world.session,
        world.context,
        shift=replacement_shift,
        operation_id=uuid4(),
        occurred_at=world.now + timedelta(minutes=30),
    )
    assert [item.from_session_id for item in terminal_receipts] == [started.affected_session_id]


def test_board_arithmetic_separates_capacity_from_configured_staff_target(
    world: World,
) -> None:
    _start_in_room_one(world)
    _add_target(world, room=world.room_one, required_staff=2)
    _add_present_child(world, room=world.room_one)
    _add_present_child(world, room=world.room_one)

    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    room = next(item for item in board.rooms if item.room_id == world.room_one.id)
    assert board.facility.confirmed_children == 2
    assert board.facility.open_shift_staff == 1
    assert board.facility.located_staff == 1
    assert board.facility.unlocated_staff == 0
    assert board.facility.overall_state == "attention"
    assert room.confirmed_children == 2
    assert room.configured_room_capacity == 1
    assert room.capacity_state == "above_configured_capacity"
    assert room.confirmed_staff == 1
    assert room.configured_target.required_staff == 2
    assert room.configured_target.state == "confirmed_staff_below_target"
    assert room.overall_state == "attention"


def test_facility_target_attention_materializes_a_facility_exception(
    world: World,
) -> None:
    _start_in_room_one(world)
    _add_target(world, room=None, required_staff=2)

    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()

    head = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.facility_id == world.facility.id,
            RoomOperationalExceptionHead.scope_kind == "facility",
            RoomOperationalExceptionHead.scope_id == world.facility.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_staff_below_configured_room_target",
            RoomOperationalExceptionHead.state != "resolved",
        )
    )
    assert head is not None
    assert head.room_id is None
    assert head.current_evidence == {
        "configured_value": 2,
        "observed_value": 1,
        "reason_codes": [],
    }


def test_target_projection_accepts_zero_and_rejects_noncanonical_stored_json(
    world: World,
) -> None:
    local_now = datetime(2026, 6, 15, 12, tzinfo=ZoneInfo("America/Edmonton"))
    canonical = SimpleNamespace(
        is_specified=True,
        windows=[
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 0,
            }
        ],
    )
    projected = _active_target(canonical, local_now=local_now)
    assert projected.state == "target_met"
    assert projected.required_staff == 0

    invalid_profiles = [
        None,
        [
            {
                "weekday": 7,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "08:07",
                "end_local": "16:00",
                "required_staff": 1,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "16:00",
                "end_local": "08:00",
                "required_staff": 1,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 501,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1,
                "legacy_note": "not part of the target contract",
            }
        ],
        [
            {
                "weekday": True,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": False,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1.0,
            }
        ],
        [
            {
                "weekday": 0,
                "start_local": "10:00",
                "end_local": "12:00",
                "required_staff": 1,
            },
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "11:00",
                "required_staff": 1,
            },
        ],
        [
            {
                "weekday": 1,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1,
            },
            {
                "weekday": 0,
                "start_local": "08:00",
                "end_local": "16:00",
                "required_staff": 1,
            },
        ],
    ]
    for windows in invalid_profiles:
        projected = _active_target(
            SimpleNamespace(is_specified=True, windows=windows),
            local_now=local_now,
        )
        assert projected.state == "unknown"
        assert projected.required_staff is None


def test_incoherent_present_day_fails_child_arithmetic_to_unknown(
    world: World,
) -> None:
    _start_in_room_one(world)
    _add_target(world, room=world.room_one, required_staff=1)
    _add_present_child(world, room=world.room_one)
    _add_present_child(world, room=world.room_one, with_interval=False)

    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    room = next(item for item in board.rooms if item.room_id == world.room_one.id)
    assert board.facility.confirmed_children is None
    assert board.facility.present_children_without_active_room is None
    assert board.facility.overall_state == "unknown"
    assert board.facility.data_quality_reason_codes == ["attendance_source_incoherent"]
    assert room.confirmed_children is None
    assert room.capacity_state == "unknown"
    assert room.confirmed_staff == 1
    assert room.configured_target.state == "target_met"
    assert room.overall_state == "unknown"
    assert room.data_quality_reason_codes == ["attendance_source_incoherent"]


def test_staff_source_incoherence_makes_unconfigured_room_unknown(
    world: World,
) -> None:
    _scope_as_educator(world)
    _start_in_room_one(world)
    world.assignment_one.is_active = False
    world.session.flush()

    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    room = next(item for item in board.rooms if item.room_id == world.room_one.id)

    assert room.confirmed_children == 0
    assert room.capacity_state == "within_configured_capacity"
    assert room.confirmed_staff is None
    assert room.configured_target.state == "not_configured"
    assert room.data_quality_reason_codes == ["room_presence_source_incoherent"]
    assert room.overall_state == "unknown"


def test_staff_board_exposes_unknown_source_even_when_attention_has_precedence(
    world: World,
) -> None:
    _start_in_room_one(world)
    _add_target(world, room=world.room_one, required_staff=2)
    _add_present_child(
        world,
        room=world.room_one,
        with_interval=False,
    )

    board = staff_room_live_board(world.session, world.context)

    assert board.current_room is not None
    assert board.current_room.overall_state == "attention"
    assert board.current_room.confirmed_children is None
    assert board.current_room.capacity_state == "unknown"
    assert board.current_room.data_quality_reason_codes == ["attendance_source_incoherent"]
    assert board.unavailable_reason == "source_integrity_unknown"


def test_active_interval_on_nonpresent_day_fails_board_to_unknown(
    world: World,
) -> None:
    _start_in_room_one(world)
    day = _add_present_child(world, room=world.room_one)
    day.status = "absent"
    world.session.flush()

    board = facility_live_board(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        as_of=_as_of(world),
    )
    room = next(item for item in board.rooms if item.room_id == world.room_one.id)
    assert board.facility.confirmed_children is None
    assert board.facility.present_children_without_active_room is None
    assert board.facility.overall_state == "unknown"
    assert board.facility.data_quality_reason_codes == ["attendance_source_incoherent"]
    assert room.confirmed_children is None
    assert room.capacity_state == "unknown"
    assert room.data_quality_reason_codes == ["attendance_source_incoherent"]


def test_incoherent_source_cannot_resolve_a_confirmed_capacity_episode(
    world: World,
) -> None:
    first_day = _add_present_child(world, room=world.room_one)
    _add_present_child(world, room=world.room_one)
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()

    capacity_head = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.facility_id == world.facility.id,
            RoomOperationalExceptionHead.scope_kind == "room",
            RoomOperationalExceptionHead.scope_id == world.room_one.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_children_above_configured_room_capacity",
        )
    )
    assert capacity_head is not None
    original_version = capacity_head.version
    original_fingerprint = capacity_head.current_fingerprint_sha256

    incoherent_day = _add_present_child(
        world,
        room=world.room_one,
        with_interval=False,
    )
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    world.session.refresh(capacity_head)

    assert capacity_head.state == "open"
    assert capacity_head.version == original_version
    assert capacity_head.current_fingerprint_sha256 == original_fingerprint
    assert (
        world.session.scalar(
            select(RoomOperationalExceptionHead).where(
                RoomOperationalExceptionHead.organization_id == world.organization.id,
                RoomOperationalExceptionHead.facility_id == world.facility.id,
                RoomOperationalExceptionHead.condition_code == "source_integrity_unknown",
                RoomOperationalExceptionHead.state != "resolved",
            )
        )
        is not None
    )
    assert (
        world.session.scalar(
            select(func.count(RoomOperationalExceptionEvent.id)).where(
                RoomOperationalExceptionEvent.organization_id == world.organization.id,
                RoomOperationalExceptionEvent.exception_id == capacity_head.id,
                RoomOperationalExceptionEvent.event_type == "resolved",
            )
        )
        == 0
    )

    first_interval = world.session.scalar(
        select(AttendanceInterval).where(
            AttendanceInterval.attendance_day_id == first_day.id,
        )
    )
    assert first_interval is not None
    first_interval.checked_out_at = world.now - timedelta(minutes=1)
    world.session.add(
        AttendanceInterval(
            id=uuid4(),
            organization_id=world.organization.id,
            attendance_day_id=incoherent_day.id,
            sequence=1,
            checked_in_at=world.now - timedelta(minutes=20),
            checked_out_at=world.now - timedelta(minutes=10),
        )
    )
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    world.session.refresh(capacity_head)

    assert capacity_head.state == "resolved"
    assert capacity_head.version == original_version + 1
    assert (
        world.session.scalar(
            select(func.count(RoomOperationalExceptionEvent.id)).where(
                RoomOperationalExceptionEvent.organization_id == world.organization.id,
                RoomOperationalExceptionEvent.exception_id == capacity_head.id,
                RoomOperationalExceptionEvent.event_type == "resolved",
            )
        )
        == 1
    )


def test_acknowledged_source_improvement_keeps_episode_and_suppresses_new_wake(
    world: World,
) -> None:
    _scope_as_educator(world)
    _start_in_room_one(world)
    world.assignment_one.is_active = False
    _add_present_child(world, room=world.room_one, with_interval=False)
    world.session.flush()

    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=False,
    )
    world.session.flush()
    head = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.facility_id == world.facility.id,
            RoomOperationalExceptionHead.scope_kind == "room",
            RoomOperationalExceptionHead.scope_id == world.room_one.id,
            RoomOperationalExceptionHead.condition_code == "source_integrity_unknown",
            RoomOperationalExceptionHead.state == "open",
        )
    )
    assert head is not None
    assert head.current_evidence["reason_codes"] == [
        "attendance_source_incoherent",
        "room_presence_source_incoherent",
    ]

    # The scoped educator source above is the fact under test. A separate
    # organization-wide manager authority is represented here before the
    # acknowledgement command.
    world.role.key = "owner"
    world.role.name = "Owner"
    world.role.permissions = [
        "facility:read",
        "care_roster:read",
        "staff:manage_educators",
        "shift:clock",
    ]
    world.session.flush()
    acknowledged = acknowledge_exception(
        world.session,
        world.context,
        exception_id=head.id,
        operation_id=uuid4(),
        expected_version=head.version,
        reason="Manager reviewed both source-integrity signals",
    )
    assert acknowledged.exception.state == "acknowledged"
    acknowledged_version = acknowledged.exception.version
    acknowledged_at = acknowledged.exception.acknowledged_at
    previous_fingerprint = head.current_fingerprint_sha256
    event_count = world.session.scalar(
        select(func.count(RoomOperationalExceptionEvent.id)).where(
            RoomOperationalExceptionEvent.organization_id == world.organization.id,
            RoomOperationalExceptionEvent.exception_id == head.id,
        )
    )
    realtime_count = world.session.scalar(
        select(func.count(RealtimeEvent.id)).where(
            RealtimeEvent.organization_id == world.organization.id,
            RealtimeEvent.entity_id == head.id,
        )
    )
    notification_count = world.session.scalar(
        select(func.count(UserNotification.id)).where(
            UserNotification.organization_id == world.organization.id,
            UserNotification.action_entity_id == head.id,
        )
    )

    world.assignment_one.is_active = True
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=False,
    )
    world.session.flush()
    world.session.refresh(head)

    assert head.state == "acknowledged"
    assert head.version == acknowledged_version
    assert head.acknowledged_at is not None
    assert acknowledged_at is not None
    assert aware_utc(head.acknowledged_at) == aware_utc(acknowledged_at)
    assert head.current_fingerprint_sha256 != previous_fingerprint
    assert head.current_evidence["reason_codes"] == ["attendance_source_incoherent"]
    assert (
        world.session.scalar(
            select(func.count(RoomOperationalExceptionEvent.id)).where(
                RoomOperationalExceptionEvent.organization_id == world.organization.id,
                RoomOperationalExceptionEvent.exception_id == head.id,
            )
        )
        == event_count
    )
    assert (
        world.session.scalar(
            select(func.count(RealtimeEvent.id)).where(
                RealtimeEvent.organization_id == world.organization.id,
                RealtimeEvent.entity_id == head.id,
            )
        )
        == realtime_count
    )
    assert (
        world.session.scalar(
            select(func.count(UserNotification.id)).where(
                UserNotification.organization_id == world.organization.id,
                UserNotification.action_entity_id == head.id,
            )
        )
        == notification_count
    )


def test_presence_commands_are_exactly_replayable_and_fail_stale_or_reused_intent(
    world: World,
) -> None:
    start_operation = uuid4()
    started = start_presence(
        world.session,
        world.context,
        operation_id=start_operation,
        shift_id=world.shift.id,
        facility_id=world.facility.id,
        room_id=world.room_one.id,
    )
    start_replay = start_presence(
        world.session,
        world.context,
        operation_id=start_operation,
        shift_id=world.shift.id,
        facility_id=world.facility.id,
        room_id=world.room_one.id,
    )
    assert start_replay.replayed is True
    assert start_replay.receipt == started.receipt
    with pytest.raises(HTTPException) as reused:
        start_presence(
            world.session,
            world.context,
            operation_id=start_operation,
            shift_id=world.shift.id,
            facility_id=world.facility.id,
            room_id=world.room_two.id,
        )
    assert _error_code(reused) == "operation_reused"

    with pytest.raises(HTTPException) as stale_move:
        move_presence(
            world.session,
            world.context,
            operation_id=uuid4(),
            expected_session_id=started.affected_session_id,
            expected_version=99,
            destination_room_id=world.room_two.id,
            reason="Move after refreshed room review",
        )
    assert _error_code(stale_move) == "stale_room_presence"

    move_operation = uuid4()
    moved = move_presence(
        world.session,
        world.context,
        operation_id=move_operation,
        expected_session_id=started.affected_session_id,
        expected_version=1,
        destination_room_id=world.room_two.id,
        reason="Move after refreshed room review",
    )
    move_replay = move_presence(
        world.session,
        world.context,
        operation_id=move_operation,
        expected_session_id=started.affected_session_id,
        expected_version=1,
        destination_room_id=world.room_two.id,
        reason="Move after refreshed room review",
    )
    assert move_replay.replayed is True
    assert move_replay.receipt == moved.receipt

    end_operation = uuid4()
    ended = end_presence(
        world.session,
        world.context,
        operation_id=end_operation,
        expected_session_id=moved.affected_session_id,
        expected_version=1,
        reason="Staff ended direct room coverage",
    )
    end_replay = end_presence(
        world.session,
        world.context,
        operation_id=end_operation,
        expected_session_id=moved.affected_session_id,
        expected_version=1,
        reason="Staff ended direct room coverage",
    )
    assert end_replay.replayed is True
    assert end_replay.receipt == ended.receipt
    assert end_replay.current_presence.current_presence is None


def test_presence_operation_id_cross_command_reuse_is_always_rejected(
    world: World,
) -> None:
    start_operation = uuid4()
    started = start_presence(
        world.session,
        world.context,
        operation_id=start_operation,
        shift_id=world.shift.id,
        facility_id=world.facility.id,
        room_id=world.room_one.id,
    )
    with pytest.raises(HTTPException) as start_as_move:
        move_presence(
            world.session,
            world.context,
            operation_id=start_operation,
            expected_session_id=started.affected_session_id,
            expected_version=1,
            destination_room_id=world.room_two.id,
            reason="Cross command operation reuse",
        )
    assert _error_code(start_as_move) == "operation_reused"
    with pytest.raises(HTTPException) as start_as_end:
        end_presence(
            world.session,
            world.context,
            operation_id=start_operation,
            expected_session_id=started.affected_session_id,
            expected_version=1,
            reason="Cross command operation reuse",
        )
    assert _error_code(start_as_end) == "operation_reused"

    move_operation = uuid4()
    moved = move_presence(
        world.session,
        world.context,
        operation_id=move_operation,
        expected_session_id=started.affected_session_id,
        expected_version=1,
        destination_room_id=world.room_two.id,
        reason="Move into the next assigned room",
    )
    with pytest.raises(HTTPException) as move_as_start:
        start_presence(
            world.session,
            world.context,
            operation_id=move_operation,
            shift_id=world.shift.id,
            facility_id=world.facility.id,
            room_id=world.room_one.id,
        )
    assert _error_code(move_as_start) == "operation_reused"
    with pytest.raises(HTTPException) as move_as_end:
        end_presence(
            world.session,
            world.context,
            operation_id=move_operation,
            expected_session_id=moved.affected_session_id,
            expected_version=1,
            reason="Cross command operation reuse",
        )
    assert _error_code(move_as_end) == "operation_reused"

    end_operation = uuid4()
    end_presence(
        world.session,
        world.context,
        operation_id=end_operation,
        expected_session_id=moved.affected_session_id,
        expected_version=1,
        reason="End the current assigned room coverage",
    )
    with pytest.raises(HTTPException) as end_as_start:
        start_presence(
            world.session,
            world.context,
            operation_id=end_operation,
            shift_id=world.shift.id,
            facility_id=world.facility.id,
            room_id=world.room_one.id,
        )
    assert _error_code(end_as_start) == "operation_reused"
    with pytest.raises(HTTPException) as end_as_move:
        move_presence(
            world.session,
            world.context,
            operation_id=end_operation,
            expected_session_id=moved.affected_session_id,
            expected_version=2,
            destination_room_id=world.room_one.id,
            reason="Cross command operation reuse",
        )
    assert _error_code(end_as_move) == "operation_reused"


def test_exception_acknowledgement_replay_resolution_and_recurrence(
    world: World,
) -> None:
    _start_in_room_one(world)
    _add_present_child(world, room=world.room_one)
    _add_present_child(world, room=world.room_one)
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    head = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.facility_id == world.facility.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_children_above_configured_room_capacity",
            RoomOperationalExceptionHead.state != "resolved",
        )
    )
    assert head is not None
    assert head.state == "open"
    assert head.version == 1

    operation_id = uuid4()
    acknowledged = acknowledge_exception(
        world.session,
        world.context,
        exception_id=head.id,
        operation_id=operation_id,
        expected_version=1,
        reason="Manager reviewed current room evidence",
    )
    replay = acknowledge_exception(
        world.session,
        world.context,
        exception_id=head.id,
        operation_id=operation_id,
        expected_version=1,
        reason="Manager reviewed current room evidence",
    )
    assert acknowledged.replayed is False
    assert acknowledged.exception.state == "acknowledged"
    assert acknowledged.exception.version == 2
    assert acknowledged.exception.materially_changed_at is None
    assert replay.replayed is True
    assert replay.receipt == acknowledged.receipt
    assert replay.exception.materially_changed_at is None

    with pytest.raises(HTTPException) as reused:
        acknowledge_exception(
            world.session,
            world.context,
            exception_id=head.id,
            operation_id=operation_id,
            expected_version=1,
            reason="Different acknowledgement intent",
        )
    assert _error_code(reused) == "operation_reused"
    with pytest.raises(HTTPException) as stale:
        acknowledge_exception(
            world.session,
            world.context,
            exception_id=head.id,
            operation_id=uuid4(),
            expected_version=1,
            reason="Manager reviewed current room evidence",
        )
    assert _error_code(stale) == "stale_exception_version"

    world.room_one.capacity = 3
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    assert head.state == "resolved"
    assert head.version == 3
    resolved_replay = acknowledge_exception(
        world.session,
        world.context,
        exception_id=head.id,
        operation_id=operation_id,
        expected_version=1,
        reason="Manager reviewed current room evidence",
    )
    assert resolved_replay.replayed is True
    assert resolved_replay.exception.state == "resolved"
    assert resolved_replay.exception.materially_changed_at is None

    world.room_one.capacity = 1
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    recurrence = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_children_above_configured_room_capacity",
            RoomOperationalExceptionHead.state == "open",
        )
    )
    assert recurrence is not None
    assert recurrence.id != head.id
    assert recurrence.version == 1


def test_exception_material_time_comes_only_from_latest_append_only_event(
    world: World,
) -> None:
    _add_present_child(world, room=world.room_one)
    _add_present_child(world, room=world.room_one)
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    first_episode = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_children_above_configured_room_capacity",
            RoomOperationalExceptionHead.state == "open",
        )
    )
    assert first_episode is not None

    world.room_one.capacity = 3
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    first_page = exception_page(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        state_filter="all",
        cursor=None,
        limit=100,
    )
    first_item = next(item for item in first_page.items if item.id == first_episode.id)
    assert first_item.state == "resolved"
    assert first_item.resolved_at is not None
    assert first_item.materially_changed_at is None

    world.room_one.capacity = 1
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    second_episode = world.session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == world.organization.id,
            RoomOperationalExceptionHead.condition_code
            == "confirmed_children_above_configured_room_capacity",
            RoomOperationalExceptionHead.state == "open",
        )
    )
    assert second_episode is not None
    assert second_episode.id != first_episode.id

    _add_present_child(world, room=world.room_one)
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    _add_present_child(world, room=world.room_one)
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    latest_material_time = world.session.scalar(
        select(func.max(RoomOperationalExceptionEvent.occurred_at)).where(
            RoomOperationalExceptionEvent.organization_id == world.organization.id,
            RoomOperationalExceptionEvent.exception_id == second_episode.id,
            RoomOperationalExceptionEvent.event_type == "materially_changed",
        )
    )
    assert latest_material_time is not None
    latest_material_time = (
        latest_material_time.astimezone(UTC)
        if latest_material_time.tzinfo
        else latest_material_time.replace(tzinfo=UTC)
    )

    acknowledgement_operation = uuid4()
    acknowledged = acknowledge_exception(
        world.session,
        world.context,
        exception_id=second_episode.id,
        operation_id=acknowledgement_operation,
        expected_version=second_episode.version,
        reason="Manager reviewed the latest material evidence",
    )
    assert acknowledged.exception.materially_changed_at == latest_material_time

    world.room_one.capacity = 5
    reconcile_facility_exceptions(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        cause_entity_type="focused_test",
        cause_entity_id=uuid4(),
        notifications_suppressed=True,
    )
    world.session.flush()
    replay = acknowledge_exception(
        world.session,
        world.context,
        exception_id=second_episode.id,
        operation_id=acknowledgement_operation,
        expected_version=acknowledged.receipt.expected_version,
        reason="Manager reviewed the latest material evidence",
    )
    assert replay.replayed is True
    assert replay.exception.state == "resolved"
    assert replay.exception.resolved_at is not None
    assert replay.exception.materially_changed_at == latest_material_time

    second_page = exception_page(
        world.session,
        organization_id=world.organization.id,
        facility_id=world.facility.id,
        state_filter="all",
        cursor=None,
        limit=100,
    )
    second_item = next(item for item in second_page.items if item.id == second_episode.id)
    assert second_item.materially_changed_at == latest_material_time
    assert second_item.materially_changed_at != second_item.resolved_at


def test_manager_permission_scope_and_cross_tenant_resources_fail_closed(
    world: World,
) -> None:
    denied_role = Role(
        id=uuid4(),
        organization_id=world.organization.id,
        key="limited_test",
        name="Limited",
        permissions=["facility:read", "care_roster:read"],
    )
    denied = BasicContext(
        user=world.user,
        organization=world.organization,
        membership=world.membership,
        role=denied_role,
    )
    with pytest.raises(HTTPException) as permission:
        _manager_access(denied)
    assert permission.value.status_code == 403

    scoped_role = Role(
        id=uuid4(),
        organization_id=world.organization.id,
        key="scoped_manager_test",
        name="Scoped manager",
        permissions=[
            "facility:read",
            "care_roster:read",
            "staff:manage_educators",
        ],
    )
    scoped = BasicContext(
        user=world.user,
        organization=world.organization,
        membership=world.membership,
        role=scoped_role,
        assigned_facility_ids=(),
        assigned_room_ids=(),
    )
    with pytest.raises(HTTPException) as hidden_scope:
        _manager_scope(scoped, world.facility.id)
    assert hidden_scope.value.status_code == 404

    foreign_organization = Organization(
        id=uuid4(),
        name="Foreign 0041 Centre",
        status="active",
        timezone="America/Edmonton",
    )
    foreign_facility = Facility(
        id=uuid4(),
        organization_id=foreign_organization.id,
        name="Foreign Main",
        status="active",
        timezone="America/Edmonton",
        licensed_capacity=10,
    )
    foreign_exception = RoomOperationalExceptionHead(
        id=uuid4(),
        organization_id=foreign_organization.id,
        facility_id=foreign_facility.id,
        scope_kind="facility",
        scope_id=foreign_facility.id,
        room_id=None,
        condition_code="open_shift_staff_without_current_room",
        state="open",
        current_fingerprint_sha256="0" * 64,
        current_evidence={"observed_value": 1},
        opened_at=world.now,
        last_changed_at=world.now,
        version=1,
    )
    world.session.add_all([foreign_organization, foreign_facility, foreign_exception])
    world.session.flush()
    with pytest.raises(HTTPException) as foreign_board:
        facility_live_board(
            world.session,
            organization_id=world.organization.id,
            facility_id=foreign_facility.id,
        )
    assert foreign_board.value.status_code == 404
    with pytest.raises(HTTPException) as foreign_ack:
        acknowledge_exception(
            world.session,
            world.context,
            exception_id=foreign_exception.id,
            operation_id=uuid4(),
            expected_version=1,
            reason="Attempted cross tenant review",
        )
    assert foreign_ack.value.status_code == 404


def test_clock_in_presence_and_terminal_clock_out_remain_coupled(
    world: World,
) -> None:
    clock_in_operation = uuid4()
    started = create_clock_in_presence(
        world.session,
        world.context,
        shift=world.shift,
        operation_id=clock_in_operation,
        scheduled_shift=None,
        explicit_room_id=world.room_one.id,
    )
    assert started is not None
    assert started.command_kind == "clock_in_presence"
    assert started.to_room_id == world.room_one.id
    world.session.flush()

    world.assignment_one.is_active = False
    world.assignment_two.is_active = False
    clock_out_operation = uuid4()
    ended = close_presence_for_clock_out(
        world.session,
        world.context,
        shift=world.shift,
        operation_id=clock_out_operation,
        occurred_at=world.now + timedelta(hours=1),
    )
    assert len(ended) == 1
    assert ended[0].command_kind == "clock_out_presence"
    assert ended[0].from_session_id == started.to_session_id
    world.session.flush()
    stored = world.session.get(StaffRoomPresenceSession, started.to_session_id)
    assert stored is not None
    assert stored.ended_at is not None
    assert stored.end_reason == "clocked_out"
    assert stored.end_operation_id == clock_out_operation
    assert stored.version == 2


def test_access_revocation_closure_always_invalidates_live_clients(
    world: World,
) -> None:
    started = _start_in_room_one(world)
    world.session.flush()
    receipts = close_presence_for_access_revocation(
        world.session,
        organization_id=world.organization.id,
        membership_id=world.membership.id,
        actor_user_id=world.user.id,
        operation_id=uuid4(),
        occurred_at=world.now + timedelta(minutes=15),
        locked_facility_ids={world.facility.id},
    )
    world.session.flush()

    assert len(receipts) == 1
    assert receipts[0].from_session_id == started.affected_session_id
    realtime = list(
        world.session.scalars(
            select(RealtimeEvent).where(
                RealtimeEvent.organization_id == world.organization.id,
                RealtimeEvent.event_type == "staff_room_presence.ended",
                RealtimeEvent.entity_id == started.affected_session_id,
            )
        )
    )
    assert len(realtime) == 1
    assert set(realtime[0].payload or {}) == {
        "event_id",
        "facility_id",
        "room_id",
        "requires_action",
    }
    assert UUID(str(realtime[0].payload["event_id"]))
    assert realtime[0].payload["facility_id"] == str(world.facility.id)
    assert realtime[0].payload["room_id"] == str(world.room_one.id)
    assert realtime[0].payload["requires_action"] is False
    assert list(
        world.session.scalars(
            select(AuditEvent).where(
                AuditEvent.organization_id == world.organization.id,
                AuditEvent.action == "staff_room_presence.access_revoked",
                AuditEvent.entity_id == started.affected_session_id,
            )
        )
    )


def test_nonterminal_roomless_child_mutation_fails_closed_but_terminal_escape_remains(
    world: World,
) -> None:
    with pytest.raises(HTTPException) as blocked:
        require_open_shift(
            world.session,
            world.context,
            world.facility.id,
            None,
            enforce_room_presence=True,
        )
    assert blocked.value.status_code == 409
    assert blocked.value.detail == {
        "code": "room_presence_source_room_unknown",
        "facility_id": str(world.facility.id),
        "required_room_id": None,
        "current_room_id": None,
        "message": (
            "This child record has no reliable room identity. "
            "Repair its room assignment before changing it."
        ),
    }

    require_open_shift(
        world.session,
        world.context,
        world.facility.id,
        None,
        enforce_room_presence=True,
        allow_terminal_integrity_escape=True,
    )


def test_future_shift_or_presence_blocks_nonterminal_child_work_but_not_checkout(
    world: World,
) -> None:
    started = _start_in_room_one(world)
    current = world.session.get(
        StaffRoomPresenceSession,
        started.affected_session_id,
    )
    assert current is not None

    world.shift.clocked_in_at = world.now + timedelta(minutes=2)
    world.session.flush()
    with pytest.raises(HTTPException) as future_shift:
        require_open_shift(
            world.session,
            world.context,
            world.facility.id,
            world.room_one.id,
            enforce_room_presence=True,
        )
    assert _error_code(future_shift) == "source_integrity_unknown"
    assert future_shift.value.detail["reason"] == "future_open_staff_shift"
    require_open_shift(
        world.session,
        world.context,
        world.facility.id,
        world.room_one.id,
        enforce_room_presence=True,
        allow_terminal_integrity_escape=True,
    )

    world.shift.clocked_in_at = world.now - timedelta(hours=1)
    current.started_at = world.now + timedelta(minutes=2)
    world.session.flush()
    with pytest.raises(HTTPException) as future_presence:
        require_open_shift(
            world.session,
            world.context,
            world.facility.id,
            world.room_one.id,
            enforce_room_presence=True,
        )
    assert _error_code(future_presence) == "source_integrity_unknown"
    assert future_presence.value.detail["reason"] == ("future_current_room_presence")
    require_open_shift(
        world.session,
        world.context,
        world.facility.id,
        world.room_one.id,
        enforce_room_presence=True,
        allow_terminal_integrity_escape=True,
    )
