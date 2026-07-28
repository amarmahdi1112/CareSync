"""Fail-closed evidence activation rules for the 0029A2 authority commands.

Reviewing an evidence asset is intentionally not enough to make it an
authority source.  These pure helpers are the single service-layer vocabulary
for the narrow positive lanes approved for A2; every unlisted combination is
non-activating.
"""

from __future__ import annotations

from typing import Literal

ReleaseAuthorityBasis = Literal[
    "guardian_record",
    "reviewed_custody_evidence",
    "reviewed_delegation_evidence",
    "other_reviewed_authority",
]
ConsentSignerRequirement = Literal[
    "guardian_record",
    "legal_decision_maker",
    "specific_reviewed_authority",
]

RELEASE_GRANT_EVIDENCE_BY_BASIS: dict[str, str] = {
    "guardian_record": "guardian_attestation",
    "reviewed_custody_evidence": "custody_document",
    "reviewed_delegation_evidence": "signed_release_delegation",
}

RELEASE_RULE_EVIDENCE_BY_BASIS: dict[str, str] = {
    "guardian_record": "guardian_attestation",
    "reviewed_custody_evidence": "custody_document",
}

CONSENT_SIGNER_AUTHORITY: dict[str, tuple[str, str]] = {
    "guardian_record": ("guardian_record", "guardian_attestation"),
    "legal_decision_maker": (
        "reviewed_custody_evidence",
        "custody_document",
    ),
}

CONSENT_DECISION_EVIDENCE_KIND = "signed_consent"
ACTIVATABLE_RELEASE_RULE_KINDS = frozenset({"deny", "manager_review"})


def release_grant_evidence_kind(authority_basis: str) -> str | None:
    """Return the only evidence kind that may activate a release grant basis."""

    return RELEASE_GRANT_EVIDENCE_BY_BASIS.get(authority_basis)


def release_rule_evidence_kind(authority_basis: str) -> str | None:
    """Return the only evidence kind that may activate a release-rule basis."""

    return RELEASE_RULE_EVIDENCE_BY_BASIS.get(authority_basis)


def consent_signer_authority(
    requirement: str,
) -> tuple[str, str] | None:
    """Return the exact signer basis and evidence kind for one policy lane."""

    return CONSENT_SIGNER_AUTHORITY.get(requirement)


def person_must_have_guardian_source(authority_basis: str) -> bool:
    """Guardians author guardian and delegation lanes; delegates cannot re-delegate."""

    return authority_basis in {"guardian_record", "reviewed_delegation_evidence"}
