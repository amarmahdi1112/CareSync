"""Current-organization profile and preference workflows."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request, status
from sqlalchemy import select, update

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/organization", tags=["organization"])
organizations = Base.metadata.tables["organizations"]
EDITABLE_FIELDS = {
    "name",
    "organization_type",
    "primary_contact_name",
    "email",
    "phone",
    "street_address",
    "city",
    "province",
    "postal_code",
    "country",
    "license_number",
    "licensed_capacity",
    "opening_time",
    "closing_time",
    "age_groups_served",
    "accreditation_status",
    "programs_offered",
    "timezone",
    "logo_url",
    "website",
    "secondary_contact_name",
    "secondary_contact_phone",
    "secondary_contact_email",
    "business_number",
    "tax_id",
    "insurance_provider",
    "insurance_policy_number",
    "insurance_expiry_date",
    "accreditation_body",
    "accreditation_expiry_date",
    "description",
    "billing_email",
    "social_media",
}


def _organization_id(current_user: CurrentUser):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user is not assigned to an organization",
        )
    return current_user.organization_id


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _parse_json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _current_row(current_user: CurrentUser, session: SessionDependency):
    row = (
        session.execute(
            select(organizations).where(organizations.c.id == _organization_id(current_user))
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return row


def _serialize(row) -> dict:
    result = dict(row)
    result["notification_preferences"] = _parse_json(result["notification_preferences"])
    result["system_preferences"] = _parse_json(result["system_preferences"])
    return result


@router.get("")
def get_current_organization(
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    return _serialize(_current_row(current_user, session))


@router.patch("")
def update_current_organization(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict:
    _ensure_writable(request)
    unknown = set(payload) - EDITABLE_FIELDS
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or protected fields: {', '.join(sorted(unknown))}",
        )
    organization_id = _organization_id(current_user)
    session.execute(
        update(organizations).where(organizations.c.id == organization_id).values(**payload)
    )
    session.commit()
    return _serialize(_current_row(current_user, session))


@router.put("/logo")
async def upload_logo(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    _ensure_writable(request)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    if content_type not in extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported logo format"
        )
    content = await request.body()
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Logo must be between 1 byte and 5 MB",
        )
    organization_id = _organization_id(current_user)
    uploads = request.app.state.settings.database_path.parent / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    for existing in uploads.glob(f"organization-{organization_id}.*"):
        existing.unlink(missing_ok=True)
    filename = f"organization-{organization_id}{extensions[content_type]}"
    (uploads / filename).write_bytes(content)
    logo_url = f"/uploads/{filename}"
    session.execute(
        update(organizations).where(organizations.c.id == organization_id).values(logo_url=logo_url)
    )
    session.commit()
    return _serialize(_current_row(current_user, session))


@router.delete("/logo")
def remove_logo(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    _ensure_writable(request)
    organization_id = _organization_id(current_user)
    uploads = request.app.state.settings.database_path.parent / "uploads"
    for existing in uploads.glob(f"organization-{organization_id}.*"):
        existing.unlink(missing_ok=True)
    session.execute(
        update(organizations).where(organizations.c.id == organization_id).values(logo_url=None)
    )
    session.commit()
    return _serialize(_current_row(current_user, session))


@router.patch("/preferences/{preference_type}")
def update_preferences(
    preference_type: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict:
    _ensure_writable(request)
    if preference_type not in {"notification", "system"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown preference type",
        )
    column_name = f"{preference_type}_preferences"
    organization_id = _organization_id(current_user)
    existing = _parse_json(_current_row(current_user, session)[column_name])
    existing.update(payload)
    session.execute(
        update(organizations)
        .where(organizations.c.id == organization_id)
        .values({column_name: json.dumps(existing)})
    )
    session.commit()
    return {column_name: existing}
