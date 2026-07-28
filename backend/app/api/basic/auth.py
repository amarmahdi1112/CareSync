"""Owner registration and fail-closed Basic authentication."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.api.basic.common import (
    cleaned_values,
    commit_in_context,
    commit_or_conflict,
    ensure_writable,
    flush_or_conflict,
    user_response,
)
from app.api.basic.dependencies import BasicContextDependency, BasicUser
from app.api.dependencies import SessionDependency
from app.basic.access import active_assignment_ids, revoke_outstanding_password_resets
from app.basic.candidate_profiles import missing_profile_fields
from app.basic.models import (
    Facility,
    MarketplaceProfile,
    MembershipRoomAssignment,
    OnboardingState,
    Organization,
    OrganizationMembership,
    PasswordResetChallenge,
    Role,
    Room,
    StaffInvitation,
    StaffInvitationRoom,
    User,
)
from app.basic.schemas import (
    AuthResponse,
    LoginRequest,
    OneTimeTokenRequest,
    PasswordChangeRequest,
    PasswordResetComplete,
    PasswordResetPreview,
    ProfileUpdateRequest,
    RegisterRequest,
    StaffActivationAccept,
    StaffActivationPreview,
    UserResponse,
)
from app.basic.security import (
    ADMINISTRATOR_PERMISSIONS,
    EDUCATOR_PERMISSIONS,
    OWNER_PERMISSIONS,
    audit,
    create_access_token,
    hash_password,
    normalize_email,
    parse_one_time_token,
    set_rls_organization,
    set_rls_user,
    token_digest_matches,
    verify_password,
)
from app.basic.verification import (
    TEMPORARY_AUTO_APPROVAL,
    apply_temporary_daycare_approval,
    apply_temporary_email_approval,
)

router = APIRouter(prefix="/auth", tags=["basic authentication"])


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _challenge_parts(token: str) -> tuple[UUID, UUID, str]:
    try:
        return parse_one_time_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Link is unavailable"
        ) from None


def _invitation_from_token(
    token: str,
    session: SessionDependency,
    *,
    lock: bool = False,
) -> StaffInvitation:
    organization_id, invitation_id, token_hash = _challenge_parts(token)
    set_rls_organization(session, organization_id)
    statement = select(StaffInvitation).where(
        StaffInvitation.id == invitation_id,
        StaffInvitation.organization_id == organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    invitation = session.scalar(statement)
    now = datetime.now(UTC)
    if (
        invitation is None
        or not token_digest_matches(invitation.token_hash, token_hash)
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or _aware(invitation.expires_at) <= now
    ):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    return invitation


def _reset_from_token(
    token: str,
    session: SessionDependency,
    *,
    lock: bool = False,
) -> PasswordResetChallenge:
    organization_id, challenge_id, token_hash = _challenge_parts(token)
    set_rls_organization(session, organization_id)
    statement = select(PasswordResetChallenge).where(
        PasswordResetChallenge.id == challenge_id,
        PasswordResetChallenge.organization_id == organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    challenge = session.scalar(statement)
    now = datetime.now(UTC)
    if (
        challenge is None
        or not token_digest_matches(challenge.token_hash, token_hash)
        or challenge.consumed_at is not None
        or challenge.revoked_at is not None
        or _aware(challenge.expires_at) <= now
    ):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    return challenge


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    session: SessionDependency,
) -> AuthResponse:
    ensure_writable(request)
    email = normalize_email(payload.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    verification_time = datetime.now(UTC)
    user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        is_active=True,
    )
    apply_temporary_email_approval(user, decided_at=verification_time)
    organization_name = (payload.organization_name or "").strip()
    if not organization_name:
        organization_name = f"{payload.first_name.strip()}'s Child Care"
    organization = Organization(
        id=uuid4(),
        name=organization_name,
        status="draft",
        email=email,
        timezone="America/Edmonton",
        preferences={},
    )
    apply_temporary_daycare_approval(organization, decided_at=verification_time)
    owner_role = Role(
        id=uuid4(),
        organization_id=organization.id,
        key="owner",
        name="Owner",
        description="Organization owner with full Basic access",
        permissions=OWNER_PERMISSIONS,
        is_system=True,
    )
    administrator_role = Role(
        id=uuid4(),
        organization_id=organization.id,
        key="administrator",
        name="Administrator",
        description="Organization-wide operational access and educator administration",
        permissions=ADMINISTRATOR_PERMISSIONS,
        is_system=True,
    )
    educator_role = Role(
        id=uuid4(),
        organization_id=organization.id,
        key="educator",
        name="Educator",
        description="Assigned-room care roster and attendance recording",
        permissions=EDUCATOR_PERMISSIONS,
        is_system=True,
    )
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        role_id=owner_role.id,
        status="active",
        joined_at=datetime.now(UTC),
    )
    onboarding = OnboardingState(
        organization_id=organization.id,
        status="draft",
        current_step="organization",
        completed_steps=[],
        draft={},
    )
    set_rls_user(session, user.id)
    set_rls_organization(session, organization.id)
    # Explicit flush boundaries keep SQLite/PostgreSQL FK ordering deterministic
    # without coupling the domain model to eager ORM relationship graphs.
    session.add_all([user, organization])
    flush_or_conflict(session, "Email or organization already registered")
    session.add_all([owner_role, administrator_role, educator_role])
    flush_or_conflict(session, "Organization authorization could not be created")
    session.add_all([membership, onboarding])
    flush_or_conflict(session, "Organization membership could not be created")
    audit(
        session,
        organization_id=organization.id,
        actor_user_id=user.id,
        action="organization.registered",
        entity_type="organization",
        entity_id=organization.id,
        details={"verification_method": TEMPORARY_AUTO_APPROVAL},
    )
    commit_or_conflict(session, "Email or organization already registered")
    session.refresh(user)
    return AuthResponse(
        access_token=create_access_token(user, request.app.state.settings),
        user=user_response(
            user,
            role=owner_role,
            membership=membership,
            organization_id=organization.id,
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDependency,
) -> AuthResponse:
    user = session.scalar(select(User).where(User.email == normalize_email(payload.email)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email verification required")
    set_rls_user(session, user.id)
    memberships = list(
        session.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "active",
            )
            .order_by(OrganizationMembership.created_at)
        )
    )
    if not memberships:
        raise HTTPException(status_code=403, detail="Active organization membership required")
    if payload.organization_id is not None:
        membership = next(
            (item for item in memberships if item.organization_id == payload.organization_id),
            None,
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="Active organization membership required")
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        organizations = []
        for item in memberships:
            set_rls_organization(session, item.organization_id)
            organization = session.get(Organization, item.organization_id)
            role = session.scalar(
                select(Role).where(
                    Role.organization_id == item.organization_id,
                    Role.id == item.role_id,
                )
            )
            if organization is not None and role is not None:
                organizations.append(
                    {
                        "organization_id": str(organization.id),
                        "organization_name": organization.name,
                        "membership_id": str(item.id),
                        "role_key": role.key,
                    }
                )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "organization_selection_required",
                "organizations": organizations,
            },
        )
    set_rls_organization(session, membership.organization_id)
    role = session.scalar(
        select(Role).where(
            Role.organization_id == membership.organization_id,
            Role.id == membership.role_id,
        )
    )
    organization = session.scalar(
        select(Organization).where(Organization.id == membership.organization_id)
    )
    if role is None or organization is None or organization.status in {"suspended", "archived"}:
        raise HTTPException(status_code=403, detail="Organization access is unavailable")
    assigned_facility_ids, assigned_room_ids = active_assignment_ids(
        session, organization.id, membership.id
    )
    return AuthResponse(
        access_token=create_access_token(user, request.app.state.settings),
        user=user_response(
            user,
            role=role,
            membership=membership,
            organization_id=organization.id,
            assigned_facility_ids=assigned_facility_ids,
            assigned_room_ids=assigned_room_ids,
        ),
    )


@router.get("/organizations")
def organizations(user: BasicUser, session: SessionDependency):
    """Return every active tenant context the authenticated identity may select."""
    memberships = list(
        session.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "active",
            )
            .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
        )
    )
    result = []
    for membership in memberships:
        set_rls_organization(session, membership.organization_id)
        organization = session.get(Organization, membership.organization_id)
        role = session.scalar(
            select(Role).where(
                Role.organization_id == membership.organization_id,
                Role.id == membership.role_id,
            )
        )
        if (
            organization is None
            or role is None
            or organization.status in {"suspended", "archived"}
        ):
            continue
        facility_ids, room_ids = active_assignment_ids(
            session, organization.id, membership.id
        )
        result.append(
            {
                "organization_id": organization.id,
                "organization_name": organization.name,
                "organization_status": organization.status,
                "membership_id": membership.id,
                "membership_status": membership.status,
                "role": {
                    "id": role.id,
                    "key": role.key,
                    "name": role.name,
                    "permissions": list(role.permissions or []),
                },
                "assigned_facility_ids": facility_ids,
                "assigned_room_ids": room_ids,
                "request_header": {
                    "name": "X-Organization-ID",
                    "value": str(organization.id),
                },
            }
        )
    return {"organizations": result, "selection_required": len(result) > 1}


@router.post("/staff-activation", response_model=StaffActivationPreview)
def staff_activation_preview(
    payload: OneTimeTokenRequest,
    session: SessionDependency,
) -> StaffActivationPreview:
    invitation = _invitation_from_token(payload.token, session)
    organization = session.scalar(
        select(Organization).where(Organization.id == invitation.organization_id)
    )
    role = session.scalar(
        select(Role).where(
            Role.organization_id == invitation.organization_id,
            Role.id == invitation.role_id,
        )
    )
    room_names = list(
        session.scalars(
            select(Room.name)
            .join(
                StaffInvitationRoom,
                (StaffInvitationRoom.organization_id == Room.organization_id)
                & (StaffInvitationRoom.room_id == Room.id),
            )
            .where(
                StaffInvitationRoom.organization_id == invitation.organization_id,
                StaffInvitationRoom.invitation_id == invitation.id,
            )
            .order_by(Room.name)
        )
    )
    if organization is None or role is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    return StaffActivationPreview(
        organization_name=organization.name,
        email=invitation.email,
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        role_name=role.name,
        expires_at=invitation.expires_at,
        assigned_room_names=room_names,
    )


@router.post("/staff-activation/accept", response_model=AuthResponse)
def accept_staff_activation(
    payload: StaffActivationAccept,
    request: Request,
    session: SessionDependency,
) -> AuthResponse:
    ensure_writable(request)
    invitation = _invitation_from_token(payload.token, session, lock=True)
    role = session.scalar(
        select(Role).where(
            Role.organization_id == invitation.organization_id,
            Role.id == invitation.role_id,
            Role.key.in_(("administrator", "educator")),
        )
    )
    organization = session.scalar(
        select(Organization).where(Organization.id == invitation.organization_id)
    )
    if role is None or organization is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    if session.scalar(select(User.id).where(User.email == invitation.email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")

    room_rows = list(
        session.execute(
            select(StaffInvitationRoom, Room)
            .join(
                Room,
                (Room.organization_id == StaffInvitationRoom.organization_id)
                & (Room.facility_id == StaffInvitationRoom.facility_id)
                & (Room.id == StaffInvitationRoom.room_id),
            )
            .join(
                Facility,
                (Facility.organization_id == Room.organization_id)
                & (Facility.id == Room.facility_id),
            )
            .where(
                StaffInvitationRoom.organization_id == invitation.organization_id,
                StaffInvitationRoom.invitation_id == invitation.id,
                Room.is_active.is_(True),
                Facility.status == "active",
            )
            .order_by(Room.facility_id, Room.id)
        )
    )
    expected_scope_count = session.scalar(
        select(sa_func.count())
        .select_from(StaffInvitationRoom)
        .where(
            StaffInvitationRoom.organization_id == invitation.organization_id,
            StaffInvitationRoom.invitation_id == invitation.id,
        )
    )
    if int(expected_scope_count or 0) != len(room_rows):
        raise HTTPException(status_code=409, detail="Invitation room access is no longer valid")
    if role.key == "administrator" and room_rows:
        raise HTTPException(
            status_code=409, detail="Administrator access must be organization-wide"
        )
    if role.key == "educator" and not room_rows:
        raise HTTPException(status_code=409, detail="Educator access requires an active room")

    now = datetime.now(UTC)
    user = User(
        id=uuid4(),
        email=invitation.email,
        password_hash=hash_password(payload.password),
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        is_active=True,
        auth_version=1,
    )
    apply_temporary_email_approval(user, decided_at=now)
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=invitation.organization_id,
        user_id=user.id,
        role_id=role.id,
        status="active",
        joined_at=now,
    )
    session.add(user)
    flush_or_conflict(session, "Email is already registered")
    set_rls_user(session, user.id)
    session.add(membership)
    flush_or_conflict(session, "Staff membership could not be activated")
    assignments = [
        MembershipRoomAssignment(
            organization_id=invitation.organization_id,
            membership_id=membership.id,
            facility_id=room.facility_id,
            room_id=room.id,
            created_by_user_id=invitation.created_by_user_id,
        )
        for _, room in room_rows
    ]
    session.add_all(assignments)
    invitation.accepted_at = now
    audit(
        session,
        organization_id=invitation.organization_id,
        actor_user_id=user.id,
        action="staff.invitation_accepted",
        entity_type="organization_membership",
        entity_id=membership.id,
        details={"invitation_id": str(invitation.id), "role_key": role.key},
    )
    commit_or_conflict(session, "Staff activation conflicts with existing data")
    assigned_facility_ids = list(dict.fromkeys(room.facility_id for _, room in room_rows))
    assigned_room_ids = [room.id for _, room in room_rows]
    return AuthResponse(
        access_token=create_access_token(user, request.app.state.settings),
        user=user_response(
            user,
            role=role,
            membership=membership,
            organization_id=organization.id,
            assigned_facility_ids=assigned_facility_ids,
            assigned_room_ids=assigned_room_ids,
        ),
    )


@router.post("/password-reset", response_model=PasswordResetPreview)
def password_reset_preview(
    payload: OneTimeTokenRequest,
    session: SessionDependency,
) -> PasswordResetPreview:
    challenge = _reset_from_token(payload.token, session)
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == challenge.organization_id,
            OrganizationMembership.id == challenge.membership_id,
        )
    )
    organization = session.scalar(
        select(Organization).where(Organization.id == challenge.organization_id)
    )
    user = session.get(User, membership.user_id) if membership is not None else None
    if (
        membership is None
        or membership.status != "active"
        or organization is None
        or user is None
        or not user.is_active
    ):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    return PasswordResetPreview(
        organization_name=organization.name,
        email=user.email,
        expires_at=challenge.expires_at,
    )


@router.post("/password-reset/complete")
def complete_password_reset(
    payload: PasswordResetComplete,
    request: Request,
    session: SessionDependency,
) -> dict[str, str]:
    ensure_writable(request)
    challenge = _reset_from_token(payload.token, session, lock=True)
    membership = session.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == challenge.organization_id,
            OrganizationMembership.id == challenge.membership_id,
        )
        .with_for_update()
    )
    user = session.get(User, membership.user_id) if membership is not None else None
    if membership is None or membership.status != "active" or user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is unavailable")
    now = datetime.now(UTC)
    user.password_hash = hash_password(payload.password)
    user.auth_version += 1
    challenge.consumed_at = now
    revoke_outstanding_password_resets(
        session,
        challenge.organization_id,
        challenge.membership_id,
        except_challenge_id=challenge.id,
        revoked_at=now,
    )
    audit(
        session,
        organization_id=challenge.organization_id,
        actor_user_id=user.id,
        action="staff.password_reset_completed",
        entity_type="user",
        entity_id=user.id,
        details={"membership_id": str(membership.id)},
    )
    commit_or_conflict(session)
    return {"detail": "Password reset complete"}


@router.get("/me", response_model=UserResponse)
def me(context: BasicContextDependency, session: SessionDependency) -> UserResponse:
    response = user_response(context.user, context)
    profile = session.get(MarketplaceProfile, context.user.id)
    if profile is None:
        return response
    missing = missing_profile_fields(context.user, profile)
    return response.model_copy(
        update={"profile_complete": not missing, "missing_profile_fields": missing}
    )


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: ProfileUpdateRequest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> UserResponse:
    ensure_writable(request)
    values = cleaned_values(payload.model_dump(exclude_unset=True, exclude_none=True))
    marketplace_profile = session.get(MarketplaceProfile, context.user.id)
    if marketplace_profile is not None and "email" in values:
        raise HTTPException(
            status_code=409,
            detail={"code": "secure_email_change_required"},
        )
    if (
        marketplace_profile is not None
        and marketplace_profile.candidate_type == "certified_educator"
        and any(
            key in values and values[key] != getattr(context.user, key)
            for key in ("first_name", "last_name")
        )
    ):
        raise HTTPException(status_code=403, detail={"code": "certified_name_locked"})
    if "email" in values:
        values["email"] = normalize_email(values["email"])
        if not values["email"] or "@" not in values["email"]:
            raise HTTPException(status_code=422, detail="Invalid email")
        existing = session.scalar(
            select(User.id).where(User.email == values["email"], User.id != context.user.id)
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email already in use")
    email_changed = "email" in values and values["email"] != context.user.email
    before = {key: getattr(context.user, key) for key in values}
    for key, value in values.items():
        setattr(context.user, key, value)
    if email_changed:
        apply_temporary_email_approval(context.user)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="profile.updated",
        entity_type="user",
        entity_id=context.user.id,
        details={
            "before": before,
            "changed_fields": sorted(values),
            "email_verification_refreshed": email_changed,
        },
    )
    commit_in_context(session, context, "Email already in use")
    session.refresh(context.user)
    response = user_response(context.user, context)
    if marketplace_profile is None:
        return response
    missing = missing_profile_fields(context.user, marketplace_profile)
    return response.model_copy(
        update={"profile_complete": not missing, "missing_profile_fields": missing}
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> None:
    ensure_writable(request)
    if not verify_password(payload.current_password, context.user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    now = datetime.now(UTC)
    memberships = list(
        session.scalars(
            select(OrganizationMembership).where(OrganizationMembership.user_id == context.user.id)
        )
    )
    for membership in memberships:
        set_rls_organization(session, membership.organization_id)
        revoke_outstanding_password_resets(
            session,
            membership.organization_id,
            membership.id,
            revoked_at=now,
        )
        # Flush while this membership's tenant context is still active. A
        # later organization context must never be used to write its rows.
        session.flush()
    set_rls_organization(session, context.organization.id)
    context.user.password_hash = hash_password(payload.new_password)
    context.user.auth_version += 1
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="password.changed",
        entity_type="user",
        entity_id=context.user.id,
    )
    commit_in_context(session, context)
