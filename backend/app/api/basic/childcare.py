"""Tenant-safe Basic families, children and enrollment workflows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import Date, Integer, and_, case, cast, exists, extract, func, literal, or_, select

from app.api.basic.common import (
    cleaned_values,
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
)
from app.api.basic.dependencies import (
    CareRosterContext,
    ChildcareManageContext,
    ChildcareReadContext,
    ChildPhotoReadContext,
)
from app.api.dependencies import SessionDependency
from app.basic.childcare_commands import begin_command, record_command, require_version
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    ChildProfilePhoto,
    EmergencyContact,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Program,
    Room,
)
from app.basic.profile_photos import normalize_profile_photo
from app.basic.programs import PROGRAM_TYPES
from app.basic.schemas import (
    ChildCreate,
    ChildDirectoryCounts,
    ChildDirectoryItem,
    ChildDirectoryOpenEnrollment,
    ChildDirectoryPage,
    ChildFamilyProfileResponse,
    ChildPatch,
    ChildProfilePhotoResponse,
    ChildProfileResponse,
    ChildResponse,
    EmergencyContactInput,
    EmergencyContactResponse,
    EmergencyContactsReplace,
    EnrollmentInput,
    EnrollmentPatch,
    EnrollmentResponse,
    FamilyBillingGuardian,
    FamilyBillingOption,
    FamilyBillingOptionsPage,
    FamilyCreate,
    FamilyDirectoryChildPreview,
    FamilyDirectoryItem,
    FamilyDirectoryPage,
    FamilyDirectoryPrimaryContact,
    FamilyOption,
    FamilyOptionsPage,
    FamilyPatch,
    FamilyResponse,
    FamilyStatsResponse,
    GuardianInput,
    GuardianResponse,
    GuardianSectionReplace,
    RoomRosterChildResponse,
    RoomRosterResponse,
    RoomRosterWorkspaceResponse,
)
from app.basic.security import audit

router = APIRouter(tags=["basic childcare"])

OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")


def _profile_photo_url(child_id: UUID) -> str:
    return f"/api/v1/children/{child_id}/photo"


def _local_today(timezone_name: str) -> date:
    try:
        return datetime.now(UTC).astimezone(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(
            status_code=422,
            detail="Timezone must be corrected before changing child records",
        ) from None


def _age_group(birth_date: date, *, today: date) -> str:
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today.day < birth_date.day:
        months -= 1
    if months <= 19:
        return "Infant"
    if months <= 36:
        return "Toddler"
    if months <= 77:
        return "Preschool"
    return "School-Age"


def _full_calendar_months(birth_date: date, as_of: date) -> int:
    months = (as_of.year - birth_date.year) * 12 + as_of.month - birth_date.month
    if as_of.day < birth_date.day:
        months -= 1
    return months


def _validate_dob_against_open_placement(
    session: SessionDependency,
    organization_id: UUID,
    child: Child,
    proposed_dob: date,
) -> None:
    snapshots = list(
        session.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == organization_id,
                Enrollment.child_id == child.id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
                Enrollment.room_id.is_not(None),
            )
        )
    )
    for snapshot in sorted(snapshots, key=lambda item: (str(item.facility_id), str(item.id))):
        facility = session.scalar(
            select(Facility)
            .where(
                Facility.organization_id == organization_id,
                Facility.id == snapshot.facility_id,
            )
            .with_for_update()
        )
        enrollment = session.scalar(
            select(Enrollment)
            .where(
                Enrollment.organization_id == organization_id,
                Enrollment.id == snapshot.id,
            )
            .with_for_update()
        )
        room = session.scalar(
            select(Room)
            .where(
                Room.organization_id == organization_id,
                Room.id == snapshot.room_id,
            )
            .with_for_update()
        )
        if facility is None or enrollment is None or room is None:
            raise HTTPException(409, detail={"code": "enrollment_placement_incoherent"})
        if enrollment.start_date < proposed_dob:
            raise HTTPException(
                409,
                detail={"code": "dob_conflicts_with_enrollment_start"},
            )
        effective_date = max(
            enrollment.start_date,
            enrollment.placement_effective_date or enrollment.start_date,
            _local_today(facility.timezone),
        )
        age_months = _full_calendar_months(proposed_dob, effective_date)
        if (
            room.minimum_age_months is None
            or room.maximum_age_months is None
            or not room.minimum_age_months <= age_months <= room.maximum_age_months
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "dob_invalidates_room_placement",
                    "enrollment_id": str(enrollment.id),
                    "room_id": str(room.id),
                },
            )


def _family(session: SessionDependency, organization_id: UUID, family_id: UUID) -> Family:
    value = session.scalar(
        select(Family).where(
            Family.id == family_id,
            Family.organization_id == organization_id,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Family not found")
    return value


def _child(session: SessionDependency, organization_id: UUID, child_id: UUID) -> Child:
    value = session.scalar(
        select(Child).where(Child.id == child_id, Child.organization_id == organization_id)
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Child not found")
    return value


def _profile_photo(
    session: SessionDependency,
    organization_id: UUID,
    child_id: UUID,
    *,
    lock: bool = False,
) -> ChildProfilePhoto | None:
    statement = select(ChildProfilePhoto).where(
        ChildProfilePhoto.organization_id == organization_id,
        ChildProfilePhoto.child_id == child_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _ensure_photo_read_scope(
    session: SessionDependency,
    context: ChildPhotoReadContext,
    child_id: UUID,
) -> None:
    if context.organization_wide:
        return
    candidates = list(
        session.execute(
            select(Enrollment, Facility)
            .join(
                Child,
                and_(
                    Child.organization_id == Enrollment.organization_id,
                    Child.id == Enrollment.child_id,
                ),
            )
            .join(
                Facility,
                and_(
                    Facility.organization_id == Enrollment.organization_id,
                    Facility.id == Enrollment.facility_id,
                ),
            )
            .join(
                Room,
                and_(
                    Room.organization_id == Enrollment.organization_id,
                    Room.id == Enrollment.room_id,
                    Room.facility_id == Enrollment.facility_id,
                ),
            )
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.child_id == child_id,
                Enrollment.status == "active",
                Child.is_active.is_(True),
                Facility.status == "active",
                Facility.id.in_(context.assigned_facility_ids),
                Room.is_active.is_(True),
                Enrollment.room_id.in_(context.assigned_room_ids),
            )
        )
    )
    now = datetime.now(UTC)
    for enrollment, facility in candidates:
        try:
            today = now.astimezone(ZoneInfo(facility.timezone)).date()
        except ZoneInfoNotFoundError:
            continue
        if (
            enrollment.start_date <= today
            and (
                enrollment.placement_effective_date is not None
                and enrollment.placement_effective_date <= today
            )
            and (enrollment.end_date is None or enrollment.end_date >= today)
        ):
            return
    # Do not reveal whether a child exists outside the educator's room scope.
    raise HTTPException(status_code=404, detail="Child not found")


def _profile_photo_response(photo: ChildProfilePhoto) -> ChildProfilePhotoResponse:
    return ChildProfilePhotoResponse(
        child_id=photo.child_id,
        url=_profile_photo_url(photo.child_id),
        content_type=photo.content_type,
        size_bytes=photo.size_bytes,
        width=photo.width,
        height=photo.height,
        sha256=photo.sha256,
        original_filename=photo.original_filename,
        updated_at=photo.updated_at,
    )


def _enrollment(
    session: SessionDependency, organization_id: UUID, enrollment_id: UUID
) -> Enrollment:
    value = session.scalar(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == organization_id,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return value


def _validate_enrollment_placement(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    program_id: UUID,
    room_id: UUID,
    *,
    lock: bool,
) -> tuple[Program, Room]:
    facility_statement = select(Facility).where(
        Facility.id == facility_id,
        Facility.organization_id == organization_id,
    )
    if lock:
        facility_statement = facility_statement.with_for_update()
    facility = session.scalar(facility_statement)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.status != "active":
        raise HTTPException(
            status_code=422,
            detail="Children can only be placed in an active facility",
        )

    program = session.scalar(
        select(Program).where(
            Program.id == program_id,
            Program.organization_id == organization_id,
            Program.facility_id == facility_id,
        )
    )
    if program is None:
        raise HTTPException(status_code=409, detail="Program does not belong to facility")
    if not program.is_active or program.program_type not in PROGRAM_TYPES:
        raise HTTPException(status_code=422, detail="Selected program is not active")

    room_statement = select(Room).where(
        Room.id == room_id,
        Room.organization_id == organization_id,
        Room.facility_id == facility_id,
    )
    if lock:
        room_statement = room_statement.with_for_update()
    room = session.scalar(room_statement)
    if room is None:
        raise HTTPException(status_code=409, detail="Room does not belong to facility")
    if not room.is_active:
        raise HTTPException(status_code=422, detail="Selected room is not active")
    if room.program_id != program.id:
        raise HTTPException(status_code=409, detail="Room does not belong to selected program")
    return program, room


def _room_occupancy(
    session: SessionDependency,
    organization_id: UUID,
    room_id: UUID,
    effective_date: date,
    *,
    exclude_enrollment_id: UUID | None = None,
) -> int:
    statement = (
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.room_id == room_id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            Enrollment.start_date <= effective_date,
            Enrollment.placement_effective_date <= effective_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= effective_date),
        )
    )
    if exclude_enrollment_id is not None:
        statement = statement.where(Enrollment.id != exclude_enrollment_id)
    return int(session.scalar(statement) or 0)


def _ensure_room_has_space(
    session: SessionDependency,
    organization_id: UUID,
    room: Room,
    effective_date: date,
    *,
    exclude_enrollment_id: UUID | None = None,
) -> None:
    occupancy = _room_occupancy(
        session,
        organization_id,
        room.id,
        effective_date,
        exclude_enrollment_id=exclude_enrollment_id,
    )
    if occupancy >= room.capacity:
        raise HTTPException(
            status_code=422,
            detail="Target room has reached its enrollment capacity",
        )


def _create_enrollment(
    session: SessionDependency,
    organization_id: UUID,
    child_id: UUID,
    payload: EnrollmentInput,
) -> Enrollment:
    snapshot = session.scalar(
        select(Child).where(
            Child.id == child_id,
            Child.organization_id == organization_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Child not found")
    family = session.scalar(
        select(Family)
        .where(
            Family.id == snapshot.family_id,
            Family.organization_id == organization_id,
        )
        .with_for_update()
    )
    child = session.scalar(
        select(Child)
        .where(
            Child.id == child_id,
            Child.organization_id == organization_id,
        )
        .with_for_update()
    )
    if child is None:
        raise HTTPException(status_code=404, detail="Child not found")
    if child.family_id != snapshot.family_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "child_family_changed", "child_id": str(child.id)},
        )
    if family is None or family.status != "active":
        raise HTTPException(
            status_code=409,
            detail={"code": "family_not_enrollable"},
        )
    if not child.is_active:
        raise HTTPException(status_code=422, detail="Inactive children cannot be enrolled")
    facility = session.scalar(
        select(Facility)
        .where(
            Facility.id == payload.facility_id,
            Facility.organization_id == organization_id,
        )
        .with_for_update()
    )
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.status != "active":
        raise HTTPException(status_code=422, detail="Enrollment requires an active facility")
    if payload.start_date < child.date_of_birth:
        raise HTTPException(status_code=422, detail="start_date cannot precede date_of_birth")
    existing = session.scalar(
        select(Enrollment.id).where(
            Enrollment.organization_id == organization_id,
            Enrollment.child_id == child_id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "open_enrollment_exists", "child_id": str(child_id)},
        )
    value = Enrollment(
        id=uuid4(),
        organization_id=organization_id,
        child_id=child_id,
        facility_id=payload.facility_id,
        program_id=None,
        room_id=None,
        placement_effective_date=None,
        start_date=payload.start_date,
        status="pending",
        version=1,
    )
    session.add(value)
    return value


def _enrollment_responses(
    session: SessionDependency,
    child: Child,
) -> list[EnrollmentResponse]:
    rows = session.execute(
        select(
            Enrollment,
            Facility.name,
            Facility.timezone,
            Program.name,
            Program.program_type,
            Room.name,
        )
        .outerjoin(
            Facility,
            and_(
                Facility.organization_id == Enrollment.organization_id,
                Facility.id == Enrollment.facility_id,
            ),
        )
        .outerjoin(
            Program,
            and_(
                Program.organization_id == Enrollment.organization_id,
                Program.id == Enrollment.program_id,
            ),
        )
        .outerjoin(
            Room,
            and_(
                Room.organization_id == Enrollment.organization_id,
                Room.id == Enrollment.room_id,
            ),
        )
        .where(
            Enrollment.organization_id == child.organization_id,
            Enrollment.child_id == child.id,
        )
        .order_by(Enrollment.start_date.desc(), Enrollment.created_at.desc())
    )
    now = datetime.now(UTC)
    return [
        EnrollmentResponse(
            **{
                column.name: getattr(enrollment, column.name)
                for column in Enrollment.__table__.columns
            },
            is_active=(
                enrollment.status == "active"
                and enrollment.program_id is not None
                and enrollment.room_id is not None
                and enrollment.placement_effective_date is not None
                and enrollment.start_date <= now.astimezone(ZoneInfo(facility_timezone)).date()
                and enrollment.placement_effective_date
                <= now.astimezone(ZoneInfo(facility_timezone)).date()
                and (
                    enrollment.end_date is None
                    or enrollment.end_date >= now.astimezone(ZoneInfo(facility_timezone)).date()
                )
            ),
            facility_name=facility_name,
            program_name=program_name,
            program_type=program_type,
            room_name=room_name,
        )
        for (
            enrollment,
            facility_name,
            facility_timezone,
            program_name,
            program_type,
            room_name,
        ) in rows
    ]


def _enrollment_response(
    session: SessionDependency,
    enrollment: Enrollment,
    *,
    replayed: bool = False,
) -> EnrollmentResponse:
    child = _child(session, enrollment.organization_id, enrollment.child_id)
    response = next(
        item for item in _enrollment_responses(session, child) if item.id == enrollment.id
    )
    return response.model_copy(update={"replayed": replayed})


def _child_response(
    session: SessionDependency,
    child: Child,
    *,
    family_name: str | None = None,
    replayed: bool = False,
) -> ChildResponse:
    if family_name is None:
        family_name = session.scalar(
            select(Family.name).where(
                Family.organization_id == child.organization_id,
                Family.id == child.family_id,
            )
        )
    photo_updated_at = session.scalar(
        select(ChildProfilePhoto.updated_at).where(
            ChildProfilePhoto.organization_id == child.organization_id,
            ChildProfilePhoto.child_id == child.id,
        )
    )
    return ChildResponse(
        **{column.name: getattr(child, column.name) for column in Child.__table__.columns},
        family_name=family_name,
        profile_photo_url=_profile_photo_url(child.id) if photo_updated_at else None,
        profile_photo_updated_at=photo_updated_at,
        enrollments=_enrollment_responses(session, child),
        replayed=replayed,
    )


def _family_care_network(
    session: SessionDependency,
    family: Family,
) -> tuple[list[GuardianResponse], list[EmergencyContactResponse]]:
    guardians = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == family.organization_id,
                Guardian.family_id == family.id,
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.is_primary.desc(), Guardian.created_at)
        )
    )
    contacts = list(
        session.scalars(
            select(EmergencyContact)
            .where(
                EmergencyContact.organization_id == family.organization_id,
                EmergencyContact.family_id == family.id,
                EmergencyContact.retired_at.is_(None),
            )
            .order_by(EmergencyContact.created_at)
        )
    )
    return (
        [GuardianResponse.model_validate(item) for item in guardians],
        [EmergencyContactResponse.model_validate(item) for item in contacts],
    )


def _child_profile_response(
    session: SessionDependency,
    child: Child,
) -> ChildProfileResponse:
    family = _family(session, child.organization_id, child.family_id)
    guardians, contacts = _family_care_network(session, family)
    response = _child_response(session, child, family_name=family.name)
    current_enrollment = next(
        (item for item in response.enrollments if item.is_active),
        None,
    )
    return ChildProfileResponse(
        **response.model_dump(),
        family=ChildFamilyProfileResponse(
            id=family.id,
            organization_id=family.organization_id,
            name=family.name,
            file_number=family.file_number,
            status=family.status,
            version=family.version,
            additional_notes=family.additional_notes,
            photo_consent=family.photo_consent,
            field_trip_consent=family.field_trip_consent,
            emergency_medical_consent=family.emergency_medical_consent,
            guardians=guardians,
            emergency_contacts=contacts,
        ),
        current_enrollment=current_enrollment,
    )


def _family_response(
    session: SessionDependency,
    family: Family,
    *,
    replayed: bool = False,
) -> FamilyResponse:
    guardians, contacts = _family_care_network(session, family)
    children = list(
        session.scalars(
            select(Child)
            .where(
                Child.organization_id == family.organization_id,
                Child.family_id == family.id,
            )
            .order_by(Child.last_name, Child.first_name)
        )
    )
    return FamilyResponse(
        **{column.name: getattr(family, column.name) for column in Family.__table__.columns},
        guardians=guardians,
        emergency_contacts=contacts,
        children=[_child_response(session, item, family_name=family.name) for item in children],
        replayed=replayed,
    )


def _replace_guardian_section(
    session: SessionDependency,
    organization_id: UUID,
    family_id: UUID,
    payload: GuardianInput | None,
    *,
    is_primary: bool,
    operation_id: UUID,
    occurred_at: datetime,
) -> None:
    existing = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == organization_id,
                Guardian.family_id == family_id,
                Guardian.is_primary.is_(is_primary),
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.created_at, Guardian.id)
            .with_for_update()
        )
    )
    for guardian in existing:
        guardian.retired_at = occurred_at
        guardian.retired_operation_id = operation_id
    if existing:
        session.flush()
    if payload is None:
        return

    values = cleaned_values(payload.model_dump())
    session.add(
        Guardian(
            id=uuid4(),
            organization_id=organization_id,
            family_id=family_id,
            is_primary=is_primary,
            created_operation_id=operation_id,
            **values,
        )
    )


def _replace_emergency_contacts(
    session: SessionDependency,
    organization_id: UUID,
    family_id: UUID,
    payload: list[EmergencyContactInput] | None,
    *,
    operation_id: UUID,
    occurred_at: datetime,
) -> None:
    existing = list(
        session.scalars(
            select(EmergencyContact)
            .where(
                EmergencyContact.organization_id == organization_id,
                EmergencyContact.family_id == family_id,
                EmergencyContact.retired_at.is_(None),
            )
            .with_for_update()
        )
    )
    for contact in existing:
        contact.retired_at = occurred_at
        contact.retired_operation_id = operation_id
    if existing:
        session.flush()
    for item in payload or []:
        session.add(
            EmergencyContact(
                id=uuid4(),
                organization_id=organization_id,
                family_id=family_id,
                created_operation_id=operation_id,
                **cleaned_values(item.model_dump()),
            )
        )


def _roster_child_response(
    enrollment: Enrollment,
    child: Child,
    family_name: str,
    has_profile_photo: bool,
) -> RoomRosterChildResponse:
    return RoomRosterChildResponse(
        child_id=child.id,
        enrollment_id=enrollment.id,
        family_id=child.family_id,
        family_name=family_name,
        first_name=child.first_name,
        middle_name=child.middle_name,
        last_name=child.last_name,
        date_of_birth=child.date_of_birth,
        age_group=child.age_group,
        child_is_active=child.is_active,
        profile_photo_url=_profile_photo_url(child.id) if has_profile_photo else None,
        facility_id=enrollment.facility_id,
        program_id=enrollment.program_id,
        room_id=enrollment.room_id,
        enrollment_status=enrollment.status,
        enrollment_version=enrollment.version,
        start_date=enrollment.start_date,
        placement_effective_date=enrollment.placement_effective_date,
        end_date=enrollment.end_date,
    )


def _current_guardian_search(
    organization_id: UUID,
    pattern: str,
    *,
    primary_only: bool = False,
):
    predicates = [
        Guardian.organization_id == organization_id,
        Guardian.family_id == Family.id,
        Guardian.retired_at.is_(None),
    ]
    if primary_only:
        predicates.append(Guardian.is_primary.is_(True))
    return exists(
        select(1).where(
            *predicates,
            or_(
                Guardian.first_name.ilike(pattern, escape="\\"),
                Guardian.last_name.ilike(pattern, escape="\\"),
                (
                    func.coalesce(Guardian.first_name, "")
                    + " "
                    + func.coalesce(Guardian.last_name, "")
                ).ilike(pattern, escape="\\"),
                Guardian.email.ilike(pattern, escape="\\"),
                Guardian.cell_phone.ilike(pattern, escape="\\"),
                Guardian.home_phone.ilike(pattern, escape="\\"),
                Guardian.work_phone.ilike(pattern, escape="\\"),
            ),
        )
    )


def _literal_search_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _directory_family_filters(
    organization_id: UUID,
    *,
    search: str | None,
    family_status: str | None,
) -> list:
    filters = [Family.organization_id == organization_id]
    if family_status is not None:
        filters.append(Family.status == family_status)
    normalized_search = search.strip() if search else ""
    if not normalized_search:
        return filters
    pattern = _literal_search_pattern(normalized_search)
    child_match = exists(
        select(1).where(
            Child.organization_id == organization_id,
            Child.family_id == Family.id,
            or_(
                Child.first_name.ilike(pattern, escape="\\"),
                Child.middle_name.ilike(pattern, escape="\\"),
                Child.last_name.ilike(pattern, escape="\\"),
                (
                    func.coalesce(Child.first_name, "") + " " + func.coalesce(Child.last_name, "")
                ).ilike(pattern, escape="\\"),
            ),
        )
    )
    emergency_match = exists(
        select(1).where(
            EmergencyContact.organization_id == organization_id,
            EmergencyContact.family_id == Family.id,
            EmergencyContact.retired_at.is_(None),
            or_(
                EmergencyContact.first_name.ilike(pattern, escape="\\"),
                EmergencyContact.last_name.ilike(pattern, escape="\\"),
                EmergencyContact.cell_phone.ilike(pattern, escape="\\"),
                EmergencyContact.home_phone.ilike(pattern, escape="\\"),
            ),
        )
    )
    filters.append(
        or_(
            Family.name.ilike(pattern, escape="\\"),
            Family.file_number.ilike(pattern, escape="\\"),
            _current_guardian_search(organization_id, pattern),
            child_match,
            emergency_match,
        )
    )
    return filters


def _family_option_filters(
    organization_id: UUID,
    *,
    search: str | None,
    family_status: str | None,
) -> list:
    filters = [Family.organization_id == organization_id]
    if family_status is not None:
        filters.append(Family.status == family_status)
    normalized_search = search.strip() if search else ""
    if normalized_search:
        pattern = _literal_search_pattern(normalized_search)
        filters.append(
            or_(
                Family.name.ilike(pattern, escape="\\"),
                Family.file_number.ilike(pattern, escape="\\"),
            )
        )
    return filters


def _family_total(session: SessionDependency, filters: list) -> int:
    return int(session.scalar(select(func.count()).select_from(Family).where(*filters)) or 0)


def _page_families(
    session: SessionDependency,
    filters: list,
    *,
    limit: int,
    offset: int,
) -> list[Family]:
    return list(
        session.scalars(
            select(Family)
            .where(*filters)
            .order_by(func.lower(Family.name), Family.id)
            .limit(limit)
            .offset(offset)
        )
    )


def _current_primary_guardians(
    session: SessionDependency,
    organization_id: UUID,
    family_ids: list[UUID],
) -> dict[UUID, Guardian]:
    if not family_ids:
        return {}
    values = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == organization_id,
                Guardian.family_id.in_(family_ids),
                Guardian.is_primary.is_(True),
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.family_id, Guardian.id)
        )
    )
    return {value.family_id: value for value in values}


def _active_child_previews(
    session: SessionDependency,
    organization_id: UUID,
    family_ids: list[UUID],
) -> tuple[dict[UUID, list[FamilyDirectoryChildPreview]], dict[UUID, int]]:
    if not family_ids:
        return {}, {}
    ranked = (
        select(
            Child.id.label("child_id"),
            Child.family_id.label("family_id"),
            Child.first_name.label("first_name"),
            Child.last_name.label("last_name"),
            Child.age_group.label("age_group"),
            func.row_number()
            .over(
                partition_by=Child.family_id,
                order_by=(func.lower(Child.last_name), func.lower(Child.first_name), Child.id),
            )
            .label("preview_rank"),
            func.count().over(partition_by=Child.family_id).label("active_child_count"),
        )
        .where(
            Child.organization_id == organization_id,
            Child.family_id.in_(family_ids),
            Child.is_active.is_(True),
        )
        .subquery()
    )
    rows = list(
        session.execute(
            select(ranked)
            .where(ranked.c.preview_rank <= 4)
            .order_by(ranked.c.family_id, ranked.c.preview_rank)
        ).mappings()
    )
    previews: dict[UUID, list[FamilyDirectoryChildPreview]] = {}
    counts: dict[UUID, int] = {}
    for row in rows:
        family_id = row["family_id"]
        previews.setdefault(family_id, []).append(
            FamilyDirectoryChildPreview(
                id=row["child_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                age_group=row["age_group"],
            )
        )
        counts[family_id] = int(row["active_child_count"])
    return previews, counts


@router.get("/room-rosters", response_model=RoomRosterWorkspaceResponse)
def get_room_rosters(
    facility_id: UUID,
    context: CareRosterContext,
    session: SessionDependency,
) -> RoomRosterWorkspaceResponse:
    facility = session.scalar(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.organization_id == context.organization.id,
        )
    )
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    if not context.organization_wide and facility.id not in context.assigned_facility_ids:
        raise HTTPException(status_code=404, detail="Facility not found")
    facility_date = _local_today(facility.timezone)

    rooms_statement = select(Room).where(
        Room.organization_id == context.organization.id,
        Room.facility_id == facility.id,
    )
    if not context.organization_wide:
        rooms_statement = rooms_statement.where(Room.id.in_(context.assigned_room_ids))
    rooms = list(session.scalars(rooms_statement.order_by(Room.name, Room.id)))
    roster_by_room = {
        room.id: RoomRosterResponse(
            room_id=room.id,
            facility_id=room.facility_id,
            program_id=room.program_id,
            name=room.name,
            capacity=room.capacity,
            is_active=room.is_active,
            occupancy=0,
        )
        for room in rooms
    }
    enrollment_statement = (
        select(Enrollment, Child, Family, Program, ChildProfilePhoto.child_id)
        .join(
            Child,
            (Child.organization_id == Enrollment.organization_id)
            & (Child.id == Enrollment.child_id),
        )
        .join(
            Family,
            (Family.organization_id == Child.organization_id) & (Family.id == Child.family_id),
        )
        .outerjoin(
            Program,
            (Program.organization_id == Enrollment.organization_id)
            & (Program.facility_id == Enrollment.facility_id)
            & (Program.id == Enrollment.program_id),
        )
        .outerjoin(
            ChildProfilePhoto,
            (ChildProfilePhoto.organization_id == Child.organization_id)
            & (ChildProfilePhoto.child_id == Child.id),
        )
        .where(
            Enrollment.organization_id == context.organization.id,
            Enrollment.facility_id == facility.id,
            Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        )
    )
    if not context.organization_wide:
        enrollment_statement = enrollment_statement.where(
            Enrollment.room_id.in_(context.assigned_room_ids)
        )
    enrollment_rows = session.execute(
        enrollment_statement.order_by(Child.last_name, Child.first_name, Enrollment.start_date)
    )
    unassigned_children: list[RoomRosterChildResponse] = []
    for enrollment, child, family, program, photo_child_id in enrollment_rows:
        roster_child = _roster_child_response(
            enrollment,
            child,
            family.name,
            photo_child_id is not None,
        )
        room_roster = roster_by_room.get(enrollment.room_id)
        base_operational = (
            facility.status == "active"
            and family.status == "active"
            and child.is_active
            and (enrollment.end_date is None or enrollment.end_date >= facility_date)
        )
        if (
            base_operational
            and enrollment.room_id is None
            and enrollment.program_id is None
            and enrollment.placement_effective_date is None
        ):
            unassigned_children.append(roster_child)
            continue
        placement_coherent = (
            base_operational
            and room_roster is not None
            and room_roster.is_active
            and enrollment.program_id is not None
            and enrollment.placement_effective_date is not None
            and program is not None
            and program.is_active
            and program.facility_id == facility.id
            and room_roster.program_id == program.id
        )
        if not placement_coherent or room_roster is None:
            continue
        is_current = (
            enrollment.status == "active"
            and enrollment.start_date <= facility_date
            and enrollment.placement_effective_date <= facility_date
        )
        if is_current:
            room_roster.children.append(roster_child)
            room_roster.occupancy += 1
        elif (
            enrollment.status == "paused"
            or enrollment.start_date > facility_date
            or enrollment.placement_effective_date > facility_date
        ):
            room_roster.reserved_children.append(roster_child)

    return RoomRosterWorkspaceResponse(
        facility_id=facility.id,
        facility_date=facility_date,
        rooms=[roster_by_room[room.id] for room in rooms],
        unassigned_children=unassigned_children,
    )


@router.get("/families/directory", response_model=FamilyDirectoryPage)
def family_directory(
    context: ChildcareReadContext,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    family_status: Literal["pending", "active", "inactive", "archived"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=50, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> FamilyDirectoryPage:
    organization_id = context.organization.id
    filters = _directory_family_filters(
        organization_id,
        search=search,
        family_status=family_status,
    )
    total = _family_total(session, filters)
    families = _page_families(session, filters, limit=limit, offset=offset)
    family_ids = [family.id for family in families]
    primary_guardians = _current_primary_guardians(session, organization_id, family_ids)
    child_previews, child_counts = _active_child_previews(
        session,
        organization_id,
        family_ids,
    )
    items: list[FamilyDirectoryItem] = []
    for family in families:
        guardian = primary_guardians.get(family.id)
        primary_contact = (
            FamilyDirectoryPrimaryContact(
                id=guardian.id,
                first_name=guardian.first_name,
                last_name=guardian.last_name,
                email=guardian.email,
                cell_phone=guardian.cell_phone,
            )
            if guardian is not None
            else None
        )
        items.append(
            FamilyDirectoryItem(
                id=family.id,
                organization_id=family.organization_id,
                name=family.name,
                file_number=family.file_number,
                status=family.status,
                version=family.version,
                created_at=family.created_at,
                updated_at=family.updated_at,
                primary_contact=primary_contact,
                active_children=child_previews.get(family.id, []),
                active_child_count=child_counts.get(family.id, 0),
            )
        )
    return FamilyDirectoryPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/families/options", response_model=FamilyOptionsPage)
def family_options(
    context: ChildcareReadContext,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    family_status: Literal["pending", "active", "inactive", "archived"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> FamilyOptionsPage:
    filters = _family_option_filters(
        context.organization.id,
        search=search,
        family_status=family_status,
    )
    total = _family_total(session, filters)
    families = _page_families(session, filters, limit=limit, offset=offset)
    return FamilyOptionsPage(
        items=[
            FamilyOption(
                id=family.id,
                organization_id=family.organization_id,
                name=family.name,
                status=family.status,
            )
            for family in families
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/families/billing-options", response_model=FamilyBillingOptionsPage)
def family_billing_options(
    context: ChildcareReadContext,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    family_status: Literal["pending", "active", "inactive", "archived"] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> FamilyBillingOptionsPage:
    organization_id = context.organization.id
    filters = _family_option_filters(
        organization_id,
        search=search,
        family_status=family_status,
    )
    normalized_search = search.strip() if search else ""
    if normalized_search:
        # Billing selection also finds a family by its current primary payer.
        filters[-1] = or_(
            filters[-1],
            _current_guardian_search(
                organization_id,
                _literal_search_pattern(normalized_search),
                primary_only=True,
            ),
        )
    total = _family_total(session, filters)
    families = _page_families(session, filters, limit=limit, offset=offset)
    family_ids = [family.id for family in families]
    guardians = _current_primary_guardians(session, organization_id, family_ids)
    items: list[FamilyBillingOption] = []
    for family in families:
        guardian = guardians.get(family.id)
        payer = (
            FamilyBillingGuardian(
                id=guardian.id,
                first_name=guardian.first_name,
                last_name=guardian.last_name,
                guardian_type="primary",
                email=guardian.email,
                address=guardian.address,
                city=guardian.city,
                postal_code=guardian.postal_code,
            )
            if guardian is not None
            else None
        )
        items.append(
            FamilyBillingOption(
                id=family.id,
                organization_id=family.organization_id,
                name=family.name,
                status=family.status,
                guardians=[payer] if payer is not None else [],
            )
        )
    return FamilyBillingOptionsPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/families", response_model=FamilyResponse, status_code=status.HTTP_201_CREATED)
def create_family(
    payload: FamilyCreate,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> FamilyResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="family.create",
        target_type="family",
        target_scope="create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _family_response(
            session,
            _family(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    family = Family(
        id=uuid4(),
        organization_id=context.organization.id,
        name=payload.name.strip(),
        file_number=payload.file_number.strip() if payload.file_number else None,
        status=payload.status,
        additional_notes=payload.additional_notes,
        version=1,
        **payload.consents.model_dump(),
    )
    session.add(family)
    flush_or_conflict(session, "Family file number already exists")
    if payload.primary_guardian is not None:
        session.add(
            Guardian(
                id=uuid4(),
                organization_id=context.organization.id,
                family_id=family.id,
                is_primary=True,
                created_operation_id=payload.client_operation_id,
                **cleaned_values(payload.primary_guardian.model_dump()),
            )
        )
    if payload.secondary_guardian is not None:
        session.add(
            Guardian(
                id=uuid4(),
                organization_id=context.organization.id,
                family_id=family.id,
                is_primary=False,
                created_operation_id=payload.client_operation_id,
                **cleaned_values(payload.secondary_guardian.model_dump()),
            )
        )
    for item in payload.emergency_contacts:
        session.add(
            EmergencyContact(
                id=uuid4(),
                organization_id=context.organization.id,
                family_id=family.id,
                created_operation_id=payload.client_operation_id,
                **cleaned_values(item.model_dump()),
            )
        )
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="family.create",
        target_type="family",
        target_id=family.id,
        request_hash=request_hash,
        committed_version=family.version,
        outcome={"action_route": f"/families/{family.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="family.created",
        entity_type="family",
        entity_id=family.id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    commit_in_context(session, context, "Family file number already exists")
    return _family_response(session, family)


@router.get("/families/stats", response_model=FamilyStatsResponse)
def family_stats(
    context: ChildcareReadContext,
    session: SessionDependency,
) -> FamilyStatsResponse:
    organization_id = context.organization.id
    family_count = (
        session.scalar(
            select(func.count())
            .select_from(Family)
            .where(Family.organization_id == organization_id)
        )
        or 0
    )
    active_families = (
        session.scalar(
            select(func.count())
            .select_from(Family)
            .where(Family.organization_id == organization_id, Family.status == "active")
        )
        or 0
    )
    pending = (
        session.scalar(
            select(func.count())
            .select_from(Family)
            .where(Family.organization_id == organization_id, Family.status == "pending")
        )
        or 0
    )
    children = (
        session.scalar(
            select(func.count()).select_from(Child).where(Child.organization_id == organization_id)
        )
        or 0
    )
    active_children = (
        session.scalar(
            select(func.count())
            .select_from(Child)
            .where(Child.organization_id == organization_id, Child.is_active.is_(True))
        )
        or 0
    )
    age_rows = session.execute(
        select(Child.age_group, func.count())
        .where(Child.organization_id == organization_id, Child.is_active.is_(True))
        .group_by(Child.age_group)
    )
    return FamilyStatsResponse(
        families=family_count,
        active_families=active_families,
        children=children,
        active_children=active_children,
        pending_families=pending,
        by_age_group={str(group or "Unspecified"): count for group, count in age_rows},
    )


@router.get("/families/{family_id}", response_model=FamilyResponse)
def get_family(
    family_id: UUID,
    context: ChildcareReadContext,
    session: SessionDependency,
) -> FamilyResponse:
    return _family_response(session, _family(session, context.organization.id, family_id))


@router.patch("/families/{family_id}", response_model=FamilyResponse)
def patch_family(
    family_id: UUID,
    payload: FamilyPatch,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> FamilyResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="family.update",
        target_type="family",
        target_scope=family_id,
        intent=payload.model_dump(exclude={"client_operation_id"}, exclude_unset=True),
    )
    if receipt is not None:
        return _family_response(
            session,
            _family(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    family = _family(session, context.organization.id, family_id)
    session.refresh(family, with_for_update=True)
    require_version(family, payload.expected_version, "family")
    values = payload.model_dump(
        exclude_unset=True,
        exclude={"client_operation_id", "expected_version"},
    )
    consents = values.pop("consents", None)
    values = cleaned_values(values)
    requested_status = values.get("status")
    if (
        requested_status in {"pending", "inactive", "archived"}
        and requested_status != family.status
    ):
        active_children = int(
            session.scalar(
                select(func.count())
                .select_from(Child)
                .where(
                    Child.organization_id == context.organization.id,
                    Child.family_id == family.id,
                    Child.is_active.is_(True),
                )
            )
            or 0
        )
        open_enrollments = int(
            session.scalar(
                select(func.count())
                .select_from(Enrollment)
                .join(
                    Child,
                    and_(
                        Child.organization_id == Enrollment.organization_id,
                        Child.id == Enrollment.child_id,
                    ),
                )
                .where(
                    Enrollment.organization_id == context.organization.id,
                    Child.family_id == family.id,
                    Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
                )
            )
            or 0
        )
        if active_children or open_enrollments:
            raise HTTPException(
                409,
                detail={
                    "code": "family_status_blocked",
                    "active_children": active_children,
                    "open_enrollments": open_enrollments,
                },
            )
    for key, value in values.items():
        setattr(family, key, value)
    if consents is not None:
        for key, value in consents.items():
            setattr(family, key, value)
    changed_fields = sorted({*values, *(consents or {})})
    family.version += 1
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="family.update",
        target_type="family",
        target_id=family.id,
        request_hash=request_hash,
        committed_version=family.version,
        outcome={"action_route": f"/families/{family.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="family.updated",
        entity_type="family",
        entity_id=family.id,
        details={
            "changed_fields": changed_fields,
            "operation_id": str(payload.client_operation_id),
        },
    )
    commit_in_context(session, context, "Family conflicts with existing data")
    return _family_response(session, family)


def _replace_guardian_command(
    family_id: UUID,
    payload: GuardianSectionReplace,
    context: ChildcareManageContext,
    session: SessionDependency,
    *,
    is_primary: bool,
) -> FamilyResponse:
    slot = "primary" if is_primary else "secondary"
    command_type = f"family.guardian.{slot}.replace"
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="family",
        target_scope=family_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _family_response(
            session,
            _family(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    family = _family(session, context.organization.id, family_id)
    session.refresh(family, with_for_update=True)
    require_version(family, payload.expected_version, "family")
    family.version += 1
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="family",
        target_id=family.id,
        request_hash=request_hash,
        committed_version=family.version,
        outcome={"action_route": f"/families/{family.id}"},
    )
    # Provenance is enforced by a non-deferrable receipt FK.  Persist the
    # receipt first inside this still-atomic transaction, then retire the old
    # slot before inserting its replacement so the current-slot unique index
    # is never transiently violated.
    session.flush()
    occurred_at = datetime.now(UTC)
    _replace_guardian_section(
        session,
        context.organization.id,
        family.id,
        payload.guardian,
        is_primary=is_primary,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"family.guardian.{slot}.replaced",
        entity_type="family",
        entity_id=family.id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    commit_in_context(session, context, "Family care network conflicts with existing data")
    return _family_response(session, family)


@router.put("/families/{family_id}/guardians/primary", response_model=FamilyResponse)
def replace_primary_guardian(
    family_id: UUID,
    payload: GuardianSectionReplace,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> FamilyResponse:
    ensure_writable(request)
    return _replace_guardian_command(family_id, payload, context, session, is_primary=True)


@router.put("/families/{family_id}/guardians/secondary", response_model=FamilyResponse)
def replace_secondary_guardian(
    family_id: UUID,
    payload: GuardianSectionReplace,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> FamilyResponse:
    ensure_writable(request)
    return _replace_guardian_command(family_id, payload, context, session, is_primary=False)


@router.put("/families/{family_id}/emergency-contacts", response_model=FamilyResponse)
def replace_family_emergency_contacts(
    family_id: UUID,
    payload: EmergencyContactsReplace,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> FamilyResponse:
    ensure_writable(request)
    command_type = "family.emergency_contacts.replace"
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="family",
        target_scope=family_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _family_response(
            session,
            _family(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    family = _family(session, context.organization.id, family_id)
    session.refresh(family, with_for_update=True)
    require_version(family, payload.expected_version, "family")
    family.version += 1
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="family",
        target_id=family.id,
        request_hash=request_hash,
        committed_version=family.version,
        outcome={"action_route": f"/families/{family.id}"},
    )
    session.flush()
    occurred_at = datetime.now(UTC)
    _replace_emergency_contacts(
        session,
        context.organization.id,
        family.id,
        payload.emergency_contacts,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="family.emergency_contacts.replaced",
        entity_type="family",
        entity_id=family.id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    commit_in_context(session, context, "Family care network conflicts with existing data")
    return _family_response(session, family)


def _child_directory_scope(
    session: SessionDependency,
    organization_id: UUID,
    *,
    search: str | None,
    family_id: UUID | None,
):
    facility_dates = {}
    for facility_id, timezone_name in session.execute(
        select(Facility.id, Facility.timezone).where(Facility.organization_id == organization_id)
    ):
        try:
            facility_dates[facility_id] = _local_today(timezone_name)
        except HTTPException:
            facility_dates[facility_id] = None
    facility_date_whens = tuple(
        (Enrollment.facility_id == facility_id, literal(local_date, type_=Date()))
        for facility_id, local_date in facility_dates.items()
        if local_date is not None
    )
    facility_date = (
        case(*facility_date_whens, else_=literal(None, type_=Date()))
        if facility_date_whens
        else literal(None, type_=Date())
    )
    placement_as_of = case(
        (
            and_(
                Enrollment.start_date >= Enrollment.placement_effective_date,
                Enrollment.start_date >= facility_date,
            ),
            Enrollment.start_date,
        ),
        (
            Enrollment.placement_effective_date >= facility_date,
            Enrollment.placement_effective_date,
        ),
        else_=facility_date,
    )
    age_months = (
        (
            cast(extract("year", placement_as_of), Integer)
            - cast(extract("year", Child.date_of_birth), Integer)
        )
        * 12
        + cast(extract("month", placement_as_of), Integer)
        - cast(extract("month", Child.date_of_birth), Integer)
        - case(
            (
                cast(extract("day", placement_as_of), Integer)
                < cast(extract("day", Child.date_of_birth), Integer),
                1,
            ),
            else_=0,
        )
    )
    unassigned = or_(
        Enrollment.id.is_(None),
        and_(
            Enrollment.status == "pending",
            Enrollment.program_id.is_(None),
            Enrollment.room_id.is_(None),
            Enrollment.placement_effective_date.is_(None),
        ),
    )
    coherent = and_(
        Enrollment.id.is_not(None),
        Enrollment.status.in_(("active", "paused")),
        Enrollment.program_id.is_not(None),
        Enrollment.room_id.is_not(None),
        Enrollment.placement_effective_date.is_not(None),
        Family.status == "active",
        Child.is_active.is_(True),
        Facility.status == "active",
        Program.is_active.is_(True),
        Program.program_type.in_(PROGRAM_TYPES),
        Room.is_active.is_(True),
        Room.facility_id == Enrollment.facility_id,
        Room.program_id == Enrollment.program_id,
        Enrollment.start_date >= Child.date_of_birth,
        Enrollment.placement_effective_date >= Enrollment.start_date,
        Room.minimum_age_months.is_not(None),
        Room.maximum_age_months.is_not(None),
        age_months >= Room.minimum_age_months,
        age_months <= Room.maximum_age_months,
        or_(
            Enrollment.end_date.is_(None),
            Enrollment.end_date >= Enrollment.placement_effective_date,
        ),
        or_(Enrollment.end_date.is_(None), Enrollment.end_date >= facility_date),
        facility_date.is_not(None),
    )
    current = and_(
        coherent,
        Enrollment.status == "active",
        Enrollment.start_date <= facility_date,
        Enrollment.placement_effective_date <= facility_date,
        or_(Enrollment.end_date.is_(None), Enrollment.end_date >= facility_date),
    )
    placement_state = case(
        (unassigned, "unassigned"),
        (current, "current"),
        (coherent, "reserved"),
        else_="needs_review",
    )
    care_lane = case(
        (unassigned, "unassigned"),
        (coherent, Program.program_type),
        else_="needs_review",
    )
    statement = (
        select(
            Child.id.label("child_id"),
            Child.organization_id.label("organization_id"),
            Child.family_id.label("family_id"),
            Family.name.label("family_name"),
            Family.status.label("family_status"),
            Child.first_name.label("first_name"),
            Child.middle_name.label("middle_name"),
            Child.last_name.label("last_name"),
            Child.date_of_birth.label("date_of_birth"),
            Child.age_group.label("age_group"),
            Child.is_active.label("child_is_active"),
            Child.version.label("child_version"),
            Child.created_at.label("child_created_at"),
            Child.updated_at.label("child_updated_at"),
            ChildProfilePhoto.child_id.label("photo_child_id"),
            ChildProfilePhoto.updated_at.label("profile_photo_updated_at"),
            Enrollment.id.label("enrollment_id"),
            Enrollment.facility_id.label("facility_id"),
            Enrollment.program_id.label("program_id"),
            Enrollment.room_id.label("room_id"),
            Enrollment.placement_effective_date.label("placement_effective_date"),
            Enrollment.start_date.label("enrollment_start_date"),
            Enrollment.end_date.label("enrollment_end_date"),
            Enrollment.status.label("enrollment_status"),
            Enrollment.version.label("enrollment_version"),
            Facility.name.label("facility_name"),
            Facility.status.label("facility_status"),
            Facility.timezone.label("facility_timezone"),
            Program.name.label("program_name"),
            Program.program_type.label("program_type"),
            Program.is_active.label("program_is_active"),
            Room.name.label("room_name"),
            Room.is_active.label("room_is_active"),
            Room.facility_id.label("room_facility_id"),
            Room.program_id.label("room_program_id"),
            Room.minimum_age_months.label("room_minimum_age_months"),
            Room.maximum_age_months.label("room_maximum_age_months"),
            placement_state.label("placement_state"),
            care_lane.label("care_lane"),
            func.count(Enrollment.id).over(partition_by=Child.id).label("open_enrollment_count"),
        )
        .join(
            Family,
            and_(
                Family.organization_id == Child.organization_id,
                Family.id == Child.family_id,
            ),
        )
        .outerjoin(
            Enrollment,
            and_(
                Enrollment.organization_id == Child.organization_id,
                Enrollment.child_id == Child.id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            ),
        )
        .outerjoin(
            Facility,
            and_(
                Facility.organization_id == Enrollment.organization_id,
                Facility.id == Enrollment.facility_id,
            ),
        )
        .outerjoin(
            Program,
            and_(
                Program.organization_id == Enrollment.organization_id,
                Program.facility_id == Enrollment.facility_id,
                Program.id == Enrollment.program_id,
            ),
        )
        .outerjoin(
            Room,
            and_(
                Room.organization_id == Enrollment.organization_id,
                Room.facility_id == Enrollment.facility_id,
                Room.id == Enrollment.room_id,
            ),
        )
        .outerjoin(
            ChildProfilePhoto,
            and_(
                ChildProfilePhoto.organization_id == Child.organization_id,
                ChildProfilePhoto.child_id == Child.id,
            ),
        )
        .where(Child.organization_id == organization_id)
    )
    if family_id is not None:
        statement = statement.where(Child.family_id == family_id)
    normalized_search = search.strip() if search else ""
    if normalized_search:
        pattern = _literal_search_pattern(normalized_search)
        statement = statement.where(
            or_(
                Child.first_name.ilike(pattern, escape="\\"),
                Child.middle_name.ilike(pattern, escape="\\"),
                Child.last_name.ilike(pattern, escape="\\"),
                (
                    func.coalesce(Child.first_name, "") + " " + func.coalesce(Child.last_name, "")
                ).ilike(pattern, escape="\\"),
                Family.name.ilike(pattern, escape="\\"),
                Family.file_number.ilike(pattern, escape="\\"),
            )
        )
    return statement.subquery()


def _child_directory_item(row, placement_state: str, care_lane: str) -> ChildDirectoryItem:
    open_enrollment = None
    if row["enrollment_id"] is not None:
        open_enrollment = ChildDirectoryOpenEnrollment(
            id=row["enrollment_id"],
            organization_id=row["organization_id"],
            child_id=row["child_id"],
            facility_id=row["facility_id"],
            facility_name=row["facility_name"],
            program_id=row["program_id"],
            program_name=row["program_name"],
            program_type=row["program_type"],
            room_id=row["room_id"],
            room_name=row["room_name"],
            placement_effective_date=row["placement_effective_date"],
            start_date=row["enrollment_start_date"],
            end_date=row["enrollment_end_date"],
            status=row["enrollment_status"],
            version=row["enrollment_version"],
            placement_state=placement_state,
        )
    return ChildDirectoryItem(
        id=row["child_id"],
        organization_id=row["organization_id"],
        family_id=row["family_id"],
        family_name=row["family_name"],
        first_name=row["first_name"],
        middle_name=row["middle_name"],
        last_name=row["last_name"],
        date_of_birth=row["date_of_birth"],
        age_group=row["age_group"],
        is_active=row["child_is_active"],
        version=row["child_version"],
        profile_photo_url=(
            _profile_photo_url(row["child_id"]) if row["photo_child_id"] is not None else None
        ),
        profile_photo_updated_at=row["profile_photo_updated_at"],
        created_at=row["child_created_at"],
        updated_at=row["child_updated_at"],
        care_lane=care_lane,
        open_enrollment=open_enrollment,
    )


@router.get("/children/directory", response_model=ChildDirectoryPage)
def child_directory(
    context: ChildcareReadContext,
    session: SessionDependency,
    search: str = Query(default="", max_length=200),
    child_status: Literal["all", "active", "inactive"] = Query(default="all", alias="status"),
    care_lane: Literal[
        "all",
        "daycare",
        "out_of_school_care",
        "unassigned",
        "needs_review",
    ] = "all",
    family_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChildDirectoryPage:
    scope = _child_directory_scope(
        session,
        context.organization.id,
        search=search,
        family_id=family_id,
    )
    duplicate_open = session.scalar(
        select(scope.c.child_id).where(scope.c.open_enrollment_count > 1).limit(1)
    )
    if duplicate_open is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_open_enrollment",
                "child_id": str(duplicate_open),
            },
        )
    count_row = (
        session.execute(
            select(
                func.count().label("total"),
                func.coalesce(
                    func.sum(case((scope.c.child_is_active.is_(True), 1), else_=0)), 0
                ).label("active"),
                func.coalesce(
                    func.sum(case((scope.c.child_is_active.is_(False), 1), else_=0)), 0
                ).label("inactive"),
                func.coalesce(
                    func.sum(case((scope.c.care_lane == "daycare", 1), else_=0)), 0
                ).label("daycare"),
                func.coalesce(
                    func.sum(case((scope.c.care_lane == "out_of_school_care", 1), else_=0)),
                    0,
                ).label("out_of_school_care"),
                func.coalesce(
                    func.sum(case((scope.c.care_lane == "unassigned", 1), else_=0)), 0
                ).label("unassigned"),
                func.coalesce(
                    func.sum(case((scope.c.placement_state == "reserved", 1), else_=0)),
                    0,
                ).label("reserved"),
                func.coalesce(
                    func.sum(case((scope.c.care_lane == "needs_review", 1), else_=0)),
                    0,
                ).label("needs_review"),
            )
        )
        .mappings()
        .one()
    )
    counts = ChildDirectoryCounts(**{key: int(value) for key, value in count_row.items()})
    filters = []
    if child_status == "active":
        filters.append(scope.c.child_is_active.is_(True))
    elif child_status == "inactive":
        filters.append(scope.c.child_is_active.is_(False))
    if care_lane != "all":
        filters.append(scope.c.care_lane == care_lane)
    total = int(session.scalar(select(func.count()).select_from(scope).where(*filters)) or 0)
    page = list(
        session.execute(
            select(scope)
            .where(*filters)
            .order_by(
                func.lower(scope.c.last_name),
                func.lower(scope.c.first_name),
                scope.c.child_id,
            )
            .limit(limit)
            .offset(offset)
        ).mappings()
    )
    return ChildDirectoryPage(
        items=[
            _child_directory_item(row, row["placement_state"], row["care_lane"]) for row in page
        ],
        total=total,
        limit=limit,
        offset=offset,
        counts=counts,
    )


@router.post("/children", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
def create_child(
    payload: ChildCreate,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> ChildResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="child.create",
        target_type="child",
        target_scope="create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _child_response(
            session,
            _child(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    family = _family(session, context.organization.id, payload.family_id)
    session.refresh(family, with_for_update=True)
    if family.status in {"inactive", "archived"} or (
        payload.is_active and family.status != "active"
    ):
        raise HTTPException(409, detail={"code": "family_not_enrollable"})
    today = _local_today(context.organization.timezone)
    if payload.date_of_birth > today:
        raise HTTPException(status_code=422, detail="date_of_birth cannot be in the future")
    values = payload.model_dump(exclude={"client_operation_id"})
    if not values.get("age_group"):
        values["age_group"] = _age_group(payload.date_of_birth, today=today)
    child = Child(
        id=uuid4(),
        organization_id=context.organization.id,
        version=1,
        **cleaned_values(values),
    )
    session.add(child)
    flush_or_conflict(session, "Child could not be created")
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="child.create",
        target_type="child",
        target_id=child.id,
        request_hash=request_hash,
        committed_version=child.version,
        outcome={"action_route": f"/children/{child.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="child.created",
        entity_type="child",
        entity_id=child.id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    commit_in_context(session, context, "Child conflicts with existing data")
    return _child_response(session, child, family_name=family.name)


@router.get("/children/{child_id}", response_model=ChildProfileResponse)
def get_child(
    child_id: UUID,
    context: ChildcareReadContext,
    session: SessionDependency,
) -> ChildProfileResponse:
    return _child_profile_response(
        session,
        _child(session, context.organization.id, child_id),
    )


@router.put("/children/{child_id}/photo", response_model=ChildProfilePhotoResponse)
def put_child_profile_photo(
    child_id: UUID,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> ChildProfilePhotoResponse:
    ensure_writable(request)
    child = _child(session, context.organization.id, child_id)
    normalized = normalize_profile_photo(file, request.app.state.settings)
    session.refresh(child, with_for_update=True)
    photo = _profile_photo(session, context.organization.id, child.id, lock=True)
    if photo is None:
        photo = ChildProfilePhoto(
            id=uuid4(),
            organization_id=context.organization.id,
            child_id=child.id,
        )
        session.add(photo)
        action = "child.photo.created"
    else:
        action = "child.photo.updated"
    photo.image_bytes = normalized.image_bytes
    photo.content_type = normalized.content_type
    photo.size_bytes = normalized.size_bytes
    photo.width = normalized.width
    photo.height = normalized.height
    photo.sha256 = normalized.sha256
    photo.original_filename = normalized.original_filename
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=action,
        entity_type="child",
        entity_id=child.id,
        details={"content_type": normalized.content_type},
    )
    commit_in_context(session, context, "Child profile photo conflicts with existing data")
    return _profile_photo_response(photo)


@router.get("/children/{child_id}/photo", response_class=Response)
def get_child_profile_photo(
    child_id: UUID,
    request: Request,
    context: ChildPhotoReadContext,
    session: SessionDependency,
) -> Response:
    child = _child(session, context.organization.id, child_id)
    _ensure_photo_read_scope(session, context, child.id)
    photo = _profile_photo(session, context.organization.id, child.id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Child photo not found")
    etag = f'"{photo.sha256}"'
    headers = {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if etag in {value.strip() for value in request.headers.get("if-none-match", "").split(",")}:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=photo.image_bytes, media_type=photo.content_type, headers=headers)


@router.delete("/children/{child_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_child_profile_photo(
    child_id: UUID,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> Response:
    ensure_writable(request)
    child = _child(session, context.organization.id, child_id)
    session.refresh(child, with_for_update=True)
    photo = _profile_photo(session, context.organization.id, child.id, lock=True)
    if photo is None:
        raise HTTPException(status_code=404, detail="Child photo not found")
    session.delete(photo)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="child.photo.deleted",
        entity_type="child",
        entity_id=child.id,
    )
    commit_in_context(session, context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/children/{child_id}", response_model=ChildResponse)
def patch_child(
    child_id: UUID,
    payload: ChildPatch,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> ChildResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="child.update",
        target_type="child",
        target_scope=child_id,
        intent=payload.model_dump(exclude={"client_operation_id"}, exclude_unset=True),
    )
    if receipt is not None:
        return _child_response(
            session,
            _child(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    child_snapshot = _child(session, context.organization.id, child_id)
    if "family_id" in payload.model_fields_set and payload.family_id is None:
        raise HTTPException(status_code=422, detail="family_id cannot be null")
    reparenting = payload.family_id is not None and payload.family_id != child_snapshot.family_id
    activation_family_check = payload.is_active is True
    target_family: Family | None = None
    current_family: Family | None = None
    if reparenting or activation_family_check:
        family_ids = sorted(
            {
                child_snapshot.family_id,
                *({payload.family_id} if reparenting else set()),
            },
            key=str,
        )
        locked_families = {
            family.id: family
            for family in session.scalars(
                select(Family)
                .where(
                    Family.organization_id == context.organization.id,
                    Family.id.in_(family_ids),
                )
                .order_by(Family.id)
                .with_for_update()
            )
        }
        if set(locked_families) != set(family_ids):
            raise HTTPException(status_code=404, detail="Family not found")
        current_family = locked_families[child_snapshot.family_id]
        if reparenting:
            target_family = locked_families[payload.family_id]
        child = session.scalar(
            select(Child)
            .where(
                Child.id == child_id,
                Child.organization_id == context.organization.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        child = session.scalar(
            select(Child)
            .where(
                Child.id == child_id,
                Child.organization_id == context.organization.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if child is None:
        raise HTTPException(status_code=404, detail="Child not found")
    require_version(child, payload.expected_version, "child")
    if reparenting and child.family_id != child_snapshot.family_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "child_family_changed", "child_id": str(child.id)},
        )
    values = cleaned_values(
        payload.model_dump(
            exclude_unset=True,
            exclude={"client_operation_id", "expected_version"},
        )
    )
    if reparenting:
        if target_family is None or target_family.status in {"inactive", "archived"}:
            raise HTTPException(409, detail={"code": "family_not_enrollable"})
        if (child.is_active or payload.is_active is True) and target_family.status != "active":
            raise HTTPException(409, detail={"code": "family_not_enrollable"})
        open_enrollment = session.scalar(
            select(Enrollment.id)
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.child_id == child.id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            )
            .with_for_update()
        )
        if open_enrollment is not None:
            raise HTTPException(
                409,
                detail={
                    "code": "child_reparenting_blocked_open_enrollment",
                    "enrollment_id": str(open_enrollment),
                },
            )
    if payload.is_active is True:
        resulting_family = target_family if reparenting else current_family
        if resulting_family is None:
            raise HTTPException(status_code=404, detail="Family not found")
        if resulting_family.status != "active":
            raise HTTPException(409, detail={"code": "family_not_enrollable"})
    today = _local_today(context.organization.timezone)
    if values.get("date_of_birth") and values["date_of_birth"] > today:
        raise HTTPException(status_code=422, detail="date_of_birth cannot be in the future")
    if values.get("is_active") is False and child.is_active:
        open_enrollment_count = session.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.child_id == child.id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            )
        )
        if open_enrollment_count:
            raise HTTPException(
                status_code=422,
                detail="End the child's open enrollment before deactivating the child",
            )
    if "date_of_birth" in values and values["date_of_birth"] != child.date_of_birth:
        _validate_dob_against_open_placement(
            session,
            context.organization.id,
            child,
            values["date_of_birth"],
        )
    for key, value in values.items():
        setattr(child, key, value)
    if "date_of_birth" in values and "age_group" not in values:
        child.age_group = _age_group(child.date_of_birth, today=today)
    child.version += 1
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="child.update",
        target_type="child",
        target_id=child.id,
        request_hash=request_hash,
        committed_version=child.version,
        outcome={"action_route": f"/children/{child.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="child.updated",
        entity_type="child",
        entity_id=child.id,
        details={
            "changed_fields": sorted(values),
            "operation_id": str(payload.client_operation_id),
        },
    )
    commit_in_context(session, context)
    return _child_response(session, child)


@router.post(
    "/children/{child_id}/enrollments",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment(
    child_id: UUID,
    payload: EnrollmentInput,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> EnrollmentResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.create",
        target_type="enrollment",
        target_scope=child_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _enrollment_response(
            session,
            _enrollment(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    enrollment = _create_enrollment(session, context.organization.id, child_id, payload)
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.create",
        target_type="enrollment",
        target_id=enrollment.id,
        request_hash=request_hash,
        committed_version=enrollment.version,
        facility_id=enrollment.facility_id,
        outcome={"action_route": f"/children/{child_id}?enrollment_id={enrollment.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="enrollment.created",
        entity_type="enrollment",
        entity_id=enrollment.id,
        facility_id=enrollment.facility_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    commit_in_context(session, context, "Enrollment conflicts with existing data")
    return _enrollment_response(session, enrollment)


@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentResponse)
def patch_enrollment(
    enrollment_id: UUID,
    payload: EnrollmentPatch,
    request: Request,
    context: ChildcareManageContext,
    session: SessionDependency,
) -> EnrollmentResponse:
    ensure_writable(request)
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.update",
        target_type="enrollment",
        target_scope=enrollment_id,
        intent=payload.model_dump(exclude={"client_operation_id"}, exclude_unset=True),
    )
    if receipt is not None:
        return _enrollment_response(
            session,
            _enrollment(session, context.organization.id, receipt.target_id),
            replayed=True,
        )
    snapshot = _enrollment(session, context.organization.id, enrollment_id)
    child_snapshot = session.scalar(
        select(Child).where(
            Child.id == snapshot.child_id,
            Child.organization_id == context.organization.id,
        )
    )
    if child_snapshot is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    expected_family_id = child_snapshot.family_id
    family = session.scalar(
        select(Family)
        .where(
            Family.id == expected_family_id,
            Family.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    child = session.scalar(
        select(Child)
        .where(
            Child.id == snapshot.child_id,
            Child.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    facility = session.scalar(
        select(Facility)
        .where(
            Facility.id == snapshot.facility_id,
            Facility.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == context.organization.id,
        )
        .with_for_update()
    )
    if child is None or enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if family is None:
        raise HTTPException(status_code=404, detail="Family not found")
    if child.family_id != expected_family_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "child_family_changed", "child_id": str(child.id)},
        )
    if enrollment.child_id != child.id:
        raise HTTPException(status_code=409, detail={"code": "enrollment_child_changed"})
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    require_version(enrollment, payload.expected_version, "enrollment")
    values = payload.model_dump(
        exclude_unset=True,
        exclude={"client_operation_id", "expected_version"},
    )
    resulting_status = values.get("status", enrollment.status)
    resulting_end_date = values.get("end_date", enrollment.end_date)
    if "end_date" in values and values["end_date"] is not None and "status" not in values:
        resulting_status = "ended"
    transitions = {
        "pending": {"pending", "ended"},
        "active": {"active", "paused", "ended"},
        "paused": {"paused", "active", "ended"},
        "ended": {"ended"},
    }
    if resulting_status not in transitions[enrollment.status]:
        raise HTTPException(
            409,
            detail={
                "code": "invalid_enrollment_transition",
                "from_status": enrollment.status,
                "to_status": resulting_status,
            },
        )
    if resulting_status in OPEN_ENROLLMENT_STATUSES and family.status != "active":
        raise HTTPException(status_code=409, detail={"code": "family_not_enrollable"})
    if resulting_status in {"active", "paused"} and (
        enrollment.program_id is None
        or enrollment.room_id is None
        or enrollment.placement_effective_date is None
    ):
        raise HTTPException(409, detail={"code": "unassigned_enrollment_cannot_activate"})
    if resulting_status == "ended" and resulting_end_date is None:
        resulting_end_date = _local_today(facility.timezone)
        values["end_date"] = resulting_end_date
    if resulting_end_date is not None and resulting_status != "ended":
        raise HTTPException(
            status_code=422,
            detail={"code": "end_date_requires_ended_status"},
        )
    if (
        resulting_status == "ended"
        and resulting_end_date is not None
        and resulting_end_date > _local_today(facility.timezone)
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "future_end_requires_scheduled_departure_workflow"},
        )
    if resulting_end_date is not None and resulting_end_date < enrollment.start_date:
        raise HTTPException(status_code=422, detail="end_date cannot precede start_date")
    if (
        resulting_end_date is not None
        and enrollment.placement_effective_date is not None
        and resulting_end_date < enrollment.placement_effective_date
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "end_date_precedes_placement_effective_date"},
        )
    if resulting_end_date is not None:
        latest_attendance_date = session.scalar(
            select(func.max(AttendanceDay.service_date)).where(
                AttendanceDay.organization_id == context.organization.id,
                AttendanceDay.enrollment_id == enrollment.id,
            )
        )
        if latest_attendance_date is not None and resulting_end_date < latest_attendance_date:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "end_date_precedes_attendance_history",
                    "latest_attendance_date": latest_attendance_date.isoformat(),
                },
            )
    if values:
        open_attendance = session.scalar(
            select(AttendanceInterval.id)
            .join(
                AttendanceDay,
                and_(
                    AttendanceDay.organization_id == AttendanceInterval.organization_id,
                    AttendanceDay.id == AttendanceInterval.attendance_day_id,
                ),
            )
            .where(
                AttendanceInterval.organization_id == context.organization.id,
                AttendanceDay.enrollment_id == enrollment.id,
                AttendanceInterval.checked_out_at.is_(None),
            )
        )
        if open_attendance is not None:
            raise HTTPException(
                status_code=409,
                detail="Check the child out before changing enrollment status",
            )
    values["status"] = resulting_status
    for key, value in values.items():
        setattr(enrollment, key, value)
    enrollment.version += 1
    record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type="enrollment.update",
        target_type="enrollment",
        target_id=enrollment.id,
        request_hash=request_hash,
        committed_version=enrollment.version,
        facility_id=enrollment.facility_id,
        outcome={"action_route": f"/children/{child.id}?enrollment_id={enrollment.id}"},
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="enrollment.updated",
        entity_type="enrollment",
        entity_id=enrollment.id,
        facility_id=enrollment.facility_id,
        details={
            "changed_fields": sorted(values),
            "operation_id": str(payload.client_operation_id),
        },
    )
    commit_in_context(session, context)
    return _enrollment_response(session, enrollment)
