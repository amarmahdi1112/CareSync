"""Internal incident workflow and manual external-report tracking.

CareSync records internal workflow state and externally supplied confirmation
metadata. It does not submit an incident to Alberta or any other authority.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, or_, select

from app.api.basic.care import (
    _attendance_day,
    _attendance_interval,
    _attendance_intervals,
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
    IncidentCreateContext,
    IncidentExternalReportContext,
    IncidentReadContext,
    IncidentReviewContext,
    IncidentUpdateContext,
    refresh_basic_context,
)
from app.api.dependencies import SessionDependency
from app.basic.daily_care import aware_utc
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    Facility,
    IncidentRecord,
    IncidentRecordEvent,
    Room,
    User,
)
from app.basic.notifications import notify_organization_members, notify_user
from app.basic.schemas import (
    IncidentAttendanceOption,
    IncidentCreateRequest,
    IncidentEventResponse,
    IncidentExternalReportRequest,
    IncidentFinalizeRequest,
    IncidentListResponse,
    IncidentResponse,
    IncidentReturnDraftRequest,
    IncidentRoomContextResponse,
    IncidentTransitionRequest,
    IncidentUpdateRequest,
)
from app.basic.security import audit
from app.basic.shift_guards import require_open_shift

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _user_names(session: SessionDependency, user_ids: set[UUID]) -> dict[UUID, str]:
    return {
        user_id: f"{first_name} {last_name}".strip()
        for user_id, first_name, last_name in session.execute(
            select(User.id, User.first_name, User.last_name).where(
                User.id.in_(user_ids) if user_ids else False
            )
        )
    }


def _snapshot(record: IncidentRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "facility_id": str(record.facility_id),
        "room_id": str(record.room_id),
        "child_id": str(record.child_id) if record.child_id else None,
        "enrollment_id": str(record.enrollment_id) if record.enrollment_id else None,
        "attendance_day_id": str(record.attendance_day_id) if record.attendance_day_id else None,
        "service_date": record.service_date.isoformat(),
        "occurred_at": aware_utc(record.occurred_at).isoformat(),
        "category": record.category,
        "severity": record.severity,
        "summary": record.summary,
        "immediate_actions": record.immediate_actions,
        "medical_attention": record.medical_attention,
        "parent_notification_status": record.parent_notification_status,
        "parent_notified_at": (
            aware_utc(record.parent_notified_at).isoformat() if record.parent_notified_at else None
        ),
        "parent_notification_notes": record.parent_notification_notes,
        "authorities_contacted": list(record.authorities_contacted or []),
        "staff_present": list(record.staff_present or []),
        "status": record.status,
        "reportability_assessment": record.reportability_assessment,
        "reviewer_note": record.reviewer_note,
        "finalized_at": (
            aware_utc(record.finalized_at).isoformat() if record.finalized_at else None
        ),
        "finalized_by_user_id": (
            str(record.finalized_by_user_id) if record.finalized_by_user_id else None
        ),
        "external_report_status": record.external_report_status,
        "external_reported_at": (
            aware_utc(record.external_reported_at).isoformat()
            if record.external_reported_at
            else None
        ),
        "external_confirmation_reference": record.external_confirmation_reference,
        "external_submission_channel": record.external_submission_channel,
        "external_submitted_by_name": record.external_submitted_by_name,
        "external_report_recorded_by_user_id": (
            str(record.external_report_recorded_by_user_id)
            if record.external_report_recorded_by_user_id
            else None
        ),
        "created_by_user_id": str(record.created_by_user_id),
        "version": record.version,
    }


def _events(session: SessionDependency, record: IncidentRecord) -> list[IncidentRecordEvent]:
    return list(
        session.scalars(
            select(IncidentRecordEvent)
            .where(
                IncidentRecordEvent.organization_id == record.organization_id,
                IncidentRecordEvent.incident_record_id == record.id,
            )
            .order_by(IncidentRecordEvent.occurred_at, IncidentRecordEvent.id)
        )
    )


def _reporting_timeline(assessment: str) -> str:
    return {
        "unassessed": "not_assessed",
        "not_reportable": "not_reportable",
        "critical": "as_soon_as_possible_no_later_than_24_hours",
        "other_reportable": "within_2_business_days",
    }[assessment]


def _response(
    session: SessionDependency,
    record: IncidentRecord,
    *,
    facility: Facility | None = None,
    room: Room | None = None,
    child: Child | None = None,
    events: Sequence[IncidentRecordEvent] | None = None,
    user_names: dict[UUID, str] | None = None,
) -> IncidentResponse:
    resolved_facility = facility or session.scalar(
        select(Facility).where(
            Facility.organization_id == record.organization_id,
            Facility.id == record.facility_id,
        )
    )
    resolved_room = room or session.scalar(
        select(Room).where(
            Room.organization_id == record.organization_id,
            Room.id == record.room_id,
        )
    )
    resolved_child = child
    if resolved_child is None and record.child_id is not None:
        resolved_child = session.scalar(
            select(Child).where(
                Child.organization_id == record.organization_id,
                Child.id == record.child_id,
            )
        )
    if resolved_facility is None or resolved_room is None:
        raise HTTPException(status_code=409, detail="Incident location is unavailable")
    resolved_events = list(events) if events is not None else _events(session, record)
    if not resolved_events:
        raise HTTPException(status_code=409, detail="Incident history is unavailable")
    creator_name = (
        user_names.get(record.created_by_user_id, "Former staff")
        if user_names is not None
        else _user_names(session, {record.created_by_user_id}).get(
            record.created_by_user_id, "Former staff"
        )
    )
    return IncidentResponse(
        id=record.id,
        organization_id=record.organization_id,
        facility_id=record.facility_id,
        facility_name=resolved_facility.name,
        facility_timezone=resolved_facility.timezone,
        room_id=record.room_id,
        room_name=resolved_room.name,
        child_id=record.child_id,
        child_name=(
            f"{resolved_child.first_name} {resolved_child.last_name}".strip()
            if resolved_child
            else None
        ),
        enrollment_id=record.enrollment_id,
        attendance_day_id=record.attendance_day_id,
        service_date=record.service_date,
        occurred_at=aware_utc(record.occurred_at),
        category=record.category,
        severity=record.severity,
        summary=record.summary,
        immediate_actions=record.immediate_actions,
        medical_attention=record.medical_attention,
        parent_notification_status=record.parent_notification_status,
        parent_notified_at=(
            aware_utc(record.parent_notified_at) if record.parent_notified_at else None
        ),
        parent_notification_notes=record.parent_notification_notes,
        authorities_contacted=list(record.authorities_contacted or []),
        staff_present=list(record.staff_present or []),
        status=record.status,
        reportability_assessment=record.reportability_assessment,
        reporting_timeline=_reporting_timeline(record.reportability_assessment),
        reviewer_note=record.reviewer_note,
        finalized_at=aware_utc(record.finalized_at) if record.finalized_at else None,
        finalized_by_user_id=record.finalized_by_user_id,
        external_report_status=record.external_report_status,
        external_reported_at=(
            aware_utc(record.external_reported_at) if record.external_reported_at else None
        ),
        external_confirmation_reference=record.external_confirmation_reference,
        external_submission_channel=record.external_submission_channel,
        external_submitted_by_name=record.external_submitted_by_name,
        external_report_recorded_by_user_id=record.external_report_recorded_by_user_id,
        created_by_user_id=record.created_by_user_id,
        created_by_name=creator_name,
        version=record.version,
        last_event_type=resolved_events[-1].event_type,
        created_at=aware_utc(record.created_at),
        updated_at=aware_utc(record.updated_at),
    )


def _event_by_operation(
    session: SessionDependency, organization_id: UUID, operation_id: UUID
) -> IncidentRecordEvent | None:
    return session.scalar(
        select(IncidentRecordEvent).where(
            IncidentRecordEvent.organization_id == organization_id,
            IncidentRecordEvent.client_operation_id == operation_id,
        )
    )


def _record_access(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
    *,
    lock: bool = False,
    allow_inactive_organization_read: bool = True,
) -> tuple[IncidentRecord, Facility, Room, Child | None]:
    statement = select(IncidentRecord).where(
        IncidentRecord.organization_id == context.organization.id,
        IncidentRecord.id == record_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    record = session.scalar(statement)
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    facility, room = _room_access(
        session,
        context,
        record.room_id,
        expected_facility_id=record.facility_id,
        allow_inactive_organization_read=allow_inactive_organization_read,
    )
    child = None
    if record.child_id is not None:
        child = session.scalar(
            select(Child).where(
                Child.organization_id == context.organization.id,
                Child.id == record.child_id,
            )
        )
    if not context.organization_wide and record.service_date != _local_date(facility):
        raise HTTPException(status_code=404, detail="Incident not found")
    return record, facility, room, child


def _locked_record_context(
    session: SessionDependency,
    context: BasicContext,
    record_id: UUID,
) -> tuple[IncidentRecord, Facility, Room, Child | None, list[AttendanceInterval]]:
    snapshot, _, _, _ = _record_access(session, context, record_id)
    intervals: list[AttendanceInterval] = []
    if snapshot.attendance_day_id is not None:
        day = _attendance_day(
            session, context.organization.id, snapshot.attendance_day_id, lock=True
        )
        intervals = _attendance_intervals(session, day, lock=True)
    record, facility, room, child = _record_access(session, context, record_id, lock=True)
    return record, facility, room, child, intervals


def _replay(
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
) -> IncidentRecord | None:
    event = _event_by_operation(session, context.organization.id, operation_id)
    if event is None:
        return None
    if event.actor_user_id != context.user.id:
        raise HTTPException(status_code=404, detail="Incident not found")
    preliminary = session.scalar(
        select(IncidentRecord).where(
            IncidentRecord.organization_id == context.organization.id,
            IncidentRecord.id == event.incident_record_id,
        )
    )
    if preliminary is None:
        raise HTTPException(status_code=409, detail="Incident is unavailable")
    _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary.facility_id,
    )
    current_context = refresh_basic_context(
        session,
        context,
        required_any_permissions={
            "drafted": ("incident:create",),
            "updated": ("incident:update", "incident:update_own"),
            "submitted_for_review": ("incident:create",),
            "returned_to_draft": ("incident:review",),
            "finalized": ("incident:review",),
            "external_report_recorded": ("incident:external_report",),
        }[event_type],
        conceal_detail="Incident not found",
    )
    record, _, _, _ = _record_access(
        session,
        current_context,
        event.incident_record_id,
    )
    if event_type == "updated":
        _ensure_incident_update_access(
            current_context,
            record,
            conceal=True,
        )
    elif event_type == "submitted_for_review":
        _ensure_incident_submit_access(
            current_context,
            record,
            conceal=True,
        )
    if event.event_type != event_type or (
        record_id is not None and event.incident_record_id != record_id
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


def _ensure_incident_update_access(
    context: BasicContext,
    record: IncidentRecord,
    *,
    conceal: bool = False,
) -> None:
    permissions = set(context.role.permissions or [])
    if (
        "incident:update" in permissions
        or record.created_by_user_id == context.user.id
    ):
        return
    raise HTTPException(
        status_code=404 if conceal else 403,
        detail=(
            "Incident not found"
            if conceal
            else "Educators can update only their own drafts"
        ),
    )


def _ensure_incident_submit_access(
    context: BasicContext,
    record: IncidentRecord,
    *,
    conceal: bool = False,
) -> None:
    if context.organization_wide or record.created_by_user_id == context.user.id:
        return
    raise HTTPException(
        status_code=404 if conceal else 403,
        detail=(
            "Incident not found"
            if conceal
            else "Educators can submit only their own drafts"
        ),
    )


def _draft_payload_expected(
    payload: IncidentCreateRequest | IncidentUpdateRequest,
) -> dict[str, Any]:
    return {
        "occurred_at": aware_utc(payload.occurred_at).isoformat(),
        "category": payload.category,
        "severity": payload.severity,
        "summary": payload.summary,
        "immediate_actions": payload.immediate_actions,
        "medical_attention": payload.medical_attention,
        "parent_notification_status": payload.parent_notification_status,
        "parent_notified_at": (
            aware_utc(payload.parent_notified_at).isoformat()
            if payload.parent_notified_at
            else None
        ),
        "parent_notification_notes": payload.parent_notification_notes,
        "authorities_contacted": list(payload.authorities_contacted),
        "staff_present": list(payload.staff_present),
    }


def _append_event(
    session: SessionDependency,
    context: BasicContext,
    record: IncidentRecord,
    *,
    operation_id: UUID,
    event_type: str,
    before: dict[str, Any] | None,
    reason: str | None = None,
) -> IncidentRecordEvent:
    event = IncidentRecordEvent(
        id=uuid4(),
        organization_id=context.organization.id,
        incident_record_id=record.id,
        actor_user_id=context.user.id,
        client_operation_id=operation_id,
        event_type=event_type,
        reason=reason,
        before=before,
        after=_snapshot(record),
    )
    session.add(event)
    return event


def _check_version(record: IncidentRecord, expected: int) -> None:
    if record.version != expected:
        raise HTTPException(status_code=409, detail="Incident version has changed")


def _validate_time(facility: Facility, occurred_at: datetime) -> tuple[datetime, date]:
    occurred = aware_utc(occurred_at)
    if occurred > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Incident time cannot be in the future")
    return occurred, _local_date(facility, occurred)


def _validate_parent_notification_time(
    occurred_at: datetime,
    parent_notified_at: datetime | None,
) -> None:
    if parent_notified_at is None:
        return
    notified_at = aware_utc(parent_notified_at)
    if notified_at < occurred_at:
        raise HTTPException(
            status_code=422,
            detail="Parent notification cannot precede the incident",
        )
    if notified_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(
            status_code=422,
            detail="Parent notification time cannot be in the future",
        )


def _apply_draft_fields(
    record: IncidentRecord, payload: IncidentCreateRequest | IncidentUpdateRequest
) -> None:
    record.occurred_at = aware_utc(payload.occurred_at)
    record.category = payload.category
    record.severity = payload.severity
    record.summary = payload.summary
    record.immediate_actions = payload.immediate_actions
    record.medical_attention = payload.medical_attention
    record.parent_notification_status = payload.parent_notification_status
    record.parent_notified_at = (
        aware_utc(payload.parent_notified_at) if payload.parent_notified_at else None
    )
    record.parent_notification_notes = payload.parent_notification_notes
    record.authorities_contacted = list(payload.authorities_contacted)
    record.staff_present = list(payload.staff_present)


@router.get("/rooms/{room_id}/context", response_model=IncidentRoomContextResponse)
def incident_room_context(
    room_id: UUID,
    response: Response,
    context: IncidentReadContext,
    session: SessionDependency,
    service_date: Annotated[date, Query(alias="date")],
) -> IncidentRoomContextResponse:
    facility, room = _room_access(session, context, room_id, allow_inactive_organization_read=True)
    if not context.organization_wide and service_date != _local_date(facility):
        raise HTTPException(
            status_code=403,
            detail="Educators can access only today's assigned-room incident context",
        )
    rows = list(
        session.execute(
            select(AttendanceDay, Child)
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
                AttendanceDay.status == "present",
            )
            .order_by(Child.last_name, Child.first_name, Child.id)
        )
    )
    day_ids = [day.id for day, _ in rows]
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
    _private_no_store(response)
    return IncidentRoomContextResponse(
        organization_id=context.organization.id,
        facility_id=facility.id,
        facility_name=facility.name,
        facility_timezone=facility.timezone,
        room_id=room.id,
        room_name=room.name,
        service_date=service_date,
        generated_at=datetime.now(UTC),
        attendance_options=[
            IncidentAttendanceOption(
                attendance_day_id=day.id,
                child_id=child.id,
                child_name=f"{child.first_name} {child.last_name}".strip(),
                attendance_state=(
                    "on_site"
                    if any(item.checked_out_at is None for item in intervals_by_day.get(day.id, ()))
                    else "checked_out"
                ),
            )
            for day, child in rows
            if intervals_by_day.get(day.id)
        ],
    )


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    response: Response,
    context: IncidentReadContext,
    session: SessionDependency,
    facility_id: Annotated[UUID | None, Query()] = None,
    room_id: Annotated[UUID | None, Query()] = None,
    incident_status: Annotated[str | None, Query(alias="status")] = None,
) -> IncidentListResponse:
    if incident_status is not None and incident_status not in {
        "draft",
        "under_review",
        "finalized",
    }:
        raise HTTPException(status_code=422, detail="Invalid incident status")
    statement = select(IncidentRecord).where(
        IncidentRecord.organization_id == context.organization.id
    )
    if facility_id is not None:
        statement = statement.where(IncidentRecord.facility_id == facility_id)
    if room_id is not None:
        statement = statement.where(IncidentRecord.room_id == room_id)
    if incident_status is not None:
        statement = statement.where(IncidentRecord.status == incident_status)
    if not context.organization_wide:
        current_by_facility: list[Any] = []
        for assigned_facility_id in context.assigned_facility_ids:
            facility = session.scalar(
                select(Facility).where(
                    Facility.organization_id == context.organization.id,
                    Facility.id == assigned_facility_id,
                    Facility.status == "active",
                )
            )
            if facility is not None:
                current_by_facility.append(
                    and_(
                        IncidentRecord.facility_id == facility.id,
                        IncidentRecord.service_date == _local_date(facility),
                    )
                )
        if not current_by_facility:
            statement = statement.where(False)
        else:
            statement = statement.where(
                IncidentRecord.room_id.in_(context.assigned_room_ids),
                or_(*current_by_facility),
            )
    records = list(
        session.scalars(statement.order_by(IncidentRecord.occurred_at.desc(), IncidentRecord.id))
    )
    facilities = {
        item.id: item
        for item in session.scalars(
            select(Facility).where(
                Facility.organization_id == context.organization.id,
                Facility.id.in_({item.facility_id for item in records}) if records else False,
            )
        )
    }
    rooms = {
        item.id: item
        for item in session.scalars(
            select(Room).where(
                Room.organization_id == context.organization.id,
                Room.id.in_({item.room_id for item in records}) if records else False,
            )
        )
    }
    children = {
        item.id: item
        for item in session.scalars(
            select(Child).where(
                Child.organization_id == context.organization.id,
                Child.id.in_({item.child_id for item in records if item.child_id})
                if any(item.child_id for item in records)
                else False,
            )
        )
    }
    events_by_record: dict[UUID, list[IncidentRecordEvent]] = {}
    if records:
        for event in session.scalars(
            select(IncidentRecordEvent)
            .where(
                IncidentRecordEvent.organization_id == context.organization.id,
                IncidentRecordEvent.incident_record_id.in_([item.id for item in records]),
            )
            .order_by(IncidentRecordEvent.occurred_at, IncidentRecordEvent.id)
        ):
            events_by_record.setdefault(event.incident_record_id, []).append(event)
    names = _user_names(session, {item.created_by_user_id for item in records})
    _private_no_store(response)
    return IncidentListResponse(
        organization_id=context.organization.id,
        generated_at=datetime.now(UTC),
        incidents=[
            _response(
                session,
                record,
                facility=facilities.get(record.facility_id),
                room=rooms.get(record.room_id),
                child=children.get(record.child_id) if record.child_id else None,
                events=events_by_record.get(record.id, ()),
                user_names=names,
            )
            for record in records
        ],
    )


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreateRequest,
    request: Request,
    response: Response,
    context: IncidentCreateContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "drafted",
        expected_after={
            **_draft_payload_expected(payload),
            "facility_id": str(payload.facility_id),
            "room_id": str(payload.room_id),
            "attendance_day_id": (
                str(payload.attendance_day_id) if payload.attendance_day_id else None
            ),
        },
    )
    if replay is not None:
        return _response(session, replay)
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        payload.facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("incident:create",),
        conceal_detail="Room not found",
    )
    facility, room = _room_access(
        session,
        context,
        payload.room_id,
        expected_facility_id=payload.facility_id,
    )
    require_open_shift(
        session,
        context,
        facility.id,
        room.id,
        enforce_room_presence=live_room_safety,
    )
    occurred_at, service_date = _validate_time(facility, payload.occurred_at)
    _validate_parent_notification_time(occurred_at, payload.parent_notified_at)
    if not context.organization_wide and service_date != _local_date(facility):
        raise HTTPException(status_code=403, detail="Educators can record only today's incidents")
    child: Child | None = None
    child_id = enrollment_id = None
    if payload.attendance_day_id is not None:
        day = _attendance_day(
            session, context.organization.id, payload.attendance_day_id, lock=True
        )
        intervals = _attendance_intervals(session, day, lock=True)
        if (
            day.facility_id != facility.id
            or day.room_id != room.id
            or day.service_date != service_date
            or day.status != "present"
        ):
            raise HTTPException(status_code=409, detail="Incident attendance identity is invalid")
        _attendance_interval(
            session,
            day,
            occurred_at,
            ended_at=None,
            require_open=False,
            intervals=intervals,
        )
        child_id = day.child_id
        enrollment_id = day.enrollment_id
        child = session.scalar(
            select(Child).where(
                Child.organization_id == context.organization.id,
                Child.id == child_id,
            )
        )
    record = IncidentRecord(
        id=uuid4(),
        organization_id=context.organization.id,
        facility_id=facility.id,
        room_id=room.id,
        child_id=child_id,
        enrollment_id=enrollment_id,
        attendance_day_id=payload.attendance_day_id,
        service_date=service_date,
        occurred_at=occurred_at,
        category=payload.category,
        severity=payload.severity,
        summary=payload.summary,
        immediate_actions=payload.immediate_actions,
        medical_attention=payload.medical_attention,
        parent_notification_status=payload.parent_notification_status,
        parent_notified_at=(
            aware_utc(payload.parent_notified_at) if payload.parent_notified_at else None
        ),
        parent_notification_notes=payload.parent_notification_notes,
        authorities_contacted=list(payload.authorities_contacted),
        staff_present=list(payload.staff_present),
        status="draft",
        reportability_assessment="unassessed",
        external_report_status="not_assessed",
        created_by_user_id=context.user.id,
        version=1,
    )
    session.add(record)
    flush_or_conflict(session, "Incident conflicts with another update")
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="drafted",
        before=None,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.drafted",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "child_id": str(record.child_id) if record.child_id else None,
            "category": record.category,
            "severity": record.severity,
            "version": record.version,
        },
    )
    commit_in_context(session, context, "Incident conflicts with another update")
    return _response(session, record, facility=facility, room=room, child=child)


@router.get("/{record_id}", response_model=IncidentResponse)
def get_incident(
    record_id: UUID,
    response: Response,
    context: IncidentReadContext,
    session: SessionDependency,
) -> IncidentResponse:
    record, facility, room, child = _record_access(session, context, record_id)
    _private_no_store(response)
    return _response(session, record, facility=facility, room=room, child=child)


@router.put("/{record_id}", response_model=IncidentResponse)
def update_incident(
    record_id: UUID,
    payload: IncidentUpdateRequest,
    request: Request,
    response: Response,
    context: IncidentUpdateContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "updated",
        record_id=record_id,
        expected_after=_draft_payload_expected(payload),
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _response(session, replay)
    preliminary_record, preliminary_facility, _, _ = _record_access(
        session,
        context,
        record_id,
    )
    preliminary_facility_id = preliminary_facility.id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("incident:update", "incident:update_own"),
        conceal_detail="Incident not found",
    )
    record, facility, room, child, intervals = _locked_record_context(session, context, record_id)
    if (
        record.id != preliminary_record.id
        or facility.id != preliminary_facility_id
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "incident_source_integrity_unknown"},
        )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    if record.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft incidents can be edited")
    _ensure_incident_update_access(context, record)
    _check_version(record, payload.expected_version)
    occurred_at, service_date = _validate_time(facility, payload.occurred_at)
    _validate_parent_notification_time(occurred_at, payload.parent_notified_at)
    if service_date != record.service_date:
        raise HTTPException(status_code=422, detail="Incident service date cannot change")
    if record.attendance_day_id is not None:
        day = _attendance_day(session, context.organization.id, record.attendance_day_id)
        _attendance_interval(
            session,
            day,
            occurred_at,
            ended_at=None,
            require_open=False,
            intervals=intervals,
        )
    before = _snapshot(record)
    _apply_draft_fields(record, payload)
    record.version += 1
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="updated",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.updated",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={"version": record.version},
    )
    commit_in_context(session, context)
    return _response(session, record, facility=facility, room=room, child=child)


@router.post("/{record_id}/submit-review", response_model=IncidentResponse)
def submit_incident_review(
    record_id: UUID,
    payload: IncidentTransitionRequest,
    request: Request,
    response: Response,
    context: IncidentCreateContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "submitted_for_review",
        record_id=record_id,
        expected_after={"status": "under_review"},
        expected_before_version=payload.expected_version,
    )
    if replay is not None:
        return _response(session, replay)
    preliminary_record, preliminary_facility, _, _ = _record_access(
        session,
        context,
        record_id,
    )
    preliminary_facility_id = preliminary_facility.id
    live_room_safety = _lock_room_safety_lane(
        request,
        session,
        context,
        preliminary_facility_id,
    )
    context = refresh_basic_context(
        session,
        context,
        required_any_permissions=("incident:create",),
        conceal_detail="Incident not found",
    )
    record, facility, room, child, _ = _locked_record_context(session, context, record_id)
    if (
        record.id != preliminary_record.id
        or facility.id != preliminary_facility_id
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "incident_source_integrity_unknown"},
        )
    require_open_shift(
        session,
        context,
        facility.id,
        record.room_id,
        enforce_room_presence=live_room_safety,
    )
    if record.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft incidents can be submitted")
    _ensure_incident_submit_access(context, record)
    _check_version(record, payload.expected_version)
    before = _snapshot(record)
    record.status = "under_review"
    record.version += 1
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="submitted_for_review",
        before=before,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.submitted_for_review",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={"version": record.version},
    )
    notify_organization_members(
        session,
        organization_id=context.organization.id,
        permission_keys={"incident:review"},
        event_key=f"incident-review:{record.id}:{record.version}",
        category="operations",
        severity="critical" if record.severity in {"serious", "critical"} else "info",
        title="Incident review required",
        body="An incident report is ready for authorized review.",
        action_path="/incidents",
        action_entity_type="incident_record",
        action_entity_id=record.id,
        facility_id=record.facility_id,
        room_id=record.room_id,
        organization_wide_only=record.room_id is None,
    )
    commit_in_context(session, context)
    return _response(session, record, facility=facility, room=room, child=child)


@router.post("/{record_id}/return-draft", response_model=IncidentResponse)
def return_incident_to_draft(
    record_id: UUID,
    payload: IncidentReturnDraftRequest,
    request: Request,
    response: Response,
    context: IncidentReviewContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "returned_to_draft",
        record_id=record_id,
        expected_after={"status": "draft"},
        expected_before_version=payload.expected_version,
        expected_reason=payload.reason,
    )
    if replay is not None:
        return _response(session, replay)
    record, facility, room, child, _ = _locked_record_context(session, context, record_id)
    if record.status != "under_review":
        raise HTTPException(status_code=409, detail="Only reviewed incidents can return to draft")
    _check_version(record, payload.expected_version)
    before = _snapshot(record)
    record.status = "draft"
    record.version += 1
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="returned_to_draft",
        before=before,
        reason=payload.reason,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.returned_to_draft",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={"version": record.version},
    )
    notify_user(
        session,
        user_id=record.created_by_user_id,
        organization_id=context.organization.id,
        event_key=f"incident-returned:{record.id}:{record.version}",
        category="operations",
        severity="warning",
        title="Incident report needs changes",
        body="An incident reviewer returned your report with feedback.",
        action_path="/incidents",
        action_entity_type="incident_record",
        action_entity_id=record.id,
    )
    commit_in_context(session, context)
    return _response(session, record, facility=facility, room=room, child=child)


@router.post("/{record_id}/finalize", response_model=IncidentResponse)
def finalize_incident(
    record_id: UUID,
    payload: IncidentFinalizeRequest,
    request: Request,
    response: Response,
    context: IncidentReviewContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "finalized",
        record_id=record_id,
        expected_after={
            "status": "finalized",
            "reportability_assessment": payload.reportability_assessment,
            "reviewer_note": payload.reviewer_note,
            "external_report_status": (
                "not_required"
                if payload.reportability_assessment == "not_reportable"
                else "pending"
            ),
        },
        expected_before_version=payload.expected_version,
        expected_reason=payload.reviewer_note,
    )
    if replay is not None:
        return _response(session, replay)
    record, facility, room, child, _ = _locked_record_context(session, context, record_id)
    if record.status != "under_review":
        raise HTTPException(status_code=409, detail="Only reviewed incidents can be finalized")
    if record.parent_notification_status == "pending":
        raise HTTPException(
            status_code=409,
            detail="Resolve the parent notification status before finalizing",
        )
    _check_version(record, payload.expected_version)
    before = _snapshot(record)
    record.status = "finalized"
    record.reportability_assessment = payload.reportability_assessment
    record.reviewer_note = payload.reviewer_note
    record.finalized_at = datetime.now(UTC)
    record.finalized_by_user_id = context.user.id
    record.external_report_status = (
        "not_required" if payload.reportability_assessment == "not_reportable" else "pending"
    )
    record.version += 1
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="finalized",
        before=before,
        reason=payload.reviewer_note,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.finalized",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "reportability_assessment": record.reportability_assessment,
            "version": record.version,
        },
    )
    notify_user(
        session,
        user_id=record.created_by_user_id,
        organization_id=context.organization.id,
        event_key=f"incident-finalized:{record.id}:{record.version}",
        category="operations",
        severity=(
            "critical" if record.reportability_assessment == "reportable" else "success"
        ),
        title="Incident review completed",
        body="An authorized reviewer completed the incident review.",
        action_path="/incidents",
        action_entity_type="incident_record",
        action_entity_id=record.id,
    )
    if record.reportability_assessment == "reportable":
        notify_organization_members(
            session,
            organization_id=context.organization.id,
            permission_keys={"incident:external_report"},
            event_key=f"incident-external-report:{record.id}:{record.version}",
            category="operations",
            severity="critical",
            title="External incident action required",
            body="A finalized incident requires authorized external-report follow-up.",
            action_path="/incidents",
            action_entity_type="incident_record",
            action_entity_id=record.id,
            facility_id=record.facility_id,
            room_id=record.room_id,
            organization_wide_only=record.room_id is None,
        )
    commit_in_context(session, context)
    return _response(session, record, facility=facility, room=room, child=child)


@router.post("/{record_id}/external-report", response_model=IncidentResponse)
def record_external_report(
    record_id: UUID,
    payload: IncidentExternalReportRequest,
    request: Request,
    response: Response,
    context: IncidentExternalReportContext,
    session: SessionDependency,
) -> IncidentResponse:
    ensure_writable(request)
    _private_no_store(response)
    lock_client_operation(session, context.organization.id, payload.client_operation_id)
    replay = _replay(
        session,
        context,
        request,
        payload.client_operation_id,
        "external_report_recorded",
        record_id=record_id,
        expected_after={
            "external_report_status": "recorded",
            "external_reported_at": aware_utc(payload.reported_at).isoformat(),
            "external_confirmation_reference": payload.confirmation_reference,
            "external_submission_channel": payload.submission_channel,
            "external_submitted_by_name": payload.submitted_by_name,
        },
        expected_before_version=payload.expected_version,
    )
    if replay is not None:
        return _response(session, replay)
    record, facility, room, child, _ = _locked_record_context(session, context, record_id)
    if record.status != "finalized" or record.external_report_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only a finalized reportable incident can record external confirmation",
        )
    _check_version(record, payload.expected_version)
    reported_at = aware_utc(payload.reported_at)
    if reported_at < aware_utc(record.occurred_at):
        raise HTTPException(status_code=422, detail="External report cannot precede the incident")
    if reported_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="External report time cannot be in the future")
    before = _snapshot(record)
    record.external_report_status = "recorded"
    record.external_reported_at = reported_at
    record.external_confirmation_reference = payload.confirmation_reference
    record.external_submission_channel = payload.submission_channel
    record.external_submitted_by_name = payload.submitted_by_name
    record.external_report_recorded_by_user_id = context.user.id
    record.version += 1
    _append_event(
        session,
        context,
        record,
        operation_id=payload.client_operation_id,
        event_type="external_report_recorded",
        before=before,
    )
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="incident.external_report_confirmation_recorded",
        entity_type="incident_record",
        entity_id=record.id,
        facility_id=record.facility_id,
        details={
            "external_report_status": record.external_report_status,
            "version": record.version,
            "caresync_submitted": False,
        },
    )
    commit_in_context(session, context)
    return _response(session, record, facility=facility, room=room, child=child)


@router.get("/{record_id}/history", response_model=list[IncidentEventResponse])
def incident_history(
    record_id: UUID,
    response: Response,
    context: IncidentReadContext,
    session: SessionDependency,
) -> list[IncidentEventResponse]:
    record, _, _, _ = _record_access(session, context, record_id)
    events = _events(session, record)
    names = _user_names(session, {event.actor_user_id for event in events})
    _private_no_store(response)
    return [
        IncidentEventResponse(
            id=event.id,
            incident_record_id=event.incident_record_id,
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
