"""Portable acceptance tests for the 0029A2 admin activation commands."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql

from alembic import command
from app.api.basic.dependencies import BasicContext
from app.basic.family_authority import (
    _bounded_summary_rows,
    get_child_authority_summary,
    get_family_authority_workspace,
)
from app.basic.family_authority_activation import (
    _consent_policy_for_decision_statement,
    _reviewed_evidence_assessments_statement,
    _reviewed_evidence_assets_statement,
    list_consent_policies,
)
from app.basic.models import (
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildConsentDecision,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityEvidenceObject,
    FamilyAuthorityEvidenceObjectAssessment,
    Organization,
    OrganizationMembership,
    Role,
    User,
)
from app.basic.security import hash_password
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct-password-123"


def test_append_only_activation_reads_do_not_request_postgres_row_locks() -> None:
    organization_id = uuid4()
    family_id = uuid4()
    evidence_ids = {uuid4(), uuid4()}
    statements = (
        _reviewed_evidence_assets_statement(
            organization_id,
            family_id,
            evidence_ids,
        ),
        _reviewed_evidence_assessments_statement(
            organization_id,
            family_id,
            evidence_ids,
        ),
        _consent_policy_for_decision_statement(
            organization_id,
            uuid4(),
            "off_site_activity",
        ),
    )

    for statement in statements:
        sql = str(statement.compile(dialect=postgresql.dialect())).upper()
        assert " FOR SHARE" not in sql
        assert " FOR UPDATE" not in sql


def _client(tmp_path, monkeypatch, revision: str = "head") -> tuple[TestClient, object]:
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
        jwt_secret="family-activation-api-test-secret-32-bytes",
    )
    application = create_app(settings)
    return TestClient(application), application


def _register(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"activation-{uuid4().hex}@example.com",
            "password": PASSWORD,
            "first_name": "Activation",
            "last_name": "Owner",
            "organization_name": "Activation Child Care",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _administrator(
    application,
    client: TestClient,
    organization_id: str,
    *,
    role_key: str = "administrator",
) -> tuple[str, dict[str, str]]:
    email = f"activation-{role_key}-{uuid4().hex}@example.com"
    password = "activation-admin-password-123"
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
            first_name="Activation",
            last_name="Administrator",
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
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return user_id, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _family_and_child(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict]:
    family_response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": "Activation Family",
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Guardian",
                "cell_phone": "780-555-0100",
            },
        },
    )
    assert family_response.status_code == 201, family_response.text
    family = family_response.json()
    child_response = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "first_name": "Authority",
            "last_name": "Child",
            "date_of_birth": "2024-01-01",
        },
    )
    assert child_response.status_code == 201, child_response.text
    return family, child_response.json()


def _authority_person(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    *,
    source: dict,
    first_name: str,
) -> dict:
    response = client.post(
        f"/api/v1/families/{family_id}/authority/people",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "source": source,
            "facts": {
                "first_name": first_name,
                "last_name": "Authority",
                "relationship_kind": "parent" if source["kind"] == "guardian" else "family_friend",
                "email": f"{first_name.lower()}@example.com",
                "primary_phone": "780-555-0111",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource"]


def _seed_reviewed_evidence(
    application,
    *,
    organization_id: str,
    family_id: str,
    recorder_id: str,
    reviewer_id: str,
    evidence_kind: str,
) -> tuple[str, str]:
    evidence_id = uuid4()
    assessment_id = uuid4()
    record_operation = uuid4()
    review_operation = uuid4()
    object_id = None
    upload_operation = None
    scan_operation = None
    document_kinds = {
        "identity_document",
        "custody_document",
        "court_order",
        "signed_consent",
        "signed_release_delegation",
        "other_document",
    }
    if evidence_kind in document_kinds:
        object_id = uuid4()
        upload_operation = uuid4()
        scan_operation = uuid4()
    organization_uuid = UUID(organization_id)
    family_uuid = UUID(family_id)
    with application.state.database.session_factory() as session:
        receipts = [
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=record_operation,
                    command_type="family.authority.evidence.record",
                    target_type="authority_evidence",
                    target_id=evidence_id,
                    request_hash=uuid4().hex * 2,
                    actor_user_id=UUID(recorder_id),
                    committed_version=1,
                    outcome={
                        "action_route": (
                            f"/families/{family_id}?authority_evidence_id={evidence_id}"
                        )
                    },
                ),
                ChildcareCommandReceipt(
                    id=uuid4(),
                    organization_id=organization_uuid,
                    client_operation_id=review_operation,
                    command_type="family.authority.evidence.review",
                    target_type="authority_evidence",
                    target_id=evidence_id,
                    request_hash=uuid4().hex * 2,
                    actor_user_id=UUID(reviewer_id),
                    committed_version=2,
                    outcome={
                        "action_route": (
                            f"/families/{family_id}?authority_evidence_id={evidence_id}"
                        )
                    },
                ),
            ]
        if object_id is not None and upload_operation is not None and scan_operation is not None:
            receipts.extend(
                [
                    ChildcareCommandReceipt(
                        id=uuid4(),
                        organization_id=organization_uuid,
                        client_operation_id=upload_operation,
                        command_type="family.authority.evidence_object.upload",
                        target_type="authority_evidence_object",
                        target_id=object_id,
                        request_hash=uuid4().hex * 2,
                        actor_user_id=UUID(recorder_id),
                        committed_version=1,
                        outcome={
                            "action_route": (
                                f"/families/{family_id}?authority_evidence_object_id={object_id}"
                            )
                        },
                    ),
                    ChildcareCommandReceipt(
                        id=uuid4(),
                        organization_id=organization_uuid,
                        client_operation_id=scan_operation,
                        command_type="family.authority.evidence_object.scan",
                        target_type="authority_evidence_object",
                        target_id=object_id,
                        request_hash=uuid4().hex * 2,
                        actor_user_id=UUID(reviewer_id),
                        committed_version=2,
                        outcome={
                            "action_route": (
                                f"/families/{family_id}?authority_evidence_object_id={object_id}"
                            )
                        },
                    ),
                ]
            )
        session.add_all(receipts)
        session.flush()
        storage_reference = None
        content_sha256 = None
        if object_id is not None and upload_operation is not None and scan_operation is not None:
            storage_reference = f"test/family-authority/{object_id}.pdf"
            content_sha256 = hashlib.sha256(b"portable activation document").hexdigest()
            session.add(
                FamilyAuthorityEvidenceObject(
                    id=object_id,
                    organization_id=organization_uuid,
                    family_id=family_uuid,
                    evidence_kind=evidence_kind,
                    object_version=1,
                    storage_reference=storage_reference,
                    media_type="application/pdf",
                    byte_size=28,
                    content_sha256=content_sha256,
                    original_filename="activation-proof.pdf",
                    status="clean",
                    uploaded_by_user_id=UUID(recorder_id),
                    uploaded_operation_id=upload_operation,
                )
            )
            session.flush()
            session.add_all(
                [
                    FamilyAuthorityEvidenceObjectAssessment(
                        id=uuid4(),
                        organization_id=organization_uuid,
                        family_id=family_uuid,
                        evidence_object_id=object_id,
                        version_number=1,
                        decision="quarantined",
                        actor_user_id=UUID(recorder_id),
                        operation_id=upload_operation,
                    ),
                    FamilyAuthorityEvidenceObjectAssessment(
                        id=uuid4(),
                        organization_id=organization_uuid,
                        family_id=family_uuid,
                        evidence_object_id=object_id,
                        version_number=2,
                        decision="clean",
                        scanner_engine="test-scanner",
                        scanner_version="1",
                        actor_user_id=UUID(reviewer_id),
                        operation_id=scan_operation,
                    ),
                ]
            )
            session.flush()
        session.add(
            FamilyAuthorityEvidence(
                id=evidence_id,
                organization_id=organization_uuid,
                family_id=family_uuid,
                evidence_kind=evidence_kind,
                source_label="Portable activation test evidence",
                evidence_object_id=object_id,
                storage_reference=storage_reference,
                media_type="application/pdf" if object_id is not None else None,
                byte_size=28 if object_id is not None else None,
                content_sha256=content_sha256,
                expires_at=datetime.now(UTC) + timedelta(days=120),
                recorded_by_user_id=UUID(recorder_id),
                created_operation_id=record_operation,
            )
        )
        session.flush()
        session.add(
            FamilyAuthorityEvidenceAssessment(
                id=assessment_id,
                organization_id=organization_uuid,
                family_id=family_uuid,
                evidence_id=evidence_id,
                version_number=2,
                decision="reviewed",
                assessed_epistemic_status=(
                    "reported" if evidence_kind == "guardian_attestation" else "document_observed"
                ),
                actor_user_id=UUID(reviewer_id),
                created_operation_id=review_operation,
            )
        )
        session.commit()
    return str(evidence_id), str(assessment_id)


def _window() -> tuple[str, str]:
    start = datetime.now(UTC) + timedelta(minutes=5)
    end = start + timedelta(days=30)
    return start.isoformat(), end.isoformat()


def _grant_payload(
    guardian: dict,
    recipient: dict,
    evidence: tuple[str, str],
    *,
    operation_id: str | None = None,
    expected_revision: int = 0,
) -> dict:
    start, end = _window()
    return {
        "client_operation_id": operation_id or str(uuid4()),
        "expected_authority_revision": expected_revision,
        "recipient_person_id": recipient["id"],
        "verification_policy_code": "government_photo_id",
        "grantor": {
            "person_id": guardian["id"],
            "person_version_id": guardian["current_version"]["id"],
            "authority_basis": "guardian_record",
            "basis_evidence_id": evidence[0],
            "basis_evidence_assessment_id": evidence[1],
        },
        "effective_from": start,
        "effective_until": end,
    }


def test_a1_workspace_and_activation_routes_fail_before_a2_orm_query(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, "0029A1")
    with client:
        _, headers = _register(client)
        family, child = _family_and_child(client, headers)
        workspace = client.get(f"/api/v1/families/{family['id']}/authority", headers=headers)
        assert workspace.status_code == 503
        assert workspace.json()["detail"]["code"] == "family_authority_activation_unavailable"
        summary = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=headers,
        )
        assert summary.status_code == 503
        assert summary.json()["detail"]["code"] == (
            "family_authority_activation_unavailable"
        )
        mutation = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_authority_revision": 0,
                "recipient_person_id": str(uuid4()),
                "verification_policy_code": "government_photo_id",
                "grantor": {
                    "person_id": str(uuid4()),
                    "person_version_id": str(uuid4()),
                    "authority_basis": "guardian_record",
                    "basis_evidence_id": str(uuid4()),
                    "basis_evidence_assessment_id": str(uuid4()),
                },
                "effective_from": _window()[0],
                "effective_until": _window()[1],
            },
        )
        assert mutation.status_code == 503
        assert mutation.json()["detail"]["code"] == "family_authority_activation_unavailable"


def test_a1_evidence_invalidation_does_not_query_a2_signer_columns(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch, "0029A1")
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
        )
        family, _ = _family_and_child(client, owner_headers)
        evidence_id, _ = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )

        response = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/invalidate",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "reason_code": "document_revoked",
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["resource"]["lifecycle_status"] == "invalidated"


def test_release_authorization_exact_retry_revoke_and_revision(tmp_path, monkeypatch) -> None:
    from app.basic import family_authority_activation as activation_service

    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Recipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        operation_id = str(uuid4())
        payload = _grant_payload(guardian, recipient, evidence, operation_id=operation_id)
        lock_order: list[str] = []
        original_boundary_lock = activation_service._lock_child_boundary
        original_evidence_read = activation_service._reviewed_evidence

        def traced_boundary_lock(session, organization_id, locked_child_id):
            lock_order.append("family_boundary_for_update")
            return original_boundary_lock(session, organization_id, locked_child_id)

        def traced_evidence_read(*args, **kwargs):
            lock_order.append("append_only_evidence_snapshot")
            return original_evidence_read(*args, **kwargs)

        monkeypatch.setattr(
            activation_service,
            "_lock_child_boundary",
            traced_boundary_lock,
        )
        monkeypatch.setattr(
            activation_service,
            "_reviewed_evidence",
            traced_evidence_read,
        )
        first = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=payload,
        )
        assert first.status_code == 201, first.text
        assert lock_order == [
            "family_boundary_for_update",
            "append_only_evidence_snapshot",
        ]
        first_body = first.json()
        assert first_body["replayed"] is False
        assert first_body["resource"]["authority_revision"] == 1
        authorization_id = first_body["resource"]["id"]
        assert first_body["receipt"]["action_route"] == (
            f"/children/{child['id']}?release_authorization_id={authorization_id}"
        )

        replay = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=payload,
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["receipt"] == first_body["receipt"]

        changed = dict(payload)
        changed["verification_policy_code"] = "documented_familiarity"
        reused = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=changed,
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "operation_reused"

        revoke_operation = str(uuid4())
        revoke_payload = {
            "client_operation_id": revoke_operation,
            "expected_version": 1,
            "expected_authority_revision": 1,
            "reason_code": "authority_withdrawn",
        }
        revoke_path = (
            f"/api/v1/children/{child['id']}/release-authorizations/{authorization_id}/revoke"
        )
        revoked = client.post(revoke_path, headers=owner_headers, json=revoke_payload)
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["resource"]["version"] == 2
        assert revoked.json()["resource"]["authority_revision"] == 2
        assert revoked.json()["resource"]["revocation_reason_code"] == ("authority_withdrawn")
        replayed_revoke = client.post(revoke_path, headers=owner_headers, json=revoke_payload)
        assert replayed_revoke.status_code == 200
        assert replayed_revoke.json()["replayed"] is True

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 1
            head = session.scalar(select(ChildAuthorityHead))
            assert head is not None and head.revision == 2
            assert session.scalar(select(func.count()).select_from(ChildReleaseAuthorization)) == 1


def test_child_authority_summary_is_private_bounded_and_exactly_focused(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, administrator_headers = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
        )
        _, educator_headers = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
            role_key="educator",
        )
        family, child = _family_and_child(client, owner_headers)
        other_child_response = client.post(
            "/api/v1/children",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Other",
                "last_name": "Child",
                "date_of_birth": "2023-01-01",
            },
        )
        assert other_child_response.status_code == 201, other_child_response.text
        other_child = other_child_response.json()
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Recipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        expired_payload = _grant_payload(guardian, recipient, evidence)
        expired_payload["effective_from"] = (
            datetime.now(UTC) - timedelta(days=2)
        ).isoformat()
        expired_payload["effective_until"] = (
            datetime.now(UTC) - timedelta(days=1)
        ).isoformat()
        expired = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=expired_payload,
        )
        assert expired.status_code == 201, expired.text
        assert expired.json()["resource"]["effective_status"] == "expired"

        granted = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=_grant_payload(
                guardian,
                recipient,
                evidence,
                expected_revision=1,
            ),
        )
        assert granted.status_code == 201, granted.text
        authorization = granted.json()["resource"]

        summary = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=owner_headers,
        )
        assert summary.status_code == 200, summary.text
        assert "private" in summary.headers["cache-control"]
        assert "no-store" in summary.headers["cache-control"]
        body = summary.json()
        assert body["schema_version"] == "child-authority-summary-v1"
        assert body["organization_id"] == auth["user"]["organization_id"]
        assert body["family_id"] == family["id"]
        assert body["child_id"] == child["id"]
        assert body["authority_revision"] == 2
        assert body["focus"] is None
        assert len(body["release_authorizations"]) == 1
        assert body["release_authorizations"][0]["recipient"] == {
            "id": recipient["id"],
            "display_name": "Recipient Authority",
            "relationship_kind": "family_friend",
            "status": "active",
        }
        serialized = summary.text
        for private_field in (
            "primary_phone",
            "email",
            "grantor",
            "basis_evidence_id",
            "confidential_reason",
            "content_text",
            "content_sha256",
        ):
            assert private_field not in serialized

        administrator_summary = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=administrator_headers,
        )
        assert administrator_summary.status_code == 200, administrator_summary.text

        denied = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=educator_headers,
        )
        assert denied.status_code == 403
        _, other_organization_headers = _register(client)
        cross_tenant = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=other_organization_headers,
        )
        assert cross_tenant.status_code == 404

        revoked = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations/{authorization['id']}/revoke",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "expected_authority_revision": 2,
                "reason_code": "authority_withdrawn",
            },
        )
        assert revoked.status_code == 200, revoked.text
        focused = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=owner_headers,
            params={
                "focus": "release_authorization",
                "record_id": authorization["id"],
            },
        )
        assert focused.status_code == 200, focused.text
        focused_body = focused.json()
        assert focused_body["release_authorizations"] == []
        assert focused_body["focus"]["id"] == authorization["id"]
        assert focused_body["focus"]["effective_status"] == "revoked"
        assert focused_body["focus"]["authority_revision"] == 3

        expired_focus = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=owner_headers,
            params={
                "focus": "release_authorization",
                "record_id": expired.json()["resource"]["id"],
            },
        )
        assert expired_focus.status_code == 200, expired_focus.text
        assert expired_focus.json()["focus"]["effective_status"] == "expired"
        assert expired_focus.json()["focus"]["authority_revision"] == 3

        wrong_child = client.get(
            f"/api/v1/children/{other_child['id']}/authority-summary",
            headers=owner_headers,
            params={
                "focus": "release_authorization",
                "record_id": authorization["id"],
            },
        )
        assert wrong_child.status_code == 404
        assert wrong_child.json()["detail"]["code"] == "child_authority_focus_not_found"
        malformed = client.get(
            f"/api/v1/children/{child['id']}/authority-summary"
            f"?focus=release_authorization&focus=release_rule&record_id={authorization['id']}",
            headers=owner_headers,
        )
        assert malformed.status_code == 422
        assert malformed.json()["detail"]["code"] == (
            "invalid_child_authority_summary_query"
        )


class _SummaryLimitStatement:
    def limit(self, value: int):
        assert value == 201
        return self


class _SummaryLimitSession:
    def scalars(self, _statement):
        return list(range(201))


def test_child_authority_summary_fails_closed_instead_of_truncating() -> None:
    with pytest.raises(HTTPException) as error:
        _bounded_summary_rows(
            _SummaryLimitSession(),
            _SummaryLimitStatement(),
            lane="release_authorizations",
        )
    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": "child_authority_summary_too_large",
        "lane": "release_authorizations",
    }


def test_child_authority_summary_query_count_is_constant_across_rows(
    tmp_path,
    monkeypatch,
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
        )
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )

        def add_authorization(index: int) -> None:
            recipient = _authority_person(
                client,
                owner_headers,
                family["id"],
                source={"kind": "manual"},
                first_name=f"Recipient{index:02d}",
            )
            evidence = _seed_reviewed_evidence(
                application,
                organization_id=auth["user"]["organization_id"],
                family_id=family["id"],
                recorder_id=auth["user"]["id"],
                reviewer_id=reviewer_id,
                evidence_kind="guardian_attestation",
            )
            response = client.post(
                f"/api/v1/children/{child['id']}/release-authorizations",
                headers=owner_headers,
                json=_grant_payload(
                    guardian,
                    recipient,
                    evidence,
                    expected_revision=index - 1,
                ),
            )
            assert response.status_code == 201, response.text

        def summary_query_count() -> tuple[int, int]:
            statements: list[str] = []

            def count_statement(_connection, _cursor, statement, *_args) -> None:
                statements.append(statement)

            engine = application.state.database.engine
            event.listen(engine, "before_cursor_execute", count_statement)
            try:
                response = client.get(
                    f"/api/v1/children/{child['id']}/authority-summary",
                    headers=owner_headers,
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_statement)
            assert response.status_code == 200, response.text
            return len(response.json()["release_authorizations"]), len(statements)

        add_authorization(1)
        small_rows, small_queries = summary_query_count()
        for index in range(2, 7):
            add_authorization(index)
        large_rows, large_queries = summary_query_count()

        assert (small_rows, large_rows) == (1, 6)
        assert large_queries == small_queries
        assert large_queries <= 20


def test_child_authority_summary_retains_retired_recipient_identity(
    tmp_path,
    monkeypatch,
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
        )
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="RetiredRecipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        granted = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=_grant_payload(guardian, recipient, evidence),
        )
        assert granted.status_code == 201, granted.text

        retired = client.post(
            f"/api/v1/families/{family['id']}/authority/people/{recipient['id']}/retire",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": recipient["version"],
            },
        )
        assert retired.status_code == 200, retired.text
        assert retired.json()["resource"]["status"] == "retired"

        summary = client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=owner_headers,
        )
        assert summary.status_code == 200, summary.text
        authorization = summary.json()["release_authorizations"][0]
        assert authorization["recipient"] == {
            "id": recipient["id"],
            "display_name": "RetiredRecipient Authority",
            "relationship_kind": "family_friend",
            "status": "retired",
        }


def test_child_authority_summary_rechecks_stale_leader_context(
    tmp_path,
    monkeypatch,
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        _, child = _family_and_child(client, owner_headers)
        user_id = UUID(auth["user"]["id"])
        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            user = session.get(User, user_id)
            organization = session.get(Organization, organization_id)
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == user_id,
                )
            )
            assert user is not None and organization is not None and membership is not None
            role = session.get(Role, membership.role_id)
            assert role is not None and role.key == "owner"
            stale_context = BasicContext(
                user=user,
                organization=organization,
                membership=membership,
                role=role,
            )

        with application.state.database.session_factory() as session:
            current = session.get(OrganizationMembership, membership.id)
            assert current is not None
            current.status = "suspended"
            session.commit()

        with (
            application.state.database.session_factory() as session,
            pytest.raises(HTTPException) as error,
        ):
            get_child_authority_summary(
                session,
                stale_context,
                UUID(child["id"]),
            )
        assert error.value.status_code == 403
        assert error.value.detail == {"code": "family_authority_access_revoked"}


def test_family_authority_reads_recheck_stale_membership_and_role_context(
    tmp_path,
    monkeypatch,
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        family, _ = _family_and_child(client, owner_headers)
        user_id = UUID(auth["user"]["id"])
        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            user = session.get(User, user_id)
            organization = session.get(Organization, organization_id)
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == user_id,
                )
            )
            assert user is not None and organization is not None and membership is not None
            role = session.get(Role, membership.role_id)
            educator_role = session.scalar(
                select(Role).where(
                    Role.organization_id == organization_id,
                    Role.key == "educator",
                )
            )
            assert role is not None and role.key == "owner"
            assert educator_role is not None
            stale_context = BasicContext(
                user=user,
                organization=organization,
                membership=membership,
                role=role,
            )
            membership_id = membership.id
            educator_role_id = educator_role.id

        for drift in ("suspended", "educator"):
            with application.state.database.session_factory() as session:
                current = session.get(OrganizationMembership, membership_id)
                assert current is not None
                current.status = "suspended" if drift == "suspended" else "active"
                if drift == "educator":
                    current.role_id = educator_role_id
                session.commit()

            for read in ("workspace", "policies"):
                with (
                    application.state.database.session_factory() as session,
                    pytest.raises(HTTPException) as error,
                ):
                    if read == "workspace":
                        get_family_authority_workspace(
                            session,
                            stale_context,
                            UUID(family["id"]),
                        )
                    else:
                        list_consent_policies(session, stale_context)
                assert error.value.status_code == 403
                assert error.value.detail == {
                    "code": "family_authority_access_revoked"
                }


def test_activation_maker_checker_failure_rolls_back_operation_and_head(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, reviewer_headers = _administrator(
            application, client, auth["user"]["organization_id"]
        )
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Recipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        operation_id = str(uuid4())
        response = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=reviewer_headers,
            json=_grant_payload(
                guardian,
                recipient,
                evidence,
                operation_id=operation_id,
            ),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == ("activation_maker_checker_required")
        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 0
            assert session.scalar(select(func.count()).select_from(ChildReleaseAuthorization)) == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(ChildcareCommandReceipt.client_operation_id == UUID(operation_id))
                )
                == 0
            )


def test_role_loss_at_commit_boundary_rolls_back_every_activation_write(
    tmp_path, monkeypatch
) -> None:
    from app.basic import family_authority_activation as activation_service

    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Recipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        operation_id = str(uuid4())
        original_recheck = activation_service.require_current_family_authority_admin

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
            activation_service,
            "require_current_family_authority_admin",
            lose_role_then_recheck,
        )
        response = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=_grant_payload(
                guardian,
                recipient,
                evidence,
                operation_id=operation_id,
            ),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "family_authority_access_revoked"
        with application.state.database.session_factory() as session:
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == UUID(auth["user"]["organization_id"]),
                    OrganizationMembership.user_id == UUID(auth["user"]["id"]),
                )
            )
            assert membership is not None and membership.status == "active"
            assert session.scalar(select(func.count()).select_from(ChildAuthorityHead)) == 0
            assert session.scalar(select(func.count()).select_from(ChildReleaseAuthorization)) == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(ChildcareCommandReceipt.client_operation_id == UUID(operation_id))
                )
                == 0
            )


def test_role_loss_blocks_every_activation_exact_replay(tmp_path, monkeypatch) -> None:
    from app.basic import family_authority_activation as activation_service

    client, application = _client(tmp_path, monkeypatch)
    with client:
        def post_with_target_before_head(path, payload, target_table):
            statements: list[str] = []

            def capture_statement(_connection, _cursor, statement, *_args) -> None:
                statements.append(
                    " ".join(statement.lower().replace('"', "").split())
                )

            engine = application.state.database.engine
            event.listen(engine, "before_cursor_execute", capture_statement)
            try:
                response = client.post(path, headers=owner_headers, json=payload)
            finally:
                event.remove(engine, "before_cursor_execute", capture_statement)

            receipt_index = next(
                index
                for index, statement in enumerate(statements)
                if statement.startswith("insert into childcare_command_receipts")
            )
            target_index = next(
                index
                for index, statement in enumerate(statements)
                if statement.startswith(f"insert into {target_table}")
            )
            head_index = next(
                index
                for index, statement in enumerate(statements)
                if statement.startswith("insert into child_authority_heads")
                or statement.startswith("update child_authority_heads")
            )
            assert receipt_index < target_index < head_index
            return response

        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="ReplayGuardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="ReplayRecipient",
        )
        guardian_evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )

        grant_path = f"/api/v1/children/{child['id']}/release-authorizations"
        grant_payload = _grant_payload(guardian, recipient, guardian_evidence)
        granted = post_with_target_before_head(
            grant_path,
            grant_payload,
            "child_release_authorizations",
        )
        assert granted.status_code == 201, granted.text
        authorization_id = granted.json()["resource"]["id"]
        revoke_authorization_path = f"{grant_path}/{authorization_id}/revoke"
        revoke_authorization_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "expected_authority_revision": 1,
            "reason_code": "authority_withdrawn",
        }
        revoked_authorization = client.post(
            revoke_authorization_path,
            headers=owner_headers,
            json=revoke_authorization_payload,
        )
        assert revoked_authorization.status_code == 200, revoked_authorization.text

        rule_path = f"/api/v1/children/{child['id']}/release-rules"
        rule_start, rule_end = _window()
        rule_payload = {
            "client_operation_id": str(uuid4()),
            "expected_authority_revision": 2,
            "rule_kind": "deny",
            "scope": {"kind": "all_recipients"},
            "directing_person": {
                "person_id": guardian["id"],
                "person_version_id": guardian["current_version"]["id"],
            },
            "authority_basis_code": "guardian_record",
            "basis_evidence_id": guardian_evidence[0],
            "basis_evidence_assessment_id": guardian_evidence[1],
            "confidential_reason": "Exact-replay authorization test",
            "effective_from": rule_start,
            "effective_until": rule_end,
        }
        created_rule = post_with_target_before_head(
            rule_path,
            rule_payload,
            "child_release_rules",
        )
        assert created_rule.status_code == 201, created_rule.text
        rule_id = created_rule.json()["resource"]["id"]
        revoke_rule_path = f"{rule_path}/{rule_id}/revoke"
        revoke_rule_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "expected_authority_revision": 3,
            "reason_code": "safety_change",
        }
        revoked_rule = client.post(
            revoke_rule_path,
            headers=owner_headers,
            json=revoke_rule_payload,
        )
        assert revoked_rule.status_code == 200, revoked_rule.text

        policy_start, policy_end = _window()
        policy_path = "/api/v1/consent-policies"
        policy_payload = {
            "client_operation_id": str(uuid4()),
            "purpose_code": "off_site_activity",
            "version_number": 1,
            "title": "Exact replay policy",
            "content_text": "I authorize this activity.",
            "signer_authority_requirement": "guardian_record",
            "effective_from": policy_start,
            "effective_until": policy_end,
        }
        published = client.post(policy_path, headers=owner_headers, json=policy_payload)
        assert published.status_code == 201, published.text

        decision_evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="signed_consent",
        )
        decision_start = datetime.fromisoformat(policy_start) + timedelta(minutes=1)
        decision_end = decision_start + timedelta(days=20)
        consent_path = f"/api/v1/children/{child['id']}/consents"
        consent_payload = {
            "client_operation_id": str(uuid4()),
            "expected_authority_revision": 4,
            "purpose_code": "off_site_activity",
            "policy_version_id": published.json()["resource"]["id"],
            "signer": {
                "person_id": guardian["id"],
                "person_version_id": guardian["current_version"]["id"],
                "authority_basis": "guardian_record",
                "authority_evidence_id": guardian_evidence[0],
                "authority_evidence_assessment_id": guardian_evidence[1],
            },
            "evidence_id": decision_evidence[0],
            "evidence_assessment_id": decision_evidence[1],
            "decision": "granted",
            "scope": {"kind": "policy"},
            "effective_from": decision_start.isoformat(),
            "effective_until": decision_end.isoformat(),
        }
        recorded_consent = post_with_target_before_head(
            consent_path,
            consent_payload,
            "child_consent_decisions",
        )
        assert recorded_consent.status_code == 201, recorded_consent.text
        consent_id = recorded_consent.json()["resource"]["id"]
        withdraw_consent_path = f"{consent_path}/{consent_id}/withdraw"
        withdraw_consent_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "expected_authority_revision": 5,
            "reason_code": "signer_withdrew",
        }
        withdrawn_consent = client.post(
            withdraw_consent_path,
            headers=owner_headers,
            json=withdraw_consent_payload,
        )
        assert withdrawn_consent.status_code == 200, withdrawn_consent.text

        original_recheck = activation_service.require_current_family_authority_admin

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
            activation_service,
            "require_current_family_authority_admin",
            lose_role_then_recheck,
        )
        exact_replays = (
            (grant_path, grant_payload, 201),
            (revoke_authorization_path, revoke_authorization_payload, 200),
            (rule_path, rule_payload, 201),
            (revoke_rule_path, revoke_rule_payload, 200),
            (policy_path, policy_payload, 201),
            (consent_path, consent_payload, 201),
            (withdraw_consent_path, withdraw_consent_payload, 200),
        )
        for path, payload, previous_status in exact_replays:
            response = client.post(path, headers=owner_headers, json=payload)
            assert response.status_code == 403, (previous_status, response.text)
            assert response.json()["detail"] == {
                "code": "family_authority_access_revoked"
            }


def test_release_rule_matrix_exact_retry_and_one_way_revocation(tmp_path, monkeypatch) -> None:
    from app.basic import family_authority_activation as activation_service

    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Director",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        start, end = _window()
        operation_id = str(uuid4())
        payload = {
            "client_operation_id": operation_id,
            "expected_authority_revision": 0,
            "rule_kind": "deny",
            "scope": {"kind": "all_recipients"},
            "directing_person": {
                "person_id": guardian["id"],
                "person_version_id": guardian["current_version"]["id"],
            },
            "authority_basis_code": "guardian_record",
            "basis_evidence_id": evidence[0],
            "basis_evidence_assessment_id": evidence[1],
            "confidential_reason": "Private reviewed release restriction",
            "effective_from": start,
            "effective_until": end,
        }
        boundary_lock_calls: list[UUID] = []
        original_boundary_lock = activation_service._lock_child_boundary

        def counted_boundary_lock(session, organization_id, locked_child_id):
            boundary_lock_calls.append(locked_child_id)
            return original_boundary_lock(session, organization_id, locked_child_id)

        monkeypatch.setattr(
            activation_service,
            "_lock_child_boundary",
            counted_boundary_lock,
        )
        unsupported = dict(payload)
        unsupported["client_operation_id"] = str(uuid4())
        unsupported["rule_kind"] = "supervised_only"
        denied = client.post(
            f"/api/v1/children/{child['id']}/release-rules",
            headers=owner_headers,
            json=unsupported,
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "release_rule_kind_not_activatable"
        assert boundary_lock_calls == []

        created = client.post(
            f"/api/v1/children/{child['id']}/release-rules",
            headers=owner_headers,
            json=payload,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["resource"]["safe_explanation_code"] == "release_restricted"
        assert body["resource"]["authority_revision"] == 1
        assert body["replayed"] is False
        assert boundary_lock_calls == [UUID(child["id"])]
        replay = client.post(
            f"/api/v1/children/{child['id']}/release-rules",
            headers=owner_headers,
            json=payload,
        )
        assert replay.status_code == 201
        assert replay.json()["replayed"] is True
        assert boundary_lock_calls == [UUID(child["id"])]

        rule_id = body["resource"]["id"]
        revoke_path = f"/api/v1/children/{child['id']}/release-rules/{rule_id}/revoke"
        revoked = client.post(
            revoke_path,
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "expected_authority_revision": 1,
                "reason_code": "safety_change",
            },
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["resource"]["version"] == 2
        assert revoked.json()["resource"]["authority_revision"] == 2
        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildReleaseRule)) == 1
            head = session.scalar(select(ChildAuthorityHead))
            assert head is not None and head.revision == 2


def test_release_delegation_cannot_be_transitively_granted_by_a_delegate(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="OriginalGuardian",
        )
        delegate = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Delegate",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "manual"},
            first_name="Recipient",
        )
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="signed_release_delegation",
        )
        delegate_payload = _grant_payload(delegate, recipient, evidence)
        delegate_payload["grantor"]["authority_basis"] = "reviewed_delegation_evidence"
        rejected = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=delegate_payload,
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "authority_basis_not_activatable"

        guardian_payload = _grant_payload(guardian, recipient, evidence)
        guardian_payload["grantor"]["authority_basis"] = "reviewed_delegation_evidence"
        granted = client.post(
            f"/api/v1/children/{child['id']}/release-authorizations",
            headers=owner_headers,
            json=guardian_payload,
        )
        assert granted.status_code == 201, granted.text
        assert granted.json()["resource"]["grantor"]["authority_basis"] == (
            "reviewed_delegation_evidence"
        )
        assert granted.json()["resource"]["authority_revision"] == 1


def test_concurrent_different_operations_cannot_double_spend_child_revision(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Guardian",
        )
        recipients = [
            _authority_person(
                client,
                owner_headers,
                family["id"],
                source={"kind": "manual"},
                first_name=f"Recipient{index}",
            )
            for index in range(2)
        ]
        evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        payloads = [_grant_payload(guardian, recipient, evidence) for recipient in recipients]

        def submit(payload: dict):
            return client.post(
                f"/api/v1/children/{child['id']}/release-authorizations",
                headers=owner_headers,
                json=payload,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(submit, payloads))
        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json()["detail"]["code"] == "authority_revision_changed"
        with application.state.database.session_factory() as session:
            head = session.scalar(select(ChildAuthorityHead))
            assert head is not None and head.revision == 1
            assert session.scalar(select(func.count()).select_from(ChildReleaseAuthorization)) == 1


def test_policy_content_is_server_derived_and_consent_tracks_both_evidence_lanes(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        reviewer_id, _ = _administrator(application, client, auth["user"]["organization_id"])
        family, child = _family_and_child(client, owner_headers)
        guardian = _authority_person(
            client,
            owner_headers,
            family["id"],
            source={"kind": "guardian", "guardian_id": family["guardians"][0]["id"]},
            first_name="Signer",
        )
        guardian_evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="guardian_attestation",
        )
        decision_evidence = _seed_reviewed_evidence(
            application,
            organization_id=auth["user"]["organization_id"],
            family_id=family["id"],
            recorder_id=auth["user"]["id"],
            reviewer_id=reviewer_id,
            evidence_kind="signed_consent",
        )
        policy_start, policy_end = _window()
        content_text = "I authorize the named off-site activity under this policy."
        published = client.post(
            "/api/v1/consent-policies",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "purpose_code": "off_site_activity",
                "version_number": 1,
                "title": "Off-site activity consent",
                "content_text": content_text,
                "signer_authority_requirement": "guardian_record",
                "effective_from": policy_start,
                "effective_until": policy_end,
            },
        )
        assert published.status_code == 201, published.text
        policy = published.json()["resource"]
        assert policy["content_text"] == content_text
        assert policy["content_reference"] == f"/consent-policies/{policy['id']}"
        assert policy["content_sha256"] == hashlib.sha256(content_text.encode("utf-8")).hexdigest()
        listed = client.get("/api/v1/consent-policies", headers=owner_headers)
        assert listed.status_code == 200
        assert listed.json() == [policy]

        decision_start = datetime.fromisoformat(policy_start) + timedelta(minutes=1)
        decision_end = decision_start + timedelta(days=20)
        recorded = client.post(
            f"/api/v1/children/{child['id']}/consents",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_authority_revision": 0,
                "purpose_code": "off_site_activity",
                "policy_version_id": policy["id"],
                "signer": {
                    "person_id": guardian["id"],
                    "person_version_id": guardian["current_version"]["id"],
                    "authority_basis": "guardian_record",
                    "authority_evidence_id": guardian_evidence[0],
                    "authority_evidence_assessment_id": guardian_evidence[1],
                },
                "evidence_id": decision_evidence[0],
                "evidence_assessment_id": decision_evidence[1],
                "decision": "granted",
                "scope": {"kind": "policy"},
                "effective_from": decision_start.isoformat(),
                "effective_until": decision_end.isoformat(),
            },
        )
        assert recorded.status_code == 201, recorded.text
        decision = recorded.json()["resource"]
        assert decision["signer"]["authority_evidence_id"] == guardian_evidence[0]
        assert decision["evidence_id"] == decision_evidence[0]
        assert decision["authority_revision"] == 1

        invalidated = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{guardian_evidence[0]}/invalidate",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "reason_code": "document_revoked",
            },
        )
        assert invalidated.status_code == 200, invalidated.text
        assert invalidated.json()["resource"]["lifecycle_status"] == "invalidated"
        workspace = client.get(
            f"/api/v1/families/{family['id']}/authority",
            headers=owner_headers,
        )
        assert workspace.status_code == 200, workspace.text
        projected_decision = workspace.json()["children"][0]["consent_decisions"][0]
        assert projected_decision["effective_status"] == (
            "supporting_evidence_unavailable"
        )
        assert projected_decision["effective_now"] is False
        with application.state.database.session_factory() as session:
            head = session.scalar(
                select(ChildAuthorityHead).where(
                    ChildAuthorityHead.child_id == UUID(child["id"])
                )
            )
            assert head is not None and head.revision == 2

        withdrawn = client.post(
            f"/api/v1/children/{child['id']}/consents/{decision['id']}/withdraw",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "expected_authority_revision": 2,
                "reason_code": "signer_withdrew",
            },
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["resource"]["version"] == 2
        assert withdrawn.json()["resource"]["authority_revision"] == 3
        assert withdrawn.json()["resource"]["effective_status"] == "withdrawn"
        assert withdrawn.json()["resource"]["effective_now"] is False
        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildConsentDecision)) == 1
