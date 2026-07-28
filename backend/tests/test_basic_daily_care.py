"""Phase 2A assigned-room daybook and safety-card acceptance tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.basic.models import AuditEvent, BasicBase, DailyCareRecord, Enrollment, Role
from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct-password-123"
LOCAL_TIMEZONE = ZoneInfo("America/Edmonton")
_TEST_NOW = datetime.now(LOCAL_TIMEZONE)
SERVICE_DATE = _TEST_NOW.date()
_DAY_START = datetime.combine(SERVICE_DATE, time.min, LOCAL_TIMEZONE)
_LOGICAL_SPAN_MINUTES = 9 * 60
_AVAILABLE_SECONDS = max((_TEST_NOW - _DAY_START).total_seconds() - 10, 1)
_TIME_SCALE = min(1.0, _AVAILABLE_SECONDS / _LOGICAL_SPAN_MINUTES)


def _instant(hour: int, minute: int = 0) -> str:
    logical_minutes = (hour * 60 + minute) - (7 * 60)
    return (_DAY_START + timedelta(seconds=1 + logical_minutes * _TIME_SCALE)).isoformat()


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="daily-care-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Care",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility_tree(client: TestClient, headers: dict[str, str], prefix: str):
    facility_response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": f"{prefix} Centre",
            "status": "active",
            "licensed_capacity": 40,
            "timezone": "America/Edmonton",
        },
    )
    assert facility_response.status_code == 201, facility_response.text
    facility = facility_response.json()
    program_response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "name": f"{prefix} Daycare",
            "program_type": "daycare",
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program_response.status_code == 201, program_response.text
    program = program_response.json()
    rooms = []
    for suffix in ("North", "South"):
        room_response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"{prefix} {suffix}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert room_response.status_code == 201, room_response.text
        rooms.append(room_response.json())
    return facility, program, rooms


def _family(client: TestClient, headers: dict[str, str], prefix: str) -> dict:
    response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": f"{prefix} Family",
            "additional_notes": "Private family administration note",
            "consents": {"emergency_medical_consent": True},
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": prefix,
                "relationship": "Parent",
                "email": f"private-{prefix.lower()}@example.com",
                "cell_phone": "",
                "home_phone": "780-555-0101",
                "address": "Private home address",
            },
            "emergency_contacts": [
                {
                    "first_name": "Emergency",
                    "last_name": prefix,
                    "relationship": "Aunt",
                    "cell_phone": "780-555-0102",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _child(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    first_name: str,
    facility: dict,
    program: dict,
    room: dict,
    *,
    enrollment_start_date: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family_id,
            "first_name": first_name,
            "last_name": "Daybook",
            "date_of_birth": "2023-01-01",
            "health_care_number": "HCN-MUST-NOT-LEAK",
            "allergies": "Peanuts",
            "medical_conditions": "Asthma",
            "medications": "Inhaler awareness only",
            "immunization_up_to_date": True,
            "doctor_name": "Dr. Must Not Leak",
            "doctor_phone": "780-555-0199",
        },
    )
    assert response.status_code == 201, response.text
    child = response.json()
    start_date = enrollment_start_date or SERVICE_DATE.isoformat()
    enrollment_response = client.post(
        f"/api/v1/children/{child['id']}/enrollments",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "start_date": start_date,
        },
    )
    assert enrollment_response.status_code == 201, enrollment_response.text
    enrollment = enrollment_response.json()
    approval_response = client.post(
        f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": enrollment["version"],
            "room_id": room["id"],
            "effective_date": max(SERVICE_DATE.isoformat(), start_date),
        },
    )
    assert approval_response.status_code == 200, approval_response.text
    if date.fromisoformat(start_date) < SERVICE_DATE:
        # Historical attendance fixtures predate the 0028 approval workflow, whose
        # live command intentionally never backdates a new placement.
        with client.app.state.database.session_factory() as session:
            stored_enrollment = session.scalar(
                select(Enrollment).where(Enrollment.id == UUID(enrollment["id"]))
            )
            assert stored_enrollment is not None
            stored_enrollment.placement_effective_date = date.fromisoformat(start_date)
            session.commit()
    refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    return refreshed.json()


def _check_in(
    client: TestClient,
    headers: dict[str, str],
    child_id: str,
    facility_id: str,
    hour: int = 8,
) -> dict:
    response = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "child_id": child_id,
            "facility_id": facility_id,
            "occurred_at": _instant(hour),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_record(
    client: TestClient,
    headers: dict[str, str],
    attendance_day_id: str,
    care_type: str,
    occurred_at: str,
    payload: dict,
    *,
    note: str | None = None,
    operation_id: str | None = None,
):
    values = {
        "attendance_day_id": attendance_day_id,
        "care_type": care_type,
        "occurred_at": occurred_at,
        "payload": payload,
        "client_operation_id": operation_id or str(uuid4()),
    }
    if note is not None:
        values["note"] = note
    return client.post("/api/v1/care/records", headers=headers, json=values)


def _token_from_url(value: str) -> str:
    parsed = urlparse(value)
    values = parse_qs(parsed.fragment).get("token", [])
    assert len(values) == 1
    return values[0]


def _invite_educator(
    client: TestClient,
    owner_headers: dict[str, str],
    facility_id: str,
    room_id: str,
    email: str,
) -> dict[str, str]:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    educator_role = next(role for role in workspace.json()["roles"] if role["key"] == "educator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": email,
            "first_name": "Room",
            "last_name": "Educator",
            "role_id": educator_role["id"],
            "assigned_facility_ids": [facility_id],
            "assigned_room_ids": [room_id],
        },
    )
    assert invitation.status_code == 201, invitation.text
    token = _token_from_url(invitation.json()["activation_url"])
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    headers = _headers(accepted.json())
    clocked_in = client.post(
        "/api/v1/staff/self/shifts/clock-in",
        headers=headers,
        json={"facility_id": facility_id, "operation_id": str(uuid4())},
    )
    assert clocked_in.status_code == 201, clocked_in.text
    return headers


def test_attendance_exact_retry_binds_the_server_evidence_timestamp(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "attendance-intent-owner@example.com",
            "Attendance Intent",
        )
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(
            client,
            headers,
            "Attendance Intent",
        )
        family = _family(client, headers, "AttendanceIntent")
        child = _child(
            client,
            headers,
            family["id"],
            "Timestamp",
            facility,
            program,
            rooms[0],
        )

        check_in_operation = str(uuid4())
        check_in_payload = {
            "client_operation_id": check_in_operation,
            "child_id": child["id"],
            "facility_id": facility["id"],
            "occurred_at": _instant(8),
        }
        checked_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json=check_in_payload,
        )
        assert checked_in.status_code == 200, checked_in.text
        exact_check_in_replay = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json=check_in_payload,
        )
        assert exact_check_in_replay.status_code == 200
        changed_check_in_replay = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={**check_in_payload, "occurred_at": _instant(8, 5)},
        )
        assert changed_check_in_replay.status_code == 409

        check_out_operation = str(uuid4())
        check_out_payload = {
            "client_operation_id": check_out_operation,
            "child_id": child["id"],
            "facility_id": facility["id"],
            "occurred_at": _instant(10),
        }
        checked_out = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json=check_out_payload,
        )
        assert checked_out.status_code == 200, checked_out.text
        exact_check_out_replay = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json=check_out_payload,
        )
        assert exact_check_out_replay.status_code == 200
        changed_check_out_replay = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={**check_out_payload, "occurred_at": _instant(10, 5)},
        )
        assert changed_check_out_replay.status_code == 409


def test_exact_care_replay_recovers_after_checkout_and_shift_close(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "care-replay-owner@example.com", "Care Replay")
        owner_headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, owner_headers, "Replay")
        family = _family(client, owner_headers, "Replay")
        child = _child(
            client,
            owner_headers,
            family["id"],
            "Safe",
            facility,
            program,
            rooms[0],
        )
        day = _check_in(client, owner_headers, child["id"], facility["id"])
        educator_headers = _invite_educator(
            client,
            owner_headers,
            facility["id"],
            rooms[0]["id"],
            "care-replay-educator@example.com",
        )
        operation_id = str(uuid4())
        created = _create_record(
            client,
            educator_headers,
            day["id"],
            "mood",
            _instant(9),
            {"value": "calm"},
            note="Response may be lost",
            operation_id=operation_id,
        )
        assert created.status_code == 201, created.text
        assert created.json()["recorded_client_operation_id"] == operation_id
        foreign_actor_replay = _create_record(
            client,
            owner_headers,
            day["id"],
            "mood",
            _instant(9),
            {"value": "calm"},
            note="Response may be lost",
            operation_id=operation_id,
        )
        assert foreign_actor_replay.status_code == 404
        correction_operation = str(uuid4())
        correction_payload = {
            "occurred_at": _instant(9, 5),
            "payload": {"value": "happy"},
            "note": "Corrected after the original save",
            "reason": "Correcting the observation",
            "expected_version": 1,
            "client_operation_id": correction_operation,
        }
        corrected = client.put(
            f"/api/v1/care/records/{created.json()['id']}/correction",
            headers=owner_headers,
            json=correction_payload,
        )
        assert corrected.status_code == 200, corrected.text
        with client.app.state.database.session_factory() as session:
            owner_role = session.scalar(
                select(Role).where(
                    Role.organization_id == UUID(owner["user"]["organization_id"]),
                    Role.key == "owner",
                )
            )
            assert owner_role is not None
            owner_role.permissions = [
                permission
                for permission in owner_role.permissions
                if permission != "care:correct"
            ]
            if "care:correct_own" not in owner_role.permissions:
                owner_role.permissions = [
                    *owner_role.permissions,
                    "care:correct_own",
                ]
            session.commit()
        unauthorized_correction_replay = client.put(
            f"/api/v1/care/records/{created.json()['id']}/correction",
            headers=owner_headers,
            json=correction_payload,
        )
        assert unauthorized_correction_replay.status_code == 404

        clocked_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert clocked_out.status_code == 200, clocked_out.text
        checked_out = client.post(
            "/api/v1/attendance/check-out",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(10),
            },
        )
        assert checked_out.status_code == 200, checked_out.text

        replay = _create_record(
            client,
            educator_headers,
            day["id"],
            "mood",
            _instant(9),
            {"value": "calm"},
            note="Response may be lost",
            operation_id=operation_id,
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == created.json()["id"]
        assert replay.json()["recorded_client_operation_id"] == operation_id
        assert replay.json()["occurred_at"] == corrected.json()["occurred_at"]
        assert replay.json()["payload"] == {"value": "happy"}
        changed = _create_record(
            client,
            educator_headers,
            day["id"],
            "mood",
            _instant(9),
            {"value": "upset"},
            operation_id=operation_id,
        )
        assert changed.status_code == 409


def test_daybook_happy_path_idempotence_truthful_sleep_and_audit_minimization(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "care-owner@example.com", "Care Daybook")
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, headers, "Care")
        family = _family(client, headers, "Care")
        child = _child(
            client,
            headers,
            family["id"],
            "Amina",
            facility,
            program,
            rooms[0],
        )
        day = _check_in(client, headers, child["id"], facility["id"])

        operation_id = str(uuid4())
        feeding = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(9),
            {"kind": "meal", "intake": "most"},
            note="Ate comfortably",
            operation_id=operation_id,
        )
        assert feeding.status_code == 201, feeding.text
        assert feeding.headers["cache-control"] == "private, no-store"
        feeding_record = feeding.json()
        assert feeding_record["last_event_type"] == "recorded"
        assert feeding_record["was_corrected"] is False

        replay = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(9),
            {"kind": "meal", "intake": "most"},
            note="Ate comfortably",
            operation_id=operation_id,
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == feeding_record["id"]
        changed_replay = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(9),
            {"kind": "meal", "intake": "none"},
            note="Different content",
            operation_id=operation_id,
        )
        assert changed_replay.status_code == 409

        sleep = _create_record(
            client,
            headers,
            day["id"],
            "sleep",
            _instant(12),
            {},
        )
        assert sleep.status_code == 201, sleep.text
        second_open_sleep = _create_record(
            client,
            headers,
            day["id"],
            "sleep",
            _instant(12, 5),
            {},
        )
        assert second_open_sleep.status_code == 409

        checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(16),
            },
        )
        assert checkout.status_code == 200, checkout.text
        daybook = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert daybook.status_code == 200, daybook.text
        assert daybook.headers["cache-control"] == "private, no-store"
        records = daybook.json()["children"][0]["records"]
        sleep_record = next(record for record in records if record["care_type"] == "sleep")
        assert sleep_record["ended_at"] is not None
        assert sleep_record["last_event_type"] == "auto_finished_at_checkout"

        history = client.get(
            f"/api/v1/care/records/{sleep_record['id']}/history",
            headers=headers,
        )
        assert history.status_code == 200, history.text
        assert [event["event_type"] for event in history.json()] == [
            "recorded",
            "auto_finished_at_checkout",
        ]
        assert history.headers["cache-control"] == "private, no-store"

        with application.state.database.session_factory() as session:
            audits = list(
                session.scalars(select(AuditEvent).where(AuditEvent.action.like("care.%")))
            )
            assert audits
            serialized_details = " ".join(str(event.details) for event in audits)
            assert "Ate comfortably" not in serialized_details
            assert "most" not in serialized_details
            assert "Peanuts" not in serialized_details


def test_safety_card_is_facility_local_minimized_and_includes_all_usable_contacts(
    tmp_path,
) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "safety-owner@example.com", "Safety Care")
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, headers, "Safety")
        family = _family(client, headers, "Safety")
        child = _child(
            client,
            headers,
            family["id"],
            "Bilal",
            facility,
            program,
            rooms[0],
        )
        response = client.get(
            f"/api/v1/care/children/{child['id']}/safety-card",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        data = response.json()
        assert data["safety"] == {
            "allergies": "Peanuts",
            "medical_conditions": "Asthma",
            "medication_awareness": "Inhaler awareness only",
            "emergency_medical_consent": True,
        }
        primary_contacts = [
            contact for contact in data["contacts"] if contact["contact_type"] == "primary_guardian"
        ]
        assert [contact["phone"] for contact in primary_contacts] == [
            "780-555-0101",
        ]
        emergency_contacts = [
            contact
            for contact in data["contacts"]
            if contact["contact_type"] == "emergency_contact"
        ]
        assert [contact["phone"] for contact in emergency_contacts] == ["780-555-0102"]
        serialized = response.text
        for forbidden in (
            "HCN-MUST-NOT-LEAK",
            "Private home address",
            "private-safety@example.com",
            "Dr. Must Not Leak",
            "780-555-0199",
            "Private family administration note",
        ):
            assert forbidden not in serialized


def test_educator_room_scope_active_roster_corrections_and_enrollment_lock(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "scope-care-owner@example.com", "Scope Care")
        owner_headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, owner_headers, "Scope")
        family = _family(client, owner_headers, "Scope")
        north_child = _child(
            client,
            owner_headers,
            family["id"],
            "North",
            facility,
            program,
            rooms[0],
        )
        south_child = _child(
            client,
            owner_headers,
            family["id"],
            "South",
            facility,
            program,
            rooms[1],
        )
        paused_child = _child(
            client,
            owner_headers,
            family["id"],
            "Paused",
            facility,
            program,
            rooms[0],
        )
        paused_enrollment = paused_child["enrollments"][0]
        paused = client.patch(
            f"/api/v1/enrollments/{paused_enrollment['id']}",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": paused_enrollment["version"],
                "status": "paused",
            },
        )
        assert paused.status_code == 200, paused.text
        north_day = _check_in(client, owner_headers, north_child["id"], facility["id"])
        south_day = _check_in(client, owner_headers, south_child["id"], facility["id"])
        educator_headers = _invite_educator(
            client,
            owner_headers,
            facility["id"],
            rooms[0]["id"],
            "north-care-educator@example.com",
        )

        north_board = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=educator_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert north_board.status_code == 200, north_board.text
        assert {child["child_name"] for child in north_board.json()["children"]} == {
            "North Daybook"
        }
        with application.state.database.session_factory() as session:
            educator_role = session.scalar(
                select(Role).where(
                    Role.organization_id == UUID(owner["user"]["organization_id"]),
                    Role.key == "educator",
                )
            )
            assert educator_role is not None
            educator_role.permissions = [
                permission
                for permission in educator_role.permissions
                if permission != "child_safety:read"
            ]
            session.commit()
        safety_permission_denied = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=educator_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert safety_permission_denied.status_code == 403
        with application.state.database.session_factory() as session:
            educator_role = session.scalar(
                select(Role).where(
                    Role.organization_id == UUID(owner["user"]["organization_id"]),
                    Role.key == "educator",
                )
            )
            assert educator_role is not None
            educator_role.permissions = [*educator_role.permissions, "child_safety:read"]
            session.commit()
        assert (
            client.get(
                f"/api/v1/care/rooms/{rooms[1]['id']}/day",
                headers=educator_headers,
                params={"date": SERVICE_DATE.isoformat()},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/care/rooms/{rooms[0]['id']}/day",
                headers=educator_headers,
                params={"date": (SERVICE_DATE - timedelta(days=1)).isoformat()},
            ).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/v1/care/children/{south_child['id']}/safety-card",
                headers=educator_headers,
                params={"facility_id": facility["id"]},
            ).status_code
            == 404
        )

        denied = _create_record(
            client,
            educator_headers,
            south_day["id"],
            "mood",
            _instant(9),
            {"value": "happy"},
        )
        assert denied.status_code == 404
        created = _create_record(
            client,
            educator_headers,
            north_day["id"],
            "diaper",
            _instant(9),
            {"outcome": "wet"},
        )
        assert created.status_code == 201, created.text
        correction_operation = str(uuid4())
        corrected = client.put(
            f"/api/v1/care/records/{created.json()['id']}/correction",
            headers=educator_headers,
            json={
                "occurred_at": _instant(9, 5),
                "payload": {"outcome": "both"},
                "note": "Corrected immediately",
                "reason": "Selected the wrong outcome",
                "expected_version": 1,
                "client_operation_id": correction_operation,
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["was_corrected"] is True
        own_history = client.get(
            f"/api/v1/care/records/{created.json()['id']}/history",
            headers=educator_headers,
        )
        assert own_history.status_code == 200, own_history.text
        assert [item["event_type"] for item in own_history.json()] == [
            "recorded",
            "corrected",
        ]
        assert (
            client.post(
                f"/api/v1/care/records/{created.json()['id']}/void",
                headers=educator_headers,
                json={
                    "reason": "Educator cannot void",
                    "expected_version": 2,
                    "client_operation_id": str(uuid4()),
                },
            ).status_code
            == 403
        )

        move_while_present = client.patch(
            f"/api/v1/enrollments/{north_child['enrollments'][0]['id']}",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": north_child["enrollments"][0]["version"],
                "status": "paused",
            },
        )
        assert move_while_present.status_code == 409


def test_care_time_bounds_attendance_corrections_and_database_checks(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "bounds-care-owner@example.com", "Bounds Care")
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, headers, "Bounds")
        family = _family(client, headers, "Bounds")
        child = _child(
            client,
            headers,
            family["id"],
            "Hana",
            facility,
            program,
            rooms[0],
        )
        future_check_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            },
        )
        assert future_check_in.status_code == 422
        day = _check_in(client, headers, child["id"], facility["id"])
        future_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            },
        )
        assert future_checkout.status_code == 422
        before_check_in = _create_record(
            client,
            headers,
            day["id"],
            "activity",
            _instant(7, 30),
            {"kind": "indoor"},
        )
        assert before_check_in.status_code == 409
        naive_time = _create_record(
            client,
            headers,
            day["id"],
            "mood",
            f"{SERVICE_DATE.isoformat()}T09:00:00",
            {"value": "calm"},
        )
        assert naive_time.status_code == 422
        wrong_payload = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(9),
            {"outcome": "wet"},
        )
        assert wrong_payload.status_code == 422
        contradictory_bottle = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(9),
            {"kind": "bottle", "intake": "none", "volume_ml": 120},
        )
        assert contradictory_bottle.status_code == 422

        care = _create_record(
            client,
            headers,
            day["id"],
            "mood",
            _instant(10),
            {"value": "calm"},
        )
        assert care.status_code == 201, care.text
        early_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(9, 30),
            },
        )
        assert early_checkout.status_code == 409
        interval_id = day["intervals"][0]["id"]
        stranded = client.put(
            f"/api/v1/attendance/{day['id']}/correction",
            headers=headers,
            json={
                "interval_id": interval_id,
                "checked_in_at": _instant(8),
                "checked_out_at": _instant(9, 30),
                "reason": "Would strand the care fact",
            },
        )
        assert stranded.status_code == 409

        with application.state.database.session_factory() as session:
            with pytest.raises(IntegrityError), session.begin():
                session.execute(
                    text(
                        "UPDATE daily_care_records SET ended_at = :ended_at WHERE id = :record_id"
                    ),
                    {
                        "ended_at": datetime.now(UTC),
                        "record_id": UUID(care.json()["id"]).hex,
                    },
                )
            stored = session.scalar(
                select(DailyCareRecord).where(DailyCareRecord.id == UUID(care.json()["id"]))
            )
            assert stored is not None and stored.ended_at is None


def test_room_daybook_query_count_does_not_scale_per_child_or_record(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "query-care-owner@example.com", "Query Care")
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, headers, "Query")
        family = _family(client, headers, "Query")

        def add_child(index: int) -> None:
            child = _child(
                client,
                headers,
                family["id"],
                f"Child{index:02d}",
                facility,
                program,
                rooms[0],
            )
            day = _check_in(client, headers, child["id"], facility["id"])
            recorded = _create_record(
                client,
                headers,
                day["id"],
                "mood",
                _instant(9),
                {"value": "happy"},
            )
            assert recorded.status_code == 201, recorded.text

        def query_count() -> int:
            statements: list[str] = []

            def count_statement(*args) -> None:
                statements.append(str(args[2]))

            engine = application.state.database.engine
            event.listen(engine, "before_cursor_execute", count_statement)
            try:
                response = client.get(
                    f"/api/v1/care/rooms/{rooms[0]['id']}/day",
                    headers=headers,
                    params={"date": SERVICE_DATE.isoformat()},
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_statement)
            assert response.status_code == 200, response.text
            return len(statements)

        add_child(1)
        one_child_queries = query_count()
        for index in range(2, 7):
            add_child(index)
        six_child_queries = query_count()

        assert six_child_queries <= one_child_queries + 1
        assert six_child_queries <= 18


def test_snapshot_daybook_and_history_survive_preexisting_move_and_placement_deactivation(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "history-care-owner@example.com", "History Care")
        owner_headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, owner_headers, "History")
        family = _family(client, owner_headers, "History")
        child = _child(
            client,
            owner_headers,
            family["id"],
            "Snapshot",
            facility,
            program,
            rooms[0],
        )
        day = _check_in(client, owner_headers, child["id"], facility["id"])
        record_operation_id = str(uuid4())
        recorded = _create_record(
            client,
            owner_headers,
            day["id"],
            "diaper",
            _instant(9),
            {"outcome": "wet"},
            operation_id=record_operation_id,
        )
        assert recorded.status_code == 201, recorded.text
        record = recorded.json()
        correction_operation_id = str(uuid4())
        corrected = client.put(
            f"/api/v1/care/records/{record['id']}/correction",
            headers=owner_headers,
            json={
                "occurred_at": _instant(9, 5),
                "ended_at": None,
                "payload": {"outcome": "both"},
                "note": "Corrected before the room closed",
                "reason": "Correcting the recorded diaper outcome",
                "expected_version": 1,
                "client_operation_id": correction_operation_id,
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["version"] == 2
        educator_headers = _invite_educator(
            client,
            owner_headers,
            facility["id"],
            rooms[0]["id"],
            "history-care-educator@example.com",
        )
        live_impact = client.get(
            f"/api/v1/rooms/{rooms[0]['id']}/deactivation-impact",
            headers=owner_headers,
        )
        assert live_impact.status_code == 200, live_impact.text
        assert live_impact.json()["open_attendance_intervals"] == 1
        assert live_impact.json()["active_staff_assignments"] == 1
        assert live_impact.json()["can_deactivate"] is False
        blocked_live_deactivation = client.patch(
            f"/api/v1/rooms/{rooms[0]['id']}",
            headers=owner_headers,
            json={
                "is_active": False,
                "deactivation_confirmation": rooms[0]["name"],
                "deactivation_reason": "Unsafe while a child is checked in",
            },
        )
        assert blocked_live_deactivation.status_code == 409
        checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(16),
            },
        )
        assert checkout.status_code == 200, checkout.text

        # The current command surface deliberately stages first-class transfers for
        # a later slice. Seed a pre-existing completed transfer to retain the
        # historical snapshot/deactivation regression this test owns.
        with application.state.database.session_factory() as session:
            moved = session.scalar(
                select(Enrollment).where(Enrollment.id == UUID(child["enrollments"][0]["id"]))
            )
            assert moved is not None
            moved.program_id = UUID(program["id"])
            moved.room_id = UUID(rooms[1]["id"])
            moved.version += 1
            session.commit()
        inactive_placement_child = _child(
            client,
            owner_headers,
            family["id"],
            "InactivePlacement",
            facility,
            program,
            rooms[0],
        )
        after_move = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=owner_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert after_move.status_code == 200, after_move.text
        after_move_children = {item["child_id"]: item for item in after_move.json()["children"]}
        assert child["id"] in after_move_children
        assert after_move_children[child["id"]]["records"][0]["id"] == record["id"]

        historical_room_impact = client.get(
            f"/api/v1/rooms/{rooms[0]['id']}/deactivation-impact",
            headers=owner_headers,
        )
        assert historical_room_impact.status_code == 200, historical_room_impact.text
        assert historical_room_impact.json()["open_attendance_intervals"] == 0
        assert historical_room_impact.json()["open_enrollments"] == 1
        assert historical_room_impact.json()["active_staff_assignments"] == 1
        assert historical_room_impact.json()["warnings"]
        assert historical_room_impact.json()["can_deactivate"] is False
        inactive_enrollment = inactive_placement_child["enrollments"][0]
        ended_inactive_placement = client.patch(
            f"/api/v1/enrollments/{inactive_enrollment['id']}",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": inactive_enrollment["version"],
                "status": "ended",
                "end_date": SERVICE_DATE.isoformat(),
            },
        )
        assert ended_inactive_placement.status_code == 200, ended_inactive_placement.text
        cleared_room_impact = client.get(
            f"/api/v1/rooms/{rooms[0]['id']}/deactivation-impact",
            headers=owner_headers,
        )
        assert cleared_room_impact.status_code == 200, cleared_room_impact.text
        assert cleared_room_impact.json()["open_enrollments"] == 0
        assert cleared_room_impact.json()["active_staff_assignments"] == 1
        assert cleared_room_impact.json()["can_deactivate"] is True
        unconfirmed_room_deactivation = client.patch(
            f"/api/v1/rooms/{rooms[0]['id']}",
            headers=owner_headers,
            json={"is_active": False},
        )
        assert unconfirmed_room_deactivation.status_code == 422

        room_deactivated = client.patch(
            f"/api/v1/rooms/{rooms[0]['id']}",
            headers=owner_headers,
            json={
                "is_active": False,
                "deactivation_confirmation": rooms[0]["name"],
                "deactivation_reason": "Historical placement closure test",
            },
        )
        assert room_deactivated.status_code == 200, room_deactivated.text
        inactive_room_check_in = client.post(
            "/api/v1/attendance/check-in",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": inactive_placement_child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(10),
            },
        )
        assert inactive_room_check_in.status_code == 409, inactive_room_check_in.text
        roster_after_room_closure = client.get(
            "/api/v1/attendance/roster",
            headers=owner_headers,
            params={"date": SERVICE_DATE.isoformat(), "facility_id": facility["id"]},
        )
        assert roster_after_room_closure.status_code == 200, roster_after_room_closure.text
        assert inactive_placement_child["id"] not in {
            item["child_id"] for item in roster_after_room_closure.json()
        }
        staff_clock_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert staff_clock_out.status_code == 200, staff_clock_out.text
        facility_impact = client.get(
            f"/api/v1/facilities/{facility['id']}/deactivation-impact",
            headers=owner_headers,
        )
        assert facility_impact.status_code == 200, facility_impact.text
        assert facility_impact.json()["open_attendance_intervals"] == 0
        assert facility_impact.json()["open_staff_shifts"] == 0
        assert facility_impact.json()["warnings"]
        assert facility_impact.json()["can_deactivate"] is False
        current_child = client.get(f"/api/v1/children/{child['id']}", headers=owner_headers)
        assert current_child.status_code == 200, current_child.text
        current_enrollment = current_child.json()["enrollments"][0]
        ended_moved_enrollment = client.patch(
            f"/api/v1/enrollments/{current_enrollment['id']}",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": current_enrollment["version"],
                "status": "ended",
                "end_date": SERVICE_DATE.isoformat(),
            },
        )
        assert ended_moved_enrollment.status_code == 200, ended_moved_enrollment.text
        second_room_closed = client.patch(
            f"/api/v1/rooms/{rooms[1]['id']}",
            headers=owner_headers,
            json={
                "is_active": False,
                "deactivation_confirmation": rooms[1]["name"],
                "deactivation_reason": "Facility closure test",
            },
        )
        assert second_room_closed.status_code == 200, second_room_closed.text
        program_closed = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=owner_headers,
            json={"is_active": False},
        )
        assert program_closed.status_code == 200, program_closed.text
        ready_facility_impact = client.get(
            f"/api/v1/facilities/{facility['id']}/deactivation-impact",
            headers=owner_headers,
        )
        assert ready_facility_impact.status_code == 200, ready_facility_impact.text
        assert ready_facility_impact.json()["can_deactivate"] is True
        facility_deactivated = client.patch(
            f"/api/v1/facilities/{facility['id']}",
            headers=owner_headers,
            json={
                "status": "inactive",
                "deactivation_confirmation": facility["name"],
                "deactivation_reason": "Historical facility closure test",
            },
        )
        assert facility_deactivated.status_code == 200, facility_deactivated.text

        retained_daybook = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=owner_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert retained_daybook.status_code == 200, retained_daybook.text
        retained_child = retained_daybook.json()["children"][0]
        assert retained_child["attendance_day_id"] == day["id"]
        assert retained_child["records"][0]["id"] == record["id"]
        history = client.get(
            f"/api/v1/care/records/{record['id']}/history",
            headers=owner_headers,
        )
        assert history.status_code == 200, history.text
        assert [item["event_type"] for item in history.json()] == [
            "recorded",
            "corrected",
        ]

        assert (
            client.get(
                f"/api/v1/care/rooms/{rooms[0]['id']}/day",
                headers=educator_headers,
                params={"date": SERVICE_DATE.isoformat()},
            ).status_code
            == 404
        )
        create_replay = _create_record(
            client,
            owner_headers,
            day["id"],
            "diaper",
            _instant(9),
            {"outcome": "wet"},
            operation_id=record_operation_id,
        )
        assert create_replay.status_code == 201, create_replay.text
        assert create_replay.json()["id"] == record["id"]
        assert create_replay.json()["payload"] == {"outcome": "both"}
        correction_replay = client.put(
            f"/api/v1/care/records/{record['id']}/correction",
            headers=owner_headers,
            json={
                "occurred_at": _instant(9, 5),
                "ended_at": None,
                "payload": {"outcome": "both"},
                "note": "Corrected before the room closed",
                "reason": "Correcting the recorded diaper outcome",
                "expected_version": 1,
                "client_operation_id": correction_operation_id,
            },
        )
        assert correction_replay.status_code == 200, correction_replay.text
        assert correction_replay.json()["version"] == 2
        denied_mutation = client.put(
            f"/api/v1/care/records/{record['id']}/correction",
            headers=owner_headers,
            json={
                "occurred_at": _instant(9, 5),
                "payload": {"outcome": "both"},
                "reason": "Must remain blocked after placement deactivation",
                "expected_version": 2,
                "client_operation_id": str(uuid4()),
            },
        )
        assert denied_mutation.status_code == 404


def test_attendance_stays_on_service_date_but_allows_dst_offset_change(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "date-care-owner@example.com", "Date Care")
        headers = _headers(owner)
        facility, program, rooms = _facility_tree(client, headers, "Date")
        family = _family(client, headers, "Date")
        cross_midnight_child = _child(
            client,
            headers,
            family["id"],
            "Midnight",
            facility,
            program,
            rooms[0],
            enrollment_start_date="2025-01-01",
        )
        checked_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": cross_midnight_child["id"],
                "facility_id": facility["id"],
                "occurred_at": "2025-11-01T08:00:00-06:00",
            },
        )
        assert checked_in.status_code == 200, checked_in.text
        day = checked_in.json()
        sleep = _create_record(
            client,
            headers,
            day["id"],
            "sleep",
            "2025-11-01T23:30:00-06:00",
            {},
        )
        assert sleep.status_code == 201, sleep.text

        cross_midnight_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": cross_midnight_child["id"],
                "facility_id": facility["id"],
                "occurred_at": "2025-11-02T00:05:00-06:00",
            },
        )
        assert cross_midnight_checkout.status_code == 422
        daybook = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/day",
            headers=headers,
            params={"date": "2025-11-01"},
        )
        assert daybook.status_code == 200, daybook.text
        assert daybook.json()["children"][0]["records"][0]["ended_at"] is None

        cross_midnight_correction = client.put(
            f"/api/v1/attendance/{day['id']}/correction",
            headers=headers,
            json={
                "interval_id": day["intervals"][0]["id"],
                "checked_in_at": "2025-11-01T08:00:00-06:00",
                "checked_out_at": "2025-11-02T00:05:00-06:00",
                "reason": "Must not cross the service-date boundary",
            },
        )
        assert cross_midnight_correction.status_code == 422
        valid_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": cross_midnight_child["id"],
                "facility_id": facility["id"],
                "occurred_at": "2025-11-01T23:45:00-06:00",
            },
        )
        assert valid_checkout.status_code == 200, valid_checkout.text

        dst_child = _child(
            client,
            headers,
            family["id"],
            "Fallback",
            facility,
            program,
            rooms[0],
            enrollment_start_date="2025-01-01",
        )
        dst_check_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": dst_child["id"],
                "facility_id": facility["id"],
                "occurred_at": "2025-11-02T01:30:00-06:00",
            },
        )
        assert dst_check_in.status_code == 200, dst_check_in.text
        dst_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": dst_child["id"],
                "facility_id": facility["id"],
                "occurred_at": "2025-11-02T01:45:00-07:00",
            },
        )
        assert dst_checkout.status_code == 200, dst_checkout.text
        assert dst_checkout.json()["service_date"] == "2025-11-02"
