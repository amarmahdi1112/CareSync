"""Derived tenant action queue for incomplete or contradictory child records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.basic.dependencies import ChildcareReadContext
from app.api.dependencies import SessionDependency
from app.basic.models import (
    Child,
    EmergencyContact,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Program,
    Room,
)
from app.basic.schemas import (
    ChildRecordReadinessCode,
    ChildRecordReadinessCounts,
    ChildRecordReadinessItem,
    ChildRecordReadinessResponse,
    ChildRecordReadinessSeverity,
)

router = APIRouter(tags=["child record readiness"])
OPEN_STATUSES = ("pending", "active", "paused")


def _months(birth_date: date, as_of: date) -> int:
    value = (as_of.year - birth_date.year) * 12 + as_of.month - birth_date.month
    return value - (1 if as_of.day < birth_date.day else 0)


def _facility_date(facility: Facility) -> date | None:
    try:
        return datetime.now(UTC).astimezone(ZoneInfo(facility.timezone)).date()
    except ZoneInfoNotFoundError:
        return None


def _child_display_name(child: Child) -> str:
    """Return a bounded human label for an operator-facing readiness item."""

    value = " ".join(
        part.strip()
        for part in (child.first_name, child.middle_name, child.last_name)
        if part and part.strip()
    )
    return value if len(value) <= 160 else f"{value[:157].rstrip()}…"


def _item(
    code: ChildRecordReadinessCode,
    severity: ChildRecordReadinessSeverity,
    *,
    family_id: UUID | None = None,
    child_id: UUID | None = None,
    enrollment_id: UUID | None = None,
    facility_id: UUID | None = None,
    title: str,
    message: str,
    action_route: str,
) -> ChildRecordReadinessItem:
    parts = [code]
    parts.extend(
        str(value)
        for value in (family_id, child_id, enrollment_id, facility_id)
        if value is not None
    )
    return ChildRecordReadinessItem(
        key=":".join(parts),
        code=code,
        severity=severity,
        family_id=family_id,
        child_id=child_id,
        enrollment_id=enrollment_id,
        facility_id=facility_id,
        title=title,
        message=message,
        action_route=action_route,
    )


@router.get("/child-record-readiness", response_model=ChildRecordReadinessResponse)
def child_record_readiness(
    context: ChildcareReadContext,
    session: SessionDependency,
    severity: Annotated[ChildRecordReadinessSeverity | None, Query()] = None,
    code: Annotated[ChildRecordReadinessCode | None, Query()] = None,
    facility_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChildRecordReadinessResponse:
    organization_id = context.organization.id
    families = list(
        session.scalars(
            select(Family).where(Family.organization_id == organization_id).order_by(Family.id)
        )
    )
    children = list(
        session.scalars(
            select(Child).where(Child.organization_id == organization_id).order_by(Child.id)
        )
    )
    enrollments = list(
        session.scalars(
            select(Enrollment)
            .where(Enrollment.organization_id == organization_id)
            .order_by(Enrollment.id)
        )
    )
    guardians = list(
        session.scalars(
            select(Guardian).where(
                Guardian.organization_id == organization_id,
                Guardian.retired_at.is_(None),
            )
        )
    )
    contacts = list(
        session.scalars(
            select(EmergencyContact).where(
                EmergencyContact.organization_id == organization_id,
                EmergencyContact.retired_at.is_(None),
            )
        )
    )
    facility_rows = {
        value.id: value
        for value in session.scalars(
            select(Facility).where(Facility.organization_id == organization_id)
        )
    }
    program_rows = {
        value.id: value
        for value in session.scalars(
            select(Program).where(Program.organization_id == organization_id)
        )
    }
    room_rows = {
        value.id: value
        for value in session.scalars(select(Room).where(Room.organization_id == organization_id))
    }
    children_by_family: dict[UUID, list[Child]] = defaultdict(list)
    guardians_by_family: dict[UUID, list[Guardian]] = defaultdict(list)
    contacts_by_family: dict[UUID, list[EmergencyContact]] = defaultdict(list)
    enrollment_by_child: dict[UUID, list[Enrollment]] = defaultdict(list)
    for child in children:
        children_by_family[child.family_id].append(child)
    for guardian in guardians:
        guardians_by_family[guardian.family_id].append(guardian)
    for contact in contacts:
        contacts_by_family[contact.family_id].append(contact)
    for enrollment in enrollments:
        enrollment_by_child[enrollment.child_id].append(enrollment)

    items: list[ChildRecordReadinessItem] = []
    for family in families:
        current_guardians = guardians_by_family[family.id]
        if not any(value.is_primary for value in current_guardians):
            items.append(
                _item(
                    "missing_primary_guardian",
                    "warning",
                    family_id=family.id,
                    title="Primary guardian is missing",
                    message="Add a current primary guardian to the family record.",
                    action_route=f"/families/{family.id}",
                )
            )
        if not any(
            (value.cell_phone or "").strip()
            or (value.home_phone or "").strip()
            or (value.work_phone or "").strip()
            for value in current_guardians
        ):
            items.append(
                _item(
                    "unreachable_guardian_telephone",
                    "critical",
                    family_id=family.id,
                    title="No reachable guardian telephone",
                    message="Record at least one current guardian telephone number.",
                    action_route=f"/families/{family.id}",
                )
            )
        if not contacts_by_family[family.id]:
            items.append(
                _item(
                    "missing_emergency_contact",
                    "warning",
                    family_id=family.id,
                    title="Emergency contact is missing",
                    message="Add a dedicated current emergency contact.",
                    action_route=f"/families/{family.id}",
                )
            )
        family_children = children_by_family[family.id]
        family_open = [
            enrollment
            for child in family_children
            for enrollment in enrollment_by_child[child.id]
            if enrollment.status in OPEN_STATUSES
        ]
        if family.status in {"inactive", "archived"} and (
            any(child.is_active for child in family_children) or family_open
        ):
            items.append(
                _item(
                    "inactive_family_active_records",
                    "critical",
                    family_id=family.id,
                    title="Inactive family still has active records",
                    message="Resolve active children and open enrollments before archival.",
                    action_route=f"/families/{family.id}",
                )
            )

    open_counts = Counter(
        enrollment.child_id for enrollment in enrollments if enrollment.status in OPEN_STATUSES
    )
    child_rows = {value.id: value for value in children}
    family_rows = {value.id: value for value in families}
    for child in children:
        if child.immunization_up_to_date is None:
            items.append(
                _item(
                    "unknown_immunization_status",
                    "warning",
                    family_id=child.family_id,
                    child_id=child.id,
                    title="Immunization marker is unknown",
                    message="Review the child health record without inferring an answer.",
                    action_route=f"/children/{child.id}",
                )
            )
        if open_counts[child.id] > 1:
            items.append(
                _item(
                    "duplicate_open_enrollment",
                    "critical",
                    family_id=child.family_id,
                    child_id=child.id,
                    title="Multiple open enrollments need reconciliation",
                    message="End or reconcile duplicate open organization enrollments.",
                    action_route=f"/children/{child.id}",
                )
            )

    for enrollment in enrollments:
        if enrollment.status not in OPEN_STATUSES:
            continue
        child = child_rows.get(enrollment.child_id)
        if child is None:
            continue
        family = family_rows.get(child.family_id)
        # Placement review intentionally excludes non-active families.  A pending
        # family is therefore a family-intake remediation, not a room-selection
        # problem.  Point the operator at the exact family/child/enrollment focus
        # instead of opening a child profile that cannot resolve the blocker.
        if family is not None and family.status == "pending":
            child_name = _child_display_name(child)
            items.append(
                _item(
                    "enrollment_placement_incoherent",
                    "critical",
                    family_id=family.id,
                    child_id=child.id,
                    enrollment_id=enrollment.id,
                    facility_id=enrollment.facility_id,
                    title=f"{child_name}: family activation required",
                    message=(
                        f"{family.name} is Pending, so {child_name}'s open enrollment cannot "
                        "be treated as operational. Open the family status review, confirm "
                        "intake is complete, then change the family to Active; otherwise end "
                        "the child's enrollment."
                    ),
                    action_route=(
                        f"/families/{family.id}?focus=family-status"
                        f"&child_id={child.id}&enrollment_id={enrollment.id}"
                    ),
                )
            )
            continue
        # Inactive and archived families already receive the family-level
        # lifecycle blocker above.  Do not add an unusable room-review link.
        if family is not None and family.status in {"inactive", "archived"}:
            continue
        if enrollment.program_id is None and enrollment.room_id is None:
            items.append(
                _item(
                    "open_unassigned_enrollment",
                    "warning",
                    family_id=child.family_id,
                    child_id=child.id,
                    enrollment_id=enrollment.id,
                    facility_id=enrollment.facility_id,
                    title="Open enrollment needs room review",
                    message="Review DOB-aware room candidates and approve a placement.",
                    action_route=(
                        f"/rooms?facility_id={enrollment.facility_id}"
                        f"&placement_enrollment_id={enrollment.id}"
                    ),
                )
            )
            continue
        facility = facility_rows.get(enrollment.facility_id)
        program = program_rows.get(enrollment.program_id)
        room = room_rows.get(enrollment.room_id)
        facility_today = _facility_date(facility) if facility is not None else None
        effective_date = (
            max(
                enrollment.start_date,
                enrollment.placement_effective_date,
                facility_today,
            )
            if enrollment.placement_effective_date is not None and facility_today is not None
            else None
        )
        age_months = (
            _months(child.date_of_birth, effective_date) if effective_date is not None else None
        )
        coherent = (
            facility is not None
            and program is not None
            and room is not None
            and enrollment.status != "pending"
            and enrollment.program_id is not None
            and enrollment.room_id is not None
            and enrollment.placement_effective_date is not None
            and enrollment.start_date >= child.date_of_birth
            and program.facility_id == enrollment.facility_id
            and room.facility_id == enrollment.facility_id
            and room.program_id == enrollment.program_id
            and child.is_active
            and family is not None
            and family.status == "active"
            and facility.status == "active"
            and program.is_active
            and room.is_active
            and age_months is not None
            and room.minimum_age_months is not None
            and room.maximum_age_months is not None
            and room.minimum_age_months <= age_months <= room.maximum_age_months
        )
        if not coherent:
            items.append(
                _item(
                    "enrollment_placement_incoherent",
                    "critical",
                    family_id=child.family_id,
                    child_id=child.id,
                    enrollment_id=enrollment.id,
                    facility_id=enrollment.facility_id,
                    title="Enrollment placement needs review",
                    message="Facility, program, room, age, or effective-date facts conflict.",
                    action_route=f"/children/{child.id}",
                )
            )

    items.sort(key=lambda item: ({"critical": 0, "warning": 1, "info": 2}[item.severity], item.key))
    family_facilities: dict[UUID, set[UUID]] = defaultdict(set)
    for child in children:
        for enrollment in enrollment_by_child[child.id]:
            if enrollment.status in OPEN_STATUSES:
                family_facilities[child.family_id].add(enrollment.facility_id)
    filtered = [
        item
        for item in items
        if (severity is None or item.severity == severity)
        and (code is None or item.code == code)
        and (
            facility_id is None
            or item.facility_id == facility_id
            or (
                item.facility_id is None
                and item.family_id is not None
                and facility_id in family_facilities[item.family_id]
            )
        )
    ]
    counts = Counter(item.severity for item in filtered)
    return ChildRecordReadinessResponse(
        items=filtered[offset : offset + limit],
        total=len(filtered),
        limit=limit,
        offset=offset,
        counts=ChildRecordReadinessCounts(
            critical=counts["critical"],
            warning=counts["warning"],
            info=counts["info"],
        ),
    )
