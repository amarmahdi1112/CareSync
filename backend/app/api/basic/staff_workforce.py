"""Workforce planning APIs layered on the planned staff rota."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

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
    OrganizationMembership,
    Role,
    ScheduledStaffShift,
    StaffAvailabilityProfile,
    StaffCoverageTargetProfile,
    StaffOpenShift,
    StaffOpenShiftEngagement,
    StaffRotationPattern,
    StaffShiftSwapRequest,
    StaffShiftTemplate,
    StaffSubstituteProfile,
    StaffTimeOffRequest,
    StaffWorkforceEvent,
)
from app.basic.notifications import notify_organization_members, notify_user
from app.basic.room_safety import (
    foundation_enabled as room_safety_enabled,
)
from app.basic.room_safety import (
    lock_facility_projection,
    reconcile_facility_exceptions,
)
from app.basic.security import audit
from app.basic.staff_schedule_schemas import ScheduledStaffShiftResponse
from app.basic.staff_scheduling import (
    add_event,
    clean_optional_text,
    ensure_no_overlap,
    idempotent_event,
    lock_schedule_lanes,
    scheduled_shift_response,
    stored_utc,
    validate_assignment,
    validate_interval,
)
from app.basic.staff_workforce import (
    add_workforce_event,
    availability_response,
    canonical_event_payload,
    canonical_windows,
    coverage_response,
    facility_row,
    facility_zone,
    idempotent_workforce_event,
    lock_workforce_lane,
    parse_local_time,
    published_schedule_conflict,
    require_current,
    resolve_local_datetime,
    room_row,
    staff_labels,
    template_response,
    time_off_response,
    validate_time_off_interval,
)
from app.basic.staff_workforce_schemas import (
    AvailabilityReplace,
    CoverageProjectionBucket,
    CoverageProjectionResponse,
    CoverageTargetRemoveResponse,
    CoverageTargetReplace,
    OptimisticRemove,
    SelfAvailabilityEnvelope,
    ShiftTemplateCreate,
    ShiftTemplateDeactivate,
    ShiftTemplateInstantiate,
    ShiftTemplatePatch,
    StaffAvailabilityList,
    StaffCoverageTargetList,
    StaffCoverageTargetResponse,
    StaffRotaActionEntityType,
    StaffRotaActionTargetResponse,
    StaffShiftTemplateList,
    StaffShiftTemplateResponse,
    StaffTimeOffList,
    StaffTimeOffResponse,
    TimeOffAction,
    TimeOffCancel,
    TimeOffCreate,
)

manager_router = APIRouter(prefix="/staff-workforce", tags=["staff workforce"])
self_router = APIRouter(
    prefix="/staff/self",
    tags=["staff workforce"],
    dependencies=[
        Depends(require_complete_if_marketplace_user),
        Depends(require_permission("shift:clock")),
    ],
)
SELF_PAST_DAYS = 90
SELF_FUTURE_DAYS = 366
MAX_LIST_RANGE = timedelta(days=366)
MAX_PROJECTION_DAYS = 31


def _require_self_facility(context, facility_id: UUID) -> None:
    if not context.organization_wide and facility_id not in context.assigned_facility_ids:
        raise HTTPException(404, "Active assigned facility not found")


def _manageable_membership_ids(organization_id: UUID):
    return (
        select(OrganizationMembership.id)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            Role.key == "educator",
        )
    )


def _require_manager_scope(session, context, membership_id: UUID) -> None:
    if context.role.key != "administrator":
        return
    if (
        session.scalar(
            _manageable_membership_ids(context.organization.id).where(
                OrganizationMembership.id == membership_id
            )
        )
        is None
    ):
        raise HTTPException(404, "Staff workforce record not found")


def _availability_profile(session, organization_id, membership_id, facility_id, *, lock=False):
    statement = select(StaffAvailabilityProfile).where(
        StaffAvailabilityProfile.organization_id == organization_id,
        StaffAvailabilityProfile.membership_id == membership_id,
        StaffAvailabilityProfile.facility_id == facility_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _time_off_row(session, organization_id, request_id, *, lock=False):
    statement = select(StaffTimeOffRequest).where(
        StaffTimeOffRequest.organization_id == organization_id,
        StaffTimeOffRequest.id == request_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Time-off request not found")
    return value


def _template_row(session, organization_id, template_id, *, lock=False):
    statement = select(StaffShiftTemplate).where(
        StaffShiftTemplate.organization_id == organization_id,
        StaffShiftTemplate.id == template_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Shift template not found")
    return value


def _list_window(
    start_at: datetime | None, end_at: datetime | None, *, self_default: bool
) -> tuple[datetime, datetime]:
    if start_at is None and end_at is None and self_default:
        now = datetime.now(UTC)
        return now - timedelta(days=SELF_PAST_DAYS), now + timedelta(days=SELF_FUTURE_DAYS)
    if start_at is None or end_at is None:
        raise HTTPException(422, detail={"code": "bounded_window_required"})
    start, end = validate_time_off_interval(start_at, end_at)
    return start, end


def _staff_rota_action_target_not_found() -> None:
    raise HTTPException(404, "Staff rota action target not found")


@manager_router.get(
    "/action-target/{entity_type}/{entity_id}",
    response_model=StaffRotaActionTargetResponse,
)
def resolve_staff_rota_action_target(
    entity_type: StaffRotaActionEntityType,
    entity_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffRotaActionTargetResponse:
    """Resolve an exact notification target without trusting routing metadata.

    The notification contains only an entity kind and identifier.  Facility,
    time range, parent linkage and current visibility are re-read from the
    tenant-scoped canonical record before the portal changes its filters.
    """

    organization_id = context.organization.id
    facility_id: UUID
    starts_at: datetime | None = None
    parent_entity_id: UUID | None = None
    membership_id: UUID | None = None
    visible = True

    if entity_type == "staff_availability":
        value = session.scalar(
            select(StaffAvailabilityProfile).where(
                StaffAvailabilityProfile.organization_id == organization_id,
                StaffAvailabilityProfile.id == entity_id,
            )
        )
        if value is None:
            _staff_rota_action_target_not_found()
        _require_manager_scope(session, context, value.membership_id)
        facility_id = value.facility_id
        membership_id = value.membership_id
        visible = bool(value.is_specified)
    elif entity_type == "staff_time_off":
        value = session.scalar(
            select(StaffTimeOffRequest).where(
                StaffTimeOffRequest.organization_id == organization_id,
                StaffTimeOffRequest.id == entity_id,
            )
        )
        if value is None:
            _staff_rota_action_target_not_found()
        _require_manager_scope(session, context, value.membership_id)
        facility_id = value.facility_id
        membership_id = value.membership_id
        starts_at = stored_utc(value.starts_at)
    elif entity_type == "staff_rotation_pattern":
        value = session.scalar(
            select(StaffRotationPattern).where(
                StaffRotationPattern.organization_id == organization_id,
                StaffRotationPattern.id == entity_id,
            )
        )
        if value is None:
            _staff_rota_action_target_not_found()
        facility_id = value.facility_id
    elif entity_type == "staff_open_shift":
        value = session.scalar(
            select(StaffOpenShift).where(
                StaffOpenShift.organization_id == organization_id,
                StaffOpenShift.id == entity_id,
            )
        )
        if value is None:
            _staff_rota_action_target_not_found()
        facility_id = value.facility_id
        starts_at = stored_utc(value.starts_at)
    elif entity_type == "staff_open_shift_engagement":
        row = session.execute(
            select(StaffOpenShiftEngagement, StaffOpenShift)
            .join(
                StaffOpenShift,
                (StaffOpenShift.organization_id == StaffOpenShiftEngagement.organization_id)
                & (StaffOpenShift.id == StaffOpenShiftEngagement.open_shift_id),
            )
            .where(
                StaffOpenShiftEngagement.organization_id == organization_id,
                StaffOpenShiftEngagement.id == entity_id,
            )
        ).one_or_none()
        if row is None:
            _staff_rota_action_target_not_found()
        engagement, open_shift = row
        _require_manager_scope(session, context, engagement.membership_id)
        facility_id = open_shift.facility_id
        starts_at = stored_utc(open_shift.starts_at)
        parent_entity_id = open_shift.id
        membership_id = engagement.membership_id
    elif entity_type == "staff_substitute_profile":
        value = session.scalar(
            select(StaffSubstituteProfile).where(
                StaffSubstituteProfile.organization_id == organization_id,
                StaffSubstituteProfile.id == entity_id,
            )
        )
        if value is None:
            _staff_rota_action_target_not_found()
        _require_manager_scope(session, context, value.membership_id)
        facility_id = value.facility_id
        membership_id = value.membership_id
        visible = bool(value.is_specified and value.is_opted_in)
    else:
        row = session.execute(
            select(StaffShiftSwapRequest, ScheduledStaffShift)
            .join(
                ScheduledStaffShift,
                (ScheduledStaffShift.organization_id == StaffShiftSwapRequest.organization_id)
                & (ScheduledStaffShift.id == StaffShiftSwapRequest.requester_schedule_id),
            )
            .where(
                StaffShiftSwapRequest.organization_id == organization_id,
                StaffShiftSwapRequest.id == entity_id,
            )
        ).one_or_none()
        if row is None:
            _staff_rota_action_target_not_found()
        swap, source_schedule = row
        _require_manager_scope(session, context, swap.requester_membership_id)
        _require_manager_scope(session, context, swap.counterparty_membership_id)
        facility_id = swap.facility_id
        starts_at = stored_utc(source_schedule.scheduled_start_at)

    # Resolving a historical record is allowed, but the referenced facility
    # must still belong to this organization. The client separately requires
    # an active facility before it can focus a live manager workspace.
    facility_row(session, organization_id, facility_id, active=False)
    return StaffRotaActionTargetResponse(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        facility_id=facility_id,
        starts_at=starts_at,
        parent_entity_id=parent_entity_id,
        membership_id=membership_id,
        visible=visible,
    )


@self_router.get("/availability", response_model=SelfAvailabilityEnvelope)
def get_my_availability(
    facility_id: UUID,
    context: BasicContextDependency,
    session: SessionDependency,
) -> SelfAvailabilityEnvelope:
    _require_self_facility(context, facility_id)
    facility_row(session, context.organization.id, facility_id)
    value = _availability_profile(
        session, context.organization.id, context.membership.id, facility_id
    )
    return SelfAvailabilityEnvelope(
        profile=availability_response(session, value) if value and value.is_specified else None,
        recorded_operation_id=value.last_operation_id if value else None,
        generated_at=datetime.now(UTC),
    )


@self_router.put("/availability/{facility_id}", response_model=SelfAvailabilityEnvelope)
def replace_my_availability(
    facility_id: UUID,
    payload: AvailabilityReplace,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> SelfAvailabilityEnvelope:
    ensure_writable(request)
    _require_self_facility(context, facility_id)
    facility_row(session, context.organization.id, facility_id)
    windows = canonical_windows(payload.windows)
    note = clean_optional_text(payload.note)
    canonical = canonical_event_payload(
        {"facility_id": facility_id, "windows": windows, "note": note}
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing_event = idempotent_workforce_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_availability",
        event_type="replaced",
        payload=canonical,
    )
    if existing_event is not None:
        value = _availability_profile(
            session, context.organization.id, context.membership.id, facility_id
        )
        if (
            value is None
            or not value.is_specified
            or existing_event.entity_id != value.id
            or value.last_operation_id != payload.client_operation_id
        ):
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return SelfAvailabilityEnvelope(
            profile=availability_response(session, value),
            recorded_operation_id=value.last_operation_id,
            generated_at=datetime.now(UTC),
        )
    lock_schedule_lanes(session, context.organization.id, {context.membership.id})
    value = _availability_profile(
        session, context.organization.id, context.membership.id, facility_id, lock=True
    )
    require_current(
        value.updated_at if value else datetime.now(UTC),
        payload.expected_updated_at,
        absent=value is None or not value.is_specified,
    )
    now = datetime.now(UTC)
    if value is None:
        value = StaffAvailabilityProfile(
            id=uuid4(),
            organization_id=context.organization.id,
            membership_id=context.membership.id,
            facility_id=facility_id,
            windows=windows,
            note=note,
            last_operation_id=payload.client_operation_id,
            created_at=now,
            updated_at=now,
        )
        session.add(value)
    else:
        value.windows = windows
        value.note = note
        value.is_specified = True
        value.last_operation_id = payload.client_operation_id
        value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_availability",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="replaced",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_availability.replaced",
        entity_type="staff_availability",
        entity_id=value.id,
        facility_id=facility_id,
        details={"window_count": len(windows)},
    )
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"staff:manage", "staff:manage_educators"},
        event_key=f"staff-availability:{value.id}:{payload.client_operation_id}",
        category="assignment",
        severity="info",
        title="Staff availability updated",
        body="A staff member updated their weekly availability.",
        action_path="/staff-rota",
        action_entity_type="staff_availability",
        action_entity_id=value.id,
        facility_id=facility_id,
    )
    flush_or_conflict(session, "Availability profile conflicts with existing data")
    commit_in_context(session, context)
    return SelfAvailabilityEnvelope(
        profile=availability_response(session, value),
        recorded_operation_id=value.last_operation_id,
        generated_at=now,
    )


@self_router.delete("/availability/{facility_id}", response_model=SelfAvailabilityEnvelope)
def remove_my_availability(
    facility_id: UUID,
    payload: OptimisticRemove,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> SelfAvailabilityEnvelope:
    ensure_writable(request)
    _require_self_facility(context, facility_id)
    canonical = canonical_event_payload({"facility_id": facility_id})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing_event = idempotent_workforce_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_availability",
        event_type="removed",
        payload=canonical,
    )
    if existing_event is not None:
        if existing_event.actor_user_id != context.user.id:
            raise HTTPException(404, "Availability profile not found")
        value = _availability_profile(
            session, context.organization.id, context.membership.id, facility_id
        )
        if (
            value is None
            or value.is_specified
            or value.last_operation_id != payload.client_operation_id
        ):
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return SelfAvailabilityEnvelope(
            profile=None,
            recorded_operation_id=payload.client_operation_id,
            generated_at=datetime.now(UTC),
        )
    lock_schedule_lanes(session, context.organization.id, {context.membership.id})
    value = _availability_profile(
        session, context.organization.id, context.membership.id, facility_id, lock=True
    )
    if value is None or not value.is_specified:
        raise HTTPException(404, "Availability profile not found")
    require_current(value.updated_at, payload.expected_updated_at)
    entity_id = value.id
    now = datetime.now(UTC)
    value.windows = []
    value.note = None
    value.is_specified = False
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_availability",
        entity_id=entity_id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="removed",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_availability.removed",
        entity_type="staff_availability",
        entity_id=entity_id,
        facility_id=facility_id,
    )
    commit_in_context(session, context)
    return SelfAvailabilityEnvelope(
        profile=None, recorded_operation_id=payload.client_operation_id, generated_at=now
    )


@manager_router.get("/availability", response_model=StaffAvailabilityList)
def list_availability(
    facility_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
    staff_user_id: UUID | None = None,
) -> StaffAvailabilityList:
    facility_row(session, context.organization.id, facility_id, active=False)
    statement = select(StaffAvailabilityProfile).where(
        StaffAvailabilityProfile.organization_id == context.organization.id,
        StaffAvailabilityProfile.facility_id == facility_id,
        StaffAvailabilityProfile.is_specified.is_(True),
    )
    if context.role.key == "administrator":
        statement = statement.where(
            StaffAvailabilityProfile.membership_id.in_(
                _manageable_membership_ids(context.organization.id)
            )
        )
    if staff_user_id is not None:
        statement = statement.join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == StaffAvailabilityProfile.organization_id)
            & (OrganizationMembership.id == StaffAvailabilityProfile.membership_id),
        ).where(OrganizationMembership.user_id == staff_user_id)
    values = list(session.scalars(statement.order_by(StaffAvailabilityProfile.membership_id)))
    return StaffAvailabilityList(
        items=[availability_response(session, item) for item in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


def _time_off_statement(
    organization_id: UUID,
    start: datetime,
    end: datetime,
    *,
    membership_id: UUID | None = None,
    facility_id: UUID | None = None,
    staff_user_id: UUID | None = None,
    request_status: str | None = None,
):
    statement = select(StaffTimeOffRequest).where(
        StaffTimeOffRequest.organization_id == organization_id,
        StaffTimeOffRequest.starts_at < end,
        StaffTimeOffRequest.ends_at > start,
    )
    if membership_id is not None:
        statement = statement.where(StaffTimeOffRequest.membership_id == membership_id)
    if facility_id is not None:
        statement = statement.where(StaffTimeOffRequest.facility_id == facility_id)
    if staff_user_id is not None:
        statement = statement.join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == StaffTimeOffRequest.organization_id)
            & (OrganizationMembership.id == StaffTimeOffRequest.membership_id),
        ).where(OrganizationMembership.user_id == staff_user_id)
    if request_status is not None:
        if request_status not in {"pending", "approved", "declined", "cancelled"}:
            raise HTTPException(422, detail={"code": "invalid_time_off_status"})
        statement = statement.where(StaffTimeOffRequest.status == request_status)
    return statement.order_by(StaffTimeOffRequest.starts_at, StaffTimeOffRequest.id)


@self_router.post(
    "/time-off", response_model=StaffTimeOffResponse, status_code=status.HTTP_201_CREATED
)
def create_my_time_off(
    payload: TimeOffCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> StaffTimeOffResponse:
    ensure_writable(request)
    _require_self_facility(context, payload.facility_id)
    facility_row(session, context.organization.id, payload.facility_id)
    start, end = validate_time_off_interval(payload.starts_at, payload.ends_at)
    note = clean_optional_text(payload.note)
    canonical = canonical_event_payload(
        {
            "facility_id": payload.facility_id,
            "starts_at": start,
            "ends_at": end,
            "category": payload.category,
            "note": note,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = session.scalar(
        select(StaffTimeOffRequest).where(
            StaffTimeOffRequest.organization_id == context.organization.id,
            StaffTimeOffRequest.create_operation_id == payload.client_operation_id,
        )
    )
    if existing is not None:
        if existing.membership_id != context.membership.id:
            raise HTTPException(409, detail={"code": "operation_reused"})
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_time_off",
            entity_id=existing.id,
            event_type="requested",
            payload=canonical,
        )
        return time_off_response(session, existing)
    if (
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_time_off",
            event_type="requested",
            payload=canonical,
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "operation_reused"})
    lock_schedule_lanes(session, context.organization.id, {context.membership.id})
    overlap = session.scalar(
        select(StaffTimeOffRequest.id)
        .where(
            StaffTimeOffRequest.organization_id == context.organization.id,
            StaffTimeOffRequest.membership_id == context.membership.id,
            StaffTimeOffRequest.status.in_(["pending", "approved"]),
            StaffTimeOffRequest.starts_at < end,
            StaffTimeOffRequest.ends_at > start,
        )
        .limit(1)
    )
    if overlap is not None:
        raise HTTPException(
            409,
            detail={"code": "overlapping_time_off_request", "time_off_request_id": str(overlap)},
        )
    now = datetime.now(UTC)
    value = StaffTimeOffRequest(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=payload.facility_id,
        starts_at=start,
        ends_at=end,
        category=payload.category,
        note=note,
        status="pending",
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_time_off",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="requested",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_time_off.requested",
        entity_type="staff_time_off",
        entity_id=value.id,
        facility_id=value.facility_id,
        details={"category": value.category},
    )
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"staff:manage", "staff:manage_educators"},
        event_key=f"staff-time-off-requested:{value.id}",
        category="assignment",
        severity="info",
        title="Time-off request submitted",
        body="A staff member submitted a time-off request.",
        action_path="/staff-rota",
        action_entity_type="staff_time_off",
        action_entity_id=value.id,
        facility_id=value.facility_id,
    )
    flush_or_conflict(session, "Time-off request conflicts with existing data")
    commit_in_context(session, context)
    return time_off_response(session, value)


@self_router.get("/time-off", response_model=StaffTimeOffList)
def list_my_time_off(
    context: BasicContextDependency,
    session: SessionDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    facility_id: UUID | None = None,
    request_status: str | None = Query(default=None, alias="status"),
) -> StaffTimeOffList:
    start, end = _list_window(start_at, end_at, self_default=True)
    values = list(
        session.scalars(
            _time_off_statement(
                context.organization.id,
                start,
                end,
                membership_id=context.membership.id,
                facility_id=facility_id,
                request_status=request_status,
            )
        )
    )
    return StaffTimeOffList(
        items=[time_off_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


def _cancel_time_off(
    *,
    request_id: UUID,
    payload: TimeOffCancel,
    request: Request,
    context,
    session,
    staff_owned: bool,
) -> StaffTimeOffResponse:
    ensure_writable(request)
    reason = clean_optional_text(payload.reason)
    if reason is None:
        raise HTTPException(422, detail={"code": "cancellation_reason_required"})
    canonical = canonical_event_payload({"reason": reason})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    value = _time_off_row(session, context.organization.id, request_id, lock=True)
    if staff_owned and value.membership_id != context.membership.id:
        raise HTTPException(404, "Time-off request not found")
    if not staff_owned:
        _require_manager_scope(session, context, value.membership_id)
    if (
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_time_off",
            entity_id=value.id,
            event_type="cancelled",
            payload=canonical,
        )
        is not None
    ):
        if value.last_operation_id != payload.client_operation_id:
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return time_off_response(session, value)
    require_current(value.updated_at, payload.expected_updated_at)
    if value.status not in {"pending", "approved"}:
        raise HTTPException(409, detail={"code": "time_off_not_cancellable"})
    lock_schedule_lanes(session, context.organization.id, {value.membership_id})
    now = datetime.now(UTC)
    value.status = "cancelled"
    value.cancelled_at = now
    value.cancelled_by_user_id = context.user.id
    value.cancellation_reason = reason
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_time_off",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="cancelled",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_time_off.cancelled",
        entity_type="staff_time_off",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    if staff_owned:
        notify_organization_members(
            session,
            organization_id=context.organization.id,
            permission_keys={"staff:manage", "staff:manage_educators"},
            event_key=f"staff-time-off-cancelled:{value.id}:{payload.client_operation_id}",
            category="assignment",
            severity="info",
            title="Time-off request cancelled",
            body="A staff member cancelled a time-off request.",
            action_path="/staff-rota",
            action_entity_type="staff_time_off",
            action_entity_id=value.id,
            facility_id=value.facility_id,
        )
    else:
        _, staff_user = staff_labels(session, value.organization_id, value.membership_id)
        notify_user(
            session,
            user_id=staff_user.id,
            organization_id=context.organization.id,
            event_key=f"staff-time-off-manager-cancelled:{value.id}",
            category="assignment",
            severity="warning",
            title="Time off cancelled",
            body="Your daycare cancelled a time-off request.",
            action_path="/shifts/time-off",
            action_entity_type="staff_time_off",
            action_entity_id=value.id,
        )
    commit_in_context(session, context)
    return time_off_response(session, value)


@self_router.post("/time-off/{request_id}/cancel", response_model=StaffTimeOffResponse)
def cancel_my_time_off(
    request_id: UUID,
    payload: TimeOffCancel,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> StaffTimeOffResponse:
    return _cancel_time_off(
        request_id=request_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        staff_owned=True,
    )


@manager_router.get("/time-off", response_model=StaffTimeOffList)
def list_time_off(
    start_at: datetime,
    end_at: datetime,
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    staff_user_id: UUID | None = None,
    request_status: str | None = Query(default=None, alias="status"),
) -> StaffTimeOffList:
    start, end = _list_window(start_at, end_at, self_default=False)
    statement = _time_off_statement(
        context.organization.id,
        start,
        end,
        facility_id=facility_id,
        staff_user_id=staff_user_id,
        request_status=request_status,
    )
    if context.role.key == "administrator":
        statement = statement.where(
            StaffTimeOffRequest.membership_id.in_(
                _manageable_membership_ids(context.organization.id)
            )
        )
    values = list(session.scalars(statement))
    return StaffTimeOffList(
        items=[time_off_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


def _decide_time_off(
    *,
    approve: bool,
    request_id: UUID,
    payload: TimeOffAction,
    request: Request,
    context,
    session,
) -> StaffTimeOffResponse:
    ensure_writable(request)
    event_type = "approved" if approve else "declined"
    note = clean_optional_text(payload.note)
    canonical = canonical_event_payload({"note": note})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    value = _time_off_row(session, context.organization.id, request_id, lock=True)
    _require_manager_scope(session, context, value.membership_id)
    if (
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_time_off",
            entity_id=value.id,
            event_type=event_type,
            payload=canonical,
        )
        is not None
    ):
        if value.last_operation_id != payload.client_operation_id:
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return time_off_response(session, value)
    require_current(value.updated_at, payload.expected_updated_at)
    if value.status != "pending":
        raise HTTPException(409, detail={"code": "pending_time_off_required"})
    lock_schedule_lanes(session, context.organization.id, {value.membership_id})
    if approve:
        conflict = published_schedule_conflict(session, value)
        if conflict is not None:
            raise HTTPException(
                409,
                detail={
                    "code": "published_schedule_conflict",
                    "scheduled_shift_id": str(conflict.id),
                    "message": "Published shifts must be resolved before approving leave",
                },
            )
    now = datetime.now(UTC)
    value.status = event_type
    value.response_note = note
    value.decided_at = now
    value.decided_by_user_id = context.user.id
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_time_off",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type=event_type,
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"staff_time_off.{event_type}",
        entity_type="staff_time_off",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _, staff_user = staff_labels(session, value.organization_id, value.membership_id)
    notify_user(
        session,
        user_id=staff_user.id,
        organization_id=context.organization.id,
        event_key=f"staff-time-off-{event_type}:{value.id}",
        category="assignment",
        severity="success" if approve else "warning",
        title="Time off approved" if approve else "Time off declined",
        body=(
            "Your time-off request was approved."
            if approve
            else "Your time-off request was declined."
        ),
        action_path="/shifts/time-off",
        action_entity_type="staff_time_off",
        action_entity_id=value.id,
    )
    commit_in_context(session, context)
    return time_off_response(session, value)


@manager_router.post("/time-off/{request_id}/approve", response_model=StaffTimeOffResponse)
def approve_time_off(
    request_id: UUID,
    payload: TimeOffAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffTimeOffResponse:
    return _decide_time_off(
        approve=True,
        request_id=request_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@manager_router.post("/time-off/{request_id}/decline", response_model=StaffTimeOffResponse)
def decline_time_off(
    request_id: UUID,
    payload: TimeOffAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffTimeOffResponse:
    return _decide_time_off(
        approve=False,
        request_id=request_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
    )


@manager_router.post("/time-off/{request_id}/cancel", response_model=StaffTimeOffResponse)
def cancel_time_off(
    request_id: UUID,
    payload: TimeOffCancel,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffTimeOffResponse:
    return _cancel_time_off(
        request_id=request_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        staff_owned=False,
    )


@manager_router.post(
    "/templates",
    response_model=StaffShiftTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shift_template(
    payload: ShiftTemplateCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffShiftTemplateResponse:
    ensure_writable(request)
    facility_row(session, context.organization.id, payload.facility_id)
    room_row(session, context.organization.id, payload.facility_id, payload.room_id)
    name = clean_optional_text(payload.name)
    if name is None:
        raise HTTPException(422, detail={"code": "template_name_required"})
    notes = clean_optional_text(payload.notes)
    start_local = parse_local_time(payload.start_local)
    end_local = parse_local_time(payload.end_local)
    if end_local <= start_local:
        raise HTTPException(422, detail={"code": "invalid_template_interval"})
    canonical = canonical_event_payload(
        {
            "facility_id": payload.facility_id,
            "room_id": payload.room_id,
            "name": name,
            "weekday": payload.weekday,
            "start_local": payload.start_local,
            "end_local": payload.end_local,
            "notes": notes,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing = session.scalar(
        select(StaffShiftTemplate).where(
            StaffShiftTemplate.organization_id == context.organization.id,
            StaffShiftTemplate.create_operation_id == payload.client_operation_id,
        )
    )
    if existing is not None:
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_shift_template",
            entity_id=existing.id,
            event_type="created",
            payload=canonical,
        )
        return template_response(session, existing)
    idempotent_workforce_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_template",
        event_type="created",
        payload=canonical,
    )
    now = datetime.now(UTC)
    value = StaffShiftTemplate(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
        name=name,
        weekday=payload.weekday,
        start_local=start_local,
        end_local=end_local,
        notes=notes,
        is_active=True,
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_shift_template",
        entity_id=value.id,
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
        action="staff_shift_template.created",
        entity_type="staff_shift_template",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    flush_or_conflict(session, "Shift template conflicts with existing data")
    commit_in_context(session, context)
    return template_response(session, value)


@manager_router.get("/templates", response_model=StaffShiftTemplateList)
def list_shift_templates(
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    room_id: UUID | None = None,
    active_only: bool = True,
) -> StaffShiftTemplateList:
    statement = select(StaffShiftTemplate).where(
        StaffShiftTemplate.organization_id == context.organization.id
    )
    if facility_id is not None:
        statement = statement.where(StaffShiftTemplate.facility_id == facility_id)
    if room_id is not None:
        statement = statement.where(StaffShiftTemplate.room_id == room_id)
    if active_only:
        statement = statement.where(StaffShiftTemplate.is_active.is_(True))
    values = list(
        session.scalars(
            statement.order_by(
                StaffShiftTemplate.facility_id,
                StaffShiftTemplate.weekday,
                StaffShiftTemplate.start_local,
                StaffShiftTemplate.name,
            )
        )
    )
    return StaffShiftTemplateList(
        items=[template_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@manager_router.patch("/templates/{template_id}", response_model=StaffShiftTemplateResponse)
def update_shift_template(
    template_id: UUID,
    payload: ShiftTemplatePatch,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffShiftTemplateResponse:
    ensure_writable(request)
    fields = payload.model_fields_set - {"client_operation_id", "expected_updated_at"}
    if not fields:
        raise HTTPException(422, detail={"code": "template_change_required"})
    raw = payload.model_dump(
        exclude={"client_operation_id", "expected_updated_at"}, exclude_unset=True
    )
    canonical = canonical_event_payload(raw)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    value = _template_row(session, context.organization.id, template_id, lock=True)
    if (
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_shift_template",
            entity_id=value.id,
            event_type="updated",
            payload=canonical,
        )
        is not None
    ):
        if value.last_operation_id != payload.client_operation_id:
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return template_response(session, value)
    require_current(value.updated_at, payload.expected_updated_at)
    if not value.is_active:
        raise HTTPException(409, detail={"code": "active_template_required"})
    facility_id = payload.facility_id if "facility_id" in fields else value.facility_id
    room_id = payload.room_id if "room_id" in fields else value.room_id
    if facility_id is None:
        raise HTTPException(422, detail={"code": "facility_required"})
    facility_row(session, context.organization.id, facility_id)
    room_row(session, context.organization.id, facility_id, room_id)
    name = clean_optional_text(payload.name) if "name" in fields else value.name
    if name is None:
        raise HTTPException(422, detail={"code": "template_name_required"})
    start_local = (
        parse_local_time(payload.start_local) if "start_local" in fields else value.start_local
    )
    end_local = parse_local_time(payload.end_local) if "end_local" in fields else value.end_local
    if end_local <= start_local:
        raise HTTPException(422, detail={"code": "invalid_template_interval"})
    value.facility_id = facility_id
    value.room_id = room_id
    value.name = name
    value.weekday = payload.weekday if "weekday" in fields else value.weekday
    value.start_local = start_local
    value.end_local = end_local
    if "notes" in fields:
        value.notes = clean_optional_text(payload.notes)
    now = datetime.now(UTC)
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_shift_template",
        entity_id=value.id,
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
        action="staff_shift_template.updated",
        entity_type="staff_shift_template",
        entity_id=value.id,
        facility_id=value.facility_id,
        details={"changed_fields": sorted(fields)},
    )
    commit_in_context(session, context)
    return template_response(session, value)


@manager_router.post(
    "/templates/{template_id}/deactivate", response_model=StaffShiftTemplateResponse
)
def deactivate_shift_template(
    template_id: UUID,
    payload: ShiftTemplateDeactivate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffShiftTemplateResponse:
    ensure_writable(request)
    canonical: dict = {}
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    value = _template_row(session, context.organization.id, template_id, lock=True)
    if (
        idempotent_workforce_event(
            session,
            context.organization.id,
            payload.client_operation_id,
            entity_type="staff_shift_template",
            entity_id=value.id,
            event_type="deactivated",
            payload=canonical,
        )
        is not None
    ):
        if value.last_operation_id != payload.client_operation_id:
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return template_response(session, value)
    require_current(value.updated_at, payload.expected_updated_at)
    if not value.is_active:
        raise HTTPException(409, detail={"code": "template_already_inactive"})
    now = datetime.now(UTC)
    value.is_active = False
    value.deactivated_at = now
    value.deactivated_by_user_id = context.user.id
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_shift_template",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="deactivated",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_shift_template.deactivated",
        entity_type="staff_shift_template",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    commit_in_context(session, context)
    return template_response(session, value)


@manager_router.post(
    "/templates/{template_id}/instantiate", response_model=ScheduledStaffShiftResponse
)
def instantiate_shift_template(
    template_id: UUID,
    payload: ShiftTemplateInstantiate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ScheduledStaffShiftResponse:
    ensure_writable(request)
    requested_notes = clean_optional_text(payload.notes)
    canonical = canonical_event_payload(
        {
            "template_id": template_id,
            "staff_user_id": payload.staff_user_id,
            "service_date": payload.service_date,
            "notes": requested_notes,
        }
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
    if (
        session.scalar(
            select(StaffWorkforceEvent.id).where(
                StaffWorkforceEvent.organization_id == context.organization.id,
                StaffWorkforceEvent.operation_id == payload.client_operation_id,
            )
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "operation_reused"})
    template = _template_row(session, context.organization.id, template_id, lock=True)
    if not template.is_active:
        raise HTTPException(409, detail={"code": "active_template_required"})
    if payload.service_date.weekday() != template.weekday:
        raise HTTPException(
            422,
            detail={
                "code": "template_weekday_mismatch",
                "expected_weekday": template.weekday,
            },
        )
    facility = facility_row(session, context.organization.id, template.facility_id)
    start = resolve_local_datetime(facility, payload.service_date, template.start_local)
    end = resolve_local_datetime(facility, payload.service_date, template.end_local)
    start, end = validate_interval(start, end)
    notes = requested_notes if payload.notes is not None else template.notes
    membership, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=payload.staff_user_id,
        facility_id=template.facility_id,
        room_id=template.room_id,
    )
    lock_schedule_lanes(session, context.organization.id, {membership.id})
    ensure_no_overlap(session, context.organization.id, membership.id, start, end)
    now = datetime.now(UTC)
    schedule = ScheduledStaffShift(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=membership.id,
        facility_id=template.facility_id,
        room_id=template.room_id,
        scheduled_start_at=start,
        scheduled_end_at=end,
        notes=notes,
        status="draft",
        response_status="pending",
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
        action="staff_shift_template.instantiated",
        entity_type="staff_shift_template",
        entity_id=template.id,
        facility_id=template.facility_id,
        details={"scheduled_shift_id": str(schedule.id)},
    )
    flush_or_conflict(session, "Shift template instantiation conflicts with existing data")
    commit_in_context(session, context)
    return scheduled_shift_response(session, schedule)


def _coverage_profile(
    session,
    organization_id: UUID,
    facility_id: UUID,
    room_id: UUID | None,
    *,
    lock: bool = False,
):
    statement = select(StaffCoverageTargetProfile).where(
        StaffCoverageTargetProfile.organization_id == organization_id,
        StaffCoverageTargetProfile.facility_id == facility_id,
    )
    statement = (
        statement.where(StaffCoverageTargetProfile.room_id.is_(None))
        if room_id is None
        else statement.where(StaffCoverageTargetProfile.room_id == room_id)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


@manager_router.get("/coverage-targets", response_model=StaffCoverageTargetList)
def list_coverage_targets(
    facility_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffCoverageTargetList:
    facility_row(session, context.organization.id, facility_id, active=False)
    values = list(
        session.scalars(
            select(StaffCoverageTargetProfile)
            .where(
                StaffCoverageTargetProfile.organization_id == context.organization.id,
                StaffCoverageTargetProfile.facility_id == facility_id,
                StaffCoverageTargetProfile.is_specified.is_(True),
            )
            .order_by(StaffCoverageTargetProfile.room_id)
        )
    )
    return StaffCoverageTargetList(
        items=[coverage_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@manager_router.put("/coverage-targets/{facility_id}", response_model=StaffCoverageTargetResponse)
def replace_coverage_target(
    facility_id: UUID,
    payload: CoverageTargetReplace,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
    room_id: UUID | None = None,
) -> StaffCoverageTargetResponse:
    ensure_writable(request)
    facility_row(session, context.organization.id, facility_id)
    room_row(session, context.organization.id, facility_id, room_id)
    windows = canonical_windows(payload.windows, coverage=True)
    canonical = canonical_event_payload(
        {"facility_id": facility_id, "room_id": room_id, "windows": windows}
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing_event = idempotent_workforce_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_coverage_target",
        event_type="replaced",
        payload=canonical,
    )
    if existing_event is not None:
        value = _coverage_profile(session, context.organization.id, facility_id, room_id)
        if (
            value is None
            or not value.is_specified
            or value.id != existing_event.entity_id
            or value.last_operation_id != payload.client_operation_id
        ):
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return coverage_response(session, value)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility_id
        )
    lock_workforce_lane(
        session,
        context.organization.id,
        f"coverage:{facility_id}:{room_id or 'facility'}",
    )
    value = _coverage_profile(session, context.organization.id, facility_id, room_id, lock=True)
    require_current(
        value.updated_at if value else datetime.now(UTC),
        payload.expected_updated_at,
        absent=value is None or not value.is_specified,
    )
    now = datetime.now(UTC)
    if value is None:
        value = StaffCoverageTargetProfile(
            id=uuid4(),
            organization_id=context.organization.id,
            facility_id=facility_id,
            room_id=room_id,
            windows=windows,
            is_specified=True,
            last_operation_id=payload.client_operation_id,
            created_at=now,
            updated_at=now,
        )
        session.add(value)
    else:
        value.windows = windows
        value.is_specified = True
        value.last_operation_id = payload.client_operation_id
        value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_coverage_target",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="replaced",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_coverage_target.replaced",
        entity_type="staff_coverage_target",
        entity_id=value.id,
        facility_id=facility_id,
        details={"room_id": str(room_id) if room_id else None, "window_count": len(windows)},
    )
    flush_or_conflict(session, "Coverage target conflicts with existing data")
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility_id,
            cause_entity_type="staff_coverage_target",
            cause_entity_id=value.id,
        )
    commit_in_context(session, context)
    return coverage_response(session, value)


@manager_router.delete(
    "/coverage-targets/{facility_id}", response_model=CoverageTargetRemoveResponse
)
def remove_coverage_target(
    facility_id: UUID,
    payload: OptimisticRemove,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
    room_id: UUID | None = None,
) -> CoverageTargetRemoveResponse:
    ensure_writable(request)
    canonical = canonical_event_payload({"facility_id": facility_id, "room_id": room_id})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    existing_event = idempotent_workforce_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_coverage_target",
        event_type="removed",
        payload=canonical,
    )
    if existing_event is not None:
        value = _coverage_profile(session, context.organization.id, facility_id, room_id)
        if (
            value is None
            or value.is_specified
            or value.last_operation_id != payload.client_operation_id
        ):
            raise HTTPException(409, detail={"code": "operation_superseded"})
        return CoverageTargetRemoveResponse(
            removed=True,
            recorded_operation_id=payload.client_operation_id,
            generated_at=datetime.now(UTC),
        )
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility_id
        )
    lock_workforce_lane(
        session,
        context.organization.id,
        f"coverage:{facility_id}:{room_id or 'facility'}",
    )
    value = _coverage_profile(session, context.organization.id, facility_id, room_id, lock=True)
    if value is None or not value.is_specified:
        raise HTTPException(404, "Coverage target not found")
    require_current(value.updated_at, payload.expected_updated_at)
    now = datetime.now(UTC)
    value.windows = []
    value.is_specified = False
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_coverage_target",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        actor_user_id=context.user.id,
        event_type="removed",
        payload=canonical,
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_coverage_target.removed",
        entity_type="staff_coverage_target",
        entity_id=value.id,
        facility_id=facility_id,
        details={"room_id": str(room_id) if room_id else None},
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility_id,
            cause_entity_type="staff_coverage_target",
            cause_entity_id=value.id,
        )
    commit_in_context(session, context)
    return CoverageTargetRemoveResponse(
        removed=True,
        recorded_operation_id=payload.client_operation_id,
        generated_at=now,
    )


@manager_router.get("/coverage-projection", response_model=CoverageProjectionResponse)
def coverage_projection(
    facility_id: UUID,
    start_date: date,
    end_date: date,
    context: StaffAccessContext,
    session: SessionDependency,
    room_id: UUID | None = None,
) -> CoverageProjectionResponse:
    if end_date < start_date or (end_date - start_date).days + 1 > MAX_PROJECTION_DAYS:
        raise HTTPException(
            422,
            detail={"code": "invalid_projection_range", "max_days": MAX_PROJECTION_DAYS},
        )
    facility = facility_row(session, context.organization.id, facility_id)
    room = room_row(session, context.organization.id, facility_id, room_id)
    range_start = resolve_local_datetime(facility, start_date, time.min)
    range_end = resolve_local_datetime(facility, end_date + timedelta(days=1), time.min)
    target = _coverage_profile(session, context.organization.id, facility_id, room_id)
    target_windows = target.windows if target is not None and target.is_specified else []
    statement = select(ScheduledStaffShift).where(
        ScheduledStaffShift.organization_id == context.organization.id,
        ScheduledStaffShift.facility_id == facility_id,
        ScheduledStaffShift.status != "cancelled",
        ScheduledStaffShift.scheduled_start_at < range_end,
        ScheduledStaffShift.scheduled_end_at > range_start,
    )
    if room_id is not None:
        statement = statement.where(ScheduledStaffShift.room_id == room_id)
    schedules = list(session.scalars(statement))
    zone = facility_zone(facility)
    buckets: list[CoverageProjectionBucket] = []
    cursor = range_start
    while cursor < range_end:
        bucket_end = min(cursor + timedelta(minutes=15), range_end)
        local_start = cursor.astimezone(zone)
        local_end = bucket_end.astimezone(zone)
        required = 0
        if local_start.date() == local_end.date() or (
            local_end.time() == time.min
            and local_end.date() == local_start.date() + timedelta(days=1)
        ):
            start_wall = local_start.time().replace(tzinfo=None)
            for window in target_windows:
                if (
                    window["weekday"] == local_start.weekday()
                    and parse_local_time(window["start_local"]) <= start_wall
                    and parse_local_time(window["end_local"]) > start_wall
                ):
                    required = window["required_staff"]
                    break
        covering = [
            item
            for item in schedules
            if stored_utc(item.scheduled_start_at) <= cursor
            and stored_utc(item.scheduled_end_at) >= bucket_end
        ]
        published = sum(item.status == "published" for item in covering)
        acknowledged = sum(
            item.status == "published" and item.response_status == "acknowledged"
            for item in covering
        )
        declined = sum(
            item.status == "published" and item.response_status == "declined" for item in covering
        )
        draft = sum(item.status == "draft" for item in covering)
        buckets.append(
            CoverageProjectionBucket(
                starts_at=cursor,
                ends_at=bucket_end,
                required=required,
                published=published,
                acknowledged=acknowledged,
                declined=declined,
                draft=draft,
                gap=max(required - (published - declined), 0),
                confirmation_gap=max(required - acknowledged, 0),
            )
        )
        cursor = bucket_end
    return CoverageProjectionResponse(
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=room_id,
        room_name=room.name if room else None,
        start_date=start_date,
        end_date=end_date,
        buckets=buckets,
        total_buckets=len(buckets),
        gap_buckets=sum(item.gap > 0 for item in buckets),
        generated_at=datetime.now(UTC),
    )
