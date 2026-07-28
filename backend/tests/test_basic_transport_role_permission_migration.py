"""Portable release proofs for the 0034 transport-role permission backfill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from alembic import command
from app.api.basic.dependencies import require_permission
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PRE_TRANSPORT_REVISION = "0030_staff_screening_paths"
PREVIOUS_REVISION = "0033_billing_ledger"
CURRENT_REVISION = "0034_transport_role_permissions"


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


def _load_migration_module():
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0034_transport_role_permissions.py"
    spec = importlib.util.spec_from_file_location("transport_role_permissions_0034", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_pre_transport_roles(database_path: Path) -> dict[str, str]:
    ids = {
        key: uuid4().hex
        for key in (
            "organization_a",
            "organization_b",
            "owner_a",
            "administrator_a",
            "educator_a",
            "owner_b",
            "administrator_b",
            "educator_b",
        )
    }
    role_rows = (
        (
            ids["owner_a"],
            ids["organization_a"],
            "owner",
            ["organization:manage", "custom:retained"],
        ),
        (
            ids["administrator_a"],
            ids["organization_a"],
            "administrator",
            ["facility:manage", "custom:administrator"],
        ),
        (
            ids["educator_a"],
            ids["organization_a"],
            "educator",
            ["attendance:record", "custom:educator"],
        ),
        (
            ids["owner_b"],
            ids["organization_b"],
            "owner",
            ["organization:manage", "transport:read", "custom:preexisting"],
        ),
        (
            ids["administrator_b"],
            ids["organization_b"],
            "administrator",
            ["facility:manage"],
        ),
        (
            ids["educator_b"],
            ids["organization_b"],
            "educator",
            ["attendance:record"],
        ),
    )
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            for suffix in ("a", "b"):
                connection.execute(
                    text(
                        "INSERT INTO organizations "
                        "(id,name,status,timezone,preferences) "
                        "VALUES (:id,:name,'active','America/Edmonton','{}')"
                    ),
                    {
                        "id": ids[f"organization_{suffix}"],
                        "name": f"Transport Migration {suffix.upper()}",
                    },
                )
            for role_id, organization_id, key, permissions in role_rows:
                connection.execute(
                    text(
                        "INSERT INTO roles "
                        "(id,organization_id,key,name,permissions,is_system) "
                        "VALUES (:id,:organization_id,:key,:name,:permissions,1)"
                    ),
                    {
                        "id": role_id,
                        "organization_id": organization_id,
                        "key": key,
                        "name": key.title(),
                        "permissions": json.dumps(permissions),
                    },
                )
    finally:
        engine.dispose()
    return ids


def _roles(database_path: Path) -> dict[str, set[str]]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return {
                row.id: set(json.loads(row.permissions))
                for row in connection.execute(
                    text("SELECT id,permissions FROM roles ORDER BY organization_id,key")
                )
            }
    finally:
        engine.dispose()


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        billing_mode="disabled",
        jwt_secret="transport-role-migration-secret-with-at-least-thirty-two-bytes",
    )


def _assert_transport_capability(permissions: set[str], *, allowed: bool) -> None:
    context = SimpleNamespace(role=SimpleNamespace(permissions=sorted(permissions)))
    dependency = require_permission("transport:manage")
    if allowed:
        assert dependency(context) is context
    else:
        with pytest.raises(HTTPException) as error:
            dependency(context)
        assert error.value.status_code == 403


def test_upgrade_backfills_only_leaders_preserves_custom_permissions_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PRE_TRANSPORT_REVISION)
    ids = _seed_pre_transport_roles(database_path)

    command.upgrade(config, PREVIOUS_REVISION)
    before = _roles(database_path)
    assert "transport:manage" not in before[ids["owner_a"]]
    assert "transport:manage" not in before[ids["administrator_a"]]

    command.upgrade(config, CURRENT_REVISION)
    database = Database(_settings(database_path))
    try:
        assert database.has_billing_ledger() is True
    finally:
        database.dispose()
    first = _roles(database_path)
    migration = _load_migration_module()
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            migration._backfill_transport_permissions(connection)
    finally:
        engine.dispose()
    second = _roles(database_path)

    assert second == first
    for key in ("owner_a", "administrator_a", "owner_b", "administrator_b"):
        assert {"transport:read", "transport:manage"}.issubset(second[ids[key]])
        _assert_transport_capability(second[ids[key]], allowed=True)
    for key in ("educator_a", "educator_b"):
        assert not {"transport:read", "transport:manage"}.intersection(second[ids[key]])
        _assert_transport_capability(second[ids[key]], allowed=False)

    assert "custom:retained" in second[ids["owner_a"]]
    assert "custom:administrator" in second[ids["administrator_a"]]
    assert "custom:educator" in second[ids["educator_a"]]
    assert "custom:preexisting" in second[ids["owner_b"]]

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num='0034_untrusted_release_marker'")
            )
    finally:
        engine.dispose()
    drifted = Database(_settings(database_path))
    try:
        with pytest.raises(RuntimeError, match="0033 billing ledger"):
            drifted.has_billing_ledger()
    finally:
        drifted.dispose()


def test_downgrade_removes_only_permissions_attributed_to_0034(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PRE_TRANSPORT_REVISION)
    ids = _seed_pre_transport_roles(database_path)
    command.upgrade(config, CURRENT_REVISION)

    command.downgrade(config, PREVIOUS_REVISION)
    permissions = _roles(database_path)
    assert not {"transport:read", "transport:manage"}.intersection(permissions[ids["owner_a"]])
    assert "transport:read" in permissions[ids["owner_b"]]
    assert "transport:manage" not in permissions[ids["owner_b"]]
    assert "custom:retained" in permissions[ids["owner_a"]]
    assert "custom:preexisting" in permissions[ids["owner_b"]]
    assert "custom:educator" in permissions[ids["educator_a"]]
