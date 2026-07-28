"""0029A2 admin command services for activating reviewed family authority.

This module deliberately stops before educator release context and checkout.
Every write is an exact-retry command, advances one bounded aggregate, and
rechecks the current owner/administrator membership while its transaction is
still open.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.api.basic.common import restore_context
from app.api.basic.dependencies import BasicContext
from app.basic.childcare_commands import begin_command, record_command, require_version
from app.basic.family_authority import (
    _authorization_response,
    _consent_response,
    _family,
    _load_valid_evidence_pairs,
    _raise_receipt_incomplete,
    _receipt_response,
    _rule_response,
    _transaction_cutoff,
    _utc,
)
from app.basic.family_authority_activation_matrix import (
    ACTIVATABLE_RELEASE_RULE_KINDS,
    CONSENT_DECISION_EVIDENCE_KIND,
    consent_signer_authority,
    person_must_have_guardian_source,
    release_grant_evidence_kind,
    release_rule_evidence_kind,
)
from app.basic.family_authority_schemas import (
    ChildConsentCommandResponse,
    ChildConsentRecordRequest,
    ChildConsentWithdrawRequest,
    ConsentPolicyCommandResponse,
    ConsentPolicyPublishRequest,
    ConsentPolicyVersionResponse,
    ReleaseAuthorizationCommandResponse,
    ReleaseAuthorizationGrantRequest,
    ReleaseAuthorizationRevokeRequest,
    ReleaseRuleCommandResponse,
    ReleaseRuleCreateRequest,
    ReleaseRuleRevokeRequest,
)
from app.basic.family_evidence_objects import require_current_family_authority_admin
from app.basic.models import (
    Child,
    ChildAuthorityHead,
    ChildcareCommandReceipt,
    ChildConsentDecision,
    ChildReleaseAuthorization,
    ChildReleaseRule,
    ConsentPolicyVersion,
    Facility,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceAssessment,
    FamilyAuthorityPerson,
    FamilyAuthorityPersonVersion,
    Guardian,
    Organization,
)
from app.basic.security import audit

AUTHORIZATION_GRANT_COMMAND = "child.release.authorization.grant"
AUTHORIZATION_REVOKE_COMMAND = "child.release.authorization.revoke"
AUTHORIZATION_TARGET_TYPE = "release_authorization"
RULE_CREATE_COMMAND = "child.release.rule.create"
RULE_REVOKE_COMMAND = "child.release.rule.revoke"
RULE_TARGET_TYPE = "release_rule"
POLICY_PUBLISH_COMMAND = "organization.consent.policy.publish"
CONSENT_RECORD_COMMAND = "child.consent.record"
CONSENT_WITHDRAW_COMMAND = "child.consent.withdraw"
CONSENT_TARGET_TYPE = "consent"

SAFE_RULE_CODE = {
    "deny": "release_restricted",
    "manager_review": "manager_review_required",
}


def _constraint_name(error: DBAPIError) -> str:
    diagnostic = getattr(error.orig, "diag", None)
    return str(getattr(diagnostic, "constraint_name", None) or "")


def _is_serialization_failure(error: DBAPIError) -> bool:
    original = error.orig
    return (
        getattr(original, "sqlstate", None) == "40001"
        or getattr(original, "pgcode", None) == "40001"
    )


def _write_error(session: Session, error: DBAPIError) -> None:
    """Translate expected database races without returning database details."""

    session.rollback()
    name = _constraint_name(error).lower()
    message = str(error.orig).lower()
    combined = f"{name} {message}"

    if _is_serialization_failure(error) or any(
        marker in combined
        for marker in (
            "child_authority_command_revision",
            "authority_revision_invariant",
            "authority revision changed",
        )
    ):
        raise HTTPException(409, detail={"code": "authority_revision_changed"}) from None
    if any(
        marker in combined
        for marker in (
            "release_authorizations_overlap",
            "ex_release_authorizations_active_window",
            "release authorization overlap",
            "release authorization interval overlaps",
        )
    ):
        raise HTTPException(409, detail={"code": "release_authorization_overlap"}) from None
    if any(
        marker in combined
        for marker in (
            "release_rules_overlap",
            "ex_release_rules_active_window",
            "release rule overlap",
            "release rule interval overlaps",
        )
    ):
        raise HTTPException(409, detail={"code": "release_rule_overlap"}) from None
    if any(
        marker in combined
        for marker in (
            "consent_policy_versions_overlap",
            "ex_consent_policy_active_window",
            "consent policy overlap",
            "consent policy interval overlaps",
        )
    ):
        raise HTTPException(409, detail={"code": "consent_policy_overlap"}) from None
    if any(
        marker in combined
        for marker in (
            "child_consent_decisions_overlap",
            "ex_child_consent_active_window",
            "consent decision overlap",
            "consent decision interval overlaps",
        )
    ):
        raise HTTPException(409, detail={"code": "consent_decision_overlap"}) from None
    if any(
        marker in combined
        for marker in (
            "activation_maker_checker",
            "activation actor must differ",
        )
    ):
        raise HTTPException(409, detail={"code": "activation_maker_checker_required"}) from None
    if any(
        marker in combined
        for marker in (
            "release_rule_kind_activatable",
            "release rule kind is not activatable",
        )
    ):
        raise HTTPException(409, detail={"code": "release_rule_kind_not_activatable"}) from None
    if any(
        marker in combined
        for marker in (
            "child_consent_signer_authority",
            "child_consent_guardian_provenance",
            "consent signer basis does not exactly satisfy",
            "guardian consent authority requires",
        )
    ):
        raise HTTPException(409, detail={"code": "consent_signer_requirement_mismatch"}) from None
    if any(
        marker in combined
        for marker in (
            "consent_policy_activatable_signer",
            "specific reviewed consent authority is not activatable",
        )
    ):
        raise HTTPException(
            409, detail={"code": "consent_signer_requirement_not_activatable"}
        ) from None
    if any(
        marker in combined
        for marker in (
            "family_authority_activation_evidence_current",
            "authority basis evidence is not current and reviewed",
        )
    ):
        raise HTTPException(
            409, detail={"code": "authority_evidence_assessment_not_current"}
        ) from None
    if any(
        marker in combined
        for marker in (
            "activation_evidence",
            "authority_basis_activation",
            "evidence kind cannot activate",
            "release_authorization_guardian_provenance",
            "release_authorization_evidence_kind",
            "release_authorization_delegation_provenance",
            "release_authorization_basis_activatable",
            "release_rule_guardian_provenance",
            "release_rule_evidence_kind",
            "release_rule_basis_activatable",
            "child_consent_decision_evidence_kind",
            "child_consent_signer_evidence_kind",
            "child_consent_signer_basis_activatable",
        )
    ):
        raise HTTPException(409, detail={"code": "authority_basis_not_activatable"}) from None
    if any(
        marker in combined
        for marker in (
            "privileged_actor",
            "family authority access revoked",
        )
    ):
        raise HTTPException(403, detail={"code": "family_authority_access_revoked"}) from None
    if isinstance(error, IntegrityError):
        raise HTTPException(409, detail={"code": "family_authority_activation_conflict"}) from None
    raise HTTPException(503, detail={"code": "family_authority_activation_unavailable"}) from None


def _flush(session: Session) -> None:
    try:
        session.flush()
    except (IntegrityError, DBAPIError) as error:
        _write_error(session, error)


def _commit(session: Session, context: BasicContext) -> None:
    try:
        session.commit()
    except (IntegrityError, DBAPIError) as error:
        _write_error(session, error)
    restore_context(session, context)
    session.expire_all()


def _policy_response(value: ConsentPolicyVersion) -> ConsentPolicyVersionResponse:
    return ConsentPolicyVersionResponse(
        id=value.id,
        organization_id=value.organization_id,
        purpose_code=value.purpose_code,
        version_number=value.version_number,
        title=value.title,
        content_text=value.content_text,
        content_reference=value.content_reference,
        content_sha256=value.content_sha256,
        signer_authority_requirement=value.signer_authority_requirement,
        effective_from=_utc(value.effective_from),
        effective_until=_utc(value.effective_until),
        published_at=_utc(value.published_at),
    )


def _organization_lock(session: Session, organization_id: UUID, *, read: bool) -> None:
    statement = select(Organization.id).where(Organization.id == organization_id)
    statement = statement.with_for_update(read=read)
    if session.scalar(statement) is None:
        raise HTTPException(404, detail="Organization not found")


def _child_family_id(
    session: Session,
    organization_id: UUID,
    child_id: UUID,
) -> UUID:
    family_id = session.scalar(
        select(Child.family_id).where(
            Child.organization_id == organization_id,
            Child.id == child_id,
        )
    )
    if family_id is None:
        raise HTTPException(404, detail="Child not found")
    return family_id


def _lock_child_boundary(
    session: Session,
    organization_id: UUID,
    child_id: UUID,
) -> tuple[Child, ChildAuthorityHead | None]:
    """Take the common family -> child -> head lock order for one child command."""

    family_id = _child_family_id(session, organization_id, child_id)
    _family(session, organization_id, family_id, for_update=True)
    child = session.scalar(
        select(Child)
        .where(
            Child.organization_id == organization_id,
            Child.family_id == family_id,
            Child.id == child_id,
        )
        .with_for_update()
    )
    if child is None:
        raise HTTPException(404, detail="Child not found")
    head = session.scalar(
        select(ChildAuthorityHead)
        .where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == family_id,
            ChildAuthorityHead.child_id == child_id,
        )
        .with_for_update()
    )
    return child, head


def _require_authority_revision(
    head: ChildAuthorityHead | None,
    expected_revision: int,
) -> int:
    current = head.revision if head is not None else 0
    if current != expected_revision:
        raise HTTPException(
            409,
            detail={
                "code": "authority_revision_changed",
                "expected_authority_revision": expected_revision,
                "current_authority_revision": current,
            },
        )
    return current


def _advance_authority_head(
    session: Session,
    child: Child,
    head: ChildAuthorityHead | None,
    operation_id: UUID,
) -> ChildAuthorityHead:
    if head is None:
        head = ChildAuthorityHead(
            organization_id=child.organization_id,
            family_id=child.family_id,
            child_id=child.id,
            revision=1,
            created_operation_id=operation_id,
            last_operation_id=operation_id,
        )
        session.add(head)
    else:
        head.revision += 1
        head.last_operation_id = operation_id
    return head


def _current_people(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person_ids: set[UUID],
) -> dict[UUID, tuple[FamilyAuthorityPerson, FamilyAuthorityPersonVersion]]:
    if not person_ids:
        return {}
    people = list(
        session.scalars(
            select(FamilyAuthorityPerson)
            .where(
                FamilyAuthorityPerson.organization_id == organization_id,
                FamilyAuthorityPerson.family_id == family_id,
                FamilyAuthorityPerson.id.in_(person_ids),
            )
            .order_by(FamilyAuthorityPerson.id)
            .with_for_update()
        )
    )
    if {person.id for person in people} != person_ids:
        raise HTTPException(404, detail="Authority person not found")
    version_ids = {
        person.current_person_version_id
        for person in people
        if person.current_person_version_id is not None
    }
    versions = list(
        session.scalars(
            select(FamilyAuthorityPersonVersion)
            .where(
                FamilyAuthorityPersonVersion.organization_id == organization_id,
                FamilyAuthorityPersonVersion.family_id == family_id,
                FamilyAuthorityPersonVersion.id.in_(version_ids),
            )
            .order_by(FamilyAuthorityPersonVersion.id)
            .with_for_update(read=True)
        )
    )
    versions_by_id = {version.id: version for version in versions}
    result: dict[UUID, tuple[FamilyAuthorityPerson, FamilyAuthorityPersonVersion]] = {}
    for person in people:
        version = versions_by_id.get(person.current_person_version_id)
        if (
            person.status != "active"
            or version is None
            or version.person_id != person.id
            or version.version_number != person.version
            or version.closed_at is not None
        ):
            raise HTTPException(409, detail={"code": "authority_person_not_current"})
        result[person.id] = (person, version)
    return result


def _require_submitted_person_version(
    current: tuple[FamilyAuthorityPerson, FamilyAuthorityPersonVersion],
    submitted_version_id: UUID,
) -> FamilyAuthorityPerson:
    person, version = current
    if version.id != submitted_version_id:
        raise HTTPException(409, detail={"code": "authority_person_not_current"})
    return person


def _require_live_guardian_source(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    person: FamilyAuthorityPerson,
) -> None:
    if person.source_guardian_id is None:
        raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})
    guardian_id = session.scalar(
        select(Guardian.id)
        .where(
            Guardian.organization_id == organization_id,
            Guardian.family_id == family_id,
            Guardian.id == person.source_guardian_id,
            Guardian.retired_at.is_(None),
        )
        .with_for_update(read=True)
    )
    if guardian_id is None:
        raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})


def _reviewed_evidence(
    session: Session,
    organization_id: UUID,
    family_id: UUID,
    references: dict[str, tuple[UUID, UUID, str]],
    *,
    actor_user_id: UUID,
    effective_until: datetime,
    evaluated_at: datetime,
) -> dict[str, tuple[FamilyAuthorityEvidence, FamilyAuthorityEvidenceAssessment]]:
    """Validate exact reviewed evidence under the caller's family aggregate lock.

    Evidence rows and their assessment history are append-only.  Every command
    that can change their effective state takes the same family ``FOR UPDATE``
    lock before appending an assessment, so taking row locks here adds no
    serialization guarantee.  It would also require ``UPDATE`` on these
    intentionally immutable tables, which the runtime role must not receive.
    """

    evidence_ids = {value[0] for value in references.values()}
    assets = list(
        session.scalars(
            _reviewed_evidence_assets_statement(
                organization_id,
                family_id,
                evidence_ids,
            )
        )
    )
    assets_by_id = {asset.id: asset for asset in assets}
    if set(assets_by_id) != evidence_ids:
        raise HTTPException(404, detail="Authority evidence not found")

    history = list(
        session.scalars(
            _reviewed_evidence_assessments_statement(
                organization_id,
                family_id,
                evidence_ids,
            )
        )
    )
    latest_by_evidence: dict[UUID, FamilyAuthorityEvidenceAssessment] = {}
    assessments_by_id = {assessment.id: assessment for assessment in history}
    for assessment in history:
        latest_by_evidence.setdefault(assessment.evidence_id, assessment)

    resolved: dict[str, tuple[FamilyAuthorityEvidence, FamilyAuthorityEvidenceAssessment]] = {}
    for label, (evidence_id, assessment_id, expected_kind) in references.items():
        evidence = assets_by_id[evidence_id]
        assessment = assessments_by_id.get(assessment_id)
        latest = latest_by_evidence.get(evidence_id)
        if (
            assessment is None
            or assessment.evidence_id != evidence_id
            or latest is None
            or latest.id != assessment.id
            or assessment.version_number != 2
            or assessment.decision != "reviewed"
        ):
            raise HTTPException(409, detail={"code": "authority_evidence_assessment_not_current"})
        if evidence.evidence_kind != expected_kind:
            raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})
        expires_at = _utc(evidence.expires_at)
        if expires_at is not None and (expires_at <= evaluated_at or effective_until > expires_at):
            raise HTTPException(409, detail={"code": "authority_evidence_expired"})
        if assessment.actor_user_id == actor_user_id:
            raise HTTPException(409, detail={"code": "activation_maker_checker_required"})
        resolved[label] = (evidence, assessment)
    return resolved


def _reviewed_evidence_assets_statement(
    organization_id: UUID,
    family_id: UUID,
    evidence_ids: set[UUID],
) -> Select[tuple[FamilyAuthorityEvidence]]:
    """Build the append-only evidence read without requesting a row lock."""

    return (
        select(FamilyAuthorityEvidence)
        .where(
            FamilyAuthorityEvidence.organization_id == organization_id,
            FamilyAuthorityEvidence.family_id == family_id,
            FamilyAuthorityEvidence.id.in_(evidence_ids),
        )
        .order_by(FamilyAuthorityEvidence.id)
    )


def _reviewed_evidence_assessments_statement(
    organization_id: UUID,
    family_id: UUID,
    evidence_ids: set[UUID],
) -> Select[tuple[FamilyAuthorityEvidenceAssessment]]:
    """Build the append-only assessment-history read without a row lock."""

    return (
        select(FamilyAuthorityEvidenceAssessment)
        .where(
            FamilyAuthorityEvidenceAssessment.organization_id == organization_id,
            FamilyAuthorityEvidenceAssessment.family_id == family_id,
            FamilyAuthorityEvidenceAssessment.evidence_id.in_(evidence_ids),
        )
        .order_by(
            FamilyAuthorityEvidenceAssessment.evidence_id,
            FamilyAuthorityEvidenceAssessment.version_number.desc(),
        )
    )


def _consent_policy_for_decision_statement(
    organization_id: UUID,
    policy_version_id: UUID,
    purpose_code: str,
) -> Select[tuple[ConsentPolicyVersion]]:
    """Read one immutable published policy without requiring UPDATE privilege."""

    return select(ConsentPolicyVersion).where(
        ConsentPolicyVersion.organization_id == organization_id,
        ConsentPolicyVersion.id == policy_version_id,
        ConsentPolicyVersion.purpose_code == purpose_code,
    )


def _overlaps(
    effective_from_column,
    effective_until_column,
    effective_from: datetime,
    effective_until: datetime,
):
    return and_(
        effective_from_column < effective_until,
        effective_until_column > effective_from,
    )


def _record_receipt(
    session: Session,
    context: BasicContext,
    *,
    operation_id: UUID,
    command_type: str,
    target_type: str,
    target_id: UUID,
    request_hash: str,
    committed_version: int,
    action_route: str,
) -> ChildcareCommandReceipt:
    receipt = record_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=operation_id,
        command_type=command_type,
        target_type=target_type,
        target_id=target_id,
        request_hash=request_hash,
        committed_version=committed_version,
        outcome={"action_route": action_route},
    )
    _flush(session)
    return receipt


def _load_authorization_for_receipt(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    recheck_current_role: bool,
) -> tuple[ChildReleaseAuthorization, ChildAuthorityHead]:
    organization_id = context.organization.id
    family_id = _child_family_id(session, organization_id, child_id)
    _family(session, organization_id, family_id, for_share=True)
    if recheck_current_role:
        require_current_family_authority_admin(session, context)
    value = session.scalar(
        select(ChildReleaseAuthorization).where(
            ChildReleaseAuthorization.organization_id == organization_id,
            ChildReleaseAuthorization.family_id == family_id,
            ChildReleaseAuthorization.child_id == child_id,
            ChildReleaseAuthorization.id == receipt.target_id,
        )
    )
    head = session.scalar(
        select(ChildAuthorityHead).where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == family_id,
            ChildAuthorityHead.child_id == child_id,
        )
    )
    if value is None or head is None or value.version < receipt.committed_version:
        _raise_receipt_incomplete(receipt)
    if receipt.command_type == AUTHORIZATION_GRANT_COMMAND:
        valid = value.created_operation_id == receipt.client_operation_id
    elif receipt.command_type == AUTHORIZATION_REVOKE_COMMAND:
        valid = (
            value.revoked_operation_id == receipt.client_operation_id
            and value.version == receipt.committed_version
        )
    else:
        valid = False
    if not valid:
        _raise_receipt_incomplete(receipt)
    return value, head


def _authorization_command_response(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    replayed: bool,
) -> ReleaseAuthorizationCommandResponse:
    organization_id = context.organization.id
    value, head = _load_authorization_for_receipt(
        session,
        context,
        child_id,
        receipt,
        recheck_current_role=replayed,
    )
    evaluated_at = _transaction_cutoff(session)
    valid_evidence_pairs = _load_valid_evidence_pairs(
        session,
        organization_id,
        value.family_id,
        {value.basis_evidence_id},
        evaluated_at,
    )
    return ReleaseAuthorizationCommandResponse(
        resource=_authorization_response(
            value,
            head.revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        ),
        receipt=_receipt_response(receipt),
        replayed=replayed,
    )


def _load_rule_for_receipt(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    recheck_current_role: bool,
) -> tuple[ChildReleaseRule, ChildAuthorityHead]:
    organization_id = context.organization.id
    family_id = _child_family_id(session, organization_id, child_id)
    _family(session, organization_id, family_id, for_share=True)
    if recheck_current_role:
        require_current_family_authority_admin(session, context)
    value = session.scalar(
        select(ChildReleaseRule).where(
            ChildReleaseRule.organization_id == organization_id,
            ChildReleaseRule.family_id == family_id,
            ChildReleaseRule.child_id == child_id,
            ChildReleaseRule.id == receipt.target_id,
        )
    )
    head = session.scalar(
        select(ChildAuthorityHead).where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == family_id,
            ChildAuthorityHead.child_id == child_id,
        )
    )
    if value is None or head is None or value.version < receipt.committed_version:
        _raise_receipt_incomplete(receipt)
    if receipt.command_type == RULE_CREATE_COMMAND:
        valid = value.created_operation_id == receipt.client_operation_id
    elif receipt.command_type == RULE_REVOKE_COMMAND:
        valid = (
            value.revoked_operation_id == receipt.client_operation_id
            and value.version == receipt.committed_version
        )
    else:
        valid = False
    if not valid:
        _raise_receipt_incomplete(receipt)
    return value, head


def _rule_command_response(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    replayed: bool,
) -> ReleaseRuleCommandResponse:
    organization_id = context.organization.id
    value, head = _load_rule_for_receipt(
        session,
        context,
        child_id,
        receipt,
        recheck_current_role=replayed,
    )
    evaluated_at = _transaction_cutoff(session)
    valid_evidence_pairs = _load_valid_evidence_pairs(
        session,
        organization_id,
        value.family_id,
        {value.basis_evidence_id},
        evaluated_at,
    )
    return ReleaseRuleCommandResponse(
        resource=_rule_response(
            value,
            head.revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        ),
        receipt=_receipt_response(receipt),
        replayed=replayed,
    )


def _load_policy_for_receipt(
    session: Session,
    context: BasicContext,
    receipt: ChildcareCommandReceipt,
    *,
    recheck_current_role: bool,
) -> ConsentPolicyVersion:
    organization_id = context.organization.id
    _organization_lock(session, organization_id, read=True)
    if recheck_current_role:
        require_current_family_authority_admin(session, context)
    value = session.scalar(
        select(ConsentPolicyVersion).where(
            ConsentPolicyVersion.organization_id == organization_id,
            ConsentPolicyVersion.id == receipt.target_id,
        )
    )
    if (
        value is None
        or value.created_operation_id != receipt.client_operation_id
        or value.version_number != receipt.committed_version
        or receipt.command_type != POLICY_PUBLISH_COMMAND
    ):
        _raise_receipt_incomplete(receipt)
    return value


def _load_consent_for_receipt(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    recheck_current_role: bool,
) -> tuple[ChildConsentDecision, ChildAuthorityHead]:
    organization_id = context.organization.id
    family_id = _child_family_id(session, organization_id, child_id)
    _family(session, organization_id, family_id, for_share=True)
    if recheck_current_role:
        require_current_family_authority_admin(session, context)
    value = session.scalar(
        select(ChildConsentDecision).where(
            ChildConsentDecision.organization_id == organization_id,
            ChildConsentDecision.family_id == family_id,
            ChildConsentDecision.child_id == child_id,
            ChildConsentDecision.id == receipt.target_id,
        )
    )
    head = session.scalar(
        select(ChildAuthorityHead).where(
            ChildAuthorityHead.organization_id == organization_id,
            ChildAuthorityHead.family_id == family_id,
            ChildAuthorityHead.child_id == child_id,
        )
    )
    if value is None or head is None or value.version < receipt.committed_version:
        _raise_receipt_incomplete(receipt)
    if receipt.command_type == CONSENT_RECORD_COMMAND:
        valid = value.created_operation_id == receipt.client_operation_id
    elif receipt.command_type == CONSENT_WITHDRAW_COMMAND:
        valid = (
            value.withdrawn_operation_id == receipt.client_operation_id
            and value.version == receipt.committed_version
        )
    else:
        valid = False
    if not valid:
        _raise_receipt_incomplete(receipt)
    return value, head


def _consent_command_response(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    receipt: ChildcareCommandReceipt,
    *,
    replayed: bool,
) -> ChildConsentCommandResponse:
    organization_id = context.organization.id
    value, head = _load_consent_for_receipt(
        session,
        context,
        child_id,
        receipt,
        recheck_current_role=replayed,
    )
    evaluated_at = _transaction_cutoff(session)
    valid_evidence_pairs = _load_valid_evidence_pairs(
        session,
        organization_id,
        value.family_id,
        {value.evidence_id, value.signer_authority_evidence_id},
        evaluated_at,
    )
    return ChildConsentCommandResponse(
        resource=_consent_response(
            value,
            head.revision,
            valid_evidence_pairs=valid_evidence_pairs,
            evaluated_at=evaluated_at,
        ),
        receipt=_receipt_response(receipt),
        replayed=replayed,
    )


def grant_release_authorization(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    payload: ReleaseAuthorizationGrantRequest,
) -> ReleaseAuthorizationCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=AUTHORIZATION_GRANT_COMMAND,
        target_type=AUTHORIZATION_TARGET_TYPE,
        target_scope=f"child:{child_id}:release_authorization:create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _authorization_command_response(
            session, context, child_id, receipt, replayed=True
        )

    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    people = _current_people(
        session,
        organization_id,
        child.family_id,
        {payload.recipient_person_id, payload.grantor.person_id},
    )
    _require_submitted_person_version(
        people[payload.grantor.person_id], payload.grantor.person_version_id
    )
    grantor_person = people[payload.grantor.person_id][0]
    expected_kind = release_grant_evidence_kind(payload.grantor.authority_basis)
    if expected_kind is None:
        raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})
    if person_must_have_guardian_source(payload.grantor.authority_basis):
        _require_live_guardian_source(
            session,
            organization_id,
            child.family_id,
            grantor_person,
        )
    evaluated_at = _transaction_cutoff(session)
    _reviewed_evidence(
        session,
        organization_id,
        child.family_id,
        {
            "grantor": (
                payload.grantor.basis_evidence_id,
                payload.grantor.basis_evidence_assessment_id,
                expected_kind,
            )
        },
        actor_user_id=context.user.id,
        effective_until=payload.effective_until,
        evaluated_at=evaluated_at,
    )
    overlap = session.scalar(
        select(ChildReleaseAuthorization.id).where(
            ChildReleaseAuthorization.organization_id == organization_id,
            ChildReleaseAuthorization.child_id == child_id,
            ChildReleaseAuthorization.recipient_person_id == payload.recipient_person_id,
            ChildReleaseAuthorization.revoked_at.is_(None),
            _overlaps(
                ChildReleaseAuthorization.effective_from,
                ChildReleaseAuthorization.effective_until,
                payload.effective_from,
                payload.effective_until,
            ),
        )
    )
    if overlap is not None:
        raise HTTPException(409, detail={"code": "release_authorization_overlap"})
    require_current_family_authority_admin(session, context)

    authorization_id = uuid4()
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=AUTHORIZATION_GRANT_COMMAND,
        target_type=AUTHORIZATION_TARGET_TYPE,
        target_id=authorization_id,
        request_hash=request_hash,
        committed_version=1,
        action_route=(f"/children/{child_id}?release_authorization_id={authorization_id}"),
    )
    session.add(
        ChildReleaseAuthorization(
            id=authorization_id,
            organization_id=organization_id,
            family_id=child.family_id,
            child_id=child_id,
            recipient_person_id=payload.recipient_person_id,
            verification_policy_code=payload.verification_policy_code,
            grantor_person_id=payload.grantor.person_id,
            grantor_person_version_id=payload.grantor.person_version_id,
            grantor_authority_basis=payload.grantor.authority_basis,
            basis_evidence_id=payload.grantor.basis_evidence_id,
            basis_evidence_assessment_id=(payload.grantor.basis_evidence_assessment_id),
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            version=1,
            created_operation_id=payload.client_operation_id,
        )
    )
    # PostgreSQL's authority-head guard verifies the command target already
    # exists in this transaction.  Keep the enforced receipt -> target -> head
    # write order explicit instead of relying on ORM table ordering.
    _flush(session)
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.release.authorization.granted",
        entity_type=AUTHORIZATION_TARGET_TYPE,
        entity_id=authorization_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _authorization_command_response(
        session, context, child_id, command_receipt, replayed=False
    )


def revoke_release_authorization(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    authorization_id: UUID,
    payload: ReleaseAuthorizationRevokeRequest,
) -> ReleaseAuthorizationCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=AUTHORIZATION_REVOKE_COMMAND,
        target_type=AUTHORIZATION_TARGET_TYPE,
        target_scope=f"child:{child_id}:release_authorization:{authorization_id}",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != authorization_id:
            _raise_receipt_incomplete(receipt)
        return _authorization_command_response(
            session, context, child_id, receipt, replayed=True
        )

    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    value = session.scalar(
        select(ChildReleaseAuthorization)
        .where(
            ChildReleaseAuthorization.organization_id == organization_id,
            ChildReleaseAuthorization.family_id == child.family_id,
            ChildReleaseAuthorization.child_id == child_id,
            ChildReleaseAuthorization.id == authorization_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, detail="Release authorization not found")
    require_version(value, payload.expected_version, AUTHORIZATION_TARGET_TYPE)
    if value.revoked_at is not None:
        raise HTTPException(409, detail={"code": "release_authorization_already_revoked"})
    require_current_family_authority_admin(session, context)
    committed_version = value.version + 1
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=AUTHORIZATION_REVOKE_COMMAND,
        target_type=AUTHORIZATION_TARGET_TYPE,
        target_id=authorization_id,
        request_hash=request_hash,
        committed_version=committed_version,
        action_route=(f"/children/{child_id}?release_authorization_id={authorization_id}"),
    )
    value.version = committed_version
    value.revoked_at = _transaction_cutoff(session)
    value.revoked_operation_id = payload.client_operation_id
    value.revocation_reason_code = payload.reason_code
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.release.authorization.revoked",
        entity_type=AUTHORIZATION_TARGET_TYPE,
        entity_id=authorization_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _authorization_command_response(
        session, context, child_id, command_receipt, replayed=False
    )


def create_release_rule(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    payload: ReleaseRuleCreateRequest,
) -> ReleaseRuleCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=RULE_CREATE_COMMAND,
        target_type=RULE_TARGET_TYPE,
        target_scope=f"child:{child_id}:release_rule:create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _rule_command_response(session, context, child_id, receipt, replayed=True)
    if payload.rule_kind not in ACTIVATABLE_RELEASE_RULE_KINDS:
        raise HTTPException(409, detail={"code": "release_rule_kind_not_activatable"})

    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    person_ids: set[UUID] = set()
    if payload.scope.kind == "specific_person":
        person_ids.add(payload.scope.person_id)
    if payload.directing_person is not None:
        person_ids.add(payload.directing_person.person_id)
    people = _current_people(session, organization_id, child.family_id, person_ids)
    directing_person = None
    if payload.directing_person is not None:
        directing_person = _require_submitted_person_version(
            people[payload.directing_person.person_id],
            payload.directing_person.person_version_id,
        )

    expected_kind = release_rule_evidence_kind(payload.authority_basis_code)
    if expected_kind is None:
        raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})
    if payload.authority_basis_code == "guardian_record":
        if directing_person is None:
            raise HTTPException(409, detail={"code": "authority_basis_not_activatable"})
        _require_live_guardian_source(
            session,
            organization_id,
            child.family_id,
            directing_person,
        )
    evaluated_at = _transaction_cutoff(session)
    _reviewed_evidence(
        session,
        organization_id,
        child.family_id,
        {
            "rule": (
                payload.basis_evidence_id,
                payload.basis_evidence_assessment_id,
                expected_kind,
            )
        },
        actor_user_id=context.user.id,
        effective_until=payload.effective_until,
        evaluated_at=evaluated_at,
    )
    scope_person_id = payload.scope.person_id if payload.scope.kind == "specific_person" else None
    lane_scope = (
        ChildReleaseRule.scope_person_id.is_(None)
        if scope_person_id is None
        else ChildReleaseRule.scope_person_id == scope_person_id
    )
    overlap = session.scalar(
        select(ChildReleaseRule.id).where(
            ChildReleaseRule.organization_id == organization_id,
            ChildReleaseRule.child_id == child_id,
            ChildReleaseRule.rule_kind == payload.rule_kind,
            ChildReleaseRule.scope_kind == payload.scope.kind,
            lane_scope,
            ChildReleaseRule.revoked_at.is_(None),
            _overlaps(
                ChildReleaseRule.effective_from,
                ChildReleaseRule.effective_until,
                payload.effective_from,
                payload.effective_until,
            ),
        )
    )
    if overlap is not None:
        raise HTTPException(409, detail={"code": "release_rule_overlap"})
    require_current_family_authority_admin(session, context)

    rule_id = uuid4()
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=RULE_CREATE_COMMAND,
        target_type=RULE_TARGET_TYPE,
        target_id=rule_id,
        request_hash=request_hash,
        committed_version=1,
        action_route=f"/children/{child_id}?release_rule_id={rule_id}",
    )
    session.add(
        ChildReleaseRule(
            id=rule_id,
            organization_id=organization_id,
            family_id=child.family_id,
            child_id=child_id,
            rule_kind=payload.rule_kind,
            scope_kind=payload.scope.kind,
            scope_person_id=scope_person_id,
            directing_person_id=(
                payload.directing_person.person_id if payload.directing_person is not None else None
            ),
            directing_person_version_id=(
                payload.directing_person.person_version_id
                if payload.directing_person is not None
                else None
            ),
            authority_basis_code=payload.authority_basis_code,
            basis_evidence_id=payload.basis_evidence_id,
            basis_evidence_assessment_id=payload.basis_evidence_assessment_id,
            safe_explanation_code=SAFE_RULE_CODE[payload.rule_kind],
            confidential_reason=payload.confidential_reason,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            version=1,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush(session)
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.release.rule.created",
        entity_type=RULE_TARGET_TYPE,
        entity_id=rule_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _rule_command_response(
        session, context, child_id, command_receipt, replayed=False
    )


def revoke_release_rule(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    rule_id: UUID,
    payload: ReleaseRuleRevokeRequest,
) -> ReleaseRuleCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=RULE_REVOKE_COMMAND,
        target_type=RULE_TARGET_TYPE,
        target_scope=f"child:{child_id}:release_rule:{rule_id}",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != rule_id:
            _raise_receipt_incomplete(receipt)
        return _rule_command_response(session, context, child_id, receipt, replayed=True)
    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    value = session.scalar(
        select(ChildReleaseRule)
        .where(
            ChildReleaseRule.organization_id == organization_id,
            ChildReleaseRule.family_id == child.family_id,
            ChildReleaseRule.child_id == child_id,
            ChildReleaseRule.id == rule_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, detail="Release rule not found")
    require_version(value, payload.expected_version, RULE_TARGET_TYPE)
    if value.revoked_at is not None:
        raise HTTPException(409, detail={"code": "release_rule_already_revoked"})
    require_current_family_authority_admin(session, context)
    committed_version = value.version + 1
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=RULE_REVOKE_COMMAND,
        target_type=RULE_TARGET_TYPE,
        target_id=rule_id,
        request_hash=request_hash,
        committed_version=committed_version,
        action_route=f"/children/{child_id}?release_rule_id={rule_id}",
    )
    value.version = committed_version
    value.revoked_at = _transaction_cutoff(session)
    value.revoked_operation_id = payload.client_operation_id
    value.revocation_reason_code = payload.reason_code
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.release.rule.revoked",
        entity_type=RULE_TARGET_TYPE,
        entity_id=rule_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _rule_command_response(
        session, context, child_id, command_receipt, replayed=False
    )


def list_consent_policies(
    session: Session,
    context: BasicContext,
) -> list[ConsentPolicyVersionResponse]:
    _organization_lock(session, context.organization.id, read=True)
    require_current_family_authority_admin(session, context)
    values = list(
        session.scalars(
            select(ConsentPolicyVersion)
            .where(ConsentPolicyVersion.organization_id == context.organization.id)
            .order_by(
                ConsentPolicyVersion.purpose_code,
                ConsentPolicyVersion.version_number,
                ConsentPolicyVersion.id,
            )
        )
    )
    return [_policy_response(value) for value in values]


def publish_consent_policy(
    session: Session,
    context: BasicContext,
    payload: ConsentPolicyPublishRequest,
) -> ConsentPolicyCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=POLICY_PUBLISH_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_scope=f"organization:{organization_id}:consent_policy:create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        value = _load_policy_for_receipt(
            session,
            context,
            receipt,
            recheck_current_role=True,
        )
        return ConsentPolicyCommandResponse(
            resource=_policy_response(value),
            receipt=_receipt_response(receipt),
            replayed=True,
        )
    if payload.signer_authority_requirement == "specific_reviewed_authority":
        raise HTTPException(409, detail={"code": "consent_signer_requirement_not_activatable"})
    _organization_lock(session, organization_id, read=False)
    existing_version = session.scalar(
        select(ConsentPolicyVersion.id).where(
            ConsentPolicyVersion.organization_id == organization_id,
            ConsentPolicyVersion.purpose_code == payload.purpose_code,
            ConsentPolicyVersion.version_number == payload.version_number,
        )
    )
    if existing_version is not None:
        raise HTTPException(409, detail={"code": "consent_policy_version_exists"})
    overlap = session.scalar(
        select(ConsentPolicyVersion.id).where(
            ConsentPolicyVersion.organization_id == organization_id,
            ConsentPolicyVersion.purpose_code == payload.purpose_code,
            _overlaps(
                ConsentPolicyVersion.effective_from,
                ConsentPolicyVersion.effective_until,
                payload.effective_from,
                payload.effective_until,
            ),
        )
    )
    if overlap is not None:
        raise HTTPException(409, detail={"code": "consent_policy_overlap"})
    require_current_family_authority_admin(session, context)
    policy_id = uuid4()
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=POLICY_PUBLISH_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_id=policy_id,
        request_hash=request_hash,
        committed_version=payload.version_number,
        action_route=f"/consent-policies/{policy_id}",
    )
    value = ConsentPolicyVersion(
        id=policy_id,
        organization_id=organization_id,
        purpose_code=payload.purpose_code,
        version_number=payload.version_number,
        title=payload.title,
        content_text=payload.content_text,
        content_reference=f"/consent-policies/{policy_id}",
        content_sha256=hashlib.sha256(payload.content_text.encode("utf-8")).hexdigest(),
        signer_authority_requirement=payload.signer_authority_requirement,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        created_operation_id=payload.client_operation_id,
        published_at=_transaction_cutoff(session),
    )
    session.add(value)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="organization.consent.policy.published",
        entity_type="consent_policy",
        entity_id=policy_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    value = _load_policy_for_receipt(
        session,
        context,
        command_receipt,
        recheck_current_role=False,
    )
    return ConsentPolicyCommandResponse(
        resource=_policy_response(value),
        receipt=_receipt_response(command_receipt),
        replayed=False,
    )


def record_child_consent(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    payload: ChildConsentRecordRequest,
) -> ChildConsentCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=CONSENT_RECORD_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_scope=f"child:{child_id}:consent:create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        return _consent_command_response(session, context, child_id, receipt, replayed=True)
    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    people = _current_people(
        session,
        organization_id,
        child.family_id,
        {payload.signer.person_id},
    )
    signer = _require_submitted_person_version(
        people[payload.signer.person_id], payload.signer.person_version_id
    )
    policy = session.scalar(
        _consent_policy_for_decision_statement(
            organization_id,
            payload.policy_version_id,
            payload.purpose_code,
        )
    )
    if policy is None:
        raise HTTPException(404, detail="Consent policy not found")
    policy_from = _utc(policy.effective_from)
    policy_until = _utc(policy.effective_until)
    if (
        policy_from is None
        or policy_until is None
        or payload.effective_from < policy_from
        or payload.effective_until > policy_until
    ):
        raise HTTPException(409, detail={"code": "consent_policy_window_mismatch"})
    signer_rule = consent_signer_authority(policy.signer_authority_requirement)
    if signer_rule is None:
        raise HTTPException(409, detail={"code": "consent_signer_requirement_not_activatable"})
    expected_basis, expected_signer_evidence_kind = signer_rule
    if payload.signer.authority_basis != expected_basis:
        raise HTTPException(409, detail={"code": "consent_signer_requirement_mismatch"})
    if expected_basis == "guardian_record":
        try:
            _require_live_guardian_source(
                session,
                organization_id,
                child.family_id,
                signer,
            )
        except HTTPException:
            raise HTTPException(
                409, detail={"code": "consent_signer_requirement_mismatch"}
            ) from None
    if payload.scope.kind == "facility":
        facility = session.scalar(
            select(Facility.id).where(
                Facility.organization_id == organization_id,
                Facility.id == payload.scope.facility_id,
                Facility.status == "active",
            )
        )
        if facility is None:
            raise HTTPException(404, detail="Facility not found")
    evaluated_at = _transaction_cutoff(session)
    _reviewed_evidence(
        session,
        organization_id,
        child.family_id,
        {
            "decision": (
                payload.evidence_id,
                payload.evidence_assessment_id,
                CONSENT_DECISION_EVIDENCE_KIND,
            ),
            "signer_authority": (
                payload.signer.authority_evidence_id,
                payload.signer.authority_evidence_assessment_id,
                expected_signer_evidence_kind,
            ),
        },
        actor_user_id=context.user.id,
        effective_until=payload.effective_until,
        evaluated_at=evaluated_at,
    )
    overlap = session.scalar(
        select(ChildConsentDecision.id).where(
            ChildConsentDecision.organization_id == organization_id,
            ChildConsentDecision.child_id == child_id,
            ChildConsentDecision.purpose_code == payload.purpose_code,
            ChildConsentDecision.withdrawn_at.is_(None),
            _overlaps(
                ChildConsentDecision.effective_from,
                ChildConsentDecision.effective_until,
                payload.effective_from,
                payload.effective_until,
            ),
        )
    )
    if overlap is not None:
        raise HTTPException(409, detail={"code": "consent_decision_overlap"})
    require_current_family_authority_admin(session, context)
    decision_id = uuid4()
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=CONSENT_RECORD_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_id=decision_id,
        request_hash=request_hash,
        committed_version=1,
        action_route=f"/children/{child_id}?consent_id={decision_id}",
    )
    scope_facility_id = payload.scope.facility_id if payload.scope.kind == "facility" else None
    scope_reference = payload.scope.reference if payload.scope.kind == "named_activity" else None
    session.add(
        ChildConsentDecision(
            id=decision_id,
            organization_id=organization_id,
            family_id=child.family_id,
            child_id=child_id,
            purpose_code=payload.purpose_code,
            policy_version_id=payload.policy_version_id,
            signer_person_id=payload.signer.person_id,
            signer_person_version_id=payload.signer.person_version_id,
            signer_authority_basis=payload.signer.authority_basis,
            signer_authority_evidence_id=payload.signer.authority_evidence_id,
            signer_authority_evidence_assessment_id=(
                payload.signer.authority_evidence_assessment_id
            ),
            evidence_id=payload.evidence_id,
            evidence_assessment_id=payload.evidence_assessment_id,
            decision=payload.decision,
            scope_kind=payload.scope.kind,
            scope_facility_id=scope_facility_id,
            scope_reference=scope_reference,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
            version=1,
            created_operation_id=payload.client_operation_id,
        )
    )
    _flush(session)
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.consent.recorded",
        entity_type="consent",
        entity_id=decision_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _consent_command_response(
        session, context, child_id, command_receipt, replayed=False
    )


def withdraw_child_consent(
    session: Session,
    context: BasicContext,
    child_id: UUID,
    decision_id: UUID,
    payload: ChildConsentWithdrawRequest,
) -> ChildConsentCommandResponse:
    organization_id = context.organization.id
    request_hash, receipt = begin_command(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        client_operation_id=payload.client_operation_id,
        command_type=CONSENT_WITHDRAW_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_scope=f"child:{child_id}:consent:{decision_id}",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if receipt is not None:
        if receipt.target_id != decision_id:
            _raise_receipt_incomplete(receipt)
        return _consent_command_response(session, context, child_id, receipt, replayed=True)
    child, head = _lock_child_boundary(session, organization_id, child_id)
    _require_authority_revision(head, payload.expected_authority_revision)
    value = session.scalar(
        select(ChildConsentDecision)
        .where(
            ChildConsentDecision.organization_id == organization_id,
            ChildConsentDecision.family_id == child.family_id,
            ChildConsentDecision.child_id == child_id,
            ChildConsentDecision.id == decision_id,
        )
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, detail="Child consent decision not found")
    require_version(value, payload.expected_version, "consent")
    if value.withdrawn_at is not None:
        raise HTTPException(409, detail={"code": "consent_already_withdrawn"})
    require_current_family_authority_admin(session, context)
    committed_version = value.version + 1
    command_receipt = _record_receipt(
        session,
        context,
        operation_id=payload.client_operation_id,
        command_type=CONSENT_WITHDRAW_COMMAND,
        target_type=CONSENT_TARGET_TYPE,
        target_id=decision_id,
        request_hash=request_hash,
        committed_version=committed_version,
        action_route=f"/children/{child_id}?consent_id={decision_id}",
    )
    value.version = committed_version
    value.withdrawn_at = _transaction_cutoff(session)
    value.withdrawn_operation_id = payload.client_operation_id
    value.withdrawal_reason_code = payload.reason_code
    _advance_authority_head(session, child, head, payload.client_operation_id)
    _flush(session)
    audit(
        session,
        organization_id=organization_id,
        actor_user_id=context.user.id,
        action="child.consent.withdrawn",
        entity_type="consent",
        entity_id=decision_id,
        details={"operation_id": str(payload.client_operation_id)},
    )
    _commit(session, context)
    return _consent_command_response(
        session, context, child_id, command_receipt, replayed=False
    )
