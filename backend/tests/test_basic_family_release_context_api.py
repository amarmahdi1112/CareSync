"""Portable API and repository acceptance proofs for 0029B release context.

These tests deliberately exercise the real SQLite repository.  The PostgreSQL
projection has separate migration/role tests; both paths terminate at the same
strict input schema and pure composer.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from alembic import command
from app.basic.family_release_context import (
    ReleaseContextInconsistentError,
    ReleaseContextReevaluationRequired,
)
from app.basic.family_release_context_repository import (
    ReleaseContextRepositoryError,
    _facility_service_date,
)
from app.basic.models import (
    AttendanceDay,
    AttendanceInterval,
    AuditEvent,
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    Facility,
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
A2 = "0029A2_authority_activation"
B = "0029B_release_context"


def test_release_context_service_date_uses_facility_timezone() -> None:
    instant = datetime(2026, 1, 1, 1, 30, tzinfo=UTC)
    assert _facility_service_date(instant, "America/Edmonton") == date(2025, 12, 31)
    assert _facility_service_date(instant, "Asia/Tokyo") == date(2026, 1, 1)


def test_release_context_invalid_facility_timezone_fails_closed() -> None:
    with pytest.raises(ReleaseContextRepositoryError) as caught:
        _facility_service_date(datetime(2026, 1, 1, tzinfo=UTC), "Not/A-Timezone")
    assert caught.value.code == "release_context_inconsistent"
    assert caught.value.status_code == 409


def _migrate(tmp_path, monkeypatch, revision: str = B) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def _application(database_path: Path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="release-context-api-test-secret-32-bytes",
    )
    return create_app(settings)


def _client(tmp_path, monkeypatch, revision: str = B):
    database_path = _migrate(tmp_path, monkeypatch, revision)
    application = _application(database_path)
    return TestClient(application), application, database_path


def _register(client: TestClient, *, suffix: str = "owner") -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"release-context-{suffix}-{uuid4().hex}@example.com",
            "password": PASSWORD,
            "first_name": "Release",
            "last_name": "Owner",
            "organization_name": f"Release Context {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _administrator(
    application,
    client: TestClient,
    organization_id: str,
) -> tuple[str, dict[str, str]]:
    email = f"release-context-admin-{uuid4().hex}@example.com"
    password = "release-context-admin-password-123"
    with application.state.database.session_factory() as session:
        role = session.scalar(
            select(Role).where(
                Role.organization_id == UUID(organization_id),
                Role.key == "administrator",
            )
        )
        assert role is not None
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            first_name="Release",
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


def _facility_tree(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict, list[dict]]:
    facility_response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": "Release Context Centre",
            "status": "active",
            "licensed_capacity": 40,
            "timezone": "America/Edmonton",
        },
    )
    assert facility_response.status_code == 201, facility_response.text
    facility = facility_response.json()
    program_response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "name": "Release Context Daycare",
            "program_type": "daycare",
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program_response.status_code == 201, program_response.text
    program = program_response.json()
    rooms = []
    for suffix in ("North", "South"):
        response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"Release {suffix}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert response.status_code == 201, response.text
        rooms.append(response.json())
    return facility, program, rooms


def _family_child_and_enrollment(
    client: TestClient,
    headers: dict[str, str],
    facility: dict,
    room: dict,
) -> tuple[dict, dict]:
    family_response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": "Private Release Family",
            "additional_notes": "CONFIDENTIAL-FAMILY-NOTE-MUST-NOT-LEAK",
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Guardian",
                "email": "guardian-private@example.com",
                "cell_phone": "780-555-0199",
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
            "first_name": "Release",
            "last_name": "Child",
            "date_of_birth": "2023-01-01",
            "allergies": "CONFIDENTIAL-ALLERGY-MUST-NOT-LEAK",
            "health_care_number": "CONFIDENTIAL-HCN-MUST-NOT-LEAK",
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()
    enrollment_response = client.post(
        f"/api/v1/children/{child['id']}/enrollments",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "start_date": date.today().isoformat(),
        },
    )
    assert enrollment_response.status_code == 201, enrollment_response.text
    enrollment = enrollment_response.json()
    approval_response = client.post(
        f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": enrollment["version"],
            "room_id": room["id"],
            "effective_date": date.today().isoformat(),
        },
    )
    assert approval_response.status_code == 200, approval_response.text
    return family, child


def _clock_in(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
) -> dict:
    response = client.post(
        "/api/v1/staff/self/shifts/clock-in",
        headers=headers,
        json={"facility_id": facility_id, "operation_id": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _clock_out(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
) -> dict:
    response = client.post(
        "/api/v1/staff/self/shifts/clock-out",
        headers=headers,
        json={"facility_id": facility_id, "operation_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _check_in_child(
    client: TestClient,
    headers: dict[str, str],
    child_id: str,
    facility_id: str,
) -> dict:
    response = client.post(
        "/api/v1/attendance/check-in",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "child_id": child_id,
            "facility_id": facility_id,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _token_from_url(value: str) -> str:
    values = parse_qs(urlparse(value).fragment).get("token", [])
    assert len(values) == 1
    return values[0]


def _educator(
    client: TestClient,
    owner_headers: dict[str, str],
    *,
    facility_id: str,
    room_id: str,
    suffix: str,
) -> tuple[dict[str, str], str]:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    educator_role = next(role for role in workspace.json()["roles"] if role["key"] == "educator")
    email = f"release-educator-{suffix}-{uuid4().hex}@example.com"
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": email,
            "first_name": "Room",
            "last_name": "Educator",
            "role_id": educator_role["id"],
            "assigned_facility_ids": [facility_id],
            "assigned_room_ids": [room_id],
        },
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": _token_from_url(invitation.json()["activation_url"]), "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    _clock_in(client, headers, facility_id)
    return headers, educator_role["id"]


def _authority_person(
    client: TestClient,
    headers: dict[str, str],
    family: dict,
    *,
    guardian: bool,
    first_name: str,
) -> dict:
    source = (
        {"kind": "guardian", "guardian_id": family["guardians"][0]["id"]}
        if guardian
        else {"kind": "manual"}
    )
    response = client.post(
        f"/api/v1/families/{family['id']}/authority/people",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "source": source,
            "facts": {
                "first_name": first_name,
                "last_name": "Authority",
                "preferred_name": f"{first_name} Preferred",
                "relationship_kind": "parent" if guardian else "family_friend",
                "email": f"{first_name.lower()}-private@example.com",
                "primary_phone": "780-555-0111",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource"]


def _reviewed_guardian_evidence(
    client: TestClient,
    owner_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    family_id: str,
) -> tuple[str, str]:
    recorded = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "evidence_kind": "guardian_attestation",
            "source_label": "CONFIDENTIAL-EVIDENCE-LABEL-MUST-NOT-LEAK",
            "captured_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        },
    )
    assert recorded.status_code == 201, recorded.text
    evidence = recorded.json()["resource"]
    reviewed = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{evidence['id']}/review",
        headers=reviewer_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": evidence["version"],
            "assessed_epistemic_status": "reported",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_resource = reviewed.json()["resource"]
    return reviewed_resource["id"], reviewed_resource["current_assessment"]["id"]


def _window() -> tuple[str, str]:
    now = datetime.now(UTC)
    return (now - timedelta(minutes=1)).isoformat(), (now + timedelta(days=30)).isoformat()


def _grant(
    client: TestClient,
    owner_headers: dict[str, str],
    child_id: str,
    guardian: dict,
    recipient: dict,
    evidence: tuple[str, str],
    *,
    expected_revision: int = 0,
    policy: str = "government_photo_id_or_documented_familiarity",
) -> dict:
    effective_from, effective_until = _window()
    response = client.post(
        f"/api/v1/children/{child_id}/release-authorizations",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_authority_revision": expected_revision,
            "recipient_person_id": recipient["id"],
            "verification_policy_code": policy,
            "grantor": {
                "person_id": guardian["id"],
                "person_version_id": guardian["current_version"]["id"],
                "authority_basis": "guardian_record",
                "basis_evidence_id": evidence[0],
                "basis_evidence_assessment_id": evidence[1],
            },
            "effective_from": effective_from,
            "effective_until": effective_until,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource"]


def _rule(
    client: TestClient,
    owner_headers: dict[str, str],
    child_id: str,
    guardian: dict,
    evidence: tuple[str, str],
    *,
    expected_revision: int,
    kind: str = "deny",
) -> dict:
    effective_from, effective_until = _window()
    response = client.post(
        f"/api/v1/children/{child_id}/release-rules",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_authority_revision": expected_revision,
            "rule_kind": kind,
            "scope": {"kind": "all_recipients"},
            "directing_person": {
                "person_id": guardian["id"],
                "person_version_id": guardian["current_version"]["id"],
            },
            "authority_basis_code": "guardian_record",
            "basis_evidence_id": evidence[0],
            "basis_evidence_assessment_id": evidence[1],
            "confidential_reason": "CONFIDENTIAL-RULE-REASON-MUST-NOT-LEAK",
            "effective_from": effective_from,
            "effective_until": effective_until,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource"]


@dataclass
class Scenario:
    client: TestClient
    application: object
    auth: dict
    owner_headers: dict[str, str]
    admin_headers: dict[str, str]
    facility: dict
    program: dict
    rooms: list[dict]
    family: dict
    child: dict
    attendance: dict

    @property
    def path(self) -> str:
        return (
            f"/api/v1/children/{self.child['id']}/release-context"
            f"?facility_id={self.facility['id']}"
        )


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    client, application, _ = _client(tmp_path, monkeypatch)
    with client:
        assert application.state.family_authority_activation_enabled is True
        assert application.state.family_authority_release_context_enabled is True
        auth, owner_headers = _register(client)
        _, admin_headers = _administrator(
            application,
            client,
            auth["user"]["organization_id"],
        )
        facility, program, rooms = _facility_tree(client, owner_headers)
        family, child = _family_child_and_enrollment(
            client, owner_headers, facility, rooms[0]
        )
        _clock_in(client, owner_headers, facility["id"])
        attendance = _check_in_child(
            client, owner_headers, child["id"], facility["id"]
        )
        yield Scenario(
            client=client,
            application=application,
            auth=auth,
            owner_headers=owner_headers,
            admin_headers=admin_headers,
            facility=facility,
            program=program,
            rooms=rooms,
            family=family,
            child=child,
            attendance=attendance,
        )


@pytest.mark.parametrize("damage", ["trigger", "permission"])
def test_runtime_gate_rejects_partial_b_without_disabling_a2(
    tmp_path,
    monkeypatch,
    damage: str,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    if damage == "permission":
        # Roles are organization-local. Create one disposable tenant so the
        # detector sees a concrete damaged system-role permission.
        bootstrap = _application(database_path)
        with TestClient(bootstrap) as bootstrap_client:
            _register(bootstrap_client, suffix="damaged-runtime-role")
    with sqlite3.connect(database_path) as connection:
        if damage == "trigger":
            connection.execute(
                "DROP TRIGGER child_authority_heads_release_context_update"
            )
        else:
            row = connection.execute(
                "SELECT id,permissions FROM roles WHERE is_system=1 AND key='educator'"
            ).fetchone()
            assert row is not None
            permissions = json.loads(row[1])
            permissions.remove("release:read")
            connection.execute(
                "UPDATE roles SET permissions=? WHERE id=?",
                (json.dumps(permissions, separators=(",", ":")), row[0]),
            )
        connection.commit()
    application = _application(database_path)
    with TestClient(application):
        assert application.state.family_authority_enabled is True
        assert application.state.family_authority_activation_enabled is True
        assert application.state.family_authority_release_context_enabled is False


def test_a2_only_route_fails_503_before_projection_or_request_shape(
    tmp_path,
    monkeypatch,
) -> None:
    from app.api.basic import family_release_context as route_module

    client, application, _ = _client(tmp_path, monkeypatch, A2)
    calls = 0

    def forbidden_projection(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("A2-only route reached the B projection")

    monkeypatch.setattr(route_module, "load_release_context_input", forbidden_projection)
    with client:
        _, headers = _register(client, suffix="a2-gate")
        response = client.request(
            "GET",
            "/api/v1/children/not-a-uuid/release-context?unexpected=value",
            headers=headers,
            content=b'{"must":"not-parse"}',
        )
        assert application.state.family_authority_activation_enabled is True
        assert application.state.family_authority_release_context_enabled is False
        # FastAPI parses path parameters before entering the route, so use a
        # valid child UUID to prove the application gate ordering as well.
        valid = client.request(
            "GET",
            "/api/v1/children/00000000-0000-0000-0000-000000000001/release-context"
            "?unexpected=value",
            headers=headers,
            content=b'{"must":"not-parse"}',
        )
    assert response.status_code == 422
    assert valid.status_code == 503
    assert valid.json() == {
        "detail": {"code": "family_authority_release_context_unavailable"}
    }
    assert calls == 0


def test_strict_query_and_body_reject_before_repository(
    scenario: Scenario,
    monkeypatch,
) -> None:
    from app.api.basic import family_release_context as route_module

    calls = 0

    def forbidden_projection(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("invalid request reached repository")

    monkeypatch.setattr(route_module, "load_release_context_input", forbidden_projection)
    base = f"/api/v1/children/{scenario.child['id']}/release-context"
    cases = [
        base,
        f"{base}?facility_id=not-a-uuid",
        f"{base}?other={scenario.facility['id']}",
        f"{base}?facility_id={scenario.facility['id']}&other=value",
        f"{base}?facility_id={scenario.facility['id']}&facility_id={scenario.facility['id']}",
    ]
    for path in cases:
        response = scenario.client.get(path, headers=scenario.owner_headers)
        assert response.status_code == 422, response.text
        assert response.json() == {
            "detail": {"code": "invalid_release_context_query"}
        }
    body_response = scenario.client.request(
        "GET",
        scenario.path,
        headers=scenario.owner_headers,
        content=b"{}",
    )
    assert body_response.status_code == 422, body_response.text
    assert body_response.json() == {
        "detail": {"code": "release_context_request_body_not_allowed"}
    }
    assert calls == 0


def _write_counts(application) -> dict[str, int]:
    with application.state.database.session_factory() as session:
        return {
            "audit": session.scalar(select(func.count()).select_from(AuditEvent)),
            "realtime": session.scalar(select(func.count()).select_from(RealtimeEvent)),
            "receipt": session.scalar(
                select(func.count()).select_from(ChildcareCommandReceipt)
            ),
            "head": session.scalar(select(func.count()).select_from(ChildAuthorityHead)),
            "authorization": session.scalar(
                select(func.count()).select_from(ChildReleaseAuthorization)
            ),
            "rule": session.scalar(select(func.count()).select_from(ChildReleaseRule)),
        }


def _assert_private_headers(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["vary"] == "Authorization, X-Organization-ID"


def test_missing_head_is_bounded_private_and_strictly_read_only(
    scenario: Scenario,
) -> None:
    before = _write_counts(scenario.application)
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    after = _write_counts(scenario.application)

    assert response.status_code == 200, response.text
    _assert_private_headers(response)
    assert before == after
    body = response.json()
    assert set(body) == {
        "schema_version",
        "decision_policy_version",
        "organization_id",
        "facility_id",
        "room_id",
        "child_id",
        "attendance_day_id",
        "attendance_interval_id",
        "staff_shift_id",
        "evaluated_at",
        "expires_at",
        "fresh_for_ms",
        "authority_revision",
        "restriction_digest_sha256",
        "decision",
        "blockers",
        "eligible_recipients",
    }
    assert body["schema_version"] == "release-context-v1"
    assert body["decision_policy_version"] == "release-context-v1"
    assert body["decision"] == "blocked"
    assert body["blockers"] == ["authority_not_reviewed"]
    assert body["eligible_recipients"] == []
    assert body["authority_revision"] == 0
    assert 1 <= body["fresh_for_ms"] <= 30_000
    serialized = response.text
    for secret in (
        "CONFIDENTIAL-FAMILY-NOTE-MUST-NOT-LEAK",
        "CONFIDENTIAL-ALLERGY-MUST-NOT-LEAK",
        "CONFIDENTIAL-HCN-MUST-NOT-LEAK",
        "guardian-private@example.com",
        "780-555-0199",
    ):
        assert secret not in serialized


def _activate_recipient(
    scenario: Scenario,
    *,
    policy: str = "government_photo_id_or_documented_familiarity",
):
    guardian = _authority_person(
        scenario.client,
        scenario.owner_headers,
        scenario.family,
        guardian=True,
        first_name="Guardian",
    )
    recipient = _authority_person(
        scenario.client,
        scenario.owner_headers,
        scenario.family,
        guardian=False,
        first_name="Recipient",
    )
    evidence = _reviewed_guardian_evidence(
        scenario.client,
        scenario.owner_headers,
        scenario.admin_headers,
        scenario.family["id"],
    )
    authorization = _grant(
        scenario.client,
        scenario.owner_headers,
        scenario.child["id"],
        guardian,
        recipient,
        evidence,
        policy=policy,
    )
    return guardian, recipient, evidence, authorization


def test_eligible_projection_is_minimum_necessary_and_get_writes_nothing(
    scenario: Scenario,
) -> None:
    _, recipient, evidence, authorization = _activate_recipient(scenario)
    before = _write_counts(scenario.application)
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    after = _write_counts(scenario.application)

    assert response.status_code == 200, response.text
    _assert_private_headers(response)
    assert before == after
    body = response.json()
    assert body["decision"] == "recipient_selection_available"
    assert body["blockers"] == []
    assert body["authority_revision"] == authorization["authority_revision"] == 1
    assert len(body["eligible_recipients"]) == 1
    projected = body["eligible_recipients"][0]
    assert set(projected) == {
        "recipient_person_id",
        "recipient_person_version_id",
        "display_name",
        "preferred_name",
        "relationship_label",
        "authorization_id",
        "authorization_version",
        "verification_policy_code",
        "verification_methods",
    }
    assert projected == {
        "recipient_person_id": recipient["id"],
        "recipient_person_version_id": recipient["current_version"]["id"],
        "display_name": "Recipient Authority",
        "preferred_name": "Recipient Preferred",
        "relationship_label": "Family friend",
        "authorization_id": authorization["id"],
        "authorization_version": 1,
        "verification_policy_code": "government_photo_id_or_documented_familiarity",
        "verification_methods": ["government_photo_id", "documented_familiarity"],
    }
    serialized = response.text
    for forbidden in (
        evidence[0],
        evidence[1],
        "recipient-private@example.com",
        "780-555-0111",
        "CONFIDENTIAL-EVIDENCE-LABEL-MUST-NOT-LEAK",
    ):
        assert forbidden not in serialized


def test_visibly_identical_recipient_records_block_selection_at_the_api(
    scenario: Scenario,
) -> None:
    guardian, first_recipient, evidence, first_authorization = _activate_recipient(scenario)
    second_recipient = _authority_person(
        scenario.client,
        scenario.owner_headers,
        scenario.family,
        guardian=False,
        first_name="Recipient",
    )
    _grant(
        scenario.client,
        scenario.owner_headers,
        scenario.child["id"],
        guardian,
        second_recipient,
        evidence,
        expected_revision=first_authorization["authority_revision"],
    )

    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "blocked"
    assert response.json()["blockers"] == ["recipient_identity_ambiguous"]
    assert response.json()["eligible_recipients"] == []
    assert first_recipient["id"] not in response.text
    assert second_recipient["id"] not in response.text


@pytest.mark.parametrize(
    ("policy", "expected_blocker"),
    [
        ("government_photo_id_and_secondary_check", "verification_workflow_unavailable"),
    ],
)
def test_unimplemented_verification_policy_blocks_without_recipient_disclosure(
    scenario: Scenario,
    policy: str,
    expected_blocker: str,
) -> None:
    _, recipient, _, _ = _activate_recipient(scenario, policy=policy)
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "blocked"
    assert response.json()["blockers"] == [expected_blocker]
    assert response.json()["eligible_recipients"] == []
    assert recipient["id"] not in response.text
    assert "Recipient Authority" not in response.text


@pytest.mark.parametrize(
    ("kind", "expected_blocker"),
    [("deny", "release_restricted"), ("manager_review", "manager_review_required")],
)
def test_all_recipient_rule_blocks_and_never_discloses_reason_or_person(
    scenario: Scenario,
    kind: str,
    expected_blocker: str,
) -> None:
    guardian, recipient, evidence, authorization = _activate_recipient(scenario)
    rule = _rule(
        scenario.client,
        scenario.owner_headers,
        scenario.child["id"],
        guardian,
        evidence,
        expected_revision=authorization["authority_revision"],
        kind=kind,
    )
    before = _write_counts(scenario.application)
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    after = _write_counts(scenario.application)

    assert response.status_code == 200, response.text
    assert before == after
    body = response.json()
    assert body["authority_revision"] == rule["authority_revision"] == 2
    assert body["decision"] == "blocked"
    assert body["blockers"] == [expected_blocker]
    assert body["eligible_recipients"] == []
    assert recipient["id"] not in response.text
    assert "Recipient Authority" not in response.text
    assert "CONFIDENTIAL-RULE-REASON-MUST-NOT-LEAK" not in response.text


def test_owner_still_requires_exact_open_facility_shift_and_on_site_child(
    scenario: Scenario,
) -> None:
    second_facility = scenario.client.post(
        "/api/v1/facilities",
        headers=scenario.owner_headers,
        json={
            "name": "Other Release Centre",
            "status": "active",
            "licensed_capacity": 10,
            "timezone": "America/Edmonton",
        },
    )
    assert second_facility.status_code == 201, second_facility.text
    other_id = second_facility.json()["id"]

    _clock_out(scenario.client, scenario.owner_headers, scenario.facility["id"])
    no_shift = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert no_shift.status_code == 409, no_shift.text
    assert no_shift.json() == {"detail": {"code": "open_shift_required"}}

    _clock_in(scenario.client, scenario.owner_headers, other_id)
    wrong_facility = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert wrong_facility.status_code == 409, wrong_facility.text
    assert wrong_facility.json() == {
        "detail": {"code": "open_shift_facility_mismatch"}
    }
    _clock_out(scenario.client, scenario.owner_headers, other_id)
    _clock_in(scenario.client, scenario.owner_headers, scenario.facility["id"])

    with scenario.application.state.database.session_factory() as session:
        interval = session.scalar(
            select(AttendanceInterval).where(
                AttendanceInterval.attendance_day_id == UUID(scenario.attendance["id"]),
                AttendanceInterval.checked_out_at.is_(None),
            )
        )
        assert interval is not None
        interval.checked_out_at = datetime.now(UTC)
        session.commit()
    off_site = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert off_site.status_code == 409, off_site.text
    assert off_site.json() == {"detail": {"code": "child_not_on_site"}}


def test_facility_and_room_scope_fail_closed_for_educator(scenario: Scenario) -> None:
    correct_headers, educator_role_id = _educator(
        scenario.client,
        scenario.owner_headers,
        facility_id=scenario.facility["id"],
        room_id=scenario.rooms[0]["id"],
        suffix="correct",
    )
    correct = scenario.client.get(scenario.path, headers=correct_headers)
    assert correct.status_code == 200, correct.text

    wrong_headers, _ = _educator(
        scenario.client,
        scenario.owner_headers,
        facility_id=scenario.facility["id"],
        room_id=scenario.rooms[1]["id"],
        suffix="wrong",
    )
    wrong_room = scenario.client.get(scenario.path, headers=wrong_headers)
    assert wrong_room.status_code == 404, wrong_room.text
    assert wrong_room.json() == {
        "detail": {"code": "release_context_scope_not_found"}
    }

    with scenario.application.state.database.session_factory() as session:
        role = session.scalar(select(Role).where(Role.id == UUID(educator_role_id)))
        assert role is not None and "release:read" in role.permissions
        role.permissions = [item for item in role.permissions if item != "release:read"]
        session.commit()
    permission_denied = scenario.client.get(scenario.path, headers=correct_headers)
    assert permission_denied.status_code == 403, permission_denied.text
    assert permission_denied.json()["detail"] == "Permission required"


def test_inactive_facility_is_hidden_as_scope_not_found(scenario: Scenario) -> None:
    with scenario.application.state.database.session_factory() as session:
        facility = session.scalar(
            select(Facility).where(Facility.id == UUID(scenario.facility["id"]))
        )
        assert facility is not None
        facility.status = "inactive"
        session.commit()
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert response.status_code == 404, response.text
    assert response.json() == {
        "detail": {"code": "release_context_scope_not_found"}
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            ReleaseContextRepositoryError("release_context_inconsistent", 409),
            409,
            "release_context_inconsistent",
        ),
        (
            ReleaseContextRepositoryError(
                "family_authority_release_context_unavailable", 503
            ),
            503,
            "family_authority_release_context_unavailable",
        ),
        (
            ReleaseContextInconsistentError("CONFIDENTIAL-INTERNAL-DETAIL"),
            409,
            "release_context_inconsistent",
        ),
        (
            ReleaseContextReevaluationRequired("CONFIDENTIAL-TIME-DETAIL"),
            409,
            "release_context_inconsistent",
        ),
    ],
)
def test_repository_and_composer_failures_are_bounded_without_internal_detail(
    scenario: Scenario,
    monkeypatch,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    from app.api.basic import family_release_context as route_module

    if isinstance(error, ReleaseContextRepositoryError):
        def fail_repository(*args, **kwargs):
            raise error

        monkeypatch.setattr(route_module, "load_release_context_input", fail_repository)
    else:
        def fail_composer(*args, **kwargs):
            raise error

        monkeypatch.setattr(route_module, "compose_release_context", fail_composer)
    before = _write_counts(scenario.application)
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    after = _write_counts(scenario.application)
    assert response.status_code == status_code, response.text
    assert response.json() == {"detail": {"code": code}}
    assert "CONFIDENTIAL" not in response.text
    assert before == after


def test_duplicate_open_attendance_intervals_fail_inconsistent_without_identity_leak(
    scenario: Scenario,
) -> None:
    with scenario.application.state.database.session_factory() as session:
        day = session.scalar(
            select(AttendanceDay).where(AttendanceDay.id == UUID(scenario.attendance["id"]))
        )
        assert day is not None
        first = session.scalar(
            select(AttendanceInterval).where(
                AttendanceInterval.attendance_day_id == day.id,
                AttendanceInterval.checked_out_at.is_(None),
            )
        )
        assert first is not None
        session.add(
            AttendanceInterval(
                id=uuid4(),
                organization_id=day.organization_id,
                attendance_day_id=day.id,
                sequence=first.sequence + 1,
                checked_in_at=first.checked_in_at + timedelta(seconds=1),
            )
        )
        session.commit()
    response = scenario.client.get(scenario.path, headers=scenario.owner_headers)
    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": {"code": "release_context_inconsistent"}
    }
    assert scenario.child["id"] not in response.text
    assert scenario.family["id"] not in response.text
