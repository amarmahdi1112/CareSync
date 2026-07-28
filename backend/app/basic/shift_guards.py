"""Operational mutation guard tied to an educator's open facility shift."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.basic.dependencies import BasicContext
from app.basic.models import StaffRoomPresenceSession, StaffShift


def _aware_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def require_open_shift(
    session: Session,
    context: BasicContext,
    facility_id: UUID,
    room_id: UUID | None = None,
    *,
    enforce_room_presence: bool = False,
    allow_terminal_integrity_escape: bool = False,
) -> None:
    """Require an actual shift and, when active, matching current-room evidence."""

    if not enforce_room_presence and context.organization_wide:
        # Preserve the retained pre-0041 organization-wide administrator
        # workflow.  Once the 0041 foundation is present, every actor uses the
        # same physical shift/current-room boundary.
        return
    shifts = list(
        session.scalars(
            select(StaffShift)
            .where(
                StaffShift.organization_id == context.organization.id,
                StaffShift.membership_id == context.membership.id,
                StaffShift.facility_id == facility_id,
                StaffShift.status == "open",
                StaffShift.clocked_out_at.is_(None),
            )
            .limit(2)
        )
    )
    if not shifts:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "open_shift_required",
                "facility_id": str(facility_id),
                "message": "Clock in to this facility before updating child records.",
            },
        )
    if len(shifts) > 1:
        if allow_terminal_integrity_escape:
            return
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "duplicate_open_staff_shifts",
                "facility_id": str(facility_id),
            },
        )
    now = datetime.now(UTC)
    shift = shifts[0]
    if (
        _aware_utc(shift.clocked_in_at) > now
        and not allow_terminal_integrity_escape
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "future_open_staff_shift",
                "facility_id": str(facility_id),
            },
        )
    if not enforce_room_presence:
        return
    if room_id is None:
        if allow_terminal_integrity_escape:
            return
        raise HTTPException(
            status_code=409,
            detail={
                "code": "room_presence_source_room_unknown",
                "facility_id": str(facility_id),
                "required_room_id": None,
                "current_room_id": None,
                "message": (
                    "This child record has no reliable room identity. "
                    "Repair its room assignment before changing it."
                ),
            },
        )
    matching_presence = list(
        session.scalars(
            select(StaffRoomPresenceSession)
            .where(
                StaffRoomPresenceSession.organization_id
                == context.organization.id,
                StaffRoomPresenceSession.membership_id
                == context.membership.id,
                StaffRoomPresenceSession.staff_shift_id == shift.id,
                StaffRoomPresenceSession.facility_id == facility_id,
                StaffRoomPresenceSession.room_id == room_id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
            .limit(2)
        )
    )
    if len(matching_presence) == 1:
        if (
            _aware_utc(matching_presence[0].started_at) > now
            and not allow_terminal_integrity_escape
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "source_integrity_unknown",
                    "reason": "future_current_room_presence",
                    "facility_id": str(facility_id),
                },
            )
        return
    if len(matching_presence) > 1 and allow_terminal_integrity_escape:
        return
    current_presence = list(
        session.execute(
            select(
                StaffRoomPresenceSession.room_id,
                StaffRoomPresenceSession.facility_id,
                StaffRoomPresenceSession.staff_shift_id,
                StaffRoomPresenceSession.started_at,
            )
            .where(
                StaffRoomPresenceSession.organization_id
                == context.organization.id,
                StaffRoomPresenceSession.membership_id
                == context.membership.id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
            .limit(2)
        )
    )
    if len(current_presence) > 1 and allow_terminal_integrity_escape:
        return
    current = current_presence[0] if len(current_presence) == 1 else None
    if (
        current is not None
        and _aware_utc(current.started_at) > now
        and not allow_terminal_integrity_escape
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "source_integrity_unknown",
                "reason": "future_current_room_presence",
                "facility_id": str(facility_id),
            },
        )
    if (
        allow_terminal_integrity_escape
        and current is not None
        and current.facility_id == facility_id
        and current.room_id == room_id
        and current.staff_shift_id != shift.id
    ):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": (
                "room_presence_required"
                if current is None
                else "room_presence_room_mismatch"
            ),
            "facility_id": str(facility_id),
            "required_room_id": str(room_id),
            "current_room_id": (
                str(current.room_id) if current is not None else None
            ),
            "message": (
                "Select this room as your current room before updating "
                "its child records."
            ),
        },
    )
