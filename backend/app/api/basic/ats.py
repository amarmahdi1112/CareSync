"""Invite-only, employer-side applicant tracking with audited lifecycle changes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.basic.common import commit_in_context, ensure_writable, flush_or_conflict
from app.api.basic.dependencies import BasicContext, BasicContextDependency, require_permission
from app.api.dependencies import SessionDependency
from app.basic.hiring_lifecycle import (
    HiringLifecycleViolation,
    require_application_transition,
    require_employer_offer_withdrawal,
    require_job_transition,
    require_offer_creation,
    require_provisioning,
)
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
from app.basic.hiring_repository import (
    require_hiring_version as _check_version,
)
from app.basic.models import (
    AtsApplication,
    AtsApplicationScreeningSnapshot,
    AtsCandidate,
    AtsInterview,
    AtsJob,
    AtsJobScreeningTerms,
    AtsOffer,
    AtsOfferAcknowledgment,
    AtsOfferScreeningTerms,
    AtsStaffProvisioning,
    Facility,
    MarketplaceScreeningProfile,
    MembershipRoomAssignment,
    OrganizationMembership,
    Role,
)
from app.basic.notifications import notify_user
from app.basic.schemas import (
    AtsApplicationResponse,
    AtsApplicationStageChange,
    AtsCandidateResponse,
    AtsCertificationReview,
    AtsJobCreate,
    AtsJobPatch,
    AtsJobResponse,
    AtsJobStatusChange,
    AtsOfferCreateAndSend,
    AtsOfferDecision,
    AtsOfferResponse,
    AtsProvisionStaffRequest,
    AtsProvisionStaffResponse,
    AtsStructuredTerms,
    AtsWorkspaceResponse,
)
from app.basic.staff_screening_terms import (
    STRUCTURED_TERM_FIELDS,
    default_structured_terms,
    driver_declaration_snapshot,
    offer_terms_digest,
    structured_terms_from_model,
    structured_terms_from_payload,
    structured_terms_match_application_snapshot,
)

router = APIRouter(prefix="/ats", tags=["basic applicant tracking"])
AtsReadContext = require_permission("ats:read")
AtsManageContext = require_permission("ats:manage")
AtsHireContext = require_permission("ats:hire")


def _enforce_lifecycle(rule, *args, **kwargs) -> None:
    try:
        rule(*args, **kwargs)
    except HiringLifecycleViolation as error:
        raise HTTPException(error.status_code, error.detail) from error


def _validate_facility(session, organization_id: UUID, facility_id: UUID | None) -> None:
    if (
        facility_id is not None
        and session.scalar(
            select(Facility.id).where(
                Facility.organization_id == organization_id, Facility.id == facility_id
            )
        )
        is None
    ):
        raise HTTPException(404, "Facility not found")


def _screening_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "staff_screening_pathways_enabled", False))


def _split_structured_payload(payload, *, exclude: set[str] | None = None) -> tuple[dict, dict]:
    excluded = (exclude or set()) | set(STRUCTURED_TERM_FIELDS)
    legacy = payload.model_dump(exclude=excluded, exclude_unset=False)
    return legacy, structured_terms_from_payload(payload)


def _require_supported_terms(request: Request, structured: dict) -> None:
    if not _screening_enabled(request) and structured != default_structured_terms():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "staff_screening_pathways_unavailable"},
        )


def _job_response(session, job: AtsJob, *, screening_enabled: bool) -> dict:
    result = AtsJobResponse.model_validate(job).model_dump()
    if screening_enabled:
        terms = session.get(AtsJobScreeningTerms, job.id)
        if terms is None:
            raise RuntimeError("0030 job screening terms are missing")
        result.update(structured_terms_from_model(terms))
    return result


def _offer_response(session, offer: AtsOffer, *, screening_enabled: bool) -> dict:
    result = AtsOfferResponse.model_validate(offer).model_dump()
    if screening_enabled:
        terms = session.get(AtsOfferScreeningTerms, offer.id)
        if terms is None:
            raise RuntimeError("0030 offer screening terms are missing")
        result.update(structured_terms_from_model(terms))
        result["terms_digest"] = terms.terms_digest
    return result


def _candidate_response(session, candidate: AtsCandidate, *, screening_enabled: bool) -> dict:
    result = AtsCandidateResponse.model_validate(candidate).model_dump()
    if screening_enabled and candidate.claimed_user_id is not None:
        profile = session.get(MarketplaceScreeningProfile, candidate.claimed_user_id)
        if profile is not None:
            result["pathway"] = profile.pathway
            result["driver_declaration"] = driver_declaration_snapshot(profile)
            result["operational_driver_ready"] = False
    return result


def _require_application_screening_snapshot(
    session, request: Request, application: AtsApplication
) -> AtsApplicationScreeningSnapshot | None:
    if not _screening_enabled(request):
        return None
    snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
    if snapshot is None:
        raise HTTPException(
            409,
            detail={
                "code": "application_screening_consent_required",
                "message": "The candidate must complete the 0030 application disclosure first",
            },
        )
    return snapshot


def _require_offer_snapshot_compatibility(
    session,
    request: Request,
    application: AtsApplication,
    structured: dict,
) -> None:
    snapshot = _require_application_screening_snapshot(session, request, application)
    if snapshot is None:
        return
    if not structured_terms_match_application_snapshot(
        pathway=snapshot.pathway,
        driver_declaration=snapshot.driver_declaration_snapshot,
        structured_terms=structured,
    ):
        raise HTTPException(
            409,
            detail={
                "code": "offer_outside_application_disclosure",
                "message": (
                    "Offer duties do not match the candidate's immutable application "
                    "pathway and driver declaration"
                ),
            },
        )


@router.get("/workspace", response_model=AtsWorkspaceResponse)
def workspace(request: Request, context: BasicContextDependency, session: SessionDependency):
    AtsReadContext(context)
    org = context.organization.id
    screening_enabled = _screening_enabled(request)
    jobs = list(
        session.scalars(
            select(AtsJob).where(AtsJob.organization_id == org).order_by(AtsJob.created_at.desc())
        )
    )
    offers = list(
        session.scalars(
            select(AtsOffer)
            .where(AtsOffer.organization_id == org)
            .order_by(AtsOffer.application_id, AtsOffer.version.desc())
        )
    )
    candidates = list(
        session.scalars(
            select(AtsCandidate)
            .where(AtsCandidate.organization_id == org)
            .order_by(AtsCandidate.created_at.desc())
        )
    )
    return AtsWorkspaceResponse(
        screening_schema_version="0030" if screening_enabled else None,
        jobs=[_job_response(session, item, screening_enabled=screening_enabled) for item in jobs],
        candidates=[
            _candidate_response(session, item, screening_enabled=screening_enabled)
            for item in candidates
        ],
        applications=list(
            session.scalars(
                select(AtsApplication)
                .where(AtsApplication.organization_id == org)
                .order_by(AtsApplication.created_at.desc())
            )
        ),
        offers=[
            _offer_response(session, item, screening_enabled=screening_enabled) for item in offers
        ],
        interviews=list(
            session.scalars(
                select(AtsInterview)
                .where(AtsInterview.organization_id == org)
                .order_by(AtsInterview.created_at.desc())
            )
        ),
    )


@router.post("/jobs", response_model=AtsJobResponse, status_code=201)
def create_job(
    payload: AtsJobCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    _validate_facility(session, context.organization.id, payload.facility_id)
    legacy, structured = _split_structured_payload(payload)
    _require_supported_terms(request, structured)
    job = AtsJob(
        organization_id=context.organization.id,
        created_by_user_id=context.user.id,
        **legacy,
    )
    session.add(job)
    flush_or_conflict(session)
    if _screening_enabled(request):
        session.add(
            AtsJobScreeningTerms(
                job_id=job.id,
                organization_id=context.organization.id,
                **structured,
                version=1,
            )
        )
        flush_or_conflict(session)
    _event(session, context, "job.created", "job", job.id, after={"status": job.status})
    commit_in_context(session, context)
    return _job_response(session, job, screening_enabled=_screening_enabled(request))


@router.patch("/jobs/{job_id}", response_model=AtsJobResponse)
def update_job(
    job_id: UUID,
    payload: AtsJobPatch,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    job = _job(session, context.organization.id, job_id, lock=True)
    _check_version(job.version, payload.expected_version)
    if job.status not in {"draft", "open", "paused"}:
        raise HTTPException(409, "Closed jobs may not be edited")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    structured_patch = {
        field: values.pop(field) for field in STRUCTURED_TERM_FIELDS if field in values
    }
    screening_enabled = _screening_enabled(request)
    if structured_patch and not screening_enabled:
        candidate_terms = default_structured_terms() | structured_patch
        validated = AtsStructuredTerms(**candidate_terms)
        if structured_terms_from_payload(validated) != default_structured_terms():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "staff_screening_pathways_unavailable"},
            )
    if "facility_id" in values:
        _validate_facility(session, context.organization.id, values["facility_id"])
    before = {"version": job.version}
    for key, value in values.items():
        setattr(job, key, value)
    if screening_enabled:
        terms = session.get(AtsJobScreeningTerms, job.id)
        if terms is None:
            raise RuntimeError("0030 job screening terms are missing")
        if structured_patch:
            merged = structured_terms_from_model(terms) | structured_patch
            validated = structured_terms_from_payload(AtsStructuredTerms(**merged))
            for key, value in validated.items():
                setattr(terms, key, value)
            terms.version += 1
    job.version += 1
    # The public projection is maintained by an ``ats_jobs`` trigger. Flush
    # the canonical change before appending its realtime event so the 0038
    # public catalog outbox observes the resulting status/version atomically.
    flush_or_conflict(session)
    _event(
        session,
        context,
        "job.updated",
        "job",
        job.id,
        before=before,
        after={"version": job.version},
    )
    commit_in_context(session, context)
    return _job_response(session, job, screening_enabled=screening_enabled)


@router.post("/jobs/{job_id}/status", response_model=AtsJobResponse)
def transition_job(
    job_id: UUID,
    payload: AtsJobStatusChange,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    job = _job(session, context.organization.id, job_id, lock=True)
    _check_version(job.version, payload.expected_version)
    _enforce_lifecycle(require_job_transition, job.status, payload.status)
    before = {"status": job.status, "version": job.version}
    now = datetime.now(UTC)
    job.status = payload.status
    job.version += 1
    if payload.status == "open":
        job.published_at, job.closed_at = now, None
    elif payload.status == "closed":
        job.closed_at = now
    # See ``update_job``: projection mutation must precede the bound realtime
    # event inside the same transaction.
    flush_or_conflict(session)
    _event(
        session,
        context,
        "job.status_changed",
        "job",
        job.id,
        reason=payload.reason,
        before=before,
        after={"status": job.status, "version": job.version},
    )
    commit_in_context(session, context)
    return _job_response(session, job, screening_enabled=_screening_enabled(request))


@router.post("/applications/{application_id}/stage", response_model=AtsApplicationResponse)
def transition_application(
    application_id: UUID,
    payload: AtsApplicationStageChange,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, application_id, lock=True)
    _require_application_screening_snapshot(session, request, application)
    _check_version(application.version, payload.expected_version)
    if _screening_enabled(request) and payload.status == "withdrawn":
        raise HTTPException(403, "Only the candidate may withdraw a 0030 application")
    if (
        _screening_enabled(request)
        and application.status == "offer"
        and payload.status == "rejected"
    ):
        raise HTTPException(409, "Withdraw the current offer before rejecting the application")
    _enforce_lifecycle(
        require_application_transition,
        "employer",
        application.status,
        payload.status,
    )
    before = {"status": application.status, "version": application.version}
    application.status = payload.status
    application.stage_notes = payload.reason
    application.version += 1
    _event(
        session,
        context,
        "application.stage_changed",
        "application",
        application.id,
        reason=payload.reason,
        before=before,
        after={"status": application.status, "version": application.version},
    )
    if application.status in {"rejected", "withdrawn"}:
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
                event_key=f"application-{application.status}:{application.id}:{application.version}",
                category="hiring",
                severity="warning",
                title="Application status updated",
                body="An employer updated the status of your job application.",
                action_path=f"/jobs/applications/{application.id}",
                action_entity_type="application",
                action_entity_id=application.id,
            )
    commit_in_context(session, context)
    return application


def _offer_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, "Offer expiry must include a timezone")
    normalized = value.astimezone(UTC)
    if normalized <= datetime.now(UTC):
        raise HTTPException(422, "Offer expiry must be in the future")
    return normalized


def _same_offer_command(
    session,
    offer: AtsOffer,
    application_id: UUID,
    payload: AtsOfferCreateAndSend,
    *,
    screening_enabled: bool,
) -> bool:
    actual_expiry = offer.expires_at
    if actual_expiry is not None and actual_expiry.tzinfo is None:
        actual_expiry = actual_expiry.replace(tzinfo=UTC)
    expected_expiry = payload.expires_at
    if expected_expiry is not None:
        if expected_expiry.tzinfo is None:
            return False
        expected_expiry = expected_expiry.astimezone(UTC)
    same_core = (
        offer.application_id == application_id
        and offer.position_title == payload.position_title
        and offer.start_date == payload.start_date
        and offer.compensation == payload.compensation
        and offer.terms == payload.terms
        and actual_expiry == expected_expiry
    )
    if not same_core:
        return False
    expected_terms = structured_terms_from_payload(payload)
    if not screening_enabled:
        return expected_terms == default_structured_terms()
    terms = session.get(AtsOfferScreeningTerms, offer.id)
    return terms is not None and structured_terms_from_model(terms) == expected_terms


@router.post(
    "/applications/{application_id}/offers/send",
    response_model=AtsOfferResponse,
    status_code=201,
)
def create_and_send_offer(
    application_id: UUID,
    payload: AtsOfferCreateAndSend,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    """Create and publish one offer version as a single idempotent transaction."""

    AtsManageContext(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, application_id, lock=True)
    _require_application_screening_snapshot(session, request, application)
    existing = session.scalar(
        select(AtsOffer)
        .where(
            AtsOffer.organization_id == context.organization.id,
            AtsOffer.client_operation_id == payload.client_operation_id,
        )
        .with_for_update()
    )
    if existing is not None:
        if not _same_offer_command(
            session,
            existing,
            application_id,
            payload,
            screening_enabled=_screening_enabled(request),
        ):
            raise HTTPException(409, "Operation identifier was used for another offer command")
        return _offer_response(session, existing, screening_enabled=_screening_enabled(request))

    _check_version(application.version, payload.expected_application_version)
    _enforce_lifecycle(require_offer_creation, application.status)
    expires_at = _offer_expiry(payload.expires_at)
    structured = structured_terms_from_payload(payload)
    _require_supported_terms(request, structured)
    _require_offer_snapshot_compatibility(session, request, application, structured)
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

    now = datetime.now(UTC)
    if previous and previous.status != "withdrawn":
        previous.status = "superseded"
        previous.terminal_at = now
    version = (previous.version + 1) if previous else 1
    offer = AtsOffer(
        organization_id=context.organization.id,
        application_id=application.id,
        version=version,
        client_operation_id=payload.client_operation_id,
        status="sent",
        sent_at=now,
        position_title=payload.position_title,
        start_date=payload.start_date,
        compensation=payload.compensation,
        terms=payload.terms,
        expires_at=expires_at,
        created_by_user_id=context.user.id,
    )
    session.add(offer)
    flush_or_conflict(session)
    if _screening_enabled(request):
        terms = AtsOfferScreeningTerms(
            offer_id=offer.id,
            organization_id=context.organization.id,
            offer_version=offer.version,
            **structured,
            terms_digest=offer_terms_digest(
                offer, structured, candidate_id=application.candidate_id
            ),
        )
        session.add(terms)
        flush_or_conflict(session)
    application.status = "offer"
    application.version += 1

    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
        .with_for_update()
    )
    if candidate is not None and candidate.claimed_user_id is not None:
        notify_user(
            session,
            user_id=candidate.claimed_user_id,
            organization_id=context.organization.id,
            event_key=f"offer-sent:{offer.id}:{offer.version}",
            category="hiring",
            severity="info",
            title="New employment offer",
            body=f"An offer for {offer.position_title} is ready for your review.",
            action_path=f"/jobs/applications/{application.id}",
            action_entity_type="offer",
            action_entity_id=offer.id,
        )
    _event(
        session,
        context,
        "offer.created",
        "offer",
        offer.id,
        after={
            "version": version,
            "application_id": str(application.id),
            "client_operation_id": str(payload.client_operation_id),
        },
    )
    _event(session, context, "offer.sent", "offer", offer.id, after={"version": version})
    commit_in_context(session, context)
    return _offer_response(session, offer, screening_enabled=_screening_enabled(request))


@router.post("/offers/{offer_id}/decision", response_model=AtsOfferResponse)
def decide_offer(
    offer_id: UUID,
    payload: AtsOfferDecision,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    if payload.decision != "withdrawn":
        raise HTTPException(403, "Only the candidate may accept or decline an offer")
    offer_identity = _offer(session, context.organization.id, offer_id)
    application = _application(
        session, context.organization.id, offer_identity.application_id, lock=True
    )
    offer = _offer(session, context.organization.id, offer_id, lock=True)
    if offer.application_id != application.id:
        raise HTTPException(409, "Offer application changed; reload and retry")
    _enforce_lifecycle(
        require_employer_offer_withdrawal,
        application.status,
        offer.status,
    )
    latest_offer_id = session.scalar(
        select(AtsOffer.id)
        .where(
            AtsOffer.organization_id == context.organization.id,
            AtsOffer.application_id == application.id,
        )
        .order_by(AtsOffer.version.desc())
        .limit(1)
    )
    if latest_offer_id != offer.id:
        raise HTTPException(409, "Only the current offer version may be withdrawn")
    now = datetime.now(UTC)
    offer.status = payload.decision
    offer.terminal_at = now
    application.status = "interview"
    application.version += 1
    _event(
        session,
        context,
        f"offer.{payload.decision}",
        "offer",
        offer.id,
        reason=payload.reason,
        after={"application_status": application.status},
    )
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
        .with_for_update()
    )
    if candidate is not None and candidate.claimed_user_id is not None:
        notify_user(
            session,
            user_id=candidate.claimed_user_id,
            organization_id=context.organization.id,
            event_key=f"offer-withdrawn:{offer.id}:{offer.version}",
            category="hiring",
            severity="warning",
            title="Employment offer updated",
            body="An employer withdrew an employment offer. Open CareSync for details.",
            action_path=f"/jobs/applications/{application.id}",
            action_entity_type="offer",
            action_entity_id=offer.id,
        )
    commit_in_context(session, context)
    return _offer_response(session, offer, screening_enabled=_screening_enabled(request))


@router.post("/candidates/{candidate_id}/certification-review", response_model=AtsCandidateResponse)
def review_certification(
    candidate_id: UUID,
    payload: AtsCertificationReview,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsManageContext(context)
    ensure_writable(request)
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == candidate_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    if payload.status == "verified" and not candidate.certification_number:
        raise HTTPException(409, "A certification number is required before verification")
    if (
        payload.status == "verified"
        and candidate.certification_expiry_date is not None
        and candidate.certification_expiry_date < datetime.now(UTC).date()
    ):
        raise HTTPException(409, "An expired certification cannot be verified")
    candidate.certification_verification_status = payload.status
    candidate.certification_review_note = payload.reason
    if payload.status == "verified":
        candidate.certification_verified_at = datetime.now(UTC)
        candidate.certification_verified_by_user_id = context.user.id
        if candidate.onboarding_status == "submitted":
            candidate.onboarding_status = "complete"
    else:
        candidate.certification_verified_at = None
        candidate.certification_verified_by_user_id = None
    _event(
        session,
        context,
        "candidate.certification_reviewed",
        "candidate",
        candidate.id,
        reason=payload.reason,
        after={"status": payload.status},
    )
    commit_in_context(session, context)
    return candidate


def provision_accepted_candidate(
    session,
    context: BasicContext,
    application: AtsApplication,
    operation_id: UUID,
    *,
    screening_enabled: bool = False,
) -> AtsStaffProvisioning:
    existing_operation = session.scalar(
        select(AtsStaffProvisioning).where(
            AtsStaffProvisioning.organization_id == context.organization.id,
            AtsStaffProvisioning.operation_id == operation_id,
        )
    )
    if existing_operation is not None:
        if existing_operation.application_id != application.id:
            raise HTTPException(409, "Operation identifier was used for another application")
        return existing_operation
    existing_application = session.scalar(
        select(AtsStaffProvisioning).where(
            AtsStaffProvisioning.organization_id == context.organization.id,
            AtsStaffProvisioning.application_id == application.id,
        )
    )
    if existing_application is not None:
        return existing_application
    candidate = session.scalar(
        select(AtsCandidate)
        .where(
            AtsCandidate.organization_id == context.organization.id,
            AtsCandidate.id == application.candidate_id,
        )
        .with_for_update()
    )
    if candidate is None or candidate.claimed_user_id is None:
        raise HTTPException(409, "Candidate must claim a verified user identity first")
    if screening_enabled:
        snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
        if snapshot is None:
            raise HTTPException(409, "Application has no 0030 screening consent snapshot")
        if snapshot.pathway in {"driver", "student_educator"}:
            code = (
                "driver_role_provisioning_not_available"
                if snapshot.pathway == "driver"
                else "student_role_provisioning_not_available"
            )
            raise HTTPException(
                409,
                detail={
                    "code": code,
                    "message": (
                        "This pathway requires a dedicated least-privilege role before access"
                    ),
                },
            )
        if candidate.certification_verification_status != "verified" or (
            candidate.certification_expiry_date is not None
            and candidate.certification_expiry_date < datetime.now(UTC).date()
        ):
            raise HTTPException(
                409,
                detail={
                    "code": "verified_ece_credential_required",
                    "message": "An employer-verified current ECE credential is required",
                },
            )
        from app.api.basic.staff_screening import application_screening_reviews_accepted

        if not application_screening_reviews_accepted(
            session,
            organization_id=context.organization.id,
            application_id=application.id,
            lock_for_provisioning=True,
        ):
            raise HTTPException(409, "Current CRC and VSS shares require accepted human review")
        accepted_offer = session.scalar(
            select(AtsOffer)
            .where(
                AtsOffer.organization_id == context.organization.id,
                AtsOffer.application_id == application.id,
                AtsOffer.status == "accepted",
            )
            .order_by(AtsOffer.version.desc())
            .limit(1)
        )
        if accepted_offer is None:
            raise HTTPException(409, "An exact accepted 0030 offer is required")
        terms = session.get(AtsOfferScreeningTerms, accepted_offer.id)
        acknowledgment = session.scalar(
            select(AtsOfferAcknowledgment).where(
                AtsOfferAcknowledgment.organization_id == context.organization.id,
                AtsOfferAcknowledgment.offer_id == accepted_offer.id,
                AtsOfferAcknowledgment.candidate_user_id == snapshot.candidate_user_id,
            )
        )
        if (
            terms is None
            or acknowledgment is None
            or acknowledgment.offer_version != accepted_offer.version
            or acknowledgment.offer_version != terms.offer_version
            or acknowledgment.terms_digest != terms.terms_digest
        ):
            raise HTTPException(409, "Exact accepted offer acknowledgment is missing")
    _enforce_lifecycle(require_provisioning, application.status)
    educator = session.scalar(
        select(Role).where(
            Role.organization_id == context.organization.id,
            Role.key == "educator",
        )
    )
    if educator is None:
        raise HTTPException(409, "Educator role is unavailable")
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.user_id == candidate.claimed_user_id,
        )
    )
    created = False
    if membership is None:
        membership = OrganizationMembership(
            organization_id=context.organization.id,
            user_id=candidate.claimed_user_id,
            role_id=educator.id,
            status="active",
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        flush_or_conflict(session)
        created = True
    elif membership.role_id != educator.id or membership.status != "active":
        raise HTTPException(
            409, "Existing organization access is not an active educator membership"
        )
    elif (
        session.scalar(
            select(MembershipRoomAssignment.id).where(
                MembershipRoomAssignment.organization_id == context.organization.id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
            )
        )
        is not None
    ):
        raise HTTPException(
            409,
            "Existing educator already has room access; review access before provisioning",
        )
    provisioning = AtsStaffProvisioning(
        organization_id=context.organization.id,
        application_id=application.id,
        membership_id=membership.id,
        candidate_user_id=candidate.claimed_user_id,
        role_id=educator.id,
        operation_id=operation_id,
        provisioned_by_user_id=context.user.id,
        membership_created=created,
    )
    session.add(provisioning)
    application.status = "hired"
    application.hire_handoff_requested_at = datetime.now(UTC)
    application.hire_handoff_requested_by_user_id = context.user.id
    application.version += 1
    _event(
        session,
        context,
        "hire.staff_provisioned",
        "application",
        application.id,
        after={
            "membership_id": str(membership.id),
            "membership_created": created,
            "assigned_room_ids": [],
        },
    )
    notify_user(
        session,
        user_id=provisioning.candidate_user_id,
        organization_id=context.organization.id,
        event_key=f"staff-provisioned:{application.id}",
        category="hiring",
        severity="success",
        title="You have been hired",
        body=f"Your staff access to {context.organization.name} is ready.",
        action_path="/today",
        action_entity_type="application",
        action_entity_id=application.id,
    )
    return provisioning


@router.post(
    "/applications/{application_id}/provision-staff",
    response_model=AtsProvisionStaffResponse,
)
def provision_staff(
    application_id: UUID,
    payload: AtsProvisionStaffRequest,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    AtsHireContext(context)
    ensure_writable(request)
    application = _application(session, context.organization.id, application_id, lock=True)
    existing = session.scalar(
        select(AtsStaffProvisioning).where(
            AtsStaffProvisioning.organization_id == context.organization.id,
            AtsStaffProvisioning.application_id == application.id,
        )
    )
    if existing is None:
        _check_version(application.version, payload.expected_version)
    provisioning = provision_accepted_candidate(
        session,
        context,
        application,
        payload.operation_id,
        screening_enabled=_screening_enabled(request),
    )
    commit_in_context(session, context)
    return AtsProvisionStaffResponse(
        application=application,
        membership_id=provisioning.membership_id,
        user_id=provisioning.candidate_user_id,
        membership_created=provisioning.membership_created,
        provisioning_id=provisioning.id,
    )
