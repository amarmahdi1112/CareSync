"""Written medication plans and attendance-linked medication ledgers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, or_, select

from app.api.basic.care import (
    _attendance_day,
    _attendance_interval,
    _attendance_intervals,
    _attendance_state,
    _local_date,
    _lock_room_safety_lane,
    _private_no_store,
    _room_access,
)
from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    BasicContext,
    MedicationCorrectContext,
    MedicationManageContext,
    MedicationReadContext,
    MedicationRecordContext,
    MedicationVoidContext,
    refresh_basic_context,
)
from app.api.dependencies import SessionDependency
from app.basic.daily_care import aware_utc
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    ChildProfilePhoto,
    Enrollment,
    Facility,
    Guardian,
    MedicationAdministration,
    MedicationAdministrationEvent,
    MedicationPlan,
    MedicationPlanEvent,
    User,
)
from app.basic.notifications import notify_organization_members
from app.basic.schemas import (
    MedicationAdministrationCorrection,
    MedicationAdministrationCreate,
    MedicationAdministrationEventResponse,
    MedicationAdministrationResponse,
    MedicationAdministrationVoidRequest,
    MedicationAuthorizationRecordRequest,
    MedicationAuthorizationRevokeRequest,
    MedicationDayChildResponse,
    MedicationGuardianOption,
    MedicationPlanActivateRequest,
    MedicationPlanArchiveRequest,
    MedicationPlanCreate,
    MedicationPlanEventResponse,
    MedicationPlanResponse,
    MedicationPlanSnapshot,
    MedicationPlanUpdate,
    MedicationRoomDayResponse,
)
from app.basic.security import audit
from app.basic.shift_guards import require_open_shift

router = APIRouter(prefix="/medications", tags=["medications"])


def _time_text(value: time) -> str:
    return value.strftime("%H:%M")


def _scheduled_times(values: Sequence[time | str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, time):
            result.append(_time_text(value))
        else:
            parsed = time.fromisoformat(value)
            result.append(_time_text(parsed))
    return sorted(dict.fromkeys(result))


def _user_names(session: SessionDependency, user_ids: set[UUID]) -> dict[UUID, str]:
    return {
        user_id: f"{first_name} {last_name}".strip()
        for user_id, first_name, last_name in session.execute(
            select(User.id, User.first_name, User.last_name).where(
                User.id.in_(user_ids) if user_ids else False
            )
        )
    }


def _guardian_options(
    session: SessionDependency,
    organization_id: UUID,
    child: Child,
) -> list[MedicationGuardianOption]:
    return [
        MedicationGuardianOption(
            id=guardian.id,
            name=f"{guardian.first_name} {guardian.last_name}".strip(),
            relationship=guardian.relationship,
        )
        for guardian in session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == organization_id,
                Guardian.family_id == child.family_id,
                Guardian.retired_at.is_(None),
            )
            .order_by(Guardian.is_primary.desc(), Guardian.created_at, Guardian.id)
        )
    ]


def _plan_snapshot(plan: MedicationPlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "facility_id": str(plan.facility_id),
        "child_id": str(plan.child_id),
        "medication_name": plan.medication_name,
        "dosage": plan.dosage,
        "route": plan.route,
        "label_directions": plan.label_directions,
        "scheduled_times": list(plan.scheduled_times or []),
        "as_needed": plan.as_needed,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
        "medication_kind": plan.medication_kind,
        "storage_method": plan.storage_method,
        "storage_instructions": plan.storage_instructions,
        "emergency_plan_reference": plan.emergency_plan_reference,
        "status": plan.status,
        "authorization_status": plan.authorization_status,
        "authorization_guardian_id": (
            str(plan.authorization_guardian_id) if plan.authorization_guardian_id else None
        ),
        "authorization_guardian_name": plan.authorization_guardian_name,
        "signed_authorization_reference": plan.signed_authorization_reference,
        "authorization_signed_at": (
            aware_utc(plan.authorization_signed_at).isoformat()
            if plan.authorization_signed_at
            else None
        ),
        "authorization_valid_until": (
            plan.authorization_valid_until.isoformat() if plan.authorization_valid_until else None
        ),
        "authorization_verified_at": (
            aware_utc(plan.authorization_verified_at).isoformat()
            if plan.authorization_verified_at
            else None
        ),
        "authorization_verified_by_user_id": (
            str(plan.authorization_verified_by_user_id)
            if plan.authorization_verified_by_user_id
            else None
        ),
        "authorization_revoked_at": (
            aware_utc(plan.authorization_revoked_at).isoformat()
            if plan.authorization_revoked_at
            else None
        ),
        "authorization_revocation_reason": plan.authorization_revocation_reason,
        "original_labelled_container_verified_at": (
            aware_utc(plan.original_labelled_container_verified_at).isoformat()
            if plan.original_labelled_container_verified_at
            else None
        ),
        "label_directions_verified_at": (
            aware_utc(plan.label_directions_verified_at).isoformat()
            if plan.label_directions_verified_at
            else None
        ),
        "created_by_user_id": str(plan.created_by_user_id),
        "version": plan.version,
        "archived_at": aware_utc(plan.archived_at).isoformat() if plan.archived_at else None,
        "archive_reason": plan.archive_reason,
    }


def _administration_plan_snapshot(plan: MedicationPlan) -> dict[str, Any]:
    if (
        plan.authorization_status != "verified"
        or plan.signed_authorization_reference is None
        or plan.authorization_guardian_name is None
        or plan.authorization_signed_at is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Current written authorization evidence is required",
        )
    return {
        "medication_name": plan.medication_name,
        "dosage": plan.dosage,
        "route": plan.route,
        "label_directions": plan.label_directions,
        "scheduled_times": list(plan.scheduled_times or []),
        "as_needed": plan.as_needed,
        "medication_kind": plan.medication_kind,
        "storage_method": plan.storage_method,
        "authorization_status": plan.authorization_status,
        "signed_authorization_reference": plan.signed_authorization_reference,
        "authorization_guardian_name": plan.authorization_guardian_name,
        "authorization_signed_at": aware_utc(plan.authorization_signed_at).isoformat(),
        "authorization_valid_until": (
            plan.authorization_valid_until.isoformat() if plan.authorization_valid_until else None
        ),
        "plan_version": plan.version,
    }


def _administration_snapshot(record: MedicationAdministration) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "medication_plan_id": str(record.medication_plan_id),
        "attendance_day_id": str(record.attendance_day_id),
        "facility_id": str(record.facility_id),
        "room_id": str(record.room_id),
        "child_id": str(record.child_id),
        "enrollment_id": str(record.enrollment_id),
        "service_date": record.service_date.isoformat(),
        "plan_version": record.plan_version,
        "plan_snapshot": dict(record.plan_snapshot or {}),
        "outcome": record.outcome,
        "scheduled_for": _time_text(record.scheduled_for) if record.scheduled_for else None,
        "occurred_at": aware_utc(record.occurred_at).isoformat(),
        "amount": record.amount,
        "reason": record.reason,
        "note": record.note,
        "staff_name_snapshot": record.staff_name_snapshot,
        "staff_initials_snapshot": record.staff_initials_snapshot,
        "created_by_user_id": str(record.created_by_user_id),
        "version": record.version,
        "voided_at": aware_utc(record.voided_at).isoformat() if record.voided_at else None,
        "voided_by_user_id": str(record.voided_by_user_id) if record.voided_by_user_id else None,
        "void_reason": record.void_reason,
    }


def _authorization_current(
    plan: MedicationPlan,
    on_date: date,
    facility: Facility,
) -> bool:
    return (
        plan.authorization_status == "verified"
        and plan.authorization_signed_at is not None
        and _local_date(facility, plan.authorization_signed_at) <= on_date
        and (plan.authorization_valid_until is None or plan.authorization_valid_until >= on_date)
    )


def _plan_dates_cover(plan: MedicationPlan, service_date: date) -> bool:
    return plan.start_date <= service_date and (
        plan.end_date is None or plan.end_date >= service_date
    )


def _plan_events(session: SessionDependency, plan: MedicationPlan) -> list[MedicationPlanEvent]:
    return list(
        session.scalars(
            select(MedicationPlanEvent)
            .where(
                MedicationPlanEvent.organization_id == plan.organization_id,
                MedicationPlanEvent.medication_plan_id == plan.id,
            )
            .order_by(MedicationPlanEvent.occurred_at, MedicationPlanEvent.id)
        )
    )


def _administration_events(
    session: SessionDependency, record: MedicationAdministration
) -> list[MedicationAdministrationEvent]:
    return list(
        session.scalars(
            select(MedicationAdministrationEvent)
            .where(
                MedicationAdministrationEvent.organization_id == record.organization_id,
                MedicationAdministrationEvent.medication_administration_id == record.id,
            )
            .order_by(
                MedicationAdministrationEvent.occurred_at,
                MedicationAdministrationEvent.id,
            )
        )
    )


def _plan_response(
    session: SessionDependency,
    plan: MedicationPlan,
    *,
    child: Child | None = None,
    guardians: list[MedicationGuardianOption] | None = None,
    events: Sequence[MedicationPlanEvent] | None = None,
    user_names: dict[UUID, str] | None = None,
    as_of_date: date | None = None,
    facility: Facility | None = None,
) -> MedicationPlanResponse:
    resolved_child = child or session.scalar(
        select(Child).where(
            Child.organization_id == plan.organization_id,
            Child.id == plan.child_id,
        )
    )
    if resolved_child is None:
        raise HTTPException(status_code=409, detail="Medication plan child is unavailable")
    resolved_events = list(events) if events is not None else _plan_events(session, plan)
    if not resolved_events:
        raise HTTPException(status_code=409, detail="Medication plan history is unavailable")
    creator_name = (
        user_names.get(plan.created_by_user_id, "Former staff")
        if user_names is not None
        else _user_names(session, {plan.created_by_user_id}).get(
            plan.created_by_user_id, "Former staff"
        )
    )
    resolved_facility = facility
    if resolved_facility is None:
        resolved_facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == plan.organization_id,
                Facility.id == plan.facility_id,
            )
        )
    if resolved_facility is None:
        raise HTTPException(status_code=409, detail="Medication plan facility is unavailable")
    if as_of_date is None:
        as_of_date = _local_date(resolved_facility)
    return MedicationPlanResponse(
        id=plan.id,
        organization_id=plan.organization_id,
        facility_id=plan.facility_id,
        child_id=plan.child_id,
        child_name=f"{resolved_child.first_name} {resolved_child.last_name}".strip(),
        medication_name=plan.medication_name,
        dosage=plan.dosage,
        route=plan.route,
        label_directions=plan.label_directions,
        scheduled_times=list(plan.scheduled_times or []),
        as_needed=plan.as_needed,
        start_date=plan.start_date,
        end_date=plan.end_date,
        medication_kind=plan.medication_kind,
        storage_method=plan.storage_method,
        storage_instructions=plan.storage_instructions,
        emergency_plan_reference=plan.emergency_plan_reference,
        status=plan.status,
        authorization_status=plan.authorization_status,
        authorization_is_current=_authorization_current(plan, as_of_date, resolved_facility),
        signed_authorization_reference=plan.signed_authorization_reference,
        authorization_guardian_id=plan.authorization_guardian_id,
        authorization_guardian_name=plan.authorization_guardian_name,
        authorization_signed_at=(
            aware_utc(plan.authorization_signed_at) if plan.authorization_signed_at else None
        ),
        authorization_valid_until=plan.authorization_valid_until,
        authorization_verified_at=(
            aware_utc(plan.authorization_verified_at) if plan.authorization_verified_at else None
        ),
        authorization_verified_by_user_id=plan.authorization_verified_by_user_id,
        authorization_revoked_at=(
            aware_utc(plan.authorization_revoked_at) if plan.authorization_revoked_at else None
        ),
        authorization_revocation_reason=plan.authorization_revocation_reason,
        original_labelled_container_verified_at=(
            aware_utc(plan.original_labelled_container_verified_at)
            if plan.original_labelled_container_verified_at
            else None
        ),
        label_directions_verified_at=(
            aware_utc(plan.label_directions_verified_at)
            if plan.label_directions_verified_at
            else None
        ),
        created_by_user_id=plan.created_by_user_id,
        created_by_name=creator_name,
        eligible_guardians=(
            guardians
            if guardians is not None
            else _guardian_options(session, plan.organization_id, resolved_child)
        ),
        version=plan.version,
        archived_at=aware_utc(plan.archived_at) if plan.archived_at else None,
        archive_reason=plan.archive_reason,
        last_event_type=resolved_events[-1].event_type,
        created_at=aware_utc(plan.created_at),
        updated_at=aware_utc(plan.updated_at),
    )


def _administration_response(
    session: SessionDependency,
    record: MedicationAdministration,
    *,
    events: Sequence[MedicationAdministrationEvent] | None = None,
    user_names: dict[UUID, str] | None = None,
) -> MedicationAdministrationResponse:
    resolved_events = (
        list(events) if events is not None else _administration_events(session, record)
    )
    if not resolved_events:
        raise HTTPException(status_code=409, detail="Medication history is unavailable")
    creator_name = (
        user_names.get(record.created_by_user_id, "Former staff")
        if user_names is not None
        else _user_names(session, {record.created_by_user_id}).get(
            record.created_by_user_id, "Former staff"
        )
    )
    return MedicationAdministrationResponse(
        id=record.id,
        organization_id=record.organization_id,
        facility_id=record.facility_id,
        room_id=record.room_id,
        child_id=record.child_id,
        enrollment_id=record.enrollment_id,
        attendance_day_id=record.attendance_day_id,
        service_date=record.service_date,
        medication_plan_id=record.medication_plan_id,
        plan_version=record.plan_version,
        plan_snapshot=MedicationPlanSnapshot.model_validate(record.plan_snapshot),
        outcome=record.outcome,
        scheduled_for=_time_text(record.scheduled_for) if record.scheduled_for else None,
        occurred_at=aware_utc(record.occurred_at),
        amount=record.amount,
        reason=record.reason,
        note=record.note,
        staff_name_snapshot=record.staff_name_snapshot,
        staff_initials_snapshot=record.staff_initials_snapshot,
        created_by_user_id=record.created_by_user_id,
        created_by_name=creator_name,
        version=record.version,
        voided_at=aware_utc(record.voided_at) if record.voided_at else None,
        voided_by_user_id=record.voided_by_user_id,
        void_reason=record.void_reason,
        last_event_type=resolved_events[-1].event_type,
        was_corrected=any(event.event_type == "corrected" for event in resolved_events),
        created_at=aware_utc(record.created_at),
        updated_at=aware_utc(record.updated_at),
    )


def _plan_event_by_operation(
    session: SessionDependency, organization_id: UUID, operation_id: UUID
) -> MedicationPlanEvent | None:
    return session.scalar(
        select(MedicationPlanEvent).where(
            MedicationPlanEvent.organization_id == organization_id,
            MedicationPlanEvent.client_operation_id == operation_id,
        )
    )


def _administration_event_by_operation(
    session: SessionDependency, organization_id: UUID, operation_id: UUID
) -> MedicationAdministrationEvent | None:
    return session.scalar(
        select(MedicationAdministrationEvent).where(
            MedicationAdministrationEvent.organization_id == organization_id,
            MedicationAdministrationEvent.client_operation_id == operation_id,
        )
    )


def _current_enrollment(
    session: SessionDependency,
    plan: MedicationPlan,
    facility: Facility,
) -> Enrollment | None:
    today = _local_date(facility)
    return session.scalar(
        select(Enrollment)
        .where(
            Enrollment.organization_id == plan.organization_id,
            Enrollment.facility_id == plan.facility_id,
            Enrollment.child_id == plan.child_id,
            Enrollment.status == "active",
            Enrollment.start_date <= today,
            Enrollment.placement_effective_date <= today,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= today),
            Enrollment.room_id.is_not(None),
        )
        .order_by(Enrollment.start_date.desc(), Enrollment.id)
    )


def _plan_access(
    session: SessionDependency,
    context: BasicContext,
    plan_id: UUID,
    *,
    lock: bool = False,
    manage: bool = False,
) -> tuple[MedicationPlan, Facility, Child]:
    statement = select(MedicationPlan).where(
        MedicationPlan.organization_id == context.organization.id,
        MedicationPlan.id == plan_id,
    )
    if lock:
        statement = statement.with_for_update()
    plan = session.scalar(statement)
    if plan is None:
        raise HTTPException(status_code=404, detail="Medication plan not found")
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == context.organization.id,
            Facility.id == plan.facility_id,
        )
    )
    child = session.scalar(
        select(Child).where(
            Child.organization_id == context.organization.id,
            Child.id == plan.child_id,
        )
    )
    if facility is None or child is None:
        raise HTTPException(status_code=404, detail="Medication plan not found")
    if manage and not context.organization_wide:
        raise HTTPException(status_code=403, detail="Permission required")
    if not context.organization_wide:
        enrollment = _current_enrollment(session, plan, facility)
        if (
            facility.status != "active"
            or not child.is_active
            or enrollment is None
            or enrollment.room_id not in context.assigned_room_ids
            or plan.status != "active"
            or not _plan_dates_cover(plan, _local_date(facility))
        ):
            raise HTTPException(status_code=404, detail="Medication plan not found")
    return plan, facility, child


def _check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise HTTPException(status_code=409, detail="Medication record version has changed")


def _append_plan_event(
    session: SessionDependency,
    context: BasicContext,
    plan: MedicationPlan,
    *,
    operation_id: UUID,
    event_type: str,
    before: dict[str, Any] | None,
    reason: str | None = None,
) -> MedicationPlanEvent:
    event = MedicationPlanEvent(
        id=uuid4(),
        organization_id=context.organization.id,
        medication_plan_id=plan.id,
        actor_user_id=context.user.id,
        client_operation_id=operation_id,
        event_type=event_type,
        reason=reason,
        before=before,
        after=_plan_snapshot(plan),
    )
    session.add(event)
    return event


def _append_administration_event(
    session: SessionDependency,
    context: BasicContext,
    record: MedicationAdministration,
    *,
    operation_id: UUID,
    event_type: str,
    before: dict[str, Any] | None,
    reason: str | None = None,
) -> MedicationAdministrationEvent:
    event = MedicationAdministrationEvent(
        id=uuid4(),
        organization_id=context.organization.id,
        medication_administration_id=record.id,
        actor_user_id=context.user.id,
        client_operation_id=operation_id,
        event_type=event_type,
        reason=reason,
        before=before,
        after=_administration_snapshot(record),
    )
    session.add(event)
    return event


def _plan_replay(
    session: SessionDependency,
    context: BasicContext,
    operation_id: UUID,
    event_type: str,
    *,
    plan_id: UUID | None = None,
    expected_after: dict[str, Any] | None = None,
    expected_before_version: int | None = None,
    expected_reason: str | None = None,
) -> MedicationPlan | None:
    event = _plan_event_by_operation(session, context.organization.id, operation_id)
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Medication plan not found")
    plan, _, _ = _plan_access(session, context, event.medication_plan_id)
    if event.event_type != event_type or (
        plan_id is not None and event.medication_plan_id != plan_id
    ):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    if (
        event.reason != expected_reason
        or (expected_before_version is not None)
        and (event.before is None or event.before.get("version") != expected_before_version)
        or expected_after is not None
        and (
            event.after is None
            or any(event.after.get(key) != value for key, value in expected_after.items())
        )
    ):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    return plan


def _administration_replay(
    session: SessionDependency,
    context: BasicContext,
    request: Request,
    operation_id: UUID,
    event_type: str,
    *,
    record_id: UUID | None = None,
    expected_after: dict[str, Any] | None = None,
    expected_before_version: int | None = None,
    expected_reason: str | None = None,
) -> MedicationAdministration | None:
    event = _administration_event_by_operation(session, context.organization.id, operation_id)
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Medication record not found")
    record = session.scalar(
        select(MedicationAdministration).where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.id == event.medication_administration_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=409, detail="Medication record is unavailable")
    _lock_room_safety_lane(
        request,
        session,
        context,
        record.facility_id,
    )
    current_context = refresh_basic_context(
        session,
        context,
        required_any_permissions={
            "recorded": ("medication:record",),
            "corrected": (
                "medication:correct",
                "medication:correct_own",
            ),
            "voided": ("medication:void",),
        }[event_type],
        conceal_detail="Medication record not found",
    )
    facility, _ = _room_access(
        session,
        current_context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=True,
    )
    if (
        not current_context.organization_wide
        and record.service_date != _local_date(facility)
    ):
        raise HTTPException(status_code=404, detail="Medication record not found")
    if event_type == "corrected":
        _ensure_administration_correction_access(
            current_context,
            record,
            conceal=True,
        )
    if event.event_type != event_type or (
        record_id is not None and event.medication_administration_id != record_id
    ):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    if (
        event.reason != expected_reason
        or (expected_before_version is not None)
        and (event.before is None or event.before.get("version") != expected_before_version)
        or expected_after is not None
        and (
            event.after is None
            or any(event.after.get(key) != value for key, value in expected_after.items())
        )
    ):
        raise HTTPException(status_code=409, detail="Client operation ID was already used")
    return record


def _plan_payload_expected(
    payload: MedicationPlanCreate | MedicationPlanUpdate,
) -> dict[str, Any]:
    return {
        "facility_id": str(payload.facility_id),
        "child_id": str(payload.child_id),
        "medication_name": payload.medication_name,
        "dosage": payload.dosage,
        "route": payload.route,
        "label_directions": payload.label_directions,
        "scheduled_times": _scheduled_times(payload.scheduled_times),
        "as_needed": payload.as_needed,
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat() if payload.end_date else None,
        "medication_kind": payload.medication_kind,
        "storage_method": payload.storage_method,
        "storage_instructions": payload.storage_instructions,
        "emergency_plan_reference": payload.emergency_plan_reference,
    }


def _administration_payload_expected(
    payload: MedicationAdministrationCreate | MedicationAdministrationCorrection,
) -> dict[str, Any]:
    return {
        "medication_plan_id": str(payload.medication_plan_id),
        "attendance_day_id": str(payload.attendance_day_id),
        "outcome": payload.outcome,
        "scheduled_for": _time_text(payload.scheduled_for) if payload.scheduled_for else None,
        "occurred_at": aware_utc(payload.occurred_at).isoformat(),
        "amount": payload.amount,
        "reason": payload.reason,
        "note": payload.note,
    }


@router.get("/rooms/{room_id}/day", response_model=MedicationRoomDayResponse)
def medication_room_day(
    room_id: UUID,
    response: Response,
    context: MedicationReadContext,
    session: SessionDependency,
    service_date: Annotated[date, Query(alias="date")],
) -> MedicationRoomDayResponse:
    facility, room = _room_access(session, context, room_id, allow_inactive_organization_read=True)
    today = _local_date(facility)
    if not context.organization_wide and service_date != today:
        raise HTTPException(
            status_code=403,
            detail="Educators can access only today's assigned-room medication daybook",
        )
    snapshot_rows = list(
        session.execute(
            select(Enrollment, Child, AttendanceDay)
            .select_from(AttendanceDay)
            .join(
                Enrollment,
                and_(
                    Enrollment.organization_id == AttendanceDay.organization_id,
                    Enrollment.id == AttendanceDay.enrollment_id,
                ),
            )
            .join(
                Child,
                and_(
                    Child.organization_id == AttendanceDay.organization_id,
                    Child.id == AttendanceDay.child_id,
                ),
            )
            .where(
                AttendanceDay.organization_id == context.organization.id,
                AttendanceDay.facility_id == facility.id,
                AttendanceDay.room_id == room.id,
                AttendanceDay.service_date == service_date,
            )
        )
    )
    roster: dict[UUID, tuple[Enrollment, Child, AttendanceDay | None]] = {
        child.id: (enrollment, child, day) for enrollment, child, day in snapshot_rows
    }
    if service_date == today and facility.status == "active" and room.is_active:
        for enrollment, child in session.execute(
            select(Enrollment, Child)
            .join(
                Child,
                and_(
                    Child.organization_id == Enrollment.organization_id,
                    Child.id == Enrollment.child_id,
                ),
            )
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.facility_id == facility.id,
                Enrollment.room_id == room.id,
                Enrollment.status == "active",
                Enrollment.start_date <= service_date,
                Enrollment.placement_effective_date <= service_date,
                or_(Enrollment.end_date.is_(None), Enrollment.end_date >= service_date),
                Child.is_active.is_(True),
            )
        ):
            roster.setdefault(child.id, (enrollment, child, None))
    rows = sorted(roster.values(), key=lambda row: (row[1].last_name, row[1].first_name))
    child_ids = [child.id for _, child, _ in rows]
    day_ids = [day.id for _, _, day in rows if day is not None]
    intervals_by_day: dict[UUID, list[AttendanceInterval]] = {}
    if day_ids:
        for interval in session.scalars(
            select(AttendanceInterval)
            .where(
                AttendanceInterval.organization_id == context.organization.id,
                AttendanceInterval.attendance_day_id.in_(day_ids),
            )
            .order_by(AttendanceInterval.attendance_day_id, AttendanceInterval.sequence)
        ):
            intervals_by_day.setdefault(interval.attendance_day_id, []).append(interval)
    photos = set(
        session.scalars(
            select(ChildProfilePhoto.child_id).where(
                ChildProfilePhoto.organization_id == context.organization.id,
                ChildProfilePhoto.child_id.in_(child_ids) if child_ids else False,
            )
        )
    )
    plans_statement = select(MedicationPlan).where(
        MedicationPlan.organization_id == context.organization.id,
        MedicationPlan.facility_id == facility.id,
        MedicationPlan.child_id.in_(child_ids) if child_ids else False,
        MedicationPlan.start_date <= service_date,
        or_(MedicationPlan.end_date.is_(None), MedicationPlan.end_date >= service_date),
    )
    if not context.organization_wide:
        plans_statement = plans_statement.where(MedicationPlan.status == "active")
    plans = list(
        session.scalars(plans_statement.order_by(MedicationPlan.medication_name, MedicationPlan.id))
    )
    plans_by_child: dict[UUID, list[MedicationPlan]] = {}
    for plan in plans:
        plans_by_child.setdefault(plan.child_id, []).append(plan)
    administrations = list(
        session.scalars(
            select(MedicationAdministration)
            .where(
                MedicationAdministration.organization_id == context.organization.id,
                MedicationAdministration.room_id == room.id,
                MedicationAdministration.service_date == service_date,
                MedicationAdministration.voided_at.is_(None),
            )
            .order_by(MedicationAdministration.occurred_at, MedicationAdministration.id)
        )
    )
    administrations_by_child: dict[UUID, list[MedicationAdministration]] = {}
    for record in administrations:
        administrations_by_child.setdefault(record.child_id, []).append(record)
    plan_events_by_id: dict[UUID, list[MedicationPlanEvent]] = {}
    if plans:
        for event in session.scalars(
            select(MedicationPlanEvent)
            .where(
                MedicationPlanEvent.organization_id == context.organization.id,
                MedicationPlanEvent.medication_plan_id.in_([plan.id for plan in plans]),
            )
            .order_by(MedicationPlanEvent.occurred_at, MedicationPlanEvent.id)
        ):
            plan_events_by_id.setdefault(event.medication_plan_id, []).append(event)
    administration_events_by_id: dict[UUID, list[MedicationAdministrationEvent]] = {}
    if administrations:
        for event in session.scalars(
            select(MedicationAdministrationEvent)
            .where(
                MedicationAdministrationEvent.organization_id == context.organization.id,
                MedicationAdministrationEvent.medication_administration_id.in_(
                    [record.id for record in administrations]
                ),
            )
            .order_by(
                MedicationAdministrationEvent.occurred_at,
                MedicationAdministrationEvent.id,
            )
        ):
            administration_events_by_id.setdefault(event.medication_administration_id, []).append(
                event
            )
    all_creator_ids = {plan.created_by_user_id for plan in plans} | {
        record.created_by_user_id for record in administrations
    }
    names = _user_names(session, all_creator_ids)
    _private_no_store(response)
    return MedicationRoomDayResponse(
        organization_id=context.organization.id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=room.id,
        room_name=room.name,
        service_date=service_date,
        generated_at=datetime.now(UTC),
        children=[
            MedicationDayChildResponse(
                child_id=child.id,
                child_name=f"{child.first_name} {child.last_name}".strip(),
                profile_photo_url=(
                    f"/api/v1/children/{child.id}/photo" if child.id in photos else None
                ),
                enrollment_id=enrollment.id,
                attendance_day_id=day.id if day else None,
                attendance_state=_attendance_state(
                    day,
                    intervals_by_day.get(day.id, ()) if day else (),
                ),
                eligible_guardians=(
                    guardians := _guardian_options(session, context.organization.id, child)
                ),
                plans=[
                    _plan_response(
                        session,
                        plan,
                        child=child,
                        guardians=guardians,
                        events=plan_events_by_id.get(plan.id, ()),
                        user_names=names,
                        as_of_date=service_date,
                        facility=facility,
                    )
                    for plan in plans_by_child.get(child.id, [])
                ],
                administrations=[
                    _administration_response(
                        session,
                        record,
                        events=administration_events_by_id.get(record.id, ()),
                        user_names=names,
                    )
                    for record in administrations_by_child.get(child.id, [])
                ],
            )
            for enrollment, child, day in rows
        ],
    )


@router.post("/plans", response_model=MedicationPlanResponse, status_code=status.HTTP_201_CREATED)
def create_medication_plan(
    payload: MedicationPlanCreate,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "created",
        expected_after=_plan_payload_expected(payload),
    )
    if replay is not None:
        return _plan_response(session, replay)
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == context.organization.id,
            Facility.id == payload.facility_id,
            Facility.status == "active",
        )
    )
    child = session.scalar(
        select(Child).where(
            Child.organization_id == context.organization.id,
            Child.id == payload.child_id,
            Child.is_active.is_(True),
        )
    )
    if facility is None or child is None:
        raise HTTPException(status_code=404, detail="Child or facility not found")
    enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.organization_id == context.organization.id,
            Enrollment.facility_id == facility.id,
            Enrollment.child_id == child.id,
            Enrollment.status == "active",
            Enrollment.start_date <= payload.start_date,
            Enrollment.placement_effective_date <= payload.start_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= payload.start_date),
        )
    )
    if enrollment is None:
        raise HTTPException(
            status_code=409,
            detail="Child must have an active facility enrollment when the plan starts",
        )
    plan = MedicationPlan(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=facility.id,
        child_id=child.id,
        medication_name=payload.medication_name,
        dosage=payload.dosage,
        route=payload.route,
        label_directions=payload.label_directions,
        scheduled_times=_scheduled_times(payload.scheduled_times),
        as_needed=payload.as_needed,
        start_date=payload.start_date,
        end_date=payload.end_date,
        medication_kind=payload.medication_kind,
        storage_method=payload.storage_method,
        storage_instructions=payload.storage_instructions,
        emergency_plan_reference=payload.emergency_plan_reference,
        status="draft",
        authorization_status="not_recorded",
        created_by_user_id=context.user.id,
        version=1,
    )
    session.add(plan)
    flush_or_conflict(session, "Medication plan conflicts with another update")
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="created",
        before=None,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.created",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    commit_in_context(session, context, "Medication plan conflicts with another update")
    return _plan_response(session, plan, child=child)


@router.get("/plans/{plan_id}", response_model=MedicationPlanResponse)
def get_medication_plan(
    plan_id: UUID,
    response: Response,
    context: MedicationReadContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    plan, _, child = _plan_access(session, context, plan_id)
    _private_no_store(response)
    return _plan_response(session, plan, child=child)


def _clear_authorization(plan: MedicationPlan) -> None:
    plan.authorization_status = "not_recorded"
    plan.authorization_guardian_id = None
    plan.authorization_guardian_name = None
    plan.signed_authorization_reference = None
    plan.authorization_signed_at = None
    plan.authorization_valid_until = None
    plan.authorization_verified_at = None
    plan.authorization_verified_by_user_id = None
    plan.authorization_revoked_at = None
    plan.authorization_revoked_by_user_id = None
    plan.authorization_revocation_reason = None
    plan.original_labelled_container_verified_at = None
    plan.original_labelled_container_verified_by_user_id = None
    plan.label_directions_verified_at = None
    plan.label_directions_verified_by_user_id = None


@router.put("/plans/{plan_id}", response_model=MedicationPlanResponse)
def update_medication_plan(
    plan_id: UUID,
    payload: MedicationPlanUpdate,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "updated",
        plan_id=plan_id,
        expected_after={**_plan_payload_expected(payload), "status": "draft"},
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _plan_response(session, replay)
    plan, _, child = _plan_access(session, context, plan_id, lock=True, manage=True)
    if plan.status == "archived":
        raise HTTPException(status_code=409, detail="Archived medication plans cannot be edited")
    _check_version(plan.version, payload.expected_version)
    if plan.facility_id != payload.facility_id or plan.child_id != payload.child_id:
        raise HTTPException(status_code=422, detail="Plan child and facility cannot be changed")
    enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.organization_id == context.organization.id,
            Enrollment.facility_id == plan.facility_id,
            Enrollment.child_id == plan.child_id,
            Enrollment.status == "active",
            Enrollment.start_date <= payload.start_date,
            Enrollment.placement_effective_date <= payload.start_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= payload.start_date),
        )
    )
    if enrollment is None:
        raise HTTPException(
            status_code=409,
            detail="Child must have an active facility enrollment when the plan starts",
        )
    before = _plan_snapshot(plan)
    for field_name in (
        "medication_name",
        "dosage",
        "route",
        "label_directions",
        "as_needed",
        "start_date",
        "end_date",
        "medication_kind",
        "storage_method",
        "storage_instructions",
        "emergency_plan_reference",
    ):
        setattr(plan, field_name, getattr(payload, field_name))
    plan.scheduled_times = _scheduled_times(payload.scheduled_times)
    plan.status = "draft"
    _clear_authorization(plan)
    plan.version += 1
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="updated",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.updated",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    commit_in_context(session, context)
    return _plan_response(session, plan, child=child)


@router.post("/plans/{plan_id}/authorization", response_model=MedicationPlanResponse)
def record_written_authorization(
    plan_id: UUID,
    payload: MedicationAuthorizationRecordRequest,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "authorization_verified",
        plan_id=plan_id,
        expected_after={
            "authorization_guardian_id": str(payload.guardian_id),
            "signed_authorization_reference": payload.signed_authorization_reference,
            "authorization_signed_at": aware_utc(payload.authorization_signed_at).isoformat(),
            "authorization_valid_until": (
                payload.valid_until.isoformat() if payload.valid_until else None
            ),
        },
        expected_before_version=payload.expected_version,
    )
    if replay is not None:
        return _plan_response(session, replay)
    plan, facility, child = _plan_access(session, context, plan_id, lock=True, manage=True)
    if plan.status == "archived":
        raise HTTPException(
            status_code=409,
            detail="Archived medication plans cannot be authorized",
        )
    _check_version(plan.version, payload.expected_version)
    signed_at = aware_utc(payload.authorization_signed_at)
    if signed_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(
            status_code=422,
            detail="Authorization signed time cannot be in the future",
        )
    if payload.valid_until is not None and payload.valid_until < _local_date(facility, signed_at):
        raise HTTPException(
            status_code=422,
            detail="Authorization validity cannot end before signing",
        )
    guardian = session.scalar(
        select(Guardian).where(
            Guardian.organization_id == context.organization.id,
            Guardian.id == payload.guardian_id,
            Guardian.family_id == child.family_id,
            Guardian.retired_at.is_(None),
        )
    )
    if guardian is None:
        raise HTTPException(status_code=404, detail="Guardian not found")
    before = _plan_snapshot(plan)
    plan.status = "draft"
    plan.original_labelled_container_verified_at = None
    plan.original_labelled_container_verified_by_user_id = None
    plan.label_directions_verified_at = None
    plan.label_directions_verified_by_user_id = None
    plan.authorization_status = "verified"
    plan.authorization_guardian_id = guardian.id
    plan.authorization_guardian_name = f"{guardian.first_name} {guardian.last_name}".strip()
    plan.signed_authorization_reference = payload.signed_authorization_reference
    plan.authorization_signed_at = signed_at
    plan.authorization_valid_until = payload.valid_until
    plan.authorization_verified_at = datetime.now(UTC)
    plan.authorization_verified_by_user_id = context.user.id
    plan.authorization_revoked_at = None
    plan.authorization_revoked_by_user_id = None
    plan.authorization_revocation_reason = None
    plan.version += 1
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="authorization_verified",
        before=before,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.written_authorization_evidence_recorded",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    commit_in_context(session, context)
    return _plan_response(session, plan, child=child)


@router.post("/plans/{plan_id}/revoke-authorization", response_model=MedicationPlanResponse)
def revoke_written_authorization(
    plan_id: UUID,
    payload: MedicationAuthorizationRevokeRequest,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "authorization_revoked",
        plan_id=plan_id,
        expected_after={
            "authorization_status": "revoked",
            "authorization_revocation_reason": payload.reason,
        },
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _plan_response(session, replay)
    plan, facility, child = _plan_access(session, context, plan_id, lock=True, manage=True)
    _check_version(plan.version, payload.expected_version)
    if plan.authorization_status != "verified":
        raise HTTPException(status_code=409, detail="No current authorization can be revoked")
    before = _plan_snapshot(plan)
    plan.authorization_status = "revoked"
    plan.authorization_revoked_at = datetime.now(UTC)
    plan.authorization_revoked_by_user_id = context.user.id
    plan.authorization_revocation_reason = payload.reason
    plan.status = "draft"
    plan.original_labelled_container_verified_at = None
    plan.original_labelled_container_verified_by_user_id = None
    plan.label_directions_verified_at = None
    plan.label_directions_verified_by_user_id = None
    plan.version += 1
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="authorization_revoked",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.authorization_revoked",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    enrollment = _current_enrollment(session, plan, facility)
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"medication:record"},
        event_key=f"medication-authorization-revoked:{plan.id}:{plan.version}",
        category="operations",
        severity="warning",
        title="Medication authorization changed",
        body="A medication plan is unavailable until authorization is reviewed.",
        action_path="/medications",
        action_entity_type="medication_plan",
        action_entity_id=plan.id,
        facility_id=plan.facility_id,
        room_id=enrollment.room_id if enrollment is not None else None,
        organization_wide_only=enrollment is None,
    )
    commit_in_context(session, context)
    return _plan_response(session, plan, child=child)


@router.post("/plans/{plan_id}/activate", response_model=MedicationPlanResponse)
def activate_medication_plan(
    plan_id: UUID,
    payload: MedicationPlanActivateRequest,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "activated",
        plan_id=plan_id,
        expected_after={"status": "active"},
        expected_before_version=payload.expected_version,
    )
    if replay is not None:
        return _plan_response(session, replay)
    plan, facility, child = _plan_access(session, context, plan_id, lock=True, manage=True)
    _check_version(plan.version, payload.expected_version)
    if plan.status == "archived":
        raise HTTPException(status_code=409, detail="Archived medication plans cannot be activated")
    today = _local_date(facility)
    if plan.end_date is not None and plan.end_date < today:
        raise HTTPException(status_code=409, detail="Expired medication plans cannot be activated")
    authorization_check_date = max(today, plan.start_date)
    if not _authorization_current(plan, authorization_check_date, facility):
        raise HTTPException(
            status_code=409,
            detail="Current separate written parent authorization evidence is required",
        )
    before = _plan_snapshot(plan)
    now = datetime.now(UTC)
    plan.original_labelled_container_verified_at = now
    plan.original_labelled_container_verified_by_user_id = context.user.id
    plan.label_directions_verified_at = now
    plan.label_directions_verified_by_user_id = context.user.id
    plan.status = "active"
    plan.version += 1
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="activated",
        before=before,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.activated",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    enrollment = _current_enrollment(session, plan, facility)
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"medication:record"},
        event_key=f"medication-plan-activated:{plan.id}:{plan.version}",
        category="operations",
        severity="info",
        title="Medication plan ready",
        body="An authorized medication plan is now available for assigned care staff.",
        action_path="/medications",
        action_entity_type="medication_plan",
        action_entity_id=plan.id,
        facility_id=plan.facility_id,
        room_id=enrollment.room_id if enrollment is not None else None,
        organization_wide_only=enrollment is None,
    )
    commit_in_context(session, context)
    return _plan_response(session, plan, child=child)


@router.post("/plans/{plan_id}/archive", response_model=MedicationPlanResponse)
def archive_medication_plan(
    plan_id: UUID,
    payload: MedicationPlanArchiveRequest,
    request: Request,
    response: Response,
    context: MedicationManageContext,
    session: SessionDependency,
) -> MedicationPlanResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _plan_replay(
        session,
        context,
        payload.client_operation_id,
        "archived",
        plan_id=plan_id,
        expected_after={"status": "archived", "archive_reason": payload.reason},
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _plan_response(session, replay)
    plan, _, child = _plan_access(session, context, plan_id, lock=True, manage=True)
    _check_version(plan.version, payload.expected_version)
    if plan.status == "archived":
        raise HTTPException(status_code=409, detail="Medication plan is already archived")
    before = _plan_snapshot(plan)
    plan.status = "archived"
    plan.archived_at = datetime.now(UTC)
    plan.archived_by_user_id = context.user.id
    plan.archive_reason = payload.reason
    plan.version += 1
    _append_plan_event(
        session,
        context,
        plan,
        operation_id=payload.client_operation_id,
        event_type="archived",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.plan.archived",
        entity_type="medication_plan",
        entity_id=plan.id,
        facility_id=plan.facility_id,
        details={"child_id": str(plan.child_id), "version": plan.version},
    )
    commit_in_context(session, context)
    return _plan_response(session, plan, child=child)


@router.get("/plans/{plan_id}/history", response_model=list[MedicationPlanEventResponse])
def medication_plan_history(
    plan_id: UUID,
    response: Response,
    context: MedicationReadContext,
    session: SessionDependency,
) -> list[MedicationPlanEventResponse]:
    plan, _, _ = _plan_access(session, context, plan_id)
    events = _plan_events(session, plan)
    names = _user_names(session, {event.actor_user_id for event in events})
    _private_no_store(response)
    return [
        MedicationPlanEventResponse(
            id=event.id,
            medication_plan_id=event.medication_plan_id,
            actor_user_id=event.actor_user_id,
            actor_name=names.get(event.actor_user_id, "Former staff"),
            client_operation_id=event.client_operation_id,
            event_type=event.event_type,
            occurred_at=aware_utc(event.occurred_at),
            reason=event.reason,
            before=event.before,
            after=event.after,
        )
        for event in events
    ]


def _validated_scheduled_for(plan: MedicationPlan, value: time | None) -> time | None:
    allowed = set(plan.scheduled_times or [])
    if value is None:
        if not plan.as_needed:
            raise HTTPException(status_code=422, detail="scheduled_for is required for this plan")
        return None
    canonical = _time_text(value)
    if canonical not in allowed:
        raise HTTPException(status_code=422, detail="scheduled_for is not a plan schedule slot")
    return time.fromisoformat(canonical)


def _validate_plan_for_administration(
    plan: MedicationPlan, service_date: date, facility: Facility
) -> None:
    if plan.status != "active" or not _plan_dates_cover(plan, service_date):
        raise HTTPException(status_code=409, detail="Medication plan is not active for this date")
    if not _authorization_current(plan, service_date, facility):
        raise HTTPException(
            status_code=409,
            detail="Current separate written parent authorization evidence is required",
        )


def _staff_identity(user: User) -> tuple[str, str]:
    name = f"{user.first_name} {user.last_name}".strip()
    initials = "".join(
        part[0].upper() for part in (user.first_name.strip(), user.last_name.strip()) if part
    )
    if not name or not initials:
        raise HTTPException(status_code=409, detail="Staff identity is incomplete")
    return name, initials


@router.post(
    "/administrations",
    response_model=MedicationAdministrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_medication_administration(
    payload: MedicationAdministrationCreate,
    request: Request,
    response: Response,
    context: MedicationRecordContext,
    session: SessionDependency,
) -> MedicationAdministrationResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _administration_replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "recorded",
        expected_after=_administration_payload_expected(payload),
    )
    if replay is not None:
        return _administration_response(session, replay)
    preliminary_day = _attendance_day(
        session,
        context.organization.id,
        payload.attendance_day_id,
    )
    preliminary_facility_id = preliminary_day.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("medication:record",),
        conceal_detail="Medication record not found",
    )
    day = _attendance_day(session, context.organization.id, payload.attendance_day_id, lock=True)
    if day.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "attendance_source_integrity_unknown"},
        )
    if day.room_id is None or day.status != "present":
        raise HTTPException(status_code=409, detail="Medication requires an on-site attendance day")
    facility, _ = _room_access(session, context, day.room_id, expected_facility_id=day.facility_id)
    require_open_shift(
        session,
        context,
        facility.id,
        day.room_id,
        enforce_room_presence=live_room_safety,
    )
    intervals = _attendance_intervals(session, day, lock=True)
    occurred_at = aware_utc(payload.occurred_at)
    if occurred_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Medication time cannot be in the future")
    if _local_date(facility, occurred_at) != day.service_date:
        raise HTTPException(
            status_code=422,
            detail="Medication time must match the attendance date",
        )
    _attendance_interval(
        session,
        day,
        occurred_at,
        ended_at=None,
        require_open=False,
        intervals=intervals,
    )
    plan = session.scalar(
        select(MedicationPlan)
        .where(
            MedicationPlan.organization_id == context.organization.id,
            MedicationPlan.id == payload.medication_plan_id,
        )
        .with_for_update()
    )
    if plan is None or plan.facility_id != day.facility_id or plan.child_id != day.child_id:
        raise HTTPException(status_code=404, detail="Medication plan not found")
    _validate_plan_for_administration(plan, day.service_date, facility)
    scheduled_for = _validated_scheduled_for(plan, payload.scheduled_for)
    staff_name, staff_initials = _staff_identity(context.user)
    record = MedicationAdministration(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=day.facility_id,
        room_id=day.room_id,
        child_id=day.child_id,
        enrollment_id=day.enrollment_id,
        attendance_day_id=day.id,
        service_date=day.service_date,
        medication_plan_id=plan.id,
        plan_version=plan.version,
        plan_snapshot=_administration_plan_snapshot(plan),
        outcome=payload.outcome,
        scheduled_for=scheduled_for,
        occurred_at=occurred_at,
        amount=payload.amount,
        reason=payload.reason,
        note=payload.note,
        staff_name_snapshot=staff_name,
        staff_initials_snapshot=staff_initials,
        created_by_user_id=context.user.id,
        version=1,
    )
    session.add(record)
    flush_or_conflict(session, "Medication schedule slot already has an active record")
    _append_administration_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="recorded",
        before=None,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.administration.recorded",
        entity_type="medication_administration",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "child_id": str(record.child_id),
            "outcome": record.outcome,
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Medication operation conflicts with another update")
    return _administration_response(session, record)


def _locked_administration_context(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
) -> tuple[MedicationAdministration, AttendanceDay, list[AttendanceInterval], Facility]:
    snapshot = session.scalar(
        select(MedicationAdministration).where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.id == record_id,
        )
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Medication record not found")
    day = _attendance_day(session, context.organization.id, snapshot.attendance_day_id, lock=True)
    intervals = _attendance_intervals(session, day, lock=True)
    record = session.scalar(
        select(MedicationAdministration)
        .where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.id == record_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None or record.attendance_day_id != day.id:
        raise HTTPException(status_code=409, detail="Medication attendance identity changed")
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=True,
    )
    if not context.organization_wide and record.service_date != _local_date(facility):
        raise HTTPException(status_code=404, detail="Medication record not found")
    return record, day, intervals, facility


def _administration_access(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
) -> tuple[MedicationAdministration, Facility]:
    """Resolve current scoped administration identity before taking its lane."""

    record = session.scalar(
        select(MedicationAdministration).where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.id == record_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Medication record not found")
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=True,
    )
    if not context.organization_wide and record.service_date != _local_date(facility):
        raise HTTPException(status_code=404, detail="Medication record not found")
    return record, facility


def _ensure_administration_correction_access(
    context: BasicContext,
    record: MedicationAdministration,
    *,
    conceal: bool = False,
) -> None:
    permissions = set(context.role.permissions or [])
    if "medication:correct" in permissions:
        return
    if (
        "medication:correct_own" in permissions
        and record.created_by_user_id == context.user.id
    ):
        return
    raise HTTPException(
        status_code=404 if conceal else 403,
        detail=(
            "Medication record not found"
            if conceal
            else "Educators can correct only their own records"
        ),
    )


@router.put(
    "/administrations/{record_id}/correction",
    response_model=MedicationAdministrationResponse,
)
def correct_medication_administration(
    record_id: UUID,
    payload: MedicationAdministrationCorrection,
    request: Request,
    response: Response,
    context: MedicationCorrectContext,
    session: SessionDependency,
) -> MedicationAdministrationResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _administration_replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "corrected",
        record_id=record_id,
        expected_after=_administration_payload_expected(payload),
        expected_before_version=payload.expected_version,
        expected_reason=payload.correction_reason,
    )
    if replay is not None:
        return _administration_response(session, replay)
    preliminary_record, _ = _administration_access(
        session,
        context,
        record_id,
    )
    preliminary_facility_id = preliminary_record.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=(
            "medication:correct",
            "medication:correct_own",
        ),
        conceal_detail="Medication record not found",
    )
    record, day, intervals, facility = _locked_administration_context(session, context, record_id)
    if record.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "medication_source_integrity_unknown"},
        )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    if record.voided_at is not None:
        raise HTTPException(status_code=409, detail="Voided medication records cannot be corrected")
    _ensure_administration_correction_access(context, record)
    _check_version(record.version, payload.expected_version)
    if (
        payload.medication_plan_id != record.medication_plan_id
        or payload.attendance_day_id != record.attendance_day_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Medication and attendance identity cannot change",
        )
    occurred_at = aware_utc(payload.occurred_at)
    if occurred_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Medication time cannot be in the future")
    if _local_date(facility, occurred_at) != day.service_date:
        raise HTTPException(
            status_code=422,
            detail="Medication time must match the attendance date",
        )
    _attendance_interval(
        session,
        day,
        occurred_at,
        ended_at=None,
        require_open=False,
        intervals=intervals,
    )
    snapshot_schedule = set(record.plan_snapshot.get("scheduled_times", []))
    if payload.scheduled_for is None:
        if not bool(record.plan_snapshot.get("as_needed")):
            raise HTTPException(status_code=422, detail="scheduled_for is required for this plan")
        scheduled_for = None
    else:
        canonical = _time_text(payload.scheduled_for)
        if canonical not in snapshot_schedule:
            raise HTTPException(status_code=422, detail="scheduled_for is not a plan schedule slot")
        scheduled_for = time.fromisoformat(canonical)
    before = _administration_snapshot(record)
    record.outcome = payload.outcome
    record.scheduled_for = scheduled_for
    record.occurred_at = occurred_at
    record.amount = payload.amount
    record.reason = payload.reason
    record.note = payload.note
    record.version += 1
    flush_or_conflict(session, "Medication schedule slot already has an active record")
    _append_administration_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="corrected",
        before=before,
        reason=payload.correction_reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.administration.corrected",
        entity_type="medication_administration",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "child_id": str(record.child_id),
            "outcome": record.outcome,
            "version": record.version,
        },
    )
    commit_in_context(session, context)
    return _administration_response(session, record)


@router.post(
    "/administrations/{record_id}/void",
    response_model=MedicationAdministrationResponse,
)
def void_medication_administration(
    record_id: UUID,
    payload: MedicationAdministrationVoidRequest,
    request: Request,
    response: Response,
    context: MedicationVoidContext,
    session: SessionDependency,
) -> MedicationAdministrationResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _administration_replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "voided",
        record_id=record_id,
        expected_after={"void_reason": payload.reason},
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _administration_response(session, replay)
    preliminary_record, _ = _administration_access(
        session,
        context,
        record_id,
    )
    preliminary_facility_id = preliminary_record.facility_id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("medication:void",),
        conceal_detail="Medication record not found",
    )
    record, _, _, facility = _locked_administration_context(session, context, record_id)
    if record.facility_id != preliminary_facility_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "medication_source_integrity_unknown"},
        )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    if record.voided_at is not None:
        raise HTTPException(status_code=409, detail="Medication record is already voided")
    _check_version(record.version, payload.expected_version)
    before = _administration_snapshot(record)
    record.voided_at = datetime.now(UTC)
    record.voided_by_user_id = context.user.id
    record.void_reason = payload.reason
    record.version += 1
    _append_administration_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="voided",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="medication.administration.voided",
        entity_type="medication_administration",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={"child_id": str(record.child_id), "version": record.version},
    )
    commit_in_context(session, context)
    return _administration_response(session, record)


@router.get(
    "/administrations/{record_id}/history",
    response_model=list[MedicationAdministrationEventResponse],
)
def medication_administration_history(
    record_id: UUID,
    response: Response,
    context: MedicationReadContext,
    session: SessionDependency,
) -> list[MedicationAdministrationEventResponse]:
    record = session.scalar(
        select(MedicationAdministration).where(
            MedicationAdministration.organization_id == context.organization.id,
            MedicationAdministration.id == record_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Medication record not found")
    facility, _ = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=True,
    )
    if not context.organization_wide and record.service_date != _local_date(facility):
        raise HTTPException(status_code=404, detail="Medication record not found")
    events = _administration_events(session, record)
    names = _user_names(session, {event.actor_user_id for event in events})
    _private_no_store(response)
    return [
        MedicationAdministrationEventResponse(
            id=event.id,
            medication_administration_id=event.medication_administration_id,
            actor_user_id=event.actor_user_id,
            actor_name=names.get(event.actor_user_id, "Former staff"),
            client_operation_id=event.client_operation_id,
            event_type=event.event_type,
            occurred_at=aware_utc(event.occurred_at),
            reason=event.reason,
            before=event.before,
            after=event.after,
        )
        for event in events
    ]
