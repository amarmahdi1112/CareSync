"""Opt-in PostgreSQL proofs for the first admin-only 0029A API slice.

The suite never provisions, migrates, truncates, or drops a database.  It runs
only against an explicitly selected disposable loopback cluster, rejects every
retained CareSync port, and isolates each scenario in newly registered tenants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Barrier, Event, Thread
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from app.basic.security import hash_password
from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
CURRENT_REVISION = "0029A1_family_evidence_vault"
RUNTIME_ROLE = "caresync_basic_app"
PASSWORD = "correct-password-123"

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}, (
        "Remote PostgreSQL is forbidden"
    )
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    assert 1 <= port <= 65535
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
        jwt_secret="postgres-family-authority-api-secret-32-bytes",
    )


@dataclass(frozen=True)
class PostgresHarness:
    admin: Engine
    application: object
    client: TestClient


@pytest.fixture
def postgres_harness() -> PostgresHarness:
    admin = create_engine(_url("postgres"))
    with admin.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == CURRENT_REVISION
        )

    application = create_app(_settings())
    with TestClient(application, raise_server_exceptions=False) as client:
        with application.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == RUNTIME_ROLE
        yield PostgresHarness(admin=admin, application=application, client=client)
    admin.dispose()


def _new_client(application) -> TestClient:
    """Use a separate runtime-role pool for a real concurrent request."""

    return TestClient(application, raise_server_exceptions=False)


def _register(client: TestClient, label: str = "Authority") -> tuple[dict, dict[str, str]]:
    identifier = uuid4().hex
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"authority-pg-{label.lower()}-{identifier}@example.test",
            "password": PASSWORD,
            "first_name": label,
            "last_name": "Owner",
            "organization_name": f"Authority PG {label} {identifier}",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _post(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
    expected_status: int,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == expected_status, response.text
    return response.json()


def _family(
    client: TestClient,
    headers: dict[str, str],
    *,
    label: str = "Authority Family",
    with_sources: bool = False,
) -> dict:
    payload = {
        "client_operation_id": str(uuid4()),
        "name": f"{label} {uuid4().hex}",
    }
    if with_sources:
        payload.update(
            {
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Guardian",
                    "relationship": "Parent",
                    "cell_phone": "780-555-0100",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Emergency",
                        "last_name": "Contact",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0101",
                    }
                ],
            }
        )
    return _post(client, "/api/v1/families", headers, payload, 201)


def _child(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    first_name: str,
) -> dict:
    return _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family_id,
            "first_name": first_name,
            "last_name": "Child",
            "date_of_birth": "2024-01-01",
        },
        201,
    )


def _person_payload(
    *,
    operation_id: UUID | None = None,
    source: dict | None = None,
    first_name: str = "Trusted",
) -> dict:
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "source": source or {"kind": "manual"},
        "facts": {
            "first_name": first_name,
            "last_name": "Recipient",
            "relationship_kind": "family_friend",
            "email": f"{first_name.lower()}.{uuid4().hex}@example.test",
            "primary_phone": "780-555-0112",
        },
    }


def _replacement_facts() -> dict:
    return {
        "first_name": "Replacement",
        "middle_name": "Postgres",
        "last_name": "Authority",
        "preferred_name": "Rex",
        "relationship_kind": "other",
        "relationship_detail": "Court-approved family support",
        "email": "replacement.postgres@example.test",
        "primary_phone": "780-555-0199",
    }


def _replace_payload(
    *, operation_id: UUID | None = None, expected_version: int = 1
) -> dict:
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "expected_version": expected_version,
        "facts": _replacement_facts(),
    }


def _retire_payload(
    *, operation_id: UUID | None = None, expected_version: int = 1
) -> dict:
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "expected_version": expected_version,
    }


def _create_person(
    client: TestClient,
    headers: dict[str, str],
    family_id: UUID,
) -> dict:
    response = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=headers,
        json=_person_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()["resource"]


def _set_authority_context(
    connection,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
) -> None:
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": str(organization_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": str(actor_user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_childcare_operation_id',:value,true)"),
        {"value": str(operation_id)},
    )


def _seed_live_authorization_dependency(
    admin: Engine,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    family_id: UUID,
    child_id: UUID,
    person: dict,
) -> dict[str, UUID]:
    ids = {
        "evidence": uuid4(),
        "evidence_operation": uuid4(),
        "evidence_assessment": uuid4(),
        "evidence_review_operation": uuid4(),
        "evidence_reviewer": uuid4(),
        "authorization": uuid4(),
        "authorization_operation": uuid4(),
    }
    person_id = UUID(person["id"])
    person_version_id = UUID(person["current_version"]["id"])
    with admin.begin() as connection:
        reviewer_role_id = connection.scalar(
            text(
                "SELECT id FROM roles WHERE organization_id=:organization_id "
                "AND key='administrator'"
            ),
            {"organization_id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                "VALUES (:id,:email,:password_hash,'Evidence','Reviewer',true,1)"
            ),
            {
                "id": ids["evidence_reviewer"],
                "email": f"evidence-reviewer-{uuid4().hex}@example.test",
                "password_hash": hash_password("reviewer-correct-password-123"),
            },
        )
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id,organization_id,user_id,role_id,status) VALUES "
                "(:id,:organization_id,:user_id,:role_id,'active')"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "user_id": ids["evidence_reviewer"],
                "role_id": reviewer_role_id,
            },
        )
        _set_authority_context(
            connection,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            operation_id=ids["evidence_operation"],
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_receipts "
                "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                "request_hash,actor_user_id,committed_version,outcome) VALUES "
                "(:id,:organization_id,:operation_id,'family.authority.evidence.record',"
                "'authority_evidence',:target_id,:request_hash,:actor_user_id,1,"
                "jsonb_build_object('action_route',CAST(:action_route AS text)))"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "operation_id": ids["evidence_operation"],
                "target_id": ids["evidence"],
                "request_hash": uuid4().hex * 2,
                "actor_user_id": actor_user_id,
                "action_route": (
                    f"/families/{family_id}?authority_evidence_id={ids['evidence']}"
                ),
            },
        )
        _set_authority_context(
            connection,
            organization_id=organization_id,
            actor_user_id=ids["evidence_reviewer"],
            operation_id=ids["evidence_review_operation"],
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_receipts "
                "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                "request_hash,actor_user_id,committed_version,outcome) VALUES "
                "(:id,:organization_id,:operation_id,'family.authority.evidence.review',"
                "'authority_evidence',:target_id,:request_hash,:actor_user_id,2,"
                "jsonb_build_object('action_route',CAST(:action_route AS text)))"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "operation_id": ids["evidence_review_operation"],
                "target_id": ids["evidence"],
                "request_hash": uuid4().hex * 2,
                "actor_user_id": ids["evidence_reviewer"],
                "action_route": (
                    f"/families/{family_id}?authority_evidence_id={ids['evidence']}"
                ),
            },
        )
        _set_authority_context(
            connection,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            operation_id=ids["evidence_operation"],
        )
        connection.execute(
            text(
                "INSERT INTO family_authority_evidence "
                "(id,organization_id,family_id,evidence_kind,source_label,"
                "recorded_by_user_id,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,'guardian_attestation',"
                "'PostgreSQL lifecycle evidence',:actor_user_id,:operation_id)"
            ),
            {
                "id": ids["evidence"],
                "organization_id": organization_id,
                "family_id": family_id,
                "actor_user_id": actor_user_id,
                "operation_id": ids["evidence_operation"],
            },
        )
        _set_authority_context(
            connection,
            organization_id=organization_id,
            actor_user_id=ids["evidence_reviewer"],
            operation_id=ids["evidence_review_operation"],
        )
        connection.execute(
            text(
                "INSERT INTO family_authority_evidence_assessments "
                "(id,organization_id,family_id,evidence_id,version_number,decision,"
                "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed',"
                "'reported',:actor_user_id,:operation_id)"
            ),
            {
                "id": ids["evidence_assessment"],
                "organization_id": organization_id,
                "family_id": family_id,
                "evidence_id": ids["evidence"],
                "actor_user_id": ids["evidence_reviewer"],
                "operation_id": ids["evidence_review_operation"],
            },
        )
    with admin.begin() as connection:
        _set_authority_context(
            connection,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            operation_id=ids["authorization_operation"],
        )
        connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        connection.execute(
            text(
                "INSERT INTO childcare_command_receipts "
                "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                "request_hash,actor_user_id,committed_version,outcome) VALUES "
                "(:id,:organization_id,:operation_id,'child.release.authorization.grant',"
                "'release_authorization',:target_id,:request_hash,:actor_user_id,1,"
                "jsonb_build_object('action_route',CAST(:action_route AS text)))"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "operation_id": ids["authorization_operation"],
                "target_id": ids["authorization"],
                "request_hash": uuid4().hex * 2,
                "actor_user_id": actor_user_id,
                "action_route": (
                    f"/children/{child_id}?release_authorization_id="
                    f"{ids['authorization']}"
                ),
            },
        )
        connection.execute(
            text(
                "INSERT INTO child_release_authorizations "
                "(id,organization_id,family_id,child_id,recipient_person_id,"
                "verification_policy_code,grantor_person_id,grantor_person_version_id,"
                "grantor_authority_basis,basis_evidence_id,basis_evidence_assessment_id,"
                "effective_from,effective_until,"
                "version,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:child_id,:person_id,"
                "'government_photo_id',:person_id,:person_version_id,'guardian_record',"
                ":evidence_id,:evidence_assessment_id,"
                "TIMESTAMPTZ '2026-01-01 00:00:00+00',"
                "TIMESTAMPTZ '2099-01-01 00:00:00+00',1,:operation_id)"
            ),
            {
                "id": ids["authorization"],
                "organization_id": organization_id,
                "family_id": family_id,
                "child_id": child_id,
                "person_id": person_id,
                "person_version_id": person_version_id,
                "evidence_id": ids["evidence"],
                "evidence_assessment_id": ids["evidence_assessment"],
                "operation_id": ids["authorization_operation"],
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
                "organization_id": organization_id,
                "family_id": family_id,
                "child_id": child_id,
                "operation_id": ids["authorization_operation"],
            },
        )
    return ids


def _role_headers(
    admin: Engine,
    client: TestClient,
    *,
    organization_id: UUID,
    role_key: str,
) -> tuple[UUID, dict[str, str]]:
    user_id = uuid4()
    email = f"authority-pg-{role_key}-{uuid4().hex}@example.test"
    password = f"{role_key}-{PASSWORD}"
    with admin.begin() as connection:
        role_id = connection.execute(
            text(
                "SELECT id FROM roles WHERE organization_id=:organization_id "
                "AND key=:role_key"
            ),
            {"organization_id": organization_id, "role_key": role_key},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,first_name,last_name,is_active,auth_version,"
                "email_verified_at,email_verification_method) VALUES "
                "(:id,:email,:password_hash,:first_name,'Authority Tester',true,1,"
                "statement_timestamp(),'test_fixture')"
            ),
            {
                "id": user_id,
                "email": email,
                "password_hash": hash_password(password),
                "first_name": role_key.title(),
            },
        )
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id,organization_id,user_id,role_id,status) "
                "VALUES (:id,:organization_id,:user_id,:role_id,'active')"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "user_id": user_id,
                "role_id": role_id,
            },
        )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_runtime_api_person_create_is_receipt_first_and_exact_retry_is_exactly_once(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, headers = _register(client, "Exact")
    organization_id = UUID(auth["user"]["organization_id"])
    family = _family(client, headers)
    family_id = UUID(family["id"])
    operation_id = uuid4()
    payload = _person_payload(operation_id=operation_id)

    first = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 201, first.text
    created = first.json()
    assert created["replayed"] is False
    person_id = UUID(created["resource"]["id"])
    assert created["resource"]["family_id"] == str(family_id)
    assert created["resource"]["organization_id"] == str(organization_id)
    assert created["resource"]["current_version"]["version_number"] == 1
    assert created["receipt"]["client_operation_id"] == str(operation_id)
    assert created["receipt"]["command_type"] == "family.authority.person.create"
    assert created["receipt"]["target_type"] == "authority_person"
    assert created["receipt"]["target_id"] == str(person_id)
    assert created["receipt"]["committed_version"] == 1

    replay = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json() == {
        **created,
        "replayed": True,
    }

    with admin.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_people "
                " WHERE organization_id=:organization_id AND id=:person_id), "
                "(SELECT count(*) FROM family_authority_person_versions "
                " WHERE organization_id=:organization_id AND person_id=:person_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id "
                " AND action='family.authority.person.created' "
                " AND entity_type='authority_person' AND entity_id=:person_id), "
                "(SELECT count(*) FROM realtime_events "
                " WHERE organization_id=:organization_id "
                " AND event_type='family.authority.person.created' "
                " AND entity_type='authority_person' AND entity_id=:person_id)"
            ),
            {
                "organization_id": organization_id,
                "person_id": person_id,
                "operation_id": operation_id,
            },
        ).one()
        assert counts == (1, 1, 1, 1, 1)
        receipt_first_binding = connection.execute(
            text(
                "SELECT p.created_operation_id=v.created_operation_id, "
                "p.created_operation_id=r.client_operation_id, "
                "r.target_id=p.id, r.committed_version=p.version "
                "FROM family_authority_people p "
                "JOIN family_authority_person_versions v ON "
                "v.organization_id=p.organization_id AND v.person_id=p.id "
                "JOIN childcare_command_receipts r ON "
                "r.organization_id=p.organization_id "
                "AND r.client_operation_id=p.created_operation_id "
                "WHERE p.organization_id=:organization_id AND p.id=:person_id"
            ),
            {"organization_id": organization_id, "person_id": person_id},
        ).one()
        assert receipt_first_binding == (True, True, True, True)


def test_runtime_api_person_replace_and_retire_are_guarded_exactly_once(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, owner_headers = _register(client, "Lifecycle")
    organization_id = UUID(auth["user"]["organization_id"])
    actor_user_id = UUID(auth["user"]["id"])
    family = _family(client, owner_headers)
    family_id = UUID(family["id"])
    child = _child(client, owner_headers, family["id"], "Lifecycle")
    child_id = UUID(child["id"])
    person = _create_person(client, owner_headers, family_id)
    person_id = UUID(person["id"])
    first_version_id = UUID(person["current_version"]["id"])
    _, administrator_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )
    _seed_live_authorization_dependency(
        admin,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        family_id=family_id,
        child_id=child_id,
        person=person,
    )

    replace_operation = uuid4()
    replace_payload = _replace_payload(operation_id=replace_operation)
    replace_path = (
        f"/api/v1/families/{family_id}/authority/people/{person_id}/versions"
    )
    replaced_response = client.post(
        replace_path,
        headers=owner_headers,
        json=replace_payload,
    )
    assert replaced_response.status_code == 200, replaced_response.text
    replaced = replaced_response.json()
    assert replaced["replayed"] is False
    assert replaced["resource"]["version"] == 2
    assert replaced["resource"]["status"] == "active"
    assert replaced["resource"]["source"] == {"kind": "manual"}
    assert replaced["resource"]["current_version"]["facts"] == _replacement_facts()
    assert replaced["receipt"]["command_type"] == "family.authority.person.replace"
    assert replaced["receipt"]["committed_version"] == 2

    exact_replace_retry = client.post(
        replace_path,
        headers=owner_headers,
        json=replace_payload,
    )
    assert exact_replace_retry.status_code == 200, exact_replace_retry.text
    assert exact_replace_retry.json() == {**replaced, "replayed": True}

    mismatch_payload = _replace_payload(operation_id=replace_operation)
    mismatch_payload["facts"]["last_name"] = "Different"
    mismatch = client.post(
        replace_path,
        headers=owner_headers,
        json=mismatch_payload,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "operation_reused"
    actor_private = client.post(
        replace_path,
        headers=administrator_headers,
        json=replace_payload,
    )
    assert actor_private.status_code == 404
    assert actor_private.json()["detail"] == "Operation receipt not found"

    stale_operation = uuid4()
    stale = client.post(
        replace_path,
        headers=owner_headers,
        json=_replace_payload(operation_id=stale_operation, expected_version=1),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_childcare_resource"

    retire_operation = uuid4()
    retire_payload = _retire_payload(
        operation_id=retire_operation,
        expected_version=2,
    )
    retire_path = f"/api/v1/families/{family_id}/authority/people/{person_id}/retire"
    retired_response = client.post(
        retire_path,
        headers=owner_headers,
        json=retire_payload,
    )
    assert retired_response.status_code == 200, retired_response.text
    retired = retired_response.json()
    assert retired["replayed"] is False
    assert retired["resource"]["version"] == 3
    assert retired["resource"]["status"] == "retired"
    assert retired["resource"]["current_version"] is None
    assert retired["receipt"]["command_type"] == "family.authority.person.retire"
    assert retired["receipt"]["committed_version"] == 3

    exact_retire_retry = client.post(
        retire_path,
        headers=owner_headers,
        json=retire_payload,
    )
    assert exact_retire_retry.status_code == 200, exact_retire_retry.text
    assert exact_retire_retry.json() == {**retired, "replayed": True}
    historical_replace_retry = client.post(
        replace_path,
        headers=owner_headers,
        json=replace_payload,
    )
    assert historical_replace_retry.status_code == 200
    assert historical_replace_retry.json()["receipt"]["committed_version"] == 2
    assert historical_replace_retry.json()["resource"] == retired["resource"]

    terminal_operation = uuid4()
    terminal = client.post(
        retire_path,
        headers=owner_headers,
        json=_retire_payload(operation_id=terminal_operation, expected_version=3),
    )
    assert terminal.status_code == 409
    assert terminal.json()["detail"]["code"] == "authority_person_inactive"

    with admin.connect() as connection:
        aggregate = connection.execute(
            text(
                "SELECT version,status,current_person_version_id,retired_operation_id,"
                "last_operation_id,retired_at>=created_at "
                "FROM family_authority_people "
                "WHERE organization_id=:organization_id AND id=:person_id"
            ),
            {"organization_id": organization_id, "person_id": person_id},
        ).one()
        assert aggregate == (
            3,
            "retired",
            None,
            retire_operation,
            retire_operation,
            True,
        )
        versions = connection.execute(
            text(
                "SELECT id,version_number,closed_operation_id,closed_at>=created_at "
                "FROM family_authority_person_versions "
                "WHERE organization_id=:organization_id AND person_id=:person_id "
                "ORDER BY version_number"
            ),
            {"organization_id": organization_id, "person_id": person_id},
        ).all()
        assert versions == [
            (first_version_id, 1, replace_operation, True),
            (
                UUID(replaced["resource"]["current_version"]["id"]),
                2,
                retire_operation,
                True,
            ),
        ]
        assert connection.execute(
            text(
                "SELECT revision,last_operation_id FROM child_authority_heads "
                "WHERE organization_id=:organization_id AND child_id=:child_id"
            ),
            {"organization_id": organization_id, "child_id": child_id},
        ).one() == (3, retire_operation)
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:replace_operation,:retire_operation)), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:stale_operation,:terminal_operation)), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id AND entity_id=:person_id "
                " AND action='family.authority.person.replaced'), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id AND entity_id=:person_id "
                " AND action='family.authority.person.retired'), "
                "(SELECT count(*) FROM realtime_events "
                " WHERE organization_id=:organization_id AND entity_id=:person_id "
                " AND event_type='family.authority.person.replaced'), "
                "(SELECT count(*) FROM realtime_events "
                " WHERE organization_id=:organization_id AND entity_id=:person_id "
                " AND event_type='family.authority.person.retired')"
            ),
            {
                "organization_id": organization_id,
                "person_id": person_id,
                "replace_operation": replace_operation,
                "retire_operation": retire_operation,
                "stale_operation": stale_operation,
                "terminal_operation": terminal_operation,
            },
        ).one()
        assert counts == (2, 0, 1, 1, 1, 1)


def test_runtime_api_missing_authority_head_rolls_back_and_same_operation_can_retry(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, headers = _register(client, "MissingHead")
    organization_id = UUID(auth["user"]["organization_id"])
    actor_user_id = UUID(auth["user"]["id"])
    family = _family(client, headers)
    family_id = UUID(family["id"])
    child = _child(client, headers, family["id"], "MissingHead")
    child_id = UUID(child["id"])
    person = _create_person(client, headers, family_id)
    person_id = UUID(person["id"])
    dependency = _seed_live_authorization_dependency(
        admin,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        family_id=family_id,
        child_id=child_id,
        person=person,
    )
    with admin.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM child_authority_heads "
                "WHERE organization_id=:organization_id AND child_id=:child_id"
            ),
            {"organization_id": organization_id, "child_id": child_id},
        )

    replace_operation = uuid4()
    replace_payload = _replace_payload(operation_id=replace_operation)
    replace_path = (
        f"/api/v1/families/{family_id}/authority/people/{person_id}/versions"
    )
    missing_replace = client.post(
        replace_path,
        headers=headers,
        json=replace_payload,
    )
    assert missing_replace.status_code == 409
    assert missing_replace.json()["detail"] == {"code": "authority_head_missing"}
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT version FROM family_authority_people "
                " WHERE organization_id=:organization_id AND id=:person_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "person_id": person_id,
                "operation_id": replace_operation,
            },
        ).one() == (1, 0)

    with admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO child_authority_heads "
                "(organization_id,family_id,child_id,revision,created_operation_id,"
                "last_operation_id) VALUES "
                "(:organization_id,:family_id,:child_id,1,:operation_id,:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "family_id": family_id,
                "child_id": child_id,
                "operation_id": dependency["authorization_operation"],
            },
        )
    repaired_replace = client.post(
        replace_path,
        headers=headers,
        json=replace_payload,
    )
    assert repaired_replace.status_code == 200, repaired_replace.text
    assert repaired_replace.json()["replayed"] is False

    with admin.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM child_authority_heads "
                "WHERE organization_id=:organization_id AND child_id=:child_id"
            ),
            {"organization_id": organization_id, "child_id": child_id},
        )
    retire_operation = uuid4()
    retire_payload = _retire_payload(
        operation_id=retire_operation,
        expected_version=2,
    )
    retire_path = f"/api/v1/families/{family_id}/authority/people/{person_id}/retire"
    missing_retire = client.post(
        retire_path,
        headers=headers,
        json=retire_payload,
    )
    assert missing_retire.status_code == 409
    assert missing_retire.json()["detail"] == {"code": "authority_head_missing"}
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT version FROM family_authority_people "
                " WHERE organization_id=:organization_id AND id=:person_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "person_id": person_id,
                "operation_id": retire_operation,
            },
        ).one() == (2, 0)

    with admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO child_authority_heads "
                "(organization_id,family_id,child_id,revision,created_operation_id,"
                "last_operation_id) VALUES "
                "(:organization_id,:family_id,:child_id,2,:created_operation_id,"
                ":last_operation_id)"
            ),
            {
                "organization_id": organization_id,
                "family_id": family_id,
                "child_id": child_id,
                "created_operation_id": dependency["authorization_operation"],
                "last_operation_id": replace_operation,
            },
        )
    repaired_retire = client.post(
        retire_path,
        headers=headers,
        json=retire_payload,
    )
    assert repaired_retire.status_code == 200, repaired_retire.text
    assert repaired_retire.json()["replayed"] is False
    assert repaired_retire.json()["resource"]["status"] == "retired"
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT revision FROM child_authority_heads "
                " WHERE organization_id=:organization_id AND child_id=:child_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:replace_operation,:retire_operation)), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id AND entity_id=:person_id "
                " AND action IN ('family.authority.person.replaced',"
                "'family.authority.person.retired'))"
            ),
            {
                "organization_id": organization_id,
                "child_id": child_id,
                "person_id": person_id,
                "replace_operation": replace_operation,
                "retire_operation": retire_operation,
            },
        ).one() == (3, 2, 2)


def test_workspace_projection_requires_a2_activation(
    postgres_harness: PostgresHarness,
) -> None:
    _, client = postgres_harness.admin, postgres_harness.client
    _, headers = _register(client, "WorkspaceActivation")
    family_id = UUID(_family(client, headers)["id"])

    response = client.get(
        f"/api/v1/families/{family_id}/authority",
        headers=headers,
    )

    assert response.status_code == 503, response.text
    assert response.json() == {
        "detail": {"code": "family_authority_activation_unavailable"}
    }


def _assert_workspace_projection_writes_nothing_and_authority_is_role_and_tenant_private(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    first_auth, first_headers = _register(client, "PrivateFirst")
    organization_id = UUID(first_auth["user"]["organization_id"])
    family = _family(client, first_headers)
    family_id = UUID(family["id"])
    children = [
        _child(client, first_headers, family["id"], "One"),
        _child(client, first_headers, family["id"], "Two"),
    ]
    _, educator_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="educator",
    )
    _, second_headers = _register(client, "PrivateSecond")

    count_sql = text(
        "SELECT "
        "(SELECT count(*) FROM child_authority_heads "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM family_authority_people "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM family_authority_evidence "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM child_release_authorizations "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM child_release_rules "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM child_consent_decisions "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM attendance_release_snapshots "
        " WHERE organization_id=:organization_id AND family_id=:family_id), "
        "(SELECT count(*) FROM childcare_command_receipts "
        " WHERE organization_id=:organization_id), "
        "(SELECT count(*) FROM audit_events WHERE organization_id=:organization_id), "
        "(SELECT count(*) FROM realtime_events WHERE organization_id=:organization_id)"
    )
    params = {"organization_id": organization_id, "family_id": family_id}
    with admin.connect() as connection:
        before = connection.execute(count_sql, params).one()
    assert before[:7] == (0, 0, 0, 0, 0, 0, 0)

    response = client.get(
        f"/api/v1/families/{family_id}/authority",
        headers=first_headers,
    )
    assert response.status_code == 200, response.text
    workspace = response.json()
    assert workspace["organization_id"] == str(organization_id)
    assert workspace["family_id"] == str(family_id)
    assert workspace["people"] == []
    assert workspace["evidence"] == []
    assert {row["child_id"] for row in workspace["children"]} == {
        child["id"] for child in children
    }
    assert all(
        not row["reviewed"]
        and row["authority_revision"] == 0
        and row["release_authorizations"] == []
        and row["release_rules"] == []
        and row["consent_decisions"] == []
        for row in workspace["children"]
    )
    assert response.headers["cache-control"] == "private, no-store"

    with admin.connect() as connection:
        after = connection.execute(count_sql, params).one()
    assert after == before

    educator_read = client.get(
        f"/api/v1/families/{family_id}/authority",
        headers=educator_headers,
    )
    assert educator_read.status_code == 403
    educator_write = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=educator_headers,
        json=_person_payload(),
    )
    assert educator_write.status_code == 403

    tenant_read = client.get(
        f"/api/v1/families/{family_id}/authority",
        headers=second_headers,
    )
    assert tenant_read.status_code == 404
    tenant_write = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=second_headers,
        json=_person_payload(),
    )
    assert tenant_write.status_code == 404


def test_exact_retry_is_actor_private_within_one_tenant(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, owner_headers = _register(client, "ActorPrivate")
    organization_id = UUID(auth["user"]["organization_id"])
    family = _family(client, owner_headers)
    family_id = UUID(family["id"])
    _, administrator_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )
    operation_id = uuid4()
    payload = _person_payload(operation_id=operation_id)

    created = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=owner_headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    private_replay = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=administrator_headers,
        json=payload,
    )
    assert private_replay.status_code == 404, private_replay.text
    assert private_replay.json()["detail"] == "Operation receipt not found"

    person_id = UUID(created.json()["resource"]["id"])
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_people "
                " WHERE organization_id=:organization_id AND id=:person_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id "
                " AND action='family.authority.person.created' AND entity_id=:person_id)"
            ),
            {
                "organization_id": organization_id,
                "person_id": person_id,
                "operation_id": operation_id,
            },
        ).one() == (1, 1, 1)


def test_guardian_source_is_unique_under_concurrent_runtime_api_creates(
    postgres_harness: PostgresHarness,
) -> None:
    admin, first_client = postgres_harness.admin, postgres_harness.client
    auth, headers = _register(first_client, "SourceRace")
    organization_id = UUID(auth["user"]["organization_id"])
    family = _family(first_client, headers, with_sources=True)
    family_id = UUID(family["id"])
    with admin.connect() as connection:
        guardian_id = connection.execute(
            text(
                "SELECT id FROM guardians WHERE organization_id=:organization_id "
                "AND family_id=:family_id AND is_primary=true AND retired_at IS NULL"
            ),
            {"organization_id": organization_id, "family_id": family_id},
        ).scalar_one()

    first_operation = uuid4()
    second_operation = uuid4()
    payloads = (
        _person_payload(
            operation_id=first_operation,
            source={"kind": "guardian", "guardian_id": str(guardian_id)},
            first_name="First",
        ),
        _person_payload(
            operation_id=second_operation,
            source={"kind": "guardian", "guardian_id": str(guardian_id)},
            first_name="Second",
        ),
    )
    second_application = create_app(_settings())
    barrier = Barrier(3)
    responses = []
    failures = []

    with _new_client(second_application) as second_client:

        def create(client: TestClient, payload: dict) -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    client.post(
                        f"/api/v1/families/{family_id}/authority/people",
                        headers=headers,
                        json=payload,
                    )
                )
            except Exception as error:  # pragma: no cover - diagnostic capture
                failures.append(error)

        threads = [
            Thread(target=create, args=(first_client, payloads[0]), daemon=True),
            Thread(target=create, args=(second_client, payloads[1]), daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()

    assert not failures
    assert sorted(response.status_code for response in responses) == [201, 409]
    rejected = next(response for response in responses if response.status_code == 409)
    assert rejected.json()["detail"]["code"] == "authority_source_already_linked"

    with admin.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_people "
                " WHERE organization_id=:organization_id AND family_id=:family_id "
                " AND source_guardian_id=:guardian_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:first_operation,:second_operation)), "
                "(SELECT count(*) FROM audit_events "
                " WHERE organization_id=:organization_id "
                " AND action='family.authority.person.created' "
                " AND entity_type='authority_person')"
            ),
            {
                "organization_id": organization_id,
                "family_id": family_id,
                "guardian_id": guardian_id,
                "first_operation": first_operation,
                "second_operation": second_operation,
            },
        ).one()
    assert counts == (1, 1, 1)


def _record_evidence(
    client: TestClient,
    headers: dict[str, str],
    family_id: UUID,
    *,
    operation_id: UUID | None = None,
    expires_at: str | None = "2099-01-01T00:00:00Z",
    source_label: str = "PostgreSQL observed evidence",
):
    payload = {
        "client_operation_id": str(operation_id or uuid4()),
        "evidence_kind": "guardian_attestation",
        "source_label": source_label,
        "issued_at": "2026-01-01T00:00:00Z",
        "captured_at": "2026-07-17T00:00:00Z",
        "expires_at": expires_at,
    }
    response = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response, payload


def _review_evidence(
    client: TestClient,
    headers: dict[str, str],
    family_id: UUID,
    evidence_id: UUID,
    *,
    operation_id: UUID | None = None,
):
    payload = {
        "client_operation_id": str(operation_id or uuid4()),
        "expected_version": 1,
        "assessed_epistemic_status": "reported",
    }
    response = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{evidence_id}/review",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response, payload


def _assert_workspace_and_exact_replays_share_the_family_command_boundary(
    postgres_harness: PostgresHarness,
) -> None:
    """A projection cannot straddle a concurrent person/evidence transition."""

    admin, application, client = (
        postgres_harness.admin,
        postgres_harness.application,
        postgres_harness.client,
    )
    auth, headers = _register(client, "ProjectionLock")
    organization_id = UUID(auth["user"]["organization_id"])
    family_id = UUID(_family(client, headers)["id"])

    person_payload = _person_payload(operation_id=uuid4())
    person_path = f"/api/v1/families/{family_id}/authority/people"
    created_person = client.post(person_path, headers=headers, json=person_payload)
    assert created_person.status_code == 201, created_person.text

    recorded_evidence, evidence_payload = _record_evidence(
        client,
        headers,
        family_id,
        operation_id=uuid4(),
        source_label="Projection lock evidence",
    )
    evidence_id = recorded_evidence.json()["resource"]["id"]

    with _new_client(application) as concurrent_client:

        def request_while_family_is_write_locked(
            path: str,
            *,
            payload: dict | None = None,
        ):
            started = Event()
            responses = []

            def issue_request() -> None:
                started.set()
                if payload is None:
                    responses.append(concurrent_client.get(path, headers=headers))
                else:
                    responses.append(
                        concurrent_client.post(path, headers=headers, json=payload)
                    )

            with admin.begin() as locker:
                assert locker.execute(
                    text(
                        "SELECT id FROM families "
                        "WHERE organization_id=:organization_id AND id=:family_id "
                        "FOR UPDATE"
                    ),
                    {
                        "organization_id": organization_id,
                        "family_id": family_id,
                    },
                ).scalar_one() == family_id
                thread = Thread(target=issue_request, daemon=True)
                thread.start()
                assert started.wait(timeout=5)
                thread.join(timeout=0.5)
                assert thread.is_alive(), (
                    "family-authority projection bypassed the family command lock"
                )

            thread.join(timeout=15)
            assert not thread.is_alive()
            assert len(responses) == 1
            return responses[0]

        workspace = request_while_family_is_write_locked(
            f"/api/v1/families/{family_id}/authority"
        )
        person_replay = request_while_family_is_write_locked(
            person_path,
            payload=person_payload,
        )
        evidence_replay = request_while_family_is_write_locked(
            f"/api/v1/families/{family_id}/authority/evidence",
            payload=evidence_payload,
        )

    assert workspace.status_code == 200, workspace.text
    assert len(workspace.json()["people"]) == 1
    assert [value["id"] for value in workspace.json()["evidence"]] == [evidence_id]
    assert person_replay.status_code == 201, person_replay.text
    assert person_replay.json()["replayed"] is True
    assert evidence_replay.status_code == 201, evidence_replay.text
    assert evidence_replay.json()["replayed"] is True


def test_postgres_evidence_exact_retry_provenance_and_expiry_are_fail_closed(
    postgres_harness: PostgresHarness,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, headers = _register(client, "EvidenceExact")
    organization_id = UUID(auth["user"]["organization_id"])
    family_id = UUID(_family(client, headers)["id"])
    _, reviewer_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )

    recorded_response, record_payload = _record_evidence(client, headers, family_id)
    recorded = recorded_response.json()
    evidence_id = UUID(recorded["resource"]["id"])
    reviewed_response, review_payload = _review_evidence(
        client, reviewer_headers, family_id, evidence_id
    )
    reviewed = reviewed_response.json()
    assessment_id = UUID(reviewed["resource"]["current_assessment"]["id"])
    assert reviewed["receipt"]["command_type"] == "family.authority.evidence.review"
    assert reviewed["receipt"]["committed_version"] == 2

    historical = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=headers,
        json=record_payload,
    )
    assert historical.status_code == 201, historical.text
    assert historical.json()["replayed"] is True
    assert historical.json()["receipt"] == recorded["receipt"]
    assert historical.json()["resource"]["version"] == 2

    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT created_operation_id FROM family_authority_evidence "
                " WHERE organization_id=:organization_id AND id=:evidence_id), "
                "(SELECT created_operation_id FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND id=:assessment_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:record_operation,:review_operation))"
            ),
            {
                "organization_id": organization_id,
                "evidence_id": evidence_id,
                "assessment_id": assessment_id,
                "record_operation": UUID(record_payload["client_operation_id"]),
                "review_operation": UUID(review_payload["client_operation_id"]),
            },
        ).one() == (
            UUID(record_payload["client_operation_id"]),
            UUID(review_payload["client_operation_id"]),
            2,
        )

    expired_response, _ = _record_evidence(
        client,
        headers,
        family_id,
        expires_at="2026-02-01T00:00:00Z",
        source_label="Expired PostgreSQL evidence",
    )
    expired_id = UUID(expired_response.json()["resource"]["id"])
    failed_operation = uuid4()
    failed = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{expired_id}/review",
        headers=reviewer_headers,
        json={
            "client_operation_id": str(failed_operation),
            "expected_version": 1,
            "assessed_epistemic_status": "reported",
        },
    )
    assert failed.status_code == 409, failed.text
    assert failed.json()["detail"]["code"] == "authority_evidence_expired"
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND evidence_id=:evidence_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "evidence_id": expired_id,
                "operation_id": failed_operation,
            },
        ).one() == (0, 0)


def test_postgres_concurrent_review_and_reject_have_one_typed_winner(
    postgres_harness: PostgresHarness,
) -> None:
    admin, application, client = (
        postgres_harness.admin,
        postgres_harness.application,
        postgres_harness.client,
    )
    auth, headers = _register(client, "EvidenceRace")
    organization_id = UUID(auth["user"]["organization_id"])
    family_id = UUID(_family(client, headers)["id"])
    _, reviewer_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )
    recorded, _ = _record_evidence(client, headers, family_id)
    evidence_id = UUID(recorded.json()["resource"]["id"])
    review_operation, reject_operation = uuid4(), uuid4()
    barrier = Barrier(2)
    responses: list = []
    failures: list[BaseException] = []

    def attempt(path_suffix: str, payload: dict) -> None:
        try:
            with _new_client(application) as concurrent_client:
                barrier.wait(timeout=10)
                responses.append(
                    concurrent_client.post(
                        f"/api/v1/families/{family_id}/authority/evidence/"
                        f"{evidence_id}/{path_suffix}",
                        headers=reviewer_headers,
                        json=payload,
                    )
                )
        except BaseException as error:  # pragma: no cover - assertion reports details
            failures.append(error)

    threads = [
        Thread(
            target=attempt,
            args=(
                "review",
                {
                    "client_operation_id": str(review_operation),
                    "expected_version": 1,
                    "assessed_epistemic_status": "reported",
                },
            ),
        ),
        Thread(
            target=attempt,
            args=(
                "reject",
                {
                    "client_operation_id": str(reject_operation),
                    "expected_version": 1,
                    "reason_code": "insufficient_evidence",
                },
            ),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not failures
    assert sorted(response.status_code for response in responses) == [200, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["detail"]["code"] in {
        "stale_childcare_resource",
        "authority_evidence_state_changed",
    }
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND evidence_id=:evidence_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN (:review_operation,:reject_operation))"
            ),
            {
                "organization_id": organization_id,
                "evidence_id": evidence_id,
                "review_operation": review_operation,
                "reject_operation": reject_operation,
            },
        ).one() == (1, 1)


def test_postgres_concurrent_invalidate_and_supersede_have_one_typed_winner(
    postgres_harness: PostgresHarness,
) -> None:
    admin, application, client = (
        postgres_harness.admin,
        postgres_harness.application,
        postgres_harness.client,
    )
    auth, headers = _register(client, "EvidenceTerminalRace")
    organization_id = UUID(auth["user"]["organization_id"])
    family_id = UUID(_family(client, headers)["id"])
    _, reviewer_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )
    target_recorded, _ = _record_evidence(client, headers, family_id)
    target_id = UUID(target_recorded.json()["resource"]["id"])
    _review_evidence(client, reviewer_headers, family_id, target_id)
    replacement_recorded, _ = _record_evidence(
        client,
        headers,
        family_id,
        source_label="Concurrent replacement evidence",
    )
    replacement_id = UUID(replacement_recorded.json()["resource"]["id"])
    _review_evidence(client, reviewer_headers, family_id, replacement_id)

    invalidate_operation, supersede_operation = uuid4(), uuid4()
    barrier = Barrier(2)
    responses: list = []
    failures: list[BaseException] = []

    def attempt(path_suffix: str, payload: dict) -> None:
        try:
            with _new_client(application) as concurrent_client:
                barrier.wait(timeout=10)
                responses.append(
                    concurrent_client.post(
                        f"/api/v1/families/{family_id}/authority/evidence/"
                        f"{target_id}/{path_suffix}",
                        headers=headers,
                        json=payload,
                    )
                )
        except BaseException as error:  # pragma: no cover - assertion reports details
            failures.append(error)

    threads = [
        Thread(
            target=attempt,
            args=(
                "invalidate",
                {
                    "client_operation_id": str(invalidate_operation),
                    "expected_version": 2,
                    "reason_code": "document_revoked",
                },
            ),
        ),
        Thread(
            target=attempt,
            args=(
                "supersede",
                {
                    "client_operation_id": str(supersede_operation),
                    "expected_version": 2,
                    "replacement_evidence_id": str(replacement_id),
                },
            ),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not failures
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response for response in responses if response.status_code == 200)
    loser = next(response for response in responses if response.status_code == 409)
    assert winner.json()["resource"]["lifecycle_status"] in {
        "invalidated",
        "superseded",
    }
    assert loser.json()["detail"]["code"] in {
        "stale_childcare_resource",
        "authority_evidence_state_changed",
        "authority_evidence_state_invalid",
    }
    with admin.connect() as connection:
        result = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND evidence_id=:evidence_id), "
                "(SELECT count(*) FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND evidence_id=:evidence_id "
                " AND version_number=3), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id IN "
                " (:invalidate_operation,:supersede_operation))"
            ),
            {
                "organization_id": organization_id,
                "evidence_id": target_id,
                "invalidate_operation": invalidate_operation,
                "supersede_operation": supersede_operation,
            },
        ).one()
    assert result == (2, 1, 1)


@pytest.mark.parametrize("terminal", ["invalidate", "supersede"])
def test_postgres_evidence_terminal_missing_head_rolls_back_and_repair_succeeds(
    postgres_harness: PostgresHarness,
    terminal: str,
) -> None:
    admin, client = postgres_harness.admin, postgres_harness.client
    auth, headers = _register(client, f"EvidenceMissing{terminal.title()}")
    organization_id = UUID(auth["user"]["organization_id"])
    actor_user_id = UUID(auth["user"]["id"])
    family_id = UUID(_family(client, headers)["id"])
    _, reviewer_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )
    child_id = UUID(_child(client, headers, str(family_id), "EvidenceHead")["id"])
    person = _create_person(client, headers, family_id)
    dependency = _seed_live_authorization_dependency(
        admin,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        family_id=family_id,
        child_id=child_id,
        person=person,
    )
    with admin.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM child_authority_heads "
                "WHERE organization_id=:organization_id AND child_id=:child_id"
            ),
            {"organization_id": organization_id, "child_id": child_id},
        )

    payload = {"client_operation_id": str(uuid4()), "expected_version": 2}
    if terminal == "invalidate":
        payload["reason_code"] = "authority_changed"
    else:
        replacement, _ = _record_evidence(
            client, headers, family_id, source_label="PostgreSQL replacement"
        )
        _review_evidence(
            client,
            reviewer_headers,
            family_id,
            UUID(replacement.json()["resource"]["id"]),
        )
        payload["replacement_evidence_id"] = replacement.json()["resource"]["id"]
    path = (
        f"/api/v1/families/{family_id}/authority/evidence/"
        f"{dependency['evidence']}/{terminal}"
    )
    failed = client.post(path, headers=headers, json=payload)
    assert failed.status_code == 409, failed.text
    assert failed.json()["detail"]["code"] == "authority_head_missing"
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM family_authority_evidence_assessments "
                " WHERE organization_id=:organization_id AND evidence_id=:evidence_id), "
                "(SELECT count(*) FROM childcare_command_receipts "
                " WHERE organization_id=:organization_id "
                " AND client_operation_id=:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "evidence_id": dependency["evidence"],
                "operation_id": UUID(payload["client_operation_id"]),
            },
        ).one() == (1, 0)

    with admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO child_authority_heads "
                "(organization_id,family_id,child_id,revision,created_operation_id,"
                "last_operation_id) VALUES "
                "(:organization_id,:family_id,:child_id,1,:operation_id,:operation_id)"
            ),
            {
                "organization_id": organization_id,
                "family_id": family_id,
                "child_id": child_id,
                "operation_id": dependency["authorization_operation"],
            },
        )
    repaired = client.post(path, headers=headers, json=payload)
    assert repaired.status_code == 200, repaired.text
    with admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT revision,last_operation_id FROM child_authority_heads "
                "WHERE organization_id=:organization_id AND child_id=:child_id"
            ),
            {"organization_id": organization_id, "child_id": child_id},
        ).one() == (2, UUID(payload["client_operation_id"]))
