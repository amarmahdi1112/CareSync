"""Pure contract proof for the 0029C normal verified-release foundation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.basic.family_release_checkout import (
    ReleaseCheckoutContractError,
    ReleaseCheckoutContractErrorCode,
    canonical_release_checkout_request_document_bytes,
    canonical_release_evidence_digest,
    canonical_release_evidence_document_bytes,
    release_checkout_request_hash,
    validate_release_checkout_response,
    validate_release_checkout_verification,
)
from app.basic.family_release_checkout_schemas import (
    ERROR_PRESENTATION,
    ReleaseCheckoutCommand,
    ReleaseCheckoutErrorResponse,
    ReleaseCheckoutResponse,
    ReleaseEvidenceDigestInput,
)

REQUESTED_AT = datetime(2026, 7, 18, 12, 34, 56, 123456, tzinfo=UTC)
COMMITTED_AT = datetime(2026, 7, 18, 12, 35, 1, 987654, tzinfo=UTC)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _command(**overrides) -> ReleaseCheckoutCommand:
    values = {
        "schema_version": "release-checkout-command-v1",
        "client_operation_id": _id(1),
        "requested_at": REQUESTED_AT,
        "child_id": _id(2),
        "facility_id": _id(3),
        "expected_room_id": _id(4),
        "expected_attendance_day_id": _id(5),
        "expected_attendance_interval_id": _id(6),
        "expected_staff_shift_id": _id(7),
        "recipient_person_id": _id(8),
        "recipient_person_version_id": _id(9),
        "authorization_id": _id(10),
        "authorization_version": 11,
        "expected_authority_revision": 12,
        "expected_restriction_digest_sha256": "ab" * 32,
        "expected_decision_policy_version": "release-context-v1",
        "verification_method": "government_photo_id",
        "verification_result": "verified",
    }
    values.update(overrides)
    return ReleaseCheckoutCommand.model_validate(values)


def _evidence(**overrides) -> ReleaseEvidenceDigestInput:
    values = {
        "schema_version": "release-evidence-v1",
        "evidence_id": _id(31),
        "evidence_kind": "identity_document",
        "evidence_object_id": _id(32),
        "content_sha256": "cd" * 32,
        "expires_at": datetime(2027, 1, 2, 3, 4, 5, 6007, tzinfo=UTC),
        "evidence_assessment_id": _id(33),
        "evidence_assessment_version": 2,
        "decision": "reviewed",
        "assessed_epistemic_status": "document_observed",
    }
    values.update(overrides)
    return ReleaseEvidenceDigestInput.model_validate(values)


def test_release_evidence_canonical_document_and_digest_golden_vector() -> None:
    expected = (
        b'{"assessed_epistemic_status":"document_observed",'
        b'"content_sha256":"' + (b"cd" * 32) + b'",'
        b'"decision":"reviewed",'
        b'"evidence_assessment_id":"00000000-0000-0000-0000-000000000021",'
        b'"evidence_assessment_version":2,'
        b'"evidence_id":"00000000-0000-0000-0000-00000000001f",'
        b'"evidence_kind":"identity_document",'
        b'"evidence_object_id":"00000000-0000-0000-0000-000000000020",'
        b'"expires_at":"2027-01-02T03:04:05.006007Z",'
        b'"schema_version":"release-evidence-v1"}'
    )
    assert canonical_release_evidence_document_bytes(_evidence()) == expected
    assert canonical_release_evidence_digest(_evidence()) == (
        "0e1e97aa5b7fa9c1c6c5b362a5da8e3ce9e09ec25de60e42322264f924b76c83"
    )


def test_release_evidence_canonical_document_preserves_explicit_nulls() -> None:
    document = json.loads(
        canonical_release_evidence_document_bytes(
            _evidence(
                evidence_object_id=None,
                content_sha256=None,
                expires_at=None,
                assessed_epistemic_status="reported",
            )
        )
    )
    assert document["evidence_object_id"] is None
    assert document["content_sha256"] is None
    assert document["expires_at"] is None


@pytest.mark.parametrize(
    ("object_id", "content_sha256"),
    [(_id(32), None), (None, "cd" * 32)],
)
def test_release_evidence_rejects_partial_object_content_pair(
    object_id: UUID | None,
    content_sha256: str | None,
) -> None:
    with pytest.raises(ValidationError, match="present together"):
        _evidence(
            evidence_object_id=object_id,
            content_sha256=content_sha256,
        )


def test_release_evidence_assessment_version_is_frozen_at_two() -> None:
    with pytest.raises(ValidationError):
        _evidence(evidence_assessment_version=3)


def _response(
    command: ReleaseCheckoutCommand | None = None,
    *,
    resource_overrides: dict | None = None,
    receipt_overrides: dict | None = None,
    response_overrides: dict | None = None,
) -> ReleaseCheckoutResponse:
    command = command or _command()
    release_id = _id(20)
    resource = {
        "release_id": release_id,
        "organization_id": _id(21),
        "facility_id": command.facility_id,
        "room_id": command.expected_room_id,
        "child_id": command.child_id,
        "attendance_day_id": command.expected_attendance_day_id,
        "attendance_interval_id": command.expected_attendance_interval_id,
        "attendance_day_version": 4,
        "checkout_event_id": _id(22),
        "staff_shift_id": command.expected_staff_shift_id,
        "actor_user_id": _id(23),
        "actor_membership_id": _id(24),
        "recipient_person_id": command.recipient_person_id,
        "recipient_person_version_id": command.recipient_person_version_id,
        "recipient_display_name": "Amal Noor Ali",
        "recipient_relationship": "Grandparent",
        "authorization_id": command.authorization_id,
        "authorization_version": command.authorization_version,
        "authority_revision": command.expected_authority_revision,
        "restriction_digest_sha256": command.expected_restriction_digest_sha256,
        "verification_policy_code": "government_photo_id_or_documented_familiarity",
        "verification_method": command.verification_method,
        "verification_result": command.verification_result,
        "decision_policy_version": command.expected_decision_policy_version,
        "requested_at": command.requested_at,
        "checked_out_at": COMMITTED_AT,
        "committed_at": COMMITTED_AT,
        "client_operation_id": command.client_operation_id,
        "request_hash": release_checkout_request_hash(command),
        "release_mode": "normal",
    }
    resource.update(resource_overrides or {})
    receipt = {
        "organization_id": resource["organization_id"],
        "client_operation_id": resource["client_operation_id"],
        "command_type": "attendance.release.checkout",
        "target_type": "attendance_release",
        "target_id": resource["release_id"],
        "committed_version": 1,
        "committed_at": resource["committed_at"],
        "facility_id": resource["facility_id"],
        "action_route": f"/attendance/releases/{resource['release_id']}",
    }
    receipt.update(receipt_overrides or {})
    response = {
        "schema_version": "release-checkout-v1",
        "resource": resource,
        "receipt": receipt,
        "replayed": False,
    }
    response.update(response_overrides or {})
    return ReleaseCheckoutResponse.model_validate(response)


def test_command_requires_every_frozen_field_and_forbids_every_extra_field() -> None:
    command = _command().model_dump(mode="python")
    for field_name in tuple(command):
        incomplete = dict(command)
        del incomplete[field_name]
        with pytest.raises(ValidationError):
            ReleaseCheckoutCommand.model_validate(incomplete)

    for forbidden in (
        "recipient_display_name",
        "recipient_relationship",
        "family_id",
        "evidence_id",
        "government_id_number",
        "notes",
        "checked_out_at",
        "override_reason_code",
    ):
        changed = dict(command)
        changed[forbidden] = "not accepted"
        with pytest.raises(ValidationError):
            ReleaseCheckoutCommand.model_validate(changed)


@pytest.mark.parametrize(
    ("method", "result", "valid"),
    [
        ("government_photo_id", "verified", True),
        ("government_photo_id", "documented_familiarity", False),
        ("documented_familiarity", "verified", False),
        ("documented_familiarity", "documented_familiarity", True),
    ],
)
def test_command_accepts_only_the_two_exact_verification_pairs(
    method: str, result: str, valid: bool
) -> None:
    values = _command().model_dump(mode="python")
    values.update(verification_method=method, verification_result=result)
    if valid:
        ReleaseCheckoutCommand.model_validate(values)
    else:
        with pytest.raises(ValidationError, match="verification method/result pair"):
            ReleaseCheckoutCommand.model_validate(values)


@pytest.mark.parametrize(
    ("policy", "method", "result"),
    [
        ("government_photo_id", "government_photo_id", "verified"),
        (
            "documented_familiarity",
            "documented_familiarity",
            "documented_familiarity",
        ),
        (
            "government_photo_id_or_documented_familiarity",
            "government_photo_id",
            "verified",
        ),
        (
            "government_photo_id_or_documented_familiarity",
            "documented_familiarity",
            "documented_familiarity",
        ),
    ],
)
def test_policy_validator_accepts_every_and_only_executable_lane(
    policy: str, method: str, result: str
) -> None:
    assert validate_release_checkout_verification(
        verification_policy_code=policy,
        verification_method=method,
        verification_result=result,
    ) == (method, result)


@pytest.mark.parametrize(
    ("policy", "method", "result", "code"),
    [
        (
            "government_photo_id",
            "documented_familiarity",
            "verified",
            ReleaseCheckoutContractErrorCode.VERIFICATION_PAIR_INVALID,
        ),
        (
            "government_photo_id",
            "documented_familiarity",
            "documented_familiarity",
            ReleaseCheckoutContractErrorCode.VERIFICATION_POLICY_MISMATCH,
        ),
        (
            "documented_familiarity",
            "government_photo_id",
            "verified",
            ReleaseCheckoutContractErrorCode.VERIFICATION_POLICY_MISMATCH,
        ),
        (
            "government_photo_id_and_secondary_check",
            "government_photo_id",
            "verified",
            ReleaseCheckoutContractErrorCode.VERIFICATION_POLICY_UNAVAILABLE,
        ),
    ],
)
def test_policy_validator_returns_only_bounded_failures(
    policy: str,
    method: str,
    result: str,
    code: ReleaseCheckoutContractErrorCode,
) -> None:
    with pytest.raises(ReleaseCheckoutContractError) as captured:
        validate_release_checkout_verification(
            verification_policy_code=policy,
            verification_method=method,
            verification_result=result,
        )
    assert captured.value.code == code
    message, action = ERROR_PRESENTATION[code.value]
    assert captured.value.product_error.model_dump() == {
        "schema_version": "release-checkout-error-v1",
        "code": code.value,
        "message": message,
        "recovery_action": action,
    }


def test_request_hash_has_fixed_canonical_golden_vector() -> None:
    expected_document = (
        '{"command_type":"attendance.release.checkout","intent":{'
        '"authorization_id":"00000000-0000-0000-0000-00000000000a",'
        '"authorization_version":11,'
        '"child_id":"00000000-0000-0000-0000-000000000002",'
        '"expected_attendance_day_id":"00000000-0000-0000-0000-000000000005",'
        '"expected_attendance_interval_id":"00000000-0000-0000-0000-000000000006",'
        '"expected_authority_revision":12,'
        '"expected_decision_policy_version":"release-context-v1",'
        '"expected_restriction_digest_sha256":"abababababababababababababababab'
        'abababababababababababababababab",'
        '"expected_room_id":"00000000-0000-0000-0000-000000000004",'
        '"expected_staff_shift_id":"00000000-0000-0000-0000-000000000007",'
        '"facility_id":"00000000-0000-0000-0000-000000000003",'
        '"recipient_person_id":"00000000-0000-0000-0000-000000000008",'
        '"recipient_person_version_id":"00000000-0000-0000-0000-000000000009",'
        '"requested_at":"2026-07-18T12:34:56.123456+00:00",'
        '"schema_version":"release-checkout-command-v1",'
        '"verification_method":"government_photo_id",'
        '"verification_result":"verified"},'
        '"target_scope":"00000000-0000-0000-0000-000000000002",'
        '"target_type":"attendance_release"}'
    )
    command = _command()
    assert canonical_release_checkout_request_document_bytes(command) == expected_document.encode()
    assert release_checkout_request_hash(command) == (
        "f2823ead1d7820b6bab5e74c38ad9db79e62bd1573bc5c835e2a442b79d42d4a"
    )
    assert json.loads(expected_document)["intent"].get("client_operation_id") is None


def test_hash_excludes_only_operation_identity_and_binds_every_other_field() -> None:
    baseline = _command()
    baseline_hash = release_checkout_request_hash(baseline)
    assert (
        release_checkout_request_hash(baseline.model_copy(update={"client_operation_id": _id(999)}))
        == baseline_hash
    )

    changes = {
        "requested_at": REQUESTED_AT + timedelta(microseconds=1),
        "child_id": _id(102),
        "facility_id": _id(103),
        "expected_room_id": _id(104),
        "expected_attendance_day_id": _id(105),
        "expected_attendance_interval_id": _id(106),
        "expected_staff_shift_id": _id(107),
        "recipient_person_id": _id(108),
        "recipient_person_version_id": _id(109),
        "authorization_id": _id(110),
        "authorization_version": 111,
        "expected_authority_revision": 112,
        "expected_restriction_digest_sha256": "cd" * 32,
        "verification_method": "documented_familiarity",
        "verification_result": "documented_familiarity",
    }
    for field_name, changed_value in changes.items():
        updated = baseline.model_copy(update={field_name: changed_value})
        assert release_checkout_request_hash(updated) != baseline_hash, field_name


def test_request_hash_is_normalized_to_utc_but_non_utc_input_is_rejected_by_schema() -> None:
    values = _command().model_dump(mode="python")
    values["requested_at"] = REQUESTED_AT.astimezone(timezone(timedelta(hours=-6)))
    with pytest.raises(ValidationError, match="timestamp must be UTC"):
        ReleaseCheckoutCommand.model_validate(values)


def test_success_response_is_minimum_necessary_strict_and_coherent() -> None:
    response = _response()
    validate_release_checkout_response(_command(), response)
    serialized = response.model_dump_json()
    for forbidden in (
        "family_id",
        "evidence_id",
        "evidence_digest",
        "government_id",
        "notes",
        "override_reason",
        "phone",
        "email",
    ):
        assert forbidden not in serialized.lower()

    changed = response.model_dump(mode="python")
    changed["resource"]["evidence_id"] = _id(90)
    with pytest.raises(ValidationError):
        ReleaseCheckoutResponse.model_validate(changed)


@pytest.mark.parametrize(
    ("receipt_field", "changed_value"),
    [
        ("organization_id", _id(91)),
        ("facility_id", _id(92)),
        ("client_operation_id", _id(93)),
        ("target_id", _id(94)),
        ("committed_at", COMMITTED_AT + timedelta(microseconds=1)),
    ],
)
def test_response_rejects_every_resource_receipt_echo_mismatch(
    receipt_field: str, changed_value
) -> None:
    receipt_overrides = {receipt_field: changed_value}
    if receipt_field == "target_id":
        receipt_overrides["action_route"] = f"/attendance/releases/{changed_value}"
    with pytest.raises(ValidationError, match="receipt does not echo"):
        _response(receipt_overrides=receipt_overrides)


def test_response_rejects_wrong_receipt_purpose_version_route_and_release_time() -> None:
    for field_name, value in (
        ("command_type", "attendance.check-out"),
        ("target_type", "child"),
        ("committed_version", 2),
    ):
        with pytest.raises(ValidationError):
            _response(receipt_overrides={field_name: value})
    with pytest.raises(ValidationError, match="action_route"):
        _response(receipt_overrides={"action_route": "/attendance"})
    with pytest.raises(ValidationError, match="checked_out_at"):
        _response(resource_overrides={"checked_out_at": COMMITTED_AT - timedelta(seconds=1)})


def test_requested_at_cannot_be_later_than_the_authoritative_release_time() -> None:
    future_observation = COMMITTED_AT + timedelta(days=30)
    command = _command(requested_at=future_observation)
    with pytest.raises(ValidationError, match="requested_at must not be later"):
        _response(command)


def test_public_wire_timestamps_are_exact_six_digit_utc_values() -> None:
    command = _command()
    assert json.loads(command.model_dump_json())["requested_at"] == ("2026-07-18T12:34:56.123456Z")
    response = json.loads(_response(command).model_dump_json())
    assert response["resource"]["requested_at"] == "2026-07-18T12:34:56.123456Z"
    assert response["resource"]["checked_out_at"] == "2026-07-18T12:35:01.987654Z"
    assert response["resource"]["committed_at"] == "2026-07-18T12:35:01.987654Z"
    assert response["receipt"]["committed_at"] == "2026-07-18T12:35:01.987654Z"


def test_visible_recipient_text_is_normalized_before_serialization() -> None:
    response = _response(
        resource_overrides={
            "recipient_display_name": "  Amal\n Noor   Ali  ",
            "recipient_relationship": "  Family   friend ",
        }
    )
    assert response.resource.recipient_display_name == "Amal Noor Ali"
    assert response.resource.recipient_relationship == "Family friend"


@pytest.mark.parametrize(
    ("resource_field", "changed_value"),
    [
        ("client_operation_id", _id(201)),
        ("request_hash", "01" * 32),
        ("child_id", _id(202)),
        ("facility_id", _id(203)),
        ("room_id", _id(204)),
        ("attendance_day_id", _id(205)),
        ("attendance_interval_id", _id(206)),
        ("staff_shift_id", _id(207)),
        ("recipient_person_id", _id(208)),
        ("recipient_person_version_id", _id(209)),
        ("authorization_id", _id(210)),
        ("authorization_version", 211),
        ("authority_revision", 212),
        ("restriction_digest_sha256", "ef" * 32),
        ("decision_policy_version", "not-release-context-v1"),
        ("verification_method", "documented_familiarity"),
        ("verification_result", "documented_familiarity"),
        ("requested_at", REQUESTED_AT + timedelta(microseconds=1)),
    ],
)
def test_command_response_comparison_rejects_every_nonmatching_echo(
    resource_field: str, changed_value
) -> None:
    command = _command()
    resource_overrides = {resource_field: changed_value}
    if resource_field == "verification_method":
        resource_overrides["verification_result"] = "documented_familiarity"
    if resource_field == "verification_result":
        resource_overrides["verification_method"] = "documented_familiarity"
    if resource_field == "decision_policy_version":
        # A literal mismatch is correctly rejected before the echo checker.
        with pytest.raises(ValidationError):
            _response(command, resource_overrides=resource_overrides)
        return
    response = _response(command, resource_overrides=resource_overrides)
    with pytest.raises(ReleaseCheckoutContractError) as captured:
        validate_release_checkout_response(command, response)
    assert captured.value.code == ReleaseCheckoutContractErrorCode.RESPONSE_MISMATCH


def test_all_bounded_error_presentations_are_exhaustive_and_immutable() -> None:
    assert {code.value for code in ReleaseCheckoutContractErrorCode} == set(ERROR_PRESENTATION)
    for code in ReleaseCheckoutContractErrorCode:
        error = ReleaseCheckoutContractError(code).product_error
        assert error.code == code.value
        changed = error.model_dump()
        changed["message"] = "Caller-authored explanation"
        with pytest.raises(ValidationError, match="bounded code"):
            ReleaseCheckoutErrorResponse.model_validate(changed)
