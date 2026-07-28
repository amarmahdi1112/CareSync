"""Read-only, dependency-ordered setup planning for the canonical billing ledger.

The planner deliberately stops at command intent.  It never prepares or executes
commands, activates billing, creates ledger records, or contacts a provider.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.basic.billing_projections import build_billing_readiness
from app.basic.billing_schemas import (
    BillingReadinessBatchAffectedChild,
    BillingReadinessBatchPayerOption,
    BillingReadinessBatchPlanGroup,
    BillingReadinessBatchRatePlanOption,
    BillingReadinessBatchWave,
    BillingReadinessResponse,
)
from app.basic.models import (
    BillingAccountPayerVersion,
    BillingRatePlan,
    BillingRatePlanVersion,
    BillingSandboxSourceAttestation,
    Child,
    Enrollment,
    Facility,
    Guardian,
    Program,
)

MAX_BATCH_OPTIONS = 50
MAX_AFFECTED_CHILD_PREVIEW = 25


@dataclass(frozen=True)
class BillingReadinessBatchSnapshot:
    readiness: BillingReadinessResponse
    groups: tuple[BillingReadinessBatchPlanGroup, ...]
    snapshot_token: str
    reserved_rate_codes: frozenset[str]
    membership_search_index: dict[str, str]


def _latest_by_parent(rows: list[Any], parent_attribute: str) -> dict[UUID, Any]:
    latest: dict[UUID, Any] = {}
    for row in rows:
        parent_id = getattr(row, parent_attribute)
        current = latest.get(parent_id)
        if current is None or (row.version_number, str(row.id)) > (
            current.version_number,
            str(current.id),
        ):
            latest[parent_id] = row
    return latest


def _group_id(
    organization_id: UUID,
    wave: BillingReadinessBatchWave,
    *scope: object,
) -> str:
    canonical_scope = "|".join("" if value is None else str(value) for value in scope)
    return hashlib.sha256(
        f"0040|{organization_id}|{wave}|{canonical_scope}".encode()
    ).hexdigest()


def _subject(item, *, family_name: str | None = None) -> BillingReadinessBatchAffectedChild:
    return BillingReadinessBatchAffectedChild(
        family_id=item.family_id,
        family_name=family_name or item.family_name,
        child_id=item.child_id,
        child_name=item.child_name,
        enrollment_id=item.enrollment_id,
    )


def _affected_facts(items) -> tuple[int, str, list[BillingReadinessBatchAffectedChild], bool]:
    ordered = sorted(
        items,
        key=lambda item: (
            str(item.family_id),
            str(item.child_id),
            str(item.enrollment_id or ""),
        ),
    )
    canonical = [
        {
            "family_id": str(item.family_id),
            "family_name": item.family_name,
            "child_id": str(item.child_id),
            "child_name": item.child_name,
            "enrollment_id": (
                str(item.enrollment_id) if item.enrollment_id is not None else None
            ),
        }
        for item in ordered
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    preview = [_subject(item) for item in ordered[:MAX_AFFECTED_CHILD_PREVIEW]]
    return len(ordered), digest, preview, len(ordered) > len(preview)


def _full_membership_search_text(items) -> str:
    return "\n".join(
        value
        for item in items
        for value in (item.family_name, item.child_name)
    ).casefold()


def _manual_review_group(
    organization_id: UUID,
    item,
    *,
    facility_names: dict[UUID, str],
    programs: dict[UUID, Program],
    age_groups: dict[UUID, str | None],
    block_code: str | None = None,
) -> BillingReadinessBatchPlanGroup:
    program = programs.get(item.program_id) if item.program_id is not None else None
    reason = block_code or item.reason_codes[0]
    affected_count, membership_digest, subjects, truncated = _affected_facts([item])
    return BillingReadinessBatchPlanGroup(
        group_id=_group_id(
            organization_id,
            "manual_review",
            item.family_id,
            item.child_id,
            item.enrollment_id,
            reason,
            membership_digest,
        ),
        wave="manual_review",
        readiness_status=item.status,
        reason_codes=item.reason_codes,
        actionable=False,
        block_code=reason,
        suggested_command_type=None,
        family_id=item.family_id,
        family_name=item.family_name,
        billing_account_id=item.billing_account_id,
        latest_payer_version_id=None,
        latest_payer_version_number=None,
        facility_id=item.facility_id,
        facility_name=facility_names.get(item.facility_id),
        program_id=item.program_id,
        program_name=program.name if program is not None else None,
        program_type=program.program_type if program is not None else None,
        age_group=age_groups.get(item.child_id),
        rate_plan_id=item.rate_plan_id,
        rate_plan_version_id=item.rate_plan_version_id,
        affected_count=affected_count,
        affected_membership_digest=membership_digest,
        affected_children=subjects,
        affected_children_truncated=truncated,
        payer_options=[],
        rate_plan_options=[],
        action_path=item.action_path,
    )


def _supporting_facts(
    session: Session,
    *,
    organization_id: UUID,
    readiness: BillingReadinessResponse,
    source_attestations_required: bool,
) -> dict[str, Any]:
    family_ids = {item.family_id for item in readiness.items}
    child_ids = {item.child_id for item in readiness.items}
    account_ids = {
        item.billing_account_id
        for item in readiness.items
        if item.billing_account_id is not None
    }
    facility_ids = {
        item.facility_id for item in readiness.items if item.facility_id is not None
    }
    program_ids = {item.program_id for item in readiness.items if item.program_id is not None}
    enrollment_ids = {
        item.enrollment_id for item in readiness.items if item.enrollment_id is not None
    }

    children = {
        child.id: child
        for child in session.scalars(
            select(Child)
            .where(
                Child.organization_id == organization_id,
                Child.id.in_(child_ids),
            )
            .order_by(Child.id)
        )
    }
    guardian_rows = list(
        session.scalars(
            select(Guardian)
            .where(
                Guardian.organization_id == organization_id,
                Guardian.family_id.in_(family_ids),
                Guardian.retired_at.is_(None),
            )
            .order_by(
                Guardian.family_id,
                Guardian.is_primary.desc(),
                Guardian.last_name,
                Guardian.first_name,
                Guardian.id,
            )
        )
    )
    guardians_by_family: dict[UUID, list[Guardian]] = defaultdict(list)
    for guardian in guardian_rows:
        guardians_by_family[guardian.family_id].append(guardian)

    payer_versions = list(
        session.scalars(
            select(BillingAccountPayerVersion)
            .where(
                BillingAccountPayerVersion.organization_id == organization_id,
                BillingAccountPayerVersion.billing_account_id.in_(account_ids),
            )
            .order_by(
                BillingAccountPayerVersion.billing_account_id,
                BillingAccountPayerVersion.version_number,
                BillingAccountPayerVersion.id,
            )
        )
    )
    latest_payers = _latest_by_parent(payer_versions, "billing_account_id")

    facilities = {
        facility.id: facility
        for facility in session.scalars(
            select(Facility)
            .where(
                Facility.organization_id == organization_id,
                Facility.id.in_(facility_ids),
            )
            .order_by(Facility.id)
        )
    }
    programs = {
        program.id: program
        for program in session.scalars(
            select(Program)
            .where(
                Program.organization_id == organization_id,
                Program.id.in_(program_ids),
            )
            .order_by(Program.id)
        )
    }
    enrollments = {
        enrollment.id: enrollment
        for enrollment in session.scalars(
            select(Enrollment)
            .where(
                Enrollment.organization_id == organization_id,
                Enrollment.id.in_(enrollment_ids),
            )
            .order_by(Enrollment.id)
        )
    }
    rate_plans = list(
        session.scalars(
            select(BillingRatePlan)
            .where(BillingRatePlan.organization_id == organization_id)
            .order_by(
                BillingRatePlan.facility_id,
                BillingRatePlan.program_id,
                BillingRatePlan.age_group,
                BillingRatePlan.code,
                BillingRatePlan.id,
            )
        )
    )
    rate_versions = list(
        session.scalars(
            select(BillingRatePlanVersion)
            .where(BillingRatePlanVersion.organization_id == organization_id)
            .order_by(
                BillingRatePlanVersion.rate_plan_id,
                BillingRatePlanVersion.version_number,
                BillingRatePlanVersion.id,
            )
        )
    )
    attested_sources: set[tuple[str, UUID]] = set()
    if source_attestations_required:
        attested_sources = {
            (source_type, source_id)
            for source_type, source_id in session.execute(
                select(
                    BillingSandboxSourceAttestation.source_type,
                    BillingSandboxSourceAttestation.source_id,
                ).where(
                    BillingSandboxSourceAttestation.organization_id
                    == organization_id,
                    BillingSandboxSourceAttestation.marker
                    == "TEST_SYNTHETIC_ONLY",
                    BillingSandboxSourceAttestation.reason_code
                    == "disposable_test_fixture",
                )
            )
        }
    return {
        "children": children,
        "guardians_by_family": guardians_by_family,
        "latest_payers": latest_payers,
        "facilities": facilities,
        "programs": programs,
        "enrollments": enrollments,
        "rate_plans": rate_plans,
        "latest_rate_versions": _latest_by_parent(rate_versions, "rate_plan_id"),
        "rate_versions_by_id": {version.id: version for version in rate_versions},
        "attested_sources": attested_sources,
    }


def _payer_options(
    guardians: list[Guardian],
) -> list[BillingReadinessBatchPayerOption]:
    return [
        BillingReadinessBatchPayerOption(
            guardian_id=guardian.id,
            display_name=f"{guardian.first_name} {guardian.last_name}".strip(),
            is_primary=guardian.is_primary,
        )
        for guardian in guardians[:MAX_BATCH_OPTIONS]
    ]


def _rate_options(
    *,
    plans: list[BillingRatePlan],
    latest_versions: dict[UUID, BillingRatePlanVersion],
    facility_id: UUID,
    program_id: UUID,
    program_type: str,
    age_group: str | None,
    as_of_date: date,
) -> list[BillingReadinessBatchRatePlanOption]:
    candidates = [
        plan
        for plan in plans
        if plan.facility_id == facility_id
        and plan.program_id == program_id
        and plan.program_type == program_type
        and (
            (age_group is None and plan.age_group is None)
            or (
                age_group is not None
                and (plan.age_group == age_group or plan.age_group is None)
            )
        )
    ]
    candidates.sort(
        key=lambda plan: (
            0 if plan.age_group == age_group else 1,
            plan.code.casefold(),
            str(plan.id),
        )
    )
    return [
        BillingReadinessBatchRatePlanOption(
            rate_plan_id=plan.id,
            code=plan.code,
            name=plan.name,
            age_group=plan.age_group,
            latest_version_id=(
                latest_versions[plan.id].id if plan.id in latest_versions else None
            ),
            latest_version_number=(
                latest_versions[plan.id].version_number
                if plan.id in latest_versions
                else None
            ),
            latest_billing_unit=(
                latest_versions[plan.id].billing_unit
                if plan.id in latest_versions
                else None
            ),
            latest_unit_amount_minor=(
                latest_versions[plan.id].unit_amount_minor
                if plan.id in latest_versions
                else None
            ),
            latest_effective_from=(
                latest_versions[plan.id].effective_from
                if plan.id in latest_versions
                else None
            ),
            latest_effective_until=(
                latest_versions[plan.id].effective_until
                if plan.id in latest_versions
                else None
            ),
            revision_can_resolve_as_of_date=(
                plan.id in latest_versions
                and latest_versions[plan.id].effective_from < as_of_date
            ),
        )
        for plan in candidates[:MAX_BATCH_OPTIONS]
    ]


def _build_groups(
    session: Session,
    *,
    organization_id: UUID,
    readiness: BillingReadinessResponse,
    source_attestations_required: bool,
) -> tuple[list[BillingReadinessBatchPlanGroup], dict[str, str]]:
    facts = _supporting_facts(
        session,
        organization_id=organization_id,
        readiness=readiness,
        source_attestations_required=source_attestations_required,
    )
    children: dict[UUID, Child] = facts["children"]
    guardians_by_family: dict[UUID, list[Guardian]] = facts["guardians_by_family"]
    latest_payers: dict[UUID, BillingAccountPayerVersion] = facts["latest_payers"]
    facilities: dict[UUID, Facility] = facts["facilities"]
    programs: dict[UUID, Program] = facts["programs"]
    enrollments: dict[UUID, Enrollment] = facts["enrollments"]
    plans: list[BillingRatePlan] = facts["rate_plans"]
    plans_by_id = {plan.id: plan for plan in plans}
    latest_rate_versions: dict[UUID, BillingRatePlanVersion] = facts[
        "latest_rate_versions"
    ]
    rate_versions_by_id: dict[UUID, BillingRatePlanVersion] = facts[
        "rate_versions_by_id"
    ]
    attested_sources: set[tuple[str, UUID]] = facts["attested_sources"]
    facility_names = {facility.id: facility.name for facility in facilities.values()}
    age_groups = {child.id: child.age_group for child in children.values()}

    groups: list[BillingReadinessBatchPlanGroup] = []
    membership_search_index: dict[str, str] = {}
    consumed_child_ids: set[UUID] = set()

    account_items: dict[UUID, list[Any]] = defaultdict(list)
    for item in readiness.items:
        if item.status in {"needs_account", "needs_payer"}:
            account_items[item.family_id].append(item)
    for family_id in sorted(account_items, key=str):
        items = account_items[family_id]
        consumed_child_ids.update(item.child_id for item in items)
        statuses = {item.status for item in items}
        account_ids = {item.billing_account_id for item in items}
        family_guardians = guardians_by_family.get(family_id, [])
        guardians = [
            guardian
            for guardian in family_guardians
            if not source_attestations_required
            or ("guardian", guardian.id) in attested_sources
        ]
        representative = items[0]
        command_type: str | None = None
        block_code: str | None = None
        latest_payer = None
        if len(statuses) != 1 or len(account_ids) != 1:
            block_code = "billing_account_family_projection_inconsistent"
        elif len(guardians) > MAX_BATCH_OPTIONS:
            block_code = "billing_payer_options_exceed_limit"
        elif not guardians:
            block_code = (
                "billing_payer_source_attestation_missing"
                if source_attestations_required and family_guardians
                else "billing_payer_option_missing"
            )
        elif representative.status == "needs_account":
            command_type = "account_open"
        elif representative.billing_account_id is None:
            block_code = "billing_account_reference_missing"
        else:
            latest_payer = latest_payers.get(representative.billing_account_id)
            if latest_payer is None:
                block_code = "billing_account_payer_history_missing"
            else:
                command_type = "account_payer_assign"
        wave: BillingReadinessBatchWave = (
            "account_payer" if command_type is not None else "manual_review"
        )
        affected_count, membership_digest, subjects, truncated = _affected_facts(
            items
        )
        group = BillingReadinessBatchPlanGroup(
                group_id=_group_id(
                    organization_id,
                    wave,
                    family_id,
                    representative.billing_account_id,
                    representative.status,
                    block_code,
                    membership_digest,
                ),
                wave=wave,
                readiness_status=representative.status,
                reason_codes=representative.reason_codes,
                actionable=command_type is not None,
                block_code=block_code,
                suggested_command_type=command_type,
                family_id=family_id,
                family_name=representative.family_name,
                billing_account_id=representative.billing_account_id,
                latest_payer_version_id=(
                    latest_payer.id if latest_payer is not None else None
                ),
                latest_payer_version_number=(
                    latest_payer.version_number if latest_payer is not None else None
                ),
                facility_id=None,
                facility_name=None,
                program_id=None,
                program_name=None,
                program_type=None,
                age_group=None,
                rate_plan_id=None,
                rate_plan_version_id=None,
                affected_count=affected_count,
                affected_membership_digest=membership_digest,
                affected_children=subjects,
                affected_children_truncated=truncated,
                payer_options=_payer_options(guardians),
                rate_plan_options=[],
                action_path=representative.action_path,
            )
        groups.append(group)
        membership_search_index[group.group_id] = _full_membership_search_text(
            items
        )

    rate_items: dict[tuple[UUID, UUID, str | None], list[Any]] = defaultdict(list)
    for item in readiness.items:
        if item.status == "needs_rate_plan" and item.child_id not in consumed_child_ids:
            if item.facility_id is None or item.program_id is None:
                groups.append(
                    _manual_review_group(
                        organization_id,
                        item,
                        facility_names=facility_names,
                        programs=programs,
                        age_groups=age_groups,
                        block_code="billing_rate_scope_missing",
                    )
                )
                consumed_child_ids.add(item.child_id)
            else:
                rate_items[
                    (
                        item.facility_id,
                        item.program_id,
                        age_groups.get(item.child_id),
                    )
                ].append(item)
    for scope in sorted(rate_items, key=lambda value: tuple(str(part or "") for part in value)):
        facility_id, program_id, age_group = scope
        items = rate_items[scope]
        consumed_child_ids.update(item.child_id for item in items)
        facility = facilities.get(facility_id)
        program = programs.get(program_id)
        options = _rate_options(
            plans=plans,
            latest_versions=latest_rate_versions,
            facility_id=facility_id,
            program_id=program_id,
            program_type=program.program_type if program is not None else "",
            age_group=age_group,
            as_of_date=readiness.as_of_date,
        )
        option_count = sum(
            1
            for plan in plans
            if plan.facility_id == facility_id
            and plan.program_id == program_id
            and program is not None
            and plan.program_type == program.program_type
            and (
                (age_group is None and plan.age_group is None)
                or (
                    age_group is not None
                    and (plan.age_group == age_group or plan.age_group is None)
                )
            )
        )
        block_code = None
        if facility is None or program is None or program.facility_id != facility_id:
            block_code = "billing_rate_program_scope_invalid"
        elif facility.status != "active":
            block_code = "billing_facility_inactive"
        elif not program.is_active:
            block_code = "billing_program_inactive"
        elif source_attestations_required and (
            ("facility", facility_id) not in attested_sources
            or ("program", program_id) not in attested_sources
        ):
            block_code = "billing_rate_source_attestation_missing"
        elif option_count > MAX_BATCH_OPTIONS:
            block_code = "billing_rate_options_exceed_limit"
        wave = "rate_plan" if block_code is None else "manual_review"
        sole_option = options[0] if len(options) == 1 else None
        sole_rate_version = (
            latest_rate_versions.get(sole_option.rate_plan_id)
            if sole_option is not None
            else None
        )
        affected_count, membership_digest, subjects, truncated = _affected_facts(
            items
        )
        group = BillingReadinessBatchPlanGroup(
                group_id=_group_id(
                    organization_id,
                    wave,
                    facility_id,
                    program_id,
                    age_group,
                    block_code,
                    membership_digest,
                ),
                wave=wave,
                readiness_status="needs_rate_plan",
                reason_codes=["applicable_rate_plan_missing"],
                actionable=block_code is None,
                block_code=block_code,
                suggested_command_type=(
                    "rate_version_publish" if block_code is None else None
                ),
                family_id=None,
                family_name=None,
                billing_account_id=None,
                latest_payer_version_id=None,
                latest_payer_version_number=None,
                facility_id=facility_id,
                facility_name=facility.name if facility is not None else None,
                program_id=program_id,
                program_name=program.name if program is not None else None,
                program_type=program.program_type if program is not None else None,
                age_group=age_group,
                rate_plan_id=sole_option.rate_plan_id if sole_option else None,
                rate_plan_version_id=(
                    sole_option.latest_version_id if sole_option else None
                ),
                rate_billing_unit=(
                    sole_rate_version.billing_unit
                    if sole_rate_version is not None
                    else None
                ),
                rate_unit_amount_minor=(
                    sole_rate_version.unit_amount_minor
                    if sole_rate_version is not None
                    else None
                ),
                rate_effective_from=(
                    sole_rate_version.effective_from
                    if sole_rate_version is not None
                    else None
                ),
                rate_effective_until=(
                    sole_rate_version.effective_until
                    if sole_rate_version is not None
                    else None
                ),
                affected_count=affected_count,
                affected_membership_digest=membership_digest,
                affected_children=subjects,
                affected_children_truncated=truncated,
                payer_options=[],
                rate_plan_options=options,
                action_path=items[0].action_path,
            )
        groups.append(group)
        membership_search_index[group.group_id] = _full_membership_search_text(
            items
        )

    for item in readiness.items:
        if item.child_id in consumed_child_ids:
            continue
        child = children.get(item.child_id)
        facility = facilities.get(item.facility_id) if item.facility_id else None
        program = programs.get(item.program_id) if item.program_id else None
        if item.status == "needs_agreement":
            rate_version = (
                rate_versions_by_id.get(item.rate_plan_version_id)
                if item.rate_plan_version_id is not None
                else None
            )
            rate_plan = (
                plans_by_id.get(item.rate_plan_id)
                if item.rate_plan_id is not None
                else None
            )
            enrollment = (
                enrollments.get(item.enrollment_id)
                if item.enrollment_id is not None
                else None
            )
            complete = all(
                value is not None
                for value in (
                    item.billing_account_id,
                    item.enrollment_id,
                    item.facility_id,
                    item.program_id,
                    item.rate_plan_id,
                    item.rate_plan_version_id,
                    child,
                    facility,
                    program,
                    rate_plan,
                    rate_version,
                    enrollment,
                )
            )
            block_code = None if complete else "billing_agreement_scope_missing"
            if complete and (
                program is None
                or program.facility_id != item.facility_id
            ):
                complete = False
                block_code = "billing_agreement_program_scope_invalid"
            elif complete and facility.status != "active":
                complete = False
                block_code = "billing_facility_inactive"
            elif complete and not program.is_active:
                complete = False
                block_code = "billing_program_inactive"
            elif complete and (
                rate_plan.facility_id != item.facility_id
                or rate_plan.program_id != item.program_id
                or rate_plan.program_type != program.program_type
                or rate_version.rate_plan_id != rate_plan.id
                or (
                    rate_plan.age_group is not None
                    and (
                        child is None
                        or child.age_group is None
                        or rate_plan.age_group.casefold()
                        != child.age_group.casefold()
                    )
                )
            ):
                complete = False
                block_code = "billing_agreement_rate_scope_invalid"
            elif complete and (
                enrollment.child_id != item.child_id
                or enrollment.facility_id != item.facility_id
                or enrollment.program_id != item.program_id
            ):
                complete = False
                block_code = "billing_agreement_enrollment_scope_invalid"
            elif complete and source_attestations_required and (
                ("facility", item.facility_id) not in attested_sources
                or ("program", item.program_id) not in attested_sources
            ):
                complete = False
                block_code = "billing_agreement_source_attestation_missing"
            effective_from_min = None
            effective_until_max = None
            if rate_version is not None and enrollment is not None:
                effective_from_min = max(
                    rate_version.effective_from,
                    enrollment.start_date,
                )
                end_dates = [
                    value
                    for value in (
                        rate_version.effective_until,
                        enrollment.end_date,
                    )
                    if value is not None
                ]
                effective_until_max = min(end_dates) if end_dates else None
                if (
                    effective_until_max is not None
                    and effective_from_min > effective_until_max
                ):
                    complete = False
                    block_code = "billing_agreement_effective_window_empty"
            wave = "agreement" if complete else "manual_review"
            affected_count, membership_digest, subjects, truncated = (
                _affected_facts([item])
            )
            groups.append(
                BillingReadinessBatchPlanGroup(
                    group_id=_group_id(
                        organization_id,
                        wave,
                        item.family_id,
                        item.child_id,
                        item.enrollment_id,
                        item.rate_plan_version_id,
                        block_code,
                        membership_digest,
                    ),
                    wave=wave,
                    readiness_status=item.status,
                    reason_codes=item.reason_codes,
                    actionable=complete,
                    block_code=block_code,
                    suggested_command_type="agreement_establish" if complete else None,
                    family_id=item.family_id,
                    family_name=item.family_name,
                    billing_account_id=item.billing_account_id,
                    latest_payer_version_id=None,
                    latest_payer_version_number=None,
                    facility_id=item.facility_id,
                    facility_name=facility.name if facility is not None else None,
                    program_id=item.program_id,
                    program_name=program.name if program is not None else None,
                    program_type=program.program_type if program is not None else None,
                    age_group=child.age_group if child is not None else None,
                    rate_plan_id=item.rate_plan_id,
                    rate_plan_version_id=item.rate_plan_version_id,
                    rate_billing_unit=(
                        rate_version.billing_unit
                        if rate_version is not None
                        else None
                    ),
                    rate_unit_amount_minor=(
                        rate_version.unit_amount_minor
                        if rate_version is not None
                        else None
                    ),
                    rate_effective_from=(
                        rate_version.effective_from
                        if rate_version is not None
                        else None
                    ),
                    rate_effective_until=(
                        rate_version.effective_until
                        if rate_version is not None
                        else None
                    ),
                    agreement_effective_from_min=effective_from_min,
                    agreement_effective_until_max=effective_until_max,
                    agreement_effective_until_required=(
                        effective_until_max is not None
                    ),
                    affected_count=affected_count,
                    affected_membership_digest=membership_digest,
                    affected_children=subjects,
                    affected_children_truncated=truncated,
                    payer_options=[],
                    rate_plan_options=[],
                    action_path=item.action_path,
                )
            )
        elif item.status == "setup_ready":
            ready_rate_version = (
                rate_versions_by_id.get(item.rate_plan_version_id)
                if item.rate_plan_version_id is not None
                else None
            )
            ready_rate_plan = (
                plans_by_id.get(item.rate_plan_id)
                if item.rate_plan_id is not None
                else None
            )
            ready_enrollment = (
                enrollments.get(item.enrollment_id)
                if item.enrollment_id is not None
                else None
            )
            ready_block_code = None
            if any(
                value is None
                for value in (
                    child,
                    facility,
                    program,
                    ready_rate_plan,
                    ready_rate_version,
                    ready_enrollment,
                )
            ):
                ready_block_code = "billing_ready_scope_invalid"
            elif facility.status != "active":
                ready_block_code = "billing_facility_inactive"
            elif not program.is_active:
                ready_block_code = "billing_program_inactive"
            elif (
                program.facility_id != item.facility_id
                or ready_enrollment.child_id != item.child_id
                or ready_enrollment.facility_id != item.facility_id
                or ready_enrollment.program_id != item.program_id
                or ready_rate_plan.facility_id != item.facility_id
                or ready_rate_plan.program_id != item.program_id
                or ready_rate_plan.program_type != program.program_type
                or ready_rate_version.rate_plan_id != ready_rate_plan.id
                or (
                    ready_rate_plan.age_group is not None
                    and (
                        child.age_group is None
                        or ready_rate_plan.age_group.casefold()
                        != child.age_group.casefold()
                    )
                )
            ):
                ready_block_code = "billing_ready_care_scope_invalid"
            elif source_attestations_required and (
                ("facility", item.facility_id) not in attested_sources
                or ("program", item.program_id) not in attested_sources
            ):
                ready_block_code = "billing_ready_source_attestation_missing"
            if ready_block_code is not None:
                groups.append(
                    _manual_review_group(
                        organization_id,
                        item,
                        facility_names=facility_names,
                        programs=programs,
                        age_groups=age_groups,
                        block_code=ready_block_code,
                    )
                )
                continue
            affected_count, membership_digest, subjects, truncated = (
                _affected_facts([item])
            )
            groups.append(
                BillingReadinessBatchPlanGroup(
                    group_id=_group_id(
                        organization_id,
                        "ready",
                        item.family_id,
                        item.child_id,
                        item.enrollment_id,
                        item.agreement_version_id,
                        membership_digest,
                    ),
                    wave="ready",
                    readiness_status=item.status,
                    reason_codes=item.reason_codes,
                    actionable=False,
                    block_code=None,
                    suggested_command_type=None,
                    family_id=item.family_id,
                    family_name=item.family_name,
                    billing_account_id=item.billing_account_id,
                    latest_payer_version_id=None,
                    latest_payer_version_number=None,
                    facility_id=item.facility_id,
                    facility_name=facility.name if facility is not None else None,
                    program_id=item.program_id,
                    program_name=program.name if program is not None else None,
                    program_type=program.program_type if program is not None else None,
                    age_group=child.age_group if child is not None else None,
                    rate_plan_id=item.rate_plan_id,
                    rate_plan_version_id=item.rate_plan_version_id,
                    rate_billing_unit=(
                        ready_rate_version.billing_unit
                        if ready_rate_version is not None
                        else None
                    ),
                    rate_unit_amount_minor=(
                        ready_rate_version.unit_amount_minor
                        if ready_rate_version is not None
                        else None
                    ),
                    rate_effective_from=(
                        ready_rate_version.effective_from
                        if ready_rate_version is not None
                        else None
                    ),
                    rate_effective_until=(
                        ready_rate_version.effective_until
                        if ready_rate_version is not None
                        else None
                    ),
                    affected_count=affected_count,
                    affected_membership_digest=membership_digest,
                    affected_children=subjects,
                    affected_children_truncated=truncated,
                    payer_options=[],
                    rate_plan_options=[],
                    action_path=item.action_path,
                )
            )
        else:
            groups.append(
                _manual_review_group(
                    organization_id,
                    item,
                    facility_names=facility_names,
                    programs=programs,
                    age_groups=age_groups,
                )
            )

    wave_order = {
        "account_payer": 0,
        "rate_plan": 1,
        "agreement": 2,
        "ready": 3,
        "manual_review": 4,
    }
    groups.sort(
        key=lambda group: (
            wave_order[group.wave],
            (group.family_name or "").casefold(),
            (group.facility_name or "").casefold(),
            (group.program_name or "").casefold(),
            (group.age_group or "").casefold(),
            group.affected_children[0].child_name.casefold(),
            group.group_id,
        )
    )
    for group in groups:
        membership_search_index.setdefault(
            group.group_id,
            "\n".join(
                value
                for child in group.affected_children
                for value in (child.family_name, child.child_name)
            ).casefold(),
        )
    return groups, membership_search_index


def _snapshot_token(
    *,
    organization_id: UUID,
    as_of_date: date,
    readiness: BillingReadinessResponse,
    groups: list[BillingReadinessBatchPlanGroup],
    reserved_rate_codes: frozenset[str],
    membership_search_index: dict[str, str],
) -> str:
    canonical = {
        "schema": "billing-readiness-batch-plan-v1",
        "organization_id": str(organization_id),
        "as_of_date": as_of_date.isoformat(),
        "data_through_realtime_sequence": readiness.data_through_realtime_sequence,
        "groups": [group.model_dump(mode="json") for group in groups],
        "reserved_rate_codes": sorted(reserved_rate_codes),
        "membership_search_index": membership_search_index,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_billing_readiness_batch_snapshot(
    session: Session,
    *,
    organization_id: UUID,
    as_of_date: date,
    source_attestations_required: bool,
) -> BillingReadinessBatchSnapshot:
    readiness = build_billing_readiness(
        session,
        organization_id=organization_id,
        as_of_date=as_of_date,
        source_attestations_required=source_attestations_required,
    )
    groups, membership_search_index = _build_groups(
        session,
        organization_id=organization_id,
        readiness=readiness,
        source_attestations_required=source_attestations_required,
    )
    reserved_rate_codes = frozenset(
        code.casefold()
        for code in session.scalars(
            select(BillingRatePlan.code)
            .where(BillingRatePlan.organization_id == organization_id)
            .order_by(BillingRatePlan.code, BillingRatePlan.id)
        )
    )
    token = _snapshot_token(
        organization_id=organization_id,
        as_of_date=as_of_date,
        readiness=readiness,
        groups=groups,
        reserved_rate_codes=reserved_rate_codes,
        membership_search_index=membership_search_index,
    )
    return BillingReadinessBatchSnapshot(
        readiness=readiness,
        groups=tuple(groups),
        snapshot_token=token,
        reserved_rate_codes=reserved_rate_codes,
        membership_search_index=membership_search_index,
    )
