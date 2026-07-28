"""Portable proofs for the dormant 0029C normal-release data foundation."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
B = "0029B_release_context"
C = "0029C_verified_release_checkout"
ACTIVATION_TABLE = "facility_release_checkout_activations"


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


def _schema_signature(database_path: Path) -> tuple[tuple[object, ...], ...]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return tuple(
                tuple(row)
                for row in connection.execute(
                    text(
                        "SELECT type,name,tbl_name,sql FROM sqlite_master "
                        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                    )
                )
            )
    finally:
        engine.dispose()


def _column_map(database_path: Path, table_name: str) -> dict[str, dict]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        return {column["name"]: column for column in inspect(engine).get_columns(table_name)}
    finally:
        engine.dispose()


def _snapshot_values(*, policy: str = "government_photo_id") -> dict[str, object]:
    values: dict[str, object] = {
        name: uuid4().hex
        for name in (
            "id",
            "organization_id",
            "family_id",
            "facility_id",
            "child_id",
            "attendance_day_id",
            "attendance_interval_id",
            "checkout_event_id",
            "recipient_person_id",
            "recipient_person_version_id",
            "authorization_id",
            "evidence_id",
            "evidence_assessment_id",
            "actor_user_id",
            "actor_membership_id",
            "actor_role_id",
            "staff_shift_id",
            "room_id",
            "client_operation_id",
        )
    }
    values.update(
        {
            "recipient_display_name": "R" * 302,
            "recipient_relationship": "Parent",
            "attendance_day_version": 7,
            "authorization_version": 1,
            "evidence_assessment_version": 2,
            "authority_revision": 1,
            "restriction_digest_sha256": "a" * 64,
            "verification_method": (
                "government_photo_id_and_secondary_check"
                if policy == "government_photo_id_and_secondary_check"
                else "government_photo_id"
            ),
            "verification_result": "verified",
            "verification_policy_code": policy,
            "evidence_digest_sha256": "b" * 64,
            "decision_policy_version": "release-context-v1",
            "actor_role_key": "educator",
            "scope_basis": "organization_role",
            "room_assignment_id": None,
            "requested_at": "2026-07-18 08:00:00",
            "checked_out_at": "2026-07-18 08:00:01",
            "committed_at": "2026-07-18 08:00:01",
            "request_hash": "c" * 64,
            "release_mode": "normal",
            "override_reason_code": None,
            "override_justification": None,
        }
    )
    return values


def _activation_values() -> dict[str, object]:
    values = {
        name: uuid4().hex
        for name in (
            "id",
            "organization_id",
            "facility_id",
            "activated_by_user_id",
            "activated_by_membership_id",
            "activated_by_role_id",
            "activation_operation_id",
        )
    }
    values.update(
        {
            "activated_by_role_key": "owner",
            "activation_policy_version": "normal_verified_release_v1",
        }
    )
    return values


def _seed_activation_dependencies(
    connection,
    values: dict[str, object],
    *,
    overrides: dict[str, object] | None = None,
) -> None:
    dependency = {
        "membership_id": values["activated_by_membership_id"],
        "membership_user_id": values["activated_by_user_id"],
        "membership_role_id": values["activated_by_role_id"],
        "membership_status": "active",
        "role_id": values["activated_by_role_id"],
        "role_key": values["activated_by_role_key"],
        "receipt_operation_id": values["activation_operation_id"],
        "receipt_target_id": values["id"],
        "receipt_actor_user_id": values["activated_by_user_id"],
        "receipt_facility_id": values["facility_id"],
        "receipt_command_type": "facility.release_checkout.activate",
        "receipt_target_type": "release_activation",
        "receipt_committed_version": 1,
    }
    dependency.update(overrides or {})
    connection.execute(
        text(
            "INSERT INTO roles (id,organization_id,key,name,permissions,is_system) "
            "VALUES (:role_id,:organization_id,:role_key,'Release actor','[]',0)"
        ),
        {**values, **dependency},
    )
    connection.execute(
        text(
            "INSERT INTO organization_memberships "
            "(id,organization_id,user_id,role_id,status) VALUES "
            "(:membership_id,:organization_id,:membership_user_id,"
            ":membership_role_id,:membership_status)"
        ),
        {**values, **dependency},
    )
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,facility_id,committed_version,committed_at,outcome) "
            "VALUES (:receipt_id,:organization_id,:receipt_operation_id,"
            ":receipt_command_type,:receipt_target_type,:receipt_target_id,:request_hash,"
            ":receipt_actor_user_id,:receipt_facility_id,:receipt_committed_version,"
            ":committed_at,'{}')"
        ),
        {
            **values,
            **dependency,
            "receipt_id": uuid4().hex,
            "request_hash": "9" * 64,
            "committed_at": "2026-07-18 07:59:59",
        },
    )


def _insert_activation(connection, values: dict[str, object]) -> None:
    connection.execute(
        text(
            "INSERT INTO facility_release_checkout_activations "
            "(id,organization_id,facility_id,activated_by_user_id,"
            "activated_by_membership_id,activated_by_role_id,activated_by_role_key,"
            "activation_operation_id,activation_policy_version) VALUES "
            "(:id,:organization_id,:facility_id,:activated_by_user_id,"
            ":activated_by_membership_id,:activated_by_role_id,:activated_by_role_key,"
            ":activation_operation_id,:activation_policy_version)"
        ),
        values,
    )


def _seed_snapshot_dependencies(
    connection,
    values: dict[str, object],
    *,
    overrides: dict[str, object] | None = None,
) -> None:
    dependency = {
        "membership_id": values["actor_membership_id"],
        "membership_user_id": values["actor_user_id"],
        "membership_role_id": values["actor_role_id"],
        "membership_status": "active",
        "role_id": values["actor_role_id"],
        "role_key": values["actor_role_key"],
        "shift_id": values["staff_shift_id"],
        "shift_membership_id": values["actor_membership_id"],
        "shift_facility_id": values["facility_id"],
        "receipt_operation_id": values["client_operation_id"],
        "receipt_target_id": values["id"],
        "receipt_actor_user_id": values["actor_user_id"],
        "receipt_facility_id": values["facility_id"],
        "receipt_request_hash": values["request_hash"],
        "receipt_committed_at": values["committed_at"],
        "receipt_command_type": "attendance.release.checkout",
        "receipt_target_type": "attendance_release",
        "receipt_committed_version": 1,
        "event_id": values["checkout_event_id"],
        "event_day_id": values["attendance_day_id"],
        "event_operation_id": values["client_operation_id"],
        "event_actor_user_id": values["actor_user_id"],
        "event_occurred_at": values["checked_out_at"],
        "event_type": "check_out",
        "assignment_id": values["room_assignment_id"],
        "assignment_membership_id": values["actor_membership_id"],
        "assignment_facility_id": values["facility_id"],
        "assignment_room_id": values["room_id"],
    }
    dependency.update(overrides or {})
    connection.execute(
        text(
            "INSERT INTO roles (id,organization_id,key,name,permissions,is_system) "
            "VALUES (:role_id,:organization_id,:role_key,'Checkout actor','[]',0)"
        ),
        {**values, **dependency},
    )
    connection.execute(
        text(
            "INSERT INTO organization_memberships "
            "(id,organization_id,user_id,role_id,status) VALUES "
            "(:membership_id,:organization_id,:membership_user_id,"
            ":membership_role_id,:membership_status)"
        ),
        {**values, **dependency},
    )
    connection.execute(
        text(
            "INSERT INTO staff_shifts "
            "(id,organization_id,membership_id,facility_id,status,clocked_in_at) "
            "VALUES (:shift_id,:organization_id,:shift_membership_id,"
            ":shift_facility_id,'open','2026-07-18 07:00:00')"
        ),
        {**values, **dependency},
    )
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,facility_id,committed_version,committed_at,outcome) "
            "VALUES (:receipt_id,:organization_id,:receipt_operation_id,"
            ":receipt_command_type,:receipt_target_type,:receipt_target_id,"
            ":receipt_request_hash,:receipt_actor_user_id,:receipt_facility_id,"
            ":receipt_committed_version,:receipt_committed_at,'{}')"
        ),
        {**values, **dependency, "receipt_id": uuid4().hex},
    )
    connection.execute(
        text(
            "INSERT INTO attendance_events "
            "(id,organization_id,attendance_day_id,client_operation_id,actor_user_id,"
            "event_type,occurred_at) VALUES (:event_id,:organization_id,:event_day_id,"
            ":event_operation_id,:event_actor_user_id,:event_type,:event_occurred_at)"
        ),
        {**values, **dependency},
    )
    if dependency["assignment_id"] is not None:
        connection.execute(
            text(
                "INSERT INTO membership_room_assignments "
                "(id,organization_id,membership_id,facility_id,room_id,is_active,"
                "created_by_user_id) VALUES (:assignment_id,:organization_id,"
                ":assignment_membership_id,:assignment_facility_id,"
                ":assignment_room_id,1,:actor_user_id)"
            ),
            {**values, **dependency},
        )


def _insert_snapshot(
    connection,
    *,
    policy: str = "government_photo_id",
    attendance_day_version: int = 7,
    decision_policy_version: str = "release-context-v1",
    checked_out_at: str = "2026-07-18 08:00:01",
    committed_at: str = "2026-07-18 08:00:01",
    values: dict[str, object] | None = None,
    dependency_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    values = values or _snapshot_values(policy=policy)
    values["verification_policy_code"] = policy
    values["attendance_day_version"] = attendance_day_version
    values["decision_policy_version"] = decision_policy_version
    values["checked_out_at"] = checked_out_at
    values["committed_at"] = committed_at
    _seed_snapshot_dependencies(connection, values, overrides=dependency_overrides)
    connection.execute(
        text(
            "INSERT INTO attendance_release_snapshots "
            "(id,organization_id,family_id,facility_id,child_id,attendance_day_id,"
            "attendance_day_version,"
            "attendance_interval_id,checkout_event_id,recipient_person_id,"
            "recipient_person_version_id,recipient_display_name,recipient_relationship,"
            "authorization_id,authorization_version,evidence_id,evidence_assessment_id,"
            "evidence_assessment_version,authority_revision,restriction_digest_sha256,"
            "verification_method,verification_result,verification_policy_code,"
            "evidence_digest_sha256,decision_policy_version,actor_user_id,"
            "actor_membership_id,actor_role_id,actor_role_key,staff_shift_id,room_id,"
            "scope_basis,room_assignment_id,requested_at,checked_out_at,committed_at,"
            "client_operation_id,request_hash,release_mode,override_reason_code,"
            "override_justification) VALUES "
            "(:id,:organization_id,:family_id,:facility_id,:child_id,:attendance_day_id,"
            ":attendance_day_version,"
            ":attendance_interval_id,:checkout_event_id,:recipient_person_id,"
            ":recipient_person_version_id,:recipient_display_name,:recipient_relationship,"
            ":authorization_id,:authorization_version,:evidence_id,:evidence_assessment_id,"
            ":evidence_assessment_version,:authority_revision,:restriction_digest_sha256,"
            ":verification_method,:verification_result,:verification_policy_code,"
            ":evidence_digest_sha256,:decision_policy_version,:actor_user_id,"
            ":actor_membership_id,:actor_role_id,:actor_role_key,:staff_shift_id,:room_id,"
            ":scope_basis,:room_assignment_id,:requested_at,:checked_out_at,:committed_at,"
            ":client_operation_id,:request_hash,:release_mode,:override_reason_code,"
            ":override_justification)"
        ),
        values,
    )
    return values


def test_fresh_c_foundation_has_exact_shape_and_empty_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    assert _current(database_path) == C

    activation = _column_map(database_path, ACTIVATION_TABLE)
    assert set(activation) == {
        "id",
        "organization_id",
        "facility_id",
        "activated_by_user_id",
        "activated_by_membership_id",
        "activated_by_role_id",
        "activated_by_role_key",
        "activation_operation_id",
        "activation_policy_version",
        "activated_at",
    }
    assert all(not column["nullable"] for column in activation.values())
    snapshot = _column_map(database_path, "attendance_release_snapshots")
    assert snapshot["recipient_display_name"]["type"].length == 302
    assert snapshot["attendance_day_version"]["nullable"] is False
    assert snapshot["verification_policy_code"]["type"].length == 64
    for required in (
        "actor_membership_id",
        "actor_role_id",
        "actor_role_key",
        "staff_shift_id",
        "room_id",
        "scope_basis",
        "checked_out_at",
    ):
        assert snapshot[required]["nullable"] is False
    assert snapshot["room_assignment_id"]["nullable"] is True

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        checks = {
            item["name"]: item["sqltext"]
            for item in inspector.get_check_constraints("attendance_release_snapshots")
        }
        assert "ck_release_snapshots_executable_verification_policy" in checks
        assert (
            "government_photo_id_and_secondary_check"
            not in checks["ck_release_snapshots_executable_verification_policy"]
        )
        assert "release-context-v1" in checks["ck_release_snapshots_decision_policy_version"]
        activation_checks = {
            item["name"]: item["sqltext"]
            for item in inspector.get_check_constraints(ACTIVATION_TABLE)
        }
        assert (
            "normal_verified_release_v1"
            in activation_checks["ck_release_checkout_activations_policy_version"]
        )
        trigger_names = set(
            engine.connect()
            .execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
            .scalars()
        )
        assert {
            "facility_release_checkout_activations_insert_guard",
            "facility_release_checkout_activations_no_update",
            "facility_release_checkout_activations_no_delete",
            "attendance_release_snapshots_insert_guard",
            "attendance_release_snapshots_no_update",
            "attendance_release_snapshots_no_delete",
        } <= trigger_names
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, C)
    assert _current(database_path) == C
    command.downgrade(config, B)
    assert _current(database_path) == B
    assert (
        ACTIVATION_TABLE
        not in inspect(create_engine(f"sqlite:///{database_path}")).get_table_names()
    )
    downgraded_snapshot = _column_map(database_path, "attendance_release_snapshots")
    assert downgraded_snapshot["recipient_display_name"]["type"].length == 240
    assert "verification_policy_code" not in downgraded_snapshot
    assert "attendance_day_version" not in downgraded_snapshot
    downgraded_engine = create_engine(f"sqlite:///{database_path}")
    try:
        with downgraded_engine.connect() as connection:
            downgraded_trigger_names = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='trigger' "
                        "AND name IN ('attendance_release_snapshots_insert_guard',"
                        "'attendance_release_snapshots_no_update',"
                        "'attendance_release_snapshots_no_delete')"
                    )
                ).scalars()
            )
        assert downgraded_trigger_names == set()
    finally:
        downgraded_engine.dispose()

    command.upgrade(config, C)
    assert _current(database_path) == C


def test_checkout_permission_is_exact_and_custom_roles_remain_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    organization_id = uuid4().hex
    role_rows = {
        "owner": (["organization:manage", "release:read"], True),
        "administrator": (["staff:manage", "release:read"], True),
        "educator": (["attendance:record", "release:read"], True),
        "custom_release_coordinator": (["release:read"], False),
    }
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations "
                    "(id,name,status,timezone,preferences,verification_status) "
                    "VALUES (:id,'C permission proof','active','America/Edmonton',"
                    "'{}','pending')"
                ),
                {"id": organization_id},
            )
            for key, (permissions, is_system) in role_rows.items():
                connection.execute(
                    text(
                        "INSERT INTO roles "
                        "(id,organization_id,key,name,permissions,is_system) "
                        "VALUES (:id,:organization_id,:key,:name,:permissions,:is_system)"
                    ),
                    {
                        "id": uuid4().hex,
                        "organization_id": organization_id,
                        "key": key,
                        "name": key.replace("_", " ").title(),
                        "permissions": json.dumps(permissions),
                        "is_system": is_system,
                    },
                )
    finally:
        engine.dispose()

    command.upgrade(config, C)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            upgraded = {
                row.key: json.loads(row.permissions)
                for row in connection.execute(text("SELECT key,permissions FROM roles"))
            }
        for key in ("owner", "administrator", "educator"):
            assert upgraded[key] == [*role_rows[key][0], "release:checkout"]
        assert upgraded["custom_release_coordinator"] == ["release:read"]
    finally:
        engine.dispose()

    command.downgrade(config, B)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            downgraded = {
                row.key: json.loads(row.permissions)
                for row in connection.execute(text("SELECT key,permissions FROM roles"))
            }
        assert downgraded == {key: values[0] for key, values in role_rows.items()}
    finally:
        engine.dispose()


def test_existing_ordinary_receipt_is_preserved_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, B)
    organization_id = uuid4().hex
    user_id = uuid4().hex
    receipt_id = uuid4().hex
    operation_id = uuid4().hex
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations "
                    "(id,name,status,timezone,preferences,verification_status) "
                    "VALUES (:id,'C preservation proof','active','America/Edmonton',"
                    "'{}','pending')"
                ),
                {"id": organization_id},
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                    "VALUES (:id,:email,'unused','Preserved','Actor',1,1)"
                ),
                {
                    "id": user_id,
                    "email": f"preserved-{uuid4().hex}@example.test",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO childcare_command_receipts "
                    "(id,organization_id,client_operation_id,command_type,target_type,"
                    "target_id,request_hash,actor_user_id,committed_version,outcome) "
                    "VALUES (:id,:organization_id,:operation_id,'child.update','child',"
                    ":target_id,:request_hash,:actor_user_id,3,:outcome)"
                ),
                {
                    "id": receipt_id,
                    "organization_id": organization_id,
                    "operation_id": operation_id,
                    "target_id": uuid4().hex,
                    "request_hash": "d" * 64,
                    "actor_user_id": user_id,
                    "outcome": json.dumps({"preserved": True}, separators=(",", ":")),
                },
            )
        with engine.connect() as connection:
            before = tuple(
                connection.execute(
                    text("SELECT * FROM childcare_command_receipts WHERE id=:id"),
                    {"id": receipt_id},
                ).one()
            )
    finally:
        engine.dispose()

    command.upgrade(config, C)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            after_upgrade = tuple(
                connection.execute(
                    text("SELECT * FROM childcare_command_receipts WHERE id=:id"),
                    {"id": receipt_id},
                ).one()
            )
        assert after_upgrade == before
    finally:
        engine.dispose()

    command.downgrade(config, B)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            after_downgrade = tuple(
                connection.execute(
                    text("SELECT * FROM childcare_command_receipts WHERE id=:id"),
                    {"id": receipt_id},
                ).one()
            )
        assert after_downgrade == before
    finally:
        engine.dispose()


def test_activation_rows_are_fixed_policy_unique_and_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    values = _activation_values()
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            _seed_activation_dependencies(connection, values)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            _insert_activation(
                connection,
                {**values, "activation_policy_version": "invented-v2"},
            )
        with engine.begin() as connection:
            _insert_activation(connection, values)
        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE facility_release_checkout_activations "
                    "SET activated_by_role_key='administrator' WHERE id=:id"
                ),
                {"id": values["id"]},
            )
        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text("DELETE FROM facility_release_checkout_activations WHERE id=:id"),
                {"id": values["id"]},
            )
    finally:
        engine.dispose()


def test_activation_insert_guard_rejects_every_inconsistent_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    cases: tuple[tuple[str, dict[str, object], dict[str, object]], ...] = (
        ("membership", {"activated_by_membership_id": uuid4().hex}, {}),
        ("membership actor", {}, {"membership_user_id": uuid4().hex}),
        ("membership role", {}, {"membership_role_id": uuid4().hex}),
        ("membership status", {}, {"membership_status": "suspended"}),
        ("role key", {"activated_by_role_key": "administrator"}, {}),
        ("receipt operation", {}, {"receipt_operation_id": uuid4().hex}),
        ("receipt target", {"id": uuid4().hex}, {}),
        ("receipt actor", {}, {"receipt_actor_user_id": uuid4().hex}),
        ("receipt facility", {}, {"receipt_facility_id": uuid4().hex}),
        ("receipt command", {}, {"receipt_command_type": "facility.update"}),
        ("receipt target type", {}, {"receipt_target_type": "family"}),
        ("receipt version", {}, {"receipt_committed_version": 2}),
    )
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        for label, row_changes, dependency_changes in cases:
            coherent_values = _activation_values()
            values = {**coherent_values, **row_changes}
            with (
                pytest.raises(IntegrityError, match="relational consistency") as raised,
                engine.begin() as connection,
            ):
                _seed_activation_dependencies(
                    connection,
                    coherent_values,
                    overrides=dependency_changes,
                )
                _insert_activation(connection, values)
            assert "activation" in str(raised.value), label
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM facility_release_checkout_activations")
                )
                == 0
            )
    finally:
        engine.dispose()


def test_secondary_check_policy_cannot_be_persisted_as_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            _insert_snapshot(
                connection,
                policy="government_photo_id_and_secondary_check",
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            _insert_snapshot(connection, attendance_day_version=0)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            _insert_snapshot(connection, decision_policy_version="invented-v2")
        with pytest.raises(IntegrityError), engine.begin() as connection:
            _insert_snapshot(
                connection,
                checked_out_at="2026-07-18 08:00:01",
                committed_at="2026-07-18 08:00:02",
            )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM attendance_release_snapshots")) == 0
    finally:
        engine.dispose()


def test_snapshot_insert_guard_accepts_exact_optional_room_assignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    values = _snapshot_values()
    values["scope_basis"] = "room_assignment"
    values["room_assignment_id"] = uuid4().hex
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            _insert_snapshot(connection, values=values)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM attendance_release_snapshots")) == 1
    finally:
        engine.dispose()


def test_snapshot_insert_guard_rejects_every_inconsistent_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("membership id", {"membership_id": uuid4().hex}),
        ("membership actor", {"membership_user_id": uuid4().hex}),
        ("membership role", {"membership_role_id": uuid4().hex}),
        ("membership status", {"membership_status": "suspended"}),
        ("role id", {"role_id": uuid4().hex}),
        ("role key", {"role_key": "owner"}),
        ("shift id", {"shift_id": uuid4().hex}),
        ("shift membership", {"shift_membership_id": uuid4().hex}),
        ("shift facility", {"shift_facility_id": uuid4().hex}),
        ("receipt operation", {"receipt_operation_id": uuid4().hex}),
        ("receipt target", {"receipt_target_id": uuid4().hex}),
        ("receipt actor", {"receipt_actor_user_id": uuid4().hex}),
        ("receipt facility", {"receipt_facility_id": uuid4().hex}),
        ("receipt hash", {"receipt_request_hash": "d" * 64}),
        ("receipt commit", {"receipt_committed_at": "2026-07-18 08:00:02"}),
        ("receipt command", {"receipt_command_type": "attendance.check_out"}),
        ("receipt target type", {"receipt_target_type": "family"}),
        ("receipt version", {"receipt_committed_version": 2}),
        ("event id", {"event_id": uuid4().hex}),
        ("event day", {"event_day_id": uuid4().hex}),
        ("event operation", {"event_operation_id": uuid4().hex}),
        ("event actor", {"event_actor_user_id": uuid4().hex}),
        ("event time", {"event_occurred_at": "2026-07-18 08:00:02"}),
        ("event type", {"event_type": "status_update"}),
    )
    assignment_cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("assignment id", {"assignment_id": uuid4().hex}),
        ("assignment membership", {"assignment_membership_id": uuid4().hex}),
        ("assignment facility", {"assignment_facility_id": uuid4().hex}),
        ("assignment room", {"assignment_room_id": uuid4().hex}),
    )
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        for label, dependency_changes in cases:
            with (
                pytest.raises(IntegrityError, match="relational consistency") as raised,
                engine.begin() as connection,
            ):
                _insert_snapshot(
                    connection,
                    values=_snapshot_values(),
                    dependency_overrides=dependency_changes,
                )
            assert "snapshot" in str(raised.value), label

        for label, dependency_changes in assignment_cases:
            values = _snapshot_values()
            values["scope_basis"] = "room_assignment"
            values["room_assignment_id"] = uuid4().hex
            with (
                pytest.raises(IntegrityError, match="relational consistency") as raised,
                engine.begin() as connection,
            ):
                _insert_snapshot(
                    connection,
                    values=values,
                    dependency_overrides=dependency_changes,
                )
            assert "snapshot" in str(raised.value), label

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM attendance_release_snapshots")) == 0
    finally:
        engine.dispose()


def test_release_snapshots_are_immutable_after_insert(tmp_path, monkeypatch) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            _insert_snapshot(connection)
            snapshot_id = connection.scalar(text("SELECT id FROM attendance_release_snapshots"))
        assert snapshot_id is not None

        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE attendance_release_snapshots "
                    "SET recipient_display_name='Changed' WHERE id=:snapshot_id"
                ),
                {"snapshot_id": snapshot_id},
            )
        with pytest.raises(IntegrityError, match="immutable"), engine.begin() as connection:
            connection.execute(
                text("DELETE FROM attendance_release_snapshots WHERE id=:snapshot_id"),
                {"snapshot_id": snapshot_id},
            )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM attendance_release_snapshots")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("history_kind", ["activation", "snapshot", "receipt"])
def test_downgrade_refuses_before_any_ddl_when_c_history_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history_kind: str,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            if history_kind == "snapshot":
                _insert_snapshot(connection)
            elif history_kind == "activation":
                values = _activation_values()
                values["activated_by_role_key"] = "administrator"
                _seed_activation_dependencies(connection, values)
                _insert_activation(connection, values)
            else:
                organization_id = uuid4().hex
                user_id = uuid4().hex
                connection.execute(
                    text(
                        "INSERT INTO organizations "
                        "(id,name,status,timezone,preferences,verification_status) "
                        "VALUES (:id,'Receipt history','active','America/Edmonton',"
                        "'{}','pending')"
                    ),
                    {"id": organization_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                        "VALUES (:id,:email,'unused','Receipt','Actor',1,1)"
                    ),
                    {"id": user_id, "email": f"receipt-{uuid4().hex}@example.test"},
                )
                connection.execute(
                    text(
                        "INSERT INTO childcare_command_receipts "
                        "(id,organization_id,client_operation_id,command_type,target_type,"
                        "target_id,request_hash,actor_user_id,committed_version,outcome) "
                        "VALUES (:id,:organization_id,:operation_id,"
                        "'facility.release_checkout.activate','release_activation',"
                        ":target_id,:request_hash,:actor_user_id,1,'{}')"
                    ),
                    {
                        "id": uuid4().hex,
                        "organization_id": organization_id,
                        "operation_id": uuid4().hex,
                        "target_id": uuid4().hex,
                        "request_hash": "e" * 64,
                        "actor_user_id": user_id,
                    },
                )
    finally:
        engine.dispose()

    before = _schema_signature(database_path)
    with pytest.raises(RuntimeError, match="0029C downgrade refused before DDL"):
        command.downgrade(config, B)
    assert _current(database_path) == C
    assert _schema_signature(database_path) == before
    assert not any(name.startswith("_alembic_tmp_") for _, name, _, _ in before)


def test_sqlite_multirevision_downgrade_refuses_before_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, C)
    before = _schema_signature(database_path)

    with pytest.raises(RuntimeError, match="0029C SQLite downgrade refused before DDL"):
        command.downgrade(config, "0029A2_authority_activation")

    assert _current(database_path) == C
    assert _schema_signature(database_path) == before
