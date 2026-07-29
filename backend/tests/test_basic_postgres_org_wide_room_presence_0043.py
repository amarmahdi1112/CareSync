"""PostgreSQL 17 round-trip proof for the additive 0043 presence guard.

The proof is opt-in and accepts only an administrator URL for a disposable
loopback cluster. It owns and removes one uniquely named database and role.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "0043_org_wide_room_presence.py"
)
PREVIOUS_REVISION = "0042_billing_policy_recert"
CURRENT_REVISION = "0043_org_wide_room_presence"
POSTGRES_ADMIN_URL_TEXT = os.getenv(
    "BASIC_POSTGRES_ORG_WIDE_ROOM_PRESENCE_0043_TEST_URL"
)
PROTECTED_POSTGRES_PORTS = {5432, 5433, 5434}
POSTGRES_DATABASE = "caresync_0043_presence_proof"
POSTGRES_MIGRATION_ROLE = "caresync_0043_presence_migration"
POSTGRES_MIGRATION_PASSWORD = "caresync-0043-disposable-presence-proof"
RUNTIME_ROLE = "caresync_basic_app"
PREVIOUS_GUARD_FINGERPRINT = "7f3c407496dbae87792b7c805b5e45b8"
CURRENT_GUARD_FINGERPRINT = "7324cc1ec57481f779d8f7b8e5b8e841"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "org_wide_room_presence_0043",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guard_postgres_admin_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0043 presence proof requires PostgreSQL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "0043 presence proof requires a disposable loopback cluster"
        )
    if (
        url.port is None
        or url.port in PROTECTED_POSTGRES_PORTS
        or not 1 <= url.port <= 65535
    ):
        raise RuntimeError("0043 presence proof refuses retained or invalid ports")
    if url.database != "postgres" or not url.username:
        raise RuntimeError(
            "0043 presence proof URL must target postgres as an administrator"
        )
    return url


POSTGRES_ADMIN_URL = (
    _guard_postgres_admin_url(POSTGRES_ADMIN_URL_TEXT)
    if POSTGRES_ADMIN_URL_TEXT
    else None
)


def _postgres_url(*, database: str, migration_role: bool = False) -> URL:
    assert POSTGRES_ADMIN_URL is not None
    return URL.create(
        "postgresql+psycopg",
        username=(
            POSTGRES_MIGRATION_ROLE
            if migration_role
            else POSTGRES_ADMIN_URL.username
        ),
        password=(
            POSTGRES_MIGRATION_PASSWORD
            if migration_role
            else POSTGRES_ADMIN_URL.password
        ),
        host=POSTGRES_ADMIN_URL.host,
        port=POSTGRES_ADMIN_URL.port,
        database=database,
    )


def _postgres_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        _postgres_url(
            database=POSTGRES_DATABASE,
            migration_role=True,
        )
        .render_as_string(hide_password=False)
        .replace("%", "%%"),
    )
    return config


def _guard_fingerprint(connection: sa.Connection) -> str:
    return str(
        connection.scalar(
            sa.text(
                "SELECT pg_catalog.md5("
                "pg_catalog.replace("
                "pg_catalog.regexp_replace("
                "pg_catalog.lower(procedure.prosrc),"
                "'[[:space:]]','','g'"
                "),"
                "'\"',''"
                ")"
                ") "
                "FROM pg_catalog.pg_proc AS procedure "
                "WHERE procedure.oid="
                "'public.caresync_0041_presence_row_guard()'"
                "::pg_catalog.regprocedure"
            )
        )
    )


def _assert_revision_and_guard(
    connection: sa.Connection,
    *,
    revision: str,
    fingerprint: str,
) -> None:
    assert connection.scalar(
        sa.text("SELECT version_num FROM public.alembic_version")
    ) == revision
    assert _guard_fingerprint(connection) == fingerprint
    assert connection.scalar(
        sa.text(
            "SELECT NOT pg_catalog.has_function_privilege("
            "'public',"
            "'public.caresync_0041_presence_row_guard()',"
            "'EXECUTE'"
            ")"
        )
    )


@pytest.mark.skipif(
    POSTGRES_ADMIN_URL is None,
    reason=(
        "BASIC_POSTGRES_ORG_WIDE_ROOM_PRESENCE_0043_TEST_URL must name "
        "a fresh disposable loopback PostgreSQL 17 cluster"
    ),
)
def test_postgres_17_upgrade_downgrade_reupgrade_without_runtime_role() -> None:
    assert POSTGRES_ADMIN_URL is not None
    module = _load_migration_module()
    assert module._source_sha256(module._POSTGRES_GUARD_SOURCE_0041) == (
        "c2885e959f4b68c8ac0cdbd3e1a0"
        "76a00849cb7aa643d90ff3c4db954379c2ce"
    )
    assert module._source_sha256(module._POSTGRES_GUARD_SOURCE_0043) == (
        "184a58df0881eaec6593da4f82193"
        "877bac79179ea3e26bc37bbef724e595390"
    )

    admin = create_engine(
        _postgres_url(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    database = None
    role_created = False
    database_created = False
    try:
        with admin.connect() as connection:
            assert int(connection.scalar(sa.text("SHOW server_version_num"))) // 10000 == 17
            assert connection.scalar(
                sa.text(
                    "SELECT rolsuper FROM pg_catalog.pg_roles "
                    "WHERE rolname=current_user"
                )
            )
            assert connection.scalar(
                sa.text(
                    "SELECT 1 FROM pg_catalog.pg_database WHERE datname=:name"
                ),
                {"name": POSTGRES_DATABASE},
            ) is None
            assert connection.scalar(
                sa.text("SELECT pg_catalog.to_regrole(:role)"),
                {"role": POSTGRES_MIGRATION_ROLE},
            ) is None
            assert connection.scalar(
                sa.text("SELECT pg_catalog.to_regrole(:role)"),
                {"role": RUNTIME_ROLE},
            ) is None
            connection.exec_driver_sql(
                f"CREATE ROLE {POSTGRES_MIGRATION_ROLE} LOGIN PASSWORD "
                f"'{POSTGRES_MIGRATION_PASSWORD}' NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOINHERIT BYPASSRLS"
            )
            role_created = True
            connection.exec_driver_sql(
                f"CREATE DATABASE {POSTGRES_DATABASE} "
                f"OWNER {POSTGRES_MIGRATION_ROLE}"
            )
            database_created = True

        config = _postgres_config()
        command.upgrade(config, PREVIOUS_REVISION)
        database = create_engine(
            _postgres_url(
                database=POSTGRES_DATABASE,
                migration_role=True,
            )
        )
        with database.connect() as connection:
            _assert_revision_and_guard(
                connection,
                revision=PREVIOUS_REVISION,
                fingerprint=PREVIOUS_GUARD_FINGERPRINT,
            )

        command.upgrade(config, CURRENT_REVISION)
        with database.connect() as connection:
            _assert_revision_and_guard(
                connection,
                revision=CURRENT_REVISION,
                fingerprint=CURRENT_GUARD_FINGERPRINT,
            )

        command.downgrade(config, PREVIOUS_REVISION)
        with database.connect() as connection:
            _assert_revision_and_guard(
                connection,
                revision=PREVIOUS_REVISION,
                fingerprint=PREVIOUS_GUARD_FINGERPRINT,
            )

        command.upgrade(config, CURRENT_REVISION)
        with database.connect() as connection:
            _assert_revision_and_guard(
                connection,
                revision=CURRENT_REVISION,
                fingerprint=CURRENT_GUARD_FINGERPRINT,
            )

        with admin.connect() as connection:
            assert connection.scalar(
                sa.text("SELECT pg_catalog.to_regrole(:role)"),
                {"role": RUNTIME_ROLE},
            ) is None
    finally:
        if database is not None:
            database.dispose()
        with admin.connect() as connection:
            if database_created:
                connection.execute(
                    sa.text(
                        "SELECT pg_catalog.pg_terminate_backend(pid) "
                        "FROM pg_catalog.pg_stat_activity "
                        "WHERE datname=:database AND pid<>pg_backend_pid()"
                    ),
                    {"database": POSTGRES_DATABASE},
                )
                connection.exec_driver_sql(
                    f"DROP DATABASE IF EXISTS {POSTGRES_DATABASE}"
                )
            if role_created:
                connection.exec_driver_sql(
                    f"DROP ROLE IF EXISTS {POSTGRES_MIGRATION_ROLE}"
                )
        admin.dispose()
