"""Program licence-type migration normalization, refusal, and drift checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION_TWO = "0002_verification_foundation"
FAMILY_AUTHORITY_PREVIOUS_REVISION = "0028_childcare_command_spine"
EVIDENCE_VAULT_PREVIOUS_REVISION = "0029A_family_authority_kernel"
RELEASE_CONTEXT_PREVIOUS_REVISION = "0029A2_authority_activation"
AUTHORITY_ACTIVATION_PREVIOUS_REVISION = "0029A1_family_evidence_vault"
NORMAL_RELEASE_PREVIOUS_REVISION = "0029B_release_context"


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _migration_database(tmp_path, monkeypatch, name: str) -> Path:
    database_directory = tmp_path / name
    database_directory.mkdir()
    database_path = database_directory / "caresync.db"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    return database_path


def _seed_facility(database_path: Path, program_types: list[str | None]) -> None:
    engine = create_engine(f"sqlite:///{database_path}")
    organization_id = "11111111111111111111111111111111"
    facility_id = "22222222222222222222222222222222"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id, name, status, timezone, preferences) "
                "VALUES (:id, 'Existing Child Care', 'draft', 'America/Edmonton', '{}')"
            ),
            {"id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO facilities "
                "(id, organization_id, name, status, province, timezone, licensed_capacity) "
                "VALUES (:id, :organization_id, 'Existing Centre', 'draft', 'Alberta', "
                "'America/Edmonton', 80)"
            ),
            {"id": facility_id, "organization_id": organization_id},
        )
        for index, program_type in enumerate(program_types, start=1):
            connection.execute(
                text(
                    "INSERT INTO facility_programs "
                    "(id, organization_id, facility_id, name, program_type, capacity, is_active) "
                    "VALUES (:id, :organization_id, :facility_id, :name, :program_type, 40, 1)"
                ),
                {
                    "id": f"{index + 2:032x}",
                    "organization_id": organization_id,
                    "facility_id": facility_id,
                    "name": f"Existing Program {index}",
                    "program_type": program_type,
                },
            )
    engine.dispose()


def _upgrade_to_revision_two(database_path: Path, config: Config) -> None:
    command.upgrade(config, REVISION_TWO)
    assert database_path.exists()


def test_program_type_migration_normalizes_round_trips_and_has_no_drift(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch, "normalization")
    config = _config()
    _upgrade_to_revision_two(database_path, config)
    _seed_facility(database_path, [" Day Care ", "OSC"])

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    program_type_column = next(
        column
        for column in inspector.get_columns("facility_programs")
        if column["name"] == "program_type"
    )
    assert program_type_column["nullable"] is False
    assert "ck_programs_program_type" in {
        constraint["name"]
        for constraint in inspector.get_check_constraints("facility_programs")
    }
    assert "uq_programs_facility_type" in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("facility_programs")
    }
    with engine.connect() as connection:
        values = connection.execute(
            text("SELECT program_type FROM facility_programs ORDER BY name")
        ).scalars()
        assert list(values) == ["daycare", "out_of_school_care"]
    engine.dispose()

    command.check(config)
    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, RELEASE_CONTEXT_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, EVIDENCE_VAULT_PREVIOUS_REVISION)
    command.downgrade(config, FAMILY_AUTHORITY_PREVIOUS_REVISION)
    command.downgrade(config, REVISION_TWO)
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    program_type_column = next(
        column
        for column in inspector.get_columns("facility_programs")
        if column["name"] == "program_type"
    )
    assert program_type_column["nullable"] is True
    assert "ck_programs_program_type" not in {
        constraint["name"]
        for constraint in inspector.get_check_constraints("facility_programs")
    }
    assert "uq_programs_facility_type" not in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("facility_programs")
    }
    engine.dispose()

    command.upgrade(config, "head")
    command.check(config)


def test_program_type_migration_refuses_duplicate_normalized_types_without_deleting(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch, "duplicates")
    config = _config()
    _upgrade_to_revision_two(database_path, config)
    _seed_facility(database_path, ["daycare", "Day Care"])

    with pytest.raises(RuntimeError, match="duplicate facility program types"):
        command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM facility_programs")).scalar_one() == 2
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            REVISION_TWO
        )
    engine.dispose()


def test_program_type_migration_refuses_unclassifiable_values_without_deleting(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch, "unknown")
    config = _config()
    _upgrade_to_revision_two(database_path, config)
    _seed_facility(database_path, [None, "preschool"])

    with pytest.raises(RuntimeError, match="cannot be classified safely"):
        command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM facility_programs")).scalar_one() == 2
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            REVISION_TWO
        )
    engine.dispose()
