"""Portable migration and downgrade proofs for the frozen 0039 boundary."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app
from tests.test_basic_room_placement import (
    _facility_tree,
    _headers,
    _register,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0038_public_job_catalog_outbox"
CURRENT_REVISION = "0039_admissions_decision_spine"
MIGRATION = (
    BACKEND_ROOT / "alembic" / "versions" / "0039_admissions_decision_spine.py"
)
TABLES = {
    "admission_applications",
    "admission_application_preferences",
    "admission_waitlist_entries",
    "admission_offers",
    "admission_conversion_links",
    "admission_application_events",
}


def _config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="admissions-migration-secret-at-least-thirty-two-bytes",
    )


def _create_payload(facility: dict, program: dict) -> dict:
    return {
        "client_operation_id": str(uuid4()),
        "child": {
            "first_name": "Migration",
            "last_name": "Admission",
            "date_of_birth": "2023-01-01",
        },
        "primary_contact": {
            "first_name": "Migration",
            "last_name": "Contact",
            "relationship": "Parent",
        },
        "preferences": [
            {
                "rank": 1,
                "facility_id": facility["id"],
                "program_id": program["id"],
                "desired_start_date": "2026-10-01",
            }
        ],
    }


def test_fresh_round_trip_and_permission_union(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    with TestClient(create_app(_settings(database_path))) as client:
        auth = _register(
            client, "migration-permissions@example.test", "Migration Centre"
        )
    organization_id = auth["user"]["organization_id"].replace("-", "")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            role_permissions = connection.execute(
                text(
                    "SELECT id,permissions FROM roles "
                    "WHERE organization_id=:organization_id "
                    "AND key IN ('owner','administrator')"
                ),
                {"organization_id": organization_id},
            ).mappings()
            for role in role_permissions:
                current_permissions = role["permissions"]
                if isinstance(current_permissions, str):
                    current_permissions = json.loads(current_permissions)
                pre_migration_permissions = sorted(
                    {
                        *(
                            permission
                            for permission in current_permissions
                            if not permission.startswith("admissions:")
                        ),
                    }
                )
                connection.execute(
                    text("UPDATE roles SET permissions=:permissions WHERE id=:role_id"),
                    {
                        "permissions": json.dumps(pre_migration_permissions),
                        "role_id": role["id"],
                    },
                )
        command.upgrade(config, CURRENT_REVISION)
        assert TABLES.issubset(set(inspect(engine).get_table_names()))
        with engine.connect() as connection:
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
            permissions = connection.scalar(
                text(
                    "SELECT permissions FROM roles "
                    "WHERE organization_id=:organization_id AND key='owner'"
                ),
                {"organization_id": organization_id},
            )
            if isinstance(permissions, str):
                permissions = json.loads(permissions)
            assert {
                "facility:read",
                "admissions:read",
                "admissions:manage",
                "admissions:decide",
            }.issubset(set(permissions))
            assert version == CURRENT_REVISION
            assert all(
                int(connection.scalar(text(f"SELECT count(*) FROM {table}")) or 0)
                == 0
                for table in TABLES
            )

        database = Database(_settings(database_path))
        try:
            assert database.has_admissions_decision_spine()
        finally:
            database.dispose()
        command.downgrade(config, PREVIOUS_REVISION)
        assert TABLES.isdisjoint(set(inspect(engine).get_table_names()))
        command.upgrade(config, CURRENT_REVISION)
        assert TABLES.issubset(set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()


def test_populated_downgrade_refuses_before_changing_history(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    with TestClient(create_app(_settings(database_path))) as client:
        auth = _register(
            client, "migration-populated@example.test", "Populated Centre"
        )
        headers = _headers(auth)
        facility, program, _, _ = _facility_tree(client, headers)
        created = client.post(
            "/api/v1/admissions/applications",
            headers=headers,
            json=_create_payload(facility, program),
        )
        assert created.status_code == 201, created.text
        application_id = created.json()["id"].replace("-", "")

    with pytest.raises(
        RuntimeError,
        match="admissions history or dependent events exist",
    ):
        command.downgrade(config, PREVIOUS_REVISION)

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == CURRENT_REVISION
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM admission_applications WHERE id=:id"
                ),
                {"id": application_id},
            ) == 1
    finally:
        engine.dispose()


def test_migration_is_frozen_and_bootstrap_is_capability_gated() -> None:
    source = MIGRATION.read_text()
    assert "from app.basic.models" not in source
    assert 'down_revision = "0038_public_job_catalog_outbox"' in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "admission fact is immutable" in source
    assert "0039 downgrade refused" in source

    bootstrap = (
        BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
    ).read_text()
    assert "complete 0039 admissions decision spine" in bootstrap
    assert "public.admission_conversion_links" in bootstrap
    assert "GRANT SELECT, INSERT ON TABLE" in bootstrap
    assert "DELETE, TRUNCATE, REFERENCES, TRIGGER" in bootstrap
