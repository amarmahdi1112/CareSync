"""Acceptance coverage for workforce availability, leave, templates, and coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.basic.models import (
    BasicBase,
    Role,
    Room,
    ScheduledStaffShift,
    StaffShiftTemplate,
    StaffWorkforceEvent,
)
from app.basic.security import set_rls_organization
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
        jwt_secret="staff-workforce-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"workforce-owner-{uuid4()}@example.test",
            "password": PASSWORD,
            "first_name": "Workforce",
            "last_name": "Owner",
            "organization_name": "Workforce Child Care",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility_tree(client: TestClient, headers: dict, suffix: str = "Main"):
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": f"{suffix} Centre",
            "licensed_capacity": 30,
            "status": "active",
            "timezone": "America/Edmonton",
        },
    )
    assert facility.status_code == 201, facility.text
    program = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "name": f"{suffix} Daycare",
            "program_type": "daycare",
            "capacity": 30,
        },
    )
    assert program.status_code == 201, program.text
    room = client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility.json()["id"],
            "program_id": program.json()["id"],
            "name": f"{suffix} Room",
            "capacity": 15,
        },
    )
    assert room.status_code == 201, room.text
    return facility.json(), room.json()


def _educator(client, owner_headers, facility, room, suffix="one"):
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    role = next(item for item in workspace.json()["roles"] if item["key"] == "educator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"workforce-{suffix}-{uuid4()}@example.test",
            "first_name": "Ada",
            "last_name": suffix.title(),
            "role_id": role["id"],
            "assigned_facility_ids": [facility["id"]],
            "assigned_room_ids": [room["id"]],
        },
    )
    assert invitation.status_code == 201, invitation.text
    token = parse_qs(urlparse(invitation.json()["activation_url"]).fragment)["token"][0]
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _administrator(client, owner_headers):
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    role = next(item for item in workspace.json()["roles"] if item["key"] == "administrator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"workforce-admin-{uuid4()}@example.test",
            "first_name": "Admin",
            "last_name": "Manager",
            "role_id": role["id"],
            "assigned_facility_ids": [],
            "assigned_room_ids": [],
        },
    )
    assert invitation.status_code == 201, invitation.text
    token = parse_qs(urlparse(invitation.json()["activation_url"]).fragment)["token"][0]
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _setup(tmp_path):
    client, application = _client(tmp_path)
    owner = _register(client)
    owner_headers = _headers(owner)
    facility, room = _facility_tree(client, owner_headers)
    educator = _educator(client, owner_headers, facility, room)
    return client, application, owner, educator, facility, room


def _schedule(client, headers, educator, facility, room, start, end):
    response = client.post(
        "/api/v1/staff-schedules",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": educator["user"]["id"],
            "facility_id": facility["id"],
            "room_id": room["id"],
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_availability_receipts_delete_and_publish_override(tmp_path):
    client, application, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    staff_headers = _headers(educator)
    operation = str(uuid4())
    put = client.put(
        f"/api/v1/staff/self/availability/{facility['id']}",
        headers=staff_headers,
        json={
            "client_operation_id": operation,
            "expected_updated_at": None,
            "windows": [{"weekday": 0, "start_local": "09:00", "end_local": "12:00"}],
            "note": "Mornings only",
        },
    )
    assert put.status_code == 200, put.text
    assert put.json()["recorded_operation_id"] == operation
    assert put.json()["profile"]["recorded_operation_id"] == operation
    assert (
        client.put(
            f"/api/v1/staff/self/availability/{facility['id']}",
            headers=staff_headers,
            json={
                "client_operation_id": operation,
                "expected_updated_at": None,
                "windows": [{"weekday": 0, "start_local": "09:00", "end_local": "12:00"}],
                "note": "Mornings only",
            },
        ).status_code
        == 200
    )

    start = datetime(2026, 7, 20, 19, 0, tzinfo=UTC)  # 1 PM Edmonton, outside profile.
    schedule = _schedule(
        client, owner_headers, educator, facility, room, start, start + timedelta(hours=2)
    )
    blocked = client.post(
        f"/api/v1/staff-schedules/{schedule['id']}/publish",
        headers=owner_headers,
        json={"client_operation_id": str(uuid4())},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "availability_override_required"
    published = client.post(
        f"/api/v1/staff-schedules/{schedule['id']}/publish",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "availability_override_reason": "Emergency coverage approved by director",
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["availability_override_reason"].startswith("Emergency")
    with application.state.database.session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(ScheduledStaffShift)
                .where(ScheduledStaffShift.id == UUID(schedule["id"]))
                .values(availability_override_reason="   ")
            )
            session.commit()
        session.rollback()

    delete_operation = str(uuid4())
    deleted = client.request(
        "DELETE",
        f"/api/v1/staff/self/availability/{facility['id']}",
        headers=staff_headers,
        json={
            "client_operation_id": delete_operation,
            "expected_updated_at": put.json()["profile"]["updated_at"],
        },
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {
        "profile": None,
        "recorded_operation_id": delete_operation,
        "generated_at": deleted.json()["generated_at"],
    }
    canonical = client.get(
        "/api/v1/staff/self/availability",
        headers=staff_headers,
        params={"facility_id": facility["id"]},
    )
    assert canonical.json()["profile"] is None
    assert canonical.json()["recorded_operation_id"] == delete_operation


def test_time_off_hard_conflicts_and_lifecycle(tmp_path):
    client, _, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    staff_headers = _headers(educator)
    start = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
    requested = client.post(
        "/api/v1/staff/self/time-off",
        headers=staff_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(days=1)).isoformat(),
            "category": "medical",
            "note": "Appointment",
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["can_cancel"] is True
    approve_operation = str(uuid4())
    approve_body = {
        "client_operation_id": approve_operation,
        "expected_updated_at": requested.json()["updated_at"],
        "note": "Approved",
    }
    approved = client.post(
        f"/api/v1/staff-workforce/time-off/{requested.json()['id']}/approve",
        headers=owner_headers,
        json=approve_body,
    )
    assert approved.status_code == 200, approved.text
    schedule = _schedule(
        client,
        owner_headers,
        educator,
        facility,
        room,
        start + timedelta(hours=1),
        start + timedelta(hours=5),
    )
    publish = client.post(
        f"/api/v1/staff-schedules/{schedule['id']}/publish",
        headers=owner_headers,
        json={"client_operation_id": str(uuid4())},
    )
    assert publish.status_code == 409
    assert publish.json()["detail"]["code"] == "approved_time_off_conflict"

    cancelled = client.post(
        f"/api/v1/staff/self/time-off/{requested.json()['id']}/cancel",
        headers=staff_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": approved.json()["updated_at"],
            "reason": "Appointment moved",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["can_cancel"] is False
    superseded = client.post(
        f"/api/v1/staff-workforce/time-off/{requested.json()['id']}/approve",
        headers=owner_headers,
        json=approve_body,
    )
    assert superseded.status_code == 409
    assert superseded.json()["detail"]["code"] == "operation_superseded"

    published = client.post(
        f"/api/v1/staff-schedules/{schedule['id']}/publish",
        headers=owner_headers,
        json={"client_operation_id": str(uuid4())},
    )
    assert published.status_code == 200, published.text
    second_start = start + timedelta(days=7)
    second_schedule = _schedule(
        client,
        owner_headers,
        educator,
        facility,
        room,
        second_start,
        second_start + timedelta(hours=4),
    )
    assert (
        client.post(
            f"/api/v1/staff-schedules/{second_schedule['id']}/publish",
            headers=owner_headers,
            json={"client_operation_id": str(uuid4())},
        ).status_code
        == 200
    )
    second_request = client.post(
        "/api/v1/staff/self/time-off",
        headers=staff_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": second_start.isoformat(),
            "ends_at": (second_start + timedelta(hours=8)).isoformat(),
            "category": "personal",
            "note": None,
        },
    )
    blocked_approval = client.post(
        f"/api/v1/staff-workforce/time-off/{second_request.json()['id']}/approve",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": second_request.json()["updated_at"],
            "note": None,
        },
    )
    assert blocked_approval.status_code == 409
    assert blocked_approval.json()["detail"]["code"] == "published_schedule_conflict"


def test_templates_dst_retry_and_inactive_room_projection(tmp_path):
    client, application, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    create = client.post(
        "/api/v1/staff-workforce/templates",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": room["id"],
            "name": "Monday opening",
            "weekday": 0,
            "start_local": "08:00",
            "end_local": "16:00",
            "notes": "Opening shift",
        },
    )
    assert create.status_code == 201, create.text
    with application.state.database.session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(StaffShiftTemplate)
                .where(StaffShiftTemplate.id == UUID(create.json()["id"]))
                .values(is_active=False)
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                update(StaffShiftTemplate)
                .where(StaffShiftTemplate.id == UUID(create.json()["id"]))
                .values(name="   ")
            )
            session.commit()
        session.rollback()
    instantiate_operation = str(uuid4())
    instantiate_body = {
        "client_operation_id": instantiate_operation,
        "staff_user_id": educator["user"]["id"],
        "service_date": "2026-07-20",
        "notes": None,
    }
    instantiated = client.post(
        f"/api/v1/staff-workforce/templates/{create.json()['id']}/instantiate",
        headers=owner_headers,
        json=instantiate_body,
    )
    assert instantiated.status_code == 200, instantiated.text
    deactivated = client.post(
        f"/api/v1/staff-workforce/templates/{create.json()['id']}/deactivate",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": create.json()["updated_at"],
        },
    )
    assert deactivated.status_code == 200, deactivated.text
    replay = client.post(
        f"/api/v1/staff-workforce/templates/{create.json()['id']}/instantiate",
        headers=owner_headers,
        json=instantiate_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == instantiated.json()["id"]

    with application.state.database.session_factory() as session:
        value = session.get(Room, UUID(room["id"]))
        value.is_active = False
        session.commit()
    historical = client.get(
        "/api/v1/staff-workforce/templates",
        headers=owner_headers,
        params={"active_only": "false"},
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()["items"][0]["room_name"] == room["name"]

    dst = client.post(
        "/api/v1/staff-workforce/templates",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": None,
            "name": "DST fold",
            "weekday": 6,
            "start_local": "01:30",
            "end_local": "02:30",
        },
    )
    assert dst.status_code == 201
    ambiguous = client.post(
        f"/api/v1/staff-workforce/templates/{dst.json()['id']}/instantiate",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": educator["user"]["id"],
            "service_date": "2026-11-01",
            "notes": None,
        },
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"]["code"] == "ambiguous_local_time"


def test_coverage_projection_excludes_declined_and_delete_receipt(tmp_path):
    client, _, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    second = _educator(client, owner_headers, facility, room, "two")
    target_operation = str(uuid4())
    target = client.put(
        f"/api/v1/staff-workforce/coverage-targets/{facility['id']}",
        headers=owner_headers,
        json={
            "client_operation_id": target_operation,
            "expected_updated_at": None,
            "windows": [
                {
                    "weekday": 0,
                    "start_local": "09:00",
                    "end_local": "10:00",
                    "required_staff": 2,
                }
            ],
        },
    )
    assert target.status_code == 200, target.text
    start = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)  # 9 AM Edmonton.
    first = _schedule(
        client, owner_headers, educator, facility, room, start, start + timedelta(hours=1)
    )
    published = client.post(
        f"/api/v1/staff-schedules/{first['id']}/publish",
        headers=owner_headers,
        json={"client_operation_id": str(uuid4())},
    )
    assert published.status_code == 200, published.text
    declined = client.post(
        f"/api/v1/staff/self/schedules/{first['id']}/decline",
        headers=_headers(educator),
        json={"client_operation_id": str(uuid4()), "note": "Unavailable"},
    )
    assert declined.status_code == 200, declined.text
    _schedule(client, owner_headers, second, facility, room, start, start + timedelta(hours=1))
    projection = client.get(
        "/api/v1/staff-workforce/coverage-projection",
        headers=owner_headers,
        params={
            "facility_id": facility["id"],
            "start_date": "2026-07-20",
            "end_date": "2026-07-20",
        },
    )
    assert projection.status_code == 200, projection.text
    bucket = next(item for item in projection.json()["buckets"] if item["required"] == 2)
    assert bucket == {
        **bucket,
        "required": 2,
        "published": 1,
        "acknowledged": 0,
        "declined": 1,
        "draft": 1,
        "gap": 2,
        "confirmation_gap": 2,
    }
    delete_operation = str(uuid4())
    delete_body = {
        "client_operation_id": delete_operation,
        "expected_updated_at": target.json()["updated_at"],
    }
    removed = client.request(
        "DELETE",
        f"/api/v1/staff-workforce/coverage-targets/{facility['id']}",
        headers=owner_headers,
        json=delete_body,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["recorded_operation_id"] == delete_operation
    replay = client.request(
        "DELETE",
        f"/api/v1/staff-workforce/coverage-targets/{facility['id']}",
        headers=owner_headers,
        json=delete_body,
    )
    assert replay.status_code == 200, replay.text


def test_self_routes_require_shift_clock_permission(tmp_path):
    client, application, owner, educator, facility, _ = _setup(tmp_path)
    with application.state.database.session_factory() as session:
        set_rls_organization(session, UUID(owner["user"]["organization_id"]))
        educator_role = session.scalar(
            select(Role).where(
                Role.organization_id == UUID(owner["user"]["organization_id"]),
                Role.key == "educator",
            )
        )
        educator_role.permissions = [
            item for item in educator_role.permissions if item != "shift:clock"
        ]
        session.commit()
    response = client.get(
        "/api/v1/staff/self/availability",
        headers=_headers(educator),
        params={"facility_id": facility["id"]},
    )
    assert response.status_code == 403


def test_administrator_workforce_scope_matches_staff_hierarchy(tmp_path):
    client, _, owner, educator, facility, _ = _setup(tmp_path)
    owner_headers = _headers(owner)
    educator_headers = _headers(educator)
    administrator = _administrator(client, owner_headers)
    administrator_headers = _headers(administrator)
    for headers in (owner_headers, educator_headers):
        availability = client.put(
            f"/api/v1/staff/self/availability/{facility['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": None,
                "windows": [],
                "note": None,
            },
        )
        assert availability.status_code == 200, availability.text
    start = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)
    owner_leave = client.post(
        "/api/v1/staff/self/time-off",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=8)).isoformat(),
            "category": "vacation",
            "note": None,
        },
    )
    educator_leave = client.post(
        "/api/v1/staff/self/time-off",
        headers=educator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=8)).isoformat(),
            "category": "vacation",
            "note": None,
        },
    )
    assert owner_leave.status_code == 201, owner_leave.text
    assert educator_leave.status_code == 201, educator_leave.text
    availability_list = client.get(
        "/api/v1/staff-workforce/availability",
        headers=administrator_headers,
        params={"facility_id": facility["id"]},
    )
    assert availability_list.status_code == 200, availability_list.text
    assert [item["staff_user_id"] for item in availability_list.json()["items"]] == [
        educator["user"]["id"]
    ]
    leave_list = client.get(
        "/api/v1/staff-workforce/time-off",
        headers=administrator_headers,
        params={
            "start_at": (start - timedelta(days=1)).isoformat(),
            "end_at": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert leave_list.status_code == 200, leave_list.text
    assert [item["staff_user_id"] for item in leave_list.json()["items"]] == [
        educator["user"]["id"]
    ]
    forbidden = client.post(
        f"/api/v1/staff-workforce/time-off/{owner_leave.json()['id']}/approve",
        headers=administrator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": owner_leave.json()["updated_at"],
            "note": None,
        },
    )
    assert forbidden.status_code == 404


def test_workforce_event_ledger_is_immutable_projection(tmp_path):
    client, application, owner, educator, facility, _ = _setup(tmp_path)
    operation = str(uuid4())
    response = client.put(
        f"/api/v1/staff/self/availability/{facility['id']}",
        headers=_headers(educator),
        json={
            "client_operation_id": operation,
            "expected_updated_at": None,
            "windows": [],
            "note": None,
        },
    )
    assert response.status_code == 200
    with application.state.database.session_factory() as session:
        set_rls_organization(session, UUID(owner["user"]["organization_id"]))
        event = session.scalar(
            select(StaffWorkforceEvent).where(StaffWorkforceEvent.operation_id == UUID(operation))
        )
        assert event.event_type == "replaced"
        assert event.entity_type == "staff_availability"


def test_notification_action_target_resolves_exact_canonical_workforce_rows(tmp_path):
    client, _, owner, educator, facility, _ = _setup(tmp_path)
    owner_headers = _headers(owner)
    educator_headers = _headers(educator)
    availability = client.put(
        f"/api/v1/staff/self/availability/{facility['id']}",
        headers=educator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": None,
            "windows": [{"weekday": 0, "start_local": "08:00", "end_local": "16:00"}],
            "note": "Canonical focus target",
        },
    )
    assert availability.status_code == 200, availability.text
    availability_row = availability.json()["profile"]
    start = datetime(2027, 1, 11, 15, 0, tzinfo=UTC)
    leave = client.post(
        "/api/v1/staff/self/time-off",
        headers=educator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=8)).isoformat(),
            "category": "personal",
            "note": "Canonical leave target",
        },
    )
    assert leave.status_code == 201, leave.text

    resolved_availability = client.get(
        f"/api/v1/staff-workforce/action-target/staff_availability/{availability_row['id']}",
        headers=owner_headers,
    )
    assert resolved_availability.status_code == 200, resolved_availability.text
    assert resolved_availability.json() == {
        "organization_id": owner["user"]["organization_id"],
        "entity_type": "staff_availability",
        "entity_id": availability_row["id"],
        "facility_id": facility["id"],
        "starts_at": None,
        "parent_entity_id": None,
        "membership_id": availability_row["membership_id"],
        "visible": True,
    }
    resolved_leave = client.get(
        f"/api/v1/staff-workforce/action-target/staff_time_off/{leave.json()['id']}",
        headers=owner_headers,
    )
    assert resolved_leave.status_code == 200, resolved_leave.text
    assert resolved_leave.json() == {
        "organization_id": owner["user"]["organization_id"],
        "entity_type": "staff_time_off",
        "entity_id": leave.json()["id"],
        "facility_id": facility["id"],
        "starts_at": "2027-01-11T15:00:00Z",
        "parent_entity_id": None,
        "membership_id": leave.json()["membership_id"],
        "visible": True,
    }

    administrator = _administrator(client, owner_headers)
    assert (
        client.get(
            f"/api/v1/staff-workforce/action-target/staff_time_off/{leave.json()['id']}",
            headers=_headers(administrator),
        ).status_code
        == 200
    )
    other_owner = _register(client)
    assert (
        client.get(
            f"/api/v1/staff-workforce/action-target/staff_time_off/{leave.json()['id']}",
            headers=_headers(other_owner),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/staff-workforce/action-target/staff_time_off/{availability_row['id']}",
            headers=owner_headers,
        ).status_code
        == 404
    )

    removed = client.request(
        "DELETE",
        f"/api/v1/staff/self/availability/{facility['id']}",
        headers=educator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": availability_row["updated_at"],
        },
    )
    assert removed.status_code == 200, removed.text
    stale = client.get(
        f"/api/v1/staff-workforce/action-target/staff_availability/{availability_row['id']}",
        headers=owner_headers,
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["visible"] is False
