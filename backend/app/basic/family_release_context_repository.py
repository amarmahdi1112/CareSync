"""Minimum-necessary repositories for the 0029B release-context composer.

PostgreSQL reads through the hardened SECURITY DEFINER projection installed by
0029B.  SQLite uses equivalent tenant, operational and authority queries for
portable tests and local development.  Neither path writes domain, audit,
notification, command-receipt or realtime state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.basic.dependencies import BasicContext
from app.basic.family_release_context_schemas import ReleaseContextInput
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    Child,
    ChildAuthorityHead,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    Enrollment,
    Facility,
    Family,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityPerson,
    FamilyAuthorityPersonVersion,
    MembershipRoomAssignment,
    Room,
    StaffShift,
)


@dataclass(frozen=True)
class ReleaseContextRepositoryError(RuntimeError):
    """A bounded, non-confidential repository failure."""

    code: str
    status_code: int

    def __str__(self) -> str:
        return self.code


def _fail(code: str, status_code: int) -> ReleaseContextRepositoryError:
    return ReleaseContextRepositoryError(code=code, status_code=status_code)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_projection(value: Any) -> ReleaseContextInput:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise _fail("release_context_inconsistent", 409) from error
    try:
        return ReleaseContextInput.model_validate(value)
    except ValidationError as error:
        raise _fail("release_context_inconsistent", 409) from error


def _postgres_error(error: DBAPIError) -> ReleaseContextRepositoryError:
    message = str(getattr(error, "orig", error))
    mappings = {
        "release_context_identity_unavailable": ("release_context_forbidden", 403),
        "release_context_forbidden": ("release_context_forbidden", 403),
        "release_context_scope_not_found": ("release_context_scope_not_found", 404),
        "open_shift_required": ("open_shift_required", 409),
        "open_shift_facility_mismatch": ("open_shift_facility_mismatch", 409),
        "child_not_on_site": ("child_not_on_site", 409),
        "release_context_inconsistent": ("release_context_inconsistent", 409),
    }
    for marker, (code, status_code) in mappings.items():
        if marker in message:
            return _fail(code, status_code)
    return _fail("family_authority_release_context_unavailable", 503)


def _load_postgres(
    session: Session,
    *,
    child_id: UUID,
    facility_id: UUID,
) -> ReleaseContextInput:
    try:
        value = session.scalar(
            text(
                "SELECT public.caresync_family_release_context_inputs("
                "CAST(:child_id AS uuid),CAST(:facility_id AS uuid)) AS inputs"
            ),
            {"child_id": str(child_id), "facility_id": str(facility_id)},
        )
    except DBAPIError as error:
        # A PostgreSQL exception aborts the read transaction.  Roll it back
        # before translating it into a bounded HTTP-safe failure.
        session.rollback()
        raise _postgres_error(error) from None
    if value is None:
        raise _fail("release_context_inconsistent", 409)
    return _parse_projection(value)


def _sqlite_evaluated_at(session: Session) -> datetime:
    value = session.scalar(select(func.current_timestamp()))
    if not isinstance(value, datetime):
        raise _fail("family_authority_release_context_unavailable", 503)
    return _utc(value)


def _facility_service_date(evaluated_at: datetime, timezone_name: str) -> date:
    """Return the facility-local calendar date for one captured DB instant."""

    try:
        return _utc(evaluated_at).astimezone(ZoneInfo(timezone_name)).date()
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise _fail("release_context_inconsistent", 409) from error


def _portable_operational_scope(
    session: Session,
    context: BasicContext,
    *,
    child_id: UUID,
    facility_id: UUID,
    evaluated_at: datetime,
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    organization_id = context.organization.id
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == organization_id,
            Facility.id == facility_id,
            Facility.status == "active",
        )
    )
    if facility is None:
        raise _fail("release_context_scope_not_found", 404)

    open_shifts = list(
        session.scalars(
            select(StaffShift)
            .where(
                StaffShift.organization_id == organization_id,
                StaffShift.membership_id == context.membership.id,
                StaffShift.status == "open",
                StaffShift.clocked_out_at.is_(None),
            )
            .order_by(StaffShift.id)
        )
    )
    exact_shifts = [shift for shift in open_shifts if shift.facility_id == facility_id]
    if not exact_shifts:
        code = "open_shift_facility_mismatch" if open_shifts else "open_shift_required"
        raise _fail(code, 409)
    if len(exact_shifts) != 1 or len(open_shifts) != 1:
        raise _fail("release_context_inconsistent", 409)
    shift = exact_shifts[0]

    service_date = _facility_service_date(evaluated_at, facility.timezone)
    child_scope = session.execute(
        select(Child.family_id, Enrollment.room_id)
        .join(
            Enrollment,
            and_(
                Enrollment.organization_id == Child.organization_id,
                Enrollment.child_id == Child.id,
            ),
        )
        .join(
            Room,
            and_(
                Room.organization_id == Enrollment.organization_id,
                Room.facility_id == Enrollment.facility_id,
                Room.id == Enrollment.room_id,
            ),
        )
        .where(
            Child.organization_id == organization_id,
            Child.id == child_id,
            Child.is_active.is_(True),
            Enrollment.facility_id == facility_id,
            Enrollment.status == "active",
            Enrollment.start_date <= service_date,
            Enrollment.placement_effective_date.is_not(None),
            Enrollment.placement_effective_date <= service_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= service_date),
            Room.is_active.is_(True),
        )
    ).all()
    if len(child_scope) != 1:
        if not child_scope:
            raise _fail("release_context_scope_not_found", 404)
        raise _fail("release_context_inconsistent", 409)
    family_id = child_scope[0].family_id

    attendance_rows = session.execute(
        select(AttendanceDay, AttendanceInterval)
        .join(
            AttendanceInterval,
            and_(
                AttendanceInterval.organization_id == AttendanceDay.organization_id,
                AttendanceInterval.attendance_day_id == AttendanceDay.id,
            ),
        )
        .join(
            Room,
            and_(
                Room.organization_id == AttendanceDay.organization_id,
                Room.facility_id == AttendanceDay.facility_id,
                Room.id == AttendanceDay.room_id,
            ),
        )
        .where(
            AttendanceDay.organization_id == organization_id,
            AttendanceDay.facility_id == facility_id,
            AttendanceDay.child_id == child_id,
            AttendanceDay.status == "present",
            AttendanceInterval.checked_out_at.is_(None),
            Room.is_active.is_(True),
        )
        .order_by(AttendanceInterval.checked_in_at, AttendanceInterval.id)
    ).all()
    if not attendance_rows:
        raise _fail("child_not_on_site", 409)
    if len(attendance_rows) != 1:
        raise _fail("release_context_inconsistent", 409)
    day, interval = attendance_rows[0]
    if day.room_id is None:
        raise _fail("release_context_inconsistent", 409)

    if not context.organization_wide:
        assignment_id = session.scalar(
            select(MembershipRoomAssignment.id).where(
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.membership_id == context.membership.id,
                MembershipRoomAssignment.facility_id == facility_id,
                MembershipRoomAssignment.room_id == day.room_id,
                MembershipRoomAssignment.is_active.is_(True),
            )
        )
        if assignment_id is None:
            raise _fail("release_context_scope_not_found", 404)

    family = session.scalar(
        select(Family)
        .where(
            Family.organization_id == organization_id,
            Family.id == family_id,
            Family.status == "active",
        )
        .with_for_update(read=True)
    )
    if family is None:
        raise _fail("release_context_scope_not_found", 404)
    return family_id, day.room_id, day.id, interval.id, shift.id


def _supporting_evidence(
    *,
    record_organization_id: UUID,
    record_family_id: UUID,
    evidence: FamilyAuthorityEvidence,
    assessment: FamilyAuthorityEvidenceAssessment,
    latest_version: int,
) -> dict[str, Any]:
    return {
        "bound_assessment_decision": assessment.decision,
        "bound_assessment_is_latest": assessment.version_number == latest_version,
        "evidence_expires_at": (
            None if evidence.expires_at is None else _utc(evidence.expires_at)
        ),
        "scope_matches_authority_record": (
            evidence.organization_id == record_organization_id
            and evidence.family_id == record_family_id
            and assessment.organization_id == record_organization_id
            and assessment.family_id == record_family_id
            and assessment.evidence_id == evidence.id
        ),
    }


def _portable_authority_input(
    session: Session,
    context: BasicContext,
    *,
    child_id: UUID,
    facility_id: UUID,
    evaluated_at: datetime,
    family_id: UUID,
    room_id: UUID,
    attendance_day_id: UUID,
    attendance_interval_id: UUID,
    staff_shift_id: UUID,
) -> ReleaseContextInput:
    organization_id = context.organization.id
    head = session.scalar(
        select(ChildAuthorityHead).where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == family_id,
            ChildAuthorityHead.child_id == child_id,
        )
    )
    authorizations = list(
        session.scalars(
            select(ChildReleaseAuthorization)
            .where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.family_id == family_id,
                ChildReleaseAuthorization.child_id == child_id,
                ChildReleaseAuthorization.revoked_at.is_(None),
                ChildReleaseAuthorization.effective_until > evaluated_at,
            )
            .order_by(ChildReleaseAuthorization.id)
        )
    )
    rules = list(
        session.scalars(
            select(ChildReleaseRule)
            .where(
                ChildReleaseRule.organization_id == organization_id,
                ChildReleaseRule.family_id == family_id,
                ChildReleaseRule.child_id == child_id,
                ChildReleaseRule.revoked_at.is_(None),
                ChildReleaseRule.effective_until > evaluated_at,
            )
            .order_by(ChildReleaseRule.id)
        )
    )

    evidence_ids = {
        row.basis_evidence_id for row in [*authorizations, *rules]
    }
    assessment_ids = {
        row.basis_evidence_assessment_id for row in [*authorizations, *rules]
    }
    evidence_by_id = {
        item.id: item
        for item in session.scalars(
            select(FamilyAuthorityEvidence).where(
                FamilyAuthorityEvidence.organization_id == organization_id,
                FamilyAuthorityEvidence.id.in_(evidence_ids),
            )
        )
    } if evidence_ids else {}
    assessment_by_id = {
        item.id: item
        for item in session.scalars(
            select(FamilyAuthorityEvidenceAssessment).where(
                FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
                FamilyAuthorityEvidenceAssessment.id.in_(assessment_ids),
            )
        )
    } if assessment_ids else {}
    latest_versions = {
        evidence_id: int(version)
        for evidence_id, version in session.execute(
            select(
                FamilyAuthorityEvidenceAssessment.evidence_id,
                func.max(FamilyAuthorityEvidenceAssessment.version_number),
            )
            .where(
                FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
                FamilyAuthorityEvidenceAssessment.evidence_id.in_(evidence_ids),
            )
            .group_by(FamilyAuthorityEvidenceAssessment.evidence_id)
        )
    } if evidence_ids else {}

    def evidence_projection(row: ChildReleaseAuthorization | ChildReleaseRule) -> dict[str, Any]:
        evidence = evidence_by_id.get(row.basis_evidence_id)
        assessment = assessment_by_id.get(row.basis_evidence_assessment_id)
        latest_version = latest_versions.get(row.basis_evidence_id)
        if evidence is None or assessment is None or latest_version is None:
            raise _fail("release_context_inconsistent", 409)
        return _supporting_evidence(
            record_organization_id=row.organization_id,
            record_family_id=row.family_id,
            evidence=evidence,
            assessment=assessment,
            latest_version=latest_version,
        )

    recipient_ids = {row.recipient_person_id for row in authorizations}
    people_rows = list(
        session.scalars(
            select(FamilyAuthorityPerson)
            .where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == family_id,
                FamilyAuthorityPerson.id.in_(recipient_ids),
            )
            .order_by(FamilyAuthorityPerson.id)
        )
    ) if recipient_ids else []
    version_ids = {
        person.current_person_version_id
        for person in people_rows
        if person.current_person_version_id is not None
    }
    versions_by_id = {
        version.id: version
        for version in session.scalars(
            select(FamilyAuthorityPersonVersion).where(
                FamilyAuthorityPersonVersion.organization_id == organization_id,
                FamilyAuthorityPersonVersion.id.in_(version_ids),
            )
        )
    } if version_ids else {}

    people = []
    for person in people_rows:
        current_versions = []
        version = (
            versions_by_id.get(person.current_person_version_id)
            if person.current_person_version_id is not None
            else None
        )
        if (
            version is not None
            and version.family_id == person.family_id
            and version.person_id == person.id
        ):
            current_versions.append(
                {
                    "person_version_id": version.id,
                    "first_name": version.first_name,
                    "middle_name": version.middle_name,
                    "last_name": version.last_name,
                    "preferred_name": version.preferred_name,
                    "relationship_kind": version.relationship_kind,
                    "relationship_detail": version.relationship_detail,
                }
            )
        people.append(
            {
                "organization_id": person.organization_id,
                "family_id": person.family_id,
                "person_id": person.id,
                "status": person.status,
                "current_versions": current_versions,
            }
        )

    payload = {
        "input_schema_version": "release-context-input-v1",
        "organization_id": organization_id,
        "family_id": family_id,
        "facility_id": facility_id,
        "room_id": room_id,
        "child_id": child_id,
        "attendance_day_id": attendance_day_id,
        "attendance_interval_id": attendance_interval_id,
        "staff_shift_id": staff_shift_id,
        "evaluated_at": evaluated_at,
        "authority_revision": 0 if head is None else head.revision,
        "people": people,
        "authorizations": [
            {
                "organization_id": row.organization_id,
                "family_id": row.family_id,
                "child_id": row.child_id,
                "authorization_id": row.id,
                "authorization_version": row.version,
                "recipient_person_id": row.recipient_person_id,
                "verification_policy_code": row.verification_policy_code,
                "effective_from": _utc(row.effective_from),
                "effective_until": _utc(row.effective_until),
                "revoked_at": None if row.revoked_at is None else _utc(row.revoked_at),
                "supporting_evidence": evidence_projection(row),
            }
            for row in authorizations
        ],
        "rules": [
            {
                "organization_id": row.organization_id,
                "family_id": row.family_id,
                "child_id": row.child_id,
                "rule_id": row.id,
                "rule_version": row.version,
                "rule_kind": row.rule_kind,
                "scope_kind": row.scope_kind,
                "scope_person_id": row.scope_person_id,
                "safe_explanation_code": row.safe_explanation_code,
                "effective_from": _utc(row.effective_from),
                "effective_until": _utc(row.effective_until),
                "revoked_at": None if row.revoked_at is None else _utc(row.revoked_at),
                "supporting_evidence": evidence_projection(row),
            }
            for row in rules
        ],
    }
    return _parse_projection(payload)


def load_release_context_input(
    session: Session,
    context: BasicContext,
    *,
    child_id: UUID,
    facility_id: UUID,
) -> ReleaseContextInput:
    """Load one strict input without performing any write."""

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        return _load_postgres(session, child_id=child_id, facility_id=facility_id)

    evaluated_at = _sqlite_evaluated_at(session)
    family_id, room_id, day_id, interval_id, shift_id = _portable_operational_scope(
        session,
        context,
        child_id=child_id,
        facility_id=facility_id,
        evaluated_at=evaluated_at,
    )
    return _portable_authority_input(
        session,
        context,
        child_id=child_id,
        facility_id=facility_id,
        evaluated_at=evaluated_at,
        family_id=family_id,
        room_id=room_id,
        attendance_day_id=day_id,
        attendance_interval_id=interval_id,
        staff_shift_id=shift_id,
    )
