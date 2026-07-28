"""Opt-in PostgreSQL 17 defensive checks for the terminal Basic runtime role.

The suite simulates authorized configuration drift, so it runs only when the guarded
``BASIC_POSTGRES_TEST_PORT`` identifies an explicitly disposable cluster.
Every test repairs the runtime bootstrap before returning.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(
    os.getenv(
        "CARESYNC_PSQL",
        "/opt/homebrew/Cellar/postgresql@17/17.8/bin/psql",
    )
)
TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
ADMIN_USER = os.getenv("BASIC_POSTGRES_TEST_ADMIN_USER", "postgres")
MIGRATION_USER = os.getenv("BASIC_POSTGRES_TEST_MIGRATION_USER", "migration_owner")

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=TEST_HOST,
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=TEST_DATABASE,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="runtime-role-hardening-test-secret-32-bytes",
    )


def _run_bootstrap(
    *, user: str = ADMIN_USER, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(PSQL),
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            TEST_HOST,
            "-p",
            str(TEST_PORT),
            "-U",
            user,
            "-d",
            TEST_DATABASE,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _assert_runtime_identity() -> None:
    database = Database(_settings())
    try:
        database.assert_basic_runtime_identity()
    finally:
        database.dispose()


def test_runtime_baseline_is_terminal_and_migration_owner_can_reapply_grants() -> None:
    _run_bootstrap()
    _assert_runtime_identity()
    migration_result = _run_bootstrap(user=MIGRATION_USER)
    assert migration_result.returncode == 0

    engine = create_engine(_url("caresync_basic_app"))
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT current_user, session_user, "
                    "replace(current_setting('search_path'),' ','') AS search_path, "
                    "has_database_privilege(current_user,current_database(),'CREATE'), "
                    "has_database_privilege(current_user,current_database(),'TEMPORARY')"
                )
            ).one()
            assert result == (
                "caresync_basic_app",
                "caresync_basic_app",
                "public,pg_catalog",
                False,
                False,
            )
    finally:
        engine.dispose()


def test_direct_and_indirect_set_role_paths_are_rejected_and_repaired() -> None:
    direct_role = f"role_hardening_direct_{uuid4().hex}"
    indirect_role = f"role_hardening_indirect_{uuid4().hex}"
    admin = create_engine(_url(ADMIN_USER))
    runtime = create_engine(_url("caresync_basic_app"))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE ROLE "{direct_role}" NOLOGIN')
            connection.exec_driver_sql(f'CREATE ROLE "{indirect_role}" NOLOGIN')
            connection.exec_driver_sql(f'GRANT "{indirect_role}" TO "{direct_role}"')
            connection.exec_driver_sql(f'GRANT "{direct_role}" TO caresync_basic_app')

        with pytest.raises(RuntimeError, match="SET ROLE paths"):
            _assert_runtime_identity()
        with runtime.connect() as connection:
            connection.exec_driver_sql(f'SET ROLE "{indirect_role}"')
            assert connection.execute(text("SELECT current_user")).scalar_one() == indirect_role
            connection.exec_driver_sql("RESET ROLE")

        _run_bootstrap()
        _assert_runtime_identity()
        with runtime.connect() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql(f'SET ROLE "{direct_role}"')
    finally:
        runtime.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'REVOKE "{indirect_role}" FROM "{direct_role}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{direct_role}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{indirect_role}"')
        admin.dispose()
        _run_bootstrap()


def test_runtime_owned_object_blocks_bootstrap_until_explicit_reassignment() -> None:
    table_name = f"runtime_owned_probe_{uuid4().hex}"
    admin = create_engine(_url(ADMIN_USER))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE TABLE public."{table_name}" (id integer)')
            connection.exec_driver_sql(
                f'ALTER TABLE public."{table_name}" OWNER TO caresync_basic_app'
            )

        with pytest.raises(RuntimeError, match="must not own"):
            _assert_runtime_identity()
        rejected = _run_bootstrap(check=False)
        assert rejected.returncode != 0
        assert "owns database objects" in rejected.stderr
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS public."{table_name}"')
        admin.dispose()
        _run_bootstrap()
        _assert_runtime_identity()


def test_public_database_schema_column_sequence_and_function_drift_is_repaired() -> None:
    schema_name = f"runtime_acl_probe_{uuid4().hex}"
    admin = create_engine(_url(ADMIN_USER))
    runtime = create_engine(_url("caresync_basic_app"))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
            connection.exec_driver_sql(f'GRANT CREATE ON SCHEMA "{schema_name}" TO PUBLIC')
            connection.exec_driver_sql(
                f'GRANT CREATE, TEMPORARY ON DATABASE "{TEST_DATABASE}" TO PUBLIC'
            )
            connection.exec_driver_sql(
                "GRANT UPDATE (request_hash) ON TABLE public.childcare_command_receipts TO PUBLIC"
            )
            connection.exec_driver_sql(
                "GRANT UPDATE ON SEQUENCE public.ats_events_sequence_id_seq TO PUBLIC"
            )
            connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION "
                "public.caresync_charge_childcare_reconciliation(uuid,uuid,uuid) "
                "TO PUBLIC"
            )

        with pytest.raises(RuntimeError, match="forbidden effective"):
            _assert_runtime_identity()
        with runtime.connect() as connection:
            assert connection.execute(
                text("SELECT has_database_privilege(current_user,current_database(),'TEMPORARY')")
            ).scalar_one()
            assert connection.execute(
                text("SELECT has_schema_privilege(current_user,:schema_name,'CREATE')"),
                {"schema_name": schema_name},
            ).scalar_one()
            assert connection.execute(
                text(
                    "SELECT has_column_privilege(current_user,"
                    "'public.childcare_command_receipts','request_hash','UPDATE')"
                )
            ).scalar_one()

        _run_bootstrap()
        _assert_runtime_identity()
        with runtime.connect() as connection:
            assert not connection.execute(
                text("SELECT has_database_privilege(current_user,current_database(),'TEMPORARY')")
            ).scalar_one()
            assert not connection.execute(
                text("SELECT has_schema_privilege(current_user,:schema_name,'CREATE')"),
                {"schema_name": schema_name},
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_column_privilege(current_user,"
                    "'public.childcare_command_receipts','request_hash','UPDATE')"
                )
            ).scalar_one()
            assert not connection.execute(
                text(
                    "SELECT has_sequence_privilege(current_user,"
                    "'public.ats_events_sequence_id_seq','UPDATE')"
                )
            ).scalar_one()
    finally:
        runtime.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        admin.dispose()
        _run_bootstrap()


def test_role_configuration_drift_is_detected_even_when_connection_path_is_pinned() -> None:
    admin = create_engine(_url(ADMIN_USER))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql("ALTER ROLE caresync_basic_app SET search_path = public")
            connection.exec_driver_sql(
                f'ALTER ROLE caresync_basic_app IN DATABASE "{TEST_DATABASE}" '
                "SET statement_timeout = '0'"
            )

        with pytest.raises(RuntimeError, match="pinned public,pg_catalog"):
            _assert_runtime_identity()
        _run_bootstrap()
        _assert_runtime_identity()

        with admin.connect() as connection:
            config = connection.execute(
                text("SELECT rolconfig FROM pg_catalog.pg_roles WHERE rolname='caresync_basic_app'")
            ).scalar_one()
            assert [value.replace(" ", "") for value in config] == ["search_path=public,pg_catalog"]
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_catalog.pg_db_role_setting AS setting "
                        "JOIN pg_catalog.pg_roles AS role ON role.oid=setting.setrole "
                        "WHERE role.rolname='caresync_basic_app' "
                        "AND setting.setdatabase<>0"
                    )
                ).scalar_one()
                == 0
            )
    finally:
        admin.dispose()
        _run_bootstrap()


def test_missing_required_runtime_grant_fails_closed_and_is_restored() -> None:
    admin = create_engine(_url(ADMIN_USER))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(
                "REVOKE INSERT ON TABLE public.attendance_events FROM caresync_basic_app"
            )
        with pytest.raises(RuntimeError, match="missing required effective"):
            _assert_runtime_identity()

        _run_bootstrap()
        _assert_runtime_identity()
    finally:
        admin.dispose()
        _run_bootstrap()


def test_temp_and_guard_execute_drift_fail_closed_and_are_repaired() -> None:
    admin = create_engine(_url(ADMIN_USER))
    runtime = create_engine(_url("caresync_basic_app"))
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(
                f'GRANT TEMPORARY ON DATABASE "{TEST_DATABASE}" TO caresync_basic_app'
            )
            connection.exec_driver_sql(
                "GRANT EXECUTE ON FUNCTION public.caresync_childcare_operation_guard() TO PUBLIC"
            )

        with pytest.raises(RuntimeError, match="forbidden effective"):
            _assert_runtime_identity()

        # A pooled runtime session with a temporary object is itself unsafe
        # configuration drift. Bootstrap must refuse it until the session is
        # closed, then remove both TEMP and guard EXECUTE authority.
        with runtime.begin() as connection:
            connection.exec_driver_sql("CREATE TEMP TABLE runtime_configuration_probe (id integer)")
        refused = _run_bootstrap(check=False)
        assert refused.returncode != 0
        assert "owns database objects" in refused.stderr

        runtime.dispose()
        _run_bootstrap()
        _assert_runtime_identity()
        with runtime.connect() as connection:
            assert not connection.execute(
                text(
                    "SELECT has_function_privilege(current_user,"
                    "'public.caresync_childcare_operation_guard()','EXECUTE')"
                )
            ).scalar_one()
            with pytest.raises(DBAPIError):
                connection.exec_driver_sql("CREATE TEMP TABLE exploit_blocked (id integer)")
    finally:
        runtime.dispose()
        admin.dispose()
        _run_bootstrap()
