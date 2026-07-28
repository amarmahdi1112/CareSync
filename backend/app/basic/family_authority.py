"""Admin-only 0029A family-authority services.

The write order in this module is intentionally different from older 0028
commands.  Authority database guards require the immutable command receipt to
exist before the related authority row is flushed.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.basic.common import restore_context
from app.api.basic.dependencies import BasicContext
from app.basic.childcare_commands import begin_command, record_command, require_version
from app.basic.family_authority_schemas import (
    AuthorityEvidenceAssessmentResponse,
    AuthorityEvidenceCommandResponse,
    AuthorityEvidenceInvalidateRequest,
    AuthorityEvidenceRecordRequest,
    AuthorityEvidenceRejectRequest,
    AuthorityEvidenceResponse,
    AuthorityEvidenceReviewRequest,
    AuthorityEvidenceSupersedeRequest,
    AuthorityPersonCommandResponse,
    AuthorityPersonCreateRequest,
    AuthorityPersonReplaceRequest,
    AuthorityPersonResponse,
    AuthorityPersonRetireRequest,
    AuthorityPersonVersionResponse,
    ChildAuthorityPersonSummary,
    ChildAuthoritySummaryFocusKind,
    ChildAuthoritySummaryResponse,
    ChildConsentDecisionResponse,
    ChildConsentDecisionSummary,
    ChildFamilyAuthorityResponse,
    ChildReleaseAuthorizationSummary,
    ChildReleaseRuleSummary,
    FamilyAuthorityCommandReceiptResponse,
    FamilyAuthorityWorkspaceResponse,
    ReleaseAuthorizationResponse,
    ReleaseRuleResponse,
)
from app.basic.models import (
    Child,
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildConsentDecision,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    ConsentPolicyVersion,
    EmergencyContact,
    Family,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityPerson,
    FamilyAuthorityPersonVersion,
    Guardian,
)
from app.basic.security import audit
from app.core.config import Settings

PERSON_CREATE_COMMAND = "family.authority.person.create"
PERSON_REPLACE_COMMAND = "family.authority.person.replace"
PERSON_RETIRE_COMMAND = "family.authority.person.retire"
PERSON_TARGET_TYPE = "authority_person"
EVIDENCE_RECORD_COMMAND = "family.authority.evidence.record"
EVIDENCE_REVIEW_COMMAND = "family.authority.evidence.review"
EVIDENCE_REJECT_COMMAND = "family.authority.evidence.reject"
EVIDENCE_INVALIDATE_COMMAND = "family.authority.evidence.invalidate"
EVIDENCE_SUPERSEDE_COMMAND = "family.authority.evidence.supersede"
EVIDENCE_TARGET_TYPE = "authority_evidence"


def _utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite's naive round-tripped timestamps for strict responses."""

    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _family(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    *,
    for_update: bool = False,
    for_share: bool = False,
) -> Family:
    if for_update and for_share:
        raise ValueError("A family row cannot request two lock modes")
    statement = select(Family).where(
        Family.organization_id == organization_id,
        Family.id == family_id,
    )
    if for_update:
        statement = statement.with_for_update()
    elif for_share:
        # Every family-authority writer takes FOR UPDATE on this same row.
        # A shared lock therefore gives multi-statement projections one
        # coherent aggregate view without serializing concurrent readers.
        statement = statement.with_for_update(read=True)
    family = session.scalar(statement)
    if family is None:
        raise HTTPException(404, detail="Family not found")
    return family


def _require_current_family_authority_admin(
    session: Session,
    context: BasicContext,
) -> None:
    """Recheck the live leader rows without creating an import cycle.

    ``family_evidence_objects`` imports response helpers from this module, so
    this import must remain local. Callers acquire the canonical family lock
    before this check whenever a family aggregate is available.
    """

    from app.basic.family_evidence_objects import (
        require_current_family_authority_admin,
    )

    require_current_family_authority_admin(session, context)


def _person_source(person: FamilyAuthorityPerson) -> dict[str, object]:
    if person.source_guardian_id is not None:
        return {"kind": "guardian", "guardian_id": person.source_guardian_id}
    if person.source_emergency_contact_id is not None:
        return {
            "kind": "emergency_contact",
            "emergency_contact_id": person.source_emergency_contact_id,
        }
    return {"kind": "manual"}


def _person_version_response(
    value: FamilyAuthorityPersonVersion,
) -> AuthorityPersonVersionResponse:
    return AuthorityPersonVersionResponse(
        id=value.id,
        person_id=value.person_id,
        version_number=value.version_number,
        facts={
            "first_name": value.first_name,
            "middle_name": value.middle_name,
            "last_name": value.last_name,
            "preferred_name": value.preferred_name,
            "relationship_kind": value.relationship_kind,
            "relationship_detail": value.relationship_detail,
            "email": value.email,
            "primary_phone": value.primary_phone,
        },
        closed_at=_utc(value.closed_at),
        created_at=_utc(value.created_at),
    )


def _person_response(
    person: FamilyAuthorityPerson,
    current_version: FamilyAuthorityPersonVersion | None,
) -> AuthorityPersonResponse:
    return AuthorityPersonResponse(
        id=person.id,
        organization_id=person.organization_id,
        family_id=person.family_id,
        version=person.version,
        status=person.status,
        source=_person_source(person),
        current_version=(
            _person_version_response(current_version) if current_version is not None else None
        ),
        retired_at=_utc(person.retired_at),
        created_at=_utc(person.created_at),
        updated_at=_utc(person.updated_at),
    )


def _evidence_assessment_response(
    value: FamilyAuthorityEvidenceAssessment,
) -> AuthorityEvidenceAssessmentResponse:
    return AuthorityEvidenceAssessmentResponse(
        id=value.id,
        evidence_id=value.evidence_id,
        version_number=value.version_number,
        decision=value.decision,
        assessed_epistemic_status=value.assessed_epistemic_status,
        reason_code=value.reason_code,
        confidential_note=value.confidential_note,
        superseded_by_evidence_id=value.superseded_by_evidence_id,
        actor_user_id=value.actor_user_id,
        created_at=_utc(value.created_at),
    )


def _evidence_response(
    value: FamilyAuthorityEvidence,
    current_assessment: FamilyAuthorityEvidenceAssessment | None,
    evaluated_at: datetime,
) -> AuthorityEvidenceResponse:
    storage = None
    if value.storage_reference is not None:
        storage = {
            "storage_reference": value.storage_reference,
            "media_type": value.media_type,
            "byte_size": value.byte_size,
            "content_sha256": value.content_sha256,
        }
    lifecycle_status = (
        current_assessment.decision if current_assessment is not None else "unreviewed"
    )
    expires_at = _utc(value.expires_at)
    effective_status = lifecycle_status
    if (
        lifecycle_status == "reviewed"
        and expires_at is not None
        and expires_at <= evaluated_at
    ):
        effective_status = "expired"
    return AuthorityEvidenceResponse(
        id=value.id,
        organization_id=value.organization_id,
        family_id=value.family_id,
        evidence_kind=value.evidence_kind,
        source_label=value.source_label,
        recorded_by_user_id=value.recorded_by_user_id,
        storage=storage,
        evidence_object_id=value.evidence_object_id,
        issued_at=_utc(value.issued_at),
        captured_at=_utc(value.captured_at),
        expires_at=expires_at,
        created_at=_utc(value.created_at),
        version=(
            current_assessment.version_number if current_assessment is not None else 1
        ),
        lifecycle_status=lifecycle_status,
        effective_status=effective_status,
        valid_now=effective_status == "reviewed",
        evaluated_at=evaluated_at,
        current_assessment=(
            _evidence_assessment_response(current_assessment)
            if current_assessment is not None
            else None
        ),
    )


def _authorization_response(
    value: ChildReleaseAuthorization,
    authority_revision: int,
    *,
    valid_evidence_pairs: set[tuple[UUID, UUID]],
    evaluated_at: datetime,
) -> ReleaseAuthorizationResponse:
    effective_status = _authority_record_effective_status(
        effective_from=value.effective_from,
        effective_until=value.effective_until,
        terminal_status="revoked" if value.revoked_at is not None else None,
        required_evidence_pairs={
            (value.basis_evidence_id, value.basis_evidence_assessment_id)
        },
        valid_evidence_pairs=valid_evidence_pairs,
        evaluated_at=evaluated_at,
    )
    return ReleaseAuthorizationResponse(
        id=value.id,
        organization_id=value.organization_id,
        family_id=value.family_id,
        child_id=value.child_id,
        recipient_person_id=value.recipient_person_id,
        verification_policy_code=value.verification_policy_code,
        grantor={
            "person_id": value.grantor_person_id,
            "person_version_id": value.grantor_person_version_id,
            "authority_basis": value.grantor_authority_basis,
            "basis_evidence_id": value.basis_evidence_id,
            "basis_evidence_assessment_id": value.basis_evidence_assessment_id,
        },
        effective_from=_utc(value.effective_from),
        effective_until=_utc(value.effective_until),
        version=value.version,
        revoked_at=_utc(value.revoked_at),
        revocation_reason_code=value.revocation_reason_code,
        effective_status=effective_status,
        effective_now=effective_status == "effective",
        evaluated_at=evaluated_at,
        authority_revision=authority_revision,
        created_at=_utc(value.created_at),
        updated_at=_utc(value.updated_at),
    )


def _rule_response(
    value: ChildReleaseRule,
    authority_revision: int,
    *,
    valid_evidence_pairs: set[tuple[UUID, UUID]],
    evaluated_at: datetime,
) -> ReleaseRuleResponse:
    scope: dict[str, object]
    if value.scope_kind == "specific_person":
        scope = {"kind": "specific_person", "person_id": value.scope_person_id}
    else:
        scope = {"kind": "all_recipients"}
    directing_person = None
    if value.directing_person_id is not None:
        directing_person = {
            "person_id": value.directing_person_id,
            "person_version_id": value.directing_person_version_id,
        }
    effective_status = _authority_record_effective_status(
        effective_from=value.effective_from,
        effective_until=value.effective_until,
        terminal_status="revoked" if value.revoked_at is not None else None,
        required_evidence_pairs={
            (value.basis_evidence_id, value.basis_evidence_assessment_id)
        },
        valid_evidence_pairs=valid_evidence_pairs,
        evaluated_at=evaluated_at,
    )
    return ReleaseRuleResponse(
        id=value.id,
        organization_id=value.organization_id,
        family_id=value.family_id,
        child_id=value.child_id,
        rule_kind=value.rule_kind,
        scope=scope,
        directing_person=directing_person,
        authority_basis_code=value.authority_basis_code,
        basis_evidence_id=value.basis_evidence_id,
        basis_evidence_assessment_id=value.basis_evidence_assessment_id,
        safe_explanation_code=value.safe_explanation_code,
        confidential_reason=value.confidential_reason,
        effective_from=_utc(value.effective_from),
        effective_until=_utc(value.effective_until),
        version=value.version,
        revoked_at=_utc(value.revoked_at),
        revocation_reason_code=value.revocation_reason_code,
        effective_status=effective_status,
        effective_now=effective_status == "effective",
        evaluated_at=evaluated_at,
        authority_revision=authority_revision,
        created_at=_utc(value.created_at),
        updated_at=_utc(value.updated_at),
    )


def _consent_response(
    value: ChildConsentDecision,
    authority_revision: int,
    *,
    valid_evidence_pairs: set[tuple[UUID, UUID]],
    evaluated_at: datetime,
) -> ChildConsentDecisionResponse:
    scope: dict[str, object]
    if value.scope_kind == "facility":
        scope = {"kind": "facility", "facility_id": value.scope_facility_id}
    elif value.scope_kind == "named_activity":
        scope = {"kind": "named_activity", "reference": value.scope_reference}
    else:
        scope = {"kind": "policy"}
    effective_status = _authority_record_effective_status(
        effective_from=value.effective_from,
        effective_until=value.effective_until,
        terminal_status="withdrawn" if value.withdrawn_at is not None else None,
        required_evidence_pairs={
            (value.evidence_id, value.evidence_assessment_id),
            (
                value.signer_authority_evidence_id,
                value.signer_authority_evidence_assessment_id,
            ),
        },
        valid_evidence_pairs=valid_evidence_pairs,
        evaluated_at=evaluated_at,
    )
    return ChildConsentDecisionResponse(
        id=value.id,
        organization_id=value.organization_id,
        family_id=value.family_id,
        child_id=value.child_id,
        purpose_code=value.purpose_code,
        policy_version_id=value.policy_version_id,
        signer={
            "person_id": value.signer_person_id,
            "person_version_id": value.signer_person_version_id,
            "authority_basis": value.signer_authority_basis,
            "authority_evidence_id": value.signer_authority_evidence_id,
            "authority_evidence_assessment_id": (
                value.signer_authority_evidence_assessment_id
            ),
        },
        evidence_id=value.evidence_id,
        evidence_assessment_id=value.evidence_assessment_id,
        decision=value.decision,
        scope=scope,
        effective_from=_utc(value.effective_from),
        effective_until=_utc(value.effective_until),
        version=value.version,
        withdrawn_at=_utc(value.withdrawn_at),
        withdrawal_reason_code=value.withdrawal_reason_code,
        effective_status=effective_status,
        effective_now=effective_status == "effective",
        evaluated_at=evaluated_at,
        authority_revision=authority_revision,
        created_at=_utc(value.created_at),
        updated_at=_utc(value.updated_at),
    )


def _receipt_response(
    receipt: ChildcareCommandReceipt,
) -> FamilyAuthorityCommandReceiptResponse:
    action_route = (receipt.outcome or {}).get("action_route")
    if not isinstance(action_route, str):
        raise HTTPException(
            409,
            detail={
                "code": "operation_receipt_incomplete",
                "client_operation_id": str(receipt.client_operation_id),
            },
        )
    return FamilyAuthorityCommandReceiptResponse(
        organization_id=receipt.organization_id,
        client_operation_id=receipt.client_operation_id,
        command_type=receipt.command_type,
        target_type=receipt.target_type,
        target_id=receipt.target_id,
        committed_version=receipt.committed_version,
        committed_at=_utc(receipt.committed_at),
        facility_id=receipt.facility_id,
        action_route=action_route,
    )


def _raise_receipt_incomplete(receipt: ChildcareCommandReceipt) -> None:
    raise HTTPException(
        409,
        detail={
            "code": "operation_receipt_incomplete",
            "client_operation_id": str(receipt.client_operation_id),
        },
    )


def _is_serialization_failure(error: DBAPIError) -> bool:
    original = error.orig
    return getattr(original, "sqlstate", None) == "40001" or getattr(
        original, "pgcode", None
    ) == "40001"


def _constraint_name(error: DBAPIError) -> str:
    diagnostic = getattr(error.orig, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return str(name or "")


def _commit_person_create(session: Session, context: BasicContext) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        _raise_person_write_error(session, error)
    except DBAPIError as error:
        _raise_person_write_error(session, error)
    restore_context(session, context)
    # PostgreSQL guard triggers author the canonical timestamps.  The session
    # keeps client defaults after commit, so force the first response through
    # the same persisted projection used by every exact replay.
    session.expire_all()


def _flush_person_create(session: Session) -> None:
    try:
        session.flush()
    except (IntegrityError, DBAPIError) as error:
        _raise_person_write_error(session, error)


def _raise_person_write_error(session: Session, error: DBAPIError) -> None:
    session.rollback()
    name = _constraint_name(error)
    message = str(error.orig).lower()
    if name == "ck_authority_evidence_review_unexpired":
        raise HTTPException(
            409,
            detail={"code": "authority_evidence_expired"},
        ) from None
    if name == "ck_authority_evidence_maker_checker":
        raise HTTPException(
            409,
            detail={"code": "maker_checker_required"},
        ) from None
    if name == "ck_authority_evidence_superseding_current":
        raise HTTPException(
            409,
            detail={"code": "replacement_evidence_not_current"},
        ) from None
    if name in {
        "ck_authority_evidence_privileged_actor",
        "ck_authority_evidence_assessment_privileged_actor",
    }:
        raise HTTPException(
            403,
            detail={"code": "family_authority_access_revoked"},
        ) from None
    if name in {
        "ck_authority_evidence_child_revisions",
        "ck_authority_person_child_revisions",
        "ck_child_authority_command_revision",
    }:
        raise HTTPException(
            409,
            detail={"code": "authority_revision_changed"},
        ) from None
    if name in {
        "uq_authority_evidence_assessments_version",
        "uq_authority_evidence_assessments_created_operation",
        "ck_authority_evidence_assessment_sequence",
    } or (
        "family_authority_evidence_assessments.organization_id" in message
        and (
            "family_authority_evidence_assessments.version_number" in message
            or "family_authority_evidence_assessments.created_operation_id" in message
        )
    ):
        raise HTTPException(
            409,
            detail={"code": "authority_evidence_state_changed"},
        ) from None
    if name == "uq_authority_evidence_object" or (
        "family_authority_evidence.organization_id" in message
        and "family_authority_evidence.evidence_object_id" in message
    ):
        raise HTTPException(
            409,
            detail={"code": "evidence_object_already_bound"},
        ) from None
    if isinstance(error, IntegrityError) and (
        name
        in {
            "uq_authority_people_source_guardian",
            "uq_authority_people_source_contact",
        }
        or (
            "family_authority_people.organization_id" in message
            and (
                "source_guardian_id" in message
                or "source_emergency_contact_id" in message
            )
        )
    ):
        raise HTTPException(
            409,
            detail={"code": "authority_source_already_linked"},
        ) from None
    if _is_serialization_failure(error):
        raise HTTPException(
            409,
            detail={"code": "authority_revision_changed"},
        ) from None
    raise error


def _transaction_cutoff(session: Session) -> datetime:
    value = session.scalar(select(func.current_timestamp()))
    if not isinstance(value, datetime):
        raise HTTPException(409, detail={"code": "authority_clock_unavailable"})
    normalized = _utc(value)
    if normalized is None:
        raise HTTPException(409, detail={"code": "authority_clock_unavailable"})
    return normalized


def _authority_record_effective_status(
    *,
    effective_from: datetime,
    effective_until: datetime,
    terminal_status: str | None,
    required_evidence_pairs: set[tuple[UUID, UUID]],
    valid_evidence_pairs: set[tuple[UUID, UUID]],
    evaluated_at: datetime,
) -> str:
    """Derive the administrative truth without implying release permission."""

    if terminal_status is not None:
        return terminal_status
    # A pinned assessment that is no longer the current reviewed evidence can
    # never become effective again; surface that durable blocker ahead of a
    # merely scheduled/expired window label.
    if not required_evidence_pairs <= valid_evidence_pairs:
        return "supporting_evidence_unavailable"
    starts_at = _utc(effective_from)
    ends_at = _utc(effective_until)
    if starts_at is None or ends_at is None:
        raise HTTPException(409, detail={"code": "authority_window_invalid"})
    if starts_at > evaluated_at:
        return "scheduled"
    if ends_at <= evaluated_at:
        return "expired"
    return "effective"


def _valid_evidence_pairs_from_loaded(
    evidence_values: list[FamilyAuthorityEvidence],
    current_assessments: dict[UUID, FamilyAuthorityEvidenceAssessment],
    evaluated_at: datetime,
) -> set[tuple[UUID, UUID]]:
    valid: set[tuple[UUID, UUID]] = set()
    for evidence in evidence_values:
        assessment = current_assessments.get(evidence.id)
        expires_at = _utc(evidence.expires_at)
        if (
            assessment is not None
            and assessment.decision == "reviewed"
            and (expires_at is None or expires_at > evaluated_at)
        ):
            valid.add((evidence.id, assessment.id))
    return valid


def _load_valid_evidence_pairs(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    evidence_ids: set[UUID],
    evaluated_at: datetime,
) -> set[tuple[UUID, UUID]]:
    if not evidence_ids:
        return set()
    evidence_values = list(
        session.scalars(
            select(FamilyAuthorityEvidence).where(
                FamilyAuthorityEvidence.organization_id == organization_id,
                FamilyAuthorityEvidence.family_id == family_id,
                FamilyAuthorityEvidence.id.in_(evidence_ids),
            )
        )
    )
    resolved_evidence_ids = {evidence.id for evidence in evidence_values}
    assessments_by_evidence: defaultdict[
        UUID, list[FamilyAuthorityEvidenceAssessment]
    ] = defaultdict(list)
    if resolved_evidence_ids:
        for assessment in session.scalars(
            select(FamilyAuthorityEvidenceAssessment)
            .where(
                FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
                FamilyAuthorityEvidenceAssessment.family_id == family_id,
                FamilyAuthorityEvidenceAssessment.evidence_id.in_(resolved_evidence_ids),
            )
            .order_by(
                FamilyAuthorityEvidenceAssessment.evidence_id,
                FamilyAuthorityEvidenceAssessment.version_number,
            )
        ):
            assessments_by_evidence[assessment.evidence_id].append(assessment)
    current_assessments: dict[UUID, FamilyAuthorityEvidenceAssessment] = {}
    for evidence in evidence_values:
        history = assessments_by_evidence[evidence.id]
        versions = [assessment.version_number for assessment in history]
        if versions not in ([], [2], [2, 3]):
            raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
        if history and history[0].decision not in {"reviewed", "rejected"}:
            raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
        if len(history) == 2 and (
            history[0].decision != "reviewed"
            or history[1].decision not in {"invalidated", "superseded"}
        ):
            raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
        if history:
            current_assessments[evidence.id] = history[-1]
    return _valid_evidence_pairs_from_loaded(
        evidence_values,
        current_assessments,
        evaluated_at,
    )


def _evidence_assessment_history(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    evidence_id: UUID,
) -> list[FamilyAuthorityEvidenceAssessment]:
    statement = (
        select(FamilyAuthorityEvidenceAssessment)
        .where(
            FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
            FamilyAuthorityEvidenceAssessment.family_id == family_id,
            FamilyAuthorityEvidenceAssessment.evidence_id == evidence_id,
        )
        .order_by(FamilyAuthorityEvidenceAssessment.version_number)
    )
    values = list(session.scalars(statement))
    versions = [value.version_number for value in values]
    if versions not in ([], [2], [2, 3]):
        raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
    if values and values[0].decision not in {"reviewed", "rejected"}:
        raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
    if len(values) == 2 and (
        values[0].decision != "reviewed"
        or values[1].decision not in {"invalidated", "superseded"}
    ):
        raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
    return values


def _evidence_state(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    evidence_id: UUID,
) -> tuple[FamilyAuthorityEvidence, FamilyAuthorityEvidenceAssessment | None]:
    statement = select(FamilyAuthorityEvidence).where(
        FamilyAuthorityEvidence.organization_id == organization_id,
        FamilyAuthorityEvidence.family_id == family_id,
        FamilyAuthorityEvidence.id == evidence_id,
    )
    evidence = session.scalar(statement)
    if evidence is None:
        raise HTTPException(404, detail="Authority evidence not found")
    history = _evidence_assessment_history(
        session,
        organization_id,
        family_id,
        evidence_id,
    )
    return evidence, history[-1] if history else None


def _load_evidence_for_receipt(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    receipt: ChildcareCommandReceipt,
) -> tuple[FamilyAuthorityEvidence, FamilyAuthorityEvidenceAssessment | None]:
    # Exact retry promises the current canonical projection. Serialize that
    # projection with every family-authority writer before its first mutable
    # read so READ COMMITTED cannot mix two lifecycle versions.
    organization_id = context.organization.id
    _family(session, organization_id, family_id, for_share=True)
    _require_current_family_authority_admin(session, context)
    try:
        evidence, assessment = _evidence_state(
            session,
            organization_id,
            family_id,
            receipt.target_id,
        )
    except HTTPException as error:
        if error.status_code in {404, 409}:
            _raise_receipt_incomplete(receipt)
        raise
    current_version = assessment.version_number if assessment is not None else 1
    if current_version < receipt.committed_version:
        _raise_receipt_incomplete(receipt)
    if receipt.committed_version == 1:
        if (
            receipt.command_type != EVIDENCE_RECORD_COMMAND
            or evidence.created_operation_id != receipt.client_operation_id
        ):
            _raise_receipt_incomplete(receipt)
        return evidence, assessment
    expected_decisions = {
        EVIDENCE_REVIEW_COMMAND: (2, "reviewed"),
        EVIDENCE_REJECT_COMMAND: (2, "rejected"),
        EVIDENCE_INVALIDATE_COMMAND: (3, "invalidated"),
        EVIDENCE_SUPERSEDE_COMMAND: (3, "superseded"),
    }
    expected = expected_decisions.get(receipt.command_type)
    history = _evidence_assessment_history(
        session,
        organization_id,
        family_id,
        evidence.id,
    )
    historical_assessment = next(
        (
            value
            for value in history
            if value.version_number == receipt.committed_version
        ),
        None,
    )
    if (
        expected is None
        or expected[0] != receipt.committed_version
        or historical_assessment is None
        or historical_assessment.decision != expected[1]
        or historical_assessment.created_operation_id != receipt.client_operation_id
    ):
        _raise_receipt_incomplete(receipt)
    return evidence, assessment


def _require_evidence_version(
    evidence: FamilyAuthorityEvidence,
    assessment: FamilyAuthorityEvidenceAssessment | None,
    expected_version: int,
) -> None:
    current_version = assessment.version_number if assessment is not None else 1
    if current_version != expected_version:
        raise HTTPException(
            409,
            detail={
                "code": "stale_childcare_resource",
                "resource_type": "authority_evidence",
                "resource_id": str(evidence.id),
                "expected_version": expected_version,
                "current_version": current_version,
            },
        )


def _affected_evidence_child_ids(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    evidence_id: UUID,
    evidence_assessment_id: UUID,
    cutoff: datetime,
    *,
    include_signer_authority: bool = False,
) -> list[UUID]:
    child_ids = set(
        session.scalars(
            select(ChildReleaseAuthorization.child_id).where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.family_id == family_id,
                ChildReleaseAuthorization.basis_evidence_id == evidence_id,
                ChildReleaseAuthorization.basis_evidence_assessment_id
                == evidence_assessment_id,
                ChildReleaseAuthorization.revoked_at.is_(None),
                ChildReleaseAuthorization.effective_until > cutoff,
            )
        )
    )
    child_ids.update(
        session.scalars(
            select(ChildReleaseRule.child_id).where(
                ChildReleaseRule.organization_id == organization_id,
                ChildReleaseRule.family_id == family_id,
                ChildReleaseRule.basis_evidence_id == evidence_id,
                ChildReleaseRule.basis_evidence_assessment_id == evidence_assessment_id,
                ChildReleaseRule.revoked_at.is_(None),
                ChildReleaseRule.effective_until > cutoff,
            )
        )
    )
    child_ids.update(
        session.scalars(
            select(ChildConsentDecision.child_id).where(
                ChildConsentDecision.organization_id == organization_id,
                ChildConsentDecision.family_id == family_id,
                ChildConsentDecision.evidence_id == evidence_id,
                ChildConsentDecision.evidence_assessment_id == evidence_assessment_id,
                ChildConsentDecision.withdrawn_at.is_(None),
                ChildConsentDecision.effective_until > cutoff,
            )
        )
    )
    if include_signer_authority:
        child_ids.update(
            session.scalars(
                select(ChildConsentDecision.child_id).where(
                    ChildConsentDecision.organization_id == organization_id,
                    ChildConsentDecision.family_id == family_id,
                    ChildConsentDecision.signer_authority_evidence_id == evidence_id,
                    ChildConsentDecision.signer_authority_evidence_assessment_id
                    == evidence_assessment_id,
                    ChildConsentDecision.withdrawn_at.is_(None),
                    ChildConsentDecision.effective_until > cutoff,
                )
            )
        )
    return sorted(child_ids, key=str)


def _lock_affected_evidence_children(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    evidence_id: UUID,
    evidence_assessment_id: UUID,
    cutoff: datetime,
    *,
    include_signer_authority: bool = False,
) -> list[ChildAuthorityHead]:
    child_ids = _affected_evidence_child_ids(
        session,
        organization_id,
        family_id,
        evidence_id,
        evidence_assessment_id,
        cutoff,
        include_signer_authority=include_signer_authority,
    )
    if not child_ids:
        return []
    locked_child_ids = list(
        session.scalars(
            select(Child.id)
            .where(
                Child.organization_id == organization_id,
                Child.family_id == family_id,
                Child.id.in_(child_ids),
            )
            .order_by(Child.id)
            .with_for_update()
        )
    )
    if set(locked_child_ids) != set(child_ids):
        raise HTTPException(409, detail={"code": "authority_reference_child_missing"})
    heads = list(
        session.scalars(
            select(ChildAuthorityHead)
            .where(
                ChildAuthorityHead.organization_id == organization_id,
                ChildAuthorityHead.family_id == family_id,
                ChildAuthorityHead.child_id.in_(child_ids),
            )
            .order_by(ChildAuthorityHead.child_id)
            .with_for_update()
        )
    )
    if {head.child_id for head in heads} != set(child_ids):
        raise HTTPException(409, detail={"code": "authority_head_missing"})
    return heads


def _record_evidence_observability(
    session: Session,
    context: BasicContext,
    evidence_id: UUID,
    operation_id: UUID,
    transition: str,
    affected_child_count: int,
) -> None:
    details = {
        "operation_id": str(operation_id),
        "transition": transition,
        "affected_child_count": affected_child_count,
    }
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action=f"family.authority.evidence.{transition}",
        entity_type="authority_evidence",
        entity_id=evidence_id,
        details=details,
    )


def _evidence_receipt(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    client_operation_id: UUID,
    command_type: str,
    request_hash: str,
    committed_version: int,
) -> ChildcareCommandReceipt:
    receipt = record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        target_type=EVIDENCE_TARGET_TYPE,
        target_id=evidence_id,
        request_hash=request_hash,
        committed_version=committed_version,
        outcome={
            "action_route": f"/families/{family_id}?authority_evidence_id={evidence_id}"
        },
    )
    _flush_person_create(session)
    return receipt


def _evidence_command_response(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    replayed: bool,
) -> AuthorityEvidenceCommandResponse:
    evidence, assessment = _load_evidence_for_receipt(
        session,
        context,
        family_id,
        receipt,
    )
    return AuthorityEvidenceCommandResponse(
        resource=_evidence_response(
            evidence,
            assessment,
            _transaction_cutoff(session),
        ),
        receipt=_receipt_response(receipt),
        replayed=replayed,
    )


def _source_ids(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    payload: AuthorityPersonCreateRequest,
) -> tuple[UUID | None, UUID | None]:
    source = payload.source
    if source.kind == "manual":
        return None, None
    if source.kind == "guardian":
        value = session.scalar(
            select(Guardian).where(
                Guardian.organization_id == organization_id,
                Guardian.family_id == family_id,
                Guardian.id == source.guardian_id,
            )
        )
        if value is None:
            raise HTTPException(404, detail="Authority source not found")
        linked = session.scalar(
            select(FamilyAuthorityPerson.id).where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == family_id,
                FamilyAuthorityPerson.source_guardian_id == value.id,
            )
        )
        if linked is not None:
            raise HTTPException(409, detail={"code": "authority_source_already_linked"})
        return value.id, None
    value = session.scalar(
        select(EmergencyContact).where(
            EmergencyContact.organization_id == organization_id,
            EmergencyContact.family_id == family_id,
            EmergencyContact.id == source.emergency_contact_id,
        )
    )
    if value is None:
        raise HTTPException(404, detail="Authority source not found")
    linked = session.scalar(
        select(FamilyAuthorityPerson.id).where(
            FamilyAuthorityPerson.organization_id == organization_id,
            FamilyAuthorityPerson.family_id == family_id,
            FamilyAuthorityPerson.source_emergency_contact_id == value.id,
        )
    )
    if linked is not None:
        raise HTTPException(409, detail={"code": "authority_source_already_linked"})
    return None, value.id


def _load_person_for_receipt(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    receipt: ChildcareCommandReceipt,
) -> tuple[FamilyAuthorityPerson, FamilyAuthorityPersonVersion | None]:
    # The person aggregate and its current fact version are read separately.
    # Hold the family shared lock used by the complete command boundary so a
    # concurrent replace/retire cannot commit between those statements.
    organization_id = context.organization.id
    _family(session, organization_id, family_id, for_share=True)
    _require_current_family_authority_admin(session, context)
    person = session.scalar(
        select(FamilyAuthorityPerson).where(
            FamilyAuthorityPerson.organization_id == organization_id,
            FamilyAuthorityPerson.family_id == family_id,
            FamilyAuthorityPerson.id == receipt.target_id,
        )
    )
    # A receipt records the committed version of this historical command.  A
    # later replace/retire may legitimately advance the aggregate; exact retry
    # returns that immutable receipt plus the current canonical projection.
    if person is None:
        _raise_receipt_incomplete(receipt)
    current_version = None
    if person.current_person_version_id is not None:
        current_version = session.scalar(
            select(FamilyAuthorityPersonVersion).where(
                FamilyAuthorityPersonVersion.organization_id == organization_id,
                FamilyAuthorityPersonVersion.family_id == family_id,
                FamilyAuthorityPersonVersion.person_id == person.id,
                FamilyAuthorityPersonVersion.id == person.current_person_version_id,
            )
        )
        if current_version is None:
            _raise_receipt_incomplete(receipt)
    return person, current_version


def _affected_person_child_ids(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person_id: UUID,
) -> list[UUID]:
    """Return the exact live-or-future dependency set used by the DB invariant."""

    # A person transition uses one transaction-stable cutoff. PostgreSQL's
    # matching head guard uses the same cutoff, so a dependency cannot expire
    # between discovery and the later head update and turn a safe command into
    # an untyped database failure.
    transaction_time = func.current_timestamp()
    child_ids = set(
        session.scalars(
            select(ChildReleaseAuthorization.child_id).where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.family_id == family_id,
                ChildReleaseAuthorization.revoked_at.is_(None),
                ChildReleaseAuthorization.effective_until > transaction_time,
                or_(
                    ChildReleaseAuthorization.recipient_person_id == person_id,
                    ChildReleaseAuthorization.grantor_person_id == person_id,
                ),
            )
        )
    )
    child_ids.update(
        session.scalars(
            select(ChildReleaseRule.child_id).where(
                ChildReleaseRule.organization_id == organization_id,
                ChildReleaseRule.family_id == family_id,
                ChildReleaseRule.revoked_at.is_(None),
                ChildReleaseRule.effective_until > transaction_time,
                or_(
                    ChildReleaseRule.scope_person_id == person_id,
                    ChildReleaseRule.directing_person_id == person_id,
                ),
            )
        )
    )
    child_ids.update(
        session.scalars(
            select(ChildConsentDecision.child_id).where(
                ChildConsentDecision.organization_id == organization_id,
                ChildConsentDecision.family_id == family_id,
                ChildConsentDecision.withdrawn_at.is_(None),
                ChildConsentDecision.effective_until > transaction_time,
                ChildConsentDecision.signer_person_id == person_id,
            )
        )
    )
    return sorted(child_ids, key=str)


def _lock_affected_person_children(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person_id: UUID,
) -> list[ChildAuthorityHead]:
    """Lock affected children and their existing heads in stable ID order."""

    child_ids = _affected_person_child_ids(
        session,
        organization_id,
        family_id,
        person_id,
    )
    if not child_ids:
        return []

    locked_child_ids = list(
        session.scalars(
            select(Child.id)
            .where(
                Child.organization_id == organization_id,
                Child.family_id == family_id,
                Child.id.in_(child_ids),
            )
            .order_by(Child.id)
            .with_for_update()
        )
    )
    if set(locked_child_ids) != set(child_ids):
        raise HTTPException(409, detail={"code": "authority_reference_child_missing"})

    heads = list(
        session.scalars(
            select(ChildAuthorityHead)
            .where(
                ChildAuthorityHead.organization_id == organization_id,
                ChildAuthorityHead.family_id == family_id,
                ChildAuthorityHead.child_id.in_(child_ids),
            )
            .order_by(ChildAuthorityHead.child_id)
            .with_for_update()
        )
    )
    if {head.child_id for head in heads} != set(child_ids):
        # A referenced child without a head contradicts the authority kernel.
        # Never synthesize a head while replacing shared person facts.
        raise HTTPException(409, detail={"code": "authority_head_missing"})
    return heads


def _lock_active_authority_person(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person_id: UUID,
    expected_version: int,
) -> tuple[FamilyAuthorityPerson, FamilyAuthorityPersonVersion]:
    person = session.scalar(
        select(FamilyAuthorityPerson)
        .where(
            FamilyAuthorityPerson.organization_id == organization_id,
            FamilyAuthorityPerson.family_id == family_id,
            FamilyAuthorityPerson.id == person_id,
        )
        .with_for_update()
    )
    if person is None:
        raise HTTPException(404, detail="Authority person not found")
    require_version(person, expected_version, "authority_person")
    if person.status != "active" or person.current_person_version_id is None:
        raise HTTPException(409, detail={"code": "authority_person_inactive"})

    current_version = session.scalar(
        select(FamilyAuthorityPersonVersion)
        .where(
            FamilyAuthorityPersonVersion.organization_id == organization_id,
            FamilyAuthorityPersonVersion.family_id == family_id,
            FamilyAuthorityPersonVersion.person_id == person.id,
            FamilyAuthorityPersonVersion.id == person.current_person_version_id,
        )
        .with_for_update()
    )
    if (
        current_version is None
        or current_version.version_number != person.version
        or current_version.closed_at is not None
        or current_version.closed_operation_id is not None
    ):
        raise HTTPException(409, detail={"code": "authority_person_version_missing"})
    return person, current_version


def _begin_person_transition(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonReplaceRequest | AuthorityPersonRetireRequest,
    *,
    command_type: str,
) -> tuple[
    str,
    ChildcareCommandReceipt | None,
    FamilyAuthorityPerson | None,
    FamilyAuthorityPersonVersion | None,
    list[ChildAuthorityHead],
]:
    """Reserve one operation, then acquire the canonical lifecycle lock order."""

    organization_id = context.organization.id
    target_scope = f"family:{family_id}:authority_person:{person_id}"
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type=PERSON_TARGET_TYPE,
        target_scope=target_scope,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != person_id:
            _raise_receipt_incomplete(receipt)
        person, current_version = _load_person_for_receipt(
            session,
            context,
            family_id,
            receipt,
        )
        return request_hash, receipt, person, current_version, []

    _family(session, organization_id, family_id, for_update=True)
    _require_current_family_authority_admin(session, context)
    heads = _lock_affected_person_children(
        session,
        organization_id,
        family_id,
        person_id,
    )
    person, current_version = _lock_active_authority_person(
        session,
        organization_id,
        family_id,
        person_id,
        payload.expected_version,
    )
    return request_hash, None, person, current_version, heads


def _person_transition_receipt(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonReplaceRequest | AuthorityPersonRetireRequest,
    *,
    command_type: str,
    request_hash: str,
    committed_version: int,
) -> ChildcareCommandReceipt:
    receipt = record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type=PERSON_TARGET_TYPE,
        target_id=person_id,
        request_hash=request_hash,
        committed_version=committed_version,
        outcome={
            "action_route": f"/families/{family_id}?authority_person_id={person_id}"
        },
    )
    # PostgreSQL requires a same-transaction receipt before any authority row
    # transition can be flushed.
    _flush_person_create(session)
    return receipt


def _bump_person_child_heads(
    session: Session,
    heads: list[ChildAuthorityHead],
    operation_id: UUID,
) -> None:
    for head in heads:
        head.revision += 1
        head.last_operation_id = operation_id
    _flush_person_create(session)


def create_authority_person(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    payload: AuthorityPersonCreateRequest,
) -> AuthorityPersonCommandResponse:
    """Create one stable person and its first fact version with exact retry."""

    organization_id = context.organization.id
    target_scope = f"family:{family_id}:authority_person:create"
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=PERSON_CREATE_COMMAND,
        target_type=PERSON_TARGET_TYPE,
        target_scope=target_scope,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        person, current_version = _load_person_for_receipt(
            session,
            context,
            family_id,
            receipt,
        )
        return AuthorityPersonCommandResponse(
            resource=_person_response(person, current_version),
            receipt=_receipt_response(receipt),
            replayed=True,
        )

    _family(session, organization_id, family_id, for_update=True)
    _require_current_family_authority_admin(session, context)
    source_guardian_id, source_emergency_contact_id = _source_ids(
        session,
        organization_id,
        family_id,
        payload,
    )
    person_id = uuid4()
    person_version_id = uuid4()
    action_route = f"/families/{family_id}?authority_person_id={person_id}"

    command_receipt = record_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=PERSON_CREATE_COMMAND,
        target_type=PERSON_TARGET_TYPE,
        target_id=person_id,
        request_hash=request_hash,
        committed_version=1,
        outcome={"action_route": action_route},
    )
    # 0029A PostgreSQL guards look up this receipt during authority inserts.
    _flush_person_create(session)

    person = FamilyAuthorityPerson(
        id=person_id,
        organization_id=organization_id,
        family_id=family_id,
        version=1,
        status="active",
        current_person_version_id=person_version_id,
        source_guardian_id=source_guardian_id,
        source_emergency_contact_id=source_emergency_contact_id,
        created_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
    )
    facts = payload.facts
    person_version = FamilyAuthorityPersonVersion(
        id=person_version_id,
        organization_id=organization_id,
        family_id=family_id,
        person_id=person_id,
        version_number=1,
        first_name=facts.first_name,
        middle_name=facts.middle_name,
        last_name=facts.last_name,
        preferred_name=facts.preferred_name,
        relationship_kind=facts.relationship_kind,
        relationship_detail=facts.relationship_detail,
        email=facts.email,
        primary_phone=facts.primary_phone,
        created_operation_id=payload.client_operation_id,
    )
    session.add_all([person, person_version])
    _flush_person_create(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="family.authority.person.created",
        entity_type="authority_person",
        entity_id=person_id,
        details={
            "operation_id": str(payload.client_operation_id),
            "transition": "created",
            "affected_child_count": 0,
        },
    )
    _commit_person_create(session, context)
    person, current_version = _load_person_for_receipt(
        session,
        context,
        family_id,
        command_receipt,
    )
    return AuthorityPersonCommandResponse(
        resource=_person_response(person, current_version),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def replace_authority_person(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonReplaceRequest,
) -> AuthorityPersonCommandResponse:
    """Replace current person facts and invalidate every dependent child projection."""

    request_hash, receipt, person, current_version, heads = _begin_person_transition(
        session,
        context,
        family_id,
        person_id,
        payload,
        command_type=PERSON_REPLACE_COMMAND,
    )
    if receipt is not None:
        if person is None:
            _raise_receipt_incomplete(receipt)
        return AuthorityPersonCommandResponse(
            resource=_person_response(person, current_version),
            receipt=_receipt_response(receipt),
            replayed=True,
        )
    if person is None or current_version is None:
        raise HTTPException(409, detail={"code": "authority_person_version_missing"})

    committed_version = person.version + 1
    command_receipt = _person_transition_receipt(
        session,
        context,
        family_id,
        person_id,
        payload,
        command_type=PERSON_REPLACE_COMMAND,
        request_hash=request_hash,
        committed_version=committed_version,
    )

    now = datetime.now(UTC)
    new_version_id = uuid4()
    current_version.closed_at = now
    current_version.closed_operation_id = payload.client_operation_id
    facts = payload.facts
    session.add(
        FamilyAuthorityPersonVersion(
            id=new_version_id,
            organization_id=context.organization.id,
            family_id=family_id,
            person_id=person_id,
            version_number=committed_version,
            first_name=facts.first_name,
            middle_name=facts.middle_name,
            last_name=facts.last_name,
            preferred_name=facts.preferred_name,
            relationship_kind=facts.relationship_kind,
            relationship_detail=facts.relationship_detail,
            email=facts.email,
            primary_phone=facts.primary_phone,
            created_operation_id=payload.client_operation_id,
        )
    )
    person.version = committed_version
    person.current_person_version_id = new_version_id
    person.last_operation_id = payload.client_operation_id
    _flush_person_create(session)

    _bump_person_child_heads(session, heads, payload.client_operation_id)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="family.authority.person.replaced",
        entity_type="authority_person",
        entity_id=person_id,
        details={
            "operation_id": str(payload.client_operation_id),
            "transition": "replaced",
            "committed_version": committed_version,
            "affected_child_count": len(heads),
        },
    )
    _commit_person_create(session, context)
    person, current_version = _load_person_for_receipt(
        session,
        context,
        family_id,
        command_receipt,
    )
    return AuthorityPersonCommandResponse(
        resource=_person_response(person, current_version),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def retire_authority_person(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    person_id: UUID,
    payload: AuthorityPersonRetireRequest,
) -> AuthorityPersonCommandResponse:
    """Retire one person without erasing facts or dependent authority history."""

    request_hash, receipt, person, current_version, heads = _begin_person_transition(
        session,
        context,
        family_id,
        person_id,
        payload,
        command_type=PERSON_RETIRE_COMMAND,
    )
    if receipt is not None:
        if person is None:
            _raise_receipt_incomplete(receipt)
        return AuthorityPersonCommandResponse(
            resource=_person_response(person, current_version),
            receipt=_receipt_response(receipt),
            replayed=True,
        )
    if person is None or current_version is None:
        raise HTTPException(409, detail={"code": "authority_person_version_missing"})

    committed_version = person.version + 1
    command_receipt = _person_transition_receipt(
        session,
        context,
        family_id,
        person_id,
        payload,
        command_type=PERSON_RETIRE_COMMAND,
        request_hash=request_hash,
        committed_version=committed_version,
    )

    now = datetime.now(UTC)
    current_version.closed_at = now
    current_version.closed_operation_id = payload.client_operation_id
    person.version = committed_version
    person.status = "retired"
    person.current_person_version_id = None
    person.last_operation_id = payload.client_operation_id
    person.retired_at = now
    person.retired_operation_id = payload.client_operation_id
    _flush_person_create(session)

    _bump_person_child_heads(session, heads, payload.client_operation_id)
    audit(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        action="family.authority.person.retired",
        entity_type="authority_person",
        entity_id=person_id,
        details={
            "operation_id": str(payload.client_operation_id),
            "transition": "retired",
            "committed_version": committed_version,
            "affected_child_count": len(heads),
        },
    )
    _commit_person_create(session, context)
    person, current_version = _load_person_for_receipt(
        session,
        context,
        family_id,
        command_receipt,
    )
    return AuthorityPersonCommandResponse(
        resource=_person_response(person, current_version),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def record_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    payload: AuthorityEvidenceRecordRequest,
    settings: Settings,
) -> AuthorityEvidenceCommandResponse:
    """Record immutable intake metadata without accepting client storage claims."""

    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=EVIDENCE_RECORD_COMMAND,
        target_type=EVIDENCE_TARGET_TYPE,
        target_scope=f"family:{family_id}:authority_evidence:create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _evidence_command_response(
            session,
            context,
            family_id,
            receipt,
            replayed=True,
        )

    _family(session, organization_id, family_id, for_update=True)
    _require_current_family_authority_admin(session, context)
    storage_object = None
    if payload.evidence_object_id is not None:
        from app.basic.family_evidence_objects import (
            clean_object_for_evidence,
        )

        storage_object = clean_object_for_evidence(
            session,
            organization_id,
            family_id,
            payload.evidence_object_id,
            payload.evidence_kind,
            settings,
            lock=True,
        )
    evidence_id = uuid4()
    command_receipt = _evidence_receipt(
        session,
        context,
        family_id,
        evidence_id,
        payload.client_operation_id,
        EVIDENCE_RECORD_COMMAND,
        request_hash,
        1,
    )
    session.add(
        FamilyAuthorityEvidence(
            id=evidence_id,
            organization_id=organization_id,
            family_id=family_id,
            evidence_kind=payload.evidence_kind,
            source_label=payload.source_label,
            evidence_object_id=(storage_object.id if storage_object is not None else None),
            storage_reference=(
                storage_object.storage_reference if storage_object is not None else None
            ),
            media_type=(storage_object.media_type if storage_object is not None else None),
            byte_size=(storage_object.byte_size if storage_object is not None else None),
            content_sha256=(
                storage_object.content_sha256 if storage_object is not None else None
            ),
            issued_at=payload.issued_at,
            captured_at=payload.captured_at,
            expires_at=payload.expires_at,
            recorded_by_user_id=context.user.id,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush_person_create(session)
    _record_evidence_observability(
        session,
        context,
        evidence_id,
        payload.client_operation_id,
        "recorded",
        0,
    )
    _commit_person_create(session, context)
    return _evidence_command_response(
        session,
        context,
        family_id,
        command_receipt,
        replayed=False,
    )


def _begin_evidence_transition(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceReviewRequest
    | AuthorityEvidenceRejectRequest
    | AuthorityEvidenceInvalidateRequest,
    command_type: str,
) -> tuple[
    str,
    ChildcareCommandReceipt | None,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment | None,
]:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type=EVIDENCE_TARGET_TYPE,
        target_scope=f"family:{family_id}:authority_evidence:{evidence_id}",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != evidence_id:
            _raise_receipt_incomplete(receipt)
        evidence, assessment = _load_evidence_for_receipt(
            session,
            context,
            family_id,
            receipt,
        )
        return request_hash, receipt, evidence, assessment

    _family(session, organization_id, family_id, for_update=True)
    _require_current_family_authority_admin(session, context)
    evidence, assessment = _evidence_state(
        session,
        organization_id,
        family_id,
        evidence_id,
    )
    _require_evidence_version(evidence, assessment, payload.expected_version)
    return request_hash, None, evidence, assessment


def _assess_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceReviewRequest | AuthorityEvidenceRejectRequest,
    *,
    command_type: str,
    decision: str,
    settings: Settings | None = None,
) -> AuthorityEvidenceCommandResponse:
    request_hash, receipt, evidence, assessment = _begin_evidence_transition(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        command_type,
    )
    if receipt is not None:
        return _evidence_command_response(
            session,
            context,
            family_id,
            receipt,
            replayed=True,
        )
    if assessment is not None:
        raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
    expires_at = _utc(evidence.expires_at)
    if (
        decision == "reviewed"
        and expires_at is not None
        and expires_at <= _transaction_cutoff(session)
    ):
        raise HTTPException(409, detail={"code": "authority_evidence_expired"})

    reviewed_payload = (
        payload if isinstance(payload, AuthorityEvidenceReviewRequest) else None
    )
    if decision == "reviewed" and reviewed_payload is not None:
        from app.basic.family_evidence_objects import (
            clean_object_for_evidence,
        )
        from app.basic.family_evidence_vault import DOCUMENT_EVIDENCE_KINDS

        if context.user.id == evidence.recorded_by_user_id:
            raise HTTPException(409, detail={"code": "maker_checker_required"})
        if evidence.evidence_kind in DOCUMENT_EVIDENCE_KINDS:
            if settings is None:
                raise HTTPException(
                    503, detail={"code": "family_evidence_vault_unavailable"}
                )
            if evidence.evidence_object_id is None:
                raise HTTPException(409, detail={"code": "evidence_object_required"})
            evidence_object = clean_object_for_evidence(
                session,
                context.organization.id,
                family_id,
                evidence.evidence_object_id,
                evidence.evidence_kind,
                settings,
                lock=True,
            )
            if reviewed_payload.assessed_epistemic_status != "document_observed":
                raise HTTPException(
                    409,
                    detail={"code": "document_evidence_requires_observed_review"},
                )
            if context.user.id == evidence_object.uploaded_by_user_id:
                raise HTTPException(409, detail={"code": "maker_checker_required"})
        elif reviewed_payload.assessed_epistemic_status != "reported":
            raise HTTPException(
                409,
                detail={"code": "reported_evidence_cannot_be_document_observed"},
            )

    command_receipt = _evidence_receipt(
        session,
        context,
        family_id,
        evidence.id,
        payload.client_operation_id,
        command_type,
        request_hash,
        2,
    )
    rejected_payload = (
        payload if isinstance(payload, AuthorityEvidenceRejectRequest) else None
    )
    session.add(
        FamilyAuthorityEvidenceAssessment(
            id=uuid4(),
            organization_id=context.organization.id,
            family_id=family_id,
            evidence_id=evidence.id,
            version_number=2,
            decision=decision,
            assessed_epistemic_status=(
                reviewed_payload.assessed_epistemic_status
                if reviewed_payload is not None
                else None
            ),
            reason_code=(
                rejected_payload.reason_code if rejected_payload is not None else None
            ),
            confidential_note=(
                rejected_payload.confidential_note
                if rejected_payload is not None
                else None
            ),
            superseded_by_evidence_id=None,
            actor_user_id=context.user.id,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush_person_create(session)
    _record_evidence_observability(
        session,
        context,
        evidence.id,
        payload.client_operation_id,
        decision,
        0,
    )
    _commit_person_create(session, context)
    return _evidence_command_response(
        session,
        context,
        family_id,
        command_receipt,
        replayed=False,
    )


def review_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceReviewRequest,
    settings: Settings,
) -> AuthorityEvidenceCommandResponse:
    return _assess_authority_evidence(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        command_type=EVIDENCE_REVIEW_COMMAND,
        decision="reviewed",
        settings=settings,
    )


def reject_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceRejectRequest,
) -> AuthorityEvidenceCommandResponse:
    return _assess_authority_evidence(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        command_type=EVIDENCE_REJECT_COMMAND,
        decision="rejected",
    )


def invalidate_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceInvalidateRequest,
    *,
    include_signer_authority: bool = False,
) -> AuthorityEvidenceCommandResponse:
    request_hash, receipt, evidence, assessment = _begin_evidence_transition(
        session,
        context,
        family_id,
        evidence_id,
        payload,
        EVIDENCE_INVALIDATE_COMMAND,
    )
    if receipt is not None:
        return _evidence_command_response(
            session,
            context,
            family_id,
            receipt,
            replayed=True,
        )
    if assessment is None or assessment.decision != "reviewed":
        raise HTTPException(409, detail={"code": "authority_evidence_not_reviewed"})

    cutoff = _transaction_cutoff(session)
    heads = _lock_affected_evidence_children(
        session,
        context.organization.id,
        family_id,
        evidence.id,
        assessment.id,
        cutoff,
        include_signer_authority=include_signer_authority,
    )
    command_receipt = _evidence_receipt(
        session,
        context,
        family_id,
        evidence.id,
        payload.client_operation_id,
        EVIDENCE_INVALIDATE_COMMAND,
        request_hash,
        3,
    )
    session.add(
        FamilyAuthorityEvidenceAssessment(
            id=uuid4(),
            organization_id=context.organization.id,
            family_id=family_id,
            evidence_id=evidence.id,
            version_number=3,
            decision="invalidated",
            assessed_epistemic_status=None,
            reason_code=payload.reason_code,
            confidential_note=payload.confidential_note,
            superseded_by_evidence_id=None,
            actor_user_id=context.user.id,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush_person_create(session)
    _bump_person_child_heads(session, heads, payload.client_operation_id)
    _record_evidence_observability(
        session,
        context,
        evidence.id,
        payload.client_operation_id,
        "invalidated",
        len(heads),
    )
    _commit_person_create(session, context)
    return _evidence_command_response(
        session,
        context,
        family_id,
        command_receipt,
        replayed=False,
    )


def supersede_authority_evidence(
    session: Session,
    context: BasicContext,
    family_id: UUID,
    evidence_id: UUID,
    payload: AuthorityEvidenceSupersedeRequest,
    *,
    include_signer_authority: bool = False,
) -> AuthorityEvidenceCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=EVIDENCE_SUPERSEDE_COMMAND,
        target_type=EVIDENCE_TARGET_TYPE,
        target_scope=f"family:{family_id}:authority_evidence:{evidence_id}",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != evidence_id:
            _raise_receipt_incomplete(receipt)
        return _evidence_command_response(
            session,
            context,
            family_id,
            receipt,
            replayed=True,
        )
    if payload.replacement_evidence_id == evidence_id:
        raise HTTPException(409, detail={"code": "replacement_evidence_same"})

    _family(session, organization_id, family_id, for_update=True)
    _require_current_family_authority_admin(session, context)
    requested_ids = {evidence_id, payload.replacement_evidence_id}
    evidence_assets = list(
        session.scalars(
            select(FamilyAuthorityEvidence)
            .where(
                FamilyAuthorityEvidence.organization_id == organization_id,
                FamilyAuthorityEvidence.family_id == family_id,
                FamilyAuthorityEvidence.id.in_(requested_ids),
            )
            .order_by(FamilyAuthorityEvidence.id)
        )
    )
    evidence_by_id = {value.id: value for value in evidence_assets}
    evidence = evidence_by_id.get(evidence_id)
    if evidence is None:
        raise HTTPException(404, detail="Authority evidence not found")
    replacement = evidence_by_id.get(payload.replacement_evidence_id)
    if replacement is None:
        raise HTTPException(404, detail="Replacement authority evidence not found")

    histories = {
        locked_id: _evidence_assessment_history(
            session,
            organization_id,
            family_id,
            locked_id,
        )
        for locked_id in sorted(requested_ids, key=str)
    }
    assessment = histories[evidence_id][-1] if histories[evidence_id] else None
    replacement_assessment = (
        histories[replacement.id][-1] if histories[replacement.id] else None
    )
    _require_evidence_version(evidence, assessment, payload.expected_version)
    if assessment is None or assessment.decision != "reviewed":
        raise HTTPException(409, detail={"code": "authority_evidence_not_reviewed"})

    cutoff = _transaction_cutoff(session)
    replacement_expires_at = _utc(replacement.expires_at)
    if (
        replacement_assessment is None
        or replacement_assessment.decision != "reviewed"
        or (
            replacement_expires_at is not None
            and replacement_expires_at <= cutoff
        )
    ):
        raise HTTPException(409, detail={"code": "replacement_evidence_not_current"})

    heads = _lock_affected_evidence_children(
        session,
        organization_id,
        family_id,
        evidence.id,
        assessment.id,
        cutoff,
        include_signer_authority=include_signer_authority,
    )
    command_receipt = _evidence_receipt(
        session,
        context,
        family_id,
        evidence.id,
        payload.client_operation_id,
        EVIDENCE_SUPERSEDE_COMMAND,
        request_hash,
        3,
    )
    session.add(
        FamilyAuthorityEvidenceAssessment(
            id=uuid4(),
            organization_id=organization_id,
            family_id=family_id,
            evidence_id=evidence.id,
            version_number=3,
            decision="superseded",
            assessed_epistemic_status=None,
            reason_code="superseded",
            confidential_note=None,
            superseded_by_evidence_id=replacement.id,
            actor_user_id=context.user.id,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush_person_create(session)
    _bump_person_child_heads(session, heads, payload.client_operation_id)
    _record_evidence_observability(
        session,
        context,
        evidence.id,
        payload.client_operation_id,
        "superseded",
        len(heads),
    )
    _commit_person_create(session, context)
    return _evidence_command_response(
        session,
        context,
        family_id,
        command_receipt,
        replayed=False,
    )


def get_family_authority_workspace(
    session: Session,
    context: BasicContext,
    family_id: UUID,
) -> FamilyAuthorityWorkspaceResponse:
    """Project the confidential family authority workspace without writing."""

    organization_id = context.organization.id
    # This workspace is assembled from several mutable tables. All authority
    # writers lock the family FOR UPDATE, so FOR SHARE keeps the projection at
    # one coherent command boundary while still allowing concurrent readers.
    _family(session, organization_id, family_id, for_share=True)
    _require_current_family_authority_admin(session, context)

    people = list(
        session.scalars(
            select(FamilyAuthorityPerson)
            .where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == family_id,
            )
            .order_by(FamilyAuthorityPerson.created_at, FamilyAuthorityPerson.id)
        )
    )
    current_version_ids = [
        person.current_person_version_id
        for person in people
        if person.current_person_version_id is not None
    ]
    versions_by_id: dict[UUID, FamilyAuthorityPersonVersion] = {}
    if current_version_ids:
        versions_by_id = {
            value.id: value
            for value in session.scalars(
                select(FamilyAuthorityPersonVersion).where(
                    FamilyAuthorityPersonVersion.organization_id == organization_id,
                    FamilyAuthorityPersonVersion.family_id == family_id,
                    FamilyAuthorityPersonVersion.id.in_(current_version_ids),
                )
            )
        }
    for person in people:
        if (
            person.current_person_version_id is not None
            and person.current_person_version_id not in versions_by_id
        ):
            raise HTTPException(409, detail={"code": "authority_person_version_missing"})

    evidence = list(
        session.scalars(
            select(FamilyAuthorityEvidence)
            .where(
                FamilyAuthorityEvidence.organization_id == organization_id,
                FamilyAuthorityEvidence.family_id == family_id,
            )
            .order_by(FamilyAuthorityEvidence.created_at, FamilyAuthorityEvidence.id)
        )
    )
    assessments_by_evidence: defaultdict[
        UUID, list[FamilyAuthorityEvidenceAssessment]
    ] = defaultdict(list)
    evidence_ids = [value.id for value in evidence]
    if evidence_ids:
        for assessment in session.scalars(
            select(FamilyAuthorityEvidenceAssessment)
            .where(
                FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
                FamilyAuthorityEvidenceAssessment.family_id == family_id,
                FamilyAuthorityEvidenceAssessment.evidence_id.in_(evidence_ids),
            )
            .order_by(
                FamilyAuthorityEvidenceAssessment.evidence_id,
                FamilyAuthorityEvidenceAssessment.version_number,
            )
        ):
            assessments_by_evidence[assessment.evidence_id].append(assessment)
    current_assessments: dict[UUID, FamilyAuthorityEvidenceAssessment] = {}
    for evidence_id in evidence_ids:
        history = assessments_by_evidence[evidence_id]
        versions = [value.version_number for value in history]
        if (
            versions not in ([], [2], [2, 3])
            or (history and history[0].decision not in {"reviewed", "rejected"})
            or (
                len(history) == 2
                and (
                    history[0].decision != "reviewed"
                    or history[1].decision not in {"invalidated", "superseded"}
                )
            )
        ):
            raise HTTPException(409, detail={"code": "authority_evidence_state_invalid"})
        if history:
            current_assessments[evidence_id] = history[-1]
    children = list(
        session.scalars(
            select(Child)
            .where(
                Child.organization_id == organization_id,
                Child.family_id == family_id,
            )
            .order_by(Child.created_at, Child.id)
        )
    )
    child_ids = [child.id for child in children]

    heads: dict[UUID, ChildAuthorityHead] = {}
    authorizations_by_child: defaultdict[UUID, list[ChildReleaseAuthorization]] = defaultdict(
        list
    )
    rules_by_child: defaultdict[UUID, list[ChildReleaseRule]] = defaultdict(list)
    consents_by_child: defaultdict[UUID, list[ChildConsentDecision]] = defaultdict(list)
    if child_ids:
        heads = {
            value.child_id: value
            for value in session.scalars(
                select(ChildAuthorityHead).where(
                    ChildAuthorityHead.organization_id == organization_id,
                    ChildAuthorityHead.family_id == family_id,
                    ChildAuthorityHead.child_id.in_(child_ids),
                )
            )
        }
        for value in session.scalars(
            select(ChildReleaseAuthorization)
            .where(
                ChildReleaseAuthorization.organization_id == organization_id,
                ChildReleaseAuthorization.family_id == family_id,
                ChildReleaseAuthorization.child_id.in_(child_ids),
            )
            .order_by(ChildReleaseAuthorization.created_at, ChildReleaseAuthorization.id)
        ):
            authorizations_by_child[value.child_id].append(value)
        for value in session.scalars(
            select(ChildReleaseRule)
            .where(
                ChildReleaseRule.organization_id == organization_id,
                ChildReleaseRule.family_id == family_id,
                ChildReleaseRule.child_id.in_(child_ids),
            )
            .order_by(ChildReleaseRule.created_at, ChildReleaseRule.id)
        ):
            rules_by_child[value.child_id].append(value)
        for value in session.scalars(
            select(ChildConsentDecision)
            .where(
                ChildConsentDecision.organization_id == organization_id,
                ChildConsentDecision.family_id == family_id,
                ChildConsentDecision.child_id.in_(child_ids),
            )
            .order_by(ChildConsentDecision.created_at, ChildConsentDecision.id)
        ):
            consents_by_child[value.child_id].append(value)

    evaluated_at = _transaction_cutoff(session)
    valid_evidence_pairs = _valid_evidence_pairs_from_loaded(
        evidence,
        current_assessments,
        evaluated_at,
    )
    child_workspaces: list[ChildFamilyAuthorityResponse] = []
    for child in children:
        head = heads.get(child.id)
        revision = head.revision if head is not None else 0
        has_domain_rows = bool(
            authorizations_by_child[child.id]
            or rules_by_child[child.id]
            or consents_by_child[child.id]
        )
        if revision == 0 and has_domain_rows:
            raise HTTPException(409, detail={"code": "authority_head_missing"})
        child_workspaces.append(
            ChildFamilyAuthorityResponse(
                child_id=child.id,
                reviewed=revision > 0,
                authority_revision=revision,
                release_authorizations=[
                    _authorization_response(
                        value,
                        revision,
                        valid_evidence_pairs=valid_evidence_pairs,
                        evaluated_at=evaluated_at,
                    )
                    for value in authorizations_by_child[child.id]
                ],
                release_rules=[
                    _rule_response(
                        value,
                        revision,
                        valid_evidence_pairs=valid_evidence_pairs,
                        evaluated_at=evaluated_at,
                    )
                    for value in rules_by_child[child.id]
                ],
                consent_decisions=[
                    _consent_response(
                        value,
                        revision,
                        valid_evidence_pairs=valid_evidence_pairs,
                        evaluated_at=evaluated_at,
                    )
                    for value in consents_by_child[child.id]
                ],
            )
        )

    from app.basic.family_evidence_objects import list_family_evidence_objects

    return FamilyAuthorityWorkspaceResponse(
        organization_id=organization_id,
        family_id=family_id,
        generated_at=evaluated_at,
        people=[
            _person_response(
                person,
                versions_by_id.get(person.current_person_version_id),
            )
            for person in people
        ],
        evidence_objects=list_family_evidence_objects(session, organization_id, family_id),
        evidence=[
            _evidence_response(
                value,
                current_assessments.get(value.id),
                evaluated_at,
            )
            for value in evidence
        ],
        children=child_workspaces,
    )


_CHILD_AUTHORITY_SUMMARY_LIMIT = 200


def _bounded_summary_rows(session: Session, statement, *, lane: str) -> list[object]:
    values = list(session.scalars(statement.limit(_CHILD_AUTHORITY_SUMMARY_LIMIT + 1)))
    if len(values) > _CHILD_AUTHORITY_SUMMARY_LIMIT:
        raise HTTPException(
            409,
            detail={"code": "child_authority_summary_too_large", "lane": lane},
        )
    return values


def _child_authority_person_summaries(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person_ids: set[UUID],
) -> dict[UUID, ChildAuthorityPersonSummary]:
    if not person_ids:
        return {}
    people = {
        value.id: value
        for value in session.scalars(
            select(FamilyAuthorityPerson).where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == family_id,
                FamilyAuthorityPerson.id.in_(person_ids),
            )
        )
    }
    if set(people) != person_ids:
        raise HTTPException(409, detail={"code": "authority_person_missing"})
    latest_version_numbers = (
        select(
            FamilyAuthorityPersonVersion.person_id.label("person_id"),
            func.max(FamilyAuthorityPersonVersion.version_number).label("version_number"),
        )
        .where(
            FamilyAuthorityPersonVersion.organization_id == organization_id,
            FamilyAuthorityPersonVersion.family_id == family_id,
            FamilyAuthorityPersonVersion.person_id.in_(person_ids),
        )
        .group_by(FamilyAuthorityPersonVersion.person_id)
        .subquery()
    )
    versions = {
        value.person_id: value
        for value in session.scalars(
            select(FamilyAuthorityPersonVersion)
            .join(
                latest_version_numbers,
                and_(
                    FamilyAuthorityPersonVersion.person_id
                    == latest_version_numbers.c.person_id,
                    FamilyAuthorityPersonVersion.version_number
                    == latest_version_numbers.c.version_number,
                ),
            )
            .where(
                FamilyAuthorityPersonVersion.organization_id == organization_id,
                FamilyAuthorityPersonVersion.family_id == family_id,
            )
        )
    }
    if set(versions) != person_ids:
        raise HTTPException(409, detail={"code": "authority_person_version_missing"})
    summaries: dict[UUID, ChildAuthorityPersonSummary] = {}
    for person_id in sorted(person_ids, key=str):
        person = people[person_id]
        version = versions[person_id]
        active_version_is_coherent = (
            person.status == "active"
            and person.current_person_version_id == version.id
            and version.closed_at is None
        )
        retired_version_is_coherent = (
            person.status == "retired"
            and person.current_person_version_id is None
            and version.closed_at is not None
        )
        if not active_version_is_coherent and not retired_version_is_coherent:
            raise HTTPException(409, detail={"code": "authority_person_version_missing"})
        first_name = version.preferred_name or version.first_name
        summaries[person_id] = ChildAuthorityPersonSummary(
            id=person_id,
            display_name=f"{first_name} {version.last_name}",
            relationship_kind=version.relationship_kind,
            status=person.status,
        )
    return summaries


def get_child_authority_summary(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    *,
    focus_kind: ChildAuthoritySummaryFocusKind | None = None,
    focus_id: UUID | None = None,
) -> ChildAuthoritySummaryResponse:
    """Project minimum-necessary authority facts for one child profile.

    This administrative read never answers whether a checkout is allowed.  It
    intentionally omits contact details, evidence, signer/grantor provenance,
    confidential reasons and policy content.
    """

    if (focus_kind is None) != (focus_id is None):
        raise ValueError("focus kind and id must be provided together")
    # The route dependency establishes the initial leader boundary. Recheck and
    # hold the exact membership/role rows so a concurrent revocation cannot let
    # a stale request finish projecting confidential authority facts.
    from app.basic.family_evidence_objects import require_current_family_authority_admin

    require_current_family_authority_admin(session, context)
    organization_id = context.organization.id
    child = session.scalar(
        select(Child).where(
            Child.organization_id == organization_id,
            Child.id == child_id,
        )
    )
    if child is None:
        raise HTTPException(404, detail="Child not found")
    _family(session, organization_id, child.family_id, for_share=True)
    evaluated_at = _transaction_cutoff(session)
    head = session.scalar(
        select(ChildAuthorityHead).where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == child.family_id,
            ChildAuthorityHead.child_id == child.id,
        )
    )
    revision = head.revision if head is not None else 0

    authorizations = _bounded_summary_rows(
        session,
        select(ChildReleaseAuthorization)
        .where(
            ChildReleaseAuthorization.organization_id == organization_id,
            ChildReleaseAuthorization.family_id == child.family_id,
            ChildReleaseAuthorization.child_id == child.id,
            ChildReleaseAuthorization.revoked_at.is_(None),
            ChildReleaseAuthorization.effective_until > evaluated_at,
        )
        .order_by(
            ChildReleaseAuthorization.effective_from,
            ChildReleaseAuthorization.id,
        ),
        lane="release_authorizations",
    )
    rules = _bounded_summary_rows(
        session,
        select(ChildReleaseRule)
        .where(
            ChildReleaseRule.organization_id == organization_id,
            ChildReleaseRule.family_id == child.family_id,
            ChildReleaseRule.child_id == child.id,
            ChildReleaseRule.revoked_at.is_(None),
            ChildReleaseRule.effective_until > evaluated_at,
        )
        .order_by(ChildReleaseRule.effective_from, ChildReleaseRule.id),
        lane="release_rules",
    )
    consents = _bounded_summary_rows(
        session,
        select(ChildConsentDecision)
        .where(
            ChildConsentDecision.organization_id == organization_id,
            ChildConsentDecision.family_id == child.family_id,
            ChildConsentDecision.child_id == child.id,
            ChildConsentDecision.withdrawn_at.is_(None),
            ChildConsentDecision.effective_until > evaluated_at,
        )
        .order_by(ChildConsentDecision.effective_from, ChildConsentDecision.id),
        lane="consent_decisions",
    )

    focus_value: ChildReleaseAuthorization | ChildReleaseRule | ChildConsentDecision | None = None
    if focus_kind is not None and focus_id is not None:
        model = {
            "release_authorization": ChildReleaseAuthorization,
            "release_rule": ChildReleaseRule,
            "consent": ChildConsentDecision,
        }[focus_kind]
        focus_value = session.scalar(
            select(model).where(
                model.organization_id == organization_id,
                model.family_id == child.family_id,
                model.child_id == child.id,
                model.id == focus_id,
            )
        )
        if focus_value is None:
            raise HTTPException(
                404,
                detail={"code": "child_authority_focus_not_found"},
            )

    all_authorizations = [
        *authorizations,
        *(
            [focus_value]
            if isinstance(focus_value, ChildReleaseAuthorization)
            and all(value.id != focus_value.id for value in authorizations)
            else []
        ),
    ]
    all_rules = [
        *rules,
        *(
            [focus_value]
            if isinstance(focus_value, ChildReleaseRule)
            and all(value.id != focus_value.id for value in rules)
            else []
        ),
    ]
    all_consents = [
        *consents,
        *(
            [focus_value]
            if isinstance(focus_value, ChildConsentDecision)
            and all(value.id != focus_value.id for value in consents)
            else []
        ),
    ]
    if revision == 0 and (all_authorizations or all_rules or all_consents):
        raise HTTPException(409, detail={"code": "authority_head_missing"})

    evidence_ids = {
        *(value.basis_evidence_id for value in all_authorizations),
        *(value.basis_evidence_id for value in all_rules),
        *(value.evidence_id for value in all_consents),
        *(value.signer_authority_evidence_id for value in all_consents),
    }
    valid_evidence_pairs = _load_valid_evidence_pairs(
        session,
        organization_id,
        child.family_id,
        evidence_ids,
        evaluated_at,
    )
    person_ids = {
        *(value.recipient_person_id for value in all_authorizations),
        *(
            value.scope_person_id
            for value in all_rules
            if value.scope_person_id is not None
        ),
    }
    people = _child_authority_person_summaries(
        session,
        organization_id,
        child.family_id,
        person_ids,
    )
    policy_ids = {value.policy_version_id for value in all_consents}
    policies = {
        value.id: value
        for value in session.scalars(
            select(ConsentPolicyVersion).where(
                ConsentPolicyVersion.organization_id == organization_id,
                ConsentPolicyVersion.id.in_(policy_ids),
            )
        )
    } if policy_ids else {}
    if set(policies) != policy_ids:
        raise HTTPException(409, detail={"code": "consent_policy_missing"})

    def authorization_summary(value: ChildReleaseAuthorization):
        projected = _authorization_response(
            value,
            revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        )
        return ChildReleaseAuthorizationSummary(
            record_type="release_authorization",
            id=value.id,
            child_id=child.id,
            recipient=people[value.recipient_person_id],
            verification_policy_code=value.verification_policy_code,
            effective_from=projected.effective_from,
            effective_until=projected.effective_until,
            version=value.version,
            effective_status=projected.effective_status,
            effective_now=projected.effective_now,
            authority_revision=revision,
        )

    def rule_summary(value: ChildReleaseRule):
        projected = _rule_response(
            value,
            revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        )
        return ChildReleaseRuleSummary(
            record_type="release_rule",
            id=value.id,
            child_id=child.id,
            rule_kind=value.rule_kind,
            safe_explanation_code=value.safe_explanation_code,
            scope_kind=value.scope_kind,
            scoped_person=(
                people[value.scope_person_id]
                if value.scope_person_id is not None
                else None
            ),
            effective_from=projected.effective_from,
            effective_until=projected.effective_until,
            version=value.version,
            effective_status=projected.effective_status,
            effective_now=projected.effective_now,
            authority_revision=revision,
        )

    def consent_summary(value: ChildConsentDecision):
        projected = _consent_response(
            value,
            revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        )
        policy = policies[value.policy_version_id]
        return ChildConsentDecisionSummary(
            record_type="consent",
            id=value.id,
            child_id=child.id,
            purpose_code=value.purpose_code,
            policy={
                "id": policy.id,
                "title": policy.title,
                "version_number": policy.version_number,
            },
            decision=value.decision,
            scope=projected.scope,
            effective_from=projected.effective_from,
            effective_until=projected.effective_until,
            version=value.version,
            effective_status=projected.effective_status,
            effective_now=projected.effective_now,
            authority_revision=revision,
        )

    focus = None
    if isinstance(focus_value, ChildReleaseAuthorization):
        focus = authorization_summary(focus_value)
    elif isinstance(focus_value, ChildReleaseRule):
        focus = rule_summary(focus_value)
    elif isinstance(focus_value, ChildConsentDecision):
        focus = consent_summary(focus_value)

    return ChildAuthoritySummaryResponse(
        schema_version="child-authority-summary-v1",
        organization_id=organization_id,
        family_id=child.family_id,
        child_id=child.id,
        generated_at=evaluated_at,
        reviewed=revision > 0,
        authority_revision=revision,
        release_authorizations=[authorization_summary(value) for value in authorizations],
        release_rules=[rule_summary(value) for value in rules],
        consent_decisions=[consent_summary(value) for value in consents],
        focus=focus,
    )
