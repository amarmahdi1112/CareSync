"""Fail-closed schema gates for the 0029A family-authority API boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.basic.family_authority_schemas import (
    COMMAND_TARGET_TYPES,
    AuthorityEvidenceAssessmentResponse,
    AuthorityEvidenceInvalidateRequest,
    AuthorityEvidenceRecordRequest,
    AuthorityEvidenceRejectRequest,
    AuthorityEvidenceResponse,
    AuthorityEvidenceReviewRequest,
    AuthorityEvidenceSupersedeRequest,
    AuthorityPersonCreateRequest,
    AuthorityPersonReplaceRequest,
    AuthorityPersonResponse,
    AuthorityPersonRetireRequest,
    ChildConsentRecordRequest,
    ChildConsentWithdrawRequest,
    ChildFamilyAuthorityResponse,
    ConsentPolicyPublishRequest,
    EvidenceStorage,
    FamilyAuthorityCommandReceiptResponse,
    ReleaseAuthorizationGrantRequest,
    ReleaseAuthorizationRevokeRequest,
    ReleaseRuleCreateRequest,
    ReleaseRuleRevokeRequest,
)

NOW = datetime(2026, 7, 17, 18, tzinfo=UTC)
LATER = NOW + timedelta(days=30)
SHA256 = "a" * 64


def _person_facts(**overrides):
    values = {
        "first_name": "Amal",
        "middle_name": None,
        "last_name": "Noor",
        "preferred_name": None,
        "relationship_kind": "parent",
        "relationship_detail": None,
        "email": "amal@example.test",
        "primary_phone": "+1 780 555 0100",
    }
    values.update(overrides)
    return values


def _grantor():
    return {
        "person_id": uuid4(),
        "person_version_id": uuid4(),
        "authority_basis": "guardian_record",
        "basis_evidence_id": uuid4(),
        "basis_evidence_assessment_id": uuid4(),
    }


def _valid_payloads():
    return [
        (
            AuthorityPersonCreateRequest,
            {
                "client_operation_id": uuid4(),
                "source": {"kind": "manual"},
                "facts": _person_facts(),
            },
        ),
        (
            AuthorityPersonReplaceRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "facts": _person_facts(),
            },
        ),
        (
            AuthorityPersonRetireRequest,
            {"client_operation_id": uuid4(), "expected_version": 1},
        ),
        (
            AuthorityEvidenceRecordRequest,
            {
                "client_operation_id": uuid4(),
                "evidence_kind": "identity_document",
                "source_label": "Front desk review",
                "issued_at": NOW,
                "captured_at": NOW,
                "expires_at": LATER,
                "evidence_object_id": uuid4(),
            },
        ),
        (
            AuthorityEvidenceReviewRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "assessed_epistemic_status": "document_observed",
            },
        ),
        (
            AuthorityEvidenceRejectRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "reason_code": "unreadable",
                "confidential_note": None,
            },
        ),
        (
            AuthorityEvidenceInvalidateRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 2,
                "reason_code": "document_revoked",
                "confidential_note": None,
            },
        ),
        (
            AuthorityEvidenceSupersedeRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 2,
                "replacement_evidence_id": uuid4(),
            },
        ),
        (
            ReleaseAuthorizationGrantRequest,
            {
                "client_operation_id": uuid4(),
                "expected_authority_revision": 0,
                "recipient_person_id": uuid4(),
                "verification_policy_code": "government_photo_id",
                "grantor": _grantor(),
                "effective_from": NOW,
                "effective_until": LATER,
            },
        ),
        (
            ReleaseAuthorizationRevokeRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "expected_authority_revision": 1,
                "reason_code": "authority_withdrawn",
            },
        ),
        (
            ReleaseRuleCreateRequest,
            {
                "client_operation_id": uuid4(),
                "expected_authority_revision": 0,
                "rule_kind": "deny",
                "scope": {"kind": "all_recipients"},
                "directing_person": None,
                "authority_basis_code": "reviewed_custody_evidence",
                "basis_evidence_id": uuid4(),
                "basis_evidence_assessment_id": uuid4(),
                "confidential_reason": "Reviewed restriction evidence",
                "effective_from": NOW,
                "effective_until": LATER,
            },
        ),
        (
            ReleaseRuleRevokeRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "expected_authority_revision": 1,
                "reason_code": "superseded",
            },
        ),
        (
            ConsentPolicyPublishRequest,
            {
                "client_operation_id": uuid4(),
                "purpose_code": "off_site_activity",
                "version_number": 1,
                "title": "Off-site activity permission",
                "content_text": "I authorize this defined off-site activity.",
                "signer_authority_requirement": "guardian_record",
                "effective_from": NOW,
                "effective_until": LATER,
            },
        ),
        (
            ChildConsentRecordRequest,
            {
                "client_operation_id": uuid4(),
                "expected_authority_revision": 0,
                "purpose_code": "off_site_activity",
                "policy_version_id": uuid4(),
                "signer": {
                    "person_id": uuid4(),
                    "person_version_id": uuid4(),
                    "authority_basis": "guardian_record",
                    "authority_evidence_id": uuid4(),
                    "authority_evidence_assessment_id": uuid4(),
                },
                "evidence_id": uuid4(),
                "evidence_assessment_id": uuid4(),
                "decision": "granted",
                "scope": {"kind": "policy"},
                "effective_from": NOW,
                "effective_until": LATER,
            },
        ),
        (
            ChildConsentWithdrawRequest,
            {
                "client_operation_id": uuid4(),
                "expected_version": 1,
                "expected_authority_revision": 1,
                "reason_code": "signer_withdrew",
            },
        ),
    ]


def _payload_for(schema):
    return dict(next(payload for candidate, payload in _valid_payloads() if candidate is schema))


@pytest.mark.parametrize(("schema", "payload"), _valid_payloads())
def test_every_mutation_request_forbids_unknown_fields(schema, payload):
    schema.model_validate(payload)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        schema.model_validate({**payload, "unexpected": "must fail"})


def test_command_vocabulary_and_target_mapping_are_exact():
    assert COMMAND_TARGET_TYPES == {
        "family.authority.evidence_object.upload": "authority_evidence_object",
        "family.authority.evidence_object.scan": "authority_evidence_object",
        "family.authority.person.create": "authority_person",
        "family.authority.person.replace": "authority_person",
        "family.authority.person.retire": "authority_person",
        "family.authority.evidence.record": "authority_evidence",
        "family.authority.evidence.review": "authority_evidence",
        "family.authority.evidence.reject": "authority_evidence",
        "family.authority.evidence.invalidate": "authority_evidence",
        "family.authority.evidence.supersede": "authority_evidence",
        "child.release.authorization.grant": "release_authorization",
        "child.release.authorization.revoke": "release_authorization",
        "child.release.rule.create": "release_rule",
        "child.release.rule.revoke": "release_rule",
        "organization.consent.policy.publish": "consent",
        "child.consent.record": "consent",
        "child.consent.withdraw": "consent",
    }
    assert all("_" not in command.split(".")[0] for command in COMMAND_TARGET_TYPES)


def test_person_strings_are_trimmed_and_relationship_tuple_is_exact():
    parsed = AuthorityPersonCreateRequest.model_validate(
        {
            "client_operation_id": uuid4(),
            "source": {"kind": "guardian", "guardian_id": uuid4()},
            "facts": _person_facts(first_name="  Amal  ", last_name="  Noor "),
        }
    )
    assert parsed.facts.first_name == "Amal"
    assert parsed.facts.last_name == "Noor"

    with pytest.raises(ValidationError, match="relationship_detail is required"):
        AuthorityPersonCreateRequest.model_validate(
            {
                "client_operation_id": uuid4(),
                "source": {"kind": "manual"},
                "facts": _person_facts(
                    relationship_kind="other",
                    relationship_detail=None,
                ),
            }
        )
    with pytest.raises(ValidationError, match="only allowed for other"):
        AuthorityPersonCreateRequest.model_validate(
            {
                "client_operation_id": uuid4(),
                "source": {"kind": "manual"},
                "facts": _person_facts(relationship_detail="not allowed"),
            }
        )
    with pytest.raises(ValidationError):
        AuthorityPersonCreateRequest.model_validate(
            {
                "client_operation_id": uuid4(),
                "source": {"kind": "manual"},
                "facts": _person_facts(first_name="   "),
            }
        )


@pytest.mark.parametrize(
    "source",
    [
        {"kind": "manual", "guardian_id": uuid4()},
        {"kind": "guardian"},
        {"kind": "guardian", "guardian_id": uuid4(), "emergency_contact_id": uuid4()},
        {"kind": "emergency_contact"},
        {"kind": "legacy", "guardian_id": uuid4()},
    ],
)
def test_person_source_is_one_exact_tagged_tuple(source):
    with pytest.raises(ValidationError):
        AuthorityPersonCreateRequest.model_validate(
            {
                "client_operation_id": uuid4(),
                "source": source,
                "facts": _person_facts(),
            }
        )


@pytest.mark.parametrize(
    "invalid_window",
    [
        (NOW.replace(tzinfo=None), LATER),
        (NOW.astimezone(timezone(timedelta(hours=-6))), LATER),
        (NOW, NOW),
        (LATER, NOW),
    ],
)
def test_effective_windows_require_utc_and_positive_half_open_range(invalid_window):
    start, end = invalid_window
    with pytest.raises(ValidationError):
        ReleaseAuthorizationGrantRequest.model_validate(
            {
                "client_operation_id": uuid4(),
                "expected_authority_revision": 0,
                "recipient_person_id": uuid4(),
                "verification_policy_code": "government_photo_id",
                "grantor": _grantor(),
                "effective_from": start,
                "effective_until": end,
            }
        )


def test_utc_strings_normalize_to_utc_and_nonzero_offsets_fail():
    payload = _payload_for(ReleaseAuthorizationGrantRequest)
    payload["effective_from"] = "2026-07-17T18:00:00Z"
    payload["effective_until"] = "2026-08-17T18:00:00+00:00"
    parsed = ReleaseAuthorizationGrantRequest.model_validate(payload)
    assert parsed.effective_from.tzinfo is UTC
    assert parsed.effective_until.tzinfo is UTC

    payload["effective_from"] = "2026-07-17T12:00:00-06:00"
    with pytest.raises(ValidationError, match="timestamp must be UTC"):
        ReleaseAuthorizationGrantRequest.model_validate(payload)


def test_evidence_storage_is_all_or_none_lowercase_and_opaque():
    storage = EvidenceStorage.model_validate(
        {
            "storage_reference": "authority/01JABC/document-1",
            "media_type": "application/pdf",
            "byte_size": 12345,
            "content_sha256": SHA256,
        }
    )
    assert storage.storage_reference == "authority/01JABC/document-1"

    for invalid_storage in (
        {"storage_reference": "authority/only"},
        {
            "storage_reference": "https://example.test/file.pdf",
            "media_type": "application/pdf",
            "byte_size": 1,
            "content_sha256": SHA256,
        },
        {
            "storage_reference": "authority/../file.pdf",
            "media_type": "application/pdf",
            "byte_size": 1,
            "content_sha256": SHA256,
        },
        {
            "storage_reference": "authority/file.pdf",
            "media_type": "Application/PDF",
            "byte_size": 1,
            "content_sha256": SHA256,
        },
        {
            "storage_reference": "authority/file.pdf",
            "media_type": "application/pdf",
            "byte_size": 1,
            "content_sha256": "A" * 64,
        },
        {
            "storage_reference": "authority/file.pdf/",
            "media_type": "application/pdf",
            "byte_size": 1,
            "content_sha256": SHA256,
        },
        {
            "storage_reference": "authority/file.pdf",
            "media_type": "application/pdf",
            "byte_size": 52_428_801,
            "content_sha256": SHA256,
        },
    ):
        with pytest.raises(ValidationError):
            EvidenceStorage.model_validate(invalid_storage)


def test_numeric_storage_boundaries_fail_structurally_before_database_use():
    policy = _payload_for(ConsentPolicyPublishRequest)
    policy["version_number"] = 2_147_483_648
    with pytest.raises(ValidationError):
        ConsentPolicyPublishRequest.model_validate(policy)


def test_authority_person_response_requires_the_exact_open_current_version():
    person_id = uuid4()
    base = {
        "id": person_id,
        "organization_id": uuid4(),
        "family_id": uuid4(),
        "version": 1,
        "status": "active",
        "source": {"kind": "manual"},
        "current_version": {
            "id": uuid4(),
            "person_id": person_id,
            "version_number": 1,
            "facts": _person_facts(),
            "closed_at": None,
            "created_at": NOW,
        },
        "retired_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    AuthorityPersonResponse.model_validate(base)

    for current_version_change in (
        {"person_id": uuid4()},
        {"version_number": 2},
        {"closed_at": NOW},
    ):
        current_version = {**base["current_version"], **current_version_change}
        with pytest.raises(ValidationError, match="exact and open"):
            AuthorityPersonResponse.model_validate(
                {**base, "current_version": current_version}
            )


def test_evidence_record_rejects_naive_times_and_invalid_expiry():
    payload = _payload_for(AuthorityEvidenceRecordRequest)
    payload["captured_at"] = NOW.replace(tzinfo=None)
    with pytest.raises(ValidationError, match="UTC offset"):
        AuthorityEvidenceRecordRequest.model_validate(payload)

    payload["captured_at"] = NOW
    payload["expires_at"] = NOW
    with pytest.raises(ValidationError, match="later than issued_at"):
        AuthorityEvidenceRecordRequest.model_validate(payload)


def test_evidence_record_rejects_reserved_storage_and_client_review_fields():
    payload = _payload_for(AuthorityEvidenceRecordRequest)
    for field, value in (
        ("storage", None),
        ("review_status", "reviewed"),
        ("epistemic_status", "issuer_verified"),
        ("reviewed_by_user_id", uuid4()),
    ):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            AuthorityEvidenceRecordRequest.model_validate({**payload, field: value})


def test_evidence_assessment_commands_are_state_specific_and_exact():
    review = _payload_for(AuthorityEvidenceReviewRequest)
    assert AuthorityEvidenceReviewRequest.model_validate(review).expected_version == 1
    for forbidden in (
        {"reason_code": "unreadable"},
        {"confidential_note": "not a review field"},
        {"assessed_epistemic_status": "issuer_verified"},
    ):
        with pytest.raises(ValidationError):
            AuthorityEvidenceReviewRequest.model_validate({**review, **forbidden})
    assert (
        AuthorityEvidenceReviewRequest.model_validate(
            {**review, "expected_version": 2}
        ).expected_version
        == 2
    )

    reject = _payload_for(AuthorityEvidenceRejectRequest)
    AuthorityEvidenceRejectRequest.model_validate(reject)
    with pytest.raises(ValidationError, match="required exactly"):
        AuthorityEvidenceRejectRequest.model_validate(
            {**reject, "reason_code": "other", "confidential_note": None}
        )
    with pytest.raises(ValidationError):
        AuthorityEvidenceRejectRequest.model_validate(
            {**reject, "reason_code": "document_revoked"}
        )

    invalidate = _payload_for(AuthorityEvidenceInvalidateRequest)
    AuthorityEvidenceInvalidateRequest.model_validate(invalidate)
    with pytest.raises(ValidationError):
        AuthorityEvidenceInvalidateRequest.model_validate(
            {**invalidate, "reason_code": "unreadable"}
        )
    with pytest.raises(ValidationError, match="required exactly"):
        AuthorityEvidenceInvalidateRequest.model_validate(
            {**invalidate, "reason_code": "other", "confidential_note": None}
        )

    supersede = _payload_for(AuthorityEvidenceSupersedeRequest)
    assert AuthorityEvidenceSupersedeRequest.model_validate(supersede).expected_version == 2
    assert (
        AuthorityEvidenceSupersedeRequest.model_validate(
            {**supersede, "expected_version": 1}
        ).expected_version
        == 1
    )
    with pytest.raises(ValidationError):
        AuthorityEvidenceSupersedeRequest.model_validate(
            {**supersede, "reason_code": "superseded"}
        )


def test_downstream_commands_require_exact_review_assessment_ids():
    grant = _payload_for(ReleaseAuthorizationGrantRequest)
    grant["grantor"].pop("basis_evidence_assessment_id")
    with pytest.raises(ValidationError):
        ReleaseAuthorizationGrantRequest.model_validate(grant)

    rule = _payload_for(ReleaseRuleCreateRequest)
    rule.pop("basis_evidence_assessment_id")
    with pytest.raises(ValidationError):
        ReleaseRuleCreateRequest.model_validate(rule)

    consent = _payload_for(ChildConsentRecordRequest)
    consent.pop("evidence_assessment_id")
    with pytest.raises(ValidationError):
        ChildConsentRecordRequest.model_validate(consent)


def test_evidence_response_requires_exact_current_immutable_assessment():
    evidence_id = uuid4()
    assessment = {
        "id": uuid4(),
        "evidence_id": evidence_id,
        "version_number": 2,
        "decision": "reviewed",
        "assessed_epistemic_status": "reported",
        "reason_code": None,
        "confidential_note": None,
        "superseded_by_evidence_id": None,
        "actor_user_id": uuid4(),
        "created_at": NOW,
    }
    AuthorityEvidenceAssessmentResponse.model_validate(assessment)
    base = {
        "id": evidence_id,
        "organization_id": uuid4(),
        "family_id": uuid4(),
        "evidence_kind": "guardian_attestation",
        "source_label": "Administrator review",
        "recorded_by_user_id": uuid4(),
        "storage": None,
        "issued_at": None,
        "captured_at": NOW,
        "expires_at": None,
        "created_at": NOW,
        "version": 2,
        "lifecycle_status": "reviewed",
        "effective_status": "reviewed",
        "valid_now": True,
        "evaluated_at": NOW,
        "current_assessment": assessment,
    }
    AuthorityEvidenceResponse.model_validate(base)
    with pytest.raises(ValidationError, match="current evidence assessment must be exact"):
        AuthorityEvidenceResponse.model_validate(
            {**base, "current_assessment": {**assessment, "evidence_id": uuid4()}}
        )
    with pytest.raises(ValidationError, match="valid_now must match"):
        AuthorityEvidenceResponse.model_validate({**base, "valid_now": False})

    expired = {
        **base,
        "expires_at": NOW,
        "effective_status": "expired",
        "valid_now": False,
    }
    AuthorityEvidenceResponse.model_validate(expired)
    with pytest.raises(ValidationError, match="effective status"):
        AuthorityEvidenceResponse.model_validate(
            {**expired, "expires_at": LATER}
        )


def test_rule_and_consent_scopes_reject_ambiguous_shapes():
    rule_payload = _payload_for(ReleaseRuleCreateRequest)
    rule_payload["rule_kind"] = "named_recipient_only"
    with pytest.raises(ValidationError, match="specific_person"):
        ReleaseRuleCreateRequest.model_validate(rule_payload)

    rule_payload["scope"] = {"kind": "specific_person", "person_id": uuid4()}
    ReleaseRuleCreateRequest.model_validate(rule_payload)
    rule_payload["scope"] = {
        "kind": "specific_person",
        "person_id": uuid4(),
        "unused_person_id": uuid4(),
    }
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ReleaseRuleCreateRequest.model_validate(rule_payload)

    consent_payload = _payload_for(ChildConsentRecordRequest)
    consent_payload["scope"] = {"kind": "policy", "facility_id": uuid4()}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ChildConsentRecordRequest.model_validate(consent_payload)


def test_first_child_mutation_accepts_zero_but_transitions_require_positive_revision():
    grant_payload = _payload_for(ReleaseAuthorizationGrantRequest)
    assert (
        ReleaseAuthorizationGrantRequest.model_validate(grant_payload).expected_authority_revision
        == 0
    )

    revoke_payload = _payload_for(ReleaseAuthorizationRevokeRequest)
    revoke_payload["expected_authority_revision"] = 0
    with pytest.raises(ValidationError):
        ReleaseAuthorizationRevokeRequest.model_validate(revoke_payload)


def _receipt(**overrides):
    values = {
        "organization_id": uuid4(),
        "client_operation_id": uuid4(),
        "command_type": "child.release.rule.create",
        "target_type": "release_rule",
        "target_id": uuid4(),
        "committed_version": 1,
        "committed_at": NOW,
        "facility_id": None,
        "action_route": f"/children/{uuid4()}/authority",
    }
    values.update(overrides)
    return values


def test_receipt_is_minimum_exact_and_command_target_bound():
    parsed = FamilyAuthorityCommandReceiptResponse.model_validate(_receipt())
    assert parsed.target_type == "release_rule"

    with pytest.raises(ValidationError, match="target_type does not match"):
        FamilyAuthorityCommandReceiptResponse.model_validate(
            _receipt(target_type="authority_person")
        )
    with pytest.raises(ValidationError):
        FamilyAuthorityCommandReceiptResponse.model_validate(
            _receipt(command_type="child_release_rule_create")
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        FamilyAuthorityCommandReceiptResponse.model_validate(
            _receipt(confidential_reason="must never be in a receipt")
        )


@pytest.mark.parametrize(
    "unsafe_route",
    [
        "https://example.test/children/1",
        "//example.test/children/1",
        "/children/../secrets",
        "/children/1#private",
        "/children\\1",
    ],
)
def test_receipt_action_route_is_local_and_non_traversing(unsafe_route):
    with pytest.raises(ValidationError):
        FamilyAuthorityCommandReceiptResponse.model_validate(
            _receipt(action_route=unsafe_route)
        )


def test_receipt_schema_has_no_confidential_or_arbitrary_outcome_fields():
    properties = set(FamilyAuthorityCommandReceiptResponse.model_json_schema()["properties"])
    assert properties == {
        "organization_id",
        "client_operation_id",
        "command_type",
        "target_type",
        "target_id",
        "committed_version",
        "committed_at",
        "facility_id",
        "action_route",
    }
    assert properties.isdisjoint(
        {
            "outcome",
            "confidential_reason",
            "source_label",
            "storage_reference",
            "content_sha256",
            "first_name",
            "last_name",
            "email",
            "primary_phone",
        }
    )


def test_missing_authority_head_projects_only_as_unreviewed_revision_zero():
    common = {
        "child_id": uuid4(),
        "release_authorizations": [],
        "release_rules": [],
        "consent_decisions": [],
    }
    ChildFamilyAuthorityResponse.model_validate(
        {**common, "reviewed": False, "authority_revision": 0}
    )
    ChildFamilyAuthorityResponse.model_validate(
        {**common, "reviewed": True, "authority_revision": 1}
    )
    with pytest.raises(ValidationError, match="reviewed must match"):
        ChildFamilyAuthorityResponse.model_validate(
            {**common, "reviewed": True, "authority_revision": 0}
        )
