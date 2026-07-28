"""Safety proofs for the read-only 0040 billing readiness batch planner."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.api.basic.billing import (
    _billing_batch_command_for_selection,
    require_billing_permission,
)
from app.basic import billing as billing_service
from app.basic.billing_readiness_planner import (
    build_billing_readiness_batch_snapshot,
)
from app.basic.billing_schemas import (
    BillingReadinessBatchPreviewSelection,
    EstablishBillingAgreementCommand,
    PreviewBillingReadinessBatchCommand,
    PublishRatePlanVersionCommand,
)
from app.basic.models import (
    BasicBase,
    BillingSandboxSourceAttestation,
    Child,
    Facility,
    Guardian,
    Program,
)
from app.core.config import Settings
from app.main import create_app
from tests.test_basic_billing_projections import (
    AS_OF_DATE,
    _account,
    _agreement,
    _enrollment,
    _family_child,
    _rate,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
JWT_SECRET = "billing-batch-planner-test-secret-at-least-thirty-two-bytes"


def _program_for_enrollment(
    session: Session,
    organization_id: UUID,
    enrollment,
    label: str,
) -> Program:
    facility = Facility(
        id=enrollment.facility_id,
        organization_id=organization_id,
        name=f"{label} Centre",
        status="active",
        verification_status="pending",
        licensed_capacity=40,
        timezone="America/Edmonton",
    )
    program = Program(
        id=enrollment.program_id,
        organization_id=organization_id,
        facility_id=enrollment.facility_id,
        name=f"{label} Daycare",
        program_type="daycare",
        capacity=40,
        minimum_age_months=0,
        maximum_age_months=143,
        is_active=True,
    )
    session.add_all([facility, program])
    return program


def test_batch_snapshot_groups_dependency_waves_and_digests_direct_fact_changes() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        _family_child(session, organization_id, "Account")

        payer_family, payer_guardian, payer_child = _family_child(
            session, organization_id, "Payer"
        )
        payer_account = _account(
            session,
            organization_id,
            payer_family,
            payer_guardian,
        )
        payer_guardian.retired_at = datetime.now(UTC)
        payer_guardian.retired_operation_id = uuid4()
        replacement = Guardian(
            id=uuid4(),
            organization_id=organization_id,
            family_id=payer_family.id,
            first_name="Replacement",
            last_name="Payer",
            relationship="Parent",
            email="replacement@example.test",
            cell_phone="780-555-0102",
            is_primary=True,
            authorized_pickup=True,
        )
        session.add(replacement)

        rate_family, rate_guardian, rate_child = _family_child(
            session, organization_id, "Rate"
        )
        _account(session, organization_id, rate_family, rate_guardian)
        rate_enrollment = _enrollment(session, organization_id, rate_child)
        _program_for_enrollment(
            session, organization_id, rate_enrollment, "Rate"
        )

        agreement_family, agreement_guardian, agreement_child = _family_child(
            session, organization_id, "Agreement"
        )
        _account(session, organization_id, agreement_family, agreement_guardian)
        agreement_enrollment = _enrollment(
            session, organization_id, agreement_child
        )
        _program_for_enrollment(
            session, organization_id, agreement_enrollment, "Agreement"
        )
        _agreement_plan, agreement_rate = _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="AGREEMENT-BATCH",
        )

        ready_family, ready_guardian, ready_child = _family_child(
            session, organization_id, "Ready"
        )
        ready_account = _account(
            session, organization_id, ready_family, ready_guardian
        )
        ready_enrollment = _enrollment(session, organization_id, ready_child)
        _program_for_enrollment(
            session, organization_id, ready_enrollment, "Ready"
        )
        _ready_plan, ready_rate = _rate(
            session,
            organization_id,
            ready_enrollment,
            ready_child,
            code="READY-BATCH",
        )
        _agreement(
            session,
            organization_id,
            ready_family,
            ready_child,
            ready_account,
            ready_enrollment,
            ready_rate,
        )

        _family_child(
            session,
            organization_id,
            "Review",
            family_status="pending",
        )
        session.commit()

        first = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        repeat = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert first.snapshot_token == repeat.snapshot_token
        assert [group.model_dump(mode="json") for group in first.groups] == [
            group.model_dump(mode="json") for group in repeat.groups
        ]
        waves = [group.wave for group in first.groups]
        assert waves.count("account_payer") == 2
        assert waves.count("rate_plan") == 1
        assert waves.count("agreement") == 1
        assert waves.count("ready") == 1
        assert waves.count("manual_review") == 1

        payer_group = next(
            group
            for group in first.groups
            if group.family_id == payer_family.id
        )
        assert payer_group.suggested_command_type == "account_payer_assign"
        assert payer_group.billing_account_id == payer_account.id
        assert [option.guardian_id for option in payer_group.payer_options] == [
            replacement.id
        ]
        rate_group = next(group for group in first.groups if group.wave == "rate_plan")
        assert rate_group.family_id is None
        assert rate_group.affected_children[0].child_id == rate_child.id
        agreement_group = next(
            group for group in first.groups if group.wave == "agreement"
        )
        assert agreement_group.rate_plan_version_id == agreement_rate.id

        _agreement_plan.code = "AGREEMENT-BATCH-RENAMED"
        session.commit()
        code_changed = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert (
            code_changed.readiness.data_through_realtime_sequence
            == first.readiness.data_through_realtime_sequence
        )
        assert code_changed.snapshot_token != first.snapshot_token

        # This is an out-of-band canonical fact change: no realtime event advances,
        # but the ordered fact digest must still invalidate the old plan.
        payer_child.first_name = "Changed"
        session.commit()
        changed = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert (
            changed.readiness.data_through_realtime_sequence
            == first.readiness.data_through_realtime_sequence
        )
        assert changed.snapshot_token != first.snapshot_token
    engine.dispose()


def test_large_dependency_group_is_privacy_bounded_but_hashes_every_member() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        family, _guardian, first_child = _family_child(
            session, organization_id, "Large"
        )
        children = [first_child]
        for index in range(29):
            child = Child(
                id=uuid4(),
                organization_id=organization_id,
                family_id=family.id,
                first_name=f"Child-{index:02d}",
                last_name="Large",
                date_of_birth=date(2023, 1, 1),
                age_group="preschool",
                is_active=True,
                version=1,
            )
            session.add(child)
            children.append(child)
        session.commit()
        first = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert len(first.groups) == 1
        group = first.groups[0]
        assert group.affected_count == 30
        assert len(group.affected_children) == 25
        assert group.affected_children_truncated is True
        visible_ids = {child.child_id for child in group.affected_children}
        omitted = next(child for child in children if child.id not in visible_ids)
        omitted.first_name = "Omitted changed"
        session.commit()
        changed = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert (
            changed.readiness.data_through_realtime_sequence
            == first.readiness.data_through_realtime_sequence
        )
        assert changed.snapshot_token != first.snapshot_token
        assert (
            changed.groups[0].affected_membership_digest
            != group.affected_membership_digest
        )
        assert changed.groups[0].group_id != group.group_id
    engine.dispose()


def test_inactive_programs_fail_closed_before_rate_or_agreement_preview() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        rate_family, rate_guardian, rate_child = _family_child(
            session, organization_id, "Inactive Rate"
        )
        _account(session, organization_id, rate_family, rate_guardian)
        rate_enrollment = _enrollment(session, organization_id, rate_child)
        rate_program = _program_for_enrollment(
            session,
            organization_id,
            rate_enrollment,
            "Inactive Rate",
        )
        rate_program.is_active = False

        agreement_family, agreement_guardian, agreement_child = _family_child(
            session, organization_id, "Inactive Agreement"
        )
        _account(session, organization_id, agreement_family, agreement_guardian)
        agreement_enrollment = _enrollment(
            session, organization_id, agreement_child
        )
        agreement_program = _program_for_enrollment(
            session,
            organization_id,
            agreement_enrollment,
            "Inactive Agreement",
        )
        agreement_program.is_active = False
        _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="INACTIVE-AGREEMENT",
        )
        session.commit()
        batch = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert len(batch.groups) == 2
        assert {group.wave for group in batch.groups} == {"manual_review"}
        assert {group.block_code for group in batch.groups} == {
            "billing_program_inactive"
        }
        assert all(not group.actionable for group in batch.groups)
    engine.dispose()


def test_facility_and_program_type_drift_fail_closed_and_invalidate_snapshot() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        rate_family, rate_guardian, rate_child = _family_child(
            session,
            organization_id,
            "Rate Drift",
        )
        _account(session, organization_id, rate_family, rate_guardian)
        rate_enrollment = _enrollment(session, organization_id, rate_child)
        rate_program = _program_for_enrollment(
            session,
            organization_id,
            rate_enrollment,
            "Rate Drift",
        )
        _rate_plan, future_rate = _rate(
            session,
            organization_id,
            rate_enrollment,
            rate_child,
            code="RATE-DRIFT",
        )
        future_rate.effective_from = AS_OF_DATE + timedelta(days=10)

        agreement_family, agreement_guardian, agreement_child = _family_child(
            session,
            organization_id,
            "Agreement Drift",
        )
        _account(
            session,
            organization_id,
            agreement_family,
            agreement_guardian,
        )
        agreement_enrollment = _enrollment(
            session,
            organization_id,
            agreement_child,
        )
        agreement_program = _program_for_enrollment(
            session,
            organization_id,
            agreement_enrollment,
            "Agreement Drift",
        )
        _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="AGREEMENT-DRIFT",
        )
        session.commit()

        original = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        original_rate_group = next(
            group
            for group in original.groups
            if group.affected_children[0].child_id == rate_child.id
        )
        original_agreement_group = next(
            group
            for group in original.groups
            if group.affected_children[0].child_id == agreement_child.id
        )
        assert original_rate_group.wave == "rate_plan"
        assert len(original_rate_group.rate_plan_options) == 1
        assert original_agreement_group.wave == "agreement"

        rate_facility = session.get(Facility, rate_program.facility_id)
        assert rate_facility is not None
        rate_facility.status = "inactive"
        agreement_program.program_type = "out_of_school_care"
        session.commit()
        drifted = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        assert drifted.snapshot_token != original.snapshot_token
        drifted_rate_group = next(
            group
            for group in drifted.groups
            if group.affected_children[0].child_id == rate_child.id
        )
        drifted_agreement_group = next(
            group
            for group in drifted.groups
            if group.affected_children[0].child_id == agreement_child.id
        )
        assert drifted_rate_group.wave == "manual_review"
        assert drifted_rate_group.block_code == "billing_facility_inactive"
        assert drifted_agreement_group.wave == "manual_review"
        assert (
            drifted_agreement_group.block_code
            == "billing_agreement_rate_scope_invalid"
        )

        rate_facility.status = "active"
        rate_program.program_type = "out_of_school_care"
        session.commit()
        type_drifted = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )
        type_drifted_rate_group = next(
            group
            for group in type_drifted.groups
            if group.affected_children[0].child_id == rate_child.id
        )
        assert type_drifted.snapshot_token != drifted.snapshot_token
        assert type_drifted_rate_group.wave == "rate_plan"
        assert type_drifted_rate_group.program_type == "out_of_school_care"
        assert type_drifted_rate_group.rate_plan_options == []
    engine.dispose()


def test_canonical_commands_reject_inactive_facility_and_program_type_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        billing_service,
        "_begin_command",
        lambda *args, **kwargs: ("f" * 64, None),
    )
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    actor_id = uuid4()
    context = SimpleNamespace(
        organization=SimpleNamespace(id=organization_id),
        user=SimpleNamespace(id=actor_id),
    )
    with Session(engine) as session:
        family, guardian, child = _family_child(
            session,
            organization_id,
            "Canonical Guard",
        )
        account = _account(session, organization_id, family, guardian)
        enrollment = _enrollment(session, organization_id, child)
        program = _program_for_enrollment(
            session,
            organization_id,
            enrollment,
            "Canonical Guard",
        )
        rate_plan, rate_version = _rate(
            session,
            organization_id,
            enrollment,
            child,
            code="CANONICAL-GUARD",
        )
        facility = session.get(Facility, program.facility_id)
        assert facility is not None
        session.commit()

        facility.status = "inactive"
        new_rate = PublishRatePlanVersionCommand(
            client_operation_id=uuid4(),
            code="NEW-GUARDED",
            name="New guarded rate",
            program_type="daycare",
            charge_kind="core_care",
            age_group=child.age_group,
            facility_id=facility.id,
            program_id=program.id,
            billing_unit="monthly_period",
            unit_amount_minor=100_000,
            effective_from=AS_OF_DATE,
        )
        with pytest.raises(HTTPException) as inactive_rate:
            billing_service.publish_rate_version(session, context, new_rate)
        assert inactive_rate.value.status_code == 422
        assert inactive_rate.value.detail == {"code": "billing_facility_inactive"}

        facility.status = "active"
        program.program_type = "out_of_school_care"
        revision = PublishRatePlanVersionCommand(
            client_operation_id=uuid4(),
            rate_plan_id=rate_plan.id,
            expected_latest_version_id=rate_version.id,
            expected_latest_version_number=rate_version.version_number,
            billing_unit="monthly_period",
            unit_amount_minor=100_000,
            effective_from=AS_OF_DATE + timedelta(days=1),
        )
        with pytest.raises(HTTPException) as type_drift:
            billing_service.publish_rate_version(session, context, revision)
        assert type_drift.value.status_code == 422
        assert type_drift.value.detail == {
            "code": "billing_rate_program_scope_mismatch"
        }

        program.program_type = "daycare"
        facility.status = "inactive"
        agreement = EstablishBillingAgreementCommand(
            client_operation_id=uuid4(),
            account_id=account.id,
            child_id=child.id,
            enrollment_id=enrollment.id,
            rate_plan_version_id=rate_version.id,
            billing_frequency="monthly",
            effective_from=AS_OF_DATE,
            family_amount_minor_per_unit=rate_version.unit_amount_minor,
            funding_amount_minor_per_unit=0,
            reviewed=True,
        )
        with pytest.raises(HTTPException) as inactive_agreement:
            billing_service.establish_agreement(session, context, agreement)
        assert inactive_agreement.value.status_code == 422
        assert inactive_agreement.value.detail == {
            "code": "billing_facility_inactive"
        }
    engine.dispose()


def _attest_sources(
    session: Session,
    organization_id: UUID,
    *sources: tuple[str, UUID],
) -> None:
    actor_id = uuid4()
    for source_type, source_id in (
        ("organization", organization_id),
        *sources,
    ):
        session.add(
            BillingSandboxSourceAttestation(
                id=uuid4(),
                organization_id=organization_id,
                source_type=source_type,
                source_id=source_id,
                marker="TEST_SYNTHETIC_ONLY",
                reason_code="disposable_test_fixture",
                attested_by_user_id=actor_id,
                attested_at=datetime.now(UTC),
            )
        )


def test_sandbox_groups_require_command_level_source_attestations() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        account_family, _account_guardian, account_child = _family_child(
            session, organization_id, "Unattested Payer"
        )

        rate_family, rate_guardian, rate_child = _family_child(
            session, organization_id, "Unattested Rate"
        )
        _account(session, organization_id, rate_family, rate_guardian)
        rate_enrollment = _enrollment(session, organization_id, rate_child)
        _program_for_enrollment(
            session,
            organization_id,
            rate_enrollment,
            "Unattested Rate",
        )

        agreement_family, agreement_guardian, agreement_child = _family_child(
            session, organization_id, "Unattested Agreement"
        )
        _account(session, organization_id, agreement_family, agreement_guardian)
        agreement_enrollment = _enrollment(
            session, organization_id, agreement_child
        )
        _program_for_enrollment(
            session,
            organization_id,
            agreement_enrollment,
            "Unattested Agreement",
        )
        _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="UNATTESTED-AGREEMENT",
        )
        _attest_sources(
            session,
            organization_id,
            ("family", account_family.id),
            ("child", account_child.id),
            ("family", rate_family.id),
            ("child", rate_child.id),
            ("enrollment", rate_enrollment.id),
            ("family", agreement_family.id),
            ("child", agreement_child.id),
            ("enrollment", agreement_enrollment.id),
        )
        session.commit()
        batch = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=True,
        )
        assert len(batch.groups) == 3
        assert {group.wave for group in batch.groups} == {"manual_review"}
        assert {group.block_code for group in batch.groups} == {
            "billing_payer_source_attestation_missing",
            "billing_rate_source_attestation_missing",
            "billing_agreement_source_attestation_missing",
        }
        assert all(not group.payer_options for group in batch.groups)
    engine.dispose()


def test_preview_normalization_is_deterministic_and_never_emits_financial_commands() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        account_family, _account_guardian, _account_child = _family_child(
            session, organization_id, "Account"
        )
        rate_family, rate_guardian, rate_child = _family_child(
            session, organization_id, "Rate"
        )
        _account(session, organization_id, rate_family, rate_guardian)
        rate_enrollment = _enrollment(session, organization_id, rate_child)
        _program_for_enrollment(session, organization_id, rate_enrollment, "Rate")
        future_plan, future_version = _rate(
            session,
            organization_id,
            rate_enrollment,
            rate_child,
            code="FUTURE-RATE",
        )
        future_version.effective_from = AS_OF_DATE + timedelta(days=10)
        agreement_family, agreement_guardian, agreement_child = _family_child(
            session, organization_id, "Agreement"
        )
        _account(session, organization_id, agreement_family, agreement_guardian)
        agreement_enrollment = _enrollment(
            session, organization_id, agreement_child
        )
        _program_for_enrollment(
            session, organization_id, agreement_enrollment, "Agreement"
        )
        _plan, _version = _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="AGREEMENT-PREVIEW",
        )
        session.commit()
        batch = build_billing_readiness_batch_snapshot(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            source_attestations_required=False,
        )

    account_group = next(
        group for group in batch.groups if group.family_id == account_family.id
    )
    rate_group = next(group for group in batch.groups if group.wave == "rate_plan")
    agreement_group = next(
        group for group in batch.groups if group.wave == "agreement"
    )
    selections = [
        (
            account_group,
            BillingReadinessBatchPreviewSelection(
                group_id=account_group.group_id,
                client_operation_id=uuid4(),
                payer_guardian_id=account_group.payer_options[0].guardian_id,
            ),
            "account_payer",
        ),
        (
            rate_group,
            BillingReadinessBatchPreviewSelection(
                group_id=rate_group.group_id,
                client_operation_id=uuid4(),
                code="RATE-NEW",
                name="New core care",
                billing_unit="monthly_period",
                unit_amount_minor=125_000,
                effective_from=AS_OF_DATE,
            ),
            "rate_plan",
        ),
        (
            agreement_group,
            BillingReadinessBatchPreviewSelection(
                group_id=agreement_group.group_id,
                client_operation_id=uuid4(),
                billing_frequency="monthly",
                family_amount_minor_per_unit=100_000,
                effective_from=AS_OF_DATE,
            ),
            "agreement",
        ),
    ]
    allowed = {
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
    }
    for group, selection, wave in selections:
        first, block = _billing_batch_command_for_selection(
            group, selection, wave
        )
        repeat, repeat_block = _billing_batch_command_for_selection(
            group, selection, wave
        )
        assert block is None
        assert repeat_block is None
        assert first == repeat
        assert first["command_type"] in allowed
        assert first["request_hash"] == repeat["request_hash"]
        assert len(first["request_hash"]) == 64
        assert first["request_payload"]["client_operation_id"] == str(
            selection.client_operation_id
        )
    invalid_agreement = BillingReadinessBatchPreviewSelection(
        group_id=agreement_group.group_id,
        client_operation_id=uuid4(),
        billing_frequency="weekly",
        family_amount_minor_per_unit=99_999,
        effective_from=AS_OF_DATE,
    )
    invalid_intent, invalid_block = _billing_batch_command_for_selection(
        agreement_group,
        invalid_agreement,
        "agreement",
    )
    assert invalid_intent is None
    assert invalid_block.code == (
        "billing_readiness_batch_rate_unit_frequency_mismatch"
    )
    amount_mismatch = invalid_agreement.model_copy(
        update={"billing_frequency": "monthly"}
    )
    invalid_intent, invalid_block = _billing_batch_command_for_selection(
        agreement_group,
        amount_mismatch,
        "agreement",
    )
    assert invalid_intent is None
    assert invalid_block.code == (
        "billing_readiness_batch_rate_portions_do_not_balance"
    )
    colliding_rate = selections[1][1].model_copy(
        update={"code": "AGREEMENT-PREVIEW"}
    )
    invalid_intent, invalid_block = _billing_batch_command_for_selection(
        rate_group,
        colliding_rate,
        "rate_plan",
        reserved_rate_codes=batch.reserved_rate_codes,
    )
    assert invalid_intent is None
    assert invalid_block.code == "billing_readiness_batch_rate_code_unavailable"
    future_revision = selections[1][1].model_copy(
        update={
            "rate_plan_id": future_plan.id,
            "code": None,
            "name": None,
            "effective_from": AS_OF_DATE + timedelta(days=11),
        }
    )
    invalid_intent, invalid_block = _billing_batch_command_for_selection(
        rate_group,
        future_revision,
        "rate_plan",
        reserved_rate_codes=batch.reserved_rate_codes,
        as_of_date=AS_OF_DATE,
    )
    assert invalid_intent is None
    assert invalid_block.code == (
        "billing_readiness_batch_rate_revision_cannot_resolve_current_gap"
    )
    expired_rate = selections[1][1].model_copy(
        update={
            "effective_from": AS_OF_DATE - timedelta(days=10),
            "effective_until": AS_OF_DATE - timedelta(days=1),
        }
    )
    invalid_intent, invalid_block = _billing_batch_command_for_selection(
        rate_group,
        expired_rate,
        "rate_plan",
        reserved_rate_codes=batch.reserved_rate_codes,
        as_of_date=AS_OF_DATE,
    )
    assert invalid_intent is None
    assert invalid_block.code == "billing_readiness_batch_rate_not_current"
    for invalid_agreement_window in (
        selections[2][1].model_copy(
            update={"effective_from": AS_OF_DATE + timedelta(days=1)}
        ),
        selections[2][1].model_copy(
            update={
                "effective_from": AS_OF_DATE - timedelta(days=10),
                "effective_until": AS_OF_DATE - timedelta(days=1),
            }
        ),
    ):
        invalid_intent, invalid_block = _billing_batch_command_for_selection(
            agreement_group,
            invalid_agreement_window,
            "agreement",
            as_of_date=AS_OF_DATE,
        )
        assert invalid_intent is None
        assert (
            invalid_block.code
            == "billing_readiness_batch_agreement_not_current"
        )
    engine.dispose()


def _migrate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_path


def _settings(
    database_path: Path,
    *,
    billing_mode: str = "disabled",
    organization_ids: list[UUID] | None = None,
) -> Settings:
    values = {
        "_env_file": None,
        "environment": "test",
        "database_type": "sqlite",
        "database_path": database_path,
        "database_name": "caresync",
        "database_read_only": False,
        "enable_advanced_routes": False,
        "billing_mode": billing_mode,
        "jwt_secret": JWT_SECRET,
    }
    if organization_ids:
        if billing_mode == "manual":
            values["billing_manual_organization_ids"] = organization_ids
        else:
            values["billing_sandbox_organization_ids"] = organization_ids
            values["billing_sandbox_target_attestation"] = (
                "DISPOSABLE_CARESYNC_BILLING_SANDBOX"
            )
    return Settings(**values)


def _post(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _register(client: TestClient, suffix: str) -> tuple[dict[str, str], dict]:
    result = _post(
        client,
        "/api/v1/auth/register",
        {},
        {
            "email": f"billing-batch-{suffix}@example.test",
            "password": "secure-password-123",
            "first_name": "Billing",
            "last_name": "Owner",
            "organization_name": f"Billing Batch {suffix}",
        },
    )
    return {"Authorization": f"Bearer {result['access_token']}"}, result


def _create_family_with_child(
    client: TestClient,
    headers: dict[str, str],
    suffix: str,
) -> tuple[dict, dict]:
    family = _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": f"{suffix} Family",
            "primary_guardian": {
                "first_name": suffix,
                "last_name": "Guardian",
                "relationship": "Parent",
                "email": f"{suffix.casefold()}@example.test",
                "cell_phone": "780-555-0101",
            },
        },
    )
    child = _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "first_name": suffix,
            "last_name": "Child",
            "date_of_birth": "2023-01-01",
        },
    )
    return family, child


def _billing_table_counts(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name LIKE 'billing_%' ORDER BY name"
            )
        ]
        return {
            name: int(connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0])
            for name in names
        }


def _insert_direct_family_child(database_path: Path, organization_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    family_id = uuid4().hex
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO families(id,organization_id,name,status,version,photo_consent,"
            "field_trip_consent,emergency_medical_consent,created_at,updated_at) "
            "VALUES (?,?,?,'active',1,0,0,0,?,?)",
            (
                family_id,
                UUID(organization_id).hex,
                "Direct Fact Family",
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO children(id,organization_id,family_id,first_name,last_name,"
            "date_of_birth,is_active,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'2023-01-01',1,1,?,?)",
            (
                uuid4().hex,
                UUID(organization_id).hex,
                family_id,
                "Direct",
                "Child",
                now,
                now,
            ),
        )


def _insert_direct_children(
    database_path: Path,
    *,
    organization_id: str,
    family_id: str,
    count: int,
) -> list[str]:
    now = datetime.now(UTC).isoformat()
    first_names = [f"HiddenSearch{index:02d}" for index in range(count)]
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for first_name in first_names:
            connection.execute(
                "INSERT INTO children(id,organization_id,family_id,first_name,last_name,"
                "date_of_birth,is_active,version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'2023-01-01',1,1,?,?)",
                (
                    uuid4().hex,
                    UUID(organization_id).hex,
                    UUID(family_id).hex,
                    first_name,
                    "Member",
                    now,
                    now,
                ),
            )
    return first_names


def test_endpoints_are_paginated_tenant_scoped_stale_safe_and_write_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    bootstrap = create_app(_settings(database_path))
    with TestClient(bootstrap) as client:
        owner_headers, owner = _register(client, "Owner")
        foreign_headers, foreign = _register(client, "Foreign")
        first_family, _first_child = _create_family_with_child(
            client, owner_headers, "Alpha"
        )
        _create_family_with_child(client, owner_headers, "Beta")
        disabled = client.get(
            "/api/v1/billing/readiness/batch-plan",
            headers=owner_headers,
        )
        assert disabled.status_code == 503
        assert disabled.json()["detail"] == {"code": "billing_ledger_unavailable"}

    hidden_member_names = _insert_direct_children(
        database_path,
        organization_id=owner["user"]["organization_id"],
        family_id=first_family["id"],
        count=30,
    )
    organization_ids = [
        UUID(owner["user"]["organization_id"]),
        UUID(foreign["user"]["organization_id"]),
    ]
    application = create_app(
        _settings(
            database_path,
            billing_mode="manual",
            organization_ids=organization_ids,
        )
    )
    with TestClient(application) as client:
        # SQLite cannot satisfy the private PostgreSQL write attestation, but the
        # read-only planner itself is intentionally usable before activation.
        application.state.billing_ledger_enabled = True
        assert (
            client.get("/api/v1/billing/readiness/batch-plan").status_code
            == 401
        )
        first_page = client.get(
            "/api/v1/billing/readiness/batch-plan?wave=account_payer&limit=1",
            headers=owner_headers,
        )
        assert first_page.status_code == 200, first_page.text
        first_payload = first_page.json()
        assert first_payload["apply_available"] is False
        assert first_payload["manual_activation_required"] is True
        assert first_payload["counts"]["account_payer"] == 2
        assert first_payload["page"] == {
            "offset": 0,
            "limit": 1,
            "returned": 1,
            "total": 2,
            "has_more": True,
            "next_offset": 1,
        }
        token = first_payload["snapshot_token"]
        second_page = client.get(
            "/api/v1/billing/readiness/batch-plan"
            f"?wave=account_payer&limit=1&offset=1&snapshot_token={token}",
            headers=owner_headers,
        )
        assert second_page.status_code == 200, second_page.text
        assert second_page.json()["snapshot_token"] == token
        searched = client.get(
            "/api/v1/billing/readiness/batch-plan?query=alpha",
            headers=owner_headers,
        )
        assert searched.status_code == 200, searched.text
        assert searched.json()["page"]["total"] == 1
        group = (
            first_payload["items"][0]
            if first_payload["items"][0]["family_id"] == first_family["id"]
            else second_page.json()["items"][0]
        )
        assert group["affected_count"] == 31
        assert len(group["affected_children"]) == 25
        assert group["affected_children_truncated"] is True
        visible_child_names = {
            child["child_name"] for child in group["affected_children"]
        }
        hidden_member_name = next(
            name
            for name in hidden_member_names
            if all(name not in child_name for child_name in visible_child_names)
        )
        hidden_member_search = client.get(
            "/api/v1/billing/readiness/batch-plan",
            headers=owner_headers,
            params={"query": hidden_member_name},
        )
        assert hidden_member_search.status_code == 200, hidden_member_search.text
        hidden_member_payload = hidden_member_search.json()
        assert hidden_member_payload["page"]["total"] == 1
        assert hidden_member_payload["items"][0]["group_id"] == group["group_id"]
        assert all(
            hidden_member_name not in child["child_name"]
            for child in hidden_member_payload["items"][0]["affected_children"]
        )
        payer_id = group["payer_options"][0]["guardian_id"]
        operation_id = str(uuid4())
        preview_request = {
            "snapshot_token": token,
            "wave": "account_payer",
            "selections": [
                {
                    "group_id": group["group_id"],
                    "client_operation_id": operation_id,
                    "payer_guardian_id": payer_id,
                }
            ],
        }
        before = _billing_table_counts(database_path)
        preview = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=owner_headers,
            json=preview_request,
        )
        assert preview.status_code == 200, preview.text
        preview_payload = preview.json()
        assert preview_payload["read_only"] is True
        assert preview_payload["apply_available"] is False
        assert preview_payload["manual_activation_required"] is True
        assert preview_payload["blocked"] == []
        assert [intent["sequence"] for intent in preview_payload["intents"]] == [1]
        intent = preview_payload["intents"][0]
        assert intent["command_type"] == "account_open"
        assert intent["client_operation_id"] == operation_id
        assert intent["prepare_request"] == {
            "command_type": "account_open",
            "request_payload": intent["request_payload"],
        }
        assert _billing_table_counts(database_path) == before

        repeated = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=owner_headers,
            json=preview_request,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["intents"] == preview_payload["intents"]
        assert _billing_table_counts(database_path) == before

        canonical_groups = [
            first_payload["items"][0],
            second_page.json()["items"][0],
        ]
        reversed_preview = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=owner_headers,
            json={
                "snapshot_token": token,
                "wave": "account_payer",
                "selections": [
                    {
                        "group_id": candidate["group_id"],
                        "client_operation_id": str(uuid4()),
                        "payer_guardian_id": candidate["payer_options"][0][
                            "guardian_id"
                        ],
                    }
                    for candidate in reversed(canonical_groups)
                ],
            },
        )
        assert reversed_preview.status_code == 200, reversed_preview.text
        assert [
            intent["group_id"]
            for intent in reversed_preview.json()["intents"]
        ] == [candidate["group_id"] for candidate in canonical_groups]
        assert [intent["sequence"] for intent in reversed_preview.json()["intents"]] == [
            1,
            2,
        ]
        assert _billing_table_counts(database_path) == before

        foreign_plan = client.get(
            "/api/v1/billing/readiness/batch-plan",
            headers=foreign_headers,
        )
        assert foreign_plan.status_code == 200, foreign_plan.text
        assert foreign_plan.json()["counts"]["total"] == 0
        foreign_preview = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=foreign_headers,
            json=preview_request,
        )
        assert foreign_preview.status_code == 409
        assert foreign_preview.json()["detail"]["code"] == (
            "billing_readiness_batch_snapshot_advanced"
        )

        sequence = first_payload["data_through_realtime_sequence"]
        _insert_direct_family_child(
            database_path,
            owner["user"]["organization_id"],
        )
        stale = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=owner_headers,
            json=preview_request,
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["detail"] == {
            "code": "billing_readiness_batch_snapshot_advanced",
            "restart_required": True,
            "data_through_realtime_sequence": sequence,
        }


def test_preview_requires_manage_permission_and_rejects_malformed_wave_inputs(
) -> None:
    with pytest.raises(ValidationError, match="payer_guardian_id"):
        PreviewBillingReadinessBatchCommand.model_validate(
            {
                "snapshot_token": "0" * 64,
                "wave": "account_payer",
                "selections": [
                    {
                        "group_id": "1" * 64,
                        "client_operation_id": str(uuid4()),
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="new rate plans require code and name"):
        PreviewBillingReadinessBatchCommand.model_validate(
            {
                "snapshot_token": "0" * 64,
                "wave": "rate_plan",
                "selections": [
                    {
                        "group_id": "1" * 64,
                        "client_operation_id": str(uuid4()),
                        "billing_unit": "monthly_period",
                        "unit_amount_minor": 100_000,
                        "effective_from": AS_OF_DATE.isoformat(),
                    }
                ],
            }
        )

    dependency = require_billing_permission("billing:manage")
    for role in (
        SimpleNamespace(key="owner", permissions=["billing:read"]),
        SimpleNamespace(key="educator", permissions=["billing:manage"]),
    ):
        with pytest.raises(HTTPException) as caught:
            dependency(SimpleNamespace(role=role))
        assert caught.value.status_code == 403
        assert caught.value.detail == {"code": "billing_permission_required"}
