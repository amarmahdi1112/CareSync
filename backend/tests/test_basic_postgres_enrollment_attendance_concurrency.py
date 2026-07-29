"""Opt-in PostgreSQL proof for enrollment placement/check-in serialization.

The test is skipped unless ``BASIC_POSTGRES_TEST_PORT`` identifies an explicitly
disposable, migrated PostgreSQL database with the runtime grants applied. Two
independent application pools ensure competing requests use different database
sessions and exercise real row locks.
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
from app.api.basic import childcare as childcare_api
from app.core.config import Settings
from app.main import create_app
from tests.postgres_staff_shift_fixture import clock_in_assigned_educator

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
if TEST_PORT and int(TEST_PORT) in {5432, 5433, 5434}:
    raise RuntimeError(
        "BASIC_POSTGRES_TEST_PORT must never target the existing 5432/5433/5434 databases"
    )
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)

CHECK_IN_THREAD = "enrollment-race-check-in"
SECOND_ENROLLMENT_THREAD = "enrollment-race-second-enrollment"
MOVE_THREAD = "enrollment-race-move"
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
        jwt_secret="postgres-enrollment-race-test-secret-at-least-32-bytes",
    )


def _test_application(settings: Settings):
    application = create_app(settings)

    @event.listens_for(application.state.database.engine, "connect")
    def configure_test_timeouts(dbapi_connection, _connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '3s'")
            cursor.execute("SET statement_timeout = '10s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '10s'")

    return application


def _register(client: TestClient, identifier: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"enrollment-race-{identifier}@example.com",
            "password": "correct-password",
            "first_name": "Placement",
            "last_name": "Owner",
            "organization_name": f"Enrollment Race {identifier}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_scenario(
    client: TestClient, headers: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    timezone = ZoneInfo("America/Edmonton")
    service_date = datetime.now(timezone).date()
    occurred_at = datetime.now(timezone) - timedelta(seconds=1)

    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Placement Concurrency Centre",
            "timezone": timezone.key,
            "licensed_capacity": 40,
            "status": "active",
        },
    )
    assert facility.status_code == 201, facility.text
    facility_id = facility.json()["id"]

    program = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility_id,
            "name": "Placement Daycare",
            "program_type": "daycare",
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program.status_code == 201, program.text
    program_id = program.json()["id"]

    rooms: list[str] = []
    for name in ("Original Room", "New Room"):
        room = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility_id,
                "program_id": program_id,
                "name": name,
                "capacity": 20,
                "age_group": "Toddler",
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert room.status_code == 201, room.text
        rooms.append(room.json()["id"])

    family = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": "Placement Serialization Family",
        },
    )
    assert family.status_code == 201, family.text

    child = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family.json()["id"],
            "first_name": "Row",
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
            "facility_id": facility_id,
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
            "room_id": rooms[0],
            "effective_date": service_date.isoformat(),
        },
    )
    assert placement.status_code == 200, placement.text

    staff_headers = clock_in_assigned_educator(
        client,
        headers,
        facility_id=facility_id,
        room_id=rooms[0],
    )
    return (
        {
            "facility_id": facility_id,
            "program_id": program_id,
            "original_room_id": rooms[0],
            "new_room_id": rooms[1],
            "child_id": child.json()["id"],
            "enrollment_id": enrollment.json()["id"],
            "enrollment_version": str(placement.json()["version"]),
            "occurred_at": occurred_at.isoformat(),
            "service_date": service_date.isoformat(),
        },
        staff_headers,
    )


def _add_second_facility(
    client: TestClient,
    headers: dict[str, str],
) -> str:
    timezone = ZoneInfo("America/Edmonton")
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Second Placement Centre",
            "timezone": timezone.key,
            "licensed_capacity": 20,
            "status": "active",
        },
    )
    assert facility.status_code == 201, facility.text
    return facility.json()["id"]


def _run_requests(
    *,
    attendance_client: TestClient,
    childcare_client: TestClient,
    attendance_headers: dict[str, str],
    childcare_headers: dict[str, str],
    scenario: dict[str, str],
    start_check_in_first: bool,
) -> tuple[dict[str, object], dict[str, Exception], Thread, Thread]:
    responses: dict[str, object] = {}
    failures: dict[str, Exception] = {}

    def check_in() -> None:
        try:
            responses["check_in"] = attendance_client.post(
                "/api/v1/attendance/check-in",
                headers=attendance_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "child_id": scenario["child_id"],
                    "facility_id": scenario["facility_id"],
                    "occurred_at": scenario["occurred_at"],
                },
            )
        except Exception as error:  # pragma: no cover - diagnostic path
            failures["check_in"] = error

    def move() -> None:
        try:
            responses["move"] = childcare_client.patch(
                f"/api/v1/enrollments/{scenario['enrollment_id']}",
                headers=childcare_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": int(scenario["enrollment_version"]),
                    "status": "paused",
                },
            )
        except Exception as error:  # pragma: no cover - diagnostic path
            failures["move"] = error

    check_in_thread = Thread(target=check_in, name=CHECK_IN_THREAD, daemon=True)
    move_thread = Thread(target=move, name=MOVE_THREAD, daemon=True)
    if start_check_in_first:
        check_in_thread.start()
    else:
        move_thread.start()
    return responses, failures, check_in_thread, move_thread


def test_check_in_lock_wins_and_concurrent_enrollment_pause_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    attendance_application = _test_application(settings)
    childcare_application = _test_application(settings)

    with (
        TestClient(attendance_application, raise_server_exceptions=False) as attendance_client,
        TestClient(childcare_application, raise_server_exceptions=False) as childcare_client,
    ):
        auth = _register(attendance_client, uuid4().hex)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        scenario, attendance_headers = _create_scenario(attendance_client, headers)

        enrollment_locked = Event()
        allow_check_in = Event()
        original_active_enrollment = attendance_api._active_enrollment

        def gated_active_enrollment(*args, **kwargs):
            enrollment = original_active_enrollment(*args, **kwargs)
            enrollment_locked.set()
            if not allow_check_in.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing the check-in enrollment lock")
            return enrollment

        monkeypatch.setattr(attendance_api, "_active_enrollment", gated_active_enrollment)
        responses, failures, check_in_thread, move_thread = _run_requests(
            attendance_client=attendance_client,
            childcare_client=childcare_client,
            attendance_headers=attendance_headers,
            childcare_headers=headers,
            scenario=scenario,
            start_check_in_first=True,
        )

        try:
            assert enrollment_locked.wait(EVENT_TIMEOUT_SECONDS), (
                "Check-in never reached the locked enrollment boundary"
            )
            move_thread.start()
            move_thread.join(SERIALIZATION_WINDOW_SECONDS)
            assert move_thread.is_alive(), "Enrollment pause did not wait for the check-in lock"

            allow_check_in.set()
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            move_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not check_in_thread.is_alive(), "Check-in deadlocked or timed out"
            assert not move_thread.is_alive(), "Enrollment pause deadlocked or timed out"
        finally:
            allow_check_in.set()
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            if move_thread.ident is not None:
                move_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"check_in", "move"}, responses
        check_in_response = responses["check_in"]
        move_response = responses["move"]
        assert check_in_response.status_code == 200, check_in_response.text
        assert move_response.status_code == 409, move_response.text
        assert check_in_response.json()["room_id"] == scenario["original_room_id"]


def test_enrollment_pause_lock_wins_and_check_in_sees_committed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    attendance_application = _test_application(settings)
    childcare_application = _test_application(settings)

    with (
        TestClient(attendance_application, raise_server_exceptions=False) as attendance_client,
        TestClient(childcare_application, raise_server_exceptions=False) as childcare_client,
    ):
        auth = _register(attendance_client, uuid4().hex)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        scenario, attendance_headers = _create_scenario(attendance_client, headers)

        move_ready_to_commit = Event()
        allow_move_commit = Event()
        check_in_read_enrollment = Event()
        original_commit_in_context = childcare_api.commit_in_context
        original_active_enrollment = attendance_api._active_enrollment

        def gated_move_commit(*args, **kwargs):
            move_ready_to_commit.set()
            if not allow_move_commit.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing the enrollment move commit")
            return original_commit_in_context(*args, **kwargs)

        def observed_active_enrollment(*args, **kwargs):
            enrollment = original_active_enrollment(*args, **kwargs)
            check_in_read_enrollment.set()
            return enrollment

        monkeypatch.setattr(childcare_api, "commit_in_context", gated_move_commit)
        monkeypatch.setattr(attendance_api, "_active_enrollment", observed_active_enrollment)
        responses, failures, check_in_thread, move_thread = _run_requests(
            attendance_client=attendance_client,
            childcare_client=childcare_client,
            attendance_headers=attendance_headers,
            childcare_headers=headers,
            scenario=scenario,
            start_check_in_first=False,
        )

        try:
            assert move_ready_to_commit.wait(EVENT_TIMEOUT_SECONDS), (
                "Enrollment pause never reached its commit boundary"
            )
            check_in_thread.start()
            assert not check_in_read_enrollment.wait(SERIALIZATION_WINDOW_SECONDS), (
                "Check-in read enrollment before the pause committed"
            )
            assert check_in_thread.is_alive(), "Check-in did not wait for the enrollment pause lock"

            allow_move_commit.set()
            move_thread.join(JOIN_TIMEOUT_SECONDS)
            check_in_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not move_thread.is_alive(), "Enrollment pause deadlocked or timed out"
            assert not check_in_thread.is_alive(), "Check-in deadlocked or timed out"
        finally:
            allow_move_commit.set()
            move_thread.join(JOIN_TIMEOUT_SECONDS)
            if check_in_thread.ident is not None:
                check_in_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"check_in", "move"}, responses
        check_in_response = responses["check_in"]
        move_response = responses["move"]
        assert move_response.status_code == 200, move_response.text
        assert move_response.json()["status"] == "paused"
        assert check_in_response.status_code == 409, check_in_response.text


def test_check_in_serializes_competing_second_facility_enrollment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    first_application = _test_application(settings)
    second_application = _test_application(settings)

    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        auth = _register(first_client, uuid4().hex)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        scenario, attendance_headers = _create_scenario(first_client, headers)
        second_facility_id = _add_second_facility(first_client, headers)

        first_has_child_lock = Event()
        allow_first_check_in = Event()
        second_checked_open_enrollment = Event()
        original_active_enrollment = attendance_api._active_enrollment
        original_create_enrollment = childcare_api._create_enrollment

        def gated_active_enrollment(*args, **kwargs):
            enrollment = original_active_enrollment(*args, **kwargs)
            first_has_child_lock.set()
            if not allow_first_check_in.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing the first child check-in lock")
            return enrollment

        def observed_create_enrollment(*args, **kwargs):
            try:
                return original_create_enrollment(*args, **kwargs)
            finally:
                # This boundary is reached only after _create_enrollment acquires the
                # same Child row lock and evaluates the one-open-enrollment rule.
                second_checked_open_enrollment.set()

        monkeypatch.setattr(attendance_api, "_active_enrollment", gated_active_enrollment)
        monkeypatch.setattr(childcare_api, "_create_enrollment", observed_create_enrollment)
        responses: dict[str, object] = {}
        failures: dict[str, Exception] = {}

        def check_in() -> None:
            try:
                responses["check_in"] = first_client.post(
                    "/api/v1/attendance/check-in",
                    headers=attendance_headers,
                    json={
                        "client_operation_id": str(uuid4()),
                        "child_id": scenario["child_id"],
                        "facility_id": scenario["facility_id"],
                        "occurred_at": scenario["occurred_at"],
                    },
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures["check_in"] = error

        def create_second_enrollment() -> None:
            try:
                responses["second_enrollment"] = second_client.post(
                    f"/api/v1/children/{scenario['child_id']}/enrollments",
                    headers=headers,
                    json={
                        "client_operation_id": str(uuid4()),
                        "facility_id": second_facility_id,
                        "start_date": scenario["service_date"],
                    },
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures["second_enrollment"] = error

        first_thread = Thread(
            target=check_in,
            name=CHECK_IN_THREAD,
            daemon=True,
        )
        second_thread = Thread(
            target=create_second_enrollment,
            name=SECOND_ENROLLMENT_THREAD,
            daemon=True,
        )

        try:
            first_thread.start()
            assert first_has_child_lock.wait(EVENT_TIMEOUT_SECONDS), (
                "First check-in never reached the locked child/enrollment boundary"
            )
            second_thread.start()
            assert not second_checked_open_enrollment.wait(SERIALIZATION_WINDOW_SECONDS), (
                "Second-facility enrollment passed the same-child lock before check-in committed"
            )
            assert second_thread.is_alive(), "Second enrollment did not wait for the child lock"

            allow_first_check_in.set()
            first_thread.join(JOIN_TIMEOUT_SECONDS)
            second_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not first_thread.is_alive(), "First check-in deadlocked or timed out"
            assert not second_thread.is_alive(), "Second enrollment deadlocked or timed out"
        finally:
            allow_first_check_in.set()
            first_thread.join(JOIN_TIMEOUT_SECONDS)
            if second_thread.ident is not None:
                second_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"check_in", "second_enrollment"}, responses
        check_in_response = responses["check_in"]
        second_enrollment_response = responses["second_enrollment"]
        assert check_in_response.status_code == 200, check_in_response.text
        assert second_enrollment_response.status_code == 409, second_enrollment_response.text
        assert second_enrollment_response.json()["detail"]["code"] == "open_enrollment_exists"

        attendance = first_client.get(
            "/api/v1/attendance",
            headers=headers,
            params={
                "date": scenario["service_date"],
                "facility_id": scenario["facility_id"],
            },
        )
        assert attendance.status_code == 200, attendance.text
        assert (
            sum(
                interval["checked_out_at"] is None
                for day in attendance.json()
                for interval in day["intervals"]
            )
            == 1
        )
