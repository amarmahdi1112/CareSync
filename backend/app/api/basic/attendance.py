"""Actual Basic attendance records, independent from synthetic scheduler output."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, or_, select

from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    AttendanceCorrectContext,
    AttendanceReadContext,
    AttendanceRecordContext,
    BasicContext,
    refresh_basic_context,
)
from app.api.dependencies import SessionDependency
from app.basic.daily_care import auto_finish_open_sleep
from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    Child,
    ChildProfilePhoto,
    DailyCareRecord,
    Enrollment,
    Facility,
    IncidentRecord,
    MedicationAdministration,
    Program,
    Room,
)
from app.basic.release_checkout_capability import (
    facility_requires_verified_release_checkout,
)
from app.basic.room_safety import (
    foundation_enabled as room_safety_enabled,
)
from app.basic.room_safety import (
    lock_facility_projection,
    reconcile_facility_exceptions,
)
from app.basic.schemas import (
    AbsenceRequest,
    AttendanceDayResponse,
    AttendanceEventResponse,
    AttendanceIntervalResponse,
    AttendanceRosterItem,
    AttendanceStatusCorrectionRequest,
    CheckInRequest,
    CheckOutRequest,
    CorrectionRequest,
)
from app.basic.security import audit
from app.basic.shift_guards import require_open_shift

router = APIRouter(prefix="/attendance", tags=["basic attendance"])


def _refresh_attendance_context(
    session: SessionDependency,
    context: BasicContext,
    *,
    facility_id: UUID,
    permission: str,
    room_id: UUID | None = None,
    conceal_detail: str = "Attendance resource not found",
) -> BasicContext:
    current = refresh_basic_context(
        session,
        context,
        required_all_permissions=(permission,),
        conceal_detail=conceal_detail,
    )
    if not current.organization_wide and (
        facility_id not in current.assigned_facility_ids
        or (
            room_id is not None
            and room_id not in current.assigned_room_ids
        )
    ):
        raise HTTPException(404, conceal_detail)
    return current


def _aware(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC)


def _reject_future_attendance_time(value: datetime) -> None:
    if value > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(
            status_code=422,
            detail="Attendance time cannot be more than five minutes in the future",
        )


def _facility(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    *,
    active_only: bool = False,
    allow_inactive: bool = False,
    lock: bool = False,
) -> Facility:
    statement = select(Facility).where(
        Facility.id == facility_id,
        Facility.organization_id == organization_id,
    )
    if active_only:
        statement = statement.where(Facility.status == "active")
    elif not allow_inactive:
        statement = statement.where(Facility.status != "inactive")
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    return value


def _service_date(facility: Facility, occurred_at: datetime) -> date:
    try:
        timezone = ZoneInfo(facility.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=409, detail="Facility timezone is invalid") from None
    return occurred_at.astimezone(timezone).date()


def _ensure_service_date(
    facility: Facility,
    attendance_day: AttendanceDay,
    *instants: datetime,
) -> None:
    if any(_service_date(facility, instant) != attendance_day.service_date for instant in instants):
        raise HTTPException(
            status_code=422,
            detail="Attendance interval times must remain on the attendance service date",
        )


def _active_enrollment(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    child_id: UUID,
    service_date: date,
    *,
    lock: bool = False,
    child_locked: bool = False,
) -> Enrollment:
    if not child_locked:
        child_statement = select(Child.id).where(
            Child.id == child_id,
            Child.organization_id == organization_id,
            Child.is_active.is_(True),
        )
        if lock:
            child_statement = child_statement.with_for_update()
        child = session.scalar(child_statement)
        if child is None:
            raise HTTPException(status_code=404, detail="Child not found")
    statement = (
        select(Enrollment)
        .join(
            Room,
            and_(
                Room.organization_id == Enrollment.organization_id,
                Room.facility_id == Enrollment.facility_id,
                Room.id == Enrollment.room_id,
            ),
        )
        .join(
            Program,
            and_(
                Program.organization_id == Enrollment.organization_id,
                Program.facility_id == Enrollment.facility_id,
                Program.id == Enrollment.program_id,
            ),
        )
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.facility_id == facility_id,
            Enrollment.child_id == child_id,
            Enrollment.status == "active",
            Enrollment.start_date <= service_date,
            Enrollment.placement_effective_date <= service_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= service_date),
            Room.is_active.is_(True),
            Program.is_active.is_(True),
        )
        .order_by(Enrollment.start_date.desc())
    )
    if lock:
        statement = statement.with_for_update(of=Enrollment)
    enrollment = session.scalar(statement)
    if enrollment is None:
        raise HTTPException(
            status_code=409,
            detail="Child has no active enrollment at this facility on the service date",
        )
    return enrollment


def _lock_active_child(
    session: SessionDependency,
    organization_id: UUID,
    child_id: UUID,
) -> Child:
    child = session.scalar(
        select(Child)
        .where(
            Child.id == child_id,
            Child.organization_id == organization_id,
            Child.is_active.is_(True),
        )
        .with_for_update()
    )
    if child is None:
        raise HTTPException(status_code=404, detail="Child not found")
    return child


def _lock_enrollment_room(
    session: SessionDependency,
    organization_id: UUID,
    enrollment: Enrollment,
) -> None:
    room_id = session.scalar(
        select(Room.id)
        .where(
            Room.organization_id == organization_id,
            Room.facility_id == enrollment.facility_id,
            Room.id == enrollment.room_id,
        )
        .with_for_update()
    )
    if room_id is None:
        raise HTTPException(
            status_code=409,
            detail="Child enrollment room is no longer available",
        )


def _day(
    session: SessionDependency,
    organization_id: UUID,
    attendance_day_id: UUID,
    *,
    lock: bool = False,
) -> AttendanceDay:
    statement = select(AttendanceDay).where(
        AttendanceDay.id == attendance_day_id,
        AttendanceDay.organization_id == organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    return value


def _day_response(
    session: SessionDependency,
    day: AttendanceDay,
    *,
    include_events: bool = True,
) -> AttendanceDayResponse:
    child = session.scalar(
        select(Child).where(
            Child.organization_id == day.organization_id,
            Child.id == day.child_id,
        )
    )
    if child is None:
        raise HTTPException(status_code=409, detail="Attendance child record is unavailable")
    intervals = list(
        session.scalars(
            select(AttendanceInterval)
            .where(
                AttendanceInterval.organization_id == day.organization_id,
                AttendanceInterval.attendance_day_id == day.id,
            )
            .order_by(AttendanceInterval.sequence)
        )
    )
    events = []
    if include_events:
        events = list(
            session.scalars(
                select(AttendanceEvent)
                .where(
                    AttendanceEvent.organization_id == day.organization_id,
                    AttendanceEvent.attendance_day_id == day.id,
                )
                .order_by(AttendanceEvent.occurred_at, AttendanceEvent.id)
            )
        )
    return AttendanceDayResponse(
        id=day.id,
        organization_id=day.organization_id,
        facility_id=day.facility_id,
        child_id=day.child_id,
        enrollment_id=day.enrollment_id,
        room_id=day.room_id,
        service_date=day.service_date,
        status=day.status,
        absence_reason=day.absence_reason,
        notes=day.notes,
        version=day.version,
        child_name=f"{child.first_name} {child.last_name}".strip(),
        intervals=[AttendanceIntervalResponse.model_validate(item) for item in intervals],
        events=[AttendanceEventResponse.model_validate(item) for item in events],
        created_at=day.created_at,
        updated_at=day.updated_at,
    )


def _operation_replay(
    session: SessionDependency,
    context: AttendanceRecordContext,
    request: Request,
    operation_id: UUID,
    *,
    event_type: str,
    child_id: UUID,
    facility_id: UUID,
    occurred_at: datetime,
) -> AttendanceDayResponse | None:
    event = session.scalar(
        select(AttendanceEvent).where(
            AttendanceEvent.organization_id == context.organization.id,
            AttendanceEvent.client_operation_id == operation_id,
        )
    )
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(404, "Attendance operation not found")
    preliminary_day = _day(
        session, context.organization.id, event.attendance_day_id
    )
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, preliminary_day.facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=preliminary_day.facility_id,
            permission="attendance:record",
            room_id=preliminary_day.room_id,
            conceal_detail="Attendance operation not found",
        )
    event = session.scalar(
        select(AttendanceEvent).where(
            AttendanceEvent.organization_id == context.organization.id,
            AttendanceEvent.client_operation_id == operation_id,
            AttendanceEvent.actor_user_id == context.user.id,
        )
    )
    if event is None:
        raise HTTPException(404, "Attendance operation not found")
    day = _day(session, context.organization.id, event.attendance_day_id)
    if (
        not context.organization_wide
        and day.room_id not in context.assigned_room_ids
    ):
        raise HTTPException(404, "Attendance operation not found")
    if (
        event.event_type != event_type
        or day.child_id != child_id
        or day.facility_id != facility_id
        or _aware(event.occurred_at) != occurred_at
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Client operation identifier was used for another "
                "attendance action"
            ),
        )
    return _day_response(session, day)


def _facility_requires_verified_release_checkout(
    request: Request,
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
) -> bool:
    """Resolve activation without direct PostgreSQL access to the C source."""

    return facility_requires_verified_release_checkout(
        session,
        organization_id=organization_id,
        facility_id=facility_id,
        foundation_present=bool(
            getattr(
                request.app.state,
                "family_release_checkout_foundation_present",
                False,
            )
        ),
        runtime_enabled=bool(
            getattr(request.app.state, "family_release_checkout_enabled", False)
        ),
    )


def _interval_has_release_snapshot(
    session: SessionDependency,
    organization_id: UUID,
    interval_id: UUID,
) -> bool:
    return (
        session.scalar(
            select(AttendanceReleaseSnapshot.id).where(
                AttendanceReleaseSnapshot.organization_id == organization_id,
                AttendanceReleaseSnapshot.attendance_interval_id == interval_id,
            )
        )
        is not None
    )


def _care_records_for_day(
    session: SessionDependency,
    day: AttendanceDay,
    *,
    lock: bool = False,
) -> list[DailyCareRecord]:
    statement = select(DailyCareRecord).where(
        DailyCareRecord.organization_id == day.organization_id,
        DailyCareRecord.attendance_day_id == day.id,
        DailyCareRecord.voided_at.is_(None),
    )
    if lock:
        statement = statement.order_by(DailyCareRecord.id).with_for_update()
    return list(session.scalars(statement))


def _medication_records_for_day(
    session: SessionDependency,
    day: AttendanceDay,
    *,
    lock: bool = False,
) -> list[MedicationAdministration]:
    statement = select(MedicationAdministration).where(
        MedicationAdministration.organization_id == day.organization_id,
        MedicationAdministration.attendance_day_id == day.id,
        MedicationAdministration.voided_at.is_(None),
    )
    if lock:
        statement = statement.order_by(MedicationAdministration.id).with_for_update()
    return list(session.scalars(statement))


def _incident_records_for_day(
    session: SessionDependency,
    day: AttendanceDay,
    *,
    lock: bool = False,
) -> list[IncidentRecord]:
    statement = select(IncidentRecord).where(
        IncidentRecord.organization_id == day.organization_id,
        IncidentRecord.attendance_day_id == day.id,
    )
    if lock:
        statement = statement.order_by(IncidentRecord.id).with_for_update()
    return list(session.scalars(statement))


def _intervals_for_day(
    session: SessionDependency,
    day: AttendanceDay,
    *,
    lock: bool = False,
) -> list[AttendanceInterval]:
    statement = (
        select(AttendanceInterval)
        .where(
            AttendanceInterval.organization_id == day.organization_id,
            AttendanceInterval.attendance_day_id == day.id,
        )
        .order_by(AttendanceInterval.sequence, AttendanceInterval.id)
    )
    if lock:
        statement = statement.with_for_update()
    return list(session.scalars(statement))


def _ensure_checkout_preserves_care(
    records: list[DailyCareRecord],
    checked_out_at: datetime,
) -> None:
    checkout = _aware(checked_out_at)
    for record in records:
        if _aware(record.occurred_at) > checkout or (
            record.ended_at is not None and _aware(record.ended_at) > checkout
        ):
            raise HTTPException(
                status_code=409,
                detail="Check-out would place an existing care record outside attendance",
            )


def _ensure_checkout_preserves_regulated_records(
    medication_records: list[MedicationAdministration],
    incident_records: list[IncidentRecord],
    checked_out_at: datetime,
) -> None:
    checkout = _aware(checked_out_at)
    if any(_aware(record.occurred_at) > checkout for record in medication_records):
        raise HTTPException(
            status_code=409,
            detail="Check-out would place an existing medication record outside attendance",
        )
    if any(_aware(record.occurred_at) > checkout for record in incident_records):
        raise HTTPException(
            status_code=409,
            detail="Check-out would place an existing child incident outside attendance",
        )


def _ensure_care_survives_interval_correction(
    intervals: list[AttendanceInterval],
    records: list[DailyCareRecord],
    corrected_interval_id: UUID,
    checked_in_at: datetime,
    checked_out_at: datetime | None,
) -> None:
    proposed: list[tuple[datetime, datetime | None]] = []
    for interval in intervals:
        if interval.id == corrected_interval_id:
            proposed.append(
                (
                    _aware(checked_in_at),
                    _aware(checked_out_at) if checked_out_at else None,
                )
            )
        else:
            proposed.append(
                (
                    _aware(interval.checked_in_at),
                    _aware(interval.checked_out_at) if interval.checked_out_at else None,
                )
            )
    for record in records:
        care_start = _aware(record.occurred_at)
        care_end = _aware(record.ended_at) if record.ended_at else None
        fits = False
        for interval_start, interval_end in proposed:
            if care_start < interval_start or (
                interval_end is not None and care_start > interval_end
            ):
                continue
            if care_end is not None and interval_end is not None and care_end > interval_end:
                continue
            if record.care_type == "sleep" and care_end is None and interval_end is not None:
                continue
            fits = True
            break
        if not fits:
            raise HTTPException(
                status_code=409,
                detail="Attendance correction would strand an existing care record",
            )


def _ensure_regulated_records_survive_interval_correction(
    intervals: list[AttendanceInterval],
    medication_records: list[MedicationAdministration],
    incident_records: list[IncidentRecord],
    corrected_interval_id: UUID,
    checked_in_at: datetime,
    checked_out_at: datetime | None,
) -> None:
    proposed = [
        (
            (
                _aware(checked_in_at)
                if item.id == corrected_interval_id
                else _aware(item.checked_in_at)
            ),
            (_aware(checked_out_at) if checked_out_at else None)
            if item.id == corrected_interval_id
            else (_aware(item.checked_out_at) if item.checked_out_at else None),
        )
        for item in intervals
    ]
    for record_type, records in (
        ("medication record", medication_records),
        ("child incident", incident_records),
    ):
        for record in records:
            occurred_at = _aware(record.occurred_at)
            if not any(
                occurred_at >= start and (end is None or occurred_at <= end)
                for start, end in proposed
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Attendance correction would strand an existing {record_type}",
                )


@router.get("", response_model=list[AttendanceDayResponse])
def list_attendance(
    context: AttendanceReadContext,
    session: SessionDependency,
    attendance_date: Annotated[date, Query(alias="date")],
    facility_id: Annotated[UUID, Query()],
) -> list[AttendanceDayResponse]:
    _facility(session, context.organization.id, facility_id)
    statement = select(AttendanceDay).where(
        AttendanceDay.organization_id == context.organization.id,
        AttendanceDay.facility_id == facility_id,
        AttendanceDay.service_date == attendance_date,
    )
    if not context.organization_wide:
        if facility_id not in context.assigned_facility_ids:
            raise HTTPException(status_code=404, detail="Facility not found")
        statement = statement.where(AttendanceDay.room_id.in_(context.assigned_room_ids))
    values = list(session.scalars(statement.order_by(AttendanceDay.created_at)))
    return [_day_response(session, item) for item in values]


@router.get("/roster", response_model=list[AttendanceRosterItem])
def attendance_roster(
    context: AttendanceReadContext,
    session: SessionDependency,
    attendance_date: Annotated[date, Query(alias="date")],
    facility_id: Annotated[UUID, Query()],
) -> list[AttendanceRosterItem]:
    _facility(session, context.organization.id, facility_id)
    if not context.organization_wide and facility_id not in context.assigned_facility_ids:
        raise HTTPException(status_code=404, detail="Facility not found")
    statement = (
        select(Enrollment, Child, Room.name, Program.name, ChildProfilePhoto.child_id)
        .join(
            Child,
            and_(
                Child.organization_id == Enrollment.organization_id,
                Child.id == Enrollment.child_id,
            ),
        )
        .join(
            Room,
            and_(
                Room.organization_id == Enrollment.organization_id,
                Room.id == Enrollment.room_id,
            ),
        )
        .join(
            Program,
            and_(
                Program.organization_id == Enrollment.organization_id,
                Program.id == Enrollment.program_id,
            ),
        )
        .outerjoin(
            ChildProfilePhoto,
            and_(
                ChildProfilePhoto.organization_id == Child.organization_id,
                ChildProfilePhoto.child_id == Child.id,
            ),
        )
        .where(
            Enrollment.organization_id == context.organization.id,
            Enrollment.facility_id == facility_id,
            Enrollment.status == "active",
            Enrollment.start_date <= attendance_date,
            Enrollment.placement_effective_date <= attendance_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= attendance_date),
            Child.is_active.is_(True),
            Room.is_active.is_(True),
            Program.is_active.is_(True),
        )
        .order_by(Child.last_name, Child.first_name)
    )
    if not context.organization_wide:
        statement = statement.where(Enrollment.room_id.in_(context.assigned_room_ids))
    rows = list(session.execute(statement))
    days_statement = select(AttendanceDay).where(
        AttendanceDay.organization_id == context.organization.id,
        AttendanceDay.facility_id == facility_id,
        AttendanceDay.service_date == attendance_date,
    )
    if not context.organization_wide:
        days_statement = days_statement.where(AttendanceDay.room_id.in_(context.assigned_room_ids))
    days = {value.child_id: value for value in session.scalars(days_statement)}
    return [
        AttendanceRosterItem(
            child_id=child.id,
            child_name=f"{child.first_name} {child.last_name}".strip(),
            profile_photo_url=(
                f"/api/v1/children/{child.id}/photo" if photo_child_id is not None else None
            ),
            enrollment_id=enrollment.id,
            room_id=enrollment.room_id,
            room_name=room_name,
            program_name=program_name,
            attendance_day=(_day_response(session, days[child.id]) if child.id in days else None),
        )
        for enrollment, child, room_name, program_name, photo_child_id in rows
    ]


@router.get("/{attendance_day_id}", response_model=AttendanceDayResponse)
def get_attendance_day(
    attendance_day_id: UUID,
    context: AttendanceReadContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    day = _day(session, context.organization.id, attendance_day_id)
    if not context.organization_wide and day.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    return _day_response(session, day)


@router.post("/check-in", response_model=AttendanceDayResponse)
def check_in(
    payload: CheckInRequest,
    request: Request,
    context: AttendanceRecordContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    ensure_writable(request)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    occurred_at = _aware(payload.occurred_at)
    _reject_future_attendance_time(occurred_at)
    replay = _operation_replay(
        session,
        context,
        request,
        payload.client_operation_id,
        event_type="check_in",
        child_id=payload.child_id,
        facility_id=payload.facility_id,
        occurred_at=occurred_at,
    )
    if replay is not None:
        return replay
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, payload.facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=payload.facility_id,
            permission="attendance:record",
            conceal_detail="Child enrollment not found",
        )
    # Shared mutation order inside the facility projection lane:
    # Child -> Facility -> Enrollment -> Room.
    _lock_active_child(session, context.organization.id, payload.child_id)
    facility = _facility(
        session,
        context.organization.id,
        payload.facility_id,
        active_only=True,
        lock=True,
    )
    service_date = _service_date(facility, occurred_at)
    enrollment = _active_enrollment(
        session,
        context.organization.id,
        facility.id,
        payload.child_id,
        service_date,
        lock=True,
        child_locked=True,
    )
    _lock_enrollment_room(session, context.organization.id, enrollment)
    if not context.organization_wide and enrollment.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Child enrollment not found")
    require_open_shift(
        session,
        context,
        facility.id,
        enrollment.room_id,
        enforce_room_presence=live_room_safety,
    )
    open_day_id = session.scalar(
        select(AttendanceDay.id)
        .join(
            AttendanceInterval,
            and_(
                AttendanceDay.organization_id == AttendanceInterval.organization_id,
                AttendanceDay.id == AttendanceInterval.attendance_day_id,
            ),
        )
        .where(
            AttendanceInterval.organization_id == context.organization.id,
            AttendanceDay.child_id == payload.child_id,
            AttendanceInterval.checked_out_at.is_(None),
        )
    )
    if open_day_id is not None:
        open_day = _day(session, context.organization.id, open_day_id, lock=True)
        open_intervals = _intervals_for_day(session, open_day, lock=True)
        if any(interval.checked_out_at is None for interval in open_intervals):
            raise HTTPException(
                status_code=409,
                detail="Child already has an open attendance interval",
            )
    day_id = session.scalar(
        select(AttendanceDay.id).where(
            AttendanceDay.organization_id == context.organization.id,
            AttendanceDay.facility_id == facility.id,
            AttendanceDay.child_id == payload.child_id,
            AttendanceDay.service_date == service_date,
        )
    )
    day = _day(session, context.organization.id, day_id, lock=True) if day_id is not None else None
    intervals = _intervals_for_day(session, day, lock=True) if day is not None else []
    if any(interval.checked_out_at is None for interval in intervals):
        raise HTTPException(
            status_code=409,
            detail="Child already has an open attendance interval",
        )
    if (
        day is not None
        and not context.organization_wide
        and day.room_id not in context.assigned_room_ids
    ):
        raise HTTPException(status_code=404, detail="Attendance day not found")
    if day is not None and day.status == "absent":
        raise HTTPException(
            status_code=409,
            detail="Clear the absence through a reasoned correction before check-in",
        )
    if day is None:
        day = AttendanceDay(
            id=uuid4(),
            organization_id=context.organization.id,
            facility_id=facility.id,
            child_id=payload.child_id,
            enrollment_id=enrollment.id,
            room_id=enrollment.room_id,
            service_date=service_date,
            status="present",
            version=1,
        )
        session.add(day)
        flush_or_conflict(session, "Attendance day already exists")
        sequence = 1
    else:
        sequence = max((interval.sequence for interval in intervals), default=0) + 1
        day.version += 1
    interval = AttendanceInterval(
        id=uuid4(),
        organization_id=context.organization.id,
        attendance_day_id=day.id,
        sequence=sequence,
        checked_in_at=occurred_at,
    )
    session.add(interval)
    session.add(
        AttendanceEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            attendance_day_id=day.id,
            client_operation_id=payload.client_operation_id,
            actor_user_id=context.user.id,
            event_type="check_in",
            occurred_at=occurred_at,
            after={"interval_id": str(interval.id), "checked_in_at": occurred_at.isoformat()},
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="attendance.checked_in",
        entity_type="attendance_day",
        entity_id=day.id,
        facility_id=facility.id,
        details={"child_id": str(payload.child_id)},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            cause_entity_type="attendance_day",
            cause_entity_id=day.id,
        )
    commit_in_context(session, context, "Attendance check-in conflicts with another update")
    return _day_response(session, day)


@router.post("/check-out", response_model=AttendanceDayResponse)
def check_out(
    payload: CheckOutRequest,
    request: Request,
    context: AttendanceRecordContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    ensure_writable(request)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    occurred_at = _aware(payload.occurred_at)
    _reject_future_attendance_time(occurred_at)
    replay = _operation_replay(
        session,
        context,
        request,
        payload.client_operation_id,
        event_type="check_out",
        child_id=payload.child_id,
        facility_id=payload.facility_id,
        occurred_at=occurred_at,
    )
    if replay is not None:
        return replay
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, payload.facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=payload.facility_id,
            permission="attendance:record",
            conceal_detail="Open attendance interval not found",
        )
    if _facility_requires_verified_release_checkout(
        request,
        session,
        context.organization.id,
        payload.facility_id,
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "verified_release_checkout_required"},
        )
    facility = _facility(
        session,
        context.organization.id,
        payload.facility_id,
        allow_inactive=True,
    )
    day_id = session.scalar(
        select(AttendanceDay.id)
        .join(
            AttendanceInterval,
            and_(
                AttendanceDay.organization_id == AttendanceInterval.organization_id,
                AttendanceDay.id == AttendanceInterval.attendance_day_id,
            ),
        )
        .where(
            AttendanceInterval.organization_id == context.organization.id,
            AttendanceDay.facility_id == payload.facility_id,
            AttendanceDay.child_id == payload.child_id,
            AttendanceInterval.checked_out_at.is_(None),
        )
        .order_by(AttendanceInterval.checked_in_at.desc())
    )
    if day_id is None:
        if not context.organization_wide:
            raise HTTPException(status_code=404, detail="Open attendance interval not found")
        raise HTTPException(status_code=409, detail="Child has no open attendance interval")
    day = _day(session, context.organization.id, day_id, lock=True)
    intervals = _intervals_for_day(session, day, lock=True)
    open_intervals = [interval for interval in intervals if interval.checked_out_at is None]
    interval = max(open_intervals, key=lambda item: _aware(item.checked_in_at), default=None)
    if (
        interval is None
        or day.facility_id != payload.facility_id
        or day.child_id != payload.child_id
    ):
        if not context.organization_wide:
            raise HTTPException(status_code=404, detail="Open attendance interval not found")
        raise HTTPException(status_code=409, detail="Child has no open attendance interval")
    if not context.organization_wide and day.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Open attendance interval not found")
    require_open_shift(
        session,
        context,
        facility.id,
        day.room_id,
        enforce_room_presence=live_room_safety,
        allow_terminal_integrity_escape=True,
    )
    _ensure_service_date(facility, day, occurred_at)
    if occurred_at < _aware(interval.checked_in_at):
        raise HTTPException(status_code=422, detail="Check-out cannot precede check-in")
    records = _care_records_for_day(session, day, lock=True)
    medication_records = _medication_records_for_day(session, day, lock=True)
    incident_records = _incident_records_for_day(session, day, lock=True)
    _ensure_checkout_preserves_care(records, occurred_at)
    _ensure_checkout_preserves_regulated_records(medication_records, incident_records, occurred_at)
    auto_finish_open_sleep(
        session,
        organization_id=context.organization.id,
        attendance_day_id=day.id,
        actor_user_id=context.user.id,
        checked_out_at=occurred_at,
        facility_id=day.facility_id,
        records=records,
    )
    interval.checked_out_at = occurred_at
    day.version += 1
    session.add(
        AttendanceEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            attendance_day_id=day.id,
            client_operation_id=payload.client_operation_id,
            actor_user_id=context.user.id,
            event_type="check_out",
            occurred_at=occurred_at,
            before={"checked_out_at": None},
            after={"checked_out_at": occurred_at.isoformat()},
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="attendance.checked_out",
        entity_type="attendance_day",
        entity_id=day.id,
        facility_id=day.facility_id,
        details={"child_id": str(payload.child_id)},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=day.facility_id,
            cause_entity_type="attendance_day",
            cause_entity_id=day.id,
        )
    commit_in_context(session, context)
    return _day_response(session, day)


@router.put("/absence", response_model=AttendanceDayResponse)
def mark_absent(
    payload: AbsenceRequest,
    request: Request,
    context: AttendanceRecordContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, payload.facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=payload.facility_id,
            permission="attendance:record",
            conceal_detail="Child enrollment not found",
        )
    # Shared mutation order inside the facility projection lane:
    # Child -> Facility -> Enrollment -> Room.
    _lock_active_child(session, context.organization.id, payload.child_id)
    facility = _facility(
        session,
        context.organization.id,
        payload.facility_id,
        active_only=True,
        lock=True,
    )
    enrollment = _active_enrollment(
        session,
        context.organization.id,
        payload.facility_id,
        payload.child_id,
        payload.date,
        lock=True,
        child_locked=True,
    )
    _lock_enrollment_room(session, context.organization.id, enrollment)
    if not context.organization_wide and enrollment.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Child enrollment not found")
    require_open_shift(
        session,
        context,
        facility.id,
        enrollment.room_id,
        enforce_room_presence=live_room_safety,
    )
    day = session.scalar(
        select(AttendanceDay)
        .where(
            AttendanceDay.organization_id == context.organization.id,
            AttendanceDay.facility_id == payload.facility_id,
            AttendanceDay.child_id == payload.child_id,
            AttendanceDay.service_date == payload.date,
        )
        .with_for_update()
    )
    if (
        day is not None
        and not context.organization_wide
        and day.room_id not in context.assigned_room_ids
    ):
        raise HTTPException(status_code=404, detail="Attendance day not found")
    if day is not None:
        intervals = _intervals_for_day(session, day, lock=True)
        _care_records_for_day(session, day, lock=True)
        _medication_records_for_day(session, day, lock=True)
        _incident_records_for_day(session, day, lock=True)
        if intervals:
            raise HTTPException(
                status_code=409,
                detail="A day with attendance intervals cannot be marked absent",
            )
        before = {"status": day.status, "absence_reason": day.absence_reason}
        day.version += 1
    else:
        day = AttendanceDay(
            id=uuid4(),
            organization_id=context.organization.id,
            facility_id=payload.facility_id,
            child_id=payload.child_id,
            enrollment_id=enrollment.id,
            room_id=enrollment.room_id,
            service_date=payload.date,
            status="absent",
            version=1,
        )
        session.add(day)
        flush_or_conflict(session, "Attendance day already exists")
        before = None
    day.status = "absent"
    day.absence_reason = payload.reason.strip()
    session.add(
        AttendanceEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            attendance_day_id=day.id,
            actor_user_id=context.user.id,
            event_type="absence",
            reason=payload.reason.strip(),
            before=before,
            after={"status": "absent", "absence_reason": payload.reason.strip()},
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="attendance.absence_recorded",
        entity_type="attendance_day",
        entity_id=day.id,
        facility_id=day.facility_id,
        details={"child_id": str(payload.child_id)},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=day.facility_id,
            cause_entity_type="attendance_day",
            cause_entity_id=day.id,
        )
    commit_in_context(session, context, "Attendance absence conflicts with another update")
    return _day_response(session, day)


@router.put("/{attendance_day_id}/correction", response_model=AttendanceDayResponse)
def correct_interval(
    attendance_day_id: UUID,
    payload: CorrectionRequest,
    request: Request,
    context: AttendanceCorrectContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    facility_id = session.scalar(
        select(AttendanceDay.facility_id).where(
            AttendanceDay.id == attendance_day_id,
            AttendanceDay.organization_id == context.organization.id,
        )
    )
    if facility_id is None:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=facility_id,
            permission="attendance:correct",
            conceal_detail="Attendance day not found",
        )
    day = _day(session, context.organization.id, attendance_day_id, lock=True)
    if day.facility_id != facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "attendance_source_integrity_unknown"},
        )
    if not context.organization_wide and day.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    facility = _facility(session, context.organization.id, day.facility_id)
    require_open_shift(
        session,
        context,
        facility.id,
        day.room_id,
        enforce_room_presence=live_room_safety,
    )
    intervals = _intervals_for_day(session, day, lock=True)
    interval = next((item for item in intervals if item.id == payload.interval_id), None)
    if interval is None:
        raise HTTPException(status_code=404, detail="Attendance interval not found")
    verified_release_required = _facility_requires_verified_release_checkout(
        request,
        session,
        context.organization.id,
        day.facility_id,
    )
    if verified_release_required and _interval_has_release_snapshot(
        session,
        context.organization.id,
        interval.id,
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "verified_release_interval_immutable"},
        )
    if (
        verified_release_required
        and interval.checked_out_at is None
        and payload.checked_out_at is not None
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "verified_release_checkout_required"},
        )
    records = _care_records_for_day(session, day, lock=True)
    medication_records = _medication_records_for_day(session, day, lock=True)
    incident_records = _incident_records_for_day(session, day, lock=True)
    checked_in_at = _aware(payload.checked_in_at)
    checked_out_at = _aware(payload.checked_out_at) if payload.checked_out_at else None
    _reject_future_attendance_time(checked_in_at)
    if checked_out_at is not None:
        _reject_future_attendance_time(checked_out_at)
    if checked_out_at is None:
        _ensure_service_date(facility, day, checked_in_at)
    else:
        _ensure_service_date(facility, day, checked_in_at, checked_out_at)
    if checked_out_at is not None and checked_out_at < checked_in_at:
        raise HTTPException(status_code=422, detail="Check-out cannot precede check-in")
    others = [item for item in intervals if item.id != interval.id]
    for other in others:
        other_start = _aware(other.checked_in_at)
        other_end = _aware(other.checked_out_at) if other.checked_out_at else None
        overlaps = (checked_out_at is None or other_start < checked_out_at) and (
            other_end is None or checked_in_at < other_end
        )
        if overlaps:
            raise HTTPException(
                status_code=409, detail="Corrected interval overlaps another interval"
            )
    _ensure_care_survives_interval_correction(
        intervals,
        records,
        interval.id,
        checked_in_at,
        checked_out_at,
    )
    _ensure_regulated_records_survive_interval_correction(
        intervals,
        medication_records,
        incident_records,
        interval.id,
        checked_in_at,
        checked_out_at,
    )
    before = {
        "checked_in_at": _aware(interval.checked_in_at).isoformat(),
        "checked_out_at": (
            _aware(interval.checked_out_at).isoformat() if interval.checked_out_at else None
        ),
    }
    interval.checked_in_at = checked_in_at
    interval.checked_out_at = checked_out_at
    after = {
        "checked_in_at": checked_in_at.isoformat(),
        "checked_out_at": checked_out_at.isoformat() if checked_out_at else None,
    }
    day.version += 1
    session.add(
        AttendanceEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            attendance_day_id=day.id,
            actor_user_id=context.user.id,
            event_type="correction",
            reason=payload.reason.strip(),
            before=before,
            after=after,
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="attendance.corrected",
        entity_type="attendance_day",
        entity_id=day.id,
        facility_id=day.facility_id,
        details={"interval_id": str(interval.id), "reason": payload.reason.strip()},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=day.facility_id,
            cause_entity_type="attendance_day",
            cause_entity_id=day.id,
        )
    commit_in_context(session, context)
    return _day_response(session, day)


@router.put("/{attendance_day_id}/status-correction", response_model=AttendanceDayResponse)
def correct_status(
    attendance_day_id: UUID,
    payload: AttendanceStatusCorrectionRequest,
    request: Request,
    context: AttendanceCorrectContext,
    session: SessionDependency,
) -> AttendanceDayResponse:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    facility_id = session.scalar(
        select(AttendanceDay.facility_id).where(
            AttendanceDay.id == attendance_day_id,
            AttendanceDay.organization_id == context.organization.id,
        )
    )
    if facility_id is None:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility_id
        )
        context = _refresh_attendance_context(
            session,
            context,
            facility_id=facility_id,
            permission="attendance:correct",
            conceal_detail="Attendance day not found",
        )
    day = session.scalar(
        select(AttendanceDay)
        .where(
            AttendanceDay.id == attendance_day_id,
            AttendanceDay.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    if day is None:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    if day.facility_id != facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "attendance_source_integrity_unknown"},
        )
    if not context.organization_wide and day.room_id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    require_open_shift(
        session,
        context,
        day.facility_id,
        day.room_id,
        enforce_room_presence=live_room_safety,
    )
    intervals = _intervals_for_day(session, day, lock=True)
    _care_records_for_day(session, day, lock=True)
    _medication_records_for_day(session, day, lock=True)
    _incident_records_for_day(session, day, lock=True)
    if payload.status == "absent" and intervals:
        raise HTTPException(
            status_code=409,
            detail="A day with attendance intervals cannot be corrected to absent",
        )
    before = {"status": day.status, "absence_reason": day.absence_reason}
    day.status = payload.status
    day.absence_reason = (
        payload.absence_reason.strip()
        if payload.status == "absent" and payload.absence_reason
        else None
    )
    day.version += 1
    after = {"status": day.status, "absence_reason": day.absence_reason}
    session.add(
        AttendanceEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            attendance_day_id=day.id,
            actor_user_id=context.user.id,
            event_type="status_correction",
            reason=payload.reason.strip(),
            before=before,
            after=after,
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="attendance.status_corrected",
        entity_type="attendance_day",
        entity_id=day.id,
        facility_id=day.facility_id,
        details={"reason": payload.reason.strip(), "before": before, "after": after},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=day.facility_id,
            cause_entity_type="attendance_day",
            cause_entity_id=day.id,
        )
    commit_in_context(session, context)
    return _day_response(session, day)
