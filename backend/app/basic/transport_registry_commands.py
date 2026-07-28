"""Atomic 0032 transport-registry command repository adapters.

PostgreSQL reaches registry mutations only through the certified SECURITY
DEFINER repository.  SQLite uses the same append-only models and migration
guards so portable tests can prove exact-retry and actor/result binding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.basic.dependencies import BasicContext
from app.basic.models import (
    AuditEvent,
    OrganizationMembership,
    Role,
    StaffDriverAuthorizationDecision,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationReviewDecision,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    TransportRegistryCommandReceipt,
    TransportVehicle,
    TransportVehicleEvidenceReviewDecision,
    TransportVehicleEvidenceScanFact,
    TransportVehicleEvidenceVersion,
    TransportVehicleVersion,
    UserNotification,
)
from app.basic.security import set_rls_organization, set_rls_user

CommandKind = Literal[
    "driver_declaration",
    "qualification_evidence",
    "qualification_review",
    "driver_authorization",
    "vehicle_create",
    "vehicle_version",
    "vehicle_retire",
    "vehicle_evidence",
    "vehicle_evidence_review",
    "readiness_evaluation",
]

_SERVER_KEYS = frozenset(
    {
        "result_id",
        "version_id",
        "evidence_object_id",
        "review_id",
        "scan_fact_id",
        "ciphertext_sha256",
        "storage_reference",
        "encryption_key_id",
        "scanner_engine",
        "scanner_version",
        "scanned_at",
    }
)


@dataclass(frozen=True)
class TransportCommandResult:
    client_operation_id: UUID
    command_kind: str
    result_kind: str
    result_id: UUID
    committed_at: datetime
    exact_retry: bool
    operational_driver_ready: bool = False
    dispatch_authorized: bool = False

    def as_response(self) -> dict[str, Any]:
        return {
            "schema_version": "0032",
            "client_operation_id": self.client_operation_id,
            "command_kind": self.command_kind,
            "result_kind": self.result_kind,
            "result_id": self.result_id,
            "committed_at": self.committed_at,
            "exact_retry": self.exact_retry,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }


class AmbiguousTransportCommandCommit(RuntimeError):
    """The connection failed while commit outcome was unknowable."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _organization_date(context: BasicContext, value: datetime) -> date:
    try:
        timezone = ZoneInfo(str(context.organization.timezone))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise HTTPException(
            409, detail={"code": "organization_timezone_invalid"}
        ) from error
    return _as_utc(value).astimezone(timezone).date()


def canonical_request_sha256(payload: dict[str, Any]) -> str:
    """Portable canonical digest; PostgreSQL independently hashes jsonb text."""

    public_payload = {
        key: _jsonable(value)
        for key, value in payload.items()
        if key not in _SERVER_KEYS
    }
    encoded = json.dumps(
        public_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_internal_payload(
    command_kind: CommandKind, public_payload: dict[str, Any]
) -> dict[str, Any]:
    payload = _jsonable(public_payload)
    if command_kind == "vehicle_retire":
        payload["result_id"] = payload["vehicle_id"]
    else:
        payload["result_id"] = str(uuid4())
    if command_kind == "vehicle_create":
        payload["version_id"] = str(uuid4())
    elif command_kind == "qualification_evidence":
        payload["evidence_object_id"] = str(uuid4())
    elif command_kind in {"qualification_review", "vehicle_evidence_review"}:
        payload["review_id"] = str(uuid4())
    elif command_kind == "vehicle_evidence":
        payload["scan_fact_id"] = str(uuid4())
    return payload


def _postgres_request_sha256(session: Session, payload: dict[str, Any]) -> str:
    value = session.scalar(
        text(
            "SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(("
            "CAST(:payload AS jsonb)-CAST(:server_keys AS text[]))::text,'UTF8')),'hex')"
        ),
        {
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "server_keys": sorted(_SERVER_KEYS),
        },
    )
    if not isinstance(value, str) or len(value) != 64:
        raise RuntimeError("Transport command digest could not be derived")
    return value


def _result_from_mapping(row: Any) -> TransportCommandResult:
    return TransportCommandResult(
        client_operation_id=UUID(str(row["client_operation_id"])),
        command_kind=str(row["command_kind"]),
        result_kind=str(row["result_kind"]),
        result_id=UUID(str(row["result_id"])),
        committed_at=row["committed_at"],
        exact_retry=bool(row["exact_retry"]),
        operational_driver_ready=False,
        dispatch_authorized=False,
    )


def _execute_postgres(
    session: Session,
    *,
    command_kind: CommandKind,
    operation_id: UUID,
    payload: dict[str, Any],
) -> TransportCommandResult:
    request_sha256 = _postgres_request_sha256(session, payload)
    row = session.execute(
        text(
            "SELECT * FROM public.caresync_0032_execute_command("
            ":command_kind,:operation_id,:request_sha256,CAST(:payload AS jsonb))"
        ),
        {
            "command_kind": command_kind,
            "operation_id": operation_id,
            "request_sha256": request_sha256,
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ).mappings().one()
    result = _result_from_mapping(row)
    try:
        session.commit()
    except DBAPIError as error:
        if error.connection_invalidated:
            raise AmbiguousTransportCommandCommit from error
        session.rollback()
        raise
    return result


def _receipt_result(
    receipt: TransportRegistryCommandReceipt, *, exact_retry: bool
) -> TransportCommandResult:
    return TransportCommandResult(
        client_operation_id=receipt.client_operation_id,
        command_kind=receipt.command_kind,
        result_kind=receipt.result_kind,
        result_id=receipt.result_id,
        committed_at=receipt.committed_at,
        exact_retry=exact_retry,
    )


def _next_value(session: Session, model, column, *criteria) -> int:
    return int(session.scalar(select(func.coalesce(func.max(column), 0)).where(*criteria)) or 0) + 1


def _membership(session: Session, organization_id: UUID, membership_id: UUID):
    value = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.id == membership_id,
            OrganizationMembership.status == "active",
        )
    )
    if value is None:
        raise HTTPException(404, "Active staff membership not found")
    return value


def _vehicle(session: Session, organization_id: UUID, vehicle_id: UUID) -> TransportVehicle:
    value = session.scalar(
        select(TransportVehicle).where(
            TransportVehicle.organization_id == organization_id,
            TransportVehicle.id == vehicle_id,
            TransportVehicle.retired_at.is_(None),
        )
    )
    if value is None:
        raise HTTPException(404, "Active vehicle not found")
    return value


def _can_manage(context: BasicContext) -> bool:
    return "transport:manage" in set(context.role.permissions or [])


def _assert_vehicle_actor(context: BasicContext, vehicle: TransportVehicle) -> None:
    if _can_manage(context):
        return
    if (
        vehicle.owner_kind != "staff_personal"
        or vehicle.staff_owner_membership_id != context.membership.id
    ):
        raise HTTPException(403, "Vehicle is outside this staff member's transport scope")


def _map_repository_error(error: DBAPIError) -> HTTPException:
    sqlstate = str(getattr(error.orig, "sqlstate", "") or "")
    diagnostic = getattr(error.orig, "diag", None)
    marker = str(getattr(diagnostic, "message_primary", "") or "")
    known_markers = {
        "transport_command_identity_unavailable": (403, "transport_identity_unavailable"),
        "transport_command_forbidden": (403, "transport_command_forbidden"),
        "transport_command_scope_not_found": (404, "transport_scope_not_found"),
        "transport_vehicle_not_found": (404, "transport_vehicle_not_found"),
        "transport_command_invalid": (422, "transport_command_invalid"),
        "transport_command_payload_invalid": (422, "transport_command_payload_invalid"),
        "transport_request_digest_mismatch": (422, "transport_request_digest_mismatch"),
        "transport_command_kind_unknown": (422, "transport_command_kind_unknown"),
        "transport_operation_reused": (409, "transport_operation_reused"),
        "transport_independent_review_required": (409, "independent_review_required"),
        "transport_review_source_invalid": (409, "transport_review_source_invalid"),
        "transport_authorization_capability_mismatch": (
            409,
            "authorization_capability_mismatch",
        ),
        "transport_authorization_qualification_set_invalid": (
            409,
            "authorization_qualification_set_invalid",
        ),
        "transport_organization_timezone_invalid": (
            409,
            "organization_timezone_invalid",
        ),
        "transport_vehicle_plate_conflict": (409, "vehicle_plate_conflict"),
        "transport_readiness_requires_authorization": (409, "authorization_required"),
        "transport_readiness_requires_capability": (409, "driver_declaration_required"),
        "transport_vehicle_version_missing": (409, "vehicle_version_missing"),
    }
    if marker in known_markers:
        status_code, code = known_markers[marker]
        return HTTPException(status_code, detail={"code": code})
    if sqlstate == "42501":
        return HTTPException(403, detail={"code": "transport_command_forbidden"})
    if sqlstate == "22023":
        return HTTPException(422, detail={"code": "transport_command_invalid"})
    if sqlstate in {"23505", "23514", "23503"}:
        return HTTPException(409, detail={"code": "transport_command_conflict"})
    return HTTPException(503, detail={"code": "transport_command_repository_unavailable"})


def _add_sqlite_readiness_notifications(
    session: Session,
    *,
    organization_id: UUID,
    membership: OrganizationMembership,
    readiness_id: UUID,
    vehicle_id: UUID | None,
    licence_expired: bool,
    licence_expiring: bool,
    qualification_expired: bool,
    qualification_expiring: bool,
    vehicle_expired: bool,
    vehicle_expiring: bool,
    local_today: date,
) -> None:
    def add_once(*, user_id: UUID, event_key: str, **values: Any) -> None:
        existing_id = session.scalar(
            select(UserNotification.id).where(
                UserNotification.user_id == user_id,
                UserNotification.event_key == event_key,
            )
        )
        if existing_id is None:
            session.add(UserNotification(user_id=user_id, event_key=event_key, **values))

    manager_ids = list(
        session.scalars(
            select(OrganizationMembership.user_id)
            .join(
                Role,
                (Role.organization_id == OrganizationMembership.organization_id)
                & (Role.id == OrganizationMembership.role_id),
            )
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == "active",
            )
        )
    )
    manager_ids = [
        user_id
        for user_id in manager_ids
        if "transport:manage"
        in set(
            session.scalar(
                select(Role.permissions)
                .join(
                    OrganizationMembership,
                    (OrganizationMembership.organization_id == Role.organization_id)
                    & (OrganizationMembership.role_id == Role.id),
                )
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.status == "active",
                )
            )
            or []
        )
    ]
    recipient_ids = set(manager_ids) | {membership.user_id}
    for user_id in recipient_ids:
        if licence_expired or licence_expiring:
            expired = licence_expired
            event_key = (
                f"driver-licence-expiry:{membership.id}:{local_today}:"
                f"{'expired' if expired else 'warning'}"
            )
            add_once(
                user_id=user_id,
                event_key=event_key,
                organization_id=organization_id,
                category="credential",
                severity="critical" if expired else "warning",
                title=(
                    "Driver licence expired"
                    if expired
                    else "Driver licence expires soon"
                ),
                body=(
                    "The current verified driver licence has expired."
                    if expired
                    else "The current verified driver licence expires within 30 days."
                ),
                action_path="/transport-registry",
                action_entity_type="transport_registry",
                action_entity_id=readiness_id,
            )
        if qualification_expired or qualification_expiring:
            expired = qualification_expired
            event_key = (
                f"driver-qualification-expiry:{membership.id}:{local_today}:"
                f"{'expired' if expired else 'warning'}"
            )
            add_once(
                user_id=user_id,
                event_key=event_key,
                organization_id=organization_id,
                category="credential",
                severity="critical" if expired else "warning",
                title=(
                    "Driver qualification expired"
                    if expired
                    else "Driver qualification expires soon"
                ),
                body=(
                    "A current authorization-bound driver qualification has expired."
                    if expired
                    else (
                        "A current authorization-bound driver qualification expires "
                        "within 30 days."
                    )
                ),
                action_path="/transport-registry",
                action_entity_type="transport_registry",
                action_entity_id=readiness_id,
            )
        if vehicle_id is not None and (vehicle_expired or vehicle_expiring):
            expired = vehicle_expired
            event_key = (
                f"vehicle-evidence-expiry:{vehicle_id}:{local_today}:"
                f"{'expired' if expired else 'warning'}"
            )
            add_once(
                user_id=user_id,
                event_key=event_key,
                organization_id=organization_id,
                category="credential",
                severity="critical" if expired else "warning",
                title=(
                    "Vehicle evidence expired"
                    if expired
                    else "Vehicle evidence expires soon"
                ),
                body=(
                    "Current verified vehicle evidence has expired."
                    if expired
                    else "Current verified vehicle evidence expires within 30 days."
                ),
                action_path="/transport-registry",
                action_entity_type="transport_registry",
                action_entity_id=readiness_id,
            )


def _sqlite_readiness(
    session: Session,
    *,
    context: BasicContext,
    payload: dict[str, Any],
    now: datetime,
) -> StaffDriverReadinessDecision:
    organization_id = context.organization.id
    membership_id = UUID(payload["membership_id"])
    membership = _membership(session, organization_id, membership_id)
    if membership.user_id == context.user.id:
        raise HTTPException(409, "Independent readiness evaluation is required")
    authorization = session.scalar(
        select(StaffDriverAuthorizationDecision)
        .where(
            StaffDriverAuthorizationDecision.organization_id == organization_id,
            StaffDriverAuthorizationDecision.membership_id == membership_id,
        )
        .order_by(StaffDriverAuthorizationDecision.decision_sequence.desc())
        .limit(1)
    )
    if authorization is None:
        raise HTTPException(409, "Driver authorization must be reviewed first")
    authorized_capability = session.get(
        StaffDriverCapabilityVersion, authorization.capability_version_id
    )
    current_capability = session.scalar(
        select(StaffDriverCapabilityVersion)
        .where(
            StaffDriverCapabilityVersion.organization_id == organization_id,
            StaffDriverCapabilityVersion.membership_id == membership_id,
        )
        .order_by(StaffDriverCapabilityVersion.version_number.desc())
        .limit(1)
    )
    if authorized_capability is None or current_capability is None:
        raise HTTPException(409, "Driver capability must be declared first")
    local_today = _organization_date(context, now)
    reasons: list[str] = []
    readiness_hard_block = False
    if current_capability.id != authorized_capability.id:
        reasons.append("capability_changed_since_authorization")
        readiness_hard_block = True
    elif current_capability.status != "declared":
        reasons.append("capability_withdrawn")
        readiness_hard_block = True
    if (
        authorization.decision != "authorized"
        or authorization.authorization_valid_from is None
        or authorization.authorization_valid_until is None
        or _as_utc(authorization.authorization_valid_from) > now
        or _as_utc(authorization.authorization_valid_until) <= now
    ):
        reasons.append("authorization_not_current")
        readiness_hard_block = True

    raw_bound_ids = list(authorization.qualification_version_ids or [])
    qualification_blocked = False
    try:
        bound_ids = [UUID(value) for value in raw_bound_ids]
    except (TypeError, ValueError, AttributeError):
        bound_ids = []
        reasons.append("qualification_binding_invalid")
        qualification_blocked = True
    if len(set(raw_bound_ids)) != len(raw_bound_ids):
        reasons.append("qualification_binding_invalid")
        qualification_blocked = True
    bound_rows = list(
        session.scalars(
            select(StaffDriverQualificationVersion).where(
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id == membership_id,
                StaffDriverQualificationVersion.id.in_(bound_ids),
            )
        )
    )
    if len(bound_rows) != len(bound_ids):
        if "qualification_binding_missing" not in reasons:
            reasons.append("qualification_binding_missing")
        qualification_blocked = True
    bound_by_type: dict[str, StaffDriverQualificationVersion] = {}
    for row in bound_rows:
        if row.qualification_type in bound_by_type:
            if "qualification_binding_invalid" not in reasons:
                reasons.append("qualification_binding_invalid")
            qualification_blocked = True
        bound_by_type[row.qualification_type] = row

    qualification_rows = list(
        session.scalars(
            select(StaffDriverQualificationVersion)
            .where(
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id == membership_id,
            )
            .order_by(
                StaffDriverQualificationVersion.qualification_type,
                StaffDriverQualificationVersion.version_number.desc(),
            )
        )
    )
    current_by_type: dict[str, StaffDriverQualificationVersion] = {}
    for row in qualification_rows:
        current_by_type.setdefault(row.qualification_type, row)

    licence = current_by_type.get("driver_licence")
    bound_licence = bound_by_type.get("driver_licence")
    licence_expired = False
    licence_expiring = False
    if licence is None:
        reasons.append("driver_licence_missing")
        qualification_blocked = True
    else:
        if licence.status != "verified" or _as_utc(licence.effective_at) > now:
            reasons.append("driver_licence_unverified")
            qualification_blocked = True
        if bound_licence is None or licence.id != bound_licence.id:
            reasons.append("driver_licence_changed_since_authorization")
            qualification_blocked = True
        if licence.expiry_date is not None and licence.expiry_date < local_today:
            licence_expired = True
            qualification_blocked = True
            reasons.append("driver_licence_expired")
        elif (
            licence.expiry_date is not None
            and licence.expiry_date <= local_today + timedelta(days=30)
        ):
            licence_expiring = True
            reasons.append("driver_licence_expiring_soon")

    qualification_expired = False
    for qualification_type, bound in bound_by_type.items():
        if qualification_type == "driver_licence":
            continue
        current = current_by_type.get(qualification_type)
        if current is None:
            reasons.append(f"qualification_missing:{qualification_type}")
            qualification_blocked = True
            continue
        if current.id != bound.id:
            reasons.append(
                f"qualification_changed_since_authorization:{qualification_type}"
            )
            qualification_blocked = True
        if current.status != "verified" or _as_utc(current.effective_at) > now:
            reasons.append(f"qualification_unverified:{qualification_type}")
            qualification_blocked = True
        if current.expiry_date is not None and current.expiry_date < local_today:
            reasons.append(f"qualification_expired:{qualification_type}")
            qualification_expired = True
            qualification_blocked = True
        elif (
            current.expiry_date is not None
            and current.expiry_date <= local_today + timedelta(days=30)
        ):
            reasons.append(f"qualification_expiring_soon:{qualification_type}")

    vehicle_id = UUID(payload["vehicle_id"]) if payload.get("vehicle_id") else None
    vehicle_version = None
    evidence_ids: list[str] = []
    vehicle_expired = False
    vehicle_expiring = False
    if vehicle_id is None:
        reasons.append("vehicle_not_selected_for_evaluation")
    else:
        vehicle = _vehicle(session, organization_id, vehicle_id)
        if (
            vehicle.owner_kind != "organization"
            and vehicle.staff_owner_membership_id != membership_id
        ):
            raise HTTPException(404, "Vehicle is outside this staff transport scope")
        vehicle_version = session.scalar(
            select(TransportVehicleVersion)
            .where(
                TransportVehicleVersion.organization_id == organization_id,
                TransportVehicleVersion.vehicle_id == vehicle_id,
            )
            .order_by(TransportVehicleVersion.version_number.desc())
            .limit(1)
        )
        if vehicle_version is None:
            raise HTTPException(409, "Vehicle facts are missing")
        evidence_rows = list(
            session.scalars(
                select(TransportVehicleEvidenceVersion)
                .where(
                    TransportVehicleEvidenceVersion.organization_id == organization_id,
                    TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
                )
                .order_by(
                    TransportVehicleEvidenceVersion.evidence_type,
                    TransportVehicleEvidenceVersion.version_number.desc(),
                )
            )
        )
        latest: dict[str, TransportVehicleEvidenceVersion] = {}
        for row in evidence_rows:
            latest.setdefault(row.evidence_type, row)
        current_verified = {
            kind: row
            for kind, row in latest.items()
            if row.status == "verified" and row.vehicle_version_id == vehicle_version.id
        }
        evidence_ids = [str(row.id) for row in current_verified.values()]
        for required in ("registration", "insurance"):
            row = current_verified.get(required)
            if (
                (row is None or row.expiry_date is None or row.expiry_date < local_today)
                and "vehicle_evidence_incomplete" not in reasons
            ):
                reasons.append("vehicle_evidence_incomplete")
                readiness_hard_block = True
        for row in current_verified.values():
            if row.expiry_date is not None and row.expiry_date < local_today:
                vehicle_expired = True
            elif (
                row.expiry_date is not None
                and row.expiry_date <= local_today + timedelta(days=30)
            ):
                vehicle_expiring = True
        if vehicle_expired:
            reasons.append("vehicle_evidence_expired")
        elif vehicle_expiring:
            reasons.append("vehicle_evidence_expiring_soon")
    if not reasons:
        reasons.append("operational_transport_release_not_enabled")
    readiness = StaffDriverReadinessDecision(
        id=UUID(payload["result_id"]),
        organization_id=organization_id,
        membership_id=membership_id,
        decision_sequence=_next_value(
            session,
            StaffDriverReadinessDecision,
            StaffDriverReadinessDecision.decision_sequence,
            StaffDriverReadinessDecision.organization_id == organization_id,
            StaffDriverReadinessDecision.membership_id == membership_id,
        ),
        capability_version_id=authorized_capability.id,
        authorization_decision_id=authorization.id,
        vehicle_id=vehicle_id,
        vehicle_version_id=vehicle_version.id if vehicle_version else None,
        vehicle_evidence_version_ids=evidence_ids,
        decision=(
            "blocked"
            if qualification_blocked
            or readiness_hard_block
            or licence_expired
            or qualification_expired
            or vehicle_expired
            else "needs_review"
        ),
        reason_codes=reasons,
        evaluated_by_user_id=context.user.id,
        evaluated_at=now,
        operational_driver_ready=False,
        dispatch_authorized=False,
    )
    session.add(readiness)
    session.flush()
    _add_sqlite_readiness_notifications(
        session,
        organization_id=organization_id,
        membership=membership,
        readiness_id=readiness.id,
        vehicle_id=vehicle_id,
        licence_expired=licence_expired,
        licence_expiring=licence_expiring,
        qualification_expired=qualification_expired,
        qualification_expiring=any(
            reason.startswith("qualification_expiring_soon:") for reason in reasons
        ),
        vehicle_expired=vehicle_expired,
        vehicle_expiring=vehicle_expiring,
        local_today=local_today,
    )
    return readiness


def _execute_sqlite(
    session: Session,
    *,
    context: BasicContext,
    command_kind: CommandKind,
    operation_id: UUID,
    payload: dict[str, Any],
) -> TransportCommandResult:
    organization_id = context.organization.id
    actor_user_id = context.user.id
    request_sha256 = canonical_request_sha256(payload)
    existing = session.scalar(
        select(TransportRegistryCommandReceipt).where(
            TransportRegistryCommandReceipt.organization_id == organization_id,
            TransportRegistryCommandReceipt.actor_user_id == actor_user_id,
            TransportRegistryCommandReceipt.client_operation_id == operation_id,
        )
    )
    if existing is not None:
        if existing.command_kind != command_kind or existing.request_sha256 != request_sha256:
            raise HTTPException(409, "Operation id was already used for a different command")
        return _receipt_result(existing, exact_retry=True)

    manager_commands = {
        "qualification_review",
        "driver_authorization",
        "vehicle_evidence_review",
        "readiness_evaluation",
    }
    if command_kind in manager_commands and not _can_manage(context):
        raise HTTPException(403, "Transport manager permission required")

    now = datetime.now(UTC)
    membership_id = UUID(payload["membership_id"]) if payload.get("membership_id") else None
    result_kind: str
    result_id = UUID(payload["result_id"])
    if command_kind == "driver_declaration":
        membership = _membership(session, organization_id, membership_id)
        if membership.user_id != actor_user_id:
            raise HTTPException(403, "A staff member may change only their own declaration")
        session.add(
            StaffDriverCapabilityVersion(
                id=result_id,
                organization_id=organization_id,
                membership_id=membership_id,
                version_number=_next_value(
                    session,
                    StaffDriverCapabilityVersion,
                    StaffDriverCapabilityVersion.version_number,
                    StaffDriverCapabilityVersion.organization_id == organization_id,
                    StaffDriverCapabilityVersion.membership_id == membership_id,
                ),
                status=payload["status"],
                willing_to_drive=payload["willing_to_drive"],
                licence_jurisdiction=payload.get("licence_jurisdiction"),
                licence_jurisdiction_other=payload.get("licence_jurisdiction_other"),
                licence_class=payload.get("licence_class"),
                vehicle_access=payload["vehicle_access"],
                preferred_service_radius_km=payload.get("preferred_service_radius_km"),
                source_kind="staff_self",
                source_screening_profile_version=None,
                effective_at=now,
                recorded_by_user_id=actor_user_id,
                recorded_at=now,
            )
        )
        result_kind = "driver_capability"
    elif command_kind == "qualification_evidence":
        membership = _membership(session, organization_id, membership_id)
        if membership.user_id != actor_user_id:
            raise HTTPException(403, "A staff member may upload only their own qualification")
        qualification = StaffDriverQualificationVersion(
            id=result_id,
            organization_id=organization_id,
            membership_id=membership_id,
            qualification_type=payload["qualification_type"],
            version_number=_next_value(
                session,
                StaffDriverQualificationVersion,
                StaffDriverQualificationVersion.version_number,
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id == membership_id,
                StaffDriverQualificationVersion.qualification_type == payload["qualification_type"],
            ),
            status="declared",
            jurisdiction=payload.get("jurisdiction"),
            qualification_class=payload.get("qualification_class"),
            identifier_last4=payload.get("identifier_last4"),
            issue_date=(
                date.fromisoformat(payload["issue_date"])
                if payload.get("issue_date")
                else None
            ),
            expiry_date=(
                date.fromisoformat(payload["expiry_date"])
                if payload.get("expiry_date")
                else None
            ),
            source_screening_document_version_id=None,
            evidence_reference_sha256=payload["content_sha256"],
            effective_at=now,
            recorded_by_user_id=actor_user_id,
            recorded_at=now,
        )
        session.add(qualification)
        session.flush()
        session.add(
            StaffDriverQualificationEvidenceObject(
                id=UUID(payload["evidence_object_id"]),
                organization_id=organization_id,
                membership_id=membership_id,
                qualification_version_id=result_id,
                original_filename=payload.get("original_filename"),
                media_type=payload["media_type"],
                byte_size=payload["byte_size"],
                content_sha256=payload["content_sha256"],
                ciphertext_sha256=payload["ciphertext_sha256"],
                storage_reference=payload["storage_reference"],
                encryption_key_id=payload["encryption_key_id"],
                scanner_engine=payload["scanner_engine"],
                scanner_version=payload["scanner_version"],
                scanned_at=datetime.fromisoformat(payload["scanned_at"]),
                recorded_by_user_id=actor_user_id,
                recorded_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
        )
        result_kind = "driver_qualification"
    elif command_kind == "qualification_review":
        source = session.scalar(
            select(StaffDriverQualificationVersion).where(
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id == membership_id,
                StaffDriverQualificationVersion.id
                == UUID(payload["source_qualification_version_id"]),
                StaffDriverQualificationVersion.status == "declared",
            )
        )
        evidence = session.scalar(
            select(StaffDriverQualificationEvidenceObject).where(
                StaffDriverQualificationEvidenceObject.organization_id == organization_id,
                StaffDriverQualificationEvidenceObject.membership_id == membership_id,
                StaffDriverQualificationEvidenceObject.qualification_version_id
                == UUID(payload["source_qualification_version_id"]),
            )
        )
        latest_source = (
            session.scalar(
                select(StaffDriverQualificationVersion)
                .where(
                    StaffDriverQualificationVersion.organization_id == organization_id,
                    StaffDriverQualificationVersion.membership_id == membership_id,
                    StaffDriverQualificationVersion.qualification_type
                    == source.qualification_type,
                )
                .order_by(StaffDriverQualificationVersion.version_number.desc())
                .limit(1)
            )
            if source is not None
            else None
        )
        if (
            source is None
            or latest_source is None
            or latest_source.id != source.id
            or evidence is None
            or evidence.recorded_by_user_id == actor_user_id
        ):
            raise HTTPException(409, "Independent source evidence review is required")
        result = StaffDriverQualificationVersion(
            id=result_id,
            organization_id=organization_id,
            membership_id=membership_id,
            qualification_type=source.qualification_type,
            version_number=_next_value(
                session,
                StaffDriverQualificationVersion,
                StaffDriverQualificationVersion.version_number,
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id == membership_id,
                StaffDriverQualificationVersion.qualification_type == source.qualification_type,
            ),
            status=payload["decision"],
            jurisdiction=source.jurisdiction,
            qualification_class=source.qualification_class,
            identifier_last4=source.identifier_last4,
            issue_date=source.issue_date,
            expiry_date=source.expiry_date,
            source_screening_document_version_id=source.source_screening_document_version_id,
            evidence_reference_sha256=source.evidence_reference_sha256,
            effective_at=now,
            recorded_by_user_id=actor_user_id,
            recorded_at=now,
        )
        session.add(result)
        session.flush()
        session.add(
            StaffDriverQualificationReviewDecision(
                id=UUID(payload["review_id"]),
                organization_id=organization_id,
                membership_id=membership_id,
                source_qualification_version_id=source.id,
                result_qualification_version_id=result.id,
                decision=payload["decision"],
                reason_code=payload["reason_code"],
                reviewed_by_user_id=actor_user_id,
                reviewed_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
        )
        result_kind = "driver_qualification"
    elif command_kind == "driver_authorization":
        authorization_member = _membership(session, organization_id, membership_id)
        if authorization_member.user_id == actor_user_id:
            raise HTTPException(409, "Independent authorization review is required")
        capability = session.scalar(
            select(StaffDriverCapabilityVersion).where(
                StaffDriverCapabilityVersion.organization_id == organization_id,
                StaffDriverCapabilityVersion.membership_id == membership_id,
                StaffDriverCapabilityVersion.id == UUID(payload["capability_version_id"]),
            )
        )
        if capability is None:
            raise HTTPException(
                409, detail={"code": "authorization_capability_mismatch"}
            )
        raw_qualification_ids = payload.get("qualification_version_ids") or []
        if len(set(raw_qualification_ids)) != len(raw_qualification_ids):
            raise HTTPException(
                409, detail={"code": "authorization_qualification_set_invalid"}
            )
        qualification_ids = [UUID(value) for value in raw_qualification_ids]
        qualifications = list(
            session.scalars(
                select(StaffDriverQualificationVersion).where(
                    StaffDriverQualificationVersion.organization_id == organization_id,
                    StaffDriverQualificationVersion.membership_id == membership_id,
                    StaffDriverQualificationVersion.id.in_(qualification_ids),
                )
            )
        )
        qualification_types = {row.qualification_type for row in qualifications}
        if (
            len(qualifications) != len(qualification_ids)
            or len(qualification_types) != len(qualifications)
        ):
            raise HTTPException(
                409, detail={"code": "authorization_qualification_set_invalid"}
            )
        if payload["decision"] == "authorized":
            valid_until = datetime.fromisoformat(payload["authorization_valid_until"])
            current_capability = session.scalar(
                select(StaffDriverCapabilityVersion)
                .where(
                    StaffDriverCapabilityVersion.organization_id == organization_id,
                    StaffDriverCapabilityVersion.membership_id == membership_id,
                )
                .order_by(StaffDriverCapabilityVersion.version_number.desc())
                .limit(1)
            )
            invalid_set = (
                not qualifications
                or "driver_licence" not in qualification_types
                or current_capability is None
                or current_capability.id != capability.id
                or capability.status != "declared"
                or _as_utc(capability.effective_at) > now
            )
            for qualification in qualifications:
                current = session.scalar(
                    select(StaffDriverQualificationVersion)
                    .where(
                        StaffDriverQualificationVersion.organization_id == organization_id,
                        StaffDriverQualificationVersion.membership_id == membership_id,
                        StaffDriverQualificationVersion.qualification_type
                        == qualification.qualification_type,
                    )
                    .order_by(StaffDriverQualificationVersion.version_number.desc())
                    .limit(1)
                )
                if (
                    current is None
                    or current.id != qualification.id
                    or qualification.status != "verified"
                    or _as_utc(qualification.effective_at) > now
                    or (
                        qualification.expiry_date is not None
                        and qualification.expiry_date
                        < _organization_date(context, valid_until)
                    )
                ):
                    invalid_set = True
            if invalid_set:
                raise HTTPException(
                    409, detail={"code": "authorization_qualification_set_invalid"}
                )
        session.add(
            StaffDriverAuthorizationDecision(
                id=result_id,
                organization_id=organization_id,
                membership_id=membership_id,
                decision_sequence=_next_value(
                    session,
                    StaffDriverAuthorizationDecision,
                    StaffDriverAuthorizationDecision.decision_sequence,
                    StaffDriverAuthorizationDecision.organization_id == organization_id,
                    StaffDriverAuthorizationDecision.membership_id == membership_id,
                ),
                capability_version_id=UUID(payload["capability_version_id"]),
                qualification_version_ids=payload["qualification_version_ids"],
                decision=payload["decision"],
                reason_code=payload["reason_code"],
                authorization_valid_from=(
                    _as_utc(datetime.fromisoformat(payload["authorization_valid_from"]))
                    if payload.get("authorization_valid_from")
                    else None
                ),
                authorization_valid_until=(
                    _as_utc(datetime.fromisoformat(payload["authorization_valid_until"]))
                    if payload.get("authorization_valid_until")
                    else None
                ),
                reviewed_by_user_id=actor_user_id,
                reviewed_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
        )
        result_kind = "driver_authorization"
    elif command_kind == "vehicle_create":
        owner_membership = (
            UUID(payload["staff_owner_membership_id"])
            if payload.get("staff_owner_membership_id")
            else None
        )
        if payload["owner_kind"] == "organization" and not _can_manage(context):
            raise HTTPException(403, "Transport manager permission required")
        if payload["owner_kind"] == "staff_personal":
            owner = _membership(session, organization_id, owner_membership)
            if owner.user_id != actor_user_id and not _can_manage(context):
                raise HTTPException(403, "A staff member may register only their own vehicle")
        vehicle = TransportVehicle(
            id=result_id,
            organization_id=organization_id,
            owner_kind=payload["owner_kind"],
            staff_owner_membership_id=owner_membership,
            created_by_user_id=actor_user_id,
            created_at=now,
        )
        session.add(vehicle)
        session.flush()
        session.add(
            TransportVehicleVersion(
                id=UUID(payload["version_id"]),
                organization_id=organization_id,
                vehicle_id=vehicle.id,
                version_number=1,
                make=payload["make"],
                model=payload["model"],
                model_year=payload["model_year"],
                color=payload.get("color"),
                plate_token=payload["plate_token"],
                plate_jurisdiction=payload["plate_jurisdiction"],
                passenger_capacity=payload["passenger_capacity"],
                child_passenger_capacity=payload["child_passenger_capacity"],
                wheelchair_accessible=payload["wheelchair_accessible"],
                effective_at=now,
                recorded_by_user_id=actor_user_id,
                recorded_at=now,
            )
        )
        result_kind = "vehicle"
    elif command_kind == "vehicle_version":
        vehicle_id = UUID(payload["vehicle_id"])
        vehicle = _vehicle(session, organization_id, vehicle_id)
        _assert_vehicle_actor(context, vehicle)
        session.add(
            TransportVehicleVersion(
                id=result_id,
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                version_number=_next_value(
                    session,
                    TransportVehicleVersion,
                    TransportVehicleVersion.version_number,
                    TransportVehicleVersion.organization_id == organization_id,
                    TransportVehicleVersion.vehicle_id == vehicle_id,
                ),
                make=payload["make"],
                model=payload["model"],
                model_year=payload["model_year"],
                color=payload.get("color"),
                plate_token=payload["plate_token"],
                plate_jurisdiction=payload["plate_jurisdiction"],
                passenger_capacity=payload["passenger_capacity"],
                child_passenger_capacity=payload["child_passenger_capacity"],
                wheelchair_accessible=payload["wheelchair_accessible"],
                effective_at=now,
                recorded_by_user_id=actor_user_id,
                recorded_at=now,
            )
        )
        result_kind = "vehicle_version"
    elif command_kind == "vehicle_retire":
        vehicle = _vehicle(session, organization_id, UUID(payload["vehicle_id"]))
        _assert_vehicle_actor(context, vehicle)
        vehicle.retired_at = now
        vehicle.retired_by_user_id = actor_user_id
        vehicle.retirement_reason_code = payload["reason_code"]
        result_kind = "vehicle"
    elif command_kind == "vehicle_evidence":
        vehicle_id = UUID(payload["vehicle_id"])
        vehicle = _vehicle(session, organization_id, vehicle_id)
        _assert_vehicle_actor(context, vehicle)
        vehicle_version = session.scalar(
            select(TransportVehicleVersion)
            .where(
                TransportVehicleVersion.organization_id == organization_id,
                TransportVehicleVersion.vehicle_id == vehicle_id,
            )
            .order_by(TransportVehicleVersion.version_number.desc())
            .limit(1)
        )
        if vehicle_version is None:
            raise HTTPException(409, "Vehicle facts are missing")
        evidence = TransportVehicleEvidenceVersion(
            id=result_id,
            organization_id=organization_id,
            vehicle_id=vehicle_id,
            vehicle_version_id=vehicle_version.id,
            evidence_type=payload["evidence_type"],
            version_number=_next_value(
                session,
                TransportVehicleEvidenceVersion,
                TransportVehicleEvidenceVersion.version_number,
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
                TransportVehicleEvidenceVersion.evidence_type == payload["evidence_type"],
            ),
            status="provided",
            issue_date=(
                date.fromisoformat(payload["issue_date"])
                if payload.get("issue_date")
                else None
            ),
            expiry_date=(
                date.fromisoformat(payload["expiry_date"])
                if payload.get("expiry_date")
                else None
            ),
            original_filename=payload.get("original_filename"),
            media_type=payload["media_type"],
            byte_size=payload["byte_size"],
            content_sha256=payload["content_sha256"],
            ciphertext_sha256=payload["ciphertext_sha256"],
            storage_reference=payload["storage_reference"],
            encryption_key_id=payload["encryption_key_id"],
            recorded_by_user_id=actor_user_id,
            recorded_at=now,
        )
        session.add(evidence)
        session.flush()
        session.add(
            TransportVehicleEvidenceScanFact(
                id=UUID(payload["scan_fact_id"]),
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                evidence_version_id=evidence.id,
                decision="clean",
                scanner_engine=payload["scanner_engine"],
                scanner_version=payload["scanner_version"],
                scanner_signature=None,
                scanned_at=datetime.fromisoformat(payload["scanned_at"]),
                recorded_by_user_id=actor_user_id,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
        )
        result_kind = "vehicle_evidence"
    elif command_kind == "vehicle_evidence_review":
        vehicle_id = UUID(payload["vehicle_id"])
        _vehicle(session, organization_id, vehicle_id)
        source = session.scalar(
            select(TransportVehicleEvidenceVersion).where(
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
                TransportVehicleEvidenceVersion.id == UUID(payload["source_evidence_version_id"]),
                TransportVehicleEvidenceVersion.status == "provided",
            )
        )
        scan = session.scalar(
            select(TransportVehicleEvidenceScanFact).where(
                TransportVehicleEvidenceScanFact.organization_id == organization_id,
                TransportVehicleEvidenceScanFact.vehicle_id == vehicle_id,
                TransportVehicleEvidenceScanFact.evidence_version_id
                == UUID(payload["source_evidence_version_id"]),
                TransportVehicleEvidenceScanFact.decision == "clean",
            )
        )
        latest_source = (
            session.scalar(
                select(TransportVehicleEvidenceVersion)
                .where(
                    TransportVehicleEvidenceVersion.organization_id == organization_id,
                    TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
                    TransportVehicleEvidenceVersion.evidence_type == source.evidence_type,
                )
                .order_by(TransportVehicleEvidenceVersion.version_number.desc())
                .limit(1)
            )
            if source is not None
            else None
        )
        if (
            source is None
            or latest_source is None
            or latest_source.id != source.id
            or scan is None
            or source.recorded_by_user_id == actor_user_id
        ):
            raise HTTPException(409, "Independent clean-source review is required")
        result = TransportVehicleEvidenceVersion(
            id=result_id,
            organization_id=organization_id,
            vehicle_id=vehicle_id,
            vehicle_version_id=source.vehicle_version_id,
            evidence_type=source.evidence_type,
            version_number=_next_value(
                session,
                TransportVehicleEvidenceVersion,
                TransportVehicleEvidenceVersion.version_number,
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
                TransportVehicleEvidenceVersion.evidence_type == source.evidence_type,
            ),
            status=payload["decision"],
            issue_date=source.issue_date,
            expiry_date=source.expiry_date,
            original_filename=source.original_filename,
            media_type=source.media_type,
            byte_size=source.byte_size,
            content_sha256=source.content_sha256,
            ciphertext_sha256=source.ciphertext_sha256,
            storage_reference=source.storage_reference,
            encryption_key_id=source.encryption_key_id,
            recorded_by_user_id=actor_user_id,
            recorded_at=now,
        )
        session.add(result)
        session.flush()
        session.add(
            TransportVehicleEvidenceReviewDecision(
                id=UUID(payload["review_id"]),
                organization_id=organization_id,
                vehicle_id=vehicle_id,
                source_evidence_version_id=source.id,
                result_evidence_version_id=result.id,
                decision=payload["decision"],
                reason_code=payload["reason_code"],
                reviewed_by_user_id=actor_user_id,
                reviewed_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
        )
        result_kind = "vehicle_evidence"
    elif command_kind == "readiness_evaluation":
        _sqlite_readiness(session, context=context, payload=payload, now=now)
        result_kind = "driver_readiness"
    else:  # pragma: no cover - CommandKind and routes keep this unreachable.
        raise RuntimeError("Unknown transport command")

    session.flush()
    receipt = TransportRegistryCommandReceipt(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        client_operation_id=operation_id,
        command_kind=command_kind,
        request_sha256=request_sha256,
        result_kind=result_kind,
        result_id=result_id,
        committed_at=now,
        operational_driver_ready=False,
        dispatch_authorized=False,
    )
    session.add(receipt)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=f"transport_registry.{command_kind}",
            entity_type="transport_registry_command",
            entity_id=result_id,
            occurred_at=now,
            details={
                "operation_id": str(operation_id),
                "result_kind": result_kind,
                "operational_driver_ready": False,
                "dispatch_authorized": False,
            },
        )
    )
    try:
        session.commit()
    except DBAPIError as error:
        if error.connection_invalidated:
            raise AmbiguousTransportCommandCommit from error
        session.rollback()
        raise
    return _receipt_result(receipt, exact_retry=False)


def execute_transport_command(
    *,
    session: Session,
    context: BasicContext,
    command_kind: CommandKind,
    operation_id: UUID,
    public_payload: dict[str, Any],
    evidence_session_factory: sessionmaker[Session] | None = None,
) -> TransportCommandResult:
    """Execute and commit one command, returning an actor-private exact receipt."""

    payload = _new_internal_payload(command_kind, public_payload)
    selected_session = session
    owned_session: Session | None = None
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        if command_kind in {"qualification_evidence", "vehicle_evidence"}:
            if evidence_session_factory is None:
                raise HTTPException(
                    503, detail={"code": "transport_evidence_ingest_unavailable"}
                )
            owned_session = evidence_session_factory()
            selected_session = owned_session
            set_rls_user(selected_session, context.user.id)
            set_rls_organization(selected_session, context.organization.id)
        try:
            return _execute_postgres(
                selected_session,
                command_kind=command_kind,
                operation_id=operation_id,
                payload=payload,
            )
        except AmbiguousTransportCommandCommit:
            raise
        except DBAPIError as error:
            selected_session.rollback()
            raise _map_repository_error(error) from error
        finally:
            if owned_session is not None:
                owned_session.close()
    try:
        return _execute_sqlite(
            session,
            context=context,
            command_kind=command_kind,
            operation_id=operation_id,
            payload=payload,
        )
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "Transport command conflicts with current facts") from error
