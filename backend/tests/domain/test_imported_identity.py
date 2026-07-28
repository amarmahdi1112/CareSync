from datetime import date

from app.domain.scheduling.imported_identity import may_use_claim_only_identity


def test_unmatched_import_can_use_claim_only_identity() -> None:
    assert may_use_claim_only_identity(
        matched_child_id=None,
        claim_date_of_birth=None,
        matched_child_date_of_birth=None,
    )


def test_explicit_dob_contradiction_can_use_claim_only_identity() -> None:
    assert may_use_claim_only_identity(
        matched_child_id="child-1",
        claim_date_of_birth=date(2013, 11, 6),
        matched_child_date_of_birth=date(2014, 11, 6),
        matched_group_size=2,
        has_exact_dob_anchor=True,
    )


def test_consistent_or_unknown_dob_cannot_bypass_a_stored_match() -> None:
    assert not may_use_claim_only_identity(
        matched_child_id="child-1",
        claim_date_of_birth=date(2014, 11, 6),
        matched_child_date_of_birth=date(2014, 11, 6),
    )
    assert not may_use_claim_only_identity(
        matched_child_id="child-1",
        claim_date_of_birth=None,
        matched_child_date_of_birth=date(2014, 11, 6),
        matched_group_size=2,
        has_exact_dob_anchor=True,
    )
    assert not may_use_claim_only_identity(
        matched_child_id="child-1",
        claim_date_of_birth=date(2013, 11, 6),
        matched_child_date_of_birth=date(2014, 11, 6),
        matched_group_size=1,
        has_exact_dob_anchor=False,
    )
