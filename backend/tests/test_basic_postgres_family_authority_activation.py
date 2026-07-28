"""Opt-in PostgreSQL catalog and privilege proofs for 0029A2 activation."""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import Settings
from app.db.session import Database
from tests.test_basic_postgres_family_authority_kernel import (
    BACKEND_ROOT,
    _insert_receipt,
    _seed_actor,
    _seed_base,
    _set_context,
)

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
RUNTIME_ROLE = "caresync_basic_app"
CURRENT_REVISION = "0029A2_authority_activation"

ACTIVATION_TABLES = {
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
}
EXPECTED_UPDATE_COLUMNS = {
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
    "consent_policy_versions": set(),
    "child_consent_decisions": {
        "version",
        "withdrawn_at",
        "withdrawn_operation_id",
        "withdrawal_reason_code",
        "updated_at",
    },
}

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=TEST_HOST,
        database_port=int(TEST_PORT or "0"),
        database_user=RUNTIME_ROLE,
        database_password="",
        database_name=TEST_DATABASE,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-a2-activation-test-secret-32-bytes",
    )


def test_postgres_activation_shape_guards_and_runtime_readiness() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
            assert set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname IN "
                        "('child_release_authorizations','child_release_rules',"
                        "'consent_policy_versions','child_consent_decisions') "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    )
                ).scalars()
            ) == ACTIVATION_TABLES
            triggers = set(
                connection.execute(
                    text(
                        "SELECT relation.relname,trigger.tgname,procedure.proname "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=trigger.tgfoid "
                        "WHERE relation.relname IN "
                        "('child_release_authorizations','child_release_rules',"
                        "'consent_policy_versions','child_consent_decisions') "
                        "AND NOT trigger.tgisinternal AND trigger.tgenabled<>'D'"
                    )
                )
            )
            assert {
                (
                    table_name,
                    f"trg_{table_name}_activation_guard",
                    "caresync_family_authority_activation_guard",
                )
                for table_name in ACTIVATION_TABLES
            } <= triggers
            function = connection.execute(
                text(
                    "SELECT procedure.prosecdef,procedure.proconfig "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_family_authority_activation_guard()')"
                )
            ).one()
            assert function[0] is True
            assert {str(value).replace(" ", "") for value in function[1]} == {
                "search_path=pg_catalog,public"
            }
            definitions = " ".join(
                connection.execute(
                    text(
                        "SELECT pg_catalog.pg_get_constraintdef(constraint_record.oid) "
                        "FROM pg_catalog.pg_constraint AS constraint_record "
                        "WHERE constraint_record.conname IN "
                        "('ck_authority_evidence_objects_kind',"
                        "'ck_authority_evidence_kind',"
                        "'ck_child_consent_decisions_distinct_evidence')"
                    )
                ).scalars()
            )
            assert "signed_release_delegation" in definitions
            assert "evidence_id <> signer_authority_evidence_id" in definitions
    finally:
        admin.dispose()

    database = Database(_settings())
    try:
        database.assert_basic_runtime_identity()
        assert database.has_family_authority_kernel() is True
        assert database.has_family_evidence_vault() is True
        assert database.has_family_authority_activation() is True
    finally:
        database.dispose()


def test_postgres_activation_grants_are_exact_and_snapshot_remains_read_only() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            for table_name in ACTIVATION_TABLES:
                relation = f"public.{table_name}"
                assert connection.scalar(
                    text("SELECT pg_catalog.has_table_privilege(:role,:table,'SELECT')"),
                    {"role": RUNTIME_ROLE, "table": relation},
                )
                assert connection.scalar(
                    text("SELECT pg_catalog.has_table_privilege(:role,:table,'INSERT')"),
                    {"role": RUNTIME_ROLE, "table": relation},
                )
                assert not connection.scalar(
                    text(
                        "SELECT pg_catalog.has_table_privilege("
                        ":role,:table,'UPDATE,DELETE')"
                    ),
                    {"role": RUNTIME_ROLE, "table": relation},
                )
                update_columns = set(
                    connection.execute(
                        text(
                            "SELECT attribute.attname "
                            "FROM pg_catalog.pg_attribute AS attribute "
                            "WHERE attribute.attrelid=pg_catalog.to_regclass(:table) "
                            "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                            "AND pg_catalog.has_column_privilege("
                            ":role,attribute.attrelid,attribute.attnum,'UPDATE')"
                        ),
                        {"role": RUNTIME_ROLE, "table": relation},
                    ).scalars()
                )
                assert update_columns == EXPECTED_UPDATE_COLUMNS[table_name]

            assert connection.scalar(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    ":role,'public.attendance_release_snapshots','SELECT')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert not connection.scalar(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    ":role,'public.attendance_release_snapshots',"
                    "'INSERT,UPDATE,DELETE')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert not connection.scalar(
                text(
                    "SELECT pg_catalog.has_function_privilege("
                    ":role,'public.caresync_family_authority_activation_guard()',"
                    "'EXECUTE')"
                ),
                {"role": RUNTIME_ROLE},
            )
    finally:
        admin.dispose()


def _seed_release_activation_fixture(connection) -> tuple[dict, dict[str, tuple]]:
    ids = _seed_base(connection)
    reviewer_id = _seed_actor(connection, ids, "manager")
    guardian_id = uuid4()
    person_id = uuid4()
    person_version_id = uuid4()
    person_operation_id = uuid4()
    connection.execute(text("SET session_replication_role='replica'"))
    try:
        _insert_receipt(
            connection,
            ids,
            operation_id=person_operation_id,
            target_type="authority_person",
            target_id=person_id,
            command_type="family.authority.person.create",
        )
        connection.execute(
            text(
                "INSERT INTO guardians "
                "(id,organization_id,family_id,first_name,last_name,email,cell_phone,"
                "is_primary,authorized_pickup) VALUES "
                "(:id,:organization_id,:family_id,'Live','Guardian','',"
                "'780-555-0199',true,true)"
            ),
            {
                "id": guardian_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO family_authority_people "
                "(id,organization_id,family_id,version,status,current_person_version_id,"
                "source_guardian_id,created_operation_id,last_operation_id) VALUES "
                "(:id,:organization_id,:family_id,1,'active',:version_id,"
                ":guardian_id,:operation_id,:operation_id)"
            ),
            {
                "id": person_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
                "version_id": person_version_id,
                "guardian_id": guardian_id,
                "operation_id": person_operation_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO family_authority_person_versions "
                "(id,organization_id,family_id,person_id,version_number,first_name,"
                "last_name,relationship_kind,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:person_id,1,'Live','Guardian',"
                "'parent',:operation_id)"
            ),
            {
                "id": person_version_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
                "person_id": person_id,
                "operation_id": person_operation_id,
            },
        )

        evidence: dict[str, tuple] = {}
        for label, evidence_kind, assessment_actor, epistemic_status in (
            ("valid", "guardian_attestation", reviewer_id, "reported"),
            ("wrong_kind", "custody_document", reviewer_id, "document_observed"),
            ("same_actor", "guardian_attestation", ids["user"], "reported"),
        ):
            evidence_id = uuid4()
            assessment_id = uuid4()
            record_operation_id = uuid4()
            review_operation_id = uuid4()
            _insert_receipt(
                connection,
                ids,
                operation_id=record_operation_id,
                target_type="authority_evidence",
                target_id=evidence_id,
                command_type="family.authority.evidence.record",
            )
            _insert_receipt(
                connection,
                ids,
                operation_id=review_operation_id,
                target_type="authority_evidence",
                target_id=evidence_id,
                command_type="family.authority.evidence.review",
                committed_version=2,
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_evidence "
                    "(id,organization_id,family_id,evidence_kind,source_label,expires_at,"
                    "recorded_by_user_id,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,:kind,:label,"
                    "TIMESTAMPTZ '2099-01-01 00:00:00+00',:actor,:operation_id)"
                ),
                {
                    "id": evidence_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "kind": evidence_kind,
                    "label": f"A2 PostgreSQL {label}",
                    "actor": ids["user"],
                    "operation_id": record_operation_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_evidence_assessments "
                    "(id,organization_id,family_id,evidence_id,version_number,decision,"
                    "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed',"
                    ":epistemic_status,:actor,:operation_id)"
                ),
                {
                    "id": assessment_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "evidence_id": evidence_id,
                    "epistemic_status": epistemic_status,
                    "actor": assessment_actor,
                    "operation_id": review_operation_id,
                },
            )
            evidence[label] = (evidence_id, assessment_id)
    finally:
        connection.execute(text("SET session_replication_role='origin'"))
    ids.update(
        {
            "guardian": guardian_id,
            "person": person_id,
            "person_version": person_version_id,
        }
    )
    return ids, evidence


def _insert_release_authorization(connection, ids, evidence: tuple) -> str:
    authorization_id = uuid4()
    operation_id = uuid4()
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=operation_id,
    )
    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    _insert_receipt(
        connection,
        ids,
        operation_id=operation_id,
        target_type="release_authorization",
        target_id=authorization_id,
        command_type="child.release.authorization.grant",
    )
    connection.execute(
        text(
            "INSERT INTO child_release_authorizations "
            "(id,organization_id,family_id,child_id,recipient_person_id,"
            "verification_policy_code,grantor_person_id,grantor_person_version_id,"
            "grantor_authority_basis,basis_evidence_id,basis_evidence_assessment_id,"
            "effective_from,effective_until,version,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:child_id,:person_id,"
            "'government_photo_id',:person_id,:person_version_id,'guardian_record',"
            ":evidence_id,:assessment_id,TIMESTAMPTZ '2030-01-01 08:00:00+00',"
            "TIMESTAMPTZ '2031-01-01 08:00:00+00',1,:operation_id)"
        ),
        {
            "id": authorization_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "child_id": ids["child"],
            "person_id": ids["person"],
            "person_version_id": ids["person_version"],
            "evidence_id": evidence[0],
            "assessment_id": evidence[1],
            "operation_id": operation_id,
        },
    )
    return authorization_id


def _insert_consent_policy(connection, ids, *, content_sha256: str) -> str:
    policy_id = uuid4()
    operation_id = uuid4()
    content_text = "Immutable A2 PostgreSQL consent policy."
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=operation_id,
    )
    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    _insert_receipt(
        connection,
        ids,
        operation_id=operation_id,
        target_type="consent",
        target_id=policy_id,
        command_type="organization.consent.policy.publish",
    )
    connection.execute(
        text(
            "INSERT INTO consent_policy_versions "
            "(id,organization_id,purpose_code,version_number,title,content_text,"
            "content_reference,content_sha256,signer_authority_requirement,"
            "effective_from,effective_until,created_operation_id) VALUES "
            "(:id,:organization_id,'off_site_activity',1,'A2 policy',:content_text,"
            ":content_reference,:content_sha256,'guardian_record',"
            "TIMESTAMPTZ '2030-01-01 08:00:00+00',"
            "TIMESTAMPTZ '2031-01-01 08:00:00+00',:operation_id)"
        ),
        {
            "id": policy_id,
            "organization_id": ids["organization"],
            "content_text": content_text,
            "content_reference": f"/consent-policies/{policy_id}",
            "content_sha256": content_sha256,
            "operation_id": operation_id,
        },
    )
    return policy_id


def test_postgres_activation_guard_accepts_valid_and_rejects_semantic_bypasses() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.begin() as connection:
            connection.execute(
                text("ALTER TABLE child_release_authorizations DISABLE TRIGGER USER")
            )
            connection.execute(
                text(
                    "ALTER TABLE child_release_authorizations ENABLE TRIGGER "
                    "trg_child_release_authorizations_activation_guard"
                )
            )
            ids, evidence = _seed_release_activation_fixture(connection)

        with admin.begin() as connection:
            authorization_id = _insert_release_authorization(
                connection, ids, evidence["valid"]
            )
        with admin.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM child_release_authorizations WHERE id=:id"),
                {"id": authorization_id},
            ) == 1

        with pytest.raises(DBAPIError) as wrong_kind, admin.begin() as connection:
            _insert_release_authorization(connection, ids, evidence["wrong_kind"])
        assert wrong_kind.value.orig.diag.constraint_name == (
            "ck_release_authorization_guardian_provenance"
        )

        with pytest.raises(DBAPIError) as same_actor, admin.begin() as connection:
            _insert_release_authorization(connection, ids, evidence["same_actor"])
        assert same_actor.value.orig.diag.constraint_name == (
            "ck_family_authority_activation_maker_checker"
        )

        with pytest.raises(DBAPIError) as mismatched_policy, admin.begin() as connection:
            _insert_consent_policy(connection, ids, content_sha256="0" * 64)
        assert mismatched_policy.value.orig.diag.constraint_name == (
            "ck_consent_policy_content_projection"
        )

        content_text = "Immutable A2 PostgreSQL consent policy."
        with admin.begin() as connection:
            policy_id = _insert_consent_policy(
                connection,
                ids,
                content_sha256=hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
            )
        with admin.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM consent_policy_versions WHERE id=:id"),
                {"id": policy_id},
            ) == 1

        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url", _url("postgres").render_as_string(hide_password=False)
        )
        with pytest.raises(RuntimeError, match="0029A2 downgrade refused before DDL"):
            command.downgrade(config, "0029A1_family_evidence_vault")
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_attribute "
                    "WHERE attrelid='public.child_consent_decisions'::regclass "
                    "AND attname='signer_authority_evidence_id' "
                    "AND attnum>0 AND NOT attisdropped"
                )
            ) == 1
    finally:
        with admin.begin() as connection:
            connection.execute(
                text("ALTER TABLE child_release_authorizations ENABLE TRIGGER USER")
            )
        admin.dispose()
