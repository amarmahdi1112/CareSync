"""Bounded error and corrupt-replay proofs for verified release checkout."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.api.basic.family_release_checkout import PRIVATE_HEADERS
from app.basic.models import (
    AttendanceDay,
    AttendanceEvent,
    AttendanceInterval,
    AttendanceReleaseSnapshot,
    AuditEvent,
    ChildcareCommandClaim,
    ChildcareCommandReceipt,
    ChildcareCommandSlot,
    OrganizationMembership,
    RealtimeEvent,
    StaffShift,
)
from tests import test_basic_family_release_checkout_api as checkout_api

CheckoutScenario = checkout_api.CheckoutScenario
checkout_scenario = checkout_api.checkout_scenario


def _state(scenario: CheckoutScenario) -> dict[str, object]:
    with scenario.application.state.database.session_factory() as session:
        day = session.get(AttendanceDay, scenario.day_id)
        interval = session.get(AttendanceInterval, scenario.interval_id)
        assert day is not None and interval is not None
        return {
            "day_version": day.version,
            "checked_out_at": interval.checked_out_at,
            "attendance_events": session.scalar(select(func.count()).select_from(AttendanceEvent)),
            "release_snapshots": session.scalar(
                select(func.count()).select_from(AttendanceReleaseSnapshot)
            ),
            "command_receipts": session.scalar(
                select(func.count()).select_from(ChildcareCommandReceipt)
            ),
            "command_slots": session.scalar(select(func.count()).select_from(ChildcareCommandSlot)),
            "command_claims": session.scalar(
                select(func.count()).select_from(ChildcareCommandClaim)
            ),
            "audit_events": session.scalar(select(func.count()).select_from(AuditEvent)),
            "realtime_events": session.scalar(select(func.count()).select_from(RealtimeEvent)),
        }


def _assert_bounded_error(response, *, status_code: int, code: str) -> None:
    assert response.status_code == status_code, response.text
    assert response.json() == {"detail": {"code": code}}
    for header, expected in PRIVATE_HEADERS.items():
        assert response.headers[header] == expected


def _actor_pair(scenario: CheckoutScenario) -> tuple[UUID, UUID, UUID]:
    with scenario.application.state.database.session_factory() as session:
        shift = session.get(StaffShift, UUID(scenario.command["expected_staff_shift_id"]))
        assert shift is not None
        educator = session.get(OrganizationMembership, shift.membership_id)
        assert educator is not None
        foreign_actor = session.scalar(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == educator.organization_id,
                OrganizationMembership.user_id != educator.user_id,
                OrganizationMembership.status == "active",
            )
            .order_by(OrganizationMembership.id)
        )
        assert foreign_actor is not None
        return educator.organization_id, educator.user_id, foreign_actor.user_id


def test_foreign_actor_operation_is_private_code_only_and_creates_no_writes(
    checkout_scenario: CheckoutScenario,
) -> None:
    scenario = checkout_scenario
    organization_id, _, foreign_actor_user_id = _actor_pair(scenario)
    with scenario.application.state.database.session_factory() as session:
        session.add(
            ChildcareCommandSlot(
                organization_id=organization_id,
                client_operation_id=scenario.operation_id,
                entry_kind="receipt",
                actor_user_id=foreign_actor_user_id,
            )
        )
        session.commit()
    before = _state(scenario)

    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )

    _assert_bounded_error(
        response,
        status_code=404,
        code="release_checkout_operation_not_found",
    )
    assert _state(scenario) == before
    assert str(organization_id) not in response.text
    assert str(foreign_actor_user_id) not in response.text
    assert str(scenario.operation_id) not in response.text


def test_finalized_absent_operation_is_code_only_and_creates_no_writes(
    checkout_scenario: CheckoutScenario,
) -> None:
    scenario = checkout_scenario
    organization_id, educator_user_id, _ = _actor_pair(scenario)
    with scenario.application.state.database.session_factory() as session:
        session.add_all(
            [
                ChildcareCommandSlot(
                    organization_id=organization_id,
                    client_operation_id=scenario.operation_id,
                    entry_kind="absence_claim",
                    actor_user_id=educator_user_id,
                ),
                ChildcareCommandClaim(
                    organization_id=organization_id,
                    client_operation_id=scenario.operation_id,
                    actor_user_id=educator_user_id,
                ),
            ]
        )
        session.commit()
    before = _state(scenario)

    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )

    _assert_bounded_error(response, status_code=409, code="operation_finalized_absent")
    assert _state(scenario) == before
    assert str(organization_id) not in response.text
    assert str(educator_user_id) not in response.text
    assert str(scenario.operation_id) not in response.text


def test_changed_intent_is_code_only_and_creates_no_additional_writes(
    checkout_scenario: CheckoutScenario,
) -> None:
    scenario = checkout_scenario
    first = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert first.status_code == 200, first.text
    before = _state(scenario)
    changed = dict(scenario.command)
    changed["verification_method"] = "documented_familiarity"
    changed["verification_result"] = "documented_familiarity"

    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=changed,
    )

    _assert_bounded_error(response, status_code=409, code="operation_reused")
    assert _state(scenario) == before
    assert str(scenario.operation_id) not in response.text


@pytest.mark.parametrize("corruption", ["route", "time", "target"])
def test_malformed_stored_replay_echo_is_bounded_and_creates_no_writes(
    checkout_scenario: CheckoutScenario,
    corruption: str,
) -> None:
    scenario = checkout_scenario
    first = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )
    assert first.status_code == 200, first.text

    with scenario.application.state.database.session_factory() as session:
        receipt = session.scalar(
            select(ChildcareCommandReceipt).where(
                ChildcareCommandReceipt.client_operation_id == scenario.operation_id
            )
        )
        assert receipt is not None
        if corruption == "route":
            receipt.outcome = {"action_route": "https://outside.invalid/release"}
        elif corruption == "time":
            receipt.committed_at = receipt.committed_at + timedelta(seconds=1)
        else:
            receipt.target_id = uuid4()
        session.commit()
    before = _state(scenario)

    response = scenario.client.post(
        scenario.path,
        headers=scenario.educator_headers,
        json=scenario.command,
    )

    _assert_bounded_error(
        response,
        status_code=409,
        code="release_checkout_receipt_incomplete",
    )
    assert _state(scenario) == before
    assert str(scenario.operation_id) not in response.text
