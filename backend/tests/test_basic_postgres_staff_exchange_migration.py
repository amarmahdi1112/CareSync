"""PostgreSQL authority-boundary proof for the destructive 0027 downgrade.

This suite is opt-in because it temporarily downgrades an isolated database.
It must be run only against a disposable PostgreSQL cluster and never against
the live CareSync port.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from alembic import command

TEST_PORT = os.getenv("BASIC_POSTGRES_MIGRATION_TEST_PORT")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_MIGRATION_TEST_PORT must identify a disposable cluster",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROLE = "caresync_migration_gate"
EXCHANGE_ENTITY_TYPES = (
    "staff_rotation_pattern",
    "staff_open_shift",
    "staff_open_shift_engagement",
    "staff_substitute_profile",
    "staff_shift_swap",
)
EXCHANGE_TABLES = (
    "staff_rotation_patterns",
    "staff_open_shifts",
    "staff_open_shift_engagements",
    "staff_substitute_profiles",
    "staff_shift_swap_requests",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        port=port,
        database="caresync",
    )


def _alembic_config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _runtime_security_snapshot(connection) -> list[tuple[object, ...]]:
    tables = (*EXCHANGE_TABLES, "staff_workforce_events")
    return list(
        connection.execute(
            text(
                "SELECT table_name, relrowsecurity, relforcerowsecurity, "
                "coalesce(string_agg(policyname || ':' || cmd || ':' || qual || ':' || "
                "coalesce(with_check, ''), '|' ORDER BY policyname), ''), "
                "has_table_privilege('caresync_basic_app', table_name, 'SELECT'), "
                "has_table_privilege('caresync_basic_app', table_name, 'INSERT'), "
                "has_table_privilege('caresync_basic_app', table_name, 'UPDATE'), "
                "has_table_privilege('caresync_basic_app', table_name, 'DELETE') "
                "FROM unnest(CAST(:tables AS text[])) AS requested(table_name) "
                "JOIN pg_class ON pg_class.oid=to_regclass(requested.table_name) "
                "LEFT JOIN pg_policies ON schemaname=current_schema() "
                "AND tablename=requested.table_name "
                "GROUP BY table_name, relrowsecurity, relforcerowsecurity "
                "ORDER BY table_name"
            ),
            {"tables": list(tables)},
        )
    )


def test_populated_downgrade_runs_as_forced_rls_table_owner(monkeypatch) -> None:
    admin_engine = create_engine(_url("postgres"))
    legacy_event_id = uuid4()
    exchange_event_id = uuid4()
    with admin_engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0027_staff_exchange"
        )
        membership = connection.execute(
            text(
                "SELECT organization_id, user_id FROM organization_memberships "
                "WHERE status='active' ORDER BY created_at LIMIT 1"
            )
        ).one()
        connection.execute(
            text(
                "INSERT INTO staff_workforce_events "
                "(id, organization_id, entity_type, entity_id, operation_id, actor_user_id, "
                "event_type, payload) VALUES "
                "(:legacy_id, :organization_id, 'staff_availability', :legacy_entity_id, "
                ":legacy_operation_id, :user_id, 'created', '{}'::json), "
                "(:exchange_id, :organization_id, 'staff_rotation_pattern', "
                ":exchange_entity_id, :exchange_operation_id, :user_id, 'created', '{}'::json)"
            ),
            {
                "legacy_id": legacy_event_id,
                "exchange_id": exchange_event_id,
                "organization_id": membership.organization_id,
                "user_id": membership.user_id,
                "legacy_entity_id": uuid4(),
                "legacy_operation_id": uuid4(),
                "exchange_entity_id": uuid4(),
                "exchange_operation_id": uuid4(),
            },
        )
        security_before = _runtime_security_snapshot(connection)
        connection.execute(
            text(
                "DO $role$ BEGIN "
                f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{MIGRATION_ROLE}') THEN "
                f"CREATE ROLE {MIGRATION_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOINHERIT NOBYPASSRLS; END IF; END $role$"
            )
        )
        connection.execute(
            text(
                f"ALTER ROLE {MIGRATION_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOINHERIT NOBYPASSRLS"
            )
        )
        connection.execute(text(f"ALTER DATABASE caresync OWNER TO {MIGRATION_ROLE}"))
        connection.execute(text(f"ALTER SCHEMA public OWNER TO {MIGRATION_ROLE}"))
        connection.execute(
            text(
                "DO $ownership$ DECLARE item record; BEGIN "
                "FOR item IN SELECT n.nspname, c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind IN ('r','p') LOOP "
                "EXECUTE format('ALTER TABLE %I.%I OWNER TO "
                f"{MIGRATION_ROLE}', item.nspname, item.relname); END LOOP; END $ownership$"
            )
        )
        role = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=:role"),
            {"role": MIGRATION_ROLE},
        ).one()
        assert role == (False, False)
        assert (
            connection.execute(
                text(
                    "SELECT pg_get_userbyid(relowner) FROM pg_class "
                    "WHERE oid='staff_workforce_events'::regclass"
                )
            ).scalar_one()
            == MIGRATION_ROLE
        )

    migration_engine = create_engine(_url(MIGRATION_ROLE))
    with migration_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT current_setting('app.current_organization_id', true)")
            ).scalar_one_or_none()
            is None
        )
    migration_engine.dispose()

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    monkeypatch.setenv("DATABASE_HOST", os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"))
    monkeypatch.setenv("DATABASE_PORT", str(TEST_PORT))
    monkeypatch.setenv("DATABASE_USER", MIGRATION_ROLE)
    monkeypatch.setenv("DATABASE_PASSWORD", "")
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_SSL", "false")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    config = _alembic_config()
    command.downgrade(config, "0026_staff_workforce")

    with admin_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM staff_workforce_events WHERE id=:id"),
                {"id": exchange_event_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM staff_workforce_events WHERE id=:id"),
                {"id": legacy_event_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE oid='staff_workforce_events'::regclass"
                )
            ).scalar_one()
            is True
        )

    command.upgrade(config, "head")
    with admin_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM staff_workforce_events WHERE id=:id"),
                {"id": legacy_event_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM staff_workforce_events WHERE id=:id"),
                {"id": exchange_event_id},
            ).scalar_one()
            == 0
        )
        assert _runtime_security_snapshot(connection) == security_before
    admin_engine.dispose()
    command.check(config)
