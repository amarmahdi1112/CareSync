"""Opt-in PostgreSQL proof for room-deactivation/check-in serialization.

The test is skipped unless ``BASIC_POSTGRES_TEST_PORT`` identifies an explicitly
disposable, migrated PostgreSQL database with runtime grants applied. Independent
application pools force the competing requests onto separate database sessions so
the shared facility-row lock is exercised by PostgreSQL rather than by a test
double.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from threading import Event, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.basic import attendance as attendance_api
from app.api.basic import organization as organization_api
from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
if TEST_PORT and int(TEST_PORT) in {5432, 5433, 5434}:
    raise RuntimeError(
        "BASIC_POSTGRES_TEST_PORT must never target the existing 5432/5433/5434 databases"
    )
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)

EVENT_TIMEOUT_SECONDS = 5.0
SERIALIZATION_WINDOW_SECONDS = 1.0
JOIN_TIMEOUT_SECONDS = 8.0


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-room-deactivation-race-secret-at-least-32-bytes",
    )


def _application(settings: Settings):
    application = create_app(settings)

    @event.listens_for(application.state.database.engine, "connect")
    def configure_timeouts(dbapi_connection, _connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '3s'")
            cursor.execute("SET statement_timeout = '10s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '10s'")

    return application


def _create_scenario(
    client: TestClient, *, end_enrollment: bool = False
) -> tuple[dict[str, str], dict[str, str]]:
    identifier = uuid4().hex
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"room-deactivation-race-{identifier}@example.com",
            "password": "correct-password",
            "first_name": "Room",
            "last_name": "Owner",
            "organization_name": f"Room Deactivation Race {identifier}",
        },
    )
    assert auth.status_code == 201, auth.text
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    timezone = ZoneInfo("America/Edmonton")
    service_date = datetime.now(timezone).date()
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Room Deactivation Race Centre",
            "timezone": timezone.key,
            "licensed_capacity": 20,
            "status": "active",
        },
    )
    assert facility.status_code == 201, facility.text
    program = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "name": "Race Daycare",
            "program_type": "daycare",
            "capacity": 20,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program.status_code == 201, program.text
    room = client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "program_id": program.json()["id"],
            "name": "Race Room",
            "capacity": 20,
            "age_group": "Toddler",
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert room.status_code == 201, room.text
    family = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": "Room Deactivation Race Family",
        },
    )
    assert family.status_code == 201, family.text
    child = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family.json()["id"],
            "first_name": "Facility",
            "last_name": "Lock",
            "date_of_birth": "2023-01-01",
        },
    )
    assert child.status_code == 201, child.text
    enrollment = client.post(
        f"/api/v1/children/{child.json()['id']}/enrollments",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility.json()["id"],
            "start_date": service_date.isoformat(),
        },
    )
    assert enrollment.status_code == 201, enrollment.text
    placement = client.post(
        f"/api/v1/enrollments/{enrollment.json()['id']}/placement-approval",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": enrollment.json()["version"],
            "room_id": room.json()["id"],
            "effective_date": service_date.isoformat(),
        },
    )
    assert placement.status_code == 200, placement.text
    if end_enrollment:
        ended = client.patch(
            f"/api/v1/enrollments/{enrollment.json()['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": placement.json()["version"],
                "status": "ended",
                "end_date": service_date.isoformat(),
            },
        )
        assert ended.status_code == 200, ended.text
    scenario = {
        "facility_id": facility.json()["id"],
        "room_id": room.json()["id"],
        "room_name": room.json()["name"],
        "child_id": child.json()["id"],
        "occurred_at": (datetime.now(timezone) - timedelta(seconds=1)).isoformat(),
    }
    return headers, scenario


def _check_in(
    client: TestClient,
    headers: dict[str, str],
    scenario: dict[str, str],
    responses: dict[str, object],
    failures: dict[str, Exception],
) -> None:
    try:
        responses["check_in"] = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": scenario["child_id"],
                "facility_id": scenario["facility_id"],
                "occurred_at": scenario["occurred_at"],
            },
        )
    except Exception as error:  # pragma: no cover - diagnostic path
        failures["check_in"] = error


def _deactivate_room(
    client: TestClient,
    headers: dict[str, str],
    scenario: dict[str, str],
    responses: dict[str, object],
    failures: dict[str, Exception],
) -> None:
    try:
        responses["deactivation"] = client.patch(
            f"/api/v1/rooms/{scenario['room_id']}",
            headers=headers,
            json={
                "is_active": False,
                "deactivation_confirmation": scenario["room_name"],
                "deactivation_reason": "Concurrency regression test",
            },
        )
    except Exception as error:  # pragma: no cover - diagnostic path
        failures["deactivation"] = error


def test_check_in_lock_wins_and_room_deactivation_observes_open_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    attendance_application = _application(settings)
    organization_application = _application(settings)

    with (
        TestClient(attendance_application, raise_server_exceptions=False) as attendance_client,
        TestClient(organization_application, raise_server_exceptions=False) as organization_client,
    ):
        headers, scenario = _create_scenario(attendance_client)
        check_in_holds_facility_lock = Event()
        allow_check_in_commit = Event()
        deactivation_reached_impact = Event()
        original_active_enrollment = attendance_api._active_enrollment
        original_deactivation_impact = organization_api._room_deactivation_impact

        def gated_active_enrollment(*args, **kwargs):
            enrollment = original_active_enrollment(*args, **kwargs)
            check_in_holds_facility_lock.set()
            if not allow_check_in_commit.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing check-in commit")
            return enrollment

        def observed_deactivation_impact(*args, **kwargs):
            deactivation_reached_impact.set()
            return original_deactivation_impact(*args, **kwargs)

        monkeypatch.setattr(attendance_api, "_active_enrollment", gated_active_enrollment)
        monkeypatch.setattr(
            organization_api,
            "_room_deactivation_impact",
            observed_deactivation_impact,
        )
        responses: dict[str, object] = {}
        failures: dict[str, Exception] = {}
        check_in_thread = Thread(
            target=_check_in,
            args=(attendance_client, headers, scenario, responses, failures),
            name="room-race-check-in-first",
            daemon=True,
        )
        deactivation_thread = Thread(
            target=_deactivate_room,
            args=(organization_client, headers, scenario, responses, failures),
            name="room-race-deactivation-second",
            daemon=True,
        )

        try:
            check_in_thread.start()
            assert check_in_holds_facility_lock.wait(EVENT_TIMEOUT_SECONDS), (
                "Check-in never reached the facility-locked enrollment boundary"
            )
            deactivation_thread.start()
            assert not deactivation_reached_impact.wait(SERIALIZATION_WINDOW_SECONDS), (
                "Room deactivation evaluated impact before check-in committed"
            )
            assert deactivation_thread.is_alive(), (
                "Room deactivation did not wait for the check-in facility lock"
            )

            allow_check_in_commit.set()
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            deactivation_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not check_in_thread.is_alive(), "Check-in deadlocked or timed out"
            assert not deactivation_thread.is_alive(), "Room deactivation deadlocked or timed out"
        finally:
            allow_check_in_commit.set()
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            if deactivation_thread.ident is not None:
                deactivation_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"check_in", "deactivation"}, responses
        check_in_response = responses["check_in"]
        deactivation_response = responses["deactivation"]
        assert check_in_response.status_code == 200, check_in_response.text
        assert deactivation_response.status_code == 409, deactivation_response.text
        assert "open attendance intervals" in deactivation_response.json()["detail"]
        room = attendance_client.get(
            f"/api/v1/rooms/{scenario['room_id']}",
            headers=headers,
        )
        assert room.status_code == 200, room.text
        assert room.json()["is_active"] is True


def test_room_deactivation_lock_wins_and_check_in_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    attendance_application = _application(settings)
    organization_application = _application(settings)

    with (
        TestClient(attendance_application, raise_server_exceptions=False) as attendance_client,
        TestClient(organization_application, raise_server_exceptions=False) as organization_client,
    ):
        headers, scenario = _create_scenario(
            organization_client,
            end_enrollment=True,
        )
        deactivation_holds_facility_lock = Event()
        allow_deactivation_commit = Event()
        check_in_reached_enrollment = Event()
        original_deactivation_impact = organization_api._room_deactivation_impact
        original_active_enrollment = attendance_api._active_enrollment

        def gated_deactivation_impact(*args, **kwargs):
            impact = original_deactivation_impact(*args, **kwargs)
            deactivation_holds_facility_lock.set()
            if not allow_deactivation_commit.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing room deactivation commit")
            return impact

        def observed_active_enrollment(*args, **kwargs):
            check_in_reached_enrollment.set()
            return original_active_enrollment(*args, **kwargs)

        monkeypatch.setattr(
            organization_api,
            "_room_deactivation_impact",
            gated_deactivation_impact,
        )
        monkeypatch.setattr(attendance_api, "_active_enrollment", observed_active_enrollment)
        responses: dict[str, object] = {}
        failures: dict[str, Exception] = {}
        deactivation_thread = Thread(
            target=_deactivate_room,
            args=(organization_client, headers, scenario, responses, failures),
            name="room-race-deactivation-first",
            daemon=True,
        )
        check_in_thread = Thread(
            target=_check_in,
            args=(attendance_client, headers, scenario, responses, failures),
            name="room-race-check-in-second",
            daemon=True,
        )

        try:
            deactivation_thread.start()
            assert deactivation_holds_facility_lock.wait(EVENT_TIMEOUT_SECONDS), (
                "Room deactivation never reached the facility-locked impact boundary"
            )
            check_in_thread.start()
            assert not check_in_reached_enrollment.wait(SERIALIZATION_WINDOW_SECONDS), (
                "Check-in read enrollment before room deactivation committed"
            )
            assert check_in_thread.is_alive(), (
                "Check-in did not wait for the room deactivation facility lock"
            )

            allow_deactivation_commit.set()
            deactivation_thread.join(JOIN_TIMEOUT_SECONDS)
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not deactivation_thread.is_alive(), "Room deactivation deadlocked or timed out"
            assert not check_in_thread.is_alive(), "Check-in deadlocked or timed out"
        finally:
            allow_deactivation_commit.set()
            deactivation_thread.join(JOIN_TIMEOUT_SECONDS)
            if check_in_thread.ident is not None:
                check_in_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"check_in", "deactivation"}, responses
        check_in_response = responses["check_in"]
        deactivation_response = responses["deactivation"]
        assert deactivation_response.status_code == 200, deactivation_response.text
        assert deactivation_response.json()["is_active"] is False
        assert check_in_response.status_code == 409, check_in_response.text
        assert check_in_response.json()["detail"] == (
            "Child has no active enrollment at this facility on the service date"
        )

        impact = organization_client.get(
            f"/api/v1/rooms/{scenario['room_id']}/deactivation-impact",
            headers=headers,
        )
        assert impact.status_code == 200, impact.text
        assert impact.json()["open_attendance_intervals"] == 0
