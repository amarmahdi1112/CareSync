"""Independent, deterministic validation for V3 scheduler output.

The auditor deliberately derives legal dates, care windows, occupancy, and claim
totals from the immutable V3 contracts.  It does not call the scheduler or its
candidate-building helpers, so a defect in construction cannot silently bless
the same defect during validation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date

from .types import (
    DAYCARE,
    OSC,
    ScheduleAssignment,
    TimeBlock,
    V3Child,
    V3Config,
    V3ScheduleResult,
)

_OSC_MORNING = (7 * 60 // 5, 8 * 60 // 5 + 30 // 5)
_OSC_AFTERNOON = (15 * 60 // 5 + 30 // 5, 18 * 60 // 5)
_DAYCARE_MAX_DAILY_TICKS = 9 * 60 // 5
_DAYCARE_REALISM_PHASE = "daycare_realism"
_DAYCARE_REALISM_ACTION = "applied"


@dataclass(frozen=True, slots=True)
class AuditViolation:
    """One machine-readable hard-audit failure."""

    code: str
    message: str
    child_id: str | None = None
    date: str | None = None
    tick: int | None = None
    expected: int | str | None = None
    actual: int | str | None = None


@dataclass(frozen=True, slots=True)
class CapacityPeak:
    """Peak simultaneous occupancy observed on one assignment date."""

    date: str
    occupancy: int
    first_tick: int


@dataclass(frozen=True, slots=True)
class V3AuditReport:
    """Canonical audit result suitable for certification and persistence."""

    valid: bool
    violations: tuple[AuditViolation, ...]
    requested_ticks: int
    scheduled_ticks: int
    scheduled_ticks_by_child: tuple[tuple[str, int], ...]
    shortfall_ticks_by_child: tuple[tuple[str, int], ...]
    overclaim_ticks_by_child: tuple[tuple[str, int], ...]
    capacity_peaks: tuple[CapacityPeak, ...]


def audit_assignments(
    assignments: Iterable[ScheduleAssignment],
    children: Iterable[V3Child],
    config: V3Config,
    *,
    require_exact_claims: bool = True,
    reported_requested_ticks: int | None = None,
    reported_scheduled_ticks_by_child: Iterable[tuple[str, int]] | None = None,
    enforce_daycare_realism: bool = False,
) -> V3AuditReport:
    """Audit assignments solely against source children and configuration.

    ``reported_*`` values are optional reconciliation inputs.  They allow the
    caller to prove that persisted/result metadata agrees with independently
    recomputed values, without making those metadata authoritative.
    """

    canonical_assignments = tuple(sorted(assignments, key=_assignment_key))
    canonical_children = tuple(sorted(children, key=_child_key))
    issues: list[AuditViolation] = []

    child_groups: dict[str, list[V3Child]] = {}
    for child in canonical_children:
        child_groups.setdefault(child.child_id, []).append(child)
    children_by_id: dict[str, V3Child] = {}
    for child_id, group in sorted(child_groups.items()):
        children_by_id[child_id] = group[0]
        if len(group) > 1:
            issues.append(
                AuditViolation(
                    code="DUPLICATE_CHILD_DEFINITION",
                    message=f"Child {child_id} appears more than once in audit input.",
                    child_id=child_id,
                    expected=1,
                    actual=len(group),
                )
            )

    scheduled: dict[str, int] = {child_id: 0 for child_id in children_by_id}
    occupancy: dict[tuple[str, int], int] = {}
    child_dates: dict[tuple[str, str], int] = {}
    child_date_ticks: dict[tuple[str, str], int] = {}

    for assignment in canonical_assignments:
        scheduled[assignment.child_id] = (
            scheduled.get(assignment.child_id, 0) + assignment.duration_ticks
        )
        child_date = (assignment.child_id, assignment.date)
        child_dates[child_date] = child_dates.get(child_date, 0) + 1
        child_date_ticks[child_date] = (
            child_date_ticks.get(child_date, 0) + assignment.duration_ticks
        )
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                key = (assignment.date, tick)
                occupancy[key] = occupancy.get(key, 0) + 1

        child = children_by_id.get(assignment.child_id)
        if child is None:
            issues.append(
                AuditViolation(
                    code="UNKNOWN_CHILD",
                    message=f"Assignment references unknown child {assignment.child_id}.",
                    child_id=assignment.child_id,
                    date=assignment.date,
                )
            )
            continue

        date_problem = _date_violation(child, config, assignment.date)
        if date_problem is not None:
            issues.append(date_problem)

        expected_kind = _expected_kind(child, config, assignment.date)
        if assignment.kind != expected_kind:
            issues.append(
                AuditViolation(
                    code="KIND_MISMATCH",
                    message=(
                        f"{assignment.child_id} has kind {assignment.kind} on "
                        f"{assignment.date}; expected {expected_kind}."
                    ),
                    child_id=assignment.child_id,
                    date=assignment.date,
                    expected=expected_kind,
                    actual=assignment.kind,
                )
            )

        legal_windows = _care_windows(child, config, assignment.date)
        if not _has_legal_block_structure(assignment, legal_windows, expected_kind):
            issues.append(
                AuditViolation(
                    code="ILLEGAL_TIME_BLOCKS",
                    message=(
                        f"{assignment.child_id} has blocks outside its legal care "
                        f"pattern on {assignment.date}."
                    ),
                    child_id=assignment.child_id,
                    date=assignment.date,
                )
            )

    for (child_id, current_date), count in sorted(child_dates.items()):
        if count > 1:
            issues.append(
                AuditViolation(
                    code="DUPLICATE_CHILD_DATE",
                    message=(
                        f"{child_id} has {count} assignments on {current_date}; "
                        "only one is permitted."
                    ),
                    child_id=child_id,
                    date=current_date,
                    expected=1,
                    actual=count,
                )
            )

    if enforce_daycare_realism:
        for (child_id, current_date), duration_ticks in sorted(child_date_ticks.items()):
            child = children_by_id.get(child_id)
            if child is None or child.care_type != DAYCARE:
                continue
            if duration_ticks > _DAYCARE_MAX_DAILY_TICKS:
                issues.append(
                    AuditViolation(
                        code="DAYCARE_DAILY_DURATION_EXCEEDED",
                        message=(
                            f"{child_id} is scheduled for {duration_ticks} five-minute ticks "
                            f"on {current_date}; final Daycare schedules permit at most "
                            f"{_DAYCARE_MAX_DAILY_TICKS} ticks (9 hours) per day."
                        ),
                        child_id=child_id,
                        date=current_date,
                        expected=_DAYCARE_MAX_DAILY_TICKS,
                        actual=duration_ticks,
                    )
                )

    capacity_peaks: list[CapacityPeak] = []
    occupancy_by_date: dict[str, list[tuple[int, int]]] = {}
    for (current_date, tick), count in sorted(occupancy.items()):
        occupancy_by_date.setdefault(current_date, []).append((tick, count))
        if count > config.capacity:
            issues.append(
                AuditViolation(
                    code="CAPACITY_EXCEEDED",
                    message=(
                        f"Capacity {config.capacity} is exceeded at tick {tick} "
                        f"on {current_date}: occupancy is {count}."
                    ),
                    date=current_date,
                    tick=tick,
                    expected=config.capacity,
                    actual=count,
                )
            )
    for current_date, tick_counts in sorted(occupancy_by_date.items()):
        peak = max(count for _, count in tick_counts)
        first_tick = min(tick for tick, count in tick_counts if count == peak)
        capacity_peaks.append(CapacityPeak(current_date, peak, first_tick))

    shortfalls: list[tuple[str, int]] = []
    overclaims: list[tuple[str, int]] = []
    for child_id, child in sorted(children_by_id.items()):
        actual = scheduled.get(child_id, 0)
        if actual < child.claimed_ticks:
            shortfall = child.claimed_ticks - actual
            shortfalls.append((child_id, shortfall))
            if require_exact_claims:
                issues.append(
                    AuditViolation(
                        code="CLAIM_UNDERFILLED",
                        message=(
                            f"{child_id} is short by {shortfall} ticks "
                            f"({actual}/{child.claimed_ticks})."
                        ),
                        child_id=child_id,
                        expected=child.claimed_ticks,
                        actual=actual,
                    )
                )
        elif actual > child.claimed_ticks:
            overclaim = actual - child.claimed_ticks
            overclaims.append((child_id, overclaim))
            issues.append(
                AuditViolation(
                    code="CLAIM_EXCEEDED",
                    message=(
                        f"{child_id} exceeds its claim by {overclaim} ticks "
                        f"({actual}/{child.claimed_ticks})."
                    ),
                    child_id=child_id,
                    expected=child.claimed_ticks,
                    actual=actual,
                )
            )

    requested_ticks = sum(child.claimed_ticks for child in children_by_id.values())
    scheduled_ticks = sum(assignment.duration_ticks for assignment in canonical_assignments)
    scheduled_items = tuple(sorted(scheduled.items()))

    if reported_requested_ticks is not None and reported_requested_ticks != requested_ticks:
        issues.append(
            AuditViolation(
                code="REQUESTED_TICKS_MISMATCH",
                message="Reported requested ticks do not match source child claims.",
                expected=requested_ticks,
                actual=reported_requested_ticks,
            )
        )

    if reported_scheduled_ticks_by_child is not None:
        reported_items = tuple(sorted(reported_scheduled_ticks_by_child))
        if reported_items != scheduled_items:
            issues.append(
                AuditViolation(
                    code="SCHEDULED_TICKS_MISMATCH",
                    message=("Reported scheduled ticks by child do not match assignment totals."),
                    expected=repr(scheduled_items),
                    actual=repr(reported_items),
                )
            )

    canonical_issues = tuple(sorted(issues, key=_violation_key))
    return V3AuditReport(
        valid=not canonical_issues,
        violations=canonical_issues,
        requested_ticks=requested_ticks,
        scheduled_ticks=scheduled_ticks,
        scheduled_ticks_by_child=scheduled_items,
        shortfall_ticks_by_child=tuple(shortfalls),
        overclaim_ticks_by_child=tuple(overclaims),
        capacity_peaks=tuple(capacity_peaks),
    )


def audit_schedule_result(
    result: V3ScheduleResult,
    children: Iterable[V3Child],
    config: V3Config,
    *,
    require_exact_claims: bool = True,
) -> V3AuditReport:
    """Audit a complete scheduler result, including its reconciliation fields."""

    report = audit_assignments(
        result.assignments,
        children,
        config,
        require_exact_claims=require_exact_claims,
        reported_requested_ticks=result.requested_ticks,
        reported_scheduled_ticks_by_child=result.scheduled_ticks_by_child,
        enforce_daycare_realism=_daycare_realism_was_applied(result),
    )
    issues = list(report.violations)
    metadata_codes = {"REQUESTED_TICKS_MISMATCH", "SCHEDULED_TICKS_MISMATCH"}
    non_hard_codes = metadata_codes | {"CLAIM_UNDERFILLED"}
    hard_violations = sum(issue.code not in non_hard_codes for issue in report.violations)
    total_shortfall = sum(value for _, value in report.shortfall_ticks_by_child)
    worst_shortfall = max((value for _, value in report.shortfall_ticks_by_child), default=0)
    children_by_date: dict[str, set[str]] = {}
    for assignment in result.assignments:
        children_by_date.setdefault(assignment.date, set()).add(assignment.child_id)
    daily_deviation = (
        sum(
            abs(len(children_by_date.get(current_date, set())) - config.daily_unique_target)
            for current_date in config.open_dates
        )
        if config.daily_unique_target is not None
        else 0
    )
    canonical_key = tuple(
        (
            assignment.child_id,
            assignment.date,
            tuple((block.start_tick, block.end_tick) for block in assignment.blocks),
        )
        for assignment in sorted(result.assignments, key=_engine_assignment_key)
    )
    expected_objective = (
        hard_violations,
        total_shortfall,
        worst_shortfall,
        daily_deviation,
        canonical_key,
    )
    actual_objective = (
        result.objective.hard_violations,
        result.objective.total_shortfall_ticks,
        result.objective.worst_shortfall_ticks,
        result.objective.daily_unique_deviation,
        result.objective.canonical_key,
    )
    if actual_objective != expected_objective:
        issues.append(
            AuditViolation(
                code="OBJECTIVE_MISMATCH",
                message="Reported objective does not match independently recomputed values.",
                expected=repr(expected_objective),
                actual=repr(actual_objective),
            )
        )

    realism_placement_failed = _daycare_realism_placement_failed(result)
    independently_feasible = (
        hard_violations == 0
        and not report.shortfall_ticks_by_child
        and not report.overclaim_ticks_by_child
        and not realism_placement_failed
    )
    if result.feasibility.feasible != independently_feasible:
        issues.append(
            AuditViolation(
                code="FEASIBILITY_MISMATCH",
                message="Reported feasibility does not match the independently audited schedule.",
                expected=str(independently_feasible),
                actual=str(result.feasibility.feasible),
            )
        )

    expected_proven = (
        True if independently_feasible else False if realism_placement_failed else None
    )
    if expected_proven is not None and result.feasibility.proven != expected_proven:
        issues.append(
            AuditViolation(
                code="FEASIBILITY_PROOF_MISMATCH",
                message=(
                    "Reported feasibility proof status does not match the independently "
                    "audited schedule state."
                ),
                expected=str(expected_proven),
                actual=str(result.feasibility.proven),
            )
        )

    canonical_issues = tuple(sorted(issues, key=_violation_key))
    return replace(report, valid=not canonical_issues, violations=canonical_issues)


def _daycare_realism_was_applied(result: V3ScheduleResult) -> bool:
    """Require the realism invariant only after the engine marks final shaping complete.

    Incomplete diagnostic schedules can legitimately contain the pre-shaping construction.
    Auditing those drafts as though final shaping ran would convert a useful diagnostic into
    an adapter safety failure.
    """

    return any(
        item.phase == _DAYCARE_REALISM_PHASE and item.action == _DAYCARE_REALISM_ACTION
        for item in result.trace
    )


def _daycare_realism_placement_failed(result: V3ScheduleResult) -> bool:
    """Recognize the engine's explicit, transactional realism rollback state."""

    rolled_back = any(
        item.phase == _DAYCARE_REALISM_PHASE and item.action == "rolled_back"
        for item in result.trace
    )
    placement_failed = "DAYCARE_REALISM_PLACEMENT_FAILED" in result.feasibility.reasons
    return rolled_back and placement_failed


def _child_key(child: V3Child) -> tuple[object, ...]:
    return (
        child.child_id,
        child.care_type,
        child.claimed_ticks,
        child.enrollment_date or "",
        child.excluded_dates,
    )


def _assignment_key(assignment: ScheduleAssignment) -> tuple[object, ...]:
    return (
        assignment.child_id,
        assignment.date,
        assignment.kind,
        tuple((block.start_tick, block.end_tick) for block in assignment.blocks),
    )


def _engine_assignment_key(assignment: ScheduleAssignment) -> tuple[object, ...]:
    return (
        assignment.child_id,
        assignment.date,
        tuple((block.start_tick, block.end_tick) for block in assignment.blocks),
    )


def _violation_key(violation: AuditViolation) -> tuple[object, ...]:
    return (
        violation.code,
        violation.child_id or "",
        violation.date or "",
        violation.tick if violation.tick is not None else -1,
        str(violation.expected),
        str(violation.actual),
        violation.message,
    )


def _date_violation(child: V3Child, config: V3Config, current_date: str) -> AuditViolation | None:
    if current_date not in set(config.open_dates):
        return AuditViolation(
            code="DATE_NOT_OPEN",
            message=f"{current_date} is not an open date.",
            child_id=child.child_id,
            date=current_date,
        )
    if current_date in set(child.excluded_dates):
        return AuditViolation(
            code="DATE_EXCLUDED",
            message=f"{current_date} is excluded for {child.child_id}.",
            child_id=child.child_id,
            date=current_date,
        )
    if child.enrollment_date is not None:
        try:
            before_enrollment = date.fromisoformat(current_date) < date.fromisoformat(
                child.enrollment_date
            )
        except ValueError:
            return AuditViolation(
                code="INVALID_ASSIGNMENT_DATE",
                message=f"Assignment date {current_date} is not an ISO date.",
                child_id=child.child_id,
                date=current_date,
            )
        if before_enrollment:
            return AuditViolation(
                code="BEFORE_ENROLLMENT",
                message=(
                    f"{current_date} is before {child.child_id}'s enrollment date "
                    f"{child.enrollment_date}."
                ),
                child_id=child.child_id,
                date=current_date,
            )
    return None


def _expected_kind(child: V3Child, config: V3Config, current_date: str) -> str:
    if child.care_type == DAYCARE:
        return "daycare"
    if current_date in set(config.school_off_dates):
        return "osc_school_off"
    return "osc_school"


def _care_windows(
    child: V3Child, config: V3Config, current_date: str
) -> tuple[tuple[int, int], ...]:
    if child.care_type == DAYCARE or current_date in set(config.school_off_dates):
        return ((config.operating_start_tick, config.operating_end_tick),)
    if child.care_type != OSC:
        return ()
    windows: list[tuple[int, int]] = []
    for raw_start, raw_end in (_OSC_MORNING, _OSC_AFTERNOON):
        start = max(raw_start, config.operating_start_tick)
        end = min(raw_end, config.operating_end_tick)
        if start < end:
            windows.append((start, end))
    return tuple(windows)


def _has_legal_block_structure(
    assignment: ScheduleAssignment,
    windows: tuple[tuple[int, int], ...],
    expected_kind: str,
) -> bool:
    if not windows:
        return False
    blocks = assignment.blocks
    if expected_kind in {"daycare", "osc_school_off"}:
        return len(blocks) == 1 and _block_in_window(blocks[0], windows[0])
    if len(blocks) == 1:
        return any(_block_in_window(blocks[0], window) for window in windows)
    if len(blocks) == 2 and len(windows) == 2:
        return _block_in_window(blocks[0], windows[0]) and _block_in_window(blocks[1], windows[1])
    return False


def _block_in_window(block: TimeBlock, window: tuple[int, int]) -> bool:
    return window[0] <= block.start_tick and block.end_tick <= window[1]
