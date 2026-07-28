"""Additive room-daybook migration, permission, and schema-drift proof."""

from __future__ import annotations

import json
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0005_child_profile_photos"

EXPECTED_ROLE_PERMISSIONS = {
    "owner": {"care:read", "care:record", "care:correct", "care:void", "child_safety:read"},
    "administrator": {
        "care:read",
        "care:record",
        "care:correct",
        "care:void",
        "child_safety:read",
    },
    "educator": {"care:read", "care:record", "care:correct_own", "child_safety:read"},
}


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _migration_database(tmp_path, monkeypatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    return database_path


def _seed_existing_roles(database_path: Path) -> str:
    organization_id = "11111111111111111111111111111111"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id,name,status,verification_status,timezone,preferences) "
                "VALUES (:id,'Existing Daybook','active','pending','America/Edmonton','{}')"
            ),
            {"id": organization_id},
        )
        for index, key in enumerate(EXPECTED_ROLE_PERMISSIONS, start=2):
            connection.execute(
                text(
                    "INSERT INTO roles "
                    "(id,organization_id,key,name,permissions,is_system) "
                    "VALUES (:id,:organization_id,:key,:name,:permissions,1)"
                ),
                {
                    "id": str(index) * 32,
                    "organization_id": organization_id,
                    "key": key,
                    "name": key.title(),
                    "permissions": json.dumps(["existing:permission"]),
                },
            )
    engine.dispose()
    return organization_id


def _role_permissions(database_path: Path) -> dict[str, set[str]]:
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT key, permissions FROM roles"))
        result = {key: set(json.loads(permissions)) for key, permissions in rows}
    engine.dispose()
    return result


def test_daily_care_migration_is_additive_round_trips_and_has_no_drift(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch)
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)
    _seed_existing_roles(database_path)

    command.upgrade(config, "0006_room_daybook")
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert {"daily_care_records", "daily_care_record_events"}.issubset(
        inspector.get_table_names()
    )
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("attendance_days")
    } >= {"uq_attendance_days_care_identity"}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("daily_care_records")
    } == {
        "ck_daily_care_records_end_only_for_sleep",
        "ck_daily_care_records_time_order",
        "ck_daily_care_records_type",
        "ck_daily_care_records_version",
        "ck_daily_care_records_void_evidence",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("daily_care_record_events")
    } == {
        "uq_daily_care_record_events_operation",
        "uq_daily_care_record_events_org_id",
    }
    open_sleep_index = next(
        index
        for index in inspector.get_indexes("daily_care_records")
        if index["name"] == "uq_daily_care_records_open_sleep"
    )
    assert bool(open_sleep_index["unique"])
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
    engine.dispose()

    permissions = _role_permissions(database_path)
    for key, additions in EXPECTED_ROLE_PERMISSIONS.items():
        assert permissions[key] == {"existing:permission", *additions}

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert "daily_care_records" not in inspector.get_table_names()
    assert "daily_care_record_events" not in inspector.get_table_names()
    assert "uq_attendance_days_care_identity" not in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("attendance_days")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
    engine.dispose()
    assert _role_permissions(database_path) == {
        key: {"existing:permission"} for key in EXPECTED_ROLE_PERMISSIONS
    }

    command.upgrade(config, "0006_room_daybook")
