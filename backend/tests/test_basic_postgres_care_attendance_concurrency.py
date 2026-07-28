"""Opt-in PostgreSQL proof for daily-care/attendance write serialization.

The test is skipped unless BASIC_POSTGRES_TEST_PORT points to an explicitly
disposable, already migrated database with the runtime grants applied. It uses
two independent application pools so the competing HTTP requests necessarily
run in separate PostgreSQL sessions.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from threading import Event, Thread
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.basic import attendance as attendance_api
from app.api.basic import care as care_api
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

CARE_THREAD = "care-correction-request"
ATTENDANCE_THREAD = "attendance-correction-request"
EVENT_TIMEOUT_SECONDS = 5.0
SERIALIZATION_WINDOW_SECONDS = 2.0
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
        jwt_secret="postgres-care-race-test-secret-at-least-32-bytes",
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
            "email": f"care-race-{identifier}@example.com",
            "password": "correct-password",
            "first_name": "Race",
            "last_name": "Owner",
            "organization_name": f"Care Race {identifier}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_sleep_scenario(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    timezone = ZoneInfo("America/Edmonton")
    now = datetime.now(timezone)
    service_date = now.date()
    day_start = datetime.combine(service_date, time.min, tzinfo=timezone)
    logical_span_seconds = 6 * 60 * 60
    available_seconds = max((now - day_start).total_seconds() - 10, 1)
    time_scale = min(1.0, available_seconds / logical_span_seconds)

    def local_time(hour: int) -> str:
        logical_seconds = (hour - 7) * 60 * 60
        return (day_start + timedelta(seconds=1 + logical_seconds * time_scale)).isoformat()

    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Concurrency Centre",
            "timezone": timezone.key,
            "licensed_capacity": 20,
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
            "name": "Concurrency Daycare",
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
            "facility_id": facility_id,
            "program_id": program.json()["id"],
            "name": "Serialization Room",
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
            "name": "Serialization Family",
        },
    )
    assert family.status_code == 201, family.text

    child = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family.json()["id"],
            "first_name": "Lock",
            "last_name": "Order",
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
            "room_id": room.json()["id"],
            "effective_date": service_date.isoformat(),
        },
    )
    assert placement.status_code == 200, placement.text

    checked_in = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "child_id": child.json()["id"],
            "facility_id": facility_id,
            "occurred_at": local_time(8),
        },
    )
    assert checked_in.status_code == 200, checked_in.text
    attendance_day = checked_in.json()

    sleep = client.post(
        "/api/v1/care/records",
        headers=headers,
        json={
            "attendance_day_id": attendance_day["id"],
            "care_type": "sleep",
            "occurred_at": local_time(9),
            "payload": {},
            "client_operation_id": str(uuid4()),
        },
    )
    assert sleep.status_code == 201, sleep.text

    finished = client.post(
        f"/api/v1/care/records/{sleep.json()['id']}/finish-sleep",
        headers=headers,
        json={
            "ended_at": local_time(10),
            "expected_version": sleep.json()["version"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert finished.status_code == 200, finished.text

    return {
        "attendance_day_id": attendance_day["id"],
        "attendance_interval_id": attendance_day["intervals"][0]["id"],
        "care_record_id": finished.json()["id"],
        "care_record_version": str(finished.json()["version"]),
        "facility_id": facility_id,
        "room_id": room.json()["id"],
        "service_date": service_date.isoformat(),
        "checked_in_at": local_time(8),
        "care_started_at": local_time(9),
        "care_corrected_end": local_time(12),
        "attendance_corrected_end": local_time(11),
    }


def test_concurrent_exact_create_retries_return_one_canonical_record() -> None:
    settings = _settings()
    first_application = _test_application(settings)
    second_application = _test_application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        auth = _register(first_client, uuid4().hex)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        scenario = _create_sleep_scenario(first_client, headers)
        operation_id = str(uuid4())
        payload = {
            "attendance_day_id": scenario["attendance_day_id"],
            "care_type": "mood",
            "occurred_at": scenario["care_started_at"],
            "payload": {"value": "calm"},
            "note": "Concurrent response-loss recovery",
            "client_operation_id": operation_id,
        }
        release = Event()
        responses = []

        def submit(client: TestClient) -> None:
            assert release.wait(EVENT_TIMEOUT_SECONDS)
            responses.append(client.post("/api/v1/care/records", headers=headers, json=payload))

        threads = [
            Thread(target=submit, args=(first_client,)),
            Thread(target=submit, args=(second_client,)),
        ]
        for thread in threads:
            thread.start()
        release.set()
        for thread in threads:
            thread.join(JOIN_TIMEOUT_SECONDS)
            assert not thread.is_alive()

        assert [response.status_code for response in responses] == [201, 201]
        assert len({response.json()["id"] for response in responses}) == 1
        receipts = {response.json()["recorded_client_operation_id"] for response in responses}
        assert receipts == {operation_id}


def test_sleep_correction_and_interval_correction_serialize_without_stranding_care(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    care_application = _test_application(settings)
    attendance_application = _test_application(settings)

    with (
        TestClient(care_application, raise_server_exceptions=False) as care_client,
        TestClient(attendance_application, raise_server_exceptions=False) as attendance_client,
    ):
        auth = _register(care_client, uuid4().hex)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        organization_id = auth["user"]["organization_id"]
        scenario = _create_sleep_scenario(care_client, headers)
        attendance_day_id = UUID(scenario["attendance_day_id"])

        care_reached_attendance = Event()
        allow_care_to_validate = Event()
        attendance_validated_snapshot = Event()
        allow_attendance_to_commit = Event()

        original_attendance_day = care_api._attendance_day
        original_care_guard = attendance_api._ensure_care_survives_interval_correction

        def gated_attendance_day(*args, **kwargs):
            day = original_attendance_day(*args, **kwargs)
            if day.id == attendance_day_id:
                care_reached_attendance.set()
                if not allow_care_to_validate.wait(EVENT_TIMEOUT_SECONDS):
                    raise RuntimeError("Timed out releasing the care correction test gate")
            return day

        def gated_care_guard(*args, **kwargs):
            result = original_care_guard(*args, **kwargs)
            attendance_validated_snapshot.set()
            if not allow_attendance_to_commit.wait(EVENT_TIMEOUT_SECONDS):
                raise RuntimeError("Timed out releasing the attendance correction test gate")
            return result

        monkeypatch.setattr(care_api, "_attendance_day", gated_attendance_day)
        monkeypatch.setattr(
            attendance_api,
            "_ensure_care_survives_interval_correction",
            gated_care_guard,
        )

        responses = {}
        failures: dict[str, Exception] = {}

        def correct_care() -> None:
            try:
                responses["care"] = care_client.put(
                    f"/api/v1/care/records/{scenario['care_record_id']}/correction",
                    headers=headers,
                    json={
                        "occurred_at": scenario["care_started_at"],
                        "ended_at": scenario["care_corrected_end"],
                        "payload": {},
                        "note": None,
                        "reason": "Correct observed wake time",
                        "expected_version": int(scenario["care_record_version"]),
                        "client_operation_id": str(uuid4()),
                    },
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures["care"] = error

        def correct_attendance() -> None:
            try:
                responses["attendance"] = attendance_client.put(
                    f"/api/v1/attendance/{scenario['attendance_day_id']}/correction",
                    headers=headers,
                    json={
                        "interval_id": scenario["attendance_interval_id"],
                        "checked_in_at": scenario["checked_in_at"],
                        "checked_out_at": scenario["attendance_corrected_end"],
                        "reason": "Correct observed checkout time",
                    },
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures["attendance"] = error

        care_thread = Thread(target=correct_care, name=CARE_THREAD, daemon=True)
        attendance_thread = Thread(
            target=correct_attendance,
            name=ATTENDANCE_THREAD,
            daemon=True,
        )
        attendance_started = False

        try:
            care_thread.start()
            assert care_reached_attendance.wait(EVENT_TIMEOUT_SECONDS), (
                "Care correction never reached its attendance lock/validation boundary"
            )
            attendance_thread.start()
            attendance_started = True

            # With the historical record-before-day order, attendance validates
            # the stale care projection here. With the fixed day-first order it
            # blocks until the care correction commits and is then rejected.
            attendance_saw_stale_projection = attendance_validated_snapshot.wait(
                SERIALIZATION_WINDOW_SECONDS
            )
            allow_care_to_validate.set()
            care_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not care_thread.is_alive(), "Care correction deadlocked or timed out"

            allow_attendance_to_commit.set()
            attendance_thread.join(JOIN_TIMEOUT_SECONDS)
            assert not attendance_thread.is_alive(), "Attendance correction deadlocked or timed out"
        finally:
            allow_care_to_validate.set()
            allow_attendance_to_commit.set()
            care_thread.join(JOIN_TIMEOUT_SECONDS)
            if attendance_started:
                attendance_thread.join(JOIN_TIMEOUT_SECONDS)

        assert not failures, failures
        assert set(responses) == {"care", "attendance"}, responses
        status_details = {
            name: (response.status_code, response.text) for name, response in responses.items()
        }
        assert sorted(response.status_code for response in responses.values()) == [200, 409], (
            status_details,
            f"attendance_saw_stale_projection={attendance_saw_stale_projection}",
        )

        attendance = care_client.get(
            f"/api/v1/attendance/{scenario['attendance_day_id']}",
            headers=headers,
        )
        assert attendance.status_code == 200, attendance.text
        daybook = care_client.get(
            f"/api/v1/care/rooms/{scenario['room_id']}/day",
            headers=headers,
            params={"date": scenario["service_date"]},
        )
        assert daybook.status_code == 200, daybook.text
        assert daybook.json()["organization_id"] == organization_id

        interval = attendance.json()["intervals"][0]
        records = [
            record
            for child in daybook.json()["children"]
            for record in child["records"]
            if record["id"] == scenario["care_record_id"]
        ]
        assert len(records) == 1, daybook.text
        record = records[0]
        care_start = datetime.fromisoformat(record["occurred_at"])
        care_end = datetime.fromisoformat(record["ended_at"])
        attendance_start = datetime.fromisoformat(interval["checked_in_at"])
        attendance_end = (
            datetime.fromisoformat(interval["checked_out_at"])
            if interval["checked_out_at"]
            else None
        )
        assert care_start >= attendance_start
        assert attendance_end is None or care_end <= attendance_end
