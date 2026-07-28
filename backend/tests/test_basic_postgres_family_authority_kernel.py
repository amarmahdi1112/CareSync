"""Opt-in PostgreSQL security proofs for the 0029A authority kernel.

The suite never provisions or drops a database.  It runs only when an explicit
disposable loopback port is supplied and rejects every retained CareSync port.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)

CURRENT_REVISION = "0029A_family_authority_kernel"
PREVIOUS_REVISION = "0028_childcare_command_spine"
RUNTIME_ROLE = "caresync_basic_app"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_BIN = Path(
    os.getenv(
        "CARESYNC_POSTGRES_BIN",
        "/opt/homebrew/Cellar/postgresql@17/17.8/bin",
    )
)
AUTHORITY_TABLES = (
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
)
IMMUTABLE_TABLES = (
    "family_authority_person_versions",
    "family_authority_evidence",
    "family_authority_evidence_assessments",
    "consent_policy_versions",
    "attendance_release_snapshots",
)
FUTURE_READ_ONLY_TABLES = (
    "child_release_authorizations",
    "child_release_rules",
    "consent_policy_versions",
    "child_consent_decisions",
    "attendance_release_snapshots",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    host = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
    assert host in {"127.0.0.1", "localhost", "::1"}, "Remote PostgreSQL is forbidden"
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    assert 1 <= port <= 65535
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=host,
        port=port,
        database=os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
    )


def _set_context(
    connection,
    *,
    organization_id: UUID,
    user_id: UUID,
    operation_id: UUID,
) -> None:
    connection.execute(
        text("SELECT set_config('app.current_organization_id', :value, true)"),
        {"value": str(organization_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"),
        {"value": str(user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_childcare_operation_id', :value, true)"),
        {"value": str(operation_id)},
    )


def _seed_base(connection) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "organization",
            "user",
            "family_a",
            "family_b",
            "child",
            "role",
            "membership",
        )
    }
    connection.execute(
        text(
            "INSERT INTO organizations "
            "(id,name,status,timezone,preferences,verification_status) "
            "VALUES (:id,:name,'active','America/Edmonton','{}'::json,'pending')"
        ),
        {"id": ids["organization"], "name": f"Authority gate {uuid4().hex}"},
    )
    connection.execute(
        text(
            "INSERT INTO users "
            "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
            "VALUES (:id,:email,'unused','Authority','Gate',true,1)"
        ),
        {"id": ids["user"], "email": f"authority-{uuid4().hex}@example.test"},
    )
    connection.execute(
        text(
            "INSERT INTO roles "
            "(id,organization_id,key,name,description,permissions,is_system) "
            "VALUES (:id,:organization_id,:key,'Authority Gate','Test-only authority role',"
            "'[]'::json,false)"
        ),
        {
            "id": ids["role"],
            "organization_id": ids["organization"],
            "key": "administrator",
        },
    )
    connection.execute(
        text(
            "INSERT INTO organization_memberships "
            "(id,organization_id,user_id,role_id,status,joined_at) "
            "VALUES (:id,:organization_id,:user_id,:role_id,'active',statement_timestamp())"
        ),
        {
            "id": ids["membership"],
            "organization_id": ids["organization"],
            "user_id": ids["user"],
            "role_id": ids["role"],
        },
    )
    for family_key, family_name in (("family_a", "Family A"), ("family_b", "Family B")):
        connection.execute(
            text(
                "INSERT INTO families "
                "(id,organization_id,name,status,photo_consent,field_trip_consent,"
                "emergency_medical_consent) "
                "VALUES (:id,:organization_id,:name,'active',false,false,false)"
            ),
            {
                "id": ids[family_key],
                "organization_id": ids["organization"],
                "name": family_name,
            },
        )
    connection.execute(
        text(
            "INSERT INTO children "
            "(id,organization_id,family_id,first_name,last_name,date_of_birth,is_active) "
            "VALUES (:id,:organization_id,:family_id,'Family','Bound','2023-01-01',true)"
        ),
        {
            "id": ids["child"],
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
        },
    )
    return ids


def _seed_actor(connection, ids: dict[str, UUID], role_key: str) -> UUID:
    user_id = uuid4()
    role_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO users "
            "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
            "VALUES (:id,:email,'unused',:first_name,'Authority',true,1)"
        ),
        {
            "id": user_id,
            "email": f"authority-{role_key}-{uuid4().hex}@example.test",
            "first_name": role_key.title(),
        },
    )
    connection.execute(
        text(
            "INSERT INTO roles "
            "(id,organization_id,key,name,description,permissions,is_system) "
            "VALUES (:id,:organization_id,:key,:name,'Authority policy test actor',"
            "'[]'::json,false)"
        ),
        {
            "id": role_id,
            "organization_id": ids["organization"],
            "key": role_key,
            "name": role_key.title(),
        },
    )
    connection.execute(
        text(
            "INSERT INTO organization_memberships "
            "(id,organization_id,user_id,role_id,status,joined_at) "
            "VALUES (:id,:organization_id,:user_id,:role_id,'active',"
            "statement_timestamp())"
        ),
        {
            "id": uuid4(),
            "organization_id": ids["organization"],
            "user_id": user_id,
            "role_id": role_id,
        },
    )
    return user_id


def _insert_receipt(
    connection,
    ids: dict[str, UUID],
    *,
    operation_id: UUID,
    target_type: str,
    target_id: UUID,
    command_type: str,
    committed_version: int = 1,
    action_route: str | None = None,
) -> None:
    if action_route is None:
        if target_type == "authority_person":
            action_route = (
                f"/families/{ids['family_a']}?authority_person_id={target_id}"
            )
        elif target_type == "authority_evidence":
            action_route = (
                f"/families/{ids['family_a']}?authority_evidence_id={target_id}"
            )
        elif target_type == "release_authorization":
            action_route = (
                f"/children/{ids['child']}?release_authorization_id={target_id}"
            )
        elif target_type == "release_rule":
            action_route = f"/children/{ids['child']}?release_rule_id={target_id}"
        elif command_type == "organization.consent.policy.publish":
            action_route = f"/consent-policies/{target_id}"
        elif target_type == "consent":
            action_route = f"/children/{ids['child']}?consent_id={target_id}"
        elif target_type == "attendance_release":
            action_route = f"/attendance/releases/{target_id}"
        else:  # pragma: no cover - helper is limited to authority target types
            raise AssertionError(f"No authority action route for {target_type}")
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,committed_version,outcome) VALUES "
            "(:id,:organization_id,:operation_id,:command_type,:target_type,:target_id,"
            ":request_hash,:actor_user_id,:committed_version,"
            "jsonb_build_object('action_route',CAST(:action_route AS text)))"
        ),
        {
            "id": uuid4(),
            "organization_id": ids["organization"],
            "operation_id": operation_id,
            "command_type": command_type,
            "target_type": target_type,
            "target_id": target_id,
            "request_hash": uuid4().hex * 2,
            "actor_user_id": ids["user"],
            "committed_version": committed_version,
            "action_route": action_route,
        },
    )


def _create_authority_person(
    connection,
    ids: dict[str, UUID],
    *,
    person_id: UUID,
    version_id: UUID,
    operation_id: UUID,
) -> None:
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
        target_type="authority_person",
        target_id=person_id,
        command_type="family.authority.person.create",
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
            "version_id": version_id,
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_person_versions "
            "(id,organization_id,family_id,person_id,version_number,first_name,last_name,"
            "relationship_kind,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:person_id,1,'Original','Person',"
            "'parent',:operation_id)"
        ),
        {
            "id": version_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "person_id": person_id,
            "operation_id": operation_id,
        },
    )


def _replace_authority_person(
    connection,
    ids: dict[str, UUID],
    *,
    person_id: UUID,
    old_version_id: UUID,
    new_version_id: UUID,
    operation_id: UUID,
) -> None:
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
        target_type="authority_person",
        target_id=person_id,
        command_type="family.authority.person.replace",
        committed_version=2,
    )
    connection.execute(
        text(
            "UPDATE family_authority_person_versions SET "
            "closed_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
            "closed_operation_id=:operation_id WHERE id=:id"
        ),
        {"operation_id": operation_id, "id": old_version_id},
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_person_versions "
            "(id,organization_id,family_id,person_id,version_number,first_name,last_name,"
            "relationship_kind,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:person_id,2,'Replacement','Person',"
            "'parent',:operation_id)"
        ),
        {
            "id": new_version_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "person_id": person_id,
            "operation_id": operation_id,
        },
    )
    connection.execute(
        text(
            "UPDATE family_authority_people SET version=2,"
            "current_person_version_id=:new_version_id,last_operation_id=:operation_id "
            "WHERE id=:person_id"
        ),
        {
            "new_version_id": new_version_id,
            "operation_id": operation_id,
            "person_id": person_id,
        },
    )


def _retire_authority_person(
    connection,
    ids: dict[str, UUID],
    *,
    person_id: UUID,
    version_id: UUID,
    operation_id: UUID,
) -> None:
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
        target_type="authority_person",
        target_id=person_id,
        command_type="family.authority.person.retire",
        committed_version=3,
    )
    connection.execute(
        text(
            "UPDATE family_authority_person_versions SET "
            "closed_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
            "closed_operation_id=:operation_id WHERE id=:id"
        ),
        {"operation_id": operation_id, "id": version_id},
    )
    connection.execute(
        text(
            "UPDATE family_authority_people SET version=3,status='retired',"
            "current_person_version_id=NULL,"
            "retired_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
            "retired_operation_id=:operation_id,last_operation_id=:operation_id "
            "WHERE id=:id"
        ),
        {"operation_id": operation_id, "id": person_id},
    )


def _insert_release_rule(
    connection,
    ids: dict[str, UUID],
    *,
    rule_id: UUID,
    evidence_id: UUID,
    evidence_assessment_id: UUID,
    operation_id: UUID,
    effective_from: str,
    effective_until: str,
) -> None:
    _insert_receipt(
        connection,
        ids,
        operation_id=operation_id,
        target_type="release_rule",
        target_id=rule_id,
        command_type="child.release.rule.create",
    )
    connection.execute(
        text(
            "INSERT INTO child_release_rules "
            "(id,organization_id,family_id,child_id,rule_kind,scope_kind,scope_person_id,"
            "directing_person_id,directing_person_version_id,authority_basis_code,"
            "basis_evidence_id,basis_evidence_assessment_id,safe_explanation_code,"
            "confidential_reason,effective_from,effective_until,version,"
            "created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:child_id,'deny','all_recipients',NULL,"
            "NULL,NULL,'reviewed_custody_evidence',:evidence_id,"
            ":evidence_assessment_id,'release_restricted',"
            "'Direct PostgreSQL authority gate',:effective_from,:effective_until,1,"
            ":operation_id)"
        ),
        {
            "id": rule_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "child_id": ids["child"],
            "evidence_id": evidence_id,
            "evidence_assessment_id": evidence_assessment_id,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "operation_id": operation_id,
        },
    )


def _create_evidence_asset(
    connection,
    ids: dict[str, UUID],
    *,
    evidence_id: UUID,
    operation_id: UUID,
    expires_at_sql: str = "TIMESTAMPTZ '2099-01-01 00:00:00+00'",
) -> None:
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=operation_id,
    )
    _insert_receipt(
        connection,
        ids,
        operation_id=operation_id,
        target_type="authority_evidence",
        target_id=evidence_id,
        command_type="family.authority.evidence.record",
    )
    connection.execute(
        text(
            "INSERT INTO family_authority_evidence "
            "(id,organization_id,family_id,evidence_kind,source_label,expires_at,"
            "recorded_by_user_id,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,'custody_document',"
            f"'Person serialization gate',{expires_at_sql},:recorded_by,:operation_id)"
        ),
        {
            "id": evidence_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "recorded_by": ids["user"],
            "operation_id": operation_id,
        },
    )


def _create_reviewed_evidence(
    connection,
    ids: dict[str, UUID],
    *,
    evidence_id: UUID,
    operation_id: UUID,
    expires_at_sql: str = "TIMESTAMPTZ '2099-01-01 00:00:00+00'",
) -> UUID:
    _create_evidence_asset(
        connection,
        ids,
        evidence_id=evidence_id,
        operation_id=operation_id,
        expires_at_sql=expires_at_sql,
    )
    assessment_id = uuid4()
    review_operation_id = uuid4()
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=review_operation_id,
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
            "INSERT INTO family_authority_evidence_assessments "
            "(id,organization_id,family_id,evidence_id,version_number,decision,"
            "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
            "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed',"
            "'document_observed',:actor_user_id,:operation_id)"
        ),
        {
            "id": assessment_id,
            "organization_id": ids["organization"],
            "family_id": ids["family_a"],
            "evidence_id": evidence_id,
            "actor_user_id": ids["user"],
            "operation_id": review_operation_id,
        },
    )
    return assessment_id


def _publish_consent_policy(
    connection,
    ids: dict[str, UUID],
    *,
    policy_id: UUID,
    operation_id: UUID,
) -> None:
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=operation_id,
    )
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
            "(id,organization_id,purpose_code,version_number,title,content_reference,"
            "content_sha256,signer_authority_requirement,effective_from,effective_until,"
            "created_operation_id) VALUES "
            "(:id,:organization_id,'internal_media',1,'Internal media consent',"
            "'authority-kernel/policies/internal-media/v1',:content_sha256,"
            "'guardian_record',TIMESTAMPTZ '2030-01-01 00:00:00+00',"
            "TIMESTAMPTZ '2040-01-01 00:00:00+00',:operation_id)"
        ),
        {
            "id": policy_id,
            "organization_id": ids["organization"],
            "content_sha256": "a" * 64,
            "operation_id": operation_id,
        },
    )


def _insert_person_referencing_child_record(
    connection,
    ids: dict[str, UUID],
    *,
    record_kind: str,
    record_id: UUID,
    person_id: UUID,
    person_version_id: UUID,
    evidence_id: UUID,
    evidence_assessment_id: UUID,
    policy_id: UUID | None,
    operation_id: UUID,
) -> None:
    if record_kind == "authorization":
        target_type = "release_authorization"
        command_type = "child.release.authorization.grant"
    elif record_kind == "rule":
        target_type = "release_rule"
        command_type = "child.release.rule.create"
    elif record_kind == "consent":
        target_type = "consent"
        command_type = "child.consent.record"
    else:  # pragma: no cover - fixed test parametrization
        raise AssertionError(f"unsupported authority race record: {record_kind}")

    _insert_receipt(
        connection,
        ids,
        operation_id=operation_id,
        target_type=target_type,
        target_id=record_id,
        command_type=command_type,
    )
    if record_kind == "authorization":
        connection.execute(
            text(
                "INSERT INTO child_release_authorizations "
                "(id,organization_id,family_id,child_id,recipient_person_id,"
                "verification_policy_code,grantor_person_id,grantor_person_version_id,"
                "grantor_authority_basis,basis_evidence_id,basis_evidence_assessment_id,"
                "effective_from,effective_until,version,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:child_id,:person_id,"
                "'government_photo_id',:person_id,:person_version_id,"
                "'reviewed_custody_evidence',:evidence_id,:evidence_assessment_id,"
                "TIMESTAMPTZ '2035-01-01 00:00:00+00',"
                "TIMESTAMPTZ '2036-01-01 00:00:00+00',1,:operation_id)"
            ),
            {
                "id": record_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
                "child_id": ids["child"],
                "person_id": person_id,
                "person_version_id": person_version_id,
                "evidence_id": evidence_id,
                "evidence_assessment_id": evidence_assessment_id,
                "operation_id": operation_id,
            },
        )
    elif record_kind == "rule":
        connection.execute(
            text(
                "INSERT INTO child_release_rules "
                "(id,organization_id,family_id,child_id,rule_kind,scope_kind,"
                "scope_person_id,directing_person_id,directing_person_version_id,"
                "authority_basis_code,basis_evidence_id,basis_evidence_assessment_id,"
                "safe_explanation_code,"
                "confidential_reason,effective_from,effective_until,version,"
                "created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:child_id,'deny','specific_person',"
                ":person_id,:person_id,:person_version_id,'reviewed_custody_evidence',"
                ":evidence_id,:evidence_assessment_id,'release_restricted',"
                "'Person serialization race gate',"
                "TIMESTAMPTZ '2035-01-01 00:00:00+00',"
                "TIMESTAMPTZ '2036-01-01 00:00:00+00',1,:operation_id)"
            ),
            {
                "id": record_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
                "child_id": ids["child"],
                "person_id": person_id,
                "person_version_id": person_version_id,
                "evidence_id": evidence_id,
                "evidence_assessment_id": evidence_assessment_id,
                "operation_id": operation_id,
            },
        )
    else:
        assert policy_id is not None
        connection.execute(
            text(
                "INSERT INTO child_consent_decisions "
                "(id,organization_id,family_id,child_id,purpose_code,policy_version_id,"
                "signer_person_id,signer_person_version_id,signer_authority_basis,"
                "evidence_id,evidence_assessment_id,decision,scope_kind,effective_from,"
                "effective_until,version,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:child_id,'internal_media',:policy_id,"
                ":person_id,:person_version_id,'guardian_record',:evidence_id,"
                ":evidence_assessment_id,'granted',"
                "'policy',TIMESTAMPTZ '2035-01-01 00:00:00+00',"
                "TIMESTAMPTZ '2036-01-01 00:00:00+00',1,:operation_id)"
            ),
            {
                "id": record_id,
                "organization_id": ids["organization"],
                "family_id": ids["family_a"],
                "child_id": ids["child"],
                "policy_id": policy_id,
                "person_id": person_id,
                "person_version_id": person_version_id,
                "evidence_id": evidence_id,
                "evidence_assessment_id": evidence_assessment_id,
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


def _cleanup(admin_engine, ids: dict[str, UUID], operations: set[UUID]) -> None:
    with admin_engine.begin() as connection:
        # People and their current fact versions form an intentional cycle. The
        # current-version edge is deferred so test cleanup can remove the exact
        # tenant atomically without weakening either production foreign key.
        connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        connection.execute(
            text(
                "UPDATE family_authority_people SET status='retired',"
                "current_person_version_id=NULL,"
                "retired_at=COALESCE(retired_at,statement_timestamp()),"
                "retired_operation_id=COALESCE(retired_operation_id,last_operation_id) "
                "WHERE organization_id=:organization_id AND status='active'"
            ),
            {"organization_id": ids["organization"]},
        )
        for table_name in reversed(AUTHORITY_TABLES):
            connection.execute(
                text(f'DELETE FROM public."{table_name}" WHERE organization_id=:organization_id'),
                {"organization_id": ids["organization"]},
            )
        connection.execute(
            text(
                "DELETE FROM childcare_command_receipts "
                "WHERE organization_id=:organization_id"
            ),
            {"organization_id": ids["organization"]},
        )
        if operations:
            connection.execute(
                text(
                    "DELETE FROM childcare_command_slots "
                    "WHERE organization_id=:organization_id"
                ),
                {"organization_id": ids["organization"]},
            )
        connection.execute(
            text("DELETE FROM children WHERE organization_id=:organization_id"),
            {"organization_id": ids["organization"]},
        )
        connection.execute(
            text("DELETE FROM families WHERE organization_id=:organization_id"),
            {"organization_id": ids["organization"]},
        )
        connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": ids["user"]})
        connection.execute(
            text("DELETE FROM organizations WHERE id=:id"),
            {"id": ids["organization"]},
        )


def test_postgres_catalog_enforces_tenancy_least_grants_and_triggered_history() -> None:
    admin_engine = create_engine(_url("postgres"))
    with admin_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            CURRENT_REVISION
        )
        catalog = {
            row.relname: (row.relrowsecurity, row.relforcerowsecurity)
            for row in connection.execute(
                text(
                    "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' "
                    "AND c.relname = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            )
        }
        assert catalog == {table_name: (True, True) for table_name in AUTHORITY_TABLES}

        policies = {
            row.tablename: (
                row.policyname,
                (row.qual or "") + " " + (row.with_check or ""),
            )
            for row in connection.execute(
                text(
                    "SELECT tablename,policyname,qual,with_check FROM pg_policies "
                    "WHERE schemaname='public' "
                    "AND tablename = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            )
        }
        assert set(policies) == set(AUTHORITY_TABLES)
        assert all(
            policy_name == f"{table_name}_privileged_actor"
            and "caresync_family_authority_actor_is_privileged(organization_id)"
            in definition
            for table_name, (policy_name, definition) in policies.items()
        )

        function_acl = {
            row.signature: row.runtime_can_execute
            for row in connection.execute(
                text(
                    "SELECT p.oid::regprocedure::text AS signature,"
                    "has_function_privilege(:role,p.oid,'EXECUTE') AS runtime_can_execute "
                    "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' "
                    "AND p.proname LIKE 'caresync_family_authority_%'"
                ),
                {"role": RUNTIME_ROLE},
            )
        }
        assert function_acl["caresync_family_authority_actor_is_privileged(uuid)"] is True
        assert all(
            allowed is False
            for signature, allowed in function_acl.items()
            if signature != "caresync_family_authority_actor_is_privileged(uuid)"
        )

        for table_name in AUTHORITY_TABLES:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'DELETE')"),
                {"role": RUNTIME_ROLE, "table": f"public.{table_name}"},
            ) is False
        for table_name in IMMUTABLE_TABLES:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'UPDATE')"),
                {"role": RUNTIME_ROLE, "table": f"public.{table_name}"},
            ) is False
        for table_name in FUTURE_READ_ONLY_TABLES:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'SELECT')"),
                {"role": RUNTIME_ROLE, "table": f"public.{table_name}"},
            ) is True
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert connection.scalar(
                    text("SELECT has_table_privilege(:role,:table,:privilege)"),
                    {
                        "role": RUNTIME_ROLE,
                        "table": f"public.{table_name}",
                        "privilege": privilege,
                    },
                ) is False

        trigger_definitions = "\n".join(
            connection.scalars(
                text(
                    "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE NOT t.tgisinternal AND n.nspname='public' "
                    "AND c.relname = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            )
        )
        assert "family_authority_people" in trigger_definitions
        assert "child_authority_heads" in trigger_definitions
        assert "attendance_release_snapshots" in trigger_definitions

        function_definitions = "\n".join(
            connection.scalars(
                text(
                    "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='public' AND p.proname LIKE 'caresync_family_authority_%'"
                )
            )
        )
        constraint_definitions = "\n".join(
            connection.scalars(
                text(
                    "SELECT pg_get_constraintdef(con.oid) FROM pg_constraint con "
                    "JOIN pg_class c ON c.oid=con.conrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' "
                    "AND c.relname = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            )
        )
        for fragment in (
            "app.current_organization_id",
            "app.current_user_id",
            "app.current_childcare_operation_id",
            "pg_current_xact_id()",
            "command_receipt.command_type",
            "command_receipt.target_type",
            "command_receipt.target_id",
        ):
            assert fragment in function_definitions
        database_proof = (constraint_definitions + "\n" + function_definitions).lower()
        compact_proof = "".join(database_proof.split())
        assert "^[0-9a-f]{64}$" in database_proof
        assert "isfinite(" in database_proof
        for fragment in (
            "release_authorization.version=new.authorization_version",
            "head.revision=new.authority_revision",
            "person.current_person_version_id=new.recipient_person_version_id",
            "command_receipt.request_hash<>new.request_hash",
            "command_receipt.actor_user_id<>new.actor_user_id",
            "new.revision<>old.revision+1",
            "existing.scope_person_idisnotdistinctfromnew.scope_person_id",
            "pg_advisory_xact_lock",
        ):
            assert fragment in compact_proof
    admin_engine.dispose()


def test_runtime_cannot_write_unreleased_downstream_authority_tables() -> None:
    """0029A exposes future authority projections as read-only scaffolding."""

    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    try:
        for table_name in FUTURE_READ_ONLY_TABLES:
            with pytest.raises(DBAPIError) as error, runtime_engine.begin() as connection:
                connection.execute(text(f'INSERT INTO public."{table_name}" DEFAULT VALUES'))
            assert getattr(error.value.orig, "sqlstate", None) == "42501"
    finally:
        runtime_engine.dispose()


def test_evidence_rls_allows_admin_and_hides_rows_from_educator() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    operation_id = uuid4()
    educator_operation = uuid4()
    evidence_id = uuid4()
    operations = {operation_id, educator_operation}
    educator_user_id: UUID | None = None
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)
        educator_user_id = _seed_actor(connection, ids, "educator")

    try:
        with runtime_engine.begin() as connection:
            assessment_id = _create_reviewed_evidence(
                connection,
                ids,
                evidence_id=evidence_id,
                operation_id=operation_id,
            )
            assert connection.scalar(
                text(
                    "SELECT public.caresync_family_authority_actor_is_privileged("
                    ":organization_id)"
                ),
                {"organization_id": ids["organization"]},
            ) is True

        with runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=educator_user_id,
                operation_id=educator_operation,
            )
            assert connection.scalar(
                text(
                    "SELECT public.caresync_family_authority_actor_is_privileged("
                    ":organization_id)"
                ),
                {"organization_id": ids["organization"]},
            ) is False
            assert connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM family_authority_evidence),"
                    "(SELECT count(*) FROM family_authority_evidence_assessments)"
                )
            ).one() == (0, 0)

        denied_evidence_id = uuid4()
        with pytest.raises(DBAPIError) as denied, runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=educator_user_id,
                operation_id=educator_operation,
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_evidence "
                    "(id,organization_id,family_id,evidence_kind,source_label,"
                    "recorded_by_user_id,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,'guardian_attestation',"
                    "'Educator RLS denial',:recorded_by,:operation_id)"
                ),
                {
                    "id": denied_evidence_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "recorded_by": educator_user_id,
                    "operation_id": educator_operation,
                },
            )
        assert getattr(denied.value.orig, "sqlstate", None) in {"23514", "42501"}

        with admin_engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM family_authority_evidence WHERE id=:evidence_id),"
                    "(SELECT count(*) FROM family_authority_evidence_assessments "
                    " WHERE id=:assessment_id),"
                    "(SELECT count(*) FROM family_authority_evidence "
                    " WHERE id=:denied_evidence_id)"
                ),
                {
                    "evidence_id": evidence_id,
                    "assessment_id": assessment_id,
                    "denied_evidence_id": denied_evidence_id,
                },
            ).one() == (1, 1, 0)
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        if educator_user_id is not None:
            with admin_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM users WHERE id=:id"),
                    {"id": educator_user_id},
                )
        admin_engine.dispose()


def test_restore_owner_cannot_mismatch_evidence_assessment_receipt_actor() -> None:
    admin_engine = create_engine(_url("postgres"))
    record_operation = uuid4()
    review_operation = uuid4()
    evidence_id = uuid4()
    assessment_id = uuid4()
    operations = {record_operation, review_operation}
    owner_user_id: UUID | None = None
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)
        owner_user_id = _seed_actor(connection, ids, "owner")

    try:
        with admin_engine.begin() as connection:
            _create_evidence_asset(
                connection,
                ids,
                evidence_id=evidence_id,
                operation_id=record_operation,
            )

        with pytest.raises(DBAPIError) as mismatch, admin_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=review_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            _insert_receipt(
                connection,
                ids,
                operation_id=review_operation,
                target_type="authority_evidence",
                target_id=evidence_id,
                command_type="family.authority.evidence.review",
                committed_version=2,
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_evidence_assessments "
                    "(id,organization_id,family_id,evidence_id,version_number,decision,"
                    "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed',"
                    "'document_observed',:actor_user_id,:operation_id)"
                ),
                {
                    "id": assessment_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "evidence_id": evidence_id,
                    "actor_user_id": owner_user_id,
                    "operation_id": review_operation,
                },
            )
        assert (
            mismatch.value.orig.diag.constraint_name
            == "ck_authority_evidence_assessment_receipt"
        )
        with admin_engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM family_authority_evidence_assessments "
                    " WHERE id=:assessment_id),"
                    "(SELECT count(*) FROM childcare_command_receipts "
                    " WHERE organization_id=:organization_id "
                    " AND client_operation_id=:operation_id)"
                ),
                {
                    "assessment_id": assessment_id,
                    "organization_id": ids["organization"],
                    "operation_id": review_operation,
                },
            ).one() == (0, 0)
    finally:
        _cleanup(admin_engine, ids, operations)
        if owner_user_id is not None:
            with admin_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM users WHERE id=:id"),
                    {"id": owner_user_id},
                )
        admin_engine.dispose()


def test_populated_evidence_survives_exact_pg_dump_restore(tmp_path) -> None:
    """A real PostgreSQL backup preserves asset, assessment, and receipt provenance."""

    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    record_operation = uuid4()
    evidence_id = uuid4()
    operations = {record_operation}
    restore_database = f"caresync_evidence_restore_{uuid4().hex[:12]}"
    assert restore_database.startswith("caresync_evidence_restore_")
    dump_path = tmp_path / "family-authority-evidence.dump"
    restore_created = False
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        with runtime_engine.begin() as connection:
            assessment_id = _create_reviewed_evidence(
                connection,
                ids,
                evidence_id=evidence_id,
                operation_id=record_operation,
            )

        with admin_engine.connect() as connection:
            expected_asset = dict(
                connection.execute(
                    text(
                        "SELECT * FROM family_authority_evidence "
                        "WHERE organization_id=:organization_id AND id=:evidence_id"
                    ),
                    {
                        "organization_id": ids["organization"],
                        "evidence_id": evidence_id,
                    },
                ).one()._mapping
            )
            expected_assessment = dict(
                connection.execute(
                    text(
                        "SELECT * FROM family_authority_evidence_assessments "
                        "WHERE organization_id=:organization_id AND id=:assessment_id"
                    ),
                    {
                        "organization_id": ids["organization"],
                        "assessment_id": assessment_id,
                    },
                ).one()._mapping
            )
            expected_receipts = [
                dict(row._mapping)
                for row in connection.execute(
                    text(
                        "SELECT * FROM childcare_command_receipts "
                        "WHERE organization_id=:organization_id "
                        "AND client_operation_id IN (:record_operation,:review_operation) "
                        "ORDER BY committed_version"
                    ),
                    {
                        "organization_id": ids["organization"],
                        "record_operation": record_operation,
                        "review_operation": expected_assessment["created_operation_id"],
                    },
                )
            ]
        assert len(expected_receipts) == 2

        subprocess.run(
            [
                str(POSTGRES_BIN / "pg_dump"),
                "--format=custom",
                "--file",
                str(dump_path),
                "--host",
                os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
                "--port",
                str(TEST_PORT),
                "--username",
                "postgres",
                os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                str(POSTGRES_BIN / "createdb"),
                "--host",
                os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
                "--port",
                str(TEST_PORT),
                "--username",
                "postgres",
                "--owner",
                "migration_owner",
                restore_database,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        restore_created = True
        subprocess.run(
            [
                str(POSTGRES_BIN / "pg_restore"),
                "--exit-on-error",
                "--no-owner",
                "--host",
                os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
                "--port",
                str(TEST_PORT),
                "--username",
                "migration_owner",
                "--dbname",
                restore_database,
                str(dump_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        restore_engine = create_engine(
            _url("postgres").set(database=restore_database)
        )
        try:
            with restore_engine.connect() as connection:
                restored_asset = dict(
                    connection.execute(
                        text(
                            "SELECT * FROM family_authority_evidence "
                            "WHERE organization_id=:organization_id AND id=:evidence_id"
                        ),
                        {
                            "organization_id": ids["organization"],
                            "evidence_id": evidence_id,
                        },
                    ).one()._mapping
                )
                restored_assessment = dict(
                    connection.execute(
                        text(
                            "SELECT * FROM family_authority_evidence_assessments "
                            "WHERE organization_id=:organization_id AND id=:assessment_id"
                        ),
                        {
                            "organization_id": ids["organization"],
                            "assessment_id": assessment_id,
                        },
                    ).one()._mapping
                )
                restored_receipts = [
                    dict(row._mapping)
                    for row in connection.execute(
                        text(
                            "SELECT * FROM childcare_command_receipts "
                            "WHERE organization_id=:organization_id "
                            "AND client_operation_id IN "
                            "(:record_operation,:review_operation) "
                            "ORDER BY committed_version"
                        ),
                        {
                            "organization_id": ids["organization"],
                            "record_operation": record_operation,
                            "review_operation": expected_assessment[
                                "created_operation_id"
                            ],
                        },
                    )
                ]
                restored_revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            assert restored_asset == expected_asset
            assert restored_assessment == expected_assessment
            assert restored_receipts == expected_receipts
            assert restored_revision == CURRENT_REVISION
        finally:
            restore_engine.dispose()
    finally:
        runtime_engine.dispose()
        if restore_created:
            subprocess.run(
                [
                    str(POSTGRES_BIN / "dropdb"),
                    "--force",
                    "--host",
                    os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
                    "--port",
                    str(TEST_PORT),
                    "--username",
                    "postgres",
                    restore_database,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def test_empty_postgres_0028_0029a_round_trip_is_repeatable() -> None:
    """Exercise the empty boundary while preserving the disposable baseline DB."""

    database_name = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
    saved_database = f"caresync_roundtrip_saved_{uuid4().hex[:12]}"
    assert database_name == "caresync"
    assert saved_database.startswith("caresync_roundtrip_saved_")
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": os.getenv(
                "BASIC_POSTGRES_TEST_HOST", "127.0.0.1"
            ),
            "DATABASE_PORT": str(TEST_PORT),
            "DATABASE_USER": "migration_owner",
            "DATABASE_PASSWORD": "",
            "DATABASE_NAME": database_name,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )

    def migrate(direction: str, revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=BACKEND_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    control_engine = create_engine(
        _url("postgres").set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    roundtrip_engine = None
    baseline_renamed = False
    scratch_created = False
    try:
        with control_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database_name AND pid<>pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(
                text(f'ALTER DATABASE "{database_name}" RENAME TO "{saved_database}"')
            )
        baseline_renamed = True
        subprocess.run(
            [
                str(POSTGRES_BIN / "createdb"),
                "--host",
                environment["DATABASE_HOST"],
                "--port",
                environment["DATABASE_PORT"],
                "--username",
                "postgres",
                "--owner",
                "migration_owner",
                database_name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        scratch_created = True
        migrate("upgrade", PREVIOUS_REVISION)
        roundtrip_engine = create_engine(_url("postgres"))
        with roundtrip_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == PREVIOUS_REVISION
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' "
                    "AND table_name = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            ) == 0
        roundtrip_engine.dispose()

        migrate("upgrade", CURRENT_REVISION)
        roundtrip_engine = create_engine(_url("postgres"))
        with roundtrip_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == CURRENT_REVISION
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' "
                    "AND table_name = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            ) == len(AUTHORITY_TABLES)
        roundtrip_engine.dispose()

        migrate("downgrade", PREVIOUS_REVISION)
        roundtrip_engine = create_engine(_url("postgres"))
        with roundtrip_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == PREVIOUS_REVISION
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' "
                    "AND table_name = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            ) == 0
            receipt_target_check = connection.scalar(
                text(
                    "SELECT pg_get_constraintdef(con.oid) FROM pg_constraint con "
                    "JOIN pg_class cls ON cls.oid=con.conrelid "
                    "WHERE cls.relname='childcare_command_receipts' "
                    "AND con.conname='ck_childcare_receipts_target_type'"
                )
            )
            assert "authority_evidence" not in str(receipt_target_check)

        roundtrip_engine.dispose()
        migrate("upgrade", CURRENT_REVISION)
        roundtrip_engine = create_engine(_url("postgres"))
        with roundtrip_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == CURRENT_REVISION
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public' "
                    "AND table_name = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": list(AUTHORITY_TABLES)},
            ) == len(AUTHORITY_TABLES)
    finally:
        if roundtrip_engine is not None:
            roundtrip_engine.dispose()
        if scratch_created:
            subprocess.run(
                [
                    str(POSTGRES_BIN / "dropdb"),
                    "--force",
                    "--host",
                    environment["DATABASE_HOST"],
                    "--port",
                    environment["DATABASE_PORT"],
                    "--username",
                    "postgres",
                    database_name,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        if baseline_renamed:
            with control_engine.connect() as connection:
                connection.execute(
                    text(
                        f'ALTER DATABASE "{saved_database}" RENAME TO "{database_name}"'
                    )
                )
        control_engine.dispose()


def test_runtime_rejects_missing_and_orphaned_receipt_provenance() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    operations: set[UUID] = set()
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)
    person_id = uuid4()
    version_id = uuid4()
    missing_operation = uuid4()
    operations.add(missing_operation)
    try:
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=missing_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
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
                    "version_id": version_id,
                    "operation_id": missing_operation,
                },
            )

        stale_operation = uuid4()
        operations.add(stale_operation)
        # A receipt is a commit proof, not a capability that may be persisted
        # before (or without) its exact domain row.
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=stale_operation,
            )
            _insert_receipt(
                connection,
                ids,
                operation_id=stale_operation,
                target_type="authority_person",
                target_id=person_id,
                command_type="family.authority.person.create",
            )

        # The failed orphan transaction leaves no stale authority behind.
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=stale_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
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
                    "version_id": version_id,
                    "operation_id": stale_operation,
                },
            )
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


@pytest.mark.parametrize(
    ("poison_kind", "expected_constraint"),
    (
        ("non_hex_hash", "ck_family_authority_receipt_metadata"),
        ("extra_outcome", "ck_family_authority_receipt_metadata"),
        ("wrong_action_route", "ck_family_authority_receipt_command"),
        ("blank_optional_fact", "ck_authority_person_versions_optional_facts"),
    ),
)
def test_runtime_rejects_poisoned_authority_receipts_and_append_only_facts(
    poison_kind: str,
    expected_constraint: str,
) -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    operation_id = uuid4()
    person_id = uuid4()
    version_id = uuid4()
    operations = {operation_id}
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)
    canonical_route = (
        f"/families/{ids['family_a']}?authority_person_id={person_id}"
    )

    try:
        with pytest.raises(DBAPIError) as error, runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=operation_id,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            if poison_kind == "blank_optional_fact":
                _insert_receipt(
                    connection,
                    ids,
                    operation_id=operation_id,
                    target_type="authority_person",
                    target_id=person_id,
                    command_type="family.authority.person.create",
                )
            else:
                outcome = {"action_route": canonical_route}
                if poison_kind == "extra_outcome":
                    outcome["first_name"] = "must-not-enter-the-ledger"
                if poison_kind == "wrong_action_route":
                    outcome["action_route"] = (
                        f"/families/{ids['family_a']}?authority_person_id={uuid4()}"
                    )
                connection.execute(
                    text(
                        "INSERT INTO childcare_command_receipts "
                        "(id,organization_id,client_operation_id,command_type,target_type,"
                        "target_id,request_hash,actor_user_id,committed_version,outcome) "
                        "VALUES (:id,:organization_id,:operation_id,"
                        "'family.authority.person.create','authority_person',:target_id,"
                        ":request_hash,:actor_user_id,1,CAST(:outcome AS json))"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": ids["organization"],
                        "operation_id": operation_id,
                        "target_id": person_id,
                        "request_hash": (
                            "Z" * 64 if poison_kind == "non_hex_hash" else "a" * 64
                        ),
                        "actor_user_id": ids["user"],
                        "outcome": json.dumps(outcome),
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
                    "version_id": version_id,
                    "operation_id": operation_id,
                },
            )
            if poison_kind == "blank_optional_fact":
                connection.execute(
                    text(
                        "INSERT INTO family_authority_person_versions "
                        "(id,organization_id,family_id,person_id,version_number,first_name,"
                        "middle_name,last_name,relationship_kind,created_operation_id) VALUES "
                        "(:id,:organization_id,:family_id,:person_id,1,'Valid','   ',"
                        "'Person','family_friend',:operation_id)"
                    ),
                    {
                        "id": version_id,
                        "organization_id": ids["organization"],
                        "family_id": ids["family_a"],
                        "person_id": person_id,
                        "operation_id": operation_id,
                    },
                )
        assert error.value.orig.diag.constraint_name == expected_constraint
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def test_runtime_rejects_receipt_with_wrong_committed_aggregate_version() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    person_id = uuid4()
    version_id = uuid4()
    operation_id = uuid4()
    operations = {operation_id}
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        # A create command can only commit aggregate version one. Both rows are
        # included so an implementation that ignores the receipt's version
        # cannot pass merely because the deferred person invariant is incomplete.
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
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
                target_type="authority_person",
                target_id=person_id,
                command_type="family.authority.person.create",
                committed_version=2,
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
                    "version_id": version_id,
                    "operation_id": operation_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_person_versions "
                    "(id,organization_id,family_id,person_id,version_number,first_name,"
                    "last_name,relationship_kind,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,:person_id,1,'Wrong','Version',"
                    "'parent',:operation_id)"
                ),
                {
                    "id": version_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "person_id": person_id,
                    "operation_id": operation_id,
                },
            )

        with admin_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM family_authority_people WHERE id=:id"),
                {"id": person_id},
            ) == 0
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM childcare_command_receipts "
                    "WHERE organization_id=:organization_id "
                    "AND client_operation_id=:operation_id"
                ),
                {
                    "organization_id": ids["organization"],
                    "operation_id": operation_id,
                },
            ) == 0
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def test_runtime_create_replace_retire_path_is_server_stamped_and_history_is_immutable() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    operations: set[UUID] = set()
    person_id = uuid4()
    first_version_id = uuid4()
    second_version_id = uuid4()
    create_operation = uuid4()
    replace_operation = uuid4()
    retire_operation = uuid4()
    operations.update({create_operation, replace_operation, retire_operation})
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        # These are real restricted-role writes. Owner/admin access is used
        # only for disposable base seeding, inspection, and cleanup.
        with runtime_engine.begin() as connection:
            _create_authority_person(
                connection,
                ids,
                person_id=person_id,
                version_id=first_version_id,
                operation_id=create_operation,
            )
        with runtime_engine.begin() as connection:
            _replace_authority_person(
                connection,
                ids,
                person_id=person_id,
                old_version_id=first_version_id,
                new_version_id=second_version_id,
                operation_id=replace_operation,
            )
        with runtime_engine.begin() as connection:
            _retire_authority_person(
                connection,
                ids,
                person_id=person_id,
                version_id=second_version_id,
                operation_id=retire_operation,
            )

        with admin_engine.connect() as connection:
            person = connection.execute(
                text(
                    "SELECT version,status,current_person_version_id,retired_at,created_at "
                    "FROM family_authority_people WHERE id=:id"
                ),
                {"id": person_id},
            ).one()
            versions = connection.execute(
                text(
                    "SELECT id,version_number,created_at,closed_at "
                    "FROM family_authority_person_versions WHERE person_id=:person_id "
                    "ORDER BY version_number"
                ),
                {"person_id": person_id},
            ).all()
        assert (person.version, person.status, person.current_person_version_id) == (
            3,
            "retired",
            None,
        )
        assert person.retired_at >= person.created_at
        assert len(versions) == 2
        assert [row.version_number for row in versions] == [1, 2]
        assert all(row.closed_at >= row.created_at for row in versions)
        assert all(row.closed_at.year != 2000 for row in versions)
        assert person.retired_at.year != 2000

        rewrite_operation = uuid4()
        operations.add(rewrite_operation)
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=rewrite_operation,
            )
            connection.execute(
                text(
                    "UPDATE family_authority_person_versions "
                    "SET first_name='Rewritten' WHERE id=:id"
                ),
                {"id": first_version_id},
            )

        reopen_operation = uuid4()
        operations.add(reopen_operation)
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=reopen_operation,
            )
            connection.execute(
                text(
                    "UPDATE family_authority_person_versions "
                    "SET closed_at=NULL,closed_operation_id=NULL WHERE id=:id"
                ),
                {"id": first_version_id},
            )
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def _future_runtime_rejects_skipped_head_revision_and_all_recipient_overlap_race() -> None:
    """Retained for the downstream command slice, when runtime writes are released."""
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE), pool_size=4)
    operations: set[UUID] = set()
    evidence_id = uuid4()
    evidence_assessment_id: UUID
    evidence_operation = uuid4()
    seed_rule_id = uuid4()
    seed_rule_operation = uuid4()
    skipped_rule_id = uuid4()
    skipped_operation = uuid4()
    race_rule_ids = (uuid4(), uuid4())
    race_operations = (uuid4(), uuid4())
    operations.update(
        {
            evidence_operation,
            seed_rule_operation,
            skipped_operation,
            *race_operations,
        }
    )
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        with runtime_engine.begin() as connection:
            evidence_assessment_id = _create_reviewed_evidence(
                connection,
                ids,
                evidence_id=evidence_id,
                operation_id=evidence_operation,
            )

        with runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=seed_rule_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            _insert_release_rule(
                connection,
                ids,
                rule_id=seed_rule_id,
                evidence_id=evidence_id,
                evidence_assessment_id=evidence_assessment_id,
                operation_id=seed_rule_operation,
                effective_from="2025-01-01 00:00:00+00",
                effective_until="2025-02-01 00:00:00+00",
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
                    "operation_id": seed_rule_operation,
                },
            )

        # A valid new rule cannot smuggle a 1 -> 3 head jump through the
        # deferred record/head invariant.
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=skipped_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            _insert_release_rule(
                connection,
                ids,
                rule_id=skipped_rule_id,
                evidence_id=evidence_id,
                evidence_assessment_id=evidence_assessment_id,
                operation_id=skipped_operation,
                effective_from="2026-01-01 00:00:00+00",
                effective_until="2026-02-01 00:00:00+00",
            )
            connection.execute(
                text(
                    "UPDATE child_authority_heads SET revision=3,"
                    "last_operation_id=:operation_id WHERE child_id=:child_id"
                ),
                {"operation_id": skipped_operation, "child_id": ids["child"]},
            )

        barrier = Barrier(2)

        def attempt_racing_rule(rule_id: UUID, operation_id: UUID) -> bool:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(
                        connection,
                        organization_id=ids["organization"],
                        user_id=ids["user"],
                        operation_id=operation_id,
                    )
                    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                    barrier.wait(timeout=10)
                    _insert_release_rule(
                        connection,
                        ids,
                        rule_id=rule_id,
                        evidence_id=evidence_id,
                        evidence_assessment_id=evidence_assessment_id,
                        operation_id=operation_id,
                        effective_from="2030-01-01 00:00:00+00",
                        effective_until="2030-02-01 00:00:00+00",
                    )
                    connection.execute(
                        text(
                            "UPDATE child_authority_heads SET revision=2,"
                            "last_operation_id=:operation_id WHERE child_id=:child_id"
                        ),
                        {"operation_id": operation_id, "child_id": ids["child"]},
                    )
                return True
            except DBAPIError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(attempt_racing_rule, race_rule_ids, race_operations)
            )
        assert sorted(results) == [False, True]

        with admin_engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT revision FROM child_authority_heads WHERE child_id=:child_id"
                ),
                {"child_id": ids["child"]},
            ) == 2
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM child_release_rules "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": list(race_rule_ids)},
            ) == 1
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def test_runtime_rejects_public_storage_and_evidence_expiring_before_commit() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    invalid_evidence_id = uuid4()
    invalid_evidence_operation = uuid4()
    expiring_evidence_id = uuid4()
    expiring_assessment_id: UUID
    expiring_evidence_operation = uuid4()
    rule_id = uuid4()
    rule_operation = uuid4()
    operations = {
        invalid_evidence_operation,
        expiring_evidence_operation,
        rule_operation,
    }
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        with pytest.raises(DBAPIError) as storage_error, runtime_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=invalid_evidence_operation,
            )
            _insert_receipt(
                connection,
                ids,
                operation_id=invalid_evidence_operation,
                target_type="authority_evidence",
                target_id=invalid_evidence_id,
                command_type="family.authority.evidence.record",
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_evidence "
                    "(id,organization_id,family_id,evidence_kind,"
                    "source_label,storage_reference,media_type,byte_size,"
                    "content_sha256,recorded_by_user_id,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,'custody_document',"
                    "'Opaque storage gate',"
                    "'https://public.example/evidence','image/jpeg',1,:digest,"
                    ":recorded_by,:operation_id)"
                ),
                {
                    "id": invalid_evidence_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "digest": "a" * 64,
                    "recorded_by": ids["user"],
                    "operation_id": invalid_evidence_operation,
                },
            )
        assert (
            storage_error.value.orig.diag.constraint_name
            == "ck_authority_evidence_runtime_storage_reserved"
        )

        with runtime_engine.begin() as connection:
            expiring_assessment_id = _create_reviewed_evidence(
                connection,
                ids,
                evidence_id=expiring_evidence_id,
                operation_id=expiring_evidence_operation,
                expires_at_sql="clock_timestamp() + interval '1500 milliseconds'",
            )

        with pytest.raises(DBAPIError) as expiry_error, admin_engine.begin() as connection:
            _set_context(
                connection,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=rule_operation,
            )
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            _insert_release_rule(
                connection,
                ids,
                rule_id=rule_id,
                evidence_id=expiring_evidence_id,
                evidence_assessment_id=expiring_assessment_id,
                operation_id=rule_operation,
                effective_from="2035-01-01 00:00:00+00",
                effective_until="2036-01-01 00:00:00+00",
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
                    "operation_id": rule_operation,
                },
            )
            connection.execute(text("SELECT pg_sleep(1.7)"))
        assert "release rule evidence is not reviewed" in str(expiry_error.value)

        with admin_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM child_release_rules "
                        "WHERE organization_id=:organization_id AND id=:id"
                    ),
                    {"organization_id": ids["organization"], "id": rule_id},
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM child_authority_heads "
                        "WHERE organization_id=:organization_id AND child_id=:child_id"
                    ),
                    {
                        "organization_id": ids["organization"],
                        "child_id": ids["child"],
                    },
                )
                == 0
            )
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


def test_single_replace_receipt_cannot_transition_person_or_open_versions_twice() -> None:
    """One exact receipt represents one aggregate transition, not a reusable capability."""

    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE))
    operations: set[UUID] = set()
    person_id = uuid4()
    first_version_id = uuid4()
    second_version_id = uuid4()
    third_version_id = uuid4()
    create_operation = uuid4()
    replace_operation = uuid4()
    operations.update({create_operation, replace_operation})
    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        with runtime_engine.begin() as connection:
            _create_authority_person(
                connection,
                ids,
                person_id=person_id,
                version_id=first_version_id,
                operation_id=create_operation,
            )

        # A malicious direct-SQL caller fully closes each intermediate version,
        # so the final deferred cardinality invariant alone cannot distinguish
        # this two-step replay from one legitimate replacement.
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _replace_authority_person(
                connection,
                ids,
                person_id=person_id,
                old_version_id=first_version_id,
                new_version_id=second_version_id,
                operation_id=replace_operation,
            )
            connection.execute(
                text(
                    "UPDATE family_authority_person_versions SET "
                    "closed_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
                    "closed_operation_id=:operation_id WHERE id=:id"
                ),
                {"operation_id": replace_operation, "id": second_version_id},
            )
            connection.execute(
                text(
                    "INSERT INTO family_authority_person_versions "
                    "(id,organization_id,family_id,person_id,version_number,first_name,"
                    "last_name,relationship_kind,created_operation_id) VALUES "
                    "(:id,:organization_id,:family_id,:person_id,3,'Illicit second',"
                    "'Replacement','parent',:operation_id)"
                ),
                {
                    "id": third_version_id,
                    "organization_id": ids["organization"],
                    "family_id": ids["family_a"],
                    "person_id": person_id,
                    "operation_id": replace_operation,
                },
            )
            connection.execute(
                text(
                    "UPDATE family_authority_people SET version=3,"
                    "current_person_version_id=:version_id,last_operation_id=:operation_id "
                    "WHERE id=:person_id"
                ),
                {
                    "version_id": third_version_id,
                    "operation_id": replace_operation,
                    "person_id": person_id,
                },
            )

        with admin_engine.connect() as connection:
            person = connection.execute(
                text(
                    "SELECT version,status,current_person_version_id,last_operation_id "
                    "FROM family_authority_people WHERE id=:id"
                ),
                {"id": person_id},
            ).one()
            versions = connection.execute(
                text(
                    "SELECT id,version_number,closed_at FROM "
                    "family_authority_person_versions WHERE person_id=:person_id "
                    "ORDER BY version_number"
                ),
                {"person_id": person_id},
            ).all()
        assert tuple(person) == (
            1,
            "active",
            first_version_id,
            create_operation,
        )
        assert [(row.id, row.version_number, row.closed_at) for row in versions] == [
            (first_version_id, 1, None)
        ]
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()


@pytest.mark.parametrize("person_transition", ["replace", "retire"])
@pytest.mark.parametrize("record_kind", ["authorization", "rule", "consent"])
def _future_person_transition_serializes_with_new_person_references(
    person_transition: str,
    record_kind: str,
) -> None:
    """A commit may never leave a live row pointing at retired/stale person facts."""

    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url(RUNTIME_ROLE), pool_size=4)
    operations: set[UUID] = set()
    person_id = uuid4()
    first_version_id = uuid4()
    second_version_id = uuid4()
    evidence_id = uuid4()
    evidence_assessment_id: UUID
    policy_id = uuid4() if record_kind == "consent" else None
    record_id = uuid4()
    create_person_operation = uuid4()
    evidence_operation = uuid4()
    policy_operation = uuid4() if policy_id is not None else None
    transition_operation = uuid4()
    record_operation = uuid4()
    operations.update(
        {
            create_person_operation,
            evidence_operation,
            transition_operation,
            record_operation,
        }
    )
    if policy_operation is not None:
        operations.add(policy_operation)

    transition_ready = Event()
    record_attempt_started = Event()
    record_insert_finished = Event()
    transition_committed = Event()

    with admin_engine.begin() as connection:
        ids = _seed_base(connection)

    try:
        with runtime_engine.begin() as connection:
            _create_authority_person(
                connection,
                ids,
                person_id=person_id,
                version_id=first_version_id,
                operation_id=create_person_operation,
            )
        with runtime_engine.begin() as connection:
            evidence_assessment_id = _create_reviewed_evidence(
                connection,
                ids,
                evidence_id=evidence_id,
                operation_id=evidence_operation,
            )
        if policy_id is not None and policy_operation is not None:
            with admin_engine.begin() as connection:
                _publish_consent_policy(
                    connection,
                    ids,
                    policy_id=policy_id,
                    operation_id=policy_operation,
                )

        def attempt_person_transition() -> bool:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(
                        connection,
                        organization_id=ids["organization"],
                        user_id=ids["user"],
                        operation_id=transition_operation,
                    )
                    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                    _insert_receipt(
                        connection,
                        ids,
                        operation_id=transition_operation,
                        target_type="authority_person",
                        target_id=person_id,
                        command_type=(
                            "family.authority.person.replace"
                            if person_transition == "replace"
                            else "family.authority.person.retire"
                        ),
                        committed_version=2,
                    )
                    connection.execute(
                        text(
                            "UPDATE family_authority_person_versions SET "
                            "closed_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
                            "closed_operation_id=:operation_id WHERE id=:id"
                        ),
                        {
                            "operation_id": transition_operation,
                            "id": first_version_id,
                        },
                    )
                    if person_transition == "replace":
                        connection.execute(
                            text(
                                "INSERT INTO family_authority_person_versions "
                                "(id,organization_id,family_id,person_id,version_number,"
                                "first_name,last_name,relationship_kind,"
                                "created_operation_id) VALUES "
                                "(:id,:organization_id,:family_id,:person_id,2,"
                                "'Replacement','Person','parent',:operation_id)"
                            ),
                            {
                                "id": second_version_id,
                                "organization_id": ids["organization"],
                                "family_id": ids["family_a"],
                                "person_id": person_id,
                                "operation_id": transition_operation,
                            },
                        )
                        connection.execute(
                            text(
                                "UPDATE family_authority_people SET version=2,"
                                "current_person_version_id=:version_id,"
                                "last_operation_id=:operation_id WHERE id=:person_id"
                            ),
                            {
                                "version_id": second_version_id,
                                "operation_id": transition_operation,
                                "person_id": person_id,
                            },
                        )
                    else:
                        connection.execute(
                            text(
                                "UPDATE family_authority_people SET version=2,"
                                "status='retired',current_person_version_id=NULL,"
                                "retired_at=TIMESTAMPTZ '2000-01-01 00:00:00+00',"
                                "retired_operation_id=:operation_id,"
                                "last_operation_id=:operation_id WHERE id=:person_id"
                            ),
                            {
                                "operation_id": transition_operation,
                                "person_id": person_id,
                            },
                        )

                    transition_ready.set()
                    assert record_attempt_started.wait(timeout=10)
                    # A hardened reference insert may block behind this person
                    # transition. A vulnerable insert completes immediately; in
                    # that case keep it uncommitted until this transition wins.
                    record_insert_finished.wait(timeout=0.75)
                return True
            except DBAPIError:
                return False
            finally:
                transition_ready.set()
                transition_committed.set()

        def attempt_person_reference() -> bool:
            try:
                assert transition_ready.wait(timeout=10)
                with runtime_engine.begin() as connection:
                    _set_context(
                        connection,
                        organization_id=ids["organization"],
                        user_id=ids["user"],
                        operation_id=record_operation,
                    )
                    connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                    record_attempt_started.set()
                    _insert_person_referencing_child_record(
                        connection,
                        ids,
                        record_kind=record_kind,
                        record_id=record_id,
                        person_id=person_id,
                        person_version_id=first_version_id,
                        evidence_id=evidence_id,
                        evidence_assessment_id=evidence_assessment_id,
                        policy_id=policy_id,
                        operation_id=record_operation,
                    )
                    record_insert_finished.set()
                    assert transition_committed.wait(timeout=10)
                return True
            except DBAPIError:
                return False
            finally:
                record_attempt_started.set()
                record_insert_finished.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            transition_future = executor.submit(attempt_person_transition)
            record_future = executor.submit(attempt_person_reference)
            transition_succeeded = transition_future.result(timeout=20)
            record_succeeded = record_future.result(timeout=20)

        assert int(transition_succeeded) + int(record_succeeded) == 1, (
            "person transition and person-reference creation must have exactly one "
            f"serial winner: transition={person_transition!r}, record={record_kind!r}, "
            f"results={(transition_succeeded, record_succeeded)!r}"
        )

        record_table = {
            "authorization": "child_release_authorizations",
            "rule": "child_release_rules",
            "consent": "child_consent_decisions",
        }[record_kind]
        version_column = {
            "authorization": "grantor_person_version_id",
            "rule": "directing_person_version_id",
            "consent": "signer_person_version_id",
        }[record_kind]
        with admin_engine.connect() as connection:
            person = connection.execute(
                text(
                    "SELECT status,current_person_version_id FROM "
                    "family_authority_people WHERE id=:person_id"
                ),
                {"person_id": person_id},
            ).one()
            record = connection.execute(
                text(
                    f'SELECT "{version_column}" AS referenced_version '
                    f'FROM public."{record_table}" WHERE id=:record_id'
                ),
                {"record_id": record_id},
            ).one_or_none()
            head_count = connection.scalar(
                text(
                    "SELECT count(*) FROM child_authority_heads "
                    "WHERE child_id=:child_id"
                ),
                {"child_id": ids["child"]},
            )

        assert (record is not None) is record_succeeded
        assert bool(head_count) is record_succeeded
        if record is not None:
            assert person.status == "active"
            assert record.referenced_version == person.current_person_version_id
    finally:
        runtime_engine.dispose()
        _cleanup(admin_engine, ids, operations)
        admin_engine.dispose()
