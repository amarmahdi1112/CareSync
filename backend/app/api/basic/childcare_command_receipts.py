"""Actor-private reconciliation for durable childcare commands."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.basic.common import lock_client_operation, restore_context
from app.api.basic.dependencies import CommandReconciliationContext
from app.api.dependencies import SessionDependency
from app.basic.childcare_commands import reserve_sqlite_operation_slot, safe_action_route
from app.basic.models import (
    ChildcareCommandClaim,
    ChildcareCommandReceipt,
    ChildcareCommandReconciliationProof,
)
from app.basic.schemas import ChildcareCommandReceiptResponse

router = APIRouter(tags=["basic childcare commands"])

ABSENCE_CLAIM_LIMIT_PER_HOUR = 120
ABSENCE_CLAIM_LIMIT_PER_DAY = 500


def _utc_timestamp(value: datetime) -> datetime:
    """Keep SQLite reconciliation receipts identical to strict command responses."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _terminal_absence_detail(
    *, actor_user_id: UUID, organization_id: UUID, client_operation_id: UUID
) -> dict[str, str]:
    return {
        "code": "operation_finalized_absent",
        "message": "No committed childcare command exists for this identity and operation.",
        "actor_user_id": str(actor_user_id),
        "client_operation_id": str(client_operation_id),
        "organization_id": str(organization_id),
    }


@router.get(
    "/childcare-commands/{client_operation_id}",
    response_model=ChildcareCommandReceiptResponse,
)
def get_childcare_command_receipt(
    client_operation_id: UUID,
    request: Request,
    context: CommandReconciliationContext,
    session: SessionDependency,
) -> ChildcareCommandReceiptResponse:
    """Return a receipt or durably finalize this actor's operation as absent."""

    lock_client_operation(session, context.organization.id, client_operation_id)
    if not request.app.state.settings.database_read_only:
        reserve_sqlite_operation_slot(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            client_operation_id=client_operation_id,
            entry_kind="absence_claim",
        )
    receipt = session.scalar(
        select(ChildcareCommandReceipt).where(
            ChildcareCommandReceipt.organization_id == context.organization.id,
            ChildcareCommandReceipt.client_operation_id == client_operation_id,
        )
    )
    if receipt is not None and receipt.actor_user_id == context.user.id:
        try:
            action_route = safe_action_route(receipt.outcome.get("action_route"))
        except (AttributeError, ValueError):
            raise HTTPException(
                status_code=409,
                detail={"code": "operation_receipt_invalid_action_route"},
            ) from None
        return ChildcareCommandReceiptResponse(
            organization_id=receipt.organization_id,
            client_operation_id=receipt.client_operation_id,
            command_type=receipt.command_type,
            target_type=receipt.target_type,
            target_id=receipt.target_id,
            committed_version=receipt.committed_version,
            committed_at=_utc_timestamp(receipt.committed_at),
            facility_id=receipt.facility_id,
            action_route=action_route,
        )

    claim = session.scalar(
        select(ChildcareCommandClaim).where(
            ChildcareCommandClaim.organization_id == context.organization.id,
            ChildcareCommandClaim.client_operation_id == client_operation_id,
        )
    )
    proof = session.scalar(
        select(ChildcareCommandReconciliationProof).where(
            ChildcareCommandReconciliationProof.organization_id == context.organization.id,
            ChildcareCommandReconciliationProof.actor_user_id == context.user.id,
            ChildcareCommandReconciliationProof.client_operation_id == client_operation_id,
        )
    )
    needs_claim = receipt is None and claim is None
    needs_proof = proof is None
    if needs_claim or needs_proof:
        if request.app.state.settings.database_read_only:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "operation_reconciliation_unavailable"},
            )
        if needs_proof:
            now = datetime.now(UTC)
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            hourly, daily = session.execute(
                select(
                    func.count().filter(
                        ChildcareCommandReconciliationProof.finalized_at >= hour_start
                    ),
                    func.count().filter(
                        ChildcareCommandReconciliationProof.finalized_at >= day_start
                    ),
                ).where(
                    ChildcareCommandReconciliationProof.organization_id == context.organization.id,
                    ChildcareCommandReconciliationProof.actor_user_id == context.user.id,
                )
            ).one()
            if (
                int(hourly or 0) >= ABSENCE_CLAIM_LIMIT_PER_HOUR
                or int(daily or 0) >= ABSENCE_CLAIM_LIMIT_PER_DAY
            ):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"code": "operation_reconciliation_rate_limited"},
                )
        # The terminal 404 is emitted only after actor proof and, for an
        # unknown operation, its global no-write authority are durable.
        try:
            if needs_claim:
                session.add(
                    ChildcareCommandClaim(
                        organization_id=context.organization.id,
                        client_operation_id=client_operation_id,
                        actor_user_id=context.user.id,
                    )
                )
                # Proofs are valid only after the global terminal slot exists.
                session.flush()
            if needs_proof:
                session.add(
                    ChildcareCommandReconciliationProof(
                        organization_id=context.organization.id,
                        client_operation_id=client_operation_id,
                        actor_user_id=context.user.id,
                    )
                )
            session.commit()
        except IntegrityError as error:
            session.rollback()
            diagnostic = getattr(getattr(error, "orig", None), "diag", None)
            if getattr(diagnostic, "constraint_name", None) in {
                "ck_childcare_reconciliation_hour_limit",
                "ck_childcare_reconciliation_day_limit",
            }:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"code": "operation_reconciliation_rate_limited"},
                ) from None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "operation_reconciliation_conflict"},
            ) from None
        restore_context(session, context)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_terminal_absence_detail(
            actor_user_id=context.user.id,
            organization_id=context.organization.id,
            client_operation_id=client_operation_id,
        ),
    )
