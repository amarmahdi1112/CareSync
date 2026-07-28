"""Acceptance coverage for the derived, read-only admissions intake queue."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.api.basic.admissions import _placement_conflicts
from app.basic.admissions_schemas import AdmissionIntakeAction, AdmissionIntakeQueueResponse
from app.basic.models import Child, Enrollment, Facility, Family, Program, Room
from tests.test_basic_room_placement import (
    _client,
    _educator_headers,
    _facility_tree,
    _headers,
    _post,
    _register,
)


def _family(client, headers, name: str, *, status: str = "active", contacts: bool = True) -> dict:
    payload = {
        "client_operation_id": str(uuid4()),
        "name": name,
        "status": status,
        "additional_notes": "PRIVATE INTAKE NOTE MUST NOT LEAK",
    }
    if contacts:
        payload.update(
            {
                "primary_guardian": {
                    "first_name": "Private",
                    "last_name": "Guardian",
                    "email": "private-guardian@example.test",
                    "cell_phone": "780-555-0199",
                },
                "emergency_contacts": [
                    {
                        "first_name": "Private",
                        "last_name": "Emergency",
                        "relationship": "Aunt",
                        "cell_phone": "780-555-0188",
                    }
                ],
            }
        )
    return _post(client, "/api/v1/families", headers, payload)


def _child(client, headers, family_id: str, first_name: str) -> dict:
    return _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family_id,
            "first_name": first_name,
            "last_name": "Intake",
            "date_of_birth": "2025-01-15",
            "health_care_number": "PRIVATE-HEALTH-123",
            "allergies": "PRIVATE ALLERGY",
        },
    )


def _enrollment(client, headers, child_id: str, facility_id: str) -> dict:
    return _post(
        client,
        f"/api/v1/children/{child_id}/enrollments",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "facility_id": facility_id,
            "start_date": "2025-01-15",
        },
    )


def _set_family_status(application, family: dict, status: str) -> None:
    """Reproduce a retained legacy lifecycle combination commands now block."""

    with application.state.database.session_factory() as session:
        record = session.get(Family, UUID(family["id"]))
        assert record is not None
        record.status = status
        record.version += 1
        session.commit()


def _set_child_active(application, child: dict, is_active: bool) -> None:
    with application.state.database.session_factory() as session:
        record = session.get(Child, UUID(child["id"]))
        assert record is not None
        record.is_active = is_active
        record.version += 1
        session.commit()


def test_queue_derives_each_gate_without_claiming_admission_or_waitlist(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "admissions-owner@example.com", "Admissions Centre")
        headers = _headers(owner)
        facility, _, north, _ = _facility_tree(client, headers)

        contact_family = _family(
            client,
            headers,
            "Contact Attention Family",
            status="pending",
            contacts=False,
        )
        child_family = _family(
            client,
            headers,
            "Child Record Family",
            status="pending",
        )
        setup_family = _family(client, headers, "Enrollment Setup Family")
        _child(client, headers, setup_family["id"], "Setup")

        placement_family = _family(client, headers, "Placement Review Family")
        placement_child = _child(client, headers, placement_family["id"], "Placement")
        placement_enrollment = _enrollment(
            client,
            headers,
            placement_child["id"],
            facility["id"],
        )

        review_family = _family(client, headers, "Manual Review Family")
        review_child = _child(client, headers, review_family["id"], "Manual")
        _set_child_active(application, review_child, False)
        _set_family_status(application, review_family, "pending")

        conflict_family = _family(client, headers, "Conflict Family")
        conflict_child = _child(client, headers, conflict_family["id"], "Conflict")
        _enrollment(client, headers, conflict_child["id"], facility["id"])
        with application.state.database.session_factory() as session:
            child = session.get(Child, UUID(conflict_child["id"]))
            assert child is not None
            child.is_active = False
            session.commit()

        coherent_family = _family(client, headers, "Coherent Family")
        coherent_child = _child(client, headers, coherent_family["id"], "Coherent")
        coherent_enrollment = _enrollment(
            client,
            headers,
            coherent_child["id"],
            facility["id"],
        )
        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        coherent_review = next(
            value for value in reviews.json() if value["enrollment_id"] == coherent_enrollment["id"]
        )
        approved = client.post(
            f"/api/v1/enrollments/{coherent_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": coherent_enrollment["version"],
                "room_id": north["id"],
                "effective_date": coherent_review["effective_date"],
            },
        )
        assert approved.status_code == 200, approved.text

        response = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        payload = response.json()
        assert AdmissionIntakeQueueResponse.model_validate(payload)
        assert payload["projection_kind"] == "derived_current_intake_queue"
        assert payload["read_only"] is True
        assert payload["waitlist_supported"] is False
        assert payload["compliance_certified"] is False
        assert "not a waitlist" in payload["notice"]
        assert "certification" in payload["notice"]

        cases = {item["family_id"]: item for item in payload["items"]}
        assert cases[contact_family["id"]]["stage"] == "family_contacts"
        assert cases[child_family["id"]]["stage"] == "child_record"
        assert cases[setup_family["id"]]["stage"] == "enrollment_setup"
        assert cases[placement_family["id"]]["stage"] == "placement_review"
        assert cases[review_family["id"]]["stage"] == "family_review"
        assert cases[conflict_family["id"]]["stage"] == "record_conflict"
        assert coherent_family["id"] not in cases

        contact_codes = {reason["code"] for reason in cases[contact_family["id"]]["reasons"]}
        assert {
            "missing_primary_guardian",
            "unreachable_guardian_telephone",
            "missing_emergency_contact",
        }.issubset(contact_codes)
        assert cases[contact_family["id"]]["severity"] == "warning"
        assert (
            cases[conflict_family["id"]]["reasons"][0]["code"] == "inactive_child_open_enrollment"
        )
        assert cases[conflict_family["id"]]["severity"] == "critical"
        assert cases[placement_family["id"]]["primary_action"]["path"] == (
            f"/rooms?facility_id={facility['id']}"
            f"&placement_enrollment_id={placement_enrollment['id']}"
        )
        assert cases[review_family["id"]]["primary_action"]["path"] == (
            f"/families/{review_family['id']}?focus=family-status"
        )
        assert "date_of_birth" not in cases[setup_family["id"]]["children"][0]

        assert payload["total"] == 6
        assert payload["counts"] == {
            "total": 6,
            "critical": 1,
            "warning": 5,
            "by_stage": {
                "family_contacts": 1,
                "child_record": 1,
                "enrollment_setup": 1,
                "record_conflict": 1,
                "family_review": 1,
                "placement_review": 1,
            },
        }

        serialized = json.dumps(payload)
        for private_value in (
            "PRIVATE INTAKE NOTE MUST NOT LEAK",
            "private-guardian@example.test",
            "780-555-0199",
            "780-555-0188",
            "PRIVATE-HEALTH-123",
            "PRIVATE ALLERGY",
        ):
            assert private_value not in serialized


def test_pending_family_truth_never_leads_to_enrollment_creation(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "pending-truth@example.com", "Pending Truth Centre")
        headers = _headers(owner)
        facility, _, room, _ = _facility_tree(client, headers)

        no_child = _family(client, headers, "No Child Pending", status="pending")

        manual = _family(client, headers, "Manual Pending")
        manual_child = _child(client, headers, manual["id"], "Manual")
        _set_child_active(application, manual_child, False)
        _set_family_status(application, manual, "pending")

        active_child = _family(client, headers, "Active Child Pending")
        _child(client, headers, active_child["id"], "Active")
        _set_family_status(application, active_child, "pending")

        active_open = _family(client, headers, "Active Open Pending")
        active_open_child = _child(client, headers, active_open["id"], "Open")
        _enrollment(client, headers, active_open_child["id"], facility["id"])
        _set_family_status(application, active_open, "pending")

        inactive_open = _family(client, headers, "Inactive Open Pending")
        inactive_open_child = _child(client, headers, inactive_open["id"], "Inactive")
        _enrollment(client, headers, inactive_open_child["id"], facility["id"])
        _set_child_active(application, inactive_open_child, False)
        _set_family_status(application, inactive_open, "pending")

        assigned_open = _family(client, headers, "Assigned Open Pending")
        assigned_open_child = _child(client, headers, assigned_open["id"], "Assigned")
        assigned_enrollment = _enrollment(
            client,
            headers,
            assigned_open_child["id"],
            facility["id"],
        )
        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        assigned_review = next(
            value for value in reviews.json() if value["enrollment_id"] == assigned_enrollment["id"]
        )
        approval = client.post(
            f"/api/v1/enrollments/{assigned_enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": assigned_enrollment["version"],
                "room_id": room["id"],
                "effective_date": assigned_review["effective_date"],
            },
        )
        assert approval.status_code == 200, approval.text
        _set_family_status(application, assigned_open, "pending")

        response = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert response.status_code == 200, response.text
        cases = {item["family_id"]: item for item in response.json()["items"]}

        assert cases[no_child["id"]]["stage"] == "child_record"
        assert {reason["code"] for reason in cases[no_child["id"]]["reasons"]} >= {
            "no_child_record",
            "family_pending_manual_review",
        }

        assert cases[manual["id"]]["stage"] == "family_review"
        assert [reason["code"] for reason in cases[manual["id"]]["reasons"]] == [
            "family_pending_manual_review"
        ]

        active_child_case = cases[active_child["id"]]
        assert active_child_case["stage"] == "record_conflict"
        assert active_child_case["severity"] == "critical"
        assert active_child_case["reasons"][0]["code"] == "pending_family_active_child"
        assert active_child_case["reasons"][0]["title"].startswith("Active Intake ")
        assert active_child_case["primary_action"]["path"] == (
            f"/families/{active_child['id']}?focus=family-status"
        )

        active_open_codes = {reason["code"] for reason in cases[active_open["id"]]["reasons"]}
        assert {
            "pending_family_active_child",
            "pending_family_open_enrollment",
        }.issubset(active_open_codes)
        assert any(
            reason["code"] == "pending_family_open_enrollment"
            and reason["title"].startswith("Open Intake ")
            for reason in cases[active_open["id"]]["reasons"]
        )
        assert cases[active_open["id"]]["stage"] == "record_conflict"

        inactive_open_case = cases[inactive_open["id"]]
        inactive_open_codes = {reason["code"] for reason in inactive_open_case["reasons"]}
        assert {
            "pending_family_open_enrollment",
            "inactive_child_open_enrollment",
        }.issubset(inactive_open_codes)
        assert "pending_family_active_child" not in inactive_open_codes
        assert inactive_open_case["stage"] == "record_conflict"

        assigned_open_case = cases[assigned_open["id"]]
        assert assigned_open_case["stage"] == "record_conflict"
        assert assigned_open_case["enrollments"][0]["status"] == "active"
        assert {
            "pending_family_active_child",
            "pending_family_open_enrollment",
        }.issubset({reason["code"] for reason in assigned_open_case["reasons"]})

        for family_id in (
            no_child["id"],
            manual["id"],
            active_child["id"],
            active_open["id"],
            inactive_open["id"],
            assigned_open["id"],
        ):
            codes = {reason["code"] for reason in cases[family_id]["reasons"]}
            assert "no_open_enrollment_record" not in codes
            assert not any(
                reason["action"]["path"].startswith("/rooms?")
                for reason in cases[family_id]["reasons"]
            )
        assert "no_active_child_record" not in json.dumps(response.json())


def test_enrollment_setup_is_derived_for_each_active_sibling(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        owner = _register(client, "sibling-intake@example.com", "Sibling Intake Centre")
        headers = _headers(owner)
        facility, _, _, _ = _facility_tree(client, headers)
        family = _family(client, headers, "Sibling Family")
        placed = _child(client, headers, family["id"], "Has Shell")
        first_missing = _child(client, headers, family["id"], "First Missing")
        second_missing = _child(client, headers, family["id"], "Second Missing")
        enrollment = _enrollment(client, headers, placed["id"], facility["id"])

        response = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert response.status_code == 200, response.text
        case = next(item for item in response.json()["items"] if item["family_id"] == family["id"])
        assert case["stage"] == "enrollment_setup"
        missing_reasons = [
            reason for reason in case["reasons"] if reason["code"] == "no_open_enrollment_record"
        ]
        assert {reason["entity_id"] for reason in missing_reasons} == {
            first_missing["id"],
            second_missing["id"],
        }
        assert {reason["action"]["path"] for reason in missing_reasons} == {
            f"/children/{first_missing['id']}",
            f"/children/{second_missing['id']}",
        }
        placement_reason = next(
            reason
            for reason in case["reasons"]
            if reason["code"] == "pending_enrollment_placement_review"
        )
        assert placement_reason["entity_id"] == enrollment["id"]
        assert placement_reason["action"]["path"].startswith("/rooms?")


@pytest.mark.parametrize("family_status", ["inactive", "archived"])
def test_inactive_family_active_child_conflict_uses_plain_family_path(
    tmp_path,
    family_status: str,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(
            client,
            f"{family_status}-lifecycle@example.com",
            f"{family_status.title()} Lifecycle Centre",
        )
        headers = _headers(owner)
        family = _family(client, headers, f"{family_status.title()} Family")
        _child(client, headers, family["id"], "Active")
        _set_family_status(application, family, family_status)

        response = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert response.status_code == 200, response.text
        case = next(item for item in response.json()["items"] if item["family_id"] == family["id"])
        assert case["stage"] == "record_conflict"
        assert case["severity"] == "critical"
        lifecycle = next(
            reason for reason in case["reasons"] if reason["code"] == "family_lifecycle_conflict"
        )
        assert lifecycle["action"]["path"] == f"/families/{family['id']}"
        assert "focus=" not in lifecycle["action"]["path"]


def _assigned_facts(
    enrollment_status: str = "active",
) -> tuple[Family, Child, Enrollment, Facility, Program, Room, datetime]:
    organization_id = uuid4()
    family = Family(
        id=uuid4(),
        organization_id=organization_id,
        name="Assigned Facts Family",
        status=enrollment_status,
    )
    child = Child(
        id=uuid4(),
        organization_id=organization_id,
        family_id=family.id,
        first_name="Assigned",
        last_name="Child",
        date_of_birth=date(2025, 1, 15),
        is_active=True,
    )
    facility = Facility(
        id=uuid4(),
        organization_id=organization_id,
        name="Assigned Facility",
        status="active",
        timezone="America/Edmonton",
    )
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        facility_id=facility.id,
        name="Assigned Program",
        program_type="daycare",
        is_active=True,
    )
    room = Room(
        id=uuid4(),
        organization_id=organization_id,
        facility_id=facility.id,
        program_id=program.id,
        name="Assigned Room",
        capacity=20,
        minimum_age_months=0,
        maximum_age_months=60,
        is_active=True,
    )
    enrollment = Enrollment(
        id=uuid4(),
        organization_id=organization_id,
        child_id=child.id,
        facility_id=facility.id,
        program_id=program.id,
        room_id=room.id,
        placement_effective_date=date(2026, 7, 15),
        start_date=date(2025, 1, 15),
        end_date=None,
        status="active",
    )
    return (
        family,
        child,
        enrollment,
        facility,
        program,
        room,
        datetime(2026, 7, 21, 18, tzinfo=UTC),
    )


@pytest.mark.parametrize("enrollment_status", ["active", "paused"])
def test_assigned_conflicts_use_child_record_not_pending_placement_review(
    enrollment_status: str,
) -> None:
    conflict_results = []

    facts = _assigned_facts(enrollment_status)
    facts[4].is_active = False
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[5].is_active = False
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[2].start_date = date(2026, 7, 21)
    facts[2].placement_effective_date = date(2026, 7, 20)
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[5].minimum_age_months = None
    facts[5].maximum_age_months = None
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[5].maximum_age_months = 6
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[2].program_id = None
    facts[2].room_id = None
    facts[2].placement_effective_date = None
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[3].status = "inactive"
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    facts = _assigned_facts(enrollment_status)
    facts[2].end_date = date(2026, 7, 20)
    conflict_results.append((facts[1].id, _placement_conflicts(*facts)))

    expected_codes = {
        "program_unavailable",
        "room_unavailable",
        "placement_effective_date_conflict",
        "room_age_range_missing",
        "child_outside_room_age_range",
        "placement_incomplete",
        "facility_unavailable",
        "enrollment_date_conflict",
    }
    observed = {
        reason.code: (child_id, reason)
        for child_id, reasons in conflict_results
        for reason in reasons
    }
    assert expected_codes.issubset(observed)
    for code in expected_codes:
        child_id, reason = observed[code]
        assert reason.action.path == f"/children/{child_id}"
        assert "/rooms?" not in reason.action.path
        assert "placement review" not in reason.instruction.lower()


def test_joined_placement_fact_update_advances_case_updated_at(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "updated-at@example.com", "Updated At Centre")
        headers = _headers(owner)
        facility, _, room, _ = _facility_tree(client, headers)
        family = _family(client, headers, "Placement Timestamp Family")
        child = _child(client, headers, family["id"], "Timestamp")
        enrollment = _enrollment(client, headers, child["id"], facility["id"])
        reviews = client.get(
            "/api/v1/room-placement-reviews",
            headers=headers,
            params={"facility_id": facility["id"]},
        )
        assert reviews.status_code == 200, reviews.text
        review = next(
            value for value in reviews.json() if value["enrollment_id"] == enrollment["id"]
        )
        approval = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": review["effective_date"],
            },
        )
        assert approval.status_code == 200, approval.text
        before = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert before.status_code == 200, before.text
        assert family["id"] not in {item["family_id"] for item in before.json()["items"]}

        marker = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
        with application.state.database.session_factory() as session:
            record = session.get(Room, UUID(room["id"]))
            assert record is not None
            record.name = "Renamed Inactive Room"
            record.is_active = False
            record.updated_at = marker
            session.commit()

        response = client.get("/api/v1/admissions/intake-queue", headers=headers)
        assert response.status_code == 200, response.text
        case = next(item for item in response.json()["items"] if item["family_id"] == family["id"])
        room_reason = next(
            reason for reason in case["reasons"] if reason["code"] == "room_unavailable"
        )
        assert room_reason["action"]["path"] == f"/children/{child['id']}"
        assert "placement review" not in room_reason["instruction"].lower()
        assert case["enrollments"][0]["room_name"] == "Renamed Inactive Room"
        observed = datetime.fromisoformat(case["updated_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        assert observed == marker


def test_queue_filters_counts_tenant_scope_and_owner_admin_permission(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "admissions-first@example.com", "First Admissions")
        headers = _headers(owner)
        facility, _, _, _ = _facility_tree(client, headers)
        family = _family(client, headers, "First Placement Family")
        child = _child(client, headers, family["id"], "First")
        enrollment = _enrollment(client, headers, child["id"], facility["id"])
        _family(client, headers, "No Facility Family", status="pending")

        other = _register(client, "admissions-other@example.com", "Other Admissions")
        other_headers = _headers(other)
        other_family = _family(
            client,
            other_headers,
            "Other Private Family",
            status="pending",
            contacts=False,
        )

        filtered = client.get(
            "/api/v1/admissions/intake-queue",
            headers=headers,
            params={"stage": "placement_review"},
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["family_id"] == family["id"]
        assert filtered.json()["counts"]["by_stage"] == {
            "family_contacts": 0,
            "child_record": 0,
            "enrollment_setup": 0,
            "record_conflict": 0,
            "family_review": 0,
            "placement_review": 1,
        }

        facility_filtered = client.get(
            "/api/v1/admissions/intake-queue",
            headers=headers,
            params={"facility_id": facility["id"], "limit": 1},
        )
        assert facility_filtered.status_code == 200, facility_filtered.text
        assert facility_filtered.json()["total"] == 1
        assert facility_filtered.json()["items"][0]["enrollments"][0]["id"] == enrollment["id"]

        first_payload = client.get(
            "/api/v1/admissions/intake-queue",
            headers=headers,
        ).json()
        first_serialized = json.dumps(first_payload)
        assert other_family["id"] not in first_serialized
        assert "Other Private Family" not in first_serialized
        assert first_payload["organization_id"] == owner["user"]["organization_id"]

        educator = client.get(
            "/api/v1/admissions/intake-queue",
            headers=_educator_headers(application, owner),
        )
        assert educator.status_code == 403
        assert educator.headers["cache-control"] == "private, no-store"
        assert educator.headers["pragma"] == "no-cache"

        unauthenticated = client.get("/api/v1/admissions/intake-queue")
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["cache-control"] == "private, no-store"


def test_queue_uses_constant_bulk_selects_and_never_writes(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "admissions-query@example.com", "Query Admissions")
        headers = _headers(owner)
        family = _family(client, headers, "Query Family")
        _child(client, headers, family["id"], "Query")

        def capture_get() -> tuple[list[str], dict]:
            statements: list[str] = []

            def capture(_connection, _cursor, statement, _parameters, _context, _many) -> None:
                statements.append(" ".join(statement.split()))

            event.listen(application.state.database.engine, "before_cursor_execute", capture)
            try:
                response = client.get("/api/v1/admissions/intake-queue", headers=headers)
            finally:
                event.remove(
                    application.state.database.engine,
                    "before_cursor_execute",
                    capture,
                )
            assert response.status_code == 200, response.text
            return statements, response.json()

        first_statements, first_payload = capture_get()
        second_family = _family(client, headers, "Second Query Family")
        _child(client, headers, second_family["id"], "Second")
        second_statements, second_payload = capture_get()

        for statements in (first_statements, second_statements):
            assert statements
            assert all(statement.upper().startswith("SELECT") for statement in statements)
            for marker in (
                " FROM families ",
                " FROM guardians ",
                " FROM emergency_contacts ",
                " FROM children ",
                " FROM enrollments ",
            ):
                assert sum(marker in f" {statement} " for statement in statements) == 1
        assert len(first_statements) == len(second_statements)
        assert first_payload["total"] == 1
        assert second_payload["total"] == 2


def test_projection_models_reject_extra_fields_and_unsafe_destinations() -> None:
    with pytest.raises(ValidationError):
        AdmissionIntakeAction(label="Unsafe", path="https://example.test/families/1")
    with pytest.raises(ValidationError):
        AdmissionIntakeAction(label="Unsafe", path="/families/not-a-uuid")
    with pytest.raises(ValidationError):
        AdmissionIntakeAction(
            label="Unsafe",
            path=f"/families/{uuid4()}",
            destination="invented",
        )
