"""Fail-closed verified-release capability and legacy-write closure.

PostgreSQL revision 0029D deliberately removes direct runtime-role access to
the immutable facility activation table.  The application therefore reads an
activation only through the narrow, identity-bound SECURITY DEFINER
projection.  SQLite retains a direct read solely for the portable 0029C
contract suite; it never advertises a production verified-release runtime.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.basic.family_release_checkout_repository import (
    ReleaseCheckoutRepositoryError,
    postgres_release_checkout_activation_enabled,
)
from app.basic.models import FacilityReleaseCheckoutActivation

VERIFIED_RELEASE_ACTIVATION_POLICY = "normal_verified_release_v1"
_REQUIRED_PERMISSIONS = frozenset(
    {"attendance:record", "release:read", "release:checkout"}
)


@dataclass(frozen=True)
class VerifiedReleaseCapability:
    """Minimum authenticated bootstrap projection for one assigned facility."""

    runtime_available: bool
    facility_activated: bool
    staff_eligible: bool
    legacy_checkout_allowed: bool
    policy_version: str | None

    def as_dict(self) -> dict[str, bool | str | None]:
        return {
            "runtime_available": self.runtime_available,
            "facility_activated": self.facility_activated,
            "staff_eligible": self.staff_eligible,
            "legacy_checkout_allowed": self.legacy_checkout_allowed,
            "policy_version": self.policy_version,
        }


def _is_postgresql(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _portable_activation_enabled(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
) -> bool:
    """Read the portable 0029C source only on a non-PostgreSQL test database."""

    return (
        session.scalar(
            select(FacilityReleaseCheckoutActivation.id).where(
                FacilityReleaseCheckoutActivation.organization_id == organization_id,
                FacilityReleaseCheckoutActivation.facility_id == facility_id,
                FacilityReleaseCheckoutActivation.activation_policy_version
                == VERIFIED_RELEASE_ACTIVATION_POLICY,
            )
        )
        is not None
    )


def _postgres_activation_enabled(session: Session, *, facility_id: UUID) -> bool:
    try:
        return postgres_release_checkout_activation_enabled(
            session,
            facility_id=facility_id,
        )
    except ReleaseCheckoutRepositoryError:
        # The caller must never interpret a broken/partial projection as an
        # inactive facility and fall back to the legacy checkout mutation.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_authority_release_checkout_unavailable"},
        ) from None


def verified_release_capability(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    permissions: Iterable[str],
    foundation_present: bool,
    runtime_enabled: bool,
) -> VerifiedReleaseCapability:
    """Return a user-scoped capability without weakening the database boundary."""

    staff_eligible = _REQUIRED_PERMISSIONS.issubset(set(permissions))
    if not foundation_present:
        return VerifiedReleaseCapability(False, False, staff_eligible, True, None)

    if not _is_postgresql(session):
        # SQLite proves the 0029C closure contract, but cannot safely run the
        # PostgreSQL-only 0029D writer.  Preserve its portable activation truth
        # so the client still never offers a forbidden legacy checkout.
        activated = _portable_activation_enabled(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
        )
        return VerifiedReleaseCapability(
            False,
            activated,
            staff_eligible,
            not activated,
            VERIFIED_RELEASE_ACTIVATION_POLICY if activated else None,
        )

    if not runtime_enabled:
        # C may contain an activation that the restricted runtime role cannot
        # read.  Report the mode as unavailable and mirror the mutation
        # boundary by refusing to authorize a legacy fallback.
        return VerifiedReleaseCapability(False, False, staff_eligible, False, None)

    activated = _postgres_activation_enabled(session, facility_id=facility_id)
    return VerifiedReleaseCapability(
        runtime_available=True,
        facility_activated=activated,
        staff_eligible=staff_eligible,
        legacy_checkout_allowed=not activated,
        policy_version=VERIFIED_RELEASE_ACTIVATION_POLICY if activated else None,
    )


def facility_requires_verified_release_checkout(
    session: Session,
    *,
    organization_id: UUID,
    facility_id: UUID,
    foundation_present: bool,
    runtime_enabled: bool,
) -> bool:
    """Decide whether a legacy close must be rejected before any write.

    On PostgreSQL, a partial C/D installation is deliberately treated as
    requiring the verified path.  Once D is complete, its projection returns
    pure facility activation truth for the authenticated organization actor;
    checkout eligibility remains a separate service/API concern.
    """

    if not foundation_present:
        return False
    if not _is_postgresql(session):
        return _portable_activation_enabled(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
        )
    if not runtime_enabled:
        return True
    return _postgres_activation_enabled(session, facility_id=facility_id)
