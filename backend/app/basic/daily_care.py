"""Daily-care projection helpers shared by care and attendance workflows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.basic.models import DailyCareRecord, DailyCareRecordEvent
from app.basic.security import audit


def aware_utc(value: datetime) -> datetime:
    """Normalize stored SQLite-naive and API-aware values to aware UTC."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def care_record_snapshot(record: DailyCareRecord) -> dict[str, Any]:
    """Return the complete domain snapshot kept only in the protected ledger."""

    return {
        "id": str(record.id),
        "attendance_day_id": str(record.attendance_day_id),
        "facility_id": str(record.facility_id),
        "room_id": str(record.room_id),
        "child_id": str(record.child_id),
        "enrollment_id": str(record.enrollment_id),
        "service_date": record.service_date.isoformat(),
        "care_type": record.care_type,
        "occurred_at": aware_utc(record.occurred_at).isoformat(),
        "ended_at": aware_utc(record.ended_at).isoformat() if record.ended_at else None,
        "payload": dict(record.payload or {}),
        "note": record.note,
        "created_by_user_id": str(record.created_by_user_id),
        "version": record.version,
        "voided_at": aware_utc(record.voided_at).isoformat() if record.voided_at else None,
        "voided_by_user_id": str(record.voided_by_user_id) if record.voided_by_user_id else None,
        "void_reason": record.void_reason,
    }


def auto_finish_open_sleep(
    session: Session,
    *,
    organization_id: UUID,
    attendance_day_id: UUID,
    actor_user_id: UUID,
    checked_out_at: datetime,
    facility_id: UUID,
    records: Sequence[DailyCareRecord] | None = None,
) -> list[DailyCareRecord]:
    """Close any open sleep without making child checkout depend on clean-up.

    Backdated checkout cannot rewrite an observed care time. Callers must reject
    a checkout that would place any existing care fact outside attendance.
    """

    checked_out_at = aware_utc(checked_out_at)
    open_sleeps = (
        [
            record
            for record in records
            if record.organization_id == organization_id
            and record.attendance_day_id == attendance_day_id
            and record.care_type == "sleep"
            and record.ended_at is None
            and record.voided_at is None
        ]
        if records is not None
        else list(
            session.scalars(
                select(DailyCareRecord)
                .where(
                    DailyCareRecord.organization_id == organization_id,
                    DailyCareRecord.attendance_day_id == attendance_day_id,
                    DailyCareRecord.care_type == "sleep",
                    DailyCareRecord.ended_at.is_(None),
                    DailyCareRecord.voided_at.is_(None),
                )
                .order_by(DailyCareRecord.id)
                .with_for_update()
            )
        )
    )
    for record in open_sleeps:
        if checked_out_at < aware_utc(record.occurred_at):
            raise HTTPException(
                status_code=409,
                detail="Check-out cannot precede an open sleep record",
            )
        before = care_record_snapshot(record)
        record.ended_at = checked_out_at
        record.version += 1
        session.add(
            DailyCareRecordEvent(
                id=uuid4(),
                organization_id=organization_id,
                care_record_id=record.id,
                actor_user_id=actor_user_id,
                client_operation_id=uuid4(),
                event_type="auto_finished_at_checkout",
                before=before,
                after=care_record_snapshot(record),
            )
        )
        audit(
            session,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="care.sleep.auto_finished_at_checkout",
            entity_type="daily_care_record",
            entity_id=record.id,
            facility_id=facility_id,
            details={
                "care_type": "sleep",
                "child_id": str(record.child_id),
                "version": record.version,
            },
        )
    return open_sleeps
