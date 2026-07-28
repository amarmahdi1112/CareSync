"""Domain safeguards and projections for the daily staff rota."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.basic.models import (
    Facility,
    MembershipRoomAssignment,
    OrganizationMembership,
    Role,
    Room,
    ScheduledStaffShift,
    ScheduledStaffShiftEvent,
    StaffShift,
    User,
)
from app.basic.staff_schedule_schemas import (
    ActualStaffShiftResponse,
    ScheduledStaffShiftResponse,
    UnscheduledStaffShiftResponse,
)

LATE_GRACE = timedelta(minutes=5)
MAX_SHIFT_DURATION = timedelta(hours=24)


def aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            422,
            detail={"code": "timezone_required", "field": field},
        )
    return value.astimezone(UTC)


def stored_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def stored_optional_utc(value: datetime | None) -> datetime | None:
    return stored_utc(value) if value is not None else None


def validate_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    normalized_start = aware_utc(start, "scheduled_start_at")
    normalized_end = aware_utc(end, "scheduled_end_at")
    if normalized_end <= normalized_start:
        raise HTTPException(
            422,
            detail={"code": "invalid_schedule_interval", "message": "End must follow start"},
        )
    if normalized_end - normalized_start > MAX_SHIFT_DURATION:
        raise HTTPException(
            422,
            detail={
                "code": "invalid_schedule_interval",
                "message": "A staff shift cannot exceed 24 hours",
            },
        )
    return normalized_start, normalized_end


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def lock_schedule_lanes(session: Session, organization_id: UUID, membership_ids: set[UUID]) -> None:
    """Serialize overlap decisions in deterministic order on PostgreSQL."""

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        for membership_id in sorted(membership_ids, key=str):
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
                {"value": f"staff-rota:{organization_id}:{membership_id}"},
            )


def validate_assignment(
    session: Session,
    organization_id: UUID,
    *,
    staff_user_id: UUID,
    facility_id: UUID,
    room_id: UUID | None,
) -> tuple[OrganizationMembership, User, Facility, Room | None]:
    row = session.execute(
        select(OrganizationMembership, User, Role)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == staff_user_id,
            OrganizationMembership.status == "active",
            User.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            422,
            detail={"code": "inactive_staff", "message": "Active staff member not found"},
        )
    membership, user, role = row
    if "shift:clock" not in set(role.permissions or []):
        raise HTTPException(
            422,
            detail={"code": "staff_cannot_clock", "message": "Staff role cannot clock shifts"},
        )
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == organization_id,
            Facility.id == facility_id,
            Facility.status == "active",
        )
    )
    if facility is None:
        raise HTTPException(
            422,
            detail={"code": "inactive_facility", "message": "Active facility not found"},
        )
    room = None
    if room_id is not None:
        room = session.scalar(
            select(Room).where(
                Room.organization_id == organization_id,
                Room.facility_id == facility_id,
                Room.id == room_id,
                Room.is_active.is_(True),
            )
        )
        if room is None:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_room",
                    "message": "Active room at the selected facility not found",
                },
            )
    if role.key not in {"owner", "administrator"}:
        assignment_filters = [
            MembershipRoomAssignment.organization_id == organization_id,
            MembershipRoomAssignment.membership_id == membership.id,
            MembershipRoomAssignment.facility_id == facility_id,
            MembershipRoomAssignment.is_active.is_(True),
        ]
        if room_id is not None:
            assignment_filters.append(MembershipRoomAssignment.room_id == room_id)
        assigned = session.scalar(
            select(MembershipRoomAssignment.id).where(*assignment_filters).limit(1)
        )
        if assigned is None:
            raise HTTPException(
                422,
                detail={
                    "code": "staff_scope_mismatch",
                    "message": "Staff member is not actively assigned to this location",
                },
            )
    return membership, user, facility, room


def ensure_no_overlap(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
    start: datetime,
    end: datetime,
    *,
    exclude_id: UUID | None = None,
) -> None:
    statement = select(ScheduledStaffShift.id).where(
        ScheduledStaffShift.organization_id == organization_id,
        ScheduledStaffShift.membership_id == membership_id,
        ScheduledStaffShift.status != "cancelled",
        ScheduledStaffShift.scheduled_start_at < end,
        ScheduledStaffShift.scheduled_end_at > start,
    )
    if exclude_id is not None:
        statement = statement.where(ScheduledStaffShift.id != exclude_id)
    if session.scalar(statement.limit(1)) is not None:
        raise HTTPException(
            409,
            detail={
                "code": "overlapping_schedule",
                "message": "Staff member already has an overlapping scheduled shift",
            },
        )


def event_payload(
    *,
    staff_user_id: UUID | None = None,
    facility_id: UUID | None = None,
    room_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    notes: str | None = None,
    reason: str | None = None,
    response_note: str | None = None,
    proposed_start: datetime | None = None,
    proposed_end: datetime | None = None,
    changed_fields: list[str] | None = None,
) -> dict:
    values = {
        "staff_user_id": str(staff_user_id) if staff_user_id else None,
        "facility_id": str(facility_id) if facility_id else None,
        "room_id": str(room_id) if room_id else None,
        "scheduled_start_at": stored_utc(start).isoformat() if start else None,
        "scheduled_end_at": stored_utc(end).isoformat() if end else None,
        "notes": clean_optional_text(notes),
        "reason": clean_optional_text(reason),
        "response_note": clean_optional_text(response_note),
        "proposed_start_at": stored_utc(proposed_start).isoformat() if proposed_start else None,
        "proposed_end_at": stored_utc(proposed_end).isoformat() if proposed_end else None,
        "changed_fields": sorted(changed_fields or []),
    }
    return values


def idempotent_event(
    session: Session,
    organization_id: UUID,
    operation_id: UUID,
    *,
    schedule_id: UUID,
    event_type: str,
    payload: dict,
) -> ScheduledStaffShiftEvent | None:
    existing = session.scalar(
        select(ScheduledStaffShiftEvent).where(
            ScheduledStaffShiftEvent.organization_id == organization_id,
            ScheduledStaffShiftEvent.operation_id == operation_id,
        )
    )
    if existing is None:
        return None
    if (
        existing.scheduled_shift_id != schedule_id
        or existing.event_type != event_type
        or (existing.payload or {}) != payload
    ):
        raise HTTPException(
            409,
            detail={
                "code": "operation_reused",
                "message": "Operation identifier was already used for another action",
            },
        )
    return existing


def add_event(
    session: Session,
    schedule: ScheduledStaffShift,
    *,
    operation_id: UUID,
    actor_user_id: UUID,
    event_type: str,
    payload: dict,
    occurred_at: datetime,
) -> None:
    session.add(
        ScheduledStaffShiftEvent(
            organization_id=schedule.organization_id,
            scheduled_shift_id=schedule.id,
            operation_id=operation_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )
    )


def schedule_row(
    session: Session,
    organization_id: UUID,
    schedule_id: UUID,
    *,
    lock: bool = False,
) -> ScheduledStaffShift:
    statement = select(ScheduledStaffShift).where(
        ScheduledStaffShift.organization_id == organization_id,
        ScheduledStaffShift.id == schedule_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Scheduled shift not found")
    return value


def local_day_window(facility: Facility, service_date: date) -> tuple[datetime, datetime]:
    try:
        timezone = ZoneInfo(facility.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(
            409,
            detail={"code": "invalid_facility_timezone", "facility_id": str(facility.id)},
        ) from None
    start = datetime.combine(service_date, time.min, timezone)
    end = datetime.combine(service_date + timedelta(days=1), time.min, timezone)
    return start.astimezone(UTC), end.astimezone(UTC)


def actual_shift_response(shift: StaffShift) -> ActualStaffShiftResponse:
    return ActualStaffShiftResponse(
        id=shift.id,
        membership_id=shift.membership_id,
        facility_id=shift.facility_id,
        scheduled_shift_id=shift.scheduled_shift_id,
        status=shift.status,
        clocked_in_at=stored_utc(shift.clocked_in_at),
        clocked_out_at=stored_optional_utc(shift.clocked_out_at),
    )


def scheduled_shift_response(
    session: Session,
    schedule: ScheduledStaffShift,
    *,
    now: datetime | None = None,
) -> ScheduledStaffShiftResponse:
    generated_at = now or datetime.now(UTC)
    membership, user = session.execute(
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == schedule.organization_id,
            OrganizationMembership.id == schedule.membership_id,
        )
    ).one()
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == schedule.organization_id,
            Facility.id == schedule.facility_id,
        )
    )
    room = (
        session.scalar(
            select(Room).where(
                Room.organization_id == schedule.organization_id,
                Room.id == schedule.room_id,
            )
        )
        if schedule.room_id is not None
        else None
    )
    actual = session.scalar(
        select(StaffShift).where(
            StaffShift.organization_id == schedule.organization_id,
            StaffShift.scheduled_shift_id == schedule.id,
        )
    )
    start = stored_utc(schedule.scheduled_start_at)
    end = stored_utc(schedule.scheduled_end_at)
    now_utc = stored_utc(generated_at)
    actual_is_late = bool(actual and stored_utc(actual.clocked_in_at) > start + LATE_GRACE)
    is_late = False
    minutes_late = 0
    if schedule.status == "cancelled":
        reconciliation_status = "cancelled"
    elif actual is not None and actual_is_late:
        reconciliation_status = "late"
        is_late = True
        minutes_late = max(
            0,
            int((stored_utc(actual.clocked_in_at) - start).total_seconds() // 60),
        )
    elif actual is not None and actual.status == "open":
        reconciliation_status = "active"
    elif actual is not None:
        reconciliation_status = "completed"
    elif now_utc >= end:
        reconciliation_status = "missed"
    elif schedule.status == "published" and now_utc > start + LATE_GRACE:
        reconciliation_status = "late"
        is_late = True
        minutes_late = max(0, int((now_utc - start).total_seconds() // 60))
    else:
        reconciliation_status = "upcoming"
    return ScheduledStaffShiftResponse(
        id=schedule.id,
        organization_id=schedule.organization_id,
        membership_id=membership.id,
        staff_user_id=user.id,
        staff_display_name=f"{user.first_name} {user.last_name}".strip(),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=schedule.room_id,
        room_name=room.name if room else None,
        scheduled_start_at=stored_utc(schedule.scheduled_start_at),
        scheduled_end_at=stored_utc(schedule.scheduled_end_at),
        notes=schedule.notes,
        status=schedule.status,
        response_status=schedule.response_status,
        response_note=schedule.response_note,
        proposed_start_at=stored_optional_utc(schedule.proposed_start_at),
        proposed_end_at=stored_optional_utc(schedule.proposed_end_at),
        responded_at=stored_optional_utc(schedule.responded_at),
        actual_shift=actual_shift_response(actual) if actual else None,
        reconciliation_status=reconciliation_status,
        is_late=is_late,
        minutes_late=minutes_late,
        recorded_create_operation_id=schedule.create_operation_id,
        created_by_user_id=schedule.created_by_user_id,
        published_at=stored_optional_utc(schedule.published_at),
        published_by_user_id=schedule.published_by_user_id,
        cancelled_at=stored_optional_utc(schedule.cancelled_at),
        cancelled_by_user_id=schedule.cancelled_by_user_id,
        cancellation_reason=schedule.cancellation_reason,
        availability_override_reason=schedule.availability_override_reason,
        origin_type=schedule.origin_type,
        origin_id=schedule.origin_id,
        origin_occurrence_key=schedule.origin_occurrence_key,
        supersedes_schedule_id=schedule.supersedes_schedule_id,
        created_at=stored_utc(schedule.created_at),
        updated_at=stored_utc(schedule.updated_at),
    )


def unscheduled_shift_response(
    session: Session,
    shift: StaffShift,
) -> UnscheduledStaffShiftResponse:
    membership, user = session.execute(
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == shift.organization_id,
            OrganizationMembership.id == shift.membership_id,
        )
    ).one()
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == shift.organization_id,
            Facility.id == shift.facility_id,
        )
    )
    return UnscheduledStaffShiftResponse(
        staff_user_id=user.id,
        staff_display_name=f"{user.first_name} {user.last_name}".strip(),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        actual_shift=actual_shift_response(shift),
    )
