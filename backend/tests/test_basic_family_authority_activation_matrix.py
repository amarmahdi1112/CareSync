"""Exhaustive positive-list tests for the A2 evidence activation matrix."""

from __future__ import annotations

from app.basic.family_authority_activation_matrix import (
    ACTIVATABLE_RELEASE_RULE_KINDS,
    CONSENT_DECISION_EVIDENCE_KIND,
    consent_signer_authority,
    person_must_have_guardian_source,
    release_grant_evidence_kind,
    release_rule_evidence_kind,
)

EVIDENCE_KINDS = {
    "identity_document",
    "custody_document",
    "court_order",
    "guardian_attestation",
    "signed_consent",
    "signed_release_delegation",
    "staff_witness",
    "other_document",
}
AUTHORITY_BASES = {
    "guardian_record",
    "reviewed_custody_evidence",
    "reviewed_delegation_evidence",
    "other_reviewed_authority",
}


def test_release_grant_matrix_is_an_exhaustive_positive_list() -> None:
    allowed = {
        ("guardian_record", "guardian_attestation"),
        ("reviewed_custody_evidence", "custody_document"),
        ("reviewed_delegation_evidence", "signed_release_delegation"),
    }
    for basis in AUTHORITY_BASES:
        configured_kind = release_grant_evidence_kind(basis)
        for evidence_kind in EVIDENCE_KINDS:
            assert (configured_kind == evidence_kind) == ((basis, evidence_kind) in allowed)
    assert person_must_have_guardian_source("guardian_record") is True
    assert person_must_have_guardian_source("reviewed_delegation_evidence") is True
    assert person_must_have_guardian_source("reviewed_custody_evidence") is False
    assert person_must_have_guardian_source("other_reviewed_authority") is False


def test_release_rule_matrix_rejects_every_unlisted_kind_and_rule() -> None:
    allowed = {
        ("guardian_record", "guardian_attestation"),
        ("reviewed_custody_evidence", "custody_document"),
    }
    for basis in AUTHORITY_BASES:
        configured_kind = release_rule_evidence_kind(basis)
        for evidence_kind in EVIDENCE_KINDS:
            assert (configured_kind == evidence_kind) == ((basis, evidence_kind) in allowed)
    assert {"deny", "manager_review"} == ACTIVATABLE_RELEASE_RULE_KINDS
    assert {
        "supervised_only",
        "named_recipient_only",
    }.isdisjoint(ACTIVATABLE_RELEASE_RULE_KINDS)


def test_consent_matrix_keeps_decision_and_signer_authority_separate() -> None:
    requirements = {
        "guardian_record": ("guardian_record", "guardian_attestation"),
        "legal_decision_maker": (
            "reviewed_custody_evidence",
            "custody_document",
        ),
        "specific_reviewed_authority": None,
    }
    for requirement, expected in requirements.items():
        configured = consent_signer_authority(requirement)
        assert configured == expected
        for basis in AUTHORITY_BASES:
            for evidence_kind in EVIDENCE_KINDS:
                assert (configured == (basis, evidence_kind)) == (
                    expected == (basis, evidence_kind)
                )
    assert CONSENT_DECISION_EVIDENCE_KIND == "signed_consent"
    assert CONSENT_DECISION_EVIDENCE_KIND not in {
        value[1] for value in requirements.values() if value is not None
    }
