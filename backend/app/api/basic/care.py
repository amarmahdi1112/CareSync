"""Assigned-room daily care and minimized child-safety workflows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    BasicContext,
    CareCorrectionContext,
    CareDailyCloseContext,
    CareDaybookContext,
    CareRecordContext,
    CareVoidContext,
    ChildSafetyContext,
    refresh_basic_context,
)
from app.api.dependencies import SessionDependency
from app.basic.daily_care import aware_utc, care_record_snapshot
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    ChildProfilePhoto,
    DailyCareRecord,
    DailyCareRecordEvent,
    EmergencyContact,
    Enrollment,
    Facility,
    Family,
    Guardian,
    IncidentRecord,
    MedicationAdministration,
    Room,
    User,
)
from app.basic.room_safety import (
    foundation_enabled as room_safety_enabled,
)
from app.basic.room_safety import (
    lock_facility_projection,
)
from app.basic.schemas import (
    CARE_PAYLOAD_MODELS,
    CareDayChildResponse,
    CareRoomDayResponse,
    ChildSafetyCardResponse,
    ChildSafetyContact,
    ChildSafetySummary,
    DailyCareCorrectionRequest,
    DailyCareRecordCreate,
    DailyCareRecordEventResponse,
    DailyCareRecordResponse,
    DailyCareSleepFinishRequest,
    DailyCareVoidRequest,
    DailyCloseAttendanceState,
    DailyCloseAttendanceStateCounts,
    DailyCloseAttentionFlag,
    DailyCloseAttentionFlagCounts,
    DailyCloseCareCounts,
    DailyCloseIncidentStatusCounts,
    DailyCloseMedicationOutcomeCounts,
    RoomDailyCloseChildResponse,
    RoomDailyClosePreviewResponse,
    RoomDailyCloseTotalsResponse,
)
from app.basic.security import audit
from app.basic.shift_guards import require_open_shift

router = APIRouter(prefix="/care", tags=["daily care"])

_DAILY_CLOSE_CARE_TYPES = ("feeding", "diaper", "toilet", "sleep", "mood", "activity")
_DAILY_CLOSE_MEDICATION_OUTCOMES = ("administered", "refused", "omitted")
_DAILY_CLOSE_INCIDENT_STATUSES = ("draft", "under_review", "finalized")
_DAILY_CLOSE_ATTENDANCE_STATES = ("not_recorded", "on_site", "checked_out", "no_show")
_DAILY_CLOSE_ATTENTION_FLAGS: tuple[DailyCloseAttentionFlag, ...] = (
    "open_sleep",
    "medication_refused",
    "medication_omitted",
    "incident_draft",
    "incident_under_review",
)


@dataclass(frozen=True)
class _DailyCloseRosterItem:
    enrollment_id: UUID
    child_id: UUID
    first_name: str
    last_name: str
    attendance_day_id: UUID | None
    attendance_status: str | None


def _timezone(facility: Facility) -> ZoneInfo:
    try:
        return ZoneInfo(facility.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=409, detail="Facility timezone is invalid") from None


def _local_date(facility: Facility, instant: datetime | None = None) -> date:
    resolved = aware_utc(instant or datetime.now(UTC))
    return resolved.astimezone(_timezone(facility)).date()


def _room_access(
    session: SessionDependency,
    context: BasicContext,
    room_id: UUID,
    *,
    expected_facility_id: UUID | None = None,
    allow_inactive_organization_read: bool = False,
) -> tuple[Facility, Room]:
    row = session.execute(
        select(Facility, Room)
        .join(
            Room,
            and_(
                Room.organization_id == Facility.organization_id,
                Room.facility_id == Facility.id,
            ),
        )
        .where(
            Facility.organization_id == context.organization.id,
            Room.id == room_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Room not found")
    facility, room = row
    if expected_facility_id is not None and facility.id != expected_facility_id:
        raise HTTPException(status_code=404, detail="Room not found")
    active_placement = facility.status == "active" and room.is_active
    if not active_placement and not (
        allow_inactive_organization_read and context.organization_wide
    ):
        raise HTTPException(status_code=404, detail="Room not found")
    if not context.organization_wide and (
        facility.id not in context.assigned_facility_ids or room.id not in context.assigned_room_ids
    ):
        raise HTTPException(status_code=404, detail="Room not found")
    return facility, room


def _attendance_day(
    session: SessionDependency,
    organization_id: UUID,
    attendance_day_id: UUID,
    *,
    lock: bool = False,
) -> AttendanceDay:
    statement = select(AttendanceDay).where(
        AttendanceDay.organization_id == organization_id,
        AttendanceDay.id == attendance_day_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    day = session.scalar(statement)
    if day is None:
        raise HTTPException(status_code=404, detail="Attendance day not found")
    return day


def _attendance_intervals(
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


def _care_record(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
    *,
    lock: bool = False,
    allow_inactive_organization_read: bool = False,
) -> DailyCareRecord:
    statement = select(DailyCareRecord).where(
        DailyCareRecord.organization_id == context.organization.id,
        DailyCareRecord.id == record_id,
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise HTTPException(status_code=404, detail="Care record not found")
    _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=allow_inactive_organization_read,
    )
    return record


def _locked_care_context(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
) -> tuple[DailyCareRecord, AttendanceDay, list[AttendanceInterval]]:
    """Lock a care mutation in the global day -> intervals -> record order."""

    snapshot = _care_record(session, context, record_id)
    day = _attendance_day(
        session,
        context.organization.id,
        snapshot.attendance_day_id,
        lock=True,
    )
    intervals = _attendance_intervals(session, day, lock=True)
    record = _care_record(session, context, record_id, lock=True)
    if (
        record.attendance_day_id != day.id
        or record.organization_id != day.organization_id
        or record.facility_id != day.facility_id
        or record.room_id != day.room_id
        or record.child_id != day.child_id
        or record.enrollment_id != day.enrollment_id
        or record.service_date != day.service_date
    ):
        raise HTTPException(status_code=409, detail="Care attendance identity has changed")
    return record, day, intervals


def _operation(
    session: SessionDependency,
    organization_id: UUID,
    client_operation_id: UUID,
) -> DailyCareRecordEvent | None:
    return session.scalar(
        select(DailyCareRecordEvent).where(
            DailyCareRecordEvent.organization_id == organization_id,
            DailyCareRecordEvent.client_operation_id == client_operation_id,
        )
    )


def _lock_room_safety_lane(
    request: Request,
    session: SessionDependency,
    context: BasicContext,
    facility_id: UUID,
) -> bool:
    """Serialize an operational presence check with room/shift transitions."""

    enabled = room_safety_enabled(
        request,
        session,
        context.organization.id,
    )
    if enabled:
        lock_facility_projection(
            session,
            context.organization.id,
            facility_id,
        )
    return enabled


def _idempotent_mutation(
    session: SessionDependency,
    context: BasicContext,
    request: Request,
    *,
    record_id: UUID,
    operation_id: UUID,
    event_type: str,
    expected_before_version: int,
    expected_after: dict[str, object],
    expected_reason: str | None = None,
) -> DailyCareRecord | None:
    event = _operation(session, context.organization.id, operation_id)
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Care record not found")
    preliminary = session.scalar(
        select(DailyCareRecord).where(
            DailyCareRecord.organization_id == context.organization.id,
            DailyCareRecord.id == event.care_record_id,
        )
    )
    if preliminary is None:
        raise HTTPException(
            status_code=409,
            detail="Care record is unavailable",
        )
    _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary.facility_id,
    )
    current_context = refresh_basic_context(
        session,
        context,
        required_any_permissions={
            "sleep_finished": ("care:record",),
            "corrected": ("care:correct", "care:correct_own"),
            "voided": ("care:void",),
        }[event_type],
        conceal_detail="Care record not found",
    )
    resolved = _care_record(
        session,
        current_context,
        event.care_record_id,
        allow_inactive_organization_read=True,
    )
    if event_type == "corrected":
        _ensure_correction_access(
            session,
            current_context,
            resolved,
            conceal=True,
        )
    if event.care_record_id != record_id or event.event_type != event_type:
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    if event.reason != expected_reason or event.before is None or event.after is None:
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    if event.before.get("version") != expected_before_version or any(
        event.after.get(key) != value for key, value in expected_after.items()
    ):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    # Replays are stable and side-effect free. They return the current projection,
    # which may include a later correction or void, rather than reconstructing an
    # obsolete representation from the event ledger.
    return resolved


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _validate_event_time(
    facility: Facility,
    service_date: date,
    occurred_at: datetime,
    *,
    ended_at: datetime | None = None,
) -> tuple[datetime, datetime | None]:
    occurred = aware_utc(occurred_at)
    ended = aware_utc(ended_at) if ended_at else None
    if occurred > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Care time cannot be in the future")
    if _local_date(facility, occurred) != service_date:
        raise HTTPException(
            status_code=422,
            detail="Care time must fall on the attendance service date",
        )
    if ended is not None:
        if ended < occurred:
            raise HTTPException(status_code=422, detail="End time cannot precede start time")
        if ended > datetime.now(UTC) + timedelta(minutes=5):
            raise HTTPException(status_code=422, detail="Care end time cannot be in the future")
        if _local_date(facility, ended) != service_date:
            raise HTTPException(
                status_code=422,
                detail="Care end time must fall on the attendance service date",
            )
    return occurred, ended


def _attendance_interval(
    session: SessionDependency,
    day: AttendanceDay,
    occurred_at: datetime,
    *,
    ended_at: datetime | None,
    require_open: bool,
    intervals: Sequence[AttendanceInterval] | None = None,
    lock: bool = False,
) -> AttendanceInterval:
    resolved_intervals = (
        list(intervals) if intervals is not None else _attendance_intervals(session, day, lock=lock)
    )
    for interval in resolved_intervals:
        start = aware_utc(interval.checked_in_at)
        end = aware_utc(interval.checked_out_at) if interval.checked_out_at else None
        if require_open and end is not None:
            continue
        if occurred_at < start or (end is not None and occurred_at > end):
            continue
        if ended_at is not None and end is not None and ended_at > end:
            continue
        return interval
    raise HTTPException(
        status_code=409,
        detail="Care time must fall within an actual on-site attendance interval",
    )


def _canonical_payload(care_type: str, payload: object) -> dict[str, object]:
    if not hasattr(payload, "model_dump"):
        raise HTTPException(status_code=422, detail="Care payload is invalid")
    try:
        resolved = CARE_PAYLOAD_MODELS[care_type].model_validate(
            payload.model_dump(exclude_none=True)  # type: ignore[union-attr]
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from None
    return resolved.model_dump(exclude_none=True)


def _user_name(session: SessionDependency, user_id: UUID) -> str:
    user = session.scalar(select(User).where(User.id == user_id))
    return f"{user.first_name} {user.last_name}".strip() if user else "Former staff"


def _record_response(
    session: SessionDependency,
    record: DailyCareRecord,
    *,
    events: Sequence[DailyCareRecordEvent] | None = None,
    creator_names: dict[UUID, str] | None = None,
) -> DailyCareRecordResponse:
    resolved_events = (
        list(events)
        if events is not None
        else list(
            session.scalars(
                select(DailyCareRecordEvent)
                .where(
                    DailyCareRecordEvent.organization_id == record.organization_id,
                    DailyCareRecordEvent.care_record_id == record.id,
                )
                .order_by(
                    DailyCareRecordEvent.occurred_at.desc(),
                    DailyCareRecordEvent.id.desc(),
                )
            )
        )
    )
    if not resolved_events:
        raise HTTPException(status_code=409, detail="Care record history is unavailable")
    recorded_event = next(
        (event for event in resolved_events if event.event_type == "recorded"),
        None,
    )
    if recorded_event is None:
        raise HTTPException(status_code=409, detail="Care record creation receipt is unavailable")
    created_by_name = (
        creator_names.get(record.created_by_user_id, "Former staff")
        if creator_names is not None
        else _user_name(session, record.created_by_user_id)
    )
    return DailyCareRecordResponse(
        id=record.id,
        organization_id=record.organization_id,
        facility_id=record.facility_id,
        room_id=record.room_id,
        child_id=record.child_id,
        enrollment_id=record.enrollment_id,
        attendance_day_id=record.attendance_day_id,
        service_date=record.service_date,
        care_type=record.care_type,
        occurred_at=aware_utc(record.occurred_at),
        ended_at=aware_utc(record.ended_at) if record.ended_at else None,
        payload=dict(record.payload or {}),
        note=record.note,
        created_by_user_id=record.created_by_user_id,
        created_by_name=created_by_name,
        version=record.version,
        voided_at=aware_utc(record.voided_at) if record.voided_at else None,
        voided_by_user_id=record.voided_by_user_id,
        void_reason=record.void_reason,
        last_event_type=resolved_events[0].event_type,
        recorded_client_operation_id=recorded_event.client_operation_id,
        was_corrected=any(event.event_type == "corrected" for event in resolved_events),
        created_at=aware_utc(record.created_at),
        updated_at=aware_utc(record.updated_at),
    )


def _profile_photo_url(
    session: SessionDependency, organization_id: UUID, child_id: UUID
) -> str | None:
    exists = session.scalar(
        select(ChildProfilePhoto.id).where(
            ChildProfilePhoto.organization_id == organization_id,
            ChildProfilePhoto.child_id == child_id,
        )
    )
    return f"/api/v1/children/{child_id}/photo" if exists else None


def _safety_summary(child: Child, emergency_consent: bool) -> ChildSafetySummary:
    return ChildSafetySummary(
        allergies=child.allergies,
        medical_conditions=child.medical_conditions,
        medication_awareness=child.medications,
        emergency_medical_consent=bool(emergency_consent),
    )


def _attendance_state(
    day: AttendanceDay | None,
    intervals: Sequence[AttendanceInterval] = (),
) -> str:
    if day is None:
        return "not_recorded"
    if day.status == "absent":
        return "no_show"
    if any(interval.checked_out_at is None for interval in intervals):
        return "on_site"
    if intervals:
        return "checked_out"
    return "not_recorded"


def _daily_close_attendance_summary(
    attendance_status: str | None,
    intervals: Sequence[tuple[datetime, datetime | None]],
    generated_at: datetime,
) -> tuple[
    DailyCloseAttendanceState,
    datetime | None,
    datetime | None,
    int,
    bool,
]:
    resolved = [(aware_utc(start), aware_utc(end) if end else None) for start, end in intervals]
    first_check_in_at = min((start for start, _end in resolved), default=None)
    last_checkout_at = max(
        (end for _start, end in resolved if end is not None),
        default=None,
    )
    currently_on_site = attendance_status != "absent" and any(
        end is None for _start, end in resolved
    )
    accumulated_seconds = sum(
        max(0.0, ((end or generated_at) - start).total_seconds()) for start, end in resolved
    )
    if attendance_status is None:
        state: DailyCloseAttendanceState = "not_recorded"
    elif attendance_status == "absent":
        state = "no_show"
    elif currently_on_site:
        state = "on_site"
    elif resolved:
        state = "checked_out"
    else:
        state = "not_recorded"
    return (
        state,
        first_check_in_at,
        last_checkout_at,
        int(accumulated_seconds // 60),
        currently_on_site,
    )


def _most_recent(
    current: datetime | None,
    candidate: datetime,
) -> datetime:
    resolved = aware_utc(candidate)
    return resolved if current is None or resolved > current else current


def _assert_create_idempotence(
    session: SessionDependency,
    context: BasicContext,
    request: Request,
    payload: DailyCareRecordCreate,
) -> DailyCareRecord | None:
    event = _operation(session, context.organization.id, payload.client_operation_id)
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Care record not found")
    preliminary = session.scalar(
        select(DailyCareRecord).where(
            DailyCareRecord.organization_id == context.organization.id,
            DailyCareRecord.id == event.care_record_id,
        )
    )
    if preliminary is None:
        raise HTTPException(
            status_code=409,
            detail="Care record is unavailable",
        )
    _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary.facility_id,
    )
    current_context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("care:record",),
        conceal_detail="Care record not found",
    )
    resolved = _care_record(
        session,
        current_context,
        event.care_record_id,
        allow_inactive_organization_read=True,
    )
    if event.event_type != "recorded" or event.after is None:
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    expected = {
        "attendance_day_id": str(payload.attendance_day_id),
        "care_type": payload.care_type,
        "occurred_at": aware_utc(payload.occurred_at).isoformat(),
        "payload": _canonical_payload(payload.care_type, payload.payload),
        "note": payload.note,
    }
    if any(event.after.get(key) != value for key, value in expected.items()):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    return resolved


def _ensure_correction_access(
    session: SessionDependency,
    context: BasicContext,
    record: DailyCareRecord,
    *,
    conceal: bool = False,
) -> None:
    permissions = set(context.role.permissions or [])
    if "care:correct" in permissions:
        return
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
    )
    if (
        "care:correct_own" in permissions
        and record.created_by_user_id == context.user.id
        and record.service_date == _local_date(facility)
    ):
        return
    raise HTTPException(
        status_code=404 if conceal else 403,
        detail=(
            "Care record not found"
            if conceal
            else "Care correction permission required"
        ),
    )


@router.get("/rooms/{room_id}/day", response_model=CareRoomDayResponse)
def room_day(
    room_id: UUID,
    response: Response,
    context: CareDaybookContext,
    session: SessionDependency,
    service_date: Annotated[date, Query(alias="date")],
) -> CareRoomDayResponse:
    facility, room = _room_access(
        session,
        context,
        room_id,
        allow_inactive_organization_read=True,
    )
    facility_today = _local_date(facility)
    if not context.organization_wide and service_date != facility_today:
        raise HTTPException(
            status_code=403,
            detail="Educators can access only today's assigned-room daybook",
        )
    snapshot_rows = list(
        session.execute(
            select(Enrollment, Child, AttendanceDay)
            .select_from(AttendanceDay)
            .join(
                Enrollment,
                and_(
                    Enrollment.organization_id == AttendanceDay.organization_id,
                    Enrollment.id == AttendanceDay.enrollment_id,
                ),
            )
            .join(
                Child,
                and_(
                    Child.organization_id == AttendanceDay.organization_id,
                    Child.id == AttendanceDay.child_id,
                ),
            )
            .where(
                AttendanceDay.organization_id == context.organization.id,
                AttendanceDay.facility_id == facility.id,
                AttendanceDay.room_id == room.id,
                AttendanceDay.service_date == service_date,
            )
        )
    )
    roster_by_child: dict[UUID, tuple[Enrollment, Child, AttendanceDay | None]] = {
        child.id: (enrollment, child, day) for enrollment, child, day in snapshot_rows
    }
    placement_active = facility.status == "active" and room.is_active
    if service_date == facility_today and placement_active:
        current_rows = list(
            session.execute(
                select(Enrollment, Child)
                .join(
                    Child,
                    and_(
                        Child.organization_id == Enrollment.organization_id,
                        Child.id == Enrollment.child_id,
                    ),
                )
                .where(
                    Enrollment.organization_id == context.organization.id,
                    Enrollment.facility_id == facility.id,
                    Enrollment.room_id == room.id,
                    Enrollment.start_date <= service_date,
                    Enrollment.placement_effective_date <= service_date,
                    or_(
                        Enrollment.end_date.is_(None),
                        Enrollment.end_date >= service_date,
                    ),
                    Enrollment.status == "active",
                    Child.is_active.is_(True),
                )
            )
        )
        for enrollment, child in current_rows:
            roster_by_child.setdefault(child.id, (enrollment, child, None))
    enrollment_rows = sorted(
        roster_by_child.values(),
        key=lambda row: (row[1].last_name, row[1].first_name, str(row[1].id)),
    )
    child_ids = [child.id for _, child, _ in enrollment_rows]
    days = {day.enrollment_id: day for _, _, day in enrollment_rows if day is not None}
    records = list(
        session.scalars(
            select(DailyCareRecord)
            .where(
                DailyCareRecord.organization_id == context.organization.id,
                DailyCareRecord.room_id == room.id,
                DailyCareRecord.service_date == service_date,
                DailyCareRecord.voided_at.is_(None),
            )
            .order_by(DailyCareRecord.occurred_at, DailyCareRecord.created_at)
        )
    )
    records_by_enrollment: dict[UUID, list[DailyCareRecord]] = {}
    for record in records:
        records_by_enrollment.setdefault(record.enrollment_id, []).append(record)

    day_ids = [day.id for day in days.values()]
    intervals_by_day: dict[UUID, list[AttendanceInterval]] = {}
    if day_ids:
        for interval in session.scalars(
            select(AttendanceInterval)
            .where(
                AttendanceInterval.organization_id == context.organization.id,
                AttendanceInterval.attendance_day_id.in_(day_ids),
            )
            .order_by(AttendanceInterval.attendance_day_id, AttendanceInterval.sequence)
        ):
            intervals_by_day.setdefault(interval.attendance_day_id, []).append(interval)

    photo_child_ids = set(
        session.scalars(
            select(ChildProfilePhoto.child_id).where(
                ChildProfilePhoto.organization_id == context.organization.id,
                ChildProfilePhoto.child_id.in_(child_ids) if child_ids else False,
            )
        )
    )
    family_ids = {child.family_id for _, child, _ in enrollment_rows}
    consents = {
        family_id: bool(emergency_consent)
        for family_id, emergency_consent in session.execute(
            select(Family.id, Family.emergency_medical_consent).where(
                Family.organization_id == context.organization.id,
                Family.id.in_(family_ids) if family_ids else False,
            )
        )
    }

    record_ids = [record.id for record in records]
    events_by_record: dict[UUID, list[DailyCareRecordEvent]] = {}
    if record_ids:
        for event in session.scalars(
            select(DailyCareRecordEvent)
            .where(
                DailyCareRecordEvent.organization_id == context.organization.id,
                DailyCareRecordEvent.care_record_id.in_(record_ids),
            )
            .order_by(
                DailyCareRecordEvent.care_record_id,
                DailyCareRecordEvent.occurred_at.desc(),
                DailyCareRecordEvent.id.desc(),
            )
        ):
            events_by_record.setdefault(event.care_record_id, []).append(event)
    creator_ids = {record.created_by_user_id for record in records}
    creator_names = {
        user_id: f"{first_name} {last_name}".strip()
        for user_id, first_name, last_name in session.execute(
            select(User.id, User.first_name, User.last_name).where(
                User.id.in_(creator_ids) if creator_ids else False
            )
        )
    }
    generated_at = datetime.now(UTC)
    _private_no_store(response)
    return CareRoomDayResponse(
        organization_id=context.organization.id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=room.id,
        room_name=room.name,
        service_date=service_date,
        generated_at=generated_at,
        safety_as_of=generated_at,
        children=[
            CareDayChildResponse(
                child_id=child.id,
                child_name=f"{child.first_name} {child.last_name}".strip(),
                profile_photo_url=(
                    f"/api/v1/children/{child.id}/photo" if child.id in photo_child_ids else None
                ),
                enrollment_id=enrollment.id,
                attendance_day_id=(days[enrollment.id].id if enrollment.id in days else None),
                attendance_state=_attendance_state(
                    days.get(enrollment.id),
                    intervals_by_day.get(days[enrollment.id].id, ())
                    if enrollment.id in days
                    else (),
                ),
                safety=_safety_summary(
                    child,
                    consents.get(child.family_id, False),
                ),
                records=[
                    _record_response(
                        session,
                        record,
                        events=events_by_record.get(record.id, ()),
                        creator_names=creator_names,
                    )
                    for record in records_by_enrollment.get(enrollment.id, [])
                ],
            )
            for enrollment, child, _day in enrollment_rows
        ],
    )


@router.get(
    "/rooms/{room_id}/daily-close-preview",
    response_model=RoomDailyClosePreviewResponse,
)
def room_daily_close_preview(
    room_id: UUID,
    response: Response,
    context: CareDailyCloseContext,
    session: SessionDependency,
    service_date: Annotated[date, Query(alias="date")],
) -> RoomDailyClosePreviewResponse:
    """Return a factual, read-only room/day roll-up without completion claims."""

    generated_at = datetime.now(UTC)
    facility, room = _room_access(
        session,
        context,
        room_id,
        allow_inactive_organization_read=True,
    )
    facility_today = _local_date(facility, generated_at)
    if not context.organization_wide and service_date != facility_today:
        raise HTTPException(
            status_code=403,
            detail="Educators can access only today's assigned-room daily-close preview",
        )

    snapshot_rows = session.execute(
        select(
            Enrollment.id,
            Child.id,
            Child.first_name,
            Child.last_name,
            AttendanceDay.id,
            AttendanceDay.status,
        )
        .select_from(AttendanceDay)
        .join(
            Enrollment,
            and_(
                Enrollment.organization_id == AttendanceDay.organization_id,
                Enrollment.id == AttendanceDay.enrollment_id,
            ),
        )
        .join(
            Child,
            and_(
                Child.organization_id == AttendanceDay.organization_id,
                Child.id == AttendanceDay.child_id,
            ),
        )
        .where(
            AttendanceDay.organization_id == context.organization.id,
            AttendanceDay.facility_id == facility.id,
            AttendanceDay.room_id == room.id,
            AttendanceDay.service_date == service_date,
        )
    )
    roster_by_child: dict[UUID, _DailyCloseRosterItem] = {
        child_id: _DailyCloseRosterItem(
            enrollment_id=enrollment_id,
            child_id=child_id,
            first_name=first_name,
            last_name=last_name,
            attendance_day_id=attendance_day_id,
            attendance_status=attendance_status,
        )
        for (
            enrollment_id,
            child_id,
            first_name,
            last_name,
            attendance_day_id,
            attendance_status,
        ) in snapshot_rows
    }
    if service_date == facility_today and facility.status == "active" and room.is_active:
        current_rows = session.execute(
            select(
                Enrollment.id,
                Child.id,
                Child.first_name,
                Child.last_name,
            )
            .join(
                Child,
                and_(
                    Child.organization_id == Enrollment.organization_id,
                    Child.id == Enrollment.child_id,
                ),
            )
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.facility_id == facility.id,
                Enrollment.room_id == room.id,
                Enrollment.status == "active",
                Enrollment.start_date <= service_date,
                Enrollment.placement_effective_date <= service_date,
                or_(Enrollment.end_date.is_(None), Enrollment.end_date >= service_date),
                Child.is_active.is_(True),
            )
        )
        for enrollment_id, child_id, first_name, last_name in current_rows:
            roster_by_child.setdefault(
                child_id,
                _DailyCloseRosterItem(
                    enrollment_id=enrollment_id,
                    child_id=child_id,
                    first_name=first_name,
                    last_name=last_name,
                    attendance_day_id=None,
                    attendance_status=None,
                ),
            )

    roster = sorted(
        roster_by_child.values(),
        key=lambda item: (
            item.last_name.casefold(),
            item.first_name.casefold(),
            str(item.child_id),
        ),
    )
    child_ids = [item.child_id for item in roster]
    day_ids = [item.attendance_day_id for item in roster if item.attendance_day_id]

    intervals_by_day: dict[UUID, list[tuple[datetime, datetime | None]]] = {}
    if day_ids:
        interval_rows = session.execute(
            select(
                AttendanceInterval.attendance_day_id,
                AttendanceInterval.checked_in_at,
                AttendanceInterval.checked_out_at,
            )
            .where(
                AttendanceInterval.organization_id == context.organization.id,
                AttendanceInterval.attendance_day_id.in_(day_ids),
            )
            .order_by(AttendanceInterval.attendance_day_id, AttendanceInterval.sequence)
        )
        for attendance_day_id, checked_in_at, checked_out_at in interval_rows:
            intervals_by_day.setdefault(attendance_day_id, []).append(
                (checked_in_at, checked_out_at)
            )

    photo_child_ids = set(
        session.scalars(
            select(ChildProfilePhoto.child_id).where(
                ChildProfilePhoto.organization_id == context.organization.id,
                ChildProfilePhoto.child_id.in_(child_ids) if child_ids else False,
            )
        )
    )

    care_counts_by_child: dict[UUID, dict[str, int]] = {}
    open_sleep_child_ids: set[UUID] = set()
    most_recent_care_by_child: dict[UUID, datetime] = {}
    care_rows = session.execute(
        select(
            DailyCareRecord.child_id,
            DailyCareRecord.care_type,
            DailyCareRecord.occurred_at,
            DailyCareRecord.ended_at,
        ).where(
            DailyCareRecord.organization_id == context.organization.id,
            DailyCareRecord.facility_id == facility.id,
            DailyCareRecord.room_id == room.id,
            DailyCareRecord.service_date == service_date,
            DailyCareRecord.voided_at.is_(None),
        )
    )
    for child_id, care_type, occurred_at, ended_at in care_rows:
        if child_id not in roster_by_child:
            continue
        counts = care_counts_by_child.setdefault(
            child_id,
            {care_kind: 0 for care_kind in _DAILY_CLOSE_CARE_TYPES},
        )
        if care_type in counts:
            counts[care_type] += 1
        most_recent_care_by_child[child_id] = _most_recent(
            most_recent_care_by_child.get(child_id),
            occurred_at,
        )
        if care_type == "sleep" and ended_at is None:
            open_sleep_child_ids.add(child_id)

    medication_counts_by_child: dict[UUID, dict[str, int]] = {}
    most_recent_medication_by_child: dict[UUID, datetime] = {}
    medication_rows = session.execute(
        select(
            MedicationAdministration.child_id,
            MedicationAdministration.outcome,
            MedicationAdministration.occurred_at,
        ).where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.facility_id == facility.id,
            MedicationAdministration.room_id == room.id,
            MedicationAdministration.service_date == service_date,
            MedicationAdministration.voided_at.is_(None),
        )
    )
    for child_id, outcome, occurred_at in medication_rows:
        if child_id not in roster_by_child:
            continue
        counts = medication_counts_by_child.setdefault(
            child_id,
            {value: 0 for value in _DAILY_CLOSE_MEDICATION_OUTCOMES},
        )
        if outcome in counts:
            counts[outcome] += 1
        most_recent_medication_by_child[child_id] = _most_recent(
            most_recent_medication_by_child.get(child_id),
            occurred_at,
        )

    incident_counts_by_child: dict[UUID, dict[str, int]] = {}
    most_recent_incident_by_child: dict[UUID, datetime] = {}
    incident_rows = session.execute(
        select(
            IncidentRecord.child_id,
            IncidentRecord.status,
            IncidentRecord.occurred_at,
        ).where(
            IncidentRecord.organization_id == context.organization.id,
            IncidentRecord.facility_id == facility.id,
            IncidentRecord.room_id == room.id,
            IncidentRecord.service_date == service_date,
            IncidentRecord.child_id.in_(child_ids) if child_ids else False,
        )
    )
    for child_id, incident_status, occurred_at in incident_rows:
        if child_id is None or child_id not in roster_by_child:
            continue
        counts = incident_counts_by_child.setdefault(
            child_id,
            {value: 0 for value in _DAILY_CLOSE_INCIDENT_STATUSES},
        )
        if incident_status in counts:
            counts[incident_status] += 1
        most_recent_incident_by_child[child_id] = _most_recent(
            most_recent_incident_by_child.get(child_id),
            occurred_at,
        )

    attendance_totals = {value: 0 for value in _DAILY_CLOSE_ATTENDANCE_STATES}
    care_totals = {value: 0 for value in _DAILY_CLOSE_CARE_TYPES}
    medication_totals = {value: 0 for value in _DAILY_CLOSE_MEDICATION_OUTCOMES}
    incident_totals = {value: 0 for value in _DAILY_CLOSE_INCIDENT_STATUSES}
    attention_totals = {value: 0 for value in _DAILY_CLOSE_ATTENTION_FLAGS}
    accumulated_minutes_total = 0
    currently_on_site_total = 0
    children: list[RoomDailyCloseChildResponse] = []
    for item in roster:
        intervals = (
            intervals_by_day.get(item.attendance_day_id, ())
            if item.attendance_day_id is not None
            else ()
        )
        (
            attendance_state,
            first_check_in_at,
            last_checkout_at,
            accumulated_minutes,
            currently_on_site,
        ) = _daily_close_attendance_summary(
            item.attendance_status,
            intervals,
            generated_at,
        )
        care_counts = care_counts_by_child.get(
            item.child_id,
            {value: 0 for value in _DAILY_CLOSE_CARE_TYPES},
        )
        medication_counts = medication_counts_by_child.get(
            item.child_id,
            {value: 0 for value in _DAILY_CLOSE_MEDICATION_OUTCOMES},
        )
        incident_counts = incident_counts_by_child.get(
            item.child_id,
            {value: 0 for value in _DAILY_CLOSE_INCIDENT_STATUSES},
        )
        attention_flags: list[DailyCloseAttentionFlag] = []
        if item.child_id in open_sleep_child_ids:
            attention_flags.append("open_sleep")
        if medication_counts["refused"]:
            attention_flags.append("medication_refused")
        if medication_counts["omitted"]:
            attention_flags.append("medication_omitted")
        if incident_counts["draft"]:
            attention_flags.append("incident_draft")
        if incident_counts["under_review"]:
            attention_flags.append("incident_under_review")

        attendance_totals[attendance_state] += 1
        accumulated_minutes_total += accumulated_minutes
        currently_on_site_total += int(currently_on_site)
        for key, value in care_counts.items():
            care_totals[key] += value
        for key, value in medication_counts.items():
            medication_totals[key] += value
        for key, value in incident_counts.items():
            incident_totals[key] += value
        for flag in attention_flags:
            attention_totals[flag] += 1

        children.append(
            RoomDailyCloseChildResponse(
                child_id=item.child_id,
                child_name=f"{item.first_name} {item.last_name}".strip(),
                profile_photo_url=(
                    f"/api/v1/children/{item.child_id}/photo"
                    if item.child_id in photo_child_ids
                    else None
                ),
                enrollment_id=item.enrollment_id,
                attendance_day_id=item.attendance_day_id,
                attendance_state=attendance_state,
                first_check_in_at=first_check_in_at,
                last_checkout_at=last_checkout_at,
                accumulated_minutes=accumulated_minutes,
                currently_on_site=currently_on_site,
                care_counts=DailyCloseCareCounts(**care_counts),
                open_sleep=item.child_id in open_sleep_child_ids,
                most_recent_care_at=most_recent_care_by_child.get(item.child_id),
                medication_administration_counts=DailyCloseMedicationOutcomeCounts(
                    **medication_counts
                ),
                most_recent_medication_at=most_recent_medication_by_child.get(item.child_id),
                incident_status_counts=DailyCloseIncidentStatusCounts(**incident_counts),
                most_recent_incident_at=most_recent_incident_by_child.get(item.child_id),
                attention_flags=attention_flags,
            )
        )

    _private_no_store(response)
    return RoomDailyClosePreviewResponse(
        organization_id=context.organization.id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=room.id,
        room_name=room.name,
        service_date=service_date,
        generated_at=generated_at,
        totals=RoomDailyCloseTotalsResponse(
            child_count=len(children),
            attendance_state_counts=DailyCloseAttendanceStateCounts(**attendance_totals),
            accumulated_minutes=accumulated_minutes_total,
            currently_on_site=currently_on_site_total,
            care_counts=DailyCloseCareCounts(**care_totals),
            open_sleep=len(open_sleep_child_ids),
            medication_administration_counts=DailyCloseMedicationOutcomeCounts(**medication_totals),
            incident_status_counts=DailyCloseIncidentStatusCounts(**incident_totals),
            attention_flag_counts=DailyCloseAttentionFlagCounts(**attention_totals),
        ),
        children=children,
    )


@router.get("/children/{child_id}/safety-card", response_model=ChildSafetyCardResponse)
def child_safety_card(
    child_id: UUID,
    response: Response,
    context: ChildSafetyContext,
    session: SessionDependency,
    facility_id: Annotated[UUID, Query()],
) -> ChildSafetyCardResponse:
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == context.organization.id,
            Facility.id == facility_id,
            Facility.status == "active",
        )
    )
    if facility is None or (
        not context.organization_wide and facility.id not in context.assigned_facility_ids
    ):
        raise HTTPException(status_code=404, detail="Child not found")
    today = _local_date(facility)
    row = session.execute(
        select(Enrollment, Child)
        .join(
            Child,
            and_(
                Child.organization_id == Enrollment.organization_id,
                Child.id == Enrollment.child_id,
            ),
        )
        .where(
            Enrollment.organization_id == context.organization.id,
            Enrollment.facility_id == facility_id,
            Enrollment.child_id == child_id,
            Enrollment.status == "active",
            Enrollment.start_date <= today,
            Enrollment.placement_effective_date <= today,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= today),
            Enrollment.room_id.is_not(None),
            Child.is_active.is_(True),
        )
        .order_by(Enrollment.start_date.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Child not found")
    enrollment, child = row
    assert enrollment.room_id is not None
    _room_access(
        session,
        context,
        enrollment.room_id,
        expected_facility_id=facility_id,
    )
    primary_guardians = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == context.organization.id,
                Guardian.family_id == child.family_id,
                Guardian.is_primary.is_(True),
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.created_at, Guardian.id)
        )
    )
    contacts: list[ChildSafetyContact] = []
    for primary in primary_guardians:
        primary_phone = next(
            (
                value.strip()
                for value in (primary.cell_phone, primary.home_phone, primary.work_phone)
                if value and value.strip()
            ),
            None,
        )
        if primary_phone is not None:
            contacts.append(
                ChildSafetyContact(
                    id=primary.id,
                    contact_type="primary_guardian",
                    name=f"{primary.first_name} {primary.last_name}".strip(),
                    relationship=primary.relationship,
                    phone=primary_phone,
                    authorized_pickup=primary.authorized_pickup,
                )
            )
    emergency_contacts = list(
        session.scalars(
            select(EmergencyContact)
            .where(
                EmergencyContact.organization_id == context.organization.id,
                EmergencyContact.family_id == child.family_id,
                EmergencyContact.retired_at.is_(None),
            )
            .order_by(EmergencyContact.created_at, EmergencyContact.id)
        )
    )
    contacts.extend(
        ChildSafetyContact(
            id=item.id,
            contact_type="emergency_contact",
            name=f"{item.first_name} {item.last_name}".strip(),
            relationship=item.relationship,
            phone=item.cell_phone.strip(),
            authorized_pickup=item.authorized_pickup,
        )
        for item in emergency_contacts
        if item.cell_phone and item.cell_phone.strip()
    )
    _private_no_store(response)
    return ChildSafetyCardResponse(
        child_id=child.id,
        child_name=f"{child.first_name} {child.last_name}".strip(),
        profile_photo_url=_profile_photo_url(session, context.organization.id, child.id),
        age_group=child.age_group,
        facility_id=facility_id,
        room_id=enrollment.room_id,
        safety=_safety_summary(
            child,
            bool(
                session.scalar(
                    select(Family.emergency_medical_consent).where(
                        Family.organization_id == child.organization_id,
                        Family.id == child.family_id,
                    )
                )
            ),
        ),
        contacts=contacts,
    )


@router.post(
    "/records",
    response_model=DailyCareRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_care_record(
    payload: DailyCareRecordCreate,
    request: Request,
    response: Response,
    context: CareRecordContext,
    session: SessionDependency,
) -> DailyCareRecordResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = _assert_create_idempotence(session, context, request, payload)
    if existing is not None:
        return _record_response(session, existing)
    preliminary_day = _attendance_day(
        session,
        context.organization.id,
        payload.attendance_day_id,
    )
    preliminary_facility_id = preliminary_day.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("care:record",),
        conceal_detail="Attendance day not found",
    )
    day = _attendance_day(
        session,
        context.organization.id,
        payload.attendance_day_id,
        lock=True,
    )
    if day.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "attendance_source_integrity_unknown"},
        )
    if day.room_id is None:
        raise HTTPException(status_code=409, detail="Attendance day has no room placement")
    facility, _ = _room_access(
        session,
        context,
        day.room_id,
        expected_facility_id=day.facility_id,
    )
    require_open_shift(
        session,
        context,
        facility.id,
        day.room_id,
        enforce_room_presence=live_room_safety,
    )
    if day.status != "present":
        raise HTTPException(status_code=409, detail="Care can only be recorded for an on-site day")
    occurred_at, _ = _validate_event_time(facility, day.service_date, payload.occurred_at)
    intervals = _attendance_intervals(session, day, lock=True)
    _attendance_interval(
        session,
        day,
        occurred_at,
        ended_at=None,
        require_open=payload.care_type == "sleep",
        intervals=intervals,
    )
    care_payload = _canonical_payload(payload.care_type, payload.payload)
    record = DailyCareRecord(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=day.facility_id,
        room_id=day.room_id,
        child_id=day.child_id,
        enrollment_id=day.enrollment_id,
        attendance_day_id=day.id,
        service_date=day.service_date,
        care_type=payload.care_type,
        occurred_at=occurred_at,
        payload=care_payload,
        note=payload.note,
        created_by_user_id=context.user.id,
        version=1,
    )
    session.add(record)
    flush_or_conflict(session, "Care record conflicts with another update")
    session.add(
        DailyCareRecordEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            care_record_id=record.id,
            actor_user_id=context.user.id,
            client_operation_id=payload.client_operation_id,
            event_type="recorded",
            after=care_record_snapshot(record),
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="care.record.created",
        entity_type="daily_care_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "care_type": record.care_type,
            "child_id": str(record.child_id),
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Care operation conflicts with another update")
    return _record_response(session, record)


@router.post(
    "/records/{record_id}/finish-sleep",
    response_model=DailyCareRecordResponse,
)
def finish_sleep(
    record_id: UUID,
    payload: DailyCareSleepFinishRequest,
    request: Request,
    response: Response,
    context: CareRecordContext,
    session: SessionDependency,
) -> DailyCareRecordResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = _idempotent_mutation(
        session,
        context,
        request,
        record_id=record_id,
        operation_id=payload.client_operation_id,
        event_type="sleep_finished",
        expected_before_version=payload.expected_version,
        expected_after={"ended_at": aware_utc(payload.ended_at).isoformat()},
    )
    if existing is not None:
        return _record_response(session, existing)
    preliminary_record = _care_record(session, context, record_id)
    preliminary_facility_id = preliminary_record.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("care:record",),
        conceal_detail="Care record not found",
    )
    record, day, intervals = _locked_care_context(session, context, record_id)
    if record.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "care_source_integrity_unknown"},
        )
    if record.voided_at is not None:
        raise HTTPException(status_code=409, detail="Voided care record cannot be changed")
    if record.care_type != "sleep":
        raise HTTPException(status_code=422, detail="Only a sleep record can be finished")
    if record.ended_at is not None:
        raise HTTPException(status_code=409, detail="Sleep record is already finished")
    if record.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Care record has changed; refresh and retry")
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
    )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    occurred_at, ended_at = _validate_event_time(
        facility,
        record.service_date,
        aware_utc(record.occurred_at),
        ended_at=payload.ended_at,
    )
    assert ended_at is not None
    _attendance_interval(
        session,
        day,
        occurred_at,
        ended_at=ended_at,
        require_open=False,
        intervals=intervals,
    )
    before = care_record_snapshot(record)
    record.ended_at = ended_at
    record.version += 1
    session.add(
        DailyCareRecordEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            care_record_id=record.id,
            actor_user_id=context.user.id,
            client_operation_id=payload.client_operation_id,
            event_type="sleep_finished",
            before=before,
            after=care_record_snapshot(record),
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="care.sleep.finished",
        entity_type="daily_care_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "care_type": record.care_type,
            "child_id": str(record.child_id),
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Care operation conflicts with another update")
    return _record_response(session, record)


@router.put(
    "/records/{record_id}/correction",
    response_model=DailyCareRecordResponse,
)
def correct_care_record(
    record_id: UUID,
    payload: DailyCareCorrectionRequest,
    request: Request,
    response: Response,
    context: CareCorrectionContext,
    session: SessionDependency,
) -> DailyCareRecordResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = _idempotent_mutation(
        session,
        context,
        request,
        record_id=record_id,
        operation_id=payload.client_operation_id,
        event_type="corrected",
        expected_before_version=payload.expected_version,
        expected_after={
            "occurred_at": aware_utc(payload.occurred_at).isoformat(),
            "ended_at": aware_utc(payload.ended_at).isoformat() if payload.ended_at else None,
            "payload": payload.payload.model_dump(exclude_none=True),
            "note": payload.note,
        },
        expected_reason=payload.reason,
    )
    if existing is not None:
        return _record_response(session, existing)
    preliminary_record = _care_record(session, context, record_id)
    preliminary_facility_id = preliminary_record.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("care:correct", "care:correct_own"),
        conceal_detail="Care record not found",
    )
    record, day, intervals = _locked_care_context(session, context, record_id)
    if record.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "care_source_integrity_unknown"},
        )
    if record.voided_at is not None:
        raise HTTPException(status_code=409, detail="Voided care record cannot be changed")
    _ensure_correction_access(session, context, record)
    if record.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Care record has changed; refresh and retry")
    if record.care_type != "sleep" and payload.ended_at is not None:
        raise HTTPException(status_code=422, detail="Only sleep records can have an end time")
    canonical_payload = _canonical_payload(record.care_type, payload.payload)
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
    )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    occurred_at, ended_at = _validate_event_time(
        facility,
        record.service_date,
        payload.occurred_at,
        ended_at=payload.ended_at,
    )
    _attendance_interval(
        session,
        day,
        occurred_at,
        ended_at=ended_at,
        require_open=record.care_type == "sleep" and ended_at is None,
        intervals=intervals,
    )
    before = care_record_snapshot(record)
    record.occurred_at = occurred_at
    record.ended_at = ended_at
    record.payload = canonical_payload
    record.note = payload.note
    record.version += 1
    flush_or_conflict(session, "Corrected care record conflicts with another update")
    session.add(
        DailyCareRecordEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            care_record_id=record.id,
            actor_user_id=context.user.id,
            client_operation_id=payload.client_operation_id,
            event_type="corrected",
            reason=payload.reason,
            before=before,
            after=care_record_snapshot(record),
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="care.record.corrected",
        entity_type="daily_care_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "care_type": record.care_type,
            "child_id": str(record.child_id),
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Care operation conflicts with another update")
    return _record_response(session, record)


@router.post("/records/{record_id}/void", response_model=DailyCareRecordResponse)
def void_care_record(
    record_id: UUID,
    payload: DailyCareVoidRequest,
    request: Request,
    response: Response,
    context: CareVoidContext,
    session: SessionDependency,
) -> DailyCareRecordResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = _idempotent_mutation(
        session,
        context,
        request,
        record_id=record_id,
        operation_id=payload.client_operation_id,
        event_type="voided",
        expected_before_version=payload.expected_version,
        expected_after={"void_reason": payload.reason},
        expected_reason=payload.reason,
    )
    if existing is not None:
        return _record_response(session, existing)
    preliminary_record = _care_record(session, context, record_id)
    preliminary_facility_id = preliminary_record.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("care:void",),
        conceal_detail="Care record not found",
    )
    record, _day, _intervals = _locked_care_context(session, context, record_id)
    if record.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "care_source_integrity_unknown"},
        )
    require_open_shift(
        session,
        context,
        record.facility_id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    if record.voided_at is not None:
        raise HTTPException(status_code=409, detail="Care record is already voided")
    if record.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Care record has changed; refresh and retry")
    before = care_record_snapshot(record)
    record.voided_at = datetime.now(UTC)
    record.voided_by_user_id = context.user.id
    record.void_reason = payload.reason
    record.version += 1
    session.add(
        DailyCareRecordEvent(
            id=uuid4(),
            organization_id=context.organization.id,
            care_record_id=record.id,
            actor_user_id=context.user.id,
            client_operation_id=payload.client_operation_id,
            event_type="voided",
            reason=payload.reason,
            before=before,
            after=care_record_snapshot(record),
        )
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="care.record.voided",
        entity_type="daily_care_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "care_type": record.care_type,
            "child_id": str(record.child_id),
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Care operation conflicts with another update")
    return _record_response(session, record)


@router.get(
    "/records/{record_id}/history",
    response_model=list[DailyCareRecordEventResponse],
)
def care_record_history(
    record_id: UUID,
    response: Response,
    context: CareCorrectionContext,
    session: SessionDependency,
) -> list[DailyCareRecordEventResponse]:
    _private_no_store(response)
    record = _care_record(
        session,
        context,
        record_id,
        allow_inactive_organization_read=True,
    )
    permissions = set(context.role.permissions or [])
    may_read_all = bool(permissions.intersection({"care:correct", "care:void"}))
    may_read_own = (
        "care:correct_own" in permissions and record.created_by_user_id == context.user.id
    )
    if not (may_read_all or may_read_own):
        raise HTTPException(status_code=403, detail="Care history permission required")
    events = list(
        session.scalars(
            select(DailyCareRecordEvent)
            .where(
                DailyCareRecordEvent.organization_id == context.organization.id,
                DailyCareRecordEvent.care_record_id == record.id,
            )
            .order_by(DailyCareRecordEvent.occurred_at, DailyCareRecordEvent.id)
        )
    )
    return [
        DailyCareRecordEventResponse(
            id=event.id,
            care_record_id=event.care_record_id,
            actor_user_id=event.actor_user_id,
            actor_name=_user_name(session, event.actor_user_id),
            client_operation_id=event.client_operation_id,
            event_type=event.event_type,
            occurred_at=aware_utc(event.occurred_at),
            reason=event.reason,
            before=event.before,
            after=event.after,
        )
        for event in events
    ]
