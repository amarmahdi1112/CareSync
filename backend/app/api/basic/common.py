"""Shared Basic API safeguards and serialization helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.dependencies import BasicContext
from app.basic.models import OrganizationMembership, Role, User
from app.basic.schemas import PermissionRoleResponse, UserResponse
from app.basic.security import set_rls_organization, set_rls_user


def ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled",
        )


def lock_client_operation(
    session: Session,
    organization_id: UUID,
    client_operation_id: UUID,
) -> None:
    """Serialize concurrent retries of one idempotency key on PostgreSQL."""

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
            {"value": f"{organization_id}:{client_operation_id}"},
        )
        # Receipt RLS may expose another actor's row only for this exact,
        # serialized operation so API code can return a private 404 before
        # any domain work reaches the unique receipt constraint.
        session.execute(
            text(
                "SELECT set_config('app.current_childcare_operation_id', :operation_id, true)"
            ),
            {"operation_id": str(client_operation_id)},
        )


def commit_or_conflict(
    session: Session, detail: str = "Record conflicts with existing data"
) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None


def flush_or_conflict(
    session: Session, detail: str = "Record conflicts with existing data"
) -> None:
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None


def restore_context(session: Session, context: BasicContext) -> None:
    """Restore transaction-local RLS settings after a successful commit."""

    set_rls_user(session, context.user.id)
    set_rls_organization(session, context.organization.id)


def commit_in_context(
    session: Session,
    context: BasicContext,
    detail: str = "Record conflicts with existing data",
) -> None:
    commit_or_conflict(session, detail)
    restore_context(session, context)


def user_response(
    user: User,
    context: BasicContext | None = None,
    *,
    role: Role | None = None,
    membership: OrganizationMembership | None = None,
    organization_id=None,
    assigned_facility_ids=None,
    assigned_room_ids=None,
) -> UserResponse:
    selected_role = role or (context.role if context else None)
    selected_organization_id = organization_id or (context.organization.id if context else None)
    selected_membership = membership or (context.membership if context else None)
    if selected_role is None or selected_organization_id is None or selected_membership is None:
        raise RuntimeError("User response requires an organization role")
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=PermissionRoleResponse(
            id=selected_role.id,
            key=selected_role.key,
            name=selected_role.name,
            description=selected_role.description,
            permissions=list(selected_role.permissions or []),
        ),
        organization_id=selected_organization_id,
        membership_id=selected_membership.id,
        membership_status=selected_membership.status,
        assigned_facility_ids=list(
            assigned_facility_ids
            if assigned_facility_ids is not None
            else (context.assigned_facility_ids if context else [])
        ),
        assigned_room_ids=list(
            assigned_room_ids
            if assigned_room_ids is not None
            else (context.assigned_room_ids if context else [])
        ),
        is_active=user.is_active,
        email_verification_status="verified" if user.email_verified_at is not None else "pending",
        email_verified_at=user.email_verified_at,
        email_verification_method=user.email_verification_method,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def cleaned_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.strip() if isinstance(value, str) else value for key, value in values.items()
    }
