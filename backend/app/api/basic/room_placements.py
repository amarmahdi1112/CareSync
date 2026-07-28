"""Approval-first DOB room placement recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, func, or_, select

from app.api.basic.common import commit_in_context, ensure_writable, lock_client_operation
from app.api.basic.dependencies import ChildcareManageContext
from app.api.dependencies import SessionDependency
from app.basic.childcare_commands import begin_command, record_command, require_version
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    Enrollment,
    Facility,
    Family,
    Program,
    Room,
)
from app.basic.programs import PROGRAM_TYPES
from app.basic.schemas import (
    EnrollmentResponse,
    RoomPlacementApprovalRequest,
    RoomPlacementBatchRequest,
    RoomPlacementBatchResponse,
    RoomPlacementCandidateResponse,
    RoomPlacementReviewResponse,
)
from app.basic.security import audit

router = APIRouter(tags=["basic room placements"])

OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")


@dataclass(frozen=True)
class _PlacementLockSet:
    families: dict[UUID, Family]
    children: dict[UUID, Child]
    facilities: dict[UUID, Facility]
    enrollments: dict[UUID, Enrollment]
    rooms: dict[UUID, Room]
    programs: dict[UUID, Program]


def full_calendar_months(date_of_birth: date, as_of: date) -> int:
    """Return complete calendar months elapsed, with inclusive birthday boundaries."""

    months = (as_of.year - date_of_birth.year) * 12 + as_of.month - date_of_birth.month
    if as_of.day < date_of_birth.day:
        months -= 1
    return months


def _facility_today(facility: Facility) -> date:
    try:
        return datetime.now(UTC).astimezone(ZoneInfo(facility.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(
            status_code=422,
            detail="Facility timezone must be corrected before reviewing room placement",
        ) from None


def _effective_date(enrollment: Enrollment, facility: Facility) -> date:
    """Use start date for future care, otherwise the facility's current local date."""

    return max(enrollment.start_date, _facility_today(facility))


def _occupancy(
    session: SessionDependency,
    organization_id: UUID,
    room_id: UUID,
    proposed_start: date,
    *,
    exclude_enrollment_id: UUID | None = None,
) -> int:
    statement = (
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.room_id == room_id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            Enrollment.placement_effective_date.is_not(None),
            # Open future reservations overlap an indefinite proposed
            # placement even when their own effective date is later.
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= proposed_start),
        )
    )
    if exclude_enrollment_id is not None:
        statement = statement.where(Enrollment.id != exclude_enrollment_id)
    return int(session.scalar(statement) or 0)


def _program_occupancy(
    session: SessionDependency,
    organization_id: UUID,
    program_id: UUID,
    proposed_start: date,
    *,
    exclude_enrollment_id: UUID | None = None,
) -> int:
    statement = (
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.program_id == program_id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            Enrollment.placement_effective_date.is_not(None),
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= proposed_start),
        )
    )
    if exclude_enrollment_id is not None:
        statement = statement.where(Enrollment.id != exclude_enrollment_id)
    return int(session.scalar(statement) or 0)


def _age_compatible(age_months: int, room: Room) -> bool:
    """Use the detailed room interval as the authoritative placement boundary."""

    if room.minimum_age_months is None or room.maximum_age_months is None:
        return False
    return room.minimum_age_months <= age_months <= room.maximum_age_months


def _candidate_rows(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    age_months: int,
    effective_date: date,
) -> list[RoomPlacementCandidateResponse]:
    rows = list(
        session.execute(
            select(Room, Program)
            .join(
                Program,
                and_(
                    Program.organization_id == Room.organization_id,
                    Program.id == Room.program_id,
                    Program.facility_id == Room.facility_id,
                ),
            )
            .where(
                Room.organization_id == organization_id,
                Room.facility_id == facility_id,
                Room.is_active.is_(True),
                Program.is_active.is_(True),
                Program.program_type.in_(PROGRAM_TYPES),
            )
            .order_by(Program.program_type, Program.name, Room.name, Room.id)
        )
    )
    candidates: list[RoomPlacementCandidateResponse] = []
    program_occupancy: dict[UUID, int] = {}
    for room, program in rows:
        if not _age_compatible(age_months, room):
            continue
        occupancy = _occupancy(
            session,
            organization_id,
            room.id,
            effective_date,
        )
        if program.id not in program_occupancy:
            program_occupancy[program.id] = _program_occupancy(
                session,
                organization_id,
                program.id,
                effective_date,
            )
        available_places = min(
            max(room.capacity - occupancy, 0),
            max(program.capacity - program_occupancy[program.id], 0),
        )
        candidates.append(
            RoomPlacementCandidateResponse(
                room_id=room.id,
                room_name=room.name,
                room_age_group=room.age_group,
                minimum_age_months=room.minimum_age_months,
                maximum_age_months=room.maximum_age_months,
                capacity=room.capacity,
                occupancy=occupancy,
                available_places=available_places,
                program_id=program.id,
                program_name=program.name,
                program_type=program.program_type,
            )
        )
    return candidates


def _suggestion_state(candidates: list[RoomPlacementCandidateResponse]) -> str:
    available = [candidate for candidate in candidates if candidate.available_places > 0]
    if not available:
        return "none"
    narrowest_span = min(
        candidate.maximum_age_months - candidate.minimum_age_months for candidate in available
    )
    preferred = sum(
        candidate.maximum_age_months - candidate.minimum_age_months == narrowest_span
        for candidate in available
    )
    return "one" if preferred == 1 else "multiple"


def _require_child_not_currently_on_site(
    session: SessionDependency,
    organization_id: UUID,
    child_id: UUID,
) -> None:
    """Refuse a placement change while an attendance interval is still open.

    The caller already holds the child row lock. Attendance check-in uses the
    same child-first lock, so a concurrent check-in cannot appear after this
    predicate has been checked. Checkout may only make this decision more
    conservative by closing an interval while the approval is in progress.
    Historical/closed intervals are deliberately ignored.
    """

    rows = list(
        session.execute(
            select(
                AttendanceDay.id,
                AttendanceDay.facility_id,
                AttendanceDay.room_id,
                AttendanceInterval.id,
            )
            .join(
                AttendanceInterval,
                and_(
                    AttendanceInterval.organization_id == AttendanceDay.organization_id,
                    AttendanceInterval.attendance_day_id == AttendanceDay.id,
                ),
            )
            .where(
                AttendanceDay.organization_id == organization_id,
                AttendanceDay.child_id == child_id,
                AttendanceInterval.checked_out_at.is_(None),
            )
            .order_by(AttendanceDay.id, AttendanceInterval.id)
            .limit(2)
        )
    )
    if not rows:
        return
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "child_attendance_source_integrity_unknown",
                "child_id": str(child_id),
                "message": (
                    "More than one open attendance interval exists for this child. "
                    "Resolve attendance integrity before changing placement."
                ),
            },
        )
    attendance_day_id, facility_id, room_id, attendance_interval_id = rows[0]
    raise HTTPException(
        status_code=409,
        detail={
            "code": "child_currently_on_site",
            "child_id": str(child_id),
            "attendance_day_id": str(attendance_day_id),
            "attendance_interval_id": str(attendance_interval_id),
            "facility_id": str(facility_id),
            "room_id": str(room_id) if room_id is not None else None,
            "message": (
                "Check the child out before approving a room placement. "
                "Current attendance remains bound to its recorded room."
            ),
        },
    )


def _enrollment_response(
    session: SessionDependency,
    enrollment: Enrollment,
    *,
    facility: Facility | None = None,
    replayed: bool = False,
) -> EnrollmentResponse:
    if facility is None:
        facility = session.scalar(
            select(Facility).where(
                Facility.id == enrollment.facility_id,
                Facility.organization_id == enrollment.organization_id,
            )
        )
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    program = (
        session.scalar(
            select(Program).where(
                Program.id == enrollment.program_id,
                Program.organization_id == enrollment.organization_id,
                Program.facility_id == enrollment.facility_id,
            )
        )
        if enrollment.program_id is not None
        else None
    )
    room = (
        session.scalar(
            select(Room).where(
                Room.id == enrollment.room_id,
                Room.organization_id == enrollment.organization_id,
                Room.facility_id == enrollment.facility_id,
            )
        )
        if enrollment.room_id is not None
        else None
    )
    facility_date = _facility_today(facility)
    return EnrollmentResponse(
        **{
            column.name: getattr(enrollment, column.name) for column in Enrollment.__table__.columns
        },
        is_active=enrollment.is_current_on(facility_date),
        replayed=replayed,
        facility_name=facility.name,
        program_name=program.name if program is not None else None,
        program_type=program.program_type if program is not None else None,
        room_name=room.name if room is not None else None,
    )


def _lock_batch_resources(
    session: SessionDependency,
    organization_id: UUID,
    payload: RoomPlacementBatchRequest,
) -> _PlacementLockSet:
    enrollment_ids = sorted(
        {item.enrollment_id for item in payload.placements},
        key=str,
    )
    snapshots = {
        enrollment.id: enrollment
        for enrollment in session.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == organization_id,
                Enrollment.id.in_(enrollment_ids),
            )
        )
    }
    if set(snapshots) != set(enrollment_ids):
        raise HTTPException(status_code=404, detail="Enrollment not found")

    child_ids = sorted({row.child_id for row in snapshots.values()}, key=str)
    child_snapshots = {
        row.id: row
        for row in session.scalars(
            select(Child).where(
                Child.organization_id == organization_id,
                Child.id.in_(child_ids),
            )
        )
    }
    if set(child_snapshots) != set(child_ids):
        raise HTTPException(status_code=404, detail="Enrollment not found")
    family_ids = sorted({row.family_id for row in child_snapshots.values()}, key=str)
    facility_ids = sorted({row.facility_id for row in snapshots.values()}, key=str)
    room_ids = sorted({item.room_id for item in payload.placements}, key=str)

    # Acquire the complete batch lock set by resource class and stable UUID.
    # No item mutates until every family/child/facility/enrollment/room is held.
    families = {
        row.id: row
        for row in session.scalars(
            select(Family)
            .where(
                Family.organization_id == organization_id,
                Family.id.in_(family_ids),
            )
            .order_by(Family.id)
            .with_for_update()
        )
    }
    if set(families) != set(family_ids):
        raise HTTPException(status_code=404, detail="Family not found")
    children = {
        row.id: row
        for row in session.scalars(
            select(Child)
            .where(
                Child.organization_id == organization_id,
                Child.id.in_(child_ids),
            )
            .order_by(Child.id)
            .with_for_update()
        )
    }
    if set(children) != set(child_ids) or any(
        children[child_id].family_id != child_snapshots[child_id].family_id
        for child_id in child_ids
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "child_family_changed"},
        )
    facilities = {
        row.id: row
        for row in session.scalars(
            select(Facility)
            .where(
                Facility.organization_id == organization_id,
                Facility.id.in_(facility_ids),
            )
            .order_by(Facility.id)
            .with_for_update()
        )
    }
    enrollments = {
        row.id: row
        for row in session.scalars(
            select(Enrollment)
            .where(
                Enrollment.organization_id == organization_id,
                Enrollment.id.in_(enrollment_ids),
            )
            .order_by(Enrollment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    rooms = {
        row.id: row
        for row in session.scalars(
            select(Room)
            .where(
                Room.organization_id == organization_id,
                Room.id.in_(room_ids),
            )
            .order_by(Room.id)
            .with_for_update()
        )
    }
    program_ids = sorted(
        {room.program_id for room in rooms.values() if room.program_id is not None},
        key=str,
    )
    programs = {
        row.id: row
        for row in session.scalars(
            select(Program)
            .where(
                Program.organization_id == organization_id,
                Program.id.in_(program_ids),
            )
            .order_by(Program.id)
            .with_for_update()
        )
    }
    return _PlacementLockSet(
        families=families,
        children=children,
        facilities=facilities,
        enrollments=enrollments,
        rooms=rooms,
        programs=programs,
    )


@router.get(
    "/room-placement-reviews",
    response_model=list[RoomPlacementReviewResponse],
)
def list_room_placement_reviews(
    facility_id: UUID,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> list[RoomPlacementReviewResponse]:
    facility = session.scalar(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.organization_id == context.organization.id,
        )
    )
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.status != "active":
        raise HTTPException(status_code=422, detail="Room placement requires an active facility")
    today = _facility_today(facility)
    rows = list(
        session.execute(
            select(Enrollment, Child)
            .join(
                Child,
                and_(
                    Child.organization_id == Enrollment.organization_id,
                    Child.id == Enrollment.child_id,
                ),
            )
            .join(
                Family,
                and_(
                    Family.organization_id == Child.organization_id,
                    Family.id == Child.family_id,
                ),
            )
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.facility_id == facility.id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
                Enrollment.room_id.is_(None),
                or_(Enrollment.end_date.is_(None), Enrollment.end_date >= today),
                Child.is_active.is_(True),
                Family.status == "active",
            )
            .order_by(Child.last_name, Child.first_name, Enrollment.start_date, Enrollment.id)
        )
    )
    reviews: list[RoomPlacementReviewResponse] = []
    for enrollment, child in rows:
        effective_date = _effective_date(enrollment, facility)
        age_months = full_calendar_months(child.date_of_birth, effective_date)
        candidates = _candidate_rows(
            session,
            context.organization.id,
            facility.id,
            age_months,
            effective_date,
        )
        reviews.append(
            RoomPlacementReviewResponse(
                organization_id=context.organization.id,
                facility_id=facility.id,
                enrollment_id=enrollment.id,
                enrollment_version=enrollment.version,
                child_id=child.id,
                child_first_name=child.first_name,
                child_middle_name=child.middle_name,
                child_last_name=child.last_name,
                date_of_birth=child.date_of_birth,
                enrollment_start_date=enrollment.start_date,
                effective_date=effective_date,
                age_months=age_months,
                suggestion_state=_suggestion_state(candidates),
                candidates=candidates,
            )
        )
    return reviews


def _approve_room_placement(
    enrollment_id: UUID,
    payload: RoomPlacementApprovalRequest,
    context: ChildcareManageContext,
    session: SessionDependency,
    *,
    locks: _PlacementLockSet | None = None,
) -> EnrollmentResponse:
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.placement.approve",
        target_type="enrollment",
        target_scope=enrollment_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        enrollment = session.scalar(
            select(Enrollment).where(
                Enrollment.id == receipt.target_id,
                Enrollment.organization_id == context.organization.id,
            )
        )
        if enrollment is None:
            raise HTTPException(404, detail="Enrollment not found")
        child = session.scalar(
            select(Child).where(
                Child.id == enrollment.child_id,
                Child.organization_id == context.organization.id,
            )
        )
        if child is None or enrollment.program_id is None or enrollment.room_id is None:
            raise HTTPException(409, detail={"code": "operation_receipt_incomplete"})
        facility = session.scalar(
            select(Facility).where(
                Facility.id == enrollment.facility_id,
                Facility.organization_id == context.organization.id,
            )
        )
        return _enrollment_response(
            session,
            enrollment,
            facility=facility,
            replayed=True,
        )
    enrollment_snapshot = (
        locks.enrollments.get(enrollment_id)
        if locks is not None
        else session.scalar(
            select(Enrollment).where(
                Enrollment.id == enrollment_id,
                Enrollment.organization_id == context.organization.id,
            )
        )
    )
    if enrollment_snapshot is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Family lifecycle and child placement share one deterministic lock order:
    # Family -> Child -> Facility -> Enrollment -> Room.
    if locks is None:
        child_snapshot = session.scalar(
            select(Child).where(
                Child.id == enrollment_snapshot.child_id,
                Child.organization_id == context.organization.id,
            )
        )
        if child_snapshot is None:
            raise HTTPException(status_code=404, detail="Enrollment not found")
        expected_family_id = child_snapshot.family_id
        family = session.scalar(
            select(Family)
            .where(
                Family.id == expected_family_id,
                Family.organization_id == context.organization.id,
            )
            .with_for_update()
        )
        child = session.scalar(
            select(Child)
            .where(
                Child.id == enrollment_snapshot.child_id,
                Child.organization_id == context.organization.id,
            )
            .with_for_update()
        )
        facility = session.scalar(
            select(Facility)
            .where(
                Facility.id == enrollment_snapshot.facility_id,
                Facility.organization_id == context.organization.id,
            )
            .with_for_update()
        )
        enrollment = session.scalar(
            select(Enrollment)
            .where(
                Enrollment.id == enrollment_id,
                Enrollment.organization_id == context.organization.id,
            )
            .with_for_update()
        )
    else:
        child = locks.children.get(enrollment_snapshot.child_id)
        family = locks.families.get(child.family_id) if child is not None else None
        facility = locks.facilities.get(enrollment_snapshot.facility_id)
        enrollment = locks.enrollments.get(enrollment_id)
    if child is None or enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")
    if locks is None and child.family_id != expected_family_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "child_family_changed", "child_id": str(child.id)},
        )
    if enrollment.child_id != child.id:
        raise HTTPException(status_code=409, detail={"code": "enrollment_child_changed"})
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    require_version(enrollment, payload.expected_version, "enrollment")
    _require_child_not_currently_on_site(
        session,
        context.organization.id,
        child.id,
    )
    if (
        family.status != "active"
        or not child.is_active
        or enrollment.status not in OPEN_ENROLLMENT_STATUSES
    ):
        raise HTTPException(
            status_code=409,
            detail="Enrollment is no longer eligible for placement",
        )
    if (
        enrollment.program_id is not None
        or enrollment.room_id is not None
        or enrollment.placement_effective_date is not None
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "enrollment_placement_already_resolved"},
        )
    if facility.status != "active":
        raise HTTPException(status_code=409, detail="Facility is no longer active")

    effective_date = _effective_date(enrollment, facility)
    if payload.effective_date != effective_date:
        raise HTTPException(
            status_code=409,
            detail="Placement review is stale; refresh the recommendations before approval",
        )
    if enrollment.end_date is not None and enrollment.end_date < effective_date:
        raise HTTPException(status_code=409, detail="Enrollment ended before the placement date")
    age_months = full_calendar_months(child.date_of_birth, effective_date)

    room = (
        locks.rooms.get(payload.room_id)
        if locks is not None
        else session.scalar(
            select(Room)
            .where(
                Room.id == payload.room_id,
                Room.organization_id == context.organization.id,
                Room.facility_id == facility.id,
            )
            .with_for_update()
        )
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.facility_id != facility.id:
        raise HTTPException(status_code=404, detail="Room not found")
    program = (
        locks.programs.get(room.program_id)
        if locks is not None and room.program_id is not None
        else session.scalar(
            select(Program)
            .where(
                Program.id == room.program_id,
                Program.organization_id == context.organization.id,
                Program.facility_id == facility.id,
            )
            .with_for_update()
        )
    )
    if (
        program is None
        or not room.is_active
        or not program.is_active
        or program.program_type not in PROGRAM_TYPES
        or not _age_compatible(age_months, room)
    ):
        raise HTTPException(
            status_code=409,
            detail="Selected room is no longer eligible for this child on the placement date",
        )
    occupancy = _occupancy(
        session,
        context.organization.id,
        room.id,
        effective_date,
        exclude_enrollment_id=enrollment.id,
    )
    if occupancy >= room.capacity:
        raise HTTPException(
            status_code=409,
            detail="Selected room no longer has an available place; refresh and choose again",
        )
    program_occupancy = _program_occupancy(
        session,
        context.organization.id,
        program.id,
        effective_date,
        exclude_enrollment_id=enrollment.id,
    )
    if program_occupancy >= program.capacity:
        raise HTTPException(
            status_code=409,
            detail=("Selected program no longer has licensed capacity; refresh and choose again"),
        )

    enrollment.program_id = program.id
    enrollment.room_id = room.id
    enrollment.placement_effective_date = effective_date
    enrollment.status = "active"
    enrollment.version += 1
    # The session factory disables autoflush. Flush inside the still-uncommitted
    # transaction so later items in a batch see this room's staged occupancy.
    session.flush()
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.placement.approve",
        target_type="enrollment",
        target_id=enrollment.id,
        request_hash=request_hash,
        committed_version=enrollment.version,
        facility_id=facility.id,
        outcome={"action_route": f"/children/{child.id}?enrollment_id={enrollment.id}"},
    )
    # Each batch item installs a different operation identity in the PostgreSQL
    # session. Persist this receipt while its matching identity is still active;
    # otherwise a later item could cause the runtime trigger to reject the
    # deferred INSERT as belonging to the wrong operation.
    session.flush()
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="enrollment.room_placement.approved",
        entity_type="enrollment",
        entity_id=enrollment.id,
        facility_id=facility.id,
        details={
            "program_id": str(program.id),
            "room_id": str(room.id),
            "effective_date": effective_date.isoformat(),
            "age_months": age_months,
            "basis": "configured_room_age_range",
            "operation_id": str(payload.client_operation_id),
        },
    )
    return _enrollment_response(session, enrollment, facility=facility)


@router.post(
    "/enrollments/{enrollment_id}/placement-approval",
    response_model=EnrollmentResponse,
)
def approve_room_placement(
    enrollment_id: UUID,
    payload: RoomPlacementApprovalRequest,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> EnrollmentResponse:
    ensure_writable(request)
    result = _approve_room_placement(
        enrollment_id,
        payload,
        context,
        session,
    )
    commit_in_context(session, context, "Room placement changed while approval was saved")
    return result


@router.post(
    "/room-placement-approvals/batch",
    response_model=RoomPlacementBatchResponse,
)
def approve_room_placements_batch(
    payload: RoomPlacementBatchRequest,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> RoomPlacementBatchResponse:
    ensure_writable(request)
    enrollment_ids = [item.enrollment_id for item in payload.placements]
    if len(set(enrollment_ids)) != len(enrollment_ids):
        raise HTTPException(status_code=422, detail="Each enrollment may appear only once")
    operation_ids = [item.client_operation_id for item in payload.placements]
    if len(set(operation_ids)) != len(operation_ids):
        raise HTTPException(status_code=422, detail="Each placement needs a unique operation ID")
    # Single approvals acquire their operation lock before resource locks. Do
    # the same for the whole batch so an exact single retry cannot deadlock a
    # batch that contains it.
    for operation_id in sorted(operation_ids, key=str):
        lock_client_operation(session, context.organization.id, operation_id)
    locks = _lock_batch_resources(session, context.organization.id, payload)
    approvals_by_enrollment = {}
    for item in sorted(payload.placements, key=lambda value: str(value.enrollment_id)):
        approvals_by_enrollment[item.enrollment_id] = _approve_room_placement(
            item.enrollment_id,
            item,
            context,
            session,
            locks=locks,
        )
    approvals = [approvals_by_enrollment[item.enrollment_id] for item in payload.placements]
    commit_in_context(session, context, "Room placement batch changed while approval was saved")
    return RoomPlacementBatchResponse(approvals=approvals)
