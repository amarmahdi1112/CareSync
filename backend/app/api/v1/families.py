"""Organization-scoped family reads and transactional registration."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import (
    ActivityLogs,
    Children,
    EmergencyContacts,
    Families,
    Guardians,
)
from app.schemas.family import (
    ChildListResponse,
    FamilyDetailResponse,
    FamilyRegistrationRequest,
    FamilyStatsResponse,
    FamilySummaryResponse,
)

router = APIRouter(tags=["families"])


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _age_group(birth_date: date) -> str:
    today = date.today()
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


def _organization_filter(statement, current_user: CurrentUser, model=Families):
    if current_user.organization_id is not None:
        statement = statement.where(model.organization_id == current_user.organization_id)
    return statement


@router.get("/families", response_model=list[FamilySummaryResponse])
def list_families(
    current_user: CurrentUser,
    session: SessionDependency,
    search: str | None = None,
    family_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Families]:
    statement = _organization_filter(select(Families), current_user)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(Families.name.ilike(pattern), Families.file_number.ilike(pattern))
        )
    if family_status:
        statement = statement.where(Families.status == family_status)
    statement = (
        statement.options(
            selectinload(Families.children),
            selectinload(Families.guardians),
        )
        .order_by(Families.name)
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


@router.post("/families", response_model=FamilyDetailResponse, status_code=status.HTTP_201_CREATED)
def register_family(
    payload: FamilyRegistrationRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> Families:
    _ensure_writable(request)
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    if not payload.children:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one child is required",
        )
    primary = payload.primary_guardian
    family = Families(
        organization_id=current_user.organization_id,
        name=f"{primary.last_name.strip()} Family",
        status="pending",
        photo_consent=payload.consents.photo_consent,
        field_trip_consent=payload.consents.field_trip_consent,
        emergency_medical_consent=payload.consents.emergency_medical_consent,
        additional_notes=payload.additional_notes,
    )
    session.add(family)
    session.flush()

    guardians = [primary]
    if payload.secondary_guardian and payload.secondary_guardian.first_name.strip():
        guardians.append(payload.secondary_guardian)
    for guardian in guardians:
        values = guardian.model_dump(exclude={"relationship"})
        values["relationship_"] = guardian.relationship
        values["email"] = guardian.email.strip().lower()
        session.add(Guardians(family_id=family.id, **values))
    for child in payload.children:
        session.add(
            Children(
                family_id=family.id,
                is_active=True,
                age_group=_age_group(child.date_of_birth),
                **child.model_dump(),
            )
        )
    for contact in payload.emergency_contacts:
        values = contact.model_dump(exclude={"relationship"})
        values["relationship_"] = contact.relationship
        session.add(EmergencyContacts(family_id=family.id, **values))
    session.add(
        ActivityLogs(
            organization_id=current_user.organization_id,
            activity_type="family.created",
            description=(
                f"Registered new family: {family.name} with {len(payload.children)} child(ren)"
            ),
            user_id=current_user.id,
            user_name=f"{current_user.first_name} {current_user.last_name}".strip(),
            user_email=current_user.email,
            entity_type="family",
            entity_id=family.id,
            entity_name=family.name,
        )
    )
    session.commit()
    return get_family(family.id, current_user, session)


@router.get("/families/stats", response_model=FamilyStatsResponse)
def family_stats(current_user: CurrentUser, session: SessionDependency) -> FamilyStatsResponse:
    family_base = _organization_filter(select(func.count()).select_from(Families), current_user)
    child_base = select(func.count()).select_from(Children).join(Families)
    child_base = _organization_filter(child_base, current_user)
    age_group_statement = (
        select(Children.age_group, func.count())
        .join(Families)
        .where(Children.is_active.is_(True))
        .group_by(Children.age_group)
    )
    age_group_statement = _organization_filter(age_group_statement, current_user)
    by_age_group = {
        str(age_group or "Unspecified"): count
        for age_group, count in session.execute(age_group_statement)
    }
    return FamilyStatsResponse(
        families=session.scalar(family_base) or 0,
        active_families=session.scalar(family_base.where(Families.status == "active")) or 0,
        children=session.scalar(child_base) or 0,
        active_children=session.scalar(child_base.where(Children.is_active.is_(True))) or 0,
        pending_families=session.scalar(family_base.where(Families.status == "pending")) or 0,
        by_age_group=by_age_group,
    )


@router.get("/families/{family_id}", response_model=FamilyDetailResponse)
def get_family(
    family_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
) -> Families:
    statement = (
        select(Families)
        .where(Families.id == family_id)
        .options(
            selectinload(Families.children),
            selectinload(Families.guardians),
            selectinload(Families.emergency_contacts),
        )
    )
    statement = _organization_filter(statement, current_user)
    family = session.scalar(statement)
    if family is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")
    return family


@router.get("/children", response_model=list[ChildListResponse])
def list_children(
    current_user: CurrentUser,
    session: SessionDependency,
    search: str | None = None,
    active_only: bool = False,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[ChildListResponse]:
    statement = select(Children).join(Families)
    statement = _organization_filter(statement, current_user)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Children.first_name.ilike(pattern),
                Children.middle_name.ilike(pattern),
                Children.last_name.ilike(pattern),
                Children.fscd_file_number.ilike(pattern),
            )
        )
    if active_only:
        statement = statement.where(Children.is_active.is_(True))
    statement = (
        statement.order_by(Children.last_name, Children.first_name).limit(limit).offset(offset)
    )
    children = list(session.scalars(statement))
    family_names = dict(
        session.execute(
            _organization_filter(select(Families.id, Families.name), current_user)
        ).all()
    )
    return [
        ChildListResponse.model_validate(
            {**child.__dict__, "family_name": family_names[child.family_id]}
        )
        for child in children
    ]


@router.get("/children/{child_id}", response_model=None)
def get_child(
    child_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    statement = select(Children).join(Families).where(Children.id == child_id)
    statement = _organization_filter(statement, current_user)
    child = session.scalar(statement)
    if child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child not found")
    return {column.name: getattr(child, column.name) for column in Children.__table__.c}
