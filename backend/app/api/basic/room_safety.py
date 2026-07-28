"""0041 live room-presence and operational configured-target APIs."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.api.basic.common import commit_in_context, ensure_writable
from app.api.basic.dependencies import (
    BasicContextDependency,
    require_all_permissions,
    require_complete_if_marketplace_user,
)
from app.api.dependencies import SessionDependency
from app.basic.models import RoomOperationalExceptionHead
from app.basic.room_safety import (
    acknowledge_exception,
    capability_marker,
    end_presence,
    exception_action_target,
    exception_page,
    facility_live_board,
    foundation_enabled,
    move_presence,
    reconcile_facility_exceptions,
    release_reconciliation_status,
    require_capability,
    require_foundation,
    run_release_reconciliation,
    staff_presence_projection,
    staff_room_live_board,
    start_presence,
)
from app.basic.room_safety_schemas import (
    ExceptionAcknowledgeIntent,
    ExceptionAcknowledgeResponse,
    ExceptionActionTarget,
    ExceptionPage,
    FacilityLiveBoard,
    PresenceCommandResponse,
    PresenceEndIntent,
    PresenceMoveIntent,
    PresenceStartIntent,
    ReleaseReconciliationIntent,
    ReleaseReconciliationResponse,
    ReleaseReconciliationStatus,
    RoomSafetyCapability,
    StaffPresenceProjection,
    StaffRoomLiveBoard,
)

self_router = APIRouter(
    prefix="/staff/self",
    tags=["staff room presence"],
    dependencies=[Depends(require_complete_if_marketplace_user)],
)
manager_router = APIRouter(prefix="/room-safety", tags=["room operations"])

_self_presence_access = require_all_permissions(
    "shift:clock", "care_roster:read"
)
_self_live_access = require_all_permissions(
    "shift:clock", "care_roster:read", "child_safety:read"
)
_manager_access = require_all_permissions(
    "facility:read", "care_roster:read", "staff:manage_educators"
)
_release_permissions = require_all_permissions(
    "facility:read",
    "facility:manage",
    "care_roster:read",
    "staff:manage_educators",
)


def _release_access(context: BasicContextDependency) -> None:
    _release_permissions(context)
    if (
        not context.organization_wide
        or context.role.key not in {"owner", "administrator"}
    ):
        raise HTTPException(
            403,
            detail={
                "code": "release_reconciliation_leader_required",
                "message": (
                    "Only an organization-wide owner or administrator can "
                    "activate live room safety."
                ),
            },
        )


def _manager_scope(context: BasicContextDependency, facility_id: UUID) -> None:
    _manager_access(context)
    if not context.organization_wide and facility_id not in context.assigned_facility_ids:
        raise HTTPException(404, "Facility not found")


@self_router.get(
    "/room-presence",
    response_model=StaffPresenceProjection,
)
def read_self_presence(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> StaffPresenceProjection:
    _self_presence_access(context)
    require_capability(request, session, context.organization.id)
    return staff_presence_projection(session, context)


@self_router.get(
    "/room-safety/live",
    response_model=StaffRoomLiveBoard,
)
def read_self_live_board(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> StaffRoomLiveBoard:
    _self_live_access(context)
    require_capability(request, session, context.organization.id)
    return staff_room_live_board(session, context)


@self_router.post(
    "/room-presence/start",
    response_model=PresenceCommandResponse,
    status_code=201,
)
def start_self_presence(
    payload: PresenceStartIntent,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> PresenceCommandResponse:
    _self_presence_access(context)
    require_capability(request, session, context.organization.id)
    ensure_writable(request)
    response = start_presence(
        session,
        context,
        operation_id=payload.client_operation_id,
        shift_id=payload.staff_shift_id,
        facility_id=payload.facility_id,
        room_id=payload.room_id,
    )
    if response.replayed:
        return response
    reconcile_facility_exceptions(
        session,
        organization_id=context.organization.id,
        facility_id=payload.facility_id,
        cause_entity_type="staff_room_presence",
        cause_entity_id=response.affected_session_id,
    )
    session.flush()
    response.current_presence = staff_presence_projection(session, context)
    commit_in_context(session, context, "Room presence conflicts with another update")
    return response


@self_router.post(
    "/room-presence/move",
    response_model=PresenceCommandResponse,
)
def move_self_presence(
    payload: PresenceMoveIntent,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> PresenceCommandResponse:
    _self_presence_access(context)
    require_capability(request, session, context.organization.id)
    ensure_writable(request)
    response = move_presence(
        session,
        context,
        operation_id=payload.client_operation_id,
        expected_session_id=payload.expected_session_id,
        expected_version=payload.expected_version,
        destination_room_id=payload.destination_room_id,
        reason=payload.reason,
    )
    if response.replayed:
        return response
    reconcile_facility_exceptions(
        session,
        organization_id=context.organization.id,
        facility_id=response.receipt.facility_id,
        cause_entity_type="staff_room_presence",
        cause_entity_id=response.affected_session_id,
    )
    session.flush()
    response.current_presence = staff_presence_projection(session, context)
    commit_in_context(session, context, "Room move conflicts with another update")
    return response


@self_router.post(
    "/room-presence/end",
    response_model=PresenceCommandResponse,
)
def end_self_presence(
    payload: PresenceEndIntent,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> PresenceCommandResponse:
    _self_presence_access(context)
    require_capability(request, session, context.organization.id)
    ensure_writable(request)
    response = end_presence(
        session,
        context,
        operation_id=payload.client_operation_id,
        expected_session_id=payload.expected_session_id,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    if response.replayed:
        return response
    reconcile_facility_exceptions(
        session,
        organization_id=context.organization.id,
        facility_id=response.receipt.facility_id,
        cause_entity_type="staff_room_presence",
        cause_entity_id=response.affected_session_id,
    )
    session.flush()
    response.current_presence = staff_presence_projection(session, context)
    commit_in_context(session, context, "Room presence end conflicts with another update")
    return response


@manager_router.get("/capability", response_model=RoomSafetyCapability)
def manager_capability(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> RoomSafetyCapability:
    _manager_access(context)
    require_capability(request, session, context.organization.id)
    return capability_marker()


@manager_router.get(
    "/release-reconciliation/status",
    response_model=ReleaseReconciliationStatus,
)
def manager_release_reconciliation_status(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseReconciliationStatus:
    _release_access(context)
    require_foundation(request)
    return release_reconciliation_status(
        session,
        context.organization.id,
        foundation_available=foundation_enabled(request),
    )


@manager_router.post(
    "/release-reconciliation",
    response_model=ReleaseReconciliationResponse,
)
def manager_release_reconciliation(
    payload: ReleaseReconciliationIntent,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseReconciliationResponse:
    _release_access(context)
    require_foundation(request)
    ensure_writable(request)
    response = run_release_reconciliation(
        session,
        context,
        operation_id=payload.client_operation_id,
        expected_facility_ids=payload.expected_facility_ids,
        expected_facility_set_sha256=payload.expected_facility_set_sha256,
        expected_active_facility_count=payload.expected_active_facility_count,
    )
    commit_in_context(
        session,
        context,
        "Release reconciliation conflicts with another current-state change",
    )
    return response


@manager_router.get("/live", response_model=FacilityLiveBoard)
def manager_live_board(
    facility_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> FacilityLiveBoard:
    _manager_scope(context, facility_id)
    require_capability(request, session, context.organization.id)
    return facility_live_board(
        session,
        organization_id=context.organization.id,
        facility_id=facility_id,
    )


@manager_router.get("/exceptions", response_model=ExceptionPage)
def manager_exception_page(
    facility_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
    state: Literal["open", "acknowledged", "resolved", "all"] = "all",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ExceptionPage:
    _manager_scope(context, facility_id)
    require_capability(request, session, context.organization.id)
    return exception_page(
        session,
        organization_id=context.organization.id,
        facility_id=facility_id,
        state_filter=state,
        cursor=cursor,
        limit=limit,
    )


def _manager_exception(
    session: SessionDependency,
    context: BasicContextDependency,
    exception_id: UUID,
) -> RoomOperationalExceptionHead:
    value = session.scalar(
        select(RoomOperationalExceptionHead).where(
            RoomOperationalExceptionHead.organization_id == context.organization.id,
            RoomOperationalExceptionHead.id == exception_id,
        )
    )
    if value is None:
        raise HTTPException(404, "Room operational exception not found")
    _manager_scope(context, value.facility_id)
    return value


@manager_router.get(
    "/exceptions/{exception_id}/action-target",
    response_model=ExceptionActionTarget,
)
def manager_exception_action_target(
    exception_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ExceptionActionTarget:
    _manager_access(context)
    require_capability(request, session, context.organization.id)
    value = _manager_exception(session, context, exception_id)
    return exception_action_target(value)


@manager_router.post(
    "/exceptions/{exception_id}/acknowledge",
    response_model=ExceptionAcknowledgeResponse,
)
def manager_acknowledge_exception(
    exception_id: UUID,
    payload: ExceptionAcknowledgeIntent,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ExceptionAcknowledgeResponse:
    _manager_access(context)
    require_capability(request, session, context.organization.id)
    ensure_writable(request)
    response = acknowledge_exception(
        session,
        context,
        exception_id=exception_id,
        operation_id=payload.client_operation_id,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )
    commit_in_context(
        session, context, "Exception acknowledgement conflicts with another update"
    )
    return response
