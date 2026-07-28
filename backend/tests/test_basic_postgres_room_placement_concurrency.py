"""Opt-in PostgreSQL proof that the last room place cannot be double-approved."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from threading import Barrier, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

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
        jwt_secret="postgres-placement-race-secret-at-least-32-bytes",
    )


def _application(settings: Settings):
    application = create_app(settings)

    @event.listens_for(application.state.database.engine, "connect")
    def configure_timeouts(dbapi_connection, _connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '12s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '12s'")

    return application


def _create_scenario(client: TestClient) -> tuple[dict[str, str], list[dict]]:
    identifier = uuid4().hex
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"placement-race-{identifier}@example.com",
            "password": "correct-password",
            "first_name": "Placement",
            "last_name": "Owner",
            "organization_name": f"Placement Race {identifier}",
        },
    )
    assert auth.status_code == 201, auth.text
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    timezone = ZoneInfo("America/Edmonton")
    today = datetime.now(timezone).date()
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Last Place Centre",
            "timezone": timezone.key,
            "licensed_capacity": 3,
            "status": "active",
        },
    ).json()
    program_response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "name": "Daycare",
            "program_type": "daycare",
            "capacity": 3,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program_response.status_code == 201, program_response.text
    program = program_response.json()
    rooms = []
    for name in ("Target", "Holding One", "Holding Two"):
        response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": name,
                "capacity": 1,
                "age_group": "Infant",
                "minimum_age_months": 0,
                "maximum_age_months": 35,
            },
        )
        assert response.status_code == 201, response.text
        rooms.append(response.json())

    enrollments = []
    for index, _holding_room in enumerate(rooms[1:], start=1):
        family = client.post(
            "/api/v1/families",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "name": f"Race Family {index}",
            },
        ).json()
        child = client.post(
            "/api/v1/children",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": f"Race{index}",
                "last_name": "Child",
                "date_of_birth": (today - timedelta(days=500)).isoformat(),
            },
        )
        assert child.status_code == 201, child.text
        enrollment = client.post(
            f"/api/v1/children/{child.json()['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": today.isoformat(),
            },
        )
        assert enrollment.status_code == 201, enrollment.text
        enrollments.append(enrollment.json())
    reviews = client.get(
        "/api/v1/room-placement-reviews",
        headers=headers,
        params={"facility_id": facility["id"]},
    )
    assert reviews.status_code == 200, reviews.text
    by_enrollment = {item["enrollment_id"]: item for item in reviews.json()}
    return {
        "token": auth.json()["access_token"],
        "facility_id": facility["id"],
        "target_room_id": rooms[0]["id"],
    }, [by_enrollment[item["id"]] for item in enrollments]


def test_two_sessions_competing_for_last_room_place_yield_one_conflict() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        scenario, reviews = _create_scenario(first_client)
        headers = {"Authorization": f"Bearer {scenario['token']}"}
        barrier = Barrier(3)
        responses: list[object] = []
        failures: list[Exception] = []

        def approve(client: TestClient, review: dict) -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    client.post(
                        f"/api/v1/enrollments/{review['enrollment_id']}/placement-approval",
                        headers=headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_version": review["enrollment_version"],
                            "room_id": scenario["target_room_id"],
                            "effective_date": review["effective_date"],
                        },
                    )
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures.append(error)

        threads = [
            Thread(target=approve, args=(first_client, reviews[0]), daemon=True),
            Thread(target=approve, args=(second_client, reviews[1]), daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=12)
            assert not thread.is_alive()

        assert not failures
        assert sorted(response.status_code for response in responses) == [200, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert "available place" in conflict.json()["detail"]
