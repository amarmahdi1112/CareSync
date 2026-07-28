"""Frontend-facing hiring contract backed by the tenant-safe ATS domain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.basic.ats import provision_accepted_candidate
from app.api.basic.common import commit_in_context, ensure_writable, flush_or_conflict
from app.api.basic.dependencies import BasicContextDependency, require_permission
from app.api.dependencies import SessionDependency
from app.basic.hiring_repository import (
    get_hiring_application as _application,
)
from app.basic.hiring_repository import (
    get_hiring_job as _job,
)
from app.basic.hiring_repository import (
    get_hiring_offer as _offer,
)
from app.basic.hiring_repository import (
    record_hiring_event as _event,
)
from app.basic.models import AtsApplication, AtsCandidate, AtsCandidateInvitation, AtsJob, AtsOffer
from app.basic.security import create_one_time_token, normalize_email


def reject_0030_legacy_hiring_mutation(request: Request) -> None:
    if request.method != "GET" and bool(
        getattr(request.app.state, "staff_screening_pathways_enabled", False)
    ):
        raise HTTPException(
            409,
            detail={
                "code": "legacy_hiring_mutation_disabled",
                "message": "Use the consent-bound /ats and /marketplace 0030 workflow",
            },
        )


router = APIRouter(
    prefix="/hiring",
    tags=["basic hiring"],
    dependencies=[Depends(reject_0030_legacy_hiring_mutation)],
)
read = require_permission("ats:read")
manage = require_permission("ats:manage")
hire = require_permission("ats:hire")


class ListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=180)
    location: str = Field(min_length=1, max_length=255)
    employment_type: str = Field(min_length=1, max_length=50)
    summary: str = Field(min_length=1, max_length=20000)
    openings: int = Field(ge=1, le=1000)


class ListingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    message: str | None = Field(default=None, max_length=5000)


class StageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str


class OfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position_title: str = Field(min_length=1, max_length=180)
    hourly_rate: Decimal = Field(gt=0, decimal_places=2, max_digits=10)
    start_date: datetime | None = None
    notes: str = Field(default="", max_length=30000)


class HireInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offer_id: UUID
    reason: str = Field(
        default="Offer accepted; begin controlled staff onboarding handoff.",
        min_length=3,
        max_length=2000,
    )


def listing_row(job: AtsJob, applicant_count: int = 0) -> dict:
    return {
        "id": job.id,
        "organization_id": job.organization_id,
        "title": job.title,
        "location": job.location or "Not specified",
        "employment_type": job.employment_type,
        "status": job.status,
        "summary": job.description,
        "openings": job.openings,
        "applicant_count": applicant_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def candidate_row(application: AtsApplication, candidate: AtsCandidate, invited_at=None) -> dict:
    stage = "declined" if application.status in {"rejected", "withdrawn"} else application.status
    return {
        "id": application.id,
        "organization_id": application.organization_id,
        "listing_id": application.job_id,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "email": candidate.email,
        "stage": stage,
        "source": "private_invitation",
        "invited_at": invited_at or application.created_at,
        "updated_at": application.updated_at,
    }


def offer_row(offer: AtsOffer) -> dict:
    return {
        "id": offer.id,
        "version": offer.version,
        "status": offer.status,
        "position_title": offer.position_title,
        "hourly_rate": float(offer.hourly_rate or 0),
        "start_date": offer.start_date,
        "notes": offer.notes or offer.terms,
        "created_at": offer.created_at,
    }


@router.get("/workspace")
def workspace(context: BasicContextDependency, session: SessionDependency):
    read(context)
    org = context.organization.id
    jobs = list(
        session.scalars(
            select(AtsJob).where(AtsJob.organization_id == org).order_by(AtsJob.created_at.desc())
        )
    )
    counts = dict(
        session.execute(
            select(AtsApplication.job_id, func.count())
            .where(AtsApplication.organization_id == org)
            .group_by(AtsApplication.job_id)
        )
    )
    app_rows = list(
        session.execute(
            select(AtsApplication, AtsCandidate)
            .join(
                AtsCandidate,
                (AtsCandidate.organization_id == AtsApplication.organization_id)
                & (AtsCandidate.id == AtsApplication.candidate_id),
            )
            .where(AtsApplication.organization_id == org)
            .order_by(AtsApplication.created_at.desc())
        )
    )
    applications = [row[0] for row in app_rows]
    offers = list(
        session.scalars(
            select(AtsOffer)
            .where(AtsOffer.organization_id == org)
            .order_by(AtsOffer.application_id, AtsOffer.version.desc())
        )
    )
    grouped = []
    for application in applications:
        grouped.append(
            {
                "candidate_id": application.id,
                "versions": [
                    offer_row(item) for item in offers if item.application_id == application.id
                ],
            }
        )
    return {
        "organization_id": org,
        "generated_at": datetime.now(UTC),
        "listings": [listing_row(job, counts.get(job.id, 0)) for job in jobs],
        "candidates": [candidate_row(app, candidate) for app, candidate in app_rows],
        "offers": grouped,
    }


@router.post("/listings", status_code=201)
def create_listing(
    payload: ListingInput,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    job = AtsJob(
        organization_id=context.organization.id,
        title=payload.title.strip(),
        location=payload.location.strip(),
        employment_type=payload.employment_type.strip(),
        description=payload.summary.strip(),
        openings=payload.openings,
        created_by_user_id=context.user.id,
    )
    session.add(job)
    flush_or_conflict(session)
    _event(session, context, "job.created", "job", job.id, after={"status": "draft"})
    commit_in_context(session, context)
    return listing_row(job)


@router.patch("/listings/{listing_id}")
def set_listing_status(
    listing_id: UUID,
    payload: ListingPatch,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    job = _job(session, context.organization.id, listing_id, lock=True)
    allowed = {
        "draft": {"open", "closed"},
        "open": {"paused", "closed"},
        "paused": {"open", "closed"},
        "closed": set(),
    }
    if payload.status not in allowed.get(job.status, set()):
        raise HTTPException(409, f"Cannot move listing from {job.status} to {payload.status}")
    before = job.status
    now = datetime.now(UTC)
    job.status = payload.status
    job.version += 1
    if payload.status == "open":
        job.published_at, job.closed_at = now, None
    elif payload.status == "closed":
        job.closed_at = now
    # The 0038 trigger projects from the canonical job row when the realtime
    # event is inserted. Flush that row first so SQLAlchemy cannot emit the
    # event ahead of the status/version update.
    flush_or_conflict(session)
    _event(
        session,
        context,
        "job.status_changed",
        "job",
        job.id,
        reason="Employer changed listing status",
        before={"status": before},
        after={"status": job.status},
    )
    commit_in_context(session, context)
    count = (
        session.scalar(
            select(func.count())
            .select_from(AtsApplication)
            .where(
                AtsApplication.organization_id == context.organization.id,
                AtsApplication.job_id == job.id,
            )
        )
        or 0
    )
    return listing_row(job, count)


@router.post("/invitations", status_code=201)
def invite(
    payload: InvitationInput,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    job = _job(session, context.organization.id, payload.listing_id, lock=True)
    if job.status != "open":
        raise HTTPException(409, "Candidates may only be invited to an open listing")
    email = normalize_email(payload.email)
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == context.organization.id, AtsCandidate.email == email
        )
    )
    if candidate is None:
        candidate = AtsCandidate(
            organization_id=context.organization.id,
            email=email,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            notes=payload.message,
            created_by_user_id=context.user.id,
        )
        session.add(candidate)
        flush_or_conflict(session)
    application = AtsApplication(
        organization_id=context.organization.id, job_id=job.id, candidate_id=candidate.id
    )
    session.add(application)
    flush_or_conflict(session, "Candidate already has an application for this listing")
    invitation = AtsCandidateInvitation(
        organization_id=context.organization.id,
        application_id=application.id,
        token_digest="pending",
        expires_at=datetime.now(UTC) + timedelta(days=14),
        created_by_user_id=context.user.id,
    )
    session.add(invitation)
    flush_or_conflict(session)
    token, invitation.token_digest = create_one_time_token(context.organization.id, invitation.id)
    _event(
        session,
        context,
        "candidate.invited",
        "application",
        application.id,
        after={"listing_id": str(job.id)},
    )
    commit_in_context(session, context)
    return {
        **candidate_row(application, candidate, invitation.created_at),
        "invitation_url": f"{str(request.base_url).rstrip('/')}/candidate-invitation#token={token}",
        "invitation_expires_at": invitation.expires_at,
    }


@router.post("/candidates/{candidate_id}/stage")
def move_candidate(
    candidate_id: UUID,
    payload: StageInput,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, candidate_id, lock=True)
    target = "rejected" if payload.stage == "declined" else payload.stage
    allowed = {
        "invited": {"applied"},
        "applied": {"screening", "rejected"},
        "screening": {"interview", "rejected"},
        "interview": {"screening", "rejected"},
    }
    if target not in allowed.get(application.status, set()):
        raise HTTPException(
            409, f"Cannot move candidate from {application.status} to {payload.stage}"
        )
    before = application.status
    application.status = target
    application.version += 1
    _event(
        session,
        context,
        "application.stage_changed",
        "application",
        application.id,
        reason="Employer pipeline action",
        before={"status": before},
        after={"status": target},
    )
    commit_in_context(session, context)
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
    )
    return candidate_row(application, candidate)


@router.post("/candidates/{candidate_id}/offers", status_code=201)
def create_offer(
    candidate_id: UUID,
    payload: OfferInput,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, candidate_id, lock=True)
    if application.status not in {"interview", "offer"}:
        raise HTTPException(409, "Only interviewed candidates may receive an offer")
    previous = session.scalar(
        select(AtsOffer)
        .where(
            AtsOffer.organization_id == context.organization.id,
            AtsOffer.application_id == application.id,
        )
        .order_by(AtsOffer.version.desc())
        .limit(1)
        .with_for_update()
    )
    if previous and previous.status in {"accepted", "declined"}:
        raise HTTPException(409, "A terminal offer cannot be revised")
    if previous and previous.status != "withdrawn":
        previous.status, previous.terminal_at = "superseded", datetime.now(UTC)
    offer = AtsOffer(
        organization_id=context.organization.id,
        application_id=application.id,
        version=(previous.version + 1 if previous else 1),
        position_title=payload.position_title,
        start_date=payload.start_date.date() if payload.start_date else None,
        hourly_rate=payload.hourly_rate,
        notes=payload.notes,
        terms=payload.notes or "Employment offer",
        created_by_user_id=context.user.id,
    )
    session.add(offer)
    flush_or_conflict(session)
    _event(session, context, "offer.created", "offer", offer.id, after={"version": offer.version})
    commit_in_context(session, context)
    return offer_row(offer)


@router.post("/candidates/{candidate_id}/offers/{offer_id}/send")
def send_offer(
    candidate_id: UUID,
    offer_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, candidate_id, lock=True)
    offer = _offer(session, context.organization.id, offer_id, lock=True)
    if offer.application_id != application.id:
        raise HTTPException(404, "Offer not found")
    if offer.status != "draft":
        raise HTTPException(409, "Only a draft offer may be sent")
    offer.status = "sent"
    offer.sent_at = datetime.now(UTC)
    application.status = "offer"
    application.version += 1
    _event(session, context, "offer.sent", "offer", offer.id)
    commit_in_context(session, context)
    return offer_row(offer)


@router.post("/candidates/{candidate_id}/hire")
def controlled_hire(
    candidate_id: UUID,
    payload: HireInput,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    hire(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, candidate_id, lock=True)
    offer = _offer(session, context.organization.id, payload.offer_id, lock=True)
    if offer.application_id != application.id:
        raise HTTPException(404, "Offer not found")
    if offer.status != "accepted" or application.status != "accepted":
        raise HTTPException(
            409, "The candidate must explicitly accept the current offer before hiring handoff"
        )
    provisioning = provision_accepted_candidate(session, context, application, uuid4())
    commit_in_context(session, context)
    return {
        "application_id": application.id,
        "membership_id": provisioning.membership_id,
        "membership_created": provisioning.membership_created,
        "assigned_room_ids": [],
    }
