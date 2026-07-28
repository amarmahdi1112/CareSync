"""Owner/administrator staff lifecycle and room-scoped access API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.basic.common import commit_in_context, ensure_writable, flush_or_conflict
from app.api.basic.dependencies import BasicContext, StaffAccessContext
from app.api.dependencies import SessionDependency
from app.basic.access import (
    active_assignment_ids,
    can_manage_role,
    revoke_outstanding_password_resets,
    validate_room_scope,
)
from app.basic.models import (
    AtsCandidate,
    Facility,
    MembershipRoomAssignment,
    OrganizationMembership,
    PasswordResetChallenge,
    Role,
    Room,
    StaffInvitation,
    StaffInvitationRoom,
    StaffRoomPresenceSession,
    StaffShift,
    User,
)
from app.basic.notifications import notify_user
from app.basic.room_safety import (
    close_presence_for_access_revocation,
    lock_facility_projection,
    reconcile_facility_exceptions,
)
from app.basic.room_safety import (
    foundation_enabled as room_safety_enabled,
)
from app.basic.schemas import (
    StaffFacilityResponse,
    StaffInvitationCreate,
    StaffInvitationResponse,
    StaffMemberPatch,
    StaffMemberResponse,
    StaffOneTimeActivationResponse,
    StaffPasswordResetResponse,
    StaffRoleResponse,
    StaffRoomResponse,
    StaffWorkspaceResponse,
)
from app.basic.security import (
    audit,
    create_one_time_token,
    normalize_email,
)

router = APIRouter(prefix="/staff", tags=["basic staff access"])


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _role_response(role: Role) -> StaffRoleResponse:
    return StaffRoleResponse(
        id=role.id,
        key=role.key,
        name=role.name,
        description=role.description,
        permissions=list(role.permissions or []),
    )


def _role(
    session: SessionDependency,
    organization_id: UUID,
    role_id: UUID,
) -> Role:
    value = session.scalar(
        select(Role).where(Role.organization_id == organization_id, Role.id == role_id)
    )
    if value is None or value.key not in {"owner", "administrator", "educator"}:
        raise HTTPException(status_code=404, detail="Staff role not found")
    return value


def _ensure_hierarchy(context: BasicContext, target_role: Role) -> None:
    if not can_manage_role(context.role.key, target_role.key):
        raise HTTPException(status_code=403, detail="Staff hierarchy does not allow this action")


def _invitation(
    session: SessionDependency,
    organization_id: UUID,
    invitation_id: UUID,
    *,
    lock: bool = False,
) -> StaffInvitation:
    statement = select(StaffInvitation).where(
        StaffInvitation.organization_id == organization_id,
        StaffInvitation.id == invitation_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Staff invitation not found")
    return value


def _invitation_response(
    session: SessionDependency,
    invitation: StaffInvitation,
    role: Role | None = None,
) -> StaffInvitationResponse:
    selected_role = role or _role(session, invitation.organization_id, invitation.role_id)
    scope_rows = list(
        session.execute(
            select(StaffInvitationRoom.facility_id, StaffInvitationRoom.room_id)
            .where(
                StaffInvitationRoom.organization_id == invitation.organization_id,
                StaffInvitationRoom.invitation_id == invitation.id,
            )
            .order_by(StaffInvitationRoom.facility_id, StaffInvitationRoom.room_id)
        )
    )
    now = datetime.now(UTC)
    if invitation.accepted_at is not None:
        invitation_status = "accepted"
    elif invitation.revoked_at is not None:
        invitation_status = "revoked"
    elif _aware(invitation.expires_at) <= now:
        invitation_status = "expired"
    else:
        invitation_status = "pending"
    return StaffInvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        role=_role_response(selected_role),
        status=invitation_status,
        assigned_facility_ids=list(dict.fromkeys(row.facility_id for row in scope_rows)),
        assigned_room_ids=[row.room_id for row in scope_rows],
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


def _member_row(
    session: SessionDependency,
    organization_id: UUID,
    membership_id: UUID,
    *,
    lock: bool = False,
) -> tuple[OrganizationMembership, User, Role]:
    statement = (
        select(OrganizationMembership, User, Role)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.id == membership_id,
            OrganizationMembership.status.in_(("active", "suspended")),
        )
    )
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return row[0], row[1], row[2]


def _member_response(
    session: SessionDependency,
    membership: OrganizationMembership,
    user: User,
    role: Role,
) -> StaffMemberResponse:
    facility_ids, room_ids = active_assignment_ids(
        session, membership.organization_id, membership.id
    )
    assignment_rows = list(
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
                MembershipRoomAssignment.organization_id == membership.organization_id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
                Facility.status == "active",
                Room.is_active.is_(True),
            )
            .order_by(Facility.name, Room.name)
        )
    )
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == membership.organization_id,
            AtsCandidate.claimed_user_id == user.id,
        )
        .order_by(AtsCandidate.updated_at.desc())
        .limit(1)
    )
    open_shift = session.scalar(
        select(StaffShift).where(
            StaffShift.organization_id == membership.organization_id,
            StaffShift.membership_id == membership.id,
            StaffShift.status == "open",
        )
    )
    credential = None
    if candidate is not None:
        not_expired = (
            candidate.certification_expiry_date is None
            or candidate.certification_expiry_date >= datetime.now(UTC).date()
        )
        credential = {
            "certification_type": candidate.certification_type,
            "certification_number": candidate.certification_number,
            "expiry_date": candidate.certification_expiry_date,
            "verification_status": candidate.certification_verification_status,
            "ready": bool(
                candidate.certification_number
                and candidate.certification_verification_status == "verified"
                and not_expired
            ),
        }
    return StaffMemberResponse(
        membership_id=membership.id,
        organization_id=membership.organization_id,
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=_role_response(role),
        membership_status=membership.status,
        assigned_facility_ids=facility_ids,
        assigned_room_ids=room_ids,
        active_assignments=[
            {
                "facility_id": facility.id,
                "facility_name": facility.name,
                "room_id": room.id,
                "room_name": room.name,
            }
            for _, facility, room in assignment_rows
        ],
        credential=credential,
        current_shift=(
            {
                "id": open_shift.id,
                "facility_id": open_shift.facility_id,
                "scheduled_shift_id": open_shift.scheduled_shift_id,
                "status": open_shift.status,
                "clocked_in_at": open_shift.clocked_in_at,
                "clocked_out_at": open_shift.clocked_out_at,
            }
            if open_shift is not None
            else None
        ),
        joined_at=membership.joined_at,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.get("/workspace", response_model=StaffWorkspaceResponse)
def staff_workspace(
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffWorkspaceResponse:
    role_keys = (
        ("educator",)
        if context.role.key == "administrator"
        else ("owner", "administrator", "educator")
    )
    roles = list(
        session.scalars(
            select(Role)
            .where(
                Role.organization_id == context.organization.id,
                Role.key.in_(role_keys),
            )
            .order_by(Role.name)
        )
    )
    facilities = list(
        session.scalars(
            select(Facility)
            .where(Facility.organization_id == context.organization.id)
            .order_by(Facility.name)
        )
    )
    rooms = list(
        session.scalars(
            select(Room).where(Room.organization_id == context.organization.id).order_by(Room.name)
        )
    )
    member_statement = (
        select(OrganizationMembership, User, Role)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.status.in_(("active", "suspended")),
        )
    )
    if context.role.key == "administrator":
        member_statement = member_statement.where(Role.key == "educator")
    member_rows = list(
        session.execute(
            member_statement.order_by(User.last_name, User.first_name, OrganizationMembership.id)
        )
    )
    invitation_statement = select(StaffInvitation).where(
        StaffInvitation.organization_id == context.organization.id
    )
    if context.role.key == "administrator":
        invitation_statement = invitation_statement.where(
            StaffInvitation.role_id.in_([role.id for role in roles])
        )
    invitations = list(
        session.scalars(
            invitation_statement.order_by(StaffInvitation.created_at.desc(), StaffInvitation.id)
        )
    )
    return StaffWorkspaceResponse(
        organization_id=context.organization.id,
        roles=[_role_response(item) for item in roles],
        facilities=[StaffFacilityResponse.model_validate(item) for item in facilities],
        rooms=[StaffRoomResponse.model_validate(item) for item in rooms],
        members=[_member_response(session, *row) for row in member_rows],
        invitations=[_invitation_response(session, item) for item in invitations],
    )


def _validated_scope(
    session: SessionDependency,
    organization_id: UUID,
    role: Role,
    facility_ids: list[UUID],
    room_ids: list[UUID],
    *,
    allow_empty: bool = False,
) -> list[Room]:
    if role.key == "administrator":
        if facility_ids or room_ids:
            raise HTTPException(
                status_code=422,
                detail="Administrator access is organization-wide and cannot have room scope",
            )
        return []
    if role.key != "educator":
        raise HTTPException(status_code=403, detail="Role cannot be assigned through staff access")
    if not room_ids and not allow_empty:
        raise HTTPException(status_code=422, detail="Educator access requires an active room")
    return validate_room_scope(session, organization_id, facility_ids, room_ids)


@router.post(
    "/invitations",
    response_model=StaffOneTimeActivationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_staff_invitation(
    payload: StaffInvitationCreate,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffOneTimeActivationResponse:
    ensure_writable(request)
    role = _role(session, context.organization.id, payload.role_id)
    _ensure_hierarchy(context, role)
    rooms = _validated_scope(
        session,
        context.organization.id,
        role,
        payload.assigned_facility_ids,
        payload.assigned_room_ids,
    )
    email = normalize_email(payload.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    if (
        session.scalar(
            select(StaffInvitation.id).where(
                StaffInvitation.organization_id == context.organization.id,
                StaffInvitation.email == email,
                StaffInvitation.accepted_at.is_(None),
                StaffInvitation.revoked_at.is_(None),
                StaffInvitation.expires_at > datetime.now(UTC),
            )
        )
        is not None
    ):
        raise HTTPException(status_code=409, detail="An invitation already exists for this email")

    invitation_id = uuid4()
    token, token_hash = create_one_time_token(context.organization.id, invitation_id)
    invitation = StaffInvitation(
        id=invitation_id,
        organization_id=context.organization.id,
        role_id=role.id,
        email=email,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_by_user_id=context.user.id,
    )
    session.add(invitation)
    flush_or_conflict(session, "An invitation already exists for this email")
    session.add_all(
        StaffInvitationRoom(
            organization_id=context.organization.id,
            invitation_id=invitation.id,
            facility_id=room.facility_id,
            room_id=room.id,
        )
        for room in rooms
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff.invitation_created",
        entity_type="staff_invitation",
        entity_id=invitation.id,
        details={"role_key": role.key, "room_count": len(rooms)},
    )
    commit_in_context(session, context, "Staff invitation conflicts with existing data")
    return StaffOneTimeActivationResponse(
        invitation=_invitation_response(session, invitation, role),
        activation_url=f"/activate-staff#token={token}",
    )


@router.post(
    "/invitations/{invitation_id}/regenerate",
    response_model=StaffOneTimeActivationResponse,
)
def regenerate_staff_invitation(
    invitation_id: UUID,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffOneTimeActivationResponse:
    ensure_writable(request)
    invitation = _invitation(session, context.organization.id, invitation_id, lock=True)
    role = _role(session, context.organization.id, invitation.role_id)
    _ensure_hierarchy(context, role)
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Invitation is no longer pending")
    token, token_hash = create_one_time_token(context.organization.id, invitation.id)
    invitation.token_hash = token_hash
    invitation.expires_at = datetime.now(UTC) + timedelta(days=7)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff.invitation_regenerated",
        entity_type="staff_invitation",
        entity_id=invitation.id,
    )
    commit_in_context(session, context)
    return StaffOneTimeActivationResponse(
        invitation=_invitation_response(session, invitation, role),
        activation_url=f"/activate-staff#token={token}",
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_staff_invitation(
    invitation_id: UUID,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> Response:
    ensure_writable(request)
    invitation = _invitation(session, context.organization.id, invitation_id, lock=True)
    role = _role(session, context.organization.id, invitation.role_id)
    _ensure_hierarchy(context, role)
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Accepted invitation cannot be revoked")
    invitation.revoked_at = invitation.revoked_at or datetime.now(UTC)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff.invitation_revoked",
        entity_type="staff_invitation",
        entity_id=invitation.id,
    )
    commit_in_context(session, context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _replace_member_scope(
    session: SessionDependency,
    context: BasicContext,
    membership: OrganizationMembership,
    rooms: list[Room],
) -> bool:
    existing = list(
        session.scalars(
            select(MembershipRoomAssignment).where(
                MembershipRoomAssignment.organization_id == context.organization.id,
                MembershipRoomAssignment.membership_id == membership.id,
            )
        )
    )
    desired = {room.id: room for room in rooms}
    changed = False
    existing_by_room = {item.room_id: item for item in existing}
    for item in existing:
        next_active = item.room_id in desired
        if item.is_active != next_active:
            item.is_active = next_active
            changed = True
    for room_id, room in desired.items():
        if room_id in existing_by_room:
            continue
        session.add(
            MembershipRoomAssignment(
                organization_id=context.organization.id,
                membership_id=membership.id,
                facility_id=room.facility_id,
                room_id=room.id,
                is_active=True,
                created_by_user_id=context.user.id,
            )
        )
        changed = True
    return changed


@router.patch("/members/{membership_id}", response_model=StaffMemberResponse)
def update_staff_member(
    membership_id: UUID,
    payload: StaffMemberPatch,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffMemberResponse:
    ensure_writable(request)
    live_room_safety = room_safety_enabled(
        request, session, context.organization.id
    )
    membership, user, current_role = _member_row(
        session,
        context.organization.id,
        membership_id,
        lock=not live_room_safety,
    )
    desired_role = _role(session, context.organization.id, payload.role_id)
    _ensure_hierarchy(context, current_role)
    _ensure_hierarchy(context, desired_role)
    desired_status = payload.membership_status or membership.status
    rooms = _validated_scope(
        session,
        context.organization.id,
        desired_role,
        payload.assigned_facility_ids,
        payload.assigned_room_ids,
        allow_empty=desired_status == "suspended",
    )
    if desired_status not in {"active", "suspended"}:
        raise HTTPException(status_code=422, detail="Invalid membership status")
    active_assignments = list(
        session.scalars(
            select(MembershipRoomAssignment)
            .where(
                MembershipRoomAssignment.organization_id
                == context.organization.id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
            )
        )
    )
    affected_facility_ids = {
        value.facility_id for value in active_assignments
    } | {value.facility_id for value in rooms}
    if live_room_safety:
        affected_facility_ids.update(
            session.scalars(
                select(StaffRoomPresenceSession.facility_id).where(
                    StaffRoomPresenceSession.organization_id
                    == context.organization.id,
                    StaffRoomPresenceSession.membership_id == membership.id,
                    StaffRoomPresenceSession.ended_at.is_(None),
                )
            )
        )
        affected_facility_ids.update(
            session.scalars(
                select(StaffShift.facility_id).where(
                    StaffShift.organization_id == context.organization.id,
                    StaffShift.membership_id == membership.id,
                    StaffShift.status == "open",
                    StaffShift.clocked_out_at.is_(None),
                )
            )
        )
        for facility_id in sorted(affected_facility_ids, key=str):
            lock_facility_projection(
                session, context.organization.id, facility_id
            )
        locked_facility_ids = set(affected_facility_ids)
        membership, user, current_role = _member_row(
            session,
            context.organization.id,
            membership_id,
            lock=True,
        )
        desired_role = _role(
            session, context.organization.id, payload.role_id
        )
        _ensure_hierarchy(context, current_role)
        _ensure_hierarchy(context, desired_role)
        desired_status = payload.membership_status or membership.status
        if desired_status not in {"active", "suspended"}:
            raise HTTPException(
                status_code=422, detail="Invalid membership status"
            )
        rooms = _validated_scope(
            session,
            context.organization.id,
            desired_role,
            payload.assigned_facility_ids,
            payload.assigned_room_ids,
            allow_empty=desired_status == "suspended",
        )
        active_assignments = list(
            session.scalars(
                select(MembershipRoomAssignment)
                .where(
                    MembershipRoomAssignment.organization_id
                    == context.organization.id,
                    MembershipRoomAssignment.membership_id == membership.id,
                    MembershipRoomAssignment.is_active.is_(True),
                )
                .with_for_update()
            )
        )
        current_shift_values = list(
            session.scalars(
                select(StaffShift)
                .where(
                    StaffShift.organization_id == context.organization.id,
                    StaffShift.membership_id == membership.id,
                    StaffShift.status == "open",
                    StaffShift.clocked_out_at.is_(None),
                )
                .order_by(StaffShift.id)
                .with_for_update()
            )
        )
        current_presence_values = list(
            session.scalars(
                select(StaffRoomPresenceSession)
                .where(
                    StaffRoomPresenceSession.organization_id
                    == context.organization.id,
                    StaffRoomPresenceSession.membership_id == membership.id,
                    StaffRoomPresenceSession.ended_at.is_(None),
                )
                .order_by(StaffRoomPresenceSession.id)
                .with_for_update()
            )
        )
        canonical_facility_ids = {
            value.facility_id for value in active_assignments
        } | {value.facility_id for value in rooms} | {
            value.facility_id for value in current_presence_values
        } | {
            value.facility_id for value in current_shift_values
        }
        if not canonical_facility_ids.issubset(locked_facility_ids):
            raise HTTPException(
                409,
                detail={
                    "code": "projection_changed_retry",
                    "message": (
                        "Staff room scope changed while the update was "
                        "being serialized; retry the command."
                    ),
                },
            )
        affected_facility_ids = canonical_facility_ids
    else:
        active_assignments = list(
            session.scalars(
                select(MembershipRoomAssignment)
                .where(
                    MembershipRoomAssignment.organization_id
                    == context.organization.id,
                    MembershipRoomAssignment.membership_id == membership.id,
                    MembershipRoomAssignment.is_active.is_(True),
                )
                .with_for_update()
            )
        )
        current_presence_values = []
        current_shift_values = []
    presence_authority_revoked = (
        desired_status != "active"
        or not {"shift:clock", "care_roster:read"}.issubset(
            set(desired_role.permissions or [])
        )
    )
    if len(current_presence_values) > 1 and not presence_authority_revoked:
        raise HTTPException(
            409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "duplicate_current_room_presence",
            },
        )
    current_presence = (
        current_presence_values[0]
        if len(current_presence_values) == 1
        else None
    )
    desired_room_ids = {value.id for value in rooms}
    if (
        current_presence is not None
        and current_presence.room_id not in desired_room_ids
        and not presence_authority_revoked
    ):
        raise HTTPException(
            409,
            detail={
                "code": "room_assignment_has_current_presence",
                "membership_id": str(membership.id),
                "facility_id": str(current_presence.facility_id),
                "room_id": str(current_presence.room_id),
                "message": (
                    "End or move the staff member's current room presence "
                    "before removing this assignment."
                ),
            },
    )
    presence_closed = False
    if current_presence_values and presence_authority_revoked:
        presence_closed = bool(
            close_presence_for_access_revocation(
                session,
                organization_id=context.organization.id,
                membership_id=membership.id,
                actor_user_id=context.user.id,
                operation_id=uuid4(),
                locked_facility_ids=locked_facility_ids,
            )
        )
    changed = False
    if membership.role_id != desired_role.id:
        membership.role_id = desired_role.id
        changed = True
    if membership.status != desired_status:
        membership.status = desired_status
        changed = True
    changed = _replace_member_scope(session, context, membership, rooms) or changed
    if changed:
        revoke_outstanding_password_resets(
            session,
            context.organization.id,
            membership.id,
        )
        user.auth_version += 1
        notify_user(
            session,
            user_id=user.id,
            organization_id=context.organization.id,
            event_key=f"staff-assignment:{membership.id}:{user.auth_version}",
            category="assignment",
            severity="info",
            title="Staff access updated",
            body=(
                f"Your {context.organization.name} access now includes "
                f"{len(rooms)} active room assignment(s)."
            ),
            action_path="/today" if desired_status == "active" else None,
            action_entity_type=(
                "organization_membership" if desired_status == "active" else None
            ),
            action_entity_id=membership.id if desired_status == "active" else None,
        )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff.membership_updated",
        entity_type="organization_membership",
        entity_id=membership.id,
        details={
            "role_key": desired_role.key,
            "membership_status": membership.status,
            "room_count": len(rooms),
        },
    )
    if live_room_safety and (changed or presence_closed):
        for facility_id in sorted(affected_facility_ids, key=str):
            facility = session.scalar(
                select(Facility).where(
                    Facility.organization_id == context.organization.id,
                    Facility.id == facility_id,
                    Facility.status == "active",
                )
            )
            if facility is None:
                continue
            reconcile_facility_exceptions(
                session,
                organization_id=context.organization.id,
                facility_id=facility_id,
                cause_entity_type="organization_membership",
                cause_entity_id=membership.id,
            )
    commit_in_context(session, context)
    session.refresh(membership)
    return _member_response(session, membership, user, desired_role)


@router.post(
    "/members/{membership_id}/password-reset",
    response_model=StaffPasswordResetResponse,
)
def issue_staff_password_reset(
    membership_id: UUID,
    request: Request,
    context: StaffAccessContext,
    session: SessionDependency,
) -> StaffPasswordResetResponse:
    ensure_writable(request)
    membership, user, role = _member_row(session, context.organization.id, membership_id, lock=True)
    _ensure_hierarchy(context, role)
    if membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password reset requires an active staff membership",
        )
    now = datetime.now(UTC)
    revoke_outstanding_password_resets(
        session,
        context.organization.id,
        membership.id,
        revoked_at=now,
    )
    challenge_id = uuid4()
    token, token_hash = create_one_time_token(context.organization.id, challenge_id)
    expires_at = now + timedelta(hours=1)
    challenge = PasswordResetChallenge(
        id=challenge_id,
        organization_id=context.organization.id,
        membership_id=membership.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by_user_id=context.user.id,
    )
    session.add(challenge)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="staff.password_reset_issued",
        entity_type="user",
        entity_id=user.id,
        details={"membership_id": str(membership.id)},
    )
    commit_in_context(session, context)
    return StaffPasswordResetResponse(
        reset_url=f"/reset-password#token={token}",
        expires_at=expires_at,
    )
