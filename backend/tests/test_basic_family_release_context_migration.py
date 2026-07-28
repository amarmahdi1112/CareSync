"""Portable migration proofs for the 0029B release-context boundary."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
A2 = "0029A2_authority_activation"
B = "0029B_release_context"
C = "0029C_verified_release_checkout"
INSERT_TRIGGER = "child_authority_heads_release_context_insert"
UPDATE_TRIGGER = "child_authority_heads_release_context_update"


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.delenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", raising=False)
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _current(database_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _trigger_names(database_path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return set(
                connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='trigger'")
                ).scalars()
            )
    finally:
        engine.dispose()


def test_fresh_release_context_upgrade_and_exact_empty_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    assert _current(database_path) == B
    assert {INSERT_TRIGGER, UPDATE_TRIGGER} <= _trigger_names(database_path)
    assert (
        next(
            column["type"].length
            for column in inspect(create_engine(f"sqlite:///{database_path}")).get_columns(
                "child_release_authorizations"
            )
            if column["name"] == "verification_policy_code"
        )
        == 64
    )
    command.upgrade(config, C)
    assert _current(database_path) == C
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, C)
    assert _current(database_path) == C
    command.downgrade(config, B)

    command.downgrade(config, A2)
    assert _current(database_path) == A2
    assert {INSERT_TRIGGER, UPDATE_TRIGGER}.isdisjoint(_trigger_names(database_path))
    assert (
        next(
            column["type"].length
            for column in inspect(create_engine(f"sqlite:///{database_path}")).get_columns(
                "child_release_authorizations"
            )
            if column["name"] == "verification_policy_code"
        )
        == 40
    )

    command.upgrade(config, B)
    assert _current(database_path) == B
    assert {INSERT_TRIGGER, UPDATE_TRIGGER} <= _trigger_names(database_path)


def test_system_permission_is_exact_and_custom_roles_are_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A2)
    organization_id = uuid4().hex
    role_rows = {
        "owner": (["organization:manage"], True),
        "administrator": (["staff:manage"], True),
        "educator": (["attendance:write"], True),
        "custom_release_coordinator": (["families:read"], False),
    }
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations "
                    "(id,name,status,timezone,preferences,verification_status) "
                    "VALUES (:id,'B permission proof','active','America/Edmonton',"
                    "'{}','pending')"
                ),
                {"id": organization_id},
            )
            for key, (permissions, is_system) in role_rows.items():
                connection.execute(
                    text(
                        "INSERT INTO roles "
                        "(id,organization_id,key,name,permissions,is_system) "
                        "VALUES (:id,:organization_id,:key,:name,:permissions,:is_system)"
                    ),
                    {
                        "id": uuid4().hex,
                        "organization_id": organization_id,
                        "key": key,
                        "name": key.replace("_", " ").title(),
                        "permissions": json.dumps(permissions),
                        "is_system": is_system,
                    },
                )
    finally:
        engine.dispose()

    command.upgrade(config, B)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            upgraded = {
                row.key: json.loads(row.permissions)
                for row in connection.execute(
                    text("SELECT key,permissions FROM roles ORDER BY key")
                )
            }
        for key in ("owner", "administrator", "educator"):
            assert upgraded[key] == [*role_rows[key][0], "release:read"]
        assert upgraded["custom_release_coordinator"] == ["families:read"]
    finally:
        engine.dispose()

    command.downgrade(config, A2)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            downgraded = {
                row.key: json.loads(row.permissions)
                for row in connection.execute(
                    text("SELECT key,permissions FROM roles ORDER BY key")
                )
            }
        assert downgraded == {key: values[0] for key, values in role_rows.items()}
    finally:
        engine.dispose()


def test_child_head_insert_and_revision_change_emit_one_safe_event_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    engine = create_engine(f"sqlite:///{database_path}")
    organization_id = uuid4().hex
    family_id = uuid4().hex
    child_id = uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO child_authority_heads "
                    "(organization_id,family_id,child_id,revision,"
                    "created_operation_id,last_operation_id) "
                    "VALUES (:organization_id,:family_id,:child_id,1,"
                    ":created_operation_id,:last_operation_id)"
                ),
                {
                    "organization_id": organization_id,
                    "family_id": family_id,
                    "child_id": child_id,
                    "created_operation_id": uuid4().hex,
                    "last_operation_id": uuid4().hex,
                },
            )
            connection.execute(
                text(
                    "UPDATE child_authority_heads SET revision=2,last_operation_id=:op "
                    "WHERE child_id=:child_id"
                ),
                {"op": uuid4().hex, "child_id": child_id},
            )
            connection.execute(
                text(
                    "UPDATE child_authority_heads SET revision=2,last_operation_id=:op "
                    "WHERE child_id=:child_id"
                ),
                {"op": uuid4().hex, "child_id": child_id},
            )

        with engine.connect() as connection:
            events = connection.execute(
                text(
                    "SELECT organization_id,event_type,entity_type,entity_id,payload "
                    "FROM realtime_events ORDER BY sequence_id"
                )
            ).all()
        assert len(events) == 2
        for event in events:
            assert event.organization_id == organization_id
            assert event.event_type == "family_authority.release_context_invalidated"
            assert event.entity_type == "child_authority_head"
            assert event.entity_id is None
            assert json.loads(event.payload) == {
                "source": "authority_head",
                "scope": "release_context",
            }
    finally:
        engine.dispose()


def test_sqlite_runtime_detector_rejects_child_identity_in_generic_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="release-context-detector-test-secret-32-bytes",
    )
    database = Database(settings)
    try:
        assert database.has_family_authority_release_context() is True
        with database.engine.begin() as connection:
            for trigger_name in (INSERT_TRIGGER, UPDATE_TRIGGER):
                definition = connection.scalar(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type='trigger' AND name=:trigger_name"
                    ),
                    {"trigger_name": trigger_name},
                )
                assert isinstance(definition, str)
                leaked = definition.replace(
                    "NULL, CURRENT_TIMESTAMP",
                    "NEW.child_id, CURRENT_TIMESTAMP",
                )
                assert leaked != definition
                connection.execute(text(f"DROP TRIGGER {trigger_name}"))
                connection.execute(text(leaked))
        assert database.has_family_authority_release_context() is False
    finally:
        database.dispose()


def test_sqlite_multirevision_downgrade_refuses_before_trigger_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    before = _trigger_names(database_path)

    with pytest.raises(RuntimeError, match="0029B SQLite downgrade refused before DDL"):
        command.downgrade(config, "0029A1_family_evidence_vault")

    assert _current(database_path) == B
    assert _trigger_names(database_path) == before
    assert not any(
        name.startswith("_alembic_tmp_")
        for name in inspect(create_engine(f"sqlite:///{database_path}")).get_table_names()
    )
