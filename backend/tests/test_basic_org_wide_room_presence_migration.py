"""Portable certification for the additive 0043 room-presence guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND_ROOT / "alembic" / "versions" / "0043_org_wide_room_presence.py"
PREDECESSOR = "0042_billing_policy_recert"
REVISION = "0043_org_wide_room_presence"


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "caresync_0043_org_wide_room_presence",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(database_path: Path) -> Config:
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def _trigger_sql(database_path: Path) -> str:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            value = connection.scalar(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='trigger' "
                    "AND name='staff_room_presence_sessions_insert_guard'"
                )
            )
            assert value is not None
            return str(value)
    finally:
        engine.dispose()


def _revision(database_path: Path) -> str:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return str(connection.scalar(text("SELECT version_num FROM alembic_version")))
    finally:
        engine.dispose()


def test_0043_portable_guard_round_trip_is_exact_and_runtime_detectable(
    tmp_path: Path,
) -> None:
    module = _migration_module()
    database_path = tmp_path / "caresync.db"
    config = _config(database_path)

    command.upgrade(config, PREDECESSOR)
    assert _revision(database_path) == PREDECESSOR
    assert module._compact_sql(_trigger_sql(database_path)) == module._compact_sql(
        module._SQLITE_INSERT_GUARD_0041
    )

    command.upgrade(config, REVISION)
    assert _revision(database_path) == REVISION
    installed = module._compact_sql(_trigger_sql(database_path))
    assert installed == module._compact_sql(module._SQLITE_INSERT_GUARD_0043)
    assert "membership_role.keyin('owner','administrator')" in installed
    assert "orexists(select1frommembership_room_assignments" in installed

    database = Database(
        Settings(
            _env_file=None,
            environment="test",
            database_type="sqlite",
            database_path=database_path,
            database_name="caresync",
            database_read_only=False,
            enable_advanced_routes=False,
            jwt_secret="0043-portable-test-secret-at-least-32-bytes",
        )
    )
    try:
        assert database.has_live_room_presence_safety_board() is True
    finally:
        database.dispose()

    command.downgrade(config, PREDECESSOR)
    assert _revision(database_path) == PREDECESSOR
    assert module._compact_sql(_trigger_sql(database_path)) == module._compact_sql(
        module._SQLITE_INSERT_GUARD_0041
    )

    command.upgrade(config, REVISION)
    assert _revision(database_path) == REVISION
    assert module._compact_sql(_trigger_sql(database_path)) == module._compact_sql(
        module._SQLITE_INSERT_GUARD_0043
    )


def test_0043_postgres_guard_derivation_changes_only_start_eligibility() -> None:
    module = _migration_module()
    old_source = module._POSTGRES_GUARD_SOURCE_0041
    new_source = module._POSTGRES_GUARD_SOURCE_0043

    assert module._source_sha256(old_source) == (
        "c2885e959f4b68c8ac0cdbd3e1a076a00849cb7aa643d90ff3c4db954379c2ce"
    )
    assert module._source_sha256(new_source) == (
        "184a58df0881eaec6593da4f82193877bac79179ea3e26bc37bbef724e595390"
    )
    assert old_source.count(module._POSTGRES_ASSIGNMENT_ELIGIBILITY_0041) == 1
    assert new_source == old_source.replace(
        module._POSTGRES_ASSIGNMENT_ELIGIBILITY_0041,
        module._POSTGRES_ORGANIZATION_WIDE_ELIGIBILITY_0043,
    )
    assert "membership_role.key IN ('owner','administrator')" in new_source
    for retained_guard in (
        "room presence command context is required",
        '["shift:clock","care_roster:read"]',
        "shift.clocked_out_at IS NULL",
        "membership.status='active'",
        "facility.status='active'",
        "room.is_active",
        "overlapping room presence is forbidden",
    ):
        assert retained_guard in old_source
        assert retained_guard in new_source
