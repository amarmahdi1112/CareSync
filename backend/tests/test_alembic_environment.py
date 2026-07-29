"""Alembic environment trust-boundary regression tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_TARGET_OPT_IN = "CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET"


def _postgres_environment(*, environment_name: str, port: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop(PROTECTED_TARGET_OPT_IN, None)
    environment.update(
        {
            "ENVIRONMENT": environment_name,
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": "127.0.0.1",
            "DATABASE_PORT": port,
            "DATABASE_USER": "migration_owner",
            "DATABASE_PASSWORD": "migration-password-must-not-leak",
            "DATABASE_NAME": "caresync",
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )
    return environment


def test_programmatic_sqlalchemy_url_override_precedes_retained_environment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "explicit-override.db"
    environment = os.environ.copy()
    environment.pop(PROTECTED_TARGET_OPT_IN, None)
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": "127.0.0.1",
            "DATABASE_PORT": "9",
            "DATABASE_USER": "unreachable",
            "DATABASE_PASSWORD": "",
            "DATABASE_NAME": "caresync",
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
            "OVERRIDE_DATABASE_PATH": str(database_path),
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "from alembic import command; "
                "from alembic.config import Config; "
                "config = Config('alembic.ini'); "
                "config.set_main_option('sqlalchemy.url', "
                "'sqlite:///' + os.environ['OVERRIDE_DATABASE_PATH']); "
                "command.stamp(config, 'base')"
            ),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE type='table' AND name='alembic_version'"
        ).fetchone() == (1,)


@pytest.mark.parametrize("port", ["5432", "5433", "5434"])
def test_development_refuses_protected_local_postgres_without_opt_in(port: str) -> None:
    environment = _postgres_environment(environment_name="development", port=port)
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Refusing to run Alembic against a protected local PostgreSQL port" in completed.stderr
    assert f"{PROTECTED_TARGET_OPT_IN}=true" in completed.stderr
    assert "migration-password-must-not-leak" not in completed.stdout
    assert "migration-password-must-not-leak" not in completed.stderr


def test_test_environment_refuses_protected_port_even_with_opt_in() -> None:
    environment = _postgres_environment(environment_name="test", port="5434")
    environment[PROTECTED_TARGET_OPT_IN] = "true"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Refusing to run a test migration against a protected local PostgreSQL port" in (
        completed.stderr
    )
    assert "migration-password-must-not-leak" not in completed.stdout
    assert "migration-password-must-not-leak" not in completed.stderr


def test_unix_socket_query_reaches_the_alembic_engine_without_double_escaping(
    tmp_path: Path,
) -> None:
    socket_directory = tmp_path / "missing-postgres-socket"
    environment = _postgres_environment(
        environment_name="development",
        port="5432",
    )
    environment["DATABASE_HOST"] = str(socket_directory)
    environment[PROTECTED_TARGET_OPT_IN] = "true"

    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert str(socket_directory) in completed.stderr
    assert f"%{socket_directory}" not in completed.stderr
    assert "migration-password-must-not-leak" not in completed.stdout
    assert "migration-password-must-not-leak" not in completed.stderr


def test_explicit_opt_in_allows_offline_protected_target_without_connecting() -> None:
    environment = _postgres_environment(environment_name="development", port="5434")
    environment[PROTECTED_TARGET_OPT_IN] = "true"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", "base", "--sql"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "SET LOCAL search_path TO public, pg_catalog;" in completed.stdout
    assert "migration-password-must-not-leak" not in completed.stdout
    assert "migration-password-must-not-leak" not in completed.stderr


def test_postgres_offline_sql_sets_transaction_scoped_trusted_search_path() -> None:
    environment = _postgres_environment(environment_name="test", port="55436")
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", "base", "--sql"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    sql = completed.stdout
    begin = sql.index("BEGIN;")
    trusted_path = sql.index("SET LOCAL search_path TO public, pg_catalog;")
    mutation = sql.index("DROP TABLE alembic_version;")
    commit = sql.index("COMMIT;")
    assert begin < trusted_path < mutation < commit
