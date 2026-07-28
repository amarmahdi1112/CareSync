from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.basic.models import BasicBase
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="ats-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client, email, organization):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Test",
            "last_name": "Person",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def test_only_canonical_hiring_surfaces_are_mounted(tmp_path):
    client, _ = _client(tmp_path)
    _, owner_headers = _register(client, "owner@example.test", "ATS Centre")
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/ats/workspace" in paths
    assert "/api/v1/ats/jobs" in paths
    assert "/api/v1/marketplace/jobs" in paths
    assert "/api/v1/marketplace/applications" in paths
    assert "/api/v1/realtime/tickets" in paths
    assert "/api/v1/marketplace/realtime/tickets" in paths
    assert "/api/v1/ats/applications/{application_id}/offers/send" in paths
    assert not any(
        path.startswith("/api/v1/hiring/")
        or path.startswith("/api/v1/candidate/hiring/")
        for path in paths
    )
    assert "/api/v1/ats/invitations" not in paths
    assert "/api/v1/ats/events" not in paths
    assert "/api/v1/ats/applications/{application_id}/hire-handoff" not in paths
    assert "/api/v1/ats/applications/{application_id}/offers" not in paths
    assert "/api/v1/ats/offers/{offer_id}/send" not in paths

    listing = client.post(
        "/api/v1/ats/jobs",
        headers=owner_headers,
        json={
            "title": "Early childhood educator",
            "description": "Join our room team.",
            "location": "Edmonton",
            "employment_type": "full_time",
            "requirements": [],
            "openings": 1,
        },
    )
    assert listing.status_code == 201, listing.text
    listing_id = listing.json()["id"]
    opened = client.post(
        f"/api/v1/ats/jobs/{listing_id}/status",
        headers=owner_headers,
        json={
            "status": "open",
            "expected_version": listing.json()["version"],
            "reason": "Publish canonical listing",
        },
    )
    assert opened.status_code == 200, opened.text

    legacy = client.post(
        "/api/v1/hiring/invitations",
        headers=owner_headers,
        json={},
    )
    retired_invitation = client.post(
        "/api/v1/ats/invitations",
        headers=owner_headers,
        json={},
    )
    retired_handoff = client.post(
        "/api/v1/ats/applications/00000000-0000-0000-0000-000000000001/hire-handoff",
        headers=owner_headers,
        json={},
    )
    assert legacy.status_code == 404
    assert retired_invitation.status_code == 404
    assert retired_handoff.status_code == 404


def test_staff_self_and_location_free_shift_are_scoped_and_idempotent(tmp_path):
    client, application = _client(tmp_path)
    owner, owner_headers = _register(client, "shift-owner@example.test", "Shift Centre")
    # Create a staff user through the established invitation workflow.
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers).json()
    educator = next(item for item in workspace["roles"] if item["key"] == "educator")
    facility = client.post(
        "/api/v1/facilities",
        headers=owner_headers,
        json={
            "name": "Shift Centre",
            "status": "active",
            "licensed_capacity": 20,
        },
    ).json()
    program = client.post(
        "/api/v1/programs",
        headers=owner_headers,
        json={
            "facility_id": facility["id"],
            "name": "Daycare",
            "program_type": "daycare",
            "capacity": 20,
        },
    ).json()
    room = client.post(
        "/api/v1/rooms",
        headers=owner_headers,
        json={
            "facility_id": facility["id"],
            "program_id": program["id"],
            "name": "Room",
            "capacity": 20,
        },
    ).json()
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": "shift@example.test",
            "first_name": "Shift",
            "last_name": "Staff",
            "role_id": educator["id"],
            "assigned_facility_ids": [facility["id"]],
            "assigned_room_ids": [room["id"]],
        },
    ).json()
    staff_token = parse_qs(urlparse(invitation["activation_url"]).fragment)["token"][0]
    accepted_staff = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": staff_token, "password": PASSWORD},
    ).json()
    staff_headers = {"Authorization": f"Bearer {accepted_staff['access_token']}"}
    self_response = client.get("/api/v1/staff/self", headers=staff_headers)
    assert self_response.status_code == 200
    assert [item["id"] for item in self_response.json()["assigned_rooms"]] == [room["id"]]
    clock_input = {
        "facility_id": facility["id"],
        "operation_id": "20000000-0000-0000-0000-000000000001",
    }
    first = client.post(
        "/api/v1/staff/self/shifts/clock-in", headers=staff_headers, json=clock_input
    )
    assert first.status_code == 201, first.text
    assert set(first.json()["events"][0]) == {
        "id", "operation_id", "event_type", "server_occurred_at"
    }
    retry = client.post(
        "/api/v1/staff/self/shifts/clock-in", headers=staff_headers, json=clock_input
    )
    assert retry.status_code == 201 and retry.json()["id"] == first.json()["id"]
    checkout = client.post(
        "/api/v1/staff/self/shifts/clock-out",
        headers=staff_headers,
        json={**clock_input, "operation_id": "20000000-0000-0000-0000-000000000003"},
    )
    assert checkout.status_code == 200 and checkout.json()["status"] == "closed"


def test_ats_sse_is_retired_in_favor_of_ticketed_realtime(tmp_path):
    client, _ = _client(tmp_path)
    _, headers = _register(client, "events@example.test", "Events Centre")
    response = client.post(
        "/api/v1/ats/jobs",
        headers=headers,
        json={
            "title": "Cook",
            "description": "Prepare meals",
            "employment_type": "part_time",
            "location": "Edmonton",
            "requirements": [],
        },
    )
    assert response.status_code == 201, response.text
    events = client.get("/api/v1/ats/events?after=0&limit=10", headers=headers)
    assert events.status_code == 404
    ticket = client.post("/api/v1/realtime/tickets", headers=headers, json={})
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()["websocket_path"] == "/api/v1/realtime/ws"
