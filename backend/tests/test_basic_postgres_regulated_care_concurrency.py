"""Opt-in PostgreSQL idempotency and version-race proof for Phase 2B."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from threading import Barrier, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

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
        jwt_secret="postgres-regulated-race-test-secret-at-least-32-bytes",
    )


def _local(service_date, hour: int, minute: int = 0) -> str:
    timezone = ZoneInfo("America/Edmonton")
    now = datetime.now(timezone)
    if service_date == now.date():
        day_start = datetime.combine(service_date, time.min, timezone)
        available_seconds = max((now - day_start).total_seconds() - 10, 1)
        scale = min(1.0, available_seconds / (6 * 60 * 60))
        logical_seconds = ((hour - 7) * 60 + minute) * 60
        return (day_start + timedelta(seconds=1 + logical_seconds * scale)).isoformat()
    return datetime.combine(service_date, time(hour, minute), timezone).isoformat()


def _setup(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    identifier = uuid4().hex
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"regulated-race-{identifier}@example.com",
            "password": "correct-password",
            "first_name": "Race",
            "last_name": "Owner",
            "organization_name": f"Regulated Race {identifier}",
        },
    )
    assert registration.status_code == 201, registration.text
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    service_date = datetime.now(ZoneInfo("America/Edmonton")).date()
    current_date = service_date + timedelta(days=1)
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Regulated Concurrency Centre",
            "status": "active",
            "licensed_capacity": 20,
            "timezone": "America/Edmonton",
        },
    )
    assert facility.status_code == 201, facility.text
    program = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "name": "Regulated Daycare",
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
            "name": "Regulated Room",
            "capacity": 20,
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
            "name": "Regulated Family",
            "primary_guardian": {
                "first_name": "Written",
                "last_name": "Guardian",
                "relationship": "Parent",
                "email": f"guardian-{identifier}@example.com",
                "cell_phone": "780-555-0101",
            },
        },
    )
    assert family.status_code == 201, family.text
    child = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family.json()["id"],
            "first_name": "Serial",
            "last_name": "Safety",
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
    checked_in = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "child_id": child.json()["id"],
            "facility_id": facility.json()["id"],
            "occurred_at": _local(service_date, 8),
        },
    )
    assert checked_in.status_code == 200, checked_in.text
    plan = client.post(
        "/api/v1/medications/plans",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "child_id": child.json()["id"],
            "medication_name": "Concurrency medication",
            "dosage": "5 mL",
            "route": "oral",
            "label_directions": "Follow the original pharmacy label.",
            "scheduled_times": ["09:00", "10:00"],
            "as_needed": False,
            "start_date": service_date.isoformat(),
            "end_date": current_date.isoformat(),
            "medication_kind": "non_emergency",
            "storage_method": "locked_inaccessible",
            "storage_instructions": "Locked and inaccessible.",
            "client_operation_id": str(uuid4()),
        },
    )
    assert plan.status_code == 201, plan.text
    plan_value = plan.json()
    authorized = client.post(
        f"/api/v1/medications/plans/{plan_value['id']}/authorization",
        headers=headers,
        json={
            "guardian_id": plan_value["eligible_guardians"][0]["id"],
            "signed_authorization_reference": f"paper-{identifier}",
            "authorization_signed_at": _local(service_date, 7),
            "valid_until": current_date.isoformat(),
            "expected_version": plan_value["version"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert authorized.status_code == 200, authorized.text
    activated = client.post(
        f"/api/v1/medications/plans/{plan_value['id']}/activate",
        headers=headers,
        json={
            "original_labelled_container_confirmed": True,
            "label_directions_confirmed": True,
            "expected_version": authorized.json()["version"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert activated.status_code == 200, activated.text
    return headers, {
        "facility_id": facility.json()["id"],
        "room_id": room.json()["id"],
        "attendance_day_id": checked_in.json()["id"],
        "plan_id": activated.json()["id"],
        "service_date": service_date.isoformat(),
        "nine": _local(service_date, 9),
        "ten": _local(service_date, 10),
        "eleven": _local(service_date, 11),
        "eleven_five": _local(service_date, 11, 5),
    }


def _concurrent_posts(
    first_client: TestClient,
    second_client: TestClient,
    path: str,
    headers: dict[str, str],
    first_payload: dict,
    second_payload: dict,
) -> list:
    barrier = Barrier(3)
    responses = []
    failures = []

    def run(client: TestClient, payload: dict) -> None:
        try:
            barrier.wait(timeout=5)
            responses.append(client.post(path, headers=headers, json=payload))
        except Exception as error:  # pragma: no cover - diagnostic path
            failures.append(error)

    threads = [
        Thread(target=run, args=(first_client, first_payload), daemon=True),
        Thread(target=run, args=(second_client, second_payload), daemon=True),
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent request deadlocked"
    assert not failures, failures
    assert len(responses) == 2
    return responses


def test_medication_slot_and_incident_versions_serialize_across_sessions() -> None:
    settings = _settings()
    first_application = create_app(settings)
    second_application = create_app(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        headers, scenario = _setup(first_client)
        same_operation = str(uuid4())
        nine_payload = {
            "medication_plan_id": scenario["plan_id"],
            "attendance_day_id": scenario["attendance_day_id"],
            "outcome": "administered",
            "scheduled_for": "09:00",
            "occurred_at": scenario["nine"],
            "amount": "5 mL",
            "client_operation_id": same_operation,
        }
        same_retry = _concurrent_posts(
            first_client,
            second_client,
            "/api/v1/medications/administrations",
            headers,
            nine_payload,
            dict(nine_payload),
        )
        assert [item.status_code for item in same_retry] == [201, 201]
        assert len({item.json()["id"] for item in same_retry}) == 1

        ten_payload = {
            **nine_payload,
            "scheduled_for": "10:00",
            "occurred_at": scenario["ten"],
            "client_operation_id": str(uuid4()),
        }
        competing_payload = {**ten_payload, "client_operation_id": str(uuid4())}
        competing_slot = _concurrent_posts(
            first_client,
            second_client,
            "/api/v1/medications/administrations",
            headers,
            ten_payload,
            competing_payload,
        )
        assert sorted(item.status_code for item in competing_slot) == [201, 409]

        incident = first_client.post(
            "/api/v1/incidents",
            headers=headers,
            json={
                "facility_id": scenario["facility_id"],
                "room_id": scenario["room_id"],
                "occurred_at": scenario["eleven"],
                "category": "other",
                "severity": "moderate",
                "summary": "General room incident for version serialization.",
                "immediate_actions": "Room was made safe and facts were documented.",
                "medical_attention": "none",
                "parent_notification_status": "not_applicable",
                "authorities_contacted": [],
                "staff_present": ["Race Owner"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert incident.status_code == 201, incident.text
        transition = {
            "expected_version": incident.json()["version"],
            "client_operation_id": str(uuid4()),
        }
        competing_transition = {**transition, "client_operation_id": str(uuid4())}
        transitions = _concurrent_posts(
            first_client,
            second_client,
            f"/api/v1/incidents/{incident.json()['id']}/submit-review",
            headers,
            transition,
            competing_transition,
        )
        assert sorted(item.status_code for item in transitions) == [200, 409]

        current = first_client.get(f"/api/v1/incidents/{incident.json()['id']}", headers=headers)
        assert current.status_code == 200, current.text
        assert current.json()["status"] == "under_review"
        history = first_client.get(
            f"/api/v1/incidents/{incident.json()['id']}/history", headers=headers
        )
        assert history.status_code == 200, history.text
        assert [item["event_type"] for item in history.json()] == [
            "drafted",
            "submitted_for_review",
        ]
