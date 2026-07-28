"""Portable migration and readiness gates for 0029A2 activation."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]
A1 = "0029A1_family_evidence_vault"
A2 = "0029A2_authority_activation"
B = "0029B_release_context"
C = "0029C_verified_release_checkout"

ACTIVATION_METADATA_TABLES = (
    "family_authority_evidence_objects",
    "family_authority_evidence",
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
)


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.delenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", raising=False)
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _current(database_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _database(database_path: Path) -> Database:
    return Database(
        Settings(
            _env_file=None,
            environment="test",
            database_type="sqlite",
            database_path=database_path,
            database_name="caresync",
            database_read_only=False,
            enable_advanced_routes=False,
            jwt_secret="activation-migration-test-secret-32-bytes",
        )
    )


def _normalized(value: object) -> str:
    return "".join(str(value or "").lower().split()).replace('"', "")


def _metadata_signature(database_path: Path) -> dict[str, object]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        signature: dict[str, object] = {}
        for table_name in ACTIVATION_METADATA_TABLES:
            signature[table_name] = {
                "columns": tuple(
                    (
                        column["name"],
                        str(column["type"]),
                        bool(column["nullable"]),
                        _normalized(column.get("default")),
                    )
                    for column in inspector.get_columns(table_name)
                ),
                "checks": frozenset(
                    (check["name"], _normalized(check.get("sqltext")))
                    for check in inspector.get_check_constraints(table_name)
                ),
                "foreign_keys": frozenset(
                    (
                        foreign_key["name"],
                        tuple(foreign_key["constrained_columns"]),
                        foreign_key["referred_table"],
                        tuple(foreign_key["referred_columns"]),
                        (foreign_key.get("options") or {}).get("ondelete"),
                    )
                    for foreign_key in inspector.get_foreign_keys(table_name)
                ),
                "uniques": frozenset(
                    (
                        unique["name"],
                        tuple(unique["column_names"]),
                    )
                    for unique in inspector.get_unique_constraints(table_name)
                ),
            }
        return signature
    finally:
        engine.dispose()


def test_a1_to_a2_detection_and_empty_roundtrip_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A1)
    assert _current(database_path) == A1
    a1_signature = _metadata_signature(database_path)
    database = _database(database_path)
    try:
        assert database.has_family_authority_kernel() is True
        assert database.has_family_evidence_vault() is True
        assert database.has_family_authority_activation() is False
    finally:
        database.dispose()

    command.upgrade(config, A2)
    assert _current(database_path) == A2
    database = _database(database_path)
    try:
        assert database.has_family_authority_activation() is True
    finally:
        database.dispose()
    inspector = inspect(create_engine(f"sqlite:///{database_path}"))
    assert "content_text" in {
        column["name"] for column in inspector.get_columns("consent_policy_versions")
    }
    assert {
        "signer_authority_evidence_id",
        "signer_authority_evidence_assessment_id",
    } <= {column["name"] for column in inspector.get_columns("child_consent_decisions")}
    command.upgrade(config, B)
    assert _current(database_path) == B
    command.upgrade(config, C)
    assert _current(database_path) == C
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, C)
    assert _current(database_path) == C
    command.downgrade(config, B)
    command.downgrade(config, A2)
    assert _current(database_path) == A2

    command.downgrade(config, A1)
    assert _current(database_path) == A1
    assert _metadata_signature(database_path) == a1_signature
    database = _database(database_path)
    try:
        assert database.has_family_authority_activation() is False
    finally:
        database.dispose()

    command.upgrade(config, A2)
    database = _database(database_path)
    try:
        assert database.has_family_authority_activation() is True
    finally:
        database.dispose()


def test_structural_detector_survives_descendant_revision_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A2)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num='0029B_future_descendant'")
            )
    finally:
        engine.dispose()
    database = _database(database_path)
    try:
        assert database.has_family_authority_activation() is True
    finally:
        database.dispose()


def test_partial_a2_columns_do_not_activate_a1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A1)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE consent_policy_versions ADD COLUMN content_text TEXT"
            )
            connection.exec_driver_sql(
                "ALTER TABLE child_consent_decisions "
                "ADD COLUMN signer_authority_evidence_id CHAR(32)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE child_consent_decisions "
                "ADD COLUMN signer_authority_evidence_assessment_id CHAR(32)"
            )
    finally:
        engine.dispose()
    database = _database(database_path)
    try:
        assert database.has_family_authority_activation() is False
    finally:
        database.dispose()


def test_sqlite_multirevision_downgrade_refuses_before_batch_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A2)
    before = _metadata_signature(database_path)

    with pytest.raises(RuntimeError, match="0029A2 SQLite downgrade refused before DDL"):
        command.downgrade(config, "0029A_family_authority_kernel")

    assert _current(database_path) == A2
    assert _metadata_signature(database_path) == before
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
                )
                == 0
            )
    finally:
        engine.dispose()


def test_populated_a2_downgrade_refuses_before_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A2)
    engine = create_engine(f"sqlite:///{database_path}")
    organization_id = uuid4().hex
    user_id = uuid4().hex
    operation_id = uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations "
                    "(id,name,status,timezone,preferences,verification_status) "
                    "VALUES (:id,'Activation Gate','active','America/Edmonton',"
                    "'{}','pending')"
                ),
                {"id": organization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                    "VALUES (:id,:email,'unused','Activation','Gate',1,1)"
                ),
                {
                    "id": user_id,
                    "email": f"activation-{uuid4().hex}@example.test",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO childcare_command_receipts "
                    "(id,organization_id,client_operation_id,command_type,target_type,"
                    "target_id,request_hash,actor_user_id,committed_version,outcome) "
                    "VALUES (:id,:organization_id,:operation_id,"
                    "'child.consent.record','consent',:target_id,:request_hash,"
                    ":actor_user_id,1,'{}')"
                ),
                {
                    "id": uuid4().hex,
                    "organization_id": organization_id,
                    "operation_id": operation_id,
                    "target_id": uuid4().hex,
                    "request_hash": uuid4().hex * 2,
                    "actor_user_id": user_id,
                },
            )
    finally:
        engine.dispose()

    before = _metadata_signature(database_path)
    with pytest.raises(RuntimeError, match="refused before DDL"):
        command.downgrade(config, A1)
    assert _current(database_path) == A2
    assert _metadata_signature(database_path) == before
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
                )
                == 0
            )
    finally:
        engine.dispose()
