"""Room assignment, naming, and program-capacity invariant tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.basic.models import BasicBase
from app.core.config import Settings
from app.main import create_app


def _client(tmp_path) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="room-invariant-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application)


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "Room",
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
    licensed_capacity: int = 80,
) -> dict:
    response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": name, "licensed_capacity": licensed_capacity},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _program(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    *,
    program_type: str = "daycare",
    capacity: int = 40,
    is_active: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility_id,
            "name": f"{program_type} Program",
            "program_type": program_type,
            "capacity": capacity,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_room(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    program_id: str,
    *,
    name: str,
    capacity: int,
    is_active: bool = True,
):
    return client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility_id,
            "program_id": program_id,
            "name": name,
            "capacity": capacity,
            "is_active": is_active,
        },
    )


def test_room_create_requires_program_and_patch_rejects_explicit_null(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "required-program@example.com", "Required Program Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Required Program Centre")
        program = _program(client, headers, facility["id"])

        missing = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={"facility_id": facility["id"], "name": "Missing", "capacity": 5},
        )
        assert missing.status_code == 422
        explicit_null = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": None,
                "name": "Null",
                "capacity": 5,
            },
        )
        assert explicit_null.status_code == 422

        room = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Assigned Room",
            capacity=5,
        )
        assert room.status_code == 201, room.text
        null_patch = client.patch(
            f"/api/v1/rooms/{room.json()['id']}",
            headers=headers,
            json={"program_id": None},
        )
        assert null_patch.status_code == 422


def test_room_names_are_whitespace_normalized_and_case_insensitively_unique(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "room-names@example.com", "Room Names Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Room Names Centre")
        program = _program(client, headers, facility["id"], capacity=50)

        first = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="  Moon   Room  ",
            capacity=10,
        )
        assert first.status_code == 201, first.text
        assert first.json()["name"] == "Moon Room"

        duplicate = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="moon room",
            capacity=10,
        )
        assert duplicate.status_code == 409, duplicate.text
        assert "name already exists" in duplicate.json()["detail"]

        second = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Star Room",
            capacity=10,
        )
        assert second.status_code == 201, second.text
        conflicting_patch = client.patch(
            f"/api/v1/rooms/{second.json()['id']}",
            headers=headers,
            json={"name": " MOON   ROOM "},
        )
        assert conflicting_patch.status_code == 409, conflicting_patch.text

        # The normalized name boundary remains organization/facility scoped.
        other_auth = _register(client, "other-room-names@example.com", "Other Names Child Care")
        other_headers = _headers(other_auth)
        other_facility = _facility(client, other_headers, "Other Names Centre")
        other_program = _program(client, other_headers, other_facility["id"])
        same_name_other_tenant = _create_room(
            client,
            other_headers,
            other_facility["id"],
            other_program["id"],
            name="moon room",
            capacity=10,
        )
        assert same_name_other_tenant.status_code == 201, same_name_other_tenant.text


def test_active_room_capacity_cannot_exceed_its_program_ceiling(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "room-capacity@example.com", "Room Capacity Child Care")
        headers = _headers(auth)
        # Program capacity is intentionally independent from this static facility ceiling.
        facility = _facility(client, headers, "Room Capacity Centre", licensed_capacity=5)
        program = _program(client, headers, facility["id"], capacity=10)

        inactive = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Future Room",
            capacity=50,
            is_active=False,
        )
        assert inactive.status_code == 201, inactive.text
        first = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="First Active Room",
            capacity=6,
        )
        second = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Second Active Room",
            capacity=4,
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

        over_create = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Over Capacity Room",
            capacity=1,
        )
        assert over_create.status_code == 422, over_create.text
        assert "exceeding the program capacity" in over_create.json()["detail"]

        over_resize = client.patch(
            f"/api/v1/rooms/{first.json()['id']}",
            headers=headers,
            json={"capacity": 7},
        )
        assert over_resize.status_code == 422, over_resize.text
        activate_oversized = client.patch(
            f"/api/v1/rooms/{inactive.json()['id']}",
            headers=headers,
            json={"is_active": True},
        )
        assert activate_oversized.status_code == 422, activate_oversized.text

        deactivated = client.patch(
            f"/api/v1/rooms/{second.json()['id']}",
            headers=headers,
            json={
                "is_active": False,
                "deactivation_confirmation": second.json()["name"],
                "deactivation_reason": "Rebalance program capacity",
            },
        )
        assert deactivated.status_code == 200, deactivated.text
        resized = client.patch(
            f"/api/v1/rooms/{first.json()['id']}",
            headers=headers,
            json={"capacity": 10},
        )
        assert resized.status_code == 200, resized.text


def test_program_capacity_and_deactivation_respect_active_assigned_rooms(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "program-capacity@example.com", "Program Capacity Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Program Capacity Centre")
        program = _program(client, headers, facility["id"], capacity=20)
        first = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Eight Places",
            capacity=8,
        )
        second = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Six Places",
            capacity=6,
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text

        below_rooms = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=headers,
            json={"capacity": 13},
        )
        assert below_rooms.status_code == 422, below_rooms.text
        assert "active room capacity of 14" in below_rooms.json()["detail"]
        exact_rooms = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=headers,
            json={"capacity": 14},
        )
        assert exact_rooms.status_code == 200, exact_rooms.text

        deactivation_blocked = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=headers,
            json={"is_active": False},
        )
        assert deactivation_blocked.status_code == 422, deactivation_blocked.text
        assert "active assigned rooms" in deactivation_blocked.json()["detail"]

        for room in (first.json(), second.json()):
            response = client.patch(
                f"/api/v1/rooms/{room['id']}",
                headers=headers,
                json={
                    "is_active": False,
                    "deactivation_confirmation": room["name"],
                    "deactivation_reason": "Close room before program closure",
                },
            )
            assert response.status_code == 200, response.text
        deactivated = client.patch(
            f"/api/v1/programs/{program['id']}",
            headers=headers,
            json={"is_active": False},
        )
        assert deactivated.status_code == 200, deactivated.text


def test_active_room_cannot_be_created_for_an_inactive_program(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "inactive-room-program@example.com", "Inactive Room Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Inactive Room Centre")
        program = _program(client, headers, facility["id"], is_active=False)

        active_room = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Invalid Active Room",
            capacity=5,
        )
        assert active_room.status_code == 422, active_room.text
        assert "active program" in active_room.json()["detail"]

        inactive_room = _create_room(
            client,
            headers,
            facility["id"],
            program["id"],
            name="Valid Inactive Room",
            capacity=50,
            is_active=False,
        )
        assert inactive_room.status_code == 201, inactive_room.text
