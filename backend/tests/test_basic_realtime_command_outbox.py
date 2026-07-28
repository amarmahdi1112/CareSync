"""Representative command-to-realtime transactional outbox acceptance coverage."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from alembic import command
from app.basic.models import RealtimeEvent
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct-password-123"


def _client(tmp_path, monkeypatch) -> tuple[TestClient, object]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "0028_childcare_command_spine")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="realtime-command-outbox-test-secret-32-bytes",
    )
    application = create_app(settings)
    return TestClient(application), application


def _post(client: TestClient, path: str, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def test_representative_commands_reach_the_transactional_realtime_outbox(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"realtime-spine-{uuid4()}@example.test",
                "password": PASSWORD,
                "first_name": "Realtime",
                "last_name": "Owner",
                "organization_name": "Realtime Child Care",
            },
        )
        assert registered.status_code == 201, registered.text
        auth = registered.json()
        organization_id = UUID(auth["user"]["organization_id"])
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        facility = _post(
            client,
            "/api/v1/facilities",
            headers,
            {
                "name": "Connected Centre",
                "licensed_capacity": 40,
                "status": "active",
                "timezone": "America/Edmonton",
            },
        )
        program = _post(
            client,
            "/api/v1/programs",
            headers,
            {
                "facility_id": facility["id"],
                "name": "Connected Daycare",
                "program_type": "daycare",
                "capacity": 40,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        room = _post(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Connected Room",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Connected Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0100",
                },
            },
        )
        child = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Connected",
                "last_name": "Child",
                "date_of_birth": "2024-01-01",
            },
        )
        local_now = datetime.now(ZoneInfo("America/Edmonton"))
        check_in_at = local_now - timedelta(minutes=4)
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": check_in_at.date().isoformat(),
            },
        )
        placed = _post(
            client,
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": check_in_at.date().isoformat(),
            },
        )
        assert placed["status"] == "active"
        attendance = _post(
            client,
            "/api/v1/attendance/check-in",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": check_in_at.isoformat(),
            },
        )
        care = _post(
            client,
            "/api/v1/care/records",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "attendance_day_id": attendance["id"],
                "care_type": "mood",
                "occurred_at": (check_in_at + timedelta(minutes=1)).isoformat(),
                "payload": {"value": "calm"},
            },
        )
        job = _post(
            client,
            "/api/v1/ats/jobs",
            headers,
            {
                "title": "Connected Educator",
                "description": "A representative ATS command for the realtime contract.",
                "employment_type": "full_time",
                "facility_id": facility["id"],
                "location": "Edmonton",
                "requirements": [],
            },
        )
        availability_response = client.put(
            f"/api/v1/staff/self/availability/{facility['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": None,
                "windows": [{"weekday": 1, "start_local": "08:00", "end_local": "16:00"}],
                "note": "Representative workforce command",
            },
        )
        assert availability_response.status_code == 200, availability_response.text
        availability = availability_response.json()["profile"]

        expected = {
            ("facility", "facility.created", UUID(facility["id"]), "audit_event"),
            (
                "facility_program",
                "program.created",
                UUID(program["id"]),
                "audit_event",
            ),
            ("family", "family.created", UUID(family["id"]), "audit_event"),
            ("child", "child.created", UUID(child["id"]), "audit_event"),
            ("enrollment", "enrollment.created", UUID(enrollment["id"]), "audit_event"),
            (
                "enrollment",
                "enrollment.room_placement.approved",
                UUID(enrollment["id"]),
                "audit_event",
            ),
            ("room", "room.created", UUID(room["id"]), "audit_event"),
            (
                "attendance_day",
                "attendance.checked_in",
                UUID(attendance["id"]),
                "audit_event",
            ),
            ("daily_care_record", "care.record.created", UUID(care["id"]), "audit_event"),
            ("job", "job.created", UUID(job["id"]), "ats_event"),
            (
                "staff_availability",
                "staff_availability.replaced",
                UUID(availability["id"]),
                "audit_event",
            ),
        }
        with application.state.database.session_factory() as session:
            actual = {
                (event.entity_type, event.event_type, event.entity_id, event.payload.get("source"))
                for event in session.scalars(
                    select(RealtimeEvent).where(RealtimeEvent.organization_id == organization_id)
                )
            }
        assert expected <= actual
