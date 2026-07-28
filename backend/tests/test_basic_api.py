"""CareSync Basic acceptance path and tenant-boundary tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.basic.models import BasicBase, OrganizationMembership, Role, User
from app.basic.security import create_access_token, hash_password
from app.basic.verification import apply_temporary_email_approval
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
        jwt_secret="basic-test-secret-with-at-least-32-bytes",
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
            "first_name": "Test",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict, organization_id: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {auth['access_token']}"}
    if organization_id:
        result["X-Organization-ID"] = organization_id
    return result


def test_temporary_verification_policy_and_read_only_contracts(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "verified@example.com", "Verified Child Care")
        headers = _headers(auth)
        user = auth["user"]
        assert user["email_verification_status"] == "verified"
        assert user["email_verified_at"] is not None
        assert user["email_verification_method"] == "temporary_auto_approval"

        organization = client.get("/api/v1/organization", headers=headers)
        assert organization.status_code == 200, organization.text
        organization_data = organization.json()
        assert organization_data["verification_status"] == "verified"
        assert organization_data["verified_at"] is not None
        assert organization_data["verification_method"] == "temporary_auto_approval"

        forbidden_profile = client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"email_verification_method": "manual_review"},
        )
        assert forbidden_profile.status_code == 422
        forbidden_organization = client.patch(
            "/api/v1/organization",
            headers=headers,
            json={"verification_status": "verified"},
        )
        assert forbidden_organization.status_code == 422
        forbidden_facility = client.post(
            "/api/v1/facilities",
            headers=headers,
            json={"name": "Spoofed Centre", "verification_status": "verified"},
        )
        assert forbidden_facility.status_code == 422

        facility = client.post(
            "/api/v1/facilities",
            headers=headers,
            json={
                "name": "Licensed Centre",
                "license_number": "AB-LICENCE-001",
                "licensed_capacity": 40,
            },
        )
        assert facility.status_code == 201, facility.text
        facility_data = facility.json()
        assert facility_data["verification_status"] == "verified"
        assert facility_data["verified_at"] is not None
        assert facility_data["verification_method"] == "temporary_auto_approval"

        original_facility_verified_at = datetime.fromisoformat(facility_data["verified_at"])
        changed_facility = client.patch(
            f"/api/v1/facilities/{facility_data['id']}",
            headers=headers,
            json={"license_number": "AB-LICENCE-002"},
        )
        assert changed_facility.status_code == 200, changed_facility.text
        assert (
            datetime.fromisoformat(changed_facility.json()["verified_at"])
            >= original_facility_verified_at
        )
        assert changed_facility.json()["verification_method"] == "temporary_auto_approval"

        original_organization_verified_at = datetime.fromisoformat(organization_data["verified_at"])
        changed_organization = client.patch(
            "/api/v1/organization",
            headers=headers,
            json={"legal_name": "Verified Child Care Ltd."},
        )
        assert changed_organization.status_code == 200, changed_organization.text
        assert (
            datetime.fromisoformat(changed_organization.json()["verified_at"])
            >= original_organization_verified_at
        )

        original_email_verified_at = datetime.fromisoformat(user["email_verified_at"])
        changed_email = client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"email": "new-verified@example.com"},
        )
        assert changed_email.status_code == 200, changed_email.text
        assert changed_email.json()["email_verification_status"] == "verified"
        assert changed_email.json()["email_verification_method"] == "temporary_auto_approval"
        assert (
            datetime.fromisoformat(changed_email.json()["email_verified_at"])
            >= original_email_verified_at
        )


def test_pending_email_fails_closed_for_login_and_bearer_token(tmp_path) -> None:
    client, application = _client(tmp_path)
    pending_user = User(
        id=uuid4(),
        email="pending@example.com",
        password_hash=hash_password("correct-password"),
        first_name="Pending",
        last_name="Owner",
    )
    with application.state.database.session_factory() as session:
        session.add(pending_user)
        session.commit()

    token = create_access_token(pending_user, application.state.settings)
    with client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "pending@example.com", "password": "correct-password"},
        )
        assert login.status_code == 403
        assert login.json()["detail"] == "Email verification required"

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 403
        assert me.json()["detail"] == "Email verification required"


def test_basic_register_onboard_room_family_child_and_attendance(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        service_now = datetime.now(ZoneInfo("America/Edmonton")).replace(microsecond=0)
        service_date_text = service_now.date().isoformat()
        check_in_at = (service_now - timedelta(minutes=4)).isoformat()
        check_out_at = (service_now - timedelta(minutes=2)).isoformat()
        auth = _register(client, "owner@example.com", "North Star Child Care")
        headers = _headers(auth)

        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/attendance/check-in" in paths
        assert "/api/v1/schedules/generate" not in paths
        assert "/api/v1/resources/{resource_name}" not in paths
        assert "/api/v1/claims/simulate" not in paths

        organization = client.patch(
            "/api/v1/organization",
            headers=headers,
            json={
                "legal_name": "North Star Child Care Ltd.",
                "phone": "780-555-0100",
                "timezone": "America/Edmonton",
            },
        )
        assert organization.status_code == 200, organization.text

        facility = client.post(
            "/api/v1/facilities",
            headers=headers,
            json={
                "name": "Downtown Centre",
                "license_number": "AB-TEST-001",
                "city": "Edmonton",
                "licensed_capacity": 80,
                "opening_time": "07:00:00",
                "closing_time": "18:00:00",
            },
        )
        assert facility.status_code == 201, facility.text
        facility_id = facility.json()["id"]

        program = client.post(
            "/api/v1/programs",
            headers=headers,
            json={
                "facility_id": facility_id,
                "name": "Infant Program",
                "program_type": "daycare",
                "capacity": 12,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert program.status_code == 201, program.text

        room = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility_id,
                "program_id": program.json()["id"],
                "name": "Moon Room",
                "capacity": 12,
                "age_group": "Infant",
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert room.status_code == 201, room.text

        completed = client.post("/api/v1/onboarding/complete", headers=headers)
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "complete"

        family = client.post(
            "/api/v1/families",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "name": "Example Family",
                "file_number": "F-001",
                "primary_guardian": {
                    "first_name": "Parent",
                    "last_name": "Example",
                    "email": "parent@example.com",
                    "cell_phone": "780-555-0111",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Emergency",
                        "last_name": "Contact",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0112",
                    }
                ],
                "consents": {"emergency_medical_consent": True},
            },
        )
        assert family.status_code == 201, family.text
        assert family.json()["guardians"][0]["guardian_type"] == "primary"

        child = client.post(
            "/api/v1/children",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": family.json()["id"],
                "first_name": "Child",
                "last_name": "Example",
                "date_of_birth": "2024-01-01",
            },
        )
        assert child.status_code == 201, child.text
        child_id = child.json()["id"]
        enrollment = client.post(
            f"/api/v1/children/{child_id}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility_id,
                "start_date": service_date_text,
            },
        )
        assert enrollment.status_code == 201, enrollment.text
        placement = client.post(
            f"/api/v1/enrollments/{enrollment.json()['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment.json()["version"],
                "room_id": room.json()["id"],
                "effective_date": service_date_text,
            },
        )
        assert placement.status_code == 200, placement.text
        assert placement.json()["is_active"] is True

        roster = client.get(
            f"/api/v1/attendance/roster?date={service_date_text}&facility_id={facility_id}",
            headers=headers,
        )
        assert roster.status_code == 200, roster.text
        assert roster.json()[0]["attendance_day"] is None

        check_in_operation = str(uuid4())
        check_in_payload = {
            "client_operation_id": check_in_operation,
            "child_id": child_id,
            "facility_id": facility_id,
            "occurred_at": check_in_at,
        }
        checked_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json=check_in_payload,
        )
        assert checked_in.status_code == 200, checked_in.text
        assert checked_in.json()["intervals"][0]["checked_out_at"] is None
        check_in_replay = client.post(
            "/api/v1/attendance/check-in", headers=headers, json=check_in_payload
        )
        assert check_in_replay.status_code == 200, check_in_replay.text
        assert check_in_replay.json()["id"] == checked_in.json()["id"]
        assert len(check_in_replay.json()["intervals"]) == 1

        duplicate = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child_id,
                "facility_id": facility_id,
            },
        )
        assert duplicate.status_code == 409

        operation_collision = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": check_in_operation,
                "child_id": child_id,
                "facility_id": facility_id,
                "occurred_at": check_out_at,
            },
        )
        assert operation_collision.status_code == 409

        check_out_payload = {
            "client_operation_id": str(uuid4()),
            "child_id": child_id,
            "facility_id": facility_id,
            "occurred_at": check_out_at,
        }
        checked_out = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json=check_out_payload,
        )
        assert checked_out.status_code == 200, checked_out.text
        assert checked_out.json()["intervals"][0]["checked_out_at"] is not None
        assert [event["event_type"] for event in checked_out.json()["events"]] == [
            "check_in",
            "check_out",
        ]
        check_out_replay = client.post(
            "/api/v1/attendance/check-out", headers=headers, json=check_out_payload
        )
        assert check_out_replay.status_code == 200, check_out_replay.text
        assert check_out_replay.json()["version"] == checked_out.json()["version"]

        history = client.get(
            f"/api/v1/attendance?date={service_date_text}&facility_id={facility_id}",
            headers=headers,
        )
        assert history.status_code == 200
        assert len(history.json()) == 1

        absent_child = client.post(
            "/api/v1/children",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": family.json()["id"],
                "first_name": "Absent",
                "last_name": "Example",
                "date_of_birth": "2023-01-01",
            },
        )
        assert absent_child.status_code == 201, absent_child.text
        absent_enrollment = client.post(
            f"/api/v1/children/{absent_child.json()['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility_id,
                "start_date": service_date_text,
            },
        )
        assert absent_enrollment.status_code == 201, absent_enrollment.text
        absent_placement = client.post(
            f"/api/v1/enrollments/{absent_enrollment.json()['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": absent_enrollment.json()["version"],
                "room_id": room.json()["id"],
                "effective_date": service_date_text,
            },
        )
        assert absent_placement.status_code == 200, absent_placement.text
        absent = client.put(
            "/api/v1/attendance/absence",
            headers=headers,
            json={
                "child_id": absent_child.json()["id"],
                "facility_id": facility_id,
                "date": service_date_text,
                "reason": "Family reported absence",
            },
        )
        assert absent.status_code == 200, absent.text
        assert absent.json()["status"] == "absent"
        blocked_check_in = client.post(
            "/api/v1/attendance/check-in",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": absent_child.json()["id"],
                "facility_id": facility_id,
                "occurred_at": (service_now - timedelta(minutes=1)).isoformat(),
            },
        )
        assert blocked_check_in.status_code == 409
        corrected = client.put(
            f"/api/v1/attendance/{absent.json()['id']}/status-correction",
            headers=headers,
            json={
                "status": "present",
                "reason": "Guardian corrected the mistaken absence",
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["absence_reason"] is None
        assert [event["event_type"] for event in corrected.json()["events"]] == [
            "absence",
            "status_correction",
        ]

        stats = client.get("/api/v1/families/stats", headers=headers)
        assert stats.status_code == 200
        assert stats.json()["families"] == 1
        assert stats.json()["children"] == 2

        settings = client.patch(
            "/api/v1/settings",
            headers=headers,
            json={"preferences": {"week_starts_on": "monday"}},
        )
        assert settings.status_code == 200
        assert settings.json()["preferences"]["week_starts_on"] == "monday"


def test_basic_tenant_ids_fail_closed(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        first = _register(client, "one@example.com", "Tenant One")
        second = _register(client, "two@example.com", "Tenant Two")
        first_headers = _headers(first)
        second_headers = _headers(second)

        first_family = client.post(
            "/api/v1/families",
            headers=first_headers,
            json={"client_operation_id": str(uuid4()), "name": "Private One"},
        )
        assert first_family.status_code == 201

        assert (
            client.get(
                f"/api/v1/families/{first_family.json()['id']}",
                headers=second_headers,
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/v1/families/{first_family.json()['id']}",
                headers=second_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_version": first_family.json()["version"],
                    "name": "Stolen",
                },
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/children",
                headers=second_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "family_id": first_family.json()["id"],
                    "first_name": "Wrong",
                    "last_name": "Tenant",
                    "date_of_birth": "2024-01-01",
                },
            ).status_code
            == 404
        )

        forged_context = _headers(first, second["user"]["organization_id"])
        assert client.get("/api/v1/organization", headers=forged_context).status_code == 403


def test_non_owner_cannot_mutate_organization(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "owner@example.com", "Owner Tenant")
        organization_id = UUID(owner["user"]["organization_id"])
        member_id = uuid4()
        with application.state.database.session_factory() as session:
            role = Role(
                id=uuid4(),
                organization_id=organization_id,
                key="viewer",
                name="Viewer",
                permissions=[],
            )
            member = User(
                id=member_id,
                email="member@example.com",
                password_hash=hash_password("correct-password"),
                first_name="Read",
                last_name="Only",
            )
            apply_temporary_email_approval(member)
            session.add_all([role, member])
            session.flush()
            session.add(
                OrganizationMembership(
                    id=uuid4(),
                    organization_id=organization_id,
                    user_id=member_id,
                    role_id=role.id,
                    status="active",
                    joined_at=datetime.now(UTC),
                )
            )
            session.commit()

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "member@example.com", "password": "correct-password"},
        )
        assert login.status_code == 200
        response = client.patch(
            "/api/v1/organization",
            headers=_headers(login.json()),
            json={"name": "Unauthorized rename"},
        )
        assert response.status_code == 403
