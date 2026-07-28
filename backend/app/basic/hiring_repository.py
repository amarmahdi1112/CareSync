"""Tenant-scoped persistence helpers for the canonical hiring spine."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.api.basic.dependencies import BasicContext
from app.basic.models import (
    AtsApplication,
    AtsCandidate,
    AtsCandidateInvitation,
    AtsEvent,
    AtsJob,
    AtsOffer,
)


def record_hiring_event(
    session,
    context: BasicContext,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    *,
    reason: str | None = None,
    before=None,
    after=None,
) -> None:
    """Append one tenant- and actor-bound event to the hiring outbox."""

    session.add(
        AtsEvent(
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            before=before,
            after=after,
        )
    )


def get_hiring_job(
    session,
    organization_id: UUID,
    job_id: UUID,
    *,
    lock: bool = False,
) -> AtsJob:
    statement = select(AtsJob).where(
        AtsJob.organization_id == organization_id,
        AtsJob.id == job_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return value


def get_hiring_application(
    session,
    organization_id: UUID,
    application_id: UUID,
    *,
    lock: bool = False,
) -> AtsApplication:
    statement = select(AtsApplication).where(
        AtsApplication.organization_id == organization_id,
        AtsApplication.id == application_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return value


def get_hiring_offer(
    session,
    organization_id: UUID,
    offer_id: UUID,
    *,
    lock: bool = False,
) -> AtsOffer:
    statement = select(AtsOffer).where(
        AtsOffer.organization_id == organization_id,
        AtsOffer.id == offer_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    return value


def require_hiring_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Record changed; reload and retry",
        )


@dataclass(frozen=True, slots=True)
class CanonicalHiringCutoverReport:
    """Read-only facts that must be empty before legacy route removal."""

    pending_unclaimed_invitations: int
    private_invitation_applications: int
    draft_offers: int

    @property
    def ready(self) -> bool:
        return not any(
            (
                self.pending_unclaimed_invitations,
                self.private_invitation_applications,
                self.draft_offers,
            )
        )


class CanonicalHiringCutoverBlocked(RuntimeError):
    """Raised when retained state still requires a retired hiring command."""


def inspect_canonical_hiring_cutover(session) -> CanonicalHiringCutoverReport:
    """Return deterministic, read-only cutover blocker counts.

    Invitations without an accepted or revoked marker are treated as pending
    even after expiry. That fail-closed interpretation prevents an orphaned
    invitation from becoming unreachable after the legacy surface is removed.
    """

    pending_unclaimed_invitations = session.scalar(
        select(func.count())
        .select_from(AtsCandidateInvitation)
        .join(
            AtsApplication,
            (AtsApplication.organization_id == AtsCandidateInvitation.organization_id)
            & (AtsApplication.id == AtsCandidateInvitation.application_id),
        )
        .join(
            AtsCandidate,
            (AtsCandidate.organization_id == AtsApplication.organization_id)
            & (AtsCandidate.id == AtsApplication.candidate_id),
        )
        .where(
            AtsCandidateInvitation.accepted_at.is_(None),
            AtsCandidateInvitation.revoked_at.is_(None),
            AtsCandidate.claimed_user_id.is_(None),
        )
    )
    private_invitation_applications = session.scalar(
        select(func.count())
        .select_from(AtsApplication)
        .where(AtsApplication.source == "private_invitation")
    )
    draft_offers = session.scalar(
        select(func.count()).select_from(AtsOffer).where(AtsOffer.status == "draft")
    )
    return CanonicalHiringCutoverReport(
        pending_unclaimed_invitations=int(pending_unclaimed_invitations or 0),
        private_invitation_applications=int(private_invitation_applications or 0),
        draft_offers=int(draft_offers or 0),
    )


def assert_canonical_hiring_cutover_ready(session) -> CanonicalHiringCutoverReport:
    """Fail closed unless every retired-flow blocker is absent."""

    report = inspect_canonical_hiring_cutover(session)
    if not report.ready:
        raise CanonicalHiringCutoverBlocked(
            "Canonical hiring cutover blocked: "
            f"pending_unclaimed_invitations={report.pending_unclaimed_invitations}, "
            f"private_invitation_applications={report.private_invitation_applications}, "
            f"draft_offers={report.draft_offers}"
        )
    return report
