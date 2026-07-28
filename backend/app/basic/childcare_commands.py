"""Exact-retry and optimistic concurrency helpers for child-record commands."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.api.basic.common import lock_client_operation
from app.basic.models import (
    ChildcareCommandClaim,
    ChildcareCommandReceipt,
    ChildcareCommandSlot,
)


def reserve_sqlite_operation_slot(
    session: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    client_operation_id: UUID,
    entry_kind: str,
) -> ChildcareCommandSlot | None:
    """Serialize the first ledger kind on SQLite's single-writer lock."""

    if session.bind is None or session.bind.dialect.name != "sqlite":
        return None
    session.execute(
        sqlite_insert(ChildcareCommandSlot)
        .values(
            organization_id=organization_id,
            client_operation_id=client_operation_id,
            entry_kind=entry_kind,
            actor_user_id=actor_user_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ChildcareCommandSlot.organization_id,
                ChildcareCommandSlot.client_operation_id,
            ]
        )
    )
    return session.scalar(
        select(ChildcareCommandSlot).where(
            ChildcareCommandSlot.organization_id == organization_id,
            ChildcareCommandSlot.client_operation_id == client_operation_id,
        )
    )


def safe_action_route(value: object) -> str:
    """Return a local UI route and reject redirect or traversal payloads."""

    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        raise ValueError("action_route must be a local absolute-path reference")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise ValueError("action_route contains unsafe characters")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError("action_route must not contain an origin or fragment")
    if any(segment == ".." for segment in parsed.path.split("/")):
        raise ValueError("action_route must not traverse parent paths")
    return value


def _canonical(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise HTTPException(422, detail={"code": "timezone_required"})
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        # Bind the receipt to the exact submitted intent. Route code may choose
        # to normalize a field before persistence, but two byte-different
        # requests must never share one operation receipt accidentally.
        return value
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def command_hash(
    *,
    command_type: str,
    target_type: str,
    target_scope: UUID | str | None,
    intent: dict,
) -> str:
    """Hash a purpose-bound canonical command without retaining a second PII copy."""

    canonical = _canonical(
        {
            "command_type": command_type,
            "target_type": target_type,
            "target_scope": target_scope,
            "intent": intent,
        }
    )
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def begin_command(
    session: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    client_operation_id: UUID,
    command_type: str,
    target_type: str,
    target_scope: UUID | str | None,
    intent: dict,
    reserve_sqlite_slot: bool = True,
) -> tuple[str, ChildcareCommandReceipt | None]:
    """Serialize a first use and resolve an actor-private exact replay."""

    digest = command_hash(
        command_type=command_type,
        target_type=target_type,
        target_scope=target_scope,
        intent=intent,
    )
    lock_client_operation(session, organization_id, client_operation_id)
    slot = (
        reserve_sqlite_operation_slot(
            session,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            client_operation_id=client_operation_id,
            entry_kind="receipt",
        )
        if reserve_sqlite_slot
        else None
    )
    if slot is not None and slot.actor_user_id != actor_user_id:
        raise HTTPException(404, detail="Operation receipt not found")
    if slot is not None and slot.entry_kind == "absence_claim":
        raise HTTPException(
            409,
            detail={
                "code": "operation_finalized_absent",
                "message": (
                    "No committed childcare command exists for this identity and operation."
                ),
                "actor_user_id": str(actor_user_id),
                "client_operation_id": str(client_operation_id),
                "organization_id": str(organization_id),
            },
        )
    receipt = session.scalar(
        select(ChildcareCommandReceipt).where(
            ChildcareCommandReceipt.organization_id == organization_id,
            ChildcareCommandReceipt.client_operation_id == client_operation_id,
        )
    )
    if receipt is None:
        claim = session.scalar(
            select(ChildcareCommandClaim).where(
                ChildcareCommandClaim.organization_id == organization_id,
                ChildcareCommandClaim.client_operation_id == client_operation_id,
            )
        )
        if claim is None:
            return digest, None
        if claim.actor_user_id != actor_user_id:
            raise HTTPException(404, detail="Operation receipt not found")
        raise HTTPException(
            409,
            detail={
                "code": "operation_finalized_absent",
                "message": (
                    "No committed childcare command exists for this identity and operation."
                ),
                "actor_user_id": str(actor_user_id),
                "client_operation_id": str(client_operation_id),
                "organization_id": str(organization_id),
            },
        )
    if receipt.actor_user_id != actor_user_id:
        raise HTTPException(404, detail="Operation receipt not found")
    if (
        receipt.command_type != command_type
        or receipt.target_type != target_type
        or receipt.request_hash != digest
    ):
        raise HTTPException(
            409,
            detail={
                "code": "operation_reused",
                "client_operation_id": str(client_operation_id),
            },
        )
    return digest, receipt


def record_command(
    session: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    client_operation_id: UUID,
    command_type: str,
    target_type: str,
    target_id: UUID,
    request_hash: str,
    committed_version: int,
    facility_id: UUID | None = None,
    outcome: dict | None = None,
) -> ChildcareCommandReceipt:
    resolved_outcome = dict(outcome or {})
    if "action_route" in resolved_outcome:
        resolved_outcome["action_route"] = safe_action_route(resolved_outcome["action_route"])
    value = ChildcareCommandReceipt(
        id=uuid4(),
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        target_type=target_type,
        target_id=target_id,
        request_hash=request_hash,
        facility_id=facility_id,
        committed_version=committed_version,
        outcome=resolved_outcome,
    )
    session.add(value)
    return value


def require_version(value, expected_version: int, resource_type: str) -> None:
    if value.version != expected_version:
        raise HTTPException(
            409,
            detail={
                "code": "stale_childcare_resource",
                "resource_type": resource_type,
                "resource_id": str(value.id),
                "expected_version": expected_version,
                "current_version": value.version,
            },
        )
