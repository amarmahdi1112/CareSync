"""0030 candidate screening, confidential sharing, and employer human review."""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api.basic.common import (
    commit_in_context,
    commit_or_conflict,
    ensure_writable,
    flush_or_conflict,
)
from app.api.basic.dependencies import BasicContextDependency, BasicUser, require_permission
from app.api.dependencies import SessionDependency
from app.basic.family_evidence_vault import ScannerUnavailable
from app.basic.hiring_repository import get_hiring_application as _application
from app.basic.models import (
    AtsApplicationScreeningSnapshot,
    AtsEvent,
    AtsJobScreeningTerms,
    MarketplaceApplicationLink,
    MarketplaceOnboardingState,
    MarketplaceProfile,
    MarketplaceScreeningProfile,
    StaffScreeningApplicationShare,
    StaffScreeningCandidateConfirmation,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    StaffScreeningEmployerReview,
    User,
)
from app.basic.notifications import notify_user
from app.basic.security import set_rls_organization
from app.basic.staff_screening_schemas import (
    EmployerScreeningReviewCreate,
    ScreeningDocumentConfirm,
    ScreeningDocumentResponse,
    ScreeningProfileResponse,
    ScreeningProfileUpdate,
    ScreeningShareUpdate,
)
from app.basic.staff_screening_terms import (
    default_structured_terms,
    driver_declaration_snapshot,
    screening_profile_complete,
    structured_terms_from_model,
)
from app.basic.staff_screening_vault import (
    delete_screening_object,
    read_encrypted_screening_object,
    store_encrypted_screening_upload,
)

candidate_router = APIRouter(prefix="/marketplace", tags=["candidate staff screening"])
employer_router = APIRouter(prefix="/ats", tags=["employer staff screening"])
ScreeningReadContext = require_permission("ats:read")
ScreeningManageContext = require_permission("ats:manage")
SCREENING_COVERAGE = frozenset({"criminal_record_check", "vulnerable_sector_search"})


class AmbiguousStaffScreeningCommit(RuntimeError):
    """The database connection failed while the document commit outcome was unknowable."""


def _require_0030(request: Request) -> None:
    if not bool(getattr(request.app.state, "staff_screening_pathways_enabled", False)):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "staff_screening_pathways_unavailable"},
        )


def _require_screening_evidence_upload(request: Request) -> None:
    if not bool(getattr(request.app.state, "staff_screening_evidence_upload_available", False)):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "staff_screening_evidence_upload_unavailable"},
        )


def _driver_declaration(profile: MarketplaceScreeningProfile) -> dict:
    declaration = driver_declaration_snapshot(profile)
    declaration.pop("operational_driver_ready")
    return declaration


def _profile_row(profile: MarketplaceScreeningProfile) -> dict:
    return ScreeningProfileResponse(
        user_id=profile.user_id,
        pathway=profile.pathway,
        driver_declaration=_driver_declaration(profile),
        screening_profile_complete=screening_profile_complete(profile),
        operational_driver_ready=False,
        version=profile.version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    ).model_dump()


def _version_row(session, version: StaffScreeningDocumentVersion, *, document_id: UUID) -> dict:
    confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
    server_date = date.today()
    return {
        "id": version.id,
        "version_number": version.version_number,
        "declared_coverage": list(version.declared_coverage or []),
        "original_filename": version.original_filename,
        "media_type": version.media_type,
        "size_bytes": version.byte_size,
        "sha256": version.content_sha256,
        "subject_name": confirmation.subject_name if confirmation else None,
        "account_name_snapshot": (confirmation.account_name_snapshot if confirmation else None),
        "subject_name_match": confirmation.subject_name_match if confirmation else None,
        "mismatch_resolution": confirmation.mismatch_resolution if confirmation else None,
        "issue_date": confirmation.issue_date if confirmation else None,
        "expiry_date": confirmation.expiry_date if confirmation else None,
        "candidate_confirmed_at": (confirmation.candidate_confirmed_at if confirmation else None),
        "evidence_valid": bool(
            confirmation is not None
            and (confirmation.expiry_date is None or confirmation.expiry_date >= server_date)
        ),
        "validity_as_of": server_date,
        "created_at": version.created_at,
        "content_url": (
            f"/api/v1/marketplace/screening-documents/{document_id}/versions/{version.id}/content"
        ),
    }


def _document_row(session, document: StaffScreeningDocument) -> ScreeningDocumentResponse:
    versions = list(
        session.scalars(
            select(StaffScreeningDocumentVersion)
            .where(
                StaffScreeningDocumentVersion.document_id == document.id,
                StaffScreeningDocumentVersion.user_id == document.user_id,
            )
            .order_by(StaffScreeningDocumentVersion.version_number.desc())
        )
    )
    version = next(
        (item for item in versions if item.version_number == document.current_version_number),
        None,
    )
    if version is None:
        raise RuntimeError("Staff screening current version is missing")
    return ScreeningDocumentResponse(
        id=document.id,
        status=document.status,
        current_version_number=document.current_version_number,
        declared_coverage=list(version.declared_coverage or []),
        current_version=_version_row(session, version, document_id=document.id),
        versions=[_version_row(session, item, document_id=document.id) for item in versions],
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _owned_document(
    session, user_id: UUID, document_id: UUID, *, lock: bool = False
) -> StaffScreeningDocument:
    statement = select(StaffScreeningDocument).where(
        StaffScreeningDocument.id == document_id,
        StaffScreeningDocument.user_id == user_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Screening document not found")
    return value


def _parse_coverage(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        raise HTTPException(422, "declared_coverage must be a JSON array") from None
    if (
        not isinstance(decoded, list)
        or not decoded
        or any(not isinstance(item, str) or item not in SCREENING_COVERAGE for item in decoded)
        or len(set(decoded)) != len(decoded)
    ):
        raise HTTPException(
            422,
            "declared_coverage must contain unique criminal-record and/or vulnerable-sector values",
        )
    return decoded


def _normalized_person_name(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value).casefold()
        if character.isalnum()
    )


def _commit_screening_version(session) -> None:
    try:
        commit_or_conflict(session)
    except DBAPIError as error:
        if error.connection_invalidated:
            raise AmbiguousStaffScreeningCommit from error
        session.rollback()
        raise


@candidate_router.get("/screening-profile", response_model=ScreeningProfileResponse)
def screening_profile(request: Request, user: BasicUser, session: SessionDependency):
    _require_0030(request)
    value = session.get(MarketplaceScreeningProfile, user.id)
    if value is None:
        raise HTTPException(404, "Screening pathway has not been selected")
    return _profile_row(value)


@candidate_router.put("/screening-profile", response_model=ScreeningProfileResponse)
def update_screening_profile(
    payload: ScreeningProfileUpdate,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    _require_0030(request)
    ensure_writable(request)
    marketplace = session.get(MarketplaceProfile, user.id)
    if marketplace is None:
        raise HTTPException(409, "Create a marketplace profile first")
    value = session.scalar(
        select(MarketplaceScreeningProfile)
        .where(MarketplaceScreeningProfile.user_id == user.id)
        .with_for_update()
    )
    created = value is None
    if value is not None and (
        payload.expected_version is not None and payload.expected_version != value.version
    ):
        raise HTTPException(409, "Screening profile changed; reload and retry")
    if value is None:
        value = MarketplaceScreeningProfile(user_id=user.id, pathway=payload.pathway)
        session.add(value)
    declaration = payload.driver_declaration
    pathway_changed = created or value.pathway != payload.pathway
    changed = pathway_changed or any(
        (
            value.willing_to_drive != declaration.willing_to_drive,
            value.licence_jurisdiction != declaration.licence_jurisdiction,
            value.licence_jurisdiction_other != declaration.licence_jurisdiction_other,
            value.licence_class != declaration.licence_class,
            value.vehicle_access != declaration.vehicle_access,
            value.preferred_service_radius_km != declaration.preferred_service_radius_km,
        )
    )
    value.pathway = payload.pathway
    value.willing_to_drive = declaration.willing_to_drive
    value.licence_jurisdiction = declaration.licence_jurisdiction
    value.licence_jurisdiction_other = declaration.licence_jurisdiction_other
    value.licence_class = declaration.licence_class
    value.vehicle_access = declaration.vehicle_access
    value.preferred_service_radius_km = declaration.preferred_service_radius_km
    value.candidate_provided = True
    if changed and not created:
        value.version += 1

    expected_type = {
        "educator": "certified_educator",
        "student_educator": "student",
        "driver": None,
        "educator_driver": "certified_educator",
    }[payload.pathway]
    marketplace.candidate_type = expected_type
    # A same-pathway declaration edit creates a new disclosure version but does
    # not invalidate already-completed certificate, experience, and identity
    # onboarding. A pathway change can alter those requirements and must reopen
    # the guarded onboarding flow.
    if pathway_changed:
        marketplace.onboarding_completed_at = None
        state = session.get(MarketplaceOnboardingState, user.id)
        if state is not None:
            state.status = "in_progress"
            state.current_step = (
                "student_details"
                if payload.pathway == "student_educator"
                else "certificate"
                if payload.pathway in {"educator", "educator_driver"}
                else "work_experience"
            )
            state.completed_at = None
            state.version += 1
    commit_or_conflict(session)
    return _profile_row(value)


async def _store_version(
    *,
    request: Request,
    user: BasicUser,
    session,
    document: StaffScreeningDocument,
    version_number: int,
    coverage: list[str],
    file: UploadFile,
) -> ScreeningDocumentResponse:
    version_id = uuid4()
    try:
        stored = await store_encrypted_screening_upload(
            file,
            settings=request.app.state.settings,
            user_id=user.id,
            document_id=document.id,
            version_id=version_id,
        )
    except ScannerUnavailable as error:
        raise HTTPException(
            503, detail={"code": str(error) or "screening_document_scanner_unavailable"}
        ) from None
    version = StaffScreeningDocumentVersion(
        id=version_id,
        document_id=document.id,
        user_id=user.id,
        version_number=version_number,
        declared_coverage=coverage,
        original_filename=stored.original_filename,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        content_sha256=stored.content_sha256,
        ciphertext_sha256=stored.ciphertext_sha256,
        storage_reference=stored.storage_reference,
        encryption_key_id=stored.encryption_key_id,
    )
    try:
        session.add(document)
        if version_number == 1:
            flush_or_conflict(session)
        session.add(version)
        flush_or_conflict(session)
        document.current_version_number = version_number
        document.status = "candidate_review"
        flush_or_conflict(session)
        response = _document_row(session, document)
        _commit_screening_version(session)
    except AmbiguousStaffScreeningCommit:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "staff_screening_document_commit_unknown",
                "document_id": str(document.id),
                "version_id": str(version_id),
                "recovery": ("Reload screening documents before attempting another upload."),
            },
        ) from None
    except BaseException:
        delete_screening_object(request.app.state.settings, stored.storage_reference)
        raise
    return response


@candidate_router.post(
    "/screening-documents", response_model=ScreeningDocumentResponse, status_code=201
)
async def upload_screening_document(
    request: Request,
    user: BasicUser,
    session: SessionDependency,
    declared_coverage: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    _require_0030(request)
    ensure_writable(request)
    _require_screening_evidence_upload(request)
    document = StaffScreeningDocument(
        id=uuid4(), user_id=user.id, status="candidate_review", current_version_number=1
    )
    return await _store_version(
        request=request,
        user=user,
        session=session,
        document=document,
        version_number=1,
        coverage=_parse_coverage(declared_coverage),
        file=file,
    )


@candidate_router.post(
    "/screening-documents/{document_id}/versions",
    response_model=ScreeningDocumentResponse,
    status_code=201,
)
async def upload_screening_document_version(
    document_id: UUID,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
    declared_coverage: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    _require_0030(request)
    ensure_writable(request)
    _require_screening_evidence_upload(request)
    document = _owned_document(session, user.id, document_id, lock=True)
    if document.status == "withdrawn":
        raise HTTPException(409, "A withdrawn document cannot receive a new version")
    return await _store_version(
        request=request,
        user=user,
        session=session,
        document=document,
        version_number=document.current_version_number + 1,
        coverage=_parse_coverage(declared_coverage),
        file=file,
    )


@candidate_router.get("/screening-documents", response_model=list[ScreeningDocumentResponse])
def screening_documents(request: Request, user: BasicUser, session: SessionDependency):
    _require_0030(request)
    documents = session.scalars(
        select(StaffScreeningDocument)
        .where(StaffScreeningDocument.user_id == user.id)
        .order_by(StaffScreeningDocument.updated_at.desc())
    )
    return [_document_row(session, document) for document in documents]


@candidate_router.post(
    "/screening-documents/{document_id}/confirm",
    response_model=ScreeningDocumentResponse,
)
def confirm_screening_document(
    document_id: UUID,
    payload: ScreeningDocumentConfirm,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    _require_0030(request)
    ensure_writable(request)
    document = _owned_document(session, user.id, document_id, lock=True)
    if document.current_version_number != payload.expected_version:
        raise HTTPException(409, "Document changed; reload and confirm the current version")
    version = session.scalar(
        select(StaffScreeningDocumentVersion).where(
            StaffScreeningDocumentVersion.document_id == document.id,
            StaffScreeningDocumentVersion.user_id == user.id,
            StaffScreeningDocumentVersion.version_number == payload.expected_version,
        )
    )
    if version is None:
        raise RuntimeError("Staff screening current version is missing")
    account = session.get(User, user.id)
    if account is None:
        raise HTTPException(404, "Candidate account not found")
    account_name = f"{account.first_name} {account.last_name}".strip()
    name_matches = _normalized_person_name(payload.subject_name) == _normalized_person_name(
        account_name
    )
    if not name_matches and payload.mismatch_resolution != "candidate_attests_same_person":
        raise HTTPException(
            409,
            "The document name differs from the account; explicitly reconcile it to continue",
        )
    if name_matches and payload.mismatch_resolution is not None:
        raise HTTPException(422, "Name reconciliation is only valid for a mismatch")
    resolution = "matched" if name_matches else "candidate_attests_same_person"
    existing = session.get(StaffScreeningCandidateConfirmation, version.id)
    if existing is not None:
        if (
            existing.subject_name == payload.subject_name
            and existing.issue_date == payload.issue_date
            and existing.expiry_date == payload.expiry_date
            and existing.mismatch_resolution == resolution
        ):
            return _document_row(session, document)
        raise HTTPException(409, "A confirmed source version is immutable")
    session.add(
        StaffScreeningCandidateConfirmation(
            document_version_id=version.id,
            user_id=user.id,
            subject_name=payload.subject_name,
            # Preserve both identities and explicit reconciliation; never rewrite
            # the account or infer employer suitability from a name match.
            account_name_snapshot=account_name,
            subject_name_match=name_matches,
            mismatch_resolution=resolution,
            issue_date=payload.issue_date,
            expiry_date=payload.expiry_date,
            candidate_confirmed_at=datetime.now(UTC),
        )
    )
    flush_or_conflict(session)
    document.status = "confirmed"
    flush_or_conflict(session)
    response = _document_row(session, document)
    commit_or_conflict(session)
    return response


def _owned_version(
    session, user_id: UUID, document_id: UUID, version_id: UUID
) -> StaffScreeningDocumentVersion:
    value = session.scalar(
        select(StaffScreeningDocumentVersion).where(
            StaffScreeningDocumentVersion.id == version_id,
            StaffScreeningDocumentVersion.document_id == document_id,
            StaffScreeningDocumentVersion.user_id == user_id,
        )
    )
    if value is None:
        raise HTTPException(404, "Screening document version not found")
    return value


def _content_response(request: Request, version: StaffScreeningDocumentVersion) -> Response:
    try:
        content = read_encrypted_screening_object(
            settings=request.app.state.settings,
            storage_reference=version.storage_reference,
            media_type=version.media_type,
            encryption_key_id=version.encryption_key_id,
            expected_ciphertext_sha256=version.ciphertext_sha256,
            expected_content_sha256=version.content_sha256,
            expected_byte_size=version.byte_size,
            maximum_bytes=request.app.state.settings.staff_screening_document_max_bytes,
        )
    except (RuntimeError, ScannerUnavailable):
        raise HTTPException(
            503, detail={"code": "screening_document_content_unavailable"}
        ) from None
    filename = (version.original_filename or f"screening-{version.version_number}").replace('"', "")
    return Response(
        content=content,
        media_type=version.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@candidate_router.get("/screening-documents/{document_id}/versions/{version_id}/content")
def candidate_screening_document_content(
    document_id: UUID,
    version_id: UUID,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    _require_0030(request)
    version = _owned_version(session, user.id, document_id, version_id)
    return _content_response(request, version)


def _candidate_application_link(
    session, user_id: UUID, application_id: UUID
) -> MarketplaceApplicationLink:
    link = session.scalar(
        select(MarketplaceApplicationLink).where(
            MarketplaceApplicationLink.user_id == user_id,
            MarketplaceApplicationLink.application_id == application_id,
        )
    )
    if link is None:
        raise HTTPException(404, "Application not found")
    return link


def _pathway_matches_job(pathway: str, position_shape: str) -> bool:
    if position_shape == "driver_only":
        return pathway in {"driver", "educator_driver"}
    if position_shape == "educator_driver":
        return pathway == "educator_driver"
    return pathway in {"educator", "student_educator", "educator_driver"}


def _candidate_share_summary(session, application_id: UUID, user_id: UUID) -> dict:
    snapshot = session.get(AtsApplicationScreeningSnapshot, application_id)
    shares = list(
        session.scalars(
            select(StaffScreeningApplicationShare).where(
                StaffScreeningApplicationShare.application_id == application_id,
                StaffScreeningApplicationShare.candidate_user_id == user_id,
                StaffScreeningApplicationShare.revoked_at.is_(None),
            )
        )
    )
    rows = []
    for share in shares:
        version = session.get(StaffScreeningDocumentVersion, share.document_version_id)
        if version is None:
            raise RuntimeError("Shared screening document version is missing")
        latest_reviews = {}
        for requirement in version.declared_coverage or []:
            review = session.scalar(
                select(StaffScreeningEmployerReview)
                .where(
                    StaffScreeningEmployerReview.share_id == share.id,
                    StaffScreeningEmployerReview.requirement_class == requirement,
                )
                .order_by(
                    StaffScreeningEmployerReview.review_sequence.desc(),
                    StaffScreeningEmployerReview.reviewed_at.desc(),
                    StaffScreeningEmployerReview.id.desc(),
                )
                .limit(1)
            )
            if review is not None:
                latest_reviews[requirement] = {
                    "decision": review.decision,
                    "reason_code": review.reason_code,
                    "reviewed_at": review.reviewed_at,
                }
        rows.append(
            {
                "share_id": share.id,
                "document_version_id": version.id,
                "declared_coverage": list(version.declared_coverage or []),
                "screening_profile_version": share.screening_profile_version,
                "shared_at": share.shared_at,
                "latest_reviews": latest_reviews,
            }
        )
    return {
        "screening_schema_version": "0030",
        "application_id": application_id,
        "snapshot": (
            {
                "pathway": snapshot.pathway,
                "screening_profile_version": snapshot.screening_profile_version,
                "job_terms_version": snapshot.job_terms_version,
                "driver_declaration": snapshot.driver_declaration_snapshot,
                "job_terms": snapshot.job_terms_snapshot,
                "candidate_acknowledged_at": snapshot.candidate_acknowledged_at,
            }
            if snapshot
            else None
        ),
        "shares": rows,
    }


@candidate_router.get("/applications/{application_id}/screening-shares")
def candidate_application_screening_shares(
    application_id: UUID,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    _require_0030(request)
    link = _candidate_application_link(session, user.id, application_id)
    set_rls_organization(session, link.organization_id)
    _application(session, link.organization_id, application_id)
    return _candidate_share_summary(session, application_id, user.id)


@candidate_router.put("/applications/{application_id}/screening-shares")
def update_candidate_application_screening_shares(
    application_id: UUID,
    payload: ScreeningShareUpdate,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    _require_0030(request)
    ensure_writable(request)
    link = _candidate_application_link(session, user.id, application_id)
    set_rls_organization(session, link.organization_id)
    application = _application(session, link.organization_id, application_id, lock=True)
    now = datetime.now(UTC)
    active = list(
        session.scalars(
            select(StaffScreeningApplicationShare)
            .where(
                StaffScreeningApplicationShare.application_id == application.id,
                StaffScreeningApplicationShare.candidate_user_id == user.id,
                StaffScreeningApplicationShare.revoked_at.is_(None),
            )
            .with_for_update()
        )
    )
    if not payload.document_version_ids:
        for share in active:
            share.revoked_at = now
        session.add(
            AtsEvent(
                organization_id=application.organization_id,
                actor_user_id=user.id,
                event_type="screening.share_revoked",
                entity_type="application",
                entity_id=application.id,
                after={"state": "screening_material_revoked"},
            )
        )
        flush_or_conflict(session)
        response = _candidate_share_summary(session, application.id, user.id)
        commit_or_conflict(session)
        return response
    if application.status in {"accepted", "rejected", "withdrawn", "hired"}:
        raise HTTPException(409, "A terminal application cannot receive new screening shares")
    profile = session.get(MarketplaceScreeningProfile, user.id)
    if profile is None or profile.version != payload.screening_profile_version:
        raise HTTPException(409, "Screening pathway changed; reload before sharing")
    if not screening_profile_complete(profile):
        raise HTTPException(409, "Complete the driver declaration before sharing")
    terms = session.get(AtsJobScreeningTerms, application.job_id)
    if terms is None:
        raise RuntimeError("0030 job screening terms are missing")
    structured_terms = structured_terms_from_model(terms)
    if not _pathway_matches_job(profile.pathway, structured_terms["position_shape"]):
        raise HTTPException(409, "Candidate pathway does not match this position")

    versions = list(
        session.scalars(
            select(StaffScreeningDocumentVersion).where(
                StaffScreeningDocumentVersion.user_id == user.id,
                StaffScreeningDocumentVersion.id.in_(payload.document_version_ids),
            )
        )
    )
    if len(versions) != len(payload.document_version_ids):
        raise HTTPException(404, "One or more screening document versions were not found")
    today = date.today()
    coverage_sources: dict[str, UUID] = {}
    for version in versions:
        document = _owned_document(session, user.id, version.document_id)
        confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
        if (
            version.version_number != document.current_version_number
            or document.status != "confirmed"
            or confirmation is None
            or (confirmation.expiry_date is not None and confirmation.expiry_date < today)
        ):
            raise HTTPException(409, "Only current, confirmed screening versions may be shared")
        for requirement in version.declared_coverage or []:
            if requirement in coverage_sources:
                raise HTTPException(
                    409, "Share exactly one current source for each screening requirement"
                )
            coverage_sources[requirement] = version.id
    if set(coverage_sources) != SCREENING_COVERAGE:
        raise HTTPException(409, "Share current evidence covering both required screening checks")

    snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
    declaration_snapshot = driver_declaration_snapshot(profile)
    if snapshot is None:
        snapshot = AtsApplicationScreeningSnapshot(
            application_id=application.id,
            organization_id=application.organization_id,
            candidate_user_id=user.id,
            pathway=profile.pathway,
            screening_profile_version=profile.version,
            job_terms_version=terms.version,
            driver_declaration_snapshot=declaration_snapshot,
            job_terms_snapshot=structured_terms,
            candidate_acknowledged_at=now,
        )
        session.add(snapshot)
        flush_or_conflict(session)
    elif any(
        (
            snapshot.candidate_user_id != user.id,
            snapshot.pathway != profile.pathway,
            snapshot.screening_profile_version != profile.version,
            snapshot.job_terms_version != terms.version,
            snapshot.driver_declaration_snapshot != declaration_snapshot,
            snapshot.job_terms_snapshot != structured_terms,
        )
    ):
        raise HTTPException(
            409,
            "The application screening snapshot is immutable; withdraw and reapply after changes",
        )
    requested = set(payload.document_version_ids)
    retained: set[UUID] = set()
    for share in active:
        if (
            share.document_version_id in requested
            and share.screening_profile_version == profile.version
        ):
            retained.add(share.document_version_id)
        else:
            share.revoked_at = now
    for version_id in requested - retained:
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
    session.add(
        AtsEvent(
            organization_id=application.organization_id,
            actor_user_id=user.id,
            event_type="screening.share_changed",
            entity_type="application",
            entity_id=application.id,
            after={"state": "screening_material_changed"},
        )
    )
    flush_or_conflict(session)
    response = _candidate_share_summary(session, application.id, user.id)
    commit_or_conflict(session)
    return response


def _employer_projection(session, application_id: UUID, organization_id: UUID) -> dict:
    application = _application(session, organization_id, application_id)
    snapshot = session.get(AtsApplicationScreeningSnapshot, application.id)
    shares = list(
        session.scalars(
            select(StaffScreeningApplicationShare).where(
                StaffScreeningApplicationShare.organization_id == organization_id,
                StaffScreeningApplicationShare.application_id == application.id,
                StaffScreeningApplicationShare.revoked_at.is_(None),
            )
        )
    )
    projected = []
    for share in shares:
        version = session.scalar(
            select(StaffScreeningDocumentVersion).where(
                StaffScreeningDocumentVersion.id == share.document_version_id,
                StaffScreeningDocumentVersion.user_id == share.candidate_user_id,
            )
        )
        if version is None or version.id != share.document_version_id:
            raise RuntimeError("Exact shared screening version is missing")
        confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
        if confirmation is None:
            raise RuntimeError("Shared screening version has no candidate confirmation")
        reviews = list(
            session.scalars(
                select(StaffScreeningEmployerReview)
                .where(
                    StaffScreeningEmployerReview.organization_id == organization_id,
                    StaffScreeningEmployerReview.application_id == application.id,
                    StaffScreeningEmployerReview.share_id == share.id,
                )
                .order_by(
                    StaffScreeningEmployerReview.requirement_class,
                    StaffScreeningEmployerReview.review_sequence,
                )
            )
        )
        projected.append(
            {
                "id": share.id,
                "shared_at": share.shared_at,
                "screening_profile_version": share.screening_profile_version,
                "shared_version": {
                    "id": version.id,
                    "version_number": version.version_number,
                    "declared_coverage": list(version.declared_coverage or []),
                    "subject_name": confirmation.subject_name,
                    "account_name_snapshot": confirmation.account_name_snapshot,
                    "subject_name_match": confirmation.subject_name_match,
                    "mismatch_resolution": confirmation.mismatch_resolution,
                    "issue_date": confirmation.issue_date,
                    "expiry_date": confirmation.expiry_date,
                    "candidate_confirmed_at": confirmation.candidate_confirmed_at,
                    "content_url": (
                        f"/api/v1/ats/applications/{application.id}/screening-shares/"
                        f"{share.id}/content"
                    ),
                },
                "reviews": [
                    {
                        "id": review.id,
                        "requirement_class": review.requirement_class,
                        "decision": review.decision,
                        "reason_code": review.reason_code,
                        "note": review.note,
                        "reviewer_user_id": review.reviewer_user_id,
                        "review_sequence": review.review_sequence,
                        "reviewed_at": review.reviewed_at,
                    }
                    for review in reviews
                ],
            }
        )
    return {
        "screening_schema_version": "0030",
        "application_id": application.id,
        "candidate_id": application.candidate_id,
        "snapshot": (
            {
                "pathway": snapshot.pathway,
                "screening_profile_version": snapshot.screening_profile_version,
                "job_terms_version": snapshot.job_terms_version,
                "driver_declaration": snapshot.driver_declaration_snapshot,
                "job_terms": snapshot.job_terms_snapshot,
                "candidate_acknowledged_at": snapshot.candidate_acknowledged_at,
            }
            if snapshot
            else None
        ),
        "shares": projected,
    }


@employer_router.get("/applications/{application_id}/screening")
def employer_application_screening(
    application_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    _require_0030(request)
    ScreeningManageContext(context)
    return _employer_projection(session, application_id, context.organization.id)


def _active_employer_share(
    session, organization_id: UUID, application_id: UUID, share_id: UUID, *, lock: bool = False
) -> StaffScreeningApplicationShare:
    statement = select(StaffScreeningApplicationShare).where(
        StaffScreeningApplicationShare.organization_id == organization_id,
        StaffScreeningApplicationShare.application_id == application_id,
        StaffScreeningApplicationShare.id == share_id,
        StaffScreeningApplicationShare.revoked_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update(read=True)
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, "Active screening share not found")
    return value


@employer_router.get("/applications/{application_id}/screening-shares/{share_id}/content")
def employer_screening_document_content(
    application_id: UUID,
    share_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    _require_0030(request)
    ScreeningManageContext(context)
    _application(session, context.organization.id, application_id)
    share = _active_employer_share(session, context.organization.id, application_id, share_id)
    version = session.scalar(
        select(StaffScreeningDocumentVersion).where(
            StaffScreeningDocumentVersion.id == share.document_version_id,
            StaffScreeningDocumentVersion.user_id == share.candidate_user_id,
        )
    )
    if version is None or version.id != share.document_version_id:
        raise HTTPException(404, "Shared screening source not found")
    response = _content_response(request, version)
    session.add(
        AtsEvent(
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            event_type="screening.document_viewed",
            entity_type="screening_share",
            entity_id=share.id,
            after={"state": "source_viewed"},
        )
    )
    commit_in_context(session, context)
    return response


@employer_router.post(
    "/applications/{application_id}/screening-shares/{share_id}/reviews",
    status_code=201,
)
def review_screening_document(
    application_id: UUID,
    share_id: UUID,
    payload: EmployerScreeningReviewCreate,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    _require_0030(request)
    ScreeningManageContext(context)
    ensure_writable(request)
    _application(session, context.organization.id, application_id, lock=True)
    share = _active_employer_share(
        session, context.organization.id, application_id, share_id, lock=True
    )
    version = session.scalar(
        select(StaffScreeningDocumentVersion).where(
            StaffScreeningDocumentVersion.id == share.document_version_id,
            StaffScreeningDocumentVersion.user_id == share.candidate_user_id,
        )
    )
    if version is None or payload.requirement_class not in set(version.declared_coverage or []):
        raise HTTPException(409, "Shared source does not claim this screening requirement")
    confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
    document = session.get(StaffScreeningDocument, version.document_id)
    if (
        confirmation is None
        or document is None
        or document.status != "confirmed"
        or document.current_version_number != version.version_number
        or (confirmation.expiry_date is not None and confirmation.expiry_date < date.today())
    ):
        raise HTTPException(409, "Shared screening source is no longer current and valid")
    viewed = session.scalar(
        select(AtsEvent.id).where(
            AtsEvent.organization_id == context.organization.id,
            AtsEvent.actor_user_id == context.user.id,
            AtsEvent.event_type == "screening.document_viewed",
            AtsEvent.entity_type == "screening_share",
            AtsEvent.entity_id == share.id,
        )
    )
    if viewed is None:
        raise HTTPException(409, "View the exact shared source before recording a review")
    sequence = (
        session.scalar(
            select(func.max(StaffScreeningEmployerReview.review_sequence)).where(
                StaffScreeningEmployerReview.share_id == share.id,
                StaffScreeningEmployerReview.requirement_class == payload.requirement_class,
            )
        )
        or 0
    ) + 1
    review = StaffScreeningEmployerReview(
        organization_id=context.organization.id,
        application_id=application_id,
        share_id=share.id,
        requirement_class=payload.requirement_class,
        decision=payload.decision,
        reason_code=payload.reason_code,
        note=payload.note.strip() if payload.note else None,
        reviewer_user_id=context.user.id,
        review_sequence=sequence,
    )
    session.add(review)
    session.add(
        AtsEvent(
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            event_type="screening.review_recorded",
            entity_type="screening_share",
            entity_id=share.id,
            after={"state": "review_changed"},
        )
    )
    notify_user(
        session,
        user_id=share.candidate_user_id,
        organization_id=context.organization.id,
        event_key=f"screening-review:{share.id}:{payload.requirement_class}:{sequence}",
        category="hiring",
        severity="success" if payload.decision == "accepted" else "warning",
        title="Screening document review updated",
        body="An employer updated one of your application screening requirements.",
        action_path=f"/jobs/applications/{application_id}",
        action_entity_type="application",
        action_entity_id=application_id,
    )
    commit_in_context(session, context)
    return {
        "id": review.id,
        "requirement_class": review.requirement_class,
        "decision": review.decision,
        "reason_code": review.reason_code,
        "note": review.note,
        "reviewer_user_id": review.reviewer_user_id,
        "review_sequence": review.review_sequence,
        "reviewed_at": review.reviewed_at,
    }


def application_screening_reviews_accepted(
    session,
    *,
    organization_id: UUID,
    application_id: UUID,
    lock_for_provisioning: bool = False,
) -> bool:
    """Return true only when current active shares have latest accepted CRC and VSS reviews."""

    share_statement = (
        select(StaffScreeningApplicationShare)
        .where(
            StaffScreeningApplicationShare.organization_id == organization_id,
            StaffScreeningApplicationShare.application_id == application_id,
            StaffScreeningApplicationShare.revoked_at.is_(None),
        )
        .order_by(StaffScreeningApplicationShare.id)
    )
    if lock_for_provisioning:
        share_statement = share_statement.with_for_update(read=True)
    shares = list(session.scalars(share_statement.execution_options(populate_existing=True)))
    versions = {
        version.id: version
        for version in session.scalars(
            select(StaffScreeningDocumentVersion).where(
                StaffScreeningDocumentVersion.id.in_(
                    [share.document_version_id for share in shares]
                )
            )
        )
    }
    document_statement = (
        select(StaffScreeningDocument)
        .where(
            StaffScreeningDocument.id.in_(
                sorted({version.document_id for version in versions.values()}, key=str)
            )
        )
        .order_by(StaffScreeningDocument.id)
    )
    if lock_for_provisioning:
        document_statement = document_statement.with_for_update(read=True)
    documents = {
        document.id: document
        for document in session.scalars(
            document_statement.execution_options(populate_existing=True)
        )
    }
    source_for_requirement: dict[str, StaffScreeningApplicationShare] = {}
    today = date.today()
    for share in shares:
        version = versions.get(share.document_version_id)
        if version is None:
            return False
        confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
        document = documents.get(version.document_id)
        if (
            confirmation is None
            or document is None
            or document.status != "confirmed"
            or document.current_version_number != version.version_number
            or (confirmation.expiry_date is not None and confirmation.expiry_date < today)
        ):
            return False
        for requirement in version.declared_coverage or []:
            if requirement in source_for_requirement:
                return False
            source_for_requirement[requirement] = share
    if set(source_for_requirement) != SCREENING_COVERAGE:
        return False
    for requirement, share in source_for_requirement.items():
        latest = session.scalar(
            select(StaffScreeningEmployerReview)
            .where(
                StaffScreeningEmployerReview.organization_id == organization_id,
                StaffScreeningEmployerReview.application_id == application_id,
                StaffScreeningEmployerReview.share_id == share.id,
                StaffScreeningEmployerReview.requirement_class == requirement,
            )
            .order_by(
                StaffScreeningEmployerReview.review_sequence.desc(),
                StaffScreeningEmployerReview.reviewed_at.desc(),
                StaffScreeningEmployerReview.id.desc(),
            )
            .limit(1)
        )
        if latest is None or latest.decision != "accepted":
            return False
    return True


def default_job_screening_terms() -> dict:
    """Public helper used by the legacy-compatible ATS adapter."""

    return default_structured_terms()
