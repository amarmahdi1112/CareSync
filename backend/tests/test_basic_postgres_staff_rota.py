"""Opt-in PostgreSQL proof for rota overlap serialization, RLS, and grants."""

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
        jwt_secret="postgres-staff-rota-secret-at-least-32-bytes",
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
            "email": f"rota-pg-{identifier}@example.test",
            "password": "correct-password",
            "first_name": "Rota",
            "last_name": "Owner",
            "organization_name": f"Rota PG {identifier}",
        },
    )
    assert registration.status_code == 201, registration.text
    auth = registration.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": "PostgreSQL Rota Centre", "licensed_capacity": 20, "status": "active"},
    )
    assert facility.status_code == 201, facility.text
    return auth, headers, facility.json()


def _create_payload(auth: dict, facility: dict, operation_id=None) -> dict:
    start = datetime.now(UTC) + timedelta(days=10)
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "staff_user_id": auth["user"]["id"],
        "facility_id": facility["id"],
        "scheduled_start_at": start.isoformat(),
        "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
    }


def test_runtime_role_staff_rota_rls_grants_and_tenant_filtering() -> None:
    settings = _settings()
    application = _application(settings)
    with TestClient(application) as client:
        first, first_headers, first_facility = _scenario(client)
        second, second_headers, second_facility = _scenario(client)
        for auth, headers, facility in (
            (first, first_headers, first_facility),
            (second, second_headers, second_facility),
        ):
            response = client.post(
                "/api/v1/staff-schedules",
                headers=headers,
                json=_create_payload(auth, facility),
            )
            assert response.status_code == 201, response.text

    runtime_url = URL.create(
        "postgresql+psycopg",
        username="caresync_basic_app",
        host=settings.database_host,
        port=settings.database_port,
        database=settings.database_name,
    )
    engine = create_engine(runtime_url)
    with engine.connect() as connection:
        for table_name, expected_privileges in (
            ("staff_scheduled_shifts", {"SELECT", "INSERT", "UPDATE"}),
            ("staff_scheduled_shift_events", {"SELECT", "INSERT"}),
        ):
            assert connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE oid=CAST(:table_name AS regclass)"
                ),
                {"table_name": table_name},
            ).scalar_one() is True
            policies = set(
                connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname=current_schema() AND tablename=:table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
            )
            assert policies == {f"{table_name}_tenant"}
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = connection.execute(
                    text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                    {"table": table_name, "privilege": privilege},
                ).scalar_one()
                assert granted is (privilege in expected_privileges)

        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": first["user"]["id"]},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": first["user"]["organization_id"]},
        )
        assert (
            connection.execute(text("SELECT count(*) FROM staff_scheduled_shifts")).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM staff_scheduled_shift_events")
            ).scalar_one()
            == 1
        )
        assert "staff_schedule.created" in set(
            connection.execute(
                text(
                    "SELECT event_type FROM realtime_events "
                    "WHERE entity_type='staff_schedule'"
                )
            ).scalars()
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": second["user"]["id"]},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": second["user"]["organization_id"]},
        )
        assert (
            connection.execute(text("SELECT count(*) FROM staff_scheduled_shifts")).scalar_one()
            == 1
        )
        connection.rollback()
    engine.dispose()


def test_concurrent_overlapping_creates_are_serialized_per_staff_lane() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        auth, headers, facility = _scenario(first_client)
        first_payload = _create_payload(auth, facility)
        second_payload = {**first_payload, "client_operation_id": str(uuid4())}
        barrier = Barrier(3)
        responses = []
        failures = []

        def submit(client: TestClient, payload: dict) -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    client.post("/api/v1/staff-schedules", headers=headers, json=payload)
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures.append(error)

        threads = [
            Thread(target=submit, args=(first_client, first_payload), daemon=True),
            Thread(target=submit, args=(second_client, second_payload), daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=12)
            assert not thread.is_alive()

        assert not failures
        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json()["detail"]["code"] == "overlapping_schedule"
