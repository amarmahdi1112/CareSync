"""Integrated room-roster reads and safe enrollment placement tests."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.basic.models import BasicBase, Child
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
        jwt_secret="room-roster-test-secret-with-at-least-32-bytes",
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
            "first_name": "Roster",
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
) -> dict:
    response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": name, "licensed_capacity": 80, "status": "active"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _program(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    program_type: str,
) -> dict:
    response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility_id,
            "name": f"{program_type} Program",
            "program_type": program_type,
            "capacity": 20,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _room(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    program_id: str,
    name: str,
    *,
    capacity: int = 5,
    is_active: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility_id,
            "program_id": program_id,
            "name": name,
            "capacity": capacity,
            "is_active": is_active,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _family(client: TestClient, headers: dict[str, str], name: str) -> dict:
    response = client.post(
        "/api/v1/families",
        headers=headers,
        json={"client_operation_id": str(uuid4()), "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _child(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    name: str,
    *,
    facility_id: str | None = None,
    program_id: str | None = None,
    room_id: str | None = None,
    approve: bool = True,
) -> dict:
    payload: dict[str, object] = {
        "client_operation_id": str(uuid4()),
        "family_id": family_id,
        "first_name": name,
        "last_name": "Roster",
        "date_of_birth": "2023-01-01",
    }
    response = client.post("/api/v1/children", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    child = response.json()
    if facility_id is not None:
        enrollment_response = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility_id,
                "start_date": date.today().isoformat(),
            },
        )
        assert enrollment_response.status_code == 201, enrollment_response.text
        enrollment = enrollment_response.json()
        if approve:
            assert program_id is not None and room_id is not None
            approval_response = client.post(
                f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": enrollment["version"],
                    "room_id": room_id,
                    "effective_date": date.today().isoformat(),
                },
            )
            assert approval_response.status_code == 200, approval_response.text
        refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers)
        assert refreshed.status_code == 200, refreshed.text
        child = refreshed.json()
    return child


def test_room_rosters_include_empty_rooms_open_children_and_unassigned(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "rosters@example.com", "Roster Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Roster Centre")
        daycare = _program(client, headers, facility["id"], "daycare")
        osc = _program(client, headers, facility["id"], "out_of_school_care")
        moon = _room(client, headers, facility["id"], daycare["id"], "Moon Room")
        star = _room(client, headers, facility["id"], osc["id"], "Star Room")
        empty = _room(
            client,
            headers,
            facility["id"],
            osc["id"],
            "Future Room",
            is_active=False,
        )
        family = _family(client, headers, "Roster Family")

        assigned = _child(
            client,
            headers,
            family["id"],
            "Assigned",
            facility_id=facility["id"],
            program_id=daycare["id"],
            room_id=moon["id"],
        )
        unassigned = _child(
            client,
            headers,
            family["id"],
            "Unassigned",
            facility_id=facility["id"],
            program_id=osc["id"],
            room_id=star["id"],
            approve=False,
        )

        paused = _child(
            client,
            headers,
            family["id"],
            "Paused",
            facility_id=facility["id"],
            program_id=osc["id"],
            room_id=star["id"],
        )
        paused_update = client.patch(
            f"/api/v1/enrollments/{paused['enrollments'][0]['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": paused["enrollments"][0]["version"],
                "status": "paused",
            },
        )
        assert paused_update.status_code == 200, paused_update.text

        ended = _child(
            client,
            headers,
            family["id"],
            "Ended",
            facility_id=facility["id"],
            program_id=osc["id"],
            room_id=star["id"],
        )
        ended_update = client.patch(
            f"/api/v1/enrollments/{ended['enrollments'][0]['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": ended["enrollments"][0]["version"],
                "status": "ended",
                "end_date": date.today().isoformat(),
            },
        )
        assert ended_update.status_code == 200, ended_update.text
        assert ended_update.json()["status"] == "ended"

        inactive_child = _child(
            client,
            headers,
            family["id"],
            "Inactive",
            facility_id=facility["id"],
            program_id=daycare["id"],
            room_id=moon["id"],
        )
        # Preserve visibility for a legacy inconsistent record while all new
        # API writes reject this state.
        with client.app.state.database.session_factory() as session:
            legacy_child = session.get(Child, UUID(inactive_child["id"]))
            assert legacy_child is not None
            legacy_child.is_active = False
            session.commit()

        other = _register(client, "other-rosters@example.com", "Other Roster Child Care")
        other_headers = _headers(other)
        other_facility = _facility(client, other_headers, "Other Centre")
        other_program = _program(client, other_headers, other_facility["id"], "daycare")
        other_room = _room(
            client,
            other_headers,
            other_facility["id"],
            other_program["id"],
            "Other Room",
        )
        other_family = _family(client, other_headers, "Other Family")
        other_child = _child(
            client,
            other_headers,
            other_family["id"],
            "Other",
            facility_id=other_facility["id"],
            program_id=other_program["id"],
            room_id=other_room["id"],
        )
        foreign_update = client.patch(
            f"/api/v1/enrollments/{other_child['enrollments'][0]['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": other_child["enrollments"][0]["version"],
                "status": "paused",
            },
        )
        assert foreign_update.status_code == 404

        response = client.get(
            f"/api/v1/room-rosters?facility_id={facility['id']}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["facility_id"] == facility["id"]
        assert [item["room_id"] for item in payload["rooms"]] == [
            empty["id"],
            moon["id"],
            star["id"],
        ]
        room_rosters = {item["room_id"]: item for item in payload["rooms"]}
        assert room_rosters[empty["id"]]["children"] == []
        assert room_rosters[empty["id"]]["occupancy"] == 0
        assert room_rosters[moon["id"]]["occupancy"] == 1
        assert {item["child_id"] for item in room_rosters[moon["id"]]["children"]} == {
            assigned["id"],
        }
        assert inactive_child["id"] not in {
            item["child_id"] for item in room_rosters[moon["id"]]["children"]
        }
        assert room_rosters[star["id"]]["occupancy"] == 0
        assert room_rosters[star["id"]]["children"] == []
        assert [item["child_id"] for item in payload["unassigned_children"]] == [unassigned["id"]]
        returned_ids = {
            item["child_id"] for room in payload["rooms"] for item in room["children"]
        } | {item["child_id"] for item in payload["unassigned_children"]}
        assert ended["id"] not in returned_ids
        assert paused["id"] not in returned_ids
        assert other_child["id"] not in returned_ids

        foreign = client.get(
            f"/api/v1/room-rosters?facility_id={other_facility['id']}",
            headers=headers,
        )
        assert foreign.status_code == 404


def test_placement_approval_enforces_capacity_scope_and_child_lifecycle(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "moves@example.com", "Move Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "Move Centre")
        daycare = _program(client, headers, facility["id"], "daycare")
        osc = _program(client, headers, facility["id"], "out_of_school_care")
        daycare_room = _room(
            client,
            headers,
            facility["id"],
            daycare["id"],
            "Daycare Room",
            capacity=1,
        )
        osc_room = _room(
            client,
            headers,
            facility["id"],
            osc["id"],
            "OSC Room",
            capacity=1,
        )
        inactive_room = _room(
            client,
            headers,
            facility["id"],
            osc["id"],
            "Inactive Room",
            capacity=1,
            is_active=False,
        )
        family = _family(client, headers, "Move Family")
        first = _child(
            client,
            headers,
            family["id"],
            "First",
            facility_id=facility["id"],
            program_id=daycare["id"],
            room_id=daycare_room["id"],
        )
        second = _child(
            client,
            headers,
            family["id"],
            "Second",
            facility_id=facility["id"],
            program_id=osc["id"],
            room_id=osc_room["id"],
        )
        second_enrollment = second["enrollments"][0]

        deactivate_with_open_enrollment = client.patch(
            f"/api/v1/children/{first['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": first["version"],
                "is_active": False,
            },
        )
        assert deactivate_with_open_enrollment.status_code == 422
        assert deactivate_with_open_enrollment.json()["detail"] == (
            "End the child's open enrollment before deactivating the child"
        )

        candidate = _child(
            client,
            headers,
            family["id"],
            "Candidate",
            facility_id=facility["id"],
            approve=False,
        )
        candidate_enrollment = candidate["enrollments"][0]
        full = client.post(
            f"/api/v1/enrollments/{candidate_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": candidate_enrollment["version"],
                "room_id": osc_room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert full.status_code == 409, full.text

        inactive = client.post(
            f"/api/v1/enrollments/{candidate_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": candidate_enrollment["version"],
                "room_id": inactive_room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert inactive.status_code == 409, inactive.text
        second_facility = _facility(client, headers, "Second Move Centre")
        second_program = _program(client, headers, second_facility["id"], "daycare")
        second_facility_room = _room(
            client,
            headers,
            second_facility["id"],
            second_program["id"],
            "Second Facility Room",
            capacity=1,
        )
        cross_facility = client.post(
            f"/api/v1/enrollments/{candidate_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": candidate_enrollment["version"],
                "room_id": second_facility_room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert cross_facility.status_code == 404, cross_facility.text

        ended_second = client.patch(
            f"/api/v1/enrollments/{second_enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": second_enrollment["version"],
                "status": "ended",
                "end_date": date.today().isoformat(),
            },
        )
        assert ended_second.status_code == 200, ended_second.text

        approved = client.post(
            f"/api/v1/enrollments/{candidate_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": candidate_enrollment["version"],
                "room_id": osc_room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["organization_id"] == auth["user"]["organization_id"]
        assert approved.json()["program_id"] == osc["id"]
        assert approved.json()["room_id"] == osc_room["id"]

        roster = client.get(
            f"/api/v1/room-rosters?facility_id={facility['id']}",
            headers=headers,
        )
        assert roster.status_code == 200, roster.text
        roster_payload = roster.json()
        osc_roster = next(
            item for item in roster_payload["rooms"] if item["room_id"] == osc_room["id"]
        )
        assert osc_roster["occupancy"] == 1
        assert osc_roster["children"][0]["child_id"] == candidate["id"]
        assert roster_payload["unassigned_children"] == []


def test_new_enrollments_are_pending_until_approved_and_reserve_capacity(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        auth = _register(client, "new-enrollment@example.com", "New Enrollment Child Care")
        headers = _headers(auth)
        facility = _facility(client, headers, "New Enrollment Centre")
        program = _program(client, headers, facility["id"], "daycare")
        room = _room(
            client,
            headers,
            facility["id"],
            program["id"],
            "One Place Room",
            capacity=1,
        )
        family = _family(client, headers, "New Enrollment Family")
        child = _child(client, headers, family["id"], "Waiting")

        pending = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": date.today().isoformat(),
            },
        )
        assert pending.status_code == 201, pending.text
        assert pending.json()["status"] == "pending"
        assert pending.json()["program_id"] is None
        assert pending.json()["room_id"] is None

        created = client.post(
            f"/api/v1/enrollments/{pending.json()['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": pending.json()["version"],
                "room_id": room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert created.status_code == 200, created.text

        waiting = _child(client, headers, family["id"], "Still Waiting")
        waiting_enrollment = client.post(
            f"/api/v1/children/{waiting['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": date.today().isoformat(),
            },
        )
        assert waiting_enrollment.status_code == 201, waiting_enrollment.text
        full = client.post(
            f"/api/v1/enrollments/{waiting_enrollment.json()['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": waiting_enrollment.json()["version"],
                "room_id": room["id"],
                "effective_date": date.today().isoformat(),
            },
        )
        assert full.status_code == 409, full.text

        inactive = _child(client, headers, family["id"], "Inactive Waiting")
        inactive_update = client.patch(
            f"/api/v1/children/{inactive['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": inactive["version"],
                "is_active": False,
            },
        )
        assert inactive_update.status_code == 200, inactive_update.text
        inactive_enrollment = client.post(
            f"/api/v1/children/{inactive['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": date.today().isoformat(),
            },
        )
        assert inactive_enrollment.status_code == 422, inactive_enrollment.text
        assert "Inactive children" in inactive_enrollment.json()["detail"]
