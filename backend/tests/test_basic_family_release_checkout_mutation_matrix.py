"""Portable 0029C stale-context and care-atomicity acceptance matrix.

Every case obtains a valid 0029B projection first, mutates one authoritative
fact, and then submits the frozen C command.  Rejections must be bounded and
must leave no release event, receipt, snapshot, slot, audit, or realtime row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    AuditEvent,
    ChildcareCommandReceipt,
    ChildcareCommandSlot,
    DailyCareRecord,
    DailyCareRecordEvent,
    Facility,
    MembershipRoomAssignment,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    Room,
    StaffShift,
)
from tests.test_basic_family_release_checkout_api import (
    C,
    _seed_activation,
)
from tests.test_basic_family_release_context_api import (
    _administrator,
    _authority_person,
    _check_in_child,
    _client,
    _educator,
    _facility_tree,
    _family_child_and_enrollment,
    _grant,
    _register,
    _rule,
)
from tests.test_basic_regulated_care import _active_plan


@dataclass
class MatrixScenario:
    client: object
    application: object
    owner_headers: dict[str, str]
    admin_headers: dict[str, str]
    educator_headers: dict[str, str]
    organization_id: UUID
    facility: dict
    rooms: list[dict]
    family: dict
    child: dict
    guardian: dict
    recipient: dict
    evidence_id: UUID
    evidence_assessment_id: UUID
    authorization: dict
    command: dict
    day_id: UUID
    interval_id: UUID
    operation_id: UUID

    @property
    def path(self) -> str:
        return "/api/v1/attendance/release-check-out"


def _expiring_reviewed_evidence(
    client,
    owner_headers: dict[str, str],
    admin_headers: dict[str, str],
    family_id: str,
) -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    recorded = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "evidence_kind": "guardian_attestation",
            "source_label": "Portable mutation-matrix authority evidence",
            "captured_at": now.isoformat(),
            "expires_at": (now + timedelta(days=90)).isoformat(),
        },
    )
    assert recorded.status_code == 201, recorded.text
    resource = recorded.json()["resource"]
    reviewed = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{resource['id']}/review",
        headers=admin_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": resource["version"],
            "assessed_epistemic_status": "reported",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_resource = reviewed.json()["resource"]
    return (
        UUID(reviewed_resource["id"]),
        UUID(reviewed_resource["current_assessment"]["id"]),
    )


@pytest.fixture
def matrix_scenario(tmp_path, monkeypatch):
    client, application, _ = _client(tmp_path, monkeypatch, revision=C)
    with client:
        application.state.family_release_checkout_enabled = True
        auth, owner_headers = _register(client, suffix="checkout-mutation")
        organization_id = UUID(auth["user"]["organization_id"])
        _, admin_headers = _administrator(application, client, str(organization_id))
        facility, _, rooms = _facility_tree(client, owner_headers)
        family, child = _family_child_and_enrollment(client, owner_headers, facility, rooms[0])
        guardian = _authority_person(
            client,
            owner_headers,
            family,
            guardian=True,
            first_name="MatrixGuardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family,
            guardian=False,
            first_name="MatrixRecipient",
        )
        evidence_id, evidence_assessment_id = _expiring_reviewed_evidence(
            client,
            owner_headers,
            admin_headers,
            family["id"],
        )
        authorization = _grant(
            client,
            owner_headers,
            child["id"],
            guardian,
            recipient,
            (str(evidence_id), str(evidence_assessment_id)),
        )
        _seed_activation(
            application,
            organization_id=str(organization_id),
            facility_id=facility["id"],
        )
        educator_headers, _ = _educator(
            client,
            owner_headers,
            facility_id=facility["id"],
            room_id=rooms[0]["id"],
            suffix="mutation",
        )
        _check_in_child(client, educator_headers, child["id"], facility["id"])
        context_response = client.get(
            f"/api/v1/children/{child['id']}/release-context?facility_id={facility['id']}",
            headers=educator_headers,
        )
        assert context_response.status_code == 200, context_response.text
        context = context_response.json()
        assert context["decision"] == "recipient_selection_available"
        projected = context["eligible_recipients"][0]
        operation_id = uuid4()
        command = {
            "schema_version": "release-checkout-command-v1",
            "client_operation_id": str(operation_id),
            "requested_at": context["evaluated_at"],
            "child_id": context["child_id"],
            "facility_id": context["facility_id"],
            "expected_room_id": context["room_id"],
            "expected_attendance_day_id": context["attendance_day_id"],
            "expected_attendance_interval_id": context["attendance_interval_id"],
            "expected_staff_shift_id": context["staff_shift_id"],
            "recipient_person_id": projected["recipient_person_id"],
            "recipient_person_version_id": projected["recipient_person_version_id"],
            "authorization_id": projected["authorization_id"],
            "authorization_version": projected["authorization_version"],
            "expected_authority_revision": context["authority_revision"],
            "expected_restriction_digest_sha256": context["restriction_digest_sha256"],
            "expected_decision_policy_version": context["decision_policy_version"],
            "verification_method": "government_photo_id",
            "verification_result": "verified",
        }
        yield MatrixScenario(
            client=client,
            application=application,
            owner_headers=owner_headers,
            admin_headers=admin_headers,
            educator_headers=educator_headers,
            organization_id=organization_id,
            facility=facility,
            rooms=rooms,
            family=family,
            child=child,
            guardian=guardian,
            recipient=recipient,
            evidence_id=evidence_id,
            evidence_assessment_id=evidence_assessment_id,
            authorization=authorization,
            command=command,
            day_id=UUID(context["attendance_day_id"]),
            interval_id=UUID(context["attendance_interval_id"]),
            operation_id=operation_id,
        )


def _release_state(scenario: MatrixScenario) -> dict[str, object]:
    with scenario.application.state.database.session_factory() as session:
        day = session.get(AttendanceDay, scenario.day_id)
        interval = session.get(AttendanceInterval, scenario.interval_id)
        assert day is not None and interval is not None
        return {
            "day_version": day.version,
            "interval_checkout": interval.checked_out_at,
            "event": session.scalar(
                select(func.count())
                .select_from(AttendanceEvent)
                .where(AttendanceEvent.client_operation_id == scenario.operation_id)
            ),
            "snapshot": session.scalar(
                select(func.count())
                .select_from(AttendanceReleaseSnapshot)
                .where(AttendanceReleaseSnapshot.client_operation_id == scenario.operation_id)
            ),
            "receipt": session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(ChildcareCommandReceipt.client_operation_id == scenario.operation_id)
            ),
            "slot": session.scalar(
                select(func.count())
                .select_from(ChildcareCommandSlot)
                .where(ChildcareCommandSlot.client_operation_id == scenario.operation_id)
            ),
            "audit": session.scalar(select(func.count()).select_from(AuditEvent)),
            "realtime": session.scalar(select(func.count()).select_from(RealtimeEvent)),
        }


def _assert_bounded_rejection(
    scenario: MatrixScenario,
    *,
    status_code: int,
    code: str | None = None,
    detail: str | None = None,
) -> None:
    before = _release_state(scenario)
    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert response.status_code == status_code, response.text
    if code is not None:
        assert response.json() == {"detail": {"code": code}}
    if detail is not None:
        assert response.json() == {"detail": detail}
    assert _release_state(scenario) == before


def _educator_membership(session, scenario: MatrixScenario) -> OrganizationMembership:
    shift = session.get(StaffShift, UUID(scenario.command["expected_staff_shift_id"]))
    assert shift is not None
    membership = session.get(OrganizationMembership, shift.membership_id)
    assert membership is not None
    return membership


@pytest.mark.parametrize(
    ("mutation", "status_code", "code", "detail"),
    [
        ("authorization_revoke", 409, "release_checkout_context_stale", None),
        ("rule_change", 409, "release_restricted", None),
        ("person_version_change", 409, "release_checkout_context_stale", None),
        ("evidence_invalidate", 409, "no_active_release_authorization", None),
        ("evidence_expiry", 409, "no_active_release_authorization", None),
        ("shift_close", 409, "open_shift_required", None),
        ("permission_revoke", 403, "release_checkout_forbidden", None),
        (
            "membership_revoke",
            401,
            None,
            "Invalid or missing authentication token",
        ),
        ("room_assignment_remove", 404, "release_checkout_scope_not_found", None),
        ("facility_deactivate", 404, "release_checkout_scope_not_found", None),
        ("room_deactivate", 409, "release_checkout_context_stale", None),
        ("second_checkout", 409, "child_not_on_site", None),
    ],
)
def test_context_mutation_matrix_rejects_without_partial_release(
    matrix_scenario: MatrixScenario,
    monkeypatch,
    mutation: str,
    status_code: int,
    code: str | None,
    detail: str | None,
) -> None:
    scenario = matrix_scenario
    if mutation == "authorization_revoke":
        response = scenario.client.post(
            f"/api/v1/children/{scenario.child['id']}/release-authorizations/"
            f"{scenario.authorization['id']}/revoke",
            headers=scenario.owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": scenario.authorization["version"],
                "expected_authority_revision": scenario.authorization["authority_revision"],
                "reason_code": "authority_withdrawn",
            },
        )
        assert response.status_code == 200, response.text
    elif mutation == "rule_change":
        _rule(
            scenario.client,
            scenario.owner_headers,
            scenario.child["id"],
            scenario.guardian,
            (str(scenario.evidence_id), str(scenario.evidence_assessment_id)),
            expected_revision=scenario.authorization["authority_revision"],
        )
    elif mutation == "person_version_change":
        response = scenario.client.post(
            f"/api/v1/families/{scenario.family['id']}/authority/people/"
            f"{scenario.recipient['id']}/versions",
            headers=scenario.owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": scenario.recipient["version"],
                "facts": {
                    "first_name": "UpdatedMatrixRecipient",
                    "last_name": "Authority",
                    "preferred_name": "Updated recipient",
                    "relationship_kind": "family_friend",
                    "email": "updated-matrix-recipient@example.com",
                    "primary_phone": "780-555-0144",
                },
            },
        )
        assert response.status_code == 200, response.text
    elif mutation == "evidence_invalidate":
        response = scenario.client.post(
            f"/api/v1/families/{scenario.family['id']}/authority/evidence/"
            f"{scenario.evidence_id}/invalidate",
            headers=scenario.admin_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 2,
                "reason_code": "authority_changed",
            },
        )
        assert response.status_code == 200, response.text
    elif mutation == "evidence_expiry":
        from app.basic import family_release_checkout_service as service

        evaluated_at = datetime.fromisoformat(
            scenario.command["requested_at"].replace("Z", "+00:00")
        )
        monkeypatch.setattr(
            service,
            "_database_instant",
            lambda session: evaluated_at + timedelta(days=91),
        )
    else:
        with scenario.application.state.database.session_factory() as session:
            membership = _educator_membership(session, scenario)
            if mutation == "shift_close":
                shift = session.get(StaffShift, UUID(scenario.command["expected_staff_shift_id"]))
                assert shift is not None
                shift.status = "closed"
                shift.clocked_out_at = datetime.now(UTC)
            elif mutation == "permission_revoke":
                role = session.get(Role, membership.role_id)
                assert role is not None
                role.permissions = [
                    value for value in role.permissions if value != "release:checkout"
                ]
            elif mutation == "membership_revoke":
                membership.status = "revoked"
            elif mutation == "room_assignment_remove":
                assignment = session.scalar(
                    select(MembershipRoomAssignment).where(
                        MembershipRoomAssignment.organization_id == scenario.organization_id,
                        MembershipRoomAssignment.membership_id == membership.id,
                        MembershipRoomAssignment.room_id
                        == UUID(scenario.command["expected_room_id"]),
                    )
                )
                assert assignment is not None
                assignment.is_active = False
            elif mutation == "facility_deactivate":
                facility = session.get(Facility, UUID(scenario.facility["id"]))
                assert facility is not None
                facility.status = "inactive"
            elif mutation == "room_deactivate":
                room = session.get(Room, UUID(scenario.rooms[0]["id"]))
                assert room is not None
                room.is_active = False
            elif mutation == "second_checkout":
                day = session.get(AttendanceDay, scenario.day_id)
                interval = session.get(AttendanceInterval, scenario.interval_id)
                assert day is not None and interval is not None
                interval.checked_out_at = datetime.now(UTC)
                day.version += 1
            else:  # pragma: no cover - protects the test table itself.
                raise AssertionError(f"unknown mutation: {mutation}")
            session.commit()

    _assert_bounded_rejection(
        scenario,
        status_code=status_code,
        code=code,
        detail=detail,
    )


def test_open_interval_correction_then_release_commits_one_complete_bundle(
    matrix_scenario: MatrixScenario,
) -> None:
    scenario = matrix_scenario
    with scenario.application.state.database.session_factory() as session:
        interval = session.get(AttendanceInterval, scenario.interval_id)
        assert interval is not None
        checked_in_at = interval.checked_in_at
        if checked_in_at.tzinfo is None:
            checked_in_at = checked_in_at.replace(tzinfo=UTC)

    corrected = scenario.client.put(
        f"/api/v1/attendance/{scenario.day_id}/correction",
        headers=scenario.owner_headers,
        json={
            "interval_id": str(scenario.interval_id),
            "checked_in_at": (checked_in_at - timedelta(seconds=1)).isoformat(),
            "checked_out_at": None,
            "reason": "Correcting the recorded arrival before verified release",
        },
    )
    assert corrected.status_code == 200, corrected.text
    before = _release_state(scenario)

    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replayed"] is False
    assert body["resource"]["attendance_day_id"] == str(scenario.day_id)
    assert body["resource"]["attendance_interval_id"] == str(scenario.interval_id)
    assert body["resource"]["client_operation_id"] == str(scenario.operation_id)

    after = _release_state(scenario)
    assert after["day_version"] == before["day_version"] + 1
    assert after["interval_checkout"] is not None
    for key in ("event", "snapshot", "receipt", "slot", "audit", "realtime"):
        assert after[key] == before[key] + 1


def _create_care_record(
    scenario: MatrixScenario,
    *,
    care_type: str,
    occurred_at: datetime,
) -> dict:
    payload = {} if care_type == "sleep" else {"kind": "learning"}
    response = scenario.client.post(
        "/api/v1/care/records",
        headers=scenario.educator_headers,
        json={
            "attendance_day_id": str(scenario.day_id),
            "care_type": care_type,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload,
            "client_operation_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_open_sleep_is_auto_finished_at_authoritative_checkout(
    matrix_scenario: MatrixScenario,
) -> None:
    scenario = matrix_scenario
    sleep = _create_care_record(
        scenario,
        care_type="sleep",
        occurred_at=datetime.now(UTC),
    )
    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert response.status_code == 200, response.text
    committed_at = datetime.fromisoformat(
        response.json()["resource"]["committed_at"].replace("Z", "+00:00")
    )
    with scenario.application.state.database.session_factory() as session:
        record = session.get(DailyCareRecord, UUID(sleep["id"]))
        assert record is not None
        assert record.ended_at is not None
        ended_at = (
            record.ended_at.replace(tzinfo=UTC)
            if record.ended_at.tzinfo is None
            else record.ended_at
        )
        assert ended_at == committed_at
        assert record.version == 2
        event = session.scalar(
            select(DailyCareRecordEvent).where(
                DailyCareRecordEvent.care_record_id == record.id,
                DailyCareRecordEvent.event_type == "auto_finished_at_checkout",
            )
        )
        assert event is not None


@pytest.mark.parametrize("record_kind", ["care", "medication", "incident"])
def test_future_regulated_record_blocks_release_without_partial_writes(
    matrix_scenario: MatrixScenario,
    record_kind: str,
) -> None:
    scenario = matrix_scenario
    future = datetime.now(UTC) + timedelta(minutes=4)
    if record_kind == "care":
        _create_care_record(scenario, care_type="activity", occurred_at=future)
    elif record_kind == "medication":
        plan = _active_plan(
            scenario.client,
            scenario.owner_headers,
            scenario.facility["id"],
            scenario.child["id"],
        )
        response = scenario.client.post(
            "/api/v1/medications/administrations",
            headers=scenario.educator_headers,
            json={
                "medication_plan_id": plan["id"],
                "attendance_day_id": str(scenario.day_id),
                "outcome": "administered",
                "scheduled_for": "09:00",
                "occurred_at": future.isoformat(),
                "amount": "5 mL",
                "client_operation_id": str(uuid4()),
            },
        )
        assert response.status_code == 201, response.text
    else:
        response = scenario.client.post(
            "/api/v1/incidents",
            headers=scenario.educator_headers,
            json={
                "facility_id": scenario.facility["id"],
                "room_id": scenario.rooms[0]["id"],
                "attendance_day_id": str(scenario.day_id),
                "occurred_at": future.isoformat(),
                "category": "injury",
                "severity": "minor",
                "summary": "Future observed record used for checkout consistency proof.",
                "immediate_actions": "Observed and documented.",
                "medical_attention": "none",
                "parent_notification_status": "pending",
                "client_operation_id": str(uuid4()),
            },
        )
        assert response.status_code == 201, response.text

    _assert_bounded_rejection(
        scenario,
        status_code=409,
        code="release_checkout_care_time_conflict",
    )


def test_late_failure_rolls_back_auto_finished_sleep_and_release(
    matrix_scenario: MatrixScenario,
    monkeypatch,
) -> None:
    from app.basic import family_release_checkout_service as service

    scenario = matrix_scenario
    sleep = _create_care_record(
        scenario,
        care_type="sleep",
        occurred_at=datetime.now(UTC),
    )
    before = _release_state(scenario)

    def fail_after_flush(session, context):
        session.flush()
        raise HTTPException(503, detail={"code": "forced_late_failure"})

    monkeypatch.setattr(service, "_commit", fail_after_flush)
    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": {"code": "family_authority_release_checkout_unavailable"}}
    assert _release_state(scenario) == before
    with scenario.application.state.database.session_factory() as session:
        record = session.get(DailyCareRecord, UUID(sleep["id"]))
        assert record is not None
        assert record.ended_at is None
        assert record.version == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(DailyCareRecordEvent)
                .where(
                    DailyCareRecordEvent.care_record_id == record.id,
                    DailyCareRecordEvent.event_type == "auto_finished_at_checkout",
                )
            )
            == 0
        )
