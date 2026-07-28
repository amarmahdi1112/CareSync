"""Opt-in PostgreSQL 17 tamper proofs for 0032 downstream trigger chains."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

from app.core.config import Settings
from app.db.session import Database

DISPOSABLE_URL_TEXT = os.getenv("BASIC_POSTGRES_TRANSPORT_COMMANDS_TEST_URL")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))

DATABASE_NAME = "caresync"
BASIC_ROLE = "caresync_basic_app"
EVIDENCE_ROLE = "caresync_transport_evidence_ingest"
COMMAND_OWNER_ROLE = "caresync_transport_command_owner"
PROTECTED_PORTS = {5432, 5433, 5434}


def _guard_disposable_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0032 downstream certification requires PostgreSQL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0032 downstream certification requires a loopback host")
    if url.port is None or url.port in PROTECTED_PORTS or not 1 <= url.port <= 65535:
        raise RuntimeError("0032 downstream certification refuses retained or invalid ports")
    if url.database != "postgres" or not url.username:
        raise RuntimeError("0032 downstream URL must target postgres as an admin user")
    return url


ADMIN_CLUSTER_URL = _guard_disposable_url(DISPOSABLE_URL_TEXT) if DISPOSABLE_URL_TEXT else None


def _alembic(action: str, revision: str) -> subprocess.CompletedProcess[str]:
    assert ADMIN_CLUSTER_URL is not None
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": str(ADMIN_CLUSTER_URL.host),
            "DATABASE_PORT": str(ADMIN_CLUSTER_URL.port),
            "DATABASE_USER": str(ADMIN_CLUSTER_URL.username),
            "DATABASE_PASSWORD": str(ADMIN_CLUSTER_URL.password or ""),
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
            "ENABLE_ADVANCED_ROUTES": "false",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _bootstrap() -> subprocess.CompletedProcess[str]:
    assert ADMIN_CLUSTER_URL is not None
    environment = os.environ.copy()
    if ADMIN_CLUSTER_URL.password:
        environment["PGPASSWORD"] = str(ADMIN_CLUSTER_URL.password)
    return subprocess.run(
        [
            str(PSQL),
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(ADMIN_CLUSTER_URL.host),
            "-p",
            str(ADMIN_CLUSTER_URL.port),
            "-U",
            str(ADMIN_CLUSTER_URL.username),
            "-d",
            DATABASE_NAME,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _runtime_settings(*, basic_password: str, evidence_password: str) -> Settings:
    assert ADMIN_CLUSTER_URL is not None
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_name=DATABASE_NAME,
        database_host=str(ADMIN_CLUSTER_URL.host),
        database_port=int(ADMIN_CLUSTER_URL.port or 0),
        database_user=BASIC_ROLE,
        database_password=basic_password,
        transport_evidence_ingest_password=evidence_password,
        database_read_only=False,
        enable_advanced_routes=False,
    )


def _assert_runtime_ready(settings: Settings) -> None:
    runtime = Database(settings)
    try:
        assert runtime.has_transport_registry_commands() is True
    finally:
        runtime.dispose()


def _assert_runtime_and_bootstrap_reject_tamper(
    *,
    settings: Settings,
    bootstrap_marker: str,
) -> None:
    runtime = Database(settings)
    try:
        with pytest.raises(RuntimeError, match="Partial or drifted 0032"):
            runtime.has_transport_registry_commands()
    finally:
        runtime.dispose()
    rejected = _bootstrap()
    assert rejected.returncode != 0
    assert bootstrap_marker in (rejected.stdout + rejected.stderr).lower()


def _exercise_tamper(
    database_admin: Engine,
    *,
    settings: Settings,
    tamper: Callable[[Engine], None],
    restore: Callable[[Engine], None],
    bootstrap_marker: str,
) -> None:
    tamper(database_admin)
    try:
        _assert_runtime_and_bootstrap_reject_tamper(
            settings=settings,
            bootstrap_marker=bootstrap_marker,
        )
    finally:
        restore(database_admin)
    repaired = _bootstrap()
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    _assert_runtime_ready(settings)


@pytest.mark.skipif(
    ADMIN_CLUSTER_URL is None,
    reason=(
        "BASIC_POSTGRES_TRANSPORT_COMMANDS_TEST_URL must name a fresh disposable "
        "loopback PostgreSQL 17 cluster"
    ),
)
def test_0032_downstream_trigger_function_and_policy_tampering_fails_closed() -> None:
    assert ADMIN_CLUSTER_URL is not None
    assert PSQL.is_file(), f"PostgreSQL 17 psql is unavailable at {PSQL}"
    cluster = create_engine(ADMIN_CLUSTER_URL, isolation_level="AUTOCOMMIT")
    database_admin: Engine | None = None
    database_created = False
    role_namespace_owned = False
    basic_password = f"basic-{uuid4().hex}"
    evidence_password = f"ingest-{uuid4().hex}"
    try:
        with cluster.connect() as connection:
            version = int(connection.scalar(text("SHOW server_version_num")))
            assert 170000 <= version < 180000
            assert (
                connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"),
                    {"name": DATABASE_NAME},
                )
                is None
            )
            existing_roles = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=ANY(CAST(:roles AS text[]))"),
                {"roles": [BASIC_ROLE, EVIDENCE_ROLE, COMMAND_OWNER_ROLE]},
            )
            assert existing_roles == 0
            role_namespace_owned = True
            connection.execute(text(f'CREATE DATABASE "{DATABASE_NAME}"'))
            database_created = True

        database_admin = create_engine(ADMIN_CLUSTER_URL.set(database=DATABASE_NAME))
        with database_admin.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        migration = _alembic("upgrade", "head")
        assert migration.returncode == 0, migration.stdout + migration.stderr
        bootstrapped = _bootstrap()
        assert bootstrapped.returncode == 0, bootstrapped.stdout + bootstrapped.stderr
        with cluster.begin() as connection:
            connection.execute(text(f"ALTER ROLE {BASIC_ROLE} PASSWORD '{basic_password}'"))
            connection.execute(text(f"ALTER ROLE {EVIDENCE_ROLE} PASSWORD '{evidence_password}'"))

        settings = _runtime_settings(
            basic_password=basic_password,
            evidence_password=evidence_password,
        )
        _assert_runtime_ready(settings)

        with database_admin.connect() as connection:
            audit_definition = str(
                connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'public.realtime_from_audit_event()'::regprocedure)"
                    )
                )
            )
            notification_definition = str(
                connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'public.user_notification_enqueue_trigger()'::regprocedure)"
                    )
                )
            )
            qualification_review_definition = str(
                connection.scalar(
                    text(
                        "SELECT pg_get_functiondef("
                        "'public.caresync_0032_qualification_review_guard()'::regprocedure)"
                    )
                )
            )
            policy_check = str(
                connection.scalar(
                    text(
                        "SELECT pg_get_expr(polwithcheck,polrelid) FROM pg_policy "
                        "WHERE polrelid='public.user_realtime_events'::regclass "
                        "AND polname='user_realtime_events_context_insert'"
                    )
                )
            )
            users_lock_policy = connection.execute(
                text(
                    "SELECT pg_get_expr(polqual,polrelid),"
                    "pg_get_expr(polwithcheck,polrelid) FROM pg_policy "
                    "WHERE polrelid='public.users'::regclass "
                    "AND polname='users_0032_lock'"
                )
            ).one()

        weakened_review_definition, review_replacements = re.subn(
            r"AND\s+evidence\.recorded_by_user_id<>NEW\.reviewed_by_user_id",
            "AND (evidence.recorded_by_user_id<>NEW.reviewed_by_user_id OR true)",
            qualification_review_definition,
            count=1,
            flags=re.IGNORECASE,
        )
        assert review_replacements == 1

        def weaken_review_source_predicate(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(weakened_review_definition))

        def restore_review_guard(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(qualification_review_definition))

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=weaken_review_source_predicate,
            restore=restore_review_guard,
            bootstrap_marker="canonical repository function identity audit failed",
        )

        def make_guard_replica_only(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE staff_driver_qualification_review_decisions "
                        "ENABLE REPLICA TRIGGER "
                        "staff_driver_qualification_review_insert_guard"
                    )
                )

        def restore_guard_origin_enabled(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE staff_driver_qualification_review_decisions "
                        "ENABLE TRIGGER staff_driver_qualification_review_insert_guard"
                    )
                )

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=make_guard_replica_only,
            restore=restore_guard_origin_enabled,
            bootstrap_marker="canonical protected trigger topology audit failed",
        )

        def add_protected_table_trigger(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TRIGGER zzz_caresync_test_0032_extra_receipt "
                        "BEFORE INSERT ON transport_registry_command_receipts "
                        "FOR EACH ROW EXECUTE FUNCTION public.caresync_0032_receipt_guard()"
                    )
                )

        def remove_protected_table_trigger(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP TRIGGER IF EXISTS zzz_caresync_test_0032_extra_receipt "
                        "ON transport_registry_command_receipts"
                    )
                )

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=add_protected_table_trigger,
            restore=remove_protected_table_trigger,
            bootstrap_marker="canonical protected trigger topology audit failed",
        )

        def weaken_context_lock_policy(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER POLICY users_0032_lock ON users "
                        "USING (true) WITH CHECK (false)"
                    )
                )

        def restore_context_lock_policy(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER POLICY users_0032_lock ON users "
                        f"USING ({users_lock_policy[0]}) "
                        f"WITH CHECK ({users_lock_policy[1]})"
                    )
                )

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=weaken_context_lock_policy,
            restore=restore_context_lock_policy,
            bootstrap_marker="context row-lock policy audit failed",
        )

        leaked_audit_definition, audit_replacements = re.subn(
            r"('transport_registry'\s*,\s*)NULL(\s*,\s*NEW\.occurred_at)",
            r"\1NEW.entity_id\2",
            audit_definition,
            count=1,
            flags=re.IGNORECASE,
        )
        assert audit_replacements == 1

        def leak_transport_result_id(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(leaked_audit_definition))

        def restore_audit_bridge(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(audit_definition))

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=leak_transport_result_id,
            restore=restore_audit_bridge,
            bootstrap_marker="generic audit realtime bridge audit failed",
        )

        no_raise_definition, raise_replacements = re.subn(
            r"\bRAISE\s*;",
            "NULL;",
            notification_definition,
            count=1,
            flags=re.IGNORECASE,
        )
        assert raise_replacements == 1

        def remove_notification_reraise(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(no_raise_definition))

        def restore_notification_function(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(text(notification_definition))

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=remove_notification_reraise,
            restore=restore_notification_function,
            bootstrap_marker="user notification downstream trigger audit failed",
        )

        def disable_notification_trigger(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE user_notifications DISABLE TRIGGER "
                        "user_notifications_push_realtime"
                    )
                )

        def enable_notification_trigger(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE user_notifications ENABLE TRIGGER "
                        "user_notifications_push_realtime"
                    )
                )

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=disable_notification_trigger,
            restore=enable_notification_trigger,
            bootstrap_marker="user notification downstream trigger audit failed",
        )

        def drift_context_policy(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER POLICY user_realtime_events_context_insert "
                        "ON user_realtime_events WITH CHECK (user_id IS NOT NULL)"
                    )
                )

        def restore_context_policy(engine: Engine) -> None:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER POLICY user_realtime_events_context_insert "
                        f"ON user_realtime_events WITH CHECK ({policy_check})"
                    )
                )

        _exercise_tamper(
            database_admin,
            settings=settings,
            tamper=drift_context_policy,
            restore=restore_context_policy,
            bootstrap_marker="downstream rls insert policy audit failed",
        )
    finally:
        if database_admin is not None:
            database_admin.dispose()
        if database_created:
            with cluster.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname=:name AND pid<>pg_backend_pid()"
                    ),
                    {"name": DATABASE_NAME},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"'))
        if role_namespace_owned:
            with cluster.connect() as connection:
                for role in (EVIDENCE_ROLE, BASIC_ROLE, COMMAND_OWNER_ROLE):
                    connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        cluster.dispose()
