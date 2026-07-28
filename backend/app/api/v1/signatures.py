"""Signature workflows that intentionally include the binary image payload."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Request, status
from sqlalchemy import insert, or_, select

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/signatures", tags=["signatures"])
tables = Base.metadata.tables


def _organization_id(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    return current_user.organization_id


@router.get("")
def list_signatures(current_user: CurrentUser, session: SessionDependency) -> list[dict]:
    signatures = tables["signatures"]
    guardians = tables["guardians"]
    families = tables["families"]
    statement = (
        select(
            signatures,
            guardians.c.first_name.label("guardian_first_name"),
            guardians.c.last_name.label("guardian_last_name"),
        )
        .select_from(signatures.outerjoin(guardians, signatures.c.guardian_id == guardians.c.id))
        .outerjoin(families, guardians.c.family_id == families.c.id)
        .where(
            signatures.c.is_active.is_(True),
            or_(
                families.c.organization_id == _organization_id(current_user),
                signatures.c.guardian_id.is_(None),
            ),
        )
        .order_by(signatures.c.created_at.desc())
    )
    result = []
    for row in session.execute(statement).mappings():
        item = dict(row)
        if item["guardian_id"]:
            item["guardian"] = {
                "id": item["guardian_id"],
                "first_name": item.pop("guardian_first_name"),
                "last_name": item.pop("guardian_last_name"),
            }
        else:
            item["guardian"] = None
            item.pop("guardian_first_name", None)
            item.pop("guardian_last_name", None)
        result.append(item)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_signature(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict, Body()],
) -> dict:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )
    image_data = payload.get("image_data")
    if not image_data or not isinstance(image_data, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_data is required",
        )
    guardian_id = payload.get("guardian_id")
    if guardian_id:
        guardians = tables["guardians"]
        families = tables["families"]
        allowed = session.scalar(
            select(guardians.c.id)
            .join(families, guardians.c.family_id == families.c.id)
            .where(
                guardians.c.id == UUID(guardian_id),
                families.c.organization_id == _organization_id(current_user),
            )
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardian not found")
    signatures = tables["signatures"]
    row = (
        session.execute(
            insert(signatures)
            .values(
                id=uuid4(),
                guardian_id=UUID(guardian_id) if guardian_id else None,
                image_data=image_data,
                label=payload.get("label"),
                is_active=True,
            )
            .returning(signatures)
        )
        .mappings()
        .one()
    )
    session.commit()
    return dict(row)
