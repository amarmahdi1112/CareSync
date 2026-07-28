"""Domain invariants and privacy-safe projections for the staff exchange."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.basic.models import (
    Facility,
    MembershipRoomAssignment,
    OrganizationMembership,
    Role,
    Room,
    ScheduledStaffShift,
    StaffOpenShift,
    StaffOpenShiftEngagement,
    StaffRotationPattern,
    StaffShift,
    StaffShiftSwapRequest,
    StaffSubstituteProfile,
    StaffWorkforceEvent,
    User,
)
from app.basic.staff_exchange_schemas import (
    ExchangeScheduleSummary,
    OpenShiftCandidateResponse,
    OpenShiftEngagementResponse,
    OpenShiftResponse,
    RotationIssue,
    RotationOccurrence,
    RotationPatternResponse,
    RotationPreviewResponse,
    RotationSlotResponse,
    SelfOpenShiftResponse,
    ShiftSwapResponse,
    SubstituteManagerResponse,
    SubstituteProfileResponse,
    SwapCandidateResponse,
)
from app.basic.staff_scheduling import (
    clean_optional_text,
    stored_optional_utc,
    stored_utc,
    validate_assignment,
)
from app.basic.staff_workforce import (
    approved_leave_conflict,
    facility_row,
    parse_local_time,
    resolve_local_datetime,
    room_row,
)

MAX_PREVIEW_DAYS = 84
MAX_OCCURRENCES = 500


def canonical_json(values: dict) -> dict:
    def normalize(value, field: str):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise HTTPException(422, detail={"code": "timezone_required", "field": field})
            return value.astimezone(UTC).isoformat()
        elif isinstance(value, (date, time)):
            return value.isoformat()
        elif isinstance(value, UUID):
            return str(value)
        elif isinstance(value, str):
            return clean_optional_text(value)
        elif isinstance(value, dict):
            return {
                key: normalize(nested, f"{field}.{key}" if field else key)
                for key, nested in sorted(value.items())
            }
        elif isinstance(value, (list, tuple)):
            return [normalize(nested, field) for nested in value]
        return value

    return {key: normalize(value, key) for key, value in sorted(values.items())}


def receipt_event(
    session: Session,
    organization_id: UUID,
    operation_id: UUID,
    *,
    entity_type: str,
    event_type: str,
    request_payload: dict,
    entity_id: UUID | None = None,
) -> StaffWorkforceEvent | None:
    """Resolve an immutable operation receipt before consulting current projections."""

    value = session.scalar(
        select(StaffWorkforceEvent).where(
            StaffWorkforceEvent.organization_id == organization_id,
            StaffWorkforceEvent.operation_id == operation_id,
        )
    )
    if value is None:
        return None
    if value.actor_user_id != session.info.get("rls_user_id"):
        # An operation receipt is private to the principal that created it.
        # Return the same not-found shape as an inaccessible exchange object so
        # an operation UUID cannot become a same-tenant response oracle.
        raise HTTPException(404, "Operation receipt not found")
    stored_request = (value.payload or {}).get("request", value.payload or {})
    if (
        value.entity_type != entity_type
        or value.event_type != event_type
        or (entity_id is not None and value.entity_id != entity_id)
        or stored_request != request_payload
    ):
        raise HTTPException(409, detail={"code": "operation_reused"})
    return value


def workforce_receipt_payload(request_payload: dict, **result) -> dict:
    return {"request": request_payload, **result}


def require_expected(value, expected: datetime) -> None:
    if stored_utc(value.updated_at) != stored_utc(expected):
        raise HTTPException(
            409,
            detail={
                "code": "stale_exchange_resource",
                "current_updated_at": stored_utc(value.updated_at).isoformat(),
            },
        )


def rotation_row(
    session: Session, organization_id: UUID, pattern_id: UUID, *, lock: bool = False
) -> StaffRotationPattern:
    statement = select(StaffRotationPattern).where(
        StaffRotationPattern.organization_id == organization_id,
        StaffRotationPattern.id == pattern_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Rotation pattern not found")
    return value


def open_shift_row(
    session: Session, organization_id: UUID, open_shift_id: UUID, *, lock: bool = False
) -> StaffOpenShift:
    statement = select(StaffOpenShift).where(
        StaffOpenShift.organization_id == organization_id,
        StaffOpenShift.id == open_shift_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Open shift not found")
    return value


def engagement_row(
    session: Session, organization_id: UUID, engagement_id: UUID, *, lock: bool = False
) -> StaffOpenShiftEngagement:
    statement = select(StaffOpenShiftEngagement).where(
        StaffOpenShiftEngagement.organization_id == organization_id,
        StaffOpenShiftEngagement.id == engagement_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Open-shift engagement not found")
    return value


def swap_row(
    session: Session, organization_id: UUID, swap_id: UUID, *, lock: bool = False
) -> StaffShiftSwapRequest:
    statement = select(StaffShiftSwapRequest).where(
        StaffShiftSwapRequest.organization_id == organization_id,
        StaffShiftSwapRequest.id == swap_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Shift swap not found")
    return value


def _membership_user(
    session: Session, organization_id: UUID, membership_id: UUID
) -> tuple[OrganizationMembership, User, Role]:
    row = session.execute(
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
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Staff member not found")
    return row


def _display_name(user: User) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def canonical_rotation_slots(
    session: Session,
    organization_id: UUID,
    facility_id: UUID,
    cycle_weeks: int,
    slots,
) -> list[dict]:
    if not 1 <= cycle_weeks <= 8:
        raise HTTPException(422, detail={"code": "invalid_rotation_cycle"})
    seen_ids: set[str] = set()
    lanes: dict[tuple[UUID, int, int], list[tuple[time, time]]] = {}
    result: list[dict] = []
    for slot in slots:
        slot_id = str(slot.slot_id)
        if slot_id in seen_ids:
            raise HTTPException(422, detail={"code": "duplicate_rotation_slot_id"})
        seen_ids.add(slot_id)
        if slot.cycle_week >= cycle_weeks:
            raise HTTPException(422, detail={"code": "rotation_slot_outside_cycle"})
        start = parse_local_time(slot.start_local)
        end = parse_local_time(slot.end_local)
        if end <= start:
            raise HTTPException(422, detail={"code": "overnight_rotation_slot"})
        membership, _, _, _ = validate_assignment(
            session,
            organization_id,
            staff_user_id=slot.staff_user_id,
            facility_id=facility_id,
            room_id=slot.room_id,
        )
        lane = lanes.setdefault((membership.id, slot.cycle_week, slot.weekday), [])
        if any(
            previous_start < end and previous_end > start for previous_start, previous_end in lane
        ):
            raise HTTPException(422, detail={"code": "overlapping_rotation_slots"})
        lane.append((start, end))
        result.append(
            {
                "slot_id": slot_id,
                "cycle_week": slot.cycle_week,
                "weekday": slot.weekday,
                "membership_id": str(membership.id),
                "room_id": str(slot.room_id) if slot.room_id else None,
                "start_local": start.strftime("%H:%M"),
                "end_local": end.strftime("%H:%M"),
                "notes": clean_optional_text(slot.notes),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            item["cycle_week"],
            item["weekday"],
            item["start_local"],
            item["membership_id"],
            item["slot_id"],
        ),
    )


def rotation_snapshot_digest(pattern: StaffRotationPattern) -> str:
    value = {
        "id": str(pattern.id),
        "facility_id": str(pattern.facility_id),
        "name": pattern.name,
        "version": pattern.version,
        "anchor_date": pattern.anchor_week_start.isoformat(),
        "cycle_weeks": pattern.cycle_length_weeks,
        "slots": pattern.slots or [],
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def rotation_response(session: Session, pattern: StaffRotationPattern) -> RotationPatternResponse:
    facility = facility_row(session, pattern.organization_id, pattern.facility_id, active=False)
    slots: list[RotationSlotResponse] = []
    for raw in pattern.slots or []:
        membership, user, _ = _membership_user(
            session, pattern.organization_id, UUID(raw["membership_id"])
        )
        slots.append(
            RotationSlotResponse(
                slot_id=UUID(raw["slot_id"]),
                cycle_week=raw["cycle_week"],
                weekday=raw["weekday"],
                membership_id=membership.id,
                staff_user_id=user.id,
                room_id=UUID(raw["room_id"]) if raw.get("room_id") else None,
                start_local=raw["start_local"],
                end_local=raw["end_local"],
                notes=raw.get("notes"),
            )
        )
    return RotationPatternResponse(
        id=pattern.id,
        organization_id=pattern.organization_id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        name=pattern.name,
        version=pattern.version,
        anchor_date=pattern.anchor_week_start,
        cycle_weeks=pattern.cycle_length_weeks,
        slots=slots,
        status=pattern.status,
        snapshot_digest=pattern.snapshot_digest,
        recorded_create_operation_id=pattern.create_operation_id,
        recorded_last_operation_id=pattern.last_operation_id,
        created_by_user_id=pattern.created_by_user_id,
        activated_at=stored_optional_utc(pattern.activated_at),
        activated_by_user_id=pattern.activated_by_user_id,
        retired_at=stored_optional_utc(pattern.retired_at),
        retired_by_user_id=pattern.retired_by_user_id,
        retirement_reason=pattern.retirement_reason,
        created_at=stored_utc(pattern.created_at),
        updated_at=stored_utc(pattern.updated_at),
        can_edit=pattern.status == "draft",
        can_activate=pattern.status == "draft",
        can_retire=pattern.status == "active",
        can_preview=pattern.status == "active",
        can_generate=pattern.status == "active",
    )


def _interval_conflict(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
    start: datetime,
    end: datetime,
    *,
    exclude_ids: set[UUID] | None = None,
) -> bool:
    statement = select(ScheduledStaffShift.id).where(
        ScheduledStaffShift.organization_id == organization_id,
        ScheduledStaffShift.membership_id == membership_id,
        ScheduledStaffShift.status != "cancelled",
        ScheduledStaffShift.scheduled_start_at < end,
        ScheduledStaffShift.scheduled_end_at > start,
    )
    if exclude_ids:
        statement = statement.where(ScheduledStaffShift.id.not_in(exclude_ids))
    return session.scalar(statement.limit(1)) is not None


def build_rotation_preview(
    session: Session,
    pattern: StaffRotationPattern,
    start_date: date,
    end_date: date,
) -> RotationPreviewResponse:
    if end_date < start_date or (end_date - start_date).days + 1 > MAX_PREVIEW_DAYS:
        raise HTTPException(422, detail={"code": "invalid_rotation_preview_range"})
    occurrences: list[RotationOccurrence] = []
    issues: list[RotationIssue] = []
    facility = facility_row(session, pattern.organization_id, pattern.facility_id)
    candidate_count = 0
    current = start_date
    while current <= end_date:
        days_from_anchor = (current - pattern.anchor_week_start).days
        cycle_week = (days_from_anchor // 7) % pattern.cycle_length_weeks
        for raw in pattern.slots or []:
            if raw["cycle_week"] != cycle_week or raw["weekday"] != current.weekday():
                continue
            candidate_count += 1
            if candidate_count > MAX_OCCURRENCES:
                raise HTTPException(422, detail={"code": "rotation_occurrence_limit"})
            slot_id = UUID(raw["slot_id"])
            key = f"{slot_id}:{current.isoformat()}"
            membership_id = UUID(raw["membership_id"])
            membership, user, role = _membership_user(
                session, pattern.organization_id, membership_id
            )
            try:
                start = resolve_local_datetime(
                    facility, current, parse_local_time(raw["start_local"])
                )
                end = resolve_local_datetime(facility, current, parse_local_time(raw["end_local"]))
            except HTTPException as error:
                issues.append(
                    RotationIssue(
                        code=(error.detail or {}).get("code", "invalid_local_time"),
                        message="The local shift time is unavailable on this date.",
                        slot_id=slot_id,
                        occurrence_key=key,
                        service_date=current,
                    )
                )
                continue
            room_id = UUID(raw["room_id"]) if raw.get("room_id") else None
            reasons: list[tuple[str, str]] = []
            try:
                validate_assignment(
                    session,
                    pattern.organization_id,
                    staff_user_id=user.id,
                    facility_id=pattern.facility_id,
                    room_id=room_id,
                )
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, dict) else {}
                reasons.append(
                    (
                        detail.get("code", "inactive_rotation_assignment"),
                        "The current staff or room assignment no longer permits this slot.",
                    )
                )
            if (
                membership.status != "active"
                or not user.is_active
                or "shift:clock" not in set(role.permissions or [])
            ) and not any(code == "inactive_staff" for code, _ in reasons):
                reasons.append(("inactive_staff", "The assigned staff account is not active."))
            if room_id is not None:
                room = room_row(
                    session, pattern.organization_id, pattern.facility_id, room_id, active=False
                )
                if not room.is_active:
                    reasons.append(("inactive_room", "The assigned room is inactive."))
            else:
                room = None
            if approved_leave_conflict(session, pattern.organization_id, membership_id, start, end):
                reasons.append(
                    ("approved_time_off_conflict", "Approved leave overlaps this shift.")
                )
            if _interval_conflict(session, pattern.organization_id, membership_id, start, end):
                reasons.append(("overlapping_schedule", "Another scheduled shift overlaps."))
            for code, message in reasons:
                issues.append(
                    RotationIssue(
                        code=code,
                        message=message,
                        slot_id=slot_id,
                        occurrence_key=key,
                        service_date=current,
                    )
                )
            occurrences.append(
                RotationOccurrence(
                    occurrence_key=key,
                    slot_id=slot_id,
                    service_date=current,
                    membership_id=membership_id,
                    staff_user_id=user.id,
                    staff_display_name=_display_name(user),
                    room_id=room_id,
                    room_name=room.name if room else None,
                    scheduled_start_at=start,
                    scheduled_end_at=end,
                    notes=raw.get("notes"),
                )
            )
        current += timedelta(days=1)
    sorted_issues = sorted(
        issues,
        key=lambda item: (
            item.service_date or date.min,
            item.occurrence_key or "",
            item.code,
            item.message,
        ),
    )
    digest_payload = {
        "snapshot": rotation_snapshot_digest(pattern),
        "facility_timezone": facility.timezone,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "occurrences": [item.model_dump(mode="json") for item in occurrences],
        "issues": [item.model_dump(mode="json") for item in sorted_issues],
        "can_generate": not sorted_issues,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RotationPreviewResponse(
        pattern_id=pattern.id,
        snapshot_digest=digest,
        start_date=start_date,
        end_date=end_date,
        occurrences=occurrences,
        total=len(occurrences),
        issues=sorted_issues,
        can_generate=not sorted_issues,
        generated_at=datetime.now(UTC),
    )


def schedule_summary(session: Session, schedule: ScheduledStaffShift) -> ExchangeScheduleSummary:
    _, user, _ = _membership_user(session, schedule.organization_id, schedule.membership_id)
    facility = facility_row(session, schedule.organization_id, schedule.facility_id, active=False)
    room = room_row(
        session, schedule.organization_id, schedule.facility_id, schedule.room_id, active=False
    )
    return ExchangeScheduleSummary(
        id=schedule.id,
        membership_id=schedule.membership_id,
        staff_display_name=_display_name(user),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=schedule.room_id,
        room_name=room.name if room else None,
        scheduled_start_at=stored_utc(schedule.scheduled_start_at),
        scheduled_end_at=stored_utc(schedule.scheduled_end_at),
        updated_at=stored_utc(schedule.updated_at),
    )


def candidate_eligibility(
    session: Session,
    organization_id: UUID,
    membership_id: UUID,
    *,
    facility_id: UUID,
    room_id: UUID | None,
    start: datetime,
    end: datetime,
    exclude_schedule_ids: set[UUID] | None = None,
) -> tuple[User, list[str]]:
    membership, user, role = _membership_user(session, organization_id, membership_id)
    reasons: list[str] = []
    if (
        session.scalar(
            select(Facility.id).where(
                Facility.organization_id == organization_id,
                Facility.id == facility_id,
                Facility.status == "active",
            )
        )
        is None
    ):
        reasons.append("inactive_facility")
    elif (
        room_id is not None
        and session.scalar(
            select(Room.id).where(
                Room.organization_id == organization_id,
                Room.facility_id == facility_id,
                Room.id == room_id,
                Room.is_active.is_(True),
            )
        )
        is None
    ):
        reasons.append("inactive_room")
    if (
        membership.status != "active"
        or not user.is_active
        or "shift:clock" not in set(role.permissions or [])
    ):
        reasons.append("inactive_staff")
    assignment_filters = [
        MembershipRoomAssignment.organization_id == organization_id,
        MembershipRoomAssignment.membership_id == membership_id,
        MembershipRoomAssignment.facility_id == facility_id,
        MembershipRoomAssignment.is_active.is_(True),
    ]
    if room_id is not None:
        assignment_filters.append(MembershipRoomAssignment.room_id == room_id)
    if (
        role.key not in {"owner", "administrator"}
        and session.scalar(select(MembershipRoomAssignment.id).where(*assignment_filters).limit(1))
        is None
    ):
        reasons.append("staff_scope_mismatch")
    if approved_leave_conflict(session, organization_id, membership_id, start, end):
        reasons.append("approved_time_off_conflict")
    if _interval_conflict(
        session,
        organization_id,
        membership_id,
        start,
        end,
        exclude_ids=exclude_schedule_ids,
    ):
        reasons.append("overlapping_schedule")
    return user, reasons


def engagement_response(
    session: Session,
    value: StaffOpenShiftEngagement,
    *,
    now: datetime | None = None,
    capability_scope: str = "none",
) -> OpenShiftEngagementResponse:
    _, user, _ = _membership_user(session, value.organization_id, value.membership_id)
    generated_at = now or datetime.now(UTC)
    expires = stored_optional_utc(value.expires_at)
    is_expired = bool(
        value.kind == "offer"
        and value.status == "pending"
        and expires is not None
        and expires <= stored_utc(generated_at)
    )
    open_shift = session.scalar(
        select(StaffOpenShift).where(
            StaffOpenShift.organization_id == value.organization_id,
            StaffOpenShift.id == value.open_shift_id,
        )
    )
    self_offer_actionable = bool(
        open_shift is not None
        and open_shift.status == "open"
        and stored_utc(open_shift.starts_at) > stored_utc(generated_at)
    )
    return OpenShiftEngagementResponse(
        id=value.id,
        organization_id=value.organization_id,
        open_shift_id=value.open_shift_id,
        membership_id=value.membership_id,
        staff_user_id=user.id,
        staff_display_name=_display_name(user),
        kind=value.kind,
        status=value.status,
        note=value.note,
        response_note=value.terminal_reason,
        source_interest_id=value.source_interest_id,
        converted_offer_id=value.converted_offer_id,
        expires_at=expires,
        is_expired=is_expired,
        resulting_schedule_id=value.result_schedule_id,
        recorded_create_operation_id=value.create_operation_id,
        recorded_last_operation_id=value.last_operation_id,
        can_withdraw=(
            value.status == "pending"
            and (
                (capability_scope == "self" and value.kind == "interest")
                or (capability_scope == "manager" and value.kind == "offer")
            )
        ),
        can_accept=(
            capability_scope == "self"
            and value.kind == "offer"
            and value.status == "pending"
            and not is_expired
            and self_offer_actionable
        ),
        can_decline=(
            capability_scope == "self"
            and value.kind == "offer"
            and value.status == "pending"
            and not is_expired
            and self_offer_actionable
        ),
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def open_shift_response(
    session: Session,
    value: StaffOpenShift,
    *,
    viewer_membership_id: UUID | None = None,
    now: datetime | None = None,
) -> OpenShiftResponse:
    generated_at = now or datetime.now(UTC)
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    room = room_row(session, value.organization_id, value.facility_id, value.room_id, active=False)
    my_engagement = None
    my_engagements: list[OpenShiftEngagementResponse] = []
    reasons: list[str] = []
    if viewer_membership_id is not None:
        engagement_values = list(
            session.scalars(
                select(StaffOpenShiftEngagement)
                .where(
                    StaffOpenShiftEngagement.organization_id == value.organization_id,
                    StaffOpenShiftEngagement.open_shift_id == value.id,
                    StaffOpenShiftEngagement.membership_id == viewer_membership_id,
                )
                .order_by(
                    StaffOpenShiftEngagement.created_at.desc(),
                    StaffOpenShiftEngagement.id.desc(),
                )
                .limit(MAX_OCCURRENCES + 1)
            )
        )
        if len(engagement_values) > MAX_OCCURRENCES:
            raise HTTPException(
                422,
                detail={
                    "code": "list_too_large",
                    "max_items": MAX_OCCURRENCES,
                },
            )
        my_engagements = [
            engagement_response(session, engagement, now=generated_at, capability_scope="self")
            for engagement in engagement_values
        ]
        my_engagement = my_engagements[0] if my_engagements else None
        _, reasons = candidate_eligibility(
            session,
            value.organization_id,
            viewer_membership_id,
            facility_id=value.facility_id,
            room_id=value.room_id,
            start=stored_utc(value.starts_at),
            end=stored_utc(value.ends_at),
            exclude_schedule_ids={value.source_schedule_id} if value.source_schedule_id else None,
        )
        if value.source_schedule_id is not None:
            source_membership_id = session.scalar(
                select(ScheduledStaffShift.membership_id).where(
                    ScheduledStaffShift.organization_id == value.organization_id,
                    ScheduledStaffShift.id == value.source_schedule_id,
                )
            )
            if source_membership_id == viewer_membership_id:
                reasons.append("source_educator_ineligible")
    winner = (
        session.scalar(
            select(StaffOpenShiftEngagement).where(
                StaffOpenShiftEngagement.organization_id == value.organization_id,
                StaffOpenShiftEngagement.open_shift_id == value.id,
                StaffOpenShiftEngagement.status == "accepted",
                StaffOpenShiftEngagement.result_schedule_id == value.result_schedule_id,
            )
        )
        if value.result_schedule_id
        else None
    )
    has_blocking_engagement = any(
        engagement.status == "accepted"
        or (
            engagement.status == "pending"
            and (engagement.kind == "interest" or not engagement.is_expired)
        )
        for engagement in my_engagements
    )
    starts_in_future = stored_utc(value.starts_at) > stored_utc(generated_at)
    can_interest = (
        viewer_membership_id is not None
        and value.status == "open"
        and starts_in_future
        and not reasons
        and not has_blocking_engagement
    )
    return OpenShiftResponse(
        id=value.id,
        organization_id=value.organization_id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=value.room_id,
        room_name=room.name if room else None,
        source_schedule_id=value.source_schedule_id,
        scheduled_start_at=stored_utc(value.starts_at),
        scheduled_end_at=stored_utc(value.ends_at),
        status=value.status,
        public_note=value.notes,
        is_replacement=value.source_schedule_id is not None,
        eligibility_reasons=reasons,
        can_express_interest=can_interest,
        my_engagement=my_engagement,
        my_engagements=my_engagements,
        recorded_create_operation_id=value.create_operation_id,
        recorded_last_operation_id=value.last_operation_id,
        created_by_user_id=value.created_by_user_id,
        posted_at=stored_optional_utc(value.posted_at),
        posted_by_user_id=value.posted_by_user_id,
        filled_at=stored_optional_utc(value.filled_at),
        filled_engagement_id=winner.id if winner else None,
        filled_schedule_id=value.result_schedule_id,
        cancelled_at=stored_optional_utc(value.cancelled_at),
        cancelled_by_user_id=value.cancelled_by_user_id,
        cancellation_reason=value.cancellation_reason,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
        can_edit=value.status == "draft" and starts_in_future,
        can_post=value.status == "draft" and starts_in_future,
        can_cancel=value.status in {"draft", "open"},
    )


def self_open_shift_response(
    session: Session,
    value: StaffOpenShift,
    *,
    viewer_membership_id: UUID,
    now: datetime | None = None,
) -> SelfOpenShiftResponse:
    manager_projection = open_shift_response(
        session, value, viewer_membership_id=viewer_membership_id, now=now
    )
    safe_fields = {
        "id",
        "organization_id",
        "facility_id",
        "facility_name",
        "facility_timezone",
        "room_id",
        "room_name",
        "source_schedule_id",
        "scheduled_start_at",
        "scheduled_end_at",
        "status",
        "public_note",
        "is_replacement",
        "eligibility_reasons",
        "can_express_interest",
        "my_engagement",
        "my_engagements",
        "recorded_create_operation_id",
        "recorded_last_operation_id",
        "created_at",
        "updated_at",
    }
    return SelfOpenShiftResponse(**manager_projection.model_dump(include=safe_fields))


def open_shift_candidate(
    session: Session, shift: StaffOpenShift, membership: OrganizationMembership
) -> OpenShiftCandidateResponse:
    user, reasons = candidate_eligibility(
        session,
        shift.organization_id,
        membership.id,
        facility_id=shift.facility_id,
        room_id=shift.room_id,
        start=stored_utc(shift.starts_at),
        end=stored_utc(shift.ends_at),
        exclude_schedule_ids={shift.source_schedule_id} if shift.source_schedule_id else None,
    )
    opted = (
        session.scalar(
            select(StaffSubstituteProfile.id).where(
                StaffSubstituteProfile.organization_id == shift.organization_id,
                StaffSubstituteProfile.facility_id == shift.facility_id,
                StaffSubstituteProfile.membership_id == membership.id,
                StaffSubstituteProfile.is_specified.is_(True),
                StaffSubstituteProfile.is_opted_in.is_(True),
            )
        )
        is not None
    )
    if shift.source_schedule_id:
        source_membership_id = session.scalar(
            select(ScheduledStaffShift.membership_id).where(
                ScheduledStaffShift.organization_id == shift.organization_id,
                ScheduledStaffShift.id == shift.source_schedule_id,
            )
        )
        if source_membership_id == membership.id:
            reasons.append("source_educator_ineligible")
    return OpenShiftCandidateResponse(
        membership_id=membership.id,
        staff_user_id=user.id,
        staff_display_name=_display_name(user),
        substitute_opted_in=opted,
        eligibility="ineligible" if reasons else "eligible",
        eligibility_reasons=reasons,
    )


def substitute_profile_response(
    session: Session, value: StaffSubstituteProfile
) -> SubstituteProfileResponse:
    _, user, _ = _membership_user(session, value.organization_id, value.membership_id)
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    return SubstituteProfileResponse(
        id=value.id,
        organization_id=value.organization_id,
        membership_id=value.membership_id,
        staff_user_id=user.id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        active=value.is_specified and value.is_opted_in,
        note=value.note,
        recorded_operation_id=value.last_operation_id,
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
    )


def substitute_manager_response(
    session: Session, value: StaffSubstituteProfile
) -> SubstituteManagerResponse:
    membership, user, role = _membership_user(session, value.organization_id, value.membership_id)
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    reasons: list[str] = []
    if (
        membership.status != "active"
        or not user.is_active
        or "shift:clock" not in set(role.permissions or [])
    ):
        reasons.append("inactive_staff")
    if (
        role.key not in {"owner", "administrator"}
        and session.scalar(
            select(MembershipRoomAssignment.id).where(
                MembershipRoomAssignment.organization_id == value.organization_id,
                MembershipRoomAssignment.membership_id == value.membership_id,
                MembershipRoomAssignment.facility_id == value.facility_id,
                MembershipRoomAssignment.is_active.is_(True),
            )
        )
        is None
    ):
        reasons.append("staff_scope_mismatch")
    return SubstituteManagerResponse(
        membership_id=value.membership_id,
        staff_user_id=user.id,
        staff_display_name=_display_name(user),
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        eligibility="ineligible" if reasons else "eligible",
        eligibility_reasons=reasons,
    )


def swap_response(
    session: Session,
    value: StaffShiftSwapRequest,
    *,
    viewer_membership_id: UUID | None = None,
) -> ShiftSwapResponse:
    _, requester, _ = _membership_user(
        session, value.organization_id, value.requester_membership_id
    )
    _, counterparty, _ = _membership_user(
        session, value.organization_id, value.counterparty_membership_id
    )
    facility = facility_row(session, value.organization_id, value.facility_id, active=False)
    requester_schedule = session.scalar(
        select(ScheduledStaffShift).where(
            ScheduledStaffShift.organization_id == value.organization_id,
            ScheduledStaffShift.id == value.requester_schedule_id,
        )
    )
    counterparty_schedule = (
        session.scalar(
            select(ScheduledStaffShift).where(
                ScheduledStaffShift.organization_id == value.organization_id,
                ScheduledStaffShift.id == value.counterparty_schedule_id,
            )
        )
        if value.counterparty_schedule_id
        else None
    )
    if requester_schedule is None or (
        value.counterparty_schedule_id and counterparty_schedule is None
    ):
        raise HTTPException(409, detail={"code": "swap_schedule_history_missing"})
    is_counterparty = viewer_membership_id == value.counterparty_membership_id
    is_requester = viewer_membership_id == value.requester_membership_id
    return ShiftSwapResponse(
        id=value.id,
        organization_id=value.organization_id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        kind=value.kind,
        status=value.status,
        requester_membership_id=value.requester_membership_id,
        requester_staff_user_id=requester.id,
        requester_display_name=_display_name(requester),
        counterparty_membership_id=value.counterparty_membership_id,
        counterparty_staff_user_id=counterparty.id,
        counterparty_display_name=_display_name(counterparty),
        requester_schedule_id=value.requester_schedule_id,
        counterparty_schedule_id=value.counterparty_schedule_id,
        requester_schedule=schedule_summary(session, requester_schedule),
        counterparty_schedule=(
            schedule_summary(session, counterparty_schedule) if counterparty_schedule else None
        ),
        note=value.note,
        counterparty_response_note=value.counterparty_response_note,
        manager_decision_reason=value.manager_decision_reason,
        cancellation_reason=value.cancellation_reason,
        requester_replacement_schedule_id=value.requester_replacement_schedule_id,
        counterparty_replacement_schedule_id=value.counterparty_replacement_schedule_id,
        recorded_create_operation_id=value.create_operation_id,
        recorded_last_operation_id=value.last_operation_id,
        counterparty_responded_at=stored_optional_utc(value.counterparty_responded_at),
        manager_decided_at=stored_optional_utc(value.manager_decided_at),
        cancelled_at=stored_optional_utc(value.cancelled_at),
        created_at=stored_utc(value.created_at),
        updated_at=stored_utc(value.updated_at),
        can_counterparty_accept=is_counterparty and value.status == "pending_counterparty",
        can_counterparty_decline=is_counterparty and value.status == "pending_counterparty",
        can_cancel=is_requester and value.status in {"pending_counterparty", "pending_manager"},
        can_approve=viewer_membership_id is None and value.status == "pending_manager",
        can_reject=viewer_membership_id is None and value.status == "pending_manager",
    )


def swap_candidate(
    session: Session,
    source: ScheduledStaffShift,
    membership: OrganizationMembership,
    *,
    kind: str,
    counterparty_schedule: ScheduledStaffShift | None,
    exclude_swap_id: UUID | None = None,
) -> SwapCandidateResponse:
    _, user, _ = _membership_user(session, source.organization_id, membership.id)
    exclusions = {source.id}
    if counterparty_schedule:
        exclusions.add(counterparty_schedule.id)
    _, reasons = candidate_eligibility(
        session,
        source.organization_id,
        membership.id,
        facility_id=source.facility_id,
        room_id=source.room_id,
        start=stored_utc(source.scheduled_start_at),
        end=stored_utc(source.scheduled_end_at),
        exclude_schedule_ids=exclusions,
    )
    if counterparty_schedule and counterparty_schedule.membership_id != membership.id:
        reasons.append("counterparty_schedule_owner_mismatch")
    if counterparty_schedule:
        if (
            counterparty_schedule.status != "published"
            or counterparty_schedule.response_status != "acknowledged"
            or stored_utc(counterparty_schedule.scheduled_start_at) <= datetime.now(UTC)
            or counterparty_schedule.facility_id != source.facility_id
            or has_clock_link(session, source.organization_id, counterparty_schedule.id)
            or schedule_exchange_pending(
                session,
                source.organization_id,
                counterparty_schedule.id,
                exclude_swap_id=exclude_swap_id,
            )
        ):
            reasons.append("counterparty_schedule_ineligible")
        _, reverse_reasons = candidate_eligibility(
            session,
            source.organization_id,
            source.membership_id,
            facility_id=counterparty_schedule.facility_id,
            room_id=counterparty_schedule.room_id,
            start=stored_utc(counterparty_schedule.scheduled_start_at),
            end=stored_utc(counterparty_schedule.scheduled_end_at),
            exclude_schedule_ids=exclusions,
        )
        reasons.extend(f"requester_{reason}" for reason in reverse_reasons)
    schedule_key = counterparty_schedule.id if counterparty_schedule else "cover"
    return SwapCandidateResponse(
        candidate_key=f"{kind}:{membership.id}:{schedule_key}",
        kind=kind,
        counterparty_membership_id=membership.id,
        counterparty_staff_user_id=user.id,
        counterparty_display_name=_display_name(user),
        counterparty_schedule_id=counterparty_schedule.id if counterparty_schedule else None,
        counterparty_schedule=(
            schedule_summary(session, counterparty_schedule) if counterparty_schedule else None
        ),
        eligibility_reasons=reasons,
        can_propose=not reasons,
    )


def has_clock_link(session: Session, organization_id: UUID, schedule_id: UUID) -> bool:
    return (
        session.scalar(
            select(StaffShift.id).where(
                StaffShift.organization_id == organization_id,
                StaffShift.scheduled_shift_id == schedule_id,
            )
        )
        is not None
    )


def pending_swap_for_schedule(
    session: Session, organization_id: UUID, schedule_id: UUID, *, exclude_id: UUID | None = None
) -> bool:
    statement = select(StaffShiftSwapRequest.id).where(
        StaffShiftSwapRequest.organization_id == organization_id,
        StaffShiftSwapRequest.status.in_({"pending_counterparty", "pending_manager"}),
        or_(
            StaffShiftSwapRequest.requester_schedule_id == schedule_id,
            StaffShiftSwapRequest.counterparty_schedule_id == schedule_id,
        ),
    )
    if exclude_id:
        statement = statement.where(StaffShiftSwapRequest.id != exclude_id)
    return session.scalar(statement.limit(1)) is not None


def schedule_exchange_pending(
    session: Session,
    organization_id: UUID,
    schedule_id: UUID,
    *,
    exclude_open_shift_id: UUID | None = None,
    exclude_swap_id: UUID | None = None,
) -> bool:
    """Return whether a source schedule is reserved by either exchange workflow."""

    open_statement = select(StaffOpenShift.id).where(
        StaffOpenShift.organization_id == organization_id,
        StaffOpenShift.source_schedule_id == schedule_id,
        StaffOpenShift.status.in_({"draft", "open"}),
    )
    if exclude_open_shift_id is not None:
        open_statement = open_statement.where(StaffOpenShift.id != exclude_open_shift_id)
    if session.scalar(open_statement.limit(1)) is not None:
        return True
    return pending_swap_for_schedule(
        session,
        organization_id,
        schedule_id,
        exclude_id=exclude_swap_id,
    )
