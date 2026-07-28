"""Pure deterministic 0029B release-context composition.

This module performs no database, audit, notification, realtime, attendance, or
command work.  A future repository supplies one strictly validated input and
the caller maps :class:`ReleaseContextInconsistentError` to the bounded 409.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.basic.family_release_context_schemas import (
    RELEASE_CONTEXT_MAX_TTL_MS,
    RELEASE_CONTEXT_SCHEMA_VERSION,
    CanonicalReleaseRestriction,
    EligibleReleaseRecipient,
    ReleaseAuthorizationInput,
    ReleaseContextInput,
    ReleaseContextResponse,
    ReleaseRecipientPersonInput,
    ReleaseRuleInput,
    SupportingEvidenceInput,
)


class ReleaseContextCompositionError(ValueError):
    """Base class for bounded composer failures."""


class ReleaseContextInconsistentError(ReleaseContextCompositionError):
    """The repository projection contradicts a release-authority invariant."""


class ReleaseContextReevaluationRequired(ReleaseContextCompositionError):
    """A time boundary is too close to return a positive freshness lease."""


VERIFICATION_METHODS: dict[str, list[str]] = {
    "government_photo_id": ["government_photo_id"],
    "documented_familiarity": ["documented_familiarity"],
    "government_photo_id_or_documented_familiarity": [
        "government_photo_id",
        "documented_familiarity",
    ],
}
SAFE_CODE_BY_RULE_KIND = {
    "deny": "release_restricted",
    "supervised_only": "supervision_required",
    "named_recipient_only": "named_recipient_only",
    "manager_review": "manager_review_required",
}
RULE_BLOCKER_ORDER = ["release_restricted", "manager_review_required"]
RELATIONSHIP_LABELS = {
    "parent": "Parent",
    "legal_guardian": "Legal guardian",
    "foster_parent": "Foster parent",
    "grandparent": "Grandparent",
    "adult_sibling": "Adult sibling",
    "aunt_uncle": "Aunt or uncle",
    "family_friend": "Family friend",
    "caseworker": "Caseworker",
    "transport_provider": "Transport provider",
}


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_restriction_document_bytes(
    restrictions: Iterable[CanonicalReleaseRestriction],
) -> bytes:
    """Serialize restrictions using the exact B/C canonical byte contract."""

    ordered = sorted(restrictions, key=lambda item: str(item.rule_id))
    rule_ids = [item.rule_id for item in ordered]
    if len(rule_ids) != len(set(rule_ids)):
        raise ReleaseContextInconsistentError("duplicate canonical release restriction")
    document = {
        "decision_policy_version": RELEASE_CONTEXT_SCHEMA_VERSION,
        "rules": [
            {
                "effective_from": _canonical_timestamp(item.effective_from),
                "effective_until": _canonical_timestamp(item.effective_until),
                "rule_id": str(item.rule_id),
                "rule_kind": item.rule_kind,
                "rule_version": item.rule_version,
                "safe_explanation_code": item.safe_explanation_code,
                "scope_kind": item.scope_kind,
                "scope_person_id": (
                    None if item.scope_person_id is None else str(item.scope_person_id)
                ),
            }
            for item in ordered
        ],
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_restriction_digest(
    restrictions: Iterable[CanonicalReleaseRestriction],
) -> str:
    """Return lower-case SHA-256 for the exact canonical restriction bytes."""

    return hashlib.sha256(canonical_restriction_document_bytes(restrictions)).hexdigest()


def _evidence_is_current(evidence: SupportingEvidenceInput, evaluated_at: datetime) -> bool:
    if not evidence.scope_matches_authority_record:
        raise ReleaseContextInconsistentError("supporting evidence crosses authority scope")
    if evidence.bound_assessment_decision != "reviewed":
        raise ReleaseContextInconsistentError("activated row is not bound to a reviewed assessment")
    if not evidence.bound_assessment_is_latest:
        return False
    return evidence.evidence_expires_at is None or evidence.evidence_expires_at > evaluated_at


def _row_scope_is_exact(
    *,
    row_organization_id: UUID,
    row_family_id: UUID,
    row_child_id: UUID,
    context: ReleaseContextInput,
) -> bool:
    return (
        row_organization_id == context.organization_id
        and row_family_id == context.family_id
        and row_child_id == context.child_id
    )


def _is_effective(row: ReleaseAuthorizationInput | ReleaseRuleInput, at: datetime) -> bool:
    return row.effective_from <= at < row.effective_until


def _validate_people(
    context: ReleaseContextInput,
) -> dict[UUID, ReleaseRecipientPersonInput]:
    people: dict[UUID, ReleaseRecipientPersonInput] = {}
    for person in context.people:
        if (
            person.organization_id != context.organization_id
            or person.family_id != context.family_id
        ):
            raise ReleaseContextInconsistentError("recipient person crosses authority scope")
        if person.person_id in people:
            raise ReleaseContextInconsistentError("duplicate recipient person projection")
        version_ids = [version.person_version_id for version in person.current_versions]
        if len(version_ids) != len(set(version_ids)):
            raise ReleaseContextInconsistentError("duplicate current person version projection")
        if len(person.current_versions) > 1:
            raise ReleaseContextInconsistentError(
                "recipient has incoherent current person versions"
            )
        if person.status == "active" and len(person.current_versions) != 1:
            raise ReleaseContextInconsistentError(
                "active recipient has no coherent current version"
            )
        people[person.person_id] = person
    return people


def _validate_rule_shape(rule: ReleaseRuleInput) -> None:
    if rule.safe_explanation_code != SAFE_CODE_BY_RULE_KIND[rule.rule_kind]:
        raise ReleaseContextInconsistentError("release rule has a malformed safe-code pair")


def _current_rows(
    context: ReleaseContextInput,
) -> tuple[list[ReleaseAuthorizationInput], list[ReleaseRuleInput]]:
    current_authorizations: list[ReleaseAuthorizationInput] = []
    seen_authorization_ids: set[UUID] = set()
    for authorization in context.authorizations:
        if not _row_scope_is_exact(
            row_organization_id=authorization.organization_id,
            row_family_id=authorization.family_id,
            row_child_id=authorization.child_id,
            context=context,
        ):
            raise ReleaseContextInconsistentError("release authorization crosses authority scope")
        if authorization.authorization_id in seen_authorization_ids:
            raise ReleaseContextInconsistentError("duplicate release authorization projection")
        seen_authorization_ids.add(authorization.authorization_id)
        evidence_current = _evidence_is_current(
            authorization.supporting_evidence, context.evaluated_at
        )
        if authorization.revoked_at is None and evidence_current:
            current_authorizations.append(authorization)

    current_rules: list[ReleaseRuleInput] = []
    seen_rule_ids: set[UUID] = set()
    for rule in context.rules:
        if not _row_scope_is_exact(
            row_organization_id=rule.organization_id,
            row_family_id=rule.family_id,
            row_child_id=rule.child_id,
            context=context,
        ):
            raise ReleaseContextInconsistentError("release rule crosses authority scope")
        if rule.rule_id in seen_rule_ids:
            raise ReleaseContextInconsistentError("duplicate release rule projection")
        seen_rule_ids.add(rule.rule_id)
        _validate_rule_shape(rule)
        evidence_current = _evidence_is_current(rule.supporting_evidence, context.evaluated_at)
        if rule.revoked_at is None and evidence_current:
            current_rules.append(rule)
    return current_authorizations, current_rules


def _freshness(
    context: ReleaseContextInput,
    authorizations: list[ReleaseAuthorizationInput],
    rules: list[ReleaseRuleInput],
) -> tuple[datetime, int]:
    cap = context.evaluated_at + timedelta(milliseconds=RELEASE_CONTEXT_MAX_TTL_MS)
    boundaries = [cap]
    for row in [*authorizations, *rules]:
        if row.effective_from > context.evaluated_at:
            boundaries.append(row.effective_from)
        if row.effective_until > context.evaluated_at:
            boundaries.append(row.effective_until)
        evidence_expiry = row.supporting_evidence.evidence_expires_at
        if evidence_expiry is not None and evidence_expiry > context.evaluated_at:
            boundaries.append(evidence_expiry)
    expires_at = min(boundaries)
    fresh_for_ms = (expires_at - context.evaluated_at) // timedelta(milliseconds=1)
    if fresh_for_ms <= 0:
        raise ReleaseContextReevaluationRequired(
            "release context crossed an immediate time boundary"
        )
    return expires_at, fresh_for_ms


def _canonical_rules(
    active_rules: list[ReleaseRuleInput],
) -> list[CanonicalReleaseRestriction]:
    return [
        CanonicalReleaseRestriction(
            effective_from=rule.effective_from,
            effective_until=rule.effective_until,
            rule_id=rule.rule_id,
            rule_kind=rule.rule_kind,
            rule_version=rule.rule_version,
            safe_explanation_code=rule.safe_explanation_code,
            scope_kind=rule.scope_kind,
            scope_person_id=rule.scope_person_id,
        )
        for rule in active_rules
    ]


def _rule_blockers(rules: Iterable[ReleaseRuleInput]) -> list[str]:
    present = {rule.safe_explanation_code for rule in rules}
    return [code for code in RULE_BLOCKER_ORDER if code in present]


def _eligible_recipient(
    authorization: ReleaseAuthorizationInput,
    person: ReleaseRecipientPersonInput,
) -> EligibleReleaseRecipient:
    version = person.current_versions[0]
    display_name = " ".join(
        item for item in (version.first_name, version.middle_name, version.last_name) if item
    )
    relationship_label = (
        version.relationship_detail
        if version.relationship_kind == "other"
        else RELATIONSHIP_LABELS[version.relationship_kind]
    )
    return EligibleReleaseRecipient(
        recipient_person_id=person.person_id,
        recipient_person_version_id=version.person_version_id,
        display_name=display_name,
        preferred_name=version.preferred_name,
        relationship_label=relationship_label,
        authorization_id=authorization.authorization_id,
        authorization_version=authorization.authorization_version,
        verification_policy_code=authorization.verification_policy_code,
        verification_methods=VERIFICATION_METHODS[authorization.verification_policy_code],
    )


def _visible_recipient_identity(
    recipient: EligibleReleaseRecipient,
) -> tuple[str, str, str]:
    """Return the case-insensitive identity exactly available to staff.

    Opaque person IDs cannot safely distinguish two rows that present the same
    name, preferred name, and relationship.  That data needs administrative
    review before a normal release flow can ask staff to select either row.
    """

    return tuple(
        unicodedata.normalize("NFKC", value or "").casefold()
        for value in (
            recipient.display_name,
            recipient.preferred_name,
            recipient.relationship_label,
        )
    )


def compose_release_context(context: ReleaseContextInput) -> ReleaseContextResponse:
    """Compose one deterministic, expiring, read-only educator projection."""

    people = _validate_people(context)
    current_authorizations, current_rules = _current_rows(context)
    if context.authority_revision == 0 and (context.authorizations or context.rules):
        raise ReleaseContextInconsistentError("authority rows exist without a child authority head")

    expires_at, fresh_for_ms = _freshness(context, current_authorizations, current_rules)
    active_rules = [row for row in current_rules if _is_effective(row, context.evaluated_at)]
    for rule in active_rules:
        if rule.rule_kind not in {"deny", "manager_review"}:
            raise ReleaseContextInconsistentError("release rule kind is not activatable in B")
    restriction_digest = canonical_restriction_digest(_canonical_rules(active_rules))

    response_values = {
        "organization_id": context.organization_id,
        "facility_id": context.facility_id,
        "room_id": context.room_id,
        "child_id": context.child_id,
        "attendance_day_id": context.attendance_day_id,
        "attendance_interval_id": context.attendance_interval_id,
        "staff_shift_id": context.staff_shift_id,
        "evaluated_at": context.evaluated_at,
        "expires_at": expires_at,
        "fresh_for_ms": fresh_for_ms,
        "authority_revision": context.authority_revision,
        "restriction_digest_sha256": restriction_digest,
    }
    if context.authority_revision == 0:
        return ReleaseContextResponse(
            **response_values,
            decision="blocked",
            blockers=["authority_not_reviewed"],
            eligible_recipients=[],
        )

    all_recipient_rules = [
        rule for rule in active_rules if rule.scope_kind == "all_recipients"
    ]
    if all_recipient_rules:
        return ReleaseContextResponse(
            **response_values,
            decision="blocked",
            blockers=_rule_blockers(all_recipient_rules),
            eligible_recipients=[],
        )

    active_authorizations: list[ReleaseAuthorizationInput] = []
    authorization_by_recipient: dict[UUID, ReleaseAuthorizationInput] = {}
    for authorization in current_authorizations:
        person = people.get(authorization.recipient_person_id)
        if person is None:
            raise ReleaseContextInconsistentError("release authorization has no recipient person")
        if not _is_effective(authorization, context.evaluated_at):
            continue
        if authorization.recipient_person_id in authorization_by_recipient:
            raise ReleaseContextInconsistentError(
                "recipient has duplicate active release authorizations"
            )
        authorization_by_recipient[authorization.recipient_person_id] = authorization
        if person.status == "retired":
            continue
        active_authorizations.append(authorization)

    specific_rules_by_person: dict[UUID, list[ReleaseRuleInput]] = {}
    for rule in active_rules:
        if rule.scope_person_id is not None:
            specific_rules_by_person.setdefault(rule.scope_person_id, []).append(rule)

    after_rules = [
        authorization
        for authorization in active_authorizations
        if authorization.recipient_person_id not in specific_rules_by_person
    ]
    executable = [
        authorization
        for authorization in after_rules
        if authorization.verification_policy_code in VERIFICATION_METHODS
    ]
    if executable:
        recipients = [
            _eligible_recipient(authorization, people[authorization.recipient_person_id])
            for authorization in executable
        ]
        recipients.sort(key=lambda item: str(item.recipient_person_id))
        visible_identities = [
            _visible_recipient_identity(recipient) for recipient in recipients
        ]
        if len(visible_identities) != len(set(visible_identities)):
            return ReleaseContextResponse(
                **response_values,
                decision="blocked",
                blockers=["recipient_identity_ambiguous"],
                eligible_recipients=[],
            )
        return ReleaseContextResponse(
            **response_values,
            decision="recipient_selection_available",
            blockers=[],
            eligible_recipients=recipients,
        )

    if after_rules:
        return ReleaseContextResponse(
            **response_values,
            decision="blocked",
            blockers=["verification_workflow_unavailable"],
            eligible_recipients=[],
        )
    if active_authorizations:
        affecting_rules = [
            rule
            for authorization in active_authorizations
            for rule in specific_rules_by_person.get(authorization.recipient_person_id, [])
        ]
        return ReleaseContextResponse(
            **response_values,
            decision="blocked",
            blockers=_rule_blockers(affecting_rules),
            eligible_recipients=[],
        )
    return ReleaseContextResponse(
        **response_values,
        decision="blocked",
        blockers=["no_active_release_authorization"],
        eligible_recipients=[],
    )
