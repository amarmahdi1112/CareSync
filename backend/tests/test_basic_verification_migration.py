"""Verification migration backfill, rollback, and schema-drift checks."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FAMILY_AUTHORITY_PREVIOUS_REVISION = "0028_childcare_command_spine"
EVIDENCE_VAULT_PREVIOUS_REVISION = "0029A_family_authority_kernel"
RELEASE_CONTEXT_PREVIOUS_REVISION = "0029A2_authority_activation"
AUTHORITY_ACTIVATION_PREVIOUS_REVISION = "0029A1_family_evidence_vault"
NORMAL_RELEASE_PREVIOUS_REVISION = "0029B_release_context"


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _migration_database(tmp_path, monkeypatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    return database_path


def _seed_revision_one(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path}")
    organization_id = "11111111111111111111111111111111"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id, name, status, timezone, preferences) "
                "VALUES (:id, :name, 'draft', 'America/Edmonton', '{}')"
            ),
            {"id": organization_id, "name": "Existing Child Care"},
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, password_hash, first_name, last_name, is_active) "
                "VALUES (:id, :email, :password_hash, :first_name, :last_name, 1)"
            ),
            {
                "id": "22222222222222222222222222222222",
                "email": "existing@example.com",
                "password_hash": "not-used",
                "first_name": "Existing",
                "last_name": "Owner",
            },
        )
        connection.execute(
            text(
                "INSERT INTO facilities "
                "(id, organization_id, name, status, province, timezone, licensed_capacity) "
                "VALUES (:id, :organization_id, :name, 'draft', 'Alberta', "
                "'America/Edmonton', 10)"
            ),
            {
                "id": "33333333333333333333333333333333",
                "organization_id": organization_id,
                "name": "Existing Centre",
            },
        )
    engine.dispose()


def test_verification_migration_backfills_round_trips_and_has_no_drift(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch)
    config = _config()
    command.upgrade(config, "0001_basic_foundation")
    _seed_revision_one(database_path)

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        user = connection.execute(
            text(
                "SELECT email_verified_at, email_verification_method "
                "FROM users WHERE email = 'existing@example.com'"
            )
        ).mappings().one()
        assert user["email_verified_at"] is not None
        assert user["email_verification_method"] == "migration_backfill"

        organization = connection.execute(
            text(
                "SELECT verification_status, verified_at, verification_method "
                "FROM organizations WHERE name = 'Existing Child Care'"
            )
        ).mappings().one()
        assert organization["verification_status"] == "verified"
        assert organization["verified_at"] is not None
        assert organization["verification_method"] == "migration_backfill"

        facility = connection.execute(
            text(
                "SELECT verification_status, verified_at, verification_method "
                "FROM facilities WHERE name = 'Existing Centre'"
            )
        ).mappings().one()
        assert facility["verification_status"] == "verified"
        assert facility["verified_at"] is not None
        assert facility["verification_method"] == "migration_backfill"
    engine.dispose()

    command.check(config)
    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, RELEASE_CONTEXT_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, EVIDENCE_VAULT_PREVIOUS_REVISION)
    command.downgrade(config, FAMILY_AUTHORITY_PREVIOUS_REVISION)
    command.downgrade(config, "0001_basic_foundation")
    engine = create_engine(f"sqlite:///{database_path}")
    assert "email_verification_method" not in {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert "verification_status" not in {
        column["name"] for column in inspect(engine).get_columns("organizations")
    }
    assert "verification_status" not in {
        column["name"] for column in inspect(engine).get_columns("facilities")
    }
    engine.dispose()

    command.upgrade(config, "head")
    command.check(config)
