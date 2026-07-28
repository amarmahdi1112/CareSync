"""Manager rota authoring and staff-owned schedule decisions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select

from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    BasicContextDependency,
    StaffAccessContext,
    require_complete_if_marketplace_user,
    require_permission,
)
from app.api.dependencies import SessionDependency
from app.basic.models import (
    Facility,
    OrganizationMembership,
    ScheduledStaffShift,
    ScheduledStaffShiftEvent,
    StaffShift,
)
from app.basic.notifications import notify_organization_members, notify_user
from app.basic.security import audit
from app.basic.staff_schedule_schemas import (
    ScheduledShiftAlternateResolution,
    ScheduledShiftCancel,
    ScheduledShiftCreate,
    ScheduledShiftPatch,
    ScheduledShiftPublish,
    ScheduledStaffShiftListResponse,
    ScheduledStaffShiftResponse,
    StaffScheduledShiftProposal,
    StaffScheduledShiftResponseAction,
    StaffShiftReconciliationResponse,
)
from app.basic.staff_scheduling import (
    add_event,
    aware_utc,
    clean_optional_text,
    ensure_no_overlap,
    event_payload,
    idempotent_event,
    local_day_window,
    lock_schedule_lanes,
    schedule_row,
    scheduled_shift_response,
    stored_utc,
    unscheduled_shift_response,
    validate_assignment,
    validate_interval,
)
from app.basic.staff_workforce import approved_leave_conflict, schedule_matches_availability

manager_router = APIRouter(prefix="/staff-schedules", tags=["staff rota"])
self_router = APIRouter(
    prefix="/staff/self/schedules",
    tags=["staff rota"],
    dependencies=[Depends(require_complete_if_marketplace_user)],
)
shift_context = require_permission("shift:clock")
DEFAULT_SELF_PAST_DAYS = 30
DEFAULT_SELF_FUTURE_DAYS = 90


def _canonical_payload(values: dict) -> dict:
    canonical = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            canonical[key] = aware_utc(value, key).isoformat()
        elif isinstance(value, UUID):
            canonical[key] = str(value)
        elif isinstance(value, str):
            canonical[key] = clean_optional_text(value)
        else:
            canonical[key] = value
    return canonical


def _operation_is_unused(session, organization_id: UUID, operation_id: UUID) -> None:
    if (
        session.scalar(
            select(ScheduledStaffShiftEvent.id).where(
                ScheduledStaffShiftEvent.organization_id == organization_id,
                ScheduledStaffShiftEvent.operation_id == operation_id,
            )
        )
        is not None
    ):
        raise HTTPException(
            409,
            detail={
                "code": "operation_reused",
                "message": "Operation identifier was already used for another action",
            },
        )


def _staff_user_id(session, schedule: ScheduledStaffShift) -> UUID:
    return session.scalar(
        select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == schedule.organization_id,
            OrganizationMembership.id == schedule.membership_id,
        )
    )


def _require_version(schedule: ScheduledStaffShift, expected: datetime) -> None:
    if stored_utc(schedule.updated_at) != aware_utc(expected, "expected_updated_at"):
        raise HTTPException(
            409,
            detail={
                "code": "stale_schedule",
                "message": "Scheduled shift changed since it was loaded",
                "current_updated_at": stored_utc(schedule.updated_at).isoformat(),
            },
        )


def _query_window(
    session,
    organization_id: UUID,
    *,
    facility_id: UUID | None,
    service_date: date | None,
    start_at: datetime | None,
    end_at: datetime | None,
    default_self: bool,
) -> tuple[datetime, datetime]:
    if service_date is not None:
        if facility_id is None:
            raise HTTPException(
                422,
                detail={
                    "code": "facility_required_for_date",
                    "message": "facility_id is required when filtering by local date",
                },
            )
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization_id,
                Facility.id == facility_id,
            )
        )
        if facility is None:
            raise HTTPException(404, "Facility not found")
        if start_at is not None or end_at is not None:
            raise HTTPException(422, "Use either date or start_at/end_at, not both")
        return local_day_window(facility, service_date)
    if (start_at is None) != (end_at is None):
        raise HTTPException(422, "start_at and end_at must be supplied together")
    if start_at is not None and end_at is not None:
        start = aware_utc(start_at, "start_at")
        end = aware_utc(end_at, "end_at")
        if end <= start:
            raise HTTPException(422, "end_at must follow start_at")
        if end - start > timedelta(days=366):
            raise HTTPException(422, "Schedule list range cannot exceed 366 days")
        return start, end
    if not default_self:
        raise HTTPException(
            422,
            detail={
                "code": "schedule_window_required",
                "message": "Provide date with facility_id or a bounded start_at/end_at range",
            },
        )
    now = datetime.now(UTC)
    return (
        now - timedelta(days=DEFAULT_SELF_PAST_DAYS),
        now + timedelta(days=DEFAULT_SELF_FUTURE_DAYS),
    )


def _list_statement(
    organization_id: UUID,
    start: datetime,
    end: datetime,
    *,
    facility_id: UUID | None,
    membership_id: UUID | None = None,
    staff_user_id: UUID | None = None,
    schedule_status: str | None = None,
):
    statement = select(ScheduledStaffShift).where(
        ScheduledStaffShift.organization_id == organization_id,
        ScheduledStaffShift.scheduled_start_at < end,
        ScheduledStaffShift.scheduled_end_at > start,
    )
    if facility_id is not None:
        statement = statement.where(ScheduledStaffShift.facility_id == facility_id)
    if membership_id is not None:
        statement = statement.where(ScheduledStaffShift.membership_id == membership_id)
    if staff_user_id is not None:
        statement = statement.join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == ScheduledStaffShift.organization_id)
            & (OrganizationMembership.id == ScheduledStaffShift.membership_id),
        ).where(OrganizationMembership.user_id == staff_user_id)
    if schedule_status is not None:
        if schedule_status not in {"draft", "published", "cancelled"}:
            raise HTTPException(422, "Invalid schedule status")
        statement = statement.where(ScheduledStaffShift.status == schedule_status)
    return statement.order_by(ScheduledStaffShift.scheduled_start_at, ScheduledStaffShift.id)


@manager_router.post(
    "",
    response_model=ScheduledStaffShiftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scheduled_shift(
    payload: ScheduledShiftCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    start, end = validate_interval(payload.scheduled_start_at, payload.scheduled_end_at)
    notes = clean_optional_text(payload.notes)
    canonical = event_payload(
        staff_user_id=payload.staff_user_id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
        start=start,
        end=end,
        notes=notes,
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = session.scalar(
        select(ScheduledStaffShift).where(
            ScheduledStaffShift.organization_id == context.organization.id,
            ScheduledStaffShift.create_operation_id == payload.client_operation_id,
        )
    )
    if existing is not None:
        idempotent_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            schedule_id=existing.id,
            event_type="created",
            payload=canonical,
        )
        return scheduled_shift_response(session, existing)
    _operation_is_unused(session, context.organization.id, payload.client_operation_id)
    membership, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=payload.staff_user_id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
    )
    lock_schedule_lanes(session, context.organization.id, {membership.id})
    ensure_no_overlap(session, context.organization.id, membership.id, start, end)
    now = datetime.now(UTC)
    schedule = ScheduledStaffShift(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=membership.id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
        scheduled_start_at=start,
        scheduled_end_at=end,
        notes=notes,
        create_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(schedule)
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="created",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.created",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
        details={"status": "draft"},
    )
    flush_or_conflict(session, "Scheduled shift conflicts with existing data")
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


@manager_router.get("", response_model=ScheduledStaffShiftListResponse)
def list_scheduled_shifts(
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    staff_user_id: UUID | None = None,
    service_date: Annotated[date | None, Query(alias="date")] = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    schedule_status: str | None = Query(default=None, alias="status"),
) -> ScheduledStaffShiftListResponse:
    start, end = _query_window(
        session,
        context.organization.id,
        facility_id=facility_id,
        service_date=service_date,
        start_at=start_at,
        end_at=end_at,
        default_self=False,
    )
    schedules = list(
        session.scalars(
            _list_statement(
                context.organization.id,
                start,
                end,
                facility_id=facility_id,
                staff_user_id=staff_user_id,
                schedule_status=schedule_status,
            )
        )
    )
    generated_at = datetime.now(UTC)
    return ScheduledStaffShiftListResponse(
        items=[
            scheduled_shift_response(session, schedule, now=generated_at) for schedule in schedules
        ],
        total=len(schedules),
        generated_at=generated_at,
    )


@manager_router.get("/reconciliation", response_model=StaffShiftReconciliationResponse)
def reconcile_staff_shifts(
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    service_date: Annotated[date | None, Query(alias="date")] = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> StaffShiftReconciliationResponse:
    start, end = _query_window(
        session,
        context.organization.id,
        facility_id=facility_id,
        service_date=service_date,
        start_at=start_at,
        end_at=end_at,
        default_self=False,
    )
    schedules = list(
        session.scalars(
            _list_statement(
                context.organization.id,
                start,
                end,
                facility_id=facility_id,
            )
        )
    )
    actual_statement = select(StaffShift).where(
        StaffShift.organization_id == context.organization.id,
        StaffShift.scheduled_shift_id.is_(None),
        StaffShift.clocked_in_at < end,
        (StaffShift.clocked_out_at.is_(None) | (StaffShift.clocked_out_at > start)),
    )
    if facility_id is not None:
        actual_statement = actual_statement.where(StaffShift.facility_id == facility_id)
    actual = list(session.scalars(actual_statement.order_by(StaffShift.clocked_in_at)))
    generated_at = datetime.now(UTC)
    return StaffShiftReconciliationResponse(
        scheduled=[
            scheduled_shift_response(session, schedule, now=generated_at) for schedule in schedules
        ],
        unscheduled=[unscheduled_shift_response(session, shift) for shift in actual],
        total_scheduled=len(schedules),
        total_unscheduled=len(actual),
        generated_at=generated_at,
    )


@manager_router.patch("/{schedule_id}", response_model=ScheduledStaffShiftResponse)
def update_draft_scheduled_shift(
    schedule_id: UUID,
    payload: ScheduledShiftPatch,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    canonical = _canonical_payload(
        payload.model_dump(exclude={"client_operation_id"}, exclude_unset=True)
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    schedule = schedule_row(session, context.organization.id, schedule_id, lock=True)
    existing_event = idempotent_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        schedule_id=schedule.id,
        event_type="updated",
        payload=canonical,
    )
    if existing_event is not None:
        return scheduled_shift_response(session, schedule)
    if schedule.status != "draft":
        raise HTTPException(409, detail={"code": "draft_required"})
    _require_version(schedule, payload.expected_updated_at)
    fields = payload.model_fields_set - {"client_operation_id", "expected_updated_at"}
    if not fields:
        raise HTTPException(422, "At least one draft field must be changed")
    current_user_id = _staff_user_id(session, schedule)
    staff_user_id = payload.staff_user_id if "staff_user_id" in fields else current_user_id
    facility_id = payload.facility_id if "facility_id" in fields else schedule.facility_id
    room_id = payload.room_id if "room_id" in fields else schedule.room_id
    start_value = (
        payload.scheduled_start_at
        if "scheduled_start_at" in fields
        else stored_utc(schedule.scheduled_start_at)
    )
    end_value = (
        payload.scheduled_end_at
        if "scheduled_end_at" in fields
        else stored_utc(schedule.scheduled_end_at)
    )
    if staff_user_id is None or facility_id is None or start_value is None or end_value is None:
        raise HTTPException(422, "Staff, facility, start, and end cannot be null")
    start, end = validate_interval(start_value, end_value)
    membership, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=staff_user_id,
        facility_id=facility_id,
        room_id=room_id,
    )
    lock_schedule_lanes(
        session,
        context.organization.id,
        {schedule.membership_id, membership.id},
    )
    ensure_no_overlap(
        session,
        context.organization.id,
        membership.id,
        start,
        end,
        exclude_id=schedule.id,
    )
    schedule.membership_id = membership.id
    schedule.facility_id = facility_id
    schedule.room_id = room_id
    schedule.scheduled_start_at = start
    schedule.scheduled_end_at = end
    if "notes" in fields:
        schedule.notes = clean_optional_text(payload.notes)
    now = datetime.now(UTC)
    schedule.updated_at = now
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="updated",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.updated",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
        details={"changed_fields": sorted(fields)},
    )
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


def _manager_action_payload(payload) -> dict:
    return _canonical_payload(payload.model_dump(exclude={"client_operation_id"}))


@manager_router.post("/{schedule_id}/publish", response_model=ScheduledStaffShiftResponse)
def publish_scheduled_shift(
    schedule_id: UUID,
    payload: ScheduledShiftPublish,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    override_reason = clean_optional_text(payload.availability_override_reason)
    canonical: dict = (
        {"availability_override_reason": override_reason} if override_reason is not None else {}
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    schedule = schedule_row(session, context.organization.id, schedule_id, lock=True)
    if (
        idempotent_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            schedule_id=schedule.id,
            event_type="published",
            payload=canonical,
        )
        is not None
    ):
        return scheduled_shift_response(session, schedule)
    if schedule.status != "draft":
        raise HTTPException(409, detail={"code": "draft_required"})
    staff_user_id = _staff_user_id(session, schedule)
    validate_assignment(
        session,
        context.organization.id,
        staff_user_id=staff_user_id,
        facility_id=schedule.facility_id,
        room_id=schedule.room_id,
    )
    lock_schedule_lanes(session, context.organization.id, {schedule.membership_id})
    ensure_no_overlap(
        session,
        context.organization.id,
        schedule.membership_id,
        stored_utc(schedule.scheduled_start_at),
        stored_utc(schedule.scheduled_end_at),
        exclude_id=schedule.id,
    )
    leave = approved_leave_conflict(
        session,
        context.organization.id,
        schedule.membership_id,
        stored_utc(schedule.scheduled_start_at),
        stored_utc(schedule.scheduled_end_at),
    )
    if leave is not None:
        raise HTTPException(
            409,
            detail={
                "code": "approved_time_off_conflict",
                "time_off_request_id": str(leave.id),
                "message": "Published shifts cannot overlap approved time off",
            },
        )
    matches_availability, availability = schedule_matches_availability(session, schedule)
    if not matches_availability and override_reason is None:
        raise HTTPException(
            409,
            detail={
                "code": "availability_override_required",
                "profile_id": str(availability.id),
                "facility_id": str(schedule.facility_id),
                "membership_id": str(schedule.membership_id),
                "message": "Shift falls outside the staff member's declared availability",
            },
        )
    if matches_availability and override_reason is not None:
        raise HTTPException(422, detail={"code": "availability_override_not_required"})
    now = datetime.now(UTC)
    schedule.status = "published"
    schedule.published_at = now
    schedule.published_by_user_id = context.user.id
    schedule.availability_override_reason = override_reason
    schedule.updated_at = now
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="published",
        payload=canonical,
        occurred_at=now,
    )
    notify_user(
        session,
        user_id=staff_user_id,
        organization_id=context.organization.id,
        event_key=f"staff-schedule-published:{schedule.id}",
        category="assignment",
        severity="info",
        title="New shift available",
        body="A scheduled shift is ready for your response.",
        action_path="/shifts",
        action_entity_type="staff_schedule",
        action_entity_id=schedule.id,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.published",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
        details={
            "availability_override": override_reason is not None,
            "availability_override_reason": override_reason,
        },
    )
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


@manager_router.post("/{schedule_id}/cancel", response_model=ScheduledStaffShiftResponse)
def cancel_scheduled_shift(
    schedule_id: UUID,
    payload: ScheduledShiftCancel,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    reason = clean_optional_text(payload.reason)
    if reason is None:
        raise HTTPException(422, detail={"code": "cancellation_reason_required"})
    canonical = {"reason": reason}
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    schedule = schedule_row(session, context.organization.id, schedule_id, lock=True)
    if (
        idempotent_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            schedule_id=schedule.id,
            event_type="cancelled",
            payload=canonical,
        )
        is not None
    ):
        return scheduled_shift_response(session, schedule)
    if schedule.status not in {"draft", "published"}:
        raise HTTPException(409, detail={"code": "schedule_already_cancelled"})
    if (
        session.scalar(
            select(StaffShift.id).where(
                StaffShift.organization_id == context.organization.id,
                StaffShift.scheduled_shift_id == schedule.id,
            )
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "clocked_schedule_cannot_cancel"})
    now = datetime.now(UTC)
    was_published = schedule.status == "published"
    schedule.status = "cancelled"
    schedule.cancelled_at = now
    schedule.cancelled_by_user_id = context.user.id
    schedule.cancellation_reason = reason
    schedule.updated_at = now
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="cancelled",
        payload=canonical,
        occurred_at=now,
    )
    if was_published:
        notify_user(
            session,
            user_id=_staff_user_id(session, schedule),
            organization_id=context.organization.id,
            event_key=f"staff-schedule-cancelled:{schedule.id}",
            category="assignment",
            severity="warning",
            title="Shift cancelled",
            body="A scheduled shift was cancelled by your daycare.",
            action_path="/shifts",
            action_entity_type="staff_schedule",
            action_entity_id=schedule.id,
        )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.cancelled",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
    )
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


def _alternate_resolution(
    *,
    accept: bool,
    schedule_id: UUID,
    payload: ScheduledShiftAlternateResolution,
    request: Request,
    context,
    session,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    event_type = "alternate_accepted" if accept else "alternate_rejected"
    canonical = _manager_action_payload(payload)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    schedule = schedule_row(session, context.organization.id, schedule_id, lock=True)
    if (
        idempotent_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            schedule_id=schedule.id,
            event_type=event_type,
            payload=canonical,
        )
        is not None
    ):
        return scheduled_shift_response(session, schedule)
    _require_version(schedule, payload.expected_updated_at)
    if schedule.status != "published" or schedule.response_status != "alternate_proposed":
        raise HTTPException(409, detail={"code": "alternate_proposal_required"})
    now = datetime.now(UTC)
    if accept:
        validate_assignment(
            session,
            context.organization.id,
            staff_user_id=_staff_user_id(session, schedule),
            facility_id=schedule.facility_id,
            room_id=schedule.room_id,
        )
        start, end = validate_interval(
            stored_utc(schedule.proposed_start_at), stored_utc(schedule.proposed_end_at)
        )
        lock_schedule_lanes(session, context.organization.id, {schedule.membership_id})
        ensure_no_overlap(
            session,
            context.organization.id,
            schedule.membership_id,
            start,
            end,
            exclude_id=schedule.id,
        )
        leave = approved_leave_conflict(
            session,
            context.organization.id,
            schedule.membership_id,
            start,
            end,
        )
        if leave is not None:
            raise HTTPException(
                409,
                detail={
                    "code": "approved_time_off_conflict",
                    "time_off_request_id": str(leave.id),
                    "message": "Published shifts cannot overlap approved time off",
                },
            )
        schedule.scheduled_start_at = start
        schedule.scheduled_end_at = end
        schedule.response_status = "acknowledged"
    else:
        schedule.response_status = "pending"
    schedule.response_note = clean_optional_text(payload.note) if accept else None
    schedule.proposed_start_at = None
    schedule.proposed_end_at = None
    schedule.responded_at = now if accept else None
    schedule.updated_at = now
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type=event_type,
        payload=canonical,
        occurred_at=now,
    )
    notify_user(
        session,
        user_id=_staff_user_id(session, schedule),
        organization_id=context.organization.id,
        event_key=f"staff-schedule-{event_type}:{schedule.id}",
        category="assignment",
        severity="success" if accept else "info",
        title="Alternate shift time accepted" if accept else "Alternate shift time declined",
        body=(
            "Your proposed shift time was accepted."
            if accept
            else "Your proposed shift time was declined. Please review the original shift."
        ),
        action_path="/shifts",
        action_entity_type="staff_schedule",
        action_entity_id=schedule.id,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"staff_schedule.{event_type}",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
    )
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


@manager_router.post("/{schedule_id}/alternate/accept", response_model=ScheduledStaffShiftResponse)
def accept_alternate_shift(
    schedule_id: UUID,
    payload: ScheduledShiftAlternateResolution,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    return _alternate_resolution(
        accept=True,
        schedule_id=schedule_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@manager_router.post("/{schedule_id}/alternate/reject", response_model=ScheduledStaffShiftResponse)
def reject_alternate_shift(
    schedule_id: UUID,
    payload: ScheduledShiftAlternateResolution,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    return _alternate_resolution(
        accept=False,
        schedule_id=schedule_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@self_router.get("", response_model=ScheduledStaffShiftListResponse)
def list_my_scheduled_shifts(
    context: BasicContextDependency,
    session: SessionDependency,
    facility_id: UUID | None = None,
    service_date: Annotated[date | None, Query(alias="date")] = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ScheduledStaffShiftListResponse:
    shift_context(context)
    start, end = _query_window(
        session,
        context.organization.id,
        facility_id=facility_id,
        service_date=service_date,
        start_at=start_at,
        end_at=end_at,
        default_self=True,
    )
    statement = _list_statement(
        context.organization.id,
        start,
        end,
        facility_id=facility_id,
        membership_id=context.membership.id,
    ).where(
        or_(
            ScheduledStaffShift.status == "published",
            (ScheduledStaffShift.status == "cancelled")
            & ScheduledStaffShift.published_at.is_not(None),
        )
    )
    schedules = list(session.scalars(statement))
    generated_at = datetime.now(UTC)
    return ScheduledStaffShiftListResponse(
        items=[
            scheduled_shift_response(session, schedule, now=generated_at) for schedule in schedules
        ],
        total=len(schedules),
        generated_at=generated_at,
    )


def _staff_response(
    *,
    response_status: str,
    event_type: str,
    schedule_id: UUID,
    payload,
    request: Request,
    context,
    session,
) -> ScheduledStaffShiftResponse:
    shift_context(context)
    ensure_writable(request)
    values = payload.model_dump(exclude={"client_operation_id"})
    proposed_start = values.get("proposed_start_at")
    proposed_end = values.get("proposed_end_at")
    if proposed_start is not None or proposed_end is not None:
        proposed_start, proposed_end = validate_interval(proposed_start, proposed_end)
        values["proposed_start_at"] = proposed_start
        values["proposed_end_at"] = proposed_end
    canonical = _canonical_payload(values)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    schedule = schedule_row(session, context.organization.id, schedule_id, lock=True)
    if schedule.membership_id != context.membership.id:
        raise HTTPException(404, "Scheduled shift not found")
    if (
        idempotent_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            schedule_id=schedule.id,
            event_type=event_type,
            payload=canonical,
        )
        is not None
    ):
        return scheduled_shift_response(session, schedule)
    if schedule.status != "published":
        raise HTTPException(409, detail={"code": "published_schedule_required"})
    if schedule.response_status != "pending":
        raise HTTPException(409, detail={"code": "schedule_response_already_recorded"})
    if (
        session.scalar(
            select(StaffShift.id).where(
                StaffShift.organization_id == context.organization.id,
                StaffShift.scheduled_shift_id == schedule.id,
            )
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "response_locked_after_clock_in"})
    now = datetime.now(UTC)
    schedule.response_status = response_status
    schedule.response_note = clean_optional_text(values.get("note"))
    schedule.proposed_start_at = proposed_start
    schedule.proposed_end_at = proposed_end
    schedule.responded_at = now
    schedule.updated_at = now
    add_event(
        session,
        schedule,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type=event_type,
        payload=canonical,
        occurred_at=now,
    )
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"staff:manage", "staff:manage_educators"},
        event_key=f"staff-schedule-response:{schedule.id}:{payload.client_operation_id}",
        category="assignment",
        severity="warning" if response_status in {"declined", "alternate_proposed"} else "info",
        title="Staff shift response updated",
        body="A staff member responded to a scheduled shift.",
        action_path="/staff-rota",
        action_entity_type="staff_schedule",
        action_entity_id=schedule.id,
        facility_id=schedule.facility_id,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"staff_schedule.{event_type}",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        facility_id=schedule.facility_id,
    )
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


@self_router.post("/{schedule_id}/acknowledge", response_model=ScheduledStaffShiftResponse)
def acknowledge_scheduled_shift(
    schedule_id: UUID,
    payload: StaffScheduledShiftResponseAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    return _staff_response(
        response_status="acknowledged",
        event_type="acknowledged",
        schedule_id=schedule_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@self_router.post("/{schedule_id}/decline", response_model=ScheduledStaffShiftResponse)
def decline_scheduled_shift(
    schedule_id: UUID,
    payload: StaffScheduledShiftResponseAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    return _staff_response(
        response_status="declined",
        event_type="declined",
        schedule_id=schedule_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@self_router.post("/{schedule_id}/propose-alternate", response_model=ScheduledStaffShiftResponse)
def propose_alternate_shift(
    schedule_id: UUID,
    payload: StaffScheduledShiftProposal,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    return _staff_response(
        response_status="alternate_proposed",
        event_type="alternate_proposed",
        schedule_id=schedule_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )
