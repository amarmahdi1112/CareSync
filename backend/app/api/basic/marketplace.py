"""Global candidate marketplace with consent-gated tenant application creation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.basic.common import (
    commit_in_context,
    commit_or_conflict,
    ensure_writable,
    flush_or_conflict,
)
from app.api.basic.dependencies import (
    BasicContextDependency,
    BasicUser,
    CompleteMarketplaceUser,
    require_permission,
)
from app.api.dependencies import SessionDependency
from app.basic.access import active_assignment_ids
from app.basic.candidate_profiles import missing_profile_fields
from app.basic.hiring_lifecycle import (
    HiringLifecycleViolation,
    require_candidate_interview_decision,
    require_candidate_offer_decision,
    require_candidate_withdrawal,
    require_employer_proposal_decision,
    require_interview_request,
)
from app.basic.hiring_repository import (
    get_hiring_application as _application,
)
from app.basic.hiring_repository import (
    get_hiring_job as _job,
)
from app.basic.hiring_repository import (
    record_hiring_event as _event,
)
from app.basic.models import (
    AtsApplication,
    AtsApplicationScreeningSnapshot,
    AtsCandidate,
    AtsEvent,
    AtsInterview,
    AtsJob,
    AtsJobScreeningTerms,
    AtsOffer,
    AtsOfferAcknowledgment,
    AtsOfferScreeningTerms,
    Facility,
    MarketplaceApplicationLink,
    MarketplaceCredentialNotification,
    MarketplaceInterest,
    MarketplaceJob,
    MarketplaceJobScreeningTerms,
    MarketplaceProfile,
    MarketplaceScreeningProfile,
    Organization,
    OrganizationMembership,
    Role,
    StaffScreeningApplicationShare,
    StaffScreeningCandidateConfirmation,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    User,
)
from app.basic.notifications import notify_organization_hiring_managers, notify_user
from app.basic.security import (
    create_access_token,
    hash_password,
    normalize_email,
    set_rls_organization,
    set_rls_user,
    verify_password,
)
from app.basic.staff_screening_terms import (
    driver_declaration_snapshot,
    offer_terms_digest,
    screening_profile_complete,
    structured_terms_from_model,
    structured_terms_match_application_snapshot,
)
from app.basic.verification import apply_temporary_email_approval

router = APIRouter(prefix="/marketplace", tags=["candidate marketplace"])
employer_router = APIRouter(prefix="/ats/marketplace", tags=["employer marketplace"])
manage = require_permission("ats:manage")
read_marketplace = require_permission("ats:read")

# A superseded offer may have been superseded while it was still a draft.
# Requiring sent evidence prevents employer-only compensation and terms from
# leaking into the candidate projection through a status transition.
CANDIDATE_VISIBLE_OFFER_STATUSES = frozenset(
    {"sent", "accepted", "declined", "withdrawn", "superseded"}
)
SCREENING_COVERAGE = frozenset({"criminal_record_check", "vulnerable_sector_search"})


def _enforce_lifecycle(rule, *args, **kwargs) -> None:
    try:
        rule(*args, **kwargs)
    except HiringLifecycleViolation as error:
        raise HTTPException(error.status_code, error.detail) from error


def _screening_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "staff_screening_pathways_enabled", False))


def _pathway_matches_job(pathway: str, position_shape: str) -> bool:
    if position_shape == "driver_only":
        return pathway in {"driver", "educator_driver"}
    if position_shape == "educator_driver":
        return pathway == "educator_driver"
    return pathway in {"educator", "student_educator", "educator_driver"}


def _public_job_row(session, row: MarketplaceJob, *, screening_enabled: bool) -> dict:
    result = {
        "id": row.listing_id,
        "organization_id": row.organization_id,
        "organization_name": row.organization_name,
        "title": row.title,
        "description": row.description,
        "employment_type": row.employment_type,
        "location": row.location,
        "openings": row.openings,
        "published_at": row.published_at,
    }
    if screening_enabled:
        terms = session.get(MarketplaceJobScreeningTerms, row.listing_id)
        if terms is None:
            raise RuntimeError("0030 public job screening terms are missing")
        result.update(structured_terms_from_model(terms))
        result["structured_terms_version"] = terms.source_version
    return result


def _candidate_offer_row(session, offer: AtsOffer, *, screening_enabled: bool) -> dict:
    result = {
        "id": offer.id,
        "version": offer.version,
        "status": offer.status,
        "sent_at": offer.sent_at,
        "expires_at": offer.expires_at,
        "position_title": offer.position_title,
        "start_date": offer.start_date,
        "hourly_rate": float(offer.hourly_rate or 0),
        "notes": offer.notes or offer.terms,
        "terms": offer.terms,
        "compensation": offer.compensation,
    }
    if screening_enabled:
        terms = session.get(AtsOfferScreeningTerms, offer.id)
        if terms is None:
            raise RuntimeError("0030 offer screening terms are missing")
        result.update(structured_terms_from_model(terms))
        result["terms_digest"] = terms.terms_digest
    return result


def _utc_iso_z(value: datetime | None) -> str | None:
    """Serialize timestamps canonically even when SQLite drops timezone metadata."""
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


class MarketplaceRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        result = value.strip()
        if not result:
            raise ValueError("Name cannot be blank")
        return result


class MarketplaceLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=1, max_length=100)
    headline: str = Field(min_length=1, max_length=180)
    bio: str | None = Field(default=None, max_length=5000)
    certification_type: str | None = Field(default=None, max_length=120)
    certification_number: str | None = Field(default=None, max_length=120)
    certification_expiry_date: date | None = None
    work_history: list[dict] = Field(default_factory=list, max_length=50)
    discoverable: bool = False


class InterestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_user_id: UUID
    job_id: UUID
    message: str | None = Field(default=None, max_length=3000)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str


class MarketplaceApplyDisclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screening_schema_version: Literal["0030"]
    screening_profile_version: int = Field(ge=1)
    acknowledged_job_terms_version: int = Field(ge=1)
    document_version_ids: list[UUID] = Field(min_length=1, max_length=20)
    acknowledge_profile_snapshot: Literal[True]
    acknowledge_screening_disclosure: Literal[True]

    @field_validator("document_version_ids")
    @classmethod
    def unique_screening_versions(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("document_version_ids cannot contain duplicates")
        return value


class InterestDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "declined"]
    screening_schema_version: Literal["0030"] | None = None
    screening_profile_version: int | None = Field(default=None, ge=1)
    acknowledged_job_terms_version: int | None = Field(default=None, ge=1)
    document_version_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)
    acknowledge_profile_snapshot: Literal[True] | None = None
    acknowledge_screening_disclosure: Literal[True] | None = None

    @model_validator(mode="after")
    def all_or_none_disclosure(self) -> InterestDecision:
        fields = (
            self.screening_schema_version,
            self.screening_profile_version,
            self.acknowledged_job_terms_version,
            self.document_version_ids,
            self.acknowledge_profile_snapshot,
            self.acknowledge_screening_disclosure,
        )
        supplied = [value is not None for value in fields]
        if self.decision == "declined" and any(supplied):
            raise ValueError("declined interests cannot include screening disclosure")
        if any(supplied) and not all(supplied):
            raise ValueError("screening disclosure fields must be supplied together")
        return self

    def disclosure(self) -> MarketplaceApplyDisclosure | None:
        values = self.model_dump(exclude={"decision"})
        if all(value is None for value in values.values()):
            return None
        return MarketplaceApplyDisclosure(**values)


class CandidateOfferDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "declined"]
    acknowledged_offer_version: int | None = Field(default=None, ge=1)
    acknowledged_terms_digest: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    driver_terms_acknowledged: bool | None = None


class InterviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: datetime
    location_or_link: str = Field(min_length=1, max_length=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class CandidateInterviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    proposed_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)


class EmployerProposalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    scheduled_at: datetime | None = None
    location_or_link: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


def _profile_row(
    profile: MarketplaceProfile,
    *,
    private: bool,
    screening: MarketplaceScreeningProfile | None = None,
) -> dict:
    value = {
        "user_id": profile.user_id,
        "city": profile.city,
        "headline": profile.headline,
        "candidate_type": profile.candidate_type,
        "institution": profile.institution,
        "program": profile.program,
        "expected_graduation_date": profile.expected_graduation_date,
        "onboarding_completed_at": profile.onboarding_completed_at,
        "certification_type": profile.certification_type,
        "certification_verification_status": profile.certification_verification_status,
        "discoverable": profile.discoverable,
        "certification_provenance": profile.certification_provenance,
        "certification_candidate_confirmed_at": profile.certification_candidate_confirmed_at,
        "work_history_provenance": profile.work_history_provenance,
        "work_history_candidate_confirmed_at": profile.work_history_candidate_confirmed_at,
        "experience_count": len(profile.work_history or []),
        "updated_at": profile.updated_at,
    }
    if private:
        value.update(
            bio=profile.bio,
            certification_number=profile.certification_number,
            certification_expiry_date=profile.certification_expiry_date,
            work_history=profile.work_history,
        )
    if screening is not None:
        value.update(
            pathway=screening.pathway,
            driver_declaration=driver_declaration_snapshot(screening),
            operational_driver_ready=False,
        )
    return value


@router.post("/auth/register", status_code=201)
def register(payload: MarketplaceRegister, request: Request, session: SessionDependency):
    ensure_writable(request)
    email = normalize_email(payload.email)
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            409, "Email already registered; sign in and create a marketplace profile"
        )
    user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        is_active=True,
    )
    apply_temporary_email_approval(user, decided_at=datetime.now(UTC))
    profile = MarketplaceProfile(
        user_id=user.id,
        city="",
        headline="",
        discoverable=False,
    )
    session.add(user)
    flush_or_conflict(session, "Email already registered")
    set_rls_user(session, user.id)
    session.add(profile)
    commit_or_conflict(session)
    missing = missing_profile_fields(user, profile)
    return {
        "access_token": create_access_token(user, request.app.state.settings),
        "token_type": "bearer",
        "user_id": user.id,
        "organization_membership_created": False,
        "profile": _profile_row(profile, private=True),
        "profile_complete": not missing,
        "missing_profile_fields": missing,
    }


@router.post("/auth/login")
def login(payload: MarketplaceLogin, request: Request, session: SessionDependency):
    user = session.scalar(select(User).where(User.email == normalize_email(payload.email)))
    if (
        user is None
        or not user.is_active
        or user.email_verified_at is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(401, "Invalid email or password")
    set_rls_user(session, user.id)
    profile = session.get(MarketplaceProfile, user.id)
    missing = missing_profile_fields(user, profile)
    return {
        "access_token": create_access_token(user, request.app.state.settings),
        "token_type": "bearer",
        "user_id": user.id,
        "profile_complete": not missing,
        "missing_profile_fields": missing,
    }


@router.get("/profile")
def get_profile(user: CompleteMarketplaceUser, session: SessionDependency):
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        raise HTTPException(404, "Marketplace profile not found")
    return _profile_row(profile, private=True)


@router.put("/profile")
def put_profile(
    payload: ProfileUpdate,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    for row in payload.work_history:
        if not isinstance(row, dict) or not str(row.get("employer", "")).strip():
            raise HTTPException(422, "Each work history item requires an employer")
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        profile = MarketplaceProfile(user_id=user.id, city=payload.city, headline=payload.headline)
        session.add(profile)
    if profile.candidate_type == "student" and any(
        (
            payload.certification_type,
            payload.certification_number,
            payload.certification_expiry_date,
        )
    ):
        raise HTTPException(422, "Student profiles cannot contain certification fields")
    previous_certification = (
        profile.certification_type,
        profile.certification_number,
        profile.certification_expiry_date,
    )
    requested_certification = (
        payload.certification_type,
        payload.certification_number,
        payload.certification_expiry_date,
    )
    if _screening_enabled(request) and requested_certification != previous_certification:
        raise HTTPException(
            422,
            {
                "code": "credential_facts_require_document_workflow",
                "message": (
                    "Certification facts cannot be edited manually. Upload and confirm "
                    "the credential document so every connected employer record is "
                    "invalidated and re-reviewed together."
                ),
            },
        )
    previous_work_history = profile.work_history
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    now = datetime.now(UTC)
    certification_changed = previous_certification != (
        profile.certification_type,
        profile.certification_number,
        profile.certification_expiry_date,
    )
    work_history_changed = previous_work_history != profile.work_history
    if certification_changed:
        profile.certification_verification_status = "unverified"
    if certification_changed and profile.certification_number:
        profile.certification_provenance = "manual"
        profile.certification_candidate_confirmed_at = now
    if work_history_changed:
        profile.work_history_provenance = "manual"
        profile.work_history_candidate_confirmed_at = now
    commit_or_conflict(session)
    return _profile_row(profile, private=True)


@router.get("/jobs")
def public_jobs(request: Request, session: SessionDependency):
    rows = list(
        session.scalars(select(MarketplaceJob).order_by(MarketplaceJob.published_at.desc()))
    )
    return [
        _public_job_row(session, row, screening_enabled=_screening_enabled(request)) for row in rows
    ]


@router.get("/jobs/{listing_id}")
def public_job_detail(listing_id: UUID, request: Request, session: SessionDependency):
    row = session.get(MarketplaceJob, listing_id)
    if row is None:
        raise HTTPException(404, "Open job not found")
    return _public_job_row(session, row, screening_enabled=_screening_enabled(request))


@router.get("/me")
def marketplace_me(request: Request, user: BasicUser, session: SessionDependency):
    profile = session.get(MarketplaceProfile, user.id)
    missing = missing_profile_fields(user, profile)
    memberships = list(
        session.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id, OrganizationMembership.status == "active"
            )
        )
    )
    staff = []
    for membership in memberships:
        set_rls_organization(session, membership.organization_id)
        role = session.scalar(
            select(Role).where(
                Role.organization_id == membership.organization_id, Role.id == membership.role_id
            )
        )
        organization = session.get(Organization, membership.organization_id)
        if role is not None and organization is not None:
            facility_ids, room_ids = active_assignment_ids(session, organization.id, membership.id)
            staff.append(
                {
                    "organization_id": organization.id,
                    "organization_name": organization.name,
                    "membership_id": membership.id,
                    "role_key": role.key,
                    "role_name": role.name,
                    "permissions": list(role.permissions or []),
                    "assigned_facility_ids": facility_ids,
                    "assigned_room_ids": room_ids,
                    "request_header": {
                        "name": "X-Organization-ID",
                        "value": str(organization.id),
                    },
                    "staff_api_ready": role.key in {"owner", "administrator", "educator"},
                }
            )
    return {
        "screening_schema_version": "0030" if _screening_enabled(request) else None,
        "staff_screening_evidence_upload_available": bool(
            getattr(
                request.app.state,
                "staff_screening_evidence_upload_available",
                False,
            )
        ),
        "user_id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "profile": _profile_row(profile, private=True) if profile else None,
        "active_staff_memberships": staff,
        "staff_session_uses_same_access_token": True,
        "profile_complete": not missing,
        "missing_profile_fields": missing,
    }


def _candidate_for_user(session, organization_id: UUID, user: User) -> AtsCandidate:
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == organization_id, AtsCandidate.claimed_user_id == user.id
        )
    )
    if candidate is None:
        candidate = session.scalar(
            select(AtsCandidate).where(
                AtsCandidate.organization_id == organization_id, AtsCandidate.email == user.email
            )
        )
        if candidate is not None and candidate.claimed_user_id not in {None, user.id}:
            raise HTTPException(409, "Candidate email is linked to another identity")
    if candidate is None:
        candidate = AtsCandidate(
            organization_id=organization_id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            claimed_user_id=user.id,
            created_by_user_id=user.id,
            status="active",
        )
        session.add(candidate)
        flush_or_conflict(session)
    else:
        candidate.claimed_user_id = user.id
    profile = session.get(MarketplaceProfile, user.id)
    if profile is not None:
        candidate.certification_type = profile.certification_type
        candidate.certification_number = profile.certification_number
        candidate.certification_expiry_date = profile.certification_expiry_date
        candidate.certification_verification_status = profile.certification_verification_status
        candidate.work_history = list(profile.work_history or [])
        candidate.certification_provenance = profile.certification_provenance
        candidate.certification_candidate_confirmed_at = (
            profile.certification_candidate_confirmed_at
        )
        candidate.work_history_provenance = profile.work_history_provenance
        candidate.work_history_candidate_confirmed_at = profile.work_history_candidate_confirmed_at
        candidate.candidate_type = profile.candidate_type
        candidate.institution = profile.institution
        candidate.program = profile.program
        candidate.expected_graduation_date = profile.expected_graduation_date
        candidate.phone = profile.phone
        candidate.notes = f"Marketplace city: {profile.city}"
    return candidate


def _screening_disclosure_facts(
    session,
    *,
    user_id: UUID,
    job: AtsJob,
    disclosure: MarketplaceApplyDisclosure,
) -> tuple[MarketplaceScreeningProfile, AtsJobScreeningTerms, dict, list[UUID]]:
    profile = session.scalar(
        select(MarketplaceScreeningProfile)
        .where(MarketplaceScreeningProfile.user_id == user_id)
        .with_for_update()
    )
    if profile is None or profile.version != disclosure.screening_profile_version:
        raise HTTPException(409, "Screening profile changed; reload before applying")
    if not screening_profile_complete(profile):
        raise HTTPException(409, "Complete the candidate pathway before applying")
    terms = session.scalar(
        select(AtsJobScreeningTerms).where(
            AtsJobScreeningTerms.organization_id == job.organization_id,
            AtsJobScreeningTerms.job_id == job.id,
        )
    )
    if terms is None:
        raise RuntimeError("0030 job screening terms are missing")
    if terms.version != disclosure.acknowledged_job_terms_version:
        raise HTTPException(409, "Job duties changed; review them before applying")
    structured_terms = structured_terms_from_model(terms)
    if not _pathway_matches_job(profile.pathway, structured_terms["position_shape"]):
        raise HTTPException(409, "Candidate pathway does not match this position")
    versions = list(
        session.scalars(
            select(StaffScreeningDocumentVersion).where(
                StaffScreeningDocumentVersion.user_id == user_id,
                StaffScreeningDocumentVersion.id.in_(disclosure.document_version_ids),
            )
        )
    )
    if len(versions) != len(disclosure.document_version_ids):
        raise HTTPException(404, "One or more screening document versions were not found")
    coverage_sources: dict[str, UUID] = {}
    today = date.today()
    for version in versions:
        document = session.scalar(
            select(StaffScreeningDocument).where(
                StaffScreeningDocument.user_id == user_id,
                StaffScreeningDocument.id == version.document_id,
            )
        )
        confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
        if (
            document is None
            or confirmation is None
            or document.status != "confirmed"
            or document.current_version_number != version.version_number
            or (confirmation.expiry_date is not None and confirmation.expiry_date < today)
        ):
            raise HTTPException(409, "Only current, confirmed screening evidence may be shared")
        for requirement in version.declared_coverage or []:
            if requirement in coverage_sources:
                raise HTTPException(409, "Share exactly one source per screening requirement")
            coverage_sources[requirement] = version.id
    if set(coverage_sources) != SCREENING_COVERAGE:
        raise HTTPException(409, "Both police-check screening requirements must be covered")
    return profile, terms, structured_terms, list(disclosure.document_version_ids)


def _apply(
    session,
    user: User,
    listing: MarketplaceJob,
    *,
    source: str,
    screening_enabled: bool,
    disclosure: MarketplaceApplyDisclosure | None,
) -> tuple[AtsApplication, bool]:
    set_rls_organization(session, listing.organization_id)
    job = _job(session, listing.organization_id, listing.listing_id, lock=True)
    if job.status != "open":
        raise HTTPException(409, "Job is no longer open")
    screening_facts = None
    if screening_enabled:
        if disclosure is None:
            raise HTTPException(422, "0030 applications require explicit screening disclosure")
        screening_facts = _screening_disclosure_facts(
            session, user_id=user.id, job=job, disclosure=disclosure
        )
    elif disclosure is not None:
        raise HTTPException(409, "Screening disclosure is unavailable on this server")
    candidate = _candidate_for_user(session, listing.organization_id, user)
    application = session.scalar(
        select(AtsApplication).where(
            AtsApplication.organization_id == listing.organization_id,
            AtsApplication.job_id == job.id,
            AtsApplication.candidate_id == candidate.id,
        )
    )
    created = False
    transitioned = False
    transition_before: dict | None = None
    if application is None:
        application = AtsApplication(
            organization_id=listing.organization_id,
            job_id=job.id,
            candidate_id=candidate.id,
            status="applied",
            source=source,
            candidate_consent_status="accepted",
        )
        session.add(application)
        flush_or_conflict(session)
        created = True
    elif application.status in {"accepted", "rejected", "withdrawn", "hired"}:
        raise HTTPException(409, "A terminal application cannot be re-applied")
    else:
        # A public submission supersedes a pre-existing invitation without
        # regressing applications that have already advanced in the ATS.
        transition_before = {
            "status": application.status,
            "candidate_consent_status": application.candidate_consent_status,
            "version": application.version,
        }
        if application.status == "invited":
            application.status = "applied"
        application.candidate_consent_status = "accepted"
        transitioned = any(
            (
                application.status != transition_before["status"],
                application.candidate_consent_status
                != transition_before["candidate_consent_status"],
            )
        )
        if transitioned:
            application.version += 1
    if screening_facts is not None:
        profile, terms, structured_terms, version_ids = screening_facts
        declaration = driver_declaration_snapshot(profile)
        snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
        if snapshot is None:
            snapshot = AtsApplicationScreeningSnapshot(
                application_id=application.id,
                organization_id=application.organization_id,
                candidate_user_id=user.id,
                pathway=profile.pathway,
                screening_profile_version=profile.version,
                job_terms_version=terms.version,
                driver_declaration_snapshot=declaration,
                job_terms_snapshot=structured_terms,
                candidate_acknowledged_at=datetime.now(UTC),
            )
            session.add(snapshot)
            flush_or_conflict(session)
            now = datetime.now(UTC)
            for version_id in version_ids:
                session.add(
                    StaffScreeningApplicationShare(
                        candidate_user_id=user.id,
                        organization_id=application.organization_id,
                        application_id=application.id,
                        document_version_id=version_id,
                        screening_profile_version=profile.version,
                        shared_at=now,
                    )
                )
            flush_or_conflict(session)
        else:
            if any(
                (
                    snapshot.candidate_user_id != user.id,
                    snapshot.pathway != profile.pathway,
                    snapshot.screening_profile_version != profile.version,
                    snapshot.job_terms_version != terms.version,
                    snapshot.driver_declaration_snapshot != declaration,
                    snapshot.job_terms_snapshot != structured_terms,
                )
            ):
                raise HTTPException(
                    409, "Application disclosure differs from its immutable snapshot"
                )
            active_ids = set(
                session.scalars(
                    select(StaffScreeningApplicationShare.document_version_id).where(
                        StaffScreeningApplicationShare.application_id == application.id,
                        StaffScreeningApplicationShare.candidate_user_id == user.id,
                        StaffScreeningApplicationShare.revoked_at.is_(None),
                    )
                )
            )
            if active_ids != set(version_ids):
                raise HTTPException(409, "Application disclosure differs from active shares")
    link = session.scalar(
        select(MarketplaceApplicationLink).where(
            MarketplaceApplicationLink.user_id == user.id,
            MarketplaceApplicationLink.application_id == application.id,
        )
    )
    if link is None:
        session.add(
            MarketplaceApplicationLink(
                user_id=user.id,
                organization_id=listing.organization_id,
                listing_id=listing.listing_id,
                application_id=application.id,
                listing_title=listing.title,
                organization_name=listing.organization_name,
                listing_location=listing.location,
                employment_type=listing.employment_type,
                published_at=listing.published_at,
            )
        )
    if created or transitioned:
        session.add(
            AtsEvent(
                organization_id=listing.organization_id,
                actor_user_id=user.id,
                event_type=(
                    "marketplace.application_created"
                    if created
                    else "marketplace.application_submitted"
                ),
                entity_type="application",
                entity_id=application.id,
                before=transition_before,
                after={
                    "source": source,
                    "status": application.status,
                    "candidate_consent_status": application.candidate_consent_status,
                    "version": application.version,
                },
            )
        )
    return application, created


@router.post("/jobs/{listing_id}/apply")
def apply(
    listing_id: UUID,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
    payload: MarketplaceApplyDisclosure | None = None,
):
    ensure_writable(request)
    profile = session.get(MarketplaceProfile, user.id)
    screening_enabled = _screening_enabled(request)
    screening_profile = (
        session.get(MarketplaceScreeningProfile, user.id) if screening_enabled else None
    )
    legacy_invalid = profile is None or profile.candidate_type not in {
        "certified_educator",
        "student",
    }
    modern_invalid = screening_profile is None or not screening_profile_complete(screening_profile)
    if (
        profile is None
        or profile.onboarding_completed_at is None
        or (modern_invalid if screening_enabled else legacy_invalid)
    ):
        raise HTTPException(409, "Complete the candidate pathway and onboarding before applying")
    listing = session.get(MarketplaceJob, listing_id)
    if listing is None:
        raise HTTPException(404, "Open job not found")
    application, created = _apply(
        session,
        user,
        listing,
        source="marketplace_application",
        screening_enabled=screening_enabled,
        disclosure=payload,
    )
    commit_or_conflict(session)
    return {
        "application_id": application.id,
        "organization_id": application.organization_id,
        "job_id": application.job_id,
        "status": application.status,
        "source": application.source,
        "created": created,
    }


@router.get("/applications")
def applications(request: Request, user: CompleteMarketplaceUser, session: SessionDependency):
    links = list(
        session.scalars(
            select(MarketplaceApplicationLink)
            .where(MarketplaceApplicationLink.user_id == user.id)
            .order_by(MarketplaceApplicationLink.created_at.desc())
        )
    )
    result = []
    screening_enabled = _screening_enabled(request)
    candidate_share_summary = None
    if screening_enabled:
        from app.api.basic.staff_screening import _candidate_share_summary

        candidate_share_summary = _candidate_share_summary
    for link in links:
        set_rls_organization(session, link.organization_id)
        application = session.scalar(
            select(AtsApplication).where(
                AtsApplication.organization_id == link.organization_id,
                AtsApplication.id == link.application_id,
            )
        )
        offers = list(
            session.scalars(
                select(AtsOffer)
                .where(
                    AtsOffer.organization_id == link.organization_id,
                    AtsOffer.application_id == link.application_id,
                    AtsOffer.status.in_(CANDIDATE_VISIBLE_OFFER_STATUSES),
                    AtsOffer.sent_at.is_not(None),
                )
                .order_by(AtsOffer.version.desc())
            )
        )
        interviews = list(
            session.scalars(
                select(AtsInterview)
                .where(
                    AtsInterview.organization_id == link.organization_id,
                    AtsInterview.application_id == link.application_id,
                )
                .order_by(AtsInterview.created_at.desc())
            )
        )
        result.append(
            {
                "id": application.id,
                "organization_id": application.organization_id,
                "job_id": application.job_id,
                "job": {
                    "id": link.listing_id,
                    "title": link.listing_title,
                    "organization_name": link.organization_name,
                    "location": link.listing_location,
                    "employment_type": link.employment_type,
                    "published_at": _utc_iso_z(link.published_at),
                },
                "status": application.status,
                "source": application.source,
                "candidate_consent_status": application.candidate_consent_status,
                "version": application.version,
                "offers": [
                    _candidate_offer_row(session, item, screening_enabled=screening_enabled)
                    for item in offers
                ],
                "interviews": [
                    {
                        "id": item.id,
                        "scheduled_at": item.scheduled_at,
                        "timezone": item.timezone,
                        "location_or_link": item.location_or_link,
                        "status": item.status,
                        "candidate_proposed_at": item.candidate_proposed_at,
                        "candidate_proposal_note": item.candidate_proposal_note,
                    }
                    for item in interviews
                ],
                "screening": (
                    candidate_share_summary(session, application.id, user.id)
                    if candidate_share_summary is not None
                    else None
                ),
            }
        )
    return result


@router.post("/applications/{application_id}/withdraw")
def withdraw(
    application_id: UUID,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    link = session.scalar(
        select(MarketplaceApplicationLink).where(
            MarketplaceApplicationLink.user_id == user.id,
            MarketplaceApplicationLink.application_id == application_id,
        )
    )
    if link is None:
        raise HTTPException(404, "Application not found")
    set_rls_organization(session, link.organization_id)
    application = _application(session, link.organization_id, application_id, lock=True)
    _enforce_lifecycle(require_candidate_withdrawal, application.status)
    application.status = "withdrawn"
    application.version += 1
    if _screening_enabled(request):
        revoked_at = datetime.now(UTC)
        for share in session.scalars(
            select(StaffScreeningApplicationShare)
            .where(
                StaffScreeningApplicationShare.application_id == application.id,
                StaffScreeningApplicationShare.candidate_user_id == user.id,
                StaffScreeningApplicationShare.revoked_at.is_(None),
            )
            .order_by(StaffScreeningApplicationShare.id)
            .with_for_update()
        ):
            share.revoked_at = revoked_at
    session.add(
        AtsEvent(
            organization_id=link.organization_id,
            actor_user_id=user.id,
            event_type="marketplace.application_withdrawn",
            entity_type="application",
            entity_id=application.id,
        )
    )
    commit_or_conflict(session)
    return {"id": application.id, "status": application.status, "version": application.version}


@router.post("/applications/{application_id}/offers/{offer_id}/decision")
def candidate_offer_decision(
    application_id: UUID,
    offer_id: UUID,
    payload: CandidateOfferDecision,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    if payload.decision not in {"accepted", "declined"}:
        raise HTTPException(422, "Decision must be accepted or declined")
    link = session.scalar(
        select(MarketplaceApplicationLink).where(
            MarketplaceApplicationLink.user_id == user.id,
            MarketplaceApplicationLink.application_id == application_id,
        )
    )
    if link is None:
        raise HTTPException(404, "Application not found")
    set_rls_organization(session, link.organization_id)
    application = _application(session, link.organization_id, application_id, lock=True)
    offer = session.scalar(
        select(AtsOffer)
        .where(
            AtsOffer.organization_id == link.organization_id,
            AtsOffer.application_id == application.id,
            AtsOffer.id == offer_id,
        )
        .with_for_update()
    )
    if offer is None:
        raise HTTPException(404, "Offer not found")
    latest = session.scalar(
        select(AtsOffer.id)
        .where(
            AtsOffer.organization_id == link.organization_id,
            AtsOffer.application_id == application.id,
        )
        .order_by(AtsOffer.version.desc())
        .limit(1)
    )
    if offer.id != latest:
        raise HTTPException(409, "Only the current sent offer may receive a decision")
    _enforce_lifecycle(
        require_candidate_offer_decision,
        application.status,
        offer.status,
        payload.decision,
    )
    screening_terms = None
    if _screening_enabled(request):
        snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
        if snapshot is None:
            raise HTTPException(409, "Application has no 0030 screening consent snapshot")
        screening_terms = session.get(AtsOfferScreeningTerms, offer.id)
        if screening_terms is None:
            raise RuntimeError("0030 offer screening terms are missing")
        structured = structured_terms_from_model(screening_terms)
        if not structured_terms_match_application_snapshot(
            pathway=snapshot.pathway,
            driver_declaration=snapshot.driver_declaration_snapshot,
            structured_terms=structured,
        ):
            raise HTTPException(409, "Offer duties exceed the application disclosure")
        expected_digest = offer_terms_digest(
            offer, structured, candidate_id=application.candidate_id
        )
        if screening_terms.terms_digest != expected_digest:
            raise RuntimeError("0030 offer terms digest does not match persisted terms")
        if payload.decision == "accepted":
            driver_ack = screening_terms.driving_requirement != "not_applicable"
            if (
                payload.acknowledged_offer_version != offer.version
                or payload.acknowledged_terms_digest != screening_terms.terms_digest
                or payload.driver_terms_acknowledged is not driver_ack
            ):
                raise HTTPException(409, "Acknowledge the exact current offer terms")
        elif any(
            value is not None
            for value in (
                payload.acknowledged_offer_version,
                payload.acknowledged_terms_digest,
                payload.driver_terms_acknowledged,
            )
        ):
            raise HTTPException(422, "A declined offer cannot include acceptance acknowledgment")
    elif any(
        value is not None
        for value in (
            payload.acknowledged_offer_version,
            payload.acknowledged_terms_digest,
            payload.driver_terms_acknowledged,
        )
    ):
        raise HTTPException(409, "Exact offer acknowledgment is unavailable on this server")
    now = datetime.now(UTC)
    if offer.expires_at is not None:
        expiry = (
            offer.expires_at if offer.expires_at.tzinfo else offer.expires_at.replace(tzinfo=UTC)
        )
        if expiry <= now:
            raise HTTPException(409, "Offer has expired")
    offer.status = payload.decision
    offer.terminal_at = now
    if payload.decision == "accepted":
        offer.accepted_at = now
        application.status = "accepted"
    else:
        application.status = "rejected"
    application.version += 1
    if screening_terms is not None and payload.decision == "accepted":
        # The DB guard binds the acknowledgment to an already-accepted exact offer.
        flush_or_conflict(session)
        session.add(
            AtsOfferAcknowledgment(
                organization_id=application.organization_id,
                offer_id=offer.id,
                candidate_user_id=user.id,
                offer_version=offer.version,
                terms_digest=screening_terms.terms_digest,
                driver_terms_acknowledged=bool(payload.driver_terms_acknowledged),
                acknowledged_at=now,
            )
        )
        flush_or_conflict(session)
    session.add(
        AtsEvent(
            organization_id=link.organization_id,
            actor_user_id=user.id,
            event_type=f"marketplace.offer_{payload.decision}",
            entity_type="offer",
            entity_id=offer.id,
        )
    )
    notify_organization_hiring_managers(
        session,
        organization_id=link.organization_id,
        event_key=f"offer-{payload.decision}:{offer.id}",
        title="Candidate responded to offer",
        body=f"The candidate {payload.decision} the employment offer.",
        action_path=f"/jobs/applications/{application.id}",
        action_entity_type="offer",
        action_entity_id=offer.id,
        severity="success" if payload.decision == "accepted" else "warning",
    )
    commit_or_conflict(session)
    return {
        "offer_id": offer.id,
        "offer_status": offer.status,
        "application_id": application.id,
        "application_status": application.status,
    }


@employer_router.get("/candidates")
def search_candidates(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
    city: str | None = None,
):
    manage(context)
    screening_enabled = _screening_enabled(request)
    statement = select(MarketplaceProfile).where(
        MarketplaceProfile.discoverable.is_(True),
        MarketplaceProfile.onboarding_completed_at.is_not(None),
        MarketplaceProfile.date_of_birth.is_not(None),
        MarketplaceProfile.phone.is_not(None),
        MarketplaceProfile.phone != "",
        MarketplaceProfile.user_id.in_(
            select(User.id).where(User.first_name != "", User.last_name != "", User.email != "")
        ),
    )
    if not screening_enabled:
        statement = statement.where(
            MarketplaceProfile.candidate_type.in_(("certified_educator", "student"))
        )
    else:
        statement = statement.where(
            MarketplaceProfile.user_id.in_(select(MarketplaceScreeningProfile.user_id))
        )
    if city:
        statement = statement.where(MarketplaceProfile.city.ilike(f"%{city.strip()}%"))
    return [
        _profile_row(
            item,
            private=False,
            screening=(
                session.get(MarketplaceScreeningProfile, item.user_id)
                if screening_enabled
                else None
            ),
        )
        for item in session.scalars(
            statement.order_by(MarketplaceProfile.updated_at.desc()).limit(100)
        )
    ]


@employer_router.post("/interests", status_code=201)
def express_interest(
    payload: InterestCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    profile = session.get(MarketplaceProfile, payload.profile_user_id)
    profile_user = session.get(User, payload.profile_user_id)
    if (
        profile is None
        or profile_user is None
        or missing_profile_fields(profile_user, profile)
        or not profile.discoverable
        or profile.onboarding_completed_at is None
    ):
        raise HTTPException(404, "Discoverable candidate not found")
    job = _job(session, context.organization.id, payload.job_id)
    if job.status != "open":
        raise HTTPException(409, "Interest requires an open job")
    interest = MarketplaceInterest(
        organization_id=context.organization.id,
        profile_user_id=profile.user_id,
        job_id=job.id,
        message=payload.message,
        created_by_user_id=context.user.id,
    )
    session.add(interest)
    flush_or_conflict(session, "Interest already exists for this candidate and job")
    _event(
        session,
        context,
        "marketplace.interest_requested",
        "marketplace_interest",
        interest.id,
        after={"profile_user_id": str(profile.user_id), "job_id": str(job.id)},
    )
    commit_in_context(session, context)
    return {
        "id": interest.id,
        "profile_user_id": interest.profile_user_id,
        "job_id": interest.job_id,
        "status": interest.status,
        "message": interest.message,
        "created_at": interest.created_at,
    }


@router.get("/interests")
def candidate_interests(user: CompleteMarketplaceUser, session: SessionDependency):
    return [
        {
            "id": row.id,
            "organization_id": row.organization_id,
            "job_id": row.job_id,
            "status": row.status,
            "message": row.message,
            "created_at": row.created_at,
        }
        for row in session.scalars(
            select(MarketplaceInterest)
            .where(MarketplaceInterest.profile_user_id == user.id)
            .order_by(MarketplaceInterest.created_at.desc())
        )
    ]


@router.post("/interests/{interest_id}/decision")
def interest_decision(
    interest_id: UUID,
    payload: InterestDecision,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    if payload.decision not in {"accepted", "declined"}:
        raise HTTPException(422, "Decision must be accepted or declined")
    disclosure = payload.disclosure()
    interest = session.scalar(
        select(MarketplaceInterest)
        .where(
            MarketplaceInterest.id == interest_id, MarketplaceInterest.profile_user_id == user.id
        )
        .with_for_update()
    )
    if interest is None:
        raise HTTPException(404, "Interest not found")
    if interest.status != "requested":
        raise HTTPException(409, "Interest already received a decision")
    interest.status = payload.decision
    interest.responded_at = datetime.now(UTC)
    application = None
    if payload.decision == "accepted":
        listing = session.get(MarketplaceJob, interest.job_id)
        if listing is None:
            raise HTTPException(409, "Job is no longer open")
        application, _ = _apply(
            session,
            user,
            listing,
            source="employer_interest",
            screening_enabled=_screening_enabled(request),
            disclosure=disclosure,
        )
    set_rls_organization(session, interest.organization_id)
    session.add(
        AtsEvent(
            organization_id=interest.organization_id,
            actor_user_id=user.id,
            event_type=f"marketplace.interest_{payload.decision}",
            entity_type="marketplace_interest",
            entity_id=interest.id,
        )
    )
    commit_or_conflict(session)
    return {
        "id": interest.id,
        "status": interest.status,
        "application_id": application.id if application else None,
    }


@employer_router.post("/applications/{application_id}/interviews", status_code=201)
def request_interview(
    application_id: UUID,
    payload: InterviewCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, application_id, lock=True)
    _enforce_lifecycle(
        require_interview_request,
        application.status,
        application.candidate_consent_status,
    )
    if payload.scheduled_at.tzinfo is None:
        raise HTTPException(422, "Interview time must include a timezone")
    if payload.scheduled_at.astimezone(UTC) <= datetime.now(UTC):
        raise HTTPException(422, "Interview time must be in the future")
    pending_interview = session.scalar(
        select(AtsInterview.id).where(
            AtsInterview.organization_id == context.organization.id,
            AtsInterview.application_id == application.id,
            AtsInterview.status.in_(("requested", "candidate_proposed", "confirmed")),
        )
    )
    if pending_interview is not None:
        raise HTTPException(409, "An active interview already exists for this application")
    job = _job(session, context.organization.id, application.job_id)
    timezone = payload.timezone
    if timezone is None and job.facility_id is not None:
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == context.organization.id,
                Facility.id == job.facility_id,
            )
        )
        timezone = facility.timezone if facility is not None else None
    timezone = timezone or context.organization.timezone
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Interview timezone is invalid") from None
    interview = AtsInterview(
        organization_id=context.organization.id,
        application_id=application.id,
        scheduled_at=payload.scheduled_at,
        timezone=timezone,
        location_or_link=payload.location_or_link,
        created_by_user_id=context.user.id,
    )
    session.add(interview)
    flush_or_conflict(session)
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
    )
    if candidate is not None and candidate.claimed_user_id is not None:
        notify_user(
            session,
            user_id=candidate.claimed_user_id,
            organization_id=context.organization.id,
            event_key=f"interview-requested:{interview.id}",
            category="hiring",
            severity="info",
            title="Interview requested",
            body=f"{context.organization.name} requested an interview.",
            action_path=f"/jobs/applications/{application.id}",
            action_entity_type="interview",
            action_entity_id=interview.id,
        )
    application.status = "screening"
    application.version += 1
    _event(
        session,
        context,
        "marketplace.interview_requested",
        "interview",
        interview.id,
        after={"application_id": str(application.id)},
    )
    commit_in_context(session, context)
    return {
        "id": interview.id,
        "application_id": application.id,
        "scheduled_at": interview.scheduled_at,
        "timezone": interview.timezone,
        "location_or_link": interview.location_or_link,
        "status": interview.status,
    }


@employer_router.get("/credential-notifications")
def credential_notifications(
    context: BasicContextDependency,
    session: SessionDependency,
):
    read_marketplace(context)
    rows = list(
        session.scalars(
            select(MarketplaceCredentialNotification)
            .where(MarketplaceCredentialNotification.organization_id == context.organization.id)
            .order_by(MarketplaceCredentialNotification.created_at.desc())
            .limit(100)
        )
    )
    users = (
        {
            user.id: user
            for user in session.scalars(
                select(User).where(User.id.in_({row.candidate_user_id for row in rows}))
            )
        }
        if rows
        else {}
    )
    return [
        {
            "id": row.id,
            "credential_id": row.credential_id,
            "candidate_user_id": row.candidate_user_id,
            "candidate_name": (
                f"{users[row.candidate_user_id].first_name} "
                f"{users[row.candidate_user_id].last_name}"
                if row.candidate_user_id in users
                else "Candidate"
            ),
            "previous_certificate_type": row.previous_certificate_type,
            "certificate_type": row.certificate_type,
            "read_at": row.read_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@employer_router.post("/credential-notifications/{notification_id}/read")
def read_credential_notification(
    notification_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    read_marketplace(context)
    ensure_writable(request)
    row = session.scalar(
        select(MarketplaceCredentialNotification)
        .where(
            MarketplaceCredentialNotification.organization_id == context.organization.id,
            MarketplaceCredentialNotification.id == notification_id,
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Credential notification not found")
    row.read_at = row.read_at or datetime.now(UTC)
    commit_in_context(session, context)
    return {"id": row.id, "read_at": row.read_at}


@router.post("/interviews/{interview_id}/decision")
def interview_decision(
    interview_id: UUID,
    payload: CandidateInterviewDecision,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    if payload.decision not in {"confirmed", "declined", "proposed"}:
        raise HTTPException(422, "Decision must be confirmed, declined, or proposed")
    if payload.decision == "proposed" and payload.proposed_at is None:
        raise HTTPException(422, "A proposed interview time is required")
    if payload.proposed_at is not None:
        if payload.proposed_at.tzinfo is None:
            raise HTTPException(422, "Proposed interview time must include a timezone")
        if payload.proposed_at.astimezone(UTC) <= datetime.now(UTC):
            raise HTTPException(422, "Proposed interview time must be in the future")
    links = list(
        session.scalars(
            select(MarketplaceApplicationLink).where(MarketplaceApplicationLink.user_id == user.id)
        )
    )
    found = None
    application = None
    for link in links:
        set_rls_organization(session, link.organization_id)
        identity = session.scalar(
            select(AtsInterview).where(
                AtsInterview.organization_id == link.organization_id,
                AtsInterview.id == interview_id,
                AtsInterview.application_id == link.application_id,
            )
        )
        if identity is not None:
            application = _application(
                session, link.organization_id, link.application_id, lock=True
            )
            found = session.scalar(
                select(AtsInterview)
                .where(
                    AtsInterview.organization_id == link.organization_id,
                    AtsInterview.id == interview_id,
                    AtsInterview.application_id == application.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if found is None:
                raise HTTPException(409, "Interview changed; reload and retry")
            break
    if found is None:
        raise HTTPException(404, "Interview not found")
    _enforce_lifecycle(
        require_candidate_interview_decision,
        application.status,
        found.status,
        payload.decision,
    )
    found.status = "candidate_proposed" if payload.decision == "proposed" else payload.decision
    found.responded_at = datetime.now(UTC)
    found.candidate_proposed_at = payload.proposed_at if payload.decision == "proposed" else None
    found.candidate_proposal_note = (
        payload.note.strip() if payload.note and payload.decision == "proposed" else None
    )
    application.status = "interview" if payload.decision == "confirmed" else "screening"
    application.version += 1
    session.add(
        AtsEvent(
            organization_id=application.organization_id,
            actor_user_id=user.id,
            event_type=f"marketplace.interview_{payload.decision}",
            entity_type="interview",
            entity_id=found.id,
        )
    )
    notify_organization_hiring_managers(
        session,
        organization_id=application.organization_id,
        event_key=f"interview-{payload.decision}:{found.id}",
        title="Candidate responded to interview",
        body=f"The candidate {payload.decision} the interview request.",
        action_path=f"/jobs/applications/{application.id}",
        action_entity_type="interview",
        action_entity_id=found.id,
    )
    commit_or_conflict(session)
    return {
        "id": found.id,
        "status": found.status,
        "application_id": application.id,
        "application_status": application.status,
        "candidate_proposed_at": found.candidate_proposed_at,
    }


@employer_router.post("/interviews/{interview_id}/proposal-decision")
def employer_interview_proposal_decision(
    interview_id: UUID,
    payload: EmployerProposalDecision,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    manage(context)
    ensure_writable(request)
    if payload.decision not in {"accepted", "declined", "countered"}:
        raise HTTPException(422, "Decision must be accepted, declined, or countered")
    if payload.decision == "countered" and payload.scheduled_at is None:
        raise HTTPException(422, "A counter-proposed interview time is required")
    if payload.scheduled_at is not None:
        if payload.scheduled_at.tzinfo is None:
            raise HTTPException(422, "Counter-proposed interview time must include a timezone")
        if payload.scheduled_at.astimezone(UTC) <= datetime.now(UTC):
            raise HTTPException(422, "Counter-proposed interview time must be in the future")
    if payload.timezone is not None:
        try:
            ZoneInfo(payload.timezone)
        except ZoneInfoNotFoundError:
            raise HTTPException(422, "Interview timezone is invalid") from None
    interview_identity = session.scalar(
        select(AtsInterview).where(
            AtsInterview.organization_id == context.organization.id,
            AtsInterview.id == interview_id,
        )
    )
    if interview_identity is None:
        raise HTTPException(404, "Interview not found")
    application = _application(
        session, context.organization.id, interview_identity.application_id, lock=True
    )
    interview = session.scalar(
        select(AtsInterview)
        .where(
            AtsInterview.organization_id == context.organization.id,
            AtsInterview.id == interview_id,
            AtsInterview.application_id == application.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if interview is None:
        raise HTTPException(409, "Interview changed; reload and retry")
    _enforce_lifecycle(
        require_employer_proposal_decision,
        application.status,
        interview.status,
        has_candidate_proposal=interview.candidate_proposed_at is not None,
        decision=payload.decision,
    )
    if payload.decision == "accepted":
        interview.scheduled_at = interview.candidate_proposed_at
        interview.status = "confirmed"
        application.status = "interview"
    elif payload.decision == "declined":
        interview.status = "proposal_declined"
        application.status = "screening"
    else:
        interview.scheduled_at = payload.scheduled_at
        if payload.timezone:
            interview.timezone = payload.timezone
        if payload.location_or_link and payload.location_or_link.strip():
            interview.location_or_link = payload.location_or_link.strip()
        interview.status = "requested"
        application.status = "screening"
    interview.responded_at = datetime.now(UTC)
    application.version += 1
    _event(
        session,
        context,
        f"marketplace.interview_proposal_{payload.decision}",
        "interview",
        interview.id,
        after={"application_id": str(application.id), "status": interview.status},
    )
    candidate = session.scalar(
        select(AtsCandidate).where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
    )
    if candidate is not None and candidate.claimed_user_id is not None:
        notify_user(
            session,
            user_id=candidate.claimed_user_id,
            organization_id=context.organization.id,
            event_key=f"interview-proposal-{payload.decision}:{interview.id}",
            category="hiring",
            severity="info",
            title="Interview schedule updated",
            body=f"{context.organization.name} {payload.decision} your proposed interview time.",
            action_path=f"/jobs/applications/{application.id}",
            action_entity_type="interview",
            action_entity_id=interview.id,
        )
    commit_in_context(session, context)
    return {
        "id": interview.id,
        "application_id": application.id,
        "scheduled_at": interview.scheduled_at,
        "timezone": interview.timezone,
        "location_or_link": interview.location_or_link,
        "status": interview.status,
        "candidate_proposed_at": interview.candidate_proposed_at,
        "candidate_proposal_note": interview.candidate_proposal_note,
    }
