"""Acceptance coverage for planned staff rota and actual-clock reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.basic.models import (
    AuditEvent,
    BasicBase,
    OrganizationMembership,
    UserNotification,
)
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
        jwt_secret="staff-rota-test-secret-with-at-least-32-bytes",
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
            "first_name": "Rota",
            "last_name": "Owner",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility_tree(client: TestClient, headers: dict, prefix: str) -> tuple[dict, dict]:
    facility_response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": f"{prefix} Centre", "licensed_capacity": 30, "status": "active"},
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
            "capacity": 30,
        },
    )
    assert program_response.status_code == 201, program_response.text
    room_response = client.post(
        "/api/v1/rooms",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "program_id": program_response.json()["id"],
            "name": f"{prefix} Room",
            "capacity": 15,
        },
    )
    assert room_response.status_code == 201, room_response.text
    return facility, room_response.json()


def _educator(
    client: TestClient, owner_headers: dict, facility: dict, room: dict, suffix: str = "one"
) -> dict:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    role = next(item for item in workspace.json()["roles"] if item["key"] == "educator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"rota-educator-{suffix}@example.test",
            "first_name": "Ada",
            "last_name": "Educator",
            "role_id": role["id"],
            "assigned_facility_ids": [facility["id"]],
            "assigned_room_ids": [room["id"]],
        },
    )
    assert invitation.status_code == 201, invitation.text
    url = urlparse(invitation.json()["activation_url"])
    token = parse_qs(url.fragment)["token"][0]
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _setup(tmp_path):
    client, application = _client(tmp_path)
    owner = _register(client, f"rota-owner-{uuid4()}@example.test", "Rota Child Care")
    owner_headers = _headers(owner)
    facility, room = _facility_tree(client, owner_headers, "Main")
    educator = _educator(client, owner_headers, facility, room)
    return client, application, owner, educator, facility, room


def _create_schedule(
    client: TestClient,
    owner_headers: dict,
    educator: dict,
    facility: dict,
    room: dict,
    start: datetime,
    end: datetime,
    *,
    operation_id=None,
    notes: str | None = "Infant room",
):
    return client.post(
        "/api/v1/staff-schedules",
        headers=owner_headers,
        json={
            "client_operation_id": str(operation_id or uuid4()),
            "staff_user_id": educator["user"]["id"],
            "facility_id": facility["id"],
            "room_id": room["id"],
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "notes": notes,
        },
    )


def _publish(client, headers, schedule_id: str, operation_id=None):
    return client.post(
        f"/api/v1/staff-schedules/{schedule_id}/publish",
        headers=headers,
        json={"client_operation_id": str(operation_id or uuid4())},
    )


def _acknowledge(client, headers, schedule_id: str, operation_id=None, note=None):
    return client.post(
        f"/api/v1/staff/self/schedules/{schedule_id}/acknowledge",
        headers=headers,
        json={"client_operation_id": str(operation_id or uuid4()), "note": note},
    )


def test_draft_publish_and_staff_response_are_scoped_and_exactly_idempotent(tmp_path) -> None:
    client, application, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    educator_headers = _headers(educator)
    now = datetime.now(UTC)
    operation_id = uuid4()
    payload_start = now + timedelta(days=1)
    payload_end = payload_start + timedelta(hours=8)
    with client:
        created = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            payload_start,
            payload_end,
            operation_id=operation_id,
        )
        assert created.status_code == 201, created.text
        schedule = created.json()
        assert schedule["status"] == "draft"
        assert schedule["response_status"] == "pending"
        assert schedule["staff_display_name"] == "Ada Educator"
        assert schedule["facility_timezone"] == "America/Edmonton"
        assert schedule["recorded_create_operation_id"] == str(operation_id)

        hidden = client.get(
            "/api/v1/staff/self/schedules",
            headers=educator_headers,
            params={
                "facility_id": facility["id"],
                "date": payload_start.astimezone(ZoneInfo("America/Edmonton")).date().isoformat(),
            },
        )
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["items"] == []
        cancelled_draft_start = payload_start + timedelta(days=3)
        cancelled_draft = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            cancelled_draft_start,
            cancelled_draft_start + timedelta(hours=4),
        )
        assert cancelled_draft.status_code == 201, cancelled_draft.text
        cancelled = client.post(
            f"/api/v1/staff-schedules/{cancelled_draft.json()['id']}/cancel",
            headers=owner_headers,
            json={"client_operation_id": str(uuid4()), "reason": "Coverage changed"},
        )
        assert cancelled.status_code == 200, cancelled.text
        cancelled_hidden = client.get(
            "/api/v1/staff/self/schedules",
            headers=educator_headers,
            params={
                "facility_id": facility["id"],
                "date": cancelled_draft_start.astimezone(
                    ZoneInfo("America/Edmonton")
                ).date().isoformat(),
            },
        )
        assert cancelled_hidden.status_code == 200, cancelled_hidden.text
        assert cancelled_hidden.json()["items"] == []
        forbidden = _create_schedule(
            client,
            educator_headers,
            educator,
            facility,
            room,
            payload_start + timedelta(days=2),
            payload_end + timedelta(days=2),
        )
        assert forbidden.status_code == 403

        exact = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            payload_start,
            payload_end,
            operation_id=operation_id,
        )
        assert exact.status_code == 201
        assert exact.json()["id"] == schedule["id"]
        changed = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            payload_start,
            payload_end,
            operation_id=operation_id,
            notes="Changed payload",
        )
        assert changed.status_code == 409
        assert changed.json()["detail"]["code"] == "operation_reused"

        unbounded = client.get("/api/v1/staff-schedules", headers=owner_headers)
        assert unbounded.status_code == 422
        publish_operation = uuid4()
        published = _publish(client, owner_headers, schedule["id"], publish_operation)
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "published"
        assert _publish(client, owner_headers, schedule["id"], publish_operation).status_code == 200

        visible = client.get(
            "/api/v1/staff/self/schedules",
            headers=educator_headers,
            params={
                "facility_id": facility["id"],
                "date": payload_start.astimezone(ZoneInfo("America/Edmonton")).date().isoformat(),
            },
        )
        assert visible.status_code == 200, visible.text
        assert visible.json()["total"] == 1
        response_operation = uuid4()
        acknowledged = _acknowledge(
            client, educator_headers, schedule["id"], response_operation, "Confirmed"
        )
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["response_status"] == "acknowledged"
        assert (
            _acknowledge(
                client, educator_headers, schedule["id"], response_operation, "Confirmed"
            ).status_code
            == 200
        )
        changed_response = _acknowledge(
            client, educator_headers, schedule["id"], response_operation, "Different"
        )
        assert changed_response.status_code == 409
        second_educator = _educator(
            client, owner_headers, facility, room, suffix="replay-isolation"
        )
        cross_staff_replay = _acknowledge(
            client,
            _headers(second_educator),
            schedule["id"],
            response_operation,
            "Confirmed",
        )
        assert cross_staff_replay.status_code == 404
        second_response = _acknowledge(client, educator_headers, schedule["id"])
        assert second_response.status_code == 409
        assert second_response.json()["detail"]["code"] == "schedule_response_already_recorded"

    with application.state.database.session_factory() as session:
        notifications = list(session.scalars(select(UserNotification)))
        assert {item.action_path for item in notifications} >= {"/shifts", "/staff-rota"}
        actions = set(session.scalars(select(AuditEvent.action)))
        assert {
            "staff_schedule.created",
            "staff_schedule.published",
            "staff_schedule.acknowledged",
        } <= actions


def test_draft_edit_rejects_stale_overlap_invalid_scope_and_inactive_staff(tmp_path) -> None:
    client, application, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    now = datetime.now(UTC) + timedelta(days=2)
    with client:
        created = _create_schedule(
            client, owner_headers, educator, facility, room, now, now + timedelta(hours=4)
        )
        assert created.status_code == 201, created.text
        schedule = created.json()
        edit_operation = uuid4()
        edit_payload = {
            "client_operation_id": str(edit_operation),
            "expected_updated_at": schedule["updated_at"],
            "notes": "Updated draft",
        }
        edited = client.patch(
            f"/api/v1/staff-schedules/{schedule['id']}",
            headers=owner_headers,
            json=edit_payload,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["notes"] == "Updated draft"
        exact = client.patch(
            f"/api/v1/staff-schedules/{schedule['id']}",
            headers=owner_headers,
            json=edit_payload,
        )
        assert exact.status_code == 200, exact.text
        stale = client.patch(
            f"/api/v1/staff-schedules/{schedule['id']}",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": schedule["updated_at"],
                "notes": "Stale edit",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_schedule"

        overlap = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            now + timedelta(hours=1),
            now + timedelta(hours=5),
        )
        assert overlap.status_code == 409
        assert overlap.json()["detail"]["code"] == "overlapping_schedule"

        other_facility, _ = _facility_tree(client, owner_headers, "Other")
        wrong_room = _create_schedule(
            client,
            owner_headers,
            educator,
            other_facility,
            room,
            now + timedelta(days=1),
            now + timedelta(days=1, hours=4),
        )
        assert wrong_room.status_code == 422
        assert wrong_room.json()["detail"]["code"] == "invalid_room"
        wrong_scope = client.post(
            "/api/v1/staff-schedules",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "staff_user_id": educator["user"]["id"],
                "facility_id": other_facility["id"],
                "scheduled_start_at": (now + timedelta(days=1)).isoformat(),
                "scheduled_end_at": (now + timedelta(days=1, hours=4)).isoformat(),
            },
        )
        assert wrong_scope.status_code == 422
        assert wrong_scope.json()["detail"]["code"] == "staff_scope_mismatch"
        naive = client.post(
            "/api/v1/staff-schedules",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "staff_user_id": educator["user"]["id"],
                "facility_id": facility["id"],
                "room_id": room["id"],
                "scheduled_start_at": "2026-08-01T08:00:00",
                "scheduled_end_at": "2026-08-01T16:00:00",
            },
        )
        assert naive.status_code == 422
        assert naive.json()["detail"]["code"] == "timezone_required"
        too_long = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            now + timedelta(days=3),
            now + timedelta(days=4, minutes=1),
        )
        assert too_long.status_code == 422
        assert too_long.json()["detail"]["code"] == "invalid_schedule_interval"

    with application.state.database.session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.id == UUID(educator["user"]["membership_id"])
            )
        )
        membership.status = "suspended"
        session.commit()
    with client:
        inactive = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            now + timedelta(days=5),
            now + timedelta(days=5, hours=4),
        )
        assert inactive.status_code == 422
        assert inactive.json()["detail"]["code"] == "inactive_staff"


def test_counter_proposal_has_manager_accept_and_reject_resolution(tmp_path) -> None:
    client, _, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    educator_headers = _headers(educator)
    start = datetime.now(UTC) + timedelta(days=3)
    with client:
        created = _create_schedule(
            client, owner_headers, educator, facility, room, start, start + timedelta(hours=6)
        ).json()
        assert _publish(client, owner_headers, created["id"]).status_code == 200
        proposed_start = start + timedelta(hours=1)
        propose_operation = uuid4()
        proposed = client.post(
            f"/api/v1/staff/self/schedules/{created['id']}/propose-alternate",
            headers=educator_headers,
            json={
                "client_operation_id": str(propose_operation),
                "proposed_start_at": proposed_start.isoformat(),
                "proposed_end_at": (proposed_start + timedelta(hours=6)).isoformat(),
                "note": "College appointment",
            },
        )
        assert proposed.status_code == 200, proposed.text
        assert proposed.json()["response_status"] == "alternate_proposed"
        accept_operation = uuid4()
        resolution_payload = {
            "client_operation_id": str(accept_operation),
            "expected_updated_at": proposed.json()["updated_at"],
            "note": "Approved",
        }
        accepted = client.post(
            f"/api/v1/staff-schedules/{created['id']}/alternate/accept",
            headers=owner_headers,
            json=resolution_payload,
        )
        assert accepted.status_code == 200, accepted.text
        accepted_data = accepted.json()
        assert accepted_data["response_status"] == "acknowledged"
        assert datetime.fromisoformat(accepted_data["scheduled_start_at"]) == proposed_start
        assert accepted_data["proposed_start_at"] is None
        retry = client.post(
            f"/api/v1/staff-schedules/{created['id']}/alternate/accept",
            headers=owner_headers,
            json=resolution_payload,
        )
        assert retry.status_code == 200, retry.text

        second_start = start + timedelta(days=1)
        second = _create_schedule(
            client,
            owner_headers,
            educator,
            facility,
            room,
            second_start,
            second_start + timedelta(hours=6),
        ).json()
        assert _publish(client, owner_headers, second["id"]).status_code == 200
        proposed_second = client.post(
            f"/api/v1/staff/self/schedules/{second['id']}/propose-alternate",
            headers=educator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "proposed_start_at": (second_start + timedelta(hours=1)).isoformat(),
                "proposed_end_at": (second_start + timedelta(hours=7)).isoformat(),
            },
        )
        rejected = client.post(
            f"/api/v1/staff-schedules/{second['id']}/alternate/reject",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": proposed_second.json()["updated_at"],
                "note": "Original coverage is required",
            },
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["response_status"] == "pending"
        assert rejected.json()["proposed_start_at"] is None
        assert rejected.json()["responded_at"] is None
        assert rejected.json()["response_note"] is None


def test_scheduled_clock_link_unscheduled_escape_and_reconciliation_states(tmp_path) -> None:
    client, _, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    educator_headers = _headers(educator)
    now = datetime.now(UTC)
    start = now + timedelta(minutes=10)
    with client:
        created = _create_schedule(
            client, owner_headers, educator, facility, room, start, start + timedelta(hours=1)
        ).json()
        assert _publish(client, owner_headers, created["id"]).status_code == 200
        assert _acknowledge(client, educator_headers, created["id"]).status_code == 200
        clock_operation = uuid4()
        clocked_in = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(clock_operation),
                "scheduled_shift_id": created["id"],
            },
        )
        assert clocked_in.status_code == 201, clocked_in.text
        assert clocked_in.json()["scheduled_shift_id"] == created["id"]
        exact = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(clock_operation),
                "scheduled_shift_id": created["id"],
            },
        )
        assert exact.status_code == 201
        changed_replay = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(clock_operation),
            },
        )
        assert changed_replay.status_code == 409
        assert changed_replay.json()["detail"]["code"] == "operation_reused"
        clocked_out = client.post(
            "/api/v1/staff/self/shifts/clock-out",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "operation_id": str(uuid4()),
                "scheduled_shift_id": created["id"],
            },
        )
        assert clocked_out.status_code == 200, clocked_out.text

        ad_hoc = client.post(
            "/api/v1/staff/self/shifts/clock-in",
            headers=educator_headers,
            json={"facility_id": facility["id"], "operation_id": str(uuid4())},
        )
        assert ad_hoc.status_code == 201, ad_hoc.text
        assert ad_hoc.json()["scheduled_shift_id"] is None
        reconciliation = client.get(
            "/api/v1/staff-schedules/reconciliation",
            headers=owner_headers,
            params={
                "start_at": (now - timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1)).isoformat(),
            },
        )
        assert reconciliation.status_code == 200, reconciliation.text
        scheduled = reconciliation.json()["scheduled"]
        assert scheduled[0]["reconciliation_status"] == "completed"
        assert scheduled[0]["is_late"] is False
        assert reconciliation.json()["total_unscheduled"] == 1
        assert reconciliation.json()["unscheduled"][0]["reconciliation_status"] == "unscheduled"


def test_missing_shift_reconciliation_distinguishes_late_from_missed(tmp_path) -> None:
    client, _, owner, educator, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    now = datetime.now(UTC)
    missed_start = now - timedelta(hours=2)
    missed = _create_schedule(
        client,
        owner_headers,
        educator,
        facility,
        room,
        missed_start,
        now - timedelta(hours=1),
    )
    assert missed.status_code == 201, missed.text
    assert _publish(client, owner_headers, missed.json()["id"]).status_code == 200
    late_start = now - timedelta(minutes=20)
    late = _create_schedule(
        client,
        owner_headers,
        educator,
        facility,
        room,
        late_start,
        now + timedelta(hours=1),
    )
    assert late.status_code == 201, late.text
    assert _publish(client, owner_headers, late.json()["id"]).status_code == 200
    with client:
        response = client.get(
            "/api/v1/staff-schedules/reconciliation",
            headers=owner_headers,
            params={
                "start_at": (now - timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 200, response.text
        by_id = {item["id"]: item for item in response.json()["scheduled"]}
        missed_row = by_id[missed.json()["id"]]
        assert missed_row["reconciliation_status"] == "missed"
        assert missed_row["is_late"] is False
        assert missed_row["minutes_late"] == 0
        late_row = by_id[late.json()["id"]]
        assert late_row["reconciliation_status"] == "late"
        assert late_row["is_late"] is True
        assert late_row["minutes_late"] >= 19
