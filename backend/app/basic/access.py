"""Central staff permission, hierarchy, and active-room scope helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.basic.models import (
    Facility,
    MembershipRoomAssignment,
    PasswordResetChallenge,
    Room,
)


def revoke_outstanding_password_resets(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
    *,
    except_challenge_id: UUID | None = None,
    revoked_at: datetime | None = None,
) -> int:
    """Revoke every usable reset challenge for one membership.

    Reset authorization is derived from the membership's current access. Any
    role, status, room-scope, or password change therefore invalidates links
    created under the previous authorization state.
    """

    statement = select(PasswordResetChallenge).where(
        PasswordResetChallenge.organization_id == organization_id,
        PasswordResetChallenge.membership_id == membership_id,
        PasswordResetChallenge.consumed_at.is_(None),
        PasswordResetChallenge.revoked_at.is_(None),
    )
    if except_challenge_id is not None:
        statement = statement.where(PasswordResetChallenge.id != except_challenge_id)
    challenges = list(session.scalars(statement))
    terminal_time = revoked_at or datetime.now(UTC)
    for challenge in challenges:
        challenge.revoked_at = terminal_time
    return len(challenges)


def active_assignment_ids(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
) -> tuple[list[UUID], list[UUID]]:
    rows = list(
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
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.membership_id == membership_id,
                MembershipRoomAssignment.is_active.is_(True),
                Room.is_active.is_(True),
                Facility.status == "active",
            )
            .order_by(MembershipRoomAssignment.facility_id, MembershipRoomAssignment.room_id)
        )
    )
    return (
        list(dict.fromkeys(row.facility_id for row in rows)),
        [row.room_id for row in rows],
    )


def validate_room_scope(
    session: Session,
    organization_id: UUID,
    facility_ids: list[UUID],
    room_ids: list[UUID],
) -> list[Room]:
    requested_facilities = set(facility_ids)
    requested_rooms = set(room_ids)
    facilities = list(
        session.scalars(
            select(Facility).where(
                Facility.organization_id == organization_id,
                Facility.id.in_(requested_facilities) if requested_facilities else False,
                Facility.status == "active",
            )
        )
    )
    if {item.id for item in facilities} != requested_facilities:
        raise HTTPException(status_code=404, detail="Assigned facility not found")
    rooms = list(
        session.scalars(
            select(Room).where(
                Room.organization_id == organization_id,
                Room.id.in_(requested_rooms) if requested_rooms else False,
                Room.is_active.is_(True),
            )
        )
    )
    if {item.id for item in rooms} != requested_rooms:
        raise HTTPException(status_code=404, detail="Assigned room not found")
    derived_facilities = {item.facility_id for item in rooms}
    if derived_facilities != requested_facilities:
        raise HTTPException(
            status_code=422,
            detail="Assigned facilities must exactly match the selected active rooms",
        )
    return sorted(rooms, key=lambda item: (str(item.facility_id), item.name, str(item.id)))


def can_manage_role(actor_key: str, target_key: str) -> bool:
    if actor_key == "owner":
        return target_key in {"administrator", "educator"}
    if actor_key == "administrator":
        return target_key == "educator"
    return False
