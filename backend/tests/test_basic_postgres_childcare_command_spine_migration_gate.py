"""Process-level PostgreSQL migration gate for the 0028 command spine.

This destructive proof is opt-in and requires a fresh disposable local cluster.
It creates and drops only the ``caresync`` database on that isolated cluster.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

TEST_PORT = os.getenv("BASIC_POSTGRES_MIGRATION_TEST_PORT")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_MIGRATION_TEST_PORT must identify a fresh disposable cluster",
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = "caresync"
MIGRATION_ROLE = "caresync_hostile_migration_owner"
HOSTILE_SCHEMA = MIGRATION_ROLE
PREVIOUS_REVISION = "0027_staff_exchange"
CURRENT_REVISION = "0028_childcare_command_spine"

COMMAND_TABLES = (
    "childcare_command_slots",
    "childcare_command_receipts",
    "childcare_command_claims",
    "childcare_command_reconciliation_proofs",
    "childcare_command_reconciliation_budget_entries",
    "childcare_command_reconciliation_budgets",
)
COMMAND_FUNCTIONS = (
    "caresync_charge_childcare_reconciliation",
    "caresync_childcare_operation_guard",
    "caresync_childcare_reconciliation_proof_guard",
    "caresync_childcare_immutable_ledger_guard",
    "caresync_childcare_contact_retirement_guard",
)


def _url(database: str, user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        port=port,
        database=database,
    )


def _migration_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
            "DATABASE_PORT": str(TEST_PORT),
            "DATABASE_USER": MIGRATION_ROLE,
            "DATABASE_PASSWORD": "",
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )
    return environment


def _alembic(action: str, revision: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=_migration_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _require_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _assert_0028_is_public_and_committed() -> None:
    migration_engine = create_engine(_url(DATABASE_NAME, MIGRATION_ROLE))
    with migration_engine.connect() as connection:
        # Reconnecting proves the migration transaction committed. The role's
        # hostile default remains intact outside Alembic's transaction.
        assert connection.execute(text("SHOW search_path")).scalar_one() == '"$user", public'
        assert connection.execute(text("SELECT current_schema()")).scalar_one() == HOSTILE_SCHEMA
        assert (
            connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
            == CURRENT_REVISION
        )
        table_schemas = {
            row.table_name: row.table_schema
            for row in connection.execute(
                text(
                    "SELECT table_name, table_schema FROM information_schema.tables "
                    "WHERE table_name = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(COMMAND_TABLES)},
            )
        }
        assert table_schemas == {table: "public" for table in COMMAND_TABLES}
        function_schemas = {
            row.proname: row.nspname
            for row in connection.execute(
                text(
                    "SELECT DISTINCT p.proname, n.nspname FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE p.proname = ANY(CAST(:functions AS text[]))"
                ),
                {"functions": list(COMMAND_FUNCTIONS)},
            )
        }
        assert function_schemas == {function: "public" for function in COMMAND_FUNCTIONS}
        leaked_relations = connection.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=:schema"
            ),
            {"schema": HOSTILE_SCHEMA},
        ).scalar_one()
        leaked_functions = connection.execute(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname=:schema"
            ),
            {"schema": HOSTILE_SCHEMA},
        ).scalar_one()
        assert leaked_relations == 0
        assert leaked_functions == 0
    migration_engine.dispose()


def test_hostile_role_search_path_commits_roundtrip_and_refusal_rolls_back() -> None:
    cluster_engine = create_engine(_url("postgres", "postgres"), isolation_level="AUTOCOMMIT")
    database_created = False
    role_created = False
    try:
        with cluster_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"),
                    {"name": DATABASE_NAME},
                ).scalar_one_or_none()
                is None
            ), "The migration gate requires a fresh cluster without a caresync database"
            assert (
                connection.execute(
                    text("SELECT 1 FROM pg_roles WHERE rolname=:name"),
                    {"name": MIGRATION_ROLE},
                ).scalar_one_or_none()
                is None
            ), "The migration gate requires a fresh cluster without its owner role"
            connection.execute(
                text(
                    f"CREATE ROLE {MIGRATION_ROLE} LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                )
            )
            role_created = True
            connection.execute(
                text(f'ALTER ROLE {MIGRATION_ROLE} SET search_path TO "$user", public')
            )
            connection.execute(text(f"CREATE DATABASE {DATABASE_NAME} OWNER {MIGRATION_ROLE}"))
            database_created = True

        database_engine = create_engine(_url(DATABASE_NAME, "postgres"))
        with database_engine.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            connection.execute(text(f"ALTER SCHEMA public OWNER TO {MIGRATION_ROLE}"))
            connection.execute(
                text(f"CREATE SCHEMA {HOSTILE_SCHEMA} AUTHORIZATION {MIGRATION_ROLE}")
            )
            role_security = connection.execute(
                text(
                    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, "
                    "rolbypassrls FROM pg_roles WHERE rolname=:name"
                ),
                {"name": MIGRATION_ROLE},
            ).one()
            assert role_security == (False, False, False, False, False)

        # Each Alembic call is a separate process and therefore a separate DB
        # connection. This catches both search-path capture and close-time rollback.
        _require_success(_alembic("upgrade", PREVIOUS_REVISION))
        _require_success(_alembic("upgrade", CURRENT_REVISION))
        _assert_0028_is_public_and_committed()

        _require_success(_alembic("downgrade", PREVIOUS_REVISION))
        with database_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalar_one()
                == PREVIOUS_REVISION
            )
            assert all(
                connection.execute(
                    text("SELECT to_regclass(:relation)"),
                    {"relation": f"public.{table}"},
                ).scalar_one_or_none()
                is None
                for table in COMMAND_TABLES
            )

        _require_success(_alembic("upgrade", CURRENT_REVISION))
        _assert_0028_is_public_and_committed()

        # A committed 0028 quota row is irreducible history. The downgrade
        # must refuse atomically, including rolling back its temporary RLS DDL.
        actor_id = uuid4()
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.users "
                    "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                    "VALUES (:id,:email,'unused','Migration','Actor',true,1)"
                ),
                {"id": actor_id, "email": f"migration-{uuid4().hex}@example.com"},
            )
            connection.execute(
                text(
                    "INSERT INTO public.childcare_command_reconciliation_budgets "
                    "(organization_id,actor_user_id,window_kind,window_started_at,operation_count) "
                    "VALUES (:organization_id,:actor_id,'hour',date_trunc('hour', now()),1)"
                ),
                {"organization_id": uuid4(), "actor_id": actor_id},
            )

        refused = _alembic("downgrade", PREVIOUS_REVISION)
        assert refused.returncode != 0
        assert "0028 downgrade refused because committed childcare command history" in (
            refused.stdout + refused.stderr
        )
        with database_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalar_one()
                == CURRENT_REVISION
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM public.childcare_command_reconciliation_budgets")
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE oid='public.childcare_command_reconciliation_budgets'::regclass"
                    )
                ).scalar_one()
                is True
            )
        database_engine.dispose()
    finally:
        with cluster_engine.connect() as connection:
            if database_created:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname=:name AND pid <> pg_backend_pid()"
                    ),
                    {"name": DATABASE_NAME},
                )
                connection.execute(text(f"DROP DATABASE IF EXISTS {DATABASE_NAME}"))
            if role_created:
                connection.execute(text(f"DROP ROLE IF EXISTS {MIGRATION_ROLE}"))
        cluster_engine.dispose()
