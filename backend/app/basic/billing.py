"""Append-only billing ledger commands and projections.

The module deliberately performs no card or bank movement.  It records only
reviewed childcare charges and already-settled off-platform payment facts.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.common import lock_client_operation
from app.api.basic.dependencies import BasicContext
from app.basic.billing_schemas import (
    MAX_CAD_MINOR,
    AllocateBillingPaymentCommand,
    AssignBillingAccountPayerCommand,
    EstablishBillingAgreementCommand,
    IssueBillingCreditCommand,
    IssueBillingInvoiceCommand,
    OpenBillingAccountCommand,
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
    BillingCredit,
    BillingInvoice,
    BillingInvoiceLine,
    BillingJournalEntry,
    BillingJournalLine,
    BillingManualActivation,
    BillingPayment,
    BillingRatePlan,
    BillingRatePlanVersion,
    BillingSandboxSourceAttestation,
    Child,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Program,
    RealtimeEvent,
)

CommandType = Literal[
    "account_open",
    "account_payer_assign",
    "rate_version_publish",
    "agreement_establish",
    "invoice_issue",
    "payment_record",
    "payment_allocate",
    "credit_issue",
]
ResultKind = Literal[
    "billing_account",
    "billing_rate_plan",
    "billing_agreement",
    "billing_invoice",
    "billing_payment",
    "billing_allocation",
    "billing_credit",
]


@dataclass(frozen=True)
class BillingCommandResult:
    organization_id: UUID
    client_operation_id: UUID
    command_type: CommandType
    request_hash: str
    result_kind: ResultKind
    result_id: UUID
    committed_at: datetime
    exact_retry: bool
    action_path: str

    def as_response(self) -> dict[str, Any]:
        committed_at = self.committed_at
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            committed_at = committed_at.replace(tzinfo=UTC)
        else:
            committed_at = committed_at.astimezone(UTC)
        return {
            "schema_version": "0033",
            "organization_id": self.organization_id,
            "client_operation_id": self.client_operation_id,
            "command_type": self.command_type,
            "request_hash": self.request_hash,
            "result_kind": self.result_kind,
            "result_id": self.result_id,
            "committed_at": committed_at,
            "exact_retry": self.exact_retry,
            "action_path": self.action_path,
        }


def _intent(payload) -> dict[str, Any]:
    return payload.model_dump(mode="python", exclude={"client_operation_id"})


def _lock_billing_scope(
    session: Session, organization_id: UUID, scope_kind: str, scope_id: UUID | str
) -> None:
    """Serialize immutable-ledger aggregates without requiring UPDATE table authority."""

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": f"billing:0033:{organization_id}:{scope_kind}:{scope_id}"},
        )


def _begin_command(
    session: Session,
    *,
    context: BasicContext,
    client_operation_id: UUID,
    command_type: CommandType,
    target_scope: UUID | str | None,
    intent: dict[str, Any],
) -> tuple[str, BillingCommandResult | None]:
    digest = command_hash(
        command_type=command_type,
        target_type="billing_command",
        target_scope=target_scope,
        intent=intent,
    )
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
        raise HTTPException(409, detail={"code": "billing_command_not_prepared"})
    if preparation.actor_user_id != context.user.id:
        raise HTTPException(404, detail={"code": "billing_command_preparation_not_found"})
    if (
        preparation.command_type != command_type
        or preparation.request_hash != digest
        or preparation.target_scope != str(target_scope)
    ):
        raise HTTPException(409, detail={"code": "billing_command_preparation_mismatch"})
    receipt = session.scalar(
        select(BillingCommandReceipt).where(
            BillingCommandReceipt.organization_id == context.organization.id,
            BillingCommandReceipt.client_operation_id == client_operation_id,
        )
    )
    if receipt is None:
        claim = session.scalar(
            select(BillingCommandClaim).where(
                BillingCommandClaim.organization_id == context.organization.id,
                BillingCommandClaim.client_operation_id == client_operation_id,
            )
        )
        if claim is None:
            return digest, None
        if claim.actor_user_id != context.user.id:
            raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
        if (
            claim.command_type != command_type
            or claim.request_hash != digest
            or claim.target_scope != str(target_scope)
            or claim.command_type != preparation.command_type
            or claim.request_hash != preparation.request_hash
            or claim.target_scope != preparation.target_scope
        ):
            raise HTTPException(409, detail={"code": "billing_operation_reused"})
        raise HTTPException(
            409,
            detail={
                "code": "billing_operation_finalized_absent",
                "organization_id": str(context.organization.id),
                "client_operation_id": str(client_operation_id),
            },
        )
    if receipt.actor_user_id != context.user.id:
        raise HTTPException(404, detail={"code": "billing_command_receipt_not_found"})
    if receipt.command_type != command_type or receipt.request_hash != digest:
        raise HTTPException(
            409,
            detail={
                "code": "billing_operation_reused",
                "client_operation_id": str(client_operation_id),
            },
        )
    return digest, BillingCommandResult(
        organization_id=receipt.organization_id,
        client_operation_id=receipt.client_operation_id,
        command_type=receipt.command_type,  # type: ignore[arg-type]
        request_hash=receipt.request_hash,
        result_kind=receipt.result_kind,  # type: ignore[arg-type]
        result_id=receipt.result_id,
        committed_at=receipt.committed_at,
        exact_retry=True,
        action_path=safe_action_route(receipt.action_path),
    )


def _finish_command(
    session: Session,
    *,
    context: BasicContext,
    client_operation_id: UUID,
    command_type: CommandType,
    request_hash: str,
    result_kind: ResultKind,
    result_id: UUID,
    action_path: str,
    audit_action: str,
    realtime_type: str,
    details: dict[str, Any] | None = None,
) -> BillingCommandResult:
    committed_at = datetime.now(UTC)
    resolved_path = safe_action_route(action_path)
    # Flush domain and journal facts before the terminal receipt. SQLite's
    # migration-owned receipt guard can therefore attest the complete journal;
    # PostgreSQL additionally verifies it with deferred constraint triggers.
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, detail={"code": "billing_command_conflict"}) from None
    receipt = BillingCommandReceipt(
        id=uuid4(),
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        request_hash=request_hash,
        result_kind=result_kind,
        result_id=result_id,
        action_path=resolved_path,
        committed_at=committed_at,
    )
    audit_kwargs = {
        "id": uuid4(),
        "organization_id": context.organization.id,
        "actor_user_id": context.user.id,
        "action": audit_action,
        "entity_id": result_id,
        "occurred_at": committed_at,
        "details": {
            "client_operation_id": str(client_operation_id),
            "request_hash": request_hash,
            "source": "billing_command",
            **(details or {}),
        },
    }
    realtime_kwargs = {
        "id": uuid4(),
        "organization_id": context.organization.id,
        "event_type": realtime_type,
        "entity_id": result_id,
        "occurred_at": committed_at,
        "payload": {
            "refresh_required": True,
            "source": "billing_command",
            "client_operation_id": str(client_operation_id),
            "request_hash": request_hash,
        },
    }
    if result_kind == "billing_account":
        audit_event = AuditEvent(entity_type="billing_account", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_account", **realtime_kwargs)
    elif result_kind == "billing_rate_plan":
        audit_event = AuditEvent(entity_type="billing_rate_plan", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_rate_plan", **realtime_kwargs)
    elif result_kind == "billing_agreement":
        audit_event = AuditEvent(entity_type="billing_agreement", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_agreement", **realtime_kwargs)
    elif result_kind == "billing_invoice":
        audit_event = AuditEvent(entity_type="billing_invoice", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_invoice", **realtime_kwargs)
    elif result_kind == "billing_payment":
        audit_event = AuditEvent(entity_type="billing_payment", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_payment", **realtime_kwargs)
    elif result_kind == "billing_allocation":
        audit_event = AuditEvent(entity_type="billing_allocation", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_allocation", **realtime_kwargs)
    else:
        audit_event = AuditEvent(entity_type="billing_credit", **audit_kwargs)
        realtime_event = RealtimeEvent(entity_type="billing_credit", **realtime_kwargs)
    session.add_all(
        [
            audit_event,
            realtime_event,
        ]
    )
    try:
        session.flush()
        # The immutable receipt is deliberately inserted last so SQLite and
        # PostgreSQL guards can attest the domain fact, journal, audit, and outbox.
        session.add(receipt)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, detail={"code": "billing_command_conflict"}) from None
    return BillingCommandResult(
        organization_id=context.organization.id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        request_hash=request_hash,
        result_kind=result_kind,
        result_id=result_id,
        committed_at=committed_at,
        exact_retry=False,
        action_path=resolved_path,
    )


def _journal(
    session: Session,
    *,
    context: BasicContext,
    client_operation_id: UUID,
    request_hash: str,
    entry_kind: str,
    source_type: str,
    source_id: UUID,
    debits: list[tuple[str, int]],
    credits: list[tuple[str, int]],
) -> BillingJournalEntry:
    debit_lines = [(code, amount) for code, amount in debits if amount > 0]
    credit_lines = [(code, amount) for code, amount in credits if amount > 0]
    debit_total = sum(amount for _code, amount in debit_lines)
    credit_total = sum(amount for _code, amount in credit_lines)
    if debit_total <= 0 or debit_total != credit_total:
        raise RuntimeError("Billing journal construction is not balanced")
    if debit_total > MAX_CAD_MINOR:
        raise HTTPException(422, detail={"code": "billing_money_limit_exceeded"})
    _lock_billing_scope(session, context.organization.id, "journal_book", context.organization.id)
    book_sequence = int(
        session.scalar(
            select(func.coalesce(func.max(BillingJournalEntry.book_sequence), 0) + 1).where(
                BillingJournalEntry.organization_id == context.organization.id
            )
        )
        or 1
    )
    entry = BillingJournalEntry(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=client_operation_id,
        request_hash=request_hash,
        book_sequence=book_sequence,
        entry_kind=entry_kind,
        source_type=source_type,
        source_id=source_id,
        currency="CAD",
        line_count=len(debit_lines) + len(credit_lines),
        total_debit_minor=debit_total,
        total_credit_minor=credit_total,
        posted_by_user_id=context.user.id,
        posted_at=datetime.now(UTC),
    )
    session.add(entry)
    line_number = 0
    for direction, values in (("debit", debit_lines), ("credit", credit_lines)):
        for account_code, amount_minor in values:
            line_number += 1
            session.add(
                BillingJournalLine(
                    id=uuid4(),
                    organization_id=context.organization.id,
                    journal_entry_id=entry.id,
                    line_number=line_number,
                    account_code=account_code,
                    direction=direction,
                    amount_minor=amount_minor,
                )
            )
    return entry


def _manual_billing_is_activated(session: Session, organization_id: UUID) -> bool:
    return (
        session.scalar(
            select(BillingManualActivation.id).where(
                BillingManualActivation.organization_id == organization_id
            )
        )
        is not None
    )


def _invoice_number(
    session: Session,
    organization_id: UUID,
    issue_date: date,
    invoice_id: UUID,
) -> str:
    namespace = (
        "MANUAL-INV" if _manual_billing_is_activated(session, organization_id) else "TEST-INV"
    )
    return f"{namespace}-{issue_date:%Y%m}-{invoice_id.hex[:10].upper()}"


def _require_synthetic_sources(
    session: Session,
    organization_id: UUID,
    *sources: tuple[str, UUID],
) -> None:
    """Require either the reviewed manual boundary or disposable synthetic attestations."""

    if _manual_billing_is_activated(session, organization_id):
        return

    required = (("organization", organization_id), *sources)
    for source_type, source_id in required:
        exists = session.scalar(
            select(BillingSandboxSourceAttestation.id).where(
                BillingSandboxSourceAttestation.organization_id == organization_id,
                BillingSandboxSourceAttestation.source_type == source_type,
                BillingSandboxSourceAttestation.source_id == source_id,
                BillingSandboxSourceAttestation.marker == "TEST_SYNTHETIC_ONLY",
                BillingSandboxSourceAttestation.reason_code == "disposable_test_fixture",
            )
        )
        if exists is None:
            raise HTTPException(
                409,
                detail={
                    "code": "billing_synthetic_source_attestation_required",
                    "source_type": source_type,
                    "source_id": str(source_id),
                },
            )


def _require_active_facility_program_scope(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID | None,
    program_id: UUID | None,
    expected_program_type: str | None,
    mismatch_code: str,
    inactive_program_code: str = "billing_program_inactive",
) -> Program:
    if facility_id is None or program_id is None:
        raise HTTPException(422, detail={"code": mismatch_code})
    facility = session.scalar(
        select(Facility)
        .where(
            Facility.organization_id == organization_id,
            Facility.id == facility_id,
        )
        .with_for_update()
    )
    if facility is None:
        raise HTTPException(422, detail={"code": mismatch_code})
    if facility.status != "active":
        raise HTTPException(422, detail={"code": "billing_facility_inactive"})
    program = session.scalar(
        select(Program)
        .where(
            Program.organization_id == organization_id,
            Program.facility_id == facility.id,
            Program.id == program_id,
        )
        .with_for_update()
    )
    if program is None or (
        expected_program_type is not None
        and program.program_type != expected_program_type
    ):
        raise HTTPException(422, detail={"code": mismatch_code})
    if not program.is_active:
        raise HTTPException(422, detail={"code": inactive_program_code})
    return program


def open_account(
    session: Session, context: BasicContext, payload: OpenBillingAccountCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="account_open",
        target_scope=payload.family_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    family = session.scalar(
        select(Family)
        .where(
            Family.organization_id == context.organization.id,
            Family.id == payload.family_id,
            Family.status != "archived",
        )
        .with_for_update()
    )
    payer = session.scalar(
        select(Guardian)
        .where(
            Guardian.organization_id == context.organization.id,
            Guardian.family_id == payload.family_id,
            Guardian.id == payload.payer_guardian_id,
            Guardian.retired_at.is_(None),
        )
        .with_for_update()
    )
    if family is None or payer is None:
        raise HTTPException(404, detail={"code": "billing_family_or_payer_not_found"})
    _require_synthetic_sources(
        session,
        context.organization.id,
        ("family", family.id),
        ("guardian", payer.id),
    )
    if session.scalar(
        select(BillingAccount.id).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.family_id == family.id,
        )
    ):
        raise HTTPException(409, detail={"code": "billing_account_already_exists"})
    account_id = uuid4()
    account = BillingAccount(
        id=account_id,
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        family_id=family.id,
        payer_guardian_id=payer.id,
        account_number=f"BA-{account_id.hex[:12].upper()}",
        currency="CAD",
        status="open",
        opened_by_user_id=context.user.id,
        opened_at=datetime.now(UTC),
    )
    session.add(account)
    session.add(
        BillingAccountPayerVersion(
            id=uuid4(),
            organization_id=context.organization.id,
            client_operation_id=payload.client_operation_id,
            request_hash=digest,
            billing_account_id=account.id,
            family_id=family.id,
            payer_guardian_id=payer.id,
            version_number=1,
            assigned_by_user_id=context.user.id,
            assigned_at=account.opened_at,
        )
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="account_open",
        request_hash=digest,
        result_kind="billing_account",
        result_id=account.id,
        action_path=f"/billing?focus=billing_account&record={account.id}",
        audit_action="billing.account.opened",
        realtime_type="billing.account.changed",
    )


def current_account_payer_version(
    session: Session, organization_id: UUID, account_id: UUID, *, lock: bool = False
) -> BillingAccountPayerVersion | None:
    if lock:
        _lock_billing_scope(session, organization_id, "account", account_id)
    statement = (
        select(BillingAccountPayerVersion)
        .where(
            BillingAccountPayerVersion.organization_id == organization_id,
            BillingAccountPayerVersion.billing_account_id == account_id,
        )
        .order_by(BillingAccountPayerVersion.version_number.desc())
        .limit(1)
    )
    return session.scalar(statement)


def assign_account_payer(
    session: Session,
    context: BasicContext,
    account_id: UUID,
    payload: AssignBillingAccountPayerCommand,
) -> BillingCommandResult:
    if payload.account_id != account_id:
        raise HTTPException(422, detail={"code": "billing_account_target_mismatch"})
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="account_payer_assign",
        target_scope=account_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    _lock_billing_scope(session, context.organization.id, "account", account_id)
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == account_id,
            BillingAccount.status == "open",
        )
    )
    if account is None:
        raise HTTPException(404, detail={"code": "billing_account_not_found"})
    payer = session.scalar(
        select(Guardian)
        .where(
            Guardian.organization_id == context.organization.id,
            Guardian.family_id == account.family_id,
            Guardian.id == payload.payer_guardian_id,
            Guardian.retired_at.is_(None),
        )
        .with_for_update()
    )
    if payer is None:
        raise HTTPException(404, detail={"code": "billing_payer_guardian_not_found"})
    _require_synthetic_sources(
        session,
        context.organization.id,
        ("family", account.family_id),
        ("guardian", payer.id),
    )
    latest = current_account_payer_version(session, context.organization.id, account.id, lock=True)
    if latest is None:
        raise HTTPException(409, detail={"code": "billing_account_payer_history_missing"})
    if (
        latest.id != payload.expected_latest_payer_version_id
        or latest.version_number != payload.expected_latest_payer_version_number
    ):
        raise HTTPException(
            409,
            detail={
                "code": "billing_account_payer_version_stale",
                "current_version_id": str(latest.id),
                "current_version_number": latest.version_number,
            },
        )
    if latest.payer_guardian_id == payer.id:
        raise HTTPException(409, detail={"code": "billing_account_payer_unchanged"})
    session.add(
        BillingAccountPayerVersion(
            id=uuid4(),
            organization_id=context.organization.id,
            client_operation_id=payload.client_operation_id,
            request_hash=digest,
            billing_account_id=account.id,
            family_id=account.family_id,
            payer_guardian_id=payer.id,
            version_number=latest.version_number + 1,
            assigned_by_user_id=context.user.id,
            assigned_at=datetime.now(UTC),
        )
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="account_payer_assign",
        request_hash=digest,
        result_kind="billing_account",
        result_id=account.id,
        action_path=f"/billing?focus=billing_account&record={account.id}",
        audit_action="billing.account.payer_assigned",
        realtime_type="billing.account.changed",
    )


def publish_rate_version(
    session: Session, context: BasicContext, payload: PublishRatePlanVersionCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="rate_version_publish",
        target_scope=payload.rate_plan_id or "new",
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    if payload.rate_plan_id is None:
        program = _require_active_facility_program_scope(
            session,
            organization_id=context.organization.id,
            facility_id=payload.facility_id,
            program_id=payload.program_id,
            expected_program_type=payload.program_type,
            mismatch_code="billing_rate_program_scope_mismatch",
        )
        _require_synthetic_sources(
            session,
            context.organization.id,
            ("facility", program.facility_id),
            ("program", program.id),
        )
        plan = BillingRatePlan(
            id=uuid4(),
            organization_id=context.organization.id,
            client_operation_id=payload.client_operation_id,
            request_hash=digest,
            code=payload.code,
            name=payload.name,
            program_type=payload.program_type,
            charge_kind="core_care",
            age_group=payload.age_group,
            facility_id=payload.facility_id,
            program_id=payload.program_id,
            created_by_user_id=context.user.id,
            created_at=datetime.now(UTC),
        )
        session.add(plan)
        version_number = 1
    else:
        _lock_billing_scope(session, context.organization.id, "rate_plan", payload.rate_plan_id)
        plan = session.scalar(
            select(BillingRatePlan).where(
                BillingRatePlan.organization_id == context.organization.id,
                BillingRatePlan.id == payload.rate_plan_id,
            )
        )
        if plan is None:
            raise HTTPException(404, detail={"code": "billing_rate_plan_not_found"})
        program = _require_active_facility_program_scope(
            session,
            organization_id=context.organization.id,
            facility_id=plan.facility_id,
            program_id=plan.program_id,
            expected_program_type=plan.program_type,
            mismatch_code="billing_rate_program_scope_mismatch",
        )
        _require_synthetic_sources(
            session,
            context.organization.id,
            ("facility", program.facility_id),
            ("program", program.id),
        )
        latest = session.scalar(
            select(BillingRatePlanVersion)
            .where(
                BillingRatePlanVersion.organization_id == context.organization.id,
                BillingRatePlanVersion.rate_plan_id == plan.id,
            )
            .order_by(BillingRatePlanVersion.version_number.desc())
            .limit(1)
        )
        if latest is None:
            raise HTTPException(409, detail={"code": "billing_rate_plan_has_no_version"})
        if (
            latest.id != payload.expected_latest_version_id
            or latest.version_number != payload.expected_latest_version_number
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "billing_rate_version_stale",
                    "current_version_id": str(latest.id),
                    "current_version_number": latest.version_number,
                },
            )
        if payload.effective_from <= latest.effective_from:
            raise HTTPException(
                422, detail={"code": "billing_rate_version_effective_order_invalid"}
            )
        version_number = latest.version_number + 1
    version = BillingRatePlanVersion(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        rate_plan_id=plan.id,
        version_number=version_number,
        billing_unit=payload.billing_unit,
        unit_amount_minor=payload.unit_amount_minor,
        tax_rate_basis_points=0,
        currency="CAD",
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        description=payload.description,
        status="published",
        published_by_user_id=context.user.id,
        published_at=datetime.now(UTC),
    )
    session.add(version)
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="rate_version_publish",
        request_hash=digest,
        result_kind="billing_rate_plan",
        result_id=plan.id,
        action_path=f"/billing?focus=billing_rate_plan&record={plan.id}",
        audit_action="billing.rate_plan.published",
        realtime_type="billing.rate_plan.changed",
        details={"version_number": version_number},
    )


def _rate_version(
    session: Session, organization_id: UUID, rate_version_id: UUID
) -> tuple[BillingRatePlanVersion, BillingRatePlan]:
    row = session.execute(
        select(BillingRatePlanVersion, BillingRatePlan)
        .join(
            BillingRatePlan,
            (BillingRatePlan.organization_id == BillingRatePlanVersion.organization_id)
            & (BillingRatePlan.id == BillingRatePlanVersion.rate_plan_id),
        )
        .where(
            BillingRatePlanVersion.organization_id == organization_id,
            BillingRatePlanVersion.id == rate_version_id,
            BillingRatePlanVersion.status == "published",
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail={"code": "billing_rate_version_not_found"})
    return row[0], row[1]


def _ensure_new_agreement_scope_available(
    session: Session,
    *,
    organization_id: UUID,
    billing_account_id: UUID,
    child_id: UUID,
    enrollment_id: UUID | None,
) -> None:
    """Reject only the immutable scope that the new agreement would duplicate."""

    statement = select(BillingAgreement.id).where(
        BillingAgreement.organization_id == organization_id,
        BillingAgreement.billing_account_id == billing_account_id,
    )
    if enrollment_id is None:
        statement = statement.where(
            BillingAgreement.child_id == child_id,
            BillingAgreement.enrollment_id.is_(None),
        )
        conflict_code = "billing_legacy_agreement_already_exists_for_child"
    else:
        statement = statement.where(BillingAgreement.enrollment_id == enrollment_id)
        conflict_code = "billing_agreement_already_exists_for_enrollment"
    if session.scalar(statement.limit(1)) is not None:
        raise HTTPException(409, detail={"code": conflict_code})


def establish_agreement(
    session: Session, context: BasicContext, payload: EstablishBillingAgreementCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="agreement_establish",
        target_scope=payload.agreement_id or payload.account_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    _lock_billing_scope(session, context.organization.id, "account", payload.account_id)
    _lock_billing_scope(
        session, context.organization.id, "rate_version", payload.rate_plan_version_id
    )
    if payload.agreement_id is not None:
        _lock_billing_scope(session, context.organization.id, "agreement", payload.agreement_id)
    rate_version, rate_plan = _rate_version(
        session, context.organization.id, payload.rate_plan_version_id
    )
    if payload.funding_amount_minor_per_unit != 0:
        raise HTTPException(422, detail={"code": "billing_funding_rules_unavailable"})
    required_unit = {
        "weekly": "weekly_period",
        "biweekly": "biweekly_period",
        "monthly": "monthly_period",
        "per_service": "service_event",
    }[payload.billing_frequency]
    if rate_version.billing_unit != required_unit:
        raise HTTPException(422, detail={"code": "billing_rate_unit_frequency_mismatch"})
    if (
        payload.family_amount_minor_per_unit + payload.funding_amount_minor_per_unit
        != rate_version.unit_amount_minor
    ):
        raise HTTPException(422, detail={"code": "billing_agreement_rate_portions_do_not_balance"})
    if rate_version.effective_from > payload.effective_from or (
        rate_version.effective_until is not None
        and (
            payload.effective_until is None
            or rate_version.effective_until < payload.effective_until
        )
    ):
        raise HTTPException(422, detail={"code": "billing_rate_not_effective_for_agreement"})
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == payload.account_id,
            BillingAccount.status == "open",
        )
    )
    child = session.scalar(
        select(Child)
        .where(
            Child.organization_id == context.organization.id,
            Child.id == payload.child_id,
            Child.is_active.is_(True),
        )
        .with_for_update()
    )
    if account is None or child is None or child.family_id != account.family_id:
        raise HTTPException(404, detail={"code": "billing_agreement_account_or_child_not_found"})
    enrollment = None
    enrollment_program = None
    if rate_plan.program_type in {"daycare", "out_of_school_care"} and (
        payload.enrollment_id is None
    ):
        raise HTTPException(422, detail={"code": "billing_current_enrollment_required"})
    if payload.enrollment_id is not None:
        enrollment = session.scalar(
            select(Enrollment)
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.id == payload.enrollment_id,
                Enrollment.child_id == child.id,
            )
            .with_for_update()
        )
        if enrollment is None:
            raise HTTPException(404, detail={"code": "billing_enrollment_not_found"})
        if (
            enrollment.status != "active"
            or enrollment.program_id is None
            or enrollment.start_date > payload.effective_from
            or (payload.effective_until is None and enrollment.end_date is not None)
            or (
                payload.effective_until is not None
                and enrollment.end_date is not None
                and enrollment.end_date < payload.effective_until
            )
        ):
            raise HTTPException(
                422, detail={"code": "billing_enrollment_not_current_for_agreement"}
            )
        enrollment_program = _require_active_facility_program_scope(
            session,
            organization_id=context.organization.id,
            facility_id=enrollment.facility_id,
            program_id=enrollment.program_id,
            expected_program_type=None,
            mismatch_code="billing_enrollment_program_inactive",
            inactive_program_code="billing_enrollment_program_inactive",
        )
        if rate_plan.program_type != enrollment_program.program_type:
            raise HTTPException(422, detail={"code": "billing_rate_program_type_mismatch"})
        if rate_plan.facility_id is not None and (
            rate_plan.facility_id != enrollment.facility_id
            or rate_plan.program_id != enrollment.program_id
        ):
            raise HTTPException(422, detail={"code": "billing_rate_enrollment_scope_mismatch"})
    elif rate_plan.facility_id is not None or rate_plan.program_id is not None:
        raise HTTPException(422, detail={"code": "billing_rate_enrollment_scope_mismatch"})
    if enrollment is not None and enrollment_program is not None:
        _require_synthetic_sources(
            session,
            context.organization.id,
            ("family", account.family_id),
            ("child", child.id),
            ("enrollment", enrollment.id),
            ("facility", enrollment.facility_id),
            ("program", enrollment_program.id),
        )
    if rate_plan.age_group and (
        child.age_group is None or rate_plan.age_group.casefold() != child.age_group.casefold()
    ):
        raise HTTPException(422, detail={"code": "billing_rate_age_group_mismatch"})
    if payload.agreement_id is None:
        _ensure_new_agreement_scope_available(
            session,
            organization_id=context.organization.id,
            billing_account_id=account.id,
            child_id=child.id,
            enrollment_id=enrollment.id if enrollment else None,
        )
        agreement = BillingAgreement(
            id=uuid4(),
            organization_id=context.organization.id,
            client_operation_id=payload.client_operation_id,
            request_hash=digest,
            billing_account_id=account.id,
            family_id=account.family_id,
            child_id=child.id,
            enrollment_id=enrollment.id if enrollment else None,
            facility_id=enrollment.facility_id if enrollment else None,
            created_by_user_id=context.user.id,
            created_at=datetime.now(UTC),
        )
        session.add(agreement)
        version_number = 1
    else:
        agreement = session.scalar(
            select(BillingAgreement).where(
                BillingAgreement.organization_id == context.organization.id,
                BillingAgreement.id == payload.agreement_id,
            )
        )
        if agreement is None:
            raise HTTPException(404, detail={"code": "billing_agreement_not_found"})
        if (
            agreement.billing_account_id != payload.account_id
            or agreement.child_id != payload.child_id
            or agreement.enrollment_id != payload.enrollment_id
            or agreement.facility_id != (enrollment.facility_id if enrollment else None)
        ):
            raise HTTPException(422, detail={"code": "billing_agreement_immutable_scope_mismatch"})
        latest = session.scalar(
            select(BillingAgreementVersion)
            .where(
                BillingAgreementVersion.organization_id == context.organization.id,
                BillingAgreementVersion.agreement_id == agreement.id,
            )
            .order_by(BillingAgreementVersion.version_number.desc())
            .limit(1)
        )
        if latest is None:
            raise HTTPException(409, detail={"code": "billing_agreement_has_no_version"})
        if (
            latest.id != payload.expected_latest_version_id
            or latest.version_number != payload.expected_latest_version_number
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "billing_agreement_version_stale",
                    "current_version_id": str(latest.id),
                    "current_version_number": latest.version_number,
                },
            )
        if payload.effective_from <= latest.effective_from:
            raise HTTPException(
                422, detail={"code": "billing_agreement_version_effective_order_invalid"}
            )
        version_number = latest.version_number + 1
    version = BillingAgreementVersion(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        agreement_id=agreement.id,
        rate_plan_version_id=rate_version.id,
        version_number=version_number,
        billing_frequency=payload.billing_frequency,
        family_amount_minor_per_unit=payload.family_amount_minor_per_unit,
        funding_amount_minor_per_unit=payload.funding_amount_minor_per_unit,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        review_status="reviewed",
        reviewed_by_user_id=context.user.id,
        reviewed_at=datetime.now(UTC),
    )
    session.add(version)
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="agreement_establish",
        request_hash=digest,
        result_kind="billing_agreement",
        result_id=agreement.id,
        action_path=f"/billing?focus=billing_agreement&record={agreement.id}",
        audit_action="billing.agreement.reviewed",
        realtime_type="billing.agreement.changed",
        details={"version_number": version_number},
    )


def _period_matches_frequency(start: date, end: date, frequency: str) -> bool:
    inclusive_days = (end - start).days + 1
    if frequency == "weekly":
        return inclusive_days == 7
    if frequency == "biweekly":
        return inclusive_days == 14
    if frequency == "per_service":
        return inclusive_days == 1
    if frequency == "monthly":
        return (
            start.day == 1
            and start.year == end.year
            and start.month == end.month
            and end.day == calendar.monthrange(start.year, start.month)[1]
        )
    return False


def _tax_minor(subtotal_minor: int, basis_points: int) -> int:
    return (subtotal_minor * basis_points + 5_000) // 10_000


def issue_invoice(
    session: Session, context: BasicContext, payload: IssueBillingInvoiceCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="invoice_issue",
        target_scope=payload.account_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    try:
        organization_today = datetime.now(ZoneInfo(context.organization.timezone)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(409, detail={"code": "organization_timezone_invalid"}) from None
    if payload.issue_date != organization_today:
        raise HTTPException(
            422,
            detail={
                "code": "billing_invoice_issue_date_must_be_today",
                "organization_local_date": organization_today.isoformat(),
            },
        )
    _lock_billing_scope(session, context.organization.id, "account", payload.account_id)
    for agreement_id in sorted(
        (selection.agreement_id for selection in payload.agreements), key=str
    ):
        _lock_billing_scope(session, context.organization.id, "agreement", agreement_id)
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == payload.account_id,
            BillingAccount.status == "open",
        )
    )
    if account is None:
        raise HTTPException(404, detail={"code": "billing_account_not_found"})
    family = session.scalar(
        select(Family)
        .where(
            Family.organization_id == context.organization.id,
            Family.id == account.family_id,
        )
        .with_for_update()
    )
    payer_version = current_account_payer_version(
        session, context.organization.id, account.id, lock=True
    )
    payer = session.scalar(
        select(Guardian)
        .where(
            Guardian.organization_id == context.organization.id,
            Guardian.family_id == account.family_id,
            Guardian.id == (payer_version.payer_guardian_id if payer_version is not None else None),
            Guardian.retired_at.is_(None),
        )
        .with_for_update()
    )
    if family is None or payer_version is None or payer is None:
        raise HTTPException(409, detail={"code": "billing_account_payer_needs_review"})
    agreements = list(
        session.scalars(
            select(BillingAgreement).where(
                BillingAgreement.organization_id == context.organization.id,
                BillingAgreement.id.in_(
                    [selection.agreement_id for selection in payload.agreements]
                ),
                BillingAgreement.billing_account_id == account.id,
            )
        )
    )
    by_id = {agreement.id: agreement for agreement in agreements}
    selected_agreement_ids = {selection.agreement_id for selection in payload.agreements}
    if set(by_id) != selected_agreement_ids:
        raise HTTPException(404, detail={"code": "billing_agreement_not_found"})
    line_values: list[dict[str, Any]] = []
    frequencies: set[str] = set()
    for selection in payload.agreements:
        agreement = by_id[selection.agreement_id]
        version = session.scalar(
            select(BillingAgreementVersion).where(
                BillingAgreementVersion.organization_id == context.organization.id,
                BillingAgreementVersion.agreement_id == agreement.id,
                BillingAgreementVersion.id == selection.agreement_version_id,
            )
        )
        if version is None or version.review_status != "reviewed":
            raise HTTPException(409, detail={"code": "billing_agreement_not_reviewed"})
        _lock_billing_scope(
            session, context.organization.id, "rate_version", version.rate_plan_version_id
        )
        applicable_version_id = session.scalar(
            select(BillingAgreementVersion.id)
            .where(
                BillingAgreementVersion.organization_id == context.organization.id,
                BillingAgreementVersion.agreement_id == agreement.id,
                BillingAgreementVersion.review_status == "reviewed",
                BillingAgreementVersion.effective_from <= payload.service_period_start,
                (
                    BillingAgreementVersion.effective_until.is_(None)
                    | (BillingAgreementVersion.effective_until >= payload.service_period_end)
                ),
            )
            .order_by(
                BillingAgreementVersion.effective_from.desc(),
                BillingAgreementVersion.version_number.desc(),
            )
            .limit(1)
        )
        if applicable_version_id != version.id:
            raise HTTPException(
                409,
                detail={
                    "code": "billing_agreement_version_stale",
                    "agreement_id": str(agreement.id),
                },
            )
        if version.effective_from > payload.service_period_start or (
            version.effective_until is not None
            and version.effective_until < payload.service_period_end
        ):
            raise HTTPException(422, detail={"code": "billing_agreement_not_effective_for_period"})
        frequencies.add(version.billing_frequency)
        if not _period_matches_frequency(
            payload.service_period_start,
            payload.service_period_end,
            version.billing_frequency,
        ):
            raise HTTPException(
                422,
                detail={
                    "code": "billing_service_period_frequency_mismatch",
                    "agreement_id": str(agreement.id),
                    "billing_frequency": version.billing_frequency,
                },
            )
        rate_version, rate_plan = _rate_version(
            session, context.organization.id, version.rate_plan_version_id
        )
        applicable_latest = session.scalar(
            select(BillingRatePlanVersion)
            .where(
                BillingRatePlanVersion.organization_id == context.organization.id,
                BillingRatePlanVersion.rate_plan_id == rate_plan.id,
                BillingRatePlanVersion.status == "published",
                BillingRatePlanVersion.effective_from <= payload.service_period_start,
                (
                    BillingRatePlanVersion.effective_until.is_(None)
                    | (BillingRatePlanVersion.effective_until >= payload.service_period_end)
                ),
            )
            .order_by(
                BillingRatePlanVersion.effective_from.desc(),
                BillingRatePlanVersion.version_number.desc(),
            )
            .limit(1)
        )
        if applicable_latest is None or applicable_latest.id != rate_version.id:
            raise HTTPException(409, detail={"code": "billing_agreement_rate_drift"})
        if (
            version.family_amount_minor_per_unit + version.funding_amount_minor_per_unit
            != rate_version.unit_amount_minor
        ):
            raise HTTPException(409, detail={"code": "billing_agreement_portion_drift"})
        overlap = session.scalar(
            select(BillingInvoiceLine.id)
            .join(
                BillingAgreementVersion,
                (BillingAgreementVersion.organization_id == BillingInvoiceLine.organization_id)
                & (BillingAgreementVersion.id == BillingInvoiceLine.agreement_version_id),
            )
            .where(
                BillingInvoiceLine.organization_id == context.organization.id,
                BillingAgreementVersion.agreement_id == agreement.id,
                BillingInvoiceLine.service_period_start <= payload.service_period_end,
                BillingInvoiceLine.service_period_end >= payload.service_period_start,
            )
            .limit(1)
        )
        if overlap is not None:
            raise HTTPException(
                409,
                detail={
                    "code": "billing_agreement_period_already_invoiced",
                    "agreement_id": str(agreement.id),
                },
            )
        child = session.scalar(
            select(Child)
            .where(
                Child.organization_id == context.organization.id,
                Child.id == agreement.child_id,
            )
            .with_for_update()
        )
        if child is None:
            raise HTTPException(409, detail={"code": "billing_agreement_child_missing"})
        enrollment = session.scalar(
            select(Enrollment)
            .where(
                Enrollment.organization_id == context.organization.id,
                Enrollment.id == agreement.enrollment_id,
                Enrollment.child_id == agreement.child_id,
                Enrollment.facility_id == agreement.facility_id,
            )
            .with_for_update()
        )
        if (
            enrollment is None
            or enrollment.status not in {"active", "ended"}
            or enrollment.program_id is None
            or enrollment.start_date > payload.service_period_start
            or (
                enrollment.end_date is not None and enrollment.end_date < payload.service_period_end
            )
            or (enrollment.status == "ended" and enrollment.end_date is None)
        ):
            raise HTTPException(409, detail={"code": "billing_enrollment_not_billable_for_period"})
        program = session.scalar(
            select(Program)
            .where(
                Program.organization_id == context.organization.id,
                Program.facility_id == enrollment.facility_id,
                Program.id == enrollment.program_id,
            )
            .with_for_update()
        )
        if (
            program is None
            or program.id != rate_plan.program_id
            or program.facility_id != rate_plan.facility_id
            or program.program_type != rate_plan.program_type
        ):
            raise HTTPException(409, detail={"code": "billing_enrollment_program_scope_drift"})
        _require_synthetic_sources(
            session,
            context.organization.id,
            ("family", account.family_id),
            ("guardian", payer.id),
            ("child", child.id),
            ("enrollment", enrollment.id),
            ("facility", enrollment.facility_id),
            ("program", program.id),
        )
        family_amount = version.family_amount_minor_per_unit
        funding_amount = version.funding_amount_minor_per_unit
        tax_amount = _tax_minor(family_amount, rate_version.tax_rate_basis_points)
        line_values.append(
            {
                "agreement_version": version,
                "child": child,
                "rate_plan": rate_plan,
                "rate_version": rate_version,
                "gross": rate_version.unit_amount_minor,
                "funding": funding_amount,
                "family": family_amount,
                "tax": tax_amount,
            }
        )
    if len(frequencies) != 1:
        raise HTTPException(422, detail={"code": "billing_mixed_agreement_frequencies"})
    gross_subtotal = sum(item["gross"] for item in line_values)
    funding_total = sum(item["funding"] for item in line_values)
    subtotal = sum(item["family"] for item in line_values)
    tax_total = sum(item["tax"] for item in line_values)
    total = subtotal + tax_total
    if any(
        amount > MAX_CAD_MINOR
        for amount in (gross_subtotal, funding_total, subtotal, tax_total, total)
    ):
        raise HTTPException(422, detail={"code": "billing_money_limit_exceeded"})
    if total <= 0:
        raise HTTPException(422, detail={"code": "billing_invoice_has_no_family_charge"})
    invoice_id = uuid4()
    address_parts = [payer.address, payer.city, payer.postal_code]
    invoice = BillingInvoice(
        id=invoice_id,
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        billing_account_id=account.id,
        family_id=account.family_id,
        billing_account_payer_version_id=payer_version.id,
        payer_guardian_id=payer.id,
        invoice_number=_invoice_number(
            session,
            context.organization.id,
            payload.issue_date,
            invoice_id,
        ),
        status="issued",
        currency="CAD",
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        service_period_start=payload.service_period_start,
        service_period_end=payload.service_period_end,
        family_name_snapshot=family.name,
        payer_name_snapshot=f"{payer.first_name} {payer.last_name}".strip(),
        payer_email_snapshot=payer.email or None,
        payer_address_snapshot=", ".join(part for part in address_parts if part) or None,
        gross_subtotal_minor=gross_subtotal,
        funding_minor=funding_total,
        subtotal_minor=subtotal,
        tax_minor=tax_total,
        total_minor=total,
        issued_by_user_id=context.user.id,
        issued_at=datetime.now(UTC),
    )
    session.add(invoice)
    for index, item in enumerate(line_values, start=1):
        child = item["child"]
        rate_plan = item["rate_plan"]
        rate_version = item["rate_version"]
        session.add(
            BillingInvoiceLine(
                id=uuid4(),
                organization_id=context.organization.id,
                client_operation_id=payload.client_operation_id,
                request_hash=digest,
                invoice_id=invoice.id,
                agreement_version_id=item["agreement_version"].id,
                child_id=child.id,
                line_number=index,
                description_snapshot=(
                    f"{rate_plan.name} — contracted {next(iter(frequencies))} period"
                ),
                child_name_snapshot=f"{child.first_name} {child.last_name}".strip(),
                rate_plan_name_snapshot=rate_plan.name,
                billing_unit_snapshot=rate_version.billing_unit,
                service_period_start=payload.service_period_start,
                service_period_end=payload.service_period_end,
                quantity=1,
                gross_unit_amount_minor=item["gross"],
                funding_unit_amount_minor=item["funding"],
                unit_amount_minor=item["family"],
                tax_rate_basis_points=rate_version.tax_rate_basis_points,
                gross_subtotal_minor=item["gross"],
                funding_minor=item["funding"],
                subtotal_minor=item["family"],
                tax_minor=item["tax"],
                total_minor=item["family"] + item["tax"],
            )
        )
    _journal(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        entry_kind="invoice_issued",
        source_type="billing_invoice",
        source_id=invoice.id,
        debits=[
            ("accounts_receivable", total),
            ("funding_receivable", funding_total),
        ],
        credits=[("childcare_revenue", gross_subtotal), ("sales_tax_payable", tax_total)],
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="invoice_issue",
        request_hash=digest,
        result_kind="billing_invoice",
        result_id=invoice.id,
        action_path=f"/billing?focus=billing_invoice&record={invoice.id}",
        audit_action="billing.invoice.issued",
        realtime_type="billing.invoice.changed",
        details={"total_minor": total, "currency": "CAD"},
    )


def record_payment(
    session: Session, context: BasicContext, payload: RecordBillingPaymentCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="payment_record",
        target_scope=payload.account_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    if payload.received_at.astimezone(UTC) > datetime.now(UTC):
        raise HTTPException(422, detail={"code": "billing_payment_received_at_in_future"})
    _lock_billing_scope(session, context.organization.id, "account", payload.account_id)
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == payload.account_id,
            BillingAccount.status == "open",
        )
    )
    if account is None:
        raise HTTPException(404, detail={"code": "billing_account_not_found"})
    payer = session.scalar(
        select(Guardian)
        .where(
            Guardian.organization_id == context.organization.id,
            Guardian.family_id == account.family_id,
            Guardian.id == payload.payer_guardian_id,
            Guardian.retired_at.is_(None),
        )
        .with_for_update()
    )
    if payer is None:
        raise HTTPException(404, detail={"code": "billing_payment_payer_not_found"})
    _require_synthetic_sources(
        session,
        context.organization.id,
        ("family", account.family_id),
        ("guardian", payer.id),
    )
    reference = payload.external_reference.strip().upper()
    duplicate_reference = session.scalar(
        select(BillingPayment.id).where(
            BillingPayment.organization_id == context.organization.id,
            BillingPayment.external_reference == reference,
        )
    )
    if duplicate_reference is not None:
        raise HTTPException(
            409,
            detail={
                "code": "billing_payment_reference_reused",
                "payment_id": str(duplicate_reference),
            },
        )
    payment = BillingPayment(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        billing_account_id=account.id,
        family_id=account.family_id,
        payer_guardian_id=payer.id,
        status="settled",
        method=payload.method,
        currency="CAD",
        amount_minor=payload.amount_minor,
        external_reference=reference,
        payer_name_snapshot=f"{payer.first_name} {payer.last_name}".strip(),
        payer_email_snapshot=payer.email or None,
        operator_confirmation_note=payload.operator_confirmation_note,
        memo=payload.memo,
        received_at=payload.received_at.astimezone(UTC),
        recorded_by_user_id=context.user.id,
        recorded_at=datetime.now(UTC),
    )
    session.add(payment)
    clearing_code = {
        "cash": "cash_on_hand",
        "cheque": "cheque_clearing",
        "e_transfer": "e_transfer_clearing",
        "other": "other_payment_clearing",
    }[payload.method]
    _journal(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        entry_kind="payment_settled",
        source_type="billing_payment",
        source_id=payment.id,
        debits=[(clearing_code, payment.amount_minor)],
        credits=[("unapplied_cash", payment.amount_minor)],
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="payment_record",
        request_hash=digest,
        result_kind="billing_payment",
        result_id=payment.id,
        action_path=f"/billing?focus=billing_payment&record={payment.id}",
        audit_action="billing.payment.recorded",
        realtime_type="billing.payment.changed",
        details={"amount_minor": payment.amount_minor, "currency": "CAD"},
    )


def _sum_allocations(
    session: Session,
    organization_id: UUID,
    *,
    payment_id: UUID | None = None,
    invoice_id: UUID | None = None,
) -> int:
    statement = select(func.coalesce(func.sum(BillingAllocation.amount_minor), 0)).where(
        BillingAllocation.organization_id == organization_id
    )
    if payment_id is not None:
        statement = statement.where(BillingAllocation.payment_id == payment_id)
    if invoice_id is not None:
        statement = statement.where(BillingAllocation.invoice_id == invoice_id)
    return int(session.scalar(statement) or 0)


def _sum_credits(session: Session, organization_id: UUID, invoice_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(BillingCredit.amount_minor), 0)).where(
                BillingCredit.organization_id == organization_id,
                BillingCredit.invoice_id == invoice_id,
            )
        )
        or 0
    )


def allocate_payment(
    session: Session, context: BasicContext, payload: AllocateBillingPaymentCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="payment_allocate",
        target_scope=payload.payment_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    payment_account_id = session.scalar(
        select(BillingPayment.billing_account_id).where(
            BillingPayment.organization_id == context.organization.id,
            BillingPayment.id == payload.payment_id,
        )
    )
    invoice_account_id = session.scalar(
        select(BillingInvoice.billing_account_id).where(
            BillingInvoice.organization_id == context.organization.id,
            BillingInvoice.id == payload.invoice_id,
        )
    )
    if payment_account_id is None or invoice_account_id is None:
        raise HTTPException(404, detail={"code": "billing_payment_or_invoice_not_found"})
    if payment_account_id != invoice_account_id:
        raise HTTPException(422, detail={"code": "billing_allocation_account_mismatch"})
    _lock_billing_scope(session, context.organization.id, "account", payment_account_id)
    _lock_billing_scope(session, context.organization.id, "payment", payload.payment_id)
    _lock_billing_scope(session, context.organization.id, "invoice", payload.invoice_id)
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == payment_account_id,
        )
    )
    if account is None:
        raise HTTPException(409, detail={"code": "billing_account_missing"})
    payment = session.scalar(
        select(BillingPayment).where(
            BillingPayment.organization_id == context.organization.id,
            BillingPayment.id == payload.payment_id,
            BillingPayment.billing_account_id == account.id,
        )
    )
    invoice = session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.organization_id == context.organization.id,
            BillingInvoice.id == payload.invoice_id,
            BillingInvoice.billing_account_id == account.id,
        )
    )
    if payment is None or invoice is None:
        raise HTTPException(409, detail={"code": "billing_allocation_source_drift"})
    payment_allocated = _sum_allocations(session, context.organization.id, payment_id=payment.id)
    invoice_allocated = _sum_allocations(session, context.organization.id, invoice_id=invoice.id)
    invoice_credited = _sum_credits(session, context.organization.id, invoice.id)
    current_payment_unapplied = payment.amount_minor - payment_allocated
    current_invoice_outstanding = invoice.total_minor - invoice_allocated - invoice_credited
    if (
        payload.expected_payment_unapplied_minor != current_payment_unapplied
        or payload.expected_invoice_outstanding_minor != current_invoice_outstanding
    ):
        raise HTTPException(
            409,
            detail={
                "code": "billing_allocation_projection_stale",
                "current_payment_unapplied_minor": current_payment_unapplied,
                "current_invoice_outstanding_minor": current_invoice_outstanding,
            },
        )
    if payment_allocated + payload.amount_minor > payment.amount_minor:
        raise HTTPException(422, detail={"code": "billing_payment_overallocated"})
    if invoice_allocated + invoice_credited + payload.amount_minor > invoice.total_minor:
        raise HTTPException(422, detail={"code": "billing_invoice_overallocated"})
    allocation = BillingAllocation(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        billing_account_id=payment.billing_account_id,
        payment_id=payment.id,
        invoice_id=invoice.id,
        amount_minor=payload.amount_minor,
        allocated_by_user_id=context.user.id,
        allocated_at=datetime.now(UTC),
    )
    session.add(allocation)
    _journal(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        entry_kind="payment_allocated",
        source_type="billing_allocation",
        source_id=allocation.id,
        debits=[("unapplied_cash", allocation.amount_minor)],
        credits=[("accounts_receivable", allocation.amount_minor)],
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="payment_allocate",
        request_hash=digest,
        result_kind="billing_allocation",
        result_id=allocation.id,
        action_path=f"/billing?focus=billing_allocation&record={allocation.id}",
        audit_action="billing.payment.allocated",
        realtime_type="billing.allocation.changed",
        details={"amount_minor": allocation.amount_minor, "currency": "CAD"},
    )


def issue_credit(
    session: Session, context: BasicContext, payload: IssueBillingCreditCommand
) -> BillingCommandResult:
    digest, retry = _begin_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="credit_issue",
        target_scope=payload.invoice_id,
        intent=_intent(payload),
    )
    if retry is not None:
        return retry
    invoice_account_id = session.scalar(
        select(BillingInvoice.billing_account_id).where(
            BillingInvoice.organization_id == context.organization.id,
            BillingInvoice.id == payload.invoice_id,
        )
    )
    if invoice_account_id is None:
        raise HTTPException(404, detail={"code": "billing_invoice_not_found"})
    _lock_billing_scope(session, context.organization.id, "account", invoice_account_id)
    _lock_billing_scope(session, context.organization.id, "invoice", payload.invoice_id)
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.organization_id == context.organization.id,
            BillingAccount.id == invoice_account_id,
        )
    )
    if account is None:
        raise HTTPException(409, detail={"code": "billing_account_missing"})
    invoice = session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.organization_id == context.organization.id,
            BillingInvoice.id == payload.invoice_id,
            BillingInvoice.billing_account_id == account.id,
        )
    )
    if invoice is None:
        raise HTTPException(409, detail={"code": "billing_credit_source_drift"})
    allocated = _sum_allocations(session, context.organization.id, invoice_id=invoice.id)
    credited = _sum_credits(session, context.organization.id, invoice.id)
    current_outstanding = invoice.total_minor - allocated - credited
    if payload.expected_invoice_outstanding_minor != current_outstanding:
        raise HTTPException(
            409,
            detail={
                "code": "billing_credit_projection_stale",
                "current_invoice_outstanding_minor": current_outstanding,
            },
        )
    if allocated + credited + payload.amount_minor > invoice.total_minor:
        raise HTTPException(422, detail={"code": "billing_credit_exceeds_outstanding"})
    credit = BillingCredit(
        id=uuid4(),
        organization_id=context.organization.id,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        billing_account_id=invoice.billing_account_id,
        invoice_id=invoice.id,
        status="issued",
        currency="CAD",
        amount_minor=payload.amount_minor,
        reason_code=payload.reason_code,
        note=payload.note,
        issued_by_user_id=context.user.id,
        issued_at=datetime.now(UTC),
    )
    session.add(credit)
    _journal(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        request_hash=digest,
        entry_kind="credit_issued",
        source_type="billing_credit",
        source_id=credit.id,
        debits=[("billing_adjustments", credit.amount_minor)],
        credits=[("accounts_receivable", credit.amount_minor)],
    )
    return _finish_command(
        session,
        context=context,
        client_operation_id=payload.client_operation_id,
        command_type="credit_issue",
        request_hash=digest,
        result_kind="billing_credit",
        result_id=credit.id,
        action_path=f"/billing?focus=billing_credit&record={credit.id}",
        audit_action="billing.credit.issued",
        realtime_type="billing.credit.changed",
        details={"amount_minor": credit.amount_minor, "currency": "CAD"},
    )
