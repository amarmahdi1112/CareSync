"""Acceptance coverage for versioned exact child-record commands."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from alembic import command
from app.basic.models import (
    AttendanceDay,
    AuditEvent,
    Child,
    ChildcareCommandClaim,
    ChildcareCommandReceipt,
    ChildcareCommandReconciliationProof,
    ChildcareCommandSlot,
    EmergencyContact,
    Enrollment,
    Family,
    Guardian,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    Room,
    User,
)
from app.basic.security import hash_password
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FACILITY_TIME_ZONE = ZoneInfo("America/Edmonton")


def _facility_today() -> date:
    return datetime.now(FACILITY_TIME_ZONE).date()


def _client(tmp_path, monkeypatch) -> tuple[TestClient, object]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="childcare-command-spine-test-secret-32-bytes",
    )
    application = create_app(settings)
    return TestClient(application), application


def _register(client: TestClient) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "spine@example.com",
            "password": "correct-password-123",
            "first_name": "Command",
            "last_name": "Owner",
            "organization_name": "Command Child Care",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _register_named(client: TestClient, name: str) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{name}-{uuid4().hex}@example.com",
            "password": "correct-password-123",
            "first_name": name,
            "last_name": "Owner",
            "organization_name": f"{name} Child Care",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _second_actor_headers(
    application, client: TestClient, organization_id: str
) -> tuple[str, dict[str, str]]:
    email = f"second-{uuid4().hex}@example.com"
    password = "second-correct-password-123"
    with application.state.database.session_factory() as session:
        role = session.scalar(
            select(Role).where(
                Role.organization_id == UUID(organization_id),
                Role.key == "administrator",
            )
        )
        assert role is not None
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            first_name="Second",
            last_name="Actor",
            is_active=True,
            email_verified_at=datetime.now(UTC),
            email_verification_method="test_fixture",
        )
        session.add(user)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=UUID(organization_id),
                user_id=user.id,
                role_id=role.id,
                status="active",
            )
        )
        session.commit()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return str(user.id), {"Authorization": f"Bearer {login.json()['access_token']}"}


def _post(client: TestClient, path: str, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _family(client: TestClient, headers: dict[str, str], operation_id: str | None = None) -> dict:
    return _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": operation_id or str(uuid4()),
            "name": "Exact Family",
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Guardian",
                "cell_phone": "780-555-0100",
            },
            "emergency_contacts": [
                {
                    "first_name": "Emergency",
                    "last_name": "Contact",
                    "relationship": "Aunt",
                    "cell_phone": "780-555-0101",
                }
            ],
        },
    )


def _child(client: TestClient, headers: dict[str, str], family_id: str) -> dict:
    return _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family_id,
            "first_name": "Exact",
            "last_name": "Child",
            "date_of_birth": "2024-01-01",
        },
    )


def _facility_tree(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict, dict]:
    facility = _post(
        client,
        "/api/v1/facilities",
        headers,
        {"name": "Spine Centre", "status": "active", "licensed_capacity": 100},
    )
    program = _post(
        client,
        "/api/v1/programs",
        headers,
        {
            "facility_id": facility["id"],
            "name": "Daycare",
            "program_type": "daycare",
            "capacity": 100,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    room = _post(
        client,
        "/api/v1/rooms",
        headers,
        {
            "facility_id": facility["id"],
            "program_id": program["id"],
            "name": "Command Room",
            "capacity": 20,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    return facility, program, room


def test_exact_replay_stale_conflict_temporal_history_and_private_headers(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        operation_id = str(uuid4())
        family = _family(client, headers, operation_id)
        assert family["version"] == 1
        assert family["replayed"] is False
        assert family["guardians"][0]["authorized_pickup"] is False
        assert family["emergency_contacts"][0]["authorized_pickup"] is False
        replay = client.post(
            "/api/v1/families",
            headers=headers,
            json={
                "client_operation_id": operation_id,
                "name": "Exact Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0100",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Emergency",
                        "last_name": "Contact",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0101",
                    }
                ],
            },
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == family["id"]
        assert replay.json()["replayed"] is True
        whitespace_reuse = client.post(
            "/api/v1/families",
            headers=headers,
            json={"client_operation_id": operation_id, "name": "Exact Family "},
        )
        assert whitespace_reuse.status_code == 409
        assert whitespace_reuse.json()["detail"]["code"] == "operation_reused"

        family_patch_operation = str(uuid4())
        changed = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": family_patch_operation,
                "expected_version": 1,
                "additional_notes": "Version two",
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == 2
        stale = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "additional_notes": "Stale",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == {
            "code": "stale_childcare_resource",
            "resource_type": "family",
            "resource_id": family["id"],
            "expected_version": 1,
            "current_version": 2,
        }

        primary_operation = str(uuid4())
        guardian_replace = client.put(
            f"/api/v1/families/{family['id']}/guardians/primary",
            headers=headers,
            json={
                "client_operation_id": primary_operation,
                "expected_version": 2,
                "guardian": {
                    "first_name": "Replacement",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0110",
                },
            },
        )
        assert guardian_replace.status_code == 200, guardian_replace.text
        assert guardian_replace.json()["version"] == 3
        assert [row["first_name"] for row in guardian_replace.json()["guardians"]] == [
            "Replacement"
        ]
        assert guardian_replace.json()["guardians"][0]["authorized_pickup"] is False
        assert guardian_replace.headers["cache-control"] == "private, no-store"
        assert guardian_replace.headers["pragma"] == "no-cache"

        secondary_first_operation = str(uuid4())
        secondary_first = client.put(
            f"/api/v1/families/{family['id']}/guardians/secondary",
            headers=headers,
            json={
                "client_operation_id": secondary_first_operation,
                "expected_version": 3,
                "guardian": {
                    "first_name": "First Secondary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0111",
                },
            },
        )
        assert secondary_first.status_code == 200, secondary_first.text
        assert secondary_first.json()["version"] == 4
        secondary_second_operation = str(uuid4())
        secondary_second = client.put(
            f"/api/v1/families/{family['id']}/guardians/secondary",
            headers=headers,
            json={
                "client_operation_id": secondary_second_operation,
                "expected_version": 4,
                "guardian": {
                    "first_name": "Final Secondary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0112",
                },
            },
        )
        assert secondary_second.status_code == 200, secondary_second.text
        assert secondary_second.json()["version"] == 5

        emergency_first_operation = str(uuid4())
        emergency_first = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": emergency_first_operation,
                "expected_version": 5,
                "emergency_contacts": [
                    {
                        "first_name": "First Replacement",
                        "last_name": "Contact",
                        "relationship": "Uncle",
                        "cell_phone": "780-555-0113",
                    }
                ],
            },
        )
        assert emergency_first.status_code == 200, emergency_first.text
        assert emergency_first.json()["version"] == 6
        emergency_second_operation = str(uuid4())
        emergency_second = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": emergency_second_operation,
                "expected_version": 6,
                "emergency_contacts": [
                    {
                        "first_name": "Final Emergency",
                        "last_name": "Contact",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0114",
                    }
                ],
            },
        )
        assert emergency_second.status_code == 200, emergency_second.text
        assert emergency_second.json()["version"] == 7
        assert {row["first_name"] for row in emergency_second.json()["guardians"]} == {
            "Replacement",
            "Final Secondary",
        }
        assert [row["first_name"] for row in emergency_second.json()["emergency_contacts"]] == [
            "Final Emergency"
        ]

        late_replay = client.put(
            f"/api/v1/families/{family['id']}/guardians/secondary",
            headers=headers,
            json={
                "client_operation_id": secondary_first_operation,
                "expected_version": 3,
                "guardian": {
                    "first_name": "First Secondary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0111",
                },
            },
        )
        assert late_replay.status_code == 200, late_replay.text
        assert late_replay.json()["replayed"] is True
        assert late_replay.json()["version"] == 7

        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            guardian_rows = list(
                session.scalars(select(Guardian).where(Guardian.organization_id == organization_id))
            )
            assert len(guardian_rows) == 4
            assert sum(row.retired_at is not None for row in guardian_rows) == 2
            guardians_by_first_name = {row.first_name: row for row in guardian_rows}
            assert guardians_by_first_name["Primary"].created_operation_id == UUID(operation_id)
            assert guardians_by_first_name["Primary"].retired_operation_id == UUID(
                primary_operation
            )
            assert guardians_by_first_name["Replacement"].created_operation_id == UUID(
                primary_operation
            )
            assert guardians_by_first_name["Replacement"].retired_at is None
            assert guardians_by_first_name["First Secondary"].created_operation_id == UUID(
                secondary_first_operation
            )
            assert guardians_by_first_name["First Secondary"].retired_operation_id == UUID(
                secondary_second_operation
            )
            assert guardians_by_first_name["Final Secondary"].created_operation_id == UUID(
                secondary_second_operation
            )
            assert guardians_by_first_name["Final Secondary"].retired_at is None

            contact_rows = list(
                session.scalars(
                    select(EmergencyContact).where(
                        EmergencyContact.organization_id == organization_id
                    )
                )
            )
            assert len(contact_rows) == 3
            assert sum(row.retired_at is not None for row in contact_rows) == 2
            contacts_by_first_name = {row.first_name: row for row in contact_rows}
            assert contacts_by_first_name["Emergency"].created_operation_id == UUID(operation_id)
            assert contacts_by_first_name["Emergency"].retired_operation_id == UUID(
                emergency_first_operation
            )
            assert contacts_by_first_name["First Replacement"].created_operation_id == UUID(
                emergency_first_operation
            )
            assert contacts_by_first_name["First Replacement"].retired_operation_id == UUID(
                emergency_second_operation
            )
            assert contacts_by_first_name["Final Emergency"].created_operation_id == UUID(
                emergency_second_operation
            )
            assert contacts_by_first_name["Final Emergency"].retired_at is None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(ChildcareCommandReceipt.organization_id == organization_id)
                )
                == 7
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.entity_type == "family",
                    )
                )
                == 7
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RealtimeEvent)
                    .where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_type == "family",
                    )
                )
                == 7
            )


def test_pending_unassigned_approval_reserved_roster_and_readiness(tmp_path, monkeypatch) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        child = _child(client, headers, family["id"])
        facility, _, room = _facility_tree(client, headers)
        future_start = _facility_today() + timedelta(days=20)
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": future_start.isoformat(),
            },
        )
        assert enrollment["status"] == "pending"
        assert enrollment["program_id"] is None
        assert enrollment["room_id"] is None
        assert enrollment["placement_effective_date"] is None

        duplicate = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": future_start.isoformat(),
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "open_enrollment_exists"
        other_family = _family(client, headers)
        reparent = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": child["version"],
                "family_id": other_family["id"],
            },
        )
        assert reparent.status_code == 409
        assert reparent.json()["detail"]["code"] == ("child_reparenting_blocked_open_enrollment")

        readiness = client.get("/api/v1/child-record-readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        assert any(
            item["code"] == "open_unassigned_enrollment"
            and item["enrollment_id"] == enrollment["id"]
            for item in readiness.json()["items"]
        )
        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        review = next(row for row in reviews.json() if row["enrollment_id"] == enrollment["id"])
        assert review["enrollment_version"] == 1
        approval_operation = str(uuid4())
        approved = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": approval_operation,
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": future_start.isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "active"
        assert approved.json()["version"] == 2
        assert approved.json()["placement_effective_date"] == future_start.isoformat()
        assert approved.json()["is_active"] is False
        replay = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": approval_operation,
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": future_start.isoformat(),
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        stale_approval = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": future_start.isoformat(),
            },
        )
        assert stale_approval.status_code == 409
        assert stale_approval.json()["detail"]["code"] == "stale_childcare_resource"
        future_ended = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "status": "ended",
                "end_date": (future_start + timedelta(days=1)).isoformat(),
            },
        )
        assert future_ended.status_code == 422
        assert future_ended.json()["detail"]["code"] == (
            "future_end_requires_scheduled_departure_workflow"
        )
        second_approval = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "room_id": room["id"],
                "effective_date": future_start.isoformat(),
            },
        )
        assert second_approval.status_code == 409
        assert second_approval.json()["detail"]["code"] == ("enrollment_placement_already_resolved")

        roster = client.get(
            "/api/v1/room-rosters",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert roster.status_code == 200, roster.text
        room_row = next(row for row in roster.json()["rooms"] if row["room_id"] == room["id"])
        assert room_row["occupancy"] == 0
        assert room_row["children"] == []
        assert [row["child_id"] for row in room_row["reserved_children"]] == [child["id"]]
        assert room_row["reserved_children"][0]["enrollment_version"] == 2

        facility_date = roster.json()["facility_date"]
        care_daybook = client.get(
            f"/api/v1/care/rooms/{room['id']}/day",
            headers=headers,
            params={"date": facility_date},
        )
        assert care_daybook.status_code == 200, care_daybook.text
        assert child["id"] not in {row["child_id"] for row in care_daybook.json()["children"]}
        medication_daybook = client.get(
            f"/api/v1/medications/rooms/{room['id']}/day",
            headers=headers,
            params={"date": facility_date},
        )
        assert medication_daybook.status_code == 200, medication_daybook.text
        assert child["id"] not in {row["child_id"] for row in medication_daybook.json()["children"]}

        check_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
            },
        )
        assert check_in.status_code == 409
        assert check_in.json()["detail"] == (
            "Child has no active enrollment at this facility on the service date"
        )
        with application.state.database.session_factory() as session:
            stored = session.scalar(
                select(Enrollment).where(Enrollment.id == UUID(enrollment["id"]))
            )
            assert stored is not None
            assert stored.placement_effective_date == future_start


def test_pending_family_placement_signal_opens_exact_family_status_remediation(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        child = _child(client, headers, family["id"])
        facility, _, room = _facility_tree(client, headers)
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )
        approved = _post(
            client,
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": _facility_today().isoformat(),
            },
        )
        assert approved["status"] == "active"

        # Reproduce an imported/legacy contradiction that normal commands forbid.
        with application.state.database.session_factory() as session:
            stored_family = session.scalar(select(Family).where(Family.id == UUID(family["id"])))
            assert stored_family is not None
            stored_family.status = "pending"
            session.commit()

        response = client.get(
            "/api/v1/child-record-readiness",
            headers=headers,
            params={"code": "enrollment_placement_incoherent"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        item = response.json()["items"][0]
        assert item["child_id"] == child["id"]
        assert item["enrollment_id"] == enrollment["id"]
        assert item["family_id"] == family["id"]
        assert item["title"] == "Exact Child: family activation required"
        assert "Exact Family is Pending" in item["message"]
        assert "change the family to Active" in item["message"]
        assert item["action_route"] == (
            f"/families/{family['id']}?focus=family-status"
            f"&child_id={child['id']}&enrollment_id={enrollment['id']}"
        )

        # Other placement contradictions keep the generic child-record lane.
        with application.state.database.session_factory() as session:
            stored_family = session.scalar(select(Family).where(Family.id == UUID(family["id"])))
            stored_room = session.scalar(select(Room).where(Room.id == UUID(room["id"])))
            assert stored_family is not None and stored_room is not None
            stored_family.status = "active"
            stored_room.is_active = False
            session.commit()
        generic = client.get(
            "/api/v1/child-record-readiness",
            headers=headers,
            params={"code": "enrollment_placement_incoherent"},
        )
        assert generic.status_code == 200, generic.text
        assert generic.json()["total"] == 1
        assert generic.json()["items"][0]["title"] == "Enrollment placement needs review"
        assert generic.json()["items"][0]["action_route"] == f"/children/{child['id']}"


def test_child_and_enrollment_commands_are_exact_actor_private_and_exactly_once(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        _, second_headers = _second_actor_headers(
            application,
            client,
            auth["user"]["organization_id"],
        )
        family_operation = str(uuid4())
        family = _family(client, owner_headers, family_operation)

        child_operation = str(uuid4())
        child_payload = {
            "client_operation_id": child_operation,
            "family_id": family["id"],
            "first_name": "Exact Child",
            "last_name": "Command",
            "date_of_birth": "2023-05-01",
        }
        created_child = client.post(
            "/api/v1/children",
            headers=owner_headers,
            json=child_payload,
        )
        assert created_child.status_code == 201, created_child.text
        child = created_child.json()
        assert child["replayed"] is False
        replayed_child = client.post(
            "/api/v1/children",
            headers=owner_headers,
            json=child_payload,
        )
        assert replayed_child.status_code == 201, replayed_child.text
        assert replayed_child.json()["id"] == child["id"]
        assert replayed_child.json()["replayed"] is True
        altered_child = client.post(
            "/api/v1/children",
            headers=owner_headers,
            json={**child_payload, "last_name": "Changed"},
        )
        assert altered_child.status_code == 409
        assert altered_child.json()["detail"]["code"] == "operation_reused"
        private_child = client.post(
            "/api/v1/children",
            headers=second_headers,
            json=child_payload,
        )
        assert private_child.status_code == 404
        assert private_child.json()["detail"] == "Operation receipt not found"

        facility, _, _ = _facility_tree(client, owner_headers)
        enrollment_operation = str(uuid4())
        enrollment_payload = {
            "client_operation_id": enrollment_operation,
            "facility_id": facility["id"],
            "start_date": _facility_today().isoformat(),
        }
        created_enrollment = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=owner_headers,
            json=enrollment_payload,
        )
        assert created_enrollment.status_code == 201, created_enrollment.text
        enrollment = created_enrollment.json()
        assert enrollment["replayed"] is False
        enrollment_receipt = client.get(
            f"/api/v1/childcare-commands/{enrollment_operation}",
            headers=owner_headers,
        )
        assert enrollment_receipt.status_code == 200, enrollment_receipt.text
        assert enrollment_receipt.json()["action_route"] == (
            f"/children/{child['id']}?enrollment_id={enrollment['id']}"
        )
        replayed_enrollment = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=owner_headers,
            json=enrollment_payload,
        )
        assert replayed_enrollment.status_code == 201, replayed_enrollment.text
        assert replayed_enrollment.json()["id"] == enrollment["id"]
        assert replayed_enrollment.json()["replayed"] is True
        altered_enrollment = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=owner_headers,
            json={
                **enrollment_payload,
                "start_date": (_facility_today() + timedelta(days=1)).isoformat(),
            },
        )
        assert altered_enrollment.status_code == 409
        assert altered_enrollment.json()["detail"]["code"] == "operation_reused"
        private_enrollment = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=second_headers,
            json=enrollment_payload,
        )
        assert private_enrollment.status_code == 404
        assert private_enrollment.json()["detail"] == "Operation receipt not found"

        family_replay = client.post(
            "/api/v1/families",
            headers=owner_headers,
            json={
                "client_operation_id": family_operation,
                "name": "Exact Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0100",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Emergency",
                        "last_name": "Contact",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0101",
                    }
                ],
            },
        )
        assert family_replay.status_code == 201, family_replay.text
        assert family_replay.json()["replayed"] is True
        assert family_replay.json()["children"][0]["replayed"] is False
        assert family_replay.json()["children"][0]["enrollments"][0]["replayed"] is False

        organization_id = UUID(auth["user"]["organization_id"])
        command_ids = {UUID(child_operation), UUID(enrollment_operation)}
        with application.state.database.session_factory() as session:
            receipts = list(
                session.scalars(
                    select(ChildcareCommandReceipt).where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id.in_(command_ids),
                    )
                )
            )
            assert {row.client_operation_id for row in receipts} == command_ids
            assert len(receipts) == 2
            for entity_type, entity_id, action in (
                ("child", UUID(child["id"]), "child.created"),
                ("enrollment", UUID(enrollment["id"]), "enrollment.created"),
            ):
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(
                            AuditEvent.organization_id == organization_id,
                            AuditEvent.entity_type == entity_type,
                            AuditEvent.entity_id == entity_id,
                            AuditEvent.action == action,
                        )
                    )
                    == 1
                )
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(RealtimeEvent)
                        .where(
                            RealtimeEvent.organization_id == organization_id,
                            RealtimeEvent.entity_type == entity_type,
                            RealtimeEvent.entity_id == entity_id,
                            RealtimeEvent.event_type == action,
                        )
                    )
                    == 1
                )


def test_family_archive_blockers_and_readiness_unknown_facts(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        child = _child(client, headers, family["id"])
        blocked = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": family["version"],
                "status": "archived",
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "family_status_blocked"
        deactivated = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": child["version"],
                "is_active": False,
            },
        )
        assert deactivated.status_code == 200, deactivated.text
        archived = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": family["version"],
                "status": "archived",
            },
        )
        assert archived.status_code == 200, archived.text
        activation = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": deactivated.json()["version"],
                "is_active": True,
            },
        )
        assert activation.status_code == 409
        assert activation.json()["detail"]["code"] == "family_not_enrollable"
        readiness = client.get(
            "/api/v1/child-record-readiness",
            headers=headers,
            params={"code": "unknown_immunization_status"},
        )
        assert readiness.status_code == 200
        assert readiness.json()["total"] == 1
        assert readiness.json()["items"][0]["child_id"] == child["id"]
        assert sum(readiness.json()["counts"].values()) == readiness.json()["total"]


def test_batch_placement_preserves_order_replays_exactly_and_rolls_back_atomically(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        facility, program, room = _facility_tree(client, headers)
        second_room = _post(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Second Command Room",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        start_date = _facility_today() + timedelta(days=5)

        successful: list[dict] = []
        for _ in range(2):
            child = _child(client, headers, family["id"])
            enrollment = _post(
                client,
                f"/api/v1/children/{child['id']}/enrollments",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "facility_id": facility["id"],
                    "start_date": start_date.isoformat(),
                },
            )
            successful.append(enrollment)

        success_operations = {enrollment["id"]: str(uuid4()) for enrollment in successful}
        input_order = list(reversed(successful))
        success_payload = {
            "placements": [
                {
                    "enrollment_id": enrollment["id"],
                    "client_operation_id": success_operations[enrollment["id"]],
                    "expected_version": 1,
                    "room_id": room["id"],
                    "effective_date": start_date.isoformat(),
                }
                for enrollment in input_order
            ]
        }
        approved = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json=success_payload,
        )
        assert approved.status_code == 200, approved.text
        assert [row["id"] for row in approved.json()["approvals"]] == [
            row["id"] for row in input_order
        ]
        assert all(row["version"] == 2 for row in approved.json()["approvals"])
        assert all(row["replayed"] is False for row in approved.json()["approvals"])

        replay = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json=success_payload,
        )
        assert replay.status_code == 200, replay.text
        assert [row["id"] for row in replay.json()["approvals"]] == [
            row["id"] for row in input_order
        ]
        assert all(row["replayed"] is True for row in replay.json()["approvals"])

        altered_reuse = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        **success_payload["placements"][0],
                        "room_id": second_room["id"],
                    }
                ]
            },
        )
        assert altered_reuse.status_code == 409
        assert altered_reuse.json()["detail"]["code"] == "operation_reused"

        duplicate_operation = str(uuid4())
        duplicate_ops = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        **success_payload["placements"][0],
                        "client_operation_id": duplicate_operation,
                    },
                    {
                        **success_payload["placements"][1],
                        "client_operation_id": duplicate_operation,
                    },
                ]
            },
        )
        assert duplicate_ops.status_code == 422

        rollback_enrollments: list[dict] = []
        for _ in range(2):
            child = _child(client, headers, family["id"])
            rollback_enrollments.append(
                _post(
                    client,
                    f"/api/v1/children/{child['id']}/enrollments",
                    headers,
                    {
                        "client_operation_id": str(uuid4()),
                        "facility_id": facility["id"],
                        "start_date": start_date.isoformat(),
                    },
                )
            )
        sorted_rollback = sorted(rollback_enrollments, key=lambda row: row["id"])
        valid_operation = str(uuid4())
        invalid_operation = str(uuid4())
        rollback = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        "enrollment_id": sorted_rollback[1]["id"],
                        "client_operation_id": invalid_operation,
                        "expected_version": 999,
                        "room_id": second_room["id"],
                        "effective_date": start_date.isoformat(),
                    },
                    {
                        "enrollment_id": sorted_rollback[0]["id"],
                        "client_operation_id": valid_operation,
                        "expected_version": 1,
                        "room_id": second_room["id"],
                        "effective_date": start_date.isoformat(),
                    },
                ]
            },
        )
        assert rollback.status_code == 409, rollback.text
        assert rollback.json()["detail"]["code"] == "stale_childcare_resource"

        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            stored_rollback = list(
                session.scalars(
                    select(Enrollment).where(
                        Enrollment.id.in_([UUID(row["id"]) for row in rollback_enrollments])
                    )
                )
            )
            assert len(stored_rollback) == 2
            assert all(row.version == 1 for row in stored_rollback)
            assert all(row.room_id is None for row in stored_rollback)
            assert all(row.program_id is None for row in stored_rollback)
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RealtimeEvent)
                    .where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_type == "enrollment",
                        RealtimeEvent.entity_id.in_(
                            [UUID(row["id"]) for row in rollback_enrollments]
                        ),
                        RealtimeEvent.event_type == "enrollment.room_placement.approved",
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id.in_(
                            [UUID(valid_operation), UUID(invalid_operation)]
                        ),
                    )
                )
                == 0
            )
            successful_ids = [UUID(row["id"]) for row in successful]
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.entity_type == "enrollment",
                        AuditEvent.entity_id.in_(successful_ids),
                        AuditEvent.action == "enrollment.room_placement.approved",
                    )
                )
                == 2
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RealtimeEvent)
                    .where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_type == "enrollment_batch",
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(RealtimeEvent)
                    .where(
                        RealtimeEvent.organization_id == organization_id,
                        RealtimeEvent.entity_type == "enrollment",
                        RealtimeEvent.entity_id.in_(successful_ids),
                        RealtimeEvent.event_type == "enrollment.room_placement.approved",
                    )
                )
                == 2
            )


def test_readiness_is_tenant_safe_and_facility_filters_family_level_items(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        first_auth, first_headers = _register(client)
        first_family = _family(client, first_headers)
        first_child = _child(client, first_headers, first_family["id"])
        first_facility, _, _ = _facility_tree(client, first_headers)
        first_enrollment = _post(
            client,
            f"/api/v1/children/{first_child['id']}/enrollments",
            first_headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": first_facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )

        second_facility = _post(
            client,
            "/api/v1/facilities",
            first_headers,
            {
                "name": "Second Readiness Centre",
                "status": "active",
                "licensed_capacity": 20,
            },
        )
        second_family = _family(client, first_headers)
        second_child = _child(client, first_headers, second_family["id"])
        second_enrollment = _post(
            client,
            f"/api/v1/children/{second_child['id']}/enrollments",
            first_headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": second_facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )
        orphan = _post(
            client,
            "/api/v1/families",
            first_headers,
            {"client_operation_id": str(uuid4()), "name": "No Facility Family"},
        )

        with application.state.database.session_factory() as session:
            stored_first = session.scalar(
                select(Family).where(Family.id == UUID(first_family["id"]))
            )
            assert stored_first is not None
            stored_first.status = "inactive"
            session.commit()

        _, other_headers = _register_named(client, "other-tenant")
        other_family = _post(
            client,
            "/api/v1/families",
            other_headers,
            {"client_operation_id": str(uuid4()), "name": "Other Tenant Family"},
        )

        first_filtered = client.get(
            "/api/v1/child-record-readiness",
            headers=first_headers,
            params={"facility_id": first_facility["id"]},
        )
        assert first_filtered.status_code == 200, first_filtered.text
        assert first_filtered.headers["cache-control"] == "private, no-store"
        first_items = first_filtered.json()["items"]
        assert {row["family_id"] for row in first_items} == {first_family["id"]}
        assert {row["code"] for row in first_items} == {
            "inactive_family_active_records",
            "unknown_immunization_status",
        }
        assert any(
            row["code"] == "inactive_family_active_records" and row["facility_id"] is None
            for row in first_items
        )
        # Room placement cannot be approved while the family is inactive. Keep
        # the actionable family lifecycle blocker and do not emit a dead room link.
        assert not any(row["action_route"].startswith("/rooms?") for row in first_items)
        assert first_filtered.json()["total"] == 2
        assert sum(first_filtered.json()["counts"].values()) == 2

        critical = client.get(
            "/api/v1/child-record-readiness",
            headers=first_headers,
            params={"facility_id": first_facility["id"], "severity": "critical"},
        )
        assert critical.status_code == 200, critical.text
        assert critical.json()["total"] == 1
        assert critical.json()["items"][0]["code"] == "inactive_family_active_records"
        immunization = client.get(
            "/api/v1/child-record-readiness",
            headers=first_headers,
            params={
                "facility_id": first_facility["id"],
                "code": "unknown_immunization_status",
            },
        )
        assert immunization.status_code == 200
        assert immunization.json()["total"] == 1
        assert immunization.json()["items"][0]["child_id"] == first_child["id"]

        second_filtered = client.get(
            "/api/v1/child-record-readiness",
            headers=first_headers,
            params={"facility_id": second_facility["id"]},
        )
        assert second_filtered.status_code == 200, second_filtered.text
        assert {row["family_id"] for row in second_filtered.json()["items"]} == {
            second_family["id"]
        }
        assert {
            row["enrollment_id"] for row in second_filtered.json()["items"] if row["enrollment_id"]
        } == {second_enrollment["id"]}

        paged = client.get(
            "/api/v1/child-record-readiness",
            headers=first_headers,
            params={"limit": 1, "offset": 1},
        )
        assert paged.status_code == 200
        assert len(paged.json()["items"]) == 1
        assert paged.json()["total"] > 1
        assert sum(paged.json()["counts"].values()) == paged.json()["total"]

        global_first = client.get("/api/v1/child-record-readiness", headers=first_headers)
        assert global_first.status_code == 200
        serialized = global_first.text
        assert other_family["id"] not in serialized
        assert orphan["id"] in serialized
        assert first_enrollment["id"] not in serialized

        global_other = client.get("/api/v1/child-record-readiness", headers=other_headers)
        assert global_other.status_code == 200
        assert {row["family_id"] for row in global_other.json()["items"]} == {other_family["id"]}
        assert first_family["id"] not in global_other.text


def test_patch_contracts_reject_empty_intent_and_explicit_nonnullable_nulls(
    tmp_path, monkeypatch
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        child = _child(client, headers, family["id"])
        facility, _, _ = _facility_tree(client, headers)
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )

        empty_family = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": family["version"],
            },
        )
        assert empty_family.status_code == 422
        for field_name in ("name", "status", "consents"):
            response = client.patch(
                f"/api/v1/families/{family['id']}",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": family["version"],
                    field_name: None,
                },
            )
            assert response.status_code == 422, (field_name, response.text)

        empty_child = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": child["version"],
            },
        )
        assert empty_child.status_code == 422
        for field_name in (
            "family_id",
            "first_name",
            "last_name",
            "date_of_birth",
            "is_active",
        ):
            response = client.patch(
                f"/api/v1/children/{child['id']}",
                headers=headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": child["version"],
                    field_name: None,
                },
            )
            assert response.status_code == 422, (field_name, response.text)

        empty_enrollment = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
            },
        )
        assert empty_enrollment.status_code == 422
        null_status = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "status": None,
            },
        )
        assert null_status.status_code == 422


def test_family_directory_contracts_are_bounded_literal_and_temporal(tmp_path, monkeypatch) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)

        def create_named_family(name: str, guardian_name: str = "Current") -> dict:
            return _post(
                client,
                "/api/v1/families",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "name": name,
                    "primary_guardian": {
                        "first_name": guardian_name,
                        "last_name": "Payer",
                        "email": f"{uuid4().hex}@example.com",
                        "cell_phone": "780-555-0190",
                        "address": "1 Test Way",
                        "city": "Edmonton",
                        "postal_code": "T5A 0A1",
                    },
                    "emergency_contacts": [
                        {
                            "first_name": "Current",
                            "last_name": "Emergency",
                            "relationship": "Aunt",
                            "cell_phone": "780-555-0191",
                        }
                    ],
                },
            )

        focus = create_named_family("Directory Focus", "RetiredGuardianMarker")
        create_named_family("Literal % Family")
        create_named_family("Literal _ Family")
        same_one = create_named_family("same sort name")
        same_two = create_named_family("Same Sort Name")
        for index in range(6):
            child = _post(
                client,
                "/api/v1/children",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": focus["id"],
                    "first_name": f"Preview {index}",
                    "last_name": "Child",
                    "date_of_birth": "2023-01-01",
                },
            )
            if index == 5:
                response = client.patch(
                    f"/api/v1/children/{child['id']}",
                    headers=headers,
                    json={
                        "client_operation_id": str(uuid4()),
                        "expected_version": child["version"],
                        "is_active": False,
                    },
                )
                assert response.status_code == 200, response.text

        replaced = client.put(
            f"/api/v1/families/{focus['id']}/guardians/primary",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": focus["version"],
                "guardian": {
                    "first_name": "Visible",
                    "last_name": "Payer",
                    "email": "visible@example.com",
                    "cell_phone": "780-555-0192",
                    "address": "2 Test Way",
                    "city": "Edmonton",
                    "postal_code": "T5A 0A2",
                },
            },
        )
        assert replaced.status_code == 200, replaced.text
        replaced_contacts = client.put(
            f"/api/v1/families/{focus['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": replaced.json()["version"],
                "emergency_contacts": [
                    {
                        "first_name": "Visible",
                        "last_name": "Emergency",
                        "relationship": "Uncle",
                        "cell_phone": "780-555-0193",
                    }
                ],
            },
        )
        assert replaced_contacts.status_code == 200, replaced_contacts.text

        statements: list[str] = []

        def capture_statement(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(" ".join(statement.lower().split()))

        event.listen(application.state.database.engine, "before_cursor_execute", capture_statement)
        try:
            directory = client.get(
                "/api/v1/families/directory",
                headers=headers,
                params={"search": "Directory", "limit": 50, "offset": 0},
            )
        finally:
            event.remove(
                application.state.database.engine,
                "before_cursor_execute",
                capture_statement,
            )
        assert directory.status_code == 200, directory.text
        assert client.get("/api/v1/children", headers=headers).status_code == 405
        directory_queries = [
            statement
            for statement in statements
            if " from families" in statement
            or " from guardians" in statement
            or " from (select children" in statement
        ]
        assert len(directory_queries) == 4
        payload = directory.json()
        assert payload["total"] == 1
        assert payload["limit"] == 50
        assert payload["offset"] == 0
        item = payload["items"][0]
        assert set(item) == {
            "id",
            "organization_id",
            "name",
            "file_number",
            "status",
            "version",
            "created_at",
            "updated_at",
            "primary_contact",
            "active_children",
            "active_child_count",
        }
        assert item["active_child_count"] == 5
        assert len(item["active_children"]) == 4
        assert len({child["id"] for child in item["active_children"]}) == 4
        assert item["primary_contact"]["first_name"] == "Visible"

        assert (
            client.get(
                "/api/v1/families/directory",
                headers=headers,
                params={"search": "RetiredGuardianMarker"},
            ).json()["total"]
            == 0
        )
        percent = client.get("/api/v1/families/directory", headers=headers, params={"search": "%"})
        underscore = client.get(
            "/api/v1/families/directory", headers=headers, params={"search": "_"}
        )
        assert [row["name"] for row in percent.json()["items"]] == ["Literal % Family"]
        assert [row["name"] for row in underscore.json()["items"]] == ["Literal _ Family"]
        unfiltered = client.get("/api/v1/families/directory", headers=headers).json()
        whitespace = client.get(
            "/api/v1/families/directory", headers=headers, params={"search": "   "}
        ).json()
        assert whitespace["total"] == unfiltered["total"]

        sorted_same_ids = [
            row["id"]
            for row in unfiltered["items"]
            if row["id"] in {same_one["id"], same_two["id"]}
        ]
        assert sorted_same_ids == sorted([same_one["id"], same_two["id"]])
        assert client.get("/api/v1/families", headers=headers).status_code == 405

        for path, expected_queries in (
            ("/api/v1/families/options", 2),
            ("/api/v1/families/billing-options", 3),
        ):
            statements.clear()
            event.listen(
                application.state.database.engine,
                "before_cursor_execute",
                capture_statement,
            )
            try:
                response = client.get(
                    path,
                    headers=headers,
                    params={"search": "Directory", "limit": 200, "offset": 0},
                )
            finally:
                event.remove(
                    application.state.database.engine,
                    "before_cursor_execute",
                    capture_statement,
                )
            assert response.status_code == 200, response.text
            domain_queries = [
                statement
                for statement in statements
                if " from families" in statement or " from guardians" in statement
            ]
            assert len(domain_queries) == expected_queries
            assert response.json()["total"] == 1
            assert len(response.json()["items"]) == 1
        billing_item = client.get(
            "/api/v1/families/billing-options",
            headers=headers,
            params={"search": "Visible Payer"},
        ).json()["items"][0]
        assert set(billing_item) == {
            "id",
            "organization_id",
            "name",
            "status",
            "guardians",
        }
        assert len(billing_item["guardians"]) == 1
        assert billing_item["guardians"][0]["guardian_type"] == "primary"


def test_alternate_model_paths_default_pickup_authorization_to_false(tmp_path, monkeypatch) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        with application.state.database.session_factory() as session:
            guardian = Guardian(
                id=uuid4(),
                organization_id=UUID(auth["user"]["organization_id"]),
                family_id=UUID(family["id"]),
                first_name="Imported",
                last_name="Guardian",
                email="",
                cell_phone="780-555-0123",
                is_primary=False,
            )
            contact = EmergencyContact(
                id=uuid4(),
                organization_id=UUID(auth["user"]["organization_id"]),
                family_id=UUID(family["id"]),
                first_name="Imported",
                last_name="Contact",
                relationship="Aunt",
                cell_phone="780-555-0124",
            )
            session.add_all([guardian, contact])
            session.flush()
            assert guardian.authorized_pickup is False
            assert contact.authorized_pickup is False


def test_command_reconciliation_is_org_bound_actor_private_and_non_pii(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, owner_headers = _register(client)
        operation_id = str(uuid4())
        family = _family(client, owner_headers, operation_id)
        receipt = client.get(
            f"/api/v1/childcare-commands/{operation_id}",
            headers=owner_headers,
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.headers["cache-control"] == "private, no-store"
        assert receipt.headers["pragma"] == "no-cache"
        assert receipt.json() == {
            "organization_id": auth["user"]["organization_id"],
            "client_operation_id": operation_id,
            "command_type": "family.create",
            "target_type": "family",
            "target_id": family["id"],
            "committed_version": 1,
            "committed_at": receipt.json()["committed_at"],
            "facility_id": None,
            "action_route": f"/families/{family['id']}",
        }
        assert "actor" not in receipt.text
        assert "request_hash" not in receipt.text

        second_actor_id, second_headers = _second_actor_headers(
            application,
            client,
            auth["user"]["organization_id"],
        )
        occupied_receipt = client.get(
            f"/api/v1/childcare-commands/{operation_id}", headers=second_headers
        )
        assert occupied_receipt.status_code == 404
        assert occupied_receipt.headers["cache-control"] == "private, no-store"
        assert occupied_receipt.headers["pragma"] == "no-cache"
        assert occupied_receipt.json() == {
            "detail": {
                "code": "operation_finalized_absent",
                "message": (
                    "No committed childcare command exists for this identity and operation."
                ),
                "actor_user_id": second_actor_id,
                "client_operation_id": operation_id,
                "organization_id": auth["user"]["organization_id"],
            }
        }
        _, other_headers = _register_named(client, "receipt-other-tenant")
        assert (
            client.get(
                f"/api/v1/childcare-commands/{operation_id}", headers=other_headers
            ).status_code
            == 404
        )
        absent_operation = uuid4()
        absent = client.get(
            f"/api/v1/childcare-commands/{absent_operation}",
            headers=owner_headers,
        )
        assert absent.status_code == 404
        assert absent.headers["cache-control"] == "private, no-store"
        assert absent.headers["pragma"] == "no-cache"
        assert absent.json() == {
            "detail": {
                "code": "operation_finalized_absent",
                "message": (
                    "No committed childcare command exists for this identity and operation."
                ),
                "actor_user_id": auth["user"]["id"],
                "client_operation_id": str(absent_operation),
                "organization_id": auth["user"]["organization_id"],
            }
        }
        with application.state.database.session_factory() as session:
            claim = session.scalar(
                select(ChildcareCommandClaim).where(
                    ChildcareCommandClaim.organization_id == UUID(auth["user"]["organization_id"]),
                    ChildcareCommandClaim.client_operation_id == absent_operation,
                )
            )
            assert claim is not None
            assert str(claim.actor_user_id) == auth["user"]["id"]
            proof = session.scalar(
                select(ChildcareCommandReconciliationProof).where(
                    ChildcareCommandReconciliationProof.organization_id
                    == UUID(auth["user"]["organization_id"]),
                    ChildcareCommandReconciliationProof.actor_user_id == UUID(auth["user"]["id"]),
                    ChildcareCommandReconciliationProof.client_operation_id == absent_operation,
                )
            )
            slot = session.scalar(
                select(ChildcareCommandSlot).where(
                    ChildcareCommandSlot.organization_id == UUID(auth["user"]["organization_id"]),
                    ChildcareCommandSlot.client_operation_id == absent_operation,
                )
            )
            assert proof is not None
            assert slot is not None and slot.entry_kind == "absence_claim"

        occupied_claim = client.get(
            f"/api/v1/childcare-commands/{absent_operation}",
            headers=second_headers,
        )
        assert occupied_claim.status_code == 404
        assert occupied_claim.headers["cache-control"] == "private, no-store"
        assert occupied_claim.headers["pragma"] == "no-cache"
        assert occupied_claim.json() == {
            "detail": {
                "code": "operation_finalized_absent",
                "message": occupied_receipt.json()["detail"]["message"],
                "actor_user_id": second_actor_id,
                "client_operation_id": str(absent_operation),
                "organization_id": auth["user"]["organization_id"],
            }
        }
        assert set(occupied_claim.json()["detail"]) == set(occupied_receipt.json()["detail"])

        repeated_absent = client.get(
            f"/api/v1/childcare-commands/{absent_operation}",
            headers=owner_headers,
        )
        assert repeated_absent.status_code == 404
        assert repeated_absent.json() == absent.json()
        assert repeated_absent.headers["cache-control"] == "private, no-store"

        family_count_before = 0
        audit_count_before = 0
        realtime_count_before = 0
        with application.state.database.session_factory() as session:
            family_count_before = int(session.scalar(select(func.count()).select_from(Family)) or 0)
            audit_count_before = int(
                session.scalar(select(func.count()).select_from(AuditEvent)) or 0
            )
            realtime_count_before = int(
                session.scalar(select(func.count()).select_from(RealtimeEvent)) or 0
            )
        blocked = client.post(
            "/api/v1/families",
            headers=owner_headers,
            json={
                "client_operation_id": str(absent_operation),
                "name": "Must Never Be Written",
            },
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"] == {
            "code": "operation_finalized_absent",
            "message": "No committed childcare command exists for this identity and operation.",
            "actor_user_id": auth["user"]["id"],
            "client_operation_id": str(absent_operation),
            "organization_id": auth["user"]["organization_id"],
        }
        other_actor_blocked = client.post(
            "/api/v1/families",
            headers=second_headers,
            json={
                "client_operation_id": str(absent_operation),
                "name": "Must Never Be Written By Another Actor",
            },
        )
        assert other_actor_blocked.status_code == 404
        assert other_actor_blocked.json() == {"detail": "Operation receipt not found"}
        with application.state.database.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(Family)) or 0) == (
                family_count_before
            )
            assert int(session.scalar(select(func.count()).select_from(AuditEvent)) or 0) == (
                audit_count_before
            )
            assert int(session.scalar(select(func.count()).select_from(RealtimeEvent)) or 0) == (
                realtime_count_before
            )
            assert (
                int(
                    session.scalar(
                        select(func.count())
                        .select_from(ChildcareCommandClaim)
                        .where(
                            ChildcareCommandClaim.organization_id
                            == UUID(auth["user"]["organization_id"]),
                            ChildcareCommandClaim.client_operation_id == absent_operation,
                        )
                    )
                    or 0
                )
                == 1
            )
            second_actor_proofs = int(
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReconciliationProof)
                    .where(
                        ChildcareCommandReconciliationProof.organization_id
                        == UUID(auth["user"]["organization_id"]),
                        ChildcareCommandReconciliationProof.actor_user_id == UUID(second_actor_id),
                        ChildcareCommandReconciliationProof.client_operation_id.in_(
                            [UUID(operation_id), absent_operation]
                        ),
                    )
                )
                or 0
            )
            assert second_actor_proofs == 2


def test_sqlite_reconciliation_get_wins_and_permanently_blocks_delayed_post(
    tmp_path, monkeypatch
) -> None:
    from app.api.basic import childcare_command_receipts as receipt_api

    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        operation_id = uuid4()
        slot_reserved = Event()
        release_reader = Event()
        post_done = Event()
        responses: dict[str, object] = {}
        original = receipt_api.reserve_sqlite_operation_slot

        def delayed_reader_slot(*args, **kwargs):
            slot = original(*args, **kwargs)
            slot_reserved.set()
            assert release_reader.wait(timeout=8)
            return slot

        monkeypatch.setattr(
            receipt_api,
            "reserve_sqlite_operation_slot",
            delayed_reader_slot,
        )

        def read_missing() -> None:
            responses["get"] = client.get(
                f"/api/v1/childcare-commands/{operation_id}",
                headers=headers,
            )

        def delayed_post() -> None:
            assert slot_reserved.wait(timeout=8)
            responses["post"] = client.post(
                "/api/v1/families",
                headers=headers,
                json={
                    "client_operation_id": str(operation_id),
                    "name": "SQLite GET Must Win",
                },
            )
            post_done.set()

        read_thread = Thread(target=read_missing, daemon=True)
        post_thread = Thread(target=delayed_post, daemon=True)
        read_thread.start()
        post_thread.start()
        assert slot_reserved.wait(timeout=8)
        assert not post_done.wait(timeout=0.25)
        release_reader.set()
        read_thread.join(timeout=10)
        post_thread.join(timeout=10)
        assert not read_thread.is_alive() and not post_thread.is_alive()

        get_response = responses["get"]
        post_response = responses["post"]
        assert get_response.status_code == 404
        assert get_response.json()["detail"]["code"] == "operation_finalized_absent"
        assert post_response.status_code == 409
        assert post_response.json()["detail"]["code"] == "operation_finalized_absent"
        with application.state.database.session_factory() as session:
            organization_id = UUID(auth["user"]["organization_id"])
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Family)
                    .where(Family.name == "SQLite GET Must Win")
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id == operation_id,
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandClaim)
                    .where(
                        ChildcareCommandClaim.organization_id == organization_id,
                        ChildcareCommandClaim.client_operation_id == operation_id,
                    )
                )
                == 1
            )


def test_sqlite_command_post_wins_and_reconciliation_returns_receipt(tmp_path, monkeypatch) -> None:
    from app.basic import childcare_commands

    client, _ = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        operation_id = uuid4()
        slot_reserved = Event()
        release_writer = Event()
        reader_done = Event()
        responses: dict[str, object] = {}
        original = childcare_commands.reserve_sqlite_operation_slot

        def delayed_writer_slot(*args, **kwargs):
            slot = original(*args, **kwargs)
            if kwargs.get("entry_kind") == "receipt":
                slot_reserved.set()
                assert release_writer.wait(timeout=8)
            return slot

        monkeypatch.setattr(
            childcare_commands,
            "reserve_sqlite_operation_slot",
            delayed_writer_slot,
        )

        def create_family() -> None:
            responses["post"] = client.post(
                "/api/v1/families",
                headers=headers,
                json={
                    "client_operation_id": str(operation_id),
                    "name": "SQLite POST Must Win",
                },
            )

        def reconcile() -> None:
            assert slot_reserved.wait(timeout=8)
            responses["get"] = client.get(
                f"/api/v1/childcare-commands/{operation_id}",
                headers=headers,
            )
            reader_done.set()

        post_thread = Thread(target=create_family, daemon=True)
        read_thread = Thread(target=reconcile, daemon=True)
        post_thread.start()
        read_thread.start()
        assert slot_reserved.wait(timeout=8)
        assert not reader_done.wait(timeout=0.25)
        release_writer.set()
        post_thread.join(timeout=10)
        read_thread.join(timeout=10)
        assert not post_thread.is_alive() and not read_thread.is_alive()

        post_response = responses["post"]
        get_response = responses["get"]
        assert post_response.status_code == 201, post_response.text
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["client_operation_id"] == str(operation_id)
        assert get_response.json()["target_id"] == post_response.json()["id"]


def test_read_only_sqlite_reconciliation_never_writes_and_fails_unknown_as_unresolved(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        receipt_operation = str(uuid4())
        _family(client, headers, receipt_operation)
        absent_operation = uuid4()
        terminal = client.get(
            f"/api/v1/childcare-commands/{absent_operation}",
            headers=headers,
        )
        assert terminal.status_code == 404

    read_only_settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=application.state.settings.database_path,
        database_name="caresync",
        database_read_only=True,
        enable_advanced_routes=False,
        jwt_secret="childcare-command-spine-test-secret-32-bytes",
    )
    read_only_application = create_app(read_only_settings)
    unknown_operation = uuid4()
    with TestClient(read_only_application) as read_only_client:
        receipt = read_only_client.get(
            f"/api/v1/childcare-commands/{receipt_operation}",
            headers=headers,
        )
        assert receipt.status_code == 200
        existing_terminal = read_only_client.get(
            f"/api/v1/childcare-commands/{absent_operation}",
            headers=headers,
        )
        assert existing_terminal.status_code == 404
        assert existing_terminal.json()["detail"]["code"] == "operation_finalized_absent"
        unknown = read_only_client.get(
            f"/api/v1/childcare-commands/{unknown_operation}",
            headers=headers,
        )
        assert unknown.status_code == 503
        assert unknown.json() == {"detail": {"code": "operation_reconciliation_unavailable"}}

    with application.state.database.session_factory() as session:
        organization_id = UUID(auth["user"]["organization_id"])
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChildcareCommandSlot)
                .where(
                    ChildcareCommandSlot.organization_id == organization_id,
                    ChildcareCommandSlot.client_operation_id == unknown_operation,
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReconciliationProof)
                .where(
                    ChildcareCommandReconciliationProof.organization_id == organization_id,
                    ChildcareCommandReconciliationProof.client_operation_id == unknown_operation,
                )
            )
            == 0
        )


def test_active_family_is_required_for_enrollment_placement_and_status_regression(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        pending_family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Pending Family",
                "status": "pending",
            },
        )
        child = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": pending_family["id"],
                "first_name": "Pending",
                "last_name": "Child",
                "date_of_birth": "2024-01-01",
                "is_active": False,
            },
        )
        facility, _, room = _facility_tree(client, headers)
        rejected = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "family_not_enrollable"
        rejected_activation = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": child["version"],
                "is_active": True,
            },
        )
        assert rejected_activation.status_code == 409
        assert rejected_activation.json()["detail"]["code"] == "family_not_enrollable"
        activated = client.patch(
            f"/api/v1/families/{pending_family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": pending_family["version"],
                "status": "active",
            },
        )
        assert activated.status_code == 200, activated.text
        activated_child = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": child["version"],
                "is_active": True,
            },
        )
        assert activated_child.status_code == 200, activated_child.text
        draft_target = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Pending Reparent Target",
                "status": "pending",
            },
        )
        reparent_to_pending = client.patch(
            f"/api/v1/children/{child['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": activated_child.json()["version"],
                "family_id": draft_target["id"],
            },
        )
        assert reparent_to_pending.status_code == 409
        assert reparent_to_pending.json()["detail"]["code"] == "family_not_enrollable"
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": _facility_today().isoformat(),
            },
        )
        regression = client.patch(
            f"/api/v1/families/{pending_family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": activated.json()["version"],
                "status": "pending",
            },
        )
        assert regression.status_code == 409
        assert regression.json()["detail"]["code"] == "family_status_blocked"

        with application.state.database.session_factory() as session:
            stored_family = session.scalar(
                select(Family).where(Family.id == UUID(pending_family["id"]))
            )
            assert stored_family is not None
            stored_family.status = "pending"
            session.commit()
        approval_operation = str(uuid4())
        placement = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": approval_operation,
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": _facility_today().isoformat(),
            },
        )
        assert placement.status_code == 409
        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(
                        ChildcareCommandReceipt.organization_id == organization_id,
                        ChildcareCommandReceipt.client_operation_id == UUID(approval_operation),
                    )
                )
                == 0
            )
            stored_enrollment = session.scalar(
                select(Enrollment).where(Enrollment.id == UUID(enrollment["id"]))
            )
            assert stored_enrollment is not None
            stored_enrollment.program_id = UUID(room["program_id"])
            stored_enrollment.room_id = UUID(room["id"])
            stored_enrollment.placement_effective_date = _facility_today()
            stored_enrollment.status = "active"
            session.commit()
        lifecycle = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "status": "paused",
            },
        )
        assert lifecycle.status_code == 409
        assert lifecycle.json()["detail"]["code"] == "family_not_enrollable"


def test_enrollment_end_requires_ended_and_cannot_erase_attendance_history(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        child = _child(client, headers, family["id"])
        facility, _, room = _facility_tree(client, headers)
        start_date = _facility_today() - timedelta(days=10)
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": start_date.isoformat(),
            },
        )
        approved = _post(
            client,
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": _facility_today().isoformat(),
            },
        )
        contradictory = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": approved["version"],
                "status": "active",
                "end_date": _facility_today().isoformat(),
            },
        )
        assert contradictory.status_code == 422
        assert contradictory.json()["detail"]["code"] == "end_date_requires_ended_status"

        organization_id = UUID(auth["user"]["organization_id"])
        service_date = _facility_today() - timedelta(days=2)
        with application.state.database.session_factory() as session:
            stored = session.scalar(
                select(Enrollment).where(Enrollment.id == UUID(enrollment["id"]))
            )
            assert stored is not None
            stored.placement_effective_date = start_date
            session.add(
                AttendanceDay(
                    id=uuid4(),
                    organization_id=organization_id,
                    facility_id=UUID(facility["id"]),
                    child_id=UUID(child["id"]),
                    enrollment_id=UUID(enrollment["id"]),
                    room_id=UUID(room["id"]),
                    service_date=service_date,
                    status="present",
                    version=1,
                )
            )
            session.commit()
        erased = client.patch(
            f"/api/v1/enrollments/{enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": approved["version"],
                "status": "ended",
                "end_date": (_facility_today() - timedelta(days=5)).isoformat(),
            },
        )
        assert erased.status_code == 409
        assert erased.json()["detail"] == {
            "code": "end_date_precedes_attendance_history",
            "latest_attendance_date": service_date.isoformat(),
        }


def test_reverse_time_single_and_batch_placement_never_overbook_commitments(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client)
        family = _family(client, headers)
        facility, program, _ = _facility_tree(client, headers)

        def capacity_one_room(name: str) -> dict:
            return _post(
                client,
                "/api/v1/rooms",
                headers,
                {
                    "facility_id": facility["id"],
                    "program_id": program["id"],
                    "name": name,
                    "capacity": 1,
                    "minimum_age_months": 0,
                    "maximum_age_months": 143,
                },
            )

        def pending_enrollment(start_date: date) -> tuple[dict, dict]:
            child = _child(client, headers, family["id"])
            enrollment = _post(
                client,
                f"/api/v1/children/{child['id']}/enrollments",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "facility_id": facility["id"],
                    "start_date": start_date.isoformat(),
                },
            )
            return child, enrollment

        room = capacity_one_room("Reverse Single")
        earlier = _facility_today() + timedelta(days=3)
        later = _facility_today() + timedelta(days=4)
        _, later_enrollment = pending_enrollment(later)
        _, earlier_enrollment = pending_enrollment(earlier)
        later_approval = client.post(
            f"/api/v1/enrollments/{later_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": later.isoformat(),
            },
        )
        assert later_approval.status_code == 200, later_approval.text
        reverse = client.post(
            f"/api/v1/enrollments/{earlier_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": earlier.isoformat(),
            },
        )
        assert reverse.status_code == 409
        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        review = next(
            row for row in reviews.json() if row["enrollment_id"] == earlier_enrollment["id"]
        )
        room_candidate = next(
            candidate for candidate in review["candidates"] if candidate["room_id"] == room["id"]
        )
        assert room_candidate["available_places"] == 0

        batch_room = capacity_one_room("Reverse Batch")
        _, first = pending_enrollment(_facility_today() + timedelta(days=5))
        _, second = pending_enrollment(_facility_today() + timedelta(days=6))
        batch = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json={
                "placements": [
                    {
                        "enrollment_id": second["id"],
                        "client_operation_id": str(uuid4()),
                        "expected_version": 1,
                        "room_id": batch_room["id"],
                        "effective_date": (_facility_today() + timedelta(days=6)).isoformat(),
                    },
                    {
                        "enrollment_id": first["id"],
                        "client_operation_id": str(uuid4()),
                        "expected_version": 1,
                        "room_id": batch_room["id"],
                        "effective_date": (_facility_today() + timedelta(days=5)).isoformat(),
                    },
                ]
            },
        )
        assert batch.status_code == 409, batch.text
        with application.state.database.session_factory() as session:
            stored = list(
                session.scalars(
                    select(Enrollment).where(
                        Enrollment.id.in_([UUID(first["id"]), UUID(second["id"])])
                    )
                )
            )
            assert len(stored) == 2
            assert all(enrollment.room_id is None for enrollment in stored)
            assert all(enrollment.version == 1 for enrollment in stored)

        paused = client.patch(
            f"/api/v1/enrollments/{later_enrollment['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "status": "paused",
            },
        )
        assert paused.status_code == 200, paused.text
        still_reserved = client.post(
            f"/api/v1/enrollments/{earlier_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": room["id"],
                "effective_date": earlier.isoformat(),
            },
        )
        assert still_reserved.status_code == 409


def test_child_directory_is_sql_paged_minimal_and_uses_future_placement_age(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        organization_id = UUID(auth["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            for index in range(105):
                session.add(
                    Child(
                        id=uuid4(),
                        organization_id=organization_id,
                        family_id=UUID(family["id"]),
                        first_name=f"Bulk {index:03d}",
                        last_name="Directory",
                        date_of_birth=date(2023, 1, 1),
                        age_group="Preschool",
                        is_active=index % 2 == 0,
                        version=1,
                    )
                )
            session.commit()

        statements: list[str] = []

        def capture_statement(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(" ".join(statement.lower().split()))

        event.listen(application.state.database.engine, "before_cursor_execute", capture_statement)
        try:
            directory = client.get(
                "/api/v1/children/directory",
                headers=headers,
                params={
                    "search": "Bulk",
                    "status": "all",
                    "care_lane": "all",
                    "limit": 50,
                    "offset": 100,
                },
            )
        finally:
            event.remove(
                application.state.database.engine,
                "before_cursor_execute",
                capture_statement,
            )
        assert directory.status_code == 200, directory.text
        payload = directory.json()
        assert payload["total"] == 105
        assert len(payload["items"]) == 5
        assert payload["counts"] == {
            "total": 105,
            "active": 53,
            "inactive": 52,
            "daycare": 0,
            "out_of_school_care": 0,
            "unassigned": 105,
            "reserved": 0,
            "needs_review": 0,
        }
        assert any(" limit ? offset ?" in statement for statement in statements)
        assert len(statements) <= 12
        expected_item_keys = {
            "id",
            "organization_id",
            "family_id",
            "family_name",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "age_group",
            "is_active",
            "version",
            "profile_photo_url",
            "profile_photo_updated_at",
            "created_at",
            "updated_at",
            "care_lane",
            "open_enrollment",
        }
        assert all(set(item) == expected_item_keys for item in payload["items"])
        assert all(
            forbidden not in directory.text
            for forbidden in (
                "health_care_number",
                "allergies",
                "medical_conditions",
                "doctor_name",
                "guardians",
                "consents",
                "additional_notes",
            )
        )

        facility, program, _ = _facility_tree(client, headers)
        age_room = _post(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Future Age Window",
                "capacity": 10,
                "minimum_age_months": 24,
                "maximum_age_months": 30,
            },
        )

        def months_before(reference: date, months: int) -> date:
            zero_based = reference.year * 12 + reference.month - 1 - months
            return date(zero_based // 12, zero_based % 12 + 1, min(reference.day, 28))

        future_date = _facility_today() + timedelta(days=62)
        reaches_minimum = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Future Minimum",
                "last_name": "Age",
                "date_of_birth": months_before(_facility_today(), 23).isoformat(),
            },
        )
        future_enrollment = _post(
            client,
            f"/api/v1/children/{reaches_minimum['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": future_date.isoformat(),
            },
        )
        approved = client.post(
            f"/api/v1/enrollments/{future_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "room_id": age_room["id"],
                "effective_date": future_date.isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text

        ages_out = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Future Maximum",
                "last_name": "Age",
                "date_of_birth": months_before(_facility_today(), 30).isoformat(),
            },
        )
        with application.state.database.session_factory() as session:
            session.add(
                Enrollment(
                    id=uuid4(),
                    organization_id=organization_id,
                    child_id=UUID(ages_out["id"]),
                    facility_id=UUID(facility["id"]),
                    program_id=UUID(program["id"]),
                    room_id=UUID(age_room["id"]),
                    placement_effective_date=future_date,
                    start_date=future_date,
                    status="active",
                    version=1,
                )
            )
            session.commit()
        future_rows = client.get(
            "/api/v1/children/directory",
            headers=headers,
            params={"search": "Future", "limit": 10, "offset": 0},
        )
        assert future_rows.status_code == 200, future_rows.text
        by_first_name = {item["first_name"]: item for item in future_rows.json()["items"]}
        assert by_first_name["Future Minimum"]["care_lane"] == "daycare"
        assert by_first_name["Future Minimum"]["open_enrollment"]["placement_state"] == ("reserved")
        assert by_first_name["Future Maximum"]["care_lane"] == "needs_review"
        assert by_first_name["Future Maximum"]["open_enrollment"]["placement_state"] == (
            "needs_review"
        )


def test_child_directory_does_not_reserve_an_enrollment_ended_before_today(
    tmp_path, monkeypatch
) -> None:
    client, application = _client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client)
        family = _family(client, headers)
        facility, program, room = _facility_tree(client, headers)
        child = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Stale Ended",
                "last_name": "Placement",
                "date_of_birth": "2024-01-01",
            },
        )
        organization_id = UUID(auth["user"]["organization_id"])
        placement_date = _facility_today() - timedelta(days=10)
        with application.state.database.session_factory() as session:
            session.add(
                Enrollment(
                    id=uuid4(),
                    organization_id=organization_id,
                    child_id=UUID(child["id"]),
                    facility_id=UUID(facility["id"]),
                    program_id=UUID(program["id"]),
                    room_id=UUID(room["id"]),
                    placement_effective_date=placement_date,
                    start_date=placement_date,
                    end_date=_facility_today() - timedelta(days=1),
                    status="active",
                    version=1,
                )
            )
            session.commit()

        directory = client.get(
            "/api/v1/children/directory",
            headers=headers,
            params={"search": "Stale Ended", "limit": 10, "offset": 0},
        )
        assert directory.status_code == 200, directory.text
        assert directory.json()["total"] == 1
        item = directory.json()["items"][0]
        assert item["care_lane"] == "needs_review"
        assert item["open_enrollment"]["placement_state"] == "needs_review"

        rosters = client.get(
            "/api/v1/room-rosters",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert rosters.status_code == 200, rosters.text
        room_roster = next(row for row in rosters.json()["rooms"] if row["room_id"] == room["id"])
        assert room_roster["occupancy"] == 0
        assert room_roster["children"] == []
        assert room_roster["reserved_children"] == []
