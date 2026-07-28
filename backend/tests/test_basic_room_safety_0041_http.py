"""Bounded HTTP regressions for the 0041 room-safety command boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.basic.models import (
    BasicBase,
    MembershipRoomAssignment,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    StaffRoomPresenceSession,
    StaffShift,
)
from app.basic.room_safety import request_sha256
from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct-password-123"


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="room-safety-http-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, suffix: str = "owner") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{suffix}@example.test",
            "password": PASSWORD,
            "first_name": "Room",
            "last_name": "Owner",
            "organization_name": f"{suffix.title()} Child Care",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _workspace(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/staff/workspace", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _role(workspace: dict, key: str) -> dict:
    return next(value for value in workspace["roles"] if value["key"] == key)


def _facility_tree(
    client: TestClient,
    headers: dict[str, str],
    prefix: str,
    *,
    room_count: int = 2,
) -> tuple[dict, list[dict]]:
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
    rooms: list[dict] = []
    for index in range(room_count):
        room_response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"{prefix} Room {index + 1}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert room_response.status_code == 201, room_response.text
        rooms.append(room_response.json())
    return facility, rooms


def _activation_secret(value: str) -> str:
    fragment = parse_qs(urlparse(value).fragment)
    return fragment["token"][0]


def _invite(
    client: TestClient,
    owner_headers: dict[str, str],
    *,
    email: str,
    role_id: str,
    facility_ids: list[str],
    room_ids: list[str],
) -> dict:
    response = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": email,
            "first_name": "Scoped",
            "last_name": "Staff",
            "role_id": role_id,
            "assigned_facility_ids": facility_ids,
            "assigned_room_ids": room_ids,
        },
    )
    assert response.status_code == 201, response.text
    token = _activation_secret(response.json()["activation_url"])
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _reviewed_activation(status: dict, operation_id: UUID) -> dict:
    return {
        "client_operation_id": str(operation_id),
        "expected_active_facility_count": status["active_facility_count"],
        "expected_facility_set_sha256": status["facility_set_sha256"],
        "expected_facility_ids": status["missing_facility_ids"],
    }


def test_release_activation_binds_reviewed_set_and_hides_foreign_receipts(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "release-owner")
        owner_headers = _headers(owner)
        _facility_tree(client, owner_headers, "Reviewed", room_count=1)
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        reviewed = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        )
        assert reviewed.status_code == 200, reviewed.text
        stale_review = reviewed.json()

        # A facility created after GET must invalidate that reviewed POST.
        _facility_tree(client, owner_headers, "Changed", room_count=1)
        stale = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=_reviewed_activation(stale_review, uuid4()),
        )
        assert stale.status_code == 409, stale.text
        assert (
            stale.json()["detail"]["code"]
            == "release_reconciliation_facility_set_changed_retry"
        )

        current = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        ).json()
        before_capability = client.get(
            "/api/v1/room-safety/capability",
            headers=owner_headers,
        )
        assert before_capability.status_code == 503
        assert (
            before_capability.json()["detail"]["code"]
            == "room_presence_release_reconciliation_required"
        )
        operation_id = uuid4()
        payload = _reviewed_activation(current, operation_id)
        activated = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=payload,
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["client_operation_id"] == str(operation_id)
        completed_status = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        )
        assert completed_status.status_code == 200, completed_status.text
        assert completed_status.json()["complete"] is True
        assert completed_status.json()["missing_facility_ids"] == []
        capability = client.get(
            "/api/v1/room-safety/capability",
            headers=owner_headers,
        )
        assert capability.status_code == 200, capability.text
        assert capability.json()["runtime_available"] is True

        exact_replay = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=payload,
        )
        assert exact_replay.status_code == 200, exact_replay.text
        assert exact_replay.json()["replayed"] is True

        workspace = _workspace(client, owner_headers)
        administrator = _invite(
            client,
            owner_headers,
            email="foreign-release-replay@example.test",
            role_id=_role(workspace, "administrator")["id"],
            facility_ids=[],
            room_ids=[],
        )
        foreign_replay = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=_headers(administrator),
            json=payload,
        )
        assert foreign_replay.status_code == 404, foreign_replay.text
        assert foreign_replay.json() == {
            "detail": "Release reconciliation operation not found"
        }
        assert "receipt" not in foreign_replay.text.lower()

        competing = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=_reviewed_activation(current, uuid4()),
        )
        assert competing.status_code == 409, competing.text
        assert competing.json() == {
            "detail": {"code": "release_reconciliation_already_complete"}
        }
        assert "receipt" not in competing.text.lower()

        fake_id = uuid4()
        reused = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json={
                "client_operation_id": str(operation_id),
                "expected_active_facility_count": 1,
                "expected_facility_ids": [str(fake_id)],
                "expected_facility_set_sha256": request_sha256(
                    {"facility_ids": [str(fake_id)]}
                ),
            },
        )
        assert reused.status_code == 409, reused.text
        assert (
            reused.json()["detail"]["code"]
            == "release_reconciliation_operation_reused"
        )


def test_release_activation_rejects_custom_facility_scoped_role(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "leader-owner")
        owner_headers = _headers(owner)
        facility, rooms = _facility_tree(
            client, owner_headers, "Leader", room_count=1
        )
        workspace = _workspace(client, owner_headers)
        administrator = _invite(
            client,
            owner_headers,
            email="custom-release@example.test",
            role_id=_role(workspace, "administrator")["id"],
            facility_ids=[],
            room_ids=[],
        )
        with application.state.database.session_factory() as session:
            membership = session.get(
                OrganizationMembership,
                UUID(administrator["user"]["membership_id"]),
            )
            assert membership is not None
            role = session.get(Role, membership.role_id)
            assert role is not None
            assert {
                "facility:read",
                "facility:manage",
                "care_roster:read",
                "staff:manage_educators",
            }.issubset(set(role.permissions or []))
            role.key = "custom_facility_operator"
            session.add(
                MembershipRoomAssignment(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    facility_id=UUID(facility["id"]),
                    room_id=UUID(rooms[0]["id"]),
                    created_by_user_id=UUID(owner["user"]["id"]),
                    is_active=True,
                )
            )
            session.commit()
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        denied = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=_headers(administrator),
        )
        assert denied.status_code == 403, denied.text
        assert (
            denied.json()["detail"]["code"]
            == "release_reconciliation_leader_required"
        )

        from app.api.basic import organization

        original_lock = organization.lock_facility_projection

        def revoke_after_lane(session, organization_id, facility_id):
            original_lock(session, organization_id, facility_id)
            assignment = session.scalar(
                select(MembershipRoomAssignment).where(
                    MembershipRoomAssignment.organization_id
                    == organization_id,
                    MembershipRoomAssignment.membership_id
                    == UUID(administrator["user"]["membership_id"]),
                    MembershipRoomAssignment.room_id
                    == UUID(rooms[0]["id"]),
                    MembershipRoomAssignment.is_active.is_(True),
                )
            )
            assert assignment is not None
            assignment.is_active = False
            session.flush()

        monkeypatch.setattr(
            organization,
            "lock_facility_projection",
            revoke_after_lane,
        )
        preview = client.get(
            f"/api/v1/rooms/{rooms[0]['id']}/deactivation-impact",
            headers=_headers(administrator),
        )
        assert preview.status_code == 404, preview.text
        patch = client.patch(
            f"/api/v1/rooms/{rooms[0]['id']}",
            headers=_headers(administrator),
            json={"name": "Must not change"},
        )
        assert patch.status_code == 404, patch.text


def _educator_world(
    client: TestClient,
    owner: dict,
    *,
    prefix: str,
    room_count: int = 2,
) -> tuple[dict, list[dict], dict]:
    owner_headers = _headers(owner)
    facility, rooms = _facility_tree(
        client, owner_headers, prefix, room_count=room_count
    )
    workspace = _workspace(client, owner_headers)
    educator = _invite(
        client,
        owner_headers,
        email=f"{prefix.lower()}-educator@example.test",
        role_id=_role(workspace, "educator")["id"],
        facility_ids=[facility["id"]],
        room_ids=[room["id"] for room in rooms],
    )
    return facility, rooms, educator


def test_clock_http_requires_room_decision_and_terminal_input_is_private(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "clock-owner")
        facility, rooms, educator = _educator_world(
            client, owner, prefix="Clock"
        )
        educator_headers = _headers(educator)
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        clock_in_operation = uuid4()
        clock_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(clock_in_operation),
            },
        )
        assert clock_in.status_code == 201, clock_in.text
        projection = clock_in.json()
        assert projection["room_presence_required"] is True
        assert projection["current_room_presence"] is None
        assert projection["room_presence_decision_reason"] == (
            "room_selection_required"
        )
        assert {value["id"] for value in projection["eligible_rooms"]} == {
            value["id"] for value in rooms
        }

        exact_replay = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(clock_in_operation),
            },
        )
        assert exact_replay.status_code == 201, exact_replay.text
        assert exact_replay.json()["id"] == projection["id"]

        room_on_terminal = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
                "room_id": rooms[0]["id"],
            },
        )
        assert room_on_terminal.status_code == 422, room_on_terminal.text
        assert (
            room_on_terminal.json()["detail"]["code"]
            == "clock_out_room_id_forbidden"
        )

        arbitrary_facility = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": str(uuid4()),
                "operation_id": str(uuid4()),
            },
        )
        assert arbitrary_facility.status_code == 409, arbitrary_facility.text
        assert (
            arbitrary_facility.json()["detail"]["code"]
            == "open_shift_mismatch"
        )

        clock_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
            },
        )
        assert clock_out.status_code == 200, clock_out.text
        assert clock_out.json()["status"] == "closed"


def test_staff_marker_keeps_roomless_open_shift_recoverable(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "roomless-marker-owner")
        owner_headers = _headers(owner)
        facility, rooms, educator = _educator_world(
            client,
            owner,
            prefix="RoomlessMarker",
            room_count=2,
        )
        educator_headers = _headers(educator)
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        reviewed = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        ).json()
        activated = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=_reviewed_activation(reviewed, uuid4()),
        )
        assert activated.status_code == 200, activated.text

        clock_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
            },
        )
        assert clock_in.status_code == 201, clock_in.text
        assert clock_in.json()["current_room_presence"] is None
        assert (
            clock_in.json()["room_presence_decision_reason"]
            == "room_selection_required"
        )

        with application.state.database.session_factory() as session:
            assignments = list(
                session.scalars(
                    select(MembershipRoomAssignment).where(
                        MembershipRoomAssignment.organization_id
                        == UUID(owner["user"]["organization_id"]),
                        MembershipRoomAssignment.membership_id
                        == UUID(educator["user"]["membership_id"]),
                        MembershipRoomAssignment.is_active.is_(True),
                    )
                )
            )
            assert {value.room_id for value in assignments} == {
                UUID(room["id"]) for room in rooms
            }
            for assignment in assignments:
                assignment.is_active = False
            session.commit()

        bootstrap = client.get(
            "/api/v1/staff/self",
            headers=educator_headers,
        )
        assert bootstrap.status_code == 200, bootstrap.text
        assert bootstrap.json()["open_shift"]["id"] == clock_in.json()["id"]
        assert bootstrap.json()["assigned_rooms"] == []
        assert (
            bootstrap.json()["live_room_presence_safety_board"][
                "runtime_available"
            ]
            is True
        )

        presence = client.get(
            "/api/v1/staff/self/room-presence",
            headers=educator_headers,
        )
        assert presence.status_code == 200, presence.text
        assert presence.json()["open_shift"]["id"] == clock_in.json()["id"]
        assert presence.json()["eligible_rooms"] == []
        assert presence.json()["current_presence"] is None
        assert presence.json()["room_presence_required"] is True
        assert presence.json()["decision_reason"] == "no_eligible_room"

        live = client.get(
            "/api/v1/staff/self/room-safety/live",
            headers=educator_headers,
        )
        assert live.status_code == 200, live.text
        assert live.json()["facility_id"] == facility["id"]
        assert live.json()["current_room"] is None
        assert live.json()["unavailable_reason"] == "room_presence_required"

        clock_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
            },
        )
        assert clock_out.status_code == 200, clock_out.text
        assert clock_out.json()["status"] == "closed"


def test_staff_marker_attests_the_live_board_permission_conjunction(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "marker-permission-owner")
        owner_headers = _headers(owner)
        _facility, _rooms, educator = _educator_world(
            client,
            owner,
            prefix="MarkerPermission",
            room_count=1,
        )
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        reviewed = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        ).json()
        activated = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=_reviewed_activation(reviewed, uuid4()),
        )
        assert activated.status_code == 200, activated.text

        with application.state.database.session_factory() as session:
            membership = session.get(
                OrganizationMembership,
                UUID(educator["user"]["membership_id"]),
            )
            assert membership is not None
            role = session.get(Role, membership.role_id)
            assert role is not None
            assert "child_safety:read" in (role.permissions or [])
            role.permissions = [
                permission
                for permission in role.permissions
                if permission != "child_safety:read"
            ]
            session.commit()

        bootstrap = client.get(
            "/api/v1/staff/self",
            headers=_headers(educator),
        )
        assert bootstrap.status_code == 200, bootstrap.text
        assert "live_room_presence_safety_board" not in bootstrap.json()
        denied = client.get(
            "/api/v1/staff/self/room-safety/live",
            headers=_headers(educator),
        )
        assert denied.status_code == 403, denied.text


def test_clock_out_recovers_all_duplicate_open_shifts_and_presences(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "terminal-owner")
        facility, rooms, educator = _educator_world(
            client, owner, prefix="Terminal", room_count=1
        )
        educator_headers = _headers(educator)
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        clock_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
                "room_id": rooms[0]["id"],
            },
        )
        assert clock_in.status_code == 201, clock_in.text

        with application.state.database.engine.begin() as connection:
            for index_name in (
                "uq_staff_shifts_open_membership",
                "uq_room_presence_sessions_open_membership",
                "uq_room_presence_sessions_open_shift",
            ):
                connection.exec_driver_sql(
                    f'DROP INDEX IF EXISTS "{index_name}"'
                )
        with application.state.database.session_factory() as session:
            original_shift = session.get(
                StaffShift, UUID(clock_in.json()["id"])
            )
            assert original_shift is not None
            original_presence = session.scalar(
                select(StaffRoomPresenceSession).where(
                    StaffRoomPresenceSession.organization_id
                    == original_shift.organization_id,
                    StaffRoomPresenceSession.membership_id
                    == original_shift.membership_id,
                    StaffRoomPresenceSession.ended_at.is_(None),
                )
            )
            assert original_presence is not None
            duplicate_shift = StaffShift(
                organization_id=original_shift.organization_id,
                membership_id=original_shift.membership_id,
                facility_id=original_shift.facility_id,
                status="open",
                clocked_in_at=datetime.now(UTC),
                clocked_out_at=None,
            )
            session.add(duplicate_shift)
            session.flush()
            session.add(
                StaffRoomPresenceSession(
                    organization_id=original_presence.organization_id,
                    membership_id=original_presence.membership_id,
                    staff_shift_id=duplicate_shift.id,
                    facility_id=original_presence.facility_id,
                    room_id=original_presence.room_id,
                    source="staff_selected",
                    started_at=datetime.now(UTC),
                    ended_at=None,
                    end_reason=None,
                    start_operation_id=uuid4(),
                    end_operation_id=None,
                    started_by_user_id=original_presence.started_by_user_id,
                    ended_by_user_id=None,
                    version=1,
                )
            )
            session.commit()

        clock_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
            },
        )
        assert clock_out.status_code == 200, clock_out.text
        with application.state.database.session_factory() as session:
            shifts = list(
                session.scalars(
                    select(StaffShift).where(
                        StaffShift.membership_id
                        == UUID(educator["user"]["membership_id"])
                    )
                )
            )
            presences = list(
                session.scalars(
                    select(StaffRoomPresenceSession).where(
                        StaffRoomPresenceSession.membership_id
                        == UUID(educator["user"]["membership_id"])
                    )
                )
            )
            assert len(shifts) == 2
            assert all(
                value.status == "closed"
                and value.clocked_out_at is not None
                for value in shifts
            )
            assert len(presences) == 2
            assert all(
                value.ended_at is not None
                and value.end_reason == "clocked_out"
                and value.version == 2
                for value in presences
            )


def test_direct_presence_and_ack_realtime_are_exactly_once_and_pii_free(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "realtime-owner")
        owner_headers = _headers(owner)
        facility, rooms, educator = _educator_world(
            client, owner, prefix="Realtime"
        )
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        reviewed = client.get(
            "/api/v1/room-safety/release-reconciliation/status",
            headers=owner_headers,
        ).json()
        activation = client.post(
            "/api/v1/room-safety/release-reconciliation",
            headers=owner_headers,
            json=_reviewed_activation(reviewed, uuid4()),
        )
        assert activation.status_code == 200, activation.text

        educator_headers = _headers(educator)
        clock_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
            },
        )
        assert clock_in.status_code == 201, clock_in.text
        exceptions = client.get(
            "/api/v1/room-safety/exceptions",
            headers=owner_headers,
            params={"facility_id": facility["id"], "state": "open"},
        )
        assert exceptions.status_code == 200, exceptions.text
        unlocated = next(
            value
            for value in exceptions.json()["items"]
            if value["condition_code"]
            == "open_shift_staff_without_current_room"
        )
        ack_operation = uuid4()
        ack_payload = {
            "client_operation_id": str(ack_operation),
            "expected_version": unlocated["version"],
            "reason": "Director reviewed the current room-location signal.",
        }
        acknowledged = client.post(
            (
                "/api/v1/room-safety/exceptions/"
                f"{unlocated['id']}/acknowledge"
            ),
            headers=owner_headers,
            json=ack_payload,
        )
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["replayed"] is False
        ack_replay = client.post(
            (
                "/api/v1/room-safety/exceptions/"
                f"{unlocated['id']}/acknowledge"
            ),
            headers=owner_headers,
            json=ack_payload,
        )
        assert ack_replay.status_code == 200, ack_replay.text
        assert ack_replay.json()["replayed"] is True

        start_operation = uuid4()
        start_payload = {
            "client_operation_id": str(start_operation),
            "staff_shift_id": clock_in.json()["id"],
            "facility_id": facility["id"],
            "room_id": rooms[0]["id"],
        }
        started = client.post(
            "/api/v1/staff/self/room-presence/start",
            headers=educator_headers,
            json=start_payload,
        )
        assert started.status_code == 201, started.text
        assert started.json()["replayed"] is False
        presence_id = started.json()["affected_session_id"]

        ended = client.post(
            "/api/v1/staff/self/room-presence/end",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_session_id": presence_id,
                "expected_version": 1,
                "reason": "Leaving this room for another duty.",
            },
        )
        assert ended.status_code == 200, ended.text
        assert ended.json()["current_resource_version"] == 2

        start_replay = client.post(
            "/api/v1/staff/self/room-presence/start",
            headers=educator_headers,
            json=start_payload,
        )
        assert start_replay.status_code == 201, start_replay.text
        assert start_replay.json()["replayed"] is True
        assert start_replay.json()["current_resource_version"] == 2

        with application.state.database.session_factory() as session:
            relevant = list(
                session.scalars(
                    select(RealtimeEvent).where(
                        RealtimeEvent.organization_id
                        == UUID(owner["user"]["organization_id"]),
                        RealtimeEvent.event_type.in_(
                            (
                                "staff_room_presence.started",
                                "room_operational_exception.acknowledged",
                            )
                        ),
                    )
                )
            )
            grouped = {
                event_type: [
                    value
                    for value in relevant
                    if value.event_type == event_type
                ]
                for event_type in (
                    "staff_room_presence.started",
                    "room_operational_exception.acknowledged",
                )
            }
            assert all(len(values) == 1 for values in grouped.values())
            assert grouped[
                "staff_room_presence.started"
            ][0].entity_id == UUID(presence_id)
            assert grouped[
                "room_operational_exception.acknowledged"
            ][0].entity_id == UUID(unlocated["id"])
            for value in relevant:
                assert set(value.payload or {}) == {
                    "event_id",
                    "facility_id",
                    "room_id",
                    "requires_action",
                }
                serialized = str(value.payload).lower()
                assert not any(
                    forbidden in serialized
                    for forbidden in (
                        "email",
                        "first_name",
                        "last_name",
                        "reason",
                    )
                )


def test_clock_in_rechecks_room_assignment_after_facility_lane(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "race-owner")
        facility, rooms, educator = _educator_world(
            client, owner, prefix="Race", room_count=1
        )
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        from app.api.basic import staff_operations

        original_lock = staff_operations.lock_facility_projection

        def revoke_after_lane(session, organization_id, facility_id):
            original_lock(session, organization_id, facility_id)
            assignment = session.scalar(
                select(MembershipRoomAssignment).where(
                    MembershipRoomAssignment.organization_id
                    == organization_id,
                    MembershipRoomAssignment.membership_id
                    == UUID(educator["user"]["membership_id"]),
                    MembershipRoomAssignment.room_id
                    == UUID(rooms[0]["id"]),
                    MembershipRoomAssignment.is_active.is_(True),
                )
            )
            assert assignment is not None
            assignment.is_active = False
            session.flush()

        monkeypatch.setattr(
            staff_operations,
            "lock_facility_projection",
            revoke_after_lane,
        )
        denied = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=_headers(educator),
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
                "room_id": rooms[0]["id"],
            },
        )
        assert denied.status_code == 404, denied.text
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(StaffShift.id).where(
                        StaffShift.membership_id
                        == UUID(educator["user"]["membership_id"])
                    )
                )
                is None
            )


def test_attendance_rechecks_current_scope_before_source_records(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "attendance-race-owner")
        facility, rooms, educator = _educator_world(
            client, owner, prefix="AttendanceRace", room_count=1
        )
        application.state.live_room_presence_safety_board_foundation_enabled = (
            True
        )
        from app.api.basic import attendance

        original_lock = attendance.lock_facility_projection

        def revoke_after_lane(session, organization_id, facility_id):
            original_lock(session, organization_id, facility_id)
            assignment = session.scalar(
                select(MembershipRoomAssignment).where(
                    MembershipRoomAssignment.organization_id
                    == organization_id,
                    MembershipRoomAssignment.membership_id
                    == UUID(educator["user"]["membership_id"]),
                    MembershipRoomAssignment.room_id
                    == UUID(rooms[0]["id"]),
                    MembershipRoomAssignment.is_active.is_(True),
                )
            )
            assert assignment is not None
            assignment.is_active = False
            session.flush()

        def source_record_must_not_be_read(*_args, **_kwargs):
            raise AssertionError(
                "child source lock ran before current authority recheck"
            )

        monkeypatch.setattr(
            attendance,
            "lock_facility_projection",
            revoke_after_lane,
        )
        monkeypatch.setattr(
            attendance,
            "_lock_active_child",
            source_record_must_not_be_read,
        )
        denied = client.post(
            "/api/v1/attendance/check-in",
            headers=_headers(educator),
            json={
                "client_operation_id": str(uuid4()),
                "child_id": str(uuid4()),
                "facility_id": facility["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        assert denied.status_code == 404, denied.text
        assert denied.json()["detail"] == "Child enrollment not found"
