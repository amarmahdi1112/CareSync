"""Exact-retry services for private family-authority evidence objects."""

from __future__ import annotations

import hashlib
import os
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.common import restore_context
from app.api.basic.dependencies import BasicContext
from app.basic.childcare_commands import begin_command, record_command
from app.basic.family_authority import _family, _receipt_response, _utc
from app.basic.family_authority_schemas import (
    AuthorityEvidenceObjectAssessmentResponse,
    AuthorityEvidenceObjectCommandResponse,
    AuthorityEvidenceObjectResponse,
    AuthorityEvidenceObjectScanRequest,
)
from app.basic.family_evidence_vault import (
    MalwareScanResult,
    PrivateObjectHandle,
    ScannerUnavailable,
    StoredEvidenceObject,
    open_private_object,
    scan_private_object,
    validate_scanned_document,
)
from app.basic.models import (
    ChildcareCommandReceipt,
    FamilyAuthorityEvidenceObject,
    FamilyAuthorityEvidenceObjectAssessment,
    OrganizationMembership,
    Role,
)
from app.basic.security import audit
from app.core.config import Settings

OBJECT_UPLOAD_COMMAND = "family.authority.evidence_object.upload"
OBJECT_SCAN_COMMAND = "family.authority.evidence_object.scan"
OBJECT_TARGET_TYPE = "authority_evidence_object"


class EvidenceObjectCommitAmbiguous(RuntimeError):
    """The database could have committed; private bytes must be retained."""


def _commit(session: Session, context: BasicContext, detail: dict[str, str]) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from None
    except DBAPIError as error:
        session.rollback()
        raise EvidenceObjectCommitAmbiguous from error
    restore_context(session, context)
    # PostgreSQL receipt guards author the canonical committed timestamp.  Do
    # not expose the pre-trigger ORM default on the first response when exact
    # replay will load the persisted value.
    session.expire_all()


def _flush(session: Session, detail: dict[str, str]) -> None:
    try:
        session.flush()
    except (IntegrityError, DBAPIError):
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from None


def require_current_family_authority_admin(
    session: Session,
    context: BasicContext,
) -> None:
    """Hold the exact membership and role stable through the authority commit."""

    membership = session.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == context.organization.id,
            OrganizationMembership.id == context.membership.id,
            OrganizationMembership.user_id == context.user.id,
            OrganizationMembership.status == "active",
        )
        .with_for_update(read=True)
    )
    if membership is None:
        raise HTTPException(403, detail={"code": "family_authority_access_revoked"})
    role = session.scalar(
        select(Role)
        .where(
            Role.organization_id == context.organization.id,
            Role.id == membership.role_id,
            Role.key.in_(("owner", "administrator")),
        )
        .with_for_update(read=True)
    )
    if role is None:
        raise HTTPException(403, detail={"code": "family_authority_access_revoked"})


def _assessment_response(
    value: FamilyAuthorityEvidenceObjectAssessment,
) -> AuthorityEvidenceObjectAssessmentResponse:
    return AuthorityEvidenceObjectAssessmentResponse(
        id=value.id,
        version_number=value.version_number,
        decision=value.decision,
        scanner_engine=value.scanner_engine,
        scanner_version=value.scanner_version,
        scanner_signature=value.scanner_signature,
        reason_code=value.reason_code,
        actor_user_id=value.actor_user_id,
        created_at=_utc(value.created_at),
    )


def _current_assessment(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    object_id: UUID,
) -> FamilyAuthorityEvidenceObjectAssessment:
    statement = (
        select(FamilyAuthorityEvidenceObjectAssessment)
        .where(
            FamilyAuthorityEvidenceObjectAssessment.organization_id == organization_id,
            FamilyAuthorityEvidenceObjectAssessment.family_id == family_id,
            FamilyAuthorityEvidenceObjectAssessment.evidence_object_id == object_id,
        )
        .order_by(FamilyAuthorityEvidenceObjectAssessment.version_number.desc())
        .limit(1)
    )
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(409, detail={"code": "evidence_object_assessment_missing"})
    return value


def evidence_object_response(
    session: Session,
    value: FamilyAuthorityEvidenceObject,
    assessment: FamilyAuthorityEvidenceObjectAssessment | None = None,
) -> AuthorityEvidenceObjectResponse:
    current = assessment or _current_assessment(
        session,
        value.organization_id,
        value.family_id,
        value.id,
    )
    if current.version_number not in {1, 2} or current.decision != value.status:
        raise HTTPException(409, detail={"code": "evidence_object_state_invalid"})
    return AuthorityEvidenceObjectResponse(
        id=value.id,
        organization_id=value.organization_id,
        family_id=value.family_id,
        evidence_kind=value.evidence_kind,
        version=current.version_number,
        lifecycle_status=value.status,
        valid_for_evidence=value.status == "clean",
        object_version=value.object_version,
        media_type=value.media_type,
        byte_size=value.byte_size,
        content_sha256=value.content_sha256,
        original_filename=value.original_filename,
        uploaded_by_user_id=value.uploaded_by_user_id,
        created_at=_utc(value.created_at),
        current_assessment=_assessment_response(current),
    )


def _object(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    object_id: UUID,
    *,
    lock: bool = False,
) -> FamilyAuthorityEvidenceObject:
    statement = select(FamilyAuthorityEvidenceObject).where(
        FamilyAuthorityEvidenceObject.organization_id == organization_id,
        FamilyAuthorityEvidenceObject.family_id == family_id,
        FamilyAuthorityEvidenceObject.id == object_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(404, detail="Authority evidence object not found")
    return value


def _load_for_receipt(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    receipt: ChildcareCommandReceipt,
) -> tuple[FamilyAuthorityEvidenceObject, FamilyAuthorityEvidenceObjectAssessment]:
    if receipt.target_type != OBJECT_TARGET_TYPE:
        raise HTTPException(409, detail={"code": "operation_receipt_incomplete"})
    value = _object(session, organization_id, family_id, receipt.target_id)
    assessment = _current_assessment(session, organization_id, family_id, value.id)
    if assessment.version_number < receipt.committed_version:
        raise HTTPException(409, detail={"code": "operation_receipt_incomplete"})
    return value, assessment


def _command_response(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    replayed: bool,
) -> AuthorityEvidenceObjectCommandResponse:
    value, assessment = _load_for_receipt(session, organization_id, family_id, receipt)
    return AuthorityEvidenceObjectCommandResponse(
        resource=evidence_object_response(session, value, assessment),
        receipt=_receipt_response(receipt),
        replayed=replayed,
    )


def record_evidence_object_upload(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    object_id: UUID,
    evidence_kind: str,
    client_operation_id: UUID,
    stored: StoredEvidenceObject,
) -> AuthorityEvidenceObjectCommandResponse:
    organization_id = context.organization.id
    intent = {
        "evidence_kind": evidence_kind,
        "object_version": 1,
        "media_type": stored.media_type,
        "byte_size": stored.byte_size,
        "content_sha256": stored.content_sha256,
        "original_filename": stored.original_filename,
    }
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=OBJECT_UPLOAD_COMMAND,
        target_type=OBJECT_TARGET_TYPE,
        target_scope=f"family:{family_id}:authority_evidence_object:upload",
        intent=intent,
    )
    if receipt is not None:
        return _command_response(
            session,
            organization_id,
            family_id,
            receipt,
            replayed=True,
        )
    _family(session, organization_id, family_id, for_update=True)
    require_current_family_authority_admin(session, context)
    command_receipt = record_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=OBJECT_UPLOAD_COMMAND,
        target_type=OBJECT_TARGET_TYPE,
        target_id=object_id,
        request_hash=request_hash,
        committed_version=1,
        outcome={
            "action_route": (f"/families/{family_id}?authority_evidence_object_id={object_id}")
        },
    )
    _flush(session, {"code": "evidence_object_upload_conflict"})
    value = FamilyAuthorityEvidenceObject(
        id=object_id,
        organization_id=organization_id,
        family_id=family_id,
        evidence_kind=evidence_kind,
        object_version=1,
        storage_reference=stored.storage_reference,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        content_sha256=stored.content_sha256,
        original_filename=stored.original_filename,
        status="quarantined",
        uploaded_by_user_id=context.user.id,
        uploaded_operation_id=client_operation_id,
    )
    assessment = FamilyAuthorityEvidenceObjectAssessment(
        organization_id=organization_id,
        family_id=family_id,
        evidence_object_id=object_id,
        version_number=1,
        decision="quarantined",
        scanner_engine=None,
        scanner_version=None,
        scanner_signature=None,
        reason_code=None,
        actor_user_id=context.user.id,
        operation_id=client_operation_id,
    )
    session.add_all([value, assessment])
    _flush(session, {"code": "evidence_object_upload_conflict"})
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="family.authority.evidence_object.uploaded",
        entity_type="authority_evidence_object",
        entity_id=object_id,
        details={"operation_id": str(client_operation_id), "transition": "quarantined"},
    )
    _flush(session, {"code": "evidence_object_upload_conflict"})
    _commit(session, context, {"code": "evidence_object_upload_conflict"})
    return AuthorityEvidenceObjectCommandResponse(
        resource=evidence_object_response(session, value, assessment),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def _verify_stored_measurements(
    handle: PrivateObjectHandle,
    value: FamilyAuthorityEvidenceObject,
) -> None:
    handle.validate_private_inode(value.byte_size)
    digest = hashlib.sha256()
    total = 0
    handle.rewind()
    while True:
        chunk = os.read(handle.descriptor, 64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        digest.update(chunk)
    handle.rewind()
    if total != value.byte_size or digest.hexdigest() != value.content_sha256:
        raise RuntimeError("Evidence object measurements changed")


def scan_evidence_object(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    object_id: UUID,
    payload: AuthorityEvidenceObjectScanRequest,
    settings: Settings,
) -> AuthorityEvidenceObjectCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=OBJECT_SCAN_COMMAND,
        target_type=OBJECT_TARGET_TYPE,
        target_scope=f"family:{family_id}:authority_evidence_object:{object_id}",
        intent={"expected_version": payload.expected_version},
    )
    if receipt is not None:
        return _command_response(
            session,
            organization_id,
            family_id,
            receipt,
            replayed=True,
        )
    _family(session, organization_id, family_id, for_update=True)
    require_current_family_authority_admin(session, context)
    value = _object(session, organization_id, family_id, object_id, lock=True)
    assessment = _current_assessment(
        session,
        organization_id,
        family_id,
        object_id,
    )
    if (
        payload.expected_version != assessment.version_number
        or value.status != "quarantined"
        or assessment.decision != "quarantined"
    ):
        raise HTTPException(
            409,
            detail={
                "code": "stale_evidence_object",
                "expected_version": payload.expected_version,
                "current_version": assessment.version_number,
            },
        )
    try:
        with open_private_object(settings, value.storage_reference) as handle:
            _verify_stored_measurements(handle, value)
            result = scan_private_object(handle, settings)
            if result.decision == "clean":
                try:
                    validate_scanned_document(handle, value.media_type, settings)
                except HTTPException:
                    result = MalwareScanResult(
                        decision="rejected",
                        scanner_engine=result.scanner_engine,
                        scanner_version=result.scanner_version,
                        scanner_signature=None,
                        reason_code="invalid_document",
                    )
            # A local writer cannot alter and restore bytes around only one
            # verification boundary without the post-scan check detecting it.
            _verify_stored_measurements(handle, value)
    except ScannerUnavailable as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": str(error)},
        ) from None
    except (OSError, RuntimeError):
        session.rollback()
        raise HTTPException(409, detail={"code": "evidence_object_integrity_failed"}) from None
    command_receipt = record_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=OBJECT_SCAN_COMMAND,
        target_type=OBJECT_TARGET_TYPE,
        target_id=object_id,
        request_hash=request_hash,
        committed_version=2,
        outcome={
            "action_route": (f"/families/{family_id}?authority_evidence_object_id={object_id}")
        },
    )
    _flush(session, {"code": "evidence_object_scan_conflict"})
    value.status = result.decision
    terminal = FamilyAuthorityEvidenceObjectAssessment(
        organization_id=organization_id,
        family_id=family_id,
        evidence_object_id=object_id,
        version_number=2,
        decision=result.decision,
        scanner_engine=result.scanner_engine[:80],
        scanner_version=result.scanner_version[:160],
        scanner_signature=(result.scanner_signature[:160] if result.scanner_signature else None),
        reason_code=result.reason_code,
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
    )
    session.add(terminal)
    _flush(session, {"code": "evidence_object_scan_conflict"})
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action=f"family.authority.evidence_object.{result.decision}",
        entity_type="authority_evidence_object",
        entity_id=object_id,
        details={
            "operation_id": str(payload.client_operation_id),
            "transition": result.decision,
        },
    )
    _flush(session, {"code": "evidence_object_scan_conflict"})
    _commit(session, context, {"code": "evidence_object_scan_conflict"})
    # Rejected bytes remain in the private 0600 vault. They are never eligible
    # for download or evidence binding, while immutable metadata remains truthful.
    return AuthorityEvidenceObjectCommandResponse(
        resource=evidence_object_response(session, value, terminal),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def clean_object_for_evidence(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    object_id: UUID,
    evidence_kind: str,
    settings: Settings,
    *,
    lock: bool = False,
) -> FamilyAuthorityEvidenceObject:
    value = _object(session, organization_id, family_id, object_id, lock=lock)
    assessment = _current_assessment(
        session,
        organization_id,
        family_id,
        object_id,
    )
    if value.status != "clean" or assessment.version_number != 2 or assessment.decision != "clean":
        raise HTTPException(409, detail={"code": "evidence_object_not_clean"})
    if value.evidence_kind != evidence_kind:
        raise HTTPException(409, detail={"code": "evidence_object_kind_mismatch"})
    try:
        with open_private_object(settings, value.storage_reference) as handle:
            _verify_stored_measurements(handle, value)
    except (OSError, RuntimeError):
        raise HTTPException(409, detail={"code": "evidence_object_integrity_failed"}) from None
    return value


def list_family_evidence_objects(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
) -> list[AuthorityEvidenceObjectResponse]:
    values = list(
        session.scalars(
            select(FamilyAuthorityEvidenceObject)
            .where(
                FamilyAuthorityEvidenceObject.organization_id == organization_id,
                FamilyAuthorityEvidenceObject.family_id == family_id,
            )
            .order_by(FamilyAuthorityEvidenceObject.created_at, FamilyAuthorityEvidenceObject.id)
        )
    )
    return [evidence_object_response(session, value) for value in values]


def clean_evidence_object_download(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    object_id: UUID,
    settings: Settings,
) -> tuple[FamilyAuthorityEvidenceObject, PrivateObjectHandle]:
    require_current_family_authority_admin(session, context)
    value = _object(session, context.organization.id, family_id, object_id)
    assessment = _current_assessment(
        session,
        context.organization.id,
        family_id,
        object_id,
    )
    if value.status != "clean" or assessment.decision != "clean":
        raise HTTPException(409, detail={"code": "evidence_object_not_clean"})
    try:
        handle = open_private_object(settings, value.storage_reference)
        _verify_stored_measurements(handle, value)
    except (OSError, RuntimeError):
        if "handle" in locals():
            handle.close()
        raise HTTPException(409, detail={"code": "evidence_object_integrity_failed"}) from None
    return value, handle
