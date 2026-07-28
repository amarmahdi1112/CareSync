"""Migration regression coverage for the destructive 0027 downgrade policy."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import Settings
from app.main import create_app
from tests.test_basic_staff_exchange import (
    _educator,
    _facility_tree,
    _headers,
    _register,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0026_staff_workforce"
FAMILY_AUTHORITY_PREVIOUS_REVISION = "0028_childcare_command_spine"
EVIDENCE_VAULT_PREVIOUS_REVISION = "0029A_family_authority_kernel"
RELEASE_CONTEXT_PREVIOUS_REVISION = "0029A2_authority_activation"
AUTHORITY_ACTIVATION_PREVIOUS_REVISION = "0029A1_family_evidence_vault"
NORMAL_RELEASE_PREVIOUS_REVISION = "0029B_release_context"
EXCHANGE_TABLES = {
    "staff_rotation_patterns",
    "staff_open_shifts",
    "staff_open_shift_engagements",
    "staff_substitute_profiles",
    "staff_shift_swap_requests",
}
EXCHANGE_EVENT_TYPES = {
    "staff_rotation_pattern",
    "staff_open_shift",
    "staff_open_shift_engagement",
    "staff_substitute_profile",
    "staff_shift_swap",
}


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def test_populated_exchange_downgrade_discards_only_0027_evidence_and_re_upgrades(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    config = _config()
    command.upgrade(config, "head")

    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="staff-exchange-migration-test-secret-at-least-32-bytes",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        owner = _register(client, "downgrade")
        owner_headers = _headers(owner)
        facility, room = _facility_tree(client, owner_headers, "Downgrade")
        educator = _educator(client, owner_headers, facility, room, "downgrade")
        availability = client.put(
            f"/api/v1/staff/self/availability/{facility['id']}",
            headers=_headers(educator),
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": None,
                "windows": [],
                "note": "Pre-0027 evidence must survive",
            },
        )
        assert availability.status_code == 200, availability.text
        rotation = client.post(
            "/api/v1/staff-exchange/rotations",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "name": "Disposable 0027 evidence",
                "anchor_date": "2029-01-01",
                "cycle_weeks": 1,
                "slots": [
                    {
                        "slot_id": str(uuid4()),
                        "cycle_week": 0,
                        "weekday": 0,
                        "staff_user_id": educator["user"]["id"],
                        "room_id": room["id"],
                        "start_local": "08:00",
                        "end_local": "16:00",
                        "notes": None,
                    }
                ],
            },
        )
        assert rotation.status_code == 201, rotation.text

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT count(*) FROM staff_workforce_events "
                "WHERE entity_type='staff_availability'"
            )
        ).scalar_one() == 1
        assert connection.execute(
            text(
                "SELECT count(*) FROM staff_workforce_events "
                "WHERE entity_type='staff_rotation_pattern'"
            )
        ).scalar_one() == 1
    engine.dispose()

    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, RELEASE_CONTEXT_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, EVIDENCE_VAULT_PREVIOUS_REVISION)
    command.downgrade(config, FAMILY_AUTHORITY_PREVIOUS_REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert not EXCHANGE_TABLES.intersection(inspector.get_table_names())
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                text("SELECT entity_type FROM staff_workforce_events ORDER BY occurred_at")
            ).scalars()
        )
        assert "staff_availability" in rows
        assert EXCHANGE_EVENT_TYPES.isdisjoint(rows)
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    assert EXCHANGE_TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT count(*) FROM staff_workforce_events "
                "WHERE entity_type='staff_availability'"
            )
        ).scalar_one() == 1
        assert connection.execute(
            text(
                "SELECT count(*) FROM staff_workforce_events "
                "WHERE entity_type='staff_rotation_pattern'"
            )
        ).scalar_one() == 0
    engine.dispose()
    command.check(config)
