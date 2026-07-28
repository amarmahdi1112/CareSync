"""Additive medication/incident migration, permissions, and drift proof."""

from __future__ import annotations

import json
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0006_room_daybook"
FAMILY_AUTHORITY_PREVIOUS_REVISION = "0028_childcare_command_spine"
EVIDENCE_VAULT_PREVIOUS_REVISION = "0029A_family_authority_kernel"
RELEASE_CONTEXT_PREVIOUS_REVISION = "0029A2_authority_activation"
AUTHORITY_ACTIVATION_PREVIOUS_REVISION = "0029A1_family_evidence_vault"
NORMAL_RELEASE_PREVIOUS_REVISION = "0029B_release_context"

EXPECTED_ROLE_PERMISSIONS = {
    "owner": {
        "admissions:read",
        "admissions:manage",
        "admissions:decide",
        "billing:read",
        "billing:manage",
        "billing:issue",
        "billing:payments",
        "billing:adjust",
        "billing:close",
        "billing:recover",
        "release:checkout",
        "release:read",
        "shift:clock",
        "transport:manage",
        "transport:read",
        "ats:read",
        "ats:manage",
        "ats:hire",
        "medication:read",
        "medication:manage",
        "medication:record",
        "medication:correct",
        "medication:void",
        "incident:read",
        "incident:create",
        "incident:update",
        "incident:review",
        "incident:external_report",
    },
    "administrator": {
        "admissions:read",
        "admissions:manage",
        "admissions:decide",
        "billing:read",
        "billing:manage",
        "billing:issue",
        "billing:payments",
        "billing:recover",
        "release:checkout",
        "release:read",
        "shift:clock",
        "transport:manage",
        "transport:read",
        "ats:read",
        "ats:manage",
        "ats:hire",
        "medication:read",
        "medication:manage",
        "medication:record",
        "medication:correct",
        "medication:void",
        "incident:read",
        "incident:create",
        "incident:update",
        "incident:review",
        "incident:external_report",
    },
    "educator": {
        "release:checkout",
        "release:read",
        "shift:clock",
        "medication:read",
        "medication:record",
        "medication:correct_own",
        "incident:read",
        "incident:create",
        "incident:update_own",
    },
}

NEW_TABLES = {
    "medication_plans",
    "medication_plan_events",
    "medication_administrations",
    "medication_administration_events",
    "incident_records",
    "incident_record_events",
}


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _database(tmp_path, monkeypatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    return database_path


def _seed_roles(database_path: Path) -> None:
    organization_id = "11111111111111111111111111111111"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id,name,status,verification_status,timezone,preferences) "
                "VALUES (:id,'Existing Regulated Care','active','pending',"
                "'America/Edmonton','{}')"
            ),
            {"id": organization_id},
        )
        for index, key in enumerate(EXPECTED_ROLE_PERMISSIONS, start=2):
            connection.execute(
                text(
                    "INSERT INTO roles "
                    "(id,organization_id,key,name,permissions,is_system) "
                    "VALUES (:id,:organization_id,:key,:name,:permissions,1)"
                ),
                {
                    "id": str(index) * 32,
                    "organization_id": organization_id,
                    "key": key,
                    "name": key.title(),
                    "permissions": json.dumps(["existing:permission"]),
                },
            )
    engine.dispose()


def _permissions(database_path: Path) -> dict[str, set[str]]:
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        result = {
            key: set(json.loads(permissions))
            for key, permissions in connection.execute(text("SELECT key, permissions FROM roles"))
        }
    engine.dispose()
    return result


def test_regulated_care_migration_round_trips_permissions_and_schema(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = _database(tmp_path, monkeypatch)
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)
    _seed_roles(database_path)

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert NEW_TABLES.issubset(inspector.get_table_names())
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("medication_plan_events")
    } == {"uq_medication_plan_events_org_id", "uq_medication_plan_events_operation"}
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("medication_administration_events")
    } == {
        "uq_medication_administration_events_org_id",
        "uq_medication_administration_events_operation",
    }
    slot_index = next(
        item
        for item in inspector.get_indexes("medication_administrations")
        if item["name"] == "uq_medication_administrations_schedule_slot"
    )
    assert bool(slot_index["unique"])
    assert {
        "ck_medication_plans_active_evidence",
        "ck_medication_plans_authorization_evidence",
        "ck_medication_plans_storage_safety",
    }.issubset(
        {constraint["name"] for constraint in inspector.get_check_constraints("medication_plans")}
    )
    assert {
        "ck_incident_records_finalization_state",
        "ck_incident_records_external_evidence",
        "ck_incident_records_parent_notification_evidence",
    }.issubset(
        {constraint["name"] for constraint in inspector.get_check_constraints("incident_records")}
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
    engine.dispose()

    for key, additions in EXPECTED_ROLE_PERMISSIONS.items():
        assert _permissions(database_path)[key] == {"existing:permission", *additions}
    command.check(config)

    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, RELEASE_CONTEXT_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, EVIDENCE_VAULT_PREVIOUS_REVISION)
    command.downgrade(config, FAMILY_AUTHORITY_PREVIOUS_REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert not NEW_TABLES.intersection(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1
    engine.dispose()
    assert _permissions(database_path) == {
        key: {"existing:permission"} for key in EXPECTED_ROLE_PERMISSIONS
    }

    command.upgrade(config, "head")
    command.check(config)
