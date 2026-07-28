"""Portable contract proofs for connected enrollment and family billing projections."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.api.basic.billing import require_billing_permission
from app.basic.billing_projections import (
    BillingProjectionIntegrityError,
    billing_projection_snapshot,
    build_billing_readiness,
    build_family_finance_summary,
)
from app.basic.billing_schemas import (
    BillingFamilyFinanceSummaryResponse,
    BillingReadinessResponse,
)
from app.basic.models import (
    BasicBase,
    BillingAccount,
    BillingAccountPayerVersion,
    BillingAgreement,
    BillingAgreementVersion,
    BillingAllocation,
    BillingCredit,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPayment,
    BillingRatePlan,
    BillingRatePlanVersion,
    Child,
    Enrollment,
    Family,
    Guardian,
)
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
AS_OF_DATE = date(2026, 7, 22)
GENERATED_AT = datetime(2026, 7, 22, 18, 0, tzinfo=UTC)
JWT_SECRET = "billing-projection-endpoint-test-secret-at-least-thirty-two-bytes"


def _effect() -> dict[str, object]:
    return {"client_operation_id": uuid4(), "request_hash": uuid4().hex * 2}


def _family_child(
    session: Session,
    organization_id: UUID,
    label: str,
    *,
    active: bool = True,
    family_status: str = "active",
) -> tuple[Family, Guardian, Child]:
    family = Family(
        id=uuid4(),
        organization_id=organization_id,
        name=f"{label} Family",
        status=family_status,
        version=1,
    )
    guardian = Guardian(
        id=uuid4(),
        organization_id=organization_id,
        family_id=family.id,
        first_name=label,
        last_name="Payer",
        relationship="Parent",
        email=f"{label.lower()}@example.test",
        cell_phone="780-555-0101",
        is_primary=True,
        authorized_pickup=True,
    )
    child = Child(
        id=uuid4(),
        organization_id=organization_id,
        family_id=family.id,
        first_name=label,
        last_name="Child",
        date_of_birth=date(2022, 1, 1),
        age_group="preschool",
        is_active=active,
        version=1,
    )
    session.add_all([family, guardian, child])
    return family, guardian, child


def _account(
    session: Session,
    organization_id: UUID,
    family: Family,
    guardian: Guardian,
    *,
    with_payer_version: bool = True,
) -> BillingAccount:
    account = BillingAccount(
        id=uuid4(),
        organization_id=organization_id,
        family_id=family.id,
        payer_guardian_id=guardian.id,
        account_number=f"MANUAL-{uuid4().hex[:10].upper()}",
        status="open",
        currency="CAD",
        opened_by_user_id=uuid4(),
        opened_at=GENERATED_AT,
        **_effect(),
    )
    session.add(account)
    if with_payer_version:
        session.add(
            BillingAccountPayerVersion(
                id=uuid4(),
                organization_id=organization_id,
                billing_account_id=account.id,
                family_id=family.id,
                payer_guardian_id=guardian.id,
                version_number=1,
                assigned_by_user_id=account.opened_by_user_id,
                assigned_at=GENERATED_AT,
                **_effect(),
            )
        )
    return account


def _enrollment(
    session: Session,
    organization_id: UUID,
    child: Child,
) -> Enrollment:
    enrollment = Enrollment(
        id=uuid4(),
        organization_id=organization_id,
        facility_id=uuid4(),
        child_id=child.id,
        program_id=uuid4(),
        room_id=uuid4(),
        placement_effective_date=date(2026, 1, 1),
        start_date=date(2026, 1, 1),
        end_date=None,
        status="active",
        version=1,
    )
    session.add(enrollment)
    return enrollment


def _rate(
    session: Session,
    organization_id: UUID,
    enrollment: Enrollment,
    child: Child,
    *,
    code: str,
) -> tuple[BillingRatePlan, BillingRatePlanVersion]:
    plan = BillingRatePlan(
        id=uuid4(),
        organization_id=organization_id,
        code=code,
        name=f"{code} Core care",
        program_type="daycare",
        charge_kind="core_care",
        age_group=child.age_group,
        facility_id=enrollment.facility_id,
        program_id=enrollment.program_id,
        created_by_user_id=uuid4(),
        created_at=GENERATED_AT,
        **_effect(),
    )
    version = BillingRatePlanVersion(
        id=uuid4(),
        organization_id=organization_id,
        rate_plan_id=plan.id,
        version_number=1,
        billing_unit="monthly_period",
        unit_amount_minor=100_000,
        tax_rate_basis_points=0,
        currency="CAD",
        effective_from=date(2026, 1, 1),
        effective_until=None,
        description="Core care",
        status="published",
        published_by_user_id=plan.created_by_user_id,
        published_at=GENERATED_AT,
        **_effect(),
    )
    session.add_all([plan, version])
    return plan, version


def _agreement(
    session: Session,
    organization_id: UUID,
    family: Family,
    child: Child,
    account: BillingAccount,
    enrollment: Enrollment,
    rate_version: BillingRatePlanVersion | None,
    *,
    enrollment_id: UUID | None = None,
    with_version: bool = True,
) -> BillingAgreement:
    agreement = BillingAgreement(
        id=uuid4(),
        organization_id=organization_id,
        billing_account_id=account.id,
        family_id=family.id,
        child_id=child.id,
        enrollment_id=enrollment.id if enrollment_id is None else enrollment_id,
        facility_id=enrollment.facility_id,
        created_by_user_id=account.opened_by_user_id,
        created_at=GENERATED_AT,
        **_effect(),
    )
    session.add(agreement)
    if with_version and rate_version is not None:
        session.add(
            BillingAgreementVersion(
                id=uuid4(),
                organization_id=organization_id,
                agreement_id=agreement.id,
                rate_plan_version_id=rate_version.id,
                version_number=1,
                billing_frequency="monthly",
                family_amount_minor_per_unit=rate_version.unit_amount_minor,
                funding_amount_minor_per_unit=0,
                effective_from=date(2026, 1, 1),
                effective_until=None,
                review_status="reviewed",
                reviewed_by_user_id=account.opened_by_user_id,
                reviewed_at=GENERATED_AT,
                **_effect(),
            )
        )
    return agreement


def test_readiness_projects_every_deterministic_state_and_safe_action() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        pending_family, _pending_guardian, pending_child = _family_child(
            session,
            organization_id,
            "Pending",
            family_status="pending",
        )
        _family_child(session, organization_id, "Account")

        payer_family, payer_guardian, _payer_child = _family_child(
            session, organization_id, "Payer"
        )
        _account(
            session,
            organization_id,
            payer_family,
            payer_guardian,
            with_payer_version=False,
        )

        enrollment_family, enrollment_guardian, _enrollment_child = _family_child(
            session, organization_id, "Enrollment"
        )
        _account(session, organization_id, enrollment_family, enrollment_guardian)

        rate_family, rate_guardian, rate_child = _family_child(
            session, organization_id, "Rate"
        )
        _account(session, organization_id, rate_family, rate_guardian)
        _enrollment(session, organization_id, rate_child)

        agreement_family, agreement_guardian, agreement_child = _family_child(
            session, organization_id, "Agreement"
        )
        _account(session, organization_id, agreement_family, agreement_guardian)
        agreement_enrollment = _enrollment(session, organization_id, agreement_child)
        _rate(
            session,
            organization_id,
            agreement_enrollment,
            agreement_child,
            code="AGREEMENT",
        )

        ready_family, ready_guardian, ready_child = _family_child(
            session, organization_id, "Ready"
        )
        ready_account = _account(session, organization_id, ready_family, ready_guardian)
        ready_enrollment = _enrollment(session, organization_id, ready_child)
        _ready_plan, ready_rate = _rate(
            session,
            organization_id,
            ready_enrollment,
            ready_child,
            code="READY",
        )
        _agreement(
            session,
            organization_id,
            ready_family,
            ready_child,
            ready_account,
            ready_enrollment,
            None,
            enrollment_id=uuid4(),
            with_version=False,
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

        conflict_family, conflict_guardian, conflict_child = _family_child(
            session, organization_id, "Conflict"
        )
        conflict_account = _account(
            session, organization_id, conflict_family, conflict_guardian
        )
        conflict_enrollment = _enrollment(session, organization_id, conflict_child)
        _agreement(
            session,
            organization_id,
            conflict_family,
            conflict_child,
            conflict_account,
            conflict_enrollment,
            None,
            enrollment_id=uuid4(),
            with_version=False,
        )

        review_family, review_guardian, review_child = _family_child(
            session, organization_id, "Review"
        )
        _account(session, organization_id, review_family, review_guardian)
        review_enrollment = _enrollment(session, organization_id, review_child)
        _rate(
            session,
            organization_id,
            review_enrollment,
            review_child,
            code="REVIEW-A",
        )
        _rate(
            session,
            organization_id,
            review_enrollment,
            review_child,
            code="REVIEW-B",
        )
        session.commit()

        response = build_billing_readiness(
            session,
            organization_id=organization_id,
            as_of_date=AS_OF_DATE,
            generated_at=GENERATED_AT,
        )

    engine.dispose()
    validated = BillingReadinessResponse.model_validate(response.model_dump())
    assert validated.counts.model_dump() == {
        "total": 9,
        "setup_ready": 1,
        "needs_account": 1,
        "needs_payer": 1,
        "needs_current_enrollment": 1,
        "needs_rate_plan": 1,
        "needs_agreement": 1,
        "agreement_scope_conflict": 1,
        "needs_review": 2,
    }
    by_name = {item.child_name: item for item in validated.items}
    assert by_name["Conflict Child"].reason_codes == [
        "billing_agreement_enrollment_conflict"
    ]
    assert by_name["Review Child"].reason_codes == ["multiple_applicable_rate_plans"]
    assert by_name["Ready Child"].reason_codes == ["billing_setup_ready"]
    assert by_name["Pending Child"].reason_codes == ["billing_family_not_active"]
    assert by_name["Pending Child"].action_path == (
        f"/families/{pending_family.id}?focus=family-status"
    )
    assert by_name["Pending Child"].child_id == pending_child.id
    assert all(item.action_path.startswith("/") for item in validated.items)
    assert all(
        "://" not in item.action_path and "#" not in item.action_path
        for item in validated.items
    )


def _add_invoice_facts(
    session: Session,
    organization_id: UUID,
    family: Family,
    guardian: Guardian,
    account: BillingAccount,
    active_child: Child,
    inactive_child: Child,
) -> None:
    invoice = BillingInvoice(
        id=uuid4(),
        organization_id=organization_id,
        billing_account_id=account.id,
        family_id=family.id,
        billing_account_payer_version_id=session.query(BillingAccountPayerVersion.id)
        .filter(BillingAccountPayerVersion.billing_account_id == account.id)
        .scalar(),
        payer_guardian_id=guardian.id,
        invoice_number="MANUAL-INV-202607-TEST",
        status="issued",
        currency="CAD",
        issue_date=date(2026, 7, 1),
        due_date=date(2026, 7, 15),
        service_period_start=date(2026, 7, 1),
        service_period_end=date(2026, 7, 31),
        family_name_snapshot=family.name,
        payer_name_snapshot=f"{guardian.first_name} {guardian.last_name}",
        payer_email_snapshot=guardian.email,
        payer_address_snapshot=None,
        gross_subtotal_minor=10_000,
        funding_minor=0,
        subtotal_minor=10_000,
        tax_minor=0,
        total_minor=10_000,
        issued_by_user_id=account.opened_by_user_id,
        issued_at=GENERATED_AT,
        **_effect(),
    )
    payment = BillingPayment(
        id=uuid4(),
        organization_id=organization_id,
        billing_account_id=account.id,
        family_id=family.id,
        payer_guardian_id=guardian.id,
        status="settled",
        method="e_transfer",
        currency="CAD",
        amount_minor=5_000,
        external_reference="TRANSFER-TEST",
        payer_name_snapshot=f"{guardian.first_name} {guardian.last_name}",
        payer_email_snapshot=guardian.email,
        operator_confirmation_note=None,
        memo=None,
        received_at=GENERATED_AT,
        recorded_by_user_id=account.opened_by_user_id,
        recorded_at=GENERATED_AT,
        **_effect(),
    )
    session.add_all([invoice, payment])
    for line_number, child, amount in (
        (1, active_child, 6_000),
        (2, inactive_child, 4_000),
    ):
        session.add(
            BillingInvoiceLine(
                id=uuid4(),
                organization_id=organization_id,
                invoice_id=invoice.id,
                agreement_version_id=uuid4(),
                child_id=child.id,
                line_number=line_number,
                description_snapshot="Core care",
                child_name_snapshot=f"{child.first_name} {child.last_name}",
                rate_plan_name_snapshot="Core care",
                billing_unit_snapshot="monthly_period",
                service_period_start=date(2026, 7, 1),
                service_period_end=date(2026, 7, 31),
                quantity=1,
                gross_unit_amount_minor=amount,
                funding_unit_amount_minor=0,
                unit_amount_minor=amount,
                tax_rate_basis_points=0,
                gross_subtotal_minor=amount,
                funding_minor=0,
                subtotal_minor=amount,
                tax_minor=0,
                total_minor=amount,
                **_effect(),
            )
        )
    session.add_all(
        [
            BillingAllocation(
                id=uuid4(),
                organization_id=organization_id,
                billing_account_id=account.id,
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount_minor=3_000,
                allocated_by_user_id=account.opened_by_user_id,
                allocated_at=GENERATED_AT,
                **_effect(),
            ),
            BillingCredit(
                id=uuid4(),
                organization_id=organization_id,
                billing_account_id=account.id,
                invoice_id=invoice.id,
                status="issued",
                currency="CAD",
                amount_minor=1_000,
                reason_code="adjustment",
                note=None,
                issued_by_user_id=account.opened_by_user_id,
                issued_at=GENERATED_AT,
                **_effect(),
            ),
        ]
    )


def test_family_summary_keeps_settlement_at_family_invoice_scope() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        family, guardian, active_child = _family_child(
            session, organization_id, "Finance"
        )
        inactive_child = Child(
            id=uuid4(),
            organization_id=organization_id,
            family_id=family.id,
            first_name="Historical",
            last_name="Child",
            date_of_birth=date(2018, 1, 1),
            age_group="school_age",
            is_active=False,
            version=1,
        )
        session.add(inactive_child)
        account = _account(session, organization_id, family, guardian)
        _enrollment(session, organization_id, active_child)
        session.flush()
        _add_invoice_facts(
            session,
            organization_id,
            family,
            guardian,
            account,
            active_child,
            inactive_child,
        )
        session.commit()
        summary = build_family_finance_summary(
            session,
            organization_id=organization_id,
            family_id=family.id,
            as_of_date=AS_OF_DATE,
            generated_at=GENERATED_AT,
        )

    engine.dispose()
    assert summary is not None
    validated = BillingFamilyFinanceSummaryResponse.model_validate(summary.model_dump())
    assert validated.invoice_summary.model_dump() == {
        "invoice_count": 1,
        "open_invoice_count": 1,
        "settled_invoice_count": 0,
        "total_minor": 10_000,
        "allocated_minor": 3_000,
        "credits_minor": 1_000,
        "outstanding_minor": 6_000,
    }
    assert validated.payment_summary.model_dump() == {
        "payment_count": 1,
        "recorded_minor": 5_000,
        "allocated_minor": 3_000,
        "unapplied_minor": 2_000,
    }
    children = {child.child_name: child for child in validated.children}
    assert children["Finance Child"].charge_attribution.total_minor == 6_000
    assert children["Historical Child"].charge_attribution.total_minor == 4_000
    assert children["Historical Child"].readiness_status is None
    serialized_child = validated.children[0].model_dump()
    assert "paid_minor" not in serialized_child
    assert "outstanding_minor" not in serialized_child
    assert "settled_minor" not in serialized_child


def test_family_summary_fails_closed_when_invoice_settlement_is_overapplied() -> None:
    engine = create_engine("sqlite:///:memory:")
    BasicBase.metadata.create_all(engine)
    organization_id = uuid4()
    with Session(engine) as session:
        family, guardian, child = _family_child(session, organization_id, "Integrity")
        account = _account(session, organization_id, family, guardian)
        session.flush()
        _add_invoice_facts(
            session,
            organization_id,
            family,
            guardian,
            account,
            child,
            child,
        )
        allocation = session.query(BillingAllocation).one()
        allocation.amount_minor = 11_000
        payment = session.query(BillingPayment).one()
        payment.amount_minor = 12_000
        session.commit()
        try:
            build_family_finance_summary(
                session,
                organization_id=organization_id,
                family_id=family.id,
                as_of_date=AS_OF_DATE,
            )
        except BillingProjectionIntegrityError as error:
            assert error.code == "billing_invoice_settlement_overapplied"
        else:
            raise AssertionError("overapplied invoice settlement was not rejected")
    engine.dispose()


def _settings(
    database_path: Path,
    organization_ids: list[UUID],
) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        billing_mode="sandbox",
        billing_sandbox_target_attestation="DISPOSABLE_CARESYNC_BILLING_SANDBOX",
        billing_sandbox_organization_ids=organization_ids,
        jwt_secret=JWT_SECRET,
    )


def _migrate(tmp_path: Path, monkeypatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_path


def _post(client: TestClient, path: str, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _register(client: TestClient, suffix: str) -> tuple[dict[str, str], dict]:
    auth = _post(
        client,
        "/api/v1/auth/register",
        {},
        {
            "email": f"projection-{suffix}@example.test",
            "password": "secure-password-123",
            "first_name": "Billing",
            "last_name": "Owner",
            "organization_name": f"Projection {suffix}",
        },
    )
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth


def _create_family(client: TestClient, headers: dict[str, str], suffix: str) -> dict:
    return _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": f"Projection Family {suffix}",
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Payer",
                "relationship": "Parent",
                "email": f"payer-{suffix}@example.test",
                "cell_phone": "780-555-0101",
            },
        },
    )


def _sqlite_uuid(value: str | UUID) -> str:
    return UUID(str(value)).hex


def _attest(
    database_path: Path,
    organization_id: str,
    actor_user_id: str,
    family_id: str,
) -> None:
    now = GENERATED_AT.isoformat()
    with sqlite3.connect(database_path) as connection:
        for source_type, source_id in (
            ("organization", organization_id),
            ("family", family_id),
        ):
            connection.execute(
                "INSERT INTO billing_sandbox_source_attestations "
                "(id,organization_id,source_type,source_id,marker,reason_code,"
                "attested_by_user_id,attested_at) VALUES "
                "(?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    _sqlite_uuid(organization_id),
                    source_type,
                    _sqlite_uuid(source_id),
                    "TEST_SYNTHETIC_ONLY",
                    "disposable_test_fixture",
                    _sqlite_uuid(actor_user_id),
                    now,
                ),
            )


def test_projection_endpoints_are_authenticated_tenant_scoped_and_permission_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    bootstrap = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret=JWT_SECRET,
    )
    with TestClient(create_app(bootstrap)) as client:
        owner_headers, owner = _register(client, "owner")
        foreign_headers, foreign = _register(client, "foreign")
        family = _create_family(client, owner_headers, "owner")
    _attest(
        database_path,
        owner["user"]["organization_id"],
        owner["user"]["id"],
        family["id"],
    )
    organization_ids = [
        UUID(owner["user"]["organization_id"]),
        UUID(foreign["user"]["organization_id"]),
    ]
    application = create_app(_settings(database_path, organization_ids))
    family_path = f"/api/v1/billing/families/{family['id']}/summary"
    with TestClient(application) as client:
        assert client.get("/api/v1/billing/readiness").status_code == 401

        readiness = client.get("/api/v1/billing/readiness", headers=owner_headers)
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["counts"]["total"] == 0

        summary = client.get(family_path, headers=owner_headers)
        assert summary.status_code == 200, summary.text
        assert summary.json()["family"]["id"] == family["id"]
        assert summary.json()["account"] is None
        assert summary.json()["invoice_summary"]["outstanding_minor"] == 0

        foreign_summary = client.get(family_path, headers=foreign_headers)
        assert foreign_summary.status_code == 404, foreign_summary.text
        assert foreign_summary.json()["detail"] == {"code": "billing_family_not_found"}



def test_projection_read_permission_requires_both_leadership_and_literal_permission() -> None:
    dependency = require_billing_permission("billing:read")
    for role in (
        SimpleNamespace(key="owner", permissions=[]),
        SimpleNamespace(key="educator", permissions=["billing:read"]),
    ):
        context = SimpleNamespace(role=role)
        with pytest.raises(HTTPException) as caught:
            dependency(context)
        assert caught.value.status_code == 403
        assert caught.value.detail == {"code": "billing_permission_required"}


def test_projection_snapshot_is_repeatable_read_only_tenant_bound_and_rollback_only() -> None:
    calls: list[object] = []

    class Snapshot:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def __init__(self) -> None:
            self.info: dict[str, object] = {}

        def connection(self, *, execution_options):
            calls.append(("connection", execution_options))
            return self

        def execute(self, statement, parameters=None):
            calls.append(("execute", str(statement), parameters))

        def rollback(self):
            calls.append("rollback")

        def close(self):
            calls.append("close")

    snapshot = Snapshot()
    database = SimpleNamespace(session_factory=lambda: snapshot)
    user_id = uuid4()
    organization_id = uuid4()
    with billing_projection_snapshot(
        database,
        user_id=user_id,
        organization_id=organization_id,
    ) as yielded:
        assert yielded is snapshot
        assert snapshot.info["rls_user_id"] == user_id

    assert calls[0] == (
        "connection",
        {"isolation_level": "REPEATABLE READ"},
    )
    executed_sql = [call[1] for call in calls if isinstance(call, tuple) and call[0] == "execute"]
    assert executed_sql[0] == "SET TRANSACTION READ ONLY"
    assert sum("set_config" in value for value in executed_sql) == 2
    assert calls[-2:] == ["rollback", "close"]
