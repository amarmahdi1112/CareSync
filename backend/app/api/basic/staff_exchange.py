"""Recurring rota, open-shift exchange, substitute, and whole-shift swap APIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

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
    MembershipRoomAssignment,
    OrganizationMembership,
    Role,
    ScheduledStaffShift,
    StaffOpenShift,
    StaffOpenShiftEngagement,
    StaffRotationPattern,
    StaffShiftSwapRequest,
    StaffSubstituteProfile,
    StaffWorkforceEvent,
)
from app.basic.notifications import (
    emit_user_realtime_event,
    notify_organization_members,
    notify_user,
)
from app.basic.security import audit
from app.basic.staff_exchange import (
    build_rotation_preview,
    candidate_eligibility,
    canonical_json,
    canonical_rotation_slots,
    engagement_response,
    engagement_row,
    has_clock_link,
    open_shift_candidate,
    open_shift_response,
    open_shift_row,
    receipt_event,
    require_expected,
    rotation_response,
    rotation_row,
    rotation_snapshot_digest,
    schedule_exchange_pending,
    self_open_shift_response,
    substitute_manager_response,
    substitute_profile_response,
    swap_candidate,
    swap_response,
    swap_row,
    workforce_receipt_payload,
)
from app.basic.staff_exchange_schemas import (
    EngagementAction,
    ExchangeOptimisticAction,
    ExpressInterest,
    ManagerOfferCreate,
    OpenShiftCancelAction,
    OpenShiftCandidateList,
    OpenShiftCreate,
    OpenShiftEngagementList,
    OpenShiftEngagementResponse,
    OpenShiftList,
    OpenShiftPatch,
    OpenShiftResponse,
    RotationGenerateRequest,
    RotationGenerateResponse,
    RotationPatternCreate,
    RotationPatternList,
    RotationPatternPatch,
    RotationPatternResponse,
    RotationPreviewRequest,
    RotationPreviewResponse,
    RotationRetireAction,
    SelfOpenShiftList,
    ShiftSwapList,
    ShiftSwapResponse,
    SubstituteManagerList,
    SubstituteProfileList,
    SubstituteProfileReplace,
    SubstituteProfileResponse,
    SwapCandidateList,
    SwapRejectAction,
    SwapRequestCreate,
    SwapResponseAction,
)
from app.basic.staff_scheduling import (
    add_event,
    aware_utc,
    clean_optional_text,
    event_payload,
    lock_schedule_lanes,
    schedule_row,
    stored_utc,
    validate_assignment,
    validate_interval,
)
from app.basic.staff_workforce import (
    add_workforce_event,
    facility_row,
    lock_workforce_lane,
    room_row,
    schedule_matches_availability,
)

manager_router = APIRouter(prefix="/staff-exchange", tags=["staff exchange"])
self_router = APIRouter(
    prefix="/staff/self/exchange",
    tags=["staff exchange"],
    dependencies=[
        Depends(require_complete_if_marketplace_user),
        Depends(require_permission("shift:clock")),
    ],
)
MAX_LIST_DAYS = 366
MAX_LIST_ITEMS = 500
MAX_SWAP_CANDIDATE_DAYS = 84


def _receipt_response[T: BaseModel](event: StaffWorkforceEvent, model: type[T]) -> T:
    response = (event.payload or {}).get("response")
    if response is None:
        raise HTTPException(409, detail={"code": "operation_receipt_incomplete"})
    return model.model_validate(response)


def _store_event(
    session,
    *,
    context,
    entity_type: str,
    entity_id: UUID,
    operation_id: UUID,
    event_type: str,
    request_payload: dict,
    response: BaseModel,
    occurred_at: datetime,
    receipt_extra: dict | None = None,
) -> None:
    extra = receipt_extra or {}
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        event_type=event_type,
        payload=workforce_receipt_payload(
            request_payload,
            response=response.model_dump(mode="json"),
            **extra,
        ),
        occurred_at=occurred_at,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"{entity_type}.{event_type}",
        entity_type=entity_type,
        entity_id=entity_id,
        details={"operation_id": str(operation_id)},
    )
    prefix = {
        "staff_rotation_pattern": "staff_rotation",
        "staff_open_shift": "staff_open_shift",
        "staff_open_shift_engagement": "staff_open_shift_engagement",
        "staff_substitute_profile": "staff_substitute_profile",
        "staff_shift_swap": "staff_shift_swap",
    }[entity_type]
    emit_user_realtime_event(
        session,
        user_id=context.user.id,
        organization_id=context.organization.id,
        event_type=f"{prefix}.{event_type}",
        entity_type=entity_type,
        entity_id=entity_id,
        payload={"source": "operation_receipt"},
    )


def _manager_user_ids(session, organization_id: UUID) -> list[UUID]:
    rows = session.execute(
        select(OrganizationMembership, Role)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
    )
    return [
        membership.user_id
        for membership, role in rows
        if {"staff:manage", "staff:manage_educators"}.intersection(role.permissions or [])
    ]


def _invalidate(
    session,
    *,
    organization_id: UUID,
    user_ids: set[UUID],
    event_type: str,
    entity_type: str,
    entity_id: UUID,
) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        # Cross-recipient domain events cannot be inserted under the actor's
        # forced user RLS context. Recipient notifications above are the safe
        # bridge: their trigger temporarily assumes the recipient and appends
        # a private ``notification.created`` realtime invalidation. The actor
        # already owns the operation-receipt event emitted by ``_store_event``.
        return
    for user_id in sorted(user_ids, key=str):
        emit_user_realtime_event(
            session,
            user_id=user_id,
            organization_id=organization_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload={"source": "staff_exchange"},
        )


def _notify_managers(
    session,
    *,
    context,
    event_key: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: UUID,
    facility_id: UUID,
) -> None:
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"staff:manage", "staff:manage_educators"},
        event_key=event_key,
        category="assignment",
        severity="info",
        title=title,
        body=body,
        action_path="/staff-rota",
        action_entity_type=entity_type,
        action_entity_id=entity_id,
        facility_id=facility_id,
    )


def _notify_staff(
    session,
    *,
    context,
    membership_id: UUID,
    event_key: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: UUID,
    action_path: str,
) -> UUID:
    user_id = session.scalar(
        select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == membership_id,
        )
    )
    if user_id is None:
        raise HTTPException(404, "Staff member not found")
    notify_user(
        session,
        user_id=user_id,
        organization_id=context.organization.id,
        event_key=event_key,
        category="assignment",
        severity="info",
        title=title,
        body=body,
        action_path=action_path,
        action_entity_type=entity_type,
        action_entity_id=entity_id,
    )
    return user_id


def _default_window(
    start_at: datetime | None, end_at: datetime | None
) -> tuple[datetime, datetime]:
    if start_at is None and end_at is None:
        now = datetime.now(UTC)
        return now - timedelta(days=30), now + timedelta(days=90)
    if start_at is None or end_at is None:
        raise HTTPException(422, detail={"code": "bounded_window_required"})
    start = aware_utc(start_at, "start_at")
    end = aware_utc(end_at, "end_at")
    if end <= start:
        raise HTTPException(422, detail={"code": "invalid_list_window"})
    if end - start > timedelta(days=MAX_LIST_DAYS):
        raise HTTPException(422, detail={"code": "list_range_too_large"})
    return start, end


def _bounded_rows(rows, *, code: str = "list_too_large") -> list:
    values = list(rows)
    if len(values) > MAX_LIST_ITEMS:
        raise HTTPException(
            422,
            detail={
                "code": code,
                "max_items": MAX_LIST_ITEMS,
                "message": "Narrow the facility or date filters and try again.",
            },
        )
    return values


@manager_router.get("/rotations", response_model=RotationPatternList)
def list_rotations(
    facility_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
    include_retired: bool = True,
) -> RotationPatternList:
    facility_row(session, context.organization.id, facility_id)
    statement = select(StaffRotationPattern).where(
        StaffRotationPattern.organization_id == context.organization.id,
        StaffRotationPattern.facility_id == facility_id,
    )
    if not include_retired:
        statement = statement.where(StaffRotationPattern.status != "retired")
    values = _bounded_rows(
        session.scalars(
            statement.order_by(StaffRotationPattern.created_at.desc()).limit(MAX_LIST_ITEMS + 1)
        )
    )
    return RotationPatternList(
        items=[rotation_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@manager_router.post(
    "/rotations", response_model=RotationPatternResponse, status_code=status.HTTP_201_CREATED
)
def create_rotation(
    payload: RotationPatternCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationPatternResponse:
    ensure_writable(request)
    if payload.anchor_date.weekday() != 0:
        raise HTTPException(422, detail={"code": "rotation_anchor_must_be_monday"})
    name = clean_optional_text(payload.name)
    if name is None:
        raise HTTPException(422, detail={"code": "rotation_name_required"})
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_rotation_pattern",
        event_type="created",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, RotationPatternResponse)
    facility_row(session, context.organization.id, payload.facility_id)
    lock_workforce_lane(session, context.organization.id, "rotation", payload.facility_id, name)
    slots = canonical_rotation_slots(
        session,
        context.organization.id,
        payload.facility_id,
        payload.cycle_weeks,
        payload.slots,
    )
    version = (
        session.scalar(
            select(func.max(StaffRotationPattern.version)).where(
                StaffRotationPattern.organization_id == context.organization.id,
                StaffRotationPattern.facility_id == payload.facility_id,
                StaffRotationPattern.name == name,
            )
        )
        or 0
    ) + 1
    now = datetime.now(UTC)
    value = StaffRotationPattern(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=payload.facility_id,
        name=name,
        version=version,
        cycle_length_weeks=payload.cycle_weeks,
        anchor_week_start=payload.anchor_date,
        slots=slots,
        status="draft",
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    response = rotation_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="created",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-rotation-created:{value.id}:{payload.client_operation_id}",
        title="Staff rotation created",
        body="A staff rotation draft was created for this facility.",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_rotation.created",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Rotation pattern conflicts with existing data")
    commit_in_context(session, context)
    return response


@manager_router.patch("/rotations/{pattern_id}", response_model=RotationPatternResponse)
def patch_rotation(
    pattern_id: UUID,
    payload: RotationPatternPatch,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationPatternResponse:
    ensure_writable(request)
    changes = payload.model_dump(
        exclude={"client_operation_id", "expected_updated_at"}, exclude_unset=True
    )
    if not changes:
        raise HTTPException(422, detail={"code": "empty_patch"})
    canonical = canonical_json({**changes, "expected_updated_at": payload.expected_updated_at})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_rotation_pattern",
        event_type="updated",
        request_payload=canonical,
        entity_id=pattern_id,
    )
    if receipt:
        return _receipt_response(receipt, RotationPatternResponse)
    lock_workforce_lane(session, context.organization.id, "rotation", pattern_id)
    value = rotation_row(session, context.organization.id, pattern_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.status != "draft":
        raise HTTPException(409, detail={"code": "draft_rotation_required"})
    name = clean_optional_text(changes.get("name", value.name))
    anchor = changes.get("anchor_date", value.anchor_week_start)
    cycle = changes.get("cycle_weeks", value.cycle_length_weeks)
    if name is None:
        raise HTTPException(422, detail={"code": "rotation_name_required"})
    if anchor.weekday() != 0:
        raise HTTPException(422, detail={"code": "rotation_anchor_must_be_monday"})
    slots = (
        canonical_rotation_slots(
            session,
            context.organization.id,
            value.facility_id,
            cycle,
            payload.slots,
        )
        if payload.slots is not None
        else value.slots
    )
    if payload.slots is None and any(item["cycle_week"] >= cycle for item in slots):
        raise HTTPException(422, detail={"code": "rotation_slot_outside_cycle"})
    now = datetime.now(UTC)
    value.name = name
    value.anchor_week_start = anchor
    value.cycle_length_weeks = cycle
    value.slots = slots
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = rotation_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="updated",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-rotation-updated:{value.id}:{payload.client_operation_id}",
        title="Staff rotation updated",
        body="A staff rotation draft was updated for this facility.",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_rotation.updated",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


def _rotation_action(
    *,
    pattern_id: UUID,
    payload,
    request: Request,
    context,
    session,
    action: str,
) -> RotationPatternResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_rotation_pattern",
        event_type=action,
        request_payload=canonical,
        entity_id=pattern_id,
    )
    if receipt:
        return _receipt_response(receipt, RotationPatternResponse)
    lock_workforce_lane(session, context.organization.id, "rotation", pattern_id)
    value = rotation_row(session, context.organization.id, pattern_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    now = datetime.now(UTC)
    if action == "activated":
        if value.status != "draft":
            raise HTTPException(409, detail={"code": "draft_rotation_required"})
        if session.scalar(
            select(StaffRotationPattern.id).where(
                StaffRotationPattern.organization_id == context.organization.id,
                StaffRotationPattern.facility_id == value.facility_id,
                StaffRotationPattern.name == value.name,
                StaffRotationPattern.status == "active",
                StaffRotationPattern.id != value.id,
            )
        ):
            raise HTTPException(409, detail={"code": "active_rotation_version_exists"})
        facility_row(session, context.organization.id, value.facility_id)
        for raw in value.slots or []:
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == context.organization.id,
                    OrganizationMembership.id == UUID(raw["membership_id"]),
                )
            )
            if membership is None:
                raise HTTPException(409, detail={"code": "inactive_rotation_assignment"})
            validate_assignment(
                session,
                context.organization.id,
                staff_user_id=membership.user_id,
                facility_id=value.facility_id,
                room_id=UUID(raw["room_id"]) if raw.get("room_id") else None,
            )
        value.status = "active"
        value.snapshot_digest = rotation_snapshot_digest(value)
        value.activation_operation_id = payload.client_operation_id
        value.activated_at = now
        value.activated_by_user_id = context.user.id
    else:
        if value.status != "active":
            raise HTTPException(409, detail={"code": "active_rotation_required"})
        reason = clean_optional_text(payload.reason)
        if reason is None:
            raise HTTPException(422, detail={"code": "retirement_reason_required"})
        value.status = "retired"
        value.retirement_operation_id = payload.client_operation_id
        value.retired_at = now
        value.retired_by_user_id = context.user.id
        value.retirement_reason = reason
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = rotation_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type=action,
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-rotation-{action}:{value.id}:{payload.client_operation_id}",
        title="Staff rotation updated",
        body=(
            "A staff rotation is now active."
            if action == "activated"
            else "A staff rotation was retired."
        ),
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type=f"staff_rotation.{action}",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@manager_router.post("/rotations/{pattern_id}/activate", response_model=RotationPatternResponse)
def activate_rotation(
    pattern_id: UUID,
    payload: ExchangeOptimisticAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationPatternResponse:
    return _rotation_action(
        pattern_id=pattern_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="activated",
    )


@manager_router.post("/rotations/{pattern_id}/retire", response_model=RotationPatternResponse)
def retire_rotation(
    pattern_id: UUID,
    payload: RotationRetireAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationPatternResponse:
    return _rotation_action(
        pattern_id=pattern_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="retired",
    )


@manager_router.post("/rotations/{pattern_id}/preview", response_model=RotationPreviewResponse)
def preview_rotation(
    pattern_id: UUID,
    payload: RotationPreviewRequest,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationPreviewResponse:
    value = rotation_row(session, context.organization.id, pattern_id)
    if value.status != "active":
        raise HTTPException(409, detail={"code": "active_rotation_required"})
    return build_rotation_preview(session, value, payload.start_date, payload.end_date)


@manager_router.post("/rotations/{pattern_id}/generate", response_model=RotationGenerateResponse)
def generate_rotation(
    pattern_id: UUID,
    payload: RotationGenerateRequest,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> RotationGenerateResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_rotation_pattern",
        event_type="generated",
        request_payload=canonical,
        entity_id=pattern_id,
    )
    if receipt:
        return _receipt_response(receipt, RotationGenerateResponse)
    lock_workforce_lane(session, context.organization.id, "rotation", pattern_id)
    value = rotation_row(session, context.organization.id, pattern_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.status != "active" or value.snapshot_digest != rotation_snapshot_digest(value):
        raise HTTPException(409, detail={"code": "active_rotation_snapshot_required"})
    preview = build_rotation_preview(session, value, payload.start_date, payload.end_date)
    if preview.snapshot_digest != payload.preview_digest:
        raise HTTPException(409, detail={"code": "preview_stale"})
    membership_ids = {item.membership_id for item in preview.occurrences}
    lock_schedule_lanes(session, context.organization.id, membership_ids)
    preview = build_rotation_preview(session, value, payload.start_date, payload.end_date)
    if preview.snapshot_digest != payload.preview_digest:
        raise HTTPException(409, detail={"code": "preview_stale"})
    if preview.issues:
        raise HTTPException(
            409,
            detail={
                "code": "rotation_conflicts",
                "issues": [item.model_dump(mode="json") for item in preview.issues],
            },
        )
    now = datetime.now(UTC)
    schedules: list[ScheduledStaffShift] = []
    for occurrence in preview.occurrences:
        operation_id = uuid5(
            NAMESPACE_URL,
            f"caresync:rotation:{payload.client_operation_id}:{occurrence.occurrence_key}",
        )
        schedule = ScheduledStaffShift(
            id=uuid4(),
            organization_id=context.organization.id,
            membership_id=occurrence.membership_id,
            facility_id=value.facility_id,
            room_id=occurrence.room_id,
            scheduled_start_at=occurrence.scheduled_start_at,
            scheduled_end_at=occurrence.scheduled_end_at,
            notes=occurrence.notes,
            status="draft",
            response_status="pending",
            create_operation_id=operation_id,
            created_by_user_id=context.user.id,
            origin_type="rotation",
            origin_id=value.id,
            origin_occurrence_key=occurrence.occurrence_key,
            created_at=now,
            updated_at=now,
        )
        session.add(schedule)
        add_event(
            session,
            schedule,
            operation_id=operation_id,
            actor_user_id=context.user.id,
            event_type="created",
            payload=event_payload(
                staff_user_id=occurrence.staff_user_id,
                facility_id=value.facility_id,
                room_id=occurrence.room_id,
                start=occurrence.scheduled_start_at,
                end=occurrence.scheduled_end_at,
                notes=occurrence.notes,
            ),
            occurred_at=now,
        )
        audit(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action="staff_schedule.created_from_rotation",
            entity_type="staff_schedule",
            entity_id=schedule.id,
            details={"operation_id": str(operation_id)},
        )
        schedules.append(schedule)
    response = RotationGenerateResponse(
        pattern_id=value.id,
        snapshot_digest=preview.snapshot_digest,
        schedule_ids=[item.id for item in schedules],
        total=len(schedules),
        recorded_operation_id=payload.client_operation_id,
        generated_at=now,
    )
    _store_event(
        session,
        context=context,
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="generated",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-rotation-generated:{value.id}:{payload.client_operation_id}",
        title="Rotation drafts generated",
        body="A recurring rotation generated draft staff shifts for review.",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_rotation.generated",
        entity_type="staff_rotation_pattern",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Rotation occurrence conflicts with existing data")
    commit_in_context(session, context)
    return response


def _validate_replacement_source(
    session,
    organization_id: UUID,
    *,
    source_schedule_id: UUID | None,
    facility_id: UUID,
    room_id: UUID | None,
    start: datetime,
    end: datetime,
    lock: bool = False,
) -> ScheduledStaffShift | None:
    if source_schedule_id is None:
        return None
    source = schedule_row(session, organization_id, source_schedule_id, lock=lock)
    if (
        source.status != "published"
        or source.response_status != "acknowledged"
        or stored_utc(source.scheduled_start_at) <= datetime.now(UTC)
        or source.facility_id != facility_id
        or source.room_id != room_id
        or stored_utc(source.scheduled_start_at) != stored_utc(start)
        or stored_utc(source.scheduled_end_at) != stored_utc(end)
        or has_clock_link(session, organization_id, source.id)
    ):
        raise HTTPException(409, detail={"code": "invalid_replacement_source"})
    return source


def _lock_schedule_exchange_sources(
    session,
    organization_id: UUID,
    schedule_ids: set[UUID | None],
) -> None:
    for schedule_id in sorted((value for value in schedule_ids if value is not None), key=str):
        lock_workforce_lane(
            session,
            organization_id,
            f"schedule-exchange:{schedule_id}",
        )


def _ensure_schedule_exchange_available(
    session,
    organization_id: UUID,
    source_schedule_id: UUID | None,
    *,
    exclude_open_shift_id: UUID | None = None,
) -> None:
    if source_schedule_id is None:
        return
    if schedule_exchange_pending(
        session,
        organization_id,
        source_schedule_id,
        exclude_open_shift_id=exclude_open_shift_id,
    ):
        raise HTTPException(409, detail={"code": "schedule_exchange_pending"})


def _terminalize_engagement(
    session,
    *,
    context,
    engagement: StaffOpenShiftEngagement,
    status_value: str,
    reason: str,
    source_operation_id: UUID,
    now: datetime,
    notification_title: str,
    notification_body: str,
) -> UUID:
    operation_id = uuid5(
        NAMESPACE_URL,
        f"caresync:open-shift-terminal:{source_operation_id}:{engagement.id}:{status_value}",
    )
    engagement.status = status_value
    engagement.terminal_at = now
    engagement.terminal_by_user_id = context.user.id
    engagement.terminal_reason = reason
    engagement.last_operation_id = operation_id
    engagement.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        event_type=status_value,
        payload=workforce_receipt_payload(
            canonical_json(
                {
                    "source_operation_id": source_operation_id,
                    "reason": reason,
                }
            ),
            status=status_value,
        ),
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"staff_open_shift_engagement.{status_value}",
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        details={"operation_id": str(operation_id)},
    )
    user_id = _notify_staff(
        session,
        context=context,
        membership_id=engagement.membership_id,
        event_key=f"staff-open-shift-terminal:{engagement.id}:{operation_id}",
        title=notification_title,
        body=notification_body,
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        action_path="/staff/self/exchange/open-shift-activity",
    )
    return user_id


@manager_router.get("/open-shifts", response_model=OpenShiftList)
def list_manager_open_shifts(
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> OpenShiftList:
    start, end = _default_window(start_at, end_at)
    statement = select(StaffOpenShift).where(
        StaffOpenShift.organization_id == context.organization.id,
        StaffOpenShift.starts_at < end,
        StaffOpenShift.ends_at > start,
    )
    if facility_id:
        statement = statement.where(StaffOpenShift.facility_id == facility_id)
    values = _bounded_rows(
        session.scalars(
            statement.order_by(StaffOpenShift.starts_at, StaffOpenShift.id).limit(
                MAX_LIST_ITEMS + 1
            )
        )
    )
    return OpenShiftList(
        items=[open_shift_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@manager_router.post(
    "/open-shifts", response_model=OpenShiftResponse, status_code=status.HTTP_201_CREATED
)
def create_open_shift(
    payload: OpenShiftCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftResponse:
    ensure_writable(request)
    start, end = validate_interval(payload.scheduled_start_at, payload.scheduled_end_at)
    if start <= datetime.now(UTC):
        raise HTTPException(422, detail={"code": "future_open_shift_required"})
    note = clean_optional_text(payload.public_note)
    canonical = canonical_json(
        {
            "facility_id": payload.facility_id,
            "room_id": payload.room_id,
            "source_schedule_id": payload.source_schedule_id,
            "scheduled_start_at": start,
            "scheduled_end_at": end,
            "public_note": note,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift",
        event_type="created",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftResponse)
    facility_row(session, context.organization.id, payload.facility_id)
    room_row(session, context.organization.id, payload.facility_id, payload.room_id)
    _lock_schedule_exchange_sources(
        session,
        context.organization.id,
        {payload.source_schedule_id},
    )
    lock_workforce_lane(
        session,
        context.organization.id,
        "open-shift",
        payload.source_schedule_id or payload.facility_id,
    )
    _validate_replacement_source(
        session,
        context.organization.id,
        source_schedule_id=payload.source_schedule_id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
        start=start,
        end=end,
        lock=payload.source_schedule_id is not None,
    )
    _ensure_schedule_exchange_available(
        session,
        context.organization.id,
        payload.source_schedule_id,
    )
    now = datetime.now(UTC)
    value = StaffOpenShift(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
        starts_at=start,
        ends_at=end,
        notes=note,
        status="draft",
        source_schedule_id=payload.source_schedule_id,
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    response = open_shift_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="created",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-created:{value.id}:{payload.client_operation_id}",
        title="Open shift created",
        body="An open shift draft was created for this facility.",
        entity_type="staff_open_shift",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_open_shift.created",
        entity_type="staff_open_shift",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Open shift conflicts with existing data")
    commit_in_context(session, context)
    return response


@manager_router.patch("/open-shifts/{open_shift_id}", response_model=OpenShiftResponse)
def patch_open_shift(
    open_shift_id: UUID,
    payload: OpenShiftPatch,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftResponse:
    ensure_writable(request)
    changes = payload.model_dump(
        exclude={"client_operation_id", "expected_updated_at"}, exclude_unset=True
    )
    if not changes:
        raise HTTPException(422, detail={"code": "empty_patch"})
    canonical = canonical_json({**changes, "expected_updated_at": payload.expected_updated_at})
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift",
        event_type="updated",
        request_payload=canonical,
        entity_id=open_shift_id,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftResponse)
    lock_workforce_lane(session, context.organization.id, "open-shift", open_shift_id)
    value = open_shift_row(session, context.organization.id, open_shift_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.status != "draft":
        raise HTTPException(409, detail={"code": "draft_open_shift_required"})
    facility_id = changes.get("facility_id", value.facility_id)
    room_id = changes.get("room_id", value.room_id)
    source_id = changes.get("source_schedule_id", value.source_schedule_id)
    _lock_schedule_exchange_sources(
        session,
        context.organization.id,
        {value.source_schedule_id, source_id},
    )
    if source_id is not None:
        lock_workforce_lane(
            session,
            context.organization.id,
            "open-shift-source",
            source_id,
        )
    start = changes.get("scheduled_start_at", stored_utc(value.starts_at))
    end = changes.get("scheduled_end_at", stored_utc(value.ends_at))
    start, end = validate_interval(start, end)
    if start <= datetime.now(UTC):
        raise HTTPException(422, detail={"code": "future_open_shift_required"})
    facility_row(session, context.organization.id, facility_id)
    room_row(session, context.organization.id, facility_id, room_id)
    _validate_replacement_source(
        session,
        context.organization.id,
        source_schedule_id=source_id,
        facility_id=facility_id,
        room_id=room_id,
        start=start,
        end=end,
        lock=source_id is not None,
    )
    _ensure_schedule_exchange_available(
        session,
        context.organization.id,
        source_id,
        exclude_open_shift_id=value.id,
    )
    now = datetime.now(UTC)
    value.facility_id = facility_id
    value.room_id = room_id
    value.source_schedule_id = source_id
    value.starts_at = start
    value.ends_at = end
    if "public_note" in changes:
        value.notes = clean_optional_text(changes["public_note"])
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = open_shift_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="updated",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-updated:{value.id}:{payload.client_operation_id}",
        title="Open shift updated",
        body="An open shift draft was updated for this facility.",
        entity_type="staff_open_shift",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_open_shift.updated",
        entity_type="staff_open_shift",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


def _open_shift_lifecycle_action(
    *,
    open_shift_id: UUID,
    payload,
    request: Request,
    context,
    session,
    action: str,
) -> OpenShiftResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift",
        event_type=action,
        request_payload=canonical,
        entity_id=open_shift_id,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftResponse)
    lock_workforce_lane(session, context.organization.id, "open-shift", open_shift_id)
    value = open_shift_row(session, context.organization.id, open_shift_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    now = datetime.now(UTC)
    terminalized_ids: list[str] = []
    affected_user_ids: set[UUID] = set()
    if action == "posted":
        if value.status != "draft":
            raise HTTPException(409, detail={"code": "draft_open_shift_required"})
        if stored_utc(value.starts_at) <= now:
            raise HTTPException(409, detail={"code": "future_open_shift_required"})
        facility_row(session, context.organization.id, value.facility_id)
        room_row(
            session,
            context.organization.id,
            value.facility_id,
            value.room_id,
        )
        _lock_schedule_exchange_sources(
            session,
            context.organization.id,
            {value.source_schedule_id},
        )
        _validate_replacement_source(
            session,
            context.organization.id,
            source_schedule_id=value.source_schedule_id,
            facility_id=value.facility_id,
            room_id=value.room_id,
            start=stored_utc(value.starts_at),
            end=stored_utc(value.ends_at),
            lock=value.source_schedule_id is not None,
        )
        _ensure_schedule_exchange_available(
            session,
            context.organization.id,
            value.source_schedule_id,
            exclude_open_shift_id=value.id,
        )
        value.status = "open"
        value.post_operation_id = payload.client_operation_id
        value.posted_at = now
        value.posted_by_user_id = context.user.id
    else:
        if value.status not in {"draft", "open"}:
            raise HTTPException(409, detail={"code": "open_shift_not_cancellable"})
        reason = clean_optional_text(payload.reason)
        if reason is None:
            raise HTTPException(422, detail={"code": "cancellation_reason_required"})
        value.status = "cancelled"
        value.cancelled_at = now
        value.cancelled_by_user_id = context.user.id
        value.cancellation_reason = reason
        pending = list(
            session.scalars(
                select(StaffOpenShiftEngagement)
                .where(
                    StaffOpenShiftEngagement.organization_id == context.organization.id,
                    StaffOpenShiftEngagement.open_shift_id == value.id,
                    StaffOpenShiftEngagement.status == "pending",
                )
                .with_for_update()
            )
        )
        for engagement in pending:
            affected_user_ids.add(
                _terminalize_engagement(
                    session,
                    context=context,
                    engagement=engagement,
                    status_value="superseded",
                    reason="Open shift cancelled",
                    source_operation_id=payload.client_operation_id,
                    now=now,
                    notification_title="Open shift cancelled",
                    notification_body="An open shift you responded to is no longer available.",
                )
            )
            terminalized_ids.append(str(engagement.id))
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = open_shift_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type=action,
        request_payload=canonical,
        response=response,
        occurred_at=now,
        receipt_extra={"terminalized_engagement_ids": terminalized_ids},
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-{action}:{value.id}:{payload.client_operation_id}",
        title="Open shift updated",
        body=(
            "An open shift is now available to eligible substitute staff."
            if action == "posted"
            else "An open shift was cancelled."
        ),
        entity_type="staff_open_shift",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    if action == "posted":
        source_membership_id = None
        if value.source_schedule_id:
            source_membership_id = schedule_row(
                session, context.organization.id, value.source_schedule_id
            ).membership_id
        opted_in_membership_ids = _bounded_rows(
            session.scalars(
                select(StaffSubstituteProfile.membership_id)
                .where(
                    StaffSubstituteProfile.organization_id == context.organization.id,
                    StaffSubstituteProfile.facility_id == value.facility_id,
                    StaffSubstituteProfile.is_specified.is_(True),
                    StaffSubstituteProfile.is_opted_in.is_(True),
                    StaffSubstituteProfile.membership_id != source_membership_id,
                )
                .order_by(StaffSubstituteProfile.membership_id)
                .limit(MAX_LIST_ITEMS + 1)
            )
        )
        for membership_id in opted_in_membership_ids:
            _, ineligibility_reasons = candidate_eligibility(
                session,
                context.organization.id,
                membership_id,
                facility_id=value.facility_id,
                room_id=value.room_id,
                start=stored_utc(value.starts_at),
                end=stored_utc(value.ends_at),
                exclude_schedule_ids=(
                    {value.source_schedule_id} if value.source_schedule_id else None
                ),
            )
            if ineligibility_reasons:
                continue
            affected_user_ids.add(
                _notify_staff(
                    session,
                    context=context,
                    membership_id=membership_id,
                    event_key=(
                        f"staff-open-shift-posted:{value.id}:"
                        f"{payload.client_operation_id}:{membership_id}"
                    ),
                    title="New open shift",
                    body="A new open shift is available at one of your facilities.",
                    entity_type="staff_open_shift",
                    entity_id=value.id,
                    action_path="/staff/self/exchange/open-shifts",
                )
            )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=(set(_manager_user_ids(session, context.organization.id)) | affected_user_ids),
        event_type=f"staff_open_shift.{action}",
        entity_type="staff_open_shift",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@manager_router.post("/open-shifts/{open_shift_id}/post", response_model=OpenShiftResponse)
def post_open_shift(
    open_shift_id: UUID,
    payload: ExchangeOptimisticAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftResponse:
    return _open_shift_lifecycle_action(
        open_shift_id=open_shift_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="posted",
    )


@manager_router.post("/open-shifts/{open_shift_id}/cancel", response_model=OpenShiftResponse)
def cancel_open_shift(
    open_shift_id: UUID,
    payload: OpenShiftCancelAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftResponse:
    return _open_shift_lifecycle_action(
        open_shift_id=open_shift_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="cancelled",
    )


@manager_router.get(
    "/open-shifts/{open_shift_id}/candidates", response_model=OpenShiftCandidateList
)
def list_open_shift_candidates(
    open_shift_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftCandidateList:
    value = open_shift_row(session, context.organization.id, open_shift_id)
    if value.status != "open":
        raise HTTPException(409, detail={"code": "open_shift_required"})
    source_membership_id = None
    if value.source_schedule_id:
        source_membership_id = schedule_row(
            session, context.organization.id, value.source_schedule_id
        ).membership_id
    memberships = _bounded_rows(
        session.scalars(
            select(OrganizationMembership)
            .join(
                Role,
                (Role.organization_id == OrganizationMembership.organization_id)
                & (Role.id == OrganizationMembership.role_id),
            )
            .where(
                OrganizationMembership.organization_id == context.organization.id,
                OrganizationMembership.status == "active",
                Role.key == "educator",
            )
            .order_by(OrganizationMembership.created_at)
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    items = [
        open_shift_candidate(session, value, membership)
        for membership in memberships
        if membership.id != source_membership_id
    ]
    return OpenShiftCandidateList(items=items, total=len(items), generated_at=datetime.now(UTC))


@manager_router.get(
    "/open-shifts/{open_shift_id}/engagements", response_model=OpenShiftEngagementList
)
def list_open_shift_engagements(
    open_shift_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftEngagementList:
    open_shift_row(session, context.organization.id, open_shift_id)
    values = _bounded_rows(
        session.scalars(
            select(StaffOpenShiftEngagement)
            .where(
                StaffOpenShiftEngagement.organization_id == context.organization.id,
                StaffOpenShiftEngagement.open_shift_id == open_shift_id,
            )
            .order_by(StaffOpenShiftEngagement.created_at.desc())
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    now = datetime.now(UTC)
    return OpenShiftEngagementList(
        items=[
            engagement_response(session, value, now=now, capability_scope="manager")
            for value in values
        ],
        total=len(values),
        generated_at=now,
    )


@manager_router.post(
    "/open-shifts/{open_shift_id}/offers",
    response_model=OpenShiftEngagementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_open_shift_offer(
    open_shift_id: UUID,
    payload: ManagerOfferCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    ensure_writable(request)
    expires_at = aware_utc(payload.expires_at, "expires_at")
    now = datetime.now(UTC)
    if expires_at <= now:
        raise HTTPException(422, detail={"code": "future_offer_expiry_required"})
    note = clean_optional_text(payload.note)
    canonical = canonical_json(
        {
            "open_shift_id": open_shift_id,
            "staff_user_id": payload.staff_user_id,
            "source_interest_id": payload.source_interest_id,
            "note": note,
            "expires_at": expires_at,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift_engagement",
        event_type="offered",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftEngagementResponse)
    lock_workforce_lane(
        session, context.organization.id, "open-shift", open_shift_id, payload.staff_user_id
    )
    value = open_shift_row(session, context.organization.id, open_shift_id, lock=True)
    if value.status != "open" or stored_utc(value.starts_at) <= now:
        raise HTTPException(409, detail={"code": "open_shift_required"})
    if expires_at >= stored_utc(value.starts_at):
        raise HTTPException(422, detail={"code": "offer_expiry_must_precede_shift"})
    membership, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=payload.staff_user_id,
        facility_id=value.facility_id,
        room_id=value.room_id,
    )
    if value.source_schedule_id is not None:
        source_membership_id = session.scalar(
            select(ScheduledStaffShift.membership_id).where(
                ScheduledStaffShift.organization_id == context.organization.id,
                ScheduledStaffShift.id == value.source_schedule_id,
            )
        )
        if source_membership_id == membership.id:
            raise HTTPException(409, detail={"code": "source_educator_ineligible"})
    source_interest = None
    if payload.source_interest_id:
        source_interest = engagement_row(
            session, context.organization.id, payload.source_interest_id, lock=True
        )
        if (
            source_interest.kind != "interest"
            or source_interest.status != "pending"
            or source_interest.open_shift_id != value.id
            or source_interest.membership_id != membership.id
        ):
            raise HTTPException(409, detail={"code": "invalid_source_interest"})
    else:
        lock_workforce_lane(
            session,
            context.organization.id,
            "substitute",
            membership.id,
            value.facility_id,
        )
        opted_in = session.scalar(
            select(StaffSubstituteProfile)
            .where(
                StaffSubstituteProfile.organization_id == context.organization.id,
                StaffSubstituteProfile.facility_id == value.facility_id,
                StaffSubstituteProfile.membership_id == membership.id,
                StaffSubstituteProfile.is_specified.is_(True),
                StaffSubstituteProfile.is_opted_in.is_(True),
            )
            .with_for_update()
        )
        if opted_in is None:
            raise HTTPException(409, detail={"code": "substitute_opt_in_required"})
    _, reasons = candidate_eligibility(
        session,
        context.organization.id,
        membership.id,
        facility_id=value.facility_id,
        room_id=value.room_id,
        start=stored_utc(value.starts_at),
        end=stored_utc(value.ends_at),
        exclude_schedule_ids={value.source_schedule_id} if value.source_schedule_id else None,
    )
    if reasons:
        raise HTTPException(409, detail={"code": "candidate_ineligible", "reasons": reasons})
    existing_pending = list(
        session.scalars(
            select(StaffOpenShiftEngagement)
            .where(
                StaffOpenShiftEngagement.organization_id == context.organization.id,
                StaffOpenShiftEngagement.open_shift_id == value.id,
                StaffOpenShiftEngagement.membership_id == membership.id,
                StaffOpenShiftEngagement.kind == "offer",
                StaffOpenShiftEngagement.status == "pending",
            )
            .with_for_update()
        )
    )
    superseded_ids: list[str] = []
    child_user_ids: set[UUID] = set()
    for existing in existing_pending:
        if stored_utc(existing.expires_at) > now:
            raise HTTPException(409, detail={"code": "pending_offer_exists"})
        child_user_ids.add(
            _terminalize_engagement(
                session,
                context=context,
                engagement=existing,
                status_value="superseded",
                reason="Offer expired before replacement",
                source_operation_id=payload.client_operation_id,
                now=now,
                notification_title="Open shift offer renewed",
                notification_body="An expired open shift offer was replaced with a new offer.",
            )
        )
        superseded_ids.append(str(existing.id))
    offer = StaffOpenShiftEngagement(
        id=uuid4(),
        organization_id=context.organization.id,
        open_shift_id=value.id,
        membership_id=membership.id,
        kind="offer",
        status="pending",
        note=note,
        expires_at=expires_at,
        source_interest_id=source_interest.id if source_interest else None,
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(offer)
    # The converted interest references this offer by ID. Flush the new parent
    # first because both links are assigned as scalar IDs, so SQLAlchemy cannot
    # otherwise infer the required insert-before-update dependency.
    flush_or_conflict(session, "Open-shift offer conflicts with existing data")
    if source_interest:
        source_interest.converted_offer_id = offer.id
        child_user_ids.add(
            _terminalize_engagement(
                session,
                context=context,
                engagement=source_interest,
                status_value="converted",
                reason="Manager created an offer from this interest",
                source_operation_id=payload.client_operation_id,
                now=now,
                notification_title="Open shift interest advanced",
                notification_body="A manager sent an offer for an open shift you requested.",
            )
        )
    response = engagement_response(session, offer, now=now, capability_scope="manager")
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift_engagement",
        entity_id=offer.id,
        operation_id=payload.client_operation_id,
        event_type="offered",
        request_payload=canonical,
        response=response,
        occurred_at=now,
        receipt_extra={
            "superseded_offer_ids": superseded_ids,
            "converted_interest_id": str(source_interest.id) if source_interest else None,
        },
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-offer:{offer.id}:{payload.client_operation_id}:managers",
        title="Open shift offer sent",
        body="A manager sent an offer for an open shift.",
        entity_type="staff_open_shift_engagement",
        entity_id=offer.id,
        facility_id=value.facility_id,
    )
    target_user_id = _notify_staff(
        session,
        context=context,
        membership_id=membership.id,
        event_key=f"staff-open-shift-offer:{offer.id}:{payload.client_operation_id}",
        title="Open shift offer",
        body="A care program sent you a staff shift offer.",
        entity_type="staff_open_shift_engagement",
        entity_id=offer.id,
        action_path="/staff/self/exchange/open-shift-activity",
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=(
            {target_user_id}
            | child_user_ids
            | set(_manager_user_ids(session, context.organization.id))
        ),
        event_type="staff_open_shift_engagement.offered",
        entity_type="staff_open_shift_engagement",
        entity_id=offer.id,
    )
    flush_or_conflict(session, "Open-shift offer conflicts with existing data")
    commit_in_context(session, context)
    return response


def _require_self_facility(context, facility_id: UUID) -> None:
    if not context.organization_wide and facility_id not in context.assigned_facility_ids:
        raise HTTPException(404, "Active assigned facility not found")


@self_router.get("/open-shifts", response_model=SelfOpenShiftList)
def list_self_open_shifts(
    context: BasicContextDependency,
    session: SessionDependency,
    facility_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> SelfOpenShiftList:
    start, end = _default_window(start_at, end_at)
    if facility_id:
        _require_self_facility(context, facility_id)
    statement = select(StaffOpenShift).where(
        StaffOpenShift.organization_id == context.organization.id,
        StaffOpenShift.status == "open",
        StaffOpenShift.starts_at < end,
        StaffOpenShift.ends_at > start,
    )
    if facility_id:
        statement = statement.where(StaffOpenShift.facility_id == facility_id)
    elif not context.organization_wide:
        statement = statement.where(
            StaffOpenShift.facility_id.in_(context.assigned_facility_ids or [UUID(int=0)])
        )
    values = _bounded_rows(
        session.scalars(
            statement.order_by(StaffOpenShift.starts_at, StaffOpenShift.id).limit(
                MAX_LIST_ITEMS + 1
            )
        )
    )
    now = datetime.now(UTC)
    items = [
        self_open_shift_response(
            session, value, viewer_membership_id=context.membership.id, now=now
        )
        for value in values
    ]
    return SelfOpenShiftList(items=items, total=len(items), generated_at=now)


@self_router.get("/open-shift-activity", response_model=SelfOpenShiftList)
def list_self_open_shift_activity(
    context: BasicContextDependency,
    session: SessionDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> SelfOpenShiftList:
    start, end = _default_window(start_at, end_at)
    values = _bounded_rows(
        session.scalars(
            select(StaffOpenShift)
            .join(
                StaffOpenShiftEngagement,
                (StaffOpenShiftEngagement.organization_id == StaffOpenShift.organization_id)
                & (StaffOpenShiftEngagement.open_shift_id == StaffOpenShift.id),
            )
            .where(
                StaffOpenShift.organization_id == context.organization.id,
                StaffOpenShiftEngagement.membership_id == context.membership.id,
                StaffOpenShift.starts_at < end,
                StaffOpenShift.ends_at > start,
            )
            .distinct()
            .order_by(StaffOpenShift.starts_at.desc(), StaffOpenShift.id)
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    now = datetime.now(UTC)
    items = [
        self_open_shift_response(
            session, value, viewer_membership_id=context.membership.id, now=now
        )
        for value in values
    ]
    return SelfOpenShiftList(items=items, total=len(items), generated_at=now)


@self_router.post(
    "/open-shifts/{open_shift_id}/interest",
    response_model=OpenShiftEngagementResponse,
    status_code=status.HTTP_201_CREATED,
)
def express_open_shift_interest(
    open_shift_id: UUID,
    payload: ExpressInterest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    ensure_writable(request)
    note = clean_optional_text(payload.note)
    canonical = canonical_json(
        {
            "open_shift_id": open_shift_id,
            "expected_updated_at": payload.expected_updated_at,
            "note": note,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift_engagement",
        event_type="interested",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftEngagementResponse)
    lock_workforce_lane(
        session, context.organization.id, "open-shift", open_shift_id, context.membership.id
    )
    value = open_shift_row(session, context.organization.id, open_shift_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    now = datetime.now(UTC)
    if value.status != "open" or stored_utc(value.starts_at) <= now:
        raise HTTPException(409, detail={"code": "open_shift_required"})
    _require_self_facility(context, value.facility_id)
    if value.source_schedule_id:
        source = schedule_row(session, context.organization.id, value.source_schedule_id)
        if source.membership_id == context.membership.id:
            raise HTTPException(409, detail={"code": "source_educator_ineligible"})
    _, reasons = candidate_eligibility(
        session,
        context.organization.id,
        context.membership.id,
        facility_id=value.facility_id,
        room_id=value.room_id,
        start=stored_utc(value.starts_at),
        end=stored_utc(value.ends_at),
        exclude_schedule_ids={value.source_schedule_id} if value.source_schedule_id else None,
    )
    if reasons:
        raise HTTPException(409, detail={"code": "candidate_ineligible", "reasons": reasons})
    if session.scalar(
        select(StaffOpenShiftEngagement.id).where(
            StaffOpenShiftEngagement.organization_id == context.organization.id,
            StaffOpenShiftEngagement.open_shift_id == value.id,
            StaffOpenShiftEngagement.membership_id == context.membership.id,
            StaffOpenShiftEngagement.kind == "offer",
            StaffOpenShiftEngagement.status == "pending",
            StaffOpenShiftEngagement.expires_at > now,
        )
    ):
        raise HTTPException(409, detail={"code": "pending_offer_exists"})
    if session.scalar(
        select(StaffOpenShiftEngagement.id).where(
            StaffOpenShiftEngagement.organization_id == context.organization.id,
            StaffOpenShiftEngagement.open_shift_id == value.id,
            StaffOpenShiftEngagement.membership_id == context.membership.id,
            StaffOpenShiftEngagement.kind == "interest",
            StaffOpenShiftEngagement.status == "pending",
        )
    ):
        raise HTTPException(409, detail={"code": "pending_interest_exists"})
    engagement = StaffOpenShiftEngagement(
        id=uuid4(),
        organization_id=context.organization.id,
        open_shift_id=value.id,
        membership_id=context.membership.id,
        kind="interest",
        status="pending",
        note=note,
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(engagement)
    response = engagement_response(session, engagement, now=now, capability_scope="self")
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        operation_id=payload.client_operation_id,
        event_type="interested",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-interest:{engagement.id}:{payload.client_operation_id}",
        title="Open shift interest",
        body="A staff member expressed interest in an open shift.",
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        facility_id=value.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_open_shift_engagement.interested",
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
    )
    flush_or_conflict(session, "Open-shift interest conflicts with existing data")
    commit_in_context(session, context)
    return response


@self_router.post(
    "/open-shift-engagements/{engagement_id}/withdraw",
    response_model=OpenShiftEngagementResponse,
)
def withdraw_self_interest(
    engagement_id: UUID,
    payload: EngagementAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift_engagement",
        event_type="withdrawn",
        request_payload=canonical,
        entity_id=engagement_id,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftEngagementResponse)
    lock_workforce_lane(session, context.organization.id, "engagement", engagement_id)
    value = engagement_row(session, context.organization.id, engagement_id, lock=True)
    if value.membership_id != context.membership.id:
        raise HTTPException(404, "Open-shift engagement not found")
    require_expected(value, payload.expected_updated_at)
    if value.kind != "interest" or value.status != "pending":
        raise HTTPException(409, detail={"code": "pending_interest_required"})
    now = datetime.now(UTC)
    value.status = "withdrawn"
    value.terminal_at = now
    value.terminal_by_user_id = context.user.id
    value.terminal_reason = clean_optional_text(payload.note)
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = engagement_response(session, value, now=now, capability_scope="self")
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="withdrawn",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    open_shift = open_shift_row(session, context.organization.id, value.open_shift_id)
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-interest-withdrawn:{value.id}:{payload.client_operation_id}",
        title="Open shift interest withdrawn",
        body="A staff member withdrew interest in an open shift.",
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
        facility_id=open_shift.facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_open_shift_engagement.withdrawn",
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


def _self_offer_action(
    *,
    engagement_id: UUID,
    payload: EngagementAction,
    request: Request,
    context,
    session,
    action: str,
) -> OpenShiftEngagementResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift_engagement",
        event_type=action,
        request_payload=canonical,
        entity_id=engagement_id,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftEngagementResponse)
    initial_engagement = engagement_row(session, context.organization.id, engagement_id)
    if initial_engagement.membership_id != context.membership.id:
        raise HTTPException(404, "Open-shift engagement not found")
    # Every fill/cancel path takes the open-shift row before engagement rows.
    # Keep that single lock order so two acceptances and accept-vs-cancel cannot
    # deadlock or partially observe one another.
    lock_workforce_lane(
        session,
        context.organization.id,
        "open-shift",
        initial_engagement.open_shift_id,
    )
    open_shift = open_shift_row(
        session,
        context.organization.id,
        initial_engagement.open_shift_id,
        lock=True,
    )
    engagement = engagement_row(session, context.organization.id, engagement_id, lock=True)
    if (
        engagement.membership_id != context.membership.id
        or engagement.open_shift_id != open_shift.id
    ):
        raise HTTPException(404, "Open-shift engagement not found")
    now = datetime.now(UTC)
    if engagement.kind != "offer" or engagement.status != "pending":
        raise HTTPException(409, detail={"code": "pending_offer_required"})
    if stored_utc(engagement.expires_at) <= now:
        raise HTTPException(409, detail={"code": "offer_expired"})
    require_expected(engagement, payload.expected_updated_at)
    if open_shift.status != "open" or stored_utc(open_shift.starts_at) <= now:
        raise HTTPException(409, detail={"code": "open_shift_required"})
    if action == "declined":
        engagement.status = "declined"
        engagement.terminal_at = now
        engagement.terminal_by_user_id = context.user.id
        engagement.terminal_reason = clean_optional_text(payload.note)
        engagement.last_operation_id = payload.client_operation_id
        engagement.updated_at = now
        response = engagement_response(session, engagement, now=now, capability_scope="self")
        _store_event(
            session,
            context=context,
            entity_type="staff_open_shift_engagement",
            entity_id=engagement.id,
            operation_id=payload.client_operation_id,
            event_type="declined",
            request_payload=canonical,
            response=response,
            occurred_at=now,
        )
        _notify_managers(
            session,
            context=context,
            event_key=f"staff-open-shift-offer-declined:{engagement.id}:{payload.client_operation_id}",
            title="Open shift offer declined",
            body="A staff member declined an open shift offer.",
            entity_type="staff_open_shift_engagement",
            entity_id=engagement.id,
            facility_id=open_shift.facility_id,
        )
        _invalidate(
            session,
            organization_id=context.organization.id,
            user_ids=set(_manager_user_ids(session, context.organization.id)) | {context.user.id},
            event_type="staff_open_shift_engagement.declined",
            entity_type="staff_open_shift_engagement",
            entity_id=engagement.id,
        )
        commit_in_context(session, context)
        return response

    lock_schedule_lanes(session, context.organization.id, {context.membership.id})
    accepted_membership, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=context.user.id,
        facility_id=open_shift.facility_id,
        room_id=open_shift.room_id,
    )
    if accepted_membership.id != context.membership.id:
        raise HTTPException(409, detail={"code": "offer_membership_changed"})
    source = _validate_replacement_source(
        session,
        context.organization.id,
        source_schedule_id=open_shift.source_schedule_id,
        facility_id=open_shift.facility_id,
        room_id=open_shift.room_id,
        start=stored_utc(open_shift.starts_at),
        end=stored_utc(open_shift.ends_at),
        lock=open_shift.source_schedule_id is not None,
    )
    if source and source.membership_id == context.membership.id:
        raise HTTPException(409, detail={"code": "source_educator_ineligible"})
    _, reasons = candidate_eligibility(
        session,
        context.organization.id,
        context.membership.id,
        facility_id=open_shift.facility_id,
        room_id=open_shift.room_id,
        start=stored_utc(open_shift.starts_at),
        end=stored_utc(open_shift.ends_at),
        exclude_schedule_ids={source.id} if source else None,
    )
    if reasons:
        raise HTTPException(409, detail={"code": "candidate_ineligible", "reasons": reasons})
    schedule_operation = uuid5(
        NAMESPACE_URL, f"caresync:open-shift:{payload.client_operation_id}:created"
    )
    schedule = ScheduledStaffShift(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=open_shift.facility_id,
        room_id=open_shift.room_id,
        scheduled_start_at=open_shift.starts_at,
        scheduled_end_at=open_shift.ends_at,
        notes=open_shift.notes,
        status="published",
        response_status="acknowledged",
        responded_at=now,
        create_operation_id=schedule_operation,
        created_by_user_id=context.user.id,
        published_at=now,
        published_by_user_id=context.user.id,
        origin_type="open_shift",
        origin_id=open_shift.id,
        origin_occurrence_key=str(engagement.id),
        supersedes_schedule_id=source.id if source else None,
        created_at=now,
        updated_at=now,
    )
    session.add(schedule)
    is_available, _ = schedule_matches_availability(session, schedule)
    if not is_available:
        schedule.availability_override_reason = (
            "Staff explicitly accepted this open shift outside declared recurring availability."
        )
    add_event(
        session,
        schedule,
        operation_id=schedule_operation,
        actor_user_id=context.user.id,
        event_type="created",
        payload=event_payload(
            staff_user_id=context.user.id,
            facility_id=schedule.facility_id,
            room_id=schedule.room_id,
            start=stored_utc(schedule.scheduled_start_at),
            end=stored_utc(schedule.scheduled_end_at),
            notes=schedule.notes,
        ),
        occurred_at=now,
    )
    for suffix, event_type in (("published", "published"), ("acknowledged", "acknowledged")):
        add_event(
            session,
            schedule,
            operation_id=uuid5(
                NAMESPACE_URL, f"caresync:open-shift:{payload.client_operation_id}:{suffix}"
            ),
            actor_user_id=context.user.id,
            event_type=event_type,
            payload={"source": "accepted_open_shift_offer"},
            occurred_at=now,
        )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.created_from_open_shift",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        details={"operation_id": str(schedule_operation)},
    )
    if source:
        source.status = "cancelled"
        source.cancelled_at = now
        source.cancelled_by_user_id = context.user.id
        source.cancellation_reason = "Replaced by an accepted open-shift offer"
        source.updated_at = now
        add_event(
            session,
            source,
            operation_id=uuid5(
                NAMESPACE_URL, f"caresync:open-shift:{payload.client_operation_id}:source-cancel"
            ),
            actor_user_id=context.user.id,
            event_type="cancelled",
            payload={"reason": source.cancellation_reason},
            occurred_at=now,
        )
        audit(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action="staff_schedule.cancelled_for_open_shift",
            entity_type="staff_schedule",
            entity_id=source.id,
            details={"operation_id": str(payload.client_operation_id)},
        )
    engagement.status = "accepted"
    engagement.result_schedule_id = schedule.id
    engagement.terminal_at = now
    engagement.terminal_by_user_id = context.user.id
    engagement.terminal_reason = clean_optional_text(payload.note)
    engagement.last_operation_id = payload.client_operation_id
    engagement.updated_at = now
    open_shift.status = "filled"
    open_shift.result_schedule_id = schedule.id
    open_shift.filled_at = now
    open_shift.filled_by_user_id = context.user.id
    filled_operation_id = uuid5(
        NAMESPACE_URL,
        f"caresync:open-shift:{payload.client_operation_id}:filled",
    )
    open_shift.last_operation_id = filled_operation_id
    open_shift.updated_at = now
    add_workforce_event(
        session,
        organization_id=context.organization.id,
        entity_type="staff_open_shift",
        entity_id=open_shift.id,
        operation_id=filled_operation_id,
        actor_user_id=context.user.id,
        event_type="filled",
        payload=workforce_receipt_payload(
            canonical_json(
                {
                    "source_operation_id": payload.client_operation_id,
                    "accepted_engagement_id": engagement.id,
                }
            ),
            result_schedule_id=str(schedule.id),
        ),
        occurred_at=now,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_open_shift.filled",
        entity_type="staff_open_shift",
        entity_id=open_shift.id,
        details={"operation_id": str(filled_operation_id)},
    )
    competing = list(
        session.scalars(
            select(StaffOpenShiftEngagement)
            .where(
                StaffOpenShiftEngagement.organization_id == context.organization.id,
                StaffOpenShiftEngagement.open_shift_id == open_shift.id,
                StaffOpenShiftEngagement.id != engagement.id,
                StaffOpenShiftEngagement.status == "pending",
            )
            .with_for_update()
        )
    )
    competing_user_ids: set[UUID] = set()
    terminalized_ids: list[str] = []
    for item in competing:
        competing_user_ids.add(
            _terminalize_engagement(
                session,
                context=context,
                engagement=item,
                status_value="rejected" if item.kind == "interest" else "superseded",
                reason="Another offer filled this open shift",
                source_operation_id=payload.client_operation_id,
                now=now,
                notification_title="Open shift filled",
                notification_body="Another staff member filled an open shift you responded to.",
            )
        )
        terminalized_ids.append(str(item.id))
    response = engagement_response(session, engagement, now=now, capability_scope="self")
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        operation_id=payload.client_operation_id,
        event_type="accepted",
        request_payload=canonical,
        response=response,
        occurred_at=now,
        receipt_extra={
            "filled_operation_id": str(filled_operation_id),
            "result_schedule_id": str(schedule.id),
            "terminalized_engagement_ids": terminalized_ids,
        },
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-offer-accepted:{engagement.id}:{payload.client_operation_id}",
        title="Open shift filled",
        body="A staff member accepted an open shift offer.",
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
        facility_id=open_shift.facility_id,
    )
    affected_user_ids = (
        set(_manager_user_ids(session, context.organization.id))
        | {context.user.id}
        | competing_user_ids
    )
    if source:
        source_user_id = _notify_staff(
            session,
            context=context,
            membership_id=source.membership_id,
            event_key=(
                f"staff-open-shift-source-replaced:{source.id}:{payload.client_operation_id}"
            ),
            title="Assigned shift replaced",
            body="Another staff member accepted coverage for one of your assigned shifts.",
            entity_type="staff_open_shift",
            entity_id=open_shift.id,
            action_path="/staff/schedule",
        )
        affected_user_ids.add(source_user_id)
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=affected_user_ids,
        event_type="staff_open_shift_engagement.accepted",
        entity_type="staff_open_shift_engagement",
        entity_id=engagement.id,
    )
    flush_or_conflict(session, "Open shift was filled by another operation")
    commit_in_context(session, context)
    return response


@self_router.post(
    "/open-shift-offers/{engagement_id}/accept",
    response_model=OpenShiftEngagementResponse,
)
def accept_open_shift_offer(
    engagement_id: UUID,
    payload: EngagementAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    return _self_offer_action(
        engagement_id=engagement_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="accepted",
    )


@self_router.post(
    "/open-shift-offers/{engagement_id}/decline",
    response_model=OpenShiftEngagementResponse,
)
def decline_open_shift_offer(
    engagement_id: UUID,
    payload: EngagementAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    return _self_offer_action(
        engagement_id=engagement_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="declined",
    )


def _substitute_row(
    session,
    organization_id: UUID,
    membership_id: UUID,
    facility_id: UUID,
    *,
    lock: bool = False,
) -> StaffSubstituteProfile | None:
    statement = select(StaffSubstituteProfile).where(
        StaffSubstituteProfile.organization_id == organization_id,
        StaffSubstituteProfile.membership_id == membership_id,
        StaffSubstituteProfile.facility_id == facility_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


@self_router.get("/substitute-profiles", response_model=SubstituteProfileList)
def list_substitute_profiles(
    context: BasicContextDependency,
    session: SessionDependency,
) -> SubstituteProfileList:
    values = _bounded_rows(
        session.scalars(
            select(StaffSubstituteProfile)
            .where(
                StaffSubstituteProfile.organization_id == context.organization.id,
                StaffSubstituteProfile.membership_id == context.membership.id,
            )
            .order_by(StaffSubstituteProfile.facility_id)
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    return SubstituteProfileList(
        items=[substitute_profile_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@self_router.put("/substitute-profiles/{facility_id}", response_model=SubstituteProfileResponse)
def replace_substitute_profile(
    facility_id: UUID,
    payload: SubstituteProfileReplace,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> SubstituteProfileResponse:
    ensure_writable(request)
    _require_self_facility(context, facility_id)
    note = clean_optional_text(payload.note)
    canonical = canonical_json(
        {
            "facility_id": facility_id,
            "expected_updated_at": payload.expected_updated_at,
            "note": note,
        }
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_substitute_profile",
        event_type="replaced",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, SubstituteProfileResponse)
    facility_row(session, context.organization.id, facility_id)
    lock_workforce_lane(
        session, context.organization.id, "substitute", context.membership.id, facility_id
    )
    value = _substitute_row(
        session,
        context.organization.id,
        context.membership.id,
        facility_id,
        lock=True,
    )
    if value is not None:
        if payload.expected_updated_at is None:
            raise HTTPException(409, detail={"code": "stale_exchange_resource"})
        require_expected(value, payload.expected_updated_at)
    elif payload.expected_updated_at is not None:
        raise HTTPException(409, detail={"code": "stale_exchange_resource"})
    now = datetime.now(UTC)
    if value is None:
        value = StaffSubstituteProfile(
            id=uuid4(),
            organization_id=context.organization.id,
            membership_id=context.membership.id,
            facility_id=facility_id,
            is_specified=True,
            is_opted_in=True,
            note=note,
            last_operation_id=payload.client_operation_id,
            created_at=now,
            updated_at=now,
        )
        session.add(value)
    else:
        value.is_specified = True
        value.is_opted_in = True
        value.note = note
        value.last_operation_id = payload.client_operation_id
        value.updated_at = now
    response = substitute_profile_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_substitute_profile",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="replaced",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-substitute-replaced:{value.id}:{payload.client_operation_id}",
        title="Substitute availability updated",
        body="A staff member updated substitute availability for this facility.",
        entity_type="staff_substitute_profile",
        entity_id=value.id,
        facility_id=facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)) | {context.user.id},
        event_type="staff_substitute_profile.replaced",
        entity_type="staff_substitute_profile",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Substitute preference conflicts with existing data")
    commit_in_context(session, context)
    return response


@self_router.delete("/substitute-profiles/{facility_id}", response_model=SubstituteProfileResponse)
def remove_substitute_profile(
    facility_id: UUID,
    payload: ExchangeOptimisticAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> SubstituteProfileResponse:
    ensure_writable(request)
    canonical = canonical_json(
        {"facility_id": facility_id, "expected_updated_at": payload.expected_updated_at}
    )
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_substitute_profile",
        event_type="removed",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, SubstituteProfileResponse)
    lock_workforce_lane(
        session, context.organization.id, "substitute", context.membership.id, facility_id
    )
    value = _substitute_row(
        session,
        context.organization.id,
        context.membership.id,
        facility_id,
        lock=True,
    )
    if value is None or not value.is_specified:
        raise HTTPException(404, "Substitute preference not found")
    require_expected(value, payload.expected_updated_at)
    now = datetime.now(UTC)
    value.is_specified = False
    value.is_opted_in = False
    value.note = None
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = substitute_profile_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_substitute_profile",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="removed",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-substitute-removed:{value.id}:{payload.client_operation_id}",
        title="Substitute availability updated",
        body="A staff member is no longer available as a substitute at this facility.",
        entity_type="staff_substitute_profile",
        entity_id=value.id,
        facility_id=facility_id,
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=set(_manager_user_ids(session, context.organization.id)) | {context.user.id},
        event_type="staff_substitute_profile.removed",
        entity_type="staff_substitute_profile",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@manager_router.get("/substitutes", response_model=SubstituteManagerList)
def list_substitutes(
    facility_id: UUID,
    context: StaffAccessContext,
    session: SessionDependency,
) -> SubstituteManagerList:
    facility_row(session, context.organization.id, facility_id)
    values = _bounded_rows(
        session.scalars(
            select(StaffSubstituteProfile)
            .where(
                StaffSubstituteProfile.organization_id == context.organization.id,
                StaffSubstituteProfile.facility_id == facility_id,
                StaffSubstituteProfile.is_specified.is_(True),
                StaffSubstituteProfile.is_opted_in.is_(True),
            )
            .order_by(StaffSubstituteProfile.created_at)
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    items = [substitute_manager_response(session, value) for value in values]
    return SubstituteManagerList(items=items, total=len(items), generated_at=datetime.now(UTC))


def _eligible_source_schedule(
    session,
    organization_id: UUID,
    schedule_id: UUID,
    *,
    membership_id: UUID | None = None,
    lock: bool = False,
) -> ScheduledStaffShift:
    value = schedule_row(session, organization_id, schedule_id, lock=lock)
    if membership_id is not None and value.membership_id != membership_id:
        raise HTTPException(404, "Scheduled shift not found")
    if (
        value.status != "published"
        or value.response_status != "acknowledged"
        or stored_utc(value.scheduled_start_at) <= datetime.now(UTC)
        or has_clock_link(session, organization_id, value.id)
    ):
        raise HTTPException(409, detail={"code": "swap_source_ineligible"})
    return value


@self_router.get("/swaps", response_model=ShiftSwapList)
def list_self_swaps(
    context: BasicContextDependency,
    session: SessionDependency,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ShiftSwapList:
    start, end = _default_window(start_at, end_at)
    values = _bounded_rows(
        session.scalars(
            select(StaffShiftSwapRequest)
            .join(
                ScheduledStaffShift,
                (ScheduledStaffShift.organization_id == StaffShiftSwapRequest.organization_id)
                & (ScheduledStaffShift.id == StaffShiftSwapRequest.requester_schedule_id),
            )
            .where(
                StaffShiftSwapRequest.organization_id == context.organization.id,
                ScheduledStaffShift.scheduled_start_at < end,
                ScheduledStaffShift.scheduled_end_at > start,
                or_(
                    StaffShiftSwapRequest.requester_membership_id == context.membership.id,
                    StaffShiftSwapRequest.counterparty_membership_id == context.membership.id,
                ),
            )
            .order_by(StaffShiftSwapRequest.created_at.desc())
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    return ShiftSwapList(
        items=[
            swap_response(session, value, viewer_membership_id=context.membership.id)
            for value in values
        ],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


@self_router.get("/schedules/{schedule_id}/swap-candidates", response_model=SwapCandidateList)
def list_swap_candidates(
    schedule_id: UUID,
    context: BasicContextDependency,
    session: SessionDependency,
    kind: str = Query(pattern="^(cover|trade)$"),
) -> SwapCandidateList:
    source = _eligible_source_schedule(
        session,
        context.organization.id,
        schedule_id,
        membership_id=context.membership.id,
    )
    if schedule_exchange_pending(session, context.organization.id, source.id):
        raise HTTPException(409, detail={"code": "schedule_exchange_pending"})
    assignment_filters = [
        MembershipRoomAssignment.organization_id == context.organization.id,
        MembershipRoomAssignment.facility_id == source.facility_id,
        MembershipRoomAssignment.is_active.is_(True),
    ]
    if source.room_id is not None:
        assignment_filters.append(MembershipRoomAssignment.room_id == source.room_id)
    memberships = _bounded_rows(
        session.scalars(
            select(OrganizationMembership)
            .join(
                Role,
                (Role.organization_id == OrganizationMembership.organization_id)
                & (Role.id == OrganizationMembership.role_id),
            )
            .join(
                MembershipRoomAssignment,
                (MembershipRoomAssignment.organization_id == OrganizationMembership.organization_id)
                & (MembershipRoomAssignment.membership_id == OrganizationMembership.id),
            )
            .where(
                OrganizationMembership.organization_id == context.organization.id,
                OrganizationMembership.status == "active",
                OrganizationMembership.id != context.membership.id,
                Role.key == "educator",
                *assignment_filters,
            )
            .distinct()
            .order_by(OrganizationMembership.id)
            .limit(MAX_LIST_ITEMS + 1)
        )
    )
    items = []
    if kind == "cover":
        items = [
            swap_candidate(session, source, membership, kind="cover", counterparty_schedule=None)
            for membership in memberships
        ]
    else:
        membership_ids = {value.id for value in memberships}
        now = datetime.now(UTC)
        schedules = _bounded_rows(
            session.scalars(
                select(ScheduledStaffShift)
                .where(
                    ScheduledStaffShift.organization_id == context.organization.id,
                    ScheduledStaffShift.facility_id == source.facility_id,
                    ScheduledStaffShift.membership_id.in_(membership_ids or [UUID(int=0)]),
                    ScheduledStaffShift.status == "published",
                    ScheduledStaffShift.response_status == "acknowledged",
                    ScheduledStaffShift.scheduled_start_at > now,
                    ScheduledStaffShift.scheduled_start_at
                    < now + timedelta(days=MAX_SWAP_CANDIDATE_DAYS),
                )
                .order_by(ScheduledStaffShift.scheduled_start_at, ScheduledStaffShift.id)
                .limit(MAX_LIST_ITEMS + 1)
            )
        )
        by_membership = {value.id: value for value in memberships}
        items = [
            swap_candidate(
                session,
                source,
                by_membership[schedule.membership_id],
                kind="trade",
                counterparty_schedule=schedule,
            )
            for schedule in schedules
        ]
    return SwapCandidateList(items=items, total=len(items), generated_at=datetime.now(UTC))


@self_router.post("/swaps", response_model=ShiftSwapResponse, status_code=status.HTTP_201_CREATED)
def create_swap(
    payload: SwapRequestCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ShiftSwapResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_swap",
        event_type="requested",
        request_payload=canonical,
    )
    if receipt:
        return _receipt_response(receipt, ShiftSwapResponse)
    _lock_schedule_exchange_sources(
        session,
        context.organization.id,
        {payload.requester_schedule_id, payload.counterparty_schedule_id},
    )
    lock_workforce_lane(
        session,
        context.organization.id,
        "swap",
        payload.requester_schedule_id,
        payload.counterparty_schedule_id or payload.counterparty_membership_id,
    )
    lock_schedule_lanes(
        session,
        context.organization.id,
        {context.membership.id, payload.counterparty_membership_id},
    )
    source = _eligible_source_schedule(
        session,
        context.organization.id,
        payload.requester_schedule_id,
        membership_id=context.membership.id,
        lock=True,
    )
    if schedule_exchange_pending(session, context.organization.id, source.id):
        raise HTTPException(409, detail={"code": "schedule_exchange_pending"})
    counterparty = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == payload.counterparty_membership_id,
            OrganizationMembership.status == "active",
        )
    )
    if counterparty is None or counterparty.id == context.membership.id:
        raise HTTPException(422, detail={"code": "invalid_swap_counterparty"})
    counterparty_schedule = None
    if payload.kind == "trade":
        counterparty_schedule = _eligible_source_schedule(
            session,
            context.organization.id,
            payload.counterparty_schedule_id,
            membership_id=counterparty.id,
            lock=True,
        )
        if counterparty_schedule.facility_id != source.facility_id:
            raise HTTPException(422, detail={"code": "swap_facility_mismatch"})
        if schedule_exchange_pending(
            session,
            context.organization.id,
            counterparty_schedule.id,
        ):
            raise HTTPException(409, detail={"code": "schedule_exchange_pending"})
    candidate = swap_candidate(
        session,
        source,
        counterparty,
        kind=payload.kind,
        counterparty_schedule=counterparty_schedule,
    )
    if not candidate.can_propose:
        raise HTTPException(
            409,
            detail={"code": "swap_candidate_ineligible", "reasons": candidate.eligibility_reasons},
        )
    now = datetime.now(UTC)
    value = StaffShiftSwapRequest(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=source.facility_id,
        kind=payload.kind,
        status="pending_counterparty",
        requester_membership_id=context.membership.id,
        counterparty_membership_id=counterparty.id,
        requester_schedule_id=source.id,
        requester_schedule_updated_at=stored_utc(source.updated_at),
        counterparty_schedule_id=counterparty_schedule.id if counterparty_schedule else None,
        counterparty_schedule_updated_at=(
            stored_utc(counterparty_schedule.updated_at) if counterparty_schedule else None
        ),
        note=clean_optional_text(payload.note),
        create_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_by_user_id=context.user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(value)
    response = swap_response(session, value, viewer_membership_id=context.membership.id)
    _store_event(
        session,
        context=context,
        entity_type="staff_shift_swap",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="requested",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    user_id = _notify_staff(
        session,
        context=context,
        membership_id=counterparty.id,
        event_key=f"staff-shift-swap-requested:{value.id}:{payload.client_operation_id}",
        title="Shift exchange request",
        body="Another staff member proposed a whole-shift exchange.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        action_path="/staff/self/exchange/swaps",
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids={user_id},
        event_type="staff_shift_swap.requested",
        entity_type="staff_shift_swap",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Shift already has a pending exchange")
    commit_in_context(session, context)
    return response


def _peer_swap_action(
    *,
    swap_id: UUID,
    payload: SwapResponseAction,
    request: Request,
    context,
    session,
    action: str,
) -> ShiftSwapResponse:
    ensure_writable(request)
    response_note = clean_optional_text(payload.note)
    if action == "decline" and response_note is None:
        raise HTTPException(422, detail={"code": "decline_reason_required"})
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    event_type = "counterparty_accepted" if action == "accept" else "declined"
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_swap",
        event_type=event_type,
        request_payload=canonical,
        entity_id=swap_id,
    )
    if receipt:
        return _receipt_response(receipt, ShiftSwapResponse)
    lock_workforce_lane(session, context.organization.id, "swap", swap_id)
    value = swap_row(session, context.organization.id, swap_id, lock=True)
    if value.counterparty_membership_id != context.membership.id:
        raise HTTPException(404, "Shift swap not found")
    require_expected(value, payload.expected_updated_at)
    if value.status != "pending_counterparty":
        raise HTTPException(409, detail={"code": "counterparty_response_unavailable"})
    if action == "accept":
        lock_schedule_lanes(
            session,
            context.organization.id,
            {value.requester_membership_id, value.counterparty_membership_id},
        )
        requester_schedule = _eligible_source_schedule(
            session,
            context.organization.id,
            value.requester_schedule_id,
            membership_id=value.requester_membership_id,
            lock=True,
        )
        if stored_utc(requester_schedule.updated_at) != stored_utc(
            value.requester_schedule_updated_at
        ):
            raise HTTPException(409, detail={"code": "swap_source_changed"})
        if value.counterparty_schedule_id:
            counterparty_schedule = _eligible_source_schedule(
                session,
                context.organization.id,
                value.counterparty_schedule_id,
                membership_id=value.counterparty_membership_id,
                lock=True,
            )
            if stored_utc(counterparty_schedule.updated_at) != stored_utc(
                value.counterparty_schedule_updated_at
            ):
                raise HTTPException(409, detail={"code": "swap_source_changed"})
    now = datetime.now(UTC)
    value.counterparty_responded_at = now
    value.counterparty_responded_by_user_id = context.user.id
    value.counterparty_response_note = response_note
    value.status = "pending_manager" if action == "accept" else "declined"
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = swap_response(session, value, viewer_membership_id=context.membership.id)
    _store_event(
        session,
        context=context,
        entity_type="staff_shift_swap",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type=event_type,
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    requester_user_id = _notify_staff(
        session,
        context=context,
        membership_id=value.requester_membership_id,
        event_key=f"staff-shift-swap-{action}:{value.id}:{payload.client_operation_id}",
        title="Shift exchange updated",
        body=(
            "Your proposed exchange is awaiting manager review."
            if action == "accept"
            else "The proposed shift exchange was declined."
        ),
        entity_type="staff_shift_swap",
        entity_id=value.id,
        action_path="/staff/self/exchange/swaps",
    )
    target_users = {requester_user_id}
    if action == "accept":
        _notify_managers(
            session,
            context=context,
            event_key=f"staff-shift-swap-manager-review:{value.id}:{payload.client_operation_id}",
            title="Shift exchange needs review",
            body="Two staff members consented to a whole-shift exchange.",
            entity_type="staff_shift_swap",
            entity_id=value.id,
            facility_id=value.facility_id,
        )
        target_users.update(_manager_user_ids(session, context.organization.id))
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=target_users,
        event_type=f"staff_shift_swap.{event_type}",
        entity_type="staff_shift_swap",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@self_router.post("/swaps/{swap_id}/accept", response_model=ShiftSwapResponse)
def accept_swap(
    swap_id: UUID,
    payload: SwapResponseAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ShiftSwapResponse:
    return _peer_swap_action(
        swap_id=swap_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="accept",
    )


@self_router.post("/swaps/{swap_id}/decline", response_model=ShiftSwapResponse)
def decline_swap(
    swap_id: UUID,
    payload: SwapResponseAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ShiftSwapResponse:
    return _peer_swap_action(
        swap_id=swap_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        action="decline",
    )


@self_router.post("/swaps/{swap_id}/cancel", response_model=ShiftSwapResponse)
def cancel_swap(
    swap_id: UUID,
    payload: SwapResponseAction,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ShiftSwapResponse:
    ensure_writable(request)
    reason = clean_optional_text(payload.note)
    if reason is None:
        raise HTTPException(422, detail={"code": "cancellation_reason_required"})
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_swap",
        event_type="cancelled",
        request_payload=canonical,
        entity_id=swap_id,
    )
    if receipt:
        return _receipt_response(receipt, ShiftSwapResponse)
    lock_workforce_lane(session, context.organization.id, "swap", swap_id)
    value = swap_row(session, context.organization.id, swap_id, lock=True)
    if value.requester_membership_id != context.membership.id:
        raise HTTPException(404, "Shift swap not found")
    require_expected(value, payload.expected_updated_at)
    if value.status not in {"pending_counterparty", "pending_manager"}:
        raise HTTPException(409, detail={"code": "swap_not_cancellable"})
    was_pending_manager = value.status == "pending_manager"
    now = datetime.now(UTC)
    value.status = "cancelled"
    value.cancelled_at = now
    value.cancelled_by_user_id = context.user.id
    value.cancellation_reason = reason
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = swap_response(session, value, viewer_membership_id=context.membership.id)
    _store_event(
        session,
        context=context,
        entity_type="staff_shift_swap",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="cancelled",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    counterparty_user_id = _notify_staff(
        session,
        context=context,
        membership_id=value.counterparty_membership_id,
        event_key=f"staff-shift-swap-cancelled:{value.id}:{payload.client_operation_id}",
        title="Shift exchange cancelled",
        body="A proposed shift exchange was cancelled.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        action_path="/staff/self/exchange/swaps",
    )
    target_user_ids = {counterparty_user_id}
    if was_pending_manager:
        _notify_managers(
            session,
            context=context,
            event_key=f"staff-shift-swap-cancelled-manager:{value.id}:{payload.client_operation_id}",
            title="Shift exchange cancelled",
            body="A staff member cancelled an exchange that was awaiting manager review.",
            entity_type="staff_shift_swap",
            entity_id=value.id,
            facility_id=value.facility_id,
        )
        target_user_ids.update(_manager_user_ids(session, context.organization.id))
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=target_user_ids,
        event_type="staff_shift_swap.cancelled",
        entity_type="staff_shift_swap",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@manager_router.get("/swaps", response_model=ShiftSwapList)
def list_manager_swaps(
    context: StaffAccessContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    swap_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(pending_counterparty|pending_manager|approved|declined|cancelled|rejected)$",
    ),
) -> ShiftSwapList:
    start, end = _default_window(start_at, end_at)
    statement = (
        select(StaffShiftSwapRequest)
        .join(
            ScheduledStaffShift,
            (ScheduledStaffShift.organization_id == StaffShiftSwapRequest.organization_id)
            & (ScheduledStaffShift.id == StaffShiftSwapRequest.requester_schedule_id),
        )
        .where(
            StaffShiftSwapRequest.organization_id == context.organization.id,
            ScheduledStaffShift.scheduled_start_at < end,
            ScheduledStaffShift.scheduled_end_at > start,
        )
    )
    if facility_id:
        statement = statement.where(StaffShiftSwapRequest.facility_id == facility_id)
    if swap_status:
        statement = statement.where(StaffShiftSwapRequest.status == swap_status)
    values = _bounded_rows(
        session.scalars(
            statement.order_by(StaffShiftSwapRequest.created_at.desc()).limit(MAX_LIST_ITEMS + 1)
        )
    )
    return ShiftSwapList(
        items=[swap_response(session, value) for value in values],
        total=len(values),
        generated_at=datetime.now(UTC),
    )


def _create_swap_replacement(
    session,
    *,
    context,
    swap: StaffShiftSwapRequest,
    original: ScheduledStaffShift,
    target_membership_id: UUID,
    occurrence_key: str,
    operation_id: UUID,
    now: datetime,
) -> ScheduledStaffShift:
    target_user_id = session.scalar(
        select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == target_membership_id,
        )
    )
    if target_user_id is None:
        raise HTTPException(409, detail={"code": "swap_staff_missing"})
    schedule = ScheduledStaffShift(
        id=uuid4(),
        organization_id=context.organization.id,
        membership_id=target_membership_id,
        facility_id=original.facility_id,
        room_id=original.room_id,
        scheduled_start_at=original.scheduled_start_at,
        scheduled_end_at=original.scheduled_end_at,
        notes=original.notes,
        status="published",
        response_status="acknowledged",
        responded_at=now,
        create_operation_id=operation_id,
        created_by_user_id=context.user.id,
        published_at=now,
        published_by_user_id=context.user.id,
        origin_type="swap",
        origin_id=swap.id,
        origin_occurrence_key=occurrence_key,
        supersedes_schedule_id=original.id,
        created_at=now,
        updated_at=now,
    )
    session.add(schedule)
    is_available, _ = schedule_matches_availability(session, schedule)
    if not is_available:
        schedule.availability_override_reason = (
            "Staff consented to this whole-shift exchange outside declared recurring availability."
        )
    add_event(
        session,
        schedule,
        operation_id=operation_id,
        actor_user_id=context.user.id,
        event_type="created",
        payload=event_payload(
            staff_user_id=target_user_id,
            facility_id=schedule.facility_id,
            room_id=schedule.room_id,
            start=stored_utc(schedule.scheduled_start_at),
            end=stored_utc(schedule.scheduled_end_at),
            notes=schedule.notes,
        ),
        occurred_at=now,
    )
    for suffix, event_type in (("published", "published"), ("acknowledged", "acknowledged")):
        add_event(
            session,
            schedule,
            operation_id=uuid5(NAMESPACE_URL, f"{operation_id}:{suffix}"),
            actor_user_id=context.user.id,
            event_type=event_type,
            payload={"source": "approved_shift_swap"},
            occurred_at=now,
        )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_schedule.created_from_swap",
        entity_type="staff_schedule",
        entity_id=schedule.id,
        details={"operation_id": str(operation_id)},
    )
    return schedule


@manager_router.post("/swaps/{swap_id}/approve", response_model=ShiftSwapResponse)
def approve_swap(
    swap_id: UUID,
    payload: ExchangeOptimisticAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ShiftSwapResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_swap",
        event_type="approved",
        request_payload=canonical,
        entity_id=swap_id,
    )
    if receipt:
        return _receipt_response(receipt, ShiftSwapResponse)
    lock_workforce_lane(session, context.organization.id, "swap", swap_id)
    value = swap_row(session, context.organization.id, swap_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.status != "pending_manager":
        raise HTTPException(409, detail={"code": "manager_review_unavailable"})
    lock_schedule_lanes(
        session,
        context.organization.id,
        {value.requester_membership_id, value.counterparty_membership_id},
    )
    schedule_ids = [value.requester_schedule_id]
    if value.counterparty_schedule_id:
        schedule_ids.append(value.counterparty_schedule_id)
    locked = list(
        session.scalars(
            select(ScheduledStaffShift)
            .where(
                ScheduledStaffShift.organization_id == context.organization.id,
                ScheduledStaffShift.id.in_(schedule_ids),
            )
            .order_by(ScheduledStaffShift.id)
            .with_for_update()
        )
    )
    by_id = {schedule.id: schedule for schedule in locked}
    requester_schedule = by_id.get(value.requester_schedule_id)
    counterparty_schedule = (
        by_id.get(value.counterparty_schedule_id) if value.counterparty_schedule_id else None
    )
    if requester_schedule is None or (
        value.counterparty_schedule_id and counterparty_schedule is None
    ):
        raise HTTPException(409, detail={"code": "swap_source_missing"})
    now = datetime.now(UTC)
    if (
        requester_schedule.status != "published"
        or requester_schedule.response_status != "acknowledged"
        or stored_utc(requester_schedule.scheduled_start_at) <= now
        or stored_utc(requester_schedule.updated_at)
        != stored_utc(value.requester_schedule_updated_at)
        or has_clock_link(session, context.organization.id, requester_schedule.id)
    ):
        raise HTTPException(409, detail={"code": "swap_source_changed"})
    if counterparty_schedule and (
        counterparty_schedule.status != "published"
        or counterparty_schedule.response_status != "acknowledged"
        or stored_utc(counterparty_schedule.scheduled_start_at) <= now
        or stored_utc(counterparty_schedule.updated_at)
        != stored_utc(value.counterparty_schedule_updated_at)
        or has_clock_link(session, context.organization.id, counterparty_schedule.id)
    ):
        raise HTTPException(409, detail={"code": "swap_source_changed"})
    counterparty_membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == value.counterparty_membership_id,
        )
    )
    if counterparty_membership is None:
        raise HTTPException(409, detail={"code": "swap_staff_missing"})
    requester_membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == value.requester_membership_id,
        )
    )
    if requester_membership is None:
        raise HTTPException(409, detail={"code": "swap_staff_missing"})
    validated_counterparty, _, _, _ = validate_assignment(
        session,
        context.organization.id,
        staff_user_id=counterparty_membership.user_id,
        facility_id=requester_schedule.facility_id,
        room_id=requester_schedule.room_id,
    )
    if validated_counterparty.id != counterparty_membership.id:
        raise HTTPException(409, detail={"code": "swap_staff_changed"})
    if counterparty_schedule is not None:
        validated_requester, _, _, _ = validate_assignment(
            session,
            context.organization.id,
            staff_user_id=requester_membership.user_id,
            facility_id=counterparty_schedule.facility_id,
            room_id=counterparty_schedule.room_id,
        )
        if validated_requester.id != requester_membership.id:
            raise HTTPException(409, detail={"code": "swap_staff_changed"})
    candidate = swap_candidate(
        session,
        requester_schedule,
        counterparty_membership,
        kind=value.kind,
        counterparty_schedule=counterparty_schedule,
        exclude_swap_id=value.id,
    )
    if not candidate.can_propose:
        raise HTTPException(
            409,
            detail={"code": "swap_candidate_ineligible", "reasons": candidate.eligibility_reasons},
        )
    first_operation = uuid5(
        NAMESPACE_URL, f"caresync:swap:{payload.client_operation_id}:requester-replacement"
    )
    first = _create_swap_replacement(
        session,
        context=context,
        swap=value,
        original=requester_schedule,
        target_membership_id=value.counterparty_membership_id,
        occurrence_key="requester",
        operation_id=first_operation,
        now=now,
    )
    second = None
    if counterparty_schedule:
        second_operation = uuid5(
            NAMESPACE_URL,
            f"caresync:swap:{payload.client_operation_id}:counterparty-replacement",
        )
        second = _create_swap_replacement(
            session,
            context=context,
            swap=value,
            original=counterparty_schedule,
            target_membership_id=value.requester_membership_id,
            occurrence_key="counterparty",
            operation_id=second_operation,
            now=now,
        )
    for original, label in (
        (requester_schedule, "requester"),
        (counterparty_schedule, "counterparty"),
    ):
        if original is None:
            continue
        original.status = "cancelled"
        original.cancelled_at = now
        original.cancelled_by_user_id = context.user.id
        original.cancellation_reason = "Replaced by an approved whole-shift exchange"
        original.updated_at = now
        add_event(
            session,
            original,
            operation_id=uuid5(
                NAMESPACE_URL, f"caresync:swap:{payload.client_operation_id}:{label}-cancel"
            ),
            actor_user_id=context.user.id,
            event_type="cancelled",
            payload={"reason": original.cancellation_reason},
            occurred_at=now,
        )
        audit(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action="staff_schedule.cancelled_for_swap",
            entity_type="staff_schedule",
            entity_id=original.id,
            details={"operation_id": str(payload.client_operation_id)},
        )
    value.status = "approved"
    value.manager_decided_at = now
    value.manager_decided_by_user_id = context.user.id
    value.requester_replacement_schedule_id = first.id
    value.counterparty_replacement_schedule_id = second.id if second else None
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = swap_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_shift_swap",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="approved",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-shift-swap-approved:{value.id}:{payload.client_operation_id}:managers",
        title="Shift exchange approved",
        body="A manager approved a whole-shift exchange.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    requester_user = _notify_staff(
        session,
        context=context,
        membership_id=value.requester_membership_id,
        event_key=f"staff-shift-swap-approved:{value.id}:{payload.client_operation_id}:requester",
        title="Shift exchange approved",
        body="A manager approved your whole-shift exchange.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        action_path="/staff/self/exchange/swaps",
    )
    counterparty_user = _notify_staff(
        session,
        context=context,
        membership_id=value.counterparty_membership_id,
        event_key=f"staff-shift-swap-approved:{value.id}:{payload.client_operation_id}:counterparty",
        title="Shift exchange approved",
        body="A manager approved your whole-shift exchange.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        action_path="/staff/self/exchange/swaps",
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=(
            {requester_user, counterparty_user}
            | set(_manager_user_ids(session, context.organization.id))
        ),
        event_type="staff_shift_swap.approved",
        entity_type="staff_shift_swap",
        entity_id=value.id,
    )
    flush_or_conflict(session, "Shift exchange sources changed during approval")
    commit_in_context(session, context)
    return response


@manager_router.post("/swaps/{swap_id}/reject", response_model=ShiftSwapResponse)
def reject_swap(
    swap_id: UUID,
    payload: SwapRejectAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> ShiftSwapResponse:
    ensure_writable(request)
    reason = clean_optional_text(payload.reason)
    if reason is None:
        raise HTTPException(422, detail={"code": "rejection_reason_required"})
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_shift_swap",
        event_type="rejected",
        request_payload=canonical,
        entity_id=swap_id,
    )
    if receipt:
        return _receipt_response(receipt, ShiftSwapResponse)
    lock_workforce_lane(session, context.organization.id, "swap", swap_id)
    value = swap_row(session, context.organization.id, swap_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.status != "pending_manager":
        raise HTTPException(409, detail={"code": "manager_review_unavailable"})
    now = datetime.now(UTC)
    value.status = "rejected"
    value.manager_decided_at = now
    value.manager_decided_by_user_id = context.user.id
    value.manager_decision_reason = reason
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = swap_response(session, value)
    _store_event(
        session,
        context=context,
        entity_type="staff_shift_swap",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="rejected",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-shift-swap-rejected:{value.id}:{payload.client_operation_id}:managers",
        title="Shift exchange not approved",
        body="A manager rejected a proposed whole-shift exchange.",
        entity_type="staff_shift_swap",
        entity_id=value.id,
        facility_id=value.facility_id,
    )
    user_ids = {
        _notify_staff(
            session,
            context=context,
            membership_id=membership_id,
            event_key=f"staff-shift-swap-rejected:{value.id}:{payload.client_operation_id}:{label}",
            title="Shift exchange not approved",
            body="A manager did not approve the proposed whole-shift exchange.",
            entity_type="staff_shift_swap",
            entity_id=value.id,
            action_path="/staff/self/exchange/swaps",
        )
        for membership_id, label in (
            (value.requester_membership_id, "requester"),
            (value.counterparty_membership_id, "counterparty"),
        )
    }
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids=(user_ids | set(_manager_user_ids(session, context.organization.id))),
        event_type="staff_shift_swap.rejected",
        entity_type="staff_shift_swap",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response


@manager_router.post(
    "/open-shift-engagements/{engagement_id}/withdraw",
    response_model=OpenShiftEngagementResponse,
)
def withdraw_manager_offer(
    engagement_id: UUID,
    payload: EngagementAction,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> OpenShiftEngagementResponse:
    ensure_writable(request)
    canonical = canonical_json(payload.model_dump(exclude={"client_operation_id"}))
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    receipt = receipt_event(
        session,
        context.organization.id,
        payload.client_operation_id,
        entity_type="staff_open_shift_engagement",
        event_type="withdrawn",
        request_payload=canonical,
        entity_id=engagement_id,
    )
    if receipt:
        return _receipt_response(receipt, OpenShiftEngagementResponse)
    lock_workforce_lane(session, context.organization.id, "engagement", engagement_id)
    value = engagement_row(session, context.organization.id, engagement_id, lock=True)
    require_expected(value, payload.expected_updated_at)
    if value.kind != "offer" or value.status != "pending":
        raise HTTPException(409, detail={"code": "pending_offer_required"})
    now = datetime.now(UTC)
    value.status = "withdrawn"
    value.terminal_at = now
    value.terminal_by_user_id = context.user.id
    value.terminal_reason = clean_optional_text(payload.note)
    value.last_operation_id = payload.client_operation_id
    value.updated_at = now
    response = engagement_response(session, value, now=now, capability_scope="manager")
    _store_event(
        session,
        context=context,
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
        operation_id=payload.client_operation_id,
        event_type="withdrawn",
        request_payload=canonical,
        response=response,
        occurred_at=now,
    )
    open_shift = open_shift_row(session, context.organization.id, value.open_shift_id)
    _notify_managers(
        session,
        context=context,
        event_key=f"staff-open-shift-offer-withdrawn:{value.id}:{payload.client_operation_id}:managers",
        title="Shift offer withdrawn",
        body="A manager withdrew an open shift offer.",
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
        facility_id=open_shift.facility_id,
    )
    user_id = _notify_staff(
        session,
        context=context,
        membership_id=value.membership_id,
        event_key=f"staff-open-shift-offer-withdrawn:{value.id}:{payload.client_operation_id}",
        title="Shift offer withdrawn",
        body="A previously sent staff shift offer is no longer available.",
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
        action_path="/staff/self/exchange/open-shift-activity",
    )
    _invalidate(
        session,
        organization_id=context.organization.id,
        user_ids={user_id} | set(_manager_user_ids(session, context.organization.id)),
        event_type="staff_open_shift_engagement.withdrawn",
        entity_type="staff_open_shift_engagement",
        entity_id=value.id,
    )
    commit_in_context(session, context)
    return response
