"""Opt-in PostgreSQL proof for workforce RLS, grants, and race serialization."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL

from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
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
        jwt_secret="postgres-staff-workforce-secret-at-least-32-bytes",
    )


def _application(settings: Settings):
    application = create_app(settings)

    @event.listens_for(application.state.database.engine, "connect")
    def configure_timeouts(dbapi_connection, _connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '12s'")

    return application


def _scenario(client: TestClient) -> tuple[dict, dict, dict]:
    identifier = uuid4().hex
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"workforce-pg-{identifier}@example.test",
            "password": "correct-password",
            "first_name": "Workforce",
            "last_name": "Owner",
            "organization_name": f"Workforce PG {identifier}",
        },
    )
    assert registration.status_code == 201, registration.text
    auth = registration.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "PostgreSQL Workforce Centre",
            "licensed_capacity": 20,
            "status": "active",
            "timezone": "America/Edmonton",
        },
    )
    assert facility.status_code == 201, facility.text
    return auth, headers, facility.json()


def _schedule(client, auth, headers, facility, start):
    response = client.post(
        "/api/v1/staff-schedules",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": auth["user"]["id"],
            "facility_id": facility["id"],
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _time_off(client, headers, facility, start):
    response = client.post(
        "/api/v1/staff/self/time-off",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=8)).isoformat(),
            "category": "personal",
            "note": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_runtime_role_workforce_rls_grants_and_tenant_filtering() -> None:
    settings = _settings()
    application = _application(settings)
    scenarios = []
    with TestClient(application) as client:
        for _ in range(2):
            auth, headers, facility = _scenario(client)
            availability = client.put(
                f"/api/v1/staff/self/availability/{facility['id']}",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_updated_at": None,
                    "windows": [],
                    "note": None,
                },
            )
            assert availability.status_code == 200, availability.text
            _time_off(
                client,
                headers,
                facility,
                datetime(2027, 2, 1, 16, 0, tzinfo=UTC),
            )
            template = client.post(
                "/api/v1/staff-workforce/templates",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "facility_id": facility["id"],
                    "room_id": None,
                    "name": "Opening",
                    "weekday": 0,
                    "start_local": "08:00",
                    "end_local": "16:00",
                    "notes": None,
                },
            )
            assert template.status_code == 201, template.text
            coverage = client.put(
                f"/api/v1/staff-workforce/coverage-targets/{facility['id']}",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_updated_at": None,
                    "windows": [
                        {
                            "weekday": 0,
                            "start_local": "08:00",
                            "end_local": "16:00",
                            "required_staff": 1,
                        }
                    ],
                },
            )
            assert coverage.status_code == 200, coverage.text
            scenarios.append(auth)

    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="caresync_basic_app",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    mutable_tables = (
        "staff_availability_profiles",
        "staff_time_off_requests",
        "staff_shift_templates",
        "staff_coverage_target_profiles",
    )
    with engine.connect() as connection:
        for table_name in (*mutable_tables, "staff_workforce_events"):
            assert (
                connection.execute(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE oid=CAST(:table_name AS regclass)"
                    ),
                    {"table_name": table_name},
                ).scalar_one()
                is True
            )
            assert set(
                connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname=current_schema() AND tablename=:table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
            ) == {f"{table_name}_tenant"}
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = connection.execute(
                    text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                    {"table": table_name, "privilege": privilege},
                ).scalar_one()
                expected = {"SELECT", "INSERT"}
                if table_name in mutable_tables:
                    expected.add("UPDATE")
                assert granted is (privilege in expected)

        for auth in scenarios:
            connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": auth["user"]["id"]},
            )
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :value, true)"),
                {"value": auth["user"]["organization_id"]},
            )
            for table_name in mutable_tables:
                assert (
                    connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one() == 1
                )
            assert (
                connection.execute(text("SELECT count(*) FROM staff_workforce_events")).scalar_one()
                == 4
            )
            connection.rollback()
    engine.dispose()


def test_publish_and_leave_approval_are_serialized() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        auth, headers, facility = _scenario(first_client)
        start = datetime(2027, 3, 1, 16, 0, tzinfo=UTC)
        schedule = _schedule(first_client, auth, headers, facility, start)
        leave = _time_off(first_client, headers, facility, start)
        barrier = Barrier(3)
        responses = []
        failures = []

        def publish() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    first_client.post(
                        f"/api/v1/staff-schedules/{schedule['id']}/publish",
                        headers=headers,
                        json={"client_operation_id": str(uuid4())},
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        def approve() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    second_client.post(
                        f"/api/v1/staff-workforce/time-off/{leave['id']}/approve",
                        headers=headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_updated_at": leave["updated_at"],
                            "note": None,
                        },
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        threads = [Thread(target=publish, daemon=True), Thread(target=approve, daemon=True)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=12)
            assert not thread.is_alive()
        assert not failures
        assert sorted(response.status_code for response in responses) == [200, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json()["detail"]["code"] in {
            "approved_time_off_conflict",
            "published_schedule_conflict",
        }


def test_availability_replace_and_publish_share_staff_lane() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        auth, headers, facility = _scenario(first_client)
        availability = first_client.put(
            f"/api/v1/staff/self/availability/{facility['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": None,
                "windows": [{"weekday": 0, "start_local": "08:00", "end_local": "18:00"}],
                "note": None,
            },
        )
        assert availability.status_code == 200, availability.text
        schedule = _schedule(
            first_client,
            auth,
            headers,
            facility,
            datetime(2027, 3, 8, 16, 0, tzinfo=UTC),
        )
        barrier = Barrier(3)
        responses = []

        def replace() -> None:
            barrier.wait(timeout=5)
            responses.append(
                first_client.put(
                    f"/api/v1/staff/self/availability/{facility['id']}",
                    headers=headers,
                    json={
                        "client_operation_id": str(uuid4()),
                        "expected_updated_at": availability.json()["profile"]["updated_at"],
                        "windows": [],
                        "note": None,
                    },
                )
            )

        def publish() -> None:
            barrier.wait(timeout=5)
            responses.append(
                second_client.post(
                    f"/api/v1/staff-schedules/{schedule['id']}/publish",
                    headers=headers,
                    json={"client_operation_id": str(uuid4())},
                )
            )

        threads = [Thread(target=replace, daemon=True), Thread(target=publish, daemon=True)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=12)
            assert not thread.is_alive()
        assert sorted(response.status_code for response in responses) in ([200, 200], [200, 409])
        if any(response.status_code == 409 for response in responses):
            conflict = next(response for response in responses if response.status_code == 409)
            assert conflict.json()["detail"]["code"] == "availability_override_required"
