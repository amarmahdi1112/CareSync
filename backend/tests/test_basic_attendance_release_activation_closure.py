"""Portable closure proofs for legacy attendance writes after facility activation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    AuditEvent,
    ChildcareCommandReceipt,
    FacilityReleaseCheckoutActivation,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    StaffShift,
)
from tests.test_basic_family_release_context_api import (
    _check_in_child,
    _client,
    _clock_in,
    _facility_tree,
    _family_child_and_enrollment,
    _register,
)

B = "0029B_release_context"
C = "0029C_verified_release_checkout"
ACTIVATION_POLICY = "normal_verified_release_v1"


def _activate_facility(application, auth: dict, facility_id: str) -> UUID:
    """Seed the source-only C activation and its required command receipt."""

    user_id = UUID(auth["user"]["id"])
    facility_uuid = UUID(facility_id)
    with application.state.database.session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
            )
        )
        assert membership is not None
        role = session.scalar(
            select(Role).where(
                Role.organization_id == membership.organization_id,
                Role.id == membership.role_id,
            )
        )
        assert role is not None and role.key == "owner"
        activation_id = uuid4()
        operation_id = uuid4()
        committed_at = datetime.now(UTC)
        session.add(
            ChildcareCommandReceipt(
                id=uuid4(),
                organization_id=membership.organization_id,
                client_operation_id=operation_id,
                command_type="facility.release_checkout.activate",
                target_type="release_activation",
                target_id=activation_id,
                request_hash="a" * 64,
                actor_user_id=user_id,
                facility_id=facility_uuid,
                committed_version=1,
                committed_at=committed_at,
                outcome={},
            )
        )
        session.flush()
        session.add(
            FacilityReleaseCheckoutActivation(
                id=activation_id,
                organization_id=membership.organization_id,
                facility_id=facility_uuid,
                activated_by_user_id=user_id,
                activated_by_membership_id=membership.id,
                activated_by_role_id=role.id,
                activated_by_role_key=role.key,
                activation_operation_id=operation_id,
                activation_policy_version=ACTIVATION_POLICY,
                activated_at=committed_at,
            )
        )
        session.commit()
    return operation_id


def _attendance_write_state(application, attendance_day_id: str) -> tuple[object, ...]:
    day_id = UUID(attendance_day_id)
    with application.state.database.session_factory() as session:
        day = session.get(AttendanceDay, day_id)
        assert day is not None
        intervals = tuple(
            (
                str(interval.id),
                interval.checked_in_at,
                interval.checked_out_at,
            )
            for interval in session.scalars(
                select(AttendanceInterval)
                .where(AttendanceInterval.attendance_day_id == day_id)
                .order_by(AttendanceInterval.sequence)
            )
        )
        return (
            day.version,
            intervals,
            session.scalar(
                select(func.count())
                .select_from(AttendanceEvent)
                .where(AttendanceEvent.attendance_day_id == day_id)
            ),
            session.scalar(select(func.count()).select_from(AuditEvent)),
            session.scalar(select(func.count()).select_from(RealtimeEvent)),
            session.scalar(select(func.count()).select_from(ChildcareCommandReceipt)),
        )


def _wire_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _seed_release_snapshot(application, auth: dict, family: dict, day: dict) -> None:
    """Bind one existing interval to a representative immutable C snapshot."""

    organization_id = UUID(day["organization_id"])
    attendance_day_id = UUID(day["id"])
    interval_id = UUID(day["intervals"][0]["id"])
    user_id = UUID(auth["user"]["id"])
    with application.state.database.session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
        )
        assert membership is not None
        role = session.get(Role, membership.role_id)
        assert role is not None
        staff_shift_id = session.scalar(
            select(StaffShift.id).where(
                StaffShift.organization_id == organization_id,
                StaffShift.membership_id == membership.id,
                StaffShift.facility_id == UUID(day["facility_id"]),
            )
        )
        assert staff_shift_id is not None
        interval = session.scalar(
            select(AttendanceInterval).where(
                AttendanceInterval.organization_id == organization_id,
                AttendanceInterval.attendance_day_id == attendance_day_id,
                AttendanceInterval.id == interval_id,
            )
        )
        assert interval is not None and interval.checked_out_at is not None

    checked_out_at = interval.checked_out_at
    if checked_out_at.tzinfo is None:
        checked_out_at = checked_out_at.replace(tzinfo=UTC)
    release_id = uuid4()
    operation_id = uuid4()
    event_id = uuid4()
    request_hash = "d" * 64
    values = {
        "id": release_id,
        "organization_id": organization_id,
        "family_id": UUID(family["id"]),
        "facility_id": UUID(day["facility_id"]),
        "child_id": UUID(day["child_id"]),
        "attendance_day_id": attendance_day_id,
        "attendance_day_version": day["version"],
        "attendance_interval_id": interval_id,
        "checkout_event_id": event_id,
        "recipient_person_id": uuid4(),
        "recipient_person_version_id": uuid4(),
        "recipient_display_name": "Historical Recipient",
        "recipient_relationship": "Parent",
        "authorization_id": uuid4(),
        "authorization_version": 1,
        "evidence_id": uuid4(),
        "evidence_assessment_id": uuid4(),
        "evidence_assessment_version": 2,
        "authority_revision": 1,
        "restriction_digest_sha256": "b" * 64,
        "verification_method": "government_photo_id",
        "verification_result": "verified",
        "verification_policy_code": "government_photo_id",
        "evidence_digest_sha256": "c" * 64,
        "decision_policy_version": "release-context-v1",
        "actor_user_id": user_id,
        "actor_membership_id": membership.id,
        "actor_role_id": role.id,
        "actor_role_key": role.key,
        "staff_shift_id": staff_shift_id,
        "room_id": UUID(day["room_id"]),
        "scope_basis": "organization_role",
        "room_assignment_id": None,
        "requested_at": checked_out_at - timedelta(seconds=1),
        "checked_out_at": checked_out_at,
        "committed_at": checked_out_at,
        "client_operation_id": operation_id,
        "request_hash": request_hash,
        "release_mode": "normal",
        "override_reason_code": None,
        "override_justification": None,
    }
    engine = application.state.database.engine
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
        connection.execute(
            ChildcareCommandReceipt.__table__.insert(),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "client_operation_id": operation_id,
                "command_type": "attendance.release.checkout",
                "target_type": "attendance_release",
                "target_id": release_id,
                "request_hash": request_hash,
                "actor_user_id": user_id,
                "facility_id": UUID(day["facility_id"]),
                "committed_version": 1,
                "committed_at": checked_out_at,
                "outcome": {},
            },
        )
        connection.execute(
            AttendanceEvent.__table__.insert(),
            {
                "id": event_id,
                "organization_id": organization_id,
                "attendance_day_id": attendance_day_id,
                "client_operation_id": operation_id,
                "actor_user_id": user_id,
                "event_type": "check_out",
                "occurred_at": checked_out_at,
                "reason": None,
                "before": None,
                "after": {"release_snapshot_id": str(release_id)},
            },
        )
        connection.execute(AttendanceReleaseSnapshot.__table__.insert(), values)
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _setup_open_child(tmp_path, monkeypatch, revision: str):
    client, application, _ = _client(tmp_path, monkeypatch, revision)
    auth, headers = _register(client, suffix=f"legacy-{revision}-{uuid4().hex}")
    facility, _, rooms = _facility_tree(client, headers)
    family, child = _family_child_and_enrollment(
        client,
        headers,
        facility,
        rooms[0],
    )
    _clock_in(client, headers, facility["id"])
    day = _check_in_child(client, headers, child["id"], facility["id"])
    return client, application, auth, headers, facility, family, child, day


@pytest.mark.parametrize("revision", [B, C])
def test_legacy_facilities_keep_historical_checkout_behavior(
    tmp_path,
    monkeypatch,
    revision: str,
) -> None:
    client, application, _, headers, facility, _, child, day = _setup_open_child(
        tmp_path,
        monkeypatch,
        revision,
    )
    with client:
        assert application.state.family_release_checkout_foundation_present is (revision == C)
        response = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["id"] == day["id"]


def test_activation_rejects_new_legacy_checkout_without_writes_but_replays_history(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, auth, headers, facility, _, child, day = _setup_open_child(
        tmp_path,
        monkeypatch,
        C,
    )
    with client:
        historical_operation_id = uuid4()
        historical_occurred_at = datetime.now(UTC).isoformat()
        historical = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(historical_operation_id),
                "child_id": child["id"],
                "facility_id": facility["id"],
                    "occurred_at": historical_occurred_at,
            },
        )
        assert historical.status_code == 200, historical.text
        _activate_facility(application, auth, facility["id"])

        replay = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(historical_operation_id),
                "child_id": child["id"],
                "facility_id": facility["id"],
                    "occurred_at": historical_occurred_at,
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == historical.json()["id"]
        assert replay.json()["version"] == historical.json()["version"]
        assert [event["id"] for event in replay.json()["events"]] == [
            event["id"] for event in historical.json()["events"]
        ]

        reopened = _check_in_child(client, headers, child["id"], facility["id"])
        before = _attendance_write_state(application, day["id"])
        rejected = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        after = _attendance_write_state(application, day["id"])

        assert reopened["id"] == day["id"]
        assert rejected.status_code == 409, rejected.text
        assert rejected.json() == {"detail": {"code": "verified_release_checkout_required"}}
        assert after == before


def test_activation_allows_open_interval_correction_but_not_closure(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, auth, headers, facility, _, _, day = _setup_open_child(
        tmp_path,
        monkeypatch,
        C,
    )
    with client:
        _activate_facility(application, auth, facility["id"])
        interval = day["intervals"][0]
        checked_in_at = _wire_instant(interval["checked_in_at"])
        adjusted_check_in = checked_in_at + timedelta(seconds=1)
        corrected = client.put(
            f"/api/v1/attendance/{day['id']}/correction",
            headers=headers,
            json={
                "interval_id": interval["id"],
                "checked_in_at": adjusted_check_in.isoformat(),
                "checked_out_at": None,
                "reason": "Correcting the recorded arrival time",
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["intervals"][0]["checked_out_at"] is None

        before = _attendance_write_state(application, day["id"])
        rejected = client.put(
            f"/api/v1/attendance/{day['id']}/correction",
            headers=headers,
            json={
                "interval_id": interval["id"],
                "checked_in_at": adjusted_check_in.isoformat(),
                "checked_out_at": (adjusted_check_in + timedelta(seconds=2)).isoformat(),
                "reason": "Must use the verified release workflow",
            },
        )
        after = _attendance_write_state(application, day["id"])

        assert rejected.status_code == 409, rejected.text
        assert rejected.json() == {"detail": {"code": "verified_release_checkout_required"}}
        assert after == before


def test_activation_makes_release_bound_interval_immutable(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, auth, headers, facility, family, child, day = _setup_open_child(
        tmp_path,
        monkeypatch,
        C,
    )
    with client:
        checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        assert checkout.status_code == 200, checkout.text
        _activate_facility(application, auth, facility["id"])
        _seed_release_snapshot(application, auth, family, checkout.json())

        interval = checkout.json()["intervals"][0]
        checked_in_at = _wire_instant(interval["checked_in_at"])
        checked_out_at = _wire_instant(interval["checked_out_at"])
        before = _attendance_write_state(application, day["id"])
        rejected = client.put(
            f"/api/v1/attendance/{day['id']}/correction",
            headers=headers,
            json={
                "interval_id": interval["id"],
                "checked_in_at": (checked_in_at - timedelta(seconds=1)).isoformat(),
                "checked_out_at": checked_out_at.isoformat(),
                "reason": "Attempting to rewrite immutable release attendance",
            },
        )
        after = _attendance_write_state(application, day["id"])

        assert rejected.status_code == 409, rejected.text
        assert rejected.json() == {"detail": {"code": "verified_release_interval_immutable"}}
        assert after == before
