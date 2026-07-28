"""Identity rules for imported claims used as synthetic schedule participants."""

from __future__ import annotations

from datetime import date
from uuid import UUID


def may_use_claim_only_identity(
    *,
    matched_child_id: UUID | str | None,
    claim_date_of_birth: date | None,
    matched_child_date_of_birth: date | None,
    matched_group_size: int = 1,
    has_exact_dob_anchor: bool = False,
) -> bool:
    """Allow unmatched rows or an anchored duplicate that contradicts its match.

    A lone mismatch can be stale or imprecise source data. It stays associated
    with its stored child. A duplicate group is splittable only when another
    source row positively anchors the child by exact DOB. Missing dates are not
    evidence of a conflict.
    """

    if matched_child_id is None:
        return True
    return (
        matched_group_size > 1
        and has_exact_dob_anchor
        and claim_date_of_birth is not None
        and matched_child_date_of_birth is not None
        and claim_date_of_birth != matched_child_date_of_birth
    )
