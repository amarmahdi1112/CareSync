"""Tenant-scoped read models and commands for the 0033 billing ledger."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.common import ensure_writable, lock_client_operation
from app.api.basic.dependencies import BasicContext, BasicContextDependency
from app.api.dependencies import SessionDependency
from app.basic.billing import (
    _sum_allocations,
    _sum_credits,
    allocate_payment,
    assign_account_payer,
    current_account_payer_version,
    establish_agreement,
    issue_credit,
    issue_invoice,
    open_account,
    publish_rate_version,
    record_payment,
)
from app.basic.billing_projections import (
    BillingProjectionIntegrityError,
    billing_projection_snapshot,
    build_billing_readiness,
    build_family_finance_summary,
)
from app.basic.billing_readiness_planner import build_billing_readiness_batch_snapshot
from app.basic.billing_schemas import (
    MAX_CAD_MINOR,
    PRIVATE_MANUAL_BILLING_LABEL,
    SYNTHETIC_BILLING_LABEL,
    ActivateManualBillingCommand,
    AllocateBillingPaymentCommand,
    AssignBillingAccountPayerCommand,
    BillingAbsenceClaimResponse,
    BillingAccountDetailResponse,
    BillingAccountListResponse,
    BillingAccountPayerVersionListResponse,
    BillingAccountPayerVersionResponse,
    BillingAccountSummary,
    BillingAgreementListResponse,
    BillingAgreementResponse,
    BillingAgreementVersionResponse,
    BillingAllocationListResponse,
    BillingAllocationResponse,
    BillingCapabilityResponse,
    BillingCollectionPage,
    BillingCommandPreparationResponse,
    BillingCommandReceiptResponse,
    BillingCreditListResponse,
    BillingCreditResponse,
    BillingFamilyFinanceSummaryResponse,
    BillingInvoiceDocumentAllocationResponse,
    BillingInvoiceDocumentCreditResponse,
    BillingInvoiceDocumentOrganizationResponse,
    BillingInvoiceDocumentPayerSnapshotResponse,
    BillingInvoiceDocumentPreviewResponse,
    BillingInvoiceDocumentResponse,
    BillingInvoiceDocumentSettlementResponse,
    BillingInvoiceLineResponse,
    BillingInvoiceListResponse,
    BillingInvoiceResponse,
    BillingManualActivationResponse,
    BillingOverviewResponse,
    BillingPaymentListResponse,
    BillingPaymentResponse,
    BillingRatePlanListResponse,
    BillingRatePlanResponse,
    BillingRatePlanVersionResponse,
    BillingReadinessActionableWave,
    BillingReadinessBatchPlanResponse,
    BillingReadinessBatchPrepareRequest,
    BillingReadinessBatchPreviewBlock,
    BillingReadinessBatchPreviewIntent,
    BillingReadinessBatchPreviewResponse,
    BillingReadinessBatchWave,
    BillingReadinessBatchWaveCounts,
    BillingReadinessResponse,
    BillingReadinessStatus,
    BillingSourceOptionsResponse,
    BillingWorkspacePaging,
    BillingWorkspaceResponse,
    EstablishBillingAgreementCommand,
    FinalizeBillingCommandAbsenceCommand,
    IssueBillingCreditCommand,
    IssueBillingInvoiceCommand,
    OpenBillingAccountCommand,
    PrepareBillingCommand,
    PreviewBillingReadinessBatchCommand,
    PublishRatePlanVersionCommand,
    RecordBillingPaymentCommand,
)
from app.basic.childcare_commands import command_hash, safe_action_route
from app.basic.models import (
    AuditEvent,
    BillingAccount,
    BillingAccountPayerVersion,
    BillingAgreement,
    BillingAgreementVersion,
    BillingAllocation,
    BillingCommandClaim,
    BillingCommandPreparation,
    BillingCommandReceipt,
    BillingCommandTerminal,
    BillingCredit,
    BillingInvoice,
    BillingInvoiceLine,
    BillingJournalEntry,
    BillingJournalLine,
    BillingManualActivation,
    BillingPayment,
    BillingRatePlan,
    BillingRatePlanVersion,
    BillingReversal,
    BillingSandboxSourceAttestation,
    Child,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Program,
    RealtimeEvent,
)
from app.basic.security import set_rls_organization, set_rls_user

router = APIRouter(prefix="/billing", tags=["billing ledger"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_billing_permission(permission: str):
    """Require both leadership identity and the exact finance permission."""

    def dependency(context: BasicContextDependency) -> BasicContext:
        if context.role.key not in {"owner", "administrator"} or permission not in set(
            context.role.permissions or []
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "billing_permission_required"},
            )
        return context

    return dependency


BillingReadContext = Annotated[BasicContext, Depends(require_billing_permission("billing:read"))]
BillingManageContext = Annotated[
    BasicContext, Depends(require_billing_permission("billing:manage"))
]
BillingIssueContext = Annotated[BasicContext, Depends(require_billing_permission("billing:issue"))]
BillingPaymentsContext = Annotated[
    BasicContext, Depends(require_billing_permission("billing:payments"))
]
BillingAdjustContext = Annotated[
    BasicContext, Depends(require_billing_permission("billing:adjust"))
]
BillingRecoveryContext = Annotated[
    BasicContext, Depends(require_billing_permission("billing:recover"))
]


def require_billing_owner(context: BasicContextDependency) -> BasicContext:
    if context.role.key != "owner" or "billing:manage" not in set(context.role.permissions or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "billing_owner_required"},
        )
    return context


BillingOwnerContext = Annotated[BasicContext, Depends(require_billing_owner)]


def _manual_activation(
    session: Session,
    organization_id: UUID,
) -> BillingManualActivation | None:
    return session.scalar(
        select(BillingManualActivation).where(
            BillingManualActivation.organization_id == organization_id
        )
    )


def _provenance_values(
    session: Session,
    organization_id: UUID,
) -> dict[str, object]:
    manual = _manual_activation(session, organization_id) is not None
    return {
        "billing_mode": "manual" if manual else "sandbox",
        "sandbox": not manual,
        "provenance_label": (PRIVATE_MANUAL_BILLING_LABEL if manual else SYNTHETIC_BILLING_LABEL),
    }


def _available(request: Request, organization_id: UUID) -> bool:
    settings = request.app.state.settings
    return bool(
        getattr(request.app.state, "billing_ledger_enabled", False)
        and settings.billing_organization_is_allowlisted(organization_id)
    )


def _require_available(request: Request, organization_id: UUID) -> None:
    if not _available(request, organization_id):
        raise HTTPException(503, detail={"code": "billing_ledger_unavailable"})


def _billing_readiness(
    request: Request,
    session: Session,
    organization_id: UUID,
    organization_timezone: str,
) -> tuple[bool, bool, date]:
    """Return the single authoritative runtime/write readiness decision."""

    try:
        organization_local_date = datetime.now(ZoneInfo(organization_timezone)).date()
        timezone_valid = True
    except ZoneInfoNotFoundError:
        organization_local_date = datetime.now(UTC).date()
        timezone_valid = False
    settings = request.app.state.settings
    runtime_available = bool(_available(request, organization_id) and timezone_valid)
    server_write_boundary = bool(
        (settings.billing_mode == "sandbox" and settings.billing_sandbox_target_is_disposable)
        or (
            settings.billing_mode == "manual"
            and settings.billing_manual_target_is_private_local
            and _manual_activation(session, organization_id) is not None
        )
    )
    writes_available = bool(
        runtime_available
        and getattr(request.app.state, "billing_ledger_writes_enabled", False)
        and settings.database_type == "postgres"
        and settings.billing_organization_is_allowlisted(organization_id)
        and server_write_boundary
    )
    return runtime_available, writes_available, organization_local_date


def _require_write_ready(
    request: Request,
    session: Session,
    context: BasicContext,
) -> None:
    runtime_available, writes_available, _local_date = _billing_readiness(
        request,
        session,
        context.organization.id,
        context.organization.timezone,
    )
    if not runtime_available:
        raise HTTPException(503, detail={"code": "billing_ledger_unavailable"})
    if not writes_available:
        code = (
            "billing_manual_activation_required"
            if request.app.state.settings.billing_mode == "manual"
            else "billing_sandbox_writes_disabled"
        )
        raise HTTPException(409, detail={"code": code})


_RECOVERY_COMMAND_MODELS = {
    "account_open": OpenBillingAccountCommand,
    "account_payer_assign": AssignBillingAccountPayerCommand,
    "rate_version_publish": PublishRatePlanVersionCommand,
    "agreement_establish": EstablishBillingAgreementCommand,
    "invoice_issue": IssueBillingInvoiceCommand,
    "payment_record": RecordBillingPaymentCommand,
    "payment_allocate": AllocateBillingPaymentCommand,
    "credit_issue": IssueBillingCreditCommand,
}


def _canonical_preparation(payload: PrepareBillingCommand):
    """Validate a full typed command and derive its server-authoritative redacted proof."""

    model = _RECOVERY_COMMAND_MODELS[payload.command_type]
    try:
        typed = model.model_validate(payload.request_payload)
    except ValidationError as exc:
        raise HTTPException(
            422,
            detail={"code": "billing_recovery_intent_invalid", "errors": exc.errors()},
        ) from None
    canonical_target: UUID | str
    if payload.command_type == "account_open":
        canonical_target = typed.family_id
    elif payload.command_type == "account_payer_assign":
        canonical_target = typed.account_id
    elif payload.command_type == "rate_version_publish":
        canonical_target = typed.rate_plan_id or "new"
    elif payload.command_type == "agreement_establish":
        canonical_target = typed.agreement_id or typed.account_id
    elif payload.command_type in {"invoice_issue", "payment_record"}:
        canonical_target = typed.account_id
    elif payload.command_type == "payment_allocate":
        canonical_target = typed.payment_id
    else:
        canonical_target = typed.invoice_id
    digest = command_hash(
        command_type=payload.command_type,
        target_type="billing_command",
        target_scope=canonical_target,
        intent=typed.model_dump(mode="python", exclude={"client_operation_id"}),
    )
    return typed, str(canonical_target), digest


def _minor_sum(session, model, column, organization_id: UUID, *filters) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(column), 0)).where(
                model.organization_id == organization_id, *filters
            )
        )
        or 0
    )


def _synthetic_source_exists(organization_id: UUID, source_type: str, source_id):
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


def _require_nonnegative_projection(kind: str, value: int) -> int:
    if value < 0 or value > MAX_CAD_MINOR:
        raise HTTPException(
            409,
            detail={
                "code": "billing_ledger_projection_invalid",
                "projection": kind,
            },
        )
    return value


def _overview_response(session: Session, organization_id: UUID) -> BillingOverviewResponse:
    account_count = int(
        session.scalar(
            select(func.count())
            .select_from(BillingAccount)
            .where(BillingAccount.organization_id == organization_id)
        )
        or 0
    )
    invoice_count = int(
        session.scalar(
            select(func.count())
            .select_from(BillingInvoice)
            .where(BillingInvoice.organization_id == organization_id)
        )
        or 0
    )
    invoiced = _minor_sum(session, BillingInvoice, BillingInvoice.total_minor, organization_id)
    settled = _minor_sum(session, BillingPayment, BillingPayment.amount_minor, organization_id)
    allocated = _minor_sum(
        session, BillingAllocation, BillingAllocation.amount_minor, organization_id
    )
    credits = _minor_sum(session, BillingCredit, BillingCredit.amount_minor, organization_id)
    return BillingOverviewResponse(
        organization_id=organization_id,
        as_of=datetime.now(UTC),
        account_count=account_count,
        open_account_count=account_count,
        issued_invoice_count=invoice_count,
        outstanding_minor=_require_nonnegative_projection(
            "overview_outstanding", invoiced - allocated - credits
        ),
        settled_payments_minor=settled,
        unapplied_payments_minor=_require_nonnegative_projection(
            "overview_unapplied", settled - allocated
        ),
        credits_minor=credits,
    )


def _payer_version_response(
    version: BillingAccountPayerVersion,
) -> BillingAccountPayerVersionResponse:
    return BillingAccountPayerVersionResponse(
        organization_id=version.organization_id,
        id=version.id,
        billing_account_id=version.billing_account_id,
        family_id=version.family_id,
        payer_guardian_id=version.payer_guardian_id,
        version_number=version.version_number,
        assigned_by_user_id=version.assigned_by_user_id,
        assigned_at=version.assigned_at,
    )


def _account_summary(session, account: BillingAccount, family_name: str) -> BillingAccountSummary:
    organization_id = account.organization_id
    invoiced = _minor_sum(
        session,
        BillingInvoice,
        BillingInvoice.total_minor,
        organization_id,
        BillingInvoice.billing_account_id == account.id,
    )
    allocated = _minor_sum(
        session,
        BillingAllocation,
        BillingAllocation.amount_minor,
        organization_id,
        BillingAllocation.billing_account_id == account.id,
    )
    credits = _minor_sum(
        session,
        BillingCredit,
        BillingCredit.amount_minor,
        organization_id,
        BillingCredit.billing_account_id == account.id,
    )
    settled = _minor_sum(
        session,
        BillingPayment,
        BillingPayment.amount_minor,
        organization_id,
        BillingPayment.billing_account_id == account.id,
    )
    payer_version = current_account_payer_version(session, organization_id, account.id)
    if payer_version is None:
        raise HTTPException(409, detail={"code": "billing_account_payer_history_missing"})
    return BillingAccountSummary(
        organization_id=organization_id,
        id=account.id,
        family_id=account.family_id,
        payer_guardian_id=payer_version.payer_guardian_id,
        latest_payer_version_id=payer_version.id,
        latest_payer_version_number=payer_version.version_number,
        family_name=family_name,
        account_number=account.account_number,
        status="open",
        currency="CAD",
        opened_at=account.opened_at,
        invoiced_minor=invoiced,
        allocated_minor=allocated,
        credits_minor=credits,
        outstanding_minor=_require_nonnegative_projection(
            "account_outstanding", invoiced - allocated - credits
        ),
        unapplied_minor=_require_nonnegative_projection("account_unapplied", settled - allocated),
    )


def _invoice_response(session, invoice: BillingInvoice) -> BillingInvoiceResponse:
    allocated = _sum_allocations(session, invoice.organization_id, invoice_id=invoice.id)
    credited = _sum_credits(session, invoice.organization_id, invoice.id)
    outstanding = _require_nonnegative_projection(
        "invoice_outstanding", invoice.total_minor - allocated - credited
    )
    if outstanding == 0:
        if allocated > 0 and credited > 0:
            lifecycle_status = "settled_mixed"
        elif allocated > 0:
            lifecycle_status = "settled_paid"
        else:
            lifecycle_status = "settled_credited"
    elif allocated or credited:
        lifecycle_status = "partially_settled"
    else:
        lifecycle_status = "open"
    lines = list(
        session.scalars(
            select(BillingInvoiceLine)
            .where(
                BillingInvoiceLine.organization_id == invoice.organization_id,
                BillingInvoiceLine.invoice_id == invoice.id,
            )
            .order_by(BillingInvoiceLine.line_number)
        )
    )
    provenance = _provenance_values(session, invoice.organization_id)
    return BillingInvoiceResponse(
        **provenance,
        document_label=provenance["provenance_label"],
        organization_id=invoice.organization_id,
        id=invoice.id,
        billing_account_id=invoice.billing_account_id,
        family_id=invoice.family_id,
        billing_account_payer_version_id=invoice.billing_account_payer_version_id,
        payer_guardian_id=invoice.payer_guardian_id,
        invoice_number=invoice.invoice_number,
        lifecycle_status=lifecycle_status,
        currency="CAD",
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        service_period_start=invoice.service_period_start,
        service_period_end=invoice.service_period_end,
        family_name=invoice.family_name_snapshot,
        payer_name=invoice.payer_name_snapshot,
        payer_email=invoice.payer_email_snapshot,
        payer_address=invoice.payer_address_snapshot,
        gross_subtotal_minor=invoice.gross_subtotal_minor,
        funding_minor=invoice.funding_minor,
        subtotal_minor=invoice.subtotal_minor,
        tax_minor=invoice.tax_minor,
        total_minor=invoice.total_minor,
        allocated_minor=allocated,
        credits_minor=credited,
        outstanding_minor=outstanding,
        issued_at=invoice.issued_at,
        lines=[
            BillingInvoiceLineResponse(
                organization_id=line.organization_id,
                id=line.id,
                agreement_version_id=line.agreement_version_id,
                child_id=line.child_id,
                line_number=line.line_number,
                description=line.description_snapshot,
                child_name=line.child_name_snapshot,
                rate_plan_name=line.rate_plan_name_snapshot,
                billing_unit=line.billing_unit_snapshot,
                service_period_start=line.service_period_start,
                service_period_end=line.service_period_end,
                quantity=line.quantity,
                gross_unit_amount_minor=line.gross_unit_amount_minor,
                funding_unit_amount_minor=line.funding_unit_amount_minor,
                unit_amount_minor=line.unit_amount_minor,
                tax_rate_basis_points=line.tax_rate_basis_points,
                gross_subtotal_minor=line.gross_subtotal_minor,
                funding_minor=line.funding_minor,
                subtotal_minor=line.subtotal_minor,
                tax_minor=line.tax_minor,
                total_minor=line.total_minor,
            )
            for line in lines
        ],
    )


def _invoice_document_preview(
    session: Session,
    *,
    context: BasicContext,
    invoice: BillingInvoice,
) -> BillingInvoiceDocumentPreviewResponse:
    """Build one deterministic, tenant-scoped rendering source without mutating state."""

    lines = list(
        session.scalars(
            select(BillingInvoiceLine)
            .where(
                BillingInvoiceLine.organization_id == context.organization.id,
                BillingInvoiceLine.invoice_id == invoice.id,
            )
            .order_by(BillingInvoiceLine.line_number, BillingInvoiceLine.id)
        )
    )
    allocations = list(
        session.scalars(
            select(BillingAllocation)
            .where(
                BillingAllocation.organization_id == context.organization.id,
                BillingAllocation.invoice_id == invoice.id,
            )
            .order_by(BillingAllocation.allocated_at, BillingAllocation.id)
        )
    )
    credits = list(
        session.scalars(
            select(BillingCredit)
            .where(
                BillingCredit.organization_id == context.organization.id,
                BillingCredit.invoice_id == invoice.id,
            )
            .order_by(BillingCredit.issued_at, BillingCredit.id)
        )
    )
    allocated_minor = sum(value.amount_minor for value in allocations)
    credits_minor = sum(value.amount_minor for value in credits)
    outstanding_minor = _require_nonnegative_projection(
        "invoice_document_outstanding",
        invoice.total_minor - allocated_minor - credits_minor,
    )
    immutable_lines = [
        BillingInvoiceLineResponse(
            organization_id=line.organization_id,
            id=line.id,
            agreement_version_id=line.agreement_version_id,
            child_id=line.child_id,
            line_number=line.line_number,
            description=line.description_snapshot,
            child_name=line.child_name_snapshot,
            rate_plan_name=line.rate_plan_name_snapshot,
            billing_unit=line.billing_unit_snapshot,
            service_period_start=line.service_period_start,
            service_period_end=line.service_period_end,
            quantity=line.quantity,
            gross_unit_amount_minor=line.gross_unit_amount_minor,
            funding_unit_amount_minor=line.funding_unit_amount_minor,
            unit_amount_minor=line.unit_amount_minor,
            tax_rate_basis_points=line.tax_rate_basis_points,
            gross_subtotal_minor=line.gross_subtotal_minor,
            funding_minor=line.funding_minor,
            subtotal_minor=line.subtotal_minor,
            tax_minor=line.tax_minor,
            total_minor=line.total_minor,
        )
        for line in lines
    ]
    allocation_documents = [
        BillingInvoiceDocumentAllocationResponse(
            id=value.id,
            payment_id=value.payment_id,
            amount_minor=value.amount_minor,
            allocated_at=_as_utc(value.allocated_at),
        )
        for value in allocations
    ]
    credit_documents = [
        BillingInvoiceDocumentCreditResponse(
            id=value.id,
            amount_minor=value.amount_minor,
            reason_code=value.reason_code,
            note=value.note,
            issued_at=_as_utc(value.issued_at),
        )
        for value in credits
    ]
    issued_at = _as_utc(invoice.issued_at)
    data_through_at = max(
        [
            issued_at,
            *(value.allocated_at for value in allocation_documents),
            *(value.issued_at for value in credit_documents),
        ]
    )
    realtime_sequence = int(
        session.scalar(
            select(func.coalesce(func.max(RealtimeEvent.sequence_id), 0)).where(
                RealtimeEvent.organization_id == context.organization.id
            )
        )
        or 0
    )
    organization = BillingInvoiceDocumentOrganizationResponse(
        id=context.organization.id,
        display_name=context.organization.name,
        legal_name=context.organization.legal_name,
        email=context.organization.email,
        phone=context.organization.phone,
    )
    immutable_invoice = BillingInvoiceDocumentResponse(
        organization_id=invoice.organization_id,
        id=invoice.id,
        billing_account_id=invoice.billing_account_id,
        family_id=invoice.family_id,
        billing_account_payer_version_id=invoice.billing_account_payer_version_id,
        payer_guardian_id=invoice.payer_guardian_id,
        invoice_number=invoice.invoice_number,
        status="issued",
        currency="CAD",
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        service_period_start=invoice.service_period_start,
        service_period_end=invoice.service_period_end,
        family_name=invoice.family_name_snapshot,
        gross_subtotal_minor=invoice.gross_subtotal_minor,
        funding_minor=invoice.funding_minor,
        subtotal_minor=invoice.subtotal_minor,
        tax_minor=invoice.tax_minor,
        total_minor=invoice.total_minor,
        issued_at=issued_at,
        lines=immutable_lines,
    )
    payer_snapshot = BillingInvoiceDocumentPayerSnapshotResponse(
        payer_version_id=invoice.billing_account_payer_version_id,
        guardian_id=invoice.payer_guardian_id,
        name=invoice.payer_name_snapshot,
        email=invoice.payer_email_snapshot,
        address=invoice.payer_address_snapshot,
    )
    settlement = BillingInvoiceDocumentSettlementResponse(
        total_minor=invoice.total_minor,
        allocated_minor=allocated_minor,
        credits_minor=credits_minor,
        outstanding_minor=outstanding_minor,
    )
    draft = BillingInvoiceDocumentPreviewResponse(
        **_provenance_values(session, context.organization.id),
        organization_id=context.organization.id,
        invoice_id=invoice.id,
        generated_at=datetime.now(UTC),
        data_through_at=data_through_at,
        data_through_realtime_sequence=realtime_sequence,
        organization=organization,
        invoice=immutable_invoice,
        payer_snapshot=payer_snapshot,
        allocations=allocation_documents,
        credits=credit_documents,
        settlement=settlement,
        canonical_sha256="0" * 64,
    )
    canonical_payload = draft.model_dump(
        mode="json",
        exclude={"generated_at", "canonical_sha256"},
    )
    canonical_sha256 = hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return draft.model_copy(update={"canonical_sha256": canonical_sha256})


def _payment_response(session, payment: BillingPayment) -> BillingPaymentResponse:
    allocated = _sum_allocations(session, payment.organization_id, payment_id=payment.id)
    unapplied = _require_nonnegative_projection(
        "payment_unapplied", payment.amount_minor - allocated
    )
    if allocated == 0:
        lifecycle_status = "settled"
    elif unapplied == 0:
        lifecycle_status = "fully_allocated"
    else:
        lifecycle_status = "partially_allocated"
    return BillingPaymentResponse(
        **_provenance_values(session, payment.organization_id),
        organization_id=payment.organization_id,
        id=payment.id,
        billing_account_id=payment.billing_account_id,
        family_id=payment.family_id,
        payer_guardian_id=payment.payer_guardian_id,
        payer_name=payment.payer_name_snapshot,
        payer_email=payment.payer_email_snapshot,
        lifecycle_status=lifecycle_status,
        method=payment.method,
        currency="CAD",
        amount_minor=payment.amount_minor,
        allocated_minor=allocated,
        unapplied_minor=unapplied,
        external_reference=payment.external_reference,
        memo=payment.memo,
        operator_confirmation_note=payment.operator_confirmation_note,
        received_at=payment.received_at,
        recorded_at=payment.recorded_at,
    )


def _allocation_response(allocation: BillingAllocation) -> BillingAllocationResponse:
    return BillingAllocationResponse(
        organization_id=allocation.organization_id,
        id=allocation.id,
        billing_account_id=allocation.billing_account_id,
        payment_id=allocation.payment_id,
        invoice_id=allocation.invoice_id,
        amount_minor=allocation.amount_minor,
        allocated_by_user_id=allocation.allocated_by_user_id,
        allocated_at=allocation.allocated_at,
        client_operation_id=allocation.client_operation_id,
        request_hash=allocation.request_hash,
    )


def _credit_response(credit: BillingCredit) -> BillingCreditResponse:
    return BillingCreditResponse(
        organization_id=credit.organization_id,
        id=credit.id,
        billing_account_id=credit.billing_account_id,
        invoice_id=credit.invoice_id,
        status="issued",
        currency="CAD",
        amount_minor=credit.amount_minor,
        reason_code=credit.reason_code,
        note=credit.note,
        issued_by_user_id=credit.issued_by_user_id,
        issued_at=credit.issued_at,
        client_operation_id=credit.client_operation_id,
        request_hash=credit.request_hash,
    )


def _page(*, offset: int, limit: int, total: int, returned: int) -> BillingCollectionPage:
    next_offset = offset + returned
    has_more = next_offset < total
    return BillingCollectionPage(
        offset=offset,
        limit=limit,
        returned=returned,
        total=total,
        has_more=has_more,
        next_offset=next_offset if has_more else None,
    )


def _rate_version_response(version: BillingRatePlanVersion) -> BillingRatePlanVersionResponse:
    return BillingRatePlanVersionResponse(
        organization_id=version.organization_id,
        id=version.id,
        rate_plan_id=version.rate_plan_id,
        version_number=version.version_number,
        status="published",
        billing_unit=version.billing_unit,
        unit_amount_minor=version.unit_amount_minor,
        tax_rate_basis_points=version.tax_rate_basis_points,
        currency="CAD",
        effective_from=version.effective_from,
        effective_until=version.effective_until,
        description=version.description,
        published_at=version.published_at,
    )


def _rate_plan_response(session, plan: BillingRatePlan) -> BillingRatePlanResponse:
    versions = list(
        session.scalars(
            select(BillingRatePlanVersion)
            .where(
                BillingRatePlanVersion.organization_id == plan.organization_id,
                BillingRatePlanVersion.rate_plan_id == plan.id,
            )
            .order_by(BillingRatePlanVersion.version_number.desc())
        )
    )
    if not versions:
        raise HTTPException(409, detail={"code": "billing_rate_plan_has_no_version"})
    projected = [_rate_version_response(version) for version in versions]
    return BillingRatePlanResponse(
        organization_id=plan.organization_id,
        id=plan.id,
        code=plan.code,
        name=plan.name,
        program_type=plan.program_type,
        charge_kind="core_care",
        age_group=plan.age_group,
        facility_id=plan.facility_id,
        program_id=plan.program_id,
        created_at=plan.created_at,
        latest_version=projected[0],
        versions=projected,
    )


def _agreement_version_response(
    version: BillingAgreementVersion,
) -> BillingAgreementVersionResponse:
    return BillingAgreementVersionResponse(
        organization_id=version.organization_id,
        id=version.id,
        agreement_id=version.agreement_id,
        rate_plan_version_id=version.rate_plan_version_id,
        version_number=version.version_number,
        billing_frequency=version.billing_frequency,
        family_amount_minor_per_unit=version.family_amount_minor_per_unit,
        funding_amount_minor_per_unit=version.funding_amount_minor_per_unit,
        effective_from=version.effective_from,
        effective_until=version.effective_until,
        review_status="reviewed",
        reviewed_at=version.reviewed_at,
    )


def _agreement_response(session, agreement: BillingAgreement) -> BillingAgreementResponse:
    versions = list(
        session.scalars(
            select(BillingAgreementVersion)
            .where(
                BillingAgreementVersion.organization_id == agreement.organization_id,
                BillingAgreementVersion.agreement_id == agreement.id,
            )
            .order_by(BillingAgreementVersion.version_number.desc())
        )
    )
    child = session.scalar(
        select(Child).where(
            Child.organization_id == agreement.organization_id,
            Child.id == agreement.child_id,
        )
    )
    if not versions or child is None:
        raise HTTPException(409, detail={"code": "billing_agreement_projection_invalid"})
    projected = [_agreement_version_response(version) for version in versions]
    return BillingAgreementResponse(
        organization_id=agreement.organization_id,
        id=agreement.id,
        billing_account_id=agreement.billing_account_id,
        family_id=agreement.family_id,
        child_id=agreement.child_id,
        child_name=f"{child.first_name} {child.last_name}".strip(),
        enrollment_id=agreement.enrollment_id,
        facility_id=agreement.facility_id,
        created_at=agreement.created_at,
        latest_version=projected[0],
        versions=projected,
    )


def _manual_activation_response(
    request: Request,
    context: BasicContext,
    activation: BillingManualActivation | None,
) -> BillingManualActivationResponse:
    settings = request.app.state.settings
    return BillingManualActivationResponse(
        organization_id=context.organization.id,
        billing_mode="manual",
        server_attested=settings.billing_manual_target_is_private_local,
        organization_allowlisted=settings.billing_organization_is_allowlisted(
            context.organization.id
        ),
        activated=activation is not None,
        activation_policy_version=(
            activation.activation_policy_version if activation is not None else None
        ),
        activated_by_user_id=(activation.activated_by_user_id if activation is not None else None),
        activated_at=_as_utc(activation.activated_at) if activation is not None else None,
    )


def _require_manual_activation_configuration(
    request: Request,
    context: BasicContext,
) -> None:
    settings = request.app.state.settings
    if settings.billing_mode != "manual":
        raise HTTPException(409, detail={"code": "billing_manual_mode_disabled"})
    if not getattr(request.app.state, "billing_manual_boundary_present", False):
        raise HTTPException(503, detail={"code": "billing_manual_boundary_unavailable"})
    if not settings.billing_manual_target_is_private_local:
        raise HTTPException(409, detail={"code": "billing_manual_server_attestation_required"})
    if not settings.billing_organization_is_allowlisted(context.organization.id):
        raise HTTPException(403, detail={"code": "billing_manual_organization_not_allowlisted"})


@router.get("/manual-activation", response_model=BillingManualActivationResponse)
def billing_manual_activation_status(
    request: Request,
    context: BillingOwnerContext,
    session: SessionDependency,
) -> BillingManualActivationResponse:
    _require_manual_activation_configuration(request, context)
    return _manual_activation_response(
        request,
        context,
        _manual_activation(session, context.organization.id),
    )


@router.post(
    "/manual-activation",
    response_model=BillingManualActivationResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_billing_manual_mode(
    payload: ActivateManualBillingCommand,
    request: Request,
    context: BillingOwnerContext,
    session: SessionDependency,
) -> BillingManualActivationResponse:
    _require_manual_activation_configuration(request, context)
    ensure_writable(request)
    existing = _manual_activation(session, context.organization.id)
    if existing is not None:
        return _manual_activation_response(request, context, existing)
    existing_facts = any(
        session.scalar(
            select(model.id).where(model.organization_id == context.organization.id).limit(1)
        )
        is not None
        for model in (
            BillingSandboxSourceAttestation,
            BillingAccount,
            BillingAccountPayerVersion,
            BillingRatePlan,
            BillingRatePlanVersion,
            BillingAgreement,
            BillingAgreementVersion,
            BillingInvoice,
            BillingInvoiceLine,
            BillingPayment,
            BillingAllocation,
            BillingCredit,
            BillingJournalEntry,
            BillingJournalLine,
            BillingReversal,
            BillingCommandPreparation,
            BillingCommandTerminal,
            BillingCommandReceipt,
            BillingCommandClaim,
        )
    )
    if existing_facts:
        raise HTTPException(
            409,
            detail={"code": "billing_manual_activation_requires_empty_ledger"},
        )
    activated_at = datetime.now(UTC)
    activation = BillingManualActivation(
        id=uuid4(),
        organization_id=context.organization.id,
        activated_by_user_id=context.user.id,
        activated_by_membership_id=context.membership.id,
        activation_policy_version=payload.activation_policy_version,
        review_attestation=payload.review_attestation,
        activated_at=activated_at,
    )
    session.add_all(
        [
            activation,
            AuditEvent(
                id=uuid4(),
                organization_id=context.organization.id,
                actor_user_id=context.user.id,
                action="billing.manual_mode.activated",
                entity_type="billing_manual_activation",
                entity_id=activation.id,
                details={
                    "activation_policy_version": payload.activation_policy_version,
                    "processor_enabled": False,
                    "money_movement_enabled": False,
                    "automatic_issue_enabled": False,
                    "delivery_enabled": False,
                    "tax_advice_enabled": False,
                },
                occurred_at=activated_at,
            ),
            RealtimeEvent(
                id=uuid4(),
                organization_id=context.organization.id,
                event_type="billing.manual_mode.activated",
                entity_type="billing_manual_activation",
                entity_id=activation.id,
                payload={"refresh_required": True},
                occurred_at=activated_at,
            ),
        ]
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        concurrent = _manual_activation(session, context.organization.id)
        if concurrent is None:
            raise HTTPException(
                409,
                detail={"code": "billing_manual_activation_conflict"},
            ) from None
        activation = concurrent
    return _manual_activation_response(request, context, activation)


@router.get("/capability", response_model=BillingCapabilityResponse)
def billing_capability(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
) -> BillingCapabilityResponse:
    available, writes_available, organization_local_date = _billing_readiness(
        request,
        session,
        context.organization.id,
        context.organization.timezone,
    )
    manual_activation = _manual_activation(session, context.organization.id)
    manual_mode = request.app.state.settings.billing_mode == "manual"
    return BillingCapabilityResponse(
        organization_id=context.organization.id,
        sandbox=not manual_mode,
        provenance_label=(PRIVATE_MANUAL_BILLING_LABEL if manual_mode else SYNTHETIC_BILLING_LABEL),
        runtime_available=available,
        writes_available=writes_available,
        billing_mode=request.app.state.settings.billing_mode,
        manual_activation_required=manual_mode and manual_activation is None,
        manual_activated=manual_mode and manual_activation is not None,
        organization_timezone=context.organization.timezone,
        organization_local_date=organization_local_date,
        server_time=datetime.now(UTC),
        reason_code=None if available else "billing_ledger_unavailable",
    )


@router.post(
    "/commands/prepare",
    response_model=BillingCommandPreparationResponse,
    status_code=status.HTTP_201_CREATED,
)
def prepare_billing_command(
    payload: PrepareBillingCommand,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> BillingCommandPreparationResponse:
    permission = {
        "account_open": "billing:manage",
        "account_payer_assign": "billing:manage",
        "rate_version_publish": "billing:manage",
        "agreement_establish": "billing:manage",
        "invoice_issue": "billing:issue",
        "payment_record": "billing:payments",
        "payment_allocate": "billing:payments",
        "credit_issue": "billing:adjust",
    }[payload.command_type]
    if context.role.key not in {"owner", "administrator"} or permission not in set(
        context.role.permissions or []
    ):
        raise HTTPException(403, detail={"code": "billing_permission_required"})
    _require_write_ready(request, session, context)
    ensure_writable(request)
    typed, target_scope, digest = _canonical_preparation(payload)
    client_operation_id = typed.client_operation_id
    lock_client_operation(session, context.organization.id, client_operation_id)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_billing_operation_id', :value, true)"),
            {"value": str(client_operation_id)},
        )
    preparation = session.scalar(
        select(BillingCommandPreparation).where(
            BillingCommandPreparation.organization_id == context.organization.id,
            BillingCommandPreparation.client_operation_id == client_operation_id,
        )
    )
    if preparation is not None:
        if preparation.actor_user_id != context.user.id:
            raise HTTPException(404, detail={"code": "billing_command_preparation_not_found"})
        if (
            preparation.command_type != payload.command_type
            or preparation.target_scope != target_scope
            or preparation.request_hash != digest
        ):
            raise HTTPException(409, detail={"code": "billing_operation_reused"})
        return BillingCommandPreparationResponse(
            **_provenance_values(session, context.organization.id),
            organization_id=preparation.organization_id,
            client_operation_id=preparation.client_operation_id,
            command_type=preparation.command_type,
            target_scope=preparation.target_scope,
            request_hash=preparation.request_hash,
            prepared_at=_as_utc(preparation.prepared_at),
            exact_retry=True,
        )
    if (
        session.scalar(
            select(BillingCommandClaim.id).where(
                BillingCommandClaim.organization_id == context.organization.id,
                BillingCommandClaim.client_operation_id == client_operation_id,
            )
        )
        is not None
    ):
        raise HTTPException(409, detail={"code": "billing_operation_finalized_absent"})
    prepared_at = datetime.now(UTC)
    provenance = _provenance_values(session, context.organization.id)
    preparation = BillingCommandPreparation(
        id=uuid4(),
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=payload.command_type,
        target_scope=target_scope,
        request_hash=digest,
        prepared_at=prepared_at,
    )
    session.add(preparation)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, detail={"code": "billing_operation_reused"}) from None
    return BillingCommandPreparationResponse(
        **provenance,
        organization_id=context.organization.id,
        client_operation_id=client_operation_id,
        command_type=payload.command_type,
        target_scope=target_scope,
        request_hash=digest,
        prepared_at=prepared_at,
        exact_retry=False,
    )


@router.get("/commands/{client_operation_id}", response_model=BillingCommandReceiptResponse)
def billing_command_status(
    client_operation_id: UUID,
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    request_hash: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
) -> BillingCommandReceiptResponse:
    _require_available(request, context.organization.id)
    lock_client_operation(session, context.organization.id, client_operation_id)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_billing_operation_id', :value, true)"),
            {"value": str(client_operation_id)},
        )
    preparation = session.scalar(
        select(BillingCommandPreparation).where(
            BillingCommandPreparation.organization_id == context.organization.id,
            BillingCommandPreparation.client_operation_id == client_operation_id,
        )
    )
    receipt = session.scalar(
        select(BillingCommandReceipt).where(
            BillingCommandReceipt.organization_id == context.organization.id,
            BillingCommandReceipt.client_operation_id == client_operation_id,
        )
    )
    if receipt is not None:
        if (
            preparation is None
            or receipt.actor_user_id != context.user.id
            or receipt.request_hash != request_hash
            or receipt.actor_user_id != preparation.actor_user_id
            or receipt.command_type != preparation.command_type
            or receipt.request_hash != preparation.request_hash
        ):
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        committed_at = _as_utc(receipt.committed_at)
        return BillingCommandReceiptResponse(
            **_provenance_values(session, context.organization.id),
            organization_id=receipt.organization_id,
            client_operation_id=receipt.client_operation_id,
            command_type=receipt.command_type,
            request_hash=receipt.request_hash,
            result_kind=receipt.result_kind,
            result_id=receipt.result_id,
            committed_at=committed_at,
            exact_retry=True,
            action_path=safe_action_route(receipt.action_path),
        )
    claim = session.scalar(
        select(BillingCommandClaim).where(
            BillingCommandClaim.organization_id == context.organization.id,
            BillingCommandClaim.client_operation_id == client_operation_id,
        )
    )
    if claim is not None:
        if (
            preparation is None
            or claim.actor_user_id != context.user.id
            or claim.request_hash != request_hash
            or claim.command_type != preparation.command_type
            or claim.request_hash != preparation.request_hash
            or claim.target_scope != preparation.target_scope
        ):
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        raise HTTPException(
            404,
            detail={
                "code": "billing_operation_finalized_absent",
                "organization_id": str(context.organization.id),
                "client_operation_id": str(client_operation_id),
                "finalized": True,
            },
        )
    if preparation is not None:
        if preparation.actor_user_id != context.user.id or preparation.request_hash != request_hash:
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        raise HTTPException(
            404,
            detail={
                "code": "billing_command_prepared_not_committed",
                "organization_id": str(context.organization.id),
                "client_operation_id": str(client_operation_id),
                "finalized": False,
            },
        )
    raise HTTPException(
        404,
        detail={
            "code": "billing_command_not_found",
            "organization_id": str(context.organization.id),
            "client_operation_id": str(client_operation_id),
            "finalized": False,
        },
    )


@router.post(
    "/commands/{client_operation_id}/finalize-absence",
    response_model=BillingAbsenceClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
def finalize_billing_command_absence(
    client_operation_id: UUID,
    payload: FinalizeBillingCommandAbsenceCommand,
    request: Request,
    context: BillingRecoveryContext,
    session: SessionDependency,
) -> BillingAbsenceClaimResponse:
    _require_write_ready(request, session, context)
    ensure_writable(request)
    lock_client_operation(session, context.organization.id, client_operation_id)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_billing_operation_id', :value, true)"),
            {"value": str(client_operation_id)},
        )
    preparation = session.scalar(
        select(BillingCommandPreparation).where(
            BillingCommandPreparation.organization_id == context.organization.id,
            BillingCommandPreparation.client_operation_id == client_operation_id,
        )
    )
    if preparation is None:
        raise HTTPException(404, detail={"code": "billing_command_preparation_not_found"})
    if (
        preparation.actor_user_id != context.user.id
        or preparation.request_hash != payload.expected_request_hash
    ):
        raise HTTPException(404, detail={"code": "billing_command_preparation_not_found"})
    digest = preparation.request_hash
    receipt = session.scalar(
        select(BillingCommandReceipt).where(
            BillingCommandReceipt.organization_id == context.organization.id,
            BillingCommandReceipt.client_operation_id == client_operation_id,
        )
    )
    if receipt is not None:
        if receipt.actor_user_id != context.user.id or receipt.request_hash != digest:
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        raise HTTPException(409, detail={"code": "billing_operation_already_committed"})
    claim = session.scalar(
        select(BillingCommandClaim).where(
            BillingCommandClaim.organization_id == context.organization.id,
            BillingCommandClaim.client_operation_id == client_operation_id,
        )
    )
    if claim is not None:
        if claim.actor_user_id != context.user.id:
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        if (
            claim.command_type != preparation.command_type
            or claim.request_hash != digest
            or claim.target_scope != preparation.target_scope
        ):
            raise HTTPException(409, detail={"code": "billing_operation_reused"})
        finalized_at = _as_utc(claim.finalized_at)
        return BillingAbsenceClaimResponse(
            organization_id=claim.organization_id,
            client_operation_id=claim.client_operation_id,
            command_type=claim.command_type,
            request_hash=claim.request_hash,
            target_scope=claim.target_scope,
            reason_code=claim.reason_code,
            finalized_at=finalized_at,
            exact_retry=True,
        )
    finalized_at = datetime.now(UTC)
    claim = BillingCommandClaim(
        id=uuid4(),
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=preparation.command_type,
        request_hash=digest,
        target_scope=preparation.target_scope,
        reason_code=payload.reason_code,
        finalized_at=finalized_at,
    )
    audit_kwargs = {
        "id": uuid4(),
        "organization_id": context.organization.id,
        "actor_user_id": context.user.id,
        "action": "billing.command.finalized_absent",
        "entity_id": None,
        "occurred_at": finalized_at,
        "details": {
            "client_operation_id": str(client_operation_id),
            "command_type": preparation.command_type,
            "request_hash": digest,
            "reason_code": payload.reason_code,
            "claim_id": str(claim.id),
        },
    }
    if preparation.command_type in {"account_open", "account_payer_assign"}:
        recovery_audit = AuditEvent(entity_type="billing_account", **audit_kwargs)
    elif preparation.command_type == "rate_version_publish":
        recovery_audit = AuditEvent(entity_type="billing_rate_plan", **audit_kwargs)
    elif preparation.command_type == "agreement_establish":
        recovery_audit = AuditEvent(entity_type="billing_agreement", **audit_kwargs)
    elif preparation.command_type == "invoice_issue":
        recovery_audit = AuditEvent(entity_type="billing_invoice", **audit_kwargs)
    elif preparation.command_type == "payment_record":
        recovery_audit = AuditEvent(entity_type="billing_payment", **audit_kwargs)
    elif preparation.command_type == "payment_allocate":
        recovery_audit = AuditEvent(entity_type="billing_allocation", **audit_kwargs)
    else:
        recovery_audit = AuditEvent(entity_type="billing_credit", **audit_kwargs)
    # The retained audit bridge emits the single canonical broad invalidation.
    # A null entity id deliberately prevents a nonexistent recovery claim from
    # being interpreted as a focusable billing record.
    session.add(recovery_audit)
    try:
        session.flush()
        session.add(claim)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, detail={"code": "billing_operation_reconciliation_conflict"}
        ) from None
    return BillingAbsenceClaimResponse(
        organization_id=context.organization.id,
        client_operation_id=client_operation_id,
        command_type=preparation.command_type,
        request_hash=digest,
        target_scope=preparation.target_scope,
        reason_code=payload.reason_code,
        finalized_at=finalized_at,
        exact_retry=False,
    )


@router.get("/overview", response_model=BillingOverviewResponse)
def billing_overview(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
) -> BillingOverviewResponse:
    _require_available(request, context.organization.id)
    return _overview_response(session, context.organization.id)


@router.get("/readiness", response_model=BillingReadinessResponse)
def billing_readiness_projection(
    request: Request,
    context: BillingReadContext,
) -> BillingReadinessResponse:
    """Project every active child from enrollment facts into billing setup."""

    organization_id = context.organization.id
    _require_available(request, organization_id)
    try:
        as_of_date = datetime.now(ZoneInfo(context.organization.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(409, detail={"code": "organization_timezone_invalid"}) from None
    with billing_projection_snapshot(
        request.app.state.database,
        user_id=context.user.id,
        organization_id=organization_id,
    ) as snapshot:
        return build_billing_readiness(
            snapshot,
            organization_id=organization_id,
            as_of_date=as_of_date,
            source_attestations_required=request.app.state.settings.billing_mode != "manual",
        )


def _billing_readiness_batch_local_date(context: BasicContext) -> date:
    try:
        return datetime.now(ZoneInfo(context.organization.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(409, detail={"code": "organization_timezone_invalid"}) from None


def _raise_billing_readiness_batch_snapshot_advanced(sequence: int) -> None:
    raise HTTPException(
        409,
        detail={
            "code": "billing_readiness_batch_snapshot_advanced",
            "restart_required": True,
            "data_through_realtime_sequence": sequence,
        },
    )


def _billing_readiness_batch_capability(
    request: Request,
    session: Session,
    context: BasicContext,
) -> tuple[bool, bool]:
    _runtime_available, writes_available, _local_date = _billing_readiness(
        request,
        session,
        context.organization.id,
        context.organization.timezone,
    )
    manual_activation_required = bool(
        request.app.state.settings.billing_mode == "manual"
        and _manual_activation(session, context.organization.id) is None
    )
    return writes_available, manual_activation_required


def _billing_readiness_batch_search_text(
    group,
    full_membership_search_text: str = "",
) -> str:
    values = [
        group.family_name,
        group.facility_name,
        group.program_name,
        group.program_type,
        group.age_group,
        group.readiness_status,
        *group.reason_codes,
        *(child.family_name for child in group.affected_children),
        *(child.child_name for child in group.affected_children),
        *(option.display_name for option in group.payer_options),
        *(option.code for option in group.rate_plan_options),
        *(option.name for option in group.rate_plan_options),
        full_membership_search_text,
    ]
    return "\n".join(value for value in values if value is not None).casefold()


@router.get(
    "/readiness/batch-plan",
    response_model=BillingReadinessBatchPlanResponse,
)
def billing_readiness_batch_plan(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    wave: Annotated[BillingReadinessBatchWave | None, Query()] = None,
    readiness_status: Annotated[
        BillingReadinessStatus | None,
        Query(alias="status"),
    ] = None,
    query: Annotated[str | None, Query(max_length=80)] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    snapshot_token: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
) -> BillingReadinessBatchPlanResponse:
    """Return a deterministic, privacy-bounded dependency plan without writing."""

    organization_id = context.organization.id
    _require_available(request, organization_id)
    as_of_date = _billing_readiness_batch_local_date(context)
    apply_available, manual_activation_required = _billing_readiness_batch_capability(
        request,
        session,
        context,
    )
    with billing_projection_snapshot(
        request.app.state.database,
        user_id=context.user.id,
        organization_id=organization_id,
    ) as snapshot:
        batch = build_billing_readiness_batch_snapshot(
            snapshot,
            organization_id=organization_id,
            as_of_date=as_of_date,
            source_attestations_required=request.app.state.settings.billing_mode != "manual",
        )
        if snapshot_token is not None and snapshot_token != batch.snapshot_token:
            _raise_billing_readiness_batch_snapshot_advanced(
                batch.readiness.data_through_realtime_sequence
            )
        counts_by_wave = Counter(group.wave for group in batch.groups)
        filtered = [
            group
            for group in batch.groups
            if (wave is None or group.wave == wave)
            and (
                readiness_status is None
                or group.readiness_status == readiness_status
            )
        ]
        normalized_query = (query or "").strip().casefold()
        if normalized_query:
            filtered = [
                group
                for group in filtered
                if normalized_query
                in _billing_readiness_batch_search_text(
                    group,
                    batch.membership_search_index.get(group.group_id, ""),
                )
            ]
        total = len(filtered)
        items = list(filtered[offset : offset + limit])
        next_offset = offset + len(items) if offset + len(items) < total else None
        return BillingReadinessBatchPlanResponse(
            organization_id=organization_id,
            generated_at=batch.readiness.generated_at,
            as_of_date=batch.readiness.as_of_date,
            data_through_realtime_sequence=batch.readiness.data_through_realtime_sequence,
            snapshot_token=batch.snapshot_token,
            apply_available=apply_available,
            manual_activation_required=manual_activation_required,
            counts=BillingReadinessBatchWaveCounts(
                total=len(batch.groups),
                account_payer=counts_by_wave["account_payer"],
                rate_plan=counts_by_wave["rate_plan"],
                agreement=counts_by_wave["agreement"],
                ready=counts_by_wave["ready"],
                manual_review=counts_by_wave["manual_review"],
            ),
            page=BillingCollectionPage(
                offset=offset,
                limit=limit,
                returned=len(items),
                total=total,
                has_more=next_offset is not None,
                next_offset=next_offset,
            ),
            items=items,
        )


def _billing_batch_block(
    group_id: str,
    code: str,
    message: str,
) -> BillingReadinessBatchPreviewBlock:
    return BillingReadinessBatchPreviewBlock(
        group_id=group_id,
        code=code,
        message=message,
    )


def _billing_batch_command_for_selection(
    group,
    selection,
    wave: BillingReadinessActionableWave,
    *,
    reserved_rate_codes: frozenset[str] = frozenset(),
    as_of_date: date | None = None,
):
    if group.wave != wave or not group.actionable:
        return None, _billing_batch_block(
            selection.group_id,
            "billing_readiness_batch_group_not_actionable",
            "The selected group is not actionable in this dependency wave.",
        )
    if wave == "account_payer":
        if selection.payer_guardian_id not in {
            option.guardian_id for option in group.payer_options
        }:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_payer_not_available",
                "The selected payer is not an available guardian for this family.",
            )
        if group.suggested_command_type == "account_open":
            if group.family_id is None:
                return None, _billing_batch_block(
                    selection.group_id,
                    "billing_readiness_batch_account_scope_missing",
                    "The family billing-account scope is incomplete.",
                )
            typed = OpenBillingAccountCommand(
                client_operation_id=selection.client_operation_id,
                family_id=group.family_id,
                payer_guardian_id=selection.payer_guardian_id,
            )
            label = f"Open billing account for {group.family_name}"
            execute_path = "/api/v1/billing/accounts"
        elif (
            group.suggested_command_type == "account_payer_assign"
            and group.billing_account_id is not None
            and group.latest_payer_version_id is not None
            and group.latest_payer_version_number is not None
        ):
            typed = AssignBillingAccountPayerCommand(
                client_operation_id=selection.client_operation_id,
                account_id=group.billing_account_id,
                payer_guardian_id=selection.payer_guardian_id,
                expected_latest_payer_version_id=group.latest_payer_version_id,
                expected_latest_payer_version_number=group.latest_payer_version_number,
            )
            label = f"Assign payer for {group.family_name}"
            execute_path = (
                f"/api/v1/billing/accounts/{group.billing_account_id}/payer-assign"
            )
        else:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_payer_scope_missing",
                "The payer assignment version scope is incomplete.",
            )
    elif wave == "rate_plan":
        if (
            group.suggested_command_type != "rate_version_publish"
            or group.facility_id is None
            or group.program_id is None
            or group.program_type is None
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_scope_missing",
                "The facility and program rate scope is incomplete.",
            )
        selected_option = next(
            (
                option
                for option in group.rate_plan_options
                if option.rate_plan_id == selection.rate_plan_id
            ),
            None,
        )
        if selection.rate_plan_id is not None and selected_option is None:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_plan_not_available",
                "The selected rate plan is not available in this group.",
            )
        if (
            selection.rate_plan_id is None
            and selection.code is not None
            and selection.code.casefold() in reserved_rate_codes
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_code_unavailable",
                "The new rate-plan code is already in use.",
            )
        if selected_option is not None and (
            selected_option.latest_version_id is None
            or selected_option.latest_version_number is None
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_version_missing",
                "The selected existing rate plan has no canonical latest version.",
            )
        if (
            selected_option is not None
            and not selected_option.revision_can_resolve_as_of_date
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_revision_cannot_resolve_current_gap",
                "This existing rate plan cannot be revised into a current rate.",
            )
        if (
            selected_option is not None
            and selected_option.latest_effective_from is not None
            and selection.effective_from <= selected_option.latest_effective_from
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_effective_order_invalid",
                "A new rate version must begin after the selected latest version.",
            )
        if as_of_date is not None and (
            selection.effective_from > as_of_date
            or (
                selection.effective_until is not None
                and selection.effective_until < as_of_date
            )
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_not_current",
                "The proposed rate window must include the plan date.",
            )
        typed = PublishRatePlanVersionCommand(
            client_operation_id=selection.client_operation_id,
            rate_plan_id=selection.rate_plan_id,
            expected_latest_version_id=(
                selected_option.latest_version_id if selected_option else None
            ),
            expected_latest_version_number=(
                selected_option.latest_version_number if selected_option else None
            ),
            code=selection.code,
            name=selection.name,
            program_type=group.program_type if selected_option is None else None,
            charge_kind="core_care" if selected_option is None else None,
            age_group=group.age_group if selected_option is None else None,
            facility_id=group.facility_id if selected_option is None else None,
            program_id=group.program_id if selected_option is None else None,
            billing_unit=selection.billing_unit,
            unit_amount_minor=selection.unit_amount_minor,
            tax_rate_basis_points=0,
            effective_from=selection.effective_from,
            effective_until=selection.effective_until,
            description=selection.description,
        )
        label = (
            f"Publish rate for {group.program_name}"
            + (f" · {group.age_group}" if group.age_group else "")
        )
        execute_path = "/api/v1/billing/rate-plans"
    else:
        subject = group.affected_children[0]
        if (
            group.suggested_command_type != "agreement_establish"
            or len(group.affected_children) != 1
            or group.billing_account_id is None
            or subject.enrollment_id is None
            or group.rate_plan_version_id is None
            or group.rate_billing_unit is None
            or group.rate_unit_amount_minor is None
            or group.agreement_effective_from_min is None
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_agreement_scope_missing",
                "The enrollment-scoped agreement references are incomplete.",
            )
        required_frequency = {
            "weekly_period": "weekly",
            "biweekly_period": "biweekly",
            "monthly_period": "monthly",
            "service_event": "per_service",
        }[group.rate_billing_unit]
        if selection.billing_frequency != required_frequency:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_unit_frequency_mismatch",
                "The agreement frequency must match the selected rate billing unit.",
            )
        if selection.family_amount_minor_per_unit != group.rate_unit_amount_minor:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_rate_portions_do_not_balance",
                "The family amount must equal the selected rate amount.",
            )
        if selection.effective_from < group.agreement_effective_from_min:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_agreement_starts_before_scope",
                "The agreement cannot begin before its rate and enrollment scope.",
            )
        if group.agreement_effective_until_required and selection.effective_until is None:
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_agreement_end_required",
                "This bounded rate or enrollment requires an agreement end date.",
            )
        if (
            group.agreement_effective_until_max is not None
            and (
                selection.effective_from > group.agreement_effective_until_max
                or selection.effective_until is None
                or selection.effective_until > group.agreement_effective_until_max
            )
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_agreement_ends_after_scope",
                "The agreement dates exceed the selected rate or enrollment window.",
            )
        if as_of_date is not None and (
            selection.effective_from > as_of_date
            or (
                selection.effective_until is not None
                and selection.effective_until < as_of_date
            )
        ):
            return None, _billing_batch_block(
                selection.group_id,
                "billing_readiness_batch_agreement_not_current",
                "The proposed agreement window must include the plan date.",
            )
        typed = EstablishBillingAgreementCommand(
            client_operation_id=selection.client_operation_id,
            agreement_id=None,
            expected_latest_version_id=None,
            expected_latest_version_number=None,
            account_id=group.billing_account_id,
            child_id=subject.child_id,
            enrollment_id=subject.enrollment_id,
            rate_plan_version_id=group.rate_plan_version_id,
            billing_frequency=selection.billing_frequency,
            effective_from=selection.effective_from,
            effective_until=selection.effective_until,
            family_amount_minor_per_unit=selection.family_amount_minor_per_unit,
            funding_amount_minor_per_unit=0,
            reviewed=True,
        )
        label = f"Establish agreement for {subject.child_name}"
        execute_path = "/api/v1/billing/agreements"
    command_type = group.suggested_command_type
    preparation = PrepareBillingCommand(
        command_type=command_type,
        request_payload=typed.model_dump(mode="python"),
    )
    _canonical, target_scope, request_hash = _canonical_preparation(preparation)
    request_payload = typed.model_dump(mode="json")
    return (
        {
            "group_id": group.group_id,
            "label": label,
            "command_type": command_type,
            "client_operation_id": selection.client_operation_id,
            "target_scope": target_scope,
            "request_hash": request_hash,
            "request_payload": request_payload,
            "prepare_request": BillingReadinessBatchPrepareRequest(
                command_type=command_type,
                request_payload=request_payload,
            ),
            "execute_path": execute_path,
            "affected_count": group.affected_count,
        },
        None,
    )


@router.post(
    "/readiness/batch-plan/preview",
    response_model=BillingReadinessBatchPreviewResponse,
)
def preview_billing_readiness_batch_plan(
    payload: PreviewBillingReadinessBatchCommand,
    request: Request,
    context: BillingManageContext,
    session: SessionDependency,
) -> BillingReadinessBatchPreviewResponse:
    """Normalize one reviewed setup wave into existing command intents, without writes."""

    organization_id = context.organization.id
    _require_available(request, organization_id)
    as_of_date = _billing_readiness_batch_local_date(context)
    apply_available, manual_activation_required = _billing_readiness_batch_capability(
        request,
        session,
        context,
    )
    with billing_projection_snapshot(
        request.app.state.database,
        user_id=context.user.id,
        organization_id=organization_id,
    ) as snapshot:
        batch = build_billing_readiness_batch_snapshot(
            snapshot,
            organization_id=organization_id,
            as_of_date=as_of_date,
            source_attestations_required=request.app.state.settings.billing_mode != "manual",
        )
        if payload.snapshot_token != batch.snapshot_token:
            _raise_billing_readiness_batch_snapshot_advanced(
                batch.readiness.data_through_realtime_sequence
            )
        groups_by_id = {group.group_id: group for group in batch.groups}
        group_order = {group.group_id: index for index, group in enumerate(batch.groups)}
        selections = sorted(
            payload.selections,
            key=lambda selection: (
                group_order.get(selection.group_id, len(group_order)),
                selection.group_id,
            ),
        )
        already_used_operation_ids = set(
            snapshot.scalars(
                select(BillingCommandPreparation.client_operation_id).where(
                    BillingCommandPreparation.organization_id == organization_id,
                    BillingCommandPreparation.client_operation_id.in_(
                        [selection.client_operation_id for selection in selections]
                    ),
                )
            )
        )
        intents: list[BillingReadinessBatchPreviewIntent] = []
        blocked: list[BillingReadinessBatchPreviewBlock] = []
        for selection in selections:
            if selection.client_operation_id in already_used_operation_ids:
                blocked.append(
                    _billing_batch_block(
                        selection.group_id,
                        "billing_readiness_batch_operation_already_used",
                        "Use a new client operation id for this reviewed preview.",
                    )
                )
                continue
            group = groups_by_id.get(selection.group_id)
            if group is None:
                blocked.append(
                    _billing_batch_block(
                        selection.group_id,
                        "billing_readiness_batch_group_not_found",
                        "The selected dependency group is not present in this snapshot.",
                    )
                )
                continue
            intent_values, block = _billing_batch_command_for_selection(
                group,
                selection,
                payload.wave,
                reserved_rate_codes=batch.reserved_rate_codes,
                as_of_date=batch.readiness.as_of_date,
            )
            if block is not None:
                blocked.append(block)
                continue
            intents.append(
                BillingReadinessBatchPreviewIntent(
                    sequence=len(intents) + 1,
                    **intent_values,
                )
            )
        return BillingReadinessBatchPreviewResponse(
            organization_id=organization_id,
            snapshot_token=batch.snapshot_token,
            wave=payload.wave,
            previewed_at=datetime.now(UTC),
            data_through_realtime_sequence=(
                batch.readiness.data_through_realtime_sequence
            ),
            apply_available=apply_available,
            manual_activation_required=manual_activation_required,
            intents=intents,
            blocked=blocked,
        )


@router.get(
    "/families/{family_id}/summary",
    response_model=BillingFamilyFinanceSummaryResponse,
)
def billing_family_finance_summary(
    family_id: UUID,
    request: Request,
    context: BillingReadContext,
) -> BillingFamilyFinanceSummaryResponse:
    """Return family/invoice settlement and child charge attribution."""

    organization_id = context.organization.id
    _require_available(request, organization_id)
    try:
        as_of_date = datetime.now(ZoneInfo(context.organization.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(409, detail={"code": "organization_timezone_invalid"}) from None
    with billing_projection_snapshot(
        request.app.state.database,
        user_id=context.user.id,
        organization_id=organization_id,
    ) as snapshot:
        try:
            summary = build_family_finance_summary(
                snapshot,
                organization_id=organization_id,
                family_id=family_id,
                as_of_date=as_of_date,
                source_attestations_required=request.app.state.settings.billing_mode != "manual",
            )
        except BillingProjectionIntegrityError as error:
            raise HTTPException(409, detail={"code": error.code}) from None
        if summary is None:
            raise HTTPException(404, detail={"code": "billing_family_not_found"})
        return summary


@router.get("/workspace", response_model=BillingWorkspaceResponse)
def billing_workspace(
    request: Request,
    context: BillingReadContext,
    page_size: int = Query(default=500, ge=1, le=500),
    snapshot_token: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
    accounts_offset: int = Query(default=0, ge=0),
    payer_versions_offset: int = Query(default=0, ge=0),
    invoices_offset: int = Query(default=0, ge=0),
    payments_offset: int = Query(default=0, ge=0),
    rate_plans_offset: int = Query(default=0, ge=0),
    agreements_offset: int = Query(default=0, ge=0),
    allocations_offset: int = Query(default=0, ge=0),
    credits_offset: int = Query(default=0, ge=0),
) -> BillingWorkspaceResponse:
    """Return one coherent page-set, bound to a fail-closed snapshot token."""

    organization_id = context.organization.id
    _require_available(request, organization_id)
    snapshot = request.app.state.database.session_factory()
    try:
        if snapshot.bind is not None and snapshot.bind.dialect.name == "postgresql":
            snapshot.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
        set_rls_user(snapshot, context.user.id)
        set_rls_organization(snapshot, organization_id)
        generated_at = datetime.now(UTC)
        event_cursor = int(
            snapshot.scalar(
                select(func.coalesce(func.max(RealtimeEvent.sequence_id), 0)).where(
                    RealtimeEvent.organization_id == organization_id
                )
            )
            or 0
        )
        canonical_counts = {
            "accounts": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingAccount)
                    .where(BillingAccount.organization_id == organization_id)
                )
                or 0
            ),
            "payer_versions": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingAccountPayerVersion)
                    .where(BillingAccountPayerVersion.organization_id == organization_id)
                )
                or 0
            ),
            "invoices": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingInvoice)
                    .where(BillingInvoice.organization_id == organization_id)
                )
                or 0
            ),
            "payments": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingPayment)
                    .where(BillingPayment.organization_id == organization_id)
                )
                or 0
            ),
            "rate_plans": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingRatePlan)
                    .where(BillingRatePlan.organization_id == organization_id)
                )
                or 0
            ),
            "agreements": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingAgreement)
                    .where(BillingAgreement.organization_id == organization_id)
                )
                or 0
            ),
            "allocations": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingAllocation)
                    .where(BillingAllocation.organization_id == organization_id)
                )
                or 0
            ),
            "credits": int(
                snapshot.scalar(
                    select(func.count())
                    .select_from(BillingCredit)
                    .where(BillingCredit.organization_id == organization_id)
                )
                or 0
            ),
        }
        current_snapshot_token = hashlib.sha256(
            (
                f"0033|{organization_id}|{event_cursor}|"
                + "|".join(f"{name}:{canonical_counts[name]}" for name in sorted(canonical_counts))
            ).encode("utf-8")
        ).hexdigest()
        if snapshot_token is not None and snapshot_token != current_snapshot_token:
            raise HTTPException(
                409,
                detail={
                    "code": "billing_workspace_snapshot_advanced",
                    "restart_required": True,
                    "data_through_realtime_sequence": event_cursor,
                },
            )
        account_rows = list(
            snapshot.execute(
                select(BillingAccount, Family.name)
                .join(
                    Family,
                    (Family.organization_id == BillingAccount.organization_id)
                    & (Family.id == BillingAccount.family_id),
                )
                .where(BillingAccount.organization_id == organization_id)
                .order_by(Family.name, BillingAccount.account_number, BillingAccount.id)
                .limit(page_size)
                .offset(accounts_offset)
            )
        )
        account_items = [
            _account_summary(snapshot, account, family_name)
            for account, family_name in account_rows
        ]
        payer_version_items = [
            _payer_version_response(version)
            for version in snapshot.scalars(
                select(BillingAccountPayerVersion)
                .where(BillingAccountPayerVersion.organization_id == organization_id)
                .order_by(
                    BillingAccountPayerVersion.billing_account_id,
                    BillingAccountPayerVersion.version_number,
                    BillingAccountPayerVersion.id,
                )
                .limit(page_size)
                .offset(payer_versions_offset)
            )
        ]
        invoice_items = [
            _invoice_response(snapshot, invoice)
            for invoice in snapshot.scalars(
                select(BillingInvoice)
                .where(BillingInvoice.organization_id == organization_id)
                .order_by(
                    BillingInvoice.issue_date.desc(),
                    BillingInvoice.issued_at.desc(),
                    BillingInvoice.id.desc(),
                )
                .limit(page_size)
                .offset(invoices_offset)
            )
        ]
        payment_items = [
            _payment_response(snapshot, payment)
            for payment in snapshot.scalars(
                select(BillingPayment)
                .where(BillingPayment.organization_id == organization_id)
                .order_by(
                    BillingPayment.received_at.desc(),
                    BillingPayment.recorded_at.desc(),
                    BillingPayment.id.desc(),
                )
                .limit(page_size)
                .offset(payments_offset)
            )
        ]
        rate_items = [
            _rate_plan_response(snapshot, plan)
            for plan in snapshot.scalars(
                select(BillingRatePlan)
                .where(BillingRatePlan.organization_id == organization_id)
                .order_by(BillingRatePlan.name, BillingRatePlan.code, BillingRatePlan.id)
                .limit(page_size)
                .offset(rate_plans_offset)
            )
        ]
        agreement_items = [
            _agreement_response(snapshot, agreement)
            for agreement in snapshot.scalars(
                select(BillingAgreement)
                .where(BillingAgreement.organization_id == organization_id)
                .order_by(BillingAgreement.created_at.desc(), BillingAgreement.id.desc())
                .limit(page_size)
                .offset(agreements_offset)
            )
        ]
        allocation_items = [
            _allocation_response(allocation)
            for allocation in snapshot.scalars(
                select(BillingAllocation)
                .where(BillingAllocation.organization_id == organization_id)
                .order_by(BillingAllocation.allocated_at.desc(), BillingAllocation.id.desc())
                .limit(page_size)
                .offset(allocations_offset)
            )
        ]
        credit_items = [
            _credit_response(credit)
            for credit in snapshot.scalars(
                select(BillingCredit)
                .where(BillingCredit.organization_id == organization_id)
                .order_by(BillingCredit.issued_at.desc(), BillingCredit.id.desc())
                .limit(page_size)
                .offset(credits_offset)
            )
        ]
        offsets = {
            "accounts": accounts_offset,
            "payer_versions": payer_versions_offset,
            "invoices": invoices_offset,
            "payments": payments_offset,
            "rate_plans": rate_plans_offset,
            "agreements": agreements_offset,
            "allocations": allocations_offset,
            "credits": credits_offset,
        }
        returned = {
            "accounts": len(account_items),
            "payer_versions": len(payer_version_items),
            "invoices": len(invoice_items),
            "payments": len(payment_items),
            "rate_plans": len(rate_items),
            "agreements": len(agreement_items),
            "allocations": len(allocation_items),
            "credits": len(credit_items),
        }
        pages = {
            name: _page(
                offset=offsets[name],
                limit=page_size,
                total=canonical_counts[name],
                returned=returned[name],
            )
            for name in canonical_counts
        }
        complete = all(page.offset == 0 and not page.has_more for page in pages.values())
        return BillingWorkspaceResponse(
            **_provenance_values(snapshot, organization_id),
            organization_id=organization_id,
            complete=complete,
            canonical_collection_limit=page_size,
            generated_at=generated_at,
            data_through_realtime_sequence=event_cursor,
            paging=BillingWorkspacePaging(
                snapshot_token=current_snapshot_token,
                accounts=pages["accounts"],
                payer_versions=pages["payer_versions"],
                invoices=pages["invoices"],
                payments=pages["payments"],
                rate_plans=pages["rate_plans"],
                agreements=pages["agreements"],
                allocations=pages["allocations"],
                credits=pages["credits"],
            ),
            overview=_overview_response(snapshot, organization_id),
            accounts=BillingAccountListResponse(
                organization_id=organization_id,
                items=account_items,
                total=canonical_counts["accounts"],
            ),
            payer_versions=BillingAccountPayerVersionListResponse(
                organization_id=organization_id,
                items=payer_version_items,
                total=canonical_counts["payer_versions"],
            ),
            invoices=BillingInvoiceListResponse(
                organization_id=organization_id,
                items=invoice_items,
                total=canonical_counts["invoices"],
            ),
            payments=BillingPaymentListResponse(
                organization_id=organization_id,
                items=payment_items,
                total=canonical_counts["payments"],
            ),
            rate_plans=BillingRatePlanListResponse(
                organization_id=organization_id,
                items=rate_items,
                total=canonical_counts["rate_plans"],
            ),
            agreements=BillingAgreementListResponse(
                organization_id=organization_id,
                items=agreement_items,
                total=canonical_counts["agreements"],
            ),
            allocations=BillingAllocationListResponse(
                organization_id=organization_id,
                items=allocation_items,
                total=canonical_counts["allocations"],
                limit=page_size,
                offset=allocations_offset,
            ),
            credits=BillingCreditListResponse(
                organization_id=organization_id,
                items=credit_items,
                total=canonical_counts["credits"],
                limit=page_size,
                offset=credits_offset,
            ),
        )
    finally:
        snapshot.rollback()
        snapshot.close()


@router.get("/source-options", response_model=BillingSourceOptionsResponse)
def billing_source_options(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BillingSourceOptionsResponse:
    _require_available(request, context.organization.id)
    organization_id = context.organization.id
    manual_sources = request.app.state.settings.billing_mode == "manual"
    filters = [
        Family.organization_id == organization_id,
        Family.status == "active",
    ]
    if not manual_sources:
        filters.extend(
            [
                _synthetic_source_exists(organization_id, "organization", organization_id),
                _synthetic_source_exists(organization_id, "family", Family.id),
            ]
        )
    normalized_search = (search or "").strip()
    if normalized_search:
        escaped = normalized_search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        filters.append(
            or_(
                Family.name.ilike(pattern, escape="\\"),
                Family.file_number.ilike(pattern, escape="\\"),
            )
        )
    total = int(session.scalar(select(func.count()).select_from(Family).where(*filters)) or 0)
    families = list(
        session.scalars(
            select(Family)
            .where(*filters)
            .order_by(Family.name, Family.id)
            .limit(limit)
            .offset(offset)
        )
    )
    try:
        local_today = datetime.now(ZoneInfo(context.organization.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(409, detail={"code": "organization_timezone_invalid"}) from None
    items: list[dict] = []
    for family in families:
        guardian_filters = [
            Guardian.organization_id == organization_id,
            Guardian.family_id == family.id,
            Guardian.retired_at.is_(None),
        ]
        if not manual_sources:
            guardian_filters.append(
                _synthetic_source_exists(organization_id, "guardian", Guardian.id)
            )
        guardians = list(
            session.scalars(
                select(Guardian)
                .where(*guardian_filters)
                .order_by(Guardian.is_primary.desc(), Guardian.last_name, Guardian.first_name)
            )
        )
        child_filters = [
            Child.organization_id == organization_id,
            Child.family_id == family.id,
            Child.is_active.is_(True),
        ]
        if not manual_sources:
            child_filters.append(_synthetic_source_exists(organization_id, "child", Child.id))
        children = list(
            session.scalars(
                select(Child).where(*child_filters).order_by(Child.last_name, Child.first_name)
            )
        )
        child_items: list[dict] = []
        for child in children:
            enrollment_filters = [
                Enrollment.organization_id == organization_id,
                Enrollment.child_id == child.id,
                Enrollment.status == "active",
                Enrollment.start_date <= local_today,
                or_(Enrollment.end_date.is_(None), Enrollment.end_date >= local_today),
            ]
            if not manual_sources:
                enrollment_filters.append(
                    _synthetic_source_exists(organization_id, "enrollment", Enrollment.id)
                )
            enrollment = session.scalar(
                select(Enrollment)
                .where(*enrollment_filters)
                .order_by(Enrollment.start_date.desc(), Enrollment.created_at.desc())
                .limit(1)
            )
            program_type = None
            if enrollment is not None and enrollment.program_id is not None:
                program_type = session.scalar(
                    select(Program.program_type).where(
                        Program.organization_id == organization_id,
                        Program.facility_id == enrollment.facility_id,
                        Program.id == enrollment.program_id,
                    )
                )
            child_items.append(
                {
                    "organization_id": organization_id,
                    "id": child.id,
                    "family_id": family.id,
                    "first_name": child.first_name,
                    "last_name": child.last_name,
                    "age_group": child.age_group,
                    "enrollment_id": enrollment.id if enrollment else None,
                    "facility_id": enrollment.facility_id if enrollment else None,
                    "program_id": enrollment.program_id if enrollment else None,
                    "program_type": program_type,
                }
            )
        items.append(
            {
                "organization_id": organization_id,
                "id": family.id,
                "name": family.name,
                "status": family.status,
                "guardians": [
                    {
                        "organization_id": organization_id,
                        "id": guardian.id,
                        "family_id": family.id,
                        "first_name": guardian.first_name,
                        "last_name": guardian.last_name,
                        "email": guardian.email,
                        "cell_phone": guardian.cell_phone,
                    }
                    for guardian in guardians
                ],
                "children": child_items,
            }
        )
    program_filters = [
        Program.organization_id == organization_id,
        Program.is_active.is_(True),
        Facility.status == "active",
    ]
    if not manual_sources:
        program_filters.extend(
            [
                _synthetic_source_exists(organization_id, "facility", Facility.id),
                _synthetic_source_exists(organization_id, "program", Program.id),
            ]
        )
    program_rows = list(
        session.execute(
            select(Program, Facility.name)
            .join(
                Facility,
                (Facility.organization_id == Program.organization_id)
                & (Facility.id == Program.facility_id),
            )
            .where(*program_filters)
            .order_by(Facility.name, Program.name)
        )
    )
    return BillingSourceOptionsResponse(
        organization_id=organization_id,
        items=items,
        programs=[
            {
                "organization_id": organization_id,
                "facility_id": program.facility_id,
                "facility_name": facility_name,
                "program_id": program.id,
                "program_name": program.name,
                "program_type": program.program_type,
                "minimum_age_months": program.minimum_age_months,
                "maximum_age_months": program.maximum_age_months,
            }
            for program, facility_name in program_rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/accounts", response_model=BillingAccountListResponse)
def billing_accounts(
    request: Request, context: BillingReadContext, session: SessionDependency
) -> BillingAccountListResponse:
    _require_available(request, context.organization.id)
    rows = list(
        session.execute(
            select(BillingAccount, Family.name)
            .join(
                Family,
                (Family.organization_id == BillingAccount.organization_id)
                & (Family.id == BillingAccount.family_id),
            )
            .where(BillingAccount.organization_id == context.organization.id)
            .order_by(Family.name, BillingAccount.account_number)
        )
    )
    items = [_account_summary(session, row[0], row[1]) for row in rows]
    return BillingAccountListResponse(
        organization_id=context.organization.id, items=items, total=len(items)
    )


@router.get("/accounts/{account_id}", response_model=BillingAccountDetailResponse)
def billing_account_detail(
    account_id: UUID,
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
) -> BillingAccountDetailResponse:
    _require_available(request, context.organization.id)
    row = session.execute(
        select(BillingAccount, Family.name)
        .join(
            Family,
            (Family.organization_id == BillingAccount.organization_id)
            & (Family.id == BillingAccount.family_id),
        )
        .where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == account_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail={"code": "billing_account_not_found"})
    payer_versions = list(
        session.scalars(
            select(BillingAccountPayerVersion)
            .where(
                BillingAccountPayerVersion.organization_id == context.organization.id,
                BillingAccountPayerVersion.billing_account_id == account_id,
            )
            .order_by(BillingAccountPayerVersion.version_number)
        )
    )
    invoices = list(
        session.scalars(
            select(BillingInvoice)
            .where(
                BillingInvoice.organization_id == context.organization.id,
                BillingInvoice.billing_account_id == account_id,
            )
            .order_by(BillingInvoice.issue_date.desc(), BillingInvoice.issued_at.desc())
        )
    )
    payments = list(
        session.scalars(
            select(BillingPayment)
            .where(
                BillingPayment.organization_id == context.organization.id,
                BillingPayment.billing_account_id == account_id,
            )
            .order_by(BillingPayment.received_at.desc(), BillingPayment.recorded_at.desc())
        )
    )
    agreements = list(
        session.scalars(
            select(BillingAgreement)
            .where(
                BillingAgreement.organization_id == context.organization.id,
                BillingAgreement.billing_account_id == account_id,
            )
            .order_by(BillingAgreement.created_at.desc())
        )
    )
    return BillingAccountDetailResponse(
        organization_id=context.organization.id,
        account=_account_summary(session, row[0], row[1]),
        payer_versions=[_payer_version_response(value) for value in payer_versions],
        invoices=[_invoice_response(session, value) for value in invoices],
        payments=[_payment_response(session, value) for value in payments],
        agreements=[_agreement_response(session, value) for value in agreements],
    )


@router.get(
    "/invoices/{invoice_id}/document-preview",
    response_model=BillingInvoiceDocumentPreviewResponse,
)
def billing_invoice_document_preview(
    invoice_id: UUID,
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
) -> BillingInvoiceDocumentPreviewResponse:
    """Return a canonical synthetic preview source; this endpoint never writes or delivers."""

    _require_available(request, context.organization.id)
    invoice = session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.organization_id == context.organization.id,
            BillingInvoice.id == invoice_id,
        )
    )
    if invoice is None:
        raise HTTPException(404, detail={"code": "billing_invoice_not_found"})
    return _invoice_document_preview(session, context=context, invoice=invoice)


@router.get("/invoices", response_model=BillingInvoiceListResponse)
def billing_invoices(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    account_id: UUID | None = None,
) -> BillingInvoiceListResponse:
    _require_available(request, context.organization.id)
    statement = select(BillingInvoice).where(
        BillingInvoice.organization_id == context.organization.id
    )
    if account_id is not None:
        statement = statement.where(BillingInvoice.billing_account_id == account_id)
    invoices = list(
        session.scalars(
            statement.order_by(BillingInvoice.issue_date.desc(), BillingInvoice.issued_at.desc())
        )
    )
    items = [_invoice_response(session, invoice) for invoice in invoices]
    return BillingInvoiceListResponse(
        organization_id=context.organization.id, items=items, total=len(items)
    )


@router.get("/payments", response_model=BillingPaymentListResponse)
def billing_payments(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    account_id: UUID | None = None,
) -> BillingPaymentListResponse:
    _require_available(request, context.organization.id)
    statement = select(BillingPayment).where(
        BillingPayment.organization_id == context.organization.id
    )
    if account_id is not None:
        statement = statement.where(BillingPayment.billing_account_id == account_id)
    payments = list(
        session.scalars(
            statement.order_by(BillingPayment.received_at.desc(), BillingPayment.recorded_at.desc())
        )
    )
    items = [_payment_response(session, payment) for payment in payments]
    return BillingPaymentListResponse(
        organization_id=context.organization.id, items=items, total=len(items)
    )


@router.get("/allocations", response_model=BillingAllocationListResponse)
def billing_allocations(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    account_id: UUID | None = None,
    invoice_id: UUID | None = None,
    payment_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BillingAllocationListResponse:
    _require_available(request, context.organization.id)
    filters = [BillingAllocation.organization_id == context.organization.id]
    if account_id is not None:
        filters.append(BillingAllocation.billing_account_id == account_id)
    if invoice_id is not None:
        filters.append(BillingAllocation.invoice_id == invoice_id)
    if payment_id is not None:
        filters.append(BillingAllocation.payment_id == payment_id)
    total = int(
        session.scalar(select(func.count()).select_from(BillingAllocation).where(*filters)) or 0
    )
    allocations = list(
        session.scalars(
            select(BillingAllocation)
            .where(*filters)
            .order_by(BillingAllocation.allocated_at.desc(), BillingAllocation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return BillingAllocationListResponse(
        organization_id=context.organization.id,
        items=[_allocation_response(value) for value in allocations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/credits", response_model=BillingCreditListResponse)
def billing_credits(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    account_id: UUID | None = None,
    invoice_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BillingCreditListResponse:
    _require_available(request, context.organization.id)
    filters = [BillingCredit.organization_id == context.organization.id]
    if account_id is not None:
        filters.append(BillingCredit.billing_account_id == account_id)
    if invoice_id is not None:
        filters.append(BillingCredit.invoice_id == invoice_id)
    total = int(
        session.scalar(select(func.count()).select_from(BillingCredit).where(*filters)) or 0
    )
    credits = list(
        session.scalars(
            select(BillingCredit)
            .where(*filters)
            .order_by(BillingCredit.issued_at.desc(), BillingCredit.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return BillingCreditListResponse(
        organization_id=context.organization.id,
        items=[_credit_response(value) for value in credits],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/rate-plans", response_model=BillingRatePlanListResponse)
def billing_rate_plans(
    request: Request, context: BillingReadContext, session: SessionDependency
) -> BillingRatePlanListResponse:
    _require_available(request, context.organization.id)
    plans = list(
        session.scalars(
            select(BillingRatePlan)
            .where(BillingRatePlan.organization_id == context.organization.id)
            .order_by(BillingRatePlan.name, BillingRatePlan.code)
        )
    )
    items = [_rate_plan_response(session, plan) for plan in plans]
    return BillingRatePlanListResponse(
        organization_id=context.organization.id, items=items, total=len(items)
    )


@router.get("/agreements", response_model=BillingAgreementListResponse)
def billing_agreements(
    request: Request,
    context: BillingReadContext,
    session: SessionDependency,
    account_id: UUID | None = None,
) -> BillingAgreementListResponse:
    _require_available(request, context.organization.id)
    statement = select(BillingAgreement).where(
        BillingAgreement.organization_id == context.organization.id
    )
    if account_id is not None:
        statement = statement.where(BillingAgreement.billing_account_id == account_id)
    agreements = list(session.scalars(statement.order_by(BillingAgreement.created_at.desc())))
    items = [_agreement_response(session, agreement) for agreement in agreements]
    return BillingAgreementListResponse(
        organization_id=context.organization.id, items=items, total=len(items)
    )


def _execute(request: Request, session: Session, context: BasicContext, callback):
    _require_write_ready(request, session, context)
    ensure_writable(request)
    provenance = _provenance_values(session, context.organization.id)
    return {**callback().as_response(), **provenance}


@router.post(
    "/accounts", response_model=BillingCommandReceiptResponse, status_code=status.HTTP_201_CREATED
)
def create_billing_account(
    payload: OpenBillingAccountCommand,
    request: Request,
    context: BillingManageContext,
    session: SessionDependency,
):
    return _execute(request, session, context, lambda: open_account(session, context, payload))


@router.post(
    "/accounts/{account_id}/payer-assign",
    response_model=BillingCommandReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_billing_account_payer(
    account_id: UUID,
    payload: AssignBillingAccountPayerCommand,
    request: Request,
    context: BillingManageContext,
    session: SessionDependency,
):
    return _execute(
        request,
        session,
        context,
        lambda: assign_account_payer(session, context, account_id, payload),
    )


@router.post(
    "/rate-plans",
    response_model=BillingCommandReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_billing_rate_version(
    payload: PublishRatePlanVersionCommand,
    request: Request,
    context: BillingManageContext,
    session: SessionDependency,
):
    return _execute(
        request,
        session,
        context,
        lambda: publish_rate_version(session, context, payload),
    )


@router.post(
    "/agreements",
    response_model=BillingCommandReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_billing_agreement(
    payload: EstablishBillingAgreementCommand,
    request: Request,
    context: BillingManageContext,
    session: SessionDependency,
):
    return _execute(
        request,
        session,
        context,
        lambda: establish_agreement(session, context, payload),
    )


@router.post(
    "/invoices/issue",
    response_model=BillingCommandReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_billing_invoice(
    payload: IssueBillingInvoiceCommand,
    request: Request,
    context: BillingIssueContext,
    session: SessionDependency,
):
    return _execute(request, session, context, lambda: issue_invoice(session, context, payload))


@router.post(
    "/payments", response_model=BillingCommandReceiptResponse, status_code=status.HTTP_201_CREATED
)
def record_billing_payment(
    payload: RecordBillingPaymentCommand,
    request: Request,
    context: BillingPaymentsContext,
    session: SessionDependency,
):
    return _execute(request, session, context, lambda: record_payment(session, context, payload))


@router.post(
    "/allocations",
    response_model=BillingCommandReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def allocate_billing_payment(
    payload: AllocateBillingPaymentCommand,
    request: Request,
    context: BillingPaymentsContext,
    session: SessionDependency,
):
    return _execute(
        request,
        session,
        context,
        lambda: allocate_payment(session, context, payload),
    )


@router.post(
    "/credits", response_model=BillingCommandReceiptResponse, status_code=status.HTTP_201_CREATED
)
def create_billing_credit(
    payload: IssueBillingCreditCommand,
    request: Request,
    context: BillingAdjustContext,
    session: SessionDependency,
):
    return _execute(request, session, context, lambda: issue_credit(session, context, payload))
