"""Atomic command for one normal, verified child release.

SQLite retains the complete portable implementation used by local development
and acceptance tests.  PostgreSQL uses the narrow 0029D security-definer
adapter for private evidence, activation, immutable snapshot append and exact
replay while keeping attendance, care, receipt and audit writes in this one
transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.attendance import (
    _care_records_for_day,
    _ensure_checkout_preserves_care,
    _ensure_checkout_preserves_regulated_records,
    _ensure_service_date,
    _incident_records_for_day,
    _medication_records_for_day,
)
from app.api.basic.common import restore_context
from app.api.basic.dependencies import BasicContext
from app.basic.childcare_commands import begin_command, record_command, safe_action_route
from app.basic.daily_care import auto_finish_open_sleep
from app.basic.family_release_checkout import (
    ReleaseCheckoutContractError,
    canonical_release_evidence_digest,
    release_checkout_request_hash,
    validate_release_checkout_response,
    validate_release_checkout_verification,
)
from app.basic.family_release_checkout_repository import (
    ReleaseCheckoutRepositoryError,
    ReleaseSnapshotAppendInput,
    postgres_release_checkout_activation_enabled,
    postgres_release_checkout_context_input_at,
    postgres_release_checkout_insert_snapshot,
    postgres_release_checkout_instant,
    postgres_release_checkout_replay,
)
from app.basic.family_release_checkout_schemas import (
    RELEASE_CHECKOUT_COMMAND_TYPE,
    RELEASE_CHECKOUT_TARGET_TYPE,
    ReleaseCheckoutCommand,
    ReleaseCheckoutReceipt,
    ReleaseCheckoutResource,
    ReleaseCheckoutResponse,
    ReleaseEvidenceDigestInput,
)
from app.basic.family_release_context import (
    ReleaseContextInconsistentError,
    ReleaseContextReevaluationRequired,
    compose_release_context,
)
from app.basic.family_release_context_repository import (
    ReleaseContextRepositoryError,
    _portable_authority_input,
)
from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    Child,
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    Enrollment,
    Facility,
    FacilityReleaseCheckoutActivation,
    Family,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityPerson,
    FamilyAuthorityPersonVersion,
    MembershipRoomAssignment,
    Organization,
    OrganizationMembership,
    Program,
    RealtimeEvent,
    Role,
    Room,
    StaffRoomPresenceSession,
    StaffShift,
    User,
)
from app.basic.room_safety import (
    lock_facility_projection,
    reconcile_facility_exceptions,
)
from app.basic.security import audit


@dataclass(frozen=True)
class ReleaseCheckoutServiceError(RuntimeError):
    code: str
    status_code: int

    def __str__(self) -> str:
        return self.code


def _fail(code: str, status_code: int) -> ReleaseCheckoutServiceError:
    return ReleaseCheckoutServiceError(code=code, status_code=status_code)


def _require_release_room_presence(
    session: Session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    staff_shift_id: UUID,
    facility_id: UUID,
    room_id: UUID,
    enabled: bool,
) -> None:
    if not enabled:
        return
    values = list(
        session.scalars(
            select(StaffRoomPresenceSession.id)
            .where(
                StaffRoomPresenceSession.organization_id
                == organization_id,
                StaffRoomPresenceSession.membership_id == membership_id,
                StaffRoomPresenceSession.staff_shift_id == staff_shift_id,
                StaffRoomPresenceSession.facility_id == facility_id,
                StaffRoomPresenceSession.room_id == room_id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
            .limit(2)
        )
    )
    if len(values) == 1:
        return
    # Checkout is the one child mutation that may reduce risk when canonical
    # presence source rows are internally contradictory.  It must not become
    # a general no-presence or wrong-room bypass.
    if len(values) > 1:
        return
    current = list(
        session.execute(
            select(
                StaffRoomPresenceSession.facility_id,
                StaffRoomPresenceSession.room_id,
                StaffRoomPresenceSession.staff_shift_id,
            )
            .where(
                StaffRoomPresenceSession.organization_id
                == organization_id,
                StaffRoomPresenceSession.membership_id == membership_id,
                StaffRoomPresenceSession.ended_at.is_(None),
            )
            .limit(2)
        )
    )
    if len(current) > 1:
        return
    current_value = current[0] if current else None
    if (
        current_value is not None
        and current_value.facility_id == facility_id
        and current_value.room_id == room_id
        and current_value.staff_shift_id != staff_shift_id
    ):
        return
    raise _fail(
        (
            "release_checkout_room_presence_required"
            if current_value is None
            else "release_checkout_room_presence_mismatch"
        ),
        409,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _database_instant(session: Session) -> datetime:
    """Capture the database-owned instant used by this transaction."""

    if session.bind is None:
        raise _fail("family_authority_release_checkout_unavailable", 503)
    if session.bind.dialect.name == "postgresql":
        return _utc(postgres_release_checkout_instant(session))
    if session.bind.dialect.name != "sqlite":
        raise _fail("family_authority_release_checkout_unavailable", 503)
    raw = session.scalar(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')"))
    if not isinstance(raw, str):
        raise _fail("family_authority_release_checkout_unavailable", 503)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as error:
        raise _fail("family_authority_release_checkout_unavailable", 503) from error


def _commit(session: Session, context: BasicContext) -> None:
    """Single injectable commit boundary used by the rollback acceptance proof."""

    session.flush()
    session.commit()
    restore_context(session, context)
    session.expire_all()


def _record_release_commit_signals(
    session: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    facility_id: UUID,
    release_id: UUID,
    client_operation_id: UUID,
    occurred_at: datetime,
) -> None:
    """Append the confidential audit and PII-free realtime invalidation.

    The authority migration suppresses ``child.release.*`` audit rows from the
    tenant-wide audit bridge.  This explicit outbox row is therefore the one
    public invalidation for a fresh verified release; exact replay never calls
    this helper.  Both rows remain inside the checkout transaction.
    """

    audit(
        session,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="child.release.checked_out",
        entity_type="attendance_release",
        entity_id=release_id,
        facility_id=facility_id,
        details={"client_operation_id": str(client_operation_id)},
    )
    session.add(
        RealtimeEvent(
            organization_id=organization_id,
            event_type="attendance.release.checked_out",
            entity_type="attendance_release",
            entity_id=release_id,
            occurred_at=occurred_at,
            payload={
                "source": "verified_release_checkout",
                "facility_id": str(facility_id),
            },
        )
    )


def _receipt_projection(receipt) -> ReleaseCheckoutReceipt:
    try:
        route = safe_action_route((receipt.outcome or {}).get("action_route"))
        return ReleaseCheckoutReceipt(
            organization_id=receipt.organization_id,
            client_operation_id=receipt.client_operation_id,
            command_type=receipt.command_type,
            target_type=receipt.target_type,
            target_id=receipt.target_id,
            committed_version=receipt.committed_version,
            committed_at=_utc(receipt.committed_at),
            facility_id=receipt.facility_id,
            action_route=route,
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
        raise _fail("release_checkout_receipt_incomplete", 409) from error


def _resource_projection(snapshot: AttendanceReleaseSnapshot) -> ReleaseCheckoutResource:
    try:
        return ReleaseCheckoutResource(
            release_id=snapshot.id,
            organization_id=snapshot.organization_id,
            facility_id=snapshot.facility_id,
            room_id=snapshot.room_id,
            child_id=snapshot.child_id,
            attendance_day_id=snapshot.attendance_day_id,
            attendance_interval_id=snapshot.attendance_interval_id,
            attendance_day_version=snapshot.attendance_day_version,
            checkout_event_id=snapshot.checkout_event_id,
            staff_shift_id=snapshot.staff_shift_id,
            actor_user_id=snapshot.actor_user_id,
            actor_membership_id=snapshot.actor_membership_id,
            recipient_person_id=snapshot.recipient_person_id,
            recipient_person_version_id=snapshot.recipient_person_version_id,
            recipient_display_name=snapshot.recipient_display_name,
            recipient_relationship=snapshot.recipient_relationship,
            authorization_id=snapshot.authorization_id,
            authorization_version=snapshot.authorization_version,
            authority_revision=snapshot.authority_revision,
            restriction_digest_sha256=snapshot.restriction_digest_sha256,
            verification_policy_code=snapshot.verification_policy_code,
            verification_method=snapshot.verification_method,
            verification_result=snapshot.verification_result,
            decision_policy_version=snapshot.decision_policy_version,
            requested_at=_utc(snapshot.requested_at),
            checked_out_at=_utc(snapshot.checked_out_at),
            committed_at=_utc(snapshot.committed_at),
            client_operation_id=snapshot.client_operation_id,
            request_hash=snapshot.request_hash,
            release_mode=snapshot.release_mode,
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
        raise _fail("release_checkout_receipt_incomplete", 409) from error


def _replay(
    session: Session,
    *,
    command: ReleaseCheckoutCommand,
    receipt,
) -> ReleaseCheckoutResponse:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        resource = postgres_release_checkout_replay(
            session,
            client_operation_id=command.client_operation_id,
        )
    else:
        snapshot = session.scalar(
            select(AttendanceReleaseSnapshot).where(
                AttendanceReleaseSnapshot.organization_id == receipt.organization_id,
                AttendanceReleaseSnapshot.id == receipt.target_id,
                AttendanceReleaseSnapshot.client_operation_id == command.client_operation_id,
            )
        )
        if snapshot is None:
            raise _fail("release_checkout_receipt_incomplete", 409)
        resource = _resource_projection(snapshot)
    try:
        response = ReleaseCheckoutResponse(
            schema_version="release-checkout-v1",
            resource=resource,
            receipt=_receipt_projection(receipt),
            replayed=True,
        )
        return validate_release_checkout_response(command, response)
    except (ReleaseCheckoutContractError, ValidationError) as error:
        # A receipt/snapshot that no longer cross-echoes the exact committed
        # response is a bounded reconciliation conflict.  It is not a transient
        # service outage and no stored value is reflected back to the caller.
        raise _fail("release_checkout_receipt_incomplete", 409) from error


def _revalidated_actor(
    session: Session,
    context: BasicContext,
    *,
    lock: bool = False,
) -> tuple[User, Organization, OrganizationMembership, Role]:
    organization_id = context.organization.id
    user_statement = select(User).where(
        User.id == context.user.id,
        User.is_active.is_(True),
        User.email_verified_at.is_not(None),
    )
    organization_statement = select(Organization).where(
        Organization.id == organization_id,
        Organization.status == "active",
    )
    membership_statement = select(OrganizationMembership).where(
        OrganizationMembership.id == context.membership.id,
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == context.user.id,
        OrganizationMembership.status == "active",
    )
    if lock:
        user_statement = user_statement.with_for_update()
        organization_statement = organization_statement.with_for_update()
        membership_statement = membership_statement.with_for_update()
    user = session.scalar(user_statement)
    organization = session.scalar(organization_statement)
    membership = session.scalar(membership_statement)
    role = None
    if membership is not None:
        role_statement = select(Role).where(
            Role.id == membership.role_id,
            Role.organization_id == organization_id,
        )
        if lock:
            role_statement = role_statement.with_for_update()
        role = session.scalar(role_statement)
    if user is None or organization is None or membership is None or role is None:
        raise _fail("release_checkout_forbidden", 403)
    if not {"attendance:record", "release:checkout"}.issubset(set(role.permissions or [])):
        raise _fail("release_checkout_forbidden", 403)
    return user, organization, membership, role


def _selected_release_recipient(release_context, command: ReleaseCheckoutCommand):
    if release_context.decision != "recipient_selection_available":
        blocker = (
            release_context.blockers[0]
            if release_context.blockers
            else "release_checkout_context_stale"
        )
        raise _fail(blocker, 409)
    if (
        release_context.authority_revision != command.expected_authority_revision
        or release_context.restriction_digest_sha256
        != command.expected_restriction_digest_sha256
        or release_context.decision_policy_version
        != command.expected_decision_policy_version
    ):
        raise _fail("release_checkout_context_stale", 409)
    eligible = next(
        (
            item
            for item in release_context.eligible_recipients
            if item.recipient_person_id == command.recipient_person_id
            and item.recipient_person_version_id == command.recipient_person_version_id
            and item.authorization_id == command.authorization_id
        ),
        None,
    )
    if eligible is None or eligible.authorization_version != command.authorization_version:
        raise _fail("release_checkout_context_stale", 409)
    try:
        validate_release_checkout_verification(
            verification_policy_code=eligible.verification_policy_code,
            verification_method=command.verification_method,
            verification_result=command.verification_result,
        )
    except ReleaseCheckoutContractError as error:
        raise _fail(error.code.value, 409) from error
    return eligible


def _fresh_release_postgres(
    session: Session,
    context: BasicContext,
    command: ReleaseCheckoutCommand,
    request_hash: str,
    *,
    room_safety_active: bool,
) -> ReleaseCheckoutResponse:
    """Commit one release through the hardened 0029D PostgreSQL adapter."""

    organization_id = context.organization.id
    if room_safety_active:
        lock_facility_projection(
            session,
            organization_id,
            command.facility_id,
        )
    user, _, membership, role = _revalidated_actor(session, context, lock=True)

    # Hold the same family synchronization boundary as every authority writer
    # before locking child and operational state.  No decision timestamp is
    # captured until every row capable of changing the result is stable.
    child_identity = session.execute(
        select(Child.id, Child.family_id).where(
            Child.organization_id == organization_id,
            Child.id == command.child_id,
            Child.is_active.is_(True),
        )
    ).one_or_none()
    if child_identity is None:
        raise _fail("release_checkout_scope_not_found", 404)
    family = session.scalar(
        select(Family)
        .where(
            Family.organization_id == organization_id,
            Family.id == child_identity.family_id,
            Family.status == "active",
        )
        .with_for_update()
    )
    child = session.scalar(
        select(Child)
        .where(
            Child.organization_id == organization_id,
            Child.id == command.child_id,
            Child.family_id == child_identity.family_id,
            Child.is_active.is_(True),
        )
        .with_for_update()
    )
    if family is None or child is None:
        raise _fail("release_checkout_context_stale", 409)

    facility = session.scalar(
        select(Facility)
        .where(
            Facility.organization_id == organization_id,
            Facility.id == command.facility_id,
            Facility.status == "active",
        )
        .with_for_update()
    )
    if facility is None:
        raise _fail("release_checkout_scope_not_found", 404)

    if not postgres_release_checkout_activation_enabled(
        session,
        facility_id=command.facility_id,
    ):
        raise _fail("release_checkout_not_activated", 409)

    shift = session.scalar(
        select(StaffShift)
        .where(
            StaffShift.organization_id == organization_id,
            StaffShift.id == command.expected_staff_shift_id,
            StaffShift.membership_id == membership.id,
            StaffShift.facility_id == command.facility_id,
            StaffShift.status == "open",
            StaffShift.clocked_out_at.is_(None),
        )
        .with_for_update()
    )
    if shift is None:
        raise _fail("release_checkout_context_stale", 409)

    day = session.scalar(
        select(AttendanceDay)
        .where(
            AttendanceDay.organization_id == organization_id,
            AttendanceDay.id == command.expected_attendance_day_id,
            AttendanceDay.facility_id == command.facility_id,
            AttendanceDay.child_id == command.child_id,
            AttendanceDay.room_id == command.expected_room_id,
            AttendanceDay.status == "present",
        )
        .with_for_update()
    )
    if day is None:
        raise _fail("child_not_on_site", 409)
    interval = session.scalar(
        select(AttendanceInterval)
        .where(
            AttendanceInterval.organization_id == organization_id,
            AttendanceInterval.id == command.expected_attendance_interval_id,
            AttendanceInterval.attendance_day_id == day.id,
            AttendanceInterval.checked_out_at.is_(None),
        )
        .with_for_update()
    )
    if interval is None:
        raise _fail("child_not_on_site", 409)

    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.id == day.enrollment_id,
            Enrollment.facility_id == command.facility_id,
            Enrollment.child_id == command.child_id,
            Enrollment.room_id == command.expected_room_id,
            Enrollment.status == "active",
            Enrollment.start_date <= day.service_date,
            Enrollment.placement_effective_date <= day.service_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= day.service_date),
        )
        .with_for_update()
    )
    room = session.scalar(
        select(Room)
        .where(
            Room.organization_id == organization_id,
            Room.facility_id == command.facility_id,
            Room.id == command.expected_room_id,
            Room.is_active.is_(True),
        )
        .with_for_update()
    )
    program = (
        None
        if enrollment is None
        else session.scalar(
            select(Program)
            .where(
                Program.organization_id == organization_id,
                Program.facility_id == command.facility_id,
                Program.id == enrollment.program_id,
                Program.is_active.is_(True),
            )
            .with_for_update()
        )
    )
    if enrollment is None or room is None or program is None or room.program_id != program.id:
        raise _fail("release_checkout_context_stale", 409)
    _require_release_room_presence(
        session,
        organization_id=organization_id,
        membership_id=membership.id,
        staff_shift_id=shift.id,
        facility_id=facility.id,
        room_id=room.id,
        enabled=room_safety_active,
    )

    if role.key not in {"owner", "administrator"}:
        assignment = session.scalar(
            select(MembershipRoomAssignment)
            .where(
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.facility_id == command.facility_id,
                MembershipRoomAssignment.room_id == command.expected_room_id,
                MembershipRoomAssignment.is_active.is_(True),
            )
            .with_for_update()
        )
        if assignment is None:
            raise _fail("release_checkout_scope_not_found", 404)

    care_records = _care_records_for_day(session, day, lock=True)
    medication_records = _medication_records_for_day(session, day, lock=True)
    incident_records = _incident_records_for_day(session, day, lock=True)

    decision_at = _database_instant(session)
    if command.requested_at > decision_at:
        raise _fail("release_checkout_requested_at_future", 422)
    if decision_at < _utc(interval.checked_in_at):
        raise _fail("release_checkout_context_stale", 409)

    context_input = postgres_release_checkout_context_input_at(
        session,
        child_id=command.child_id,
        facility_id=command.facility_id,
        decision_at=decision_at,
    )
    if _utc(context_input.evaluated_at) != decision_at:
        raise _fail("family_authority_release_checkout_unavailable", 503)
    try:
        release_context = compose_release_context(context_input)
    except (
        ReleaseContextInconsistentError,
        ReleaseContextReevaluationRequired,
        ValidationError,
    ) as error:
        raise _fail("release_checkout_context_stale", 409) from error
    if (
        context_input.organization_id != organization_id
        or context_input.family_id != family.id
        or context_input.child_id != command.child_id
        or context_input.facility_id != command.facility_id
        or context_input.room_id != command.expected_room_id
        or context_input.attendance_day_id != command.expected_attendance_day_id
        or context_input.attendance_interval_id != command.expected_attendance_interval_id
        or context_input.staff_shift_id != command.expected_staff_shift_id
    ):
        raise _fail("release_checkout_context_stale", 409)
    eligible = _selected_release_recipient(release_context, command)

    try:
        _ensure_service_date(facility, day, _utc(interval.checked_in_at), decision_at)
        _ensure_checkout_preserves_care(care_records, decision_at)
        _ensure_checkout_preserves_regulated_records(
            medication_records,
            incident_records,
            decision_at,
        )
        auto_finish_open_sleep(
            session,
            organization_id=organization_id,
            attendance_day_id=day.id,
            actor_user_id=user.id,
            checked_out_at=decision_at,
            facility_id=facility.id,
            records=care_records,
        )
    except HTTPException as error:
        raise _fail("release_checkout_care_time_conflict", error.status_code) from error

    release_id = uuid4()
    checkout_event_id = uuid4()
    day.version += 1

    # Persist the new day version and any automatic sleep closure first.  The
    # definer then inserts the event, receipt and snapshot as one guarded
    # bundle while the interval deliberately remains open.
    session.flush()
    resource = postgres_release_checkout_insert_snapshot(
        session,
        ReleaseSnapshotAppendInput(
            release_id=release_id,
            child_id=command.child_id,
            facility_id=command.facility_id,
            room_id=command.expected_room_id,
            attendance_day_id=day.id,
            attendance_day_version=day.version,
            attendance_interval_id=interval.id,
            checkout_event_id=checkout_event_id,
            staff_shift_id=shift.id,
            recipient_person_id=eligible.recipient_person_id,
            recipient_person_version_id=eligible.recipient_person_version_id,
            authorization_id=eligible.authorization_id,
            authorization_version=eligible.authorization_version,
            authority_revision=release_context.authority_revision,
            restriction_digest_sha256=release_context.restriction_digest_sha256,
            verification_method=command.verification_method,
            verification_result=command.verification_result,
            decision_policy_version=release_context.decision_policy_version,
            decision_at=decision_at,
            requested_at=command.requested_at,
            request_hash=request_hash,
        ),
    )
    if (
        resource.release_id != release_id
        or resource.organization_id != organization_id
        or resource.attendance_day_version != day.version
        or resource.checkout_event_id != checkout_event_id
        or resource.actor_user_id != user.id
        or resource.actor_membership_id != membership.id
        or _utc(resource.checked_out_at) != decision_at
        or _utc(resource.committed_at) != decision_at
    ):
        raise _fail("family_authority_release_checkout_unavailable", 503)

    receipt = session.scalar(
        select(ChildcareCommandReceipt).where(
            ChildcareCommandReceipt.organization_id == organization_id,
            ChildcareCommandReceipt.client_operation_id == command.client_operation_id,
            ChildcareCommandReceipt.actor_user_id == user.id,
        )
    )
    if receipt is None:
        raise _fail("release_checkout_receipt_incomplete", 409)

    interval.checked_out_at = decision_at
    _record_release_commit_signals(
        session,
        organization_id=organization_id,
        actor_user_id=user.id,
        facility_id=facility.id,
        release_id=release_id,
        client_operation_id=command.client_operation_id,
        occurred_at=decision_at,
    )
    if room_safety_active:
        reconcile_facility_exceptions(
            session,
            organization_id=organization_id,
            facility_id=facility.id,
            cause_entity_type="attendance_release",
            cause_entity_id=release_id,
        )
    response = ReleaseCheckoutResponse(
        schema_version="release-checkout-v1",
        resource=resource,
        receipt=_receipt_projection(receipt),
        replayed=False,
    )
    try:
        validate_release_checkout_response(command, response)
    except ReleaseCheckoutContractError as error:
        raise _fail(error.code.value, 409) from error
    _commit(session, context)
    return response


def _fresh_release(
    session: Session,
    context: BasicContext,
    command: ReleaseCheckoutCommand,
    request_hash: str,
    *,
    room_safety_active: bool,
) -> ReleaseCheckoutResponse:
    organization_id = context.organization.id
    if room_safety_active:
        lock_facility_projection(
            session,
            organization_id,
            command.facility_id,
        )
    user, _, membership, role = _revalidated_actor(session, context)

    # Family -> child -> authority-head is the shared authority lock order.
    child_identity = session.execute(
        select(Child.id, Child.family_id).where(
            Child.organization_id == organization_id,
            Child.id == command.child_id,
            Child.is_active.is_(True),
        )
    ).one_or_none()
    if child_identity is None:
        raise _fail("release_checkout_scope_not_found", 404)
    family = session.scalar(
        select(Family)
        .where(
            Family.organization_id == organization_id,
            Family.id == child_identity.family_id,
            Family.status == "active",
        )
        .with_for_update()
    )
    child = session.scalar(
        select(Child)
        .where(
            Child.organization_id == organization_id,
            Child.id == command.child_id,
            Child.family_id == child_identity.family_id,
            Child.is_active.is_(True),
        )
        .with_for_update()
    )
    head = session.scalar(
        select(ChildAuthorityHead)
        .where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == child_identity.family_id,
            ChildAuthorityHead.child_id == command.child_id,
        )
        .with_for_update()
    )
    if family is None or child is None or head is None:
        raise _fail("release_checkout_context_stale", 409)

    facility = session.scalar(
        select(Facility)
        .where(
            Facility.organization_id == organization_id,
            Facility.id == command.facility_id,
            Facility.status == "active",
        )
        .with_for_update()
    )
    activation = session.scalar(
        select(FacilityReleaseCheckoutActivation)
        .where(
            FacilityReleaseCheckoutActivation.organization_id == organization_id,
            FacilityReleaseCheckoutActivation.facility_id == command.facility_id,
            FacilityReleaseCheckoutActivation.activation_policy_version
            == "normal_verified_release_v1",
        )
        .with_for_update()
    )
    if facility is None:
        raise _fail("release_checkout_scope_not_found", 404)
    if activation is None:
        raise _fail("release_checkout_not_activated", 409)

    open_shifts = list(
        session.scalars(
            select(StaffShift)
            .where(
                StaffShift.organization_id == organization_id,
                StaffShift.membership_id == membership.id,
                StaffShift.status == "open",
                StaffShift.clocked_out_at.is_(None),
            )
            .order_by(StaffShift.id)
            .with_for_update()
        )
    )
    if not open_shifts:
        raise _fail("open_shift_required", 409)
    if len(open_shifts) != 1:
        raise _fail("release_checkout_context_stale", 409)
    shift = open_shifts[0]
    if shift.facility_id != command.facility_id:
        raise _fail("open_shift_facility_mismatch", 409)
    if shift.id != command.expected_staff_shift_id:
        raise _fail("release_checkout_context_stale", 409)

    day = session.scalar(
        select(AttendanceDay)
        .where(
            AttendanceDay.organization_id == organization_id,
            AttendanceDay.id == command.expected_attendance_day_id,
            AttendanceDay.facility_id == command.facility_id,
            AttendanceDay.child_id == command.child_id,
            AttendanceDay.room_id == command.expected_room_id,
            AttendanceDay.status == "present",
        )
        .with_for_update()
    )
    if day is None:
        raise _fail("child_not_on_site", 409)
    interval_rows = list(
        session.scalars(
            select(AttendanceInterval)
            .where(
                AttendanceInterval.organization_id == organization_id,
                AttendanceInterval.attendance_day_id == day.id,
                AttendanceInterval.checked_out_at.is_(None),
            )
            .order_by(AttendanceInterval.id)
            .with_for_update()
        )
    )
    if len(interval_rows) != 1:
        code = "child_not_on_site" if not interval_rows else "release_checkout_context_stale"
        raise _fail(code, 409)
    interval = interval_rows[0]
    if interval.id != command.expected_attendance_interval_id:
        raise _fail("release_checkout_context_stale", 409)

    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.organization_id == organization_id,
            Enrollment.id == day.enrollment_id,
            Enrollment.facility_id == command.facility_id,
            Enrollment.child_id == command.child_id,
            Enrollment.room_id == command.expected_room_id,
            Enrollment.status == "active",
            Enrollment.start_date <= day.service_date,
            Enrollment.placement_effective_date <= day.service_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= day.service_date),
        )
        .with_for_update()
    )
    room = session.scalar(
        select(Room)
        .where(
            Room.organization_id == organization_id,
            Room.facility_id == command.facility_id,
            Room.id == command.expected_room_id,
            Room.is_active.is_(True),
        )
        .with_for_update()
    )
    program = (
        None
        if enrollment is None
        else session.scalar(
            select(Program)
            .where(
                Program.organization_id == organization_id,
                Program.facility_id == command.facility_id,
                Program.id == enrollment.program_id,
                Program.is_active.is_(True),
            )
            .with_for_update()
        )
    )
    if enrollment is None or room is None or program is None or room.program_id != program.id:
        raise _fail("release_checkout_context_stale", 409)
    _require_release_room_presence(
        session,
        organization_id=organization_id,
        membership_id=membership.id,
        staff_shift_id=shift.id,
        facility_id=facility.id,
        room_id=room.id,
        enabled=room_safety_active,
    )

    room_assignment_id: UUID | None = None
    scope_basis = "organization_role"
    if role.key not in {"owner", "administrator"}:
        assignment = session.scalar(
            select(MembershipRoomAssignment)
            .where(
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.facility_id == command.facility_id,
                MembershipRoomAssignment.room_id == command.expected_room_id,
                MembershipRoomAssignment.is_active.is_(True),
            )
            .with_for_update()
        )
        if assignment is None:
            raise _fail("release_checkout_scope_not_found", 404)
        scope_basis = "room_assignment"
        room_assignment_id = assignment.id

    authorizations = list(
        session.scalars(
            select(ChildReleaseAuthorization)
            .where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.family_id == child.family_id,
                ChildReleaseAuthorization.child_id == child.id,
                ChildReleaseAuthorization.revoked_at.is_(None),
            )
            .order_by(ChildReleaseAuthorization.id)
            .with_for_update()
        )
    )
    rules = list(
        session.scalars(
            select(ChildReleaseRule)
            .where(
                ChildReleaseRule.organization_id == organization_id,
                ChildReleaseRule.family_id == child.family_id,
                ChildReleaseRule.child_id == child.id,
                ChildReleaseRule.revoked_at.is_(None),
            )
            .order_by(ChildReleaseRule.id)
            .with_for_update()
        )
    )
    selected_authorization = next(
        (row for row in authorizations if row.id == command.authorization_id), None
    )
    if selected_authorization is None:
        raise _fail("release_checkout_context_stale", 409)

    people = list(
        session.scalars(
            select(FamilyAuthorityPerson)
            .where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == child.family_id,
            )
            .order_by(FamilyAuthorityPerson.id)
            .with_for_update()
        )
    )
    versions = list(
        session.scalars(
            select(FamilyAuthorityPersonVersion)
            .where(
                FamilyAuthorityPersonVersion.organization_id == organization_id,
                FamilyAuthorityPersonVersion.family_id == child.family_id,
            )
            .order_by(FamilyAuthorityPersonVersion.id)
            .with_for_update()
        )
    )
    evidence_ids = {row.basis_evidence_id for row in [*authorizations, *rules]}
    evidence_rows = (
        list(
            session.scalars(
                select(FamilyAuthorityEvidence)
                .where(
                    FamilyAuthorityEvidence.organization_id == organization_id,
                    FamilyAuthorityEvidence.family_id == child.family_id,
                    FamilyAuthorityEvidence.id.in_(evidence_ids),
                )
                .order_by(FamilyAuthorityEvidence.id)
                .with_for_update()
            )
        )
        if evidence_ids
        else []
    )
    assessment_rows = (
        list(
            session.scalars(
                select(FamilyAuthorityEvidenceAssessment)
                .where(
                    FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
                    FamilyAuthorityEvidenceAssessment.family_id == child.family_id,
                    FamilyAuthorityEvidenceAssessment.evidence_id.in_(evidence_ids),
                )
                .order_by(
                    FamilyAuthorityEvidenceAssessment.evidence_id,
                    FamilyAuthorityEvidenceAssessment.version_number,
                )
                .with_for_update()
            )
        )
        if evidence_ids
        else []
    )

    decision_at = _database_instant(session)
    if command.requested_at > decision_at:
        raise _fail("release_checkout_requested_at_future", 422)
    if decision_at < _utc(interval.checked_in_at):
        raise _fail("release_checkout_context_stale", 409)

    try:
        context_input = _portable_authority_input(
            session,
            context,
            child_id=child.id,
            facility_id=facility.id,
            evaluated_at=decision_at,
            family_id=child.family_id,
            room_id=room.id,
            attendance_day_id=day.id,
            attendance_interval_id=interval.id,
            staff_shift_id=shift.id,
        )
        release_context = compose_release_context(context_input)
    except (
        ReleaseContextRepositoryError,
        ReleaseContextInconsistentError,
        ReleaseContextReevaluationRequired,
        ValidationError,
    ) as error:
        raise _fail("release_checkout_context_stale", 409) from error
    if release_context.decision != "recipient_selection_available":
        blocker = (
            release_context.blockers[0]
            if release_context.blockers
            else "release_checkout_context_stale"
        )
        raise _fail(blocker, 409)
    if (
        release_context.authority_revision != command.expected_authority_revision
        or release_context.restriction_digest_sha256 != command.expected_restriction_digest_sha256
        or release_context.decision_policy_version != command.expected_decision_policy_version
    ):
        raise _fail("release_checkout_context_stale", 409)
    eligible = next(
        (
            item
            for item in release_context.eligible_recipients
            if item.recipient_person_id == command.recipient_person_id
            and item.recipient_person_version_id == command.recipient_person_version_id
            and item.authorization_id == command.authorization_id
        ),
        None,
    )
    if eligible is None or eligible.authorization_version != command.authorization_version:
        raise _fail("release_checkout_context_stale", 409)
    try:
        validate_release_checkout_verification(
            verification_policy_code=eligible.verification_policy_code,
            verification_method=command.verification_method,
            verification_result=command.verification_result,
        )
    except ReleaseCheckoutContractError as error:
        raise _fail(error.code.value, 409) from error

    selected_person = next(
        (item for item in people if item.id == command.recipient_person_id), None
    )
    selected_version = next(
        (item for item in versions if item.id == command.recipient_person_version_id), None
    )
    evidence = next(
        (item for item in evidence_rows if item.id == selected_authorization.basis_evidence_id),
        None,
    )
    evidence_assessments = [
        item for item in assessment_rows if evidence is not None and item.evidence_id == evidence.id
    ]
    latest_assessment = (
        max(evidence_assessments, key=lambda item: item.version_number)
        if evidence_assessments
        else None
    )
    if (
        selected_person is None
        or selected_person.status != "active"
        or selected_person.current_person_version_id != command.recipient_person_version_id
        or selected_version is None
        or selected_version.person_id != selected_person.id
        or selected_version.closed_at is not None
        or selected_authorization.recipient_person_id != selected_person.id
        or selected_authorization.version != command.authorization_version
        or selected_authorization.basis_evidence_assessment_id
        != (None if latest_assessment is None else latest_assessment.id)
        or evidence is None
        or latest_assessment is None
        or latest_assessment.version_number != 2
        or latest_assessment.decision != "reviewed"
        or latest_assessment.assessed_epistemic_status not in {"reported", "document_observed"}
        or (evidence.expires_at is not None and _utc(evidence.expires_at) <= decision_at)
    ):
        raise _fail("release_checkout_context_stale", 409)

    evidence_digest = canonical_release_evidence_digest(
        ReleaseEvidenceDigestInput(
            schema_version="release-evidence-v1",
            evidence_id=evidence.id,
            evidence_kind=evidence.evidence_kind,
            evidence_object_id=evidence.evidence_object_id,
            content_sha256=evidence.content_sha256,
            expires_at=None if evidence.expires_at is None else _utc(evidence.expires_at),
            evidence_assessment_id=latest_assessment.id,
            evidence_assessment_version=latest_assessment.version_number,
            decision="reviewed",
            assessed_epistemic_status=latest_assessment.assessed_epistemic_status,
        )
    )

    try:
        _ensure_service_date(facility, day, _utc(interval.checked_in_at), decision_at)
        care_records = _care_records_for_day(session, day, lock=True)
        medication_records = _medication_records_for_day(session, day, lock=True)
        incident_records = _incident_records_for_day(session, day, lock=True)
        _ensure_checkout_preserves_care(care_records, decision_at)
        _ensure_checkout_preserves_regulated_records(
            medication_records, incident_records, decision_at
        )
        auto_finish_open_sleep(
            session,
            organization_id=organization_id,
            attendance_day_id=day.id,
            actor_user_id=user.id,
            checked_out_at=decision_at,
            facility_id=facility.id,
            records=care_records,
        )
    except HTTPException as error:
        raise _fail("release_checkout_care_time_conflict", error.status_code) from error

    release_id = uuid4()
    checkout_event_id = uuid4()
    previous_day_version = day.version
    interval.checked_out_at = decision_at
    day.version += 1
    session.add(
        AttendanceEvent(
            id=checkout_event_id,
            organization_id=organization_id,
            attendance_day_id=day.id,
            client_operation_id=command.client_operation_id,
            actor_user_id=user.id,
            event_type="check_out",
            occurred_at=decision_at,
            before={"checked_out_at": None, "attendance_day_version": previous_day_version},
            after={
                "checked_out_at": decision_at.isoformat(),
                "attendance_day_version": day.version,
                "release_id": str(release_id),
            },
        )
    )
    receipt = record_command(
        session,
        organization_id=organization_id,
        actor_user_id=user.id,
        client_operation_id=command.client_operation_id,
        command_type=RELEASE_CHECKOUT_COMMAND_TYPE,
        target_type=RELEASE_CHECKOUT_TARGET_TYPE,
        target_id=release_id,
        request_hash=request_hash,
        committed_version=1,
        facility_id=facility.id,
        outcome={"action_route": f"/attendance/releases/{release_id}"},
    )
    receipt.committed_at = decision_at
    # SQLite cannot defer the snapshot's event/receipt foreign keys.  Materialize
    # those parent rows first while keeping every write inside this transaction.
    session.flush()
    snapshot = AttendanceReleaseSnapshot(
        id=release_id,
        organization_id=organization_id,
        family_id=child.family_id,
        facility_id=facility.id,
        child_id=child.id,
        attendance_day_id=day.id,
        attendance_day_version=day.version,
        attendance_interval_id=interval.id,
        checkout_event_id=checkout_event_id,
        recipient_person_id=selected_person.id,
        recipient_person_version_id=selected_version.id,
        recipient_display_name=eligible.display_name,
        recipient_relationship=eligible.relationship_label,
        authorization_id=selected_authorization.id,
        authorization_version=selected_authorization.version,
        evidence_id=evidence.id,
        evidence_assessment_id=latest_assessment.id,
        evidence_assessment_version=latest_assessment.version_number,
        authority_revision=head.revision,
        restriction_digest_sha256=release_context.restriction_digest_sha256,
        verification_method=command.verification_method,
        verification_result=command.verification_result,
        verification_policy_code=eligible.verification_policy_code,
        evidence_digest_sha256=evidence_digest,
        decision_policy_version=release_context.decision_policy_version,
        actor_user_id=user.id,
        actor_membership_id=membership.id,
        actor_role_id=role.id,
        actor_role_key=role.key,
        staff_shift_id=shift.id,
        room_id=room.id,
        scope_basis=scope_basis,
        room_assignment_id=room_assignment_id,
        requested_at=command.requested_at,
        checked_out_at=decision_at,
        committed_at=decision_at,
        client_operation_id=command.client_operation_id,
        request_hash=request_hash,
        release_mode="normal",
        override_reason_code=None,
        override_justification=None,
    )
    session.add(snapshot)
    _record_release_commit_signals(
        session,
        organization_id=organization_id,
        actor_user_id=user.id,
        facility_id=facility.id,
        release_id=release_id,
        client_operation_id=command.client_operation_id,
        occurred_at=decision_at,
    )
    if room_safety_active:
        reconcile_facility_exceptions(
            session,
            organization_id=organization_id,
            facility_id=facility.id,
            cause_entity_type="attendance_release",
            cause_entity_id=release_id,
        )

    response = ReleaseCheckoutResponse(
        schema_version="release-checkout-v1",
        resource=_resource_projection(snapshot),
        receipt=_receipt_projection(receipt),
        replayed=False,
    )
    try:
        validate_release_checkout_response(command, response)
    except ReleaseCheckoutContractError as error:
        raise _fail(error.code.value, 409) from error
    _commit(session, context)
    return response


def release_checkout(
    session: Session,
    context: BasicContext,
    command: ReleaseCheckoutCommand,
    *,
    writable: bool = True,
    room_safety_active: bool = False,
) -> ReleaseCheckoutResponse:
    """Resolve exact replay first, or commit one fresh all-or-nothing release."""

    try:
        if session.bind is None or session.bind.dialect.name not in {
            "sqlite",
            "postgresql",
        }:
            raise _fail("family_authority_release_checkout_unavailable", 503)
        request_hash, receipt = begin_command(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            client_operation_id=command.client_operation_id,
            command_type=RELEASE_CHECKOUT_COMMAND_TYPE,
            target_type=RELEASE_CHECKOUT_TARGET_TYPE,
            target_scope=command.child_id,
            intent=command.model_dump(mode="python", exclude={"client_operation_id"}),
            reserve_sqlite_slot=writable,
        )
        if request_hash != release_checkout_request_hash(command):
            raise _fail("release_checkout_request_hash_inconsistent", 503)
        if receipt is not None:
            return _replay(session, command=command, receipt=receipt)
        if not writable:
            raise _fail("database_writes_disabled", 409)
        if session.bind.dialect.name == "postgresql":
            return _fresh_release_postgres(
                session,
                context,
                command,
                request_hash,
                room_safety_active=room_safety_active,
            )
        return _fresh_release(
            session,
            context,
            command,
            request_hash,
            room_safety_active=room_safety_active,
        )
    except ReleaseCheckoutRepositoryError as error:
        session.rollback()
        raise _fail(error.code, error.status_code) from error
    except (ReleaseCheckoutServiceError, HTTPException):
        session.rollback()
        raise
    except (IntegrityError, DBAPIError, ValidationError):
        session.rollback()
        raise _fail("family_authority_release_checkout_unavailable", 503) from None
