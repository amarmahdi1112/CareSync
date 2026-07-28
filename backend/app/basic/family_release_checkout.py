"""Pure contract helpers for normal verified child release checkout.

This module performs no database, attendance, audit, notification, outbox, or
receipt work.  The future atomic service will invoke these helpers before and
after its single authoritative transaction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from enum import StrEnum
from uuid import UUID

from app.basic.family_release_checkout_schemas import (
    ERROR_PRESENTATION,
    RELEASE_CHECKOUT_COMMAND_TYPE,
    RELEASE_CHECKOUT_TARGET_TYPE,
    VERIFICATION_RESULT_BY_METHOD,
    ReleaseCheckoutCommand,
    ReleaseCheckoutErrorResponse,
    ReleaseCheckoutResponse,
    ReleaseEvidenceDigestInput,
)


class ReleaseCheckoutContractErrorCode(StrEnum):
    VERIFICATION_PAIR_INVALID = "release_checkout_verification_pair_invalid"
    VERIFICATION_POLICY_UNAVAILABLE = "release_checkout_verification_policy_unavailable"
    VERIFICATION_POLICY_MISMATCH = "release_checkout_verification_policy_mismatch"
    RESPONSE_MISMATCH = "release_checkout_response_mismatch"


class ReleaseCheckoutContractError(ValueError):
    """One bounded pure-contract failure with no caller-authored explanation."""

    def __init__(self, code: ReleaseCheckoutContractErrorCode):
        self.code = code
        message, recovery_action = ERROR_PRESENTATION[code.value]
        self.product_error = ReleaseCheckoutErrorResponse(
            schema_version="release-checkout-error-v1",
            code=code.value,
            message=message,
            recovery_action=recovery_action,
        )
        super().__init__(message)


def _canonical(value):
    """Use the command-spine canonical scalar representation."""

    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_release_checkout_request_document_bytes(
    command: ReleaseCheckoutCommand,
) -> bytes:
    """Return the exact purpose-bound command-spine bytes.

    As with every CareSync command receipt, the operation identifier selects
    the immutable receipt and is excluded from the intent hash.  Every other
    normalized request field is included.  The child identifier is also the
    command target scope so this digest cannot be reused for another command
    purpose or target kind.
    """

    intent = command.model_dump(
        mode="python",
        exclude={"client_operation_id"},
    )
    document = _canonical(
        {
            "command_type": RELEASE_CHECKOUT_COMMAND_TYPE,
            "target_type": RELEASE_CHECKOUT_TARGET_TYPE,
            "target_scope": command.child_id,
            "intent": intent,
        }
    )
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def release_checkout_request_hash(command: ReleaseCheckoutCommand) -> str:
    """Return lower-case SHA-256 for one normalized, purpose-bound command."""

    return hashlib.sha256(canonical_release_checkout_request_document_bytes(command)).hexdigest()


def canonical_release_evidence_document_bytes(
    evidence: ReleaseEvidenceDigestInput,
) -> bytes:
    """Return the frozen, versioned evidence document sealed at checkout.

    Null values remain explicit so a later object attachment, content digest,
    or expiry cannot be confused with the evidence facts reviewed here.
    """

    document = evidence.model_dump(mode="json")
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_release_evidence_digest(
    evidence: ReleaseEvidenceDigestInput,
) -> str:
    """Return lower-case SHA-256 for the exact release evidence document."""

    return hashlib.sha256(canonical_release_evidence_document_bytes(evidence)).hexdigest()


def validate_release_checkout_verification(
    *,
    verification_policy_code: str,
    verification_method: str,
    verification_result: str,
) -> tuple[str, str]:
    """Validate the executable policy matrix and return the accepted pair."""

    expected_result = VERIFICATION_RESULT_BY_METHOD.get(verification_method)
    if expected_result is None or verification_result != expected_result:
        raise ReleaseCheckoutContractError(
            ReleaseCheckoutContractErrorCode.VERIFICATION_PAIR_INVALID
        )
    allowed_methods = {
        "government_photo_id": {"government_photo_id"},
        "documented_familiarity": {"documented_familiarity"},
        "government_photo_id_or_documented_familiarity": {
            "government_photo_id",
            "documented_familiarity",
        },
    }
    if verification_policy_code == "government_photo_id_and_secondary_check":
        raise ReleaseCheckoutContractError(
            ReleaseCheckoutContractErrorCode.VERIFICATION_POLICY_UNAVAILABLE
        )
    if verification_method not in allowed_methods.get(verification_policy_code, set()):
        raise ReleaseCheckoutContractError(
            ReleaseCheckoutContractErrorCode.VERIFICATION_POLICY_MISMATCH
        )
    return verification_method, verification_result


def validate_release_checkout_response(
    command: ReleaseCheckoutCommand,
    response: ReleaseCheckoutResponse,
) -> ReleaseCheckoutResponse:
    """Accept a success only when every immutable command echo is exact."""

    resource = response.resource
    if (
        resource.client_operation_id != command.client_operation_id
        or resource.request_hash != release_checkout_request_hash(command)
        or resource.child_id != command.child_id
        or resource.facility_id != command.facility_id
        or resource.room_id != command.expected_room_id
        or resource.attendance_day_id != command.expected_attendance_day_id
        or resource.attendance_interval_id != command.expected_attendance_interval_id
        or resource.staff_shift_id != command.expected_staff_shift_id
        or resource.recipient_person_id != command.recipient_person_id
        or resource.recipient_person_version_id != command.recipient_person_version_id
        or resource.authorization_id != command.authorization_id
        or resource.authorization_version != command.authorization_version
        or resource.authority_revision != command.expected_authority_revision
        or resource.restriction_digest_sha256 != command.expected_restriction_digest_sha256
        or resource.decision_policy_version != command.expected_decision_policy_version
        or resource.verification_method != command.verification_method
        or resource.verification_result != command.verification_result
        or resource.requested_at != command.requested_at
    ):
        raise ReleaseCheckoutContractError(ReleaseCheckoutContractErrorCode.RESPONSE_MISMATCH)
    return response
