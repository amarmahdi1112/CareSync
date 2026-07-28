"""Coherent enrollment-to-billing and family-finance read projections.

These projections never infer payment settlement at child scope. Payments and
credits settle family invoices; child totals below are invoice-line charge
attribution only.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.basic.billing_schemas import (
    BillingChildChargeAttribution,
    BillingFamilyAccountResponse,
    BillingFamilyChildFinanceResponse,
    BillingFamilyFinanceSummaryResponse,
    BillingFamilyIdentityResponse,
    BillingFamilyInvoiceSummary,
    BillingFamilyPaymentSummary,
    BillingReadinessCounts,
    BillingReadinessItem,
    BillingReadinessResponse,
    BillingReadinessStatus,
)
from app.basic.childcare_commands import safe_action_route
from app.basic.models import (
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
    BillingSandboxSourceAttestation,
    Child,
    Enrollment,
    Family,
    Guardian,
    RealtimeEvent,
)
from app.basic.security import set_rls_organization, set_rls_user


class BillingProjectionIntegrityError(RuntimeError):
    """A supposedly immutable ledger projection did not conserve its facts."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@contextmanager
def billing_projection_snapshot(
    database: Any,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> Iterator[Session]:
    """Open one tenant-bound, rollback-only coherent projection snapshot."""

    snapshot = database.session_factory()
    try:
        if snapshot.bind is not None and snapshot.bind.dialect.name == "postgresql":
            snapshot.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
        set_rls_user(snapshot, user_id)
        set_rls_organization(snapshot, organization_id)
        yield snapshot
    finally:
        snapshot.rollback()
        snapshot.close()


def _realtime_sequence(session: Session, organization_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.max(RealtimeEvent.sequence_id), 0)).where(
                RealtimeEvent.organization_id == organization_id
            )
        )
        or 0
    )


def _active_enrollment_candidates(
    session: Session,
    organization_id: UUID,
    as_of_date: date,
    child_ids: set[UUID],
    source_attestations_required: bool,
) -> dict[UUID, list[Enrollment]]:
    if not child_ids:
        return {}
    filters = [
        Enrollment.organization_id == organization_id,
        Enrollment.child_id.in_(child_ids),
        Enrollment.status == "active",
        Enrollment.start_date <= as_of_date,
        or_(Enrollment.end_date.is_(None), Enrollment.end_date >= as_of_date),
    ]
    if source_attestations_required:
        filters.append(_attested_source_exists(organization_id, "enrollment", Enrollment.id))
    rows = list(
        session.scalars(
            select(Enrollment)
            .where(*filters)
            .order_by(
                Enrollment.child_id,
                Enrollment.start_date.desc(),
                Enrollment.created_at.desc(),
                Enrollment.id,
            )
        )
    )
    grouped: dict[UUID, list[Enrollment]] = defaultdict(list)
    for enrollment in rows:
        grouped[enrollment.child_id].append(enrollment)
    return grouped


def _attested_source_exists(
    organization_id: UUID,
    source_type: str,
    source_id: Any,
):
    return (
        select(BillingSandboxSourceAttestation.id)
        .where(
            BillingSandboxSourceAttestation.organization_id == organization_id,
            BillingSandboxSourceAttestation.source_type == source_type,
            BillingSandboxSourceAttestation.source_id == source_id,
            BillingSandboxSourceAttestation.marker == "TEST_SYNTHETIC_ONLY",
            BillingSandboxSourceAttestation.reason_code == "disposable_test_fixture",
        )
        .exists()
    )


def _is_placed_current(enrollment: Enrollment | None, as_of_date: date) -> bool:
    return bool(
        enrollment is not None
        and enrollment.program_id is not None
        and enrollment.room_id is not None
        and enrollment.placement_effective_date is not None
        and enrollment.placement_effective_date <= as_of_date
    )


def _latest_by_version(values: list[Any], key: str) -> dict[UUID, Any]:
    latest: dict[UUID, Any] = {}
    for value in values:
        parent_id = getattr(value, key)
        current = latest.get(parent_id)
        if current is None or (value.version_number, str(value.id)) > (
            current.version_number,
            str(current.id),
        ):
            latest[parent_id] = value
    return latest


def _readiness_action(
    status: BillingReadinessStatus,
    *,
    family_id: UUID,
    child_id: UUID,
    account_id: UUID | None,
    reason_code: str,
) -> str:
    if reason_code == "billing_family_not_active":
        return safe_action_route(f"/families/{family_id}?focus=family-status")
    if status == "needs_account":
        return safe_action_route("/billing?view=accounts")
    if status == "needs_payer":
        return safe_action_route(f"/billing?view=accounts&account={account_id}")
    if status == "needs_current_enrollment":
        return safe_action_route(f"/children/{child_id}?section=enrollment")
    if status == "needs_rate_plan":
        return safe_action_route("/billing?view=rates")
    if status in {"needs_agreement", "agreement_scope_conflict", "needs_review"}:
        suffix = f"&account={account_id}" if account_id is not None else ""
        return safe_action_route(f"/billing?view=rates{suffix}")
    suffix = f"&account={account_id}" if account_id is not None else ""
    return safe_action_route(f"/billing?view=invoices{suffix}")


def _readiness_items(
    session: Session,
    *,
    organization_id: UUID,
    as_of_date: date,
    family_id: UUID | None = None,
    source_attestations_required: bool = False,
) -> list[BillingReadinessItem]:
    family_filters = [
        Family.organization_id == organization_id,
        Child.organization_id == organization_id,
        Child.is_active.is_(True),
    ]
    if family_id is not None:
        family_filters.append(Family.id == family_id)
    if source_attestations_required:
        family_filters.extend(
            [
                _attested_source_exists(
                    organization_id,
                    "organization",
                    organization_id,
                ),
                _attested_source_exists(organization_id, "family", Family.id),
                _attested_source_exists(organization_id, "child", Child.id),
            ]
        )
    child_rows = list(
        session.execute(
            select(Child, Family)
            .join(
                Family,
                (Family.organization_id == Child.organization_id)
                & (Family.id == Child.family_id),
            )
            .where(*family_filters)
            .order_by(Family.name, Child.last_name, Child.first_name, Child.id)
        )
    )
    if not child_rows:
        return []

    child_ids = {child.id for child, _family in child_rows}
    family_ids = {family.id for _child, family in child_rows}
    enrollments = _active_enrollment_candidates(
        session,
        organization_id,
        as_of_date,
        child_ids,
        source_attestations_required,
    )

    account_rows = list(
        session.scalars(
            select(BillingAccount)
            .where(
                BillingAccount.organization_id == organization_id,
                BillingAccount.family_id.in_(family_ids),
            )
            .order_by(BillingAccount.family_id, BillingAccount.id)
        )
    )
    accounts_by_family: dict[UUID, list[BillingAccount]] = defaultdict(list)
    for account in account_rows:
        accounts_by_family[account.family_id].append(account)

    payer_versions = list(
        session.scalars(
            select(BillingAccountPayerVersion)
            .where(
                BillingAccountPayerVersion.organization_id == organization_id,
                BillingAccountPayerVersion.billing_account_id.in_(
                    {account.id for account in account_rows}
                ),
            )
            .order_by(
                BillingAccountPayerVersion.billing_account_id,
                BillingAccountPayerVersion.version_number,
                BillingAccountPayerVersion.id,
            )
        )
    )
    latest_payers = _latest_by_version(payer_versions, "billing_account_id")
    guardian_ids = {version.payer_guardian_id for version in latest_payers.values()}
    guardians = {
        guardian.id: guardian
        for guardian in session.scalars(
            select(Guardian).where(
                Guardian.organization_id == organization_id,
                Guardian.id.in_(guardian_ids),
            )
        )
    }

    agreements = list(
        session.scalars(
            select(BillingAgreement)
            .where(
                BillingAgreement.organization_id == organization_id,
                BillingAgreement.child_id.in_(child_ids),
            )
            .order_by(BillingAgreement.child_id, BillingAgreement.created_at, BillingAgreement.id)
        )
    )
    agreements_by_scope: dict[tuple[UUID, UUID], list[BillingAgreement]] = defaultdict(list)
    for agreement in agreements:
        agreements_by_scope[(agreement.billing_account_id, agreement.child_id)].append(agreement)
    agreement_versions = list(
        session.scalars(
            select(BillingAgreementVersion)
            .where(
                BillingAgreementVersion.organization_id == organization_id,
                BillingAgreementVersion.agreement_id.in_(
                    {agreement.id for agreement in agreements}
                ),
            )
            .order_by(
                BillingAgreementVersion.agreement_id,
                BillingAgreementVersion.version_number,
                BillingAgreementVersion.id,
            )
        )
    )
    latest_agreements = _latest_by_version(agreement_versions, "agreement_id")

    rate_plans = list(
        session.scalars(
            select(BillingRatePlan)
            .where(BillingRatePlan.organization_id == organization_id)
            .order_by(
                BillingRatePlan.facility_id,
                BillingRatePlan.program_id,
                BillingRatePlan.code,
                BillingRatePlan.id,
            )
        )
    )
    plans_by_program: dict[tuple[UUID, UUID], list[BillingRatePlan]] = defaultdict(list)
    plans_by_id = {plan.id: plan for plan in rate_plans}
    for plan in rate_plans:
        plans_by_program[(plan.facility_id, plan.program_id)].append(plan)
    rate_versions = list(
        session.scalars(
            select(BillingRatePlanVersion)
            .where(
                BillingRatePlanVersion.organization_id == organization_id,
                BillingRatePlanVersion.status == "published",
            )
            .order_by(
                BillingRatePlanVersion.rate_plan_id,
                BillingRatePlanVersion.version_number,
                BillingRatePlanVersion.id,
            )
        )
    )
    rate_versions_by_id = {version.id: version for version in rate_versions}
    effective_rate_versions = [
        version
        for version in rate_versions
        if version.effective_from <= as_of_date
        and (version.effective_until is None or version.effective_until >= as_of_date)
    ]
    latest_effective_rates = _latest_by_version(effective_rate_versions, "rate_plan_id")

    items: list[BillingReadinessItem] = []
    for child, family in child_rows:
        enrollment_candidates = enrollments.get(child.id, [])
        enrollment = enrollment_candidates[0] if enrollment_candidates else None
        account_candidates = accounts_by_family.get(family.id, [])
        account = account_candidates[0] if account_candidates else None
        latest_payer = latest_payers.get(account.id) if account is not None else None
        guardian = guardians.get(latest_payer.payer_guardian_id) if latest_payer else None
        valid_payer = bool(
            latest_payer is not None
            and guardian is not None
            and guardian.family_id == family.id
            and guardian.retired_at is None
        )

        status: BillingReadinessStatus
        reason_codes: list[str]
        rate_plan: BillingRatePlan | None = None
        rate_version: BillingRatePlanVersion | None = None
        agreement: BillingAgreement | None = None
        agreement_version: BillingAgreementVersion | None = None

        if family.status != "active":
            status = "needs_review"
            reason_codes = ["billing_family_not_active"]
        elif len(account_candidates) > 1 or len(enrollment_candidates) > 1:
            status = "needs_review"
            reason_codes = ["billing_projection_inconsistent"]
        elif account is None:
            status = "needs_account"
            reason_codes = ["billing_account_missing"]
        elif not valid_payer:
            status = "needs_payer"
            reason_codes = ["billing_payer_missing"]
        elif not _is_placed_current(enrollment, as_of_date):
            status = "needs_current_enrollment"
            reason_codes = ["current_enrollment_missing"]
        else:
            scoped_agreements = agreements_by_scope.get((account.id, child.id), [])
            exact_agreements = [
                candidate
                for candidate in scoped_agreements
                if candidate.enrollment_id == enrollment.id
                and candidate.facility_id == enrollment.facility_id
            ]
            conflicting_agreements = [
                candidate
                for candidate in scoped_agreements
                if candidate.enrollment_id != enrollment.id
                or candidate.facility_id != enrollment.facility_id
            ]
            if len(exact_agreements) > 1:
                status = "needs_review"
                reason_codes = ["billing_projection_inconsistent"]
            elif exact_agreements:
                agreement = exact_agreements[0]
                agreement_version = latest_agreements.get(agreement.id)
                if agreement_version is not None:
                    rate_version = rate_versions_by_id.get(agreement_version.rate_plan_version_id)
                    rate_plan = (
                        plans_by_id.get(rate_version.rate_plan_id)
                        if rate_version is not None
                        else None
                    )
                agreement_is_current = bool(
                    agreement_version is not None
                    and agreement_version.review_status == "reviewed"
                    and agreement_version.effective_from <= as_of_date
                    and (
                        agreement_version.effective_until is None
                        or agreement_version.effective_until >= as_of_date
                    )
                )
                rate_is_current = bool(
                    rate_version is not None
                    and rate_plan is not None
                    and rate_version.status == "published"
                    and rate_version.effective_from <= as_of_date
                    and (
                        rate_version.effective_until is None
                        or rate_version.effective_until >= as_of_date
                    )
                    and rate_plan.facility_id == enrollment.facility_id
                    and rate_plan.program_id == enrollment.program_id
                    and (
                        rate_plan.age_group is None
                        or (
                            child.age_group is not None
                            and rate_plan.age_group == child.age_group
                        )
                    )
                )
                if agreement_is_current and rate_is_current:
                    status = "setup_ready"
                    reason_codes = ["billing_setup_ready"]
                else:
                    status = "needs_review"
                    reason_codes = ["billing_agreement_review_required"]
            elif conflicting_agreements:
                agreement = conflicting_agreements[0]
                agreement_version = latest_agreements.get(agreement.id)
                status = "agreement_scope_conflict"
                reason_codes = ["billing_agreement_enrollment_conflict"]
            else:
                plan_candidates = plans_by_program.get(
                    (enrollment.facility_id, enrollment.program_id),
                    [],
                )
                specific = [
                    plan
                    for plan in plan_candidates
                    if child.age_group is not None
                    and plan.age_group == child.age_group
                    and plan.id in latest_effective_rates
                ]
                generic = [
                    plan
                    for plan in plan_candidates
                    if plan.age_group is None and plan.id in latest_effective_rates
                ]
                applicable = specific or generic
                if not applicable:
                    status = "needs_rate_plan"
                    reason_codes = ["applicable_rate_plan_missing"]
                elif len(applicable) > 1:
                    status = "needs_review"
                    reason_codes = ["multiple_applicable_rate_plans"]
                else:
                    rate_plan = applicable[0]
                    rate_version = latest_effective_rates[rate_plan.id]
                    status = "needs_agreement"
                    reason_codes = ["billing_agreement_missing"]

        items.append(
            BillingReadinessItem(
                family_id=family.id,
                family_name=family.name,
                child_id=child.id,
                child_name=f"{child.first_name} {child.last_name}".strip(),
                enrollment_id=enrollment.id if enrollment is not None else None,
                facility_id=enrollment.facility_id if enrollment is not None else None,
                program_id=enrollment.program_id if enrollment is not None else None,
                billing_account_id=account.id if account is not None else None,
                payer_guardian_id=guardian.id if valid_payer and guardian is not None else None,
                rate_plan_id=rate_plan.id if rate_plan is not None else None,
                rate_plan_version_id=rate_version.id if rate_version is not None else None,
                agreement_id=agreement.id if agreement is not None else None,
                agreement_version_id=(
                    agreement_version.id if agreement_version is not None else None
                ),
                status=status,
                reason_codes=reason_codes,
                action_path=_readiness_action(
                    status,
                    family_id=family.id,
                    child_id=child.id,
                    account_id=account.id if account is not None else None,
                    reason_code=reason_codes[0],
                ),
            )
        )
    return items


def build_billing_readiness(
    session: Session,
    *,
    organization_id: UUID,
    as_of_date: date,
    generated_at: datetime | None = None,
    source_attestations_required: bool = False,
) -> BillingReadinessResponse:
    generated = generated_at or datetime.now(UTC)
    items = _readiness_items(
        session,
        organization_id=organization_id,
        as_of_date=as_of_date,
        source_attestations_required=source_attestations_required,
    )
    status_counts = Counter(item.status for item in items)
    counts = BillingReadinessCounts(
        total=len(items),
        setup_ready=status_counts["setup_ready"],
        needs_account=status_counts["needs_account"],
        needs_payer=status_counts["needs_payer"],
        needs_current_enrollment=status_counts["needs_current_enrollment"],
        needs_rate_plan=status_counts["needs_rate_plan"],
        needs_agreement=status_counts["needs_agreement"],
        agreement_scope_conflict=status_counts["agreement_scope_conflict"],
        needs_review=status_counts["needs_review"],
    )
    return BillingReadinessResponse(
        organization_id=organization_id,
        generated_at=generated,
        as_of_date=as_of_date,
        data_through_realtime_sequence=_realtime_sequence(session, organization_id),
        counts=counts,
        items=items,
    )


def _zero_charge_attribution() -> dict[str, int]:
    return {
        "invoice_count": 0,
        "line_count": 0,
        "gross_minor": 0,
        "funding_minor": 0,
        "subtotal_minor": 0,
        "tax_minor": 0,
        "total_minor": 0,
    }


def build_family_finance_summary(
    session: Session,
    *,
    organization_id: UUID,
    family_id: UUID,
    as_of_date: date,
    generated_at: datetime | None = None,
    source_attestations_required: bool = False,
) -> BillingFamilyFinanceSummaryResponse | None:
    generated = generated_at or datetime.now(UTC)
    family_filters = [
        Family.organization_id == organization_id,
        Family.id == family_id,
    ]
    if source_attestations_required:
        family_filters.extend(
            [
                _attested_source_exists(
                    organization_id,
                    "organization",
                    organization_id,
                ),
                _attested_source_exists(organization_id, "family", Family.id),
            ]
        )
    family = session.scalar(select(Family).where(*family_filters))
    if family is None:
        return None
    child_filters = [
        Child.organization_id == organization_id,
        Child.family_id == family_id,
    ]
    if source_attestations_required:
        child_filters.append(_attested_source_exists(organization_id, "child", Child.id))
    children = list(
        session.scalars(
            select(Child)
            .where(*child_filters)
            .order_by(Child.last_name, Child.first_name, Child.id)
        )
    )
    current_enrollment_groups = _active_enrollment_candidates(
        session,
        organization_id,
        as_of_date,
        {child.id for child in children},
        source_attestations_required,
    )
    if any(len(values) > 1 for values in current_enrollment_groups.values()):
        raise BillingProjectionIntegrityError("billing_projection_inconsistent")

    accounts = list(
        session.scalars(
            select(BillingAccount)
            .where(
                BillingAccount.organization_id == organization_id,
                BillingAccount.family_id == family_id,
            )
            .order_by(BillingAccount.id)
        )
    )
    if len(accounts) > 1:
        raise BillingProjectionIntegrityError("billing_projection_inconsistent")
    account = accounts[0] if accounts else None

    invoices: list[BillingInvoice] = []
    payments: list[BillingPayment] = []
    allocations: list[BillingAllocation] = []
    credits: list[BillingCredit] = []
    lines: list[BillingInvoiceLine] = []
    account_response: BillingFamilyAccountResponse | None = None
    if account is not None:
        invoices = list(
            session.scalars(
                select(BillingInvoice)
                .where(
                    BillingInvoice.organization_id == organization_id,
                    BillingInvoice.billing_account_id == account.id,
                    BillingInvoice.family_id == family_id,
                )
                .order_by(BillingInvoice.issue_date, BillingInvoice.issued_at, BillingInvoice.id)
            )
        )
        invoice_ids = {invoice.id for invoice in invoices}
        payments = list(
            session.scalars(
                select(BillingPayment)
                .where(
                    BillingPayment.organization_id == organization_id,
                    BillingPayment.billing_account_id == account.id,
                    BillingPayment.family_id == family_id,
                )
                .order_by(BillingPayment.received_at, BillingPayment.recorded_at, BillingPayment.id)
            )
        )
        allocations = list(
            session.scalars(
                select(BillingAllocation)
                .where(
                    BillingAllocation.organization_id == organization_id,
                    BillingAllocation.billing_account_id == account.id,
                )
                .order_by(BillingAllocation.allocated_at, BillingAllocation.id)
            )
        )
        credits = list(
            session.scalars(
                select(BillingCredit)
                .where(
                    BillingCredit.organization_id == organization_id,
                    BillingCredit.billing_account_id == account.id,
                )
                .order_by(BillingCredit.issued_at, BillingCredit.id)
            )
        )
        if invoice_ids:
            lines = list(
                session.scalars(
                    select(BillingInvoiceLine)
                    .where(
                        BillingInvoiceLine.organization_id == organization_id,
                        BillingInvoiceLine.invoice_id.in_(invoice_ids),
                    )
                    .order_by(
                        BillingInvoiceLine.invoice_id,
                        BillingInvoiceLine.line_number,
                        BillingInvoiceLine.id,
                    )
                )
            )

        payer_versions = list(
            session.scalars(
                select(BillingAccountPayerVersion)
                .where(
                    BillingAccountPayerVersion.organization_id == organization_id,
                    BillingAccountPayerVersion.billing_account_id == account.id,
                )
                .order_by(
                    BillingAccountPayerVersion.version_number,
                    BillingAccountPayerVersion.id,
                )
            )
        )
        current_payer_id = (
            payer_versions[-1].payer_guardian_id
            if payer_versions
            else account.payer_guardian_id
        )
        payer = session.scalar(
            select(Guardian).where(
                Guardian.organization_id == organization_id,
                Guardian.family_id == family_id,
                Guardian.id == current_payer_id,
            )
        )
        if payer is None:
            raise BillingProjectionIntegrityError("billing_projection_inconsistent")
        account_response = BillingFamilyAccountResponse(
            id=account.id,
            account_number=account.account_number,
            status=account.status,
            payer_guardian_id=payer.id,
            payer_name=f"{payer.first_name} {payer.last_name}".strip(),
        )

    allocations_by_invoice: dict[UUID, int] = defaultdict(int)
    allocations_by_payment: dict[UUID, int] = defaultdict(int)
    for allocation in allocations:
        allocations_by_invoice[allocation.invoice_id] += allocation.amount_minor
        allocations_by_payment[allocation.payment_id] += allocation.amount_minor
    credits_by_invoice: dict[UUID, int] = defaultdict(int)
    for credit in credits:
        credits_by_invoice[credit.invoice_id] += credit.amount_minor

    invoice_total = sum(invoice.total_minor for invoice in invoices)
    allocated_total = sum(allocation.amount_minor for allocation in allocations)
    credits_total = sum(credit.amount_minor for credit in credits)
    open_invoices = 0
    for invoice in invoices:
        outstanding = (
            invoice.total_minor
            - allocations_by_invoice[invoice.id]
            - credits_by_invoice[invoice.id]
        )
        if outstanding < 0:
            raise BillingProjectionIntegrityError("billing_invoice_settlement_overapplied")
        if outstanding:
            open_invoices += 1
    outstanding_total = invoice_total - allocated_total - credits_total
    if outstanding_total < 0:
        raise BillingProjectionIntegrityError("billing_invoice_settlement_overapplied")

    payment_total = sum(payment.amount_minor for payment in payments)
    for payment in payments:
        if allocations_by_payment[payment.id] > payment.amount_minor:
            raise BillingProjectionIntegrityError("billing_payment_allocation_overapplied")
    if allocated_total > payment_total:
        raise BillingProjectionIntegrityError("billing_payment_allocation_overapplied")

    child_ids = {child.id for child in children}
    attributed: dict[UUID, dict[str, Any]] = {
        child.id: {**_zero_charge_attribution(), "_invoice_ids": set()} for child in children
    }
    for line in lines:
        if line.child_id not in child_ids:
            raise BillingProjectionIntegrityError("billing_projection_inconsistent")
        totals = attributed[line.child_id]
        totals["line_count"] += 1
        totals["_invoice_ids"].add(line.invoice_id)
        totals["gross_minor"] += line.gross_subtotal_minor
        totals["funding_minor"] += line.funding_minor
        totals["subtotal_minor"] += line.subtotal_minor
        totals["tax_minor"] += line.tax_minor
        totals["total_minor"] += line.total_minor

    readiness_by_child = {
        item.child_id: item.status
        for item in _readiness_items(
            session,
            organization_id=organization_id,
            as_of_date=as_of_date,
            family_id=family_id,
            source_attestations_required=source_attestations_required,
        )
    }
    child_items: list[BillingFamilyChildFinanceResponse] = []
    for child in children:
        enrollment_candidates = current_enrollment_groups.get(child.id, [])
        enrollment = enrollment_candidates[0] if enrollment_candidates else None
        charge_values = attributed[child.id]
        charge_values["invoice_count"] = len(charge_values.pop("_invoice_ids"))
        child_items.append(
            BillingFamilyChildFinanceResponse(
                child_id=child.id,
                child_name=f"{child.first_name} {child.last_name}".strip(),
                is_active=child.is_active,
                current_enrollment_id=enrollment.id if enrollment is not None else None,
                readiness_status=readiness_by_child.get(child.id),
                charge_attribution=BillingChildChargeAttribution(**charge_values),
            )
        )

    return BillingFamilyFinanceSummaryResponse(
        organization_id=organization_id,
        generated_at=generated,
        as_of_date=as_of_date,
        data_through_realtime_sequence=_realtime_sequence(session, organization_id),
        family=BillingFamilyIdentityResponse(
            id=family.id,
            name=family.name,
            status=family.status,
        ),
        account=account_response,
        invoice_summary=BillingFamilyInvoiceSummary(
            invoice_count=len(invoices),
            open_invoice_count=open_invoices,
            settled_invoice_count=len(invoices) - open_invoices,
            total_minor=invoice_total,
            allocated_minor=allocated_total,
            credits_minor=credits_total,
            outstanding_minor=outstanding_total,
        ),
        payment_summary=BillingFamilyPaymentSummary(
            payment_count=len(payments),
            recorded_minor=payment_total,
            allocated_minor=allocated_total,
            unapplied_minor=payment_total - allocated_total,
        ),
        children=child_items,
    )
