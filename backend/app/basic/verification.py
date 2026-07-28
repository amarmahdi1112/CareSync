"""Verification policy boundary for the Basic release.

The launch policy temporarily approves identities immediately.  Keeping that
decision here makes it explicit and replaceable when email delivery and daycare
licence review are introduced.  Verification challenges and raw tokens do not
belong on these domain records.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.basic.models import Facility, Organization, User

TEMPORARY_AUTO_APPROVAL = "temporary_auto_approval"


def apply_temporary_email_approval(user: User, *, decided_at: datetime | None = None) -> None:
    """Approve the user's current email under the temporary launch policy."""

    user.email_verified_at = decided_at or datetime.now(UTC)
    user.email_verification_method = TEMPORARY_AUTO_APPROVAL


def apply_temporary_daycare_approval(
    subject: Organization | Facility,
    *,
    decided_at: datetime | None = None,
) -> None:
    """Approve an organization or licensed facility under the launch policy."""

    subject.verification_status = "verified"
    subject.verified_at = decided_at or datetime.now(UTC)
    subject.verification_method = TEMPORARY_AUTO_APPROVAL
