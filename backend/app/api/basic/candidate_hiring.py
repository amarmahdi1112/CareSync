"""Candidate-owned invitation claim and application/offer decisions."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.basic.common import commit_or_conflict, ensure_writable
from app.api.basic.dependencies import BasicUser
from app.api.dependencies import SessionDependency
from app.basic.models import (
    AtsApplication,
    AtsCandidate,
    AtsCandidateInvitation,
    AtsEvent,
    AtsJob,
    AtsOffer,
    User,
)
from app.basic.security import (
    create_access_token,
    hash_password,
    normalize_email,
    parse_one_time_token,
    set_rls_organization,
    token_digest_matches,
    verify_password,
)


def reject_0030_legacy_candidate_decision(request: Request) -> None:
    blocked = {"claim", "activate", "apply", "offer-decision", "withdraw"}
    if (
        request.url.path.rsplit("/", 1)[-1] in blocked
        and bool(getattr(request.app.state, "staff_screening_pathways_enabled", False))
    ):
        raise HTTPException(
            409,
            detail={
                "code": "legacy_candidate_hiring_disabled",
                "message": "Use the consent-bound /marketplace 0030 workflow",
            },
        )


router = APIRouter(
    prefix="/candidate/hiring",
    tags=["candidate hiring"],
    dependencies=[Depends(reject_0030_legacy_candidate_decision)],
)


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=400)


class CandidateDecision(TokenBody):
    offer_id: UUID
    decision: str
    reason: str | None = Field(default=None, max_length=2000)


class CandidateActivation(TokenBody):
    password: str = Field(min_length=12, max_length=128)


class CandidateLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class CandidateProfileUpdate(TokenBody):
    certification_type: str | None = Field(default=None, max_length=120)
    certification_number: str | None = Field(default=None, max_length=120)
    certification_expiry_date: date | None = None
    work_history: list[dict] = Field(default_factory=list, max_length=50)
    submit: bool = False


def _invitation(session, token: str, *, lock: bool = False) -> AtsCandidateInvitation:
    try:
        organization_id, invitation_id, digest = parse_one_time_token(token)
    except ValueError:
        raise HTTPException(404, "Invitation not found") from None
    set_rls_organization(session, organization_id)
    statement = select(AtsCandidateInvitation).where(
        AtsCandidateInvitation.organization_id == organization_id,
        AtsCandidateInvitation.id == invitation_id,
    )
    if lock:
        statement = statement.with_for_update()
    invitation = session.scalar(statement)
    now = datetime.now(UTC)
    if invitation is None or not token_digest_matches(invitation.token_digest, digest):
        raise HTTPException(404, "Invitation not found")
    expires_at = (
        invitation.expires_at
        if invitation.expires_at.tzinfo
        else invitation.expires_at.replace(tzinfo=UTC)
    )
    if invitation.revoked_at is not None or expires_at <= now:
        raise HTTPException(410, "Invitation is no longer available")
    return invitation


def _claimed(session, token: str, user, *, lock: bool = False):
    invitation = _invitation(session, token, lock=lock)
    application = session.scalar(
        select(AtsApplication)
        .where(
            AtsApplication.organization_id == invitation.organization_id,
            AtsApplication.id == invitation.application_id,
        )
        .with_for_update()
        if lock
        else select(AtsApplication).where(
            AtsApplication.organization_id == invitation.organization_id,
            AtsApplication.id == invitation.application_id,
        )
    )
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == invitation.organization_id,
            AtsCandidate.id == application.candidate_id,
        )
    )
    if candidate.claimed_user_id != user.id:
        raise HTTPException(403, "This invitation is not claimed by the signed-in user")
    return invitation, application, candidate


def _record(
    session, invitation, user, event_type, entity_type, entity_id, *, reason=None, after=None
):
    session.add(
        AtsEvent(
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            after=after,
        )
    )


@router.post("/invitation-preview")
def preview(payload: TokenBody, session: SessionDependency):
    invitation = _invitation(session, payload.token)
    application = session.scalar(
        select(AtsApplication).where(
            AtsApplication.organization_id == invitation.organization_id,
            AtsApplication.id == invitation.application_id,
        )
    )
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == invitation.organization_id,
            AtsCandidate.id == application.candidate_id,
        )
    )
    job = session.scalar(
        select(AtsJob).where(
            AtsJob.organization_id == invitation.organization_id, AtsJob.id == application.job_id
        )
    )
    return {
        "email": candidate.email,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "job_title": job.title,
        "expires_at": invitation.expires_at,
        "claimed": candidate.claimed_user_id is not None,
    }


@router.post("/claim")
def claim(payload: TokenBody, request: Request, user: BasicUser, session: SessionDependency):
    ensure_writable(request)
    invitation = _invitation(session, payload.token, lock=True)
    application = session.scalar(
        select(AtsApplication)
        .where(
            AtsApplication.organization_id == invitation.organization_id,
            AtsApplication.id == invitation.application_id,
        )
        .with_for_update()
    )
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == invitation.organization_id,
            AtsCandidate.id == application.candidate_id,
        )
        .with_for_update()
    )
    if normalize_email(user.email) != candidate.email:
        raise HTTPException(403, "Sign in with the invited verified email address")
    if candidate.claimed_user_id not in {None, user.id}:
        raise HTTPException(409, "Invitation was claimed by another identity")
    candidate.claimed_user_id = user.id
    invitation.accepted_at = invitation.accepted_at or datetime.now(UTC)
    _record(session, invitation, user, "candidate.identity_claimed", "candidate", candidate.id)
    commit_or_conflict(session)
    return {
        "candidate_id": candidate.id,
        "application_id": application.id,
        "organization_membership_created": False,
    }


@router.post("/activate", status_code=201)
def activate_candidate(
    payload: CandidateActivation,
    request: Request,
    session: SessionDependency,
):
    """Create an invite-bound identity without creating a daycare tenant membership."""
    ensure_writable(request)
    invitation = _invitation(session, payload.token, lock=True)
    application = session.scalar(
        select(AtsApplication)
        .where(
            AtsApplication.organization_id == invitation.organization_id,
            AtsApplication.id == invitation.application_id,
        )
        .with_for_update()
    )
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == invitation.organization_id,
            AtsCandidate.id == application.candidate_id,
        )
        .with_for_update()
    )
    if candidate.claimed_user_id is not None or invitation.accepted_at is not None:
        raise HTTPException(409, "Invitation identity is already claimed")
    if session.scalar(select(User.id).where(User.email == candidate.email)) is not None:
        raise HTTPException(
            409, "An account exists for this email; sign in and claim the invitation"
        )
    now = datetime.now(UTC)
    user = User(
        email=candidate.email,
        password_hash=hash_password(payload.password),
        first_name=candidate.first_name,
        last_name=candidate.last_name,
        email_verified_at=now,
        email_verification_method="candidate_invitation",
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, "Candidate account activation conflicted; sign in and retry"
        ) from None
    candidate.claimed_user_id = user.id
    invitation.accepted_at = now
    _record(
        session,
        invitation,
        user,
        "candidate.identity_activated",
        "candidate",
        candidate.id,
        after={"organization_membership_created": False},
    )
    commit_or_conflict(session)
    return {
        "access_token": create_access_token(user, request.app.state.settings),
        "token_type": "bearer",
        "candidate_id": candidate.id,
        "application_id": application.id,
        "organization_membership_created": False,
    }


@router.post("/login")
def candidate_login(
    payload: CandidateLogin,
    request: Request,
    session: SessionDependency,
):
    user = session.scalar(select(User).where(User.email == normalize_email(payload.email)))
    if (
        user is None
        or not user.is_active
        or user.email_verified_at is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(401, "Invalid email or password")
    if user.email_verification_method != "candidate_invitation":
        raise HTTPException(403, "A claimed candidate identity is required")
    return {
        "access_token": create_access_token(user, request.app.state.settings),
        "token_type": "bearer",
    }


def _profile(candidate: AtsCandidate) -> dict:
    return {
        "candidate_id": candidate.id,
        "onboarding_status": candidate.onboarding_status,
        "certification_type": candidate.certification_type,
        "certification_number": candidate.certification_number,
        "certification_expiry_date": candidate.certification_expiry_date,
        "certification_verification_status": candidate.certification_verification_status,
        "certification_verified_at": candidate.certification_verified_at,
        "certification_review_note": candidate.certification_review_note,
        "work_history": candidate.work_history,
    }


@router.post("/profile")
def candidate_profile(payload: TokenBody, user: BasicUser, session: SessionDependency):
    _, _, candidate = _claimed(session, payload.token, user)
    return _profile(candidate)


@router.put("/profile")
def update_candidate_profile(
    payload: CandidateProfileUpdate,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    invitation, _, candidate = _claimed(session, payload.token, user, lock=True)
    if candidate.onboarding_status == "complete":
        raise HTTPException(409, "A completed onboarding profile cannot be changed")
    for item in payload.work_history:
        if not isinstance(item, dict) or not str(item.get("employer", "")).strip():
            raise HTTPException(422, "Each work history item requires an employer")
    candidate.certification_type = payload.certification_type
    candidate.certification_number = payload.certification_number
    candidate.certification_expiry_date = payload.certification_expiry_date
    candidate.work_history = payload.work_history
    candidate.certification_verification_status = (
        "pending" if payload.certification_number else "unverified"
    )
    candidate.certification_verified_at = None
    candidate.certification_verified_by_user_id = None
    candidate.certification_review_note = None
    candidate.onboarding_status = "submitted" if payload.submit else "in_progress"
    _record(
        session,
        invitation,
        user,
        "candidate.profile_updated",
        "candidate",
        candidate.id,
        after={
            "onboarding_status": candidate.onboarding_status,
            "certification_verification_status": candidate.certification_verification_status,
        },
    )
    commit_or_conflict(session)
    return _profile(candidate)


@router.post("/application")
def application(payload: TokenBody, user: BasicUser, session: SessionDependency):
    invitation, app, candidate = _claimed(session, payload.token, user)
    job = session.scalar(
        select(AtsJob).where(
            AtsJob.organization_id == invitation.organization_id, AtsJob.id == app.job_id
        )
    )
    offers = list(
        session.scalars(
            select(AtsOffer)
            .where(
                AtsOffer.organization_id == invitation.organization_id,
                AtsOffer.application_id == app.id,
            )
            .order_by(AtsOffer.version.desc())
        )
    )
    return {
        "id": app.id,
        "status": app.status,
        "version": app.version,
        "job": {
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "location": job.location,
            "employment_type": job.employment_type,
        },
        "candidate": {
            "first_name": candidate.first_name,
            "last_name": candidate.last_name,
            "email": candidate.email,
        },
        "offers": [
            {
                "id": o.id,
                "version": o.version,
                "status": o.status,
                "position_title": o.position_title,
                "hourly_rate": float(o.hourly_rate or 0),
                "start_date": o.start_date,
                "notes": o.notes or o.terms,
                "sent_at": o.sent_at,
            }
            for o in offers
        ],
    }


@router.post("/apply")
def apply(payload: TokenBody, request: Request, user: BasicUser, session: SessionDependency):
    ensure_writable(request)
    invitation, app, _ = _claimed(session, payload.token, user, lock=True)
    if app.status != "invited":
        raise HTTPException(409, "Only an invited application may be submitted")
    app.status = "applied"
    app.version += 1
    _record(
        session,
        invitation,
        user,
        "application.applied",
        "application",
        app.id,
        after={"status": "applied"},
    )
    commit_or_conflict(session)
    return {"id": app.id, "status": app.status, "version": app.version}


@router.post("/withdraw")
def withdraw(payload: TokenBody, request: Request, user: BasicUser, session: SessionDependency):
    ensure_writable(request)
    invitation, app, _ = _claimed(session, payload.token, user, lock=True)
    if app.status in {"accepted", "rejected", "withdrawn", "hired"}:
        raise HTTPException(409, "Application is already terminal")
    app.status = "withdrawn"
    app.version += 1
    _record(
        session,
        invitation,
        user,
        "application.withdrawn",
        "application",
        app.id,
        after={"status": "withdrawn"},
    )
    commit_or_conflict(session)
    return {"id": app.id, "status": app.status, "version": app.version}


@router.post("/offer-decision")
def offer_decision(
    payload: CandidateDecision, request: Request, user: BasicUser, session: SessionDependency
):
    ensure_writable(request)
    invitation, app, _ = _claimed(session, payload.token, user, lock=True)
    if payload.decision not in {"accepted", "declined"}:
        raise HTTPException(422, "Decision must be accepted or declined")
    offer = session.scalar(
        select(AtsOffer)
        .where(
            AtsOffer.organization_id == invitation.organization_id,
            AtsOffer.id == payload.offer_id,
            AtsOffer.application_id == app.id,
        )
        .with_for_update()
    )
    if offer is None:
        raise HTTPException(404, "Offer not found")
    if offer.status != "sent" or app.status != "offer":
        raise HTTPException(409, "Only the current sent offer may receive a decision")
    latest = session.scalar(
        select(AtsOffer.id)
        .where(
            AtsOffer.organization_id == invitation.organization_id,
            AtsOffer.application_id == app.id,
        )
        .order_by(AtsOffer.version.desc())
        .limit(1)
    )
    if latest != offer.id:
        raise HTTPException(409, "Only the current offer version may receive a decision")
    now = datetime.now(UTC)
    offer.status = payload.decision
    offer.terminal_at = now
    if payload.decision == "accepted":
        offer.accepted_at = now
        app.status = "accepted"
    else:
        app.status = "rejected"
    app.version += 1
    _record(
        session,
        invitation,
        user,
        f"offer.{payload.decision}",
        "offer",
        offer.id,
        reason=payload.reason,
        after={"application_status": app.status},
    )
    commit_or_conflict(session)
    return {
        "offer_id": offer.id,
        "offer_status": offer.status,
        "application_id": app.id,
        "application_status": app.status,
    }
