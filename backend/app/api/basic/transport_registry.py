"""Capability-gated 0032 staff and manager transport-registry API."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import func, select

from app.api.basic.common import ensure_writable
from app.api.basic.dependencies import (
    BasicContextDependency,
    require_complete_if_marketplace_user,
    require_permission,
)
from app.api.dependencies import SessionDependency
from app.basic.models import (
    OrganizationMembership,
    StaffDriverAuthorizationDecision,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationReviewDecision,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    TransportVehicle,
    TransportVehicleEvidenceReviewDecision,
    TransportVehicleEvidenceVersion,
    TransportVehicleVersion,
    User,
)
from app.basic.staff_screening_vault import (
    StoredScreeningObject,
    delete_screening_object,
    read_encrypted_screening_object,
    store_encrypted_screening_upload,
)
from app.basic.transport_registry_command_schemas import (
    DriverAuthorizationCommand,
    DriverDeclarationCommand,
    OrganizationVehicleCreateCommand,
    PersonalVehicleCreateCommand,
    QualificationEvidenceFields,
    QualificationReviewCommand,
    ReadinessEvaluationCommand,
    TransportCommandReceiptResponse,
    TransportRegistryCommandCapability,
    TransportRegistryWorkspaceResponse,
    VehicleEvidenceFields,
    VehicleEvidenceReviewCommand,
    VehicleRetireCommand,
    VehicleVersionCommand,
)
from app.basic.transport_registry_commands import (
    AmbiguousTransportCommandCommit,
    CommandKind,
    execute_transport_command,
)

self_router = APIRouter(
    prefix="/staff/self/transport-registry",
    tags=["staff transport registry"],
    dependencies=[Depends(require_complete_if_marketplace_user)],
)
manager_router = APIRouter(prefix="/staff/transport-registry", tags=["transport registry"])
TransportManageContext = Annotated[Any, Depends(require_permission("transport:manage"))]


def _require_commands(request: Request) -> None:
    if request.app.state.settings.database_type != "postgres" or not bool(
        getattr(request.app.state, "transport_registry_commands_enabled", False)
    ):
        raise HTTPException(503, detail={"code": "transport_registry_commands_unavailable"})


def _require_evidence_ingest(request: Request) -> None:
    _require_commands(request)
    if (
        not bool(
            getattr(
                request.app.state,
                "transport_registry_evidence_ingest_available",
                False,
            )
        )
        or not bool(
            getattr(
                request.app.state,
                "transport_registry_evidence_pipeline_available",
                False,
            )
        )
        or getattr(request.app.state, "transport_evidence_session_factory", None) is None
    ):
        raise HTTPException(503, detail={"code": "transport_evidence_ingest_unavailable"})


def _evidence_upload_available(request: Request) -> bool:
    return bool(
        getattr(request.app.state, "transport_registry_evidence_ingest_available", False)
        and getattr(request.app.state, "transport_registry_evidence_pipeline_available", False)
        and getattr(request.app.state, "transport_evidence_session_factory", None) is not None
    )


def _public_payload(model, **server_targets: Any) -> tuple[UUID, dict[str, Any]]:
    values = model.model_dump(mode="json")
    operation_id = UUID(values.pop("operation_id"))
    return operation_id, {**server_targets, **values}


def _execute(
    *,
    request: Request,
    session,
    context,
    command_kind: CommandKind,
    operation_id: UUID,
    public_payload: dict[str, Any],
):
    _require_commands(request)
    ensure_writable(request)
    return execute_transport_command(
        session=session,
        context=context,
        command_kind=command_kind,
        operation_id=operation_id,
        public_payload=public_payload,
    ).as_response()


def _stored_payload(stored: StoredScreeningObject) -> dict[str, Any]:
    return {
        "original_filename": stored.original_filename,
        "media_type": stored.media_type,
        "byte_size": stored.byte_size,
        "content_sha256": stored.content_sha256,
        "ciphertext_sha256": stored.ciphertext_sha256,
        "storage_reference": stored.storage_reference,
        "encryption_key_id": stored.encryption_key_id,
        "scanner_engine": stored.scanner_engine,
        "scanner_version": stored.scanner_version,
        "scanned_at": stored.scanned_at.isoformat(),
    }


async def _execute_evidence(
    *,
    request: Request,
    session,
    context,
    command_kind: CommandKind,
    operation_id: UUID,
    public_payload: dict[str, Any],
    file: UploadFile,
    document_id: UUID,
):
    _require_evidence_ingest(request)
    ensure_writable(request)
    try:
        stored = await store_encrypted_screening_upload(
            file,
            settings=request.app.state.settings,
            user_id=context.user.id,
            document_id=document_id,
            version_id=uuid4(),
        )
    except (OSError, RuntimeError):
        raise HTTPException(
            503, detail={"code": "transport_evidence_pipeline_unavailable"}
        ) from None
    try:
        result = execute_transport_command(
            session=session,
            context=context,
            command_kind=command_kind,
            operation_id=operation_id,
            public_payload={**public_payload, **_stored_payload(stored)},
            evidence_session_factory=request.app.state.transport_evidence_session_factory,
        )
    except AmbiguousTransportCommandCommit as error:
        raise HTTPException(
            503,
            detail={
                "code": "transport_command_commit_unknown",
                "operation_id": str(operation_id),
                "recovery": "Retry the same command with the same operation_id and file.",
            },
        ) from error
    except BaseException:
        delete_screening_object(request.app.state.settings, stored.storage_reference)
        raise
    if result.exact_retry:
        delete_screening_object(request.app.state.settings, stored.storage_reference)
    return result.as_response()


@self_router.post("/declarations", response_model=TransportCommandReceiptResponse, status_code=201)
def declare_driver(
    payload: DriverDeclarationCommand,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, membership_id=str(context.membership.id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="driver_declaration",
        operation_id=operation_id,
        public_payload=values,
    )


@self_router.post(
    "/qualification-evidence",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
async def upload_qualification_evidence(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
    operation_id: Annotated[UUID, Form()],
    qualification_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    jurisdiction: Annotated[str | None, Form()] = None,
    qualification_class: Annotated[str | None, Form()] = None,
    identifier_last4: Annotated[str | None, Form()] = None,
    issue_date: Annotated[date | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
):
    fields = QualificationEvidenceFields(
        operation_id=operation_id,
        qualification_type=qualification_type,
        jurisdiction=jurisdiction,
        qualification_class=qualification_class,
        identifier_last4=identifier_last4,
        issue_date=issue_date,
        expiry_date=expiry_date,
    )
    selected_operation, values = _public_payload(fields, membership_id=str(context.membership.id))
    return await _execute_evidence(
        request=request,
        session=session,
        context=context,
        command_kind="qualification_evidence",
        operation_id=selected_operation,
        public_payload=values,
        file=file,
        document_id=context.membership.id,
    )


@self_router.post("/vehicles", response_model=TransportCommandReceiptResponse, status_code=201)
def create_personal_vehicle(
    payload: PersonalVehicleCreateCommand,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    operation_id, values = _public_payload(
        payload,
        owner_kind="staff_personal",
        staff_owner_membership_id=str(context.membership.id),
    )
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_create",
        operation_id=operation_id,
        public_payload=values,
    )


@self_router.post(
    "/vehicles/{vehicle_id}/versions",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def version_personal_vehicle(
    vehicle_id: UUID,
    payload: VehicleVersionCommand,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, vehicle_id=str(vehicle_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_version",
        operation_id=operation_id,
        public_payload=values,
    )


@self_router.post(
    "/vehicles/{vehicle_id}/retire",
    response_model=TransportCommandReceiptResponse,
)
def retire_personal_vehicle(
    vehicle_id: UUID,
    payload: VehicleRetireCommand,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, vehicle_id=str(vehicle_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_retire",
        operation_id=operation_id,
        public_payload=values,
    )


@self_router.post(
    "/vehicles/{vehicle_id}/evidence",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
async def upload_personal_vehicle_evidence(
    vehicle_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
    operation_id: Annotated[UUID, Form()],
    evidence_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    issue_date: Annotated[date | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
):
    fields = VehicleEvidenceFields(
        operation_id=operation_id,
        evidence_type=evidence_type,
        issue_date=issue_date,
        expiry_date=expiry_date,
    )
    selected_operation, values = _public_payload(fields, vehicle_id=str(vehicle_id))
    return await _execute_evidence(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_evidence",
        operation_id=selected_operation,
        public_payload=values,
        file=file,
        document_id=vehicle_id,
    )


def _private_content_response(request: Request, evidence) -> Response:
    try:
        content = read_encrypted_screening_object(
            settings=request.app.state.settings,
            storage_reference=evidence.storage_reference,
            media_type=evidence.media_type,
            encryption_key_id=evidence.encryption_key_id,
            expected_ciphertext_sha256=evidence.ciphertext_sha256,
            expected_content_sha256=evidence.content_sha256,
            expected_byte_size=evidence.byte_size,
            maximum_bytes=request.app.state.settings.staff_screening_document_max_bytes,
        )
    except (OSError, RuntimeError):
        raise HTTPException(
            503, detail={"code": "transport_evidence_content_unavailable"}
        ) from None
    filename = evidence.original_filename or "transport-evidence"
    return Response(
        content=content,
        media_type=evidence.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


def _qualification_evidence_for_result(
    session,
    *,
    organization_id: UUID,
    membership_id: UUID,
    qualification_version_id: UUID,
):
    evidence = session.scalar(
        select(StaffDriverQualificationEvidenceObject).where(
            StaffDriverQualificationEvidenceObject.organization_id == organization_id,
            StaffDriverQualificationEvidenceObject.membership_id == membership_id,
            StaffDriverQualificationEvidenceObject.qualification_version_id
            == qualification_version_id,
        )
    )
    if evidence is not None:
        return evidence
    qualification = session.scalar(
        select(StaffDriverQualificationVersion).where(
            StaffDriverQualificationVersion.organization_id == organization_id,
            StaffDriverQualificationVersion.membership_id == membership_id,
            StaffDriverQualificationVersion.id == qualification_version_id,
        )
    )
    if qualification is None or qualification.evidence_reference_sha256 is None:
        return None
    return session.scalar(
        select(StaffDriverQualificationEvidenceObject)
        .where(
            StaffDriverQualificationEvidenceObject.organization_id == organization_id,
            StaffDriverQualificationEvidenceObject.membership_id == membership_id,
            StaffDriverQualificationEvidenceObject.content_sha256
            == qualification.evidence_reference_sha256,
        )
        .order_by(
            StaffDriverQualificationEvidenceObject.recorded_at.desc(),
            StaffDriverQualificationEvidenceObject.id.desc(),
        )
        .limit(1)
    )


@self_router.get("/qualification-evidence/{qualification_version_id}/content")
def self_qualification_evidence_content(
    qualification_version_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    _require_commands(request)
    evidence = _qualification_evidence_for_result(
        session,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        qualification_version_id=qualification_version_id,
    )
    if evidence is None:
        raise HTTPException(404, "Qualification evidence not found")
    return _private_content_response(request, evidence)


@self_router.get("/vehicles/{vehicle_id}/evidence/{evidence_version_id}/content")
def self_vehicle_evidence_content(
    vehicle_id: UUID,
    evidence_version_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    _require_commands(request)
    owned_vehicle = session.scalar(
        select(TransportVehicle.id).where(
            TransportVehicle.organization_id == context.organization.id,
            TransportVehicle.id == vehicle_id,
            TransportVehicle.owner_kind == "staff_personal",
            TransportVehicle.staff_owner_membership_id == context.membership.id,
        )
    )
    if owned_vehicle is None:
        raise HTTPException(404, "Vehicle evidence not found")
    evidence = session.scalar(
        select(TransportVehicleEvidenceVersion).where(
            TransportVehicleEvidenceVersion.organization_id == context.organization.id,
            TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
            TransportVehicleEvidenceVersion.id == evidence_version_id,
        )
    )
    if evidence is None:
        raise HTTPException(404, "Vehicle evidence not found")
    return _private_content_response(request, evidence)


@manager_router.get("/capability", response_model=TransportRegistryCommandCapability)
def transport_registry_capability(
    request: Request,
    _context: TransportManageContext,
):
    _require_commands(request)
    return TransportRegistryCommandCapability(
        evidence_upload_available=_evidence_upload_available(request)
    )


@manager_router.get("/{membership_id}/qualification-evidence/{qualification_version_id}/content")
def manager_qualification_evidence_content(
    membership_id: UUID,
    qualification_version_id: UUID,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    _require_commands(request)
    evidence = _qualification_evidence_for_result(
        session,
        organization_id=context.organization.id,
        membership_id=membership_id,
        qualification_version_id=qualification_version_id,
    )
    if evidence is None:
        raise HTTPException(404, "Qualification evidence not found")
    return _private_content_response(request, evidence)


@manager_router.get("/vehicles/{vehicle_id}/evidence/{evidence_version_id}/content")
def manager_vehicle_evidence_content(
    vehicle_id: UUID,
    evidence_version_id: UUID,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    _require_commands(request)
    evidence = session.scalar(
        select(TransportVehicleEvidenceVersion).where(
            TransportVehicleEvidenceVersion.organization_id == context.organization.id,
            TransportVehicleEvidenceVersion.vehicle_id == vehicle_id,
            TransportVehicleEvidenceVersion.id == evidence_version_id,
        )
    )
    if evidence is None:
        raise HTTPException(404, "Vehicle evidence not found")
    return _private_content_response(request, evidence)


@manager_router.get("", response_model=TransportRegistryWorkspaceResponse)
def transport_registry_workspace(
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    _require_commands(request)
    organization_id = context.organization.id
    membership_rows = list(
        session.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == "active",
            )
            .order_by(User.last_name, User.first_name, OrganizationMembership.id)
            .limit(201)
        )
    )
    staff_truncated = len(membership_rows) > 200
    selected_memberships = membership_rows[:200]
    membership_ids = [membership.id for membership, _user in selected_memberships]
    capabilities_by_membership: dict[UUID, list[tuple[StaffDriverCapabilityVersion, int]]] = (
        defaultdict(list)
    )
    qualifications_by_membership: dict[UUID, list[tuple[StaffDriverQualificationVersion, int]]] = (
        defaultdict(list)
    )
    qualification_reviews_by_membership: dict[
        UUID, list[tuple[StaffDriverQualificationReviewDecision, int]]
    ] = defaultdict(list)
    authorizations_by_membership: dict[UUID, list[tuple[StaffDriverAuthorizationDecision, int]]] = (
        defaultdict(list)
    )
    readiness_by_membership: dict[UUID, list[tuple[StaffDriverReadinessDecision, int]]] = (
        defaultdict(list)
    )
    qualification_evidence_ids: set[UUID] = set()

    if membership_ids:
        capability_rank = (
            select(
                StaffDriverCapabilityVersion.id.label("capability_id"),
                func.row_number()
                .over(
                    partition_by=StaffDriverCapabilityVersion.membership_id,
                    order_by=StaffDriverCapabilityVersion.version_number.desc(),
                )
                .label("history_rank"),
            )
            .where(
                StaffDriverCapabilityVersion.organization_id == organization_id,
                StaffDriverCapabilityVersion.membership_id.in_(membership_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(StaffDriverCapabilityVersion, capability_rank.c.history_rank)
            .join(
                capability_rank,
                capability_rank.c.capability_id == StaffDriverCapabilityVersion.id,
            )
            .where(
                StaffDriverCapabilityVersion.organization_id == organization_id,
                capability_rank.c.history_rank <= 21,
            )
            .order_by(
                StaffDriverCapabilityVersion.membership_id,
                StaffDriverCapabilityVersion.version_number.desc(),
            )
        ):
            capabilities_by_membership[row.membership_id].append((row, history_rank))

        qualification_rank = (
            select(
                StaffDriverQualificationVersion.id.label("qualification_id"),
                func.row_number()
                .over(
                    partition_by=(
                        StaffDriverQualificationVersion.membership_id,
                        StaffDriverQualificationVersion.qualification_type,
                    ),
                    order_by=StaffDriverQualificationVersion.version_number.desc(),
                )
                .label("lane_rank"),
            )
            .where(
                StaffDriverQualificationVersion.organization_id == organization_id,
                StaffDriverQualificationVersion.membership_id.in_(membership_ids),
            )
            .subquery()
        )
        for row, lane_rank in session.execute(
            select(StaffDriverQualificationVersion, qualification_rank.c.lane_rank)
            .join(
                qualification_rank,
                qualification_rank.c.qualification_id == StaffDriverQualificationVersion.id,
            )
            .where(
                StaffDriverQualificationVersion.organization_id == organization_id,
                qualification_rank.c.lane_rank <= 21,
            )
            .order_by(
                StaffDriverQualificationVersion.membership_id,
                StaffDriverQualificationVersion.qualification_type,
                StaffDriverQualificationVersion.version_number.desc(),
            )
        ):
            qualifications_by_membership[row.membership_id].append((row, lane_rank))

        direct_evidence = (
            select(
                StaffDriverQualificationEvidenceObject.qualification_version_id.label(
                    "qualification_id"
                )
            )
            .join(
                qualification_rank,
                qualification_rank.c.qualification_id
                == StaffDriverQualificationEvidenceObject.qualification_version_id,
            )
            .where(
                StaffDriverQualificationEvidenceObject.organization_id == organization_id,
                StaffDriverQualificationEvidenceObject.membership_id.in_(membership_ids),
                qualification_rank.c.lane_rank <= 20,
            )
        )
        reviewed_evidence = (
            select(
                StaffDriverQualificationReviewDecision.result_qualification_version_id.label(
                    "qualification_id"
                )
            )
            .join(
                qualification_rank,
                qualification_rank.c.qualification_id
                == StaffDriverQualificationReviewDecision.result_qualification_version_id,
            )
            .join(
                StaffDriverQualificationEvidenceObject,
                (
                    StaffDriverQualificationEvidenceObject.organization_id
                    == StaffDriverQualificationReviewDecision.organization_id
                )
                & (
                    StaffDriverQualificationEvidenceObject.membership_id
                    == StaffDriverQualificationReviewDecision.membership_id
                )
                & (
                    StaffDriverQualificationEvidenceObject.qualification_version_id
                    == StaffDriverQualificationReviewDecision.source_qualification_version_id
                ),
            )
            .where(
                StaffDriverQualificationReviewDecision.organization_id == organization_id,
                StaffDriverQualificationReviewDecision.membership_id.in_(membership_ids),
                StaffDriverQualificationEvidenceObject.organization_id == organization_id,
                qualification_rank.c.lane_rank <= 20,
            )
        )
        qualification_evidence_ids = set(session.scalars(direct_evidence.union(reviewed_evidence)))

        qualification_review_rank = (
            select(
                StaffDriverQualificationReviewDecision.id.label("review_id"),
                func.row_number()
                .over(
                    partition_by=StaffDriverQualificationReviewDecision.membership_id,
                    order_by=(
                        StaffDriverQualificationReviewDecision.reviewed_at.desc(),
                        StaffDriverQualificationReviewDecision.id.desc(),
                    ),
                )
                .label("history_rank"),
            )
            .where(
                StaffDriverQualificationReviewDecision.organization_id == organization_id,
                StaffDriverQualificationReviewDecision.membership_id.in_(membership_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(
                StaffDriverQualificationReviewDecision,
                qualification_review_rank.c.history_rank,
            )
            .join(
                qualification_review_rank,
                qualification_review_rank.c.review_id == StaffDriverQualificationReviewDecision.id,
            )
            .where(
                StaffDriverQualificationReviewDecision.organization_id == organization_id,
                qualification_review_rank.c.history_rank <= 21,
            )
            .order_by(
                StaffDriverQualificationReviewDecision.membership_id,
                StaffDriverQualificationReviewDecision.reviewed_at.desc(),
                StaffDriverQualificationReviewDecision.id.desc(),
            )
        ):
            qualification_reviews_by_membership[row.membership_id].append((row, history_rank))

        authorization_rank = (
            select(
                StaffDriverAuthorizationDecision.id.label("authorization_id"),
                func.row_number()
                .over(
                    partition_by=StaffDriverAuthorizationDecision.membership_id,
                    order_by=StaffDriverAuthorizationDecision.decision_sequence.desc(),
                )
                .label("history_rank"),
            )
            .where(
                StaffDriverAuthorizationDecision.organization_id == organization_id,
                StaffDriverAuthorizationDecision.membership_id.in_(membership_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(StaffDriverAuthorizationDecision, authorization_rank.c.history_rank)
            .join(
                authorization_rank,
                authorization_rank.c.authorization_id == StaffDriverAuthorizationDecision.id,
            )
            .where(
                StaffDriverAuthorizationDecision.organization_id == organization_id,
                authorization_rank.c.history_rank <= 21,
            )
            .order_by(
                StaffDriverAuthorizationDecision.membership_id,
                StaffDriverAuthorizationDecision.decision_sequence.desc(),
            )
        ):
            authorizations_by_membership[row.membership_id].append((row, history_rank))

        readiness_rank = (
            select(
                StaffDriverReadinessDecision.id.label("readiness_id"),
                func.row_number()
                .over(
                    partition_by=StaffDriverReadinessDecision.membership_id,
                    order_by=StaffDriverReadinessDecision.decision_sequence.desc(),
                )
                .label("history_rank"),
            )
            .where(
                StaffDriverReadinessDecision.organization_id == organization_id,
                StaffDriverReadinessDecision.membership_id.in_(membership_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(StaffDriverReadinessDecision, readiness_rank.c.history_rank)
            .join(
                readiness_rank,
                readiness_rank.c.readiness_id == StaffDriverReadinessDecision.id,
            )
            .where(
                StaffDriverReadinessDecision.organization_id == organization_id,
                readiness_rank.c.history_rank <= 21,
            )
            .order_by(
                StaffDriverReadinessDecision.membership_id,
                StaffDriverReadinessDecision.decision_sequence.desc(),
            )
        ):
            readiness_by_membership[row.membership_id].append((row, history_rank))

    staff_rows = []
    for membership, user in selected_memberships:
        capability_rows = capabilities_by_membership[membership.id]
        capabilities_truncated = any(rank > 20 for _row, rank in capability_rows)
        capabilities = [row for row, rank in capability_rows if rank <= 20]
        qualification_rows = qualifications_by_membership[membership.id]
        qualification_types_truncated = sorted(
            {row.qualification_type for row, lane_rank in qualification_rows if lane_rank > 20}
        )
        qualifications = [row for row, lane_rank in qualification_rows if lane_rank <= 20]
        qualification_review_rows = qualification_reviews_by_membership[membership.id]
        qualification_reviews_truncated = any(rank > 20 for _row, rank in qualification_review_rows)
        qualification_reviews = [row for row, rank in qualification_review_rows if rank <= 20]
        authorization_rows = authorizations_by_membership[membership.id]
        authorizations_truncated = any(rank > 20 for _row, rank in authorization_rows)
        authorizations = [row for row, rank in authorization_rows if rank <= 20]
        readiness_rows = readiness_by_membership[membership.id]
        readiness_truncated = any(rank > 20 for _row, rank in readiness_rows)
        readiness = [row for row, rank in readiness_rows if rank <= 20]
        staff_rows.append(
            {
                "membership_id": membership.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "capabilities": [
                    {
                        "id": row.id,
                        "version_number": row.version_number,
                        "status": row.status,
                        "willing_to_drive": row.willing_to_drive,
                        "licence_jurisdiction": row.licence_jurisdiction,
                        "licence_class": row.licence_class,
                        "vehicle_access": row.vehicle_access,
                        "preferred_service_radius_km": row.preferred_service_radius_km,
                        "effective_at": row.effective_at,
                    }
                    for row in capabilities
                ],
                "qualifications": [
                    {
                        "id": row.id,
                        "qualification_type": row.qualification_type,
                        "version_number": row.version_number,
                        "status": row.status,
                        "jurisdiction": row.jurisdiction,
                        "qualification_class": row.qualification_class,
                        "identifier_last4": row.identifier_last4,
                        "issue_date": row.issue_date,
                        "expiry_date": row.expiry_date,
                        "evidence_present": row.id in qualification_evidence_ids,
                        "content_path": (
                            f"/api/v1/staff/transport-registry/{membership.id}/"
                            f"qualification-evidence/{row.id}/content"
                            if row.id in qualification_evidence_ids
                            else None
                        ),
                        "effective_at": row.effective_at,
                    }
                    for row in qualifications
                ],
                "qualification_reviews": [
                    {
                        "id": row.id,
                        "source_qualification_version_id": (row.source_qualification_version_id),
                        "result_qualification_version_id": (row.result_qualification_version_id),
                        "decision": row.decision,
                        "reason_code": row.reason_code,
                        "reviewed_at": row.reviewed_at,
                    }
                    for row in qualification_reviews
                ],
                "authorizations": [
                    {
                        "id": row.id,
                        "decision_sequence": row.decision_sequence,
                        "capability_version_id": row.capability_version_id,
                        "qualification_version_ids": row.qualification_version_ids,
                        "decision": row.decision,
                        "reason_code": row.reason_code,
                        "authorization_valid_from": row.authorization_valid_from,
                        "authorization_valid_until": row.authorization_valid_until,
                        "reviewed_at": row.reviewed_at,
                        "operational_driver_ready": False,
                        "dispatch_authorized": False,
                    }
                    for row in authorizations
                ],
                "readiness": [
                    {
                        "id": row.id,
                        "decision_sequence": row.decision_sequence,
                        "decision": row.decision,
                        "reason_codes": row.reason_codes,
                        "vehicle_id": row.vehicle_id,
                        "evaluated_at": row.evaluated_at,
                        "operational_driver_ready": False,
                        "dispatch_authorized": False,
                    }
                    for row in readiness
                ],
                "capabilities_truncated": capabilities_truncated,
                "qualification_types_truncated": qualification_types_truncated,
                "qualification_reviews_truncated": qualification_reviews_truncated,
                "authorizations_truncated": authorizations_truncated,
                "readiness_truncated": readiness_truncated,
            }
        )

    vehicle_rows = list(
        session.scalars(
            select(TransportVehicle)
            .where(TransportVehicle.organization_id == organization_id)
            .order_by(TransportVehicle.created_at.desc(), TransportVehicle.id)
            .limit(101)
        )
    )
    vehicles_truncated = len(vehicle_rows) > 100
    selected_vehicles = vehicle_rows[:100]
    vehicle_ids = [vehicle.id for vehicle in selected_vehicles]
    versions_by_vehicle: dict[UUID, list[tuple[TransportVehicleVersion, int]]] = defaultdict(list)
    evidence_by_vehicle: dict[UUID, list[tuple[TransportVehicleEvidenceVersion, int]]] = (
        defaultdict(list)
    )
    evidence_reviews_by_vehicle: dict[
        UUID, list[tuple[TransportVehicleEvidenceReviewDecision, int]]
    ] = defaultdict(list)

    if vehicle_ids:
        version_rank = (
            select(
                TransportVehicleVersion.id.label("version_id"),
                func.row_number()
                .over(
                    partition_by=TransportVehicleVersion.vehicle_id,
                    order_by=TransportVehicleVersion.version_number.desc(),
                )
                .label("history_rank"),
            )
            .where(
                TransportVehicleVersion.organization_id == organization_id,
                TransportVehicleVersion.vehicle_id.in_(vehicle_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(TransportVehicleVersion, version_rank.c.history_rank)
            .join(
                version_rank,
                version_rank.c.version_id == TransportVehicleVersion.id,
            )
            .where(
                TransportVehicleVersion.organization_id == organization_id,
                version_rank.c.history_rank <= 21,
            )
            .order_by(
                TransportVehicleVersion.vehicle_id,
                TransportVehicleVersion.version_number.desc(),
            )
        ):
            versions_by_vehicle[row.vehicle_id].append((row, history_rank))

        evidence_rank = (
            select(
                TransportVehicleEvidenceVersion.id.label("evidence_id"),
                func.row_number()
                .over(
                    partition_by=(
                        TransportVehicleEvidenceVersion.vehicle_id,
                        TransportVehicleEvidenceVersion.evidence_type,
                    ),
                    order_by=TransportVehicleEvidenceVersion.version_number.desc(),
                )
                .label("lane_rank"),
            )
            .where(
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                TransportVehicleEvidenceVersion.vehicle_id.in_(vehicle_ids),
            )
            .subquery()
        )
        for row, lane_rank in session.execute(
            select(TransportVehicleEvidenceVersion, evidence_rank.c.lane_rank)
            .join(
                evidence_rank,
                evidence_rank.c.evidence_id == TransportVehicleEvidenceVersion.id,
            )
            .where(
                TransportVehicleEvidenceVersion.organization_id == organization_id,
                evidence_rank.c.lane_rank <= 21,
            )
            .order_by(
                TransportVehicleEvidenceVersion.vehicle_id,
                TransportVehicleEvidenceVersion.evidence_type,
                TransportVehicleEvidenceVersion.version_number.desc(),
            )
        ):
            evidence_by_vehicle[row.vehicle_id].append((row, lane_rank))

        evidence_review_rank = (
            select(
                TransportVehicleEvidenceReviewDecision.id.label("review_id"),
                func.row_number()
                .over(
                    partition_by=TransportVehicleEvidenceReviewDecision.vehicle_id,
                    order_by=(
                        TransportVehicleEvidenceReviewDecision.reviewed_at.desc(),
                        TransportVehicleEvidenceReviewDecision.id.desc(),
                    ),
                )
                .label("history_rank"),
            )
            .where(
                TransportVehicleEvidenceReviewDecision.organization_id == organization_id,
                TransportVehicleEvidenceReviewDecision.vehicle_id.in_(vehicle_ids),
            )
            .subquery()
        )
        for row, history_rank in session.execute(
            select(
                TransportVehicleEvidenceReviewDecision,
                evidence_review_rank.c.history_rank,
            )
            .join(
                evidence_review_rank,
                evidence_review_rank.c.review_id == TransportVehicleEvidenceReviewDecision.id,
            )
            .where(
                TransportVehicleEvidenceReviewDecision.organization_id == organization_id,
                evidence_review_rank.c.history_rank <= 21,
            )
            .order_by(
                TransportVehicleEvidenceReviewDecision.vehicle_id,
                TransportVehicleEvidenceReviewDecision.reviewed_at.desc(),
                TransportVehicleEvidenceReviewDecision.id.desc(),
            )
        ):
            evidence_reviews_by_vehicle[row.vehicle_id].append((row, history_rank))

    vehicle_records = []
    for vehicle in selected_vehicles:
        version_rows = versions_by_vehicle[vehicle.id]
        versions_truncated = any(rank > 20 for _row, rank in version_rows)
        versions = [row for row, rank in version_rows if rank <= 20]
        evidence_rows = evidence_by_vehicle[vehicle.id]
        evidence_types_truncated = sorted(
            {row.evidence_type for row, lane_rank in evidence_rows if lane_rank > 20}
        )
        evidence = [row for row, lane_rank in evidence_rows if lane_rank <= 20]
        review_rows = evidence_reviews_by_vehicle[vehicle.id]
        evidence_reviews_truncated = any(rank > 20 for _row, rank in review_rows)
        reviews = [row for row, rank in review_rows if rank <= 20]
        vehicle_records.append(
            {
                "id": vehicle.id,
                "owner_kind": vehicle.owner_kind,
                "staff_owner_membership_id": vehicle.staff_owner_membership_id,
                "retired_at": vehicle.retired_at,
                "versions": [
                    {
                        "id": row.id,
                        "version_number": row.version_number,
                        "make": row.make,
                        "model": row.model,
                        "model_year": row.model_year,
                        "color": row.color,
                        "plate_token": row.plate_token,
                        "plate_jurisdiction": row.plate_jurisdiction,
                        "passenger_capacity": row.passenger_capacity,
                        "child_passenger_capacity": row.child_passenger_capacity,
                        "wheelchair_accessible": row.wheelchair_accessible,
                        "effective_at": row.effective_at,
                    }
                    for row in versions
                ],
                "evidence": [
                    {
                        "id": row.id,
                        "vehicle_version_id": row.vehicle_version_id,
                        "evidence_type": row.evidence_type,
                        "version_number": row.version_number,
                        "status": row.status,
                        "issue_date": row.issue_date,
                        "expiry_date": row.expiry_date,
                        "original_filename": row.original_filename,
                        "media_type": row.media_type,
                        "byte_size": row.byte_size,
                        "content_path": (
                            f"/api/v1/staff/transport-registry/vehicles/{vehicle.id}/"
                            f"evidence/{row.id}/content"
                        ),
                        "recorded_at": row.recorded_at,
                    }
                    for row in evidence
                ],
                "evidence_reviews": [
                    {
                        "id": row.id,
                        "source_evidence_version_id": row.source_evidence_version_id,
                        "result_evidence_version_id": row.result_evidence_version_id,
                        "decision": row.decision,
                        "reason_code": row.reason_code,
                        "reviewed_at": row.reviewed_at,
                    }
                    for row in reviews
                ],
                "versions_truncated": versions_truncated,
                "evidence_types_truncated": evidence_types_truncated,
                "evidence_reviews_truncated": evidence_reviews_truncated,
            }
        )
    return {
        "schema_version": "0032",
        "generated_at": datetime.now(UTC),
        "staff": staff_rows,
        "vehicles": vehicle_records,
        "staff_truncated": staff_truncated,
        "vehicles_truncated": vehicles_truncated,
        "operational_driver_ready": False,
        "dispatch_authorized": False,
    }


@manager_router.post(
    "/{membership_id}/qualification-reviews",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def review_qualification(
    membership_id: UUID,
    payload: QualificationReviewCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, membership_id=str(membership_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="qualification_review",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post(
    "/{membership_id}/authorizations",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def authorize_driver(
    membership_id: UUID,
    payload: DriverAuthorizationCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, membership_id=str(membership_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="driver_authorization",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post("/vehicles", response_model=TransportCommandReceiptResponse, status_code=201)
def create_organization_vehicle(
    payload: OrganizationVehicleCreateCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(
        payload, owner_kind="organization", staff_owner_membership_id=None
    )
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_create",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post(
    "/vehicles/{vehicle_id}/versions",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def version_managed_vehicle(
    vehicle_id: UUID,
    payload: VehicleVersionCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, vehicle_id=str(vehicle_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_version",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post(
    "/vehicles/{vehicle_id}/retire", response_model=TransportCommandReceiptResponse
)
def retire_managed_vehicle(
    vehicle_id: UUID,
    payload: VehicleRetireCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, vehicle_id=str(vehicle_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_retire",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post(
    "/vehicles/{vehicle_id}/evidence",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
async def upload_managed_vehicle_evidence(
    vehicle_id: UUID,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
    operation_id: Annotated[UUID, Form()],
    evidence_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    issue_date: Annotated[date | None, Form()] = None,
    expiry_date: Annotated[date | None, Form()] = None,
):
    fields = VehicleEvidenceFields(
        operation_id=operation_id,
        evidence_type=evidence_type,
        issue_date=issue_date,
        expiry_date=expiry_date,
    )
    selected_operation, values = _public_payload(fields, vehicle_id=str(vehicle_id))
    return await _execute_evidence(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_evidence",
        operation_id=selected_operation,
        public_payload=values,
        file=file,
        document_id=vehicle_id,
    )


@manager_router.post(
    "/vehicles/{vehicle_id}/evidence-reviews",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def review_vehicle_evidence(
    vehicle_id: UUID,
    payload: VehicleEvidenceReviewCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, vehicle_id=str(vehicle_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="vehicle_evidence_review",
        operation_id=operation_id,
        public_payload=values,
    )


@manager_router.post(
    "/{membership_id}/readiness-evaluations",
    response_model=TransportCommandReceiptResponse,
    status_code=201,
)
def evaluate_readiness(
    membership_id: UUID,
    payload: ReadinessEvaluationCommand,
    request: Request,
    context: TransportManageContext,
    session: SessionDependency,
):
    operation_id, values = _public_payload(payload, membership_id=str(membership_id))
    return _execute(
        request=request,
        session=session,
        context=context,
        command_kind="readiness_evaluation",
        operation_id=operation_id,
        public_payload=values,
    )
