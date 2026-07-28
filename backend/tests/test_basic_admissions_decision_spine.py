"""Focused SQLite acceptance coverage for the 0039 admissions lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api.basic import admissions_decisions as admissions_api
from app.basic.admissions_decision_schemas import AdmissionDetail
from app.basic.childcare_commands import record_command as record_childcare_command
from app.basic.models import (
    AdmissionApplication,
    AdmissionApplicationEvent,
    AdmissionConversionLink,
    AuditEvent,
    Child,
    ChildcareCommandReceipt,
    Enrollment,
    Family,
    Guardian,
    Organization,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    User,
    UserNotification,
)
from app.basic.security import create_access_token, hash_password
from tests.test_basic_room_placement import (
    _client,
    _facility_tree,
    _headers,
    _register,
)


def _intake(
    facility: dict,
    program: dict,
    *,
    operation_id=None,
    child_first_name: str = "Amina",
) -> dict:
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "child": {
            "first_name": child_first_name,
            "last_name": "Admission",
            "date_of_birth": "2023-05-04",
        },
        "primary_contact": {
            "first_name": "Private",
            "last_name": "Contact",
            "relationship": "Parent",
            "email": "private-admission@example.test",
            "telephone": "780-555-0199",
        },
        "preferences": [
            {
                "rank": 1,
                "facility_id": facility["id"],
                "program_id": program["id"],
                "desired_start_date": "2026-09-01",
            }
        ],
        "internal_note": "PRIVATE ADMISSION NOTE",
    }


def _post(client, path: str, headers: dict, payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _version_command(version: int, **extra) -> dict:
    return {
        "client_operation_id": str(uuid4()),
        "expected_application_version": version,
        **extra,
    }


def _offered_application(
    client,
    headers: dict,
    facility: dict,
    program: dict,
    *,
    intake: dict | None = None,
) -> dict:
    created = _post(
        client,
        "/api/v1/admissions/applications",
        headers,
        intake or _intake(facility, program),
    )
    submitted = _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/submit",
        headers,
        _version_command(created["version"]),
    )
    reviewed = _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/review/start",
        headers,
        _version_command(submitted["version"]),
    )
    return _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/offers",
        headers,
        _version_command(
            reviewed["version"],
            facility_id=facility["id"],
            program_id=program["id"],
            proposed_start_date="2026-09-01",
            respond_by_date=None,
        ),
    )


def _canonical_family(
    client,
    headers: dict,
    *,
    name: str = "Reviewed Family",
) -> dict:
    return _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": name,
            "status": "active",
            "consents": {
                "photo_consent": False,
                "field_trip_consent": False,
                "emergency_medical_consent": False,
            },
            "primary_guardian": {
                "first_name": "Private",
                "last_name": "Contact",
                "relationship": "Parent",
                "email": "private-admission@example.test",
                "cell_phone": "780-555-0199",
                "authorized_pickup": False,
            },
        },
    )


def _canonical_child(
    client,
    headers: dict,
    family_id: str,
    *,
    first_name: str = "Amina",
) -> dict:
    return _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family_id,
            "first_name": first_name,
            "last_name": "Admission",
            "date_of_birth": "2023-05-04",
            "is_active": True,
        },
    )


def _conversion_review(client, headers: dict, application_id: str) -> dict:
    response = client.get(
        f"/api/v1/admissions/applications/{application_id}/conversion-candidates",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _accept_payload(offered: dict, review: dict, **extra) -> dict:
    return {
        "client_operation_id": str(uuid4()),
        "expected_application_version": offered["version"],
        "expected_offer_version": offered["offer"]["version"],
        "review_token": review["review_token"],
        "resolution_mode": "create_family_and_child",
        **extra,
    }


def _accept_offer(
    client,
    headers: dict,
    offered: dict,
    review: dict,
    **extra,
) -> dict:
    return _post(
        client,
        (
            f"/api/v1/admissions/applications/{offered['id']}/offers/"
            f"{offered['offer']['id']}/accept-and-convert"
        ),
        headers,
        _accept_payload(offered, review, **extra),
    )


def _custom_headers(
    application,
    organization_id: str,
    *,
    marker: str,
    permissions: list[str],
) -> dict[str, str]:
    with application.state.database.session_factory() as session:
        user = User(
            id=uuid4(),
            email=f"{marker}@example.test",
            password_hash=hash_password("secure-password-123"),
            first_name="Custom",
            last_name="Admission",
            email_verified_at=datetime.now(UTC),
            email_verification_method="test",
        )
        role = Role(
            id=uuid4(),
            organization_id=UUID(organization_id),
            key=f"admission_{marker}",
            name=f"Admission {marker}",
            permissions=permissions,
            is_system=False,
        )
        session.add_all([user, role])
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=UUID(organization_id),
                user_id=user.id,
                role_id=role.id,
                status="active",
                joined_at=datetime.now(UTC),
            )
        )
        session.commit()
        token = create_access_token(user, application.state.settings)
    return {"Authorization": f"Bearer {token}"}


def test_exact_retry_privacy_and_waitlist_offer_lifecycle(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client, "admission-spine@example.test", "Admission Spine Centre"
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        operation_id = uuid4()
        create_payload = _intake(
            facility, program, operation_id=operation_id
        )

        created_response = client.post(
            "/api/v1/admissions/applications",
            headers=headers,
            json=create_payload,
        )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        assert AdmissionDetail.model_validate(created)
        assert created["status"] == "draft"
        assert created["replayed"] is False
        assert created["preferences"][0]["requested_start_date"] == "2026-09-01"

        replay_response = client.post(
            "/api/v1/admissions/applications",
            headers=headers,
            json=create_payload,
        )
        assert replay_response.status_code == 200, replay_response.text
        assert replay_response.json()["id"] == created["id"]
        assert replay_response.json()["replayed"] is True

        changed = {
            **create_payload,
            "child": {**create_payload["child"], "first_name": "Changed"},
        }
        rejected = client.post(
            "/api/v1/admissions/applications",
            headers=headers,
            json=changed,
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "operation_reused"

        directory = client.get(
            "/api/v1/admissions/applications", headers=headers
        )
        assert directory.status_code == 200, directory.text
        item = directory.json()["items"][0]
        assert set(item) == {
            "id",
            "reference",
            "status",
            "version",
            "source",
            "preference_count",
            "submitted_at",
            "updated_at",
            "current_lane",
            "offer_status",
        }
        serialized = json.dumps(directory.json())
        assert "PRIVATE ADMISSION NOTE" not in serialized
        assert "private-admission@example.test" not in serialized
        assert "780-555-0199" not in serialized
        assert "Amina" not in serialized
        assert "2023-05-04" not in serialized

        application_id = created["id"]
        invalid_reason = client.post(
            f"/api/v1/admissions/applications/{application_id}/submit",
            headers=headers,
            json=_version_command(1, reason_code="contains spaces"),
        )
        assert invalid_reason.status_code == 422
        submitted_response = client.post(
            f"/api/v1/admissions/applications/{application_id}/submit",
            headers=headers,
            json=_version_command(1, reason_code="intake_complete"),
        )
        assert submitted_response.status_code == 200, submitted_response.text
        assert submitted_response.headers["cache-control"] == "private, no-store"
        submitted = submitted_response.json()
        stale_application = client.post(
            f"/api/v1/admissions/applications/{application_id}/review/start",
            headers=headers,
            json=_version_command(1),
        )
        assert stale_application.status_code == 409
        assert stale_application.json()["detail"] == {
            "code": "admission_version_conflict",
            "message": (
                "The admission application changed. Reload before retrying."
            ),
            "record_kind": "application",
            "record_id": application_id,
            "expected_version": 1,
            "current_version": submitted["version"],
        }
        invalid_transition = client.post(
            f"/api/v1/admissions/applications/{application_id}/submit",
            headers=headers,
            json=_version_command(submitted["version"]),
        )
        assert invalid_transition.status_code == 409
        assert invalid_transition.json()["detail"]["code"] == (
            "admission_transition_invalid"
        )
        reviewed = _post(
            client,
            f"/api/v1/admissions/applications/{application_id}/review/start",
            headers,
            _version_command(submitted["version"]),
        )
        waitlisted = _post(
            client,
            f"/api/v1/admissions/applications/{application_id}/waitlist",
            headers,
            _version_command(
                reviewed["version"],
                facility_id=facility["id"],
                program_id=program["id"],
                desired_start_date="2026-09-01",
            ),
        )
        first_priority = waitlisted["waitlist"]["priority_at"]
        stale_waitlist = client.post(
            (
                f"/api/v1/admissions/applications/{application_id}/"
                "waitlist/reopen-review"
            ),
            headers=headers,
            json=_version_command(
                waitlisted["version"],
                expected_waitlist_version=999,
            ),
        )
        assert stale_waitlist.status_code == 409
        assert stale_waitlist.json()["detail"]["code"] == (
            "admission_version_conflict"
        )
        assert stale_waitlist.json()["detail"]["record_kind"] == "waitlist"
        offered = _post(
            client,
            f"/api/v1/admissions/applications/{application_id}/offers",
            headers,
            _version_command(
                waitlisted["version"],
                expected_waitlist_version=waitlisted["waitlist"]["version"],
                facility_id=facility["id"],
                program_id=program["id"],
                proposed_start_date="2026-09-01",
                respond_by_date="2026-08-15",
            ),
        )
        stale_offer = client.post(
            (
                f"/api/v1/admissions/applications/{application_id}/offers/"
                f"{offered['offer']['id']}/withdraw"
            ),
            headers=headers,
            json=_version_command(
                offered["version"],
                expected_offer_version=999,
            ),
        )
        assert stale_offer.status_code == 409
        assert stale_offer.json()["detail"]["code"] == (
            "admission_version_conflict"
        )
        assert stale_offer.json()["detail"]["record_kind"] == "offer"
        withdrawn = _post(
            client,
            (
                f"/api/v1/admissions/applications/{application_id}/offers/"
                f"{offered['offer']['id']}/withdraw"
            ),
            headers,
            _version_command(
                offered["version"],
                expected_offer_version=offered["offer"]["version"],
            ),
        )
        assert withdrawn["status"] == "waitlisted"
        assert withdrawn["waitlist"]["status"] == "active"
        assert datetime.fromisoformat(
            withdrawn["waitlist"]["priority_at"].replace("Z", "+00:00")
        ).replace(tzinfo=None) == datetime.fromisoformat(
            first_priority.replace("Z", "+00:00")
        ).replace(tzinfo=None)

        second_offer = _post(
            client,
            f"/api/v1/admissions/applications/{application_id}/offers",
            headers,
            _version_command(
                withdrawn["version"],
                expected_waitlist_version=withdrawn["waitlist"]["version"],
                facility_id=facility["id"],
                program_id=program["id"],
                proposed_start_date="2026-09-01",
                respond_by_date=None,
            ),
        )
        declined = _post(
            client,
            (
                f"/api/v1/admissions/applications/{application_id}/offers/"
                f"{second_offer['offer']['id']}/decline"
            ),
            headers,
            _version_command(
                second_offer["version"],
                expected_offer_version=second_offer["offer"]["version"],
            ),
        )
        assert declined["status"] == "declined"
        assert declined["waitlist"]["status"] == "closed"
        assert declined["waitlist"]["position"] is None
        assert declined["allowed_actions"] == []
        assert [event["application_version"] for event in declined["timeline"]] == list(
            range(1, declined["version"] + 1)
        )

        waitlist_page = client.get(
            "/api/v1/admissions/waitlist", headers=headers
        )
        assert waitlist_page.status_code == 200
        assert waitlist_page.json()["items"] == []

        workspace = client.get(
            "/api/v1/admissions/workspace", headers=headers
        )
        assert workspace.status_code == 200
        assert set(workspace.json()) == {
            "counts",
            "lanes",
            "waitlist_lane_count",
        }
        assert workspace.json()["counts"]["declined"] == 1

        with application.state.database.session_factory() as session:
            assert session.query(AdmissionApplicationEvent).count() == declined[
                "version"
            ]
            assert session.query(ChildcareCommandReceipt).count() == declined[
                "version"
            ]
            assert session.query(RealtimeEvent).filter(
                RealtimeEvent.entity_type.in_(
                    (
                        "admission_application",
                        "admission_waitlist",
                        "admission_offer",
                    )
                )
            ).count() == declined["version"]
            assert session.query(UserNotification).count() == 1
            notification = session.query(UserNotification).one()
            assert notification.action_path == (
                f"/admissions/applications/{application_id}"
            )
            assert notification.action_entity_type == "admission_application"
            assert str(notification.action_entity_id) == application_id
            submit_audit = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.action == "admission.application.submit",
                    AuditEvent.entity_id == UUID(application_id),
                )
                .one()
            )
            assert submit_audit.details["operator_reason_code"] == (
                "intake_complete"
            )


def test_correction_closes_waitlist_and_offer_converts_atomically(
    tmp_path,
) -> None:
    client, _application = _client(tmp_path)
    with client:
        owner = _register(
            client, "admission-correct@example.test", "Correction Centre"
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        created = _post(
            client,
            "/api/v1/admissions/applications",
            headers,
            _intake(facility, program),
        )
        submitted = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/submit",
            headers,
            _version_command(created["version"]),
        )
        reviewed = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/review/start",
            headers,
            _version_command(submitted["version"]),
        )
        waitlisted = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/waitlist",
            headers,
            _version_command(
                reviewed["version"],
                facility_id=facility["id"],
                program_id=program["id"],
                desired_start_date="2026-09-01",
            ),
        )
        correction = _intake(
            facility, program, child_first_name="Corrected"
        )
        correction["expected_application_version"] = waitlisted["version"]
        corrected = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/correct",
            headers,
            correction,
        )
        assert corrected["status"] == "under_review"
        assert corrected["child"]["first_name"] == "Corrected"
        assert corrected["waitlist"]["status"] == "closed"
        assert corrected["waitlist"]["closure_reason"] == "facts_changed"

        offered = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/offers",
            headers,
            _version_command(
                corrected["version"],
                facility_id=facility["id"],
                program_id=program["id"],
                proposed_start_date="2026-09-01",
                respond_by_date=None,
            ),
        )
        blocked_correction = {
            **_intake(facility, program),
            "expected_application_version": offered["version"],
        }
        blocked = client.post(
            f"/api/v1/admissions/applications/{created['id']}/correct",
            headers=headers,
            json=blocked_correction,
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == (
            "admission_offer_withdrawal_required"
        )

        candidate_review = client.get(
            (
                f"/api/v1/admissions/applications/{created['id']}/"
                "conversion-candidates"
            ),
            headers=headers,
        )
        assert candidate_review.status_code == 200, candidate_review.text
        review = candidate_review.json()
        assert review["families"] == []
        assert review["children"] == []
        converted = _post(
            client,
            (
                f"/api/v1/admissions/applications/{created['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_application_version": offered["version"],
                "expected_offer_version": offered["offer"]["version"],
                "review_token": review["review_token"],
                "resolution_mode": "create_family_and_child",
            },
        )
        assert converted["status"] == "accepted"
        assert converted["offer"]["status"] == "accepted"
        assert converted["conversion"]["resolution_mode"] == (
            "create_family_and_child"
        )
        assert converted["conversion"]["family_id"]
        assert converted["conversion"]["child_id"]
        assert converted["conversion"]["enrollment_id"]


def test_tenant_and_custom_permission_separation(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        first_owner = _register(
            client, "admission-first@example.test", "First Admission Centre"
        )
        owner_headers = _headers(first_owner)
        facility, program, _, _ = _facility_tree(client, owner_headers)
        optional_contact_payload = _intake(facility, program)
        optional_contact_payload["primary_contact"].pop("email")
        optional_contact_payload["primary_contact"].pop("telephone")

        extra_field = client.post(
            "/api/v1/admissions/applications",
            headers=owner_headers,
            json={**optional_contact_payload, "unexpected": True},
        )
        assert extra_field.status_code == 422

        created = _post(
            client,
            "/api/v1/admissions/applications",
            owner_headers,
            optional_contact_payload,
        )
        assert created["contact"]["email"] is None
        assert created["contact"]["telephone"] is None

        second_owner = _register(
            client, "admission-second@example.test", "Second Admission Centre"
        )
        cross_tenant = client.get(
            f"/api/v1/admissions/applications/{created['id']}",
            headers=_headers(second_owner),
        )
        assert cross_tenant.status_code == 404

        organization_id = first_owner["user"]["organization_id"]
        read_headers = _custom_headers(
            application,
            organization_id,
            marker="read-only",
            permissions=["admissions:read"],
        )
        manage_headers = _custom_headers(
            application,
            organization_id,
            marker="manage-only",
            permissions=["admissions:manage"],
        )
        decide_headers = _custom_headers(
            application,
            organization_id,
            marker="decide",
            permissions=["admissions:read", "admissions:decide"],
        )

        readable = client.get(
            f"/api/v1/admissions/applications/{created['id']}",
            headers=read_headers,
        )
        assert readable.status_code == 200, readable.text
        forbidden_create = client.post(
            "/api/v1/admissions/applications",
            headers=read_headers,
            json=_intake(facility, program),
        )
        assert forbidden_create.status_code == 403
        managed_create = client.post(
            "/api/v1/admissions/applications",
            headers=manage_headers,
            json=_intake(facility, program, child_first_name="Managed"),
        )
        assert managed_create.status_code == 201, managed_create.text

        submitted = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/submit",
            owner_headers,
            _version_command(created["version"]),
        )
        reviewed = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/review/start",
            owner_headers,
            _version_command(submitted["version"]),
        )
        correction = _intake(
            facility, program, child_first_name="Decided"
        )
        correction["expected_application_version"] = reviewed["version"]
        manage_correction = client.post(
            f"/api/v1/admissions/applications/{created['id']}/correct",
            headers=manage_headers,
            json=correction,
        )
        assert manage_correction.status_code == 403
        correction["client_operation_id"] = str(uuid4())
        decided_correction = client.post(
            f"/api/v1/admissions/applications/{created['id']}/correct",
            headers=decide_headers,
            json=correction,
        )
        assert decided_correction.status_code == 200, decided_correction.text
        assert decided_correction.json()["child"]["first_name"] == "Decided"


def test_x02_conversion_reuses_reviewed_family_and_creates_child(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x02@example.test",
            "Admission X02 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        family = _canonical_family(client, headers)
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        assert [candidate["id"] for candidate in review["families"]] == [
            family["id"]
        ]
        assert review["children"] == []

        converted = _accept_offer(
            client,
            headers,
            offered,
            review,
            resolution_mode="reuse_family_create_child",
            family_id=family["id"],
            expected_family_version=family["version"],
        )
        assert converted["conversion"]["resolution_mode"] == (
            "reuse_family_create_child"
        )
        assert converted["conversion"]["family_id"] == family["id"]
        with application.state.database.session_factory() as session:
            child = session.get(
                Child,
                UUID(converted["conversion"]["child_id"]),
            )
            assert child is not None
            assert str(child.family_id) == family["id"]


def test_x03_conversion_reuses_reviewed_child(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x03@example.test",
            "Admission X03 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        family = _canonical_family(client, headers)
        child = _canonical_child(client, headers, family["id"])
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        assert [candidate["id"] for candidate in review["children"]] == [
            child["id"]
        ]

        converted = _accept_offer(
            client,
            headers,
            offered,
            review,
            resolution_mode="reuse_child",
            family_id=family["id"],
            expected_family_version=family["version"],
            child_id=child["id"],
            expected_child_version=child["version"],
        )
        assert converted["conversion"]["resolution_mode"] == "reuse_child"
        assert converted["conversion"]["child_id"] == child["id"]
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Child)
                    .where(
                        Child.organization_id
                        == UUID(owner["user"]["organization_id"])
                    )
                )
                == 1
            )


def test_x04_changed_candidate_makes_review_stale_without_writes(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x04@example.test",
            "Admission X04 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        family = _canonical_family(client, headers)
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        with application.state.database.session_factory() as session:
            canonical_family = session.get(Family, UUID(family["id"]))
            assert canonical_family is not None
            canonical_family.version += 1
            session.commit()

        response = client.post(
            (
                f"/api/v1/admissions/applications/{offered['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers=headers,
            json=_accept_payload(
                offered,
                review,
                resolution_mode="reuse_family_create_child",
                family_id=family["id"],
                expected_family_version=family["version"],
            ),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "admission_review_stale"
        with application.state.database.session_factory() as session:
            assert session.query(AdmissionConversionLink).count() == 0
            assert session.query(Enrollment).count() == 0


def test_x05_create_new_requires_distinct_person_confirmation(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x05@example.test",
            "Admission X05 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        _canonical_family(client, headers)
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        assert review["families"]

        blocked = client.post(
            (
                f"/api/v1/admissions/applications/{offered['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers=headers,
            json=_accept_payload(offered, review),
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == (
            "admission_distinct_confirmation_required"
        )
        with application.state.database.session_factory() as session:
            assert session.query(AdmissionConversionLink).count() == 0

        converted = _accept_offer(
            client,
            headers,
            offered,
            review,
            confirmed_distinct_person=True,
            distinct_person_reason="Verified as a different household in person.",
        )
        assert converted["status"] == "accepted"


def test_x06_reused_child_with_open_enrollment_is_rejected(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x06@example.test",
            "Admission X06 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        family = _canonical_family(client, headers)
        child = _canonical_child(client, headers, family["id"])
        _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": "2026-01-01",
            },
        )
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        assert review["children"][0]["has_open_enrollment"] is True
        response = client.post(
            (
                f"/api/v1/admissions/applications/{offered['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers=headers,
            json=_accept_payload(
                offered,
                review,
                resolution_mode="reuse_child",
                family_id=family["id"],
                expected_family_version=family["version"],
                child_id=child["id"],
                expected_child_version=child["version"],
            ),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "open_enrollment_exists"
        with application.state.database.session_factory() as session:
            assert session.query(AdmissionConversionLink).count() == 0


def test_x07_second_acceptance_has_one_canonical_winner(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x07@example.test",
            "Admission X07 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        first = _accept_payload(offered, review)
        accepted = _post(
            client,
            (
                f"/api/v1/admissions/applications/{offered['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers,
            first,
        )
        second = client.post(
            (
                f"/api/v1/admissions/applications/{offered['id']}/offers/"
                f"{offered['offer']['id']}/accept-and-convert"
            ),
            headers=headers,
            json={**first, "client_operation_id": str(uuid4())},
        )
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "admission_already_converted"
        with application.state.database.session_factory() as session:
            assert session.query(AdmissionConversionLink).count() == 1
            assert (
                session.query(Enrollment)
                .filter(
                    Enrollment.id
                    == UUID(accepted["conversion"]["enrollment_id"])
                )
                .count()
                == 1
            )


def test_x08_nested_failure_rolls_back_every_conversion_write(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-x08@example.test",
            "Admission X08 Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        offered = _offered_application(client, headers, facility, program)
        review = _conversion_review(client, headers, offered["id"])
        with application.state.database.session_factory() as session:
            before = {
                "families": session.query(Family).count(),
                "children": session.query(Child).count(),
                "enrollments": session.query(Enrollment).count(),
                "receipts": session.query(ChildcareCommandReceipt).count(),
            }

        def fail_after_child_receipt(*args, **kwargs):
            receipt = record_childcare_command(*args, **kwargs)
            if kwargs.get("command_type") == "child.create":
                raise RuntimeError("injected failure after nested child")
            return receipt

        monkeypatch.setattr(
            admissions_api,
            "record_command",
            fail_after_child_receipt,
        )
        with pytest.raises(
            RuntimeError,
            match="injected failure after nested child",
        ):
            client.post(
                (
                    f"/api/v1/admissions/applications/{offered['id']}/offers/"
                    f"{offered['offer']['id']}/accept-and-convert"
                ),
                headers=headers,
                json=_accept_payload(offered, review),
            )

        with application.state.database.session_factory() as session:
            after = {
                "families": session.query(Family).count(),
                "children": session.query(Child).count(),
                "enrollments": session.query(Enrollment).count(),
                "receipts": session.query(ChildcareCommandReceipt).count(),
            }
            assert after == before
            assert session.query(AdmissionConversionLink).count() == 0
        detail = client.get(
            f"/api/v1/admissions/applications/{offered['id']}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "offered"


def test_actor_private_receipt_and_delayed_replay_keep_historical_commit(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-receipt@example.test",
            "Admission Receipt Centre",
        )
        owner_headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, owner_headers)
        organization_id = owner["user"]["organization_id"]
        admissions_only = _custom_headers(
            application,
            organization_id,
            marker="receipt-only",
            permissions=["admissions:manage", "admissions:decide"],
        )
        created = _post(
            client,
            "/api/v1/admissions/applications",
            admissions_only,
            _intake(facility, program),
        )
        submit_operation = uuid4()
        submit_payload = {
            "client_operation_id": str(submit_operation),
            "expected_application_version": created["version"],
        }
        submitted = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/submit",
            admissions_only,
            submit_payload,
        )
        submitted_version = submitted["version"]
        reviewed = _post(
            client,
            f"/api/v1/admissions/applications/{created['id']}/review/start",
            admissions_only,
            _version_command(submitted_version),
        )

        receipt_response = client.get(
            f"/api/v1/childcare-commands/{submit_operation}",
            headers=admissions_only,
        )
        assert receipt_response.status_code == 200, receipt_response.text
        receipt = receipt_response.json()
        assert receipt["command_type"] == "admission.application.submit"
        assert receipt["target_type"] == "admission_application"
        assert receipt["target_id"] == created["id"]
        assert receipt["committed_version"] == submitted_version
        assert receipt["action_route"] == (
            f"/admissions/applications/{created['id']}"
        )

        delayed_replay = client.post(
            f"/api/v1/admissions/applications/{created['id']}/submit",
            headers=admissions_only,
            json=submit_payload,
        )
        assert delayed_replay.status_code == 200, delayed_replay.text
        replayed = delayed_replay.json()
        assert replayed["replayed"] is True
        assert replayed["status"] == "under_review"
        assert replayed["version"] == reviewed["version"]
        assert replayed["replay_receipt"] == {
            "command_type": "admission.application.submit",
            "target_type": "admission_application",
            "target_id": created["id"],
            "committed_version": submitted_version,
        }
        assert replayed["replay_receipt"]["committed_version"] < replayed["version"]


def test_lane_directory_and_reference_search_are_strict_non_pii(
    tmp_path,
) -> None:
    client, _application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-directory@example.test",
            "Admission Directory Centre",
        )
        headers = _headers(owner)
        facility, program, room, _ = _facility_tree(client, headers)
        created = _post(
            client,
            "/api/v1/admissions/applications",
            headers,
            _intake(facility, program),
        )

        lane_response = client.get(
            "/api/v1/admissions/lane-directory",
            headers=headers,
        )
        assert lane_response.status_code == 200, lane_response.text
        lane_payload = lane_response.json()
        assert lane_payload == {
            "facilities": [
                {
                    "id": facility["id"],
                    "name": facility["name"],
                    "programs": [
                        {
                            "id": program["id"],
                            "name": program["name"],
                            "program_type": program["program_type"],
                        }
                    ],
                }
            ]
        }
        serialized = json.dumps(lane_payload)
        assert room["name"] not in serialized
        assert "room" not in serialized.casefold()
        assert "Amina" not in serialized
        assert "private-admission@example.test" not in serialized

        suffix = created["reference"].split("-", maxsplit=1)[1][-6:]
        search_response = client.get(
            "/api/v1/admissions/applications",
            headers=headers,
            params={"search": suffix.lower()},
        )
        assert search_response.status_code == 200, search_response.text
        assert [item["id"] for item in search_response.json()["items"]] == [
            created["id"]
        ]
        wildcard = client.get(
            "/api/v1/admissions/applications",
            headers=headers,
            params={"search": "*"},
        )
        assert wildcard.status_code == 422


def test_conversion_review_token_is_bounded_at_candidate_limit(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-token-limit@example.test",
            "Admission Token Limit Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        offered = _offered_application(client, headers, facility, program)
        organization_id = UUID(owner["user"]["organization_id"])

        with application.state.database.session_factory() as session:
            family_ids: list[UUID] = []
            for index in range(50):
                family_id = uuid4()
                family_ids.append(family_id)
                session.add(
                    Family(
                        id=family_id,
                        organization_id=organization_id,
                        name=f"Candidate Family {index:02d}",
                        status="active",
                        version=1,
                    )
                )
            session.flush()
            for index, family_id in enumerate(family_ids):
                session.add(
                    Guardian(
                        id=uuid4(),
                        organization_id=organization_id,
                        family_id=family_id,
                        first_name="Private",
                        last_name=f"Contact {index:02d}",
                        relationship="Parent",
                        email="private-admission@example.test",
                        cell_phone=f"780555{index:04d}",
                        is_primary=True,
                        authorized_pickup=False,
                    )
                )
                session.add(
                    Child(
                        id=uuid4(),
                        organization_id=organization_id,
                        family_id=family_id,
                        first_name="Amina",
                        last_name="Admission",
                        date_of_birth=date(2023, 5, 4),
                        age_group="Preschool",
                        is_active=True,
                        version=1,
                    )
                )
            session.commit()

        review = _conversion_review(client, headers, offered["id"])
        assert len(review["families"]) == 50
        assert len(review["children"]) == 50
        assert len(review["review_token"]) < 4096


def test_timeline_window_reports_total_and_latest_two_hundred(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-timeline@example.test",
            "Admission Timeline Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        created = _post(
            client,
            "/api/v1/admissions/applications",
            headers,
            _intake(facility, program),
        )
        application_id = UUID(created["id"])
        with application.state.database.session_factory() as session:
            admission = session.get(AdmissionApplication, application_id)
            assert admission is not None
            for version in range(2, 206):
                operation_id = uuid4()
                session.add(
                    AdmissionApplicationEvent(
                        id=uuid4(),
                        organization_id=admission.organization_id,
                        application_id=admission.id,
                        application_version=version,
                        command="admission.application.update",
                        from_status="draft",
                        to_status="draft",
                        reason_code="updated",
                        actor_user_id=admission.updated_by_user_id,
                        client_operation_id=operation_id,
                    )
                )
                admission.version = version
                admission.last_operation_id = operation_id
            session.commit()

        detail_response = client.get(
            f"/api/v1/admissions/applications/{created['id']}",
            headers=headers,
        )
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["timeline_total"] == 205
        assert len(detail["timeline"]) == 200
        assert detail["timeline"][0]["application_version"] == 6
        assert detail["timeline"][-1]["application_version"] == 205


def test_admission_date_validation_uses_organization_timezone(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            "admission-timezone@example.test",
            "Admission Timezone Centre",
        )
        headers = _headers(owner)
        facility, program, _, _ = _facility_tree(client, headers)
        with application.state.database.session_factory() as session:
            organization = session.get(
                Organization,
                UUID(owner["user"]["organization_id"]),
            )
            assert organization is not None
            organization.timezone = "Not/A-Timezone"
            session.commit()

        response = client.post(
            "/api/v1/admissions/applications",
            headers=headers,
            json=_intake(facility, program),
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Timezone must be corrected before changing child records"
        )
