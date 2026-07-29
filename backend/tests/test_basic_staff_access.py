"""Security acceptance tests for Basic staff identity and room-scoped access.

These tests intentionally exercise only public HTTP contracts, except for the
single expiry setup needed to prove that a stored invitation cannot be used
after its server-side deadline.  UI visibility is never treated as an access
control.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.basic.models import BasicBase, Enrollment, UserNotification
from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct-password-123"
REPLACEMENT_PASSWORD = "replacement-password-456"
RESET_PASSWORD = "reset-password-789"
SERVICE_DATE = "2026-07-15"
FACILITY_TIME_ZONE = ZoneInfo("America/Edmonton")


def _facility_today() -> date:
    return datetime.now(FACILITY_TIME_ZONE).date()


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="staff-access-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Test",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _workspace(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/staff/workspace", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _role(workspace: dict, key: str) -> dict:
    values = [role for role in workspace["roles"] if role["key"] == key]
    assert len(values) == 1, workspace["roles"]
    return values[0]


def _secret_from_url(value: str, expected_path: str) -> str:
    parsed = urlparse(value)
    assert parsed.path.endswith(expected_path), value
    assert parsed.query == "", value
    fragment = parse_qs(parsed.fragment)
    values = fragment.get("token", [])
    assert len(values) == 1 and values[0], value
    return values[0]


def _activation_preview(client: TestClient, token: str):
    return client.post("/api/v1/auth/staff-activation", json={"token": token})


def _reset_preview(client: TestClient, token: str):
    return client.post("/api/v1/auth/password-reset", json={"token": token})


def _issue_password_reset(
    client: TestClient,
    headers: dict[str, str],
    membership_id: str,
) -> str:
    response = client.post(
        f"/api/v1/staff/members/{membership_id}/password-reset",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"reset_url", "expires_at"}
    return _secret_from_url(response.json()["reset_url"], "/reset-password")


def _invite(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    first_name: str,
    role_id: str,
    facility_ids: list[str] | None = None,
    room_ids: list[str] | None = None,
) -> tuple[dict, str]:
    response = client.post(
        "/api/v1/staff/invitations",
        headers=headers,
        json={
            "email": email,
            "first_name": first_name,
            "last_name": "Staff",
            "role_id": role_id,
            "assigned_facility_ids": facility_ids or [],
            "assigned_room_ids": room_ids or [],
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {"invitation", "activation_url"}
    invitation = data["invitation"]
    assert invitation["status"] == "pending"
    assert "token" not in invitation
    return invitation, _secret_from_url(data["activation_url"], "/activate-staff")


def _accept_invitation(
    client: TestClient,
    token: str,
    *,
    password: str = PASSWORD,
) -> dict:
    preview = _activation_preview(client, token)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert set(preview_data) == {
        "organization_name",
        "email",
        "first_name",
        "last_name",
        "role_name",
        "expires_at",
        "assigned_room_names",
    }
    response = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_facility_tree(
    client: TestClient,
    headers: dict[str, str],
    *,
    prefix: str,
) -> tuple[dict, dict, dict, dict]:
    facility_response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": f"{prefix} Centre",
            "licensed_capacity": 40,
            "status": "active",
        },
    )
    assert facility_response.status_code == 201, facility_response.text
    facility = facility_response.json()

    program_response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "name": f"{prefix} Daycare",
            "program_type": "daycare",
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program_response.status_code == 201, program_response.text
    program = program_response.json()

    rooms = []
    for name in ("North", "South"):
        response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"{prefix} {name}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert response.status_code == 201, response.text
        rooms.append(response.json())
    return facility, program, rooms[0], rooms[1]


def _create_child(
    client: TestClient,
    headers: dict[str, str],
    *,
    first_name: str,
    facility_id: str,
    program_id: str,
    room_id: str,
) -> dict:
    family_response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": f"{first_name} Family",
            "primary_guardian": {
                "first_name": "Parent",
                "last_name": first_name,
                "email": f"parent-{first_name.lower()}@example.test",
                "cell_phone": "780-555-0100",
            },
        },
    )
    assert family_response.status_code == 201, family_response.text
    response = client.post(
        "/api/v1/children",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "family_id": family_response.json()["id"],
            "first_name": first_name,
            "last_name": "Scope",
            "date_of_birth": "2023-01-01",
        },
    )
    assert response.status_code == 201, response.text
    child = response.json()
    enrollment_response = client.post(
        f"/api/v1/children/{child['id']}/enrollments",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility_id,
            "start_date": SERVICE_DATE,
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
            "room_id": room_id,
            "effective_date": _facility_today().isoformat(),
        },
    )
    assert approval_response.status_code == 200, approval_response.text
    # This security suite exercises a fixed, already-completed service day. The
    # live 0028 placement command correctly refuses retroactive approval, so seed
    # only the pre-existing effective date needed by the historical fixture.
    with client.app.state.database.session_factory() as session:
        stored = session.get(Enrollment, UUID(enrollment["id"]))
        assert stored is not None
        stored.placement_effective_date = date.fromisoformat(SERVICE_DATE)
        session.commit()
    refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    return refreshed.json()


def _member_patch(
    *,
    role_id: str,
    facility_ids: list[str],
    room_ids: list[str],
    status: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "role_id": role_id,
        "assigned_facility_ids": facility_ids,
        "assigned_room_ids": room_ids,
    }
    if status is not None:
        payload["membership_status"] = status
    return payload


def test_fixed_roles_and_session_access_contract(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "roles-owner@example.com", "Role Contract Child Care")
        user = owner["user"]

        assert user["role"]["key"] == "owner"
        assert user["membership_status"] == "active"
        assert UUID(user["membership_id"])
        assert user["assigned_facility_ids"] == []
        assert user["assigned_room_ids"] == []

        workspace = _workspace(client, _headers(owner))
        assert workspace["organization_id"] == user["organization_id"]
        assert {role["key"] for role in workspace["roles"]} == {
            "owner",
            "administrator",
            "educator",
        }
        for role in workspace["roles"]:
            assert set(role) == {"id", "key", "name", "description", "permissions"}
            assert isinstance(role["permissions"], list)


def test_invitation_tokens_are_one_time_regenerable_revocable_and_expiring(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "invite-owner@example.com", "Invite Child Care")
        headers = _headers(owner)
        assert client.get("/api/v1/auth/staff-activation").status_code == 405
        assert client.get("/api/v1/auth/password-reset").status_code == 405
        workspace = _workspace(client, headers)
        administrator_role = _role(workspace, "administrator")

        accepted_invitation, accepted_token = _invite(
            client,
            headers,
            email="accepted-administrator@example.com",
            first_name="Accepted",
            role_id=administrator_role["id"],
        )
        with application.state.database.engine.connect() as connection:
            stored_hash = connection.execute(
                text(
                    "SELECT token_hash FROM staff_invitations "
                    "WHERE lower(replace(CAST(id AS TEXT), '-', '')) = :invitation_id"
                ),
                {"invitation_id": accepted_invitation["id"].replace("-", "").lower()},
            ).scalar_one()
        assert stored_hash != accepted_token
        assert len(stored_hash) == 64
        assert all(character in "0123456789abcdef" for character in stored_hash.lower())
        accepted = _accept_invitation(client, accepted_token)
        assert accepted["user"]["role"]["key"] == "administrator"
        assert accepted["user"]["membership_status"] == "active"
        reused = client.post(
            "/api/v1/auth/staff-activation/accept",
            json={"token": accepted_token, "password": PASSWORD},
        )
        assert reused.status_code == 410, reused.text
        reused_preview = _activation_preview(client, accepted_token)
        assert reused_preview.status_code == 410, reused_preview.text

        regenerated_invitation, old_token = _invite(
            client,
            headers,
            email="regenerated-administrator@example.com",
            first_name="Regenerated",
            role_id=administrator_role["id"],
        )
        regenerated = client.post(
            f"/api/v1/staff/invitations/{regenerated_invitation['id']}/regenerate",
            headers=headers,
        )
        assert regenerated.status_code == 200, regenerated.text
        regenerated_data = regenerated.json()
        assert set(regenerated_data) == {"invitation", "activation_url"}
        new_token = _secret_from_url(regenerated_data["activation_url"], "/activate-staff")
        assert new_token != old_token
        assert _activation_preview(client, old_token).status_code == 410
        assert _activation_preview(client, new_token).status_code == 200

        revoked_invitation, revoked_token = _invite(
            client,
            headers,
            email="revoked-administrator@example.com",
            first_name="Revoked",
            role_id=administrator_role["id"],
        )
        revoked = client.delete(
            f"/api/v1/staff/invitations/{revoked_invitation['id']}",
            headers=headers,
        )
        assert revoked.status_code in {200, 204}, revoked.text
        assert _activation_preview(client, revoked_token).status_code == 410

        expired_invitation, expired_token = _invite(
            client,
            headers,
            email="expired-administrator@example.com",
            first_name="Expired",
            role_id=administrator_role["id"],
        )
        with application.state.database.engine.begin() as connection:
            changed = connection.execute(
                text(
                    "UPDATE staff_invitations SET expires_at = :expired "
                    "WHERE lower(replace(CAST(id AS TEXT), '-', '')) = :invitation_id"
                ),
                {
                    "expired": datetime.now(UTC) - timedelta(minutes=1),
                    "invitation_id": expired_invitation["id"].replace("-", "").lower(),
                },
            )
            assert changed.rowcount == 1
        expired_preview = _activation_preview(client, expired_token)
        assert expired_preview.status_code == 410, expired_preview.text

        refreshed = _workspace(client, headers)
        statuses = {item["id"]: item["status"] for item in refreshed["invitations"]}
        assert statuses[accepted_invitation["id"]] == "accepted"
        assert statuses[revoked_invitation["id"]] == "revoked"
        assert statuses[expired_invitation["id"]] == "expired"


def test_role_hierarchy_and_permission_enforcement(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "hierarchy-owner@example.com", "Hierarchy Child Care")
        owner_headers = _headers(owner)
        workspace = _workspace(client, owner_headers)
        owner_role = _role(workspace, "owner")
        administrator_role = _role(workspace, "administrator")
        educator_role = _role(workspace, "educator")
        facility, _, room, _ = _create_facility_tree(
            client,
            owner_headers,
            prefix="Hierarchy",
        )

        _, administrator_token = _invite(
            client,
            owner_headers,
            email="director@example.com",
            first_name="Director",
            role_id=administrator_role["id"],
        )
        administrator = _accept_invitation(client, administrator_token)
        administrator_headers = _headers(administrator)

        educator_without_room = client.post(
            "/api/v1/staff/invitations",
            headers=administrator_headers,
            json={
                "email": "unscoped-educator@example.com",
                "first_name": "Unscoped",
                "last_name": "Educator",
                "role_id": educator_role["id"],
                "assigned_facility_ids": [],
                "assigned_room_ids": [],
            },
        )
        assert educator_without_room.status_code == 422, educator_without_room.text

        educator_invitation, educator_token = _invite(
            client,
            administrator_headers,
            email="hierarchy-educator@example.com",
            first_name="Educator",
            role_id=educator_role["id"],
            facility_ids=[facility["id"]],
            room_ids=[room["id"]],
        )
        educator = _accept_invitation(client, educator_token)
        educator_headers = _headers(educator)
        assert educator_invitation["role"]["key"] == "educator"

        remove_required_scope = client.patch(
            f"/api/v1/staff/members/{educator['user']['membership_id']}",
            headers=administrator_headers,
            json=_member_patch(
                role_id=educator_role["id"],
                facility_ids=[],
                room_ids=[],
            ),
        )
        assert remove_required_scope.status_code == 422, remove_required_scope.text

        for forbidden_role in (owner_role, administrator_role):
            attempted = client.post(
                "/api/v1/staff/invitations",
                headers=administrator_headers,
                json={
                    "email": f"forbidden-{forbidden_role['key']}@example.com",
                    "first_name": "Forbidden",
                    "last_name": "Promotion",
                    "role_id": forbidden_role["id"],
                    "assigned_facility_ids": [],
                    "assigned_room_ids": [],
                },
            )
            assert attempted.status_code == 403, attempted.text

        owner_mutation = client.patch(
            f"/api/v1/staff/members/{owner['user']['membership_id']}",
            headers=administrator_headers,
            json=_member_patch(
                role_id=administrator_role["id"],
                facility_ids=[],
                room_ids=[],
            ),
        )
        assert owner_mutation.status_code == 403, owner_mutation.text

        educator_invite_attempt = client.post(
            "/api/v1/staff/invitations",
            headers=educator_headers,
            json={
                "email": "educator-created@example.com",
                "first_name": "No",
                "last_name": "Access",
                "role_id": educator_role["id"],
                "assigned_facility_ids": [facility["id"]],
                "assigned_room_ids": [room["id"]],
            },
        )
        assert educator_invite_attempt.status_code == 403
        assert client.get("/api/v1/staff/workspace", headers=educator_headers).status_code == 403
        assert client.get("/api/v1/families/directory", headers=educator_headers).status_code == 403
        assert client.get("/api/v1/children/directory", headers=educator_headers).status_code == 403
        assert (
            client.patch(
                "/api/v1/organization",
                headers=educator_headers,
                json={"name": "Unauthorized"},
            ).status_code
            == 403
        )

        assert (
            client.get("/api/v1/families/directory", headers=administrator_headers).status_code
            == 200
        )
        admin_family = client.post(
            "/api/v1/families",
            headers=administrator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "name": "Administrator Created",
            },
        )
        assert admin_family.status_code == 201, admin_family.text


def test_educator_rosters_and_attendance_are_room_scoped(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "scope-owner@example.com", "Scope Child Care")
        owner_headers = _headers(owner)
        facility, program, north_room, south_room = _create_facility_tree(
            client,
            owner_headers,
            prefix="Scope",
        )
        north_child = _create_child(
            client,
            owner_headers,
            first_name="North",
            facility_id=facility["id"],
            program_id=program["id"],
            room_id=north_room["id"],
        )
        south_child = _create_child(
            client,
            owner_headers,
            first_name="South",
            facility_id=facility["id"],
            program_id=program["id"],
            room_id=south_room["id"],
        )
        educator_role = _role(_workspace(client, owner_headers), "educator")
        _, token = _invite(
            client,
            owner_headers,
            email="north-educator@example.com",
            first_name="North",
            role_id=educator_role["id"],
            facility_ids=[facility["id"]],
            room_ids=[north_room["id"]],
        )
        educator = _accept_invitation(client, token)
        educator_headers = _headers(educator)
        assert educator["user"]["assigned_facility_ids"] == [facility["id"]]
        assert educator["user"]["assigned_room_ids"] == [north_room["id"]]

        attendance_roster = client.get(
            "/api/v1/attendance/roster",
            headers=educator_headers,
            params={"date": SERVICE_DATE, "facility_id": facility["id"]},
        )
        assert attendance_roster.status_code == 200, attendance_roster.text
        assert {item["child_id"] for item in attendance_roster.json()} == {north_child["id"]}

        room_rosters = client.get(
            "/api/v1/room-rosters",
            headers=educator_headers,
            params={"facility_id": facility["id"]},
        )
        assert room_rosters.status_code == 200, room_rosters.text
        assert {item["room_id"] for item in room_rosters.json()["rooms"]} == {north_room["id"]}
        assert room_rosters.json()["unassigned_children"] == []

        shift_required = client.post(
            "/api/v1/attendance/check-in",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": north_child["id"],
                "facility_id": facility["id"],
                "occurred_at": f"{SERVICE_DATE}T08:00:00-06:00",
            },
        )
        assert shift_required.status_code == 409, shift_required.text
        assert shift_required.json()["detail"] == {
            "code": "open_shift_required",
            "facility_id": facility["id"],
            "message": "Clock in to this facility before updating child records.",
        }
        clocked_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert clocked_in.status_code == 201, clocked_in.text

        checked_in = client.post(
            "/api/v1/attendance/check-in",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": north_child["id"],
                "facility_id": facility["id"],
                "occurred_at": f"{SERVICE_DATE}T08:00:00-06:00",
            },
        )
        assert checked_in.status_code == 200, checked_in.text

        staff_self = client.get("/api/v1/staff/self", headers=educator_headers)
        assert staff_self.status_code == 200, staff_self.text
        assert staff_self.json()["open_shift"]["status"] == "open"
        assert staff_self.json()["assigned_rooms"][0]["id"] == north_room["id"]
        assert staff_self.json()["assigned_facilities"][0]["verified_release_checkout"] == {
            "runtime_available": False,
            "facility_activated": False,
            "staff_eligible": True,
            "legacy_checkout_allowed": True,
            "policy_version": None,
        }

        care = client.post(
            "/api/v1/care/records",
            headers=educator_headers,
            json={
                "attendance_day_id": checked_in.json()["id"],
                "care_type": "feeding",
                "occurred_at": f"{SERVICE_DATE}T09:00:00-06:00",
                "payload": {"kind": "meal", "intake": "most"},
                "client_operation_id": str(uuid4()),
            },
        )
        assert care.status_code == 201, care.text

        plan = client.post(
            "/api/v1/medications/plans",
            headers=owner_headers,
            json={
                "facility_id": facility["id"],
                "child_id": north_child["id"],
                "medication_name": "Prescribed medication",
                "dosage": "5 mL",
                "route": "oral",
                "label_directions": "Use as written on the pharmacy label.",
                "scheduled_times": ["10:00"],
                "as_needed": False,
                "start_date": SERVICE_DATE,
                "end_date": "2026-07-31",
                "medication_kind": "non_emergency",
                "storage_method": "locked_inaccessible",
                "storage_instructions": "Locked cabinet inaccessible to children.",
                "client_operation_id": str(uuid4()),
            },
        )
        assert plan.status_code == 201, plan.text
        authorized = client.post(
            f"/api/v1/medications/plans/{plan.json()['id']}/authorization",
            headers=owner_headers,
            json={
                "guardian_id": plan.json()["eligible_guardians"][0]["id"],
                "signed_authorization_reference": "paper-e2e",
                "authorization_signed_at": f"{SERVICE_DATE}T07:00:00-06:00",
                "valid_until": "2026-07-31",
                "expected_version": plan.json()["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert authorized.status_code == 200, authorized.text
        activated = client.post(
            f"/api/v1/medications/plans/{plan.json()['id']}/activate",
            headers=owner_headers,
            json={
                "original_labelled_container_confirmed": True,
                "label_directions_confirmed": True,
                "expected_version": authorized.json()["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert activated.status_code == 200, activated.text
        medication = client.post(
            "/api/v1/medications/administrations",
            headers=educator_headers,
            json={
                "medication_plan_id": activated.json()["id"],
                "attendance_day_id": checked_in.json()["id"],
                "outcome": "administered",
                "scheduled_for": "10:00",
                "occurred_at": f"{SERVICE_DATE}T10:00:00-06:00",
                "amount": "5 mL",
                "client_operation_id": str(uuid4()),
            },
        )
        assert medication.status_code == 201, medication.text

        incident = client.post(
            "/api/v1/incidents",
            # Owner operational overrides are permitted and audited; educators
            # are deliberately limited to their facility's current local date.
            headers=owner_headers,
            json={
                "facility_id": facility["id"],
                "room_id": north_room["id"],
                "attendance_day_id": checked_in.json()["id"],
                "occurred_at": f"{SERVICE_DATE}T11:00:00-06:00",
                "category": "other",
                "severity": "minor",
                "summary": "Lifecycle integration test observation.",
                "immediate_actions": "Observed and documented.",
                "medical_attention": "none",
                "parent_notification_status": "not_applicable",
                "authorities_contacted": [],
                "staff_present": ["North Educator"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert incident.status_code == 201, incident.text

        checked_out = client.post(
            "/api/v1/attendance/check-out",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": north_child["id"],
                "facility_id": facility["id"],
                "occurred_at": f"{SERVICE_DATE}T17:00:00-06:00",
            },
        )
        assert checked_out.status_code == 200, checked_out.text

        shift_closed = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert shift_closed.status_code == 200, shift_closed.text
        blocked_after_clock_out = client.post(
            "/api/v1/care/records",
            headers=educator_headers,
            json={
                "attendance_day_id": checked_in.json()["id"],
                "care_type": "feeding",
                "occurred_at": f"{SERVICE_DATE}T12:00:00-06:00",
                "payload": {"kind": "snack", "intake": "some"},
                "client_operation_id": str(uuid4()),
            },
        )
        assert blocked_after_clock_out.status_code == 409
        assert blocked_after_clock_out.json()["detail"]["code"] == "open_shift_required"

        clocked_in_again = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert clocked_in_again.status_code == 201, clocked_in_again.text

        unassigned_room = client.post(
            "/api/v1/attendance/check-in",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": south_child["id"],
                "facility_id": facility["id"],
                "occurred_at": f"{SERVICE_DATE}T08:10:00-06:00",
            },
        )
        assert unassigned_room.status_code == 404, unassigned_room.text

        correction = client.put(
            f"/api/v1/attendance/{checked_out.json()['id']}/status-correction",
            headers=educator_headers,
            json={"status": "present", "reason": "Forbidden educator correction"},
        )
        assert correction.status_code == 403, correction.text
        final_clock_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert final_clock_out.status_code == 200, final_clock_out.text


def test_auth_version_invalidates_tokens_for_password_and_membership_changes(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "version-owner@example.com", "Version Child Care")
        owner_headers = _headers(owner)
        facility, _, room, other_room = _create_facility_tree(
            client,
            owner_headers,
            prefix="Version",
        )
        workspace = _workspace(client, owner_headers)
        educator_role = _role(workspace, "educator")
        administrator_role = _role(workspace, "administrator")
        _, token = _invite(
            client,
            owner_headers,
            email="version-educator@example.com",
            first_name="Version",
            role_id=educator_role["id"],
            facility_ids=[facility["id"]],
            room_ids=[room["id"]],
        )
        educator = _accept_invitation(client, token)
        original_headers = _headers(educator)
        membership_id = educator["user"]["membership_id"]

        stale_after_self_change = _issue_password_reset(client, owner_headers, membership_id)
        assert _reset_preview(client, stale_after_self_change).status_code == 200
        changed = client.post(
            "/api/v1/auth/change-password",
            headers=original_headers,
            json={"current_password": PASSWORD, "new_password": REPLACEMENT_PASSWORD},
        )
        assert changed.status_code == 204, changed.text
        assert _reset_preview(client, stale_after_self_change).status_code == 410
        assert (
            client.post(
                "/api/v1/auth/password-reset/complete",
                json={"token": stale_after_self_change, "password": RESET_PASSWORD},
            ).status_code
            == 410
        )
        assert client.get("/api/v1/auth/me", headers=original_headers).status_code == 401
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "version-educator@example.com", "password": PASSWORD},
            ).status_code
            == 401
        )

        after_change = _login(
            client,
            "version-educator@example.com",
            REPLACEMENT_PASSWORD,
        )
        after_change_headers = _headers(after_change)
        concurrent_reset_token = _issue_password_reset(client, owner_headers, membership_id)
        reset_token = _issue_password_reset(client, owner_headers, membership_id)
        concurrent_challenge_id = concurrent_reset_token.split(".", 2)[1]
        with application.state.database.engine.begin() as connection:
            restored = connection.execute(
                text(
                    "UPDATE password_reset_challenges SET revoked_at = NULL "
                    "WHERE lower(replace(CAST(id AS TEXT), '-', '')) = :challenge_id"
                ),
                {"challenge_id": concurrent_challenge_id.replace("-", "").lower()},
            )
            assert restored.rowcount == 1
        assert _reset_preview(client, concurrent_reset_token).status_code == 200
        preview = _reset_preview(client, reset_token)
        assert preview.status_code == 200, preview.text
        completed = client.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": reset_token, "password": RESET_PASSWORD},
        )
        assert completed.status_code in {200, 204}, completed.text
        assert _reset_preview(client, concurrent_reset_token).status_code == 410
        assert client.get("/api/v1/auth/me", headers=after_change_headers).status_code == 401
        reused = client.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": reset_token, "password": RESET_PASSWORD},
        )
        assert reused.status_code == 410, reused.text

        after_reset = _login(client, "version-educator@example.com", RESET_PASSWORD)
        after_reset_headers = _headers(after_reset)

        stale_after_scope_change = _issue_password_reset(client, owner_headers, membership_id)
        scope_changed = client.patch(
            f"/api/v1/staff/members/{membership_id}",
            headers=owner_headers,
            json=_member_patch(
                role_id=educator_role["id"],
                facility_ids=[facility["id"]],
                room_ids=[other_room["id"]],
            ),
        )
        assert scope_changed.status_code == 200, scope_changed.text
        assert _reset_preview(client, stale_after_scope_change).status_code == 410
        assert not {
            "staff:manage",
            "staff:manage_educators",
        }.intersection(educator_role["permissions"])
        with application.state.database.session_factory() as session:
            assignment_notification = session.scalar(
                select(UserNotification).where(
                    UserNotification.action_entity_id == UUID(membership_id),
                    UserNotification.event_key.like(f"staff-assignment:{membership_id}:%"),
                )
            )
            assert assignment_notification is not None
            assert assignment_notification.action_path == "/today"

        stale_after_promotion = _issue_password_reset(client, owner_headers, membership_id)
        promoted = client.patch(
            f"/api/v1/staff/members/{membership_id}",
            headers=owner_headers,
            json=_member_patch(
                role_id=administrator_role["id"],
                facility_ids=[],
                room_ids=[],
            ),
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"]["key"] == "administrator"
        assert _reset_preview(client, stale_after_promotion).status_code == 410

        stale_after_suspension = _issue_password_reset(client, owner_headers, membership_id)
        suspended = client.patch(
            f"/api/v1/staff/members/{membership_id}",
            headers=owner_headers,
            json=_member_patch(
                role_id=administrator_role["id"],
                facility_ids=[],
                room_ids=[],
                status="suspended",
            ),
        )
        assert suspended.status_code == 200, suspended.text
        assert suspended.json()["membership_status"] == "suspended"
        assert _reset_preview(client, stale_after_suspension).status_code == 410
        assert client.get("/api/v1/auth/me", headers=after_reset_headers).status_code == 401
        with application.state.database.session_factory() as session:
            access_notifications = list(
                session.scalars(
                    select(UserNotification).where(
                        UserNotification.event_key.like(f"staff-assignment:{membership_id}:%")
                    )
                )
            )
            assert any(
                item.action_path is None
                and item.action_entity_type is None
                and item.action_entity_id is None
                for item in access_notifications
            )

        rejected_while_suspended = client.post(
            f"/api/v1/staff/members/{membership_id}/password-reset",
            headers=owner_headers,
        )
        assert rejected_while_suspended.status_code == 409
        assert "active staff membership" in rejected_while_suspended.json()["detail"]

        # Re-open the just-revoked row to simulate a challenge that raced with
        # suspension. Completion must still fail while suspended, and the
        # subsequent reactivation must revoke it again.
        suspended_challenge_id = stale_after_suspension.split(".", 2)[1]
        with application.state.database.engine.begin() as connection:
            restored = connection.execute(
                text(
                    "UPDATE password_reset_challenges SET revoked_at = NULL "
                    "WHERE lower(replace(CAST(id AS TEXT), '-', '')) = :challenge_id"
                ),
                {"challenge_id": suspended_challenge_id.replace("-", "").lower()},
            )
            assert restored.rowcount == 1
        assert _reset_preview(client, stale_after_suspension).status_code == 410
        inactive_completion = client.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": stale_after_suspension, "password": REPLACEMENT_PASSWORD},
        )
        assert inactive_completion.status_code == 410, inactive_completion.text

        reactivated = client.patch(
            f"/api/v1/staff/members/{membership_id}",
            headers=owner_headers,
            json=_member_patch(
                role_id=administrator_role["id"],
                facility_ids=[],
                room_ids=[],
                status="active",
            ),
        )
        assert reactivated.status_code == 200, reactivated.text
        assert _reset_preview(client, stale_after_suspension).status_code == 410
        assert client.get("/api/v1/auth/me", headers=after_reset_headers).status_code == 401
        final_login = _login(client, "version-educator@example.com", RESET_PASSWORD)
        assert final_login["user"]["membership_status"] == "active"
        assert final_login["user"]["role"]["key"] == "administrator"


def test_staff_ids_and_assignments_fail_closed_across_tenants(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        first = _register(client, "tenant-one-owner@example.com", "Tenant One")
        second = _register(client, "tenant-two-owner@example.com", "Tenant Two")
        first_headers = _headers(first)
        second_headers = _headers(second)
        first_facility, _, first_room, _ = _create_facility_tree(
            client,
            first_headers,
            prefix="Tenant One",
        )
        first_workspace = _workspace(client, first_headers)
        first_educator_role = _role(first_workspace, "educator")
        invitation, token = _invite(
            client,
            first_headers,
            email="tenant-one-educator@example.com",
            first_name="Tenant",
            role_id=first_educator_role["id"],
            facility_ids=[first_facility["id"]],
            room_ids=[first_room["id"]],
        )
        educator = _accept_invitation(client, token)

        assert (
            client.post(
                f"/api/v1/staff/invitations/{invitation['id']}/regenerate",
                headers=second_headers,
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/staff/invitations/{invitation['id']}",
                headers=second_headers,
            ).status_code
            == 404
        )

        second_workspace = _workspace(client, second_headers)
        second_educator_role = _role(second_workspace, "educator")
        foreign_member = client.patch(
            f"/api/v1/staff/members/{educator['user']['membership_id']}",
            headers=second_headers,
            json=_member_patch(
                role_id=second_educator_role["id"],
                facility_ids=[],
                room_ids=[],
                status="suspended",
            ),
        )
        assert foreign_member.status_code == 404, foreign_member.text

        foreign_assignment = client.post(
            "/api/v1/staff/invitations",
            headers=second_headers,
            json={
                "email": "foreign-assignment@example.com",
                "first_name": "Foreign",
                "last_name": "Assignment",
                "role_id": second_educator_role["id"],
                "assigned_facility_ids": [first_facility["id"]],
                "assigned_room_ids": [first_room["id"]],
            },
        )
        assert foreign_assignment.status_code == 404, foreign_assignment.text

        visible_first_ids = {
            item["membership_id"] for item in _workspace(client, first_headers)["members"]
        }
        visible_second_ids = {
            item["membership_id"] for item in _workspace(client, second_headers)["members"]
        }
        assert educator["user"]["membership_id"] in visible_first_ids
        assert educator["user"]["membership_id"] not in visible_second_ids
