"""Onboarding completion requires a coherent active program/room structure."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.basic.models import BasicBase, Room
from app.core.config import Settings
from app.main import create_app


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="onboarding-completion-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "Onboarding",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    *,
    status: str = "draft",
) -> dict:
    response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": name, "licensed_capacity": 80, "status": status},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _program(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    *,
    program_type: str = "daycare",
    is_active: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility_id,
            "name": f"{program_type} Program",
            "program_type": program_type,
            "capacity": 40,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _room(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    *,
    program_id: str,
    name: str = "First Room",
) -> dict:
    response = client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility_id,
            "program_id": program_id,
            "name": name,
            "capacity": 20,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _insert_legacy_room(
    application,
    auth: dict,
    facility_id: str,
    *,
    program_id: str | None,
    name: str,
) -> None:
    """Insert a state now rejected by the API to prove completion fails closed."""

    with application.state.database.session_factory() as session:
        session.add(
            Room(
                id=uuid4(),
                organization_id=UUID(auth["user"]["organization_id"]),
                facility_id=UUID(facility_id),
                program_id=UUID(program_id) if program_id is not None else None,
                name=name,
                capacity=20,
                is_active=True,
            )
        )
        session.commit()


def test_completion_requires_a_tenant_owned_active_program(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        first = _register(client, "no-program@example.com", "No Program Child Care")
        first_headers = _headers(first)
        _facility(client, first_headers, "No Program Centre")

        # A complete structure in another organization must never satisfy this tenant.
        second = _register(client, "other-program@example.com", "Other Child Care")
        second_headers = _headers(second)
        second_facility = _facility(client, second_headers, "Other Centre")
        second_program = _program(client, second_headers, second_facility["id"])
        _room(
            client,
            second_headers,
            second_facility["id"],
            program_id=second_program["id"],
        )

        completed = client.post("/api/v1/onboarding/complete", headers=first_headers)
        assert completed.status_code == 422, completed.text
        assert "active Daycare or OSC program" in completed.json()["detail"]


def test_completion_rejects_an_unassigned_active_room(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "unassigned@example.com", "Unassigned Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Unassigned Centre")
        _program(client, headers, facility["id"])
        _insert_legacy_room(
            application,
            auth,
            facility["id"],
            program_id=None,
            name="Legacy Unassigned Room",
        )

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "active room must be assigned" in completed.json()["detail"]
        assert "same facility" in completed.json()["detail"]


def test_completion_rejects_a_room_assigned_to_an_inactive_program(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "inactive@example.com", "Inactive Program Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Inactive Program Centre")
        program = _program(client, headers, facility["id"], is_active=False)
        _insert_legacy_room(
            application,
            auth,
            facility["id"],
            program_id=program["id"],
            name="Legacy Inactive Program Room",
        )

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "active Daycare or OSC program" in completed.json()["detail"]


def test_completion_rejects_a_program_room_facility_mismatch(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "mismatch@example.com", "Mismatch Child Care")
        headers = _headers(auth)
        program_facility = _facility(client, headers, "Program Centre")
        room_facility = _facility(client, headers, "Room Centre")
        program = _program(client, headers, program_facility["id"])

        _insert_legacy_room(
            application,
            auth,
            room_facility["id"],
            program_id=program["id"],
            name="Mismatched Room",
        )

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "same facility" in completed.json()["detail"]


def test_completion_rejects_programs_at_an_inactive_facility(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "inactive-facility@example.com", "Inactive Facility Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Inactive Centre", status="inactive")
        program = _program(client, headers, facility["id"])
        _room(client, headers, facility["id"], program_id=program["id"])

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "active Daycare or OSC program" in completed.json()["detail"]


def test_completion_rejects_one_invalid_room_even_when_another_room_is_valid(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "mixed-rooms@example.com", "Mixed Rooms Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Mixed Rooms Centre")
        program = _program(client, headers, facility["id"])
        _room(
            client,
            headers,
            facility["id"],
            program_id=program["id"],
            name="Valid Room",
        )
        _insert_legacy_room(
            application,
            auth,
            facility["id"],
            program_id=None,
            name="Invalid Room",
        )

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "Every active room" in completed.json()["detail"]


def test_completion_requires_a_room_for_every_active_program(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "missing-room@example.com", "Missing Room Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Missing Room Centre")
        daycare = _program(client, headers, facility["id"], program_type="daycare")
        _program(client, headers, facility["id"], program_type="out_of_school_care")
        _room(client, headers, facility["id"], program_id=daycare["id"])

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 422, completed.text
        assert "Every active Daycare or OSC program" in completed.json()["detail"]


@pytest.mark.parametrize("program_type", ["daycare", "out_of_school_care"])
def test_completion_accepts_a_valid_daycare_or_osc_structure(
    tmp_path,
    program_type: str,
) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(
            client,
            f"valid-{program_type}@example.com",
            f"Valid {program_type} Child Care",
        )
        headers = _headers(auth)
        facility = _facility(client, headers, f"Valid {program_type} Centre")
        program = _program(
            client,
            headers,
            facility["id"],
            program_type=program_type,
        )
        _room(client, headers, facility["id"], program_id=program["id"])

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "complete"

        facilities = client.get("/api/v1/facilities", headers=headers)
        assert facilities.status_code == 200, facilities.text
        assert facilities.json()[0]["status"] == "active"
