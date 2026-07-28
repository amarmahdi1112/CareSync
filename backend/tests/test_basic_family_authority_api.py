"""Acceptance coverage for the first admin-only 0029A authority API slice."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.basic.family_authority import _raise_person_write_error
from app.basic.models import (
    AuditEvent,
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildReleaseAuthorization,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityPerson,
    FamilyAuthorityPersonVersion,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    User,
)
from app.basic.security import hash_password
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct-password-123"


class _ConstraintDiagnostic:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class _ConstraintFailure(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__(constraint_name)
        self.diag = _ConstraintDiagnostic(constraint_name)


class _RollbackProbe:
    def __init__(self) -> None:
        self.rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True


def _client(
    tmp_path,
    monkeypatch,
    *,
    revision: str = "head",
) -> tuple[TestClient, object]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="family-authority-api-test-secret-32-bytes",
    )
    application = create_app(settings)
    return TestClient(application), application


def _register(client: TestClient, name: str = "Authority") -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name.lower()}-{uuid4().hex}@example.com",
            "password": PASSWORD,
            "first_name": name,
            "last_name": "Owner",
            "organization_name": f"{name} Child Care",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _role_headers(
    application,
    client: TestClient,
    *,
    organization_id: str,
    role_key: str,
) -> tuple[str, dict[str, str]]:
    email = f"{role_key}-{uuid4().hex}@example.com"
    password = f"{role_key}-correct-password-123"
    with application.state.database.session_factory() as session:
        role = session.scalar(
            select(Role).where(
                Role.organization_id == UUID(organization_id),
                Role.key == role_key,
            )
        )
        assert role is not None
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            first_name=role_key.title(),
            last_name="Authority Tester",
            is_active=True,
            email_verified_at=datetime.now(UTC),
            email_verification_method="test_fixture",
        )
        session.add(user)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=UUID(organization_id),
                user_id=user.id,
                role_id=role.id,
                status="active",
            )
        )
        session.commit()
        user_id = str(user.id)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _post(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
    *,
    expected_status: int,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == expected_status, response.text
    return response.json()


def _family(client: TestClient, headers: dict[str, str], name: str = "Authority Family") -> dict:
    return _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": name,
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Guardian",
                "cell_phone": "780-555-0100",
            },
        },
        expected_status=201,
    )


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
        expected_status=201,
    )


def _person_payload(operation_id: str | None = None) -> dict:
    return {
        "client_operation_id": operation_id or str(uuid4()),
        "source": {"kind": "manual"},
        "facts": {
            "first_name": "Trusted",
            "middle_name": "Care",
            "last_name": "Recipient",
            "preferred_name": "Trust",
            "relationship_kind": "family_friend",
            "email": "trusted.recipient@example.com",
            "primary_phone": "780-555-0112",
        },
    }


def _replacement_facts() -> dict:
    return {
        "first_name": "Replacement",
        "middle_name": "Exact",
        "last_name": "Authority",
        "preferred_name": "Rex",
        "relationship_kind": "other",
        "relationship_detail": "Court-approved family support",
        "email": "replacement.authority@example.com",
        "primary_phone": "780-555-0199",
    }


def _replace_payload(
    *,
    operation_id: str | None = None,
    expected_version: int = 1,
    facts: dict | None = None,
) -> dict:
    return {
        "client_operation_id": operation_id or str(uuid4()),
        "expected_version": expected_version,
        "facts": facts or _replacement_facts(),
    }


def _retire_payload(
    *, operation_id: str | None = None, expected_version: int = 1
) -> dict:
    return {
        "client_operation_id": operation_id or str(uuid4()),
        "expected_version": expected_version,
    }


def _create_person(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    *,
    source: dict | None = None,
) -> dict:
    payload = _person_payload()
    if source is not None:
        payload["source"] = source
    response = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_live_authorization_dependency(
    application,
    *,
    organization_id: str,
    actor_user_id: str,
    family_id: str,
    child_id: str,
    person: dict,
    include_head: bool = True,
) -> dict[str, UUID]:
    ids = {
        "evidence": uuid4(),
        "evidence_operation": uuid4(),
        "evidence_assessment": uuid4(),
        "evidence_review_operation": uuid4(),
        "authorization": uuid4(),
        "authorization_operation": uuid4(),
    }
    organization_uuid = UUID(organization_id)
    actor_uuid = UUID(actor_user_id)
    family_uuid = UUID(family_id)
    child_uuid = UUID(child_id)
    person_id = UUID(person["id"])
    person_version_id = UUID(person["current_version"]["id"])
    now = datetime.now(UTC)
    with application.state.database.session_factory() as session:
        session.add_all(
            [
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=ids["evidence_operation"],
                    command_type="family.authority.evidence.record",
                    target_type="authority_evidence",
                    target_id=ids["evidence"],
                    request_hash=uuid4().hex * 2,
                    actor_user_id=actor_uuid,
                    committed_version=1,
                    outcome={
                        "action_route": (
                            f"/families/{family_id}?authority_evidence_id={ids['evidence']}"
                        )
                    },
                ),
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=ids["evidence_review_operation"],
                    command_type="family.authority.evidence.review",
                    target_type="authority_evidence",
                    target_id=ids["evidence"],
                    request_hash=uuid4().hex * 2,
                    actor_user_id=actor_uuid,
                    committed_version=2,
                    outcome={
                        "action_route": (
                            f"/families/{family_id}?authority_evidence_id={ids['evidence']}"
                        )
                    },
                ),
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=ids["authorization_operation"],
                    command_type="child.release.authorization.grant",
                    target_type="release_authorization",
                    target_id=ids["authorization"],
                    request_hash=uuid4().hex * 2,
                    actor_user_id=actor_uuid,
                    committed_version=1,
                    outcome={"action_route": f"/children/{child_id}"},
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                FamilyAuthorityEvidence(
                id=ids["evidence"],
                organization_id=organization_uuid,
                family_id=family_uuid,
                evidence_kind="guardian_attestation",
                source_label="Authority lifecycle test evidence",
                recorded_by_user_id=actor_uuid,
                created_operation_id=ids["evidence_operation"],
                ),
                FamilyAuthorityEvidenceAssessment(
                id=ids["evidence_assessment"],
                organization_id=organization_uuid,
                family_id=family_uuid,
                evidence_id=ids["evidence"],
                version_number=2,
                decision="reviewed",
                assessed_epistemic_status="document_observed",
                actor_user_id=actor_uuid,
                created_operation_id=ids["evidence_review_operation"],
                created_at=now,
                ),
            ]
        )
        session.flush()
        session.add(
            ChildReleaseAuthorization(
                id=ids["authorization"],
                organization_id=organization_uuid,
                family_id=family_uuid,
                child_id=child_uuid,
                recipient_person_id=person_id,
                verification_policy_code="government_photo_id",
                grantor_person_id=person_id,
                grantor_person_version_id=person_version_id,
                grantor_authority_basis="guardian_record",
                basis_evidence_id=ids["evidence"],
                basis_evidence_assessment_id=ids["evidence_assessment"],
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_until=datetime(2099, 1, 1, tzinfo=UTC),
                version=1,
                created_operation_id=ids["authorization_operation"],
            )
        )
        if include_head:
            session.add(
                ChildAuthorityHead(
                    organization_id=organization_uuid,
                    family_id=family_uuid,
                    child_id=child_uuid,
                    revision=1,
                    created_operation_id=ids["authorization_operation"],
                    last_operation_id=ids["authorization_operation"],
                )
            )
        session.commit()
    return ids


def _seed_authorization_dependencies_for_existing_evidence(
    application,
    *,
    organization_id: str,
    actor_user_id: str,
    family_id: str,
    child_ids: list[str],
    person: dict,
    evidence_id: str,
    evidence_assessment_id: str,
    omit_head_for: set[str] | None = None,
) -> dict[str, tuple[UUID, UUID]]:
    """Seed downstream history only; evidence itself must come through the API."""

    omitted = omit_head_for or set()
    organization_uuid = UUID(organization_id)
    actor_uuid = UUID(actor_user_id)
    family_uuid = UUID(family_id)
    person_id = UUID(person["id"])
    person_version_id = UUID(person["current_version"]["id"])
    seeded: dict[str, tuple[UUID, UUID]] = {}
    with application.state.database.session_factory() as session:
        for child_id in child_ids:
            child_uuid = UUID(child_id)
            operation_id = uuid4()
            authorization_id = uuid4()
            seeded[child_id] = (authorization_id, operation_id)
            session.add(
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=operation_id,
                    command_type="child.release.authorization.grant",
                    target_type="release_authorization",
                    target_id=authorization_id,
                    request_hash=uuid4().hex * 2,
                    actor_user_id=actor_uuid,
                    committed_version=1,
                    outcome={
                        "action_route": (
                            f"/children/{child_id}"
                            f"?release_authorization_id={authorization_id}"
                        )
                    },
                )
            )
            session.flush()
            session.add(
                ChildReleaseAuthorization(
                    id=authorization_id,
                    organization_id=organization_uuid,
                    family_id=family_uuid,
                    child_id=child_uuid,
                    recipient_person_id=person_id,
                    verification_policy_code="government_photo_id",
                    grantor_person_id=person_id,
                    grantor_person_version_id=person_version_id,
                    grantor_authority_basis="guardian_record",
                    basis_evidence_id=UUID(evidence_id),
                    basis_evidence_assessment_id=UUID(evidence_assessment_id),
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                    effective_until=datetime(2099, 1, 1, tzinfo=UTC),
                    version=1,
                    created_operation_id=operation_id,
                )
            )
            if child_id not in omitted:
                session.add(
                    ChildAuthorityHead(
                        organization_id=organization_uuid,
                        family_id=family_uuid,
                        child_id=child_uuid,
                        revision=1,
                        created_operation_id=operation_id,
                        last_operation_id=operation_id,
                    )
                )
        session.commit()
    return seeded


def test_workspace_projects_missing_child_heads_without_writes_and_requires_admin(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        family = _family(client, owner_headers)
        children = [
            _child(client, owner_headers, family["id"], "One"),
            _child(client, owner_headers, family["id"], "Two"),
        ]

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 0

        response = client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
        workspace = response.json()
        assert workspace["organization_id"] == auth["user"]["organization_id"]
        assert workspace["family_id"] == family["id"]
        assert workspace["people"] == []
        assert workspace["evidence"] == []
        assert {row["child_id"] for row in workspace["children"]} == {
            child["id"] for child in children
        }
        assert all(
            row
            == {
                "child_id": row["child_id"],
                "reviewed": False,
                "authority_revision": 0,
                "release_authorizations": [],
                "release_rules": [],
                "consent_decisions": [],
            }
            for row in workspace["children"]
        )
        assert response.headers["cache-control"] == "private, no-store"

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 0

        _, educator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="educator",
        )
        forbidden = client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=educator_headers,
        )
        assert forbidden.status_code == 403
        forbidden_create = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=educator_headers,
            json=_person_payload(),
        )
        assert forbidden_create.status_code == 403


def test_retained_0028_runtime_fails_closed_before_authority_queries(tmp_path, monkeypatch) -> None:
    client, application = _client(
        tmp_path,
        monkeypatch,
        revision="0028_childcare_command_spine",
    )
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        assert application.state.family_authority_enabled is False

        unavailable_read = client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=headers,
        )
        assert unavailable_read.status_code == 503, unavailable_read.text
        assert unavailable_read.json()["detail"] == {
            "code": "family_authority_unavailable"
        }

        operation_id = uuid4()
        unavailable_write = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=_person_payload(str(operation_id)),
        )
        assert unavailable_write.status_code == 503, unavailable_write.text
        assert unavailable_write.json()["detail"] == {
            "code": "family_authority_unavailable"
        }
        assert unavailable_write.headers["cache-control"] == "private, no-store"

        unavailable_person_id = uuid4()
        unavailable_replace = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{unavailable_person_id}/versions",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "facts": _person_payload()["facts"],
            },
        )
        assert unavailable_replace.status_code == 503, unavailable_replace.text
        assert unavailable_replace.json()["detail"] == {
            "code": "family_authority_unavailable"
        }
        unavailable_retire = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{unavailable_person_id}/retire",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
            },
        )
        assert unavailable_retire.status_code == 503, unavailable_retire.text
        assert unavailable_retire.json()["detail"] == {
            "code": "family_authority_unavailable"
        }

        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(ChildcareCommandReceipt.client_operation_id == operation_id)
                )
                == 0
            )


def test_person_create_exact_retry_scope_hash_and_exactly_once_side_effects(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        other_family = _family(client, headers, "Other Authority Family")
        operation_id = str(uuid4())
        payload = _person_payload(operation_id)

        response = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["replayed"] is False
        person = created["resource"]
        assert person["organization_id"] == auth["user"]["organization_id"]
        assert person["family_id"] == family["id"]
        assert person["version"] == 1
        assert person["status"] == "active"
        assert person["source"] == {"kind": "manual"}
        assert person["retired_at"] is None
        assert person["current_version"]["person_id"] == person["id"]
        assert person["current_version"]["version_number"] == 1
        assert person["current_version"]["facts"] == {
            **payload["facts"],
            "relationship_detail": None,
        }
        receipt = created["receipt"]
        assert receipt["organization_id"] == auth["user"]["organization_id"]
        assert receipt["client_operation_id"] == operation_id
        assert receipt["command_type"] == "family.authority.person.create"
        assert receipt["target_type"] == "authority_person"
        assert receipt["target_id"] == person["id"]
        assert receipt["committed_version"] == 1
        assert receipt["facility_id"] is None
        assert receipt["action_route"].startswith("/")
        assert "Trusted" not in str(receipt)
        assert response.headers["cache-control"] == "private, no-store"

        replay_response = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=payload,
        )
        assert replay_response.status_code == 201, replay_response.text
        replay = replay_response.json()
        assert replay["replayed"] is True
        assert replay["resource"] == created["resource"]
        assert replay["receipt"] == created["receipt"]

        reconciled = client.get(
            f"/api/v1/childcare-commands/{operation_id}",
            headers=headers,
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json() == created["receipt"]

        mismatched_payload = _person_payload(operation_id)
        mismatched_payload["facts"]["last_name"] = "Different"
        mismatch = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=mismatched_payload,
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "operation_reused"

        wrong_scope = client.post(
            f"/api/v1/families/{other_family['id']}/authority/people",
            headers=headers,
            json=payload,
        )
        assert wrong_scope.status_code == 409
        assert wrong_scope.json()["detail"]["code"] == "operation_reused"

        organization_id = UUID(auth["user"]["organization_id"])
        person_id = UUID(person["id"])
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyAuthorityPerson)
                    .where(FamilyAuthorityPerson.id == person_id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyAuthorityPersonVersion)
                    .where(FamilyAuthorityPersonVersion.person_id == person_id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id == UUID(operation_id),
                    )
                )
                == 1
            )
            audit_events = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.entity_type == "authority_person",
                        AuditEvent.entity_id == person_id,
                        AuditEvent.action == "family.authority.person.created",
                    )
                )
            )
            realtime_events = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_type == "authority_person",
                        RealtimeEvent.entity_id == person_id,
                        RealtimeEvent.event_type == "family.authority.person.created",
                    )
                )
            )
            assert len(audit_events) == 1
            assert realtime_events == []
            forbidden_person_facts = (
                "Trusted",
                "Recipient",
                "trusted.recipient@example.com",
                "780-555-0112",
            )
            assert all(
                value not in str(audit_events[0].details) for value in forbidden_person_facts
            )


def test_person_replace_retire_lifecycle_is_exactly_once_bound_and_historical(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        organization_id = UUID(auth["user"]["organization_id"])
        family = _family(client, owner_headers, "Lifecycle Family")
        other_family = _family(client, owner_headers, "Wrong Path Family")
        child = _child(client, owner_headers, family["id"], "Lifecycle")
        guardian_id = family["guardians"][0]["id"]
        created = _create_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": guardian_id},
        )
        person = created["resource"]
        person_id = UUID(person["id"])
        first_version_id = UUID(person["current_version"]["id"])
        other_person = _create_person(client, owner_headers, family["id"])["resource"]
        _, administrator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        _seed_live_authorization_dependency(
            application,
            organization_id=auth["user"]["organization_id"],
            actor_user_id=auth["user"]["id"],
            family_id=family["id"],
            child_id=child["id"],
            person=person,
        )

        replace_operation_id = str(uuid4())
        replace_payload = _replace_payload(operation_id=replace_operation_id)
        replace_path = (
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/versions"
        )
        replaced_response = client.post(
            replace_path,
            headers=owner_headers,
            json=replace_payload,
        )
        assert replaced_response.status_code == 200, replaced_response.text
        assert replaced_response.headers["cache-control"] == "private, no-store"
        replaced = replaced_response.json()
        assert replaced["replayed"] is False
        assert replaced["resource"]["id"] == person["id"]
        assert replaced["resource"]["version"] == 2
        assert replaced["resource"]["status"] == "active"
        assert replaced["resource"]["source"] == {
            "kind": "guardian",
            "guardian_id": guardian_id,
        }
        assert replaced["resource"]["current_version"]["version_number"] == 2
        assert replaced["resource"]["current_version"]["facts"] == _replacement_facts()
        assert replaced["receipt"]["client_operation_id"] == replace_operation_id
        assert replaced["receipt"]["command_type"] == "family.authority.person.replace"
        assert replaced["receipt"]["target_type"] == "authority_person"
        assert replaced["receipt"]["target_id"] == person["id"]
        assert replaced["receipt"]["committed_version"] == 2

        exact_replace_retry = client.post(
            replace_path,
            headers=owner_headers,
            json=replace_payload,
        )
        assert exact_replace_retry.status_code == 200, exact_replace_retry.text
        assert exact_replace_retry.json() == {**replaced, "replayed": True}

        changed_intent = _replace_payload(operation_id=replace_operation_id)
        changed_intent["facts"]["last_name"] = "Different"
        mismatch = client.post(
            replace_path,
            headers=owner_headers,
            json=changed_intent,
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "operation_reused"

        wrong_command = client.post(
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/retire",
            headers=owner_headers,
            json=_retire_payload(
                operation_id=replace_operation_id,
                expected_version=2,
            ),
        )
        assert wrong_command.status_code == 409
        assert wrong_command.json()["detail"]["code"] == "operation_reused"
        for path in (
            f"/api/v1/families/{other_family['id']}/authority/people/"
            f"{person['id']}/versions",
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{other_person['id']}/versions",
        ):
            wrong_path = client.post(
                path,
                headers=owner_headers,
                json=replace_payload,
            )
            assert wrong_path.status_code == 409
            assert wrong_path.json()["detail"]["code"] == "operation_reused"
        actor_private = client.post(
            replace_path,
            headers=administrator_headers,
            json=replace_payload,
        )
        assert actor_private.status_code == 404
        assert actor_private.json()["detail"] == "Operation receipt not found"

        injected_operation_id = str(uuid4())
        injected = _replace_payload(
            operation_id=injected_operation_id,
            expected_version=2,
        )
        injected.update(
            {
                "family_id": other_family["id"],
                "person_id": other_person["id"],
                "source": {"kind": "manual"},
            }
        )
        body_override = client.post(
            replace_path,
            headers=owner_headers,
            json=injected,
        )
        assert body_override.status_code == 422

        retire_operation_id = str(uuid4())
        retire_payload = _retire_payload(
            operation_id=retire_operation_id,
            expected_version=2,
        )
        retire_path = (
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/retire"
        )
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
        assert retired["resource"]["retired_at"] is not None
        assert retired["resource"]["source"] == replaced["resource"]["source"]
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
        historical = historical_replace_retry.json()
        assert historical["replayed"] is True
        assert historical["receipt"]["committed_version"] == 2
        assert historical["resource"] == retired["resource"]

        terminal_operation_ids = (str(uuid4()), str(uuid4()))
        terminal_replace = client.post(
            replace_path,
            headers=owner_headers,
            json=_replace_payload(
                operation_id=terminal_operation_ids[0],
                expected_version=3,
            ),
        )
        assert terminal_replace.status_code == 409
        assert terminal_replace.json()["detail"]["code"] == "authority_person_inactive"
        terminal_retire = client.post(
            retire_path,
            headers=owner_headers,
            json=_retire_payload(
                operation_id=terminal_operation_ids[1],
                expected_version=3,
            ),
        )
        assert terminal_retire.status_code == 409
        assert terminal_retire.json()["detail"]["code"] == "authority_person_inactive"

        with application.state.database.session_factory() as session:
            stored_person = session.scalar(
                select(FamilyAuthorityPerson).where(FamilyAuthorityPerson.id == person_id)
            )
            assert stored_person is not None
            assert stored_person.version == 3
            assert stored_person.status == "retired"
            assert stored_person.current_person_version_id is None
            assert stored_person.source_guardian_id == UUID(guardian_id)
            assert stored_person.source_emergency_contact_id is None
            assert stored_person.retired_operation_id == UUID(retire_operation_id)
            assert stored_person.last_operation_id == UUID(retire_operation_id)

            versions = list(
                session.scalars(
                    select(FamilyAuthorityPersonVersion)
                    .where(FamilyAuthorityPersonVersion.person_id == person_id)
                    .order_by(FamilyAuthorityPersonVersion.version_number)
                )
            )
            assert len(versions) == 2
            assert [value.version_number for value in versions] == [1, 2]
            assert versions[0].id == first_version_id
            assert versions[0].closed_operation_id == UUID(replace_operation_id)
            assert versions[1].closed_operation_id == UUID(retire_operation_id)
            assert all(value.closed_at is not None for value in versions)

            head = session.get(ChildAuthorityHead, UUID(child["id"]))
            assert head is not None
            assert head.revision == 3
            assert head.last_operation_id == UUID(retire_operation_id)

            lifecycle_receipts = list(
                session.scalars(
                    select(ChildcareCommandReceipt).where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id.in_(
                            [
                                UUID(replace_operation_id),
                                UUID(retire_operation_id),
                                UUID(injected_operation_id),
                                *(UUID(value) for value in terminal_operation_ids),
                            ]
                        ),
                    )
                )
            )
            assert {
                value.client_operation_id for value in lifecycle_receipts
            } == {UUID(replace_operation_id), UUID(retire_operation_id)}

            replaced_audits = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.entity_id == person_id,
                        AuditEvent.action == "family.authority.person.replaced",
                    )
                )
            )
            retired_audits = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.entity_id == person_id,
                        AuditEvent.action == "family.authority.person.retired",
                    )
                )
            )
            replaced_realtime = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_id == person_id,
                        RealtimeEvent.event_type == "family.authority.person.replaced",
                    )
                )
            )
            retired_realtime = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_id == person_id,
                        RealtimeEvent.event_type == "family.authority.person.retired",
                    )
                )
            )
            assert len(replaced_audits) == len(retired_audits) == 1
            assert replaced_realtime == []
            assert retired_realtime == []
            assert replaced_audits[0].details["affected_child_count"] == 1
            assert retired_audits[0].details["affected_child_count"] == 1
            for event in (replaced_audits[0], retired_audits[0]):
                assert "replacement.authority@example.com" not in str(event)


def test_person_transitions_reject_stale_cross_family_and_body_owned_intent(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers, "Stale Family")
        other_family = _family(client, headers, "Unrelated Family")
        person = _create_person(client, headers, family["id"])["resource"]
        replace_path = (
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/versions"
        )
        retire_path = (
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/retire"
        )

        stale_replace_operation = str(uuid4())
        stale_replace = client.post(
            replace_path,
            headers=headers,
            json=_replace_payload(
                operation_id=stale_replace_operation,
                expected_version=2,
            ),
        )
        assert stale_replace.status_code == 409
        assert stale_replace.json()["detail"] == {
            "code": "stale_childcare_resource",
            "resource_type": "authority_person",
            "resource_id": person["id"],
            "expected_version": 2,
            "current_version": 1,
        }

        stale_retire_operation = str(uuid4())
        stale_retire = client.post(
            retire_path,
            headers=headers,
            json=_retire_payload(
                operation_id=stale_retire_operation,
                expected_version=2,
            ),
        )
        assert stale_retire.status_code == 409
        assert stale_retire.json()["detail"]["code"] == "stale_childcare_resource"

        cross_family_operation = str(uuid4())
        cross_family = client.post(
            f"/api/v1/families/{other_family['id']}/authority/people/"
            f"{person['id']}/versions",
            headers=headers,
            json=_replace_payload(operation_id=cross_family_operation),
        )
        assert cross_family.status_code == 404
        assert cross_family.json()["detail"] == "Authority person not found"

        body_override_operation = str(uuid4())
        body_override_payload = _retire_payload(operation_id=body_override_operation)
        body_override_payload.update(
            {"family_id": other_family["id"], "person_id": str(uuid4())}
        )
        body_override = client.post(
            retire_path,
            headers=headers,
            json=body_override_payload,
        )
        assert body_override.status_code == 422

        rejected_operations = {
            UUID(stale_replace_operation),
            UUID(stale_retire_operation),
            UUID(cross_family_operation),
            UUID(body_override_operation),
        }
        with application.state.database.session_factory() as session:
            stored_person = session.get(FamilyAuthorityPerson, UUID(person["id"]))
            assert stored_person is not None
            assert stored_person.version == 1
            assert stored_person.status == "active"
            assert stored_person.current_person_version_id == UUID(
                person["current_version"]["id"]
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyAuthorityPersonVersion)
                    .where(FamilyAuthorityPersonVersion.person_id == UUID(person["id"]))
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id
                        == UUID(auth["user"]["organization_id"]),
                        ChildcareCommandReceipt.client_operation_id.in_(rejected_operations),
                    )
                )
                == 0
            )


def test_person_transition_missing_child_head_is_fail_closed_and_retryable_after_repair(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers, "Missing Head Family")
        child = _child(client, headers, family["id"], "MissingHead")
        person = _create_person(client, headers, family["id"])["resource"]
        dependency = _seed_live_authorization_dependency(
            application,
            organization_id=auth["user"]["organization_id"],
            actor_user_id=auth["user"]["id"],
            family_id=family["id"],
            child_id=child["id"],
            person=person,
            include_head=False,
        )
        replace_operation_id = str(uuid4())
        replace_payload = _replace_payload(operation_id=replace_operation_id)
        replace_path = (
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/versions"
        )
        missing_replace = client.post(
            replace_path,
            headers=headers,
            json=replace_payload,
        )
        assert missing_replace.status_code == 409
        assert missing_replace.json()["detail"] == {"code": "authority_head_missing"}

        retire_operation_id = str(uuid4())
        missing_retire = client.post(
            f"/api/v1/families/{family['id']}/authority/people/{person['id']}/retire",
            headers=headers,
            json=_retire_payload(operation_id=retire_operation_id),
        )
        assert missing_retire.status_code == 409
        assert missing_retire.json()["detail"] == {"code": "authority_head_missing"}

        with application.state.database.session_factory() as session:
            stored_person = session.get(FamilyAuthorityPerson, UUID(person["id"]))
            assert stored_person is not None
            assert stored_person.version == 1
            assert stored_person.current_person_version_id == UUID(
                person["current_version"]["id"]
            )
            assert session.get(ChildAuthorityHead, UUID(child["id"])) is None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.client_operation_id.in_(
                            [UUID(replace_operation_id), UUID(retire_operation_id)]
                        )
                    )
                )
                == 0
            )

            session.add(
                ChildAuthorityHead(
                    organization_id=UUID(auth["user"]["organization_id"]),
                    family_id=UUID(family["id"]),
                    child_id=UUID(child["id"]),
                    revision=1,
                    created_operation_id=dependency["authorization_operation"],
                    last_operation_id=dependency["authorization_operation"],
                )
            )
            session.commit()

        repaired_retry = client.post(
            replace_path,
            headers=headers,
            json=replace_payload,
        )
        assert repaired_retry.status_code == 200, repaired_retry.text
        assert repaired_retry.json()["replayed"] is False
        assert repaired_retry.json()["resource"]["version"] == 2
        with application.state.database.session_factory() as session:
            head = session.get(ChildAuthorityHead, UUID(child["id"]))
            assert head is not None
            assert head.revision == 2
            assert head.last_operation_id == UUID(replace_operation_id)
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.client_operation_id
                        == UUID(replace_operation_id)
                    )
                )
                == 1
            )


def test_person_create_rejects_body_owner_override_and_preserves_tenant_privacy(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        first_auth, first_headers = _register(client, "First")
        first_family = _family(client, first_headers, "First Family")
        _, second_headers = _register(client, "Second")

        injected_operation_id = str(uuid4())
        injected = _person_payload(injected_operation_id)
        injected["family_id"] = str(uuid4())
        rejected = client.post(
            f"/api/v1/families/{first_family['id']}/authority/people",
            headers=first_headers,
            json=injected,
        )
        assert rejected.status_code == 422

        private_read = client.get(
            f"/api/v1/families/{first_family['id']}/authority",
            headers=second_headers,
        )
        assert private_read.status_code == 404
        private_write = client.post(
            f"/api/v1/families/{first_family['id']}/authority/people",
            headers=second_headers,
            json=_person_payload(),
        )
        assert private_write.status_code == 404

        _, second_admin_headers = _role_headers(
            application,
            client,
            organization_id=first_auth["user"]["organization_id"],
            role_key="administrator",
        )
        operation_id = str(uuid4())
        payload = _person_payload(operation_id)
        created = client.post(
            f"/api/v1/families/{first_family['id']}/authority/people",
            headers=first_headers,
            json=payload,
        )
        assert created.status_code == 201, created.text
        actor_private = client.post(
            f"/api/v1/families/{first_family['id']}/authority/people",
            headers=second_admin_headers,
            json=payload,
        )
        assert actor_private.status_code == 404
        assert actor_private.json()["detail"] == "Operation receipt not found"

        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id
                        == UUID(first_auth["user"]["organization_id"]),
                        ChildcareCommandReceipt.client_operation_id == UUID(injected_operation_id),
                    )
                )
                == 0
            )


def test_create_retry_returns_current_person_after_a_later_version(tmp_path, monkeypatch) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        create_operation_id = str(uuid4())
        payload = _person_payload(create_operation_id)
        created = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 201, created.text
        created_body = created.json()

        organization_id = UUID(auth["user"]["organization_id"])
        actor_id = UUID(auth["user"]["id"])
        person_id = UUID(created_body["resource"]["id"])
        replace_operation_id = uuid4()
        next_version_id = uuid4()
        now = datetime.now(UTC)
        with application.state.database.session_factory() as session:
            person = session.scalar(
                select(FamilyAuthorityPerson).where(FamilyAuthorityPerson.id == person_id)
            )
            assert person is not None
            old_version = session.scalar(
                select(FamilyAuthorityPersonVersion).where(
                    FamilyAuthorityPersonVersion.id == person.current_person_version_id
                )
            )
            assert old_version is not None
            session.add(
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_id,
                    client_operation_id=replace_operation_id,
                    command_type="family.authority.person.replace",
                    target_type="authority_person",
                    target_id=person_id,
                    request_hash="a" * 64,
                    actor_user_id=actor_id,
                    committed_version=2,
                    outcome={
                        "action_route": (
                            f"/families/{family['id']}?authority_person_id={person_id}"
                        )
                    },
                )
            )
            session.flush()
            old_version.closed_at = now
            old_version.closed_operation_id = replace_operation_id
            person.version = 2
            person.current_person_version_id = next_version_id
            person.last_operation_id = replace_operation_id
            session.add(
                FamilyAuthorityPersonVersion(
                    id=next_version_id,
                    organization_id=organization_id,
                    family_id=UUID(family["id"]),
                    person_id=person_id,
                    version_number=2,
                    first_name="Current",
                    last_name="Projection",
                    relationship_kind="family_friend",
                    created_operation_id=replace_operation_id,
                )
            )
            session.commit()

        replay = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=payload,
        )
        assert replay.status_code == 201, replay.text
        replay_body = replay.json()
        assert replay_body["replayed"] is True
        assert replay_body["receipt"] == created_body["receipt"]
        assert replay_body["receipt"]["committed_version"] == 1
        assert replay_body["resource"]["version"] == 2
        assert replay_body["resource"]["current_version"]["version_number"] == 2
        assert replay_body["resource"]["current_version"]["facts"]["first_name"] == "Current"


def test_person_create_honors_read_only_guard_while_workspace_remains_available(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)

    read_only_settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=application.state.settings.database_path,
        database_name="caresync",
        database_read_only=True,
        enable_advanced_routes=False,
        jwt_secret="family-authority-api-test-secret-32-bytes",
    )
    read_only_application = create_app(read_only_settings)
    operation_id = str(uuid4())
    with TestClient(read_only_application) as read_only_client:
        workspace = read_only_client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=headers,
        )
        assert workspace.status_code == 200, workspace.text
        blocked = read_only_client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=_person_payload(operation_id),
        )
        assert blocked.status_code == 409
        assert blocked.json() == {"detail": "Database writes are disabled"}

    with application.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(FamilyAuthorityPerson)
                .where(FamilyAuthorityPerson.family_id == UUID(family["id"]))
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(ChildcareCommandReceipt.client_operation_id == UUID(operation_id))
            )
            == 0
        )


def test_person_replace_and_retire_require_leadership_and_writable_runtime(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    blocked_operation_ids: list[UUID] = []
    with client:
        auth, owner_headers = _register(client)
        family = _family(client, owner_headers, "Transition Guard Family")
        administrator_person = _create_person(client, owner_headers, family["id"])["resource"]
        blocked_person = _create_person(client, owner_headers, family["id"])["resource"]
        _, administrator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        _, educator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="educator",
        )

        blocked_replace_operation = uuid4()
        blocked_operation_ids.append(blocked_replace_operation)
        educator_replace = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{blocked_person['id']}/versions",
            headers=educator_headers,
            json=_replace_payload(operation_id=str(blocked_replace_operation)),
        )
        assert educator_replace.status_code == 403
        blocked_retire_operation = uuid4()
        blocked_operation_ids.append(blocked_retire_operation)
        educator_retire = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{blocked_person['id']}/retire",
            headers=educator_headers,
            json=_retire_payload(operation_id=str(blocked_retire_operation)),
        )
        assert educator_retire.status_code == 403

        administrator_replace = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{administrator_person['id']}/versions",
            headers=administrator_headers,
            json=_replace_payload(),
        )
        assert administrator_replace.status_code == 200, administrator_replace.text
        administrator_retire = client.post(
            f"/api/v1/families/{family['id']}/authority/people/"
            f"{administrator_person['id']}/retire",
            headers=administrator_headers,
            json=_retire_payload(expected_version=2),
        )
        assert administrator_retire.status_code == 200, administrator_retire.text
        assert administrator_retire.json()["resource"]["status"] == "retired"

    read_only_settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=application.state.settings.database_path,
        database_name="caresync",
        database_read_only=True,
        enable_advanced_routes=False,
        jwt_secret="family-authority-api-test-secret-32-bytes",
    )
    read_only_application = create_app(read_only_settings)
    read_only_replace_operation = uuid4()
    read_only_retire_operation = uuid4()
    blocked_operation_ids.extend(
        [read_only_replace_operation, read_only_retire_operation]
    )
    with TestClient(read_only_application) as read_only_client:
        for suffix, payload in (
            (
                "versions",
                _replace_payload(operation_id=str(read_only_replace_operation)),
            ),
            (
                "retire",
                _retire_payload(operation_id=str(read_only_retire_operation)),
            ),
        ):
            blocked = read_only_client.post(
                f"/api/v1/families/{family['id']}/authority/people/"
                f"{blocked_person['id']}/{suffix}",
                headers=owner_headers,
                json=payload,
            )
            assert blocked.status_code == 409
            assert blocked.json() == {"detail": "Database writes are disabled"}

    with application.state.database.session_factory() as session:
        stored_person = session.get(FamilyAuthorityPerson, UUID(blocked_person["id"]))
        assert stored_person is not None
        assert stored_person.version == 1
        assert stored_person.status == "active"
        assert (
            session.scalar(
                select(func.count())
                .select_from(FamilyAuthorityPersonVersion)
                .where(
                    FamilyAuthorityPersonVersion.person_id == UUID(blocked_person["id"])
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(
                    ChildcareCommandReceipt.client_operation_id.in_(blocked_operation_ids)
                )
            )
            == 0
        )


def test_person_sources_are_family_bound_tagged_and_single_use(tmp_path, monkeypatch) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Source Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Source",
                    "cell_phone": "780-555-0120",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Emergency",
                        "last_name": "Source",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0121",
                    }
                ],
            },
            expected_status=201,
        )
        other_family = _family(client, headers, "Unrelated Family")
        guardian_id = family["guardians"][0]["id"]
        contact_id = family["emergency_contacts"][0]["id"]

        guardian_payload = _person_payload()
        guardian_payload["source"] = {"kind": "guardian", "guardian_id": guardian_id}
        guardian_create = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=guardian_payload,
        )
        assert guardian_create.status_code == 201, guardian_create.text
        assert guardian_create.json()["resource"]["source"] == {
            "kind": "guardian",
            "guardian_id": guardian_id,
        }

        duplicate = _person_payload()
        duplicate["source"] = {"kind": "guardian", "guardian_id": guardian_id}
        duplicate_response = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=duplicate,
        )
        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"] == {
            "code": "authority_source_already_linked"
        }

        cross_family_operation = str(uuid4())
        cross_family = _person_payload(cross_family_operation)
        cross_family["source"] = {"kind": "guardian", "guardian_id": guardian_id}
        private_source = client.post(
            f"/api/v1/families/{other_family['id']}/authority/people",
            headers=headers,
            json=cross_family,
        )
        assert private_source.status_code == 404
        assert private_source.json()["detail"] == "Authority source not found"

        contact_payload = _person_payload()
        contact_payload["source"] = {
            "kind": "emergency_contact",
            "emergency_contact_id": contact_id,
        }
        contact_create = client.post(
            f"/api/v1/families/{family['id']}/authority/people",
            headers=headers,
            json=contact_payload,
        )
        assert contact_create.status_code == 201, contact_create.text
        assert contact_create.json()["resource"]["source"] == {
            "kind": "emergency_contact",
            "emergency_contact_id": contact_id,
        }

        workspace = client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=headers,
        )
        assert workspace.status_code == 200, workspace.text
        assert {row["source"]["kind"] for row in workspace.json()["people"]} == {
            "guardian",
            "emergency_contact",
        }

        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.client_operation_id
                        == UUID(cross_family_operation)
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyAuthorityPerson)
                    .where(FamilyAuthorityPerson.family_id == UUID(family["id"]))
                )
                == 2
            )


def _record_evidence_api(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    *,
    operation_id: str | None = None,
    source_label: str = "Guardian attestation",
    expires_at: str | None = "2099-01-01T00:00:00Z",
) -> tuple[dict, dict]:
    payload = {
        "client_operation_id": operation_id or str(uuid4()),
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
    return response.json(), payload


@pytest.mark.parametrize(
    ("constraint_name", "status_code", "detail_code"),
    (
        (
            "ck_authority_evidence_privileged_actor",
            403,
            "family_authority_access_revoked",
        ),
        (
            "ck_authority_evidence_assessment_privileged_actor",
            403,
            "family_authority_access_revoked",
        ),
        (
            "ck_authority_evidence_child_revisions",
            409,
            "authority_revision_changed",
        ),
        (
            "ck_authority_person_child_revisions",
            409,
            "authority_revision_changed",
        ),
    ),
)
def test_evidence_database_conflicts_have_typed_http_mappings(
    constraint_name: str,
    status_code: int,
    detail_code: str,
) -> None:
    session = _RollbackProbe()
    error = IntegrityError(
        "authority write",
        {},
        _ConstraintFailure(constraint_name),
    )
    with pytest.raises(HTTPException) as raised:
        _raise_person_write_error(session, error)  # type: ignore[arg-type]
    assert session.rolled_back is True
    assert raised.value.status_code == status_code
    assert raised.value.detail == {"code": detail_code}


def _review_evidence_api(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    evidence_id: str,
    *,
    operation_id: str | None = None,
) -> tuple[dict, dict]:
    payload = {
        "client_operation_id": operation_id or str(uuid4()),
        "expected_version": 1,
        "assessed_epistemic_status": "reported",
    }
    response = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{evidence_id}/review",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json(), payload


def test_evidence_record_review_and_reject_are_exact_retry_immutable_commands(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client, "EvidenceLifecycle")
        organization_id = auth["user"]["organization_id"]
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=organization_id,
            role_key="administrator",
        )
        family = _family(client, headers, "Evidence Lifecycle Family")

        recorded, record_payload = _record_evidence_api(
            client, headers, family["id"]
        )
        evidence_id = recorded["resource"]["id"]
        assert recorded["resource"] == {
            **recorded["resource"],
            "version": 1,
            "lifecycle_status": "unreviewed",
            "effective_status": "unreviewed",
            "valid_now": False,
            "current_assessment": None,
            "storage": None,
        }
        assert recorded["receipt"]["command_type"] == "family.authority.evidence.record"
        assert recorded["receipt"]["committed_version"] == 1
        assert recorded["receipt"]["action_route"] == (
            f"/families/{family['id']}?authority_evidence_id={evidence_id}"
        )

        reviewed, review_payload = _review_evidence_api(
            client, reviewer_headers, family["id"], evidence_id
        )
        assessment = reviewed["resource"]["current_assessment"]
        assert reviewed["resource"]["version"] == 2
        assert reviewed["resource"]["lifecycle_status"] == "reviewed"
        assert reviewed["resource"]["valid_now"] is True
        assert assessment["decision"] == "reviewed"
        assert assessment["version_number"] == 2
        assert reviewed["receipt"]["command_type"] == "family.authority.evidence.review"

        historical_replay = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json=record_payload,
        )
        assert historical_replay.status_code == 201, historical_replay.text
        assert historical_replay.json()["replayed"] is True
        assert historical_replay.json()["receipt"] == recorded["receipt"]
        assert historical_replay.json()["resource"]["version"] == 2

        review_replay = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=reviewer_headers,
            json=review_payload,
        )
        assert review_replay.status_code == 200, review_replay.text
        assert review_replay.json()["replayed"] is True
        assert review_replay.json()["receipt"] == reviewed["receipt"]

        stale_review = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=reviewer_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "assessed_epistemic_status": "reported",
            },
        )
        assert stale_review.status_code == 409, stale_review.text
        assert stale_review.json()["detail"]["code"] == "stale_childcare_resource"

        rejected, _ = _record_evidence_api(
            client,
            headers,
            family["id"],
            source_label="Unreadable custody scan",
            expires_at=None,
        )
        rejected_id = rejected["resource"]["id"]
        reject_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "reason_code": "other",
            "confidential_note": "The submitted page cannot be authenticated.",
        }
        reject_response = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{rejected_id}/reject",
            headers=headers,
            json=reject_payload,
        )
        assert reject_response.status_code == 200, reject_response.text
        rejected_resource = reject_response.json()["resource"]
        assert rejected_resource["lifecycle_status"] == "rejected"
        assert rejected_resource["current_assessment"]["reason_code"] == "other"
        reject_replay = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{rejected_id}/reject",
            headers=headers,
            json=reject_payload,
        )
        assert reject_replay.status_code == 200, reject_replay.text
        assert reject_replay.json()["replayed"] is True
        assert reject_replay.json()["receipt"] == reject_response.json()["receipt"]

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 0
            assets = list(
                session.scalars(
                    select(FamilyAuthorityEvidence).where(
                        FamilyAuthorityEvidence.organization_id == UUID(organization_id)
                    )
                )
            )
            assessments = list(
                session.scalars(
                    select(FamilyAuthorityEvidenceAssessment).where(
                        FamilyAuthorityEvidenceAssessment.organization_id
                        == UUID(organization_id)
                    )
                )
            )
            assert {value.created_operation_id for value in assets} == {
                UUID(record_payload["client_operation_id"]),
                UUID(rejected["receipt"]["client_operation_id"]),
            }
            assert {value.created_operation_id for value in assessments} == {
                UUID(review_payload["client_operation_id"]),
                UUID(reject_response.json()["receipt"]["client_operation_id"]),
            }
            evidence_ids = {UUID(evidence_id), UUID(rejected_id)}
            audit_events = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == UUID(organization_id),
                        AuditEvent.entity_type == "authority_evidence",
                        AuditEvent.entity_id.in_(evidence_ids),
                    )
                )
            )
            realtime_events = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id == UUID(organization_id),
                        RealtimeEvent.entity_type == "authority_evidence",
                        RealtimeEvent.entity_id.in_(evidence_ids),
                    )
                )
            )
            expected_events = {
                (UUID(evidence_id), "family.authority.evidence.recorded"),
                (UUID(evidence_id), "family.authority.evidence.reviewed"),
                (UUID(rejected_id), "family.authority.evidence.recorded"),
                (UUID(rejected_id), "family.authority.evidence.rejected"),
            }
            assert [(event.entity_id, event.action) for event in audit_events]
            assert {(event.entity_id, event.action) for event in audit_events} == (
                expected_events
            )
            assert len(audit_events) == len(expected_events)
            assert realtime_events == []
            private_evidence_facts = (
                "Observed custody document",
                "Unreadable custody scan",
                "The submitted page cannot be authenticated.",
            )
            assert all(
                value not in str(event.details)
                for event in audit_events
                for value in private_evidence_facts
            )
            assert all(
                value not in str(event.payload)
                for event in realtime_events
                for value in private_evidence_facts
            )


def test_evidence_intake_is_strict_and_expired_asset_cannot_be_reviewed(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client, "EvidenceStrict")
        family = _family(client, headers)
        _, educator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="educator",
        )
        rejected_operation = str(uuid4())
        response = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json={
                "client_operation_id": rejected_operation,
                "evidence_kind": "custody_document",
                "source_label": "Must reject reserved client claims",
                "storage": None,
                "review_status": "reviewed",
                "epistemic_status": "issuer_verified",
            },
        )
        assert response.status_code == 422, response.text
        denied = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "custody_document",
                "source_label": "Educator cannot manage evidence",
            },
        )
        assert denied.status_code == 403, denied.text

        expired, _ = _record_evidence_api(
            client,
            headers,
            family["id"],
            source_label="Historical expired evidence",
            expires_at="2026-02-01T00:00:00Z",
        )
        review_operation = str(uuid4())
        review = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{expired['resource']['id']}/review",
            headers=headers,
            json={
                "client_operation_id": review_operation,
                "expected_version": 1,
                "assessed_epistemic_status": "reported",
            },
        )
        assert review.status_code == 409, review.text
        assert review.json()["detail"]["code"] == "authority_evidence_expired"
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(
                    ChildcareCommandReceipt.client_operation_id.in_(
                        [UUID(rejected_operation), UUID(review_operation)]
                    )
                )
            ) == 0


@pytest.mark.parametrize("terminal", ["invalidate", "supersede"])
def test_evidence_terminal_transition_bumps_each_distinct_child_once_and_replays(
    tmp_path, monkeypatch, terminal: str
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client, f"Evidence{terminal.title()}")
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        family = _family(client, headers)
        person = _create_person(client, headers, family["id"])["resource"]
        children = [
            _child(client, headers, family["id"], "EvidenceOne"),
            _child(client, headers, family["id"], "EvidenceTwo"),
        ]
        target, _ = _record_evidence_api(client, headers, family["id"])
        target_review, _ = _review_evidence_api(
            client, reviewer_headers, family["id"], target["resource"]["id"]
        )
        assessment_id = target_review["resource"]["current_assessment"]["id"]
        _seed_authorization_dependencies_for_existing_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            actor_user_id=auth["user"]["id"],
            family_id=family["id"],
            child_ids=[child["id"] for child in children],
            person=person,
            evidence_id=target["resource"]["id"],
            evidence_assessment_id=assessment_id,
        )
        payload: dict = {
            "client_operation_id": str(uuid4()),
            "expected_version": 2,
        }
        if terminal == "invalidate":
            payload["reason_code"] = "document_revoked"
        else:
            replacement, _ = _record_evidence_api(
                client, headers, family["id"], source_label="Replacement evidence"
            )
            replacement_review, _ = _review_evidence_api(
                client,
                reviewer_headers,
                family["id"],
                replacement["resource"]["id"],
            )
            assert replacement_review["resource"]["valid_now"] is True
            payload["replacement_evidence_id"] = replacement["resource"]["id"]

        path = (
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{target['resource']['id']}/{terminal}"
        )
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["resource"]["lifecycle_status"] == (
            "invalidated" if terminal == "invalidate" else "superseded"
        )
        with application.state.database.session_factory() as session:
            first_revisions = dict(
                session.execute(
                    select(ChildAuthorityHead.child_id, ChildAuthorityHead.revision).where(
                        ChildAuthorityHead.child_id.in_(
                            [UUID(child["id"]) for child in children]
                        )
                    )
                ).all()
            )
        assert set(first_revisions.values()) == {2}

        replay = client.post(path, headers=headers, json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["receipt"] == response.json()["receipt"]
        with application.state.database.session_factory() as session:
            replay_revisions = dict(
                session.execute(
                    select(ChildAuthorityHead.child_id, ChildAuthorityHead.revision).where(
                        ChildAuthorityHead.child_id.in_(first_revisions)
                    )
                ).all()
            )
            assert replay_revisions == first_revisions
            terminal_action = (
                "family.authority.evidence.invalidated"
                if terminal == "invalidate"
                else "family.authority.evidence.superseded"
            )
            terminal_audits = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id
                        == UUID(auth["user"]["organization_id"]),
                        AuditEvent.entity_id == UUID(target["resource"]["id"]),
                        AuditEvent.action == terminal_action,
                    )
                )
            )
            terminal_realtime = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id
                        == UUID(auth["user"]["organization_id"]),
                        RealtimeEvent.entity_id == UUID(target["resource"]["id"]),
                        RealtimeEvent.event_type == terminal_action,
                    )
                )
            )
            assert len(terminal_audits) == 1
            assert terminal_realtime == []
            assert terminal_audits[0].details == {
                "operation_id": payload["client_operation_id"],
                "transition": (
                    "invalidated" if terminal == "invalidate" else "superseded"
                ),
                "affected_child_count": 2,
            }


@pytest.mark.parametrize("terminal", ["invalidate", "supersede"])
def test_evidence_terminal_transition_missing_head_rolls_back_then_exact_retry_succeeds(
    tmp_path, monkeypatch, terminal: str
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client, f"EvidenceMissing{terminal.title()}")
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        family = _family(client, headers)
        child = _child(client, headers, family["id"], "MissingHead")
        person = _create_person(client, headers, family["id"])["resource"]
        target, _ = _record_evidence_api(client, headers, family["id"])
        target_review, _ = _review_evidence_api(
            client, reviewer_headers, family["id"], target["resource"]["id"]
        )
        dependency = _seed_authorization_dependencies_for_existing_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            actor_user_id=auth["user"]["id"],
            family_id=family["id"],
            child_ids=[child["id"]],
            person=person,
            evidence_id=target["resource"]["id"],
            evidence_assessment_id=target_review["resource"]["current_assessment"]["id"],
            omit_head_for={child["id"]},
        )
        payload: dict = {
            "client_operation_id": str(uuid4()),
            "expected_version": 2,
        }
        if terminal == "invalidate":
            payload["reason_code"] = "authority_changed"
        else:
            replacement, _ = _record_evidence_api(
                client, headers, family["id"], source_label="Missing-head replacement"
            )
            _review_evidence_api(
                client,
                reviewer_headers,
                family["id"],
                replacement["resource"]["id"],
            )
            payload["replacement_evidence_id"] = replacement["resource"]["id"]
        path = (
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{target['resource']['id']}/{terminal}"
        )
        failed = client.post(path, headers=headers, json=payload)
        assert failed.status_code == 409, failed.text
        assert failed.json()["detail"]["code"] == "authority_head_missing"
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(FamilyAuthorityEvidenceAssessment)
                .where(
                    FamilyAuthorityEvidenceAssessment.evidence_id
                    == UUID(target["resource"]["id"])
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(
                    ChildcareCommandReceipt.client_operation_id
                    == UUID(payload["client_operation_id"])
                )
            ) == 0
            _, authorization_operation = dependency[child["id"]]
            session.add(
                ChildAuthorityHead(
                    organization_id=UUID(auth["user"]["organization_id"]),
                    family_id=UUID(family["id"]),
                    child_id=UUID(child["id"]),
                    revision=1,
                    created_operation_id=authorization_operation,
                    last_operation_id=authorization_operation,
                )
            )
            session.commit()
        repaired = client.post(path, headers=headers, json=payload)
        assert repaired.status_code == 200, repaired.text
        assert repaired.json()["replayed"] is False


def test_role_loss_blocks_person_and_terminal_evidence_commands_including_replays(
    tmp_path,
    monkeypatch,
) -> None:
    from app.basic import family_evidence_objects as evidence_service

    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client, "CurrentRoleCommands")
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        family = _family(client, owner_headers, "Current Role Command Family")
        people_path = f"/api/v1/families/{family['id']}/authority/people"

        create_payload = _person_payload()
        created_response = client.post(
            people_path,
            headers=owner_headers,
            json=create_payload,
        )
        assert created_response.status_code == 201, created_response.text
        active_person = created_response.json()["resource"]

        replace_person = _create_person(client, owner_headers, family["id"])["resource"]
        replace_payload = _replace_payload()
        replace_path = f"{people_path}/{replace_person['id']}/versions"
        replaced_response = client.post(
            replace_path,
            headers=owner_headers,
            json=replace_payload,
        )
        assert replaced_response.status_code == 200, replaced_response.text

        retire_person = _create_person(client, owner_headers, family["id"])["resource"]
        retire_payload = _retire_payload()
        retire_path = f"{people_path}/{retire_person['id']}/retire"
        retired_response = client.post(
            retire_path,
            headers=owner_headers,
            json=retire_payload,
        )
        assert retired_response.status_code == 200, retired_response.text

        invalidated, _ = _record_evidence_api(
            client,
            owner_headers,
            family["id"],
            source_label="Role-loss invalidation target",
        )
        _review_evidence_api(
            client,
            reviewer_headers,
            family["id"],
            invalidated["resource"]["id"],
        )
        invalidate_path = (
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{invalidated['resource']['id']}/invalidate"
        )
        invalidate_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 2,
            "reason_code": "authority_changed",
        }
        invalidated_response = client.post(
            invalidate_path,
            headers=owner_headers,
            json=invalidate_payload,
        )
        assert invalidated_response.status_code == 200, invalidated_response.text

        superseded, _ = _record_evidence_api(
            client,
            owner_headers,
            family["id"],
            source_label="Role-loss supersession target",
        )
        replacement, _ = _record_evidence_api(
            client,
            owner_headers,
            family["id"],
            source_label="Role-loss supersession replacement",
        )
        for evidence_id in (
            superseded["resource"]["id"],
            replacement["resource"]["id"],
        ):
            _review_evidence_api(
                client,
                reviewer_headers,
                family["id"],
                evidence_id,
            )
        supersede_path = (
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{superseded['resource']['id']}/supersede"
        )
        supersede_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 2,
            "replacement_evidence_id": replacement["resource"]["id"],
        }
        superseded_response = client.post(
            supersede_path,
            headers=owner_headers,
            json=supersede_payload,
        )
        assert superseded_response.status_code == 200, superseded_response.text

        original_recheck = evidence_service.require_current_family_authority_admin

        def lose_role_then_recheck(session, context):
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.id == context.membership.id
                )
            )
            assert membership is not None
            membership.status = "suspended"
            session.flush()
            original_recheck(session, context)

        monkeypatch.setattr(
            evidence_service,
            "require_current_family_authority_admin",
            lose_role_then_recheck,
        )

        new_create_payload = _person_payload()
        new_replace_payload = _replace_payload()
        new_retire_payload = _retire_payload()
        new_invalidate_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 3,
            "reason_code": "authority_changed",
        }
        new_supersede_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 3,
            "replacement_evidence_id": replacement["resource"]["id"],
        }
        blocked_requests = (
            (people_path, new_create_payload),
            (people_path, create_payload),
            (
                f"{people_path}/{active_person['id']}/versions",
                new_replace_payload,
            ),
            (replace_path, replace_payload),
            (
                f"{people_path}/{active_person['id']}/retire",
                new_retire_payload,
            ),
            (retire_path, retire_payload),
            (invalidate_path, new_invalidate_payload),
            (invalidate_path, invalidate_payload),
            (supersede_path, new_supersede_payload),
            (supersede_path, supersede_payload),
        )
        for path, payload in blocked_requests:
            response = client.post(path, headers=owner_headers, json=payload)
            assert response.status_code == 403, response.text
            assert response.json()["detail"] == {
                "code": "family_authority_access_revoked"
            }

        blocked_operation_ids = {
            UUID(payload["client_operation_id"])
            for payload in (
                new_create_payload,
                new_replace_payload,
                new_retire_payload,
                new_invalidate_payload,
                new_supersede_payload,
            )
        }
        with application.state.database.session_factory() as session:
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id
                    == UUID(auth["user"]["organization_id"]),
                    OrganizationMembership.user_id == UUID(auth["user"]["id"]),
                )
            )
            assert membership is not None and membership.status == "active"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.client_operation_id.in_(
                            blocked_operation_ids
                        )
                    )
                )
                == 0
            )
