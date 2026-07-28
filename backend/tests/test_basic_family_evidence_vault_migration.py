"""Portable migration gates for the staged 0029A1 evidence vault."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.test_basic_family_authority_api import _client, _family, _register
from tests.test_basic_family_evidence_vault import _upload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
A = "0029A_family_authority_kernel"
A1 = "0029A1_family_evidence_vault"
A2 = "0029A2_authority_activation"
B = "0029B_release_context"
C = "0029C_verified_release_checkout"
BASE = "0028_childcare_command_spine"


def _config(tmp_path, monkeypatch) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _current(database_path: Path) -> str | None:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def test_staged_upgrade_shape_and_empty_downgrade_reupgrade(tmp_path, monkeypatch) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, BASE)
    assert _current(database_path) == BASE
    command.upgrade(config, A)
    assert _current(database_path) == A
    command.upgrade(config, A1)
    assert _current(database_path) == A1
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert {
            "family_authority_evidence_objects",
            "family_authority_evidence_object_assessments",
        } <= set(inspector.get_table_names())
        assert "evidence_object_id" in {
            column["name"] for column in inspector.get_columns("family_authority_evidence")
        }
        media_checks = {
            value["name"]: value["sqltext"]
            for value in inspector.get_check_constraints("family_authority_evidence_objects")
        }
        assert "application/pdf" in media_checks["ck_authority_evidence_objects_media_type"]
        assert "image/jpeg" in media_checks["ck_authority_evidence_objects_media_type"]
        assert "image/png" in media_checks["ck_authority_evidence_objects_media_type"]
    finally:
        engine.dispose()
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
    command.downgrade(config, A)
    assert _current(database_path) == A
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert "family_authority_evidence_objects" not in inspector.get_table_names()
        assert "evidence_object_id" not in {
            column["name"] for column in inspector.get_columns("family_authority_evidence")
        }
    finally:
        engine.dispose()
    command.upgrade(config, C)
    assert _current(database_path) == C


def test_sqlite_multi_revision_downgrade_refuses_before_any_batch_ddl(
    tmp_path, monkeypatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, A1)
    with pytest.raises(RuntimeError, match="first downgrade exactly"):
        command.downgrade(config, BASE)
    assert _current(database_path) == A1
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pragma_table_info("
                        "'family_authority_evidence') WHERE name='evidence_object_id'"
                    )
                )
                == 1
            )
    finally:
        engine.dispose()


def test_populated_vault_refuses_downgrade_and_remains_at_head(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FAMILY_EVIDENCE_VAULT_PATH", str(tmp_path / "vault"))
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client, "PopulatedDowngrade")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        assert uploaded.status_code == 201, uploaded.text
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    database_path = tmp_path / "caresync.db"
    command.downgrade(config, C)
    assert _current(database_path) == C
    with pytest.raises(RuntimeError, match="first downgrade exactly"):
        command.downgrade(config, A)
    # C refuses a multi-revision SQLite downgrade before any preflight or DDL.
    assert _current(database_path) == C

    command.downgrade(config, B)
    command.downgrade(config, A2)
    assert _current(database_path) == A2
    command.downgrade(config, A1)
    assert _current(database_path) == A1
    with pytest.raises(RuntimeError, match="immutable object history"):
        command.downgrade(config, A)
    assert _current(database_path) == A1
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert "family_authority_evidence_objects" in inspector.get_table_names()
        assert "evidence_object_id" in {
            column["name"] for column in inspector.get_columns("family_authority_evidence")
        }
    finally:
        engine.dispose()


def test_upgrade_preflight_refuses_unsupported_predecessor_media_before_ddl(
    tmp_path, monkeypatch
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client, "LegacyMedia")
        family = _family(client, headers)
        recorded = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "guardian_attestation",
                "source_label": "preflight seed",
            },
        )
        assert recorded.status_code == 201, recorded.text

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    database_path = tmp_path / "caresync.db"
    command.downgrade(config, B)
    command.downgrade(config, A2)
    assert _current(database_path) == A2
    command.downgrade(config, A1)
    assert _current(database_path) == A1
    command.downgrade(config, A)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA ignore_check_constraints=ON")
            connection.execute(text("UPDATE family_authority_evidence SET media_type='image/gif'"))
            connection.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="refused before DDL"):
        command.upgrade(config, A1)
    assert _current(database_path) == A
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert "family_authority_evidence_objects" not in inspector.get_table_names()
        assert "evidence_object_id" not in {
            column["name"] for column in inspector.get_columns("family_authority_evidence")
        }
    finally:
        engine.dispose()
