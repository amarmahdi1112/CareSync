"""Fail-closed authentication and active-organization resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.api.dependencies import SessionDependency
from app.basic.models import (
    Facility,
    MarketplaceProfile,
    MembershipRoomAssignment,
    Organization,
    OrganizationMembership,
    Role,
    Room,
    User,
)
from app.basic.security import decode_access_token, set_rls_organization, set_rls_user

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class BasicContext:
    user: User
    organization: Organization
    membership: OrganizationMembership
    role: Role
    assigned_facility_ids: tuple[UUID, ...] = ()
    assigned_room_ids: tuple[UUID, ...] = ()

    @property
    def organization_wide(self) -> bool:
        return self.role.key in {"owner", "administrator"}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_basic_user(
    request: Request,
    session: SessionDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id, auth_version = decode_access_token(
            credentials.credentials, request.app.state.settings
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise _unauthorized() from None
    user = session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise _unauthorized()
    if user.auth_version != auth_version:
        raise _unauthorized()
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    set_rls_user(session, user.id)
    return user


BasicUser = Annotated[User, Depends(get_basic_user)]


def get_complete_marketplace_user(user: BasicUser, session: SessionDependency) -> User:
    from app.basic.candidate_profiles import missing_profile_fields

    profile = session.get(MarketplaceProfile, user.id)
    missing = missing_profile_fields(user, profile)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "profile_incomplete", "missing_profile_fields": missing},
        )
    return user


CompleteMarketplaceUser = Annotated[User, Depends(get_complete_marketplace_user)]


def require_complete_if_marketplace_user(user: BasicUser, session: SessionDependency) -> None:
    from app.basic.candidate_profiles import missing_profile_fields

    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        return
    missing = missing_profile_fields(user, profile)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "profile_incomplete", "missing_profile_fields": missing},
        )


def get_basic_context(
    user: BasicUser,
    session: SessionDependency,
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> BasicContext:
    statement = select(OrganizationMembership).where(
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.status == "active",
    )
    if x_organization_id is not None:
        try:
            selected_id = UUID(x_organization_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid organization context",
            ) from None
        statement = statement.where(OrganizationMembership.organization_id == selected_id)
    memberships = list(session.scalars(statement.order_by(OrganizationMembership.created_at)))
    if not memberships:
        if x_organization_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Active organization membership required",
            )
        raise _unauthorized()
    if x_organization_id is None and len(memberships) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="X-Organization-ID is required when more than one membership is active",
        )
    membership = memberships[0]
    set_rls_organization(session, membership.organization_id)
    organization = session.scalar(
        select(Organization).where(Organization.id == membership.organization_id)
    )
    role = session.scalar(
        select(Role).where(
            Role.id == membership.role_id,
            Role.organization_id == membership.organization_id,
        )
    )
    if organization is None or role is None or organization.status in {"suspended", "archived"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access is unavailable",
        )
    assignment_rows = list(
        session.execute(
            select(MembershipRoomAssignment.facility_id, MembershipRoomAssignment.room_id)
            .join(
                Room,
                (Room.organization_id == MembershipRoomAssignment.organization_id)
                & (Room.id == MembershipRoomAssignment.room_id),
            )
            .join(
                Facility,
                (Facility.organization_id == MembershipRoomAssignment.organization_id)
                & (Facility.id == MembershipRoomAssignment.facility_id),
            )
            .where(
                MembershipRoomAssignment.organization_id == membership.organization_id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
                Room.is_active.is_(True),
                Facility.status == "active",
            )
            .order_by(MembershipRoomAssignment.facility_id, MembershipRoomAssignment.room_id)
        )
    )
    return BasicContext(
        user=user,
        organization=organization,
        membership=membership,
        role=role,
        assigned_facility_ids=tuple(dict.fromkeys(row.facility_id for row in assignment_rows)),
        assigned_room_ids=tuple(row.room_id for row in assignment_rows),
    )


BasicContextDependency = Annotated[BasicContext, Depends(get_basic_context)]


def refresh_basic_context(
    session: SessionDependency,
    context: BasicContext,
    *,
    required_any_permissions: tuple[str, ...] = (),
    required_all_permissions: tuple[str, ...] = (),
    conceal_detail: str = "Resource not found",
) -> BasicContext:
    """Re-read active role and room scope inside an operational transaction lane."""

    row = session.execute(
        select(OrganizationMembership, Role)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == context.membership.id,
            OrganizationMembership.user_id == context.user.id,
            OrganizationMembership.status == "active",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=conceal_detail)
    membership, role = row
    permissions = set(role.permissions or [])
    if required_any_permissions and not permissions.intersection(
        required_any_permissions
    ):
        raise HTTPException(status_code=404, detail=conceal_detail)
    if required_all_permissions and not set(
        required_all_permissions
    ).issubset(permissions):
        raise HTTPException(status_code=404, detail=conceal_detail)
    assignment_rows = list(
        session.execute(
            select(
                MembershipRoomAssignment.facility_id,
                MembershipRoomAssignment.room_id,
            )
            .join(
                Room,
                (Room.organization_id == MembershipRoomAssignment.organization_id)
                & (Room.id == MembershipRoomAssignment.room_id),
            )
            .join(
                Facility,
                (Facility.organization_id == MembershipRoomAssignment.organization_id)
                & (Facility.id == MembershipRoomAssignment.facility_id),
            )
            .where(
                MembershipRoomAssignment.organization_id
                == context.organization.id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
                Room.is_active.is_(True),
                Facility.status == "active",
            )
            .order_by(
                MembershipRoomAssignment.facility_id,
                MembershipRoomAssignment.room_id,
            )
        )
    )
    return BasicContext(
        user=context.user,
        organization=context.organization,
        membership=membership,
        role=role,
        assigned_facility_ids=tuple(
            dict.fromkeys(value.facility_id for value in assignment_rows)
        ),
        assigned_room_ids=tuple(value.room_id for value in assignment_rows),
    )


# Command reconciliation is actor-private and organization-bound. It must stay
# available to every active member who can issue a durable command, including
# admissions-only custom roles, without granting any domain read permission.
CommandReconciliationContext = BasicContextDependency


def require_owner(context: BasicContextDependency) -> BasicContext:
    if context.role.key != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization owner permission required",
        )
    return context


OwnerContext = Annotated[BasicContext, Depends(require_owner)]


def require_family_authority_admin(context: BasicContextDependency) -> BasicContext:
    """Restrict confidential family-authority workspaces to organization leaders."""

    if context.role.key not in {"owner", "administrator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization owner or administrator permission required",
        )
    return context


FamilyAuthorityAdminContext = Annotated[
    BasicContext,
    Depends(require_family_authority_admin),
]


def require_permission(permission: str):
    def dependency(context: BasicContextDependency) -> BasicContext:
        if permission not in set(context.role.permissions or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission required",
            )
        return context

    return dependency


def require_any_permission(*permissions: str):
    def dependency(context: BasicContextDependency) -> BasicContext:
        available = set(context.role.permissions or [])
        if not available.intersection(permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission required",
            )
        return context

    return dependency


def require_all_permissions(*permissions: str):
    def dependency(context: BasicContextDependency) -> BasicContext:
        available = set(context.role.permissions or [])
        if not set(permissions).issubset(available):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission required",
            )
        return context

    return dependency


FacilityReadContext = Annotated[BasicContext, Depends(require_permission("facility:read"))]
FacilityManageContext = Annotated[BasicContext, Depends(require_permission("facility:manage"))]
ChildcareReadContext = Annotated[BasicContext, Depends(require_permission("childcare:read"))]
ChildcareManageContext = Annotated[BasicContext, Depends(require_permission("childcare:manage"))]
AdmissionsReadContext = Annotated[
    BasicContext, Depends(require_permission("admissions:read"))
]
AdmissionsManageContext = Annotated[
    BasicContext, Depends(require_permission("admissions:manage"))
]
AdmissionsDecideContext = Annotated[
    BasicContext, Depends(require_permission("admissions:decide"))
]
CareRosterContext = Annotated[BasicContext, Depends(require_permission("care_roster:read"))]
ChildPhotoReadContext = Annotated[
    BasicContext,
    Depends(require_any_permission("childcare:read", "care_roster:read")),
]
AttendanceReadContext = Annotated[BasicContext, Depends(require_permission("attendance:read"))]
AttendanceRecordContext = Annotated[BasicContext, Depends(require_permission("attendance:record"))]
AttendanceCorrectContext = Annotated[
    BasicContext, Depends(require_permission("attendance:correct"))
]
ReleaseContextReadContext = Annotated[BasicContext, Depends(require_permission("release:read"))]
CareReadContext = Annotated[BasicContext, Depends(require_permission("care:read"))]
CareDaybookContext = Annotated[
    BasicContext,
    Depends(require_all_permissions("care:read", "child_safety:read")),
]
CareDailyCloseContext = Annotated[
    BasicContext,
    Depends(
        require_all_permissions(
            "care:read",
            "child_safety:read",
            "medication:read",
            "incident:read",
        )
    ),
]
CareRecordContext = Annotated[BasicContext, Depends(require_permission("care:record"))]
CareCorrectionContext = Annotated[
    BasicContext,
    Depends(require_any_permission("care:correct", "care:correct_own")),
]
CareVoidContext = Annotated[BasicContext, Depends(require_permission("care:void"))]
ChildSafetyContext = Annotated[BasicContext, Depends(require_permission("child_safety:read"))]
MedicationReadContext = Annotated[BasicContext, Depends(require_permission("medication:read"))]
MedicationManageContext = Annotated[BasicContext, Depends(require_permission("medication:manage"))]
MedicationRecordContext = Annotated[BasicContext, Depends(require_permission("medication:record"))]
MedicationCorrectContext = Annotated[
    BasicContext,
    Depends(require_any_permission("medication:correct", "medication:correct_own")),
]
MedicationVoidContext = Annotated[BasicContext, Depends(require_permission("medication:void"))]
IncidentReadContext = Annotated[BasicContext, Depends(require_permission("incident:read"))]
IncidentCreateContext = Annotated[BasicContext, Depends(require_permission("incident:create"))]
IncidentUpdateContext = Annotated[
    BasicContext,
    Depends(require_any_permission("incident:update", "incident:update_own")),
]
IncidentReviewContext = Annotated[BasicContext, Depends(require_permission("incident:review"))]
IncidentExternalReportContext = Annotated[
    BasicContext, Depends(require_permission("incident:external_report"))
]
StaffAccessContext = Annotated[
    BasicContext,
    Depends(require_any_permission("staff:manage", "staff:manage_educators")),
]
