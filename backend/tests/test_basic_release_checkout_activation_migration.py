"""Structural and no-auto-cutover proofs for revision 0035."""

from __future__ import annotations

import sqlite3
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from tests.test_basic_family_release_context_api import (
    BACKEND_ROOT,
    _application,
    _facility_tree,
    _register,
)

PREVIOUS_REVISION = "0034_transport_role_permissions"
CURRENT_REVISION = "0035_release_checkout_activation"
MIGRATION_PATH = (
    BACKEND_ROOT / "alembic" / "versions" / "0035_release_checkout_activation.py"
)
BOOTSTRAP_PATH = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
FUNCTION_SIGNATURE = (
    "public.caresync_release_checkout_activate_facility("
    "uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)"
)


def _config(tmp_path, monkeypatch) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _postgres_statements(monkeypatch) -> list[str]:
    spec = spec_from_file_location("release_activation_0035", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = []
    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(module.op, "execute", lambda statement: statements.append(str(statement)))
    module.upgrade()
    return statements


def test_existing_facility_is_not_automatically_activated(tmp_path, monkeypatch) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    application = _application(database_path)
    with TestClient(application) as client:
        _, headers = _register(client, suffix="activation-migration")
        facility, _, _ = _facility_tree(client, headers)

    command.upgrade(config, CURRENT_REVISION)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            CURRENT_REVISION
        )
        assert connection.execute(
            "SELECT count(*) FROM facility_release_checkout_activations "
            "WHERE facility_id=?",
            (facility["id"],),
        ).fetchone()[0] == 0


def test_postgres_writer_is_narrow_derived_and_confirmation_bound(monkeypatch) -> None:
    sql = "\n".join(_postgres_statements(monkeypatch))
    assert f"CREATE FUNCTION {FUNCTION_SIGNATURE.split('(')[0]}" in sql
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = pg_catalog, public" in sql
    assert "current_setting('app.current_organization_id', true)" in sql
    assert "current_setting('app.current_user_id', true)" in sql
    assert "actor_role.key IN ('owner','administrator')" in sql
    assert "requested_confirmation_text <> 'ACTIVATE VERIFIED RELEASE CHECKOUT'" in sql
    assert "authority_records_reviewed IS DISTINCT FROM true" in sql
    assert "legacy_checkout_closure_understood IS DISTINCT FROM true" in sql
    assert "irreversible_activation_understood IS DISTINCT FROM true" in sql
    assert "AS release_auth" in sql
    assert "AS authorization" not in sql
    assert "INSERT INTO public.facility_release_checkout_activations" in sql
    assert "UPDATE public.facility_release_checkout_activations" not in sql
    assert "DELETE FROM public.facility_release_checkout_activations" not in sql
    assert f"REVOKE ALL ON FUNCTION {FUNCTION_SIGNATURE} FROM PUBLIC" in sql
    assert f"GRANT EXECUTE ON FUNCTION {FUNCTION_SIGNATURE}" in sql


def test_runtime_bootstrap_preserves_only_callable_activation_authority() -> None:
    sql = BOOTSTRAP_PATH.read_text()
    assert sql.count(FUNCTION_SIGNATURE) >= 5
    grant = sql[sql.index("DO $family_release_checkout_activation_grant$") :]
    grant = grant[: grant.index("$family_release_checkout_activation_grant$;", 10)]
    assert "GRANT EXECUTE ON FUNCTION" in grant
    assert "TO caresync_basic_app" in grant
    assert "GRANT" not in grant.split("GRANT EXECUTE ON FUNCTION", 1)[1].split(
        "TO caresync_basic_app", 1
    )[1]
    audit = sql[sql.index("DO $family_release_checkout_activation_audit$") :]
    audit = audit[: audit.index("$family_release_checkout_activation_audit$;", 10)]
    assert "has_function_privilege" in audit
    assert "has_table_privilege" in audit
    assert "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'" in audit
