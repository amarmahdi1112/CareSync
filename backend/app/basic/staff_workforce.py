"""Domain invariants and projections for workforce planning."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.basic.models import (
    Facility,
    OrganizationMembership,
    Room,
    ScheduledStaffShift,
    StaffAvailabilityProfile,
    StaffCoverageTargetProfile,
    StaffShiftTemplate,
    StaffTimeOffRequest,
    StaffWorkforceEvent,
    User,
)
from app.basic.staff_scheduling import (
    aware_utc,
    clean_optional_text,
    stored_optional_utc,
    stored_utc,
)
from app.basic.staff_workforce_schemas import (
    MAX_COVERAGE_WINDOWS,
    CoverageWindow,
    StaffAvailabilityResponse,
    StaffCoverageTargetResponse,
    StaffShiftTemplateResponse,
    StaffTimeOffResponse,
)

MAX_TIME_OFF = timedelta(days=366)
QUARTER_HOUR = timedelta(minutes=15)


def facility_row(
    session: Session, organization_id: UUID, facility_id: UUID, *, active: bool = True
) -> Facility:
    filters = [Facility.organization_id == organization_id, Facility.id == facility_id]
    if active:
        filters.append(Facility.status == "active")
    value = session.scalar(select(Facility).where(*filters))
    if value is None:
        raise HTTPException(404, "Active facility not found" if active else "Facility not found")
    facility_zone(value)
    return value


def room_row(
    session: Session,
    organization_id: UUID,
    facility_id: UUID,
    room_id: UUID | None,
    *,
    active: bool = True,
) -> Room | None:
    if room_id is None:
        return None
    filters = [
        Room.organization_id == organization_id,
        Room.facility_id == facility_id,
        Room.id == room_id,
    ]
    if active:
        filters.append(Room.is_active.is_(True))
    value = session.scalar(select(Room).where(*filters))
    if value is None:
        raise HTTPException(422, detail={"code": "invalid_room"})
    return value


def facility_zone(facility: Facility) -> ZoneInfo:
    try:
        return ZoneInfo(facility.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(
            409,
            detail={"code": "invalid_facility_timezone", "facility_id": str(facility.id)},
        ) from None


def parse_local_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, detail={"code": "invalid_local_time"}) from None


def canonical_windows(windows, *, coverage: bool = False) -> list[dict]:
    values: list[dict] = []
    by_day: dict[int, list[tuple[time, time]]] = {}
    for window in windows:
        start = parse_local_time(window.start_local)
        end = parse_local_time(window.end_local)
        if end <= start:
            raise HTTPException(
                422,
                detail={"code": "invalid_weekly_window", "message": "End must follow start"},
            )
        if coverage and (
            start.minute % 15 != 0 or end.minute % 15 != 0 or start.second or end.second
        ):
            raise HTTPException(
                422,
                detail={"code": "coverage_alignment_required", "interval_minutes": 15},
            )
        day_intervals = by_day.setdefault(window.weekday, [])
        if any(
            existing_start < end and existing_end > start
            for existing_start, existing_end in day_intervals
        ):
            raise HTTPException(422, detail={"code": "overlapping_weekly_windows"})
        day_intervals.append((start, end))
        value = {
            "weekday": window.weekday,
            "start_local": start.strftime("%H:%M"),
            "end_local": end.strftime("%H:%M"),
        }
        if coverage:
            value["required_staff"] = window.required_staff
        values.append(value)
    return sorted(
        values,
        key=lambda item: (item["weekday"], item["start_local"], item["end_local"]),
    )


def canonical_stored_coverage_windows(windows: object) -> list[dict] | None:
    """Validate stored target JSON before it participates in live arithmetic."""

    if not isinstance(windows, list) or len(windows) > MAX_COVERAGE_WINDOWS:
        return None
    if any(
        not isinstance(window, dict)
        or type(window.get("weekday")) is not int
        or type(window.get("required_staff")) is not int
        for window in windows
    ):
        return None
    try:
        parsed = [CoverageWindow.model_validate(window) for window in windows]
        canonical = canonical_windows(parsed, coverage=True)
    except (HTTPException, ValidationError):
        return None
    # This also rejects coercible legacy values and non-canonical ordering.
    return canonical if windows == canonical else None


def validate_time_off_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    normalized_start = aware_utc(start, "starts_at")
    normalized_end = aware_utc(end, "ends_at")
    if normalized_end <= normalized_start:
        raise HTTPException(422, detail={"code": "invalid_time_off_interval"})
    if normalized_end - normalized_start > MAX_TIME_OFF:
        raise HTTPException(422, detail={"code": "time_off_too_long", "max_days": 366})
    return normalized_start, normalized_end


def require_current(
    updated_at: datetime, expected: datetime | None, *, absent: bool = False
) -> None:
    if absent:
        if expected is not None:
            raise HTTPException(409, detail={"code": "stale_workforce_resource"})
        return
    if expected is None or stored_utc(updated_at) != aware_utc(expected, "expected_updated_at"):
        raise HTTPException(
            409,
            detail={
                "code": "stale_workforce_resource",
                "current_updated_at": stored_utc(updated_at).isoformat(),
            },
        )


def lock_workforce_lane(session: Session, organization_id: UUID, *keys: str | UUID) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        for key in sorted({str(value) for value in keys}):
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
                {"value": f"staff-workforce:{organization_id}:{key}"},
            )


def canonical_event_payload(values: dict) -> dict:
    result = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            result[key] = aware_utc(value, key).isoformat()
        elif isinstance(value, (date, time)):
            result[key] = value.isoformat()
        elif isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, str):
            result[key] = clean_optional_text(value)
        elif isinstance(value, list):
            result[key] = value
        else:
            result[key] = value
    return result


def idempotent_workforce_event(
    session: Session,
    organization_id: UUID,
    operation_id: UUID,
    *,
    entity_type: str,
    event_type: str,
    payload: dict,
    entity_id: UUID | None = None,
) -> StaffWorkforceEvent | None:
    existing = session.scalar(
        select(StaffWorkforceEvent).where(
            StaffWorkforceEvent.organization_id == organization_id,
            StaffWorkforceEvent.operation_id == operation_id,
        )
    )
    if existing is None:
        return None
    if (
        existing.entity_type != entity_type
        or existing.event_type != event_type
        or (entity_id is not None and existing.entity_id != entity_id)
        or (existing.payload or {}) != payload
    ):
        raise HTTPException(
            409,
            detail={"code": "operation_reused", "message": "Operation identifier was reused"},
        )
    return existing


def add_workforce_event(
    session: Session,
    *,
    organization_id: UUID,
    entity_type: str,
    entity_id: UUID,
    operation_id: UUID,
    actor_user_id: UUID,
    event_type: str,
    payload: dict,
    occurred_at: datetime,
) -> None:
    session.add(
        StaffWorkforceEvent(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            operation_id=operation_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )
    )


def staff_labels(
    session: Session, organization_id: UUID, membership_id: UUID
) -> tuple[OrganizationMembership, User]:
    row = session.execute(
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.id == membership_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Staff member not found")
    return row


def availability_response(
    session: Session, value: StaffAvailabilityProfile
) -> StaffAvailabilityResponse:
    membership, user = staff_labels(session, value.organization_id, value.membership_id)
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    return StaffAvailabilityResponse(
        id=value.id,
        organization_id=value.organization_id,
        membership_id=membership.id,
        staff_user_id=user.id,
        staff_display_name=f"{user.first_name} {user.last_name}".strip(),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        windows=value.windows or [],
        note=value.note,
        recorded_operation_id=value.last_operation_id,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def time_off_response(session: Session, value: StaffTimeOffRequest) -> StaffTimeOffResponse:
    membership, user = staff_labels(session, value.organization_id, value.membership_id)
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    return StaffTimeOffResponse(
        id=value.id,
        organization_id=value.organization_id,
        membership_id=membership.id,
        staff_user_id=user.id,
        staff_display_name=f"{user.first_name} {user.last_name}".strip(),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        starts_at=stored_utc(value.starts_at),
        ends_at=stored_utc(value.ends_at),
        category=value.category,
        note=value.note,
        status=value.status,
        can_cancel=value.status in {"pending", "approved"},
        response_note=value.response_note,
        recorded_create_operation_id=value.create_operation_id,
        recorded_last_operation_id=value.last_operation_id,
        decided_at=stored_optional_utc(value.decided_at),
        decided_by_user_id=value.decided_by_user_id,
        cancelled_at=stored_optional_utc(value.cancelled_at),
        cancelled_by_user_id=value.cancelled_by_user_id,
        cancellation_reason=value.cancellation_reason,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def template_response(session: Session, value: StaffShiftTemplate) -> StaffShiftTemplateResponse:
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    room = room_row(session, value.organization_id, value.facility_id, value.room_id, active=False)
    return StaffShiftTemplateResponse(
        id=value.id,
        organization_id=value.organization_id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=value.room_id,
        room_name=room.name if room else None,
        name=value.name,
        weekday=value.weekday,
        start_local=value.start_local.strftime("%H:%M"),
        end_local=value.end_local.strftime("%H:%M"),
        notes=value.notes,
        is_active=value.is_active,
        recorded_create_operation_id=value.create_operation_id,
        recorded_last_operation_id=value.last_operation_id,
        created_by_user_id=value.created_by_user_id,
        deactivated_at=stored_optional_utc(value.deactivated_at),
        deactivated_by_user_id=value.deactivated_by_user_id,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def coverage_response(
    session: Session, value: StaffCoverageTargetProfile
) -> StaffCoverageTargetResponse:
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    room = room_row(session, value.organization_id, value.facility_id, value.room_id, active=False)
    return StaffCoverageTargetResponse(
        id=value.id,
        organization_id=value.organization_id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=value.room_id,
        room_name=room.name if room else None,
        windows=value.windows or [],
        recorded_last_operation_id=value.last_operation_id,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def resolve_local_datetime(facility: Facility, service_date: date, local_value: time) -> datetime:
    """Resolve one local wall time, rejecting both DST gaps and ambiguous folds."""

    zone = facility_zone(facility)
    naive = datetime.combine(service_date, local_value)
    candidates: dict[timedelta | None, datetime] = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive:
            candidates[candidate.utcoffset()] = candidate
    if not candidates:
        raise HTTPException(
            409,
            detail={"code": "nonexistent_local_time", "local_datetime": naive.isoformat()},
        )
    if len(candidates) > 1:
        raise HTTPException(
            409,
            detail={"code": "ambiguous_local_time", "local_datetime": naive.isoformat()},
        )
    return next(iter(candidates.values())).astimezone(UTC)


def schedule_matches_availability(
    session: Session, schedule: ScheduledStaffShift
) -> tuple[bool, StaffAvailabilityProfile | None]:
    profile = session.scalar(
        select(StaffAvailabilityProfile).where(
            StaffAvailabilityProfile.organization_id == schedule.organization_id,
            StaffAvailabilityProfile.membership_id == schedule.membership_id,
            StaffAvailabilityProfile.facility_id == schedule.facility_id,
            StaffAvailabilityProfile.is_specified.is_(True),
        )
    )
    if profile is None:
        return True, None
    facility = facility_row(session, schedule.organization_id, schedule.facility_id, active=False)
    zone = facility_zone(facility)
    local_start = stored_utc(schedule.scheduled_start_at).astimezone(zone)
    local_end = stored_utc(schedule.scheduled_end_at).astimezone(zone)
    if local_start.date() != local_end.date():
        return False, profile
    start_time = local_start.time().replace(tzinfo=None)
    end_time = local_end.time().replace(tzinfo=None)
    for window in profile.windows or []:
        if (
            window["weekday"] == local_start.weekday()
            and parse_local_time(window["start_local"]) <= start_time
            and parse_local_time(window["end_local"]) >= end_time
        ):
            return True, profile
    return False, profile


def approved_leave_conflict(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
    start: datetime,
    end: datetime,
) -> StaffTimeOffRequest | None:
    return session.scalar(
        select(StaffTimeOffRequest)
        .where(
            StaffTimeOffRequest.organization_id == organization_id,
            StaffTimeOffRequest.membership_id == membership_id,
            StaffTimeOffRequest.status == "approved",
            StaffTimeOffRequest.starts_at < end,
            StaffTimeOffRequest.ends_at > start,
        )
        .limit(1)
    )


def published_schedule_conflict(
    session: Session,
    request: StaffTimeOffRequest,
) -> ScheduledStaffShift | None:
    return session.scalar(
        select(ScheduledStaffShift)
        .where(
            ScheduledStaffShift.organization_id == request.organization_id,
            ScheduledStaffShift.membership_id == request.membership_id,
            ScheduledStaffShift.status == "published",
            ScheduledStaffShift.scheduled_start_at < request.ends_at,
            ScheduledStaffShift.scheduled_end_at > request.starts_at,
        )
        .limit(1)
    )
