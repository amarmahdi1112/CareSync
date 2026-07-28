"""Portable proofs for the enrollment-scoped 0037 billing agreement repair."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.basic.billing import _ensure_new_agreement_scope_available
from app.basic.models import BillingAgreement
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0036_billing_manual_mode"
CURRENT_REVISION = "0037_billing_agreement_scope"
MIGRATION_PATH = (
    BACKEND_ROOT / "alembic" / "versions" / "0037_billing_agreement_scope.py"
)
POSTGRES_SCOPE_TEST_URL = os.getenv("BASIC_POSTGRES_BILLING_SCOPE_TEST_URL")


def _config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        billing_mode="disabled",
        enable_advanced_routes=False,
        jwt_secret="billing-scope-migration-secret-at-least-thirty-two-bytes",
    )


def _post(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _seed_core_records(database_path: Path) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    with TestClient(create_app(_settings(database_path))) as client:
        auth = _post(
            client,
            "/api/v1/auth/register",
            {},
            {
                "email": f"billing-scope-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Billing",
                "last_name": "Scope",
                "organization_name": f"Billing Scope {suffix}",
            },
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Scope Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Payer",
                    "cell_phone": "780-555-0101",
                },
            },
        )
        child = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Repeat",
                "last_name": "Enrollment",
                "date_of_birth": "2023-01-01",
            },
        )
    return {
        "organization_id": auth["user"]["organization_id"],
        "actor_user_id": auth["user"]["id"],
        "family_id": family["id"],
        "guardian_id": family["guardians"][0]["id"],
        "child_id": child["id"],
    }


def _sqlite_uuid(value: str) -> str:
    return UUID(value).hex


def _insert_preparation(
    connection: sqlite3.Connection,
    *,
    values: dict[str, str],
    operation_id: str,
    command_type: str,
    target_scope: str,
    request_hash: str,
) -> None:
    connection.execute(
        "INSERT INTO billing_command_preparations "
        "(id,organization_id,actor_user_id,client_operation_id,command_type,"
        "target_scope,request_hash,prepared_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            uuid4().hex,
            _sqlite_uuid(values["organization_id"]),
            _sqlite_uuid(values["actor_user_id"]),
            _sqlite_uuid(operation_id),
            command_type,
            target_scope,
            request_hash,
            datetime.now(UTC).isoformat(),
        ),
    )


def _seed_legacy_agreement(
    database_path: Path, values: dict[str, str]
) -> dict[str, str]:
    account_id = str(uuid4())
    agreement_id = str(uuid4())
    account_operation_id = str(uuid4())
    agreement_operation_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_preparation(
            connection,
            values=values,
            operation_id=account_operation_id,
            command_type="account_open",
            target_scope=values["family_id"],
            request_hash="a" * 64,
        )
        _insert_preparation(
            connection,
            values=values,
            operation_id=agreement_operation_id,
            command_type="agreement_establish",
            target_scope=account_id,
            request_hash="b" * 64,
        )
        connection.execute(
            "INSERT INTO billing_accounts "
            "(id,organization_id,family_id,payer_guardian_id,account_number,currency,"
            "status,opened_by_user_id,opened_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,'CAD','open',?,?,?,?)",
            (
                _sqlite_uuid(account_id),
                _sqlite_uuid(values["organization_id"]),
                _sqlite_uuid(values["family_id"]),
                _sqlite_uuid(values["guardian_id"]),
                f"SCOPE-{uuid4().hex[:12]}",
                _sqlite_uuid(values["actor_user_id"]),
                now,
                _sqlite_uuid(account_operation_id),
                "a" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_agreements "
            "(id,organization_id,billing_account_id,family_id,child_id,enrollment_id,"
            "facility_id,created_by_user_id,created_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,NULL,NULL,?,?,?,?)",
            (
                _sqlite_uuid(agreement_id),
                _sqlite_uuid(values["organization_id"]),
                _sqlite_uuid(account_id),
                _sqlite_uuid(values["family_id"]),
                _sqlite_uuid(values["child_id"]),
                _sqlite_uuid(values["actor_user_id"]),
                now,
                _sqlite_uuid(agreement_operation_id),
                "b" * 64,
            ),
        )
    return {"account_id": account_id, "agreement_id": agreement_id}


def _constraint_columns(database_path: Path) -> dict[str, tuple[str, ...]]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        return {
            str(item["name"]): tuple(item["column_names"])
            for item in inspect(engine).get_unique_constraints("billing_agreements")
            if item.get("name")
        }
    finally:
        engine.dispose()


def _index_details(database_path: Path) -> dict[str, dict]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        return {
            str(item["name"]): item
            for item in inspect(engine).get_indexes("billing_agreements")
            if item.get("name")
        }
    finally:
        engine.dispose()


def _dependent_triggers(database_path: Path) -> dict[str, str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(name): str(sql)
            for name, sql in connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                "AND instr(lower(sql),'billing_agreements')>0 ORDER BY name"
            )
        }


def test_fresh_chain_reproduces_0036_then_applies_0037_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)

    assert _constraint_columns(database_path)[
        "uq_bill_agreement_account_child"
    ] == ("organization_id", "billing_account_id", "child_id")
    assert "uq_bill_agreement_account_enrollment" not in _constraint_columns(
        database_path
    )
    assert "uq_bill_agreement_legacy_account_child" not in _index_details(
        database_path
    )
    database = Database(_settings(database_path))
    try:
        assert database.has_billing_ledger() is True
    finally:
        database.engine.dispose()

    command.upgrade(config, CURRENT_REVISION)

    assert _constraint_columns(database_path)[
        "uq_bill_agreement_account_enrollment"
    ] == ("organization_id", "billing_account_id", "enrollment_id")
    assert "uq_bill_agreement_account_child" not in _constraint_columns(
        database_path
    )
    assert tuple(
        _index_details(database_path)[
            "uq_bill_agreement_legacy_account_child"
        ]["column_names"]
    ) == ("organization_id", "billing_account_id", "child_id")
    database = Database(_settings(database_path))
    try:
        assert database.has_billing_ledger() is True
    finally:
        database.engine.dispose()


@pytest.mark.skipif(
    not POSTGRES_SCOPE_TEST_URL,
    reason=(
        "BASIC_POSTGRES_BILLING_SCOPE_TEST_URL must name a disposable "
        "loopback PostgreSQL cluster"
    ),
)
def test_postgres_fresh_chain_reproduces_0036_then_applies_0037_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_SCOPE_TEST_URL is not None
    admin_url = make_url(POSTGRES_SCOPE_TEST_URL)
    assert admin_url.get_backend_name() == "postgresql"
    assert admin_url.host in {"127.0.0.1", "localhost", "::1"}
    assert admin_url.port is not None
    assert admin_url.port not in {5432, 5433, 5434}
    assert admin_url.database == "postgres"
    assert admin_url.username
    database_name = f"caresync_scope_{uuid4().hex[:12]}"
    database_url = admin_url.set(database=database_name)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    database_engine = None
    try:
        with admin.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
        monkeypatch.setenv("ENVIRONMENT", "test")
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            database_url.render_as_string(hide_password=False).replace("%", "%%"),
        )

        command.upgrade(config, PREVIOUS_REVISION)
        database_engine = create_engine(database_url)
        previous_constraints = {
            str(item["name"]): tuple(item["column_names"])
            for item in inspect(database_engine).get_unique_constraints(
                "billing_agreements"
            )
            if item.get("name")
        }
        previous_indexes = {
            str(item["name"])
            for item in inspect(database_engine).get_indexes(
                "billing_agreements"
            )
            if item.get("name")
        }
        assert previous_constraints["uq_bill_agreement_account_child"] == (
            "organization_id",
            "billing_account_id",
            "child_id",
        )
        assert "uq_bill_agreement_account_enrollment" not in previous_constraints
        assert "uq_bill_agreement_legacy_account_child" not in previous_indexes

        command.upgrade(config, CURRENT_REVISION)
        current_constraints = {
            str(item["name"]): tuple(item["column_names"])
            for item in inspect(database_engine).get_unique_constraints(
                "billing_agreements"
            )
            if item.get("name")
        }
        current_indexes = {
            str(item["name"]): item
            for item in inspect(database_engine).get_indexes(
                "billing_agreements"
            )
            if item.get("name")
        }
        assert current_constraints[
            "uq_bill_agreement_account_enrollment"
        ] == ("organization_id", "billing_account_id", "enrollment_id")
        assert "uq_bill_agreement_account_child" not in current_constraints
        legacy_index = current_indexes[
            "uq_bill_agreement_legacy_account_child"
        ]
        assert tuple(legacy_index["column_names"]) == (
            "organization_id",
            "billing_account_id",
            "child_id",
        )
        assert legacy_index["unique"]
    finally:
        if database_engine is not None:
            database_engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database_name AND pid<>pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin.dispose()


def test_upgrade_and_downgrade_preserve_legacy_facts_and_every_dependent_trigger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    values = _seed_core_records(database_path)
    billing = _seed_legacy_agreement(database_path, values)
    before_triggers = _dependent_triggers(database_path)
    assert len(before_triggers) >= 4

    command.downgrade(config, PREVIOUS_REVISION)
    assert _constraint_columns(database_path)[
        "uq_bill_agreement_account_child"
    ] == ("organization_id", "billing_account_id", "child_id")
    assert "uq_bill_agreement_legacy_account_child" not in _index_details(
        database_path
    )
    assert _dependent_triggers(database_path) == before_triggers

    command.upgrade(config, CURRENT_REVISION)
    assert _constraint_columns(database_path)[
        "uq_bill_agreement_account_enrollment"
    ] == ("organization_id", "billing_account_id", "enrollment_id")
    legacy_index = _index_details(database_path)[
        "uq_bill_agreement_legacy_account_child"
    ]
    assert tuple(legacy_index["column_names"]) == (
        "organization_id",
        "billing_account_id",
        "child_id",
    )
    assert legacy_index["unique"] == 1
    assert _dependent_triggers(database_path) == before_triggers
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM billing_agreements WHERE id=?",
            (_sqlite_uuid(billing["agreement_id"]),),
        ).fetchone()[0] == 1


def test_head_allows_distinct_enrollment_scopes_and_keeps_legacy_null_unique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    values = _seed_core_records(database_path)
    billing = _seed_legacy_agreement(database_path, values)
    organization_id = _sqlite_uuid(values["organization_id"])
    account_id = _sqlite_uuid(billing["account_id"])
    child_id = _sqlite_uuid(values["child_id"])
    family_id = _sqlite_uuid(values["family_id"])
    actor_id = _sqlite_uuid(values["actor_user_id"])
    now = datetime.now(UTC).isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        for marker in ("c", "d"):
            operation_id = str(uuid4())
            enrollment_id = str(uuid4())
            _insert_preparation(
                connection,
                values=values,
                operation_id=operation_id,
                command_type="agreement_establish",
                target_scope=billing["account_id"],
                request_hash=marker * 64,
            )
            connection.execute(
                "INSERT INTO billing_agreements "
                "(id,organization_id,billing_account_id,family_id,child_id,enrollment_id,"
                "facility_id,created_by_user_id,created_at,client_operation_id,request_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    organization_id,
                    account_id,
                    family_id,
                    child_id,
                    _sqlite_uuid(enrollment_id),
                    uuid4().hex,
                    actor_id,
                    now,
                    _sqlite_uuid(operation_id),
                    marker * 64,
                ),
            )
        duplicate_operation_id = str(uuid4())
        _insert_preparation(
            connection,
            values=values,
            operation_id=duplicate_operation_id,
            command_type="agreement_establish",
            target_scope=billing["account_id"],
            request_hash="e" * 64,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO billing_agreements "
                "(id,organization_id,billing_account_id,family_id,child_id,enrollment_id,"
                "facility_id,created_by_user_id,created_at,client_operation_id,request_hash) "
                "SELECT ?,organization_id,billing_account_id,family_id,child_id,"
                "enrollment_id,facility_id,created_by_user_id,created_at,?,? "
                "FROM billing_agreements WHERE request_hash=?",
                (
                    uuid4().hex,
                    _sqlite_uuid(duplicate_operation_id),
                    "e" * 64,
                    "c" * 64,
                ),
            )
        legacy_operation_id = str(uuid4())
        _insert_preparation(
            connection,
            values=values,
            operation_id=legacy_operation_id,
            command_type="agreement_establish",
            target_scope=billing["account_id"],
            request_hash="f" * 64,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO billing_agreements "
                "(id,organization_id,billing_account_id,family_id,child_id,enrollment_id,"
                "facility_id,created_by_user_id,created_at,client_operation_id,request_hash) "
                "VALUES (?,?,?,?,?,NULL,NULL,?,?,?,?)",
                (
                    uuid4().hex,
                    organization_id,
                    account_id,
                    family_id,
                    child_id,
                    actor_id,
                    now,
                    _sqlite_uuid(legacy_operation_id),
                    "f" * 64,
                ),
            )
        assert connection.execute(
            "SELECT count(*) FROM billing_agreements "
            "WHERE billing_account_id=? AND child_id=?",
            (account_id, child_id),
        ).fetchone()[0] == 3


def test_downgrade_refuses_to_discard_valid_reenrollment_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    values = _seed_core_records(database_path)
    billing = _seed_legacy_agreement(database_path, values)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        operation_id = str(uuid4())
        _insert_preparation(
            connection,
            values=values,
            operation_id=operation_id,
            command_type="agreement_establish",
            target_scope=billing["account_id"],
            request_hash="c" * 64,
        )
        connection.execute(
            "INSERT INTO billing_agreements "
            "(id,organization_id,billing_account_id,family_id,child_id,enrollment_id,"
            "facility_id,created_by_user_id,created_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                uuid4().hex,
                _sqlite_uuid(values["organization_id"]),
                _sqlite_uuid(billing["account_id"]),
                _sqlite_uuid(values["family_id"]),
                _sqlite_uuid(values["child_id"]),
                uuid4().hex,
                uuid4().hex,
                _sqlite_uuid(values["actor_user_id"]),
                datetime.now(UTC).isoformat(),
                _sqlite_uuid(operation_id),
                "c" * 64,
            ),
        )
    with pytest.raises(RuntimeError, match="re-enrollment agreements"):
        command.downgrade(config, PREVIOUS_REVISION)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            CURRENT_REVISION
        )
        assert connection.execute("SELECT count(*) FROM billing_agreements").fetchone()[0] == 2


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "billing_agreement_scope_0037", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_postgres_upgrade_changes_only_scope_constraints(monkeypatch) -> None:
    migration = _load_migration_module()
    operations: list[tuple[str, tuple, dict]] = []
    monkeypatch.setattr(
        migration,
        "_unique_constraints",
        lambda _bind: {migration.LEGACY_CONSTRAINT},
    )
    monkeypatch.setattr(migration, "_indexes", lambda _bind: set())
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda *args, **kwargs: operations.append(("drop_constraint", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_unique_constraint",
        lambda *args, **kwargs: operations.append(("create_unique", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda *args, **kwargs: operations.append(("create_index", args, kwargs)),
    )
    migration._upgrade_postgresql(SimpleNamespace())

    assert operations[0][0] == "drop_constraint"
    assert operations[0][1][0] == migration.LEGACY_CONSTRAINT
    assert operations[1][0] == "create_unique"
    assert operations[1][1][0] == migration.ENROLLMENT_CONSTRAINT
    assert operations[1][1][2] == [
        "organization_id",
        "billing_account_id",
        "enrollment_id",
    ]
    assert operations[2][0] == "create_index"
    assert str(operations[2][2]["postgresql_where"]) == "enrollment_id IS NULL"
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    for destructive_boundary in (
        "DROP TABLE",
        "DISABLE ROW LEVEL SECURITY",
        "DROP POLICY",
        "REVOKE ",
        "GRANT ",
    ):
        assert destructive_boundary not in source


def test_model_and_service_use_exact_enrollment_scope() -> None:
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in BillingAgreement.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert constraints["uq_bill_agreement_account_enrollment"] == (
        "organization_id",
        "billing_account_id",
        "enrollment_id",
    )
    assert "uq_bill_agreement_account_child" not in constraints
    assert {
        index.name for index in BillingAgreement.__table__.indexes if index.unique
    } >= {"uq_bill_agreement_legacy_account_child"}

    class ScalarSession:
        def __init__(self, result):
            self.result = result
            self.statement = None

        def scalar(self, statement):
            self.statement = statement
            return self.result

    organization_id = uuid4()
    account_id = uuid4()
    child_id = uuid4()
    enrollment_id = uuid4()
    enrollment_session = ScalarSession(uuid4())
    with pytest.raises(HTTPException) as enrollment_conflict:
        _ensure_new_agreement_scope_available(
            enrollment_session,
            organization_id=organization_id,
            billing_account_id=account_id,
            child_id=child_id,
            enrollment_id=enrollment_id,
        )
    assert enrollment_conflict.value.status_code == 409
    assert enrollment_conflict.value.detail == {
        "code": "billing_agreement_already_exists_for_enrollment"
    }
    enrollment_sql = str(
        enrollment_session.statement.compile(compile_kwargs={"literal_binds": True})
    )
    assert "billing_agreements.enrollment_id" in enrollment_sql
    assert enrollment_id.hex in enrollment_sql
    assert "billing_agreements.child_id =" not in enrollment_sql

    legacy_session = ScalarSession(uuid4())
    with pytest.raises(HTTPException) as legacy_conflict:
        _ensure_new_agreement_scope_available(
            legacy_session,
            organization_id=organization_id,
            billing_account_id=account_id,
            child_id=child_id,
            enrollment_id=None,
        )
    assert legacy_conflict.value.detail == {
        "code": "billing_legacy_agreement_already_exists_for_child"
    }
    legacy_sql = str(
        legacy_session.statement.compile(compile_kwargs={"literal_binds": True})
    )
    assert "billing_agreements.child_id" in legacy_sql
    assert "billing_agreements.enrollment_id IS NULL" in legacy_sql

    available = ScalarSession(None)
    _ensure_new_agreement_scope_available(
        available,
        organization_id=organization_id,
        billing_account_id=account_id,
        child_id=child_id,
        enrollment_id=uuid4(),
    )

    service_source = (
        BACKEND_ROOT / "app" / "basic" / "billing.py"
    ).read_text(encoding="utf-8")
    establish_source = service_source[service_source.index("def establish_agreement(") :]
    establish_source = establish_source[: establish_source.index("\ndef _period_matches_frequency")]
    assert establish_source.index("if retry is not None:") < establish_source.index(
        "_ensure_new_agreement_scope_available("
    )
