"""Organization onboarding, facilities, programs, rooms and Basic settings."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.api.basic.common import (
    cleaned_values,
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
)
from app.api.basic.dependencies import (
    BasicContextDependency,
    FacilityManageContext,
    FacilityReadContext,
    OwnerContext,
    refresh_basic_context,
)
from app.api.dependencies import SessionDependency
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Enrollment,
    Facility,
    MembershipRoomAssignment,
    OnboardingState,
    Program,
    Room,
    StaffRoomPresenceSession,
    StaffShift,
)
from app.basic.programs import PROGRAM_TYPES
from app.basic.room_safety import (
    foundation_enabled as room_safety_enabled,
)
from app.basic.room_safety import (
    lock_facility_projection,
    lock_release_facility_set,
    reconcile_facility_exceptions,
    resolve_facility_exceptions_for_deactivation,
)
from app.basic.schemas import (
    DeactivationImpactResponse,
    FacilityCreate,
    FacilityPatch,
    FacilityResponse,
    OnboardingPatch,
    OnboardingResponse,
    OrganizationPatch,
    OrganizationResponse,
    ProgramCreate,
    ProgramPatch,
    ProgramResponse,
    RoomCreate,
    RoomPatch,
    RoomResponse,
    SettingsPatch,
    SettingsResponse,
)
from app.basic.security import audit
from app.basic.verification import (
    TEMPORARY_AUTO_APPROVAL,
    apply_temporary_daycare_approval,
)

router = APIRouter(tags=["basic organization"])
OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")


def _facility(session: SessionDependency, organization_id: UUID, facility_id: UUID) -> Facility:
    value = session.scalar(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.organization_id == organization_id,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    return value


def _lock_facility(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
) -> Facility:
    """Serialize facility-scoped room and program capacity mutations."""

    value = session.scalar(
        select(Facility)
        .where(
            Facility.id == facility_id,
            Facility.organization_id == organization_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    return value


def _count(session: SessionDependency, statement) -> int:
    return int(session.scalar(statement) or 0)


def _facility_deactivation_impact(
    session: SessionDependency,
    organization_id: UUID,
    facility: Facility,
    *,
    include_room_presence: bool = False,
) -> DeactivationImpactResponse:
    active_programs = _count(
        session,
        select(func.count())
        .select_from(Program)
        .where(
            Program.organization_id == organization_id,
            Program.facility_id == facility.id,
            Program.is_active.is_(True),
        ),
    )
    active_rooms = _count(
        session,
        select(func.count())
        .select_from(Room)
        .where(
            Room.organization_id == organization_id,
            Room.facility_id == facility.id,
            Room.is_active.is_(True),
        ),
    )
    open_enrollments = _count(
        session,
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.facility_id == facility.id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        ),
    )
    open_attendance_intervals = _count(
        session,
        select(func.count())
        .select_from(AttendanceInterval)
        .join(
            AttendanceDay,
            (AttendanceDay.organization_id == AttendanceInterval.organization_id)
            & (AttendanceDay.id == AttendanceInterval.attendance_day_id),
        )
        .where(
            AttendanceInterval.organization_id == organization_id,
            AttendanceDay.facility_id == facility.id,
            AttendanceInterval.checked_out_at.is_(None),
        ),
    )
    active_staff_assignments = _count(
        session,
        select(func.count())
        .select_from(MembershipRoomAssignment)
        .where(
            MembershipRoomAssignment.organization_id == organization_id,
            MembershipRoomAssignment.facility_id == facility.id,
            MembershipRoomAssignment.is_active.is_(True),
        ),
    )
    open_staff_shifts = _count(
        session,
        select(func.count())
        .select_from(StaffShift)
        .where(
            StaffShift.organization_id == organization_id,
            StaffShift.facility_id == facility.id,
            StaffShift.status == "open",
        ),
    )
    open_staff_room_presences = (
        _count(
            session,
            select(func.count())
            .select_from(StaffRoomPresenceSession)
            .where(
                StaffRoomPresenceSession.organization_id == organization_id,
                StaffRoomPresenceSession.facility_id == facility.id,
                StaffRoomPresenceSession.ended_at.is_(None),
            ),
        )
        if include_room_presence
        else 0
    )
    warning_values = {"active staff assignments": active_staff_assignments}
    blocker_values = {
        "active programs": active_programs,
        "active rooms": active_rooms,
        "open enrollments": open_enrollments,
        "open attendance intervals": open_attendance_intervals,
        "open staff shifts": open_staff_shifts,
        "open staff room presences": open_staff_room_presences,
    }
    warnings = [f"{count} {label}" for label, count in warning_values.items() if count]
    blockers = [f"{count} {label}" for label, count in blocker_values.items() if count]
    return DeactivationImpactResponse(
        organization_id=organization_id,
        entity_type="facility",
        entity_id=facility.id,
        entity_name=facility.name,
        active_programs=active_programs,
        active_rooms=active_rooms,
        open_enrollments=open_enrollments,
        open_attendance_intervals=open_attendance_intervals,
        active_staff_assignments=active_staff_assignments,
        open_staff_shifts=open_staff_shifts,
        open_staff_room_presences=open_staff_room_presences,
        blockers=blockers,
        warnings=warnings,
        can_deactivate=not blockers,
        confirmation_text=facility.name,
    )


def _room_deactivation_impact(
    session: SessionDependency,
    organization_id: UUID,
    room: Room,
    *,
    include_room_presence: bool = False,
) -> DeactivationImpactResponse:
    open_enrollments = _count(
        session,
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.room_id == room.id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        ),
    )
    open_attendance_intervals = _count(
        session,
        select(func.count())
        .select_from(AttendanceInterval)
        .join(
            AttendanceDay,
            (AttendanceDay.organization_id == AttendanceInterval.organization_id)
            & (AttendanceDay.id == AttendanceInterval.attendance_day_id),
        )
        .where(
            AttendanceInterval.organization_id == organization_id,
            AttendanceDay.room_id == room.id,
            AttendanceInterval.checked_out_at.is_(None),
        ),
    )
    active_staff_assignments = _count(
        session,
        select(func.count())
        .select_from(MembershipRoomAssignment)
        .where(
            MembershipRoomAssignment.organization_id == organization_id,
            MembershipRoomAssignment.room_id == room.id,
            MembershipRoomAssignment.is_active.is_(True),
        ),
    )
    open_staff_room_presences = (
        _count(
            session,
            select(func.count())
            .select_from(StaffRoomPresenceSession)
            .where(
                StaffRoomPresenceSession.organization_id == organization_id,
                StaffRoomPresenceSession.room_id == room.id,
                StaffRoomPresenceSession.ended_at.is_(None),
            ),
        )
        if include_room_presence
        else 0
    )
    warning_values = {"active staff assignments": active_staff_assignments}
    blocker_values = {
        "open enrollments": open_enrollments,
        "open attendance intervals": open_attendance_intervals,
        "open staff room presences": open_staff_room_presences,
    }
    warnings = [f"{count} {label}" for label, count in warning_values.items() if count]
    blockers = [f"{count} {label}" for label, count in blocker_values.items() if count]
    return DeactivationImpactResponse(
        organization_id=organization_id,
        entity_type="room",
        entity_id=room.id,
        entity_name=room.name,
        open_enrollments=open_enrollments,
        open_attendance_intervals=open_attendance_intervals,
        active_staff_assignments=active_staff_assignments,
        open_staff_room_presences=open_staff_room_presences,
        blockers=blockers,
        warnings=warnings,
        can_deactivate=not blockers,
        confirmation_text=room.name,
    )


def _confirm_deactivation(
    *,
    impact: DeactivationImpactResponse,
    confirmation: str | None,
    reason: str | None,
) -> str:
    if impact.blockers:
        raise HTTPException(
            status_code=409,
            detail=f"Resolve deactivation blockers first: {', '.join(impact.blockers)}",
        )
    if (confirmation or "").strip() != impact.confirmation_text:
        raise HTTPException(
            status_code=422,
            detail=f"Type the exact name '{impact.confirmation_text}' to confirm deactivation",
        )
    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 3:
        raise HTTPException(status_code=422, detail="A deactivation reason is required")
    return cleaned_reason


def _program(session: SessionDependency, organization_id: UUID, program_id: UUID) -> Program:
    value = session.scalar(
        select(Program).where(
            Program.id == program_id,
            Program.organization_id == organization_id,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return value


def _room(session: SessionDependency, organization_id: UUID, room_id: UUID) -> Room:
    value = session.scalar(
        select(Room).where(Room.id == room_id, Room.organization_id == organization_id)
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return value


def _validate_program_facility(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    program_id: UUID,
) -> Program:
    program = _program(session, organization_id, program_id)
    if program.facility_id != facility_id:
        raise HTTPException(status_code=409, detail="Program belongs to another facility")
    return program


def _normalized_room_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _ensure_room_name_available(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    name: str,
    *,
    exclude_room_id: UUID | None = None,
) -> None:
    statement = select(Room.id, Room.name).where(
        Room.organization_id == organization_id,
        Room.facility_id == facility_id,
    )
    if exclude_room_id is not None:
        statement = statement.where(Room.id != exclude_room_id)
    normalized_name = _normalized_room_name(name)
    if any(
        _normalized_room_name(existing_name) == normalized_name
        for _, existing_name in session.execute(statement)
    ):
        raise HTTPException(
            status_code=409,
            detail="A room with this name already exists in this facility",
        )


def _active_room_capacity(
    session: SessionDependency,
    organization_id: UUID,
    program_id: UUID,
    *,
    exclude_room_id: UUID | None = None,
) -> int:
    statement = select(func.coalesce(func.sum(Room.capacity), 0)).where(
        Room.organization_id == organization_id,
        Room.program_id == program_id,
        Room.is_active.is_(True),
    )
    if exclude_room_id is not None:
        statement = statement.where(Room.id != exclude_room_id)
    return int(session.scalar(statement) or 0)


def _open_enrollment_commitments(
    session: SessionDependency,
    organization_id: UUID,
    *,
    program_id: UUID | None = None,
    room_id: UUID | None = None,
) -> int:
    statement = (
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            Enrollment.placement_effective_date.is_not(None),
        )
    )
    if program_id is not None:
        statement = statement.where(Enrollment.program_id == program_id)
    if room_id is not None:
        statement = statement.where(Enrollment.room_id == room_id)
    return int(session.scalar(statement) or 0)


def _validate_active_room_capacity(
    session: SessionDependency,
    organization_id: UUID,
    program: Program,
    requested_capacity: int,
    *,
    exclude_room_id: UUID | None = None,
) -> None:
    if not program.is_active:
        raise HTTPException(
            status_code=422,
            detail="An active room must be assigned to an active program",
        )
    assigned_capacity = _active_room_capacity(
        session,
        organization_id,
        program.id,
        exclude_room_id=exclude_room_id,
    )
    resulting_capacity = assigned_capacity + requested_capacity
    if resulting_capacity > program.capacity:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Active room capacity would be {resulting_capacity}, exceeding "
                f"the program capacity of {program.capacity}"
            ),
        )


@router.get("/organization", response_model=OrganizationResponse)
def get_organization(context: BasicContextDependency) -> OrganizationResponse:
    return OrganizationResponse.model_validate(context.organization)


@router.patch("/organization", response_model=OrganizationResponse)
def patch_organization(
    payload: OrganizationPatch,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> OrganizationResponse:
    ensure_writable(request)
    values = cleaned_values(payload.model_dump(exclude_unset=True))
    identity_fields = {"name", "legal_name"}
    identity_changed = any(
        key in identity_fields and getattr(context.organization, key) != value
        for key, value in values.items()
    )
    before = {key: getattr(context.organization, key) for key in values}
    for key, value in values.items():
        setattr(context.organization, key, value)
    if identity_changed:
        apply_temporary_daycare_approval(context.organization)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="organization.updated",
        entity_type="organization",
        entity_id=context.organization.id,
        details={
            "before": before,
            "changed_fields": sorted(values),
            "verification_refreshed": identity_changed,
        },
    )
    commit_in_context(session, context, "Organization details conflict with existing data")
    session.refresh(context.organization)
    return OrganizationResponse.model_validate(context.organization)


@router.get("/onboarding", response_model=OnboardingResponse)
def get_onboarding(
    context: OwnerContext,
    session: SessionDependency,
) -> OnboardingResponse:
    onboarding = session.get(OnboardingState, context.organization.id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="Onboarding state not found")
    facilities = list(
        session.scalars(
            select(Facility)
            .where(Facility.organization_id == context.organization.id)
            .order_by(Facility.created_at)
        )
    )
    return OnboardingResponse(
        organization_id=onboarding.organization_id,
        status=onboarding.status,
        current_step=onboarding.current_step,
        completed_steps=list(onboarding.completed_steps or []),
        draft=dict(onboarding.draft or {}),
        completed_at=onboarding.completed_at,
        organization=OrganizationResponse.model_validate(context.organization),
        facilities=[FacilityResponse.model_validate(item) for item in facilities],
    )


@router.patch("/onboarding", response_model=OnboardingResponse)
def patch_onboarding(
    payload: OnboardingPatch,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> OnboardingResponse:
    ensure_writable(request)
    onboarding = session.get(OnboardingState, context.organization.id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="Onboarding state not found")
    if onboarding.status == "complete":
        raise HTTPException(status_code=409, detail="Onboarding is already complete")
    values = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "completed_steps" in values:
        values["completed_steps"] = list(dict.fromkeys(values["completed_steps"]))
    for key, value in values.items():
        setattr(onboarding, key, value)
    onboarding.status = "in_progress"
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="onboarding.saved",
        entity_type="organization_onboarding",
        entity_id=context.organization.id,
        details={"changed_fields": sorted(values)},
    )
    commit_in_context(session, context)
    return get_onboarding(context, session)


@router.post("/onboarding/complete", response_model=OnboardingResponse)
def complete_onboarding(
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> OnboardingResponse:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        # Onboarding can promote every draft facility in one transaction.  It
        # therefore participates in the same facility-set -> sorted facility
        # projection -> source-row order as ordinary facility mutations.
        lock_release_facility_set(session, context.organization.id)
    onboarding = session.get(OnboardingState, context.organization.id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="Onboarding state not found")
    facility_ids = tuple(
        session.scalars(
            select(Facility.id)
            .where(Facility.organization_id == context.organization.id)
            .order_by(Facility.id)
        )
    )
    if live_room_safety:
        for facility_id in facility_ids:
            lock_facility_projection(
                session, context.organization.id, facility_id
            )
    facilities = list(
        session.scalars(
            select(Facility)
            .where(Facility.organization_id == context.organization.id)
            .order_by(Facility.id)
            .with_for_update()
        )
    )
    if tuple(facility.id for facility in facilities) != facility_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "facility_set_changed_retry",
                "message": "The facility set changed. Retry onboarding completion.",
            },
        )
    if not facilities:
        raise HTTPException(
            status_code=422,
            detail="Complete onboarding requires at least one facility",
        )

    # Draft facilities are eligible because this transaction promotes them to
    # active after the care structure has passed validation. Inactive
    # facilities cannot satisfy onboarding.
    eligible_facility_statuses = ("draft", "active")
    active_program_count = session.scalar(
        select(func.count())
        .select_from(Program)
        .join(
            Facility,
            (Facility.organization_id == Program.organization_id)
            & (Facility.id == Program.facility_id),
        )
        .where(
            Program.organization_id == context.organization.id,
            Program.program_type.in_(PROGRAM_TYPES),
            Program.is_active.is_(True),
            Facility.status.in_(eligible_facility_statuses),
        )
    )
    if not active_program_count:
        raise HTTPException(
            status_code=422,
            detail=(
                "Complete onboarding requires at least one active Daycare or OSC "
                "program in an active facility"
            ),
        )

    eligible_active_room_count = session.scalar(
        select(func.count())
        .select_from(Room)
        .join(
            Facility,
            (Facility.organization_id == Room.organization_id) & (Facility.id == Room.facility_id),
        )
        .where(
            Room.organization_id == context.organization.id,
            Room.is_active.is_(True),
            Facility.status.in_(eligible_facility_statuses),
        )
    )
    valid_active_room_count = session.scalar(
        select(func.count())
        .select_from(Room)
        .join(
            Program,
            (Program.organization_id == Room.organization_id)
            & (Program.id == Room.program_id)
            & (Program.facility_id == Room.facility_id),
        )
        .join(
            Facility,
            (Facility.organization_id == Program.organization_id)
            & (Facility.id == Program.facility_id),
        )
        .where(
            Room.organization_id == context.organization.id,
            Room.is_active.is_(True),
            Program.program_type.in_(PROGRAM_TYPES),
            Program.is_active.is_(True),
            Facility.status.in_(eligible_facility_statuses),
        )
    )
    if eligible_active_room_count != valid_active_room_count:
        raise HTTPException(
            status_code=422,
            detail=(
                "Every active room must be assigned to an active Daycare or OSC "
                "program in the same facility before onboarding can be completed"
            ),
        )
    programs_with_active_rooms = session.scalar(
        select(func.count(func.distinct(Program.id)))
        .select_from(Program)
        .join(
            Facility,
            (Facility.organization_id == Program.organization_id)
            & (Facility.id == Program.facility_id),
        )
        .join(
            Room,
            (Room.organization_id == Program.organization_id)
            & (Room.program_id == Program.id)
            & (Room.facility_id == Program.facility_id),
        )
        .where(
            Program.organization_id == context.organization.id,
            Program.program_type.in_(PROGRAM_TYPES),
            Program.is_active.is_(True),
            Room.is_active.is_(True),
            Facility.status.in_(eligible_facility_statuses),
        )
    )
    if programs_with_active_rooms != active_program_count:
        raise HTTPException(
            status_code=422,
            detail=(
                "Every active Daycare or OSC program must have at least one active "
                "room before onboarding can be completed"
            ),
        )
    for facility in facilities:
        if facility.status == "draft":
            facility.status = "active"
    context.organization.status = "active"
    onboarding.status = "complete"
    onboarding.current_step = "complete"
    onboarding.completed_steps = list(
        dict.fromkeys(
            [*list(onboarding.completed_steps or []), "organization", "facility", "rooms"]
        )
    )
    onboarding.completed_at = datetime.now(UTC)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="onboarding.completed",
        entity_type="organization",
        entity_id=context.organization.id,
    )
    if live_room_safety:
        for facility in facilities:
            if facility.status == "active":
                reconcile_facility_exceptions(
                    session,
                    organization_id=context.organization.id,
                    facility_id=facility.id,
                    cause_entity_type="facility",
                    cause_entity_id=facility.id,
                )
    commit_in_context(session, context)
    return get_onboarding(context, session)


@router.get("/facilities", response_model=list[FacilityResponse])
def list_facilities(
    context: FacilityReadContext,
    session: SessionDependency,
) -> list[Facility]:
    statement = select(Facility).where(Facility.organization_id == context.organization.id)
    if not context.organization_wide:
        statement = statement.where(Facility.id.in_(context.assigned_facility_ids))
    return list(session.scalars(statement.order_by(Facility.name)))


@router.post("/facilities", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
def create_facility(
    payload: FacilityCreate,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> Facility:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    facility = Facility(
        id=uuid4(),
        organization_id=context.organization.id,
        **cleaned_values(payload.model_dump()),
    )
    if live_room_safety:
        lock_release_facility_set(session, context.organization.id)
        lock_facility_projection(
            session, context.organization.id, facility.id
        )
    apply_temporary_daycare_approval(facility)
    session.add(facility)
    flush_or_conflict(session, "Facility name or licence already exists")
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="facility.created",
        entity_type="facility",
        entity_id=facility.id,
        facility_id=facility.id,
        details={"verification_method": TEMPORARY_AUTO_APPROVAL},
    )
    if live_room_safety and facility.status == "active":
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            cause_entity_type="facility",
            cause_entity_id=facility.id,
        )
    commit_in_context(session, context, "Facility name or licence already exists")
    session.refresh(facility)
    return facility


@router.get("/facilities/{facility_id}", response_model=FacilityResponse)
def get_facility(
    facility_id: UUID,
    context: FacilityReadContext,
    session: SessionDependency,
) -> Facility:
    facility = _facility(session, context.organization.id, facility_id)
    if not context.organization_wide and facility.id not in context.assigned_facility_ids:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


@router.get(
    "/facilities/{facility_id}/deactivation-impact",
    response_model=DeactivationImpactResponse,
)
def get_facility_deactivation_impact(
    facility_id: UUID,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> DeactivationImpactResponse:
    facility = _facility(session, context.organization.id, facility_id)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, facility.id
        )
    return _facility_deactivation_impact(
        session,
        context.organization.id,
        facility,
        include_room_presence=live_room_safety,
    )


@router.patch("/facilities/{facility_id}", response_model=FacilityResponse)
def patch_facility(
    facility_id: UUID,
    payload: FacilityPatch,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> Facility:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_release_facility_set(session, context.organization.id)
        lock_facility_projection(
            session, context.organization.id, facility_id
        )
    facility = _lock_facility(session, context.organization.id, facility_id)
    values = cleaned_values(payload.model_dump(exclude_unset=True))
    confirmation = values.pop("deactivation_confirmation", None)
    requested_reason = values.pop("deactivation_reason", None)
    deactivation_reason = None
    deactivation_impact = None
    if facility.status == "active" and values.get("status") == "draft":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "active_facility_cannot_return_to_draft",
                "message": (
                    "An active facility cannot return to draft. Use the "
                    "guarded inactive transition instead."
                ),
            },
        )
    if values.get("status") == "inactive" and facility.status != "inactive":
        deactivation_impact = _facility_deactivation_impact(
            session,
            context.organization.id,
            facility,
            include_room_presence=live_room_safety,
        )
        deactivation_reason = _confirm_deactivation(
            impact=deactivation_impact,
            confirmation=confirmation,
            reason=requested_reason,
        )
    identity_fields = {
        "name",
        "license_number",
        "street_address",
        "city",
        "province",
        "postal_code",
        "licensed_capacity",
    }
    identity_changed = any(
        key in identity_fields and getattr(facility, key) != value for key, value in values.items()
    )
    before = {key: str(getattr(facility, key)) for key in values}
    for key, value in values.items():
        setattr(facility, key, value)
    if (
        facility.opening_time
        and facility.closing_time
        and facility.closing_time <= facility.opening_time
    ):
        raise HTTPException(status_code=422, detail="closing_time must be after opening_time")
    if identity_changed:
        apply_temporary_daycare_approval(facility)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="facility.updated",
        entity_type="facility",
        entity_id=facility.id,
        facility_id=facility.id,
        details={
            "before": before,
            "changed_fields": sorted(values),
            "verification_refreshed": identity_changed,
            "deactivation_reason": deactivation_reason,
            "deactivation_impact": (
                deactivation_impact.model_dump(mode="json") if deactivation_impact else None
            ),
        },
    )
    if live_room_safety:
        if facility.status != "active":
            resolve_facility_exceptions_for_deactivation(
                session,
                organization_id=context.organization.id,
                facility_id=facility.id,
                cause_entity_id=facility.id,
            )
        else:
            reconcile_facility_exceptions(
                session,
                organization_id=context.organization.id,
                facility_id=facility.id,
                cause_entity_type="facility",
                cause_entity_id=facility.id,
            )
    commit_in_context(session, context, "Facility name or licence conflicts with existing data")
    session.refresh(facility)
    return facility


@router.get("/programs", response_model=list[ProgramResponse])
def list_programs(
    context: FacilityReadContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
) -> list[Program]:
    statement = select(Program).where(Program.organization_id == context.organization.id)
    if not context.organization_wide:
        statement = statement.where(Program.facility_id.in_(context.assigned_facility_ids))
    if facility_id is not None:
        _facility(session, context.organization.id, facility_id)
        statement = statement.where(Program.facility_id == facility_id)
    return list(session.scalars(statement.order_by(Program.name)))


@router.post("/programs", response_model=ProgramResponse, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: ProgramCreate,
    request: Request,
    context: FacilityManageContext,
    session: SessionDependency,
) -> Program:
    ensure_writable(request)
    _lock_facility(session, context.organization.id, payload.facility_id)
    program = Program(organization_id=context.organization.id, **payload.model_dump())
    session.add(program)
    flush_or_conflict(session, "A program with this name or licence type already exists")
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="program.created",
        entity_type="facility_program",
        entity_id=program.id,
        facility_id=program.facility_id,
    )
    commit_in_context(session, context, "A program with this name or licence type already exists")
    session.refresh(program)
    return program


@router.patch("/programs/{program_id}", response_model=ProgramResponse)
def patch_program(
    program_id: UUID,
    payload: ProgramPatch,
    request: Request,
    context: FacilityManageContext,
    session: SessionDependency,
) -> Program:
    ensure_writable(request)
    program = _program(session, context.organization.id, program_id)
    _lock_facility(session, context.organization.id, program.facility_id)
    session.refresh(program, with_for_update=True)
    values = payload.model_dump(exclude_unset=True)
    assigned_room_capacity = _active_room_capacity(
        session,
        context.organization.id,
        program.id,
    )
    enrollment_commitments = _open_enrollment_commitments(
        session,
        context.organization.id,
        program_id=program.id,
    )
    if "capacity" in values and values["capacity"] < assigned_room_capacity:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Program capacity cannot be below its active room capacity of "
                f"{assigned_room_capacity}"
            ),
        )
    if "capacity" in values and values["capacity"] < enrollment_commitments:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "program_capacity_below_commitments",
                "open_commitments": enrollment_commitments,
            },
        )
    if values.get("is_active") is False and enrollment_commitments:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "program_deactivation_blocked_commitments",
                "open_commitments": enrollment_commitments,
            },
        )
    if values.get("is_active") is False and assigned_room_capacity > 0:
        raise HTTPException(
            status_code=422,
            detail="A program with active assigned rooms cannot be deactivated",
        )
    for key, value in values.items():
        setattr(program, key, value)
    if (
        program.minimum_age_months is not None
        and program.maximum_age_months is not None
        and program.maximum_age_months < program.minimum_age_months
    ):
        raise HTTPException(status_code=422, detail="Invalid program age range")
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="program.updated",
        entity_type="facility_program",
        entity_id=program.id,
        facility_id=program.facility_id,
        details={"changed_fields": sorted(values)},
    )
    commit_in_context(
        session,
        context,
        "A program with this name or licence type already exists",
    )
    session.refresh(program)
    return program


@router.get("/rooms", response_model=list[RoomResponse])
def list_rooms(
    context: FacilityReadContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
) -> list[Room]:
    statement = select(Room).where(Room.organization_id == context.organization.id)
    if not context.organization_wide:
        statement = statement.where(Room.id.in_(context.assigned_room_ids))
    if facility_id is not None:
        _facility(session, context.organization.id, facility_id)
        statement = statement.where(Room.facility_id == facility_id)
    return list(session.scalars(statement.order_by(Room.name)))


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    request: Request,
    context: FacilityManageContext,
    session: SessionDependency,
) -> Room:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, payload.facility_id
        )
    _lock_facility(session, context.organization.id, payload.facility_id)
    program = _validate_program_facility(
        session, context.organization.id, payload.facility_id, payload.program_id
    )
    _ensure_room_name_available(
        session,
        context.organization.id,
        payload.facility_id,
        payload.name,
    )
    if payload.is_active:
        _validate_active_room_capacity(
            session,
            context.organization.id,
            program,
            payload.capacity,
        )
    room = Room(organization_id=context.organization.id, **payload.model_dump())
    session.add(room)
    flush_or_conflict(session, "A room with this name already exists in this facility")
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="room.created",
        entity_type="room",
        entity_id=room.id,
        facility_id=room.facility_id,
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=room.facility_id,
            cause_entity_type="room",
            cause_entity_id=room.id,
        )
    commit_in_context(session, context, "A room with this name already exists in this facility")
    session.refresh(room)
    return room


@router.get("/rooms/{room_id}", response_model=RoomResponse)
def get_room(
    room_id: UUID,
    context: FacilityReadContext,
    session: SessionDependency,
) -> Room:
    room = _room(session, context.organization.id, room_id)
    if not context.organization_wide and room.id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.get(
    "/rooms/{room_id}/deactivation-impact",
    response_model=DeactivationImpactResponse,
)
def get_room_deactivation_impact(
    room_id: UUID,
    request: Request,
    context: FacilityManageContext,
    session: SessionDependency,
) -> DeactivationImpactResponse:
    room = _room(session, context.organization.id, room_id)
    if not context.organization_wide and room.id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Room not found")
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, room.facility_id
        )
        session.refresh(room)
        current_context = refresh_basic_context(
            session,
            context,
            required_all_permissions=("facility:manage",),
            conceal_detail="Room not found",
        )
        if (
            not current_context.organization_wide
            and room.id not in current_context.assigned_room_ids
        ):
            raise HTTPException(status_code=404, detail="Room not found")
    return _room_deactivation_impact(
        session,
        context.organization.id,
        room,
        include_room_presence=live_room_safety,
    )


@router.patch("/rooms/{room_id}", response_model=RoomResponse)
def patch_room(
    room_id: UUID,
    payload: RoomPatch,
    request: Request,
    context: FacilityManageContext,
    session: SessionDependency,
) -> Room:
    ensure_writable(request)
    room = _room(session, context.organization.id, room_id)
    if not context.organization_wide and room.id not in context.assigned_room_ids:
        raise HTTPException(status_code=404, detail="Room not found")
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    if live_room_safety:
        lock_facility_projection(
            session, context.organization.id, room.facility_id
        )
    _lock_facility(session, context.organization.id, room.facility_id)
    session.refresh(room, with_for_update=True)
    if live_room_safety:
        current_context = refresh_basic_context(
            session,
            context,
            required_all_permissions=("facility:manage",),
            conceal_detail="Room not found",
        )
        if (
            not current_context.organization_wide
            and room.id not in current_context.assigned_room_ids
        ):
            raise HTTPException(status_code=404, detail="Room not found")
    values = payload.model_dump(exclude_unset=True)
    confirmation = values.pop("deactivation_confirmation", None)
    requested_reason = values.pop("deactivation_reason", None)
    deactivation_reason = None
    deactivation_impact = None
    if values.get("is_active") is False and room.is_active:
        deactivation_impact = _room_deactivation_impact(
            session,
            context.organization.id,
            room,
            include_room_presence=live_room_safety,
        )
        deactivation_reason = _confirm_deactivation(
            impact=deactivation_impact,
            confirmation=confirmation,
            reason=requested_reason,
        )
    program_id = values.get("program_id", room.program_id)
    program = (
        _validate_program_facility(
            session,
            context.organization.id,
            room.facility_id,
            program_id,
        )
        if program_id is not None
        else None
    )
    resulting_name = values.get("name", room.name)
    _ensure_room_name_available(
        session,
        context.organization.id,
        room.facility_id,
        resulting_name,
        exclude_room_id=room.id,
    )
    resulting_active = values.get("is_active", room.is_active)
    resulting_capacity = values.get("capacity", room.capacity)
    room_commitments = _open_enrollment_commitments(
        session,
        context.organization.id,
        room_id=room.id,
    )
    if resulting_capacity < room_commitments:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "room_capacity_below_commitments",
                "open_commitments": room_commitments,
            },
        )
    if resulting_active:
        if program is None:
            raise HTTPException(
                status_code=422,
                detail="An active room must be assigned to an active program",
            )
        _validate_active_room_capacity(
            session,
            context.organization.id,
            program,
            resulting_capacity,
            exclude_room_id=room.id,
        )
    for key, value in values.items():
        setattr(room, key, value)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="room.updated",
        entity_type="room",
        entity_id=room.id,
        facility_id=room.facility_id,
        details={
            "changed_fields": sorted(values),
            "deactivation_reason": deactivation_reason,
            "deactivation_impact": (
                deactivation_impact.model_dump(mode="json") if deactivation_impact else None
            ),
        },
    )
    if live_room_safety:
        reconcile_facility_exceptions(
            session,
            organization_id=context.organization.id,
            facility_id=room.facility_id,
            cause_entity_type="room",
            cause_entity_id=room.id,
        )
    commit_in_context(session, context, "A room with this name already exists in this facility")
    session.refresh(room)
    return room


@router.get("/settings", response_model=SettingsResponse)
def get_settings(context: OwnerContext) -> SettingsResponse:
    return SettingsResponse(
        organization_id=context.organization.id,
        timezone=context.organization.timezone,
        preferences=dict(context.organization.preferences or {}),
    )


@router.patch("/settings", response_model=SettingsResponse)
def patch_settings(
    payload: SettingsPatch,
    request: Request,
    context: OwnerContext,
    session: SessionDependency,
) -> SettingsResponse:
    ensure_writable(request)
    values = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "timezone" in values:
        context.organization.timezone = values["timezone"].strip()
    if "preferences" in values:
        context.organization.preferences = values["preferences"]
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="settings.updated",
        entity_type="organization",
        entity_id=context.organization.id,
        details={"changed_fields": sorted(values)},
    )
    commit_in_context(session, context)
    return get_settings(context)
