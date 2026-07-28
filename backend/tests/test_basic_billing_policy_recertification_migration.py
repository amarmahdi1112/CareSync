"""Focused proofs for the frozen 0042 billing-policy recertification."""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from alembic import command
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0041_live_room_presence"
CURRENT_REVISION = "0042_billing_policy_recert"
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "0042_billing_policy_recertification.py"
)
POSTGRES_ADMIN_URL_TEXT = os.getenv(
    "BASIC_POSTGRES_BILLING_POLICY_0042_TEST_URL"
)
PROTECTED_POSTGRES_PORTS = {5432, 5433, 5434, 56641}
POSTGRES_DATABASE = "caresync_0042_policy_proof"
POSTGRES_RESTORE_DATABASE = "caresync_0042_policy_restore"
POSTGRES_MIGRATION_ROLE = "caresync_0042_policy_migration"
POSTGRES_MIGRATION_PASSWORD = "caresync-0042-disposable-policy-proof"
PG_DUMP = Path("/opt/homebrew/opt/postgresql@17/bin/pg_dump")
PG_RESTORE = Path("/opt/homebrew/opt/postgresql@17/bin/pg_restore")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "billing_policy_recertification_0042",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guard_postgres_admin_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0042 proof requires PostgreSQL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0042 proof requires a disposable loopback cluster")
    if (
        url.port is None
        or url.port in PROTECTED_POSTGRES_PORTS
        or not 1 <= url.port <= 65535
    ):
        raise RuntimeError("0042 proof refuses retained or invalid ports")
    if url.database != "postgres" or not url.username:
        raise RuntimeError("0042 proof URL must target postgres as an admin")
    return url


POSTGRES_ADMIN_URL = (
    _guard_postgres_admin_url(POSTGRES_ADMIN_URL_TEXT)
    if POSTGRES_ADMIN_URL_TEXT
    else None
)


def _postgres_url(
    *,
    database: str,
    migration_role: bool = False,
) -> URL:
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


def _postgres_config(database: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        _postgres_url(
            database=database,
            migration_role=True,
        ).render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _runtime_database(database: str) -> Database:
    assert POSTGRES_ADMIN_URL is not None
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=str(POSTGRES_ADMIN_URL.host),
        database_port=int(POSTGRES_ADMIN_URL.port or 0),
        database_user=POSTGRES_MIGRATION_ROLE,
        database_password=POSTGRES_MIGRATION_PASSWORD,
        database_name="caresync",
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="billing-policy-0042-runtime-proof-secret",
    )
    # The application validator deliberately preserves the retained production
    # database name. This isolated proof uses a uniquely named disposable
    # database and redirects the already-validated settings object only after
    # the protected target guard above has approved it.
    settings.database_name = database
    return Database(settings)


def _postgres_policy_rows(connection) -> list:
    module = _load_migration_module()
    return list(
        connection.execute(
            sa.text(
                "SELECT class.relname AS table_name,policy.polname AS policy_name,"
                "policy.polcmd AS command,policy.polpermissive AS permissive,"
                "policy.polroles AS roles,"
                "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                "AS using_expression,"
                "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                "AS check_expression "
                "FROM pg_catalog.pg_policy policy "
                "JOIN pg_catalog.pg_class class ON class.oid=policy.polrelid "
                "JOIN pg_catalog.pg_namespace namespace "
                "ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND class.relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": sorted(module.POLICY_TABLES)},
        )
    )


def _config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.delenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", raising=False)
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _sqlite_schema_without_revision(database_path: Path) -> list[tuple]:
    with sqlite3.connect(database_path) as connection:
        return list(
            connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND name<>'alembic_version' "
                "ORDER BY type,name"
            )
        )


def _profile_rows(module, profile: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for (table, policy), (command_name, kind) in module._policy_specs().items():
        expression = profile[kind]
        rows.append(
            {
                "table_name": table,
                "policy_name": policy,
                "command": command_name,
                "permissive": True,
                "roles": [0],
                "using_expression": expression if command_name == "r" else None,
                "check_expression": expression if command_name == "a" else None,
            }
        )
    return rows


def test_revision_is_linear_frozen_and_defines_exact_policy_catalog() -> None:
    module = _load_migration_module()

    assert module.revision == CURRENT_REVISION
    assert module.down_revision == PREVIOUS_REVISION
    assert module.branch_labels is None
    assert module.depends_on is None
    assert module.POSTGRESQL_MAJOR_VERSION == 17
    assert len(module.POLICY_TABLES) == 19
    assert len(module._policy_specs()) == 36
    assert len(module._create_policy_statements()) == 36

    created = set()
    for statement in module._create_policy_statements():
        match = re.fullmatch(
            r"CREATE POLICY ([a-z0-9_]+) ON public\.([a-z0-9_]+) "
            r"FOR (SELECT|INSERT) .+",
            statement,
        )
        assert match is not None, statement
        policy_name, table, command_name = match.groups()
        created.add((table, policy_name))
        assert table in module.POLICY_TABLES
        if command_name == "SELECT":
            assert " USING (" in statement
            assert " WITH CHECK (" not in statement
        else:
            assert " WITH CHECK (" in statement
            assert " USING (" not in statement
        assert "USING (true)" not in statement
        assert "WITH CHECK (true)" not in statement

    assert created == set(module._policy_specs())
    assert set(module.PROFILE_A_HASHES) == set(module.PROFILE_B_HASHES)
    assert all(
        len(value) == 64
        for profile in (module.PROFILE_A_HASHES, module.PROFILE_B_HASHES)
        for value in profile.values()
    )


def test_whole_catalog_preflight_accepts_only_profile_a_or_profile_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration_module()
    monkeypatch.setattr(module, "_canonical_sql_sha256", lambda value: value)

    profile_a_rows = _profile_rows(module, module.PROFILE_A_HASHES)
    profile_b_rows = _profile_rows(module, module.PROFILE_B_HASHES)
    assert module._classify_policy_rows(profile_a_rows) == "A"
    assert module._classify_policy_rows(profile_b_rows) == "B"

    mixed_rows = _profile_rows(module, module.PROFILE_A_HASHES)
    mixed_rows[0]["using_expression"] = module.PROFILE_B_HASHES["select"]
    with pytest.raises(
        module.BillingPolicyRecertificationError,
        match="unknown or mixed",
    ):
        module._classify_policy_rows(mixed_rows)

    unknown_rows = _profile_rows(module, module.PROFILE_A_HASHES)
    unknown_rows[-1]["check_expression"] = "f" * 64
    with pytest.raises(
        module.BillingPolicyRecertificationError,
        match="unknown or mixed",
    ):
        module._classify_policy_rows(unknown_rows)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda rows: rows.pop(),
            "exact 36-policy catalog",
        ),
        (
            lambda rows: rows[0].__setitem__("command", "a"),
            "noncanonical policy shape",
        ),
        (
            lambda rows: rows[0].__setitem__("permissive", False),
            "noncanonical policy shape",
        ),
        (
            lambda rows: rows[0].__setitem__("roles", [1234]),
            "noncanonical policy shape",
        ),
        (
            lambda rows: rows[0].__setitem__(
                "check_expression",
                rows[0]["using_expression"],
            ),
            "noncanonical policy shape",
        ),
    ],
)
def test_preflight_rejects_missing_or_weakened_policy_shapes(
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    message: str,
) -> None:
    module = _load_migration_module()
    monkeypatch.setattr(module, "_canonical_sql_sha256", lambda value: value)
    rows = _profile_rows(module, module.PROFILE_A_HASHES)
    mutation(rows)
    with pytest.raises(module.BillingPolicyRecertificationError, match=message):
        module._classify_policy_rows(rows)


def test_lock_order_is_deterministic_and_uses_required_strengths() -> None:
    module = _load_migration_module()

    class RecordingBind:
        statements: list[str]

        def __init__(self) -> None:
            self.statements = []

        def exec_driver_sql(self, statement: str) -> None:
            self.statements.append(statement)

    bind = RecordingBind()
    module._lock_catalog_boundary(bind)

    assert bind.statements == [
        "LOCK TABLE "
        + ",".join(
            f"public.{table}" for table in sorted(module.REFERENCE_TABLES)
        )
        + " IN ACCESS SHARE MODE",
        "LOCK TABLE "
        + ",".join(
            f"public.{table}" for table in sorted(module.POLICY_TABLES)
        )
        + " IN ACCESS EXCLUSIVE MODE",
    ]


def test_sqlite_upgrade_and_downgrade_are_true_noops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    before = _sqlite_schema_without_revision(database_path)

    command.upgrade(config, CURRENT_REVISION)
    assert _sqlite_schema_without_revision(database_path) == before
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (CURRENT_REVISION,)

    command.downgrade(config, PREVIOUS_REVISION)
    assert _sqlite_schema_without_revision(database_path) == before
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (PREVIOUS_REVISION,)


def test_direct_sqlite_calls_emit_no_catalog_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration_module()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    module.upgrade()
    module.downgrade()


def test_security_preserving_downgrade_validates_a_without_replacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration_module()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    calls: list[str] = []
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        module,
        "_prepare_postgresql_boundary",
        lambda actual: calls.append("prepare"),
    )
    monkeypatch.setattr(
        module,
        "_catalog_policy_rows",
        lambda actual: [object()],
    )
    monkeypatch.setattr(
        module,
        "_classify_policy_rows",
        lambda rows: "A",
    )
    monkeypatch.setattr(
        module,
        "_replace_policies",
        lambda actual: calls.append("replace"),
    )

    module.downgrade()
    assert calls == ["prepare"]


def test_upgrade_preflights_replaces_and_recertifies_exact_profile_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_migration_module()
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    calls: list[str] = []
    catalog_reads = iter(("B rows", "A rows"))
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        module,
        "_prepare_postgresql_boundary",
        lambda actual: calls.append("prepare"),
    )
    monkeypatch.setattr(
        module,
        "_catalog_policy_rows",
        lambda actual: next(catalog_reads),
    )
    monkeypatch.setattr(
        module,
        "_classify_policy_rows",
        lambda rows: calls.append(f"classify {rows}") or rows[0],
    )
    monkeypatch.setattr(
        module,
        "_replace_policies",
        lambda actual: calls.append("replace"),
    )
    monkeypatch.setattr(
        module,
        "_require_owned_hardened_relations",
        lambda actual: calls.append("postflight relations"),
    )

    module.upgrade()
    assert calls == [
        "prepare",
        "classify B rows",
        "replace",
        "postflight relations",
        "classify A rows",
    ]


@pytest.mark.skipif(
    POSTGRES_ADMIN_URL is None,
    reason=(
        "BASIC_POSTGRES_BILLING_POLICY_0042_TEST_URL must name a fresh "
        "disposable loopback PostgreSQL 17 cluster"
    ),
)
def test_postgres_17_recertification_tamper_downgrade_and_dump_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_ADMIN_URL is not None
    module = _load_migration_module()
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    admin = create_engine(
        _postgres_url(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    created_databases: set[str] = set()
    role_created = False
    dump_path: Path | None = None
    try:
        with admin.connect() as connection:
            assert int(
                connection.scalar(sa.text("SHOW server_version_num"))
            ) // 10000 == 17
            assert bool(
                connection.scalar(
                    sa.text(
                        "SELECT rolsuper FROM pg_catalog.pg_roles "
                        "WHERE rolname=current_user"
                    )
                )
            )
            occupied_databases = set(
                connection.execute(
                    sa.text(
                        "SELECT datname FROM pg_catalog.pg_database "
                        "WHERE datname=ANY(CAST(:names AS text[]))"
                    ),
                    {
                        "names": [
                            POSTGRES_DATABASE,
                            POSTGRES_RESTORE_DATABASE,
                        ]
                    },
                ).scalars()
            )
            occupied_role = connection.scalar(
                sa.text(
                    "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=:role"
                ),
                {"role": POSTGRES_MIGRATION_ROLE},
            )
            assert not occupied_databases
            assert occupied_role is None
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
            created_databases.add(POSTGRES_DATABASE)

        command.upgrade(_postgres_config(POSTGRES_DATABASE), PREVIOUS_REVISION)
        database = create_engine(
            _postgres_url(
                database=POSTGRES_DATABASE,
                migration_role=True,
            )
        )
        try:
            with database.connect() as connection:
                assert (
                    module._classify_policy_rows(
                        _postgres_policy_rows(connection)
                    )
                    == "A"
                )
                before_counts = {
                    table: int(
                        connection.scalar(
                            sa.text(f"SELECT count(*) FROM public.{table}")
                        )
                        or 0
                    )
                    for table in module.POLICY_TABLES
                }

            with database.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER POLICY billing_accounts_0033_select "
                    "ON public.billing_accounts USING (true)"
                )
            with pytest.raises(Exception, match="0042 billing-policy"):
                command.upgrade(
                    _postgres_config(POSTGRES_DATABASE),
                    CURRENT_REVISION,
                )
            with database.connect() as connection:
                assert connection.scalar(
                    sa.text("SELECT version_num FROM alembic_version")
                ) == PREVIOUS_REVISION
                tampered_rows = _postgres_policy_rows(connection)
                with pytest.raises(
                    module.BillingPolicyRecertificationError,
                    match="unknown or mixed",
                ):
                    module._classify_policy_rows(tampered_rows)

            with database.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER POLICY billing_accounts_0033_select "
                    "ON public.billing_accounts USING "
                    f"({module._allowed('billing:read')})"
                )
            command.upgrade(
                _postgres_config(POSTGRES_DATABASE),
                CURRENT_REVISION,
            )
            with database.connect() as connection:
                assert (
                    module._classify_policy_rows(
                        _postgres_policy_rows(connection)
                    )
                    == "A"
                )
                assert {
                    table: int(
                        connection.scalar(
                            sa.text(f"SELECT count(*) FROM public.{table}")
                        )
                        or 0
                    )
                    for table in module.POLICY_TABLES
                } == before_counts
            canonical_runtime = _runtime_database(POSTGRES_DATABASE)
            try:
                assert canonical_runtime.has_billing_ledger() is True
            finally:
                canonical_runtime.dispose()

            # A downgrade never drops or loosens the policies.  Drifted profile
            # A is refused; restored A moves only the Alembic marker.
            with database.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER POLICY billing_accounts_0033_select "
                    "ON public.billing_accounts USING (true)"
                )
            with pytest.raises(Exception, match="0042 billing-policy"):
                command.downgrade(
                    _postgres_config(POSTGRES_DATABASE),
                    PREVIOUS_REVISION,
                )
            with database.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER POLICY billing_accounts_0033_select "
                    "ON public.billing_accounts USING "
                    f"({module._allowed('billing:read')})"
                )

            proof_directory = Path(
                os.getenv("CARESYNC_0042_PROOF_DIR", str(tmp_path))
            )
            proof_directory.mkdir(parents=True, exist_ok=True)
            dump_path = proof_directory / "caresync-0042-policy.dump"
            dump_environment = {
                **os.environ,
                "PGPASSWORD": str(POSTGRES_ADMIN_URL.password or ""),
            }
            dump = subprocess.run(
                [
                    str(PG_DUMP),
                    "-Fc",
                    "--no-owner",
                    "-h",
                    str(POSTGRES_ADMIN_URL.host),
                    "-p",
                    str(POSTGRES_ADMIN_URL.port),
                    "-U",
                    str(POSTGRES_ADMIN_URL.username),
                    "-d",
                    POSTGRES_DATABASE,
                    "-f",
                    str(dump_path),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=dump_environment,
            )
            assert dump.returncode == 0, dump.stderr

            with admin.connect() as connection:
                connection.exec_driver_sql(
                    f"CREATE DATABASE {POSTGRES_RESTORE_DATABASE} "
                    f"OWNER {POSTGRES_MIGRATION_ROLE}"
                )
                created_databases.add(POSTGRES_RESTORE_DATABASE)
            restore_environment = {
                **os.environ,
                "PGPASSWORD": POSTGRES_MIGRATION_PASSWORD,
            }
            restore = subprocess.run(
                [
                    str(PG_RESTORE),
                    "--no-owner",
                    "--exit-on-error",
                    "-h",
                    str(POSTGRES_ADMIN_URL.host),
                    "-p",
                    str(POSTGRES_ADMIN_URL.port),
                    "-U",
                    POSTGRES_MIGRATION_ROLE,
                    "-d",
                    POSTGRES_RESTORE_DATABASE,
                    str(dump_path),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=restore_environment,
            )
            assert restore.returncode == 0, restore.stderr
            restored = create_engine(
                _postgres_url(
                    database=POSTGRES_RESTORE_DATABASE,
                    migration_role=True,
                )
            )
            try:
                with restored.connect() as connection:
                    assert connection.scalar(
                        sa.text("SELECT version_num FROM alembic_version")
                    ) == CURRENT_REVISION
                    assert (
                        module._classify_policy_rows(
                            _postgres_policy_rows(connection)
                        )
                        == "B"
                    )
                restored_runtime = _runtime_database(
                    POSTGRES_RESTORE_DATABASE
                )
                try:
                    assert restored_runtime.has_billing_ledger() is True
                finally:
                    restored_runtime.dispose()
                # pg_dump emits PostgreSQL's expanded catalog form.  Restoring
                # exact profile A therefore yields audited whole profile B.
                # Replaying the policy-only revision from a disposable 0041
                # marker proves that the real B catalog is accepted and
                # canonicalized back to A.
                command.stamp(
                    _postgres_config(POSTGRES_RESTORE_DATABASE),
                    PREVIOUS_REVISION,
                )
                command.upgrade(
                    _postgres_config(POSTGRES_RESTORE_DATABASE),
                    CURRENT_REVISION,
                )
                with restored.connect() as connection:
                    assert (
                        module._classify_policy_rows(
                            _postgres_policy_rows(connection)
                        )
                        == "A"
                    )
            finally:
                restored.dispose()

            command.downgrade(
                _postgres_config(POSTGRES_DATABASE),
                PREVIOUS_REVISION,
            )
            with database.connect() as connection:
                assert connection.scalar(
                    sa.text("SELECT version_num FROM alembic_version")
                ) == PREVIOUS_REVISION
                assert (
                    module._classify_policy_rows(
                        _postgres_policy_rows(connection)
                    )
                    == "A"
                )
        finally:
            database.dispose()
    finally:
        with admin.connect() as connection:
            for database_name in sorted(created_databases, reverse=True):
                connection.execute(
                    sa.text(
                        "SELECT pg_catalog.pg_terminate_backend(pid) "
                        "FROM pg_catalog.pg_stat_activity "
                        "WHERE datname=:database AND pid<>pg_backend_pid()"
                    ),
                    {"database": database_name},
                )
                connection.exec_driver_sql(
                    f"DROP DATABASE IF EXISTS {database_name}"
                )
            if role_created:
                connection.exec_driver_sql(
                    f"DROP ROLE IF EXISTS {POSTGRES_MIGRATION_ROLE}"
                )
        admin.dispose()
        if dump_path is not None:
            dump_path.unlink(missing_ok=True)
