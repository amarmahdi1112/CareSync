"""Owner/administrator routes for the 0029A family-authority kernel."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.basic.common import ensure_writable
from app.api.basic.dependencies import FamilyAuthorityAdminContext
from app.api.dependencies import SessionDependency
from app.basic.family_authority import (
    create_authority_person,
    get_child_authority_summary,
    get_family_authority_workspace,
    invalidate_authority_evidence,
    record_authority_evidence,
    reject_authority_evidence,
    replace_authority_person,
    retire_authority_person,
    review_authority_evidence,
    supersede_authority_evidence,
)
from app.basic.family_authority_activation import (
    create_release_rule,
    grant_release_authorization,
    list_consent_policies,
    publish_consent_policy,
    record_child_consent,
    revoke_release_authorization,
    revoke_release_rule,
    withdraw_child_consent,
)
from app.basic.family_authority_schemas import (
    AuthorityEvidenceCommandResponse,
    AuthorityEvidenceInvalidateRequest,
    AuthorityEvidenceObjectCommandResponse,
    AuthorityEvidenceObjectScanRequest,
    AuthorityEvidenceRecordRequest,
    AuthorityEvidenceRejectRequest,
    AuthorityEvidenceReviewRequest,
    AuthorityEvidenceSupersedeRequest,
    AuthorityPersonCommandResponse,
    AuthorityPersonCreateRequest,
    AuthorityPersonReplaceRequest,
    AuthorityPersonRetireRequest,
    ChildAuthoritySummaryFocusKind,
    ChildAuthoritySummaryResponse,
    ChildConsentCommandResponse,
    ChildConsentRecordRequest,
    ChildConsentWithdrawRequest,
    ConsentPolicyCommandResponse,
    ConsentPolicyPublishRequest,
    ConsentPolicyVersionResponse,
    EvidenceKind,
    FamilyAuthorityWorkspaceResponse,
    ReleaseAuthorizationCommandResponse,
    ReleaseAuthorizationGrantRequest,
    ReleaseAuthorizationRevokeRequest,
    ReleaseRuleCommandResponse,
    ReleaseRuleCreateRequest,
    ReleaseRuleRevokeRequest,
)
from app.basic.family_evidence_objects import (
    clean_evidence_object_download,
    record_evidence_object_upload,
    scan_evidence_object,
)
from app.basic.family_evidence_vault import (
    DOCUMENT_EVIDENCE_KINDS,
    SUPPORTED_MEDIA_SUFFIXES,
    delete_private_object,
    store_private_upload,
    stream_private_object,
)

router = APIRouter(tags=["basic family authority"])


def _require_family_authority_kernel(request: Request) -> None:
    if not getattr(request.app.state, "family_authority_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_authority_unavailable"},
        )


def _require_family_evidence_vault(request: Request) -> None:
    _require_family_authority_kernel(request)
    if not getattr(request.app.state, "family_evidence_vault_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_evidence_vault_unavailable"},
        )


def _require_family_authority_activation(request: Request) -> None:
    _require_family_authority_kernel(request)
    if not getattr(request.app.state, "family_authority_activation_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_authority_activation_unavailable"},
        )


def _child_authority_summary_focus(
    request: Request,
) -> tuple[ChildAuthoritySummaryFocusKind | None, UUID | None]:
    values = list(request.query_params.multi_items())
    if not values:
        return None, None
    if len(values) != 2 or {key for key, _ in values} != {"focus", "record_id"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_child_authority_summary_query"},
        )
    parsed = dict(values)
    focus = parsed["focus"]
    if focus not in {"release_authorization", "release_rule", "consent"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_child_authority_summary_query"},
        )
    try:
        record_id = UUID(parsed["record_id"])
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_child_authority_summary_query"},
        ) from None
    return focus, record_id


@router.post(
    "/families/{family_id}/authority/evidence-objects",
    response_model=AuthorityEvidenceObjectCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_family_authority_evidence_object(
    family_id: UUID,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
    client_operation_id: Annotated[UUID, Form()],
    evidence_kind: Annotated[EvidenceKind, Form()],
    file: Annotated[UploadFile, File()],
) -> AuthorityEvidenceObjectCommandResponse:
    _require_family_evidence_vault(request)
    ensure_writable(request)
    submitted_fields = set((await request.form()).keys())
    unexpected_fields = submitted_fields - {
        "client_operation_id",
        "evidence_kind",
        "file",
    }
    if unexpected_fields:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unexpected_evidence_upload_fields",
                "fields": sorted(unexpected_fields),
            },
        )
    if evidence_kind not in DOCUMENT_EVIDENCE_KINDS:
        raise HTTPException(
            status_code=422,
            detail={"code": "evidence_object_requires_document_kind"},
        )
    object_id = uuid4()
    stored = await store_private_upload(
        file,
        settings=request.app.state.settings,
        organization_id=context.organization.id,
        family_id=family_id,
        object_id=object_id,
    )
    try:
        result = record_evidence_object_upload(
            session,
            context,
            family_id,
            object_id,
            evidence_kind,
            client_operation_id,
            stored,
        )
    except HTTPException:
        # Typed service failures occur before commit. Commit/response ambiguity
        # is intentionally not typed and retains private bytes for reconciliation.
        delete_private_object(request.app.state.settings, stored.storage_reference)
        raise
    except BaseException:
        raise
    if result.replayed:
        # Exact replay points at the original object; discard the duplicate
        # upload bytes generated while re-measuring the retried multipart body.
        delete_private_object(request.app.state.settings, stored.storage_reference)
    return result


@router.post(
    "/families/{family_id}/authority/evidence-objects/{object_id}/scan",
    response_model=AuthorityEvidenceObjectCommandResponse,
)
def scan_family_authority_evidence_object(
    family_id: UUID,
    object_id: UUID,
    payload: AuthorityEvidenceObjectScanRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceObjectCommandResponse:
    _require_family_evidence_vault(request)
    ensure_writable(request)
    return scan_evidence_object(
        session,
        context,
        family_id,
        object_id,
        payload,
        request.app.state.settings,
    )


@router.get(
    "/families/{family_id}/authority/evidence-objects/{object_id}/download",
)
def download_family_authority_evidence_object(
    family_id: UUID,
    object_id: UUID,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
):
    _require_family_evidence_vault(request)
    value, handle = clean_evidence_object_download(
        session,
        context,
        family_id,
        object_id,
        request.app.state.settings,
    )
    suffix = SUPPORTED_MEDIA_SUFFIXES[value.media_type]
    filename = f"evidence-{value.id}{suffix}"
    return StreamingResponse(
        stream_private_object(handle),
        media_type=value.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(value.byte_size),
        },
    )


@router.get(
    "/families/{family_id}/authority",
    response_model=FamilyAuthorityWorkspaceResponse,
)
def family_authority_workspace(
    family_id: UUID,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> FamilyAuthorityWorkspaceResponse:
    # The workspace selects A2-only consent provenance columns. Keep the A1
    # mutation routes available, but fail before any ORM projection until the
    # complete activation boundary is present.
    _require_family_authority_activation(request)
    return get_family_authority_workspace(session, context, family_id)


@router.get(
    "/children/{child_id}/authority-summary",
    response_model=ChildAuthoritySummaryResponse,
)
def child_authority_summary(
    child_id: UUID,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ChildAuthoritySummaryResponse:
    # Keep retained 0028 deployments safe: this check must happen before any
    # staged authority-summary ORM projection touches 0029-only columns.
    _require_family_authority_activation(request)
    focus_kind, focus_id = _child_authority_summary_focus(request)
    return get_child_authority_summary(
        session,
        context,
        child_id,
        focus_kind=focus_kind,
        focus_id=focus_id,
    )


@router.post(
    "/families/{family_id}/authority/people",
    response_model=AuthorityPersonCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_family_authority_person(
    family_id: UUID,
    payload: AuthorityPersonCreateRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityPersonCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return create_authority_person(session, context, family_id, payload)


@router.post(
    "/families/{family_id}/authority/people/{person_id}/versions",
    response_model=AuthorityPersonCommandResponse,
)
def replace_family_authority_person(
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonReplaceRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityPersonCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return replace_authority_person(session, context, family_id, person_id, payload)


@router.post(
    "/families/{family_id}/authority/people/{person_id}/retire",
    response_model=AuthorityPersonCommandResponse,
)
def retire_family_authority_person(
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonRetireRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityPersonCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return retire_authority_person(session, context, family_id, person_id, payload)


@router.post(
    "/families/{family_id}/authority/evidence",
    response_model=AuthorityEvidenceCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_family_authority_evidence(
    family_id: UUID,
    payload: AuthorityEvidenceRecordRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return record_authority_evidence(
        session, context, family_id, payload, request.app.state.settings
    )


@router.post(
    "/families/{family_id}/authority/evidence/{evidence_id}/review",
    response_model=AuthorityEvidenceCommandResponse,
)
def review_family_authority_evidence(
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceReviewRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return review_authority_evidence(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        request.app.state.settings,
    )


@router.post(
    "/families/{family_id}/authority/evidence/{evidence_id}/reject",
    response_model=AuthorityEvidenceCommandResponse,
)
def reject_family_authority_evidence(
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceRejectRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return reject_authority_evidence(session, context, family_id, evidence_id, payload)


@router.post(
    "/families/{family_id}/authority/evidence/{evidence_id}/invalidate",
    response_model=AuthorityEvidenceCommandResponse,
)
def invalidate_family_authority_evidence(
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceInvalidateRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return invalidate_authority_evidence(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        include_signer_authority=bool(
            getattr(request.app.state, "family_authority_activation_enabled", False)
        ),
    )


@router.post(
    "/families/{family_id}/authority/evidence/{evidence_id}/supersede",
    response_model=AuthorityEvidenceCommandResponse,
)
def supersede_family_authority_evidence(
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceSupersedeRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> AuthorityEvidenceCommandResponse:
    _require_family_authority_kernel(request)
    ensure_writable(request)
    return supersede_authority_evidence(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        include_signer_authority=bool(
            getattr(request.app.state, "family_authority_activation_enabled", False)
        ),
    )


@router.post(
    "/children/{child_id}/release-authorizations",
    response_model=ReleaseAuthorizationCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_child_release_authorization(
    child_id: UUID,
    payload: ReleaseAuthorizationGrantRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ReleaseAuthorizationCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return grant_release_authorization(session, context, child_id, payload)


@router.post(
    "/children/{child_id}/release-authorizations/{authorization_id}/revoke",
    response_model=ReleaseAuthorizationCommandResponse,
)
def revoke_child_release_authorization(
    child_id: UUID,
    authorization_id: UUID,
    payload: ReleaseAuthorizationRevokeRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ReleaseAuthorizationCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return revoke_release_authorization(
        session,
        context,
        child_id,
        authorization_id,
        payload,
    )


@router.post(
    "/children/{child_id}/release-rules",
    response_model=ReleaseRuleCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_child_release_rule(
    child_id: UUID,
    payload: ReleaseRuleCreateRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ReleaseRuleCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return create_release_rule(session, context, child_id, payload)


@router.post(
    "/children/{child_id}/release-rules/{rule_id}/revoke",
    response_model=ReleaseRuleCommandResponse,
)
def revoke_child_release_rule(
    child_id: UUID,
    rule_id: UUID,
    payload: ReleaseRuleRevokeRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ReleaseRuleCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return revoke_release_rule(session, context, child_id, rule_id, payload)


@router.get(
    "/consent-policies",
    response_model=list[ConsentPolicyVersionResponse],
)
def organization_consent_policies(
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> list[ConsentPolicyVersionResponse]:
    _require_family_authority_activation(request)
    return list_consent_policies(session, context)


@router.post(
    "/consent-policies",
    response_model=ConsentPolicyCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def publish_organization_consent_policy(
    payload: ConsentPolicyPublishRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ConsentPolicyCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return publish_consent_policy(session, context, payload)


@router.post(
    "/children/{child_id}/consents",
    response_model=ChildConsentCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_child_consent_decision(
    child_id: UUID,
    payload: ChildConsentRecordRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ChildConsentCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return record_child_consent(session, context, child_id, payload)


@router.post(
    "/children/{child_id}/consents/{decision_id}/withdraw",
    response_model=ChildConsentCommandResponse,
)
def withdraw_child_consent_decision(
    child_id: UUID,
    decision_id: UUID,
    payload: ChildConsentWithdrawRequest,
    request: Request,
    context: FamilyAuthorityAdminContext,
    session: SessionDependency,
) -> ChildConsentCommandResponse:
    _require_family_authority_activation(request)
    ensure_writable(request)
    return withdraw_child_consent(session, context, child_id, decision_id, payload)
