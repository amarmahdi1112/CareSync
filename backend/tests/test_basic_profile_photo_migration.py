"""Additive child-profile-photo migration and schema-drift proof."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0004_staff_access"
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


def _seed_existing_child(database_path: Path) -> tuple[str, str]:
    organization_id = "11111111111111111111111111111111"
    family_id = "22222222222222222222222222222222"
    child_id = "33333333333333333333333333333333"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id,name,status,verification_status,timezone,preferences) "
                "VALUES (:id,'Existing Care','active','pending','America/Edmonton','{}')"
            ),
            {"id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO families "
                "(id,organization_id,name,status,photo_consent,field_trip_consent,"
                "emergency_medical_consent) "
                "VALUES (:id,:organization_id,'Existing Family','active',0,0,0)"
            ),
            {"id": family_id, "organization_id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Existing','Child','2023-01-01',1)"
            ),
            {
                "id": child_id,
                "organization_id": organization_id,
                "family_id": family_id,
            },
        )
    engine.dispose()
    return organization_id, child_id


def test_profile_photo_migration_is_additive_round_trips_and_has_no_drift(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _migration_database(tmp_path, monkeypatch)
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)
    organization_id, child_id = _seed_existing_child(database_path)

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert "child_profile_photos" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("child_profile_photos")} == {
        "id",
        "organization_id",
        "child_id",
        "image_bytes",
        "content_type",
        "size_bytes",
        "width",
        "height",
        "sha256",
        "original_filename",
        "created_at",
        "updated_at",
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("child_profile_photos")
    } == {"uq_child_profile_photos_org_id", "uq_child_profile_photos_org_child"}
    assert {
        constraint["name"] for constraint in inspector.get_check_constraints("child_profile_photos")
    } == {
        "ck_child_profile_photos_content_type",
        "ck_child_profile_photos_dimensions",
        "ck_child_profile_photos_size",
    }
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM children")).scalar_one() == 1
        values = {
            "id": "44444444444444444444444444444444",
            "organization_id": organization_id,
            "child_id": child_id,
            "image_bytes": b"normalized-image",
            "sha256": "a" * 64,
        }
        connection.execute(
            text(
                "INSERT INTO child_profile_photos "
                "(id,organization_id,child_id,image_bytes,content_type,size_bytes,width,height,"
                "sha256) VALUES (:id,:organization_id,:child_id,:image_bytes,'image/jpeg',"
                "16,1,1,:sha256)"
            ),
            values,
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO child_profile_photos "
                    "(id,organization_id,child_id,image_bytes,content_type,size_bytes,width,"
                    "height,sha256) VALUES "
                    "('55555555555555555555555555555555',:organization_id,:child_id,"
                    ":image_bytes,'image/jpeg',16,1,1,:sha256)"
                ),
                values,
            )
    engine.dispose()

    command.check(config)
    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, RELEASE_CONTEXT_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, EVIDENCE_VAULT_PREVIOUS_REVISION)
    command.downgrade(config, FAMILY_AUTHORITY_PREVIOUS_REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path}")
    assert "child_profile_photos" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM children")).scalar_one() == 1
    engine.dispose()

    command.upgrade(config, "head")
    command.check(config)
