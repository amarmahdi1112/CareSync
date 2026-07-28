"""Pure contract and composition proof for the 0029B release context."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.basic.family_release_context import (
    ReleaseContextInconsistentError,
    ReleaseContextReevaluationRequired,
    canonical_restriction_digest,
    canonical_restriction_document_bytes,
    compose_release_context,
)
from app.basic.family_release_context_schemas import (
    CanonicalReleaseRestriction,
    ReleaseContextInput,
    ReleaseContextResponse,
)

NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _evidence(**overrides) -> dict:
    values = {
        "bound_assessment_decision": "reviewed",
        "bound_assessment_is_latest": True,
        "evidence_expires_at": NOW + DAY,
        "scope_matches_authority_record": True,
    }
    values.update(overrides)
    return values


def _version(version_id: int = 20, **overrides) -> dict:
    values = {
        "person_version_id": _id(version_id),
        "first_name": "  Amal  ",
        "middle_name": "  Noor ",
        "last_name": "  Ali  ",
        "preferred_name": " Amy ",
        "relationship_kind": "grandparent",
        "relationship_detail": None,
    }
    values.update(overrides)
    return values


def _person(person_id: int = 10, **overrides) -> dict:
    values = {
        "organization_id": _id(1),
        "family_id": _id(2),
        "person_id": _id(person_id),
        "status": "active",
        "current_versions": [_version(person_id + 10)],
    }
    values.update(overrides)
    return values


def _authorization(authorization_id: int = 30, person_id: int = 10, **overrides) -> dict:
    values = {
        "organization_id": _id(1),
        "family_id": _id(2),
        "child_id": _id(6),
        "authorization_id": _id(authorization_id),
        "authorization_version": 1,
        "recipient_person_id": _id(person_id),
        "verification_policy_code": "government_photo_id",
        "supporting_evidence": _evidence(),
        "effective_from": NOW - DAY,
        "effective_until": NOW + DAY,
        "revoked_at": None,
    }
    values.update(overrides)
    return values


def _rule(
    rule_id: int = 40,
    *,
    kind: str = "deny",
    scope: str = "specific_person",
    person_id: int | None = 10,
    **overrides,
) -> dict:
    values = {
        "organization_id": _id(1),
        "family_id": _id(2),
        "child_id": _id(6),
        "rule_id": _id(rule_id),
        "rule_version": 1,
        "rule_kind": kind,
        "scope_kind": scope,
        "scope_person_id": None if scope == "all_recipients" else _id(person_id or 10),
        "safe_explanation_code": {
            "deny": "release_restricted",
            "supervised_only": "supervision_required",
            "named_recipient_only": "named_recipient_only",
            "manager_review": "manager_review_required",
        }[kind],
        "supporting_evidence": _evidence(),
        "effective_from": NOW - DAY,
        "effective_until": NOW + DAY,
        "revoked_at": None,
    }
    values.update(overrides)
    return values


def _context(**overrides) -> ReleaseContextInput:
    values = {
        "input_schema_version": "release-context-input-v1",
        "organization_id": _id(1),
        "family_id": _id(2),
        "facility_id": _id(3),
        "room_id": _id(4),
        "child_id": _id(6),
        "attendance_day_id": _id(7),
        "attendance_interval_id": _id(8),
        "staff_shift_id": _id(9),
        "evaluated_at": NOW,
        "authority_revision": 7,
        "people": [_person()],
        "authorizations": [_authorization()],
        "rules": [],
    }
    values.update(overrides)
    return ReleaseContextInput.model_validate(values)


def _canonical(**overrides) -> CanonicalReleaseRestriction:
    values = {
        "effective_from": datetime(2026, 7, 18, 10, tzinfo=UTC),
        "effective_until": datetime(2026, 7, 19, 10, tzinfo=UTC),
        "rule_id": _id(0),
        "rule_kind": "deny",
        "rule_version": 1,
        "safe_explanation_code": "release_restricted",
        "scope_kind": "specific_person",
        "scope_person_id": _id(0),
    }
    values.update(overrides)
    return CanonicalReleaseRestriction.model_validate(values)


def test_public_and_internal_shapes_forbid_extras_at_every_level() -> None:
    top = _context().model_dump(mode="python")
    top["unexpected"] = True
    with pytest.raises(ValidationError):
        ReleaseContextInput.model_validate(top)

    nested = _context().model_dump(mode="python")
    nested["authorizations"][0]["supporting_evidence"]["evidence_id"] = str(_id(99))
    with pytest.raises(ValidationError):
        ReleaseContextInput.model_validate(nested)

    response = compose_release_context(_context()).model_dump(mode="python")
    response["family_id"] = _id(2)
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(response)

    response = compose_release_context(_context()).model_dump(mode="python")
    response["eligible_recipients"][0]["phone"] = "+1 780 555 0100"
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(response)


def test_available_projection_is_minimum_necessary_normalized_and_canonically_sorted() -> None:
    people = [
        _person(
            12,
            current_versions=[
                _version(
                    22,
                    first_name=" Zain ",
                    middle_name=None,
                    last_name=" Noor ",
                    preferred_name=None,
                    relationship_kind="other",
                    relationship_detail=" School  transport ",
                )
            ],
        ),
        _person(),
    ]
    authorizations = [
        _authorization(32, 12, verification_policy_code="documented_familiarity"),
        _authorization(30, 10),
    ]
    result = compose_release_context(_context(people=people, authorizations=authorizations))

    assert result.decision == "recipient_selection_available"
    assert result.blockers == []
    assert [item.recipient_person_id for item in result.eligible_recipients] == [_id(10), _id(12)]
    first, second = result.eligible_recipients
    assert first.display_name == "Amal Noor Ali"
    assert first.preferred_name == "Amy"
    assert first.relationship_label == "Grandparent"
    assert second.display_name == "Zain Noor"
    assert second.relationship_label == "School transport"
    assert "family_id" not in result.model_dump()
    serialized = result.model_dump_json()
    for forbidden in ("phone", "email", "evidence", "grantor", "confidential", "storage"):
        assert forbidden not in serialized.lower()
    assert '"evaluated_at":"2026-07-18T12:00:00.000000Z"' in serialized
    assert str(_id(10)) in serialized


def test_visibly_identical_recipients_require_administrative_review() -> None:
    people = [
        _person(),
        _person(
            12,
            current_versions=[
                _version(
                    22,
                    first_name="amal",
                    middle_name="NOOR",
                    last_name="ali",
                    preferred_name="amy",
                )
            ],
        ),
    ]
    result = compose_release_context(
        _context(
            people=people,
            authorizations=[_authorization(30, 10), _authorization(31, 12)],
        )
    )

    assert result.decision == "blocked"
    assert result.blockers == ["recipient_identity_ambiguous"]
    assert result.eligible_recipients == []


@pytest.mark.parametrize(
    ("policy", "methods", "available"),
    [
        ("government_photo_id", ["government_photo_id"], True),
        ("documented_familiarity", ["documented_familiarity"], True),
        (
            "government_photo_id_or_documented_familiarity",
            ["government_photo_id", "documented_familiarity"],
            True,
        ),
        ("government_photo_id_and_secondary_check", None, False),
    ],
)
def test_verification_policy_projection_is_exact_and_secondary_fails_closed(
    policy: str,
    methods: list[str] | None,
    available: bool,
) -> None:
    result = compose_release_context(
        _context(authorizations=[_authorization(verification_policy_code=policy)])
    )
    if available:
        assert result.decision == "recipient_selection_available"
        assert result.eligible_recipients[0].verification_methods == methods
    else:
        assert result.decision == "blocked"
        assert result.blockers == ["verification_workflow_unavailable"]
        assert result.eligible_recipients == []


@pytest.mark.parametrize(
    "authorization_overrides",
    [
        {"revoked_at": NOW - timedelta(seconds=1)},
        {"effective_from": NOW + DAY, "effective_until": NOW + 2 * DAY},
        {"effective_from": NOW - 2 * DAY, "effective_until": NOW},
        {"supporting_evidence": _evidence(bound_assessment_is_latest=False)},
        {"supporting_evidence": _evidence(evidence_expires_at=NOW)},
    ],
)
def test_noncurrent_authorizations_do_not_become_permission(authorization_overrides: dict) -> None:
    result = compose_release_context(
        _context(authorizations=[_authorization(**authorization_overrides)])
    )
    assert result.decision == "blocked"
    assert result.blockers == ["no_active_release_authorization"]


def test_retired_recipient_is_not_eligible() -> None:
    result = compose_release_context(_context(people=[_person(status="retired")]))
    assert result.blockers == ["no_active_release_authorization"]


@pytest.mark.parametrize(
    "context",
    [
        lambda: _context(people=[_person(current_versions=[])]),
        lambda: _context(people=[_person(current_versions=[_version(20), _version(21)])]),
        lambda: _context(
            authorizations=[
                _authorization(30),
                _authorization(31),
            ]
        ),
        lambda: _context(
            authorizations=[
                _authorization(
                    supporting_evidence=_evidence(bound_assessment_decision="rejected")
                )
            ]
        ),
        lambda: _context(
            authorizations=[
                _authorization(
                    supporting_evidence=_evidence(scope_matches_authority_record=False)
                )
            ]
        ),
        lambda: _context(authorizations=[_authorization(family_id=_id(999))]),
    ],
)
def test_structural_authority_contradictions_fail_closed(context) -> None:
    with pytest.raises(ReleaseContextInconsistentError):
        compose_release_context(context())


def test_missing_head_has_one_exact_blocker_and_rows_without_head_are_inconsistent() -> None:
    result = compose_release_context(
        _context(authority_revision=0, people=[], authorizations=[], rules=[])
    )
    assert result.decision == "blocked"
    assert result.blockers == ["authority_not_reviewed"]
    assert result.restriction_digest_sha256 == (
        "ddc97498440b29337c51557fdfba1503074cc332bdd69538d3603b02238e342b"
    )
    with pytest.raises(ReleaseContextInconsistentError):
        compose_release_context(_context(authority_revision=0))


@pytest.mark.parametrize(
    ("kind", "expected_blocker"),
    [("deny", "release_restricted"), ("manager_review", "manager_review_required")],
)
@pytest.mark.parametrize("scope", ["all_recipients", "specific_person"])
def test_every_activatable_rule_kind_and_scope_blocks_normal_selection(
    kind: str,
    expected_blocker: str,
    scope: str,
) -> None:
    result = compose_release_context(_context(rules=[_rule(kind=kind, scope=scope)]))
    assert result.decision == "blocked"
    assert result.blockers == [expected_blocker]
    assert result.eligible_recipients == []


def test_specific_rule_only_filters_its_person_and_all_rules_use_safe_precedence() -> None:
    result = compose_release_context(
        _context(rules=[_rule(person_id=99)])
    )
    assert result.decision == "recipient_selection_available"

    result = compose_release_context(
        _context(
            rules=[
                _rule(42, kind="manager_review", scope="all_recipients"),
                _rule(41, kind="deny", scope="all_recipients"),
            ]
        )
    )
    assert result.blockers == ["release_restricted", "manager_review_required"]


def test_rule_for_person_without_a_grant_still_binds_the_restriction_digest() -> None:
    unrestricted = compose_release_context(_context())
    restricted = compose_release_context(_context(rules=[_rule(person_id=99)]))
    assert restricted.decision == "recipient_selection_available"
    assert restricted.restriction_digest_sha256 != unrestricted.restriction_digest_sha256


@pytest.mark.parametrize("kind", ["supervised_only", "named_recipient_only"])
def test_unsupported_effective_rule_material_fails_closed(kind: str) -> None:
    with pytest.raises(ReleaseContextInconsistentError):
        compose_release_context(_context(rules=[_rule(kind=kind)]))


def test_canonical_digest_has_fixed_empty_one_and_multi_rule_vectors() -> None:
    assert canonical_restriction_digest([]) == (
        "ddc97498440b29337c51557fdfba1503074cc332bdd69538d3603b02238e342b"
    )
    one = _canonical()
    expected_bytes = (
        b'{"decision_policy_version":"release-context-v1","rules":['
        b'{"effective_from":"2026-07-18T10:00:00.000000Z",'
        b'"effective_until":"2026-07-19T10:00:00.000000Z",'
        b'"rule_id":"00000000-0000-0000-0000-000000000000","rule_kind":"deny",'
        b'"rule_version":1,"safe_explanation_code":"release_restricted",'
        b'"scope_kind":"specific_person",'
        b'"scope_person_id":"00000000-0000-0000-0000-000000000000"}]}'
    )
    assert canonical_restriction_document_bytes([one]) == expected_bytes
    assert canonical_restriction_digest([one]) == (
        "1dcc5ebe47600ed2008aded0b34b8237ab68c140c2837c9131385b17cae2bf1e"
    )

    second = _canonical(
        rule_id=_id(2),
        rule_kind="manager_review",
        safe_explanation_code="manager_review_required",
        rule_version=3,
        scope_kind="all_recipients",
        scope_person_id=None,
        effective_from=datetime(2026, 7, 18, 11, 0, 0, 123456, tzinfo=UTC),
        effective_until=datetime(2026, 7, 20, 10, 0, 0, 654321, tzinfo=UTC),
    )
    first = _canonical(rule_id=_id(1), rule_version=2, scope_person_id=_id(10))
    expected = "7f577ee643cb875b8cd00c3e2aebbd89cbf15335ddb0a7b5b46c57f3e9e0a2a0"
    assert canonical_restriction_digest([second, first]) == expected
    assert canonical_restriction_digest([first, second]) == expected


def test_digest_changes_for_every_independently_variable_canonical_field() -> None:
    base = _canonical(rule_id=_id(1), scope_person_id=_id(10))
    variants = [
        _canonical(
            rule_id=_id(1),
            scope_person_id=_id(10),
            effective_from=base.effective_from + timedelta(microseconds=1),
        ),
        _canonical(
            rule_id=_id(1),
            scope_person_id=_id(10),
            effective_until=base.effective_until + timedelta(microseconds=1),
        ),
        _canonical(rule_id=_id(2), scope_person_id=_id(10)),
        _canonical(rule_id=_id(1), rule_version=2, scope_person_id=_id(10)),
        _canonical(rule_id=_id(1), scope_person_id=_id(11)),
        _canonical(
            rule_id=_id(1),
            rule_kind="manager_review",
            safe_explanation_code="manager_review_required",
            scope_kind="all_recipients",
            scope_person_id=None,
        ),
    ]
    base_digest = canonical_restriction_digest([base])
    assert all(canonical_restriction_digest([variant]) != base_digest for variant in variants)


def test_canonical_boundary_rejects_confidential_fields_and_duplicate_rules() -> None:
    values = _canonical().model_dump(mode="python")
    values["confidential_reason"] = "must never enter the digest"
    with pytest.raises(ValidationError):
        CanonicalReleaseRestriction.model_validate(values)
    with pytest.raises(ReleaseContextInconsistentError):
        canonical_restriction_digest([_canonical(), _canonical()])


@pytest.mark.parametrize(
    ("authorizations", "rules", "expected_ms"),
    [
        ([_authorization(effective_until=NOW + timedelta(seconds=10))], [], 10_000),
        (
            [
                _authorization(
                    effective_from=NOW + timedelta(seconds=5, microseconds=123456),
                    effective_until=NOW + DAY,
                )
            ],
            [],
            5_123,
        ),
        (
            [_authorization()],
            [_rule(effective_from=NOW + timedelta(seconds=4), effective_until=NOW + DAY)],
            4_000,
        ),
        (
            [
                _authorization(
                    supporting_evidence=_evidence(
                        evidence_expires_at=NOW + timedelta(seconds=3, microseconds=500000)
                    )
                )
            ],
            [],
            3_500,
        ),
    ],
)
def test_freshness_shortens_to_the_next_future_boundary(
    authorizations: list[dict],
    rules: list[dict],
    expected_ms: int,
) -> None:
    result = compose_release_context(_context(authorizations=authorizations, rules=rules))
    assert result.fresh_for_ms == expected_ms
    assert int((result.expires_at - NOW).total_seconds() * 1000) == expected_ms


def test_freshness_is_capped_at_thirty_seconds_and_submillisecond_lease_reevaluates() -> None:
    result = compose_release_context(_context())
    assert result.fresh_for_ms == 30_000
    assert result.expires_at == NOW + timedelta(seconds=30)

    with pytest.raises(ReleaseContextReevaluationRequired):
        compose_release_context(
            _context(
                authorizations=[
                    _authorization(
                        effective_from=NOW + timedelta(microseconds=500),
                        effective_until=NOW + DAY,
                    )
                ]
            )
        )


def test_half_open_effective_boundaries_are_exact() -> None:
    at_start = compose_release_context(
        _context(authorizations=[_authorization(effective_from=NOW, effective_until=NOW + DAY)])
    )
    assert at_start.decision == "recipient_selection_available"

    at_end = compose_release_context(
        _context(authorizations=[_authorization(effective_from=NOW - DAY, effective_until=NOW)])
    )
    assert at_end.blockers == ["no_active_release_authorization"]


def test_public_response_rejects_noncanonical_decision_and_freshness_shapes() -> None:
    available = compose_release_context(_context()).model_dump(mode="python")
    available["blockers"] = ["no_active_release_authorization"]
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(available)

    available = compose_release_context(_context()).model_dump(mode="python")
    available["fresh_for_ms"] = 29_999
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(available)

    available = compose_release_context(_context()).model_dump(mode="python")
    available["decision"] = "blocked"
    available["eligible_recipients"] = []
    available["blockers"] = ["authority_not_reviewed"]
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(available)

    available = compose_release_context(_context()).model_dump(mode="python")
    available["decision"] = "blocked"
    available["eligible_recipients"] = []
    available["blockers"] = ["release_restricted", "verification_workflow_unavailable"]
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(available)

    available = compose_release_context(_context()).model_dump(mode="python")
    duplicate_visible = dict(available["eligible_recipients"][0])
    duplicate_visible.update(
        recipient_person_id=_id(12),
        recipient_person_version_id=_id(22),
        authorization_id=_id(32),
    )
    available["eligible_recipients"].append(duplicate_visible)
    with pytest.raises(ValidationError):
        ReleaseContextResponse.model_validate(available)

    blocked = compose_release_context(
        _context(authorizations=[_authorization(revoked_at=NOW)])
    ).model_dump(mode="json")
    assert json.loads(json.dumps(blocked))["eligible_recipients"] == []
