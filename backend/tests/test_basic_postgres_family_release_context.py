"""Opt-in real PostgreSQL proofs for the 0029B projection boundary."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.basic.family_release_context_schemas import ReleaseContextInput
from app.core.config import Settings
from app.db.session import Database
from tests.test_basic_postgres_family_authority_kernel import (
    BACKEND_ROOT,
    _seed_base,
    _set_context,
)

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
RUNTIME_ROLE = "caresync_basic_app"
CURRENT_REVISION = "0029B_release_context"
PROJECTION = "public.caresync_family_release_context_inputs(uuid,uuid)"
EVENT_FUNCTION = "public.caresync_release_context_from_authority_head()"
ACTIVATION_UPDATE_COLUMNS = {
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
    assert 1 <= port <= 65535
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _public_execute_exists(connection, signature: str) -> bool:
    return bool(
        connection.scalar(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_catalog.pg_proc AS procedure, "
                "LATERAL pg_catalog.aclexplode(COALESCE("
                "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) AS acl "
                "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature) "
                "AND acl.grantee=0 AND acl.privilege_type='EXECUTE')"
            ),
            {"signature": signature},
        )
    )


def _database() -> Database:
    return Database(
        Settings(
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
            jwt_secret="postgres-b-release-context-test-secret-32-bytes",
        )
    )


def test_release_context_catalog_boundary_is_exact() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
            for signature in (PROJECTION, EVENT_FUNCTION):
                function = connection.execute(
                    text(
                        "SELECT procedure.prosecdef,procedure.proconfig,"
                        "pg_catalog.pg_get_userbyid(procedure.proowner),"
                        "pg_catalog.pg_get_function_result(procedure.oid) "
                        "FROM pg_catalog.pg_proc AS procedure "
                        "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature)"
                    ),
                    {"signature": signature},
                ).one()
                assert function.prosecdef is True
                assert {str(value).replace(" ", "") for value in function.proconfig} == {
                    "search_path=pg_catalog,public"
                }
                assert function.pg_get_userbyid != RUNTIME_ROLE
                assert not _public_execute_exists(connection, signature)
            assert function.pg_get_function_result == "trigger"
            assert connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_function_result("
                    "pg_catalog.to_regprocedure(:signature))"
                ),
                {"signature": PROJECTION},
            ) == "jsonb"
            assert connection.scalar(
                text(
                    "SELECT pg_catalog.has_function_privilege("
                    ":role,:signature,'EXECUTE')"
                ),
                {"role": RUNTIME_ROLE, "signature": PROJECTION},
            )
            assert not connection.scalar(
                text(
                    "SELECT pg_catalog.has_function_privilege("
                    ":role,:signature,'EXECUTE')"
                ),
                {"role": RUNTIME_ROLE, "signature": EVENT_FUNCTION},
            )

            trigger = connection.execute(
                text(
                    "SELECT trigger.tgname,pg_catalog.pg_get_triggerdef(trigger.oid),"
                    "procedure.proname "
                    "FROM pg_catalog.pg_trigger AS trigger "
                    "JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid "
                    "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                    "WHERE relation.oid='public.child_authority_heads'::regclass "
                    "AND trigger.tgname='child_authority_heads_release_context_invalidated' "
                    "AND NOT trigger.tgisinternal"
                )
            ).one()
            normalized_trigger = " ".join(trigger.pg_get_triggerdef.lower().split())
            assert "after insert or update of revision" in normalized_trigger
            assert trigger.proname == "caresync_release_context_from_authority_head"

            forced_rls = set(
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
            )
            assert forced_rls == {
                "child_release_authorizations",
                "child_release_rules",
                "consent_policy_versions",
                "child_consent_decisions",
            }
            assert connection.scalar(
                text(
                    "SELECT character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "AND table_name='child_release_authorizations' "
                    "AND column_name='verification_policy_code'"
                )
            ) == 64
            for table_name, expected_update_columns in ACTIVATION_UPDATE_COLUMNS.items():
                relation = f"public.{table_name}"
                assert connection.scalar(
                    text("SELECT pg_catalog.has_table_privilege(:r,:t,'SELECT,INSERT')"),
                    {"r": RUNTIME_ROLE, "t": relation},
                )
                assert not connection.scalar(
                    text("SELECT pg_catalog.has_table_privilege(:r,:t,'UPDATE,DELETE')"),
                    {"r": RUNTIME_ROLE, "t": relation},
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
                assert update_columns == expected_update_columns
    finally:
        admin.dispose()


def test_release_context_detector_accepts_complete_and_rejects_missing_execute() -> None:
    admin = create_engine(_url("postgres"))
    database = _database()
    try:
        assert database.has_family_authority_release_context() is True
        with admin.begin() as connection:
            connection.execute(
                text(
                    "REVOKE EXECUTE ON FUNCTION "
                    "public.caresync_family_release_context_inputs(uuid,uuid) "
                    "FROM caresync_basic_app"
                )
            )
        assert database.has_family_authority_release_context() is False
    finally:
        with admin.begin() as connection:
            connection.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION "
                    "public.caresync_family_release_context_inputs(uuid,uuid) "
                    "TO caresync_basic_app"
                )
            )
        database.dispose()
        admin.dispose()

    database = _database()
    try:
        assert database.has_family_authority_release_context() is True
    finally:
        database.dispose()


def _seed_operational_gate(connection) -> dict[str, object]:
    ids = _seed_base(connection)
    facility_id = uuid4()
    program_id = uuid4()
    room_id = uuid4()
    enrollment_id = uuid4()
    shift_id = uuid4()
    attendance_day_id = uuid4()
    attendance_interval_id = uuid4()
    assignment_id = uuid4()
    operation_id = uuid4()
    person_id = uuid4()
    person_version_id = uuid4()
    evidence_id = uuid4()
    evidence_assessment_id = uuid4()
    authorization_id = uuid4()
    membership_id = connection.scalar(
        text(
            "SELECT id FROM organization_memberships "
            "WHERE organization_id=:organization_id AND user_id=:user_id"
        ),
        {"organization_id": ids["organization"], "user_id": ids["user"]},
    )
    role_id = connection.scalar(
        text("SELECT role_id FROM organization_memberships WHERE id=:membership_id"),
        {"membership_id": membership_id},
    )
    connection.execute(
        text(
            "UPDATE roles SET key='educator',permissions='[\"release:read\"]'::json "
            "WHERE id=:role_id"
        ),
        {"role_id": role_id},
    )
    connection.execute(
        text(
            "INSERT INTO facilities "
            "(id,organization_id,name,status,verification_status,province,timezone,"
            "licensed_capacity) "
            "VALUES (:id,:organization_id,'Release gate','active','pending',"
            "'Alberta','America/Edmonton',20)"
        ),
        {"id": facility_id, "organization_id": ids["organization"]},
    )
    connection.execute(
        text(
            "INSERT INTO facility_programs "
            "(id,organization_id,facility_id,name,program_type,capacity,is_active) "
            "VALUES (:id,:organization_id,:facility_id,'Daycare','daycare',20,true)"
        ),
        {
            "id": program_id,
            "organization_id": ids["organization"],
            "facility_id": facility_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO rooms "
            "(id,organization_id,facility_id,program_id,name,capacity,is_active) "
            "VALUES (:id,:organization_id,:facility_id,:program_id,'Infant',20,true)"
        ),
        {
            "id": room_id,
            "organization_id": ids["organization"],
            "facility_id": facility_id,
            "program_id": program_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO enrollments "
            "(id,organization_id,facility_id,child_id,program_id,room_id,"
            "placement_effective_date,start_date,status,version) "
            "VALUES (:id,:organization_id,:facility_id,:child_id,:program_id,:room_id,"
            "CURRENT_DATE,CURRENT_DATE,'active',1)"
        ),
        {
            "id": enrollment_id,
            "organization_id": ids["organization"],
            "facility_id": facility_id,
            "child_id": ids["child"],
            "program_id": program_id,
            "room_id": room_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO staff_shifts "
            "(id,organization_id,membership_id,facility_id,status,clocked_in_at) "
            "VALUES (:id,:organization_id,:membership_id,:facility_id,'open',"
            "statement_timestamp())"
        ),
        {
            "id": shift_id,
            "organization_id": ids["organization"],
            "membership_id": membership_id,
            "facility_id": facility_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO membership_room_assignments "
            "(id,organization_id,membership_id,facility_id,room_id,is_active,"
            "created_by_user_id) VALUES "
            "(:id,:organization_id,:membership_id,:facility_id,:room_id,true,:user_id)"
        ),
        {
            "id": assignment_id,
            "organization_id": ids["organization"],
            "membership_id": membership_id,
            "facility_id": facility_id,
            "room_id": room_id,
            "user_id": ids["user"],
        },
    )
    connection.execute(
        text(
            "INSERT INTO attendance_days "
            "(id,organization_id,facility_id,child_id,enrollment_id,room_id,"
            "service_date,status,version) VALUES "
            "(:id,:organization_id,:facility_id,:child_id,:enrollment_id,:room_id,"
            "CURRENT_DATE,'present',1)"
        ),
        {
            "id": attendance_day_id,
            "organization_id": ids["organization"],
            "facility_id": facility_id,
            "child_id": ids["child"],
            "enrollment_id": enrollment_id,
            "room_id": room_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO attendance_intervals "
            "(id,organization_id,attendance_day_id,sequence,checked_in_at) "
            "VALUES (:id,:organization_id,:attendance_day_id,1,statement_timestamp())"
        ),
        {
            "id": attendance_interval_id,
            "organization_id": ids["organization"],
            "attendance_day_id": attendance_day_id,
        },
    )

    # Seed a head while all triggers and deferred references are disabled.  It
    # exists only to prove that the educator cannot directly read the A2 row;
    # the B function may project only its revision.
    connection.execute(text("SET session_replication_role='replica'"))
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,committed_version,outcome) VALUES "
            "(:id,:organization_id,:operation_id,'child.release.authorization.grant',"
            "'release_authorization',:target_id,:request_hash,:actor_user_id,1,'{}'::json)"
        ),
        {
            "id": uuid4(),
            "organization_id": ids["organization"],
            "operation_id": operation_id,
            "target_id": uuid4(),
            "request_hash": uuid4().hex * 2,
            "actor_user_id": ids["user"],
        },
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_people "
            "(id,organization_id,family_id,version,status,current_person_version_id,"
            "created_operation_id,last_operation_id) VALUES "
            "(:id,:organization_id,:family_id,1,'active',:version_id,"
            ":operation_id,:operation_id)"
        ),
        {
            "id": person_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "version_id": person_version_id,
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_person_versions "
            "(id,organization_id,family_id,person_id,version_number,first_name,"
            "last_name,preferred_name,relationship_kind,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:person_id,1,'Safe','Recipient','Sam',"
            "'grandparent',:operation_id)"
        ),
        {
            "id": person_version_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "person_id": person_id,
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_evidence "
            "(id,organization_id,family_id,evidence_kind,source_label,expires_at,"
            "recorded_by_user_id,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,'guardian_attestation','Release proof',"
            "statement_timestamp()+INTERVAL '2 days',:actor_user_id,:operation_id)"
        ),
        {
            "id": evidence_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "actor_user_id": ids["user"],
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_evidence_assessments "
            "(id,organization_id,family_id,evidence_id,version_number,decision,"
            "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed','reported',"
            ":actor_user_id,:operation_id)"
        ),
        {
            "id": evidence_assessment_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "evidence_id": evidence_id,
            "actor_user_id": ids["user"],
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO child_release_authorizations "
            "(id,organization_id,family_id,child_id,recipient_person_id,"
            "verification_policy_code,grantor_person_id,grantor_person_version_id,"
            "grantor_authority_basis,basis_evidence_id,basis_evidence_assessment_id,"
            "effective_from,effective_until,version,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:child_id,:person_id,"
            "'government_photo_id_or_documented_familiarity',:person_id,"
            ":person_version_id,'guardian_record',:evidence_id,:assessment_id,"
            "statement_timestamp()-INTERVAL '1 hour',"
            "statement_timestamp()+INTERVAL '1 day',1,:operation_id)"
        ),
        {
            "id": authorization_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "child_id": ids["child"],
            "person_id": person_id,
            "person_version_id": person_version_id,
            "evidence_id": evidence_id,
            "assessment_id": evidence_assessment_id,
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO child_authority_heads "
            "(organization_id,family_id,child_id,revision,created_operation_id,"
            "last_operation_id) VALUES "
            "(:organization_id,:family_id,:child_id,1,:operation_id,:operation_id)"
        ),
        {
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "child_id": ids["child"],
            "operation_id": operation_id,
        },
    )
    connection.execute(text("SET session_replication_role='origin'"))
    return {
        **ids,
        "facility": facility_id,
        "program": program_id,
        "room": room_id,
        "membership": membership_id,
        "role": role_id,
        "assignment": assignment_id,
        "shift": shift_id,
        "attendance_day": attendance_day_id,
        "attendance_interval": attendance_interval_id,
        "person": person_id,
        "person_version": person_version_id,
        "authorization": authorization_id,
    }


def test_runtime_projection_is_gated_minimum_and_direct_a2_reads_stay_closed() -> None:
    admin = create_engine(_url("postgres"))
    runtime = create_engine(_url(RUNTIME_ROLE))
    try:
        with admin.begin() as connection:
            ids = _seed_operational_gate(connection)

        with runtime.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=uuid4(),
            )
            assert connection.scalar(text("SELECT count(*) FROM child_authority_heads")) == 0
            raw = connection.scalar(
                text(
                    "SELECT public.caresync_family_release_context_inputs("
                    "CAST(:child_id AS uuid),CAST(:facility_id AS uuid))"
                ),
                {"child_id": ids["child"], "facility_id": ids["facility"]},
            )
            projection = ReleaseContextInput.model_validate(raw)
            assert projection.input_schema_version == "release-context-input-v1"
            assert projection.authority_revision == 1
            assert projection.organization_id == ids["organization"]
            assert projection.family_id == ids["family_a"]
            assert projection.room_id == ids["room"]
            assert projection.staff_shift_id == ids["shift"]
            assert len(projection.people) == 1
            assert projection.people[0].person_id == ids["person"]
            assert projection.people[0].current_versions[0].person_version_id == (
                ids["person_version"]
            )
            assert len(projection.authorizations) == 1
            assert projection.authorizations[0].authorization_id == ids["authorization"]
            assert projection.authorizations[0].supporting_evidence.bound_assessment_is_latest
            assert projection.rules == []
            assert projection.evaluated_at.tzinfo == UTC

        with runtime.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=uuid4(),
            )
            with pytest.raises(Exception, match="release_context_scope_not_found"):
                connection.scalar(
                    text(
                        "SELECT public.caresync_family_release_context_inputs("
                        "CAST(:child_id AS uuid),CAST(:facility_id AS uuid))"
                    ),
                    {"child_id": uuid4(), "facility_id": ids["facility"]},
                )
    finally:
        runtime.dispose()
        admin.dispose()


def test_security_definer_projection_rejects_every_operational_gate_failure() -> None:
    """Exercise the projection's bounded fail-closed paths as the runtime role."""

    cases = (
        ("forged_tenant", "release_context_scope_not_found", "P0002"),
        ("forged_user", "release_context_forbidden", "42501"),
        ("missing_release_read", "release_context_forbidden", "42501"),
        ("inactive_organization", "release_context_forbidden", "42501"),
        ("wrong_facility_shift", "open_shift_facility_mismatch", "P0001"),
        ("wrong_room_assignment", "release_context_scope_not_found", "P0002"),
        ("inactive_facility", "release_context_scope_not_found", "P0002"),
        ("inactive_room", "child_not_on_site", "P0001"),
    )
    admin = create_engine(_url("postgres"))
    runtime = create_engine(_url(RUNTIME_ROLE))
    try:
        for case, expected_message, expected_sqlstate in cases:
            context_organization_id = None
            context_user_id = None
            with admin.begin() as connection:
                ids = _seed_operational_gate(connection)
                context_organization_id = ids["organization"]
                context_user_id = ids["user"]

                if case == "forged_tenant":
                    foreign_identity = _seed_base(connection)
                    context_organization_id = foreign_identity["organization"]
                elif case == "forged_user":
                    foreign_identity = _seed_base(connection)
                    context_user_id = foreign_identity["user"]
                elif case == "missing_release_read":
                    connection.execute(
                        text("UPDATE roles SET permissions='[]'::json WHERE id=:role_id"),
                        {"role_id": ids["role"]},
                    )
                elif case == "inactive_organization":
                    connection.execute(
                        text("UPDATE organizations SET status='suspended' WHERE id=:id"),
                        {"id": ids["organization"]},
                    )
                elif case == "wrong_facility_shift":
                    other_facility_id = uuid4()
                    connection.execute(
                        text(
                            "INSERT INTO facilities "
                            "(id,organization_id,name,status,verification_status,province,"
                            "timezone,licensed_capacity) VALUES "
                            "(:id,:organization_id,'Other facility','active','pending',"
                            "'Alberta','America/Edmonton',20)"
                        ),
                        {
                            "id": other_facility_id,
                            "organization_id": ids["organization"],
                        },
                    )
                    connection.execute(
                        text("UPDATE staff_shifts SET facility_id=:facility WHERE id=:id"),
                        {"facility": other_facility_id, "id": ids["shift"]},
                    )
                elif case == "wrong_room_assignment":
                    other_room_id = uuid4()
                    connection.execute(
                        text(
                            "INSERT INTO rooms "
                            "(id,organization_id,facility_id,program_id,name,capacity,is_active) "
                            "VALUES (:id,:organization_id,:facility_id,:program_id,"
                            "'Preschool',20,true)"
                        ),
                        {
                            "id": other_room_id,
                            "organization_id": ids["organization"],
                            "facility_id": ids["facility"],
                            "program_id": ids["program"],
                        },
                    )
                    connection.execute(
                        text(
                            "UPDATE membership_room_assignments SET room_id=:room_id "
                            "WHERE id=:assignment_id"
                        ),
                        {
                            "room_id": other_room_id,
                            "assignment_id": ids["assignment"],
                        },
                    )
                elif case == "inactive_facility":
                    connection.execute(
                        text("UPDATE facilities SET status='inactive' WHERE id=:id"),
                        {"id": ids["facility"]},
                    )
                elif case == "inactive_room":
                    connection.execute(
                        text("UPDATE rooms SET is_active=false WHERE id=:id"),
                        {"id": ids["room"]},
                    )
                else:  # pragma: no cover - every case above is explicit
                    raise AssertionError(f"Unhandled gate case: {case}")

            with pytest.raises(DBAPIError) as captured, runtime.begin() as connection:
                _set_context(
                    connection,
                    organization_id=context_organization_id,
                    user_id=context_user_id,
                    operation_id=uuid4(),
                )
                connection.scalar(
                    text(
                        "SELECT public.caresync_family_release_context_inputs("
                        "CAST(:child_id AS uuid),CAST(:facility_id AS uuid))"
                    ),
                    {
                        "child_id": ids["child"],
                        "facility_id": ids["facility"],
                    },
                )
            assert captured.value.orig.diag.message_primary == expected_message, case
            assert captured.value.orig.sqlstate == expected_sqlstate, case
    finally:
        runtime.dispose()
        admin.dispose()


def test_postgres_revision_change_emits_one_exact_generic_event() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.begin() as connection:
            ids = _seed_operational_gate(connection)
            before = connection.scalar(
                text(
                    "SELECT count(*) FROM realtime_events WHERE organization_id=:org "
                    "AND event_type='family_authority.release_context_invalidated'"
                ),
                {"org": ids["organization"]},
            )
            connection.execute(
                text(
                    "ALTER TABLE child_authority_heads "
                    "DISABLE TRIGGER trg_child_authority_heads_transition_guard"
                )
            )
            connection.execute(
                text("UPDATE child_authority_heads SET revision=2 WHERE child_id=:child_id"),
                {"child_id": ids["child"]},
            )
            connection.execute(
                text("UPDATE child_authority_heads SET revision=2 WHERE child_id=:child_id"),
                {"child_id": ids["child"]},
            )
            connection.execute(
                text(
                    "ALTER TABLE child_authority_heads "
                    "ENABLE TRIGGER trg_child_authority_heads_transition_guard"
                )
            )
            events = connection.execute(
                text(
                    "SELECT event_type,entity_type,entity_id,payload "
                    "FROM realtime_events WHERE organization_id=:org "
                    "AND event_type='family_authority.release_context_invalidated' "
                    "ORDER BY sequence_id"
                ),
                {"org": ids["organization"]},
            ).all()
            assert len(events) == before + 1
            event = events[-1]
            assert event.event_type == "family_authority.release_context_invalidated"
            assert event.entity_type == "child_authority_head"
            assert event.entity_id is None
            assert event.payload == {
                "source": "authority_head",
                "scope": "release_context",
            }
    finally:
        admin.dispose()


def test_nonoverlapping_shift_and_attendance_states_never_compose_context() -> None:
    """One statement snapshot cannot synthesize operational eligibility.

    Every committed state has either an open shift or an open attendance
    interval, never both.  Rapid atomic transitions must therefore never yield
    a release-context input even under READ COMMITTED.
    """

    admin = create_engine(_url("postgres"), pool_size=3)
    runtime = create_engine(_url(RUNTIME_ROLE), pool_size=3)
    try:
        with admin.begin() as connection:
            ids = _seed_operational_gate(connection)
            connection.execute(
                text(
                    "UPDATE attendance_intervals "
                    "SET checked_out_at=statement_timestamp() WHERE id=:interval_id"
                ),
                {"interval_id": ids["attendance_interval"]},
            )

        barrier = Barrier(2)

        def toggle_nonoverlapping_states() -> None:
            barrier.wait()
            for iteration in range(400):
                shift_is_open = iteration % 2 == 1
                with admin.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE staff_shifts SET "
                            "status=CASE WHEN :is_open THEN 'open' ELSE 'closed' END,"
                            "clocked_out_at=CASE WHEN :is_open THEN NULL "
                            "ELSE statement_timestamp() END "
                            "WHERE id=:shift_id"
                        ),
                        {"is_open": shift_is_open, "shift_id": ids["shift"]},
                    )
                    connection.execute(
                        text(
                            "UPDATE attendance_intervals SET "
                            "checked_out_at=CASE WHEN :is_open THEN statement_timestamp() "
                            "ELSE NULL END WHERE id=:interval_id"
                        ),
                        {
                            "is_open": shift_is_open,
                            "interval_id": ids["attendance_interval"],
                        },
                    )

        def read_contexts() -> tuple[int, set[str]]:
            successes = 0
            failures: set[str] = set()
            barrier.wait()
            for _ in range(400):
                try:
                    with runtime.begin() as connection:
                        _set_context(
                            connection,
                            organization_id=ids["organization"],
                            user_id=ids["user"],
                            operation_id=uuid4(),
                        )
                        connection.scalar(
                            text(
                                "SELECT public.caresync_family_release_context_inputs("
                                "CAST(:child_id AS uuid),CAST(:facility_id AS uuid))"
                            ),
                            {
                                "child_id": ids["child"],
                                "facility_id": ids["facility"],
                            },
                        )
                except DBAPIError as exc:
                    message = str(exc.orig)
                    if "open_shift_required" in message:
                        failures.add("open_shift_required")
                    elif "child_not_on_site" in message:
                        failures.add("child_not_on_site")
                    else:  # pragma: no cover - preserves the unexpected DB diagnostic
                        raise
                else:
                    successes += 1
            return successes, failures

        with ThreadPoolExecutor(max_workers=2) as executor:
            toggle = executor.submit(toggle_nonoverlapping_states)
            reads = executor.submit(read_contexts)
            toggle.result(timeout=30)
            successes, failures = reads.result(timeout=30)

        assert successes == 0
        assert failures
        assert failures <= {"open_shift_required", "child_not_on_site"}
    finally:
        runtime.dispose()
        admin.dispose()


def test_z_postgres_exact_a2_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    port = int(TEST_PORT or "0")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "postgres")
    monkeypatch.setenv("DATABASE_HOST", TEST_HOST)
    monkeypatch.setenv("DATABASE_PORT", str(port))
    monkeypatch.setenv("DATABASE_USER", "postgres")
    monkeypatch.setenv("DATABASE_PASSWORD", "")
    monkeypatch.setenv("DATABASE_NAME", TEST_DATABASE)
    monkeypatch.setenv("DATABASE_SSL", "false")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("JWT_SECRET", "0029b-roundtrip-secret-at-least-32-bytes")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with pytest.raises(RuntimeError, match=r"exceeds the A2 VARCHAR\(40\) boundary"):
        command.downgrade(config, "0029A2_authority_activation")
    admin = create_engine(_url("postgres"))
    try:
        with admin.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
            connection.execute(text("SET session_replication_role='replica'"))
            connection.execute(
                text(
                    "UPDATE child_release_authorizations "
                    "SET verification_policy_code='government_photo_id'"
                )
            )
            connection.execute(text("SET session_replication_role='origin'"))
    finally:
        admin.dispose()

    command.downgrade(config, "0029A2_authority_activation")
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0029A2_authority_activation"
            )
            assert connection.scalar(
                text("SELECT pg_catalog.to_regprocedure(:signature)"),
                {"signature": PROJECTION},
            ) is None
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_trigger AS trigger "
                    "WHERE trigger.tgname='child_authority_heads_release_context_invalidated'"
                )
            ) == 0
    finally:
        admin.dispose()

    command.upgrade(config, CURRENT_REVISION)
    command.check(config)
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
            assert connection.scalar(
                text("SELECT pg_catalog.to_regprocedure(:signature) IS NOT NULL"),
                {"signature": PROJECTION},
            )
    finally:
        admin.dispose()
