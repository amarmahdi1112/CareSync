"""Staff self bootstrap and server-timestamped shift clock operations."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    BasicContextDependency,
    refresh_basic_context,
    require_complete_if_marketplace_user,
    require_permission,
)
from app.api.dependencies import SessionDependency
from app.basic.driver_vehicle_schemas import (
    DriverVehicleRegistryCapability,
    SelfTransportRegistryResponse,
)
from app.basic.models import (
    Facility,
    MembershipRoomAssignment,
    Room,
    ScheduledStaffShift,
    StaffDriverAuthorizationDecision,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    StaffRoomPresenceEvent,
    StaffRoomPresenceSession,
    StaffShift,
    StaffShiftEvent,
    TransportVehicle,
    TransportVehicleEvidenceVersion,
    TransportVehicleVersion,
)
from app.basic.release_checkout_capability import verified_release_capability
from app.basic.room_safety import (
    capability_enabled,
    capability_marker,
    close_presence_for_clock_out,
    create_clock_in_presence,
    foundation_enabled,
    lock_facility_projection,
    reconcile_facility_exceptions,
    staff_presence_projection,
)
from app.basic.security import audit

router = APIRouter(
    prefix="/staff/self",
    tags=["staff operations"],
    dependencies=[Depends(require_complete_if_marketplace_user)],
)
shift_context = require_permission("shift:clock")
CLOCK_IN_EARLY_WINDOW = timedelta(hours=2)
CLOCK_IN_LATE_WINDOW = timedelta(hours=4)


class ShiftClockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility_id: UUID
    operation_id: UUID
    scheduled_shift_id: UUID | None = None
    room_id: UUID | None = None


def _shift_row(session, shift: StaffShift) -> dict:
    events = list(
        session.scalars(
            select(StaffShiftEvent)
            .where(
                StaffShiftEvent.organization_id == shift.organization_id,
                StaffShiftEvent.shift_id == shift.id,
            )
            .order_by(StaffShiftEvent.server_occurred_at)
        )
    )
    response = {
        "id": shift.id,
        "organization_id": shift.organization_id,
        "membership_id": shift.membership_id,
        "facility_id": shift.facility_id,
        "scheduled_shift_id": shift.scheduled_shift_id,
        "status": shift.status,
        "clocked_in_at": shift.clocked_in_at,
        "clocked_out_at": shift.clocked_out_at,
        "events": [
            {
                "id": event.id,
                "operation_id": event.operation_id,
                "event_type": event.event_type,
                "server_occurred_at": event.server_occurred_at,
            }
            for event in events
        ],
    }
    return response


def _shift_row_with_room_presence(
    session,
    context,
    shift: StaffShift,
) -> dict:
    response = _shift_row(session, shift)
    projection = staff_presence_projection(session, context)
    response.update(
        {
            "room_presence_required": projection.room_presence_required,
            "eligible_rooms": [
                value.model_dump(mode="json")
                for value in projection.eligible_rooms
            ],
            "current_room_presence": (
                projection.current_presence.model_dump(mode="json")
                if projection.current_presence is not None
                else None
            ),
            "room_presence_decision_reason": projection.decision_reason,
        }
    )
    return response


def _member_open_shift(
    session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    lock: bool = False,
) -> StaffShift | None:
    statement = select(StaffShift).where(
        StaffShift.organization_id == organization_id,
        StaffShift.membership_id == membership_id,
        StaffShift.status == "open",
        StaffShift.clocked_out_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    values = list(session.scalars(statement.limit(2)))
    if len(values) > 1:
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "duplicate_open_staff_shifts",
            },
        )
    return values[0] if values else None


def _member_open_shifts(
    session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    lock: bool = False,
) -> list[StaffShift]:
    statement = (
        select(StaffShift)
        .where(
            StaffShift.organization_id == organization_id,
            StaffShift.membership_id == membership_id,
            StaffShift.status == "open",
            StaffShift.clocked_out_at.is_(None),
        )
        .order_by(StaffShift.id)
    )
    if lock:
        statement = statement.with_for_update()
    return list(session.scalars(statement))


def _driver_registry_capability(request: Request) -> dict:
    enabled = bool(getattr(request.app.state, "driver_vehicle_registry_enabled", False))
    commands_enabled = bool(
        enabled and getattr(request.app.state, "transport_registry_commands_enabled", False)
    )
    evidence_upload_available = bool(
        commands_enabled
        and getattr(request.app.state, "transport_registry_evidence_ingest_available", False)
        and getattr(request.app.state, "transport_registry_evidence_pipeline_available", False)
        and getattr(request.app.state, "transport_evidence_session_factory", None) is not None
    )
    marker = DriverVehicleRegistryCapability(
        schema_version="0032" if commands_enabled else "0031" if enabled else None,
        runtime_available=enabled,
        self_service_available=enabled,
        read_path="/api/v1/staff/self/transport-registry" if enabled else None,
        declaration_path=(
            "/api/v1/staff/self/transport-registry/declarations" if commands_enabled else None
        ),
        qualification_evidence_path=(
            "/api/v1/staff/self/transport-registry/qualification-evidence"
            if evidence_upload_available
            else None
        ),
        personal_vehicle_path=(
            "/api/v1/staff/self/transport-registry/vehicles" if commands_enabled else None
        ),
        vehicle_version_path_template=(
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/versions"
            if commands_enabled
            else None
        ),
        vehicle_retirement_path_template=(
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/retire"
            if commands_enabled
            else None
        ),
        vehicle_evidence_path_template=(
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/evidence"
            if evidence_upload_available
            else None
        ),
        evidence_upload_available=evidence_upload_available,
        operational_driver_ready=False,
        dispatch_authorized=False,
    )
    if commands_enabled:
        return marker.model_dump()
    return marker.model_dump(
        exclude={
            "declaration_path",
            "qualification_evidence_path",
            "personal_vehicle_path",
            "vehicle_version_path_template",
            "vehicle_retirement_path_template",
            "vehicle_evidence_path_template",
            "evidence_upload_available",
        }
    )


@router.get("")
def staff_self(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    assignments = list(
        session.execute(
            select(MembershipRoomAssignment, Facility, Room)
            .join(
                Facility,
                (Facility.organization_id == MembershipRoomAssignment.organization_id)
                & (Facility.id == MembershipRoomAssignment.facility_id),
            )
            .join(
                Room,
                (Room.organization_id == MembershipRoomAssignment.organization_id)
                & (Room.id == MembershipRoomAssignment.room_id),
            )
            .where(
                MembershipRoomAssignment.organization_id == context.organization.id,
                MembershipRoomAssignment.membership_id == context.membership.id,
                MembershipRoomAssignment.is_active.is_(True),
                Facility.status == "active",
                Room.is_active.is_(True),
            )
        )
    )
    open_shift = _member_open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    facilities = {}
    for _, facility, _ in assignments:
        if facility.id in facilities:
            continue
        try:
            local_service_date = datetime.now(UTC).astimezone(ZoneInfo(facility.timezone)).date()
        except ZoneInfoNotFoundError:
            raise HTTPException(409, "Assigned facility timezone is invalid") from None
        release_capability = verified_release_capability(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            permissions=context.role.permissions or [],
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
        facilities[facility.id] = {
            "id": facility.id,
            "name": facility.name,
            "timezone": facility.timezone,
            "local_service_date": local_service_date,
            "shift_clock_configured": True,
            "verified_release_checkout": release_capability.as_dict(),
        }
    response = {
        "user": {
            "id": context.user.id,
            "email": context.user.email,
            "first_name": context.user.first_name,
            "last_name": context.user.last_name,
        },
        "organization_id": context.organization.id,
        "membership_id": context.membership.id,
        "role": {"key": context.role.key, "permissions": context.role.permissions},
        "assigned_facilities": list(facilities.values()),
        "assigned_rooms": [
            {"id": room.id, "facility_id": room.facility_id, "name": room.name}
            for _, _, room in assignments
        ],
        "operational_reads": {
            "attendance_roster": "/api/v1/attendance/roster",
            "care_daybook": "/api/v1/care/daybook",
        },
        "driver_vehicle_registry": _driver_registry_capability(request),
        "open_shift": _shift_row(session, open_shift) if open_shift else None,
    }
    if (
        {"shift:clock", "care_roster:read", "child_safety:read"}.issubset(
            set(context.role.permissions or [])
        )
        and capability_enabled(
            request,
            session,
            context.organization.id,
        )
    ):
        response["live_room_presence_safety_board"] = capability_marker().model_dump(
            mode="json"
        )
    return response


@router.get("/transport-registry", response_model=SelfTransportRegistryResponse)
def self_transport_registry(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    """Return only the current staff member's fail-closed 0031 registry projection."""

    if not bool(getattr(request.app.state, "driver_vehicle_registry_enabled", False)):
        raise HTTPException(
            503,
            detail={"code": "driver_vehicle_registry_unavailable"},
        )

    organization_id = context.organization.id
    membership_id = context.membership.id
    registry_capability = _driver_registry_capability(request)
    capability = session.scalar(
        select(StaffDriverCapabilityVersion)
        .where(
            StaffDriverCapabilityVersion.organization_id == organization_id,
            StaffDriverCapabilityVersion.membership_id == membership_id,
        )
        .order_by(StaffDriverCapabilityVersion.version_number.desc())
        .limit(1)
    )
    qualification_rank = (
        select(
            StaffDriverQualificationVersion.id.label("qualification_id"),
            func.row_number()
            .over(
                partition_by=StaffDriverQualificationVersion.qualification_type,
                order_by=StaffDriverQualificationVersion.version_number.desc(),
            )
            .label("lane_rank"),
        )
        .where(
            StaffDriverQualificationVersion.organization_id == organization_id,
            StaffDriverQualificationVersion.membership_id == membership_id,
        )
        .subquery()
    )
    qualification_rows = list(
        session.scalars(
            select(StaffDriverQualificationVersion)
            .join(
                qualification_rank,
                qualification_rank.c.qualification_id == StaffDriverQualificationVersion.id,
            )
            .where(qualification_rank.c.lane_rank == 1)
            .order_by(StaffDriverQualificationVersion.qualification_type)
        )
    )
    qualification_content_ids: set[UUID] = set()
    if registry_capability["schema_version"] == "0032" and qualification_rows:
        referenced_hashes = {
            row.evidence_reference_sha256
            for row in qualification_rows
            if row.evidence_reference_sha256 is not None
        }
        evidenced_hashes = (
            set(
                session.scalars(
                    select(StaffDriverQualificationEvidenceObject.content_sha256).where(
                        StaffDriverQualificationEvidenceObject.organization_id == organization_id,
                        StaffDriverQualificationEvidenceObject.membership_id == membership_id,
                        StaffDriverQualificationEvidenceObject.content_sha256.in_(
                            referenced_hashes
                        ),
                    )
                )
            )
            if referenced_hashes
            else set()
        )
        qualification_content_ids = {
            row.id
            for row in qualification_rows
            if row.evidence_reference_sha256 in evidenced_hashes
        }

    all_authorization_rows = list(
        session.scalars(
            select(StaffDriverAuthorizationDecision)
            .where(
                StaffDriverAuthorizationDecision.organization_id == organization_id,
                StaffDriverAuthorizationDecision.membership_id == membership_id,
            )
            .order_by(StaffDriverAuthorizationDecision.decision_sequence.desc())
            .limit(21)
        )
    )
    authorizations_truncated = len(all_authorization_rows) > 20
    authorization_rows = all_authorization_rows[:20]
    readiness = session.scalar(
        select(StaffDriverReadinessDecision)
        .where(
            StaffDriverReadinessDecision.organization_id == organization_id,
            StaffDriverReadinessDecision.membership_id == membership_id,
        )
        .order_by(StaffDriverReadinessDecision.decision_sequence.desc())
        .limit(1)
    )
    vehicle_rows = list(
        session.scalars(
            select(TransportVehicle)
            .where(
                TransportVehicle.organization_id == organization_id,
                TransportVehicle.owner_kind == "staff_personal",
                TransportVehicle.staff_owner_membership_id == membership_id,
            )
            .order_by(TransportVehicle.created_at.desc(), TransportVehicle.id)
            .limit(51)
        )
    )
    vehicles_truncated = len(vehicle_rows) > 50
    selected_vehicles = vehicle_rows[:50]
    vehicle_ids = [vehicle.id for vehicle in selected_vehicles]
    current_versions_by_vehicle: dict[UUID, TransportVehicleVersion] = {}
    evidence_by_vehicle: dict[UUID, list[TransportVehicleEvidenceVersion]] = defaultdict(list)
    if vehicle_ids:
        version_rank = (
            select(
                TransportVehicleVersion.id.label("version_id"),
                func.row_number()
                .over(
                    partition_by=TransportVehicleVersion.vehicle_id,
                    order_by=TransportVehicleVersion.version_number.desc(),
                )
                .label("vehicle_rank"),
            )
            .where(
                TransportVehicleVersion.organization_id == organization_id,
                TransportVehicleVersion.vehicle_id.in_(vehicle_ids),
            )
            .subquery()
        )
        current_versions_by_vehicle = {
            row.vehicle_id: row
            for row in session.scalars(
                select(TransportVehicleVersion)
                .join(
                    version_rank,
                    version_rank.c.version_id == TransportVehicleVersion.id,
                )
                .where(
                    TransportVehicleVersion.organization_id == organization_id,
                    version_rank.c.vehicle_rank == 1,
                )
            )
        }
        evidence_rank = (
            select(
                TransportVehicleEvidenceVersion.id.label("evidence_id"),
                func.row_number()
                .over(
                    partition_by=(
                        TransportVehicleEvidenceVersion.vehicle_id,
                        TransportVehicleEvidenceVersion.evidence_type,
                    ),
                    order_by=TransportVehicleEvidenceVersion.version_number.desc(),
                )
                .label("lane_rank"),
            )
            .where(
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                TransportVehicleEvidenceVersion.vehicle_id.in_(vehicle_ids),
            )
            .subquery()
        )
        for evidence in session.scalars(
            select(TransportVehicleEvidenceVersion)
            .join(
                evidence_rank,
                evidence_rank.c.evidence_id == TransportVehicleEvidenceVersion.id,
            )
            .where(
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                evidence_rank.c.lane_rank == 1,
            )
            .order_by(
                TransportVehicleEvidenceVersion.vehicle_id,
                TransportVehicleEvidenceVersion.evidence_type,
            )
        ):
            evidence_by_vehicle[evidence.vehicle_id].append(evidence)

    vehicles = []
    for vehicle in selected_vehicles:
        current_version = current_versions_by_vehicle.get(vehicle.id)
        evidence_rows = evidence_by_vehicle[vehicle.id]
        vehicles.append(
            {
                "id": vehicle.id,
                "owner_kind": "staff_personal",
                "retired_at": vehicle.retired_at,
                "current_version": (
                    {
                        "id": current_version.id,
                        "version_number": current_version.version_number,
                        "make": current_version.make,
                        "model": current_version.model,
                        "model_year": current_version.model_year,
                        "color": current_version.color,
                        "plate_token": current_version.plate_token,
                        "plate_jurisdiction": current_version.plate_jurisdiction,
                        "passenger_capacity": current_version.passenger_capacity,
                        "child_passenger_capacity": current_version.child_passenger_capacity,
                        "wheelchair_accessible": current_version.wheelchair_accessible,
                        "effective_at": current_version.effective_at,
                        "recorded_at": current_version.recorded_at,
                    }
                    if current_version is not None
                    else None
                ),
                "evidence": [
                    {
                        "id": evidence.id,
                        "evidence_type": evidence.evidence_type,
                        "version_number": evidence.version_number,
                        "status": evidence.status,
                        "issue_date": evidence.issue_date,
                        "expiry_date": evidence.expiry_date,
                        "original_filename": evidence.original_filename,
                        "media_type": evidence.media_type,
                        "byte_size": evidence.byte_size,
                        "content_path": (
                            f"/api/v1/staff/self/transport-registry/vehicles/{vehicle.id}/"
                            f"evidence/{evidence.id}/content"
                            if registry_capability["schema_version"] == "0032"
                            else None
                        ),
                        "recorded_at": evidence.recorded_at,
                    }
                    for evidence in evidence_rows
                ],
            }
        )

    return SelfTransportRegistryResponse(
        schema_version=("0032" if registry_capability["schema_version"] == "0032" else "0031"),
        organization_id=organization_id,
        membership_id=membership_id,
        user_id=context.user.id,
        generated_at=datetime.now(UTC),
        driver_capability=(
            {
                "id": capability.id,
                "version_number": capability.version_number,
                "status": capability.status,
                "willing_to_drive": capability.willing_to_drive,
                "licence_jurisdiction": capability.licence_jurisdiction,
                "licence_jurisdiction_other": capability.licence_jurisdiction_other,
                "licence_class": capability.licence_class,
                "vehicle_access": capability.vehicle_access,
                "preferred_service_radius_km": capability.preferred_service_radius_km,
                "source_kind": capability.source_kind,
                "source_screening_profile_version": (capability.source_screening_profile_version),
                "effective_at": capability.effective_at,
                "recorded_at": capability.recorded_at,
            }
            if capability is not None
            else None
        ),
        qualifications=[
            {
                "id": row.id,
                "qualification_type": row.qualification_type,
                "version_number": row.version_number,
                "status": row.status,
                "jurisdiction": row.jurisdiction,
                "qualification_class": row.qualification_class,
                "identifier_last4": row.identifier_last4,
                "issue_date": row.issue_date,
                "expiry_date": row.expiry_date,
                "evidence_present": bool(
                    row.source_screening_document_version_id or row.evidence_reference_sha256
                ),
                "content_path": (
                    f"/api/v1/staff/self/transport-registry/qualification-evidence/{row.id}/content"
                    if row.id in qualification_content_ids
                    else None
                ),
                "effective_at": row.effective_at,
                "recorded_at": row.recorded_at,
            }
            for row in qualification_rows
        ],
        authorizations=[
            {
                "id": row.id,
                "decision_sequence": row.decision_sequence,
                "capability_version_id": row.capability_version_id,
                "qualification_version_ids": row.qualification_version_ids,
                "decision": row.decision,
                "reason_code": row.reason_code,
                "authorization_valid_from": row.authorization_valid_from,
                "authorization_valid_until": row.authorization_valid_until,
                "reviewed_at": row.reviewed_at,
                "operational_driver_ready": False,
                "dispatch_authorized": False,
            }
            for row in authorization_rows
        ],
        authorizations_truncated=authorizations_truncated,
        vehicles=vehicles,
        vehicles_truncated=vehicles_truncated,
        latest_readiness_decision=(
            {
                "id": readiness.id,
                "decision_sequence": readiness.decision_sequence,
                "capability_version_id": readiness.capability_version_id,
                "authorization_decision_id": readiness.authorization_decision_id,
                "vehicle_id": readiness.vehicle_id,
                "vehicle_version_id": readiness.vehicle_version_id,
                "vehicle_evidence_version_ids": readiness.vehicle_evidence_version_ids,
                "decision": readiness.decision,
                "reason_codes": readiness.reason_codes,
                "evaluated_at": readiness.evaluated_at,
                "operational_driver_ready": False,
                "dispatch_authorized": False,
            }
            if readiness is not None
            else None
        ),
        operational_driver_ready=False,
        dispatch_authorized=False,
    )


def _facility_for_clock(
    session,
    context,
    facility_id: UUID,
    *,
    lock: bool = False,
) -> Facility:
    statement = select(Facility).where(
        Facility.organization_id == context.organization.id,
        Facility.id == facility_id,
        Facility.status == "active",
    )
    if lock:
        statement = statement.with_for_update()
    facility = session.scalar(statement)
    if facility is None:
        raise HTTPException(404, "Facility not found")
    if not context.organization_wide and facility_id not in context.assigned_facility_ids:
        raise HTTPException(403, "An active room assignment at this facility is required")
    return facility


def _clock_operation(session, context, payload: ShiftClockRequest, event_type: str):
    existing = session.scalar(
        select(StaffShiftEvent).where(
            StaffShiftEvent.organization_id == context.organization.id,
            StaffShiftEvent.operation_id == payload.operation_id,
        )
    )
    if existing is not None:
        if (
            existing.membership_id != context.membership.id
            or existing.facility_id != payload.facility_id
            or existing.event_type != event_type
        ):
            raise HTTPException(409, "Operation identifier was already used for another action")
        return existing, None
    if event_type == "clock_out":
        # Do not probe a caller-supplied facility before resolving the
        # actor-owned open shift.  Terminal clock-out remains available after
        # assignment loss without disclosing another scoped facility.
        return None, None
    return None, _facility_for_clock(session, context, payload.facility_id)


def _validate_clock_in_room_replay(
    session,
    *,
    organization_id: UUID,
    operation_id: UUID,
    requested_room_id: UUID | None,
) -> None:
    presence_event = session.scalar(
        select(StaffRoomPresenceEvent).where(
            StaffRoomPresenceEvent.organization_id == organization_id,
            StaffRoomPresenceEvent.operation_id == operation_id,
        )
    )
    if presence_event is None:
        if requested_room_id is not None:
            raise HTTPException(409, detail={"code": "operation_reused"})
        return
    intent = dict(presence_event.intent or {})
    requested_room = (
        str(requested_room_id) if requested_room_id is not None else None
    )
    if intent.get("requested_room_id") != requested_room:
        raise HTTPException(409, detail={"code": "operation_reused"})


@router.post("/shifts/clock-in", status_code=201)
def clock_in(
    payload: ShiftClockRequest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    shift_context(context)
    ensure_writable(request)
    lock_client_operation(session, context.organization.id, payload.operation_id)
    existing, facility = _clock_operation(session, context, payload, "clock_in")
    live_room_safety = foundation_enabled(request)
    if existing is not None:
        if live_room_safety:
            lock_facility_projection(
                session, context.organization.id, existing.facility_id
            )
            context = refresh_basic_context(
                session,
                context,
                required_all_permissions=(
                    "shift:clock",
                    "care_roster:read",
                ),
                conceal_detail="Facility not found",
            )
            if (
                not context.organization_wide
                and existing.facility_id not in context.assigned_facility_ids
            ):
                raise HTTPException(404, "Facility not found")
        shift = session.scalar(
            select(StaffShift).where(
                StaffShift.organization_id == context.organization.id,
                StaffShift.id == existing.shift_id,
            )
        )
        if shift.scheduled_shift_id != payload.scheduled_shift_id:
            raise HTTPException(
                409,
                detail={
                    "code": "operation_reused",
                    "message": "Operation identifier was retried with another scheduled shift",
                },
            )
        _validate_clock_in_room_replay(
            session,
            organization_id=context.organization.id,
            operation_id=payload.operation_id,
            requested_room_id=payload.room_id,
        )
        return (
            _shift_row_with_room_presence(session, context, shift)
            if live_room_safety
            else _shift_row(session, shift)
        )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility.id
        )
        context = refresh_basic_context(
            session,
            context,
            required_all_permissions=("shift:clock", "care_roster:read"),
            conceal_detail="Facility not found",
        )
        if (
            not context.organization_wide
            and facility.id not in context.assigned_facility_ids
        ):
            raise HTTPException(404, "Facility not found")
    facility = _facility_for_clock(
        session,
        context,
        payload.facility_id,
        lock=True,
    )
    open_shift = _member_open_shift(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    if open_shift is not None:
        raise HTTPException(409, "Staff member already has an open shift")
    now = datetime.now(UTC)
    scheduled_shift = None
    if payload.scheduled_shift_id is not None:
        scheduled_shift = session.scalar(
            select(ScheduledStaffShift)
            .where(
                ScheduledStaffShift.organization_id == context.organization.id,
                ScheduledStaffShift.id == payload.scheduled_shift_id,
            )
            .with_for_update()
        )
        if scheduled_shift is None:
            raise HTTPException(404, "Scheduled shift not found")
        if (
            scheduled_shift.membership_id != context.membership.id
            or scheduled_shift.facility_id != facility.id
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "scheduled_shift_mismatch",
                    "message": "Scheduled shift does not match this staff member and facility",
                },
            )
        if (
            scheduled_shift.room_id is not None
            and payload.room_id is not None
            and payload.room_id != scheduled_shift.room_id
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "scheduled_room_conflicts_with_selected_room",
                    "scheduled_room_id": str(scheduled_shift.room_id),
                },
            )
        if (
            scheduled_shift.status != "published"
            or scheduled_shift.response_status != "acknowledged"
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "scheduled_shift_not_ready",
                    "message": "A published, acknowledged shift is required",
                },
            )
        start = (
            scheduled_shift.scheduled_start_at
            if scheduled_shift.scheduled_start_at.tzinfo
            else scheduled_shift.scheduled_start_at.replace(tzinfo=UTC)
        )
        end = (
            scheduled_shift.scheduled_end_at
            if scheduled_shift.scheduled_end_at.tzinfo
            else scheduled_shift.scheduled_end_at.replace(tzinfo=UTC)
        )
        if now < start - CLOCK_IN_EARLY_WINDOW or now > end + CLOCK_IN_LATE_WINDOW:
            raise HTTPException(
                409,
                detail={
                    "code": "outside_scheduled_clock_window",
                    "message": "Use unscheduled clock-in outside the planned shift window",
                },
            )
        if (
            session.scalar(
                select(StaffShift.id).where(
                    StaffShift.organization_id == context.organization.id,
                    StaffShift.scheduled_shift_id == scheduled_shift.id,
                )
            )
            is not None
        ):
            raise HTTPException(
                409,
                detail={"code": "scheduled_shift_already_linked"},
            )
    shift = StaffShift(
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        facility_id=facility.id,
        scheduled_shift_id=scheduled_shift.id if scheduled_shift else None,
        clocked_in_at=now,
    )
    session.add(shift)
    flush_or_conflict(session, "Staff member already has an open shift")
    event = StaffShiftEvent(
        organization_id=context.organization.id,
        shift_id=shift.id,
        membership_id=context.membership.id,
        facility_id=facility.id,
        operation_id=payload.operation_id,
        event_type="clock_in",
        server_occurred_at=now,
        latitude=None,
        longitude=None,
        accuracy_meters=None,
        distance_meters=None,
        radius_meters=None,
    )
    session.add(event)
    if live_room_safety:
        create_clock_in_presence(
            session,
            context,
            shift=shift,
            operation_id=payload.operation_id,
            scheduled_shift=scheduled_shift,
            explicit_room_id=payload.room_id,
        )
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            cause_entity_type="staff_shift",
            cause_entity_id=shift.id,
        )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_shift.clocked_in",
        entity_type="staff_shift",
        entity_id=shift.id,
        facility_id=facility.id,
        details={"operation_id": str(payload.operation_id)},
    )
    commit_in_context(session, context)
    return (
        _shift_row_with_room_presence(session, context, shift)
        if live_room_safety
        else _shift_row(session, shift)
    )


@router.post("/shifts/clock-out")
def clock_out(
    payload: ShiftClockRequest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    shift_context(context)
    ensure_writable(request)
    if payload.room_id is not None:
        raise HTTPException(
            422,
            detail={
                "code": "clock_out_room_id_forbidden",
                "message": "room_id is valid only for clock-in.",
            },
        )
    lock_client_operation(session, context.organization.id, payload.operation_id)
    existing, _ = _clock_operation(session, context, payload, "clock_out")
    if existing is not None:
        shift = session.scalar(
            select(StaffShift).where(
                StaffShift.organization_id == context.organization.id,
                StaffShift.id == existing.shift_id,
            )
        )
        if shift.scheduled_shift_id != payload.scheduled_shift_id:
            raise HTTPException(
                409,
                detail={
                    "code": "operation_reused",
                    "message": "Operation identifier was retried with another scheduled shift",
                },
            )
        return _shift_row(session, shift)
    live_room_safety = foundation_enabled(request)
    preliminary_shifts = _member_open_shifts(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
    )
    if not preliminary_shifts:
        raise HTTPException(409, "Staff member has no open shift")
    if not any(
        value.facility_id == payload.facility_id
        and value.scheduled_shift_id == payload.scheduled_shift_id
        for value in preliminary_shifts
    ):
        raise HTTPException(
            409,
            detail={
                "code": "open_shift_mismatch",
                "message": "Clock-out does not match an open shift.",
            },
        )
    locked_facility_ids = {
        value.facility_id for value in preliminary_shifts
    }
    if live_room_safety:
        locked_facility_ids.update(
            session.scalars(
                select(StaffRoomPresenceSession.facility_id).where(
                    StaffRoomPresenceSession.organization_id
                    == context.organization.id,
                    StaffRoomPresenceSession.membership_id
                    == context.membership.id,
                    StaffRoomPresenceSession.ended_at.is_(None),
                )
            )
        )
        for facility_id in sorted(locked_facility_ids, key=str):
            lock_facility_projection(
                session, context.organization.id, facility_id
            )
    shifts = _member_open_shifts(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        lock=True,
    )
    canonical_facility_ids = {value.facility_id for value in shifts}
    if not canonical_facility_ids.issubset(locked_facility_ids):
        raise HTTPException(
            409,
            detail={
                "code": "projection_changed_retry",
                "message": "Open shift state changed; retry clock-out.",
            },
        )
    matching = [
        value
        for value in shifts
        if value.facility_id == payload.facility_id
        and value.scheduled_shift_id == payload.scheduled_shift_id
    ]
    if not matching:
        raise HTTPException(
            409,
            detail={
                "code": "open_shift_mismatch",
                "message": "Clock-out does not match an open shift.",
            },
        )
    shift = min(matching, key=lambda value: str(value.id))
    facilities = {
        value.id: value
        for value in session.scalars(
            select(Facility)
            .where(
                Facility.organization_id == context.organization.id,
                Facility.id.in_(locked_facility_ids),
            )
            .order_by(Facility.id)
            .with_for_update()
        )
    }
    if not canonical_facility_ids.issubset(set(facilities)):
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "open_shift_facility_missing",
            },
        )
    now = datetime.now(UTC)
    ordered_shifts = [shift] + [
        value for value in shifts if value.id != shift.id
    ]
    for index, value in enumerate(ordered_shifts):
        event_operation_id = (
            payload.operation_id
            if index == 0
            else uuid5(
                NAMESPACE_URL,
                (
                    "caresync:0041:terminal-shift:"
                    f"{payload.operation_id}:{value.id}"
                ),
            )
        )
        value.status = "closed"
        value.clocked_out_at = now
        session.add(
            StaffShiftEvent(
                organization_id=context.organization.id,
                shift_id=value.id,
                membership_id=context.membership.id,
                facility_id=value.facility_id,
                operation_id=event_operation_id,
                event_type="clock_out",
                server_occurred_at=now,
                latitude=None,
                longitude=None,
                accuracy_meters=None,
                distance_meters=None,
                radius_meters=None,
            )
        )
    if live_room_safety:
        closed_presences = close_presence_for_clock_out(
            session,
            context,
            shift=shift,
            operation_id=payload.operation_id,
            occurred_at=now,
            locked_facility_ids=locked_facility_ids,
        )
        affected_facility_ids = canonical_facility_ids | {
            value.facility_id for value in closed_presences
        }
        for facility_id in sorted(affected_facility_ids, key=str):
            facility = facilities.get(facility_id)
            if facility is None or facility.status != "active":
                continue
            reconcile_facility_exceptions(
                session,
                organization_id=context.organization.id,
                facility_id=facility_id,
                cause_entity_type="staff_shift",
                cause_entity_id=shift.id,
            )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff_shift.clocked_out",
        entity_type="staff_shift",
        entity_id=shift.id,
        facility_id=shift.facility_id,
        details={
            "operation_id": str(payload.operation_id),
            "closed_shift_ids": [
                str(value.id) for value in ordered_shifts
            ],
        },
    )
    commit_in_context(session, context)
    return _shift_row(session, shift)
