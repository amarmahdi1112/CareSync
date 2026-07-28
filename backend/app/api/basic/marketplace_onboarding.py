"""Candidate-owned, resumable onboarding with local OCR proposals."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader
from sqlalchemy import func, select

from app.api.basic.common import commit_or_conflict, ensure_writable, flush_or_conflict
from app.api.basic.dependencies import CompleteMarketplaceUser
from app.api.dependencies import SessionDependency
from app.basic.models import (
    AtsCandidate,
    MarketplaceApplicationLink,
    MarketplaceCredentialDocument,
    MarketplaceCredentialNotification,
    MarketplaceDocumentAnalysis,
    MarketplaceInterest,
    MarketplaceOnboardingState,
    MarketplaceProfile,
    MarketplaceScreeningProfile,
    OrganizationMembership,
    RealtimeEvent,
    StaffScreeningCandidateConfirmation,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    User,
)
from app.basic.notifications import emit_user_realtime_event, notify_organization_members
from app.basic.security import set_rls_organization
from app.basic.staff_screening_terms import screening_profile_complete

router = APIRouter(prefix="/marketplace/onboarding", tags=["candidate marketplace onboarding"])
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 5
MAX_IMAGE_PIXELS = 25_000_000
RAW_TTL_MINUTES = 30
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg"}
SCREENING_COVERAGE = frozenset({"criminal_record_check", "vulnerable_sector_search"})
SAFE_SUFFIX = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


def _screening_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "staff_screening_pathways_enabled", False))


def _0030_work_history_next_step(
    session, *, user_id: UUID, profile: MarketplaceProfile, state: MarketplaceOnboardingState
) -> bool:
    screening = session.get(MarketplaceScreeningProfile, user_id)
    if screening is None:
        raise HTTPException(409, "Select a candidate pathway first")
    if screening.pathway == "driver":
        state.status = "review"
        state.current_step = "review"
    elif screening.pathway == "student_educator":
        state.status = "review" if "student_details" in state.completed_steps else "in_progress"
        state.current_step = "review" if state.status == "review" else "student_details"
    else:
        state.status = "review" if "certificate" in state.completed_steps else "in_progress"
        state.current_step = "review" if state.status == "review" else "certificate"
    return True


def _has_current_screening_coverage(session, user_id: UUID) -> bool:
    today = date.today()
    covered: set[str] = set()
    versions = session.scalars(
        select(StaffScreeningDocumentVersion)
        .join(
            StaffScreeningDocument,
            (StaffScreeningDocument.id == StaffScreeningDocumentVersion.document_id)
            & (StaffScreeningDocument.user_id == StaffScreeningDocumentVersion.user_id),
        )
        .where(
            StaffScreeningDocumentVersion.user_id == user_id,
            StaffScreeningDocument.status == "confirmed",
            StaffScreeningDocument.current_version_number
            == StaffScreeningDocumentVersion.version_number,
        )
    )
    for version in versions:
        confirmation = session.get(StaffScreeningCandidateConfirmation, version.id)
        if confirmation is not None and (
            confirmation.expiry_date is None or confirmation.expiry_date >= today
        ):
            covered.update(version.declared_coverage or [])
    return SCREENING_COVERAGE.issubset(covered)


class CertificateConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    certificate_type: str = Field(min_length=1, max_length=120)
    certificate_number: str = Field(min_length=1, max_length=120)
    expiry_date: date | None = None
    mismatch_resolution: Literal["use_certificate_name"] | None = None


class WorkConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_history: list[dict] = Field(max_length=50)


class CandidateTypeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_type: Literal["certified_educator", "student"]


class StudentDetailsConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    institution: str = Field(min_length=2, max_length=180)
    program: str = Field(min_length=2, max_length=180)
    expected_graduation_date: date


def _state(session, user_id: UUID) -> MarketplaceOnboardingState:
    value = session.get(MarketplaceOnboardingState, user_id)
    if value is None:
        value = MarketplaceOnboardingState(user_id=user_id)
        session.add(value)
        session.flush()
    return value


_IMAGE_LABEL_PREFIX = re.compile(
    r"(?i)^\s*(?:(?:[uj]?pe?g?r?|jpg|png|heic|webp)\s+(?:image|text)|"
    r"(?:image|photo|picture)(?:\s+(?:file|preview))?)\s*[:._\-–]*\s+"
)
_CAMERA_FILENAME_PREFIX = re.compile(r"(?i)^\s*(?:img|dsc|pxl)[-_ ]?\d{3,}\s*[:._\-–]*\s+")


def _clean_holder_name(value: str | None) -> str | None:
    """Remove viewer/camera metadata that OCR can merge into the printed holder line."""
    if not value:
        return None
    cleaned = " ".join(str(value).split()).strip(" .,:;_-–")
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = _IMAGE_LABEL_PREFIX.sub("", cleaned)
        cleaned = _CAMERA_FILENAME_PREFIX.sub("", cleaned)
    return cleaned[:200] or None


def _sanitized_certificate_proposal(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return value
    result = deepcopy(value)
    normalized = result.get("normalized_proposal")
    if not isinstance(normalized, dict):
        return result
    holder = _clean_holder_name(normalized.get("holder_name"))
    normalized["holder_name"] = holder
    account_name = str(result.get("account_name") or "")
    normalized_holder = re.sub(r"[^a-z]", "", holder.lower()) if holder else None
    normalized_account = re.sub(r"[^a-z]", "", account_name.lower())
    result["holder_name_mismatch"] = bool(
        normalized_holder and normalized_account and normalized_holder != normalized_account
    )
    return result


def _analysis_row(value: MarketplaceDocumentAnalysis) -> dict:
    return {
        "id": value.id,
        "document_kind": value.document_kind,
        "status": value.status,
        "mime_type": value.mime_type,
        "file_size_bytes": value.file_size_bytes,
        "page_count": value.page_count,
        "content_sha256": value.content_sha256,
        "raw_document_retained": value.raw_document_retained,
        "raw_expires_at": value.raw_expires_at,
        "ocr_engine": value.ocr_engine,
        "ocr_model": value.ocr_model,
        "proposal": _sanitized_certificate_proposal(value.proposal)
        if value.document_kind == "certificate"
        else value.proposal,
        "field_confidences": value.field_confidences,
        "overall_confidence": float(value.overall_confidence)
        if value.overall_confidence is not None
        else None,
        "proposal_is_authoritative": False,
        "analyzed_at": value.analyzed_at,
        "candidate_confirmed_at": value.candidate_confirmed_at,
        "failure_code": value.failure_code,
        "created_at": value.created_at,
    }


def _credential_row(value: MarketplaceCredentialDocument) -> dict:
    return {
        "id": value.id,
        "analysis_id": value.analysis_id,
        "version_number": value.version_number,
        "original_filename": value.original_filename,
        "content_type": value.content_type,
        "size_bytes": value.size_bytes,
        "sha256": value.sha256,
        "status": value.status,
        "is_current": value.is_current,
        "holder_name": value.holder_name,
        "certificate_type": value.certificate_type,
        "certificate_number": value.certificate_number,
        "expiry_date": value.expiry_date,
        "confirmed_at": value.confirmed_at,
        "content_url": f"/api/v1/marketplace/onboarding/credentials/{value.id}/content",
        "created_at": value.created_at,
    }


@router.get("/credentials")
def credential_history(user: CompleteMarketplaceUser, session: SessionDependency):
    rows = session.scalars(
        select(MarketplaceCredentialDocument)
        .where(MarketplaceCredentialDocument.user_id == user.id)
        .order_by(MarketplaceCredentialDocument.version_number.desc())
    )
    return [_credential_row(row) for row in rows]


@router.get("/credentials/{credential_id}/content")
def credential_content(
    credential_id: UUID,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    value = session.scalar(
        select(MarketplaceCredentialDocument).where(
            MarketplaceCredentialDocument.id == credential_id,
            MarketplaceCredentialDocument.user_id == user.id,
        )
    )
    if value is None:
        raise HTTPException(404, "Credential image not found")
    filename = (value.original_filename or f"certificate-{value.version_number}").replace('"', "")
    return Response(
        content=value.image_bytes,
        media_type=value.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _state_row(session, state: MarketplaceOnboardingState) -> dict:
    analyses = list(
        session.scalars(
            select(MarketplaceDocumentAnalysis)
            .where(MarketplaceDocumentAnalysis.user_id == state.user_id)
            .order_by(MarketplaceDocumentAnalysis.created_at.desc())
            .limit(20)
        )
    )
    profile = session.get(MarketplaceProfile, state.user_id)
    return {
        "user_id": state.user_id,
        "status": state.status,
        "current_step": state.current_step,
        "completed_steps": state.completed_steps,
        "version": state.version,
        "completed_at": state.completed_at,
        "candidate_type": profile.candidate_type if profile else None,
        "student_details": (
            {
                "institution": profile.institution,
                "program": profile.program,
                "expected_graduation_date": profile.expected_graduation_date,
            }
            if profile and profile.candidate_type == "student"
            else None
        ),
        "analyses": [_analysis_row(item) for item in analyses],
    }


@router.get("")
def onboarding_state(user: CompleteMarketplaceUser, session: SessionDependency):
    state = _state(session, user.id)
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/candidate-type")
def select_candidate_type(
    payload: CandidateTypeSelection,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Create a marketplace profile first")
    state = _state(session, user.id)
    if state.status == "complete" or state.completed_steps:
        if profile.candidate_type == payload.candidate_type:
            return _state_row(session, state)
        raise HTTPException(
            409, "Candidate type cannot change after onboarding evidence is confirmed"
        )
    profile.candidate_type = payload.candidate_type
    profile.onboarding_completed_at = None
    if payload.candidate_type == "certified_educator":
        profile.institution = None
        profile.program = None
        profile.expected_graduation_date = None
        state.current_step = "certificate"
    else:
        profile.certification_type = None
        profile.certification_number = None
        profile.certification_expiry_date = None
        profile.certification_provenance = None
        profile.certification_candidate_confirmed_at = None
        state.current_step = "student_details"
    state.status = "in_progress"
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/student-details/confirm")
def confirm_student_details(
    payload: StudentDetailsConfirmation,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None or profile.candidate_type != "student":
        raise HTTPException(409, "Select student candidate type first")
    today = date.today()
    if payload.expected_graduation_date < today or payload.expected_graduation_date > date(
        today.year + 10, today.month, min(today.day, 28)
    ):
        raise HTTPException(422, "Expected graduation date must be within the next 10 years")
    profile.institution = payload.institution.strip()
    profile.program = payload.program.strip()
    profile.expected_graduation_date = payload.expected_graduation_date
    state = _state(session, user.id)
    state.completed_steps = list(dict.fromkeys([*state.completed_steps, "student_details"]))
    state.status = "review"
    state.current_step = "review"
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)


def _validate_content(data: bytes, mime_type: str) -> int:
    if mime_type not in ALLOWED_MIME:
        raise HTTPException(415, "Only PDF, PNG, and JPEG documents are accepted")
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "Document must be between 1 byte and 8 MiB")
    if mime_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(415, "File content does not match PDF MIME type")
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise HTTPException(422, "Encrypted PDFs are not supported")
            pages = len(reader.pages)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, "PDF could not be read safely") from None
        if pages < 1 or pages > MAX_PDF_PAGES:
            raise HTTPException(422, f"PDF must contain 1 to {MAX_PDF_PAGES} pages")
        return pages
    expected = "PNG" if mime_type == "image/png" else "JPEG"
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != expected:
                raise HTTPException(415, "File content does not match image MIME type")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(422, "Image dimensions are too large")
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "Image could not be read safely") from None
    return 1


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
    document_kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    ensure_writable(request)
    if document_kind not in {"certificate", "resume"}:
        raise HTTPException(422, "document_kind must be certificate or resume")
    profile = session.get(MarketplaceProfile, user.id)
    if document_kind == "certificate" and (
        profile is None or profile.candidate_type != "certified_educator"
    ):
        raise HTTPException(409, "Select certified educator candidate type first")
    data = await file.read(MAX_FILE_BYTES + 1)
    mime_type = (file.content_type or "").lower()
    page_count = _validate_content(data, mime_type)
    identifier = uuid4()
    private_dir = request.app.state.settings.database_path.parent / "private-onboarding"
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # PaddleOCR selects its decoder from the suffix. Derive it only from the
    # already validated MIME/content pair, never from the untrusted filename.
    path = private_dir / f"{identifier.hex}{SAFE_SUFFIX[mime_type]}"
    path.write_bytes(data)
    path.chmod(0o600)
    now = datetime.now(UTC)
    analysis = MarketplaceDocumentAnalysis(
        id=identifier,
        user_id=user.id,
        document_kind=document_kind,
        mime_type=mime_type,
        file_size_bytes=len(data),
        page_count=page_count,
        content_sha256=hashlib.sha256(data).hexdigest(),
        temporary_path=str(path),
        raw_document_retained=False,
        raw_expires_at=now + timedelta(minutes=RAW_TTL_MINUTES),
    )
    state = _state(session, user.id)
    session.add(analysis)
    # Materialize the analysis parent before inserting its immutable vault child.
    flush_or_conflict(session)
    if state.status != "complete":
        state.status = "in_progress"
        state.current_step = "certificate" if document_kind == "certificate" else "work_experience"
        state.version += 1
    if document_kind == "certificate":
        latest_version = (
            session.scalar(
                select(func.max(MarketplaceCredentialDocument.version_number)).where(
                    MarketplaceCredentialDocument.user_id == user.id
                )
            )
            or 0
        )
        session.add(
            MarketplaceCredentialDocument(
                user_id=user.id,
                analysis_id=identifier,
                version_number=latest_version + 1,
                original_filename=Path(file.filename or "certificate").name[:255],
                content_type=mime_type,
                image_bytes=data,
                size_bytes=len(data),
                sha256=analysis.content_sha256,
                status="uploaded",
            )
        )
    commit_or_conflict(session)
    return _analysis_row(analysis)


def run_local_ocr(path: Path) -> dict:
    python = Path(
        os.getenv(
            "CARESYNC_OCR_PYTHON",
            str(Path.home() / "Library/Caches/CareSync-OCR/.venv/bin/python"),
        )
    )
    worker = Path(__file__).resolve().parents[3] / "scripts/ocr_worker.py"
    if not python.is_file():
        raise RuntimeError("local_ocr_runtime_unavailable")
    completed = subprocess.run(
        [str(python), str(worker), str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        raise RuntimeError("local_ocr_failed")
    return json.loads(completed.stdout)


def _matching_confidence(lines: list[dict], value: str | None) -> float:
    if not value:
        return 0.0
    scores = [
        float(item.get("confidence", 0))
        for item in lines
        if value.lower() in str(item.get("text", "")).lower()
    ]
    if scores:
        return max(scores)
    tokens = [part.casefold() for part in value.split() if len(part) > 1]
    token_scores = [
        max(
            (
                float(item.get("confidence", 0))
                for item in lines
                if token in str(item.get("text", "")).casefold()
            ),
            default=0.0,
        )
        for token in tokens
    ]
    return min(token_scores, default=0.0)


_PERSON_NAME = re.compile(r"[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){1,3}")


def _extract_holder_name(texts: list[str]) -> str | None:
    for value in texts:
        explicit = re.search(r"(?i)(?:holder|candidate|name)\s*[:\-]\s*(.+)$", value)
        if explicit:
            candidate = _clean_holder_name(explicit.group(1))
            if candidate and _PERSON_NAME.fullmatch(candidate):
                return candidate
    for index, value in enumerate(texts):
        if not re.search(r"(?i)\bthis\s+confirms\s+that\b", value):
            continue
        fragments: list[str] = []
        for following in texts[index + 1 : index + 4]:
            if re.search(r"(?i)\bhas\s+met\s+the\s+requirements\b", following):
                break
            cleaned = _clean_holder_name(following)
            if not cleaned:
                continue
            fragments.append(cleaned)
            combined = " ".join(fragments)
            if _PERSON_NAME.fullmatch(combined):
                return combined
    return None


def _extract_certificate_number(texts: list[str]) -> str | None:
    label = re.compile(r"(?i)(?:certificate|certification|registration)\s*(?:number|no\.?|#)")
    token = re.compile(r"[A-Z0-9][A-Z0-9\-]{3,29}", re.I)
    for index, value in enumerate(texts):
        match = label.search(value)
        if not match:
            continue
        same_line = re.search(
            r"[:\-]?\s*([A-Z0-9][A-Z0-9\-]{3,29})\s*$",
            value[match.end() :],
            re.I,
        )
        if same_line:
            return same_line.group(1).strip()
        for following in texts[index + 1 : index + 3]:
            candidate = following.strip().replace(" ", "")
            if token.fullmatch(candidate):
                return candidate
    return None


def _certificate_proposal(lines: list[dict], account_name: str) -> tuple[dict, dict]:
    texts = [str(item.get("text", "")).strip() for item in lines if item.get("text")]
    text = "\n".join(texts)
    certificate_type = None
    for pattern in (
        r"(?im)^(LEVEL\s*[123])\s*$",
        r"(?i)(Alberta\s+(?:child\s+care\s+staff\s+)?certification[^\n]*)",
        r"(?i)((?:Level|Early Childhood Educator)\s*[123][^\n]*)",
    ):
        match = re.search(pattern, text)
        if match:
            certificate_type = match.group(1).strip()[:120]
            break
    certificate_number = _extract_certificate_number(texts)
    expiry_match = re.search(
        r"(?i)(?:expiry|expires|valid until)\s*[:\-]?\s*([A-Z0-9, /\-]{6,30})",
        text,
    )
    holder_name = _extract_holder_name(texts)
    normalized_holder = re.sub(r"[^a-z]", "", holder_name.lower()) if holder_name else None
    normalized_account = re.sub(r"[^a-z]", "", account_name.lower())
    values = {
        "holder_name": holder_name,
        "certificate_type": certificate_type,
        "certificate_number": certificate_number,
        "expiry_date_text": expiry_match.group(1).strip() if expiry_match else None,
    }
    confidences = {key: _matching_confidence(lines, value) for key, value in values.items()}
    return {
        "provenance": "local_ocr",
        "raw_extracted_values": values,
        "normalized_proposal": values,
        "account_name": account_name,
        "holder_name_mismatch": bool(normalized_holder and normalized_holder != normalized_account),
        "requires_candidate_confirmation": True,
        "required_fields_complete": bool(holder_name and certificate_number),
    }, confidences


DATE_RANGE = re.compile(
    r"(?i)\b((?:19|20)\d{2}|[A-Z][a-z]{2,8}\s+(?:19|20)\d{2})\s*(?:-|–|to)\s*"
    r"((?:19|20)\d{2}|present|current|[A-Z][a-z]{2,8}\s+(?:19|20)\d{2})\b"
)


def _resume_proposal(lines: list[dict]) -> tuple[dict, dict]:
    texts = [str(item.get("text", "")).strip() for item in lines if item.get("text")]
    entries = []
    scores = []
    for index, value in enumerate(texts):
        match = DATE_RANGE.search(value)
        if not match:
            continue
        nearby = texts[max(0, index - 2) : index + 2]
        label = next(
            (item for item in nearby if item != value and len(item) > 2), "Unknown employer"
        )
        entries.append(
            {
                "employer": label[:255],
                "role": None,
                "start_text": match.group(1),
                "end_text": match.group(2),
            }
        )
        scores.append(_matching_confidence(lines, value))
    confidences = {f"work_history.{index}": score for index, score in enumerate(scores)}
    return {
        "provenance": "local_ocr",
        "raw_extracted_values": {"work_entries": entries},
        "normalized_proposal": {"work_history": entries},
        "requires_candidate_confirmation": True,
    }, confidences


@router.post("/documents/{analysis_id}/analyze")
def analyze_document(
    analysis_id: UUID,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    analysis = session.scalar(
        select(MarketplaceDocumentAnalysis)
        .where(
            MarketplaceDocumentAnalysis.id == analysis_id,
            MarketplaceDocumentAnalysis.user_id == user.id,
        )
        .with_for_update()
    )
    if analysis is None:
        raise HTTPException(404, "Onboarding document not found")
    if analysis.status == "analyzed":
        return _analysis_row(analysis)
    if analysis.status != "uploaded" or not analysis.temporary_path:
        raise HTTPException(409, "Document is not available for analysis")
    path = Path(analysis.temporary_path)
    expires = analysis.raw_expires_at
    if expires and (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) <= datetime.now(
        UTC
    ):
        path.unlink(missing_ok=True)
        analysis.status = "discarded"
        analysis.temporary_path = None
        analysis.raw_expires_at = None
        commit_or_conflict(session)
        raise HTTPException(410, "Temporary document expired; upload it again")
    try:
        output = run_local_ocr(path)
        lines = list(output.get("lines") or [])
        if analysis.document_kind == "certificate":
            account = session.get(User, user.id)
            account_name = f"{account.first_name} {account.last_name}" if account else ""
            proposal, confidences = _certificate_proposal(lines, account_name)
            if not proposal.get("required_fields_complete"):
                raise RuntimeError("certificate_required_fields_missing")
        else:
            proposal, confidences = _resume_proposal(lines)
        scores = [float(item.get("confidence", 0)) for item in lines]
        analysis.status = "analyzed"
        analysis.ocr_engine = str(output.get("engine") or "opencv5+paddleocr")
        vision = output.get("vision") if isinstance(output.get("vision"), dict) else {}
        vision_version = str(vision.get("version") or "5")
        vision_pipeline = str(vision.get("pipeline") or "document-v1")
        recognizer = str(output.get("model") or "PP-OCRv6_tiny")
        # MarketplaceDocumentAnalysis.ocr_model is VARCHAR(80) in PostgreSQL.
        # Keep the human-readable pipeline/model prefix without allowing richer
        # fused-model telemetry to turn a successful analysis into a DB error.
        analysis.ocr_model = f"opencv-{vision_version}:{vision_pipeline}|{recognizer}"[:80]
        analysis.proposal = proposal
        analysis.field_confidences = confidences
        analysis.overall_confidence = sum(scores) / len(scores) if scores else 0
        analysis.analyzed_at = datetime.now(UTC)
        if analysis.document_kind == "certificate":
            credential = session.scalar(
                select(MarketplaceCredentialDocument).where(
                    MarketplaceCredentialDocument.analysis_id == analysis.id
                )
            )
            if credential:
                credential.status = "analyzed"
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        analysis.status = "failed"
        analysis.failure_code = str(exc)[:80]
        credential = session.scalar(
            select(MarketplaceCredentialDocument).where(
                MarketplaceCredentialDocument.analysis_id == analysis.id
            )
        )
        if credential:
            credential.status = "failed"
        path.unlink(missing_ok=True)
        analysis.temporary_path = None
        analysis.raw_expires_at = None
        commit_or_conflict(session)
        if str(exc) == "certificate_required_fields_missing":
            raise HTTPException(
                422,
                "CareSync could not reliably read both the certificate holder name and "
                "certificate number. Retake the photo with the full certificate flat, "
                "sharp, and without viewer labels.",
            ) from None
        raise HTTPException(
            503, "Local OCR analysis is unavailable; upload can be retried"
        ) from None
    path.unlink(missing_ok=True)
    analysis.temporary_path = None
    analysis.raw_expires_at = None
    commit_or_conflict(session)
    return _analysis_row(analysis)


def _owned_analysis(session, user_id: UUID, analysis_id: UUID, kind: str):
    value = session.scalar(
        select(MarketplaceDocumentAnalysis)
        .where(
            MarketplaceDocumentAnalysis.id == analysis_id,
            MarketplaceDocumentAnalysis.user_id == user_id,
            MarketplaceDocumentAnalysis.document_kind == kind,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, "Onboarding analysis not found")
    if value.status != "analyzed":
        raise HTTPException(409, "Only an analyzed proposal can be confirmed")
    return value


def _proposed_holder(analysis: MarketplaceDocumentAnalysis) -> tuple[str | None, bool]:
    proposal = _sanitized_certificate_proposal(analysis.proposal) or {}
    normalized = proposal.get("normalized_proposal") or {}
    holder = normalized.get("holder_name")
    return (str(holder).strip() if holder else None, bool(proposal.get("holder_name_mismatch")))


def _holder_name_parts(holder_name: str) -> tuple[str, str]:
    parts = holder_name.split()
    if (
        len(parts) < 2
        or len(parts) > 4
        or any(not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", part) for part in parts)
    ):
        raise HTTPException(
            422, "Extracted certificate holder name cannot safely update the account"
        )
    return parts[0], " ".join(parts[1:])


@router.post("/documents/{analysis_id}/confirm-certificate")
def confirm_certificate(
    analysis_id: UUID,
    payload: CertificateConfirmation,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    analysis = _owned_analysis(session, user.id, analysis_id, "certificate")
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None or profile.candidate_type != "certified_educator":
        raise HTTPException(409, "Select certified educator candidate type first")
    holder_name, mismatch = _proposed_holder(analysis)
    if mismatch and payload.mismatch_resolution is None:
        raise HTTPException(409, "Certificate holder name mismatch must be resolved")
    if payload.mismatch_resolution == "use_certificate_name":
        if not holder_name:
            raise HTTPException(422, "There is no certificate holder name mismatch to resolve")
        if mismatch:
            first_name, last_name = _holder_name_parts(holder_name)
            account = session.get(User, user.id)
            if account is None:
                raise HTTPException(404, "Candidate account not found")
            account.first_name = first_name
            account.last_name = last_name
    now = datetime.now(UTC)
    credential = session.scalar(
        select(MarketplaceCredentialDocument)
        .where(MarketplaceCredentialDocument.analysis_id == analysis.id)
        .with_for_update()
    )
    if credential is None:
        raise HTTPException(409, "The original certificate image is unavailable")
    previous = session.scalar(
        select(MarketplaceCredentialDocument)
        .where(
            MarketplaceCredentialDocument.user_id == user.id,
            MarketplaceCredentialDocument.is_current.is_(True),
        )
        .with_for_update()
    )
    if previous and previous.id != credential.id:
        previous.is_current = False
        previous.status = "superseded"
        # Release the partial unique current-version slot before promoting the
        # replacement in the same transaction (PostgreSQL and SQLite).
        flush_or_conflict(session)
    previous_type = previous.certificate_type if previous and previous.id != credential.id else None
    credential.status = "confirmed"
    credential.is_current = True
    credential.holder_name = holder_name
    credential.certificate_type = payload.certificate_type
    credential.certificate_number = payload.certificate_number
    credential.expiry_date = payload.expiry_date
    credential.confirmed_at = now
    profile.certification_type = payload.certificate_type
    profile.certification_number = payload.certificate_number
    profile.certification_expiry_date = payload.expiry_date
    profile.certification_verification_status = "unverified"
    profile.certification_provenance = "local_ocr"
    profile.certification_candidate_confirmed_at = now
    analysis.status = "confirmed"
    analysis.candidate_confirmed_at = now
    state = _state(session, user.id)
    if state.status != "complete":
        state.completed_steps = list(dict.fromkeys([*state.completed_steps, "certificate"]))
        state.status = "in_progress"
        state.current_step = "work_experience"
        state.version += 1
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="marketplace.credential_updated",
        entity_type="credential",
        entity_id=credential.id,
        payload={"source": "credential_vault"},
    )
    related_orgs = set(
        session.scalars(
            select(MarketplaceApplicationLink.organization_id).where(
                MarketplaceApplicationLink.user_id == user.id
            )
        )
    )
    related_orgs.update(
        session.scalars(
            select(MarketplaceInterest.organization_id).where(
                MarketplaceInterest.profile_user_id == user.id,
                MarketplaceInterest.status.in_(("requested", "accepted")),
            )
        )
    )
    related_orgs.update(
        session.scalars(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.status == "active",
            )
        )
    )
    for organization_id in related_orgs:
        set_rls_organization(session, organization_id)
        connected_candidates = session.scalars(
            select(AtsCandidate)
            .where(
                AtsCandidate.organization_id == organization_id,
                AtsCandidate.claimed_user_id == user.id,
            )
            .with_for_update()
        )
        for candidate in connected_candidates:
            candidate.certification_type = profile.certification_type
            candidate.certification_number = profile.certification_number
            candidate.certification_expiry_date = profile.certification_expiry_date
            candidate.certification_provenance = profile.certification_provenance
            candidate.certification_candidate_confirmed_at = (
                profile.certification_candidate_confirmed_at
            )
            candidate.certification_verification_status = "unverified"
            candidate.certification_verified_at = None
            candidate.certification_verified_by_user_id = None
            candidate.certification_review_note = None
        session.add(
            MarketplaceCredentialNotification(
                organization_id=organization_id,
                credential_id=credential.id,
                candidate_user_id=user.id,
                previous_certificate_type=previous_type,
                certificate_type=payload.certificate_type,
            )
        )
        session.add(
            RealtimeEvent(
                organization_id=organization_id,
                event_type="marketplace.credential_updated",
                entity_type="credential",
                entity_id=credential.id,
                payload={"source": "credential_vault"},
            )
        )
        notify_organization_members(
            session,
            organization_id=organization_id,
            permission_keys={"ats:read", "ats:manage", "ats:hire"},
            event_key=f"credential-updated:{credential.id}",
            category="credential",
            severity="info",
            title="Candidate credential updated",
            body="A connected candidate updated a childcare credential.",
            action_path="/jobs",
            action_entity_type="credential",
            action_entity_id=credential.id,
        )
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/documents/{analysis_id}/reject-certificate-result")
def reject_certificate_result(
    analysis_id: UUID,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    analysis = _owned_analysis(session, user.id, analysis_id, "certificate")
    analysis.status = "discarded"
    analysis.failure_code = "candidate_rejected_result"
    credential = session.scalar(
        select(MarketplaceCredentialDocument).where(
            MarketplaceCredentialDocument.analysis_id == analysis.id
        )
    )
    if credential:
        credential.status = "rejected"
    state = _state(session, user.id)
    state.completed_steps = [step for step in state.completed_steps if step != "certificate"]
    state.status = "in_progress"
    state.current_step = "certificate"
    state.completed_at = None
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/documents/{analysis_id}/confirm-work-history")
def confirm_work_history(
    analysis_id: UUID,
    payload: WorkConfirmation,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    for item in payload.work_history:
        if not isinstance(item, dict) or not str(item.get("employer", "")).strip():
            raise HTTPException(422, "Each work history item requires an employer")
    analysis = _owned_analysis(session, user.id, analysis_id, "resume")
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Create a marketplace profile first")
    now = datetime.now(UTC)
    profile.work_history = payload.work_history
    profile.work_history_provenance = "local_ocr"
    profile.work_history_candidate_confirmed_at = now
    analysis.status = "confirmed"
    analysis.candidate_confirmed_at = now
    state = _state(session, user.id)
    state.completed_steps = list(dict.fromkeys([*state.completed_steps, "work_experience"]))
    if _screening_enabled(request):
        _0030_work_history_next_step(session, user_id=user.id, profile=profile, state=state)
    else:
        state.status = "review"
        state.current_step = "review"
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/work-history/confirm-manual")
def confirm_manual_work_history(
    payload: WorkConfirmation,
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    """Confirm manual work history, including an explicit empty/no-experience list."""
    ensure_writable(request)
    for item in payload.work_history:
        if not isinstance(item, dict) or not str(item.get("employer", "")).strip():
            raise HTTPException(422, "Each work history item requires an employer")
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Create a marketplace profile first")
    now = datetime.now(UTC)
    profile.work_history = payload.work_history
    profile.work_history_provenance = "manual"
    profile.work_history_candidate_confirmed_at = now
    state = _state(session, user.id)
    state.completed_steps = list(dict.fromkeys([*state.completed_steps, "work_experience"]))
    if _screening_enabled(request):
        _0030_work_history_next_step(session, user_id=user.id, profile=profile, state=state)
    elif profile.candidate_type == "student":
        state.status = "review" if "student_details" in state.completed_steps else "in_progress"
        state.current_step = "review" if state.status == "review" else "student_details"
    else:
        state.status = "review" if "certificate" in state.completed_steps else "in_progress"
        state.current_step = "review" if state.status == "review" else "certificate"
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)


@router.post("/complete")
def complete_onboarding(
    request: Request, user: CompleteMarketplaceUser, session: SessionDependency
):
    ensure_writable(request)
    state = _state(session, user.id)
    profile = session.get(MarketplaceProfile, user.id)
    if profile is None or not profile.city.strip() or not profile.headline.strip():
        raise HTTPException(409, "City and professional headline are required")
    completed = set(state.completed_steps)
    screening = (
        session.get(MarketplaceScreeningProfile, user.id) if _screening_enabled(request) else None
    )
    if _screening_enabled(request):
        if screening is None or not screening_profile_complete(screening):
            raise HTTPException(409, "Complete the candidate pathway first")
        if (
            "work_experience" not in completed
            or profile.work_history_candidate_confirmed_at is None
        ):
            raise HTTPException(409, "Work experience must be candidate-confirmed")
        if not _has_current_screening_coverage(session, user.id):
            raise HTTPException(
                409, "Current confirmed police-check evidence must cover CRC and VSS"
            )
    educator_pathway = bool(screening and screening.pathway in {"educator", "educator_driver"})
    student_pathway = bool(screening and screening.pathway == "student_educator")
    driver_pathway = bool(screening and screening.pathway == "driver")
    if educator_pathway or (screening is None and profile.candidate_type == "certified_educator"):
        if not {"certificate", "work_experience"}.issubset(completed):
            raise HTTPException(409, "OCR certificate and work experience must be confirmed")
        confirmed_ocr = session.scalar(
            select(MarketplaceDocumentAnalysis.id).where(
                MarketplaceDocumentAnalysis.user_id == user.id,
                MarketplaceDocumentAnalysis.document_kind == "certificate",
                MarketplaceDocumentAnalysis.status == "confirmed",
            )
        )
        if (
            confirmed_ocr is None
            or profile.certification_provenance != "local_ocr"
            or profile.certification_candidate_confirmed_at is None
        ):
            raise HTTPException(409, "Certified educators require a confirmed OCR certificate")
    elif student_pathway or (screening is None and profile.candidate_type == "student"):
        if "student_details" not in completed:
            raise HTTPException(409, "Student education details must be confirmed")
        if not (
            profile.institution
            and profile.program
            and profile.expected_graduation_date
            and profile.expected_graduation_date >= date.today()
        ):
            raise HTTPException(409, "Student education details are incomplete")
        if any(
            (
                profile.certification_type,
                profile.certification_number,
                profile.certification_expiry_date,
                profile.certification_provenance,
            )
        ):
            raise HTTPException(409, "Student onboarding cannot include certification evidence")
    elif not driver_pathway:
        raise HTTPException(409, "Select certified educator or student candidate type")
    if screening is not None:
        state.completed_steps = list(dict.fromkeys([*state.completed_steps, "screening"]))
    state.status = "complete"
    state.current_step = "complete"
    state.completed_at = datetime.now(UTC)
    profile.onboarding_completed_at = state.completed_at
    state.version += 1
    commit_or_conflict(session)
    return _state_row(session, state)
