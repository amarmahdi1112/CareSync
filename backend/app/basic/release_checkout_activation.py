"""Explicit, irreversible and exactly retryable facility release activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.common import restore_context
from app.api.basic.dependencies import BasicContext
from app.basic.childcare_commands import (
    begin_command,
    record_command,
    safe_action_route,
)
from app.basic.models import (
    ChildcareCommandReceipt,
    ChildReleaseAuthorization,
    Enrollment,
    Facility,
    FacilityReleaseCheckoutActivation,
)
from app.basic.release_checkout_activation_schemas import (
    RELEASE_CHECKOUT_ACTIVATION_CONFIRMATION,
    RELEASE_CHECKOUT_ACTIVATION_POLICY,
    ReleaseCheckoutActivationCommand,
    ReleaseCheckoutActivationPrerequisite,
    ReleaseCheckoutActivationReceipt,
    ReleaseCheckoutActivationResponse,
    ReleaseCheckoutActivationStatus,
)
from app.basic.release_checkout_capability import (
    facility_requires_verified_release_checkout,
)
from app.basic.security import audit

ACTIVATION_COMMAND_TYPE = "facility.release_checkout.activate"
ACTIVATION_TARGET_TYPE = "release_activation"
ACTIVATION_ACTION_ROUTE = "/settings?section=facility"
OPEN_ENROLLMENT_STATUSES = ("active", "paused")
EXECUTABLE_VERIFICATION_POLICIES = (
    "government_photo_id",
    "documented_familiarity",
    "government_photo_id_or_documented_familiarity",
)
POSTGRES_ACTIVATION_FUNCTION = (
    "public.caresync_release_checkout_activate_facility("
    "uuid,uuid,uuid,text,text,text,boolean,boolean,boolean,boolean)"
)


@dataclass(frozen=True)
class ReleaseCheckoutActivationError(RuntimeError):
    code: str
    status_code: int

    def __str__(self) -> str:
        return self.code


def _fail(code: str, status_code: int) -> ReleaseCheckoutActivationError:
    return ReleaseCheckoutActivationError(code=code, status_code=status_code)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _activation_command_available(session: Session, *, runtime_enabled: bool) -> bool:
    if not runtime_enabled:
        return False
    if not _is_postgres(session):
        # SQLite is used only by the portable contract suite. Production
        # readiness never sets runtime_enabled for that dialect.
        return True
    try:
        return bool(
            session.scalar(
                text(
                    "SELECT procedure.oid IS NOT NULL "
                    "AND procedure.prosecdef "
                    "AND NOT COALESCE(pg_catalog.has_function_privilege("
                    "'public',procedure.oid,'EXECUTE'),false) "
                    "AND COALESCE(pg_catalog.has_function_privilege("
                    "current_user,procedure.oid,'EXECUTE'),false) "
                    "FROM (SELECT pg_catalog.to_regprocedure(:signature) AS oid) AS resolved "
                    "LEFT JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=resolved.oid"
                ),
                {"signature": POSTGRES_ACTIVATION_FUNCTION},
            )
        )
    except DBAPIError:
        return False


def _facility(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    lock: bool = False,
) -> Facility:
    statement = select(Facility).where(
        Facility.organization_id == organization_id,
        Facility.id == facility_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise _fail("release_activation_facility_not_found", 404)
    return value


def _authority_readiness(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    foundation_present: bool,
) -> tuple[int, int]:
    if not foundation_present:
        return 0, 0
    child_ids = set(
        session.scalars(
            select(Enrollment.child_id).where(
                Enrollment.organization_id == organization_id,
                Enrollment.facility_id == facility_id,
                Enrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            )
        )
    )
    if not child_ids:
        return 0, 0
    evaluated_at = datetime.now(UTC)
    ready_ids = set(
        session.scalars(
            select(ChildReleaseAuthorization.child_id)
            .where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.child_id.in_(child_ids),
                ChildReleaseAuthorization.revoked_at.is_(None),
                ChildReleaseAuthorization.effective_from <= evaluated_at,
                ChildReleaseAuthorization.effective_until > evaluated_at,
                ChildReleaseAuthorization.verification_policy_code.in_(
                    EXECUTABLE_VERIFICATION_POLICIES
                ),
            )
            .distinct()
        )
    )
    return len(child_ids), len(ready_ids.intersection(child_ids))


def _portable_activated(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    foundation_present: bool,
) -> bool:
    if not foundation_present:
        return False
    return (
        session.scalar(
            select(FacilityReleaseCheckoutActivation.id).where(
                FacilityReleaseCheckoutActivation.organization_id == organization_id,
                FacilityReleaseCheckoutActivation.facility_id == facility_id,
                FacilityReleaseCheckoutActivation.activation_policy_version
                == RELEASE_CHECKOUT_ACTIVATION_POLICY,
            )
        )
        is not None
    )


def activation_status(
    session: Session,
    context: BasicContext,
    *,
    facility_id: UUID,
    foundation_present: bool,
    runtime_enabled: bool,
    database_writable: bool,
) -> ReleaseCheckoutActivationStatus:
    facility = _facility(
        session,
        organization_id=context.organization.id,
        facility_id=facility_id,
    )
    actor_authorized = context.role.key in {"owner", "administrator"}
    command_available = _activation_command_available(
        session,
        runtime_enabled=runtime_enabled,
    )
    if _is_postgres(session):
        activated = (
            facility_requires_verified_release_checkout(
                session,
                organization_id=context.organization.id,
                facility_id=facility.id,
                foundation_present=foundation_present,
                runtime_enabled=runtime_enabled,
            )
            if foundation_present
            else False
        )
        legacy_checkout_allowed = not activated if runtime_enabled else not foundation_present
    else:
        activated = _portable_activated(
            session,
            organization_id=context.organization.id,
            facility_id=facility.id,
            foundation_present=foundation_present,
        )
        legacy_checkout_allowed = not activated
    open_children, ready_children = _authority_readiness(
        session,
        organization_id=context.organization.id,
        facility_id=facility.id,
        foundation_present=foundation_present,
    )
    prerequisites = (
        ReleaseCheckoutActivationPrerequisite(
            code="runtime_available",
            label="Verified-release runtime is available",
            satisfied=runtime_enabled,
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="activation_command_available",
            label="Irreversible activation command is installed",
            satisfied=command_available,
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="database_writable",
            label="Database writes are enabled",
            satisfied=database_writable,
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="facility_active",
            label="Facility is active",
            satisfied=facility.status == "active",
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="privileged_actor",
            label="Current role is owner or administrator",
            satisfied=actor_authorized,
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="authority_records_complete",
            label=(
                "Every active or paused enrolled child has a current supported "
                "release authorization"
            ),
            satisfied=open_children == ready_children,
        ),
        ReleaseCheckoutActivationPrerequisite(
            code="not_already_activated",
            label="Facility has not already completed this one-way cutover",
            satisfied=not activated,
        ),
    )
    return ReleaseCheckoutActivationStatus(
        schema_version="release-checkout-activation-status-v1",
        organization_id=context.organization.id,
        facility_id=facility.id,
        facility_name=facility.name,
        runtime_available=runtime_enabled,
        activation_command_available=command_available,
        database_writable=database_writable,
        actor_authorized=actor_authorized,
        facility_active=facility.status == "active",
        activated=activated,
        legacy_checkout_allowed=legacy_checkout_allowed,
        activation_policy_version=(
            RELEASE_CHECKOUT_ACTIVATION_POLICY if activated else None
        ),
        open_enrollment_children=open_children,
        release_ready_children=ready_children,
        children_needing_authority_review=open_children - ready_children,
        prerequisites=prerequisites,
        can_activate=all(item.satisfied for item in prerequisites),
        confirmation_text=RELEASE_CHECKOUT_ACTIVATION_CONFIRMATION,
    )


def _receipt_response(
    session: Session,
    context: BasicContext,
    *,
    facility_id: UUID,
    receipt: ChildcareCommandReceipt,
    replayed: bool,
    foundation_present: bool,
    runtime_enabled: bool,
    database_writable: bool,
) -> ReleaseCheckoutActivationResponse:
    try:
        action_route = safe_action_route((receipt.outcome or {}).get("action_route"))
        if (
            receipt.command_type != ACTIVATION_COMMAND_TYPE
            or receipt.target_type != ACTIVATION_TARGET_TYPE
            or receipt.facility_id != facility_id
            or receipt.committed_version != 1
            or action_route != ACTIVATION_ACTION_ROUTE
        ):
            raise ValueError
        status = activation_status(
            session,
            context,
            facility_id=facility_id,
            foundation_present=foundation_present,
            runtime_enabled=runtime_enabled,
            database_writable=database_writable,
        )
        if not status.activated:
            raise ValueError
        return ReleaseCheckoutActivationResponse(
            schema_version="release-checkout-activation-v1",
            status=status,
            receipt=ReleaseCheckoutActivationReceipt(
                organization_id=context.organization.id,
                facility_id=facility_id,
                activation_id=receipt.target_id,
                client_operation_id=receipt.client_operation_id,
                committed_at=_utc(receipt.committed_at),
                action_route=ACTIVATION_ACTION_ROUTE,
            ),
            replayed=replayed,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise _fail("release_activation_receipt_incomplete", 409) from error


def _insert_postgres_activation(
    session: Session,
    command: ReleaseCheckoutActivationCommand,
    *,
    activation_id: UUID,
    request_hash: str,
) -> None:
    session.execute(
        text(
            "SELECT public.caresync_release_checkout_activate_facility("
            ":facility_id,:activation_id,:operation_id,:request_hash,"
            ":policy_version,:confirmation_text,:authority_reviewed,"
            ":verification_reviewed,:legacy_understood,:irreversible_understood)"
        ),
        {
            "facility_id": command.facility_id,
            "activation_id": activation_id,
            "operation_id": command.client_operation_id,
            "request_hash": request_hash,
            "policy_version": command.activation_policy_version,
            "confirmation_text": command.confirmation_text,
            "authority_reviewed": command.authority_records_reviewed,
            "verification_reviewed": command.verification_workflow_reviewed,
            "legacy_understood": command.legacy_checkout_closure_understood,
            "irreversible_understood": command.irreversible_activation_understood,
        },
    )


def _map_database_error(error: Exception) -> ReleaseCheckoutActivationError:
    rendered = str(getattr(error, "orig", error)).lower()
    mappings = (
        ("release_activation_authority_records_incomplete", 409),
        ("release_activation_already_active", 409),
        ("release_activation_facility_inactive", 409),
        ("release_activation_forbidden", 403),
        ("release_activation_confirmation_required", 422),
        ("uq_release_checkout_activations_facility", 409),
    )
    for code, status_code in mappings:
        if code in rendered:
            return _fail(
                "release_activation_already_active"
                if code == "uq_release_checkout_activations_facility"
                else code,
                status_code,
            )
    return _fail("release_activation_unavailable", 503)


def activate_release_checkout(
    session: Session,
    context: BasicContext,
    command: ReleaseCheckoutActivationCommand,
    *,
    foundation_present: bool,
    runtime_enabled: bool,
    database_writable: bool,
) -> ReleaseCheckoutActivationResponse:
    if command.organization_id != context.organization.id:
        raise _fail("release_activation_scope_mismatch", 403)
    if context.role.key not in {"owner", "administrator"}:
        raise _fail("release_activation_forbidden", 403)
    if not foundation_present or not runtime_enabled:
        raise _fail("release_activation_unavailable", 503)
    if not database_writable:
        raise _fail("release_activation_database_read_only", 409)

    _facility(
        session,
        organization_id=context.organization.id,
        facility_id=command.facility_id,
        lock=True,
    )
    intent = {
        "organization_id": command.organization_id,
        "facility_id": command.facility_id,
        "activation_policy_version": command.activation_policy_version,
        "authority_records_reviewed": command.authority_records_reviewed,
        "verification_workflow_reviewed": command.verification_workflow_reviewed,
        "legacy_checkout_closure_understood": (
            command.legacy_checkout_closure_understood
        ),
        "irreversible_activation_understood": (
            command.irreversible_activation_understood
        ),
        "confirmation_text": command.confirmation_text,
    }
    try:
        request_hash, replay = begin_command(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            client_operation_id=command.client_operation_id,
            command_type=ACTIVATION_COMMAND_TYPE,
            target_type=ACTIVATION_TARGET_TYPE,
            target_scope=command.facility_id,
            intent=intent,
        )
        if replay is not None:
            return _receipt_response(
                session,
                context,
                facility_id=command.facility_id,
                receipt=replay,
                replayed=True,
                foundation_present=foundation_present,
                runtime_enabled=runtime_enabled,
                database_writable=database_writable,
            )

        status = activation_status(
            session,
            context,
            facility_id=command.facility_id,
            foundation_present=foundation_present,
            runtime_enabled=runtime_enabled,
            database_writable=database_writable,
        )
        if status.activated:
            raise _fail("release_activation_already_active", 409)
        if not status.activation_command_available:
            raise _fail("release_activation_unavailable", 503)
        if status.children_needing_authority_review:
            raise _fail("release_activation_authority_records_incomplete", 409)
        if not status.can_activate:
            if not status.facility_active:
                raise _fail("release_activation_facility_inactive", 409)
            raise _fail("release_activation_prerequisites_incomplete", 409)

        activation_id = uuid4()
        receipt = record_command(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            client_operation_id=command.client_operation_id,
            command_type=ACTIVATION_COMMAND_TYPE,
            target_type=ACTIVATION_TARGET_TYPE,
            target_id=activation_id,
            request_hash=request_hash,
            committed_version=1,
            facility_id=command.facility_id,
            outcome={"action_route": ACTIVATION_ACTION_ROUTE},
        )
        session.flush()
        session.refresh(receipt)
        if _is_postgres(session):
            _insert_postgres_activation(
                session,
                command,
                activation_id=activation_id,
                request_hash=request_hash,
            )
        else:
            session.add(
                FacilityReleaseCheckoutActivation(
                    id=activation_id,
                    organization_id=context.organization.id,
                    facility_id=command.facility_id,
                    activated_by_user_id=context.user.id,
                    activated_by_membership_id=context.membership.id,
                    activated_by_role_id=context.role.id,
                    activated_by_role_key=context.role.key,
                    activation_operation_id=command.client_operation_id,
                    activation_policy_version=RELEASE_CHECKOUT_ACTIVATION_POLICY,
                    activated_at=_utc(receipt.committed_at),
                )
            )
        audit(
            session,
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action="facility.release_checkout.activated",
            entity_type="release_checkout_activation",
            entity_id=activation_id,
            facility_id=command.facility_id,
            details={
                "activation_policy_version": RELEASE_CHECKOUT_ACTIVATION_POLICY,
                "client_operation_id": str(command.client_operation_id),
            },
        )
        session.flush()
        committed_at = _utc(receipt.committed_at)
        session.commit()
        restore_context(session, context)
        receipt.committed_at = committed_at
        return _receipt_response(
            session,
            context,
            facility_id=command.facility_id,
            receipt=receipt,
            replayed=False,
            foundation_present=foundation_present,
            runtime_enabled=runtime_enabled,
            database_writable=database_writable,
        )
    except ReleaseCheckoutActivationError:
        session.rollback()
        raise
    except HTTPException:
        session.rollback()
        raise
    except (DBAPIError, IntegrityError) as error:
        session.rollback()
        raise _map_database_error(error) from None
