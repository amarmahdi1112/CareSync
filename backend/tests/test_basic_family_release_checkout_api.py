"""Portable atomic acceptance proofs for normal verified child release."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.basic.childcare_commands import command_hash
from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    AuditEvent,
    ChildcareCommandReceipt,
    ChildcareCommandSlot,
    FacilityReleaseCheckoutActivation,
    Organization,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    StaffShift,
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
    _reviewed_guardian_evidence,
)

C = "0029C_verified_release_checkout"


def _seed_activation(application, *, organization_id: str, facility_id: str) -> None:
    with application.state.database.session_factory() as session:
        organization = session.get(Organization, UUID(organization_id))
        assert organization is not None
        organization.status = "active"
        owner_role = session.scalar(
            select(Role).where(
                Role.organization_id == UUID(organization_id),
                Role.key == "owner",
            )
        )
        assert owner_role is not None
        owner_membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == UUID(organization_id),
                OrganizationMembership.role_id == owner_role.id,
                OrganizationMembership.status == "active",
            )
        )
        assert owner_membership is not None
        activation_id = uuid4()
        operation_id = uuid4()
        request_hash = command_hash(
            command_type="facility.release_checkout.activate",
            target_type="release_activation",
            target_scope=UUID(facility_id),
            intent={"policy": "normal_verified_release_v1"},
        )
        session.add(
            ChildcareCommandReceipt(
                id=uuid4(),
                organization_id=UUID(organization_id),
                client_operation_id=operation_id,
                command_type="facility.release_checkout.activate",
                target_type="release_activation",
                target_id=activation_id,
                request_hash=request_hash,
                actor_user_id=owner_membership.user_id,
                facility_id=UUID(facility_id),
                committed_version=1,
                outcome={"action_route": "/settings/release-checkout"},
            )
        )
        session.flush()
        session.add(
            FacilityReleaseCheckoutActivation(
                id=activation_id,
                organization_id=UUID(organization_id),
                facility_id=UUID(facility_id),
                activated_by_user_id=owner_membership.user_id,
                activated_by_membership_id=owner_membership.id,
                activated_by_role_id=owner_role.id,
                activated_by_role_key="owner",
                activation_operation_id=operation_id,
                activation_policy_version="normal_verified_release_v1",
            )
        )
        session.commit()


@dataclass
class CheckoutScenario:
    client: object
    application: object
    educator_headers: dict[str, str]
    command: dict
    day_id: UUID
    interval_id: UUID
    operation_id: UUID

    @property
    def path(self) -> str:
        return "/api/v1/attendance/release-check-out"


@pytest.fixture
def checkout_scenario(tmp_path, monkeypatch):
    client, application, _ = _client(tmp_path, monkeypatch, revision=C)
    with client:
        application.state.family_release_checkout_enabled = True
        auth, owner_headers = _register(client, suffix="checkout-owner")
        _, admin_headers = _administrator(application, client, auth["user"]["organization_id"])
        facility, _, rooms = _facility_tree(client, owner_headers)
        family, child = _family_child_and_enrollment(client, owner_headers, facility, rooms[0])
        guardian = _authority_person(
            client,
            owner_headers,
            family,
            guardian=True,
            first_name="Guardian",
        )
        recipient = _authority_person(
            client,
            owner_headers,
            family,
            guardian=False,
            first_name="Recipient",
        )
        evidence = _reviewed_guardian_evidence(
            client,
            owner_headers,
            admin_headers,
            family["id"],
        )
        _grant(
            client,
            owner_headers,
            child["id"],
            guardian,
            recipient,
            evidence,
        )
        _seed_activation(
            application,
            organization_id=auth["user"]["organization_id"],
            facility_id=facility["id"],
        )
        educator_headers, _ = _educator(
            client,
            owner_headers,
            facility_id=facility["id"],
            room_id=rooms[0]["id"],
            suffix="checkout",
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
        yield CheckoutScenario(
            client=client,
            application=application,
            educator_headers=educator_headers,
            command=command,
            day_id=UUID(context["attendance_day_id"]),
            interval_id=UUID(context["attendance_interval_id"]),
            operation_id=operation_id,
        )


def _counts(application) -> dict[str, int]:
    with application.state.database.session_factory() as session:
        return {
            "audit": session.scalar(select(func.count()).select_from(AuditEvent)),
            "realtime": session.scalar(select(func.count()).select_from(RealtimeEvent)),
            "event": session.scalar(select(func.count()).select_from(AttendanceEvent)),
            "snapshot": session.scalar(select(func.count()).select_from(AttendanceReleaseSnapshot)),
            "receipt": session.scalar(select(func.count()).select_from(ChildcareCommandReceipt)),
        }


def _attendance_state(scenario: CheckoutScenario):
    with scenario.application.state.database.session_factory() as session:
        day = session.get(AttendanceDay, scenario.day_id)
        interval = session.get(AttendanceInterval, scenario.interval_id)
        assert day is not None and interval is not None
        return day.version, interval.checked_out_at


def test_normal_release_commits_exact_snapshot_and_exact_replay(
    checkout_scenario: CheckoutScenario,
    monkeypatch,
) -> None:
    scenario = checkout_scenario
    before_counts = _counts(scenario.application)
    before_version, before_checkout = _attendance_state(scenario)
    assert before_checkout is None

    first = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["replayed"] is False
    assert first.headers["cache-control"] == "private, no-store"
    assert set(body) == {"schema_version", "resource", "receipt", "replayed"}
    assert set(body["resource"]) == {
        "release_id",
        "organization_id",
        "facility_id",
        "room_id",
        "child_id",
        "attendance_day_id",
        "attendance_interval_id",
        "attendance_day_version",
        "checkout_event_id",
        "staff_shift_id",
        "actor_user_id",
        "actor_membership_id",
        "recipient_person_id",
        "recipient_person_version_id",
        "recipient_display_name",
        "recipient_relationship",
        "authorization_id",
        "authorization_version",
        "authority_revision",
        "restriction_digest_sha256",
        "verification_policy_code",
        "verification_method",
        "verification_result",
        "decision_policy_version",
        "requested_at",
        "checked_out_at",
        "committed_at",
        "client_operation_id",
        "request_hash",
        "release_mode",
    }
    assert set(body["receipt"]) == {
        "organization_id",
        "client_operation_id",
        "command_type",
        "target_type",
        "target_id",
        "committed_version",
        "committed_at",
        "facility_id",
        "action_route",
    }
    assert "family_id" not in first.text
    assert "evidence_id" not in first.text
    assert "email" not in first.text

    after_counts = _counts(scenario.application)
    assert after_counts["event"] == before_counts["event"] + 1
    assert after_counts["snapshot"] == before_counts["snapshot"] + 1
    assert after_counts["receipt"] == before_counts["receipt"] + 1
    assert after_counts["audit"] == before_counts["audit"] + 1
    assert after_counts["realtime"] == before_counts["realtime"] + 1
    after_version, after_checkout = _attendance_state(scenario)
    assert after_version == before_version + 1
    assert after_checkout is not None

    with scenario.application.state.database.session_factory() as session:
        snapshot = session.scalar(
            select(AttendanceReleaseSnapshot).where(
                AttendanceReleaseSnapshot.client_operation_id == scenario.operation_id
            )
        )
        event = session.scalar(
            select(AttendanceEvent).where(
                AttendanceEvent.client_operation_id == scenario.operation_id
            )
        )
        receipt = session.scalar(
            select(ChildcareCommandReceipt).where(
                ChildcareCommandReceipt.client_operation_id == scenario.operation_id
            )
        )
        realtime_event = session.scalar(
            select(RealtimeEvent).where(
                RealtimeEvent.organization_id == snapshot.organization_id,
                RealtimeEvent.event_type == "attendance.release.checked_out",
                RealtimeEvent.entity_type == "attendance_release",
                RealtimeEvent.entity_id == snapshot.id,
            )
        ) if snapshot is not None else None
        assert (
            snapshot is not None
            and event is not None
            and receipt is not None
            and realtime_event is not None
        )
        assert snapshot.checkout_event_id == event.id
        assert snapshot.id == receipt.target_id == UUID(body["resource"]["release_id"])
        assert snapshot.request_hash == receipt.request_hash == body["resource"]["request_hash"]
        assert snapshot.checked_out_at == snapshot.committed_at
        assert snapshot.attendance_day_version == after_version
        assert realtime_event.payload.get("source") == "verified_release_checkout"
        assert UUID(realtime_event.payload["facility_id"]) == snapshot.facility_id

        shift = session.get(StaffShift, UUID(scenario.command["expected_staff_shift_id"]))
        role = session.scalar(
            select(Role)
            .join(
                OrganizationMembership,
                OrganizationMembership.role_id == Role.id,
            )
            .where(
                OrganizationMembership.id == snapshot.actor_membership_id,
                Role.organization_id == snapshot.organization_id,
            )
        )
        assert shift is not None and role is not None
        shift.status = "closed"
        shift.clocked_out_at = snapshot.committed_at
        role.permissions = [
            permission
            for permission in role.permissions
            if permission not in {"attendance:record", "release:checkout"}
        ]
        session.commit()

    from app.basic import family_release_checkout_service as service

    def fresh_path_must_not_run(*args, **kwargs):
        raise AssertionError("exact replay reached current activation or shift checks")

    monkeypatch.setattr(service, "_fresh_release", fresh_path_must_not_run)
    monkeypatch.setattr(
        scenario.application.state.settings,
        "database_read_only",
        True,
    )

    replay = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert replay.status_code == 200, replay.text
    replay_body = replay.json()
    assert replay_body["replayed"] is True
    assert replay_body["resource"] == body["resource"]
    assert replay_body["receipt"] == body["receipt"]
    assert replay.headers["cache-control"] == "private, no-store"
    assert _counts(scenario.application) == after_counts
    assert _attendance_state(scenario) == (after_version, after_checkout)


def test_same_operation_changed_intent_is_rejected_without_writes(
    checkout_scenario: CheckoutScenario,
) -> None:
    scenario = checkout_scenario
    first = scenario.client.post(
        scenario.path, headers=scenario.educator_headers, json=scenario.command
    )
    assert first.status_code == 200, first.text
    before = _counts(scenario.application)
    changed = dict(scenario.command)
    changed["verification_method"] = "documented_familiarity"
    changed["verification_result"] = "documented_familiarity"
    response = scenario.client.post(scenario.path, headers=scenario.educator_headers, json=changed)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "operation_reused"
    assert response.headers["cache-control"] == "private, no-store"
    assert _counts(scenario.application) == before


def test_late_failure_rolls_back_every_release_write(
    checkout_scenario: CheckoutScenario,
    monkeypatch,
) -> None:
    from app.basic import family_release_checkout_service as service

    scenario = checkout_scenario
    before_counts = _counts(scenario.application)
    before_state = _attendance_state(scenario)

    def fail_after_flush(session, context):
        session.flush()
        raise HTTPException(503, detail={"code": "forced_late_failure"})

    monkeypatch.setattr(service, "_commit", fail_after_flush)
    response = scenario.client.post(
        scenario.path, headers=scenario.educator_headers, json=scenario.command
    )
    assert response.status_code == 503, response.text
    assert _attendance_state(scenario) == before_state
    assert _counts(scenario.application) == before_counts
    with scenario.application.state.database.session_factory() as session:
        for model in (
            AttendanceEvent,
            AttendanceReleaseSnapshot,
            ChildcareCommandReceipt,
            ChildcareCommandSlot,
        ):
            count = session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.client_operation_id == scenario.operation_id)
            )
            assert count == 0


def test_route_gate_fails_closed_before_service(tmp_path, monkeypatch) -> None:
    from app.api.basic import family_release_checkout as route_module

    client, application, _ = _client(tmp_path, monkeypatch, revision=C)
    calls = 0

    def forbidden_service(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("disabled route reached command service")

    monkeypatch.setattr(route_module, "release_checkout", forbidden_service)
    with client:
        _, headers = _register(client, suffix="checkout-gate")
        application.state.family_release_checkout_enabled = False
        response = client.post(
            "/api/v1/attendance/release-check-out",
            headers=headers,
            json={
                "schema_version": "release-checkout-command-v1",
                "client_operation_id": str(uuid4()),
                "requested_at": "2026-07-18T00:00:00Z",
                "child_id": str(uuid4()),
                "facility_id": str(uuid4()),
                "expected_room_id": str(uuid4()),
                "expected_attendance_day_id": str(uuid4()),
                "expected_attendance_interval_id": str(uuid4()),
                "expected_staff_shift_id": str(uuid4()),
                "recipient_person_id": str(uuid4()),
                "recipient_person_version_id": str(uuid4()),
                "authorization_id": str(uuid4()),
                "authorization_version": 1,
                "expected_authority_revision": 1,
                "expected_restriction_digest_sha256": "00" * 32,
                "expected_decision_policy_version": "release-context-v1",
                "verification_method": "government_photo_id",
                "verification_result": "verified",
            },
        )
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "family_authority_release_checkout_unavailable"}}
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == 0


def test_read_only_fresh_command_creates_no_operation_slot(
    checkout_scenario: CheckoutScenario,
    monkeypatch,
) -> None:
    scenario = checkout_scenario
    monkeypatch.setattr(
        scenario.application.state.settings,
        "database_read_only",
        True,
    )
    before = _counts(scenario.application)
    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": {"code": "database_writes_disabled"}}
    assert response.headers["cache-control"] == "private, no-store"
    assert _counts(scenario.application) == before
    with scenario.application.state.database.session_factory() as session:
        assert (
            session.scalar(
                select(ChildcareCommandSlot).where(
                    ChildcareCommandSlot.client_operation_id == scenario.operation_id,
                )
            )
            is None
        )
