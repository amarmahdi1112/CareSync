"""Migration safety gates for the 0028 childcare command spine."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0027_staff_exchange"
CURRENT_REVISION = "0028_childcare_command_spine"


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _database(tmp_path, monkeypatch, name: str) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    database_path = directory / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    return database_path


def _ids() -> dict[str, str]:
    return {
        key: uuid4().hex
        for key in (
            "organization",
            "user",
            "family",
            "guardian_one",
            "guardian_two",
            "child",
            "facility",
            "program",
            "room",
            "enrollment",
            "operation",
            "receipt",
        )
    }


def _seed_organization_family(connection, ids: dict[str, str]) -> None:
    connection.execute(
        text(
            "INSERT INTO organizations "
            "(id,name,status,timezone,preferences,verification_status) "
            "VALUES (:id,'Migration Org','active','America/Edmonton','{}','pending')"
        ),
        {"id": ids["organization"]},
    )
    connection.execute(
        text(
            "INSERT INTO families "
            "(id,organization_id,name,status,photo_consent,field_trip_consent,"
            "emergency_medical_consent) "
            "VALUES (:id,:organization_id,'Migration Family','active',0,0,0)"
        ),
        {"id": ids["family"], "organization_id": ids["organization"]},
    )


def _seed_duplicate_guardians(database_path: Path) -> None:
    ids = _ids()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        for key, first_name in (
            ("guardian_one", "First"),
            ("guardian_two", "Second"),
        ):
            connection.execute(
                text(
                    "INSERT INTO guardians "
                    "(id,organization_id,family_id,first_name,last_name,email,cell_phone,"
                    "is_primary,authorized_pickup) "
                    "VALUES (:id,:organization_id,:family_id,:first_name,'Guardian','',"
                    "'780-555-0100',1,1)"
                ),
                {
                    "id": ids[key],
                    "organization_id": ids["organization"],
                    "family_id": ids["family"],
                    "first_name": first_name,
                },
            )
    engine.dispose()


def _seed_null_program_room_placement(database_path: Path) -> None:
    ids = _ids()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Migration','Child','2023-01-01',1)"
            ),
            {
                "id": ids["child"],
                "organization_id": ids["organization"],
                "family_id": ids["family"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO facilities "
                "(id,organization_id,name,status,province,timezone,licensed_capacity,"
                "verification_status,shift_clock_radius_meters) "
                "VALUES (:id,:organization_id,'Migration Centre','active','Alberta',"
                "'America/Edmonton',20,'pending',150)"
            ),
            {"id": ids["facility"], "organization_id": ids["organization"]},
        )
        connection.execute(
            text(
                "INSERT INTO facility_programs "
                "(id,organization_id,facility_id,name,program_type,capacity,is_active) "
                "VALUES (:id,:organization_id,:facility_id,'Daycare','daycare',20,1)"
            ),
            {
                "id": ids["program"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO rooms "
                "(id,organization_id,facility_id,program_id,name,capacity,is_active) "
                "VALUES (:id,:organization_id,:facility_id,NULL,'Unconfigured Room',20,1)"
            ),
            {
                "id": ids["room"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO enrollments "
                "(id,organization_id,facility_id,child_id,program_id,room_id,start_date,status) "
                "VALUES (:id,:organization_id,:facility_id,:child_id,:program_id,:room_id,"
                "'2024-01-01','active')"
            ),
            {
                "id": ids["enrollment"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
                "child_id": ids["child"],
                "program_id": ids["program"],
                "room_id": ids["room"],
            },
        )
    engine.dispose()


def _seed_assigned_pending_enrollment(database_path: Path) -> None:
    ids = _ids()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Pending','Assigned','2023-01-01',1)"
            ),
            {
                "id": ids["child"],
                "organization_id": ids["organization"],
                "family_id": ids["family"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO facilities "
                "(id,organization_id,name,status,province,timezone,licensed_capacity,"
                "verification_status,shift_clock_radius_meters) "
                "VALUES (:id,:organization_id,'Migration Centre','active','Alberta',"
                "'America/Edmonton',20,'pending',150)"
            ),
            {"id": ids["facility"], "organization_id": ids["organization"]},
        )
        connection.execute(
            text(
                "INSERT INTO facility_programs "
                "(id,organization_id,facility_id,name,program_type,capacity,is_active) "
                "VALUES (:id,:organization_id,:facility_id,'Daycare','daycare',20,1)"
            ),
            {
                "id": ids["program"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO rooms "
                "(id,organization_id,facility_id,program_id,name,capacity,is_active) "
                "VALUES (:id,:organization_id,:facility_id,:program_id,'Assigned Room',20,1)"
            ),
            {
                "id": ids["room"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
                "program_id": ids["program"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO enrollments "
                "(id,organization_id,facility_id,child_id,program_id,room_id,start_date,status) "
                "VALUES (:id,:organization_id,:facility_id,:child_id,:program_id,:room_id,"
                "'2024-01-01','pending')"
            ),
            {
                "id": ids["enrollment"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
                "child_id": ids["child"],
                "program_id": ids["program"],
                "room_id": ids["room"],
            },
        )
    engine.dispose()


def _revision_and_0028_shape(database_path: Path) -> tuple:
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        receipt_count = (
            connection.scalar(text("SELECT count(*) FROM childcare_command_receipts"))
            if "childcare_command_receipts" in inspector.get_table_names()
            else None
        )
        claim_count = (
            connection.scalar(text("SELECT count(*) FROM childcare_command_claims"))
            if "childcare_command_claims" in inspector.get_table_names()
            else None
        )
        proof_count = (
            connection.scalar(text("SELECT count(*) FROM childcare_command_reconciliation_proofs"))
            if "childcare_command_reconciliation_proofs" in inspector.get_table_names()
            else None
        )
        slot_count = (
            connection.scalar(text("SELECT count(*) FROM childcare_command_slots"))
            if "childcare_command_slots" in inspector.get_table_names()
            else None
        )
        budget_entry_count = (
            connection.scalar(
                text("SELECT count(*) FROM childcare_command_reconciliation_budget_entries")
            )
            if "childcare_command_reconciliation_budget_entries" in inspector.get_table_names()
            else None
        )
        budget_count = (
            connection.scalar(text("SELECT count(*) FROM childcare_command_reconciliation_budgets"))
            if "childcare_command_reconciliation_budgets" in inspector.get_table_names()
            else None
        )
        retired_guardians = (
            connection.scalar(text("SELECT count(*) FROM guardians WHERE retired_at IS NOT NULL"))
            if "retired_at" in {column["name"] for column in inspector.get_columns("guardians")}
            else None
        )
    shape = (
        revision,
        tuple(sorted(inspector.get_table_names())),
        tuple(sorted(column["name"] for column in inspector.get_columns("guardians"))),
        tuple(sorted(index["name"] for index in inspector.get_indexes("enrollments"))),
        tuple(sorted(fk["name"] or "" for fk in inspector.get_foreign_keys("guardians"))),
        receipt_count,
        claim_count,
        proof_count,
        slot_count,
        budget_entry_count,
        budget_count,
        retired_guardians,
    )
    engine.dispose()
    return shape


def test_clean_0028_roundtrip_preserves_pending_server_default(
    tmp_path, monkeypatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "roundtrip")
    config = _config()
    command.upgrade(config, CURRENT_REVISION)

    engine = create_engine(f"sqlite:///{database_path}")
    ids = _ids()
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Default','Child','2023-01-01',1)"
            ),
            {
                "id": ids["child"],
                "organization_id": ids["organization"],
                "family_id": ids["family"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO facilities "
                "(id,organization_id,name,status,province,timezone,licensed_capacity,"
                "verification_status,shift_clock_radius_meters) "
                "VALUES (:id,:organization_id,'Default Centre','active','Alberta',"
                "'America/Edmonton',20,'pending',150)"
            ),
            {"id": ids["facility"], "organization_id": ids["organization"]},
        )
        connection.execute(
            text(
                "INSERT INTO enrollments "
                "(id,organization_id,facility_id,child_id,start_date) "
                "VALUES (:id,:organization_id,:facility_id,:child_id,'2024-01-01')"
            ),
            {
                "id": ids["enrollment"],
                "organization_id": ids["organization"],
                "facility_id": ids["facility"],
                "child_id": ids["child"],
            },
        )
        status = next(
            row
            for row in connection.execute(text("PRAGMA table_info(enrollments)")).mappings()
            if row["name"] == "status"
        )
        assert status["dflt_value"] == "'pending'"
        assert (
            connection.scalar(
                text("SELECT status FROM enrollments WHERE id=:id"),
                {"id": ids["enrollment"]},
            )
            == "pending"
        )
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        status = next(
            row
            for row in connection.execute(text("PRAGMA table_info(enrollments)")).mappings()
            if row["name"] == "status"
        )
        assert status["dflt_value"] is None
    engine.dispose()
    command.upgrade(config, CURRENT_REVISION)


@pytest.mark.parametrize(
    "seed,expected_fragment",
    [
        (_seed_duplicate_guardians, "duplicate_guardian_slots=1"),
        (_seed_null_program_room_placement, "incoherent_placements=1"),
        (_seed_assigned_pending_enrollment, "assigned_pending_enrollments=1"),
    ],
)
def test_upgrade_preflight_fails_before_any_schema_mutation(
    tmp_path,
    monkeypatch,
    seed,
    expected_fragment: str,
) -> None:
    database_path = _database(tmp_path, monkeypatch, seed.__name__)
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)
    seed(database_path)

    with pytest.raises(RuntimeError, match=expected_fragment):
        command.upgrade(config, CURRENT_REVISION)

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            PREVIOUS_REVISION
        )
    assert "childcare_command_receipts" not in inspector.get_table_names()
    assert "version" not in {column["name"] for column in inspector.get_columns("families")}
    assert "retired_at" not in {column["name"] for column in inspector.get_columns("guardians")}
    engine.dispose()


def test_populated_downgrade_is_refused_without_mutating_schema_or_history(
    tmp_path, monkeypatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "populated-downgrade")
    config = _config()
    command.upgrade(config, CURRENT_REVISION)
    ids = _ids()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                "VALUES (:id,'migration@example.com','unused','Migration','Actor',1,1)"
            ),
            {"id": ids["user"]},
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_receipts "
                "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                "request_hash,actor_user_id,committed_version,outcome) "
                "VALUES (:id,:organization_id,:operation_id,'family.guardian.primary.replace',"
                "'family',:family_id,:request_hash,:actor_user_id,2,'{}')"
            ),
            {
                "id": ids["receipt"],
                "organization_id": ids["organization"],
                "operation_id": ids["operation"],
                "family_id": ids["family"],
                "request_hash": "a" * 64,
                "actor_user_id": ids["user"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO guardians "
                "(id,organization_id,family_id,first_name,last_name,email,cell_phone,is_primary,"
                "authorized_pickup,created_operation_id,retired_operation_id,retired_at) "
                "VALUES (:id,:organization_id,:family_id,'Historical','Guardian','',"
                "'780-555-0199',1,1,:operation_id,:operation_id,CURRENT_TIMESTAMP)"
            ),
            {
                "id": ids["guardian_one"],
                "organization_id": ids["organization"],
                "family_id": ids["family"],
                "operation_id": ids["operation"],
            },
        )
    engine.dispose()
    before = _revision_and_0028_shape(database_path)

    with pytest.raises(RuntimeError, match=r"receipts=1, .*retired_guardians=1"):
        command.downgrade(config, PREVIOUS_REVISION)

    assert _revision_and_0028_shape(database_path) == before


def test_terminal_absence_history_and_quota_state_refuse_downgrade(tmp_path, monkeypatch) -> None:
    database_path = _database(tmp_path, monkeypatch, "absence-history-downgrade")
    config = _config()
    command.upgrade(config, CURRENT_REVISION)
    ids = _ids()
    proof_id = uuid4().hex
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        _seed_organization_family(connection, ids)
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                "VALUES (:id,'absence@example.com','unused','Absence','Actor',1,1)"
            ),
            {"id": ids["user"]},
        )
        values = {
            "organization_id": ids["organization"],
            "operation_id": ids["operation"],
            "actor_user_id": ids["user"],
        }
        connection.execute(
            text(
                "INSERT INTO childcare_command_slots "
                "(organization_id,client_operation_id,entry_kind,actor_user_id) "
                "VALUES (:organization_id,:operation_id,'absence_claim',:actor_user_id)"
            ),
            values,
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_claims "
                "(id,organization_id,client_operation_id,actor_user_id) "
                "VALUES (:id,:organization_id,:operation_id,:actor_user_id)"
            ),
            {**values, "id": ids["receipt"]},
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_reconciliation_proofs "
                "(id,organization_id,client_operation_id,actor_user_id) "
                "VALUES (:id,:organization_id,:operation_id,:actor_user_id)"
            ),
            {**values, "id": proof_id},
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_reconciliation_budget_entries "
                "(organization_id,actor_user_id,client_operation_id) "
                "VALUES (:organization_id,:actor_user_id,:operation_id)"
            ),
            values,
        )
        for kind, started in (
            ("hour", "2026-07-17 12:00:00+00:00"),
            ("day", "2026-07-17 00:00:00+00:00"),
        ):
            connection.execute(
                text(
                    "INSERT INTO childcare_command_reconciliation_budgets "
                    "(organization_id,actor_user_id,window_kind,window_started_at,"
                    "operation_count) VALUES "
                    "(:organization_id,:actor_user_id,:kind,:started,1)"
                ),
                {**values, "kind": kind, "started": started},
            )
    engine.dispose()
    before = _revision_and_0028_shape(database_path)

    with pytest.raises(
        RuntimeError,
        match=(
            r"absence_claims=1, reconciliation_proofs=1, operation_slots=1, "
            r"reconciliation_budget_entries=1, reconciliation_budgets=2"
        ),
    ):
        command.downgrade(config, PREVIOUS_REVISION)

    assert _revision_and_0028_shape(database_path) == before
