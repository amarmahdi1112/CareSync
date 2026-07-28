"""Approval-first DOB room placement acceptance and security tests."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.basic import room_placements
from app.basic.models import (
    AuditEvent,
    BasicBase,
    OrganizationMembership,
    Role,
    User,
)
from app.basic.security import create_access_token, hash_password
from app.basic.verification import apply_temporary_email_approval
from app.core.config import Settings
from app.main import create_app

SERVICE_DATE = date(2026, 7, 15)
PASSWORD = "correct-password-123"


def test_room_recommendation_prefers_narrowest_interval_and_keeps_equal_ties_manual() -> None:
    broad = SimpleNamespace(
        minimum_age_months=0,
        maximum_age_months=143,
        available_places=10,
    )
    infant = SimpleNamespace(
        minimum_age_months=0,
        maximum_age_months=18,
        available_places=10,
    )
    infant_peer = SimpleNamespace(
        minimum_age_months=0,
        maximum_age_months=18,
        available_places=10,
    )
    assert room_placements._suggestion_state([broad, infant]) == "one"
    assert room_placements._suggestion_state([broad, infant, infant_peer]) == "multiple"
    infant.available_places = 0
    assert room_placements._suggestion_state([broad, infant]) == "one"


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="room-placement-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Placement",
            "last_name": "Owner",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _post(client: TestClient, path: str, headers: dict, payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _facility_tree(client: TestClient, headers: dict) -> tuple[dict, dict, dict, dict]:
    facility = _post(
        client,
        "/api/v1/facilities",
        headers,
        {"name": "Placement Centre", "licensed_capacity": 2, "status": "active"},
    )
    program = _post(
        client,
        "/api/v1/programs",
        headers,
        {
            "facility_id": facility["id"],
            "name": "Daycare",
            "program_type": "daycare",
            "capacity": 2,
            "minimum_age_months": 0,
            "maximum_age_months": 71,
        },
    )
    room_payload = {
        "facility_id": facility["id"],
        "program_id": program["id"],
        "capacity": 1,
        "age_group": "Infant",
        "minimum_age_months": 0,
        "maximum_age_months": 18,
    }
    north = _post(client, "/api/v1/rooms", headers, {**room_payload, "name": "Infant North"})
    south = _post(client, "/api/v1/rooms", headers, {**room_payload, "name": "Infant South"})
    return facility, program, north, south


def _child(
    client: TestClient,
    headers: dict,
    *,
    name: str,
    facility: dict,
    program: dict,
    room: dict,
    approve: bool = True,
) -> dict:
    family = _post(
        client,
        "/api/v1/families",
        headers,
        {"client_operation_id": str(uuid4()), "name": f"{name} Family"},
    )
    child = _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "first_name": name,
            "last_name": "Placement",
            "date_of_birth": "2025-01-15",
        },
    )
    enrollment = _post(
        client,
        f"/api/v1/children/{child['id']}/enrollments",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "start_date": "2025-01-15",
        },
    )
    if approve:
        approved = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": SERVICE_DATE.isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text
    refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    return refreshed.json()


def _educator_headers(application: object, owner: dict) -> dict[str, str]:
    with application.state.database.session_factory() as session:
        organization_id = UUID(owner["user"]["organization_id"])
        educator_role = session.scalar(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.key == "educator",
            )
        )
        assert educator_role is not None
        user = User(
            id=uuid4(),
            email="placement-educator@example.com",
            password_hash=hash_password(PASSWORD),
            first_name="Room",
            last_name="Educator",
        )
        apply_temporary_email_approval(user)
        session.add(user)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=organization_id,
                user_id=user.id,
                role_id=educator_role.id,
                status="active",
            )
        )
        session.commit()
        token = create_access_token(user, application.state.settings)
    return {"Authorization": f"Bearer {token}"}


def test_room_placement_review_capacity_stale_check_approval_audit_and_dob_edit(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(room_placements, "_facility_today", lambda _facility: SERVICE_DATE)
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "placement-owner@example.com", "Placement Child Care")
        headers = _headers(owner)
        facility, program, north, south = _facility_tree(client, headers)
        half_range = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Incomplete Ages",
                "capacity": 1,
                "minimum_age_months": 0,
            },
        )
        assert half_range.status_code == 422
        inverted_range = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Inverted Ages",
                "capacity": 1,
                "minimum_age_months": 19,
                "maximum_age_months": 18,
            },
        )
        assert inverted_range.status_code == 422
        _child(
            client,
            headers,
            name="Full",
            facility=facility,
            program=program,
            room=north,
        )
        target = _child(
            client,
            headers,
            name="Amina",
            facility=facility,
            program=program,
            room=south,
            approve=False,
        )
        enrollment = target["enrollments"][0]

        # Legacy imports sometimes carried broad program ages in years (0-6)
        # while room ranges were correctly stored in months. Detailed room
        # intervals remain authoritative for placement eligibility.
        narrowed_program = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=headers,
            json={"minimum_age_months": 0, "maximum_age_months": 6},
        )
        assert narrowed_program.status_code == 200, narrowed_program.text

        response = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert response.status_code == 200, response.text
        review = response.json()[0]
        assert review["effective_date"] == SERVICE_DATE.isoformat()
        assert review["age_months"] == 18
        assert review["suggestion_state"] == "one"
        assert {item["room_id"] for item in review["candidates"]} == {
            north["id"],
            south["id"],
        }
        available = [item for item in review["candidates"] if item["available_places"]]
        assert [item["room_id"] for item in available] == [south["id"]]

        # The same child becomes an explicit-choice case as soon as a second
        # compatible place is available; no deterministic first-room guess is made.
        assert (
            client.patch(
                f"/api/v1/programs/{program['id']}",
                headers=headers,
                json={"capacity": 3},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/v1/rooms/{north['id']}",
                headers=headers,
                json={"capacity": 2},
            ).status_code
            == 200
        )
        multiple = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert multiple.status_code == 200, multiple.text
        assert multiple.json()[0]["suggestion_state"] == "multiple"
        assert (
            client.patch(
                f"/api/v1/rooms/{north['id']}",
                headers=headers,
                json={"capacity": 1},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/v1/programs/{program['id']}",
                headers=headers,
                json={"capacity": 2},
            ).status_code
            == 200
        )

        stale = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": south["id"],
                "effective_date": "2026-07-14",
            },
        )
        assert stale.status_code == 409
        full = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": north["id"],
                "effective_date": SERVICE_DATE.isoformat(),
            },
        )
        assert full.status_code == 409
        approved = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": south["id"],
                "effective_date": SERVICE_DATE.isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["room_id"] == south["id"]

        with application.state.database.session_factory() as session:
            event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.organization_id == UUID(owner["user"]["organization_id"]),
                    AuditEvent.entity_id == UUID(enrollment["id"]),
                    AuditEvent.action == "enrollment.room_placement.approved",
                )
            )
            assert event is not None
            assert event.details["effective_date"] == SERVICE_DATE.isoformat()

        changed_dob = client.patch(
            f"/api/v1/children/{target['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": target["version"],
                "date_of_birth": "2020-01-01",
            },
        )
        assert changed_dob.status_code == 409, changed_dob.text
        assert changed_dob.json()["detail"]["code"] == "dob_invalidates_room_placement"
        unchanged = client.get(f"/api/v1/children/{target['id']}", headers=headers)
        assert unchanged.status_code == 200, unchanged.text
        assert unchanged.json()["date_of_birth"] == "2025-01-15"
        assert unchanged.json()["enrollments"][0]["room_id"] == south["id"]


def test_room_placement_is_tenant_scoped_and_requires_manage_permission(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(room_placements, "_facility_today", lambda _facility: SERVICE_DATE)
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "scope-owner@example.com", "Scope Child Care")
        headers = _headers(owner)
        facility, program, _north, south = _facility_tree(client, headers)
        child = _child(
            client,
            headers,
            name="Scoped",
            facility=facility,
            program=program,
            room=south,
            approve=False,
        )
        enrollment = child["enrollments"][0]

        educator_headers = _educator_headers(application, owner)
        assert (
            client.get(
                "/api/v1/room-placement-reviews",
                headers=educator_headers,
                params={"facility_id": facility["id"]},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
                headers=educator_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": enrollment["version"],
                    "room_id": south["id"],
                    "effective_date": SERVICE_DATE.isoformat(),
                },
            ).status_code
            == 403
        )

        other = _register(client, "other-owner@example.com", "Other Child Care")
        other_headers = _headers(other)
        assert (
            client.get(
                "/api/v1/room-placement-reviews",
                headers=other_headers,
                params={"facility_id": facility["id"]},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
                headers=other_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": enrollment["version"],
                    "room_id": south["id"],
                    "effective_date": SERVICE_DATE.isoformat(),
                },
            ).status_code
            == 404
        )


def test_review_and_approval_include_pending_unassigned_enrollment(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(room_placements, "_facility_today", lambda _facility: SERVICE_DATE)
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "program-only@example.com", "Program Only Child Care")
        headers = _headers(owner)
        facility, program, _north, south = _facility_tree(client, headers)
        child = _child(
            client,
            headers,
            name="ProgramAssigned",
            facility=facility,
            program=program,
            room=south,
            approve=False,
        )
        enrollment = child["enrollments"][0]

        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        review = next(item for item in reviews.json() if item["enrollment_id"] == enrollment["id"])
        assert any(item["room_id"] == south["id"] for item in review["candidates"])

        approved = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": south["id"],
                "effective_date": review["effective_date"],
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["program_id"] == program["id"]
        assert approved.json()["room_id"] == south["id"]


def test_batch_approval_is_atomic_capacity_safe_and_audits_each_exact_command(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(room_placements, "_facility_today", lambda _facility: SERVICE_DATE)
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "batch-placement@example.com", "Batch Placement Child Care")
        headers = _headers(owner)
        facility, program, north, south = _facility_tree(client, headers)
        first = _child(
            client,
            headers,
            name="BatchFirst",
            facility=facility,
            program=program,
            room=north,
            approve=False,
        )
        second = _child(
            client,
            headers,
            name="BatchSecond",
            facility=facility,
            program=program,
            room=south,
            approve=False,
        )
        enrollments = [first["enrollments"][0], second["enrollments"][0]]

        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        ).json()
        effective_dates = {item["enrollment_id"]: item["effective_date"] for item in reviews}
        over_capacity = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        "client_operation_id": str(uuid4()),
                        "expected_version": enrollment["version"],
                        "enrollment_id": enrollment["id"],
                        "room_id": south["id"],
                        "effective_date": effective_dates[enrollment["id"]],
                    }
                    for enrollment in enrollments
                ]
            },
        )
        assert over_capacity.status_code == 409
        for child in (first, second):
            refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers).json()
            assert refreshed["enrollments"][0]["room_id"] is None
            assert refreshed["enrollments"][0]["program_id"] is None

        success = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        "client_operation_id": str(uuid4()),
                        "expected_version": enrollments[0]["version"],
                        "enrollment_id": enrollments[0]["id"],
                        "room_id": north["id"],
                        "effective_date": effective_dates[enrollments[0]["id"]],
                    },
                    {
                        "client_operation_id": str(uuid4()),
                        "expected_version": enrollments[1]["version"],
                        "enrollment_id": enrollments[1]["id"],
                        "room_id": south["id"],
                        "effective_date": effective_dates[enrollments[1]["id"]],
                    },
                ]
            },
        )
        assert success.status_code == 200, success.text
        assert [item["id"] for item in success.json()["approvals"]] == [
            enrollment["id"] for enrollment in enrollments
        ]

        with application.state.database.session_factory() as session:
            events = list(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.organization_id == UUID(owner["user"]["organization_id"]),
                        AuditEvent.action == "enrollment.room_placement.approved",
                    )
                )
            )
            assert len(events) == 2
            assert {str(event.entity_id) for event in events} == {
                enrollment["id"] for enrollment in enrollments
            }
            assert {event.details["room_id"] for event in events} == {
                north["id"],
                south["id"],
            }
