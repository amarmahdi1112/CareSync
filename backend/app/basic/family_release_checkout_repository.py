"""Narrow PostgreSQL adapter for verified family-release checkout.

The runtime database role cannot read private family-authority evidence or
write immutable release snapshots directly.  Revision 0029D therefore exposes
four fixed ``SECURITY DEFINER`` functions.  This module is the only Python
surface that calls them, and every returned row is parsed through the public
minimum-necessary resource contract before it reaches the service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.basic.family_release_checkout_schemas import (
    ReleaseCheckoutResource,
    ReleaseCheckoutSchema,
    VerificationResult,
)
from app.basic.family_release_context_schemas import (
    ReleaseContextInput,
    Sha256Hex,
    UtcDateTime,
    VerificationMethod,
)


@dataclass(frozen=True)
class ReleaseCheckoutRepositoryError(RuntimeError):
    """Bounded repository failure safe to expose through the checkout API."""

    code: str
    status_code: int

    def __str__(self) -> str:
        return self.code


def _fail(code: str, status_code: int) -> ReleaseCheckoutRepositoryError:
    return ReleaseCheckoutRepositoryError(code=code, status_code=status_code)


class ReleaseSnapshotAppendInput(ReleaseCheckoutSchema):
    """Non-confidential assertions accepted by the 0029D append function.

    Family, actor, membership, role, room assignment, evidence and recipient
    display facts are intentionally absent.  The database derives and locks
    those values instead of trusting a runtime-role caller.
    """

    release_id: UUID
    child_id: UUID
    facility_id: UUID
    room_id: UUID
    attendance_day_id: UUID
    attendance_day_version: int
    attendance_interval_id: UUID
    checkout_event_id: UUID
    staff_shift_id: UUID
    recipient_person_id: UUID
    recipient_person_version_id: UUID
    authorization_id: UUID
    authorization_version: int
    authority_revision: int
    restriction_digest_sha256: Sha256Hex
    verification_method: VerificationMethod
    verification_result: VerificationResult
    decision_policy_version: Literal["release-context-v1"]
    decision_at: UtcDateTime
    requested_at: UtcDateTime
    request_hash: Sha256Hex


_RESOURCE_COLUMNS = """
release_id, organization_id, facility_id, room_id, child_id,
attendance_day_id, attendance_interval_id, attendance_day_version,
checkout_event_id, staff_shift_id, actor_user_id, actor_membership_id,
recipient_person_id, recipient_person_version_id, recipient_display_name,
recipient_relationship, authorization_id, authorization_version,
authority_revision, restriction_digest_sha256, verification_policy_code,
verification_method, verification_result, decision_policy_version,
requested_at, checked_out_at, committed_at, client_operation_id,
request_hash, release_mode
""".strip()


def _require_postgres(session: Session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise _fail("family_authority_release_checkout_unavailable", 503)


def _translate_database_error(error: SQLAlchemyError) -> ReleaseCheckoutRepositoryError:
    """Map only stable database markers; never reflect driver text."""

    message = str(getattr(error, "orig", error))
    mappings: tuple[tuple[str, str, int], ...] = (
        ("release_checkout_identity_unavailable", "release_checkout_forbidden", 403),
        ("release_context_identity_unavailable", "release_checkout_forbidden", 403),
        ("release_context_forbidden", "release_checkout_forbidden", 403),
        ("release_context_scope_not_found", "release_checkout_scope_not_found", 404),
        ("release_context_inconsistent", "release_checkout_context_stale", 409),
        ("release_checkout_forbidden", "release_checkout_forbidden", 403),
        ("release_checkout_scope_not_found", "release_checkout_scope_not_found", 404),
        ("release_checkout_not_activated", "release_checkout_not_activated", 409),
        ("open_shift_required", "open_shift_required", 409),
        ("open_shift_facility_mismatch", "open_shift_facility_mismatch", 409),
        ("child_not_on_site", "child_not_on_site", 409),
        ("release_checkout_requested_at_future", "release_checkout_requested_at_future", 422),
        ("release_checkout_context_stale", "release_checkout_context_stale", 409),
        (
            "release_checkout_verification_policy_mismatch",
            "release_checkout_verification_policy_mismatch",
            409,
        ),
        ("release_checkout_receipt_incomplete", "release_checkout_receipt_incomplete", 409),
    )
    for marker, code, status_code in mappings:
        if marker in message:
            return _fail(code, status_code)
    return _fail("family_authority_release_checkout_unavailable", 503)


def _resource_from_row(row, *, incomplete_code: str) -> ReleaseCheckoutResource:
    if row is None:
        raise _fail(incomplete_code, 409 if incomplete_code.endswith("incomplete") else 503)
    values = dict(row)
    # PostgreSQL renders timestamptz values in the connection/session timezone.
    # The public contract is deliberately UTC-only, so normalize the three
    # projected instants at this adapter boundary while leaving naive or
    # otherwise malformed values for the strict schema to reject.
    for field_name in ("requested_at", "checked_out_at", "committed_at"):
        value = values.get(field_name)
        if (
            isinstance(value, datetime)
            and value.tzinfo is not None
            and value.utcoffset() is not None
        ):
            values[field_name] = value.astimezone(UTC)
    try:
        return ReleaseCheckoutResource.model_validate(values)
    except (TypeError, ValueError, ValidationError) as error:
        status_code = 409 if incomplete_code.endswith("incomplete") else 503
        raise _fail(incomplete_code, status_code) from error


def postgres_release_checkout_instant(session: Session) -> datetime:
    """Capture one DB wall-clock instant after all service locks are held."""

    _require_postgres(session)
    try:
        value = session.scalar(text("SELECT pg_catalog.clock_timestamp()"))
    except SQLAlchemyError as error:
        raise _translate_database_error(error) from None
    if not isinstance(value, datetime):
        raise _fail("family_authority_release_checkout_unavailable", 503)
    return value


def _context_input_from_value(value: Any) -> ReleaseContextInput:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise _fail("family_authority_release_checkout_unavailable", 503) from error
    try:
        return ReleaseContextInput.model_validate(value)
    except (TypeError, ValueError, ValidationError) as error:
        raise _fail("family_authority_release_checkout_unavailable", 503) from error


def postgres_release_checkout_context_input_at(
    session: Session,
    *,
    child_id: UUID,
    facility_id: UUID,
    decision_at: datetime,
) -> ReleaseContextInput:
    """Re-evaluate B's minimum context at the post-lock DB instant."""

    _require_postgres(session)
    try:
        value = session.scalar(
            text(
                "SELECT public.caresync_family_release_context_inputs_at("
                "CAST(:child_id AS uuid),CAST(:facility_id AS uuid),"
                "CAST(:decision_at AS timestamp with time zone))"
            ),
            {
                "child_id": str(child_id),
                "facility_id": str(facility_id),
                "decision_at": decision_at,
            },
        )
    except SQLAlchemyError as error:
        raise _translate_database_error(error) from None
    return _context_input_from_value(value)


def postgres_release_checkout_activation_enabled(
    session: Session,
    *,
    facility_id: UUID,
) -> bool:
    """Read only the facility activation bit through the 0029D gate."""

    _require_postgres(session)
    try:
        value = session.scalar(
            text(
                "SELECT public.caresync_release_checkout_activation_enabled("
                "CAST(:facility_id AS uuid))"
            ),
            {"facility_id": str(facility_id)},
        )
    except SQLAlchemyError as error:
        raise _translate_database_error(error) from None
    if not isinstance(value, bool):
        raise _fail("family_authority_release_checkout_unavailable", 503)
    return value


def postgres_release_checkout_replay(
    session: Session,
    *,
    client_operation_id: UUID,
) -> ReleaseCheckoutResource:
    """Load one actor/org/operation-bound minimum replay projection."""

    _require_postgres(session)
    try:
        row = session.execute(
            text(
                f"SELECT {_RESOURCE_COLUMNS} "
                "FROM public.caresync_release_checkout_replay("
                "CAST(:client_operation_id AS uuid))"
            ),
            {"client_operation_id": str(client_operation_id)},
        ).mappings().one_or_none()
    except SQLAlchemyError as error:
        raise _translate_database_error(error) from None
    return _resource_from_row(row, incomplete_code="release_checkout_receipt_incomplete")


def postgres_release_checkout_insert_snapshot(
    session: Session,
    payload: ReleaseSnapshotAppendInput,
) -> ReleaseCheckoutResource:
    """Append and return one authoritative immutable snapshot projection."""

    _require_postgres(session)
    statement = text(
        f"SELECT {_RESOURCE_COLUMNS} "
        "FROM public.caresync_release_checkout_insert_snapshot("
        "CAST(:release_id AS uuid),CAST(:child_id AS uuid),"
        "CAST(:facility_id AS uuid),CAST(:room_id AS uuid),"
        "CAST(:attendance_day_id AS uuid),CAST(:attendance_day_version AS integer),"
        "CAST(:attendance_interval_id AS uuid),CAST(:checkout_event_id AS uuid),"
        "CAST(:staff_shift_id AS uuid),CAST(:recipient_person_id AS uuid),"
        "CAST(:recipient_person_version_id AS uuid),CAST(:authorization_id AS uuid),"
        "CAST(:authorization_version AS integer),CAST(:authority_revision AS integer),"
        "CAST(:restriction_digest_sha256 AS text),CAST(:verification_method AS text),"
        "CAST(:verification_result AS text),CAST(:decision_policy_version AS text),"
        "CAST(:decision_at AS timestamp with time zone),"
        "CAST(:requested_at AS timestamp with time zone),CAST(:request_hash AS text))"
    )
    values = payload.model_dump(mode="python")
    values.update(
        {
            key: str(value)
            for key, value in values.items()
            if isinstance(value, UUID)
        }
    )
    try:
        row = session.execute(statement, values).mappings().one_or_none()
    except SQLAlchemyError as error:
        raise _translate_database_error(error) from None
    return _resource_from_row(
        row,
        incomplete_code="family_authority_release_checkout_unavailable",
    )
