"""SQLite migration gates for the 0029A family-authority kernel.

The suite deliberately creates a new database under ``tmp_path`` for every
test.  Alembic now honors an explicit ``sqlalchemy.url`` override and rejects
retained loopback ports in tests; this module also sets the complete SQLite
environment as an independent defense-in-depth boundary.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0028_childcare_command_spine"
KERNEL_REVISION = "0029A_family_authority_kernel"
VAULT_REVISION = "0029A1_family_evidence_vault"
ACTIVATION_REVISION = "0029A2_authority_activation"
RELEASE_CONTEXT_REVISION = "0029B_release_context"
VERIFIED_RELEASE_REVISION = "0029C_verified_release_checkout"
AUTHORITY_TABLES = {
    "family_authority_people",
    "family_authority_person_versions",
    "family_authority_evidence",
    "family_authority_evidence_assessments",
    "child_authority_heads",
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
    "attendance_release_snapshots",
}

ACTIVATION_TABLES = {
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
}

AUTHORITY_INSERT_TABLES = {
    "family_authority_people",
    "family_authority_person_versions",
    "family_authority_evidence",
    "family_authority_evidence_assessments",
    "child_authority_heads",
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
}
VAULT_INSERT_TABLES = {
    "family_authority_evidence_objects",
    "family_authority_evidence_object_assessments",
}
AUTHORITY_SELECT_ONLY_TABLES = AUTHORITY_TABLES - AUTHORITY_INSERT_TABLES
AUTHORITY_UPDATE_COLUMNS = {
    "family_authority_people": {
        "version",
        "status",
        "current_person_version_id",
        "last_operation_id",
        "retired_at",
        "retired_operation_id",
        "updated_at",
    },
    "family_authority_person_versions": {"closed_at", "closed_operation_id"},
    "child_authority_heads": {"revision", "last_operation_id", "updated_at"},
    "child_release_authorizations": {
        "version",
        "revoked_at",
        "revoked_operation_id",
        "revocation_reason_code",
        "updated_at",
    },
    "child_release_rules": {
        "version",
        "revoked_at",
        "revoked_operation_id",
        "revocation_reason_code",
        "updated_at",
    },
    "child_consent_decisions": {
        "version",
        "withdrawn_at",
        "withdrawn_operation_id",
        "withdrawal_reason_code",
        "updated_at",
    },
}
AUTHORITY_GUARD_FUNCTIONS = {
    "caresync_family_authority_insert_guard",
    "caresync_family_authority_transition_guard",
    "caresync_family_authority_temporal_guard",
    "caresync_family_authority_person_invariant",
    "caresync_family_authority_child_revision_invariant",
    "caresync_family_authority_activation_guard",
}
VAULT_GUARD_FUNCTIONS = {
    "caresync_family_evidence_object_write_guard",
    "caresync_family_evidence_object_invariant",
    "caresync_family_evidence_object_link_guard",
    "caresync_family_evidence_review_guard",
}

RECEIPT_TARGET_TYPES = {
    "family",
    "child",
    "enrollment",
    "authority_person",
    "authority_evidence",
    "authority_evidence_object",
    "release_authorization",
    "release_rule",
    "consent",
    "release_activation",
    "attendance_release",
}

EXPECTED_COLUMNS = {
    "family_authority_people": {
        "id",
        "organization_id",
        "family_id",
        "version",
        "status",
        "current_person_version_id",
        "source_guardian_id",
        "source_emergency_contact_id",
        "created_operation_id",
        "last_operation_id",
        "retired_at",
        "retired_operation_id",
        "created_at",
        "updated_at",
    },
    "family_authority_person_versions": {
        "id",
        "organization_id",
        "family_id",
        "person_id",
        "version_number",
        "first_name",
        "middle_name",
        "last_name",
        "preferred_name",
        "relationship_kind",
        "relationship_detail",
        "email",
        "primary_phone",
        "created_operation_id",
        "closed_at",
        "closed_operation_id",
        "created_at",
    },
    "family_authority_evidence": {
        "id",
        "organization_id",
        "family_id",
        "evidence_kind",
        "source_label",
        "evidence_object_id",
        "storage_reference",
        "media_type",
        "byte_size",
        "content_sha256",
        "issued_at",
        "captured_at",
        "expires_at",
        "recorded_by_user_id",
        "created_operation_id",
        "created_at",
    },
    "family_authority_evidence_assessments": {
        "id",
        "organization_id",
        "family_id",
        "evidence_id",
        "version_number",
        "decision",
        "assessed_epistemic_status",
        "reason_code",
        "confidential_note",
        "superseded_by_evidence_id",
        "actor_user_id",
        "created_operation_id",
        "created_at",
    },
    "child_authority_heads": {
        "organization_id",
        "family_id",
        "child_id",
        "revision",
        "created_operation_id",
        "last_operation_id",
        "created_at",
        "updated_at",
    },
    "child_release_authorizations": {
        "id",
        "organization_id",
        "family_id",
        "child_id",
        "recipient_person_id",
        "verification_policy_code",
        "grantor_person_id",
        "grantor_person_version_id",
        "grantor_authority_basis",
        "basis_evidence_id",
        "basis_evidence_assessment_id",
        "effective_from",
        "effective_until",
        "version",
        "created_operation_id",
        "revoked_at",
        "revoked_operation_id",
        "revocation_reason_code",
        "created_at",
        "updated_at",
    },
    "child_release_rules": {
        "id",
        "organization_id",
        "family_id",
        "child_id",
        "rule_kind",
        "scope_kind",
        "scope_person_id",
        "directing_person_id",
        "directing_person_version_id",
        "authority_basis_code",
        "basis_evidence_id",
        "basis_evidence_assessment_id",
        "safe_explanation_code",
        "confidential_reason",
        "effective_from",
        "effective_until",
        "version",
        "created_operation_id",
        "revoked_at",
        "revoked_operation_id",
        "revocation_reason_code",
        "created_at",
        "updated_at",
    },
    "consent_policy_versions": {
        "id",
        "organization_id",
        "purpose_code",
        "version_number",
        "title",
        "content_reference",
        "content_text",
        "content_sha256",
        "signer_authority_requirement",
        "effective_from",
        "effective_until",
        "created_operation_id",
        "published_at",
    },
    "child_consent_decisions": {
        "id",
        "organization_id",
        "family_id",
        "child_id",
        "purpose_code",
        "policy_version_id",
        "signer_person_id",
        "signer_person_version_id",
        "signer_authority_basis",
        "evidence_id",
        "evidence_assessment_id",
        "signer_authority_evidence_id",
        "signer_authority_evidence_assessment_id",
        "decision",
        "scope_kind",
        "scope_facility_id",
        "scope_reference",
        "effective_from",
        "effective_until",
        "version",
        "created_operation_id",
        "withdrawn_at",
        "withdrawn_operation_id",
        "withdrawal_reason_code",
        "created_at",
        "updated_at",
    },
    "attendance_release_snapshots": {
        "id",
        "organization_id",
        "family_id",
        "facility_id",
        "child_id",
        "attendance_day_id",
        "attendance_day_version",
        "attendance_interval_id",
        "checkout_event_id",
        "recipient_person_id",
        "recipient_person_version_id",
        "recipient_display_name",
        "recipient_relationship",
        "authorization_id",
        "authorization_version",
        "authority_revision",
        "restriction_digest_sha256",
        "verification_method",
        "verification_result",
        "verification_policy_code",
        "evidence_id",
        "evidence_assessment_id",
        "evidence_assessment_version",
        "evidence_digest_sha256",
        "decision_policy_version",
        "actor_user_id",
        "actor_membership_id",
        "actor_role_id",
        "actor_role_key",
        "staff_shift_id",
        "room_id",
        "scope_basis",
        "room_assignment_id",
        "requested_at",
        "checked_out_at",
        "committed_at",
        "client_operation_id",
        "request_hash",
        "release_mode",
        "override_reason_code",
        "override_justification",
    },
}


def _config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    database_path = directory / "caresync.db"

    # Keep the complete explicit SQLite environment even though env.py also
    # honors Config URL overrides and rejects retained PostgreSQL test ports.
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.delenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", raising=False)
    assert database_path.name == "caresync.db"
    assert "5434" not in str(database_path)
    return database_path


def _engine(database_path: Path):
    return create_engine(f"sqlite:///{database_path}")


def _seed_actor_and_organization(connection) -> dict[str, str]:
    ids = {name: uuid4().hex for name in ("organization", "user", "family_a", "family_b")}
    connection.execute(
        text(
            "INSERT INTO organizations "
            "(id,name,status,timezone,preferences,verification_status) "
            "VALUES (:id,'Authority Gate','active','America/Edmonton','{}','pending')"
        ),
        {"id": ids["organization"]},
    )
    connection.execute(
        text(
            "INSERT INTO users "
            "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
            "VALUES (:id,:email,'unused','Authority','Gate',1,1)"
        ),
        {"id": ids["user"], "email": f"authority-{uuid4().hex}@example.test"},
    )
    for key, name in (("family_a", "Family A"), ("family_b", "Family B")):
        connection.execute(
            text(
                "INSERT INTO families "
                "(id,organization_id,name,status,photo_consent,field_trip_consent,"
                "emergency_medical_consent) "
                "VALUES (:id,:organization_id,:name,'active',0,0,0)"
            ),
            {"id": ids[key], "organization_id": ids["organization"], "name": name},
        )
    return ids


def _insert_receipt(
    connection,
    ids: dict[str, str],
    *,
    target_type: str,
    target_id: str | None = None,
    command_type: str = "family.authority.test",
) -> str:
    operation_id = uuid4().hex
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,committed_version,outcome) "
            "VALUES (:id,:organization_id,:operation_id,:command_type,:target_type,:target_id,"
            ":request_hash,:actor_user_id,1,'{}')"
        ),
        {
            "id": uuid4().hex,
            "organization_id": ids["organization"],
            "operation_id": operation_id,
            "command_type": command_type,
            "target_type": target_type,
            "target_id": target_id or uuid4().hex,
            "request_hash": uuid4().hex * 2,
            "actor_user_id": ids["user"],
        },
    )
    return operation_id


def _foreign_key_signatures(
    inspector, table_name: str
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _assert_foreign_key(
    inspector,
    table_name: str,
    columns: tuple[str, ...],
    referred_table: str,
    referred_columns: tuple[str, ...],
) -> None:
    assert (columns, referred_table, referred_columns) in _foreign_key_signatures(
        inspector, table_name
    )


def _check_text(inspector, table_name: str) -> str:
    return " ".join(
        str(constraint.get("sqltext") or "")
        for constraint in inspector.get_check_constraints(table_name)
    ).lower()


def _unique_signatures(inspector, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _shape(database_path: Path) -> tuple[object, ...]:
    engine = _engine(database_path)
    inspector = inspect(engine)
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        new_target_receipts = connection.scalar(
            text(
                "SELECT count(*) FROM childcare_command_receipts WHERE target_type IN "
                "('authority_person','authority_evidence','release_authorization',"
                "'release_rule','consent','release_activation','attendance_release')"
            )
        )
    shape = (
        revision,
        tuple(sorted(inspector.get_table_names())),
        tuple(
            (table, tuple(sorted(column["name"] for column in inspector.get_columns(table))))
            for table in sorted(AUTHORITY_TABLES.intersection(inspector.get_table_names()))
        ),
        new_target_receipts,
    )
    engine.dispose()
    return shape


def _authority_check_case(case: str) -> tuple[str, dict[str, object], str]:
    ids = {
        name: uuid4().hex
        for name in (
            "row",
            "organization",
            "family",
            "child",
            "person",
            "person_version",
            "evidence",
            "assessment",
            "signer_evidence",
            "signer_assessment",
            "policy",
            "facility",
            "day",
            "interval",
            "event",
            "authorization",
            "actor",
            "membership",
            "role",
            "shift",
            "room",
            "operation",
            "terminal_operation",
        )
    }
    start = "2026-01-01 08:00:00+00:00"
    end = "2026-01-02 08:00:00+00:00"
    valid_hash = "a" * 64
    non_hex_hash = "z" * 64

    if case in {
        "evidence_missing_byte_size",
        "evidence_non_hex_digest",
        "evidence_public_storage_reference",
        "evidence_trailing_storage_segment",
        "evidence_invalid_media_type",
        "evidence_oversized_byte_size",
    }:
        return (
            "INSERT INTO family_authority_evidence "
            "(id,organization_id,family_id,evidence_kind,source_label,"
            "storage_reference,media_type,byte_size,content_sha256,"
            "recorded_by_user_id,created_operation_id) VALUES "
            "(:row,:organization,:family,'custody_document',"
            "'Direct constraint gate',:storage_reference,:media_type,"
            ":byte_size,:content_sha256,:actor,:operation)",
            {
                **ids,
                "byte_size": (
                    None
                    if case == "evidence_missing_byte_size"
                    else 52_428_801
                    if case == "evidence_oversized_byte_size"
                    else 1
                ),
                "content_sha256": (
                    non_hex_hash if case == "evidence_non_hex_digest" else valid_hash
                ),
                "storage_reference": (
                    "https://public.example/evidence"
                    if case == "evidence_public_storage_reference"
                    else (
                        "authority/evidence/"
                        if case == "evidence_trailing_storage_segment"
                        else "authority/evidence"
                    )
                ),
                "media_type": (
                    "not a type" if case == "evidence_invalid_media_type" else "image/jpeg"
                ),
            },
            (
                "ck_authority_evidence_storage_tuple"
                if case == "evidence_missing_byte_size"
                else (
                    "ck_authority_evidence_storage_reference"
                    if case
                    in {
                        "evidence_public_storage_reference",
                        "evidence_trailing_storage_segment",
                    }
                    else (
                        "ck_authority_evidence_media_type"
                        if case == "evidence_invalid_media_type"
                        else (
                            "ck_authority_evidence_byte_size"
                            if case == "evidence_oversized_byte_size"
                            else "ck_authority_evidence_sha256"
                        )
                    )
                )
            ),
        )
    if case in {
        "assessment_reviewed_with_reason",
        "assessment_rejected_without_reason",
        "assessment_other_without_note",
        "assessment_self_supersession",
    }:
        decision = {
            "assessment_reviewed_with_reason": "reviewed",
            "assessment_rejected_without_reason": "rejected",
            "assessment_other_without_note": "rejected",
            "assessment_self_supersession": "superseded",
        }[case]
        return (
            "INSERT INTO family_authority_evidence_assessments "
            "(id,organization_id,family_id,evidence_id,version_number,decision,"
            "assessed_epistemic_status,reason_code,confidential_note,"
            "superseded_by_evidence_id,actor_user_id,created_operation_id) VALUES "
            "(:row,:organization,:family,:evidence,:version_number,:decision,"
            ":epistemic_status,:reason_code,NULL,:superseded_by,:actor,:operation)",
            {
                **ids,
                "version_number": 3 if decision == "superseded" else 2,
                "decision": decision,
                "epistemic_status": "reported" if decision == "reviewed" else None,
                "reason_code": (
                    "entered_in_error"
                    if case == "assessment_reviewed_with_reason"
                    else "other"
                    if case == "assessment_other_without_note"
                    else "superseded"
                    if decision == "superseded"
                    else None
                ),
                "superseded_by": ids["evidence"] if decision == "superseded" else None,
            },
            (
                "ck_authority_evidence_assessments_note"
                if case == "assessment_other_without_note"
                else "ck_authority_evidence_assessments_supersession"
                if case == "assessment_self_supersession"
                else "ck_authority_evidence_assessments_outcome"
            ),
        )
    if case == "authorization_null_revocation_reason":
        return (
            "INSERT INTO child_release_authorizations "
            "(id,organization_id,family_id,child_id,recipient_person_id,"
            "verification_policy_code,grantor_person_id,grantor_person_version_id,"
            "grantor_authority_basis,basis_evidence_id,effective_from,effective_until,"
            "basis_evidence_assessment_id,"
            "version,created_operation_id,revoked_at,revoked_operation_id,"
            "revocation_reason_code) VALUES "
            "(:row,:organization,:family,:child,:person,'government_photo_id',:person,"
            ":person_version,'guardian_record',:evidence,:start,:end,:assessment,2,"
            ":operation,:end,"
            ":terminal_operation,NULL)",
            {**ids, "start": start, "end": end},
            "ck_release_authorizations_revocation",
        )
    if case == "rule_null_revocation_reason":
        return (
            "INSERT INTO child_release_rules "
            "(id,organization_id,family_id,child_id,rule_kind,scope_kind,scope_person_id,"
            "directing_person_id,directing_person_version_id,authority_basis_code,"
            "basis_evidence_id,basis_evidence_assessment_id,safe_explanation_code,"
            "confidential_reason,effective_from,"
            "effective_until,version,created_operation_id,revoked_at,revoked_operation_id,"
            "revocation_reason_code) VALUES "
            "(:row,:organization,:family,:child,'deny','all_recipients',NULL,NULL,NULL,"
            "'reviewed_custody_evidence',:evidence,:assessment,'release_restricted',"
            "'Court direction',"
            ":start,:end,2,:operation,:end,:terminal_operation,NULL)",
            {**ids, "start": start, "end": end},
            "ck_release_rules_revocation",
        )
    if case == "consent_null_withdrawal_reason":
        return (
            "INSERT INTO child_consent_decisions "
            "(id,organization_id,family_id,child_id,purpose_code,policy_version_id,"
            "signer_person_id,signer_person_version_id,signer_authority_basis,evidence_id,"
            "evidence_assessment_id,signer_authority_evidence_id,"
            "signer_authority_evidence_assessment_id,"
            "decision,scope_kind,scope_facility_id,scope_reference,effective_from,"
            "effective_until,version,created_operation_id,withdrawn_at,"
            "withdrawn_operation_id,withdrawal_reason_code) VALUES "
            "(:row,:organization,:family,:child,'off_site_activity',:policy,:person,"
            ":person_version,'guardian_record',:evidence,:assessment,:signer_evidence,"
            ":signer_assessment,'granted','policy',NULL,NULL,"
            ":start,:end,2,:operation,:end,:terminal_operation,NULL)",
            {**ids, "start": start, "end": end},
            "ck_child_consent_decisions_withdrawal",
        )
    if case in {"policy_non_hex_digest", "policy_oversized_version"}:
        return (
            "INSERT INTO consent_policy_versions "
            "(id,organization_id,purpose_code,version_number,title,content_reference,"
            "content_text,content_sha256,signer_authority_requirement,effective_from,effective_until,"
            "created_operation_id) VALUES "
            "(:row,:organization,'off_site_activity',:version_number,'Policy','object://policy',"
            "'Policy content',:content_sha256,'guardian_record',:start,:end,:operation)",
            {
                **ids,
                "version_number": (2_147_483_648 if case == "policy_oversized_version" else 1),
                "content_sha256": (
                    valid_hash if case == "policy_oversized_version" else non_hex_hash
                ),
                "start": start,
                "end": end,
            },
            (
                "ck_consent_policy_versions_number"
                if case == "policy_oversized_version"
                else "ck_consent_policy_versions_sha256"
            ),
        )
    if case == "person_blank_optional_fact":
        return (
            "INSERT INTO family_authority_person_versions "
            "(id,organization_id,family_id,person_id,version_number,first_name,middle_name,"
            "last_name,relationship_kind,created_operation_id) VALUES "
            "(:row,:organization,:family,:person,1,'Valid','   ','Person','family_friend',"
            ":operation)",
            ids,
            "ck_authority_person_versions_optional_facts",
        )
    if case == "snapshot_non_hex_digest":
        return (
            "INSERT INTO attendance_release_snapshots "
            "(id,organization_id,family_id,facility_id,child_id,attendance_day_id,"
            "attendance_day_version,"
            "attendance_interval_id,checkout_event_id,recipient_person_id,"
            "recipient_person_version_id,recipient_display_name,recipient_relationship,"
            "authorization_id,authorization_version,authority_revision,"
            "restriction_digest_sha256,verification_method,verification_result,"
            "verification_policy_code,"
            "evidence_id,evidence_assessment_id,evidence_assessment_version,"
            "evidence_digest_sha256,decision_policy_version,actor_user_id,"
            "actor_membership_id,actor_role_id,actor_role_key,staff_shift_id,room_id,"
            "scope_basis,room_assignment_id,requested_at,checked_out_at,committed_at,"
            "client_operation_id,request_hash,release_mode,"
            "override_reason_code,override_justification) VALUES "
            "(:row,:organization,:family,:facility,:child,:day,1,:interval,:event,:person,"
            ":person_version,'Recipient Person','parent',:authorization,1,1,"
            ":restriction_hash,'government_photo_id','verified','government_photo_id',"
            ":evidence,:assessment,2,"
            ":evidence_hash,'release-context-v1',"
            ":actor,:membership,:role,'educator',:shift,:room,'organization_role',NULL,"
            ":start,:end,:end,:operation,:request_hash,'normal',NULL,NULL)",
            {
                **ids,
                "restriction_hash": non_hex_hash,
                "evidence_hash": valid_hash,
                "request_hash": valid_hash,
                "start": start,
                "end": end,
            },
            "ck_release_snapshots_hashes",
        )
    raise AssertionError(f"Unknown authority constraint case: {case}")


def _cte_values(source: str, cte_name: str) -> set[tuple[str, ...]]:
    match = re.search(
        rf"\b{re.escape(cte_name)}\s*\([^)]*\)\s+AS\s*\(\s*VALUES"
        rf"(?P<body>.*?)\)\s*,\s*[a-z_][a-z0-9_]*"
        rf"(?:\s*\([^)]*\))?\s+AS\s*\(",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"Missing runtime identity CTE: {cte_name}"
    return {
        tuple(value.lower() for value in row if value)
        for row in re.findall(
            r"\(\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)",
            match.group("body"),
        )
    }


def _bootstrap_table_privileges(source: str) -> dict[str, set[str]]:
    privileges_by_table: dict[str, set[str]] = {}
    for match in re.finditer(
        r"\bGRANT\s+(?P<privileges>[^;]*?)\s+ON\s+TABLE\s+"
        r"(?P<tables>[^;]*?)\s+TO\s+caresync_basic_app\s*;",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        privileges = set(
            re.findall(
                r"\b(?:SELECT|INSERT|UPDATE|DELETE)\b",
                match.group("privileges").upper(),
            )
        )
        for table_name in re.findall(
            r"public\.([a-z_]+)", match.group("tables"), flags=re.IGNORECASE
        ):
            privileges_by_table.setdefault(table_name.lower(), set()).update(privileges)
    return privileges_by_table


def test_clean_upgrade_has_canonical_shape_and_no_model_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "canonical-shape")
    config = _config()
    command.upgrade(config, "head")
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    assert head_revision is not None

    engine = _engine(database_path)
    inspector = inspect(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == head_revision
    assert AUTHORITY_TABLES.issubset(inspector.get_table_names())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert actual_columns == expected_columns, table_name
    engine.dispose()

    # This compares the migrated schema to BasicBase.metadata and catches the
    # model/migration split that invalidated the discarded lower-model draft.
    command.check(config)


def test_receipt_target_expansion_accepts_only_the_architecture_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "receipt-targets")
    config = _config()
    command.upgrade(config, "head")

    engine = _engine(database_path)
    with engine.begin() as connection:
        ids = _seed_actor_and_organization(connection)
        for target_type in sorted(RECEIPT_TARGET_TYPES):
            _insert_receipt(connection, ids, target_type=target_type)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_receipt(connection, ids, target_type="unbounded_future_target")
    with engine.connect() as connection:
        assert (
            set(connection.scalars(text("SELECT target_type FROM childcare_command_receipts")))
            == RECEIPT_TARGET_TYPES
        )
    engine.dispose()


def test_upgrade_does_not_promote_legacy_booleans_or_backfill_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "no-legacy-promotion")
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)
    engine = _engine(database_path)
    guardian_id = uuid4().hex
    child_id = uuid4().hex
    with engine.begin() as connection:
        ids = _seed_actor_and_organization(connection)
        connection.execute(
            text(
                "UPDATE families SET photo_consent=1,field_trip_consent=1,"
                "emergency_medical_consent=1 WHERE id=:family_id"
            ),
            {"family_id": ids["family_a"]},
        )
        connection.execute(
            text(
                "INSERT INTO guardians "
                "(id,organization_id,family_id,first_name,last_name,email,cell_phone,"
                "is_primary,authorized_pickup) VALUES "
                "(:id,:organization_id,:family_id,'Legacy','Guardian','',"
                "'780-555-0100',1,1)"
            ),
            {
                "id": guardian_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Legacy','Child','2023-01-01',1)"
            ),
            {
                "id": child_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
            },
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        for table_name in AUTHORITY_TABLES:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0
        assert connection.execute(
            text(
                "SELECT photo_consent,field_trip_consent,emergency_medical_consent "
                "FROM families WHERE id=:family_id"
            ),
            {"family_id": ids["family_a"]},
        ).one() == (True, True, True)
        assert (
            connection.scalar(
                text("SELECT authorized_pickup FROM guardians WHERE id=:guardian_id"),
                {"guardian_id": guardian_id},
            )
            == 1
        )
    engine.dispose()


def test_empty_0029A_downgrade_preserves_0028_receipts_and_restores_old_target_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "empty-roundtrip")
    config = _config()
    command.upgrade(config, "head")
    engine = _engine(database_path)
    with engine.begin() as connection:
        ids = _seed_actor_and_organization(connection)
        operation_id = _insert_receipt(
            connection,
            ids,
            target_type="family",
            target_id=ids["family_a"],
            command_type="family.update",
        )
    engine.dispose()

    command.downgrade(config, RELEASE_CONTEXT_REVISION)
    command.downgrade(config, ACTIVATION_REVISION)
    command.downgrade(config, VAULT_REVISION)
    command.downgrade(config, KERNEL_REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    engine = _engine(database_path)
    inspector = inspect(engine)
    assert AUTHORITY_TABLES.isdisjoint(inspector.get_table_names())
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM childcare_command_receipts "
                    "WHERE client_operation_id=:operation_id AND target_type='family'"
                ),
                {"operation_id": operation_id},
            )
            == 1
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_receipt(connection, ids, target_type="authority_person")
    engine.dispose()

    command.upgrade(config, "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM childcare_command_receipts "
                    "WHERE client_operation_id=:operation_id"
                ),
                {"operation_id": operation_id},
            )
            == 1
        )
    engine.dispose()
    command.check(config)


def test_new_target_receipt_refuses_downgrade_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "refused-downgrade")
    config = _config()
    command.upgrade(config, "head")
    engine = _engine(database_path)
    with engine.begin() as connection:
        ids = _seed_actor_and_organization(connection)
        _insert_receipt(
            connection,
            ids,
            target_type="authority_evidence",
            command_type="family.authority.evidence.record",
        )
    engine.dispose()
    command.downgrade(config, RELEASE_CONTEXT_REVISION)
    command.downgrade(config, ACTIVATION_REVISION)
    command.downgrade(config, VAULT_REVISION)
    command.downgrade(config, KERNEL_REVISION)
    before = _shape(database_path)

    with pytest.raises(RuntimeError, match=r"0029A.*downgrade refused"):
        command.downgrade(config, PREVIOUS_REVISION)

    assert _shape(database_path) == before


def test_sqlite_multirevision_downgrade_refuses_before_ddl_and_allows_staged_0028(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "staged-sqlite-downgrade")
    config = _config()
    command.upgrade(config, VERIFIED_RELEASE_REVISION)
    before = _shape(database_path)

    with pytest.raises(RuntimeError, match=r"0029C SQLite downgrade refused before DDL"):
        command.downgrade(config, "0027_staff_exchange")

    assert _shape(database_path) == before
    engine = _engine(database_path)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            VERIFIED_RELEASE_REVISION
        )
        assert (
            list(
                connection.scalars(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE '_alembic_tmp_%'"
                    )
                )
            )
            == []
        )
    engine.dispose()

    command.downgrade(config, RELEASE_CONTEXT_REVISION)
    command.downgrade(config, ACTIVATION_REVISION)
    command.downgrade(config, VAULT_REVISION)
    command.downgrade(config, KERNEL_REVISION)
    kernel_shape = _shape(database_path)
    with pytest.raises(
        RuntimeError,
        match=r"0029A SQLite downgrade refused before DDL.*first downgrade exactly to 0028",
    ):
        command.downgrade(config, "0027_staff_exchange")
    assert _shape(database_path) == kernel_shape
    command.downgrade(config, PREVIOUS_REVISION)
    engine = _engine(database_path)
    inspector = inspect(engine)
    assert AUTHORITY_TABLES.isdisjoint(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            PREVIOUS_REVISION
        )
    engine.dispose()


def test_child_scoped_rows_have_same_family_foreign_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "family-foreign-keys")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    inspector = inspect(engine)

    for table_name in (
        "child_authority_heads",
        "child_release_authorizations",
        "child_release_rules",
        "child_consent_decisions",
        "attendance_release_snapshots",
    ):
        _assert_foreign_key(
            inspector,
            table_name,
            ("organization_id", "family_id", "child_id"),
            "children",
            ("organization_id", "family_id", "id"),
        )

    _assert_foreign_key(
        inspector,
        "family_authority_person_versions",
        ("organization_id", "family_id", "person_id"),
        "family_authority_people",
        ("organization_id", "family_id", "id"),
    )
    for table_name, person_column in (
        ("child_release_authorizations", "recipient_person_id"),
        ("child_release_authorizations", "grantor_person_id"),
        ("child_release_rules", "scope_person_id"),
        ("child_release_rules", "directing_person_id"),
        ("child_consent_decisions", "signer_person_id"),
        ("attendance_release_snapshots", "recipient_person_id"),
    ):
        _assert_foreign_key(
            inspector,
            table_name,
            ("organization_id", "family_id", person_column),
            "family_authority_people",
            ("organization_id", "family_id", "id"),
        )
    engine.dispose()


def test_people_sources_and_current_version_are_family_coherent_and_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "person-family-foreign-keys")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    inspector = inspect(engine)

    _assert_foreign_key(
        inspector,
        "family_authority_people",
        ("organization_id", "family_id", "source_guardian_id"),
        "guardians",
        ("organization_id", "family_id", "id"),
    )
    _assert_foreign_key(
        inspector,
        "family_authority_people",
        ("organization_id", "family_id", "source_emergency_contact_id"),
        "emergency_contacts",
        ("organization_id", "family_id", "id"),
    )
    _assert_foreign_key(
        inspector,
        "family_authority_people",
        ("organization_id", "family_id", "id", "current_person_version_id"),
        "family_authority_person_versions",
        ("organization_id", "family_id", "person_id", "id"),
    )
    with engine.connect() as connection:
        people_ddl = connection.scalar(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='family_authority_people'"
            )
        )
    normalized_ddl = " ".join(str(people_ddl).upper().split())
    assert "DEFERRABLE INITIALLY DEFERRED" in normalized_ddl
    engine.dispose()


def test_evidence_assessments_are_immutable_bounded_states_and_windows_are_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "review-and-window-shapes")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    inspector = inspect(engine)

    evidence_columns = {
        column["name"] for column in inspector.get_columns("family_authority_evidence")
    }
    assert evidence_columns.isdisjoint(
        {"review_status", "epistemic_status", "reviewed_by_user_id", "reviewed_at"}
    )
    assessment_columns = {
        column["name"]: column
        for column in inspector.get_columns("family_authority_evidence_assessments")
    }
    assert assessment_columns["actor_user_id"]["nullable"] is False
    assert assessment_columns["assessed_epistemic_status"]["nullable"] is True
    assert assessment_columns["reason_code"]["nullable"] is True
    assessment_checks = _check_text(inspector, "family_authority_evidence_assessments")
    for literal in (
        "reviewed",
        "rejected",
        "invalidated",
        "superseded",
        "insufficient_evidence",
        "information_mismatch",
        "unreadable",
        "unsupported",
        "authority_changed",
        "document_revoked",
        "information_corrected",
        "entered_in_error",
        "other",
    ):
        assert literal in assessment_checks
    assert "version_number = 2" in " ".join(assessment_checks.split())
    assert "version_number = 3" in " ".join(assessment_checks.split())

    _assert_foreign_key(
        inspector,
        "family_authority_evidence_assessments",
        ("organization_id", "family_id", "evidence_id"),
        "family_authority_evidence",
        ("organization_id", "family_id", "id"),
    )
    _assert_foreign_key(
        inspector,
        "family_authority_evidence_assessments",
        ("organization_id", "family_id", "superseded_by_evidence_id"),
        "family_authority_evidence",
        ("organization_id", "family_id", "id"),
    )
    for table_name, evidence_column, assessment_column in (
        (
            "child_release_authorizations",
            "basis_evidence_id",
            "basis_evidence_assessment_id",
        ),
        (
            "child_release_rules",
            "basis_evidence_id",
            "basis_evidence_assessment_id",
        ),
        ("child_consent_decisions", "evidence_id", "evidence_assessment_id"),
    ):
        _assert_foreign_key(
            inspector,
            table_name,
            ("organization_id", "family_id", evidence_column, assessment_column),
            "family_authority_evidence_assessments",
            ("organization_id", "family_id", "evidence_id", "id"),
        )

    for table_name in (
        "child_release_authorizations",
        "child_release_rules",
        "consent_policy_versions",
        "child_consent_decisions",
    ):
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert columns["effective_from"]["nullable"] is False
        assert columns["effective_until"]["nullable"] is False
        window_checks = _check_text(inspector, table_name)
        assert "effective_until" in window_checks
        assert "effective_from" in window_checks
        assert "effective_until > effective_from" in " ".join(window_checks.split())
    engine.dispose()


@pytest.mark.parametrize(
    "case",
    (
        "evidence_missing_byte_size",
        "authorization_null_revocation_reason",
        "rule_null_revocation_reason",
        "consent_null_withdrawal_reason",
        "policy_non_hex_digest",
        "evidence_non_hex_digest",
        "evidence_public_storage_reference",
        "evidence_trailing_storage_segment",
        "evidence_invalid_media_type",
        "evidence_oversized_byte_size",
        "assessment_reviewed_with_reason",
        "assessment_rejected_without_reason",
        "assessment_other_without_note",
        "assessment_self_supersession",
        "person_blank_optional_fact",
        "policy_oversized_version",
        "snapshot_non_hex_digest",
    ),
)
def test_sqlite_checks_reject_partial_terminal_tuples_and_non_hex_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Prove CHECK behavior without letting unrelated foreign keys mask a hole."""

    database_path = _database(tmp_path, monkeypatch, f"sqlite-check-{case}")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    statement, parameters, constraint_name = _authority_check_case(case)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        assert connection.scalar(text("PRAGMA foreign_keys")) == 0
        if case == "snapshot_non_hex_digest":
            # This case isolates the original 0029A hash CHECK.  The later C
            # relational trigger is independently covered by its own exact
            # happy/rejection matrix and would otherwise reject the synthetic
            # row before SQLite evaluates the hash constraint.
            connection.exec_driver_sql("DROP TRIGGER attendance_release_snapshots_insert_guard")
        with pytest.raises(IntegrityError) as error:
            connection.execute(text(statement), parameters)
        connection.rollback()
    assert constraint_name in str(error.value.orig)
    engine.dispose()


def test_sqlite_evidence_storage_grammar_accepts_a_valid_private_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "valid-evidence-storage")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        connection.execute(
            text(
                "INSERT INTO family_authority_evidence "
                "(id,organization_id,family_id,evidence_kind,source_label,"
                "storage_reference,media_type,byte_size,content_sha256,"
                "recorded_by_user_id,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,'custody_document',"
                "'Valid private object','authority/family/document-1',"
                "'application/pdf',1024,:digest,:actor_id,:operation_id)"
            ),
            {
                "id": uuid4().hex,
                "organization_id": uuid4().hex,
                "family_id": uuid4().hex,
                "digest": "a" * 64,
                "actor_id": uuid4().hex,
                "operation_id": uuid4().hex,
            },
        )
        connection.commit()
        assert connection.scalar(text("SELECT count(*) FROM family_authority_evidence")) == 1
    engine.dispose()


def test_release_snapshot_echoes_exact_attendance_identity_and_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "snapshot-identity")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    inspector = inspect(engine)

    _assert_foreign_key(
        inspector,
        "attendance_release_snapshots",
        ("organization_id", "facility_id", "child_id", "attendance_day_id"),
        "attendance_days",
        ("organization_id", "facility_id", "child_id", "id"),
    )
    _assert_foreign_key(
        inspector,
        "attendance_release_snapshots",
        ("organization_id", "attendance_day_id", "attendance_interval_id"),
        "attendance_intervals",
        ("organization_id", "attendance_day_id", "id"),
    )
    _assert_foreign_key(
        inspector,
        "attendance_release_snapshots",
        ("organization_id", "attendance_day_id", "checkout_event_id"),
        "attendance_events",
        ("organization_id", "attendance_day_id", "id"),
    )
    unique_signatures = _unique_signatures(inspector, "attendance_release_snapshots")
    assert ("organization_id", "attendance_interval_id") in unique_signatures
    assert ("organization_id", "checkout_event_id") in unique_signatures
    assert ("organization_id", "client_operation_id") in unique_signatures
    engine.dispose()


def test_operation_provenance_columns_reference_exact_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "operation-provenance")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    inspector = inspect(engine)

    expected_operation_columns = {
        "family_authority_people": (
            "created_operation_id",
            "last_operation_id",
            "retired_operation_id",
        ),
        "family_authority_person_versions": (
            "created_operation_id",
            "closed_operation_id",
        ),
        "family_authority_evidence": ("created_operation_id",),
        "family_authority_evidence_assessments": ("created_operation_id",),
        "child_authority_heads": ("created_operation_id", "last_operation_id"),
        "child_release_authorizations": ("created_operation_id", "revoked_operation_id"),
        "child_release_rules": ("created_operation_id", "revoked_operation_id"),
        "consent_policy_versions": ("created_operation_id",),
        "child_consent_decisions": ("created_operation_id", "withdrawn_operation_id"),
        "attendance_release_snapshots": ("client_operation_id",),
    }
    for table_name, operation_columns in expected_operation_columns.items():
        for operation_column in operation_columns:
            _assert_foreign_key(
                inspector,
                table_name,
                ("organization_id", operation_column),
                "childcare_command_receipts",
                ("organization_id", "client_operation_id"),
            )
    engine.dispose()


def test_cross_family_child_head_is_rejected_by_sqlite_foreign_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = _database(tmp_path, monkeypatch, "cross-family")
    command.upgrade(_config(), "head")
    engine = _engine(database_path)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        ids = _seed_actor_and_organization(connection)
        child_id = uuid4().hex
        connection.execute(
            text(
                "INSERT INTO children "
                "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
                "VALUES (:id,:organization_id,:family_id,'Family','Bound','2023-01-01',1)"
            ),
            {
                "id": child_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
            },
        )
        release_rule_id = uuid4().hex
        operation_id = _insert_receipt(
            connection,
            ids,
            target_type="release_rule",
            target_id=release_rule_id,
            command_type="child.release.rule.create",
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                "INSERT INTO child_authority_heads "
                "(organization_id,family_id,child_id,revision,created_operation_id,"
                "last_operation_id) VALUES "
                "(:organization_id,:wrong_family_id,:child_id,1,:operation_id,:operation_id)"
            ),
            {
                "organization_id": ids["organization"],
                "wrong_family_id": ids["family_b"],
                "child_id": child_id,
                "operation_id": operation_id,
            },
        )
    engine.dispose()


def test_migration_declares_database_command_and_history_guards() -> None:
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0029A_family_authority_kernel.py"
    source = migration_path.read_text(encoding="utf-8")

    # Exact-command provenance must be checked in the database, not just in a
    # service function that direct SQL can bypass.
    for fragment in (
        "app.current_organization_id",
        "app.current_user_id",
        "app.current_childcare_operation_id",
        "pg_current_xact_id()",
        "transaction_timestamp()",
        "statement_timestamp()",
        "caresync_basic_app",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "REVOKE ALL ON FUNCTION",
    ):
        assert fragment in source

    # The kernel has append-only facts and tightly bounded one-way terminal
    # transitions; a generic tenant-only RLS policy is not sufficient.
    for table_name in AUTHORITY_TABLES:
        assert table_name in source
    for field_name in (
        "closed_operation_id",
        "retired_operation_id",
        "revoked_operation_id",
        "withdrawn_operation_id",
        "last_operation_id",
    ):
        assert field_name in source
    assert "receipt_row.xmin" in source
    assert "command_receipt.command_type" in source
    assert "command_receipt.target_type" in source
    assert "command_receipt.target_id" in source
    for fragment in (
        "^[0-9a-f]{64}$",
        "isfinite",
        "release_authorization.version = NEW.authorization_version",
        "head.revision=NEW.authority_revision",
        "person.current_person_version_id=NEW.recipient_person_version_id",
        "command_receipt.request_hash <> NEW.request_hash",
        "command_receipt.actor_user_id <> NEW.actor_user_id",
        "NEW.revision <> OLD.revision + 1",
        "scope_person_id IS NOT DISTINCT FROM NEW.scope_person_id",
        "pg_advisory_xact_lock",
    ):
        assert fragment in source
    assert "GRANT DELETE" not in source
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" not in source
    assert ":consent-policy" not in source


def test_runtime_bootstrap_and_startup_identity_cover_the_0029A_authority_surface() -> None:
    """Keep migration grants, terminal bootstrap, and API startup in one contract."""

    session_source = (BACKEND_ROOT / "app" / "db" / "session.py").read_text(encoding="utf-8")
    bootstrap_source = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text(
        encoding="utf-8"
    )

    insert_rows = _cte_values(session_source, "authority_insert_tables")
    select_only_rows = _cte_values(session_source, "authority_select_only_tables")
    update_rows = _cte_values(session_source, "authority_update_columns")
    authority_table_names = AUTHORITY_TABLES | VAULT_INSERT_TABLES
    authority_scope_rows = {(table_name,) for table_name in authority_table_names}
    assert insert_rows & authority_scope_rows == {
        (table_name,) for table_name in AUTHORITY_INSERT_TABLES | VAULT_INSERT_TABLES
    }
    # The static CTE parser also sees the A1-only scaffold branch and any
    # later, unrelated registry VALUES blocks in this shared runtime CTE. Keep
    # this assertion scoped to the complete family-authority/vault table set so
    # future additive domains cannot weaken or accidentally break the 0029A
    # privilege contract being tested here.
    activation_rows = {(table_name,) for table_name in ACTIVATION_TABLES}
    authority_select_only_rows = select_only_rows & authority_scope_rows
    assert authority_select_only_rows - activation_rows == {
        (table_name,) for table_name in AUTHORITY_SELECT_ONLY_TABLES
    }
    assert activation_rows <= authority_select_only_rows
    assert "WHERE NOT enabled.enabled" in session_source
    authority_update_rows = {row for row in update_rows if row[0] in authority_table_names}
    assert authority_update_rows == {
        (table_name, column_name)
        for table_name, columns in AUTHORITY_UPDATE_COLUMNS.items()
        for column_name in columns
    }
    assert "SELECT 'family_authority_evidence_objects', 'status'" in session_source
    for cte_name in (
        "authority_insert_tables",
        "authority_select_only_tables",
        "authority_update_columns",
    ):
        # Definition plus dangerous-grant and missing-grant audits.
        assert session_source.count(cte_name) >= 3
    deletable_rows = _cte_values(session_source, "deletable_tables")
    assert not ({row[0] for row in deletable_rows} & AUTHORITY_TABLES)

    expected_guard_rows = _cte_values(session_source, "expected_guard_functions")
    for function_name in AUTHORITY_GUARD_FUNCTIONS:
        assert (f"public.{function_name}()",) in expected_guard_rows
    for function_name in VAULT_GUARD_FUNCTIONS:
        assert (f"public.{function_name}()",) in expected_guard_rows

    bootstrap_privileges = _bootstrap_table_privileges(bootstrap_source)
    for table_name in AUTHORITY_TABLES:
        expected = {"SELECT"}
        if table_name in AUTHORITY_INSERT_TABLES:
            expected.add("INSERT")
        if table_name in AUTHORITY_UPDATE_COLUMNS:
            expected.add("UPDATE")
        assert bootstrap_privileges.get(table_name) == expected
        assert "DELETE" not in bootstrap_privileges.get(table_name, set())
    assert bootstrap_privileges["attendance_release_snapshots"] == {"SELECT"}
    assert bootstrap_privileges["family_authority_evidence_objects"] == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }
    assert bootstrap_privileges["family_authority_evidence_object_assessments"] == {
        "SELECT",
        "INSERT",
    }

    for function_name in AUTHORITY_GUARD_FUNCTIONS:
        assert session_source.count(function_name) >= 1
        assert bootstrap_source.count(function_name) >= 4
        assert re.search(
            rf"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+FUNCTION\s+"
            rf"public\.{re.escape(function_name)}\(\)\s+FROM\s+PUBLIC\s*,\s*"
            r"caresync_basic_app\s*;",
            bootstrap_source,
            flags=re.IGNORECASE | re.DOTALL,
        )
    for function_name in VAULT_GUARD_FUNCTIONS:
        assert session_source.count(function_name) >= 1
        assert bootstrap_source.count(function_name) >= 4
        assert re.search(
            rf"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+FUNCTION\s+"
            rf"public\.{re.escape(function_name)}\(\)\s+FROM\s+PUBLIC\s*,\s*"
            r"caresync_basic_app\s*;",
            bootstrap_source,
            flags=re.IGNORECASE | re.DOTALL,
        )
