"""Acceptance coverage for the recurring rota and staff exchange contract.

These tests intentionally run against an isolated SQLite database. PostgreSQL-only
serialization and RLS proofs live in ``test_basic_postgres_staff_exchange.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.basic.models import (
    BasicBase,
    Facility,
    Room,
    ScheduledStaffShift,
    StaffOpenShift,
    StaffOpenShiftEngagement,
    StaffRotationPattern,
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
        jwt_secret="staff-exchange-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, suffix: str = "one") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"exchange-owner-{suffix}-{uuid4()}@example.test",
            "password": PASSWORD,
            "first_name": "Exchange",
            "last_name": "Owner",
            "organization_name": f"Exchange Child Care {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility_tree(client: TestClient, headers: dict, suffix: str = "Main") -> tuple[dict, dict]:
    facility = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": f"{suffix} Centre",
            "licensed_capacity": 40,
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
            "capacity": 40,
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
            "capacity": 20,
        },
    )
    assert room.status_code == 201, room.text
    return facility.json(), room.json()


def _educator(
    client: TestClient,
    owner_headers: dict,
    facility: dict,
    room: dict,
    suffix: str,
) -> dict:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    role = next(item for item in workspace.json()["roles"] if item["key"] == "educator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"exchange-{suffix}-{uuid4()}@example.test",
            "first_name": suffix.title(),
            "last_name": "Educator",
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


def _setup(tmp_path, *, educator_count: int = 3):
    client, application = _client(tmp_path)
    owner = _register(client)
    owner_headers = _headers(owner)
    facility, room = _facility_tree(client, owner_headers)
    educators = [
        _educator(client, owner_headers, facility, room, suffix)
        for suffix in ("ada", "grace", "linus")[:educator_count]
    ]
    return client, application, owner, educators, facility, room


def _schedule(
    client: TestClient,
    owner_headers: dict,
    educator: dict,
    facility: dict,
    room: dict,
    start: datetime,
) -> dict:
    response = client.post(
        "/api/v1/staff-schedules",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": educator["user"]["id"],
            "facility_id": facility["id"],
            "room_id": room["id"],
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _published_acknowledged_schedule(
    client: TestClient,
    owner_headers: dict,
    educator: dict,
    facility: dict,
    room: dict,
    start: datetime,
) -> dict:
    schedule = _schedule(client, owner_headers, educator, facility, room, start)
    published = client.post(
        f"/api/v1/staff-schedules/{schedule['id']}/publish",
        headers=owner_headers,
        json={"client_operation_id": str(uuid4())},
    )
    assert published.status_code == 200, published.text
    acknowledged = client.post(
        f"/api/v1/staff/self/schedules/{schedule['id']}/acknowledge",
        headers=_headers(educator),
        json={"client_operation_id": str(uuid4()), "note": "Confirmed"},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "published"
    assert acknowledged.json()["response_status"] == "acknowledged"
    return acknowledged.json()


def _create_posted_open_shift(
    client: TestClient,
    owner_headers: dict,
    facility: dict,
    room: dict,
    start: datetime,
    *,
    source_schedule_id: str | None = None,
) -> dict:
    created = client.post(
        "/api/v1/staff-exchange/open-shifts",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": room["id"],
            "source_schedule_id": source_schedule_id,
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
            "public_note": "Coverage needed",
        },
    )
    assert created.status_code == 201, created.text
    posted = client.post(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}/post",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": created.json()["updated_at"],
        },
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "open"
    return posted.json()


def _opt_in_substitute(
    client: TestClient, educator: dict, facility: dict, operation_id: str | None = None
) -> dict:
    response = client.put(
        f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
        headers=_headers(educator),
        json={
            "client_operation_id": operation_id or str(uuid4()),
            "expected_updated_at": None,
            "active": True,
            "note": "Available for coverage",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is True
    return response.json()


def _offer(
    client: TestClient,
    owner_headers: dict,
    open_shift: dict,
    educator: dict,
    *,
    operation_id: str | None = None,
    source_interest_id: str | None = None,
    note: str = "Please cover",
) -> tuple[dict, dict]:
    body = {
        "client_operation_id": operation_id or str(uuid4()),
        "staff_user_id": educator["user"]["id"],
        "source_interest_id": source_interest_id,
        "note": note,
        "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
    }
    response = client.post(
        f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/offers",
        headers=owner_headers,
        json=body,
    )
    assert response.status_code == 201, response.text
    return response.json(), body


def test_rotation_preview_generation_bounds_digest_and_exact_receipts(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    headers = _headers(owner)
    create_operation = str(uuid4())
    slot_id = str(uuid4())
    create_body = {
        "client_operation_id": create_operation,
        "facility_id": facility["id"],
        "name": "Opening rotation",
        "anchor_date": "2027-01-04",
        "cycle_weeks": 1,
        "slots": [
            {
                "slot_id": slot_id,
                "cycle_week": 0,
                "weekday": 0,
                "staff_user_id": educators[0]["user"]["id"],
                "room_id": room["id"],
                "start_local": "08:00",
                "end_local": "16:00",
                "notes": "Opening",
            }
        ],
    }
    created = client.post("/api/v1/staff-exchange/rotations", headers=headers, json=create_body)
    assert created.status_code == 201, created.text
    assert created.json()["version"] == 1
    assert created.json()["can_preview"] is False
    assert (
        client.post("/api/v1/staff-exchange/rotations", headers=headers, json=create_body).json()
        == created.json()
    )
    reused = client.post(
        "/api/v1/staff-exchange/rotations",
        headers=headers,
        json={**create_body, "name": "Different"},
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "operation_reused"

    patch_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": created.json()["updated_at"],
        "name": "Opening rotation revised",
    }
    patched = client.patch(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}",
        headers=headers,
        json=patch_body,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Opening rotation revised"
    exact_patch = client.patch(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}",
        headers=headers,
        json=patch_body,
    )
    assert exact_patch.status_code == 200, exact_patch.text
    assert exact_patch.json() == patched.json()
    changed_precondition = client.patch(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}",
        headers=headers,
        json={**patch_body, "expected_updated_at": "2026-01-01T00:00:00Z"},
    )
    assert changed_precondition.status_code == 409
    assert changed_precondition.json()["detail"]["code"] == "operation_reused"

    activate_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": patched.json()["updated_at"],
    }
    activated = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/activate",
        headers=headers,
        json=activate_body,
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert activated.json()["can_preview"] is True
    assert len(activated.json()["snapshot_digest"]) == 64
    assert (
        client.post(
            f"/api/v1/staff-exchange/rotations/{created.json()['id']}/activate",
            headers=headers,
            json=activate_body,
        ).json()
        == activated.json()
    )

    oversized = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/preview",
        headers=headers,
        json={"start_date": "2027-01-04", "end_date": "2027-03-29"},
    )
    assert oversized.status_code == 422
    assert oversized.json()["detail"]["code"] == "invalid_rotation_preview_range"

    preview_body = {"start_date": "2027-01-04", "end_date": "2027-01-10"}
    preview = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/preview",
        headers=headers,
        json=preview_body,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["total"] == 1
    assert preview.json()["issues"] == []
    assert preview.json()["can_generate"] is True
    repeated_preview = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/preview",
        headers=headers,
        json=preview_body,
    )
    assert repeated_preview.json()["snapshot_digest"] == preview.json()["snapshot_digest"]
    assert repeated_preview.json()["occurrences"] == preview.json()["occurrences"]

    competing = _schedule(
        client,
        headers,
        educators[0],
        facility,
        room,
        datetime(2027, 1, 4, 15, 0, tzinfo=UTC),
    )
    frozen_preview_rejected = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/generate",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": activated.json()["updated_at"],
            **preview_body,
            "preview_digest": preview.json()["snapshot_digest"],
        },
    )
    assert frozen_preview_rejected.status_code == 409
    assert frozen_preview_rejected.json()["detail"]["code"] == "preview_stale"
    cancelled = client.post(
        f"/api/v1/staff-schedules/{competing['id']}/cancel",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "reason": "Restore the frozen rotation preview",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    restored_preview = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/preview",
        headers=headers,
        json=preview_body,
    )
    assert restored_preview.status_code == 200, restored_preview.text
    assert restored_preview.json()["snapshot_digest"] == preview.json()["snapshot_digest"]

    stale_generate = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/generate",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": activated.json()["updated_at"],
            **preview_body,
            "preview_digest": "0" * 64,
        },
    )
    assert stale_generate.status_code == 409
    assert stale_generate.json()["detail"]["code"] == "preview_stale"

    generate_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": activated.json()["updated_at"],
        **preview_body,
        "preview_digest": preview.json()["snapshot_digest"],
    }
    generated = client.post(
        f"/api/v1/staff-exchange/rotations/{created.json()['id']}/generate",
        headers=headers,
        json=generate_body,
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["total"] == 1
    assert (
        client.post(
            f"/api/v1/staff-exchange/rotations/{created.json()['id']}/generate",
            headers=headers,
            json=generate_body,
        ).json()
        == generated.json()
    )
    with application.state.database.session_factory() as session:
        schedule = session.get(ScheduledStaffShift, UUID(generated.json()["schedule_ids"][0]))
        assert schedule is not None
        assert schedule.origin_type == "rotation"
        assert schedule.origin_id == UUID(created.json()["id"])
        assert schedule.origin_occurrence_key == f"{slot_id}:2027-01-04"
        assert schedule.status == "draft"
        assert (
            session.scalar(
                select(StaffRotationPattern).where(
                    StaffRotationPattern.id == UUID(created.json()["id"])
                )
            )
            is not None
        )


def test_open_shift_patch_receipts_and_temporal_capabilities(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    educator_headers = _headers(educators[0])
    start = datetime(2027, 1, 25, 15, 0, tzinfo=UTC)
    create_body = {
        "client_operation_id": str(uuid4()),
        "facility_id": facility["id"],
        "room_id": room["id"],
        "source_schedule_id": None,
        "scheduled_start_at": start.isoformat(),
        "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
        "public_note": "Initial note",
    }
    created = client.post(
        "/api/v1/staff-exchange/open-shifts",
        headers=owner_headers,
        json=create_body,
    )
    assert created.status_code == 201, created.text
    patch_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": created.json()["updated_at"],
        "public_note": "Updated note",
    }
    patched = client.patch(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}",
        headers=owner_headers,
        json=patch_body,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["public_note"] == "Updated note"
    exact_patch = client.patch(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}",
        headers=owner_headers,
        json=patch_body,
    )
    assert exact_patch.status_code == 200, exact_patch.text
    assert exact_patch.json() == patched.json()
    changed_precondition = client.patch(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}",
        headers=owner_headers,
        json={**patch_body, "expected_updated_at": "2026-01-01T00:00:00Z"},
    )
    assert changed_precondition.status_code == 409
    assert changed_precondition.json()["detail"]["code"] == "operation_reused"

    posted = client.post(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}/post",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": patched.json()["updated_at"],
        },
    )
    assert posted.status_code == 200, posted.text
    _opt_in_substitute(client, educators[0], facility)
    invalid_expiry = client.post(
        f"/api/v1/staff-exchange/open-shifts/{posted.json()['id']}/offers",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": educators[0]["user"]["id"],
            "source_interest_id": None,
            "note": "Invalid boundary",
            "expires_at": start.isoformat(),
        },
    )
    assert invalid_expiry.status_code == 422
    assert invalid_expiry.json()["detail"]["code"] == "offer_expiry_must_precede_shift"
    offer, _ = _offer(client, owner_headers, posted.json(), educators[0])

    past_start = datetime.now(UTC) - timedelta(hours=2)
    with application.state.database.session_factory() as session:
        session.execute(
            update(StaffOpenShift)
            .where(StaffOpenShift.id == UUID(posted.json()["id"]))
            .values(starts_at=past_start, ends_at=past_start + timedelta(hours=1))
        )
        session.commit()

    activity = client.get(
        "/api/v1/staff/self/exchange/open-shift-activity",
        headers=educator_headers,
    )
    assert activity.status_code == 200, activity.text
    item = next(value for value in activity.json()["items"] if value["id"] == posted.json()["id"])
    assert item["can_express_interest"] is False
    assert item["my_engagement"]["can_accept"] is False
    assert item["my_engagement"]["can_decline"] is False
    rejected_action = client.post(
        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
        headers=educator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": offer["updated_at"],
            "note": "Too late",
        },
    )
    assert rejected_action.status_code == 409
    assert rejected_action.json()["detail"]["code"] == "open_shift_required"


def test_interest_conversion_is_durable_and_reconciles_from_cold_start(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    educator = educators[0]
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        datetime(2027, 1, 18, 15, 0, tzinfo=UTC),
    )
    interest = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{shift['id']}/interest",
        headers=_headers(educator),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": shift["updated_at"],
            "note": "I can cover this shift",
        },
    )
    assert interest.status_code == 201, interest.text
    assert interest.json()["status"] == "pending"
    assert interest.json()["can_withdraw"] is True

    offer, _ = _offer(
        client,
        owner_headers,
        shift,
        educator,
        source_interest_id=interest.json()["id"],
    )
    assert offer["source_interest_id"] == interest.json()["id"]
    activity = client.get(
        "/api/v1/staff/self/exchange/open-shift-activity",
        headers=_headers(educator),
        params={
            "start_at": "2027-01-01T00:00:00Z",
            "end_at": "2027-02-01T00:00:00Z",
        },
    )
    assert activity.status_code == 200, activity.text
    projection = activity.json()["items"][0]
    assert {
        "created_by_user_id",
        "posted_by_user_id",
        "cancelled_by_user_id",
        "filled_engagement_id",
        "filled_schedule_id",
    }.isdisjoint(projection)
    assert projection["my_engagement"]["id"] == offer["id"]
    assert len(projection["my_engagements"]) == 2
    history = {item["id"]: item for item in projection["my_engagements"]}
    assert history[interest.json()["id"]]["status"] == "converted"
    assert history[interest.json()["id"]]["converted_offer_id"] == offer["id"]
    assert history[offer["id"]]["source_interest_id"] == interest.json()["id"]
    assert history[offer["id"]]["can_accept"] is True


def test_open_shift_consent_history_expiry_and_exact_offer_receipts(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        datetime(2027, 2, 1, 15, 0, tzinfo=UTC),
    )
    _, denied_body = _offer_request(shift, educators[0], operation_id=str(uuid4()))
    no_consent = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/offers",
        headers=owner_headers,
        json=denied_body,
    )
    assert no_consent.status_code == 409
    assert no_consent.json()["detail"]["code"] == "substitute_opt_in_required"

    _opt_in_substitute(client, educators[0], facility)
    offer_operation = str(uuid4())
    offer, offer_body = _offer(
        client,
        owner_headers,
        shift,
        educators[0],
        operation_id=offer_operation,
    )
    assert offer["kind"] == "offer"
    assert offer["status"] == "pending"
    assert offer["is_expired"] is False
    assert offer["can_withdraw"] is True
    assert offer["can_accept"] is False
    exact = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/offers",
        headers=owner_headers,
        json=offer_body,
    )
    assert exact.status_code == 201, exact.text
    assert exact.json() == offer
    reuse = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/offers",
        headers=owner_headers,
        json={**offer_body, "note": "Changed"},
    )
    assert reuse.status_code == 409
    assert reuse.json()["detail"]["code"] == "operation_reused"

    activity = client.get(
        "/api/v1/staff/self/exchange/open-shift-activity",
        headers=_headers(educators[0]),
        params={"start_at": "2027-01-01T00:00:00Z", "end_at": "2027-03-01T00:00:00Z"},
    )
    assert activity.status_code == 200, activity.text
    self_shift = activity.json()["items"][0]
    assert self_shift["my_engagement"]["id"] == offer["id"]
    assert self_shift["my_engagement"]["can_accept"] is True
    assert self_shift["my_engagement"]["can_withdraw"] is False
    assert [item["id"] for item in self_shift["my_engagements"]] == [offer["id"]]

    # Preserve the database expiry invariant while making the offer observably expired.
    with application.state.database.session_factory() as session:
        old_created = datetime.now(UTC) - timedelta(days=2)
        session.execute(
            update(StaffOpenShiftEngagement)
            .where(StaffOpenShiftEngagement.id == UUID(offer["id"]))
            .values(created_at=old_created, expires_at=old_created + timedelta(days=1))
        )
        session.commit()
    expired_accept = client.post(
        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": offer["updated_at"],
            "note": "Too late",
        },
    )
    assert expired_accept.status_code == 409
    assert expired_accept.json()["detail"]["code"] == "offer_expired"
    replacement, _ = _offer(client, owner_headers, shift, educators[0], note="Renewed")
    assert replacement["id"] != offer["id"]
    engagements = client.get(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/engagements",
        headers=owner_headers,
    )
    assert engagements.status_code == 200, engagements.text
    by_id = {item["id"]: item for item in engagements.json()["items"]}
    assert by_id[offer["id"]]["status"] == "superseded"
    assert by_id[replacement["id"]]["status"] == "pending"


def _offer_request(
    open_shift: dict,
    educator: dict,
    *,
    operation_id: str,
) -> tuple[str, dict]:
    return operation_id, {
        "client_operation_id": operation_id,
        "staff_user_id": educator["user"]["id"],
        "source_interest_id": None,
        "note": "Please cover",
        "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
    }


def test_replacement_open_shift_is_whole_shift_atomic_and_source_owner_excluded(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path)
    owner_headers = _headers(owner)
    start = datetime(2027, 3, 1, 15, 0, tzinfo=UTC)
    source = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, start
    )
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        start,
        source_schedule_id=source["id"],
    )
    candidates = client.get(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/candidates",
        headers=owner_headers,
    )
    assert candidates.status_code == 200, candidates.text
    assert educators[0]["user"]["id"] not in {
        item["staff_user_id"] for item in candidates.json()["items"]
    }
    source_interest = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{shift['id']}/interest",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": shift["updated_at"],
            "note": "I cannot replace myself",
        },
    )
    assert source_interest.status_code == 409
    assert source_interest.json()["detail"]["code"] == "source_educator_ineligible"

    _opt_in_substitute(client, educators[0], facility)
    _, self_offer_body = _offer_request(shift, educators[0], operation_id=str(uuid4()))
    source_offer = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/offers",
        headers=owner_headers,
        json=self_offer_body,
    )
    assert source_offer.status_code == 409
    assert source_offer.json()["detail"]["code"] == "source_educator_ineligible"

    _opt_in_substitute(client, educators[1], facility)
    offer, _ = _offer(client, owner_headers, shift, educators[1])
    accept_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": offer["updated_at"],
        "note": "Accepted",
    }
    accepted = client.post(
        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
        headers=_headers(educators[1]),
        json=accept_body,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert (
        client.post(
            f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
            headers=_headers(educators[1]),
            json=accept_body,
        ).json()
        == accepted.json()
    )

    with application.state.database.session_factory() as session:
        original = session.get(ScheduledStaffShift, UUID(source["id"]))
        replacement = session.get(
            ScheduledStaffShift, UUID(accepted.json()["resulting_schedule_id"])
        )
        assert original.status == "cancelled"
        assert replacement.status == "published"
        assert replacement.response_status == "acknowledged"
        assert replacement.membership_id == UUID(educators[1]["user"]["membership_id"])
        assert replacement.scheduled_start_at == original.scheduled_start_at
        assert replacement.scheduled_end_at == original.scheduled_end_at
        assert replacement.origin_type == "open_shift"
        assert replacement.origin_id == UUID(shift["id"])
        assert replacement.supersedes_schedule_id == original.id


def test_substitute_tombstone_survives_cold_start_and_re_opt_in(tmp_path):
    client, _, owner, educators, facility, _ = _setup(tmp_path, educator_count=1)
    educator = educators[0]
    staff_headers = _headers(educator)
    owner_headers = _headers(owner)
    active = _opt_in_substitute(client, educator, facility)

    manager_active = client.get(
        "/api/v1/staff-exchange/substitutes",
        headers=owner_headers,
        params={"facility_id": facility["id"]},
    )
    assert manager_active.status_code == 200, manager_active.text
    assert manager_active.json()["total"] == 1
    assert "note" not in manager_active.json()["items"][0]

    delete_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": active["updated_at"],
    }
    removed = client.request(
        "DELETE",
        f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
        headers=staff_headers,
        json=delete_body,
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["active"] is False
    assert removed.json()["note"] is None
    assert removed.json()["recorded_operation_id"] == delete_body["client_operation_id"]
    exact = client.request(
        "DELETE",
        f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
        headers=staff_headers,
        json=delete_body,
    )
    assert exact.status_code == 200, exact.text
    assert exact.json() == removed.json()

    cold_start = client.get(
        "/api/v1/staff/self/exchange/substitute-profiles", headers=staff_headers
    )
    assert cold_start.status_code == 200, cold_start.text
    assert cold_start.json()["total"] == 1
    assert cold_start.json()["items"] == [removed.json()]
    manager_hidden = client.get(
        "/api/v1/staff-exchange/substitutes",
        headers=owner_headers,
        params={"facility_id": facility["id"]},
    )
    assert manager_hidden.status_code == 200, manager_hidden.text
    assert manager_hidden.json()["items"] == []

    reactivated = client.put(
        f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
        headers=staff_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": removed.json()["updated_at"],
            "active": True,
            "note": "Available again",
        },
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["id"] == removed.json()["id"]
    assert reactivated.json()["active"] is True
    assert reactivated.json()["note"] == "Available again"


def test_cover_and_trade_are_whole_shift_consent_then_manager_approval(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    first_start = datetime(2027, 4, 5, 14, 0, tzinfo=UTC)
    second_start = datetime(2027, 4, 7, 14, 0, tzinfo=UTC)
    requester = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, first_start
    )
    counterparty = _published_acknowledged_schedule(
        client, owner_headers, educators[1], facility, room, second_start
    )

    invalid_cover = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": requester["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": counterparty["id"],
            "note": "Invalid partial contract",
        },
    )
    assert invalid_cover.status_code == 422

    cover_body = {
        "client_operation_id": str(uuid4()),
        "kind": "cover",
        "requester_schedule_id": requester["id"],
        "counterparty_membership_id": educators[1]["user"]["membership_id"],
        "counterparty_schedule_id": None,
        "note": "Please cover my entire shift",
    }
    cover = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json=cover_body,
    )
    assert cover.status_code == 201, cover.text
    assert cover.json()["kind"] == "cover"
    assert cover.json()["counterparty_schedule"] is None
    assert (
        client.post(
            "/api/v1/staff/self/exchange/swaps",
            headers=_headers(educators[0]),
            json=cover_body,
        ).json()
        == cover.json()
    )
    duplicate_pending = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={**cover_body, "client_operation_id": str(uuid4())},
    )
    assert duplicate_pending.status_code == 409
    assert duplicate_pending.json()["detail"]["code"] == "schedule_exchange_pending"

    accepted_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": cover.json()["updated_at"],
        "note": "I consent to cover the whole shift",
    }
    peer_accepted = client.post(
        f"/api/v1/staff/self/exchange/swaps/{cover.json()['id']}/accept",
        headers=_headers(educators[1]),
        json=accepted_body,
    )
    assert peer_accepted.status_code == 200, peer_accepted.text
    assert peer_accepted.json()["status"] == "pending_manager"
    assert (
        client.post(
            f"/api/v1/staff/self/exchange/swaps/{cover.json()['id']}/accept",
            headers=_headers(educators[1]),
            json=accepted_body,
        ).json()
        == peer_accepted.json()
    )
    approve_body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": peer_accepted.json()["updated_at"],
    }
    approved = client.post(
        f"/api/v1/staff-exchange/swaps/{cover.json()['id']}/approve",
        headers=owner_headers,
        json=approve_body,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["requester_replacement_schedule_id"] is not None
    assert approved.json()["counterparty_replacement_schedule_id"] is None
    assert (
        client.post(
            f"/api/v1/staff-exchange/swaps/{cover.json()['id']}/approve",
            headers=owner_headers,
            json=approve_body,
        ).json()
        == approved.json()
    )

    # New originals on separate dates exercise the reciprocal trade cardinality.
    trade_requester = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2027, 5, 3, 14, 0, tzinfo=UTC),
    )
    trade_counterparty = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[1],
        facility,
        room,
        datetime(2027, 5, 5, 14, 0, tzinfo=UTC),
    )
    trade = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "trade",
            "requester_schedule_id": trade_requester["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": trade_counterparty["id"],
            "note": "Trade both entire shifts",
        },
    )
    assert trade.status_code == 201, trade.text
    peer = client.post(
        f"/api/v1/staff/self/exchange/swaps/{trade.json()['id']}/accept",
        headers=_headers(educators[1]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": trade.json()["updated_at"],
            "note": "Trade accepted",
        },
    )
    assert peer.status_code == 200, peer.text
    trade_approved = client.post(
        f"/api/v1/staff-exchange/swaps/{trade.json()['id']}/approve",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": peer.json()["updated_at"],
        },
    )
    assert trade_approved.status_code == 200, trade_approved.text
    assert trade_approved.json()["counterparty_replacement_schedule_id"] is not None

    with application.state.database.session_factory() as session:
        original_requester = session.get(ScheduledStaffShift, UUID(trade_requester["id"]))
        original_counterparty = session.get(ScheduledStaffShift, UUID(trade_counterparty["id"]))
        requester_replacement = session.get(
            ScheduledStaffShift,
            UUID(trade_approved.json()["requester_replacement_schedule_id"]),
        )
        counterparty_replacement = session.get(
            ScheduledStaffShift,
            UUID(trade_approved.json()["counterparty_replacement_schedule_id"]),
        )
        assert original_requester.status == original_counterparty.status == "cancelled"
        assert requester_replacement.membership_id == UUID(educators[1]["user"]["membership_id"])
        assert counterparty_replacement.membership_id == UUID(educators[0]["user"]["membership_id"])
        assert requester_replacement.supersedes_schedule_id == original_requester.id
        assert counterparty_replacement.supersedes_schedule_id == original_counterparty.id
        assert requester_replacement.scheduled_start_at == original_requester.scheduled_start_at
        assert (
            counterparty_replacement.scheduled_start_at == original_counterparty.scheduled_start_at
        )


def test_swap_approval_fails_closed_when_source_changes_after_consent(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    source = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2027, 5, 17, 14, 0, tzinfo=UTC),
    )
    swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Consent must bind to this source version",
        },
    )
    assert swap.status_code == 201, swap.text
    accepted = client.post(
        f"/api/v1/staff/self/exchange/swaps/{swap.json()['id']}/accept",
        headers=_headers(educators[1]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": swap.json()["updated_at"],
            "note": "I consent",
        },
    )
    assert accepted.status_code == 200, accepted.text
    cancelled = client.post(
        f"/api/v1/staff-schedules/{source['id']}/cancel",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "reason": "Source changed before manager review",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    approval = client.post(
        f"/api/v1/staff-exchange/swaps/{swap.json()['id']}/approve",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": accepted.json()["updated_at"],
        },
    )
    assert approval.status_code == 409
    assert approval.json()["detail"]["code"] in {
        "swap_source_changed",
        "swap_source_ineligible",
    }
    with application.state.database.session_factory() as session:
        replacements = list(
            session.scalars(
                select(ScheduledStaffShift).where(
                    ScheduledStaffShift.origin_type == "swap",
                    ScheduledStaffShift.origin_id == UUID(swap.json()["id"]),
                )
            )
        )
        assert replacements == []


def test_exchange_resources_are_tenant_isolated(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    first_headers = _headers(owner)
    shift = _create_posted_open_shift(
        client,
        first_headers,
        facility,
        room,
        datetime(2027, 6, 1, 14, 0, tzinfo=UTC),
    )
    manager_forbidden = client.get(
        "/api/v1/staff-exchange/open-shifts",
        headers=_headers(educators[0]),
        params={"start_at": "2027-05-01T00:00:00Z", "end_at": "2027-07-01T00:00:00Z"},
    )
    assert manager_forbidden.status_code == 403
    second = _register(client, "second")
    second_headers = _headers(second)
    other_facility, other_room = _facility_tree(client, second_headers, "Other")
    other_educator = _educator(client, second_headers, other_facility, other_room, "other")

    hidden = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/cancel",
        headers=second_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": shift["updated_at"],
            "reason": "Cross-tenant attempt",
        },
    )
    assert hidden.status_code == 404
    self_hidden = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{shift['id']}/interest",
        headers=_headers(other_educator),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": shift["updated_at"],
            "note": None,
        },
    )
    assert self_hidden.status_code == 404
    first_list = client.get(
        "/api/v1/staff-exchange/open-shifts",
        headers=first_headers,
        params={"start_at": "2027-05-01T00:00:00Z", "end_at": "2027-07-01T00:00:00Z"},
    )
    second_list = client.get(
        "/api/v1/staff-exchange/open-shifts",
        headers=second_headers,
        params={"start_at": "2027-05-01T00:00:00Z", "end_at": "2027-07-01T00:00:00Z"},
    )
    assert first_list.json()["total"] == 1
    assert second_list.json()["total"] == 0


def test_same_tenant_operation_receipt_is_private_to_its_actor(tmp_path):
    client, _, _, educators, facility, _ = _setup(tmp_path, educator_count=2)
    operation_id = str(uuid4())
    first = _opt_in_substitute(client, educators[0], facility, operation_id=operation_id)
    leaked_retry = client.put(
        f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
        headers=_headers(educators[1]),
        json={
            "client_operation_id": operation_id,
            "expected_updated_at": None,
            "active": True,
            "note": "Available for coverage",
        },
    )
    assert leaked_retry.status_code == 404
    assert leaked_retry.json()["detail"] == "Operation receipt not found"
    assert first["staff_user_id"] == educators[0]["user"]["id"]
    second_profiles = client.get(
        "/api/v1/staff/self/exchange/substitute-profiles",
        headers=_headers(educators[1]),
    )
    assert second_profiles.status_code == 200, second_profiles.text
    assert second_profiles.json()["items"] == []


def test_swap_candidates_do_not_enumerate_staff_from_another_facility(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    other_facility, other_room = _facility_tree(client, owner_headers, "Remote")
    remote_educator = _educator(client, owner_headers, other_facility, other_room, "remote")
    source_start = datetime.now(UTC) + timedelta(days=30)
    source = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, source_start
    )
    _published_acknowledged_schedule(
        client,
        owner_headers,
        remote_educator,
        other_facility,
        other_room,
        source_start + timedelta(days=2),
    )
    for kind in ("cover", "trade"):
        candidates = client.get(
            f"/api/v1/staff/self/exchange/schedules/{source['id']}/swap-candidates",
            headers=_headers(educators[0]),
            params={"kind": kind},
        )
        assert candidates.status_code == 200, candidates.text
        assert remote_educator["user"]["id"] not in {
            item["counterparty_staff_user_id"] for item in candidates.json()["items"]
        }
        assert remote_educator["user"]["membership_id"] not in {
            item["counterparty_membership_id"] for item in candidates.json()["items"]
        }


def test_inactive_facility_blocks_open_shift_post(tmp_path):
    client, application, owner, _, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    start = datetime(2027, 8, 2, 14, 0, tzinfo=UTC)
    created = client.post(
        "/api/v1/staff-exchange/open-shifts",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": room["id"],
            "source_schedule_id": None,
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
            "public_note": None,
        },
    )
    assert created.status_code == 201, created.text
    with application.state.database.session_factory() as session:
        session.execute(
            update(Facility).where(Facility.id == UUID(facility["id"])).values(status="inactive")
        )
        session.commit()
    posted = client.post(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}/post",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": created.json()["updated_at"],
        },
    )
    assert posted.status_code == 404
    with application.state.database.session_factory() as session:
        value = session.get(StaffOpenShift, UUID(created.json()["id"]))
        assert value.status == "draft"


def test_inactive_room_blocks_offer_accept_without_partial_fill(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        datetime(2027, 8, 16, 14, 0, tzinfo=UTC),
    )
    _opt_in_substitute(client, educators[0], facility)
    offer, _ = _offer(client, owner_headers, shift, educators[0])
    with application.state.database.session_factory() as session:
        session.execute(update(Room).where(Room.id == UUID(room["id"])).values(is_active=False))
        session.commit()
    accepted = client.post(
        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": offer["updated_at"],
            "note": "Should fail closed",
        },
    )
    assert accepted.status_code == 422
    assert accepted.json()["detail"]["code"] == "invalid_room"
    with application.state.database.session_factory() as session:
        canonical_shift = session.get(StaffOpenShift, UUID(shift["id"]))
        canonical_offer = session.get(StaffOpenShiftEngagement, UUID(offer["id"]))
        assert canonical_shift.status == "open"
        assert canonical_shift.result_schedule_id is None
        assert canonical_offer.status == "pending"
        assert canonical_offer.result_schedule_id is None
        assert (
            session.scalar(
                select(ScheduledStaffShift.id).where(
                    ScheduledStaffShift.origin_type == "open_shift",
                    ScheduledStaffShift.origin_id == UUID(shift["id"]),
                )
            )
            is None
        )


def test_inactive_facility_blocks_swap_approval_without_replacements(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    source = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2027, 8, 30, 14, 0, tzinfo=UTC),
    )
    swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Facility state must be rechecked",
        },
    )
    assert swap.status_code == 201, swap.text
    peer = client.post(
        f"/api/v1/staff/self/exchange/swaps/{swap.json()['id']}/accept",
        headers=_headers(educators[1]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": swap.json()["updated_at"],
            "note": "Consent",
        },
    )
    assert peer.status_code == 200, peer.text
    with application.state.database.session_factory() as session:
        session.execute(
            update(Facility).where(Facility.id == UUID(facility["id"])).values(status="inactive")
        )
        session.commit()
    approval = client.post(
        f"/api/v1/staff-exchange/swaps/{swap.json()['id']}/approve",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": peer.json()["updated_at"],
        },
    )
    assert approval.status_code == 422
    assert approval.json()["detail"]["code"] == "inactive_facility"
    with application.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(ScheduledStaffShift.id).where(
                    ScheduledStaffShift.origin_type == "swap",
                    ScheduledStaffShift.origin_id == UUID(swap.json()["id"]),
                )
            )
            is None
        )


def test_suspended_opted_in_staff_is_not_notified_about_new_open_shift(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    educator = educators[0]
    _opt_in_substitute(client, educator, facility)
    start = datetime(2027, 9, 13, 14, 0, tzinfo=UTC)
    created = client.post(
        "/api/v1/staff-exchange/open-shifts",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": room["id"],
            "source_schedule_id": None,
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=8)).isoformat(),
            "public_note": "Should not notify suspended staff",
        },
    )
    assert created.status_code == 201, created.text
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    educator_role = next(item for item in workspace.json()["roles"] if item["key"] == "educator")
    suspended = client.patch(
        f"/api/v1/staff/members/{educator['user']['membership_id']}",
        headers=owner_headers,
        json={
            "role_id": educator_role["id"],
            "assigned_facility_ids": [],
            "assigned_room_ids": [],
            "membership_status": "suspended",
        },
    )
    assert suspended.status_code == 200, suspended.text
    posted = client.post(
        f"/api/v1/staff-exchange/open-shifts/{created.json()['id']}/post",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": created.json()["updated_at"],
        },
    )
    assert posted.status_code == 200, posted.text
    with application.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(UserNotification.id).where(
                    UserNotification.user_id == UUID(educator["user"]["id"]),
                    UserNotification.action_entity_type == "staff_open_shift",
                    UserNotification.action_entity_id == UUID(created.json()["id"]),
                )
            )
            is None
        )


def test_manager_and_self_open_shift_lists_fail_closed_above_500_rows(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    organization_id = UUID(owner["user"]["organization_id"])
    actor_user_id = UUID(owner["user"]["id"])
    facility_id = UUID(facility["id"])
    room_id = UUID(room["id"])
    now = datetime.now(UTC)
    start = datetime(2027, 7, 5, 14, 0, tzinfo=UTC)
    with application.state.database.session_factory() as session:
        session.add_all(
            [
                StaffOpenShift(
                    id=uuid4(),
                    organization_id=organization_id,
                    facility_id=facility_id,
                    room_id=room_id,
                    starts_at=start,
                    ends_at=start + timedelta(hours=8),
                    notes=None,
                    status="open",
                    source_schedule_id=None,
                    result_schedule_id=None,
                    create_operation_id=uuid4(),
                    last_operation_id=uuid4(),
                    created_by_user_id=actor_user_id,
                    post_operation_id=uuid4(),
                    posted_at=now,
                    posted_by_user_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                for _ in range(501)
            ]
        )
        session.commit()
    params = {
        "facility_id": facility["id"],
        "start_at": "2027-07-01T00:00:00Z",
        "end_at": "2027-08-01T00:00:00Z",
    }
    manager = client.get(
        "/api/v1/staff-exchange/open-shifts",
        headers=_headers(owner),
        params=params,
    )
    assert manager.status_code == 422, manager.text
    assert manager.json()["detail"] == {
        "code": "list_too_large",
        "max_items": 500,
        "message": "Narrow the facility or date filters and try again.",
    }
    staff = client.get(
        "/api/v1/staff/self/exchange/open-shifts",
        headers=_headers(educators[0]),
        params=params,
    )
    assert staff.status_code == 422, staff.text
    assert staff.json()["detail"] == manager.json()["detail"]


def test_exact_receipts_are_private_to_the_creating_principal(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    shift = _create_posted_open_shift(
        client,
        _headers(owner),
        facility,
        room,
        datetime(2027, 8, 2, 14, 0, tzinfo=UTC),
    )
    body = {
        "client_operation_id": str(uuid4()),
        "expected_updated_at": shift["updated_at"],
        "note": "I can cover",
    }
    created = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{shift['id']}/interest",
        headers=_headers(educators[0]),
        json=body,
    )
    assert created.status_code == 201, created.text
    leaked_retry = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{shift['id']}/interest",
        headers=_headers(educators[1]),
        json=body,
    )
    assert leaked_retry.status_code == 404
    assert leaked_retry.json()["detail"] == "Operation receipt not found"


def test_replacement_source_educator_is_not_actionable_or_offerable(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    start = datetime(2027, 8, 9, 14, 0, tzinfo=UTC)
    source = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, start
    )
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        start,
        source_schedule_id=source["id"],
    )
    self_list = client.get(
        "/api/v1/staff/self/exchange/open-shifts",
        headers=_headers(educators[0]),
        params={
            "facility_id": facility["id"],
            "start_at": "2027-08-01T00:00:00Z",
            "end_at": "2027-09-01T00:00:00Z",
        },
    )
    assert self_list.status_code == 200, self_list.text
    projection = next(item for item in self_list.json()["items"] if item["id"] == shift["id"])
    assert projection["can_express_interest"] is False
    assert "source_educator_ineligible" in projection["eligibility_reasons"]
    crafted_offer = client.post(
        f"/api/v1/staff-exchange/open-shifts/{shift['id']}/offers",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "staff_user_id": educators[0]["user"]["id"],
            "source_interest_id": None,
            "note": "Invalid self replacement",
            "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert crafted_offer.status_code == 409
    assert crafted_offer.json()["detail"]["code"] == "source_educator_ineligible"


def test_swap_candidates_do_not_enumerate_other_facilities(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    same_facility = _educator(client, owner_headers, facility, room, "same-facility")
    other_facility, other_room = _facility_tree(client, owner_headers, "Other")
    other_staff = _educator(client, owner_headers, other_facility, other_room, "other-facility")
    source = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2027, 8, 16, 14, 0, tzinfo=UTC),
    )
    response = client.get(
        f"/api/v1/staff/self/exchange/schedules/{source['id']}/swap-candidates",
        headers=_headers(educators[0]),
        params={"kind": "cover"},
    )
    assert response.status_code == 200, response.text
    visible_users = {item["counterparty_staff_user_id"] for item in response.json()["items"]}
    assert same_facility["user"]["id"] in visible_users
    assert other_staff["user"]["id"] not in visible_users


def test_offer_acceptance_revalidates_active_room_before_assignment(tmp_path):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=1)
    owner_headers = _headers(owner)
    shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        datetime(2027, 8, 23, 14, 0, tzinfo=UTC),
    )
    _opt_in_substitute(client, educators[0], facility)
    offer, _ = _offer(client, owner_headers, shift, educators[0])
    with application.state.database.session_factory() as session:
        session.execute(update(Room).where(Room.id == UUID(room["id"])).values(is_active=False))
        session.commit()
    rejected = client.post(
        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": offer["updated_at"],
            "note": "Accept",
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "invalid_room"
    with application.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(ScheduledStaffShift.id).where(
                    ScheduledStaffShift.origin_type == "open_shift",
                    ScheduledStaffShift.origin_id == UUID(shift["id"]),
                )
            )
            is None
        )


def test_source_schedule_is_reserved_across_open_shift_and_swap_workflows(tmp_path):
    client, _, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    first_start = datetime(2027, 9, 6, 14, 0, tzinfo=UTC)
    first_source = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, first_start
    )
    open_shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        first_start,
        source_schedule_id=first_source["id"],
    )
    blocked_swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": first_source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "This source is already reserved",
        },
    )
    assert blocked_swap.status_code == 409
    assert blocked_swap.json()["detail"]["code"] == "schedule_exchange_pending"

    cancelled = client.post(
        f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/cancel",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": open_shift["updated_at"],
            "reason": "Use the peer exchange instead",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": first_source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Now the source is available",
        },
    )
    assert swap.status_code == 201, swap.text

    second_start = datetime(2027, 9, 13, 14, 0, tzinfo=UTC)
    second_source = _published_acknowledged_schedule(
        client, owner_headers, educators[0], facility, room, second_start
    )
    second_swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": second_source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Reserve the second source",
        },
    )
    assert second_swap.status_code == 201, second_swap.text
    blocked_open = client.post(
        "/api/v1/staff-exchange/open-shifts",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "room_id": room["id"],
            "source_schedule_id": second_source["id"],
            "scheduled_start_at": second_start.isoformat(),
            "scheduled_end_at": (second_start + timedelta(hours=8)).isoformat(),
            "public_note": "This source is already reserved",
        },
    )
    assert blocked_open.status_code == 409
    assert blocked_open.json()["detail"]["code"] == "schedule_exchange_pending"


def test_notification_action_targets_resolve_exact_exchange_rows_without_side_effects(
    tmp_path,
):
    client, application, owner, educators, facility, room = _setup(tmp_path, educator_count=2)
    owner_headers = _headers(owner)
    shift_start = datetime(2027, 10, 4, 14, 0, tzinfo=UTC)
    open_shift = _create_posted_open_shift(client, owner_headers, facility, room, shift_start)
    substitute = _opt_in_substitute(client, educators[0], facility)
    interest = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{open_shift['id']}/interest",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": open_shift["updated_at"],
            "note": "Canonical engagement target",
        },
    )
    assert interest.status_code == 201, interest.text

    rotation = client.post(
        "/api/v1/staff-exchange/rotations",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "name": "Notification focus rotation",
            "anchor_date": "2027-10-04",
            "cycle_weeks": 1,
            "slots": [
                {
                    "slot_id": str(uuid4()),
                    "cycle_week": 0,
                    "weekday": 0,
                    "staff_user_id": educators[0]["user"]["id"],
                    "room_id": room["id"],
                    "start_local": "08:00",
                    "end_local": "16:00",
                    "notes": None,
                }
            ],
        },
    )
    assert rotation.status_code == 201, rotation.text

    source = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2027, 10, 11, 14, 0, tzinfo=UTC),
    )
    swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": source["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Canonical swap target",
        },
    )
    assert swap.status_code == 201, swap.text

    with application.state.database.session_factory() as session:
        notifications_before = len(session.scalars(select(UserNotification.id)).all())

    expected = {
        ("staff_open_shift", open_shift["id"]): {
            "starts_at": "2027-10-04T14:00:00Z",
            "parent_entity_id": None,
            "membership_id": None,
            "visible": True,
        },
        ("staff_open_shift_engagement", interest.json()["id"]): {
            "starts_at": "2027-10-04T14:00:00Z",
            "parent_entity_id": open_shift["id"],
            "membership_id": interest.json()["membership_id"],
            "visible": True,
        },
        ("staff_substitute_profile", substitute["id"]): {
            "starts_at": None,
            "parent_entity_id": None,
            "membership_id": substitute["membership_id"],
            "visible": True,
        },
        ("staff_rotation_pattern", rotation.json()["id"]): {
            "starts_at": None,
            "parent_entity_id": None,
            "membership_id": None,
            "visible": True,
        },
        ("staff_shift_swap", swap.json()["id"]): {
            "starts_at": "2027-10-11T14:00:00Z",
            "parent_entity_id": None,
            "membership_id": None,
            "visible": True,
        },
    }
    for (entity_type, entity_id), locator in expected.items():
        response = client.get(
            f"/api/v1/staff-workforce/action-target/{entity_type}/{entity_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "organization_id": owner["user"]["organization_id"],
            "entity_type": entity_type,
            "entity_id": entity_id,
            "facility_id": facility["id"],
            **locator,
        }

    other_owner = _register(client, "other-tenant")
    assert (
        client.get(
            f"/api/v1/staff-workforce/action-target/staff_open_shift/{open_shift['id']}",
            headers=_headers(other_owner),
        ).status_code
        == 404
    )
    with application.state.database.session_factory() as session:
        assert len(session.scalars(select(UserNotification.id)).all()) == notifications_before
