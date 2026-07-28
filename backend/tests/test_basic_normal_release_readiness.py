"""Portable readiness proof for the dormant and runtime 0029C boundaries."""

from __future__ import annotations

import sqlite3
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.core.config import Settings
from app.db.session import (
    Database,
    _release_checkout_activation_insert_guard_is_hardened,
    _release_checkout_snapshot_immutability_is_hardened,
    _release_checkout_snapshot_insert_guard_is_hardened,
)
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
B = "0029B_release_context"
C = "0029C_verified_release_checkout"
D = "0029D_release_checkout_writer"


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="normal-release-readiness-test-secret-32-bytes",
    )


def _migrate(tmp_path, monkeypatch, revision: str) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def _postgres_snapshot_guard_statements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    migration_path = BACKEND_ROOT / "alembic/versions/0029C_verified_release_checkout.py"
    spec = spec_from_file_location("normal_release_snapshot_guard", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = []

    def capture(statement: Any) -> None:
        statements.append(str(statement))

    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    monkeypatch.setattr(module.op, "execute", capture)
    module._install_snapshot_immutability()
    # pg_get_triggerdef emits multi-event triggers in canonical event order.
    return [
        statement.replace("BEFORE UPDATE OR DELETE", "BEFORE DELETE OR UPDATE")
        for statement in statements
    ]


def _postgres_relational_guard_statements(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    migration_path = BACKEND_ROOT / "alembic/versions/0029C_verified_release_checkout.py"
    spec = spec_from_file_location("normal_release_relational_guards", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = []

    def capture(statement: Any) -> None:
        statements.append(str(statement))

    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(module.op, "get_bind", lambda: bind)
    monkeypatch.setattr(module.op, "execute", capture)
    module._install_relational_consistency_guards()
    return statements


def _rewrite_table_definition(
    database_path: Path,
    table_name: str,
    old: str,
    new: str,
) -> None:
    """Mutate one temporary SQLite catalog definition for readiness proofs."""

    with sqlite3.connect(database_path) as connection:
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()[0]
        assert definition.count(old) == 1
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?",
            (definition.replace(old, new, 1), table_name),
        )
        connection.execute("PRAGMA writable_schema=OFF")
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        connection.execute(f"PRAGMA schema_version={schema_version + 1}")
        connection.commit()


def _assert_checkout_disabled(database_path: Path) -> None:
    database = Database(_settings(database_path))
    try:
        assert database.has_family_release_checkout_foundation() is False
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()


def test_b_has_neither_c_foundation_nor_runtime(tmp_path, monkeypatch) -> None:
    database = Database(_settings(_migrate(tmp_path, monkeypatch, B)))
    try:
        assert database.has_family_release_checkout_foundation() is False
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()


def test_b_application_keeps_release_context_but_not_checkout(tmp_path, monkeypatch) -> None:
    application = create_app(_settings(_migrate(tmp_path, monkeypatch, B)))
    with TestClient(application):
        assert application.state.family_authority_release_context_enabled is True
        assert application.state.family_release_checkout_foundation_present is False
        assert application.state.family_release_checkout_enabled is False


def test_c_has_complete_dormant_foundation_but_no_runtime_boundary(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    database = Database(_settings(database_path))
    try:
        assert database.has_family_release_checkout_foundation() is True
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()

    application = create_app(_settings(database_path))
    with TestClient(application):
        assert application.state.family_authority_release_context_enabled is True
        assert application.state.family_release_checkout_foundation_present is True
        assert application.state.family_release_checkout_enabled is False


def test_d_is_portable_noop_and_never_advertises_sqlite_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, D)
    database = Database(_settings(database_path))
    try:
        assert database.has_family_release_checkout_foundation() is True
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()

    application = create_app(_settings(database_path))
    with TestClient(application):
        assert application.state.family_authority_release_context_enabled is True
        assert application.state.family_release_checkout_foundation_present is True
        assert application.state.family_release_checkout_enabled is False


def test_partial_c_fails_both_release_checkout_readiness_states(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER facility_release_checkout_activations_no_update")
        connection.commit()
    database = Database(_settings(database_path))
    try:
        assert database.has_family_release_checkout_foundation() is False
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()


@pytest.mark.parametrize(
    ("table_name", "constraint_name"),
    (
        (
            "attendance_release_snapshots",
            "ck_release_snapshots_attendance_day_version",
        ),
        (
            "attendance_release_snapshots",
            "ck_release_snapshots_scope_basis",
        ),
        (
            "attendance_release_snapshots",
            "ck_release_snapshots_executable_verification_policy",
        ),
        (
            "attendance_release_snapshots",
            "ck_release_snapshots_checkout_time_order",
        ),
        (
            "attendance_release_snapshots",
            "ck_release_snapshots_decision_policy_version",
        ),
        (
            "facility_release_checkout_activations",
            "ck_release_checkout_activations_privileged_role",
        ),
        (
            "facility_release_checkout_activations",
            "ck_release_checkout_activations_policy_version",
        ),
        (
            "childcare_command_receipts",
            "ck_childcare_command_receipts_target",
        ),
    ),
)
def test_named_c_check_is_required_for_foundation_readiness(
    tmp_path,
    monkeypatch,
    table_name: str,
    constraint_name: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    _rewrite_table_definition(
        database_path,
        table_name,
        constraint_name,
        f"{constraint_name}_changed",
    )
    _assert_checkout_disabled(database_path)


@pytest.mark.parametrize(
    ("table_name", "old", "new"),
    (
        (
            "facility_release_checkout_activations",
            "activation_policy_version VARCHAR(40) NOT NULL",
            "activation_policy_version VARCHAR(41) NOT NULL",
        ),
        (
            "attendance_release_snapshots",
            "recipient_display_name VARCHAR(302) NOT NULL",
            "recipient_display_name VARCHAR(301) NOT NULL",
        ),
        (
            "attendance_release_snapshots",
            "room_assignment_id CHAR(32),",
            "room_assignment_id CHAR(32) NOT NULL,",
        ),
    ),
)
def test_c_column_manifest_is_exact(
    tmp_path,
    monkeypatch,
    table_name: str,
    old: str,
    new: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    _rewrite_table_definition(database_path, table_name, old, new)
    _assert_checkout_disabled(database_path)


@pytest.mark.parametrize(
    "constraint_name",
    (
        "fk_release_checkout_activations_operation",
        "fk_release_checkout_activations_facility",
        "fk_release_checkout_activations_membership",
        "fk_release_checkout_activations_role",
        "uq_release_checkout_activations_org_id",
        "uq_release_checkout_activations_facility",
        "uq_release_checkout_activations_operation",
    ),
)
def test_activation_relationship_constraint_names_are_required(
    tmp_path,
    monkeypatch,
    constraint_name: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    _rewrite_table_definition(
        database_path,
        "facility_release_checkout_activations",
        constraint_name,
        f"{constraint_name}_changed",
    )
    _assert_checkout_disabled(database_path)


def test_activation_foreign_key_behavior_is_exact(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    _rewrite_table_definition(
        database_path,
        "facility_release_checkout_activations",
        "FOREIGN KEY(activated_by_user_id) REFERENCES users (id) ON DELETE RESTRICT",
        "FOREIGN KEY(activated_by_user_id) REFERENCES users (id) ON DELETE CASCADE",
    )
    _assert_checkout_disabled(database_path)


def test_receipt_target_vocabulary_is_exact(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    _rewrite_table_definition(
        database_path,
        "childcare_command_receipts",
        "'release_activation'",
        "'release_activation_changed'",
    )
    _assert_checkout_disabled(database_path)


def test_activation_trigger_body_must_be_exact(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER facility_release_checkout_activations_no_update")
        connection.execute(
            "CREATE TRIGGER facility_release_checkout_activations_no_update "
            "BEFORE UPDATE ON facility_release_checkout_activations "
            "BEGIN SELECT 1; END"
        )
        connection.commit()
    _assert_checkout_disabled(database_path)


@pytest.mark.parametrize(
    ("table_name", "trigger_name"),
    (
        (
            "facility_release_checkout_activations",
            "facility_release_checkout_activations_insert_guard",
        ),
        (
            "attendance_release_snapshots",
            "attendance_release_snapshots_insert_guard",
        ),
    ),
)
def test_relational_insert_guard_is_required(
    tmp_path,
    monkeypatch,
    table_name: str,
    trigger_name: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.commit()
    _assert_checkout_disabled(database_path)


@pytest.mark.parametrize(
    ("table_name", "trigger_name"),
    (
        (
            "facility_release_checkout_activations",
            "facility_release_checkout_activations_insert_guard",
        ),
        (
            "attendance_release_snapshots",
            "attendance_release_snapshots_insert_guard",
        ),
    ),
)
def test_relational_insert_guard_body_must_be_exact(
    tmp_path,
    monkeypatch,
    table_name: str,
    trigger_name: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(
            f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON {table_name} BEGIN SELECT 1; END"
        )
        connection.commit()
    _assert_checkout_disabled(database_path)


def test_postgres_relational_guard_detectors_accept_current_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _postgres_relational_guard_statements(monkeypatch)
    assert len(statements) == 6
    assert statements[1] == (
        "REVOKE ALL ON FUNCTION "
        "public.caresync_release_checkout_activation_insert_guard() FROM PUBLIC"
    )
    assert statements[4] == (
        "REVOKE ALL ON FUNCTION public.caresync_release_snapshot_insert_guard() FROM PUBLIC"
    )
    assert _release_checkout_activation_insert_guard_is_hardened(
        statements[0],
        statements[2],
    )
    assert _release_checkout_snapshot_insert_guard_is_hardened(
        statements[3],
        statements[5],
    )


@pytest.mark.parametrize(
    ("guard_kind", "old", "new"),
    (
        ("activation", "SECURITY DEFINER", "SECURITY INVOKER"),
        (
            "activation",
            "membership.user_id = NEW.activated_by_user_id",
            "membership.user_id <> NEW.activated_by_user_id",
        ),
        (
            "activation",
            "receipt.target_id = NEW.id",
            "receipt.target_id <> NEW.id",
        ),
        ("activation", "BEFORE INSERT", "AFTER INSERT"),
        (
            "snapshot",
            "staff_shift.facility_id = NEW.facility_id",
            "staff_shift.facility_id <> NEW.facility_id",
        ),
        (
            "snapshot",
            "room_assignment.room_id = NEW.room_id",
            "room_assignment.room_id <> NEW.room_id",
        ),
        (
            "snapshot",
            "receipt.request_hash = NEW.request_hash",
            "receipt.request_hash <> NEW.request_hash",
        ),
        (
            "snapshot",
            "receipt.committed_at = NEW.committed_at",
            "receipt.committed_at <> NEW.committed_at",
        ),
        (
            "snapshot",
            "checkout_event.client_operation_id = NEW.client_operation_id",
            "checkout_event.client_operation_id <> NEW.client_operation_id",
        ),
        (
            "snapshot",
            "checkout_event.occurred_at = NEW.checked_out_at",
            "checkout_event.occurred_at <> NEW.checked_out_at",
        ),
        ("snapshot", "BEFORE INSERT", "AFTER INSERT"),
    ),
)
def test_postgres_relational_guard_detectors_reject_weakened_definition(
    monkeypatch: pytest.MonkeyPatch,
    guard_kind: str,
    old: str,
    new: str,
) -> None:
    statements = _postgres_relational_guard_statements(monkeypatch)
    function_definition, trigger_definition = (
        (statements[0], statements[2])
        if guard_kind == "activation"
        else (statements[3], statements[5])
    )
    if old in function_definition:
        function_definition = function_definition.replace(old, new)
    else:
        assert old in trigger_definition
        trigger_definition = trigger_definition.replace(old, new)
    detector = (
        _release_checkout_activation_insert_guard_is_hardened
        if guard_kind == "activation"
        else _release_checkout_snapshot_insert_guard_is_hardened
    )
    assert not detector(function_definition, trigger_definition)


def test_postgres_snapshot_guard_detector_accepts_current_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _postgres_snapshot_guard_statements(monkeypatch)
    assert len(statements) == 3
    assert statements[1] == (
        "REVOKE ALL ON FUNCTION public.caresync_release_snapshot_immutable() FROM PUBLIC"
    )
    assert _release_checkout_snapshot_immutability_is_hardened(
        statements[0],
        statements[2],
    )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("SECURITY DEFINER", "SECURITY INVOKER"),
        (
            "attendance release snapshot is immutable",
            "attendance release snapshot may change",
        ),
        ("ERRCODE='23514'", "ERRCODE='P0001'"),
        ("BEFORE DELETE OR UPDATE", "BEFORE UPDATE"),
    ),
)
def test_postgres_snapshot_guard_detector_rejects_weakened_definition(
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
) -> None:
    statements = _postgres_snapshot_guard_statements(monkeypatch)
    function_definition = statements[0]
    trigger_definition = statements[2]
    if old in function_definition:
        function_definition = function_definition.replace(old, new)
    else:
        assert old in trigger_definition
        trigger_definition = trigger_definition.replace(old, new)
    assert not _release_checkout_snapshot_immutability_is_hardened(
        function_definition,
        trigger_definition,
    )


@pytest.mark.parametrize(
    "trigger_name",
    (
        "attendance_release_snapshots_no_update",
        "attendance_release_snapshots_no_delete",
    ),
)
def test_snapshot_immutability_trigger_is_required(
    tmp_path,
    monkeypatch,
    trigger_name: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.commit()
    _assert_checkout_disabled(database_path)


@pytest.mark.parametrize(
    ("trigger_name", "operation"),
    (
        ("attendance_release_snapshots_no_update", "UPDATE"),
        ("attendance_release_snapshots_no_delete", "DELETE"),
    ),
)
def test_snapshot_immutability_trigger_body_must_be_exact(
    tmp_path,
    monkeypatch,
    trigger_name: str,
    operation: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(
            f"CREATE TRIGGER {trigger_name} "
            f"BEFORE {operation} ON attendance_release_snapshots "
            "BEGIN SELECT 1; END"
        )
        connection.commit()
    _assert_checkout_disabled(database_path)


def test_speculative_runtime_names_never_enable_checkout(tmp_path, monkeypatch) -> None:
    database_path = _migrate(tmp_path, monkeypatch, C)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TRIGGER attendance_release_snapshots_verified_checkout_insert "
            "BEFORE INSERT ON attendance_release_snapshots BEGIN SELECT 1; END"
        )
        connection.execute(
            "CREATE TRIGGER attendance_intervals_verified_release_update_guard "
            "BEFORE UPDATE ON attendance_intervals BEGIN SELECT 1; END"
        )
        connection.execute(
            "CREATE TRIGGER attendance_days_verified_release_update_guard "
            "BEFORE UPDATE ON attendance_days BEGIN SELECT 1; END"
        )
        connection.commit()
    database = Database(_settings(database_path))
    try:
        assert database.has_family_release_checkout_foundation() is True
        assert database.has_family_release_checkout_runtime() is False
    finally:
        database.dispose()
