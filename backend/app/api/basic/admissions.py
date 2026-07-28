"""Derived, read-only admissions and intake action queue.

The retained childcare schema has no application, waitlist, or admissions
decision entity.  This projection intentionally reports only current record
signals that an organization operator can resolve through existing canonical
childcare commands.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query, Response
from sqlalchemy import and_, select

from app.api.basic.dependencies import ChildcareReadContext
from app.api.dependencies import SessionDependency
from app.basic.admissions_schemas import (
    AdmissionIntakeAction,
    AdmissionIntakeCase,
    AdmissionIntakeChild,
    AdmissionIntakeCounts,
    AdmissionIntakeEnrollment,
    AdmissionIntakeQueueResponse,
    AdmissionIntakeReason,
    AdmissionIntakeReasonCode,
    AdmissionIntakeSeverity,
    AdmissionIntakeStage,
    AdmissionIntakeStageCounts,
)
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

router = APIRouter(prefix="/admissions", tags=["admissions and intake"])

_OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")
_STAGE_ORDER: dict[AdmissionIntakeStage, int] = {
    "record_conflict": 0,
    "family_contacts": 1,
    "child_record": 2,
    "enrollment_setup": 3,
    "family_review": 4,
    "placement_review": 5,
}
_SEVERITY_ORDER: dict[AdmissionIntakeSeverity, int] = {"critical": 0, "warning": 1}
_REASON_ORDER: dict[AdmissionIntakeReasonCode, int] = {
    "pending_family_active_child": 0,
    "pending_family_open_enrollment": 1,
    "duplicate_open_enrollment": 2,
    "family_lifecycle_conflict": 3,
    "inactive_child_open_enrollment": 4,
    "enrollment_date_conflict": 5,
    "facility_unavailable": 6,
    "placement_incomplete": 7,
    "program_unavailable": 8,
    "room_unavailable": 9,
    "placement_effective_date_conflict": 10,
    "room_age_range_missing": 11,
    "child_outside_room_age_range": 12,
    "missing_primary_guardian": 13,
    "unreachable_guardian_telephone": 14,
    "missing_emergency_contact": 15,
    "no_child_record": 16,
    "no_open_enrollment_record": 17,
    "family_pending_manual_review": 18,
    "pending_enrollment_placement_review": 19,
}
_NOTICE = (
    "This read-only queue derives current record signals only. It is not a waitlist, "
    "application decision, document-completeness result, admission certification, or "
    "regulatory compliance determination."
)


def _display_name(child: Child) -> str:
    value = " ".join(
        part.strip()
        for part in (child.first_name, child.middle_name, child.last_name)
        if part and part.strip()
    )
    return value if len(value) <= 160 else f"{value[:157].rstrip()}…"


def _months(birth_date: date, as_of: date) -> int:
    value = (as_of.year - birth_date.year) * 12 + as_of.month - birth_date.month
    return value - (1 if as_of.day < birth_date.day else 0)


def _facility_today(facility: Facility | None, generated_at: datetime) -> date | None:
    if facility is None:
        return None
    try:
        return generated_at.astimezone(ZoneInfo(facility.timezone)).date()
    except ZoneInfoNotFoundError:
        return None


def _family_action(
    family_id: UUID,
    label: str,
    *,
    focus_status: bool = False,
) -> AdmissionIntakeAction:
    suffix = "?focus=family-status" if focus_status else ""
    return AdmissionIntakeAction(label=label, path=f"/families/{family_id}{suffix}")


def _child_action(child_id: UUID, label: str) -> AdmissionIntakeAction:
    return AdmissionIntakeAction(label=label, path=f"/children/{child_id}")


def _placement_action(enrollment: Enrollment, label: str) -> AdmissionIntakeAction:
    return AdmissionIntakeAction(
        label=label,
        path=(
            f"/rooms?facility_id={enrollment.facility_id}&placement_enrollment_id={enrollment.id}"
        ),
    )


def _reason(
    code: AdmissionIntakeReasonCode,
    stage: AdmissionIntakeStage,
    severity: AdmissionIntakeSeverity,
    *,
    title: str,
    instruction: str,
    entity_type: str,
    entity_id: UUID,
    action: AdmissionIntakeAction,
) -> AdmissionIntakeReason:
    return AdmissionIntakeReason(
        code=code,
        stage=stage,
        severity=severity,
        title=title,
        instruction=instruction,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )


def _placement_conflicts(
    family: Family,
    child: Child,
    enrollment: Enrollment,
    facility: Facility | None,
    program: Program | None,
    room: Room | None,
    generated_at: datetime,
) -> list[AdmissionIntakeReason]:
    reasons: list[AdmissionIntakeReason] = []
    child_action = _child_action(child.id, "Review enrollment")
    facility_today = _facility_today(facility, generated_at)

    if family.status in {"inactive", "archived"}:
        reasons.append(
            _reason(
                "family_lifecycle_conflict",
                "record_conflict",
                "critical",
                title="Open enrollment conflicts with family status",
                instruction=(
                    "Review the family lifecycle and end the open enrollment or restore the "
                    "family only when the current records support that change."
                ),
                entity_type="family",
                entity_id=family.id,
                action=_family_action(family.id, "Review family record"),
            )
        )
    if not child.is_active:
        reasons.append(
            _reason(
                "inactive_child_open_enrollment",
                "record_conflict",
                "critical",
                title="Inactive child has an open enrollment",
                instruction=(
                    "Review the child and enrollment records; do not infer that either record "
                    "should be activated or ended."
                ),
                entity_type="child",
                entity_id=child.id,
                action=_child_action(child.id, "Review child record"),
            )
        )
    if enrollment.start_date < child.date_of_birth or (
        enrollment.end_date is not None
        and (
            enrollment.end_date < enrollment.start_date
            or (facility_today is not None and enrollment.end_date < facility_today)
        )
    ):
        reasons.append(
            _reason(
                "enrollment_date_conflict",
                "record_conflict",
                "critical",
                title="Enrollment dates need review",
                instruction=(
                    "Review the recorded birth, start, and end dates. This projection does not "
                    "choose which canonical value should change."
                ),
                entity_type="enrollment",
                entity_id=enrollment.id,
                action=child_action,
            )
        )
    if facility is None or facility.status != "active" or facility_today is None:
        reasons.append(
            _reason(
                "facility_unavailable",
                "record_conflict",
                "critical",
                title="Enrollment facility is unavailable",
                instruction=(
                    "Review the enrollment facility and its current operational record before "
                    "using this placement."
                ),
                entity_type="facility",
                entity_id=enrollment.facility_id,
                action=child_action,
            )
        )

    placement_values = (
        enrollment.program_id,
        enrollment.room_id,
        enrollment.placement_effective_date,
    )
    if enrollment.status == "pending":
        if any(value is not None for value in placement_values):
            reasons.append(
                _reason(
                    "placement_incomplete",
                    "record_conflict",
                    "critical",
                    title="Pending enrollment has contradictory placement facts",
                    instruction=(
                        "Review the technical enrollment shell and its room placement facts."
                    ),
                    entity_type="enrollment",
                    entity_id=enrollment.id,
                    action=child_action,
                )
            )
        return reasons

    if not all(value is not None for value in placement_values):
        reasons.append(
            _reason(
                "placement_incomplete",
                "record_conflict",
                "critical",
                title="Open enrollment has incomplete placement facts",
                instruction=(
                    "Inspect the assigned enrollment on the child record. The current command "
                    "surface cannot reassign this placement; use only its supported correction "
                    "or end controls."
                ),
                entity_type="enrollment",
                entity_id=enrollment.id,
                action=child_action,
            )
        )
        return reasons

    if program is None or not program.is_active or program.facility_id != enrollment.facility_id:
        reasons.append(
            _reason(
                "program_unavailable",
                "record_conflict",
                "critical",
                title="Enrollment program is unavailable",
                instruction=(
                    "Inspect the assigned program on the child record. The current command "
                    "surface cannot reassign it; use only supported enrollment controls."
                ),
                entity_type="program",
                entity_id=enrollment.program_id,
                action=child_action,
            )
        )
    if (
        room is None
        or not room.is_active
        or room.facility_id != enrollment.facility_id
        or room.program_id != enrollment.program_id
    ):
        reasons.append(
            _reason(
                "room_unavailable",
                "record_conflict",
                "critical",
                title="Enrollment room is unavailable",
                instruction=(
                    "Inspect the assigned room on the child record. The current command surface "
                    "cannot reassign it; use only supported enrollment controls."
                ),
                entity_type="room",
                entity_id=enrollment.room_id,
                action=child_action,
            )
        )
    if enrollment.placement_effective_date < enrollment.start_date or (
        enrollment.end_date is not None
        and enrollment.end_date < enrollment.placement_effective_date
    ):
        reasons.append(
            _reason(
                "placement_effective_date_conflict",
                "record_conflict",
                "critical",
                title="Placement effective date needs review",
                instruction=(
                    "Inspect the assigned effective date on the child record. This queue cannot "
                    "rewrite it; use only supported enrollment correction or end controls."
                ),
                entity_type="enrollment",
                entity_id=enrollment.id,
                action=child_action,
            )
        )

    if room is not None and room.is_active:
        if room.minimum_age_months is None or room.maximum_age_months is None:
            reasons.append(
                _reason(
                    "room_age_range_missing",
                    "record_conflict",
                    "critical",
                    title="Room age interval is not configured",
                    instruction=(
                        "Inspect the assigned room on the child record. Correct room configuration "
                        "separately or use supported enrollment controls; this queue cannot "
                        "reassign the placement."
                    ),
                    entity_type="room",
                    entity_id=room.id,
                    action=child_action,
                )
            )
        elif facility_today is not None:
            effective_date = max(
                enrollment.start_date,
                enrollment.placement_effective_date,
                facility_today,
            )
            age_months = _months(child.date_of_birth, effective_date)
            if not room.minimum_age_months <= age_months <= room.maximum_age_months:
                reasons.append(
                    _reason(
                        "child_outside_room_age_range",
                        "record_conflict",
                        "critical",
                        title="Child is outside the room age interval",
                        instruction=(
                            "Inspect the assigned room and child record. The current command "
                            "surface cannot reassign this placement; use only supported enrollment "
                            "controls."
                        ),
                        entity_type="child",
                        entity_id=child.id,
                        action=child_action,
                    )
                )
    return reasons


def _latest_updated_at(
    family: Family,
    guardians: list[Guardian],
    contacts: list[EmergencyContact],
    children: list[Child],
    enrollments: list[Enrollment],
    placement_facts: list[Facility | Program | Room],
) -> datetime:
    values = [
        family.updated_at,
        *(value.updated_at for value in guardians),
        *(value.updated_at for value in contacts),
        *(value.updated_at for value in children),
        *(value.updated_at for value in enrollments),
        *(value.updated_at for value in placement_facts),
    ]
    return max(values)


def _reason_sort_key(reason: AdmissionIntakeReason) -> tuple[int, int, int, str]:
    return (
        _STAGE_ORDER[reason.stage],
        _SEVERITY_ORDER[reason.severity],
        _REASON_ORDER[reason.code],
        str(reason.entity_id),
    )


def _deduplicate_reasons(
    reasons: list[AdmissionIntakeReason],
) -> list[AdmissionIntakeReason]:
    unique: dict[tuple[str, str, UUID, str], AdmissionIntakeReason] = {}
    for reason in reasons:
        key = (
            reason.code,
            reason.entity_type,
            reason.entity_id,
            reason.action.path,
        )
        unique.setdefault(key, reason)
    return list(unique.values())


@router.get("/intake-queue", response_model=AdmissionIntakeQueueResponse)
def admissions_intake_queue(
    context: ChildcareReadContext,
    session: SessionDependency,
    response: Response,
    stage: Annotated[AdmissionIntakeStage | None, Query()] = None,
    facility_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdmissionIntakeQueueResponse:
    """Return a deterministic current-record action queue without writing state."""

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Vary"] = "Authorization, X-Organization-ID"

    organization_id = context.organization.id
    generated_at = datetime.now(UTC)
    families = list(
        session.scalars(
            select(Family).where(Family.organization_id == organization_id).order_by(Family.id)
        )
    )
    guardians = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == organization_id,
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.family_id, Guardian.id)
        )
    )
    contacts = list(
        session.scalars(
            select(EmergencyContact)
            .where(
                EmergencyContact.organization_id == organization_id,
                EmergencyContact.retired_at.is_(None),
            )
            .order_by(EmergencyContact.family_id, EmergencyContact.id)
        )
    )
    children = list(
        session.scalars(
            select(Child)
            .where(Child.organization_id == organization_id)
            .order_by(Child.family_id, Child.last_name, Child.first_name, Child.id)
        )
    )
    placement_rows = list(
        session.execute(
            select(Enrollment, Facility, Program, Room)
            .outerjoin(
                Facility,
                and_(
                    Facility.organization_id == Enrollment.organization_id,
                    Facility.id == Enrollment.facility_id,
                ),
            )
            .outerjoin(
                Program,
                and_(
                    Program.organization_id == Enrollment.organization_id,
                    Program.facility_id == Enrollment.facility_id,
                    Program.id == Enrollment.program_id,
                ),
            )
            .outerjoin(
                Room,
                and_(
                    Room.organization_id == Enrollment.organization_id,
                    Room.facility_id == Enrollment.facility_id,
                    Room.id == Enrollment.room_id,
                ),
            )
            .where(Enrollment.organization_id == organization_id)
            .order_by(Enrollment.child_id, Enrollment.id)
        )
    )

    guardians_by_family: dict[UUID, list[Guardian]] = defaultdict(list)
    contacts_by_family: dict[UUID, list[EmergencyContact]] = defaultdict(list)
    children_by_family: dict[UUID, list[Child]] = defaultdict(list)
    placement_by_child: dict[
        UUID, list[tuple[Enrollment, Facility | None, Program | None, Room | None]]
    ] = defaultdict(list)
    for guardian in guardians:
        guardians_by_family[guardian.family_id].append(guardian)
    for contact in contacts:
        contacts_by_family[contact.family_id].append(contact)
    for child in children:
        children_by_family[child.family_id].append(child)
    for enrollment, facility, program, room in placement_rows:
        placement_by_child[enrollment.child_id].append((enrollment, facility, program, room))

    cases: list[AdmissionIntakeCase] = []
    for family in families:
        family_children = children_by_family[family.id]
        open_rows = [
            row
            for child in family_children
            for row in placement_by_child[child.id]
            if row[0].status in _OPEN_ENROLLMENT_STATUSES
        ]
        open_enrollments = [row[0] for row in open_rows]
        open_counts = Counter(value.child_id for value in open_enrollments)
        open_child_ids = set(open_counts)
        child_by_id = {value.id: value for value in family_children}
        active_children = [value for value in family_children if value.is_active]
        active_children_without_open = [
            value for value in active_children if value.id not in open_child_ids
        ]
        reasons: list[AdmissionIntakeReason] = []
        conflicting_enrollment_ids: set[UUID] = set()

        if family.status == "pending":
            for child in active_children:
                reasons.append(
                    _reason(
                        "pending_family_active_child",
                        "record_conflict",
                        "critical",
                        title=(f"{_display_name(child)} is active while the family is Pending"),
                        instruction=(
                            "Review the Pending family lifecycle and active child record. The "
                            "projection does not infer whether the family or child should change."
                        ),
                        entity_type="child",
                        entity_id=child.id,
                        action=_family_action(
                            family.id,
                            "Review family status",
                            focus_status=True,
                        ),
                    )
                )
            for enrollment in open_enrollments:
                reasons.append(
                    _reason(
                        "pending_family_open_enrollment",
                        "record_conflict",
                        "critical",
                        title=(
                            f"{_display_name(child_by_id[enrollment.child_id])} has an open "
                            "enrollment while the family is Pending"
                        ),
                        instruction=(
                            "Review the child enrollment and Pending family lifecycle. Do not "
                            "create another enrollment while this record remains open."
                        ),
                        entity_type="enrollment",
                        entity_id=enrollment.id,
                        action=_child_action(enrollment.child_id, "Review enrollment"),
                    )
                )

        if family.status in {"inactive", "archived"} and active_children:
            reasons.append(
                _reason(
                    "family_lifecycle_conflict",
                    "record_conflict",
                    "critical",
                    title="Inactive family has active child records",
                    instruction=(
                        "Review the family and active child records. This projection does not "
                        "infer which lifecycle value should change."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(family.id, "Review family record"),
                )
            )

        for child_id, count in sorted(open_counts.items(), key=lambda item: str(item[0])):
            if count <= 1:
                continue
            child = child_by_id[child_id]
            reasons.append(
                _reason(
                    "duplicate_open_enrollment",
                    "record_conflict",
                    "critical",
                    title="Child has multiple open enrollments",
                    instruction=(
                        "Review and reconcile the duplicate open enrollment records without "
                        "inferring which record should remain."
                    ),
                    entity_type="child",
                    entity_id=child.id,
                    action=_child_action(child.id, "Review enrollments"),
                )
            )
            conflicting_enrollment_ids.update(
                value.id for value in open_enrollments if value.child_id == child_id
            )

        for enrollment, facility, program, room in open_rows:
            child = child_by_id[enrollment.child_id]
            placement_conflicts = _placement_conflicts(
                family,
                child,
                enrollment,
                facility,
                program,
                room,
                generated_at,
            )
            if placement_conflicts:
                conflicting_enrollment_ids.add(enrollment.id)
                reasons.extend(placement_conflicts)

        has_record_conflict = any(reason.stage == "record_conflict" for reason in reasons)
        candidate = (
            family.status == "pending"
            or (family.status == "active" and bool(active_children_without_open))
            or any(value.status == "pending" for value in open_enrollments)
            or has_record_conflict
        )
        if not candidate:
            continue

        family_guardians = guardians_by_family[family.id]
        family_contacts = contacts_by_family[family.id]
        if not any(value.is_primary for value in family_guardians):
            reasons.append(
                _reason(
                    "missing_primary_guardian",
                    "family_contacts",
                    "warning",
                    title="Primary guardian record needs attention",
                    instruction=(
                        "Review the family record and add a primary guardian when the current "
                        "family facts support it."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(family.id, "Review guardians"),
                )
            )
        if not any(
            (value.cell_phone or "").strip()
            or (value.home_phone or "").strip()
            or (value.work_phone or "").strip()
            for value in family_guardians
        ):
            reasons.append(
                _reason(
                    "unreachable_guardian_telephone",
                    "family_contacts",
                    "warning",
                    title="Guardian telephone record needs attention",
                    instruction=(
                        "Review the family record and record a current guardian telephone when "
                        "one is supplied."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(family.id, "Review guardian contacts"),
                )
            )
        if not family_contacts:
            reasons.append(
                _reason(
                    "missing_emergency_contact",
                    "family_contacts",
                    "warning",
                    title="Emergency contact record needs attention",
                    instruction=(
                        "Review the family record and add a separate current emergency contact "
                        "when supplied by the family."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(family.id, "Review emergency contacts"),
                )
            )

        if family.status == "pending" and not family_children:
            reasons.append(
                _reason(
                    "no_child_record",
                    "child_record",
                    "warning",
                    title="Pending family has no child record",
                    instruction=(
                        "Review the family and create a child record only when the current intake "
                        "facts support that action."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(family.id, "Review family children"),
                )
            )
        elif family.status == "active":
            for child in active_children_without_open:
                reasons.append(
                    _reason(
                        "no_open_enrollment_record",
                        "enrollment_setup",
                        "warning",
                        title=f"{_display_name(child)} has no open enrollment record",
                        instruction=(
                            "Review this child and create an enrollment shell only if the "
                            "organization intends to proceed with placement."
                        ),
                        entity_type="child",
                        entity_id=child.id,
                        action=_child_action(child.id, "Review enrollment records"),
                    )
                )

        if family.status == "pending":
            reasons.append(
                _reason(
                    "family_pending_manual_review",
                    "family_review",
                    "warning",
                    title="Family lifecycle needs manual review",
                    instruction=(
                        "Review the current family, child, and enrollment records. Explicitly "
                        "change family status only when your operational process supports it."
                    ),
                    entity_type="family",
                    entity_id=family.id,
                    action=_family_action(
                        family.id,
                        "Review family status",
                        focus_status=True,
                    ),
                )
            )
        elif family.status == "active":
            for enrollment in open_enrollments:
                if (
                    enrollment.status == "pending"
                    and enrollment.id not in conflicting_enrollment_ids
                ):
                    reasons.append(
                        _reason(
                            "pending_enrollment_placement_review",
                            "placement_review",
                            "warning",
                            title="Pending enrollment needs room review",
                            instruction=(
                                "Review DOB-aware room candidates and explicitly approve a "
                                "placement."
                            ),
                            entity_type="enrollment",
                            entity_id=enrollment.id,
                            action=_placement_action(enrollment, "Review room placement"),
                        )
                    )

        reasons = _deduplicate_reasons(reasons)
        reasons.sort(key=_reason_sort_key)
        if not reasons:
            continue
        relevant_facilities = {value.facility_id for value in open_enrollments}
        if facility_id is not None and facility_id not in relevant_facilities:
            continue

        enrollment_summaries = [
            AdmissionIntakeEnrollment(
                id=enrollment.id,
                child_id=enrollment.child_id,
                facility_id=enrollment.facility_id,
                facility_name=facility.name if facility is not None else None,
                program_id=enrollment.program_id,
                program_name=program.name if program is not None else None,
                room_id=enrollment.room_id,
                room_name=room.name if room is not None else None,
                placement_effective_date=enrollment.placement_effective_date,
                start_date=enrollment.start_date,
                end_date=enrollment.end_date,
                status=enrollment.status,
            )
            for enrollment, facility, program, room in open_rows
        ]
        case_severity: AdmissionIntakeSeverity = (
            "critical" if any(reason.severity == "critical" for reason in reasons) else "warning"
        )
        case = AdmissionIntakeCase(
            key=f"family:{family.id}",
            family_id=family.id,
            family_name=family.name,
            family_status=family.status,
            stage=reasons[0].stage,
            severity=case_severity,
            children=[
                AdmissionIntakeChild(
                    id=child.id,
                    display_name=_display_name(child),
                    is_active=child.is_active,
                )
                for child in family_children
            ],
            enrollments=enrollment_summaries,
            reasons=reasons,
            primary_action=reasons[0].action,
            updated_at=_latest_updated_at(
                family,
                family_guardians,
                family_contacts,
                family_children,
                open_enrollments,
                [
                    value
                    for _, facility, program, room in open_rows
                    for value in (facility, program, room)
                    if value is not None
                ],
            ),
        )
        if stage is None or case.stage == stage:
            cases.append(case)

    cases.sort(
        key=lambda value: (
            _STAGE_ORDER[value.stage],
            value.family_name.casefold(),
            str(value.family_id),
        )
    )
    severity_counts = Counter(value.severity for value in cases)
    stage_counts = Counter(value.stage for value in cases)
    counts = AdmissionIntakeCounts(
        total=len(cases),
        critical=severity_counts["critical"],
        warning=severity_counts["warning"],
        by_stage=AdmissionIntakeStageCounts(
            family_contacts=stage_counts["family_contacts"],
            child_record=stage_counts["child_record"],
            enrollment_setup=stage_counts["enrollment_setup"],
            record_conflict=stage_counts["record_conflict"],
            family_review=stage_counts["family_review"],
            placement_review=stage_counts["placement_review"],
        ),
    )
    return AdmissionIntakeQueueResponse(
        organization_id=organization_id,
        generated_at=generated_at,
        notice=_NOTICE,
        items=cases[offset : offset + limit],
        total=len(cases),
        limit=limit,
        offset=offset,
        counts=counts,
    )
