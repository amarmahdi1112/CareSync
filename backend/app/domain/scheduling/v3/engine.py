"""Deterministic, isolated V3 scheduling core."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from math import ceil

from .candidates import (
    best_available_candidate_pattern,
    care_windows,
    eligible_dates,
    enumerate_candidate_patterns,
    max_daily_ticks,
)
from .types import (
    DAYCARE,
    OSC,
    CandidatePattern,
    FeasibilityResult,
    Objective,
    PhaseTrace,
    ScheduleAssignment,
    TimeBlock,
    V3Child,
    V3Config,
    V3ScheduleResult,
    VisualizationEvent,
)


@dataclass(slots=True)
class _Construction:
    assignments: tuple[ScheduleAssignment, ...]
    scheduled: dict[str, int]
    objective: Objective


class V3Scheduler:
    """Build schedules using integer ticks and canonical deterministic choices."""

    def __init__(self, config: V3Config, children: Iterable[V3Child]) -> None:
        self.config = config
        supplied = tuple(children)
        identifiers = [child.child_id for child in supplied]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("children cannot contain duplicate child IDs")
        self.children = tuple(sorted(supplied, key=lambda child: child.child_id))
        self.child_map = {child.child_id: child for child in self.children}

    def execute(self) -> V3ScheduleResult:
        trace = [
            self._trace(
                "canonicalize",
                "complete",
                children=len(self.children),
                dates=len(self.config.open_dates),
                tick_minutes=5,
            )
        ]
        preflight = self._preflight()
        trace.append(
            self._trace(
                "feasibility_preflight",
                "passed" if not preflight else "failed",
                reasons=len(preflight),
            )
        )
        order = self._initial_order()
        current = self._construct(order)
        visualization_events = list(self._placement_events(current.assignments))
        trace.append(
            self._trace(
                "construct",
                "complete",
                assignments=len(current.assignments),
                shortfall=current.objective.total_shortfall_ticks,
            )
        )
        preflight_lower_bound = self._preflight_shortfall_lower_bound(preflight)
        if current.objective.total_shortfall_ticks == preflight_lower_bound:
            repair_trace = (
                self._trace(
                    "repair",
                    "stopped",
                    iteration=0,
                    reason="preflight_lower_bound_reached",
                    shortfall_lower_bound=preflight_lower_bound,
                ),
            )
            repair_events = ()
            search_budget_exhausted = False
        else:
            current, repair_trace, repair_events, search_budget_exhausted = self._repair(
                current, order
            )
        visualization_events.extend(repair_events)
        trace.extend(repair_trace)
        realism_failed = False
        if current.objective.total_shortfall_ticks == 0:
            shaped, realism_trace, realism_events = self._rebalance_daycare(current)
            trace.append(realism_trace)
            if shaped is None:
                realism_failed = True
            else:
                current = shaped
                visualization_events.extend(realism_events)
        else:
            trace.append(
                self._trace(
                    "daycare_realism",
                    "skipped",
                    reason="raw_schedule_incomplete",
                )
            )
        hard_violations = self._hard_violations(current.assignments)
        if hard_violations:
            raise RuntimeError("V3 produced an invalid schedule: " + "; ".join(hard_violations))
        trace.append(self._trace("validate", "passed", hard_violations=0))

        if realism_failed:
            feasibility = FeasibilityResult(
                False,
                False,
                ("DAYCARE_REALISM_PLACEMENT_FAILED",),
            )
        elif current.objective.total_shortfall_ticks == 0:
            feasibility = FeasibilityResult(True, True)
        elif preflight:
            feasibility = FeasibilityResult(False, True, preflight)
        elif search_budget_exhausted:
            short_ids = tuple(
                child.child_id
                for child in self.children
                if current.scheduled[child.child_id] < child.claimed_ticks
            )
            feasibility = FeasibilityResult(
                False,
                False,
                ("SEARCH_BUDGET_EXHAUSTED:" + ",".join(short_ids),),
            )
        else:
            short_ids = tuple(
                child.child_id
                for child in self.children
                if current.scheduled[child.child_id] < child.claimed_ticks
            )
            feasibility = FeasibilityResult(
                False,
                False,
                ("SEARCH_EXHAUSTED:" + ",".join(short_ids),),
            )
        trace.append(
            self._trace(
                "complete",
                "feasible" if feasibility.feasible else "incomplete",
                proven=feasibility.proven,
            )
        )
        return V3ScheduleResult(
            assignments=current.assignments,
            feasibility=feasibility,
            trace=tuple(trace),
            objective=current.objective,
            requested_ticks=sum(child.claimed_ticks for child in self.children),
            scheduled_ticks_by_child=tuple(sorted(current.scheduled.items())),
            visualization_events=tuple(visualization_events),
        )

    @staticmethod
    def _preflight_shortfall_lower_bound(reasons: tuple[str, ...]) -> int:
        """Return the strongest proven shortfall bound encoded by preflight.

        Individual child-window shortages add because they belong to distinct
        claims. Global and OSC aggregate bounds can overlap those individual
        shortages, so the strongest safe combined bound is their maximum.
        """

        individual = 0
        aggregate = 0
        for reason in reasons:
            try:
                shortage = int(reason.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                continue
            if reason.startswith("CHILD_WINDOW_SHORTAGE:"):
                individual += shortage
            elif reason.startswith(("GLOBAL_CAPACITY_SHORTAGE:", "OSC_WINDOW_CAPACITY_SHORTAGE:")):
                aggregate = max(aggregate, shortage)
        return max(individual, aggregate)

    def _preflight(self) -> tuple[str, ...]:
        reasons: list[str] = []
        for child in self.children:
            available = sum(
                max_daily_ticks(child, self.config, current_date)
                for current_date in eligible_dates(child, self.config)
            )
            if child.claimed_ticks > available:
                reasons.append(
                    f"CHILD_WINDOW_SHORTAGE:{child.child_id}:{child.claimed_ticks - available}"
                )
        requested = sum(child.claimed_ticks for child in self.children)
        capacity_ticks = (
            self.config.capacity
            * (self.config.operating_end_tick - self.config.operating_start_tick)
            * len(self.config.open_dates)
        )
        if requested > capacity_ticks:
            reasons.append(f"GLOBAL_CAPACITY_SHORTAGE:{requested - capacity_ticks}")
        osc_children = tuple(child for child in self.children if child.care_type == OSC)
        if osc_children:
            osc_requested = sum(child.claimed_ticks for child in osc_children)
            representative = osc_children[0]
            osc_capacity = self.config.capacity * sum(
                sum(end - start for start, end in care_windows(representative, self.config, item))
                for item in self.config.open_dates
            )
            if osc_requested > osc_capacity:
                reasons.append(f"OSC_WINDOW_CAPACITY_SHORTAGE:{osc_requested - osc_capacity}")
        return tuple(sorted(reasons))

    def _initial_order(self) -> tuple[str, ...]:
        def key(child: V3Child) -> tuple[int, int, int, str]:
            dates = eligible_dates(child, self.config)
            available = sum(max_daily_ticks(child, self.config, item) for item in dates)
            return (
                available - child.claimed_ticks,
                len(dates),
                -child.claimed_ticks,
                child.child_id,
            )

        return tuple(child.child_id for child in sorted(self.children, key=key))

    def _construct(self, order: tuple[str, ...]) -> _Construction:
        occupancy = {
            current_date: [0] * self.config.operating_end_tick
            for current_date in sorted(self.config.open_dates)
        }
        assignments: list[ScheduleAssignment] = []
        scheduled = dict.fromkeys(self.child_map, 0)
        assigned_dates: dict[str, set[str]] = {child_id: set() for child_id in self.child_map}
        for child_id in order:
            child = self.child_map[child_id]
            remaining = child.claimed_ticks
            while remaining > 0:
                choice = self._best_available_pattern(
                    child, remaining, occupancy, assigned_dates[child_id]
                )
                if choice is None:
                    break
                assignment = ScheduleAssignment(
                    choice.child_id, choice.date, choice.blocks, choice.kind
                )
                assignments.append(assignment)
                assigned_dates[child_id].add(choice.date)
                scheduled[child_id] += choice.duration_ticks
                remaining -= choice.duration_ticks
                self._reserve(occupancy, choice, 1)
        canonical = self._canonical_assignments(assignments)
        return _Construction(canonical, scheduled, self._objective(canonical, scheduled))

    def _best_available_pattern(
        self,
        child: V3Child,
        remaining: int,
        occupancy: dict[str, list[int]],
        already_assigned: set[str],
    ) -> CandidatePattern | None:
        dates = tuple(
            item
            for item in eligible_dates(child, self.config)
            if item not in already_assigned
            and any(
                occupancy[item][tick] < self.config.capacity
                for start, end in care_windows(child, self.config, item)
                for tick in range(start, end)
            )
        )
        maximum = max(
            (min(remaining, max_daily_ticks(child, self.config, item)) for item in dates),
            default=0,
        )
        for duration in range(maximum, 0, -1):
            available: list[CandidatePattern] = []
            for current_date in dates:
                pattern = best_available_candidate_pattern(
                    child,
                    self.config,
                    current_date,
                    duration,
                    occupancy[current_date],
                )
                if pattern is not None:
                    available.append(pattern)
            if available:
                return min(
                    available,
                    key=lambda pattern: (
                        sum(
                            occupancy[pattern.date][tick]
                            for block in pattern.blocks
                            for tick in range(block.start_tick, block.end_tick)
                        ),
                        pattern.date,
                        tuple((block.start_tick, block.end_tick) for block in pattern.blocks),
                    ),
                )
        return None

    def _repair(
        self, current: _Construction, initial_order: tuple[str, ...]
    ) -> tuple[
        _Construction,
        tuple[PhaseTrace, ...],
        tuple[VisualizationEvent, ...],
        bool,
    ]:
        if self.config.max_repair_iterations == 0:
            return (
                current,
                (self._trace("repair", "stopped", iteration=0, reason="disabled"),),
                (),
                current.objective.total_shortfall_ticks > 0,
            )
        trace: list[PhaseTrace] = []
        visualization_events: list[VisualizationEvent] = []
        order = initial_order
        visited = {order}
        # This is a total repair-run allowance, not a per-iteration allowance.
        # Reconstructing at most 192 schedules keeps the order neighbourhood bounded
        # for the production-sized 183-child batch.
        reorder_budget = max(32, min(192, len(self.children) * 2))
        search_budget_exhausted = False
        for iteration in range(self.config.max_repair_iterations):
            short_ids = sorted(
                (
                    child.child_id
                    for child in self.children
                    if current.scheduled[child.child_id] < child.claimed_ticks
                ),
                key=lambda child_id: (
                    -(self.child_map[child_id].claimed_ticks - current.scheduled[child_id]),
                    child_id,
                ),
            )
            proposals: list[
                tuple[Objective, tuple[object, ...], tuple[str, ...], _Construction]
            ] = []
            reorder_proposals, reconstructions, reorder_budget_exhausted = (
                self._reorder_lookahead_proposals(
                    current,
                    order,
                    visited,
                    reorder_budget,
                )
            )
            reorder_budget -= reconstructions
            search_budget_exhausted = search_budget_exhausted or reorder_budget_exhausted
            proposals.extend(reorder_proposals)
            relocation_proposals, relocation_budget_exhausted = self._relocation_proposals(
                current, short_ids, order
            )
            search_budget_exhausted = search_budget_exhausted or relocation_budget_exhausted
            proposals.extend(relocation_proposals)
            if not proposals:
                trace.append(
                    self._trace(
                        "repair",
                        "stopped",
                        iteration=iteration,
                        reason=(
                            "search_budget_exhausted" if search_budget_exhausted else "no_move"
                        ),
                    )
                )
                break
            _, move_key, proposal_order, candidate = min(
                proposals, key=lambda item: (item[0], item[1])
            )
            if candidate.objective >= current.objective:
                trace.append(
                    self._trace(
                        "repair",
                        "stopped",
                        iteration=iteration,
                        reason=(
                            "search_budget_exhausted"
                            if search_budget_exhausted
                            else "no_improvement"
                        ),
                    )
                )
                break
            previous = current
            current = candidate
            order = proposal_order
            visualization_events.extend(
                self._assignment_diffs(previous, current, iteration=iteration)
            )
            trace.append(
                self._trace(
                    "repair",
                    "accepted",
                    iteration=iteration,
                    move="reorder" if move_key[0] == 0 else "relocate",
                    shortfall=current.objective.total_shortfall_ticks,
                )
            )
        else:
            trace.append(
                self._trace(
                    "repair",
                    "stopped",
                    iteration=self.config.max_repair_iterations,
                    reason="iteration_limit",
                )
            )
        if not trace:
            trace.append(self._trace("repair", "stopped", iteration=0, reason="disabled"))
        return current, tuple(trace), tuple(visualization_events), search_budget_exhausted

    def _placement_events(
        self, assignments: tuple[ScheduleAssignment, ...]
    ) -> tuple[VisualizationEvent, ...]:
        """Describe the committed initial construction in canonical replay order."""

        shortfall = sum(child.claimed_ticks for child in self.children)
        events: list[VisualizationEvent] = []
        for assignment in assignments:
            before = shortfall
            shortfall -= assignment.duration_ticks
            events.append(
                VisualizationEvent(
                    phase="construct",
                    operation="place",
                    child_id=assignment.child_id,
                    from_date=None,
                    to_date=assignment.date,
                    from_blocks=(),
                    to_blocks=assignment.blocks,
                    before_shortfall_ticks=before,
                    after_shortfall_ticks=shortfall,
                )
            )
        return tuple(events)

    def _rebalance_daycare(
        self, current: _Construction
    ) -> tuple[_Construction | None, PhaseTrace, tuple[VisualizationEvent, ...]]:
        """Transactionally reshape an exact Daycare allocation into realistic days."""

        daycare_children = tuple(
            child
            for child in self.children
            if child.care_type == DAYCARE and child.claimed_ticks > 0
        )
        if not daycare_children:
            return (
                current,
                self._trace("daycare_realism", "skipped", reason="no_daycare_claims"),
                (),
            )
        current_daycare = tuple(
            assignment
            for assignment in current.assignments
            if self.child_map[assignment.child_id].care_type == DAYCARE
        )
        if all(assignment.duration_ticks <= 108 for assignment in current_daycare):
            return (
                current,
                self._trace(
                    "daycare_realism",
                    "applied",
                    children=len(daycare_children),
                    assignments=len(current_daycare),
                    max_daily_ticks=108,
                    preferred_min_ticks=72,
                    reason="already_within_bounds",
                ),
                (),
            )

        fixed = tuple(
            assignment
            for assignment in current.assignments
            if self.child_map[assignment.child_id].care_type != DAYCARE
        )
        order = sorted(
            daycare_children,
            key=lambda child: (
                len(eligible_dates(child, self.config)),
                -child.claimed_ticks,
                child.child_id,
            ),
        )
        plans_by_child = {child.child_id: self._daycare_duration_plans(child) for child in order}
        missing = next(
            (child.child_id for child in order if not plans_by_child[child.child_id]),
            None,
        )
        if missing is not None:
            return self._realism_rollback(missing)

        # Each day-count plan gets a seeded realism attempt followed by three
        # seed-independent canonical anchors (center, earliest, latest). These
        # bounded rescue paths prevent aesthetic seed choices from controlling
        # the known constrained packings covered by the adversarial suite.
        strategies_per_plan = 4
        attempt_count = max(len(plans) for plans in plans_by_child.values()) * strategies_per_plan
        last_failure: tuple[str, int | None] = (order[0].child_id, None)
        for attempt in range(attempt_count):
            plan_index, strategy = divmod(attempt, strategies_per_plan)
            occupancy = self._occupancy(fixed)
            shaped_assignments = list(fixed)
            daycare_load_by_date = dict.fromkeys(self.config.open_dates, 0)
            placement_failed = False
            attempt_order = (
                sorted(
                    order,
                    key=lambda child: (
                        len(eligible_dates(child, self.config)),
                        -child.claimed_ticks,
                        self._seed_value(
                            child.child_id,
                            "child-order",
                            str(plan_index),
                        ),
                        child.child_id,
                    ),
                )
                if strategy == 0
                else order
            )
            child_rank = {child.child_id: index for index, child in enumerate(attempt_order)}
            planned: list[tuple[V3Child, int, int]] = []
            selected_plans: dict[str, tuple[int, ...]] = {}
            for child in attempt_order:
                plans = plans_by_child[child.child_id]
                durations = plans[min(plan_index, len(plans) - 1)]
                if strategy > 0:
                    durations = tuple(sorted(durations, reverse=True))
                selected_plans[child.child_id] = durations
                for part, duration in enumerate(durations):
                    planned.append((child, part, duration))
            planned.sort(
                key=lambda item: (
                    len(eligible_dates(item[0], self.config))
                    - len(selected_plans[item[0].child_id]),
                    len(eligible_dates(item[0], self.config)),
                    -item[2],
                    child_rank[item[0].child_id],
                    item[1],
                )
            )
            assigned_dates_by_child: dict[str, set[str]] = {
                child.child_id: set() for child in attempt_order
            }
            for child, part, duration in planned:
                pattern = self._best_daycare_realism_pattern(
                    child,
                    duration,
                    occupancy,
                    assigned_dates_by_child[child.child_id],
                    part,
                    daycare_load_by_date,
                    pressure_first=plan_index > 0 or strategy > 0,
                    canonical_anchor=strategy,
                )
                if pattern is None:
                    last_failure = (child.child_id, duration)
                    placement_failed = True
                    break
                shaped_assignments.append(
                    ScheduleAssignment(
                        child_id=pattern.child_id,
                        date=pattern.date,
                        blocks=pattern.blocks,
                        kind=pattern.kind,
                    )
                )
                assigned_dates_by_child[child.child_id].add(pattern.date)
                daycare_load_by_date[pattern.date] += 1
                self._reserve(occupancy, pattern, 1)
            if placement_failed:
                continue

            canonical = self._canonical_assignments(shaped_assignments)
            shaped_scheduled = dict.fromkeys(self.child_map, 0)
            for assignment in canonical:
                shaped_scheduled[assignment.child_id] += assignment.duration_ticks
            shaped = _Construction(
                assignments=canonical,
                scheduled=shaped_scheduled,
                objective=self._objective(canonical, shaped_scheduled),
            )
            violations = self._hard_violations(shaped.assignments)
            daycare_overages = any(
                self.child_map[assignment.child_id].care_type == DAYCARE
                and assignment.duration_ticks > 108
                for assignment in shaped.assignments
            )
            if violations or daycare_overages or shaped.scheduled != current.scheduled:
                return (
                    None,
                    self._trace(
                        "daycare_realism",
                        "rolled_back",
                        reason="transaction_validation_failed",
                    ),
                    (),
                )
            events = self._assignment_diffs(
                current,
                shaped,
                phase="daycare_realism",
                iteration=None,
            )
            return (
                shaped,
                self._trace(
                    "daycare_realism",
                    "applied",
                    children=len(daycare_children),
                    assignments=sum(
                        self.child_map[item.child_id].care_type == DAYCARE
                        for item in shaped.assignments
                    ),
                    attempts=attempt + 1,
                    day_expansion=plan_index,
                    max_daily_ticks=108,
                    preferred_min_ticks=72,
                ),
                events,
            )
        return self._realism_rollback(*last_failure)

    def _realism_rollback(
        self, child_id: str, duration_ticks: int | None = None
    ) -> tuple[None, PhaseTrace, tuple[VisualizationEvent, ...]]:
        details: dict[str, object] = {
            "reason": "placement_failed",
            "child_id": child_id,
        }
        if duration_ticks is not None:
            details["duration_ticks"] = duration_ticks
        return None, self._trace("daycare_realism", "rolled_back", **details), ()

    def _daycare_duration_plans(self, child: V3Child) -> tuple[tuple[int, ...], ...]:
        eligible = eligible_dates(child, self.config)
        daily_max = min(
            108,
            self.config.operating_end_tick - self.config.operating_start_tick,
        )
        if daily_max <= 0 or child.claimed_ticks > daily_max * len(eligible):
            return ()
        minimum_parts = ceil(child.claimed_ticks / daily_max)
        if minimum_parts == 0:
            return ((),)
        preferred_min = min(72, daily_max)
        maximum_parts = min(
            len(eligible),
            ceil(child.claimed_ticks / preferred_min),
        )
        return (self._daycare_duration_plan(child),) + tuple(
            self._daycare_duration_plan_for_parts(
                child,
                parts,
                daily_max,
                preferred_min,
            )
            for parts in range(minimum_parts + 1, maximum_parts + 1)
        )

    def _daycare_duration_plan(self, child: V3Child) -> tuple[int, ...]:
        daily_max = min(
            108,
            self.config.operating_end_tick - self.config.operating_start_tick,
        )
        parts = ceil(child.claimed_ticks / daily_max)
        return self._daycare_duration_plan_for_parts(
            child,
            parts,
            daily_max,
            min(72, daily_max),
        )

    def _daycare_duration_plan_for_parts(
        self,
        child: V3Child,
        parts: int,
        daily_max: int,
        preferred_min: int,
    ) -> tuple[int, ...]:
        if child.claimed_ticks >= preferred_min * parts:
            durations = [preferred_min] * parts
            extra = child.claimed_ticks - preferred_min * parts
            distribution_order = sorted(
                range(parts),
                key=lambda index: self._seed_value(
                    child.child_id,
                    "duration",
                    str(parts),
                    str(index),
                ),
            )
            for index in distribution_order:
                addition = min(extra, daily_max - durations[index])
                durations[index] += addition
                extra -= addition
                if extra == 0:
                    break
        else:
            durations = [preferred_min] * (parts - 1)
            durations.append(child.claimed_ticks - sum(durations))
        indexed = tuple(enumerate(durations))
        return tuple(
            duration
            for index, duration in sorted(
                indexed,
                key=lambda item: self._seed_value(
                    child.child_id,
                    "duration-order",
                    str(parts),
                    str(item[0]),
                ),
            )
        )

    def _best_daycare_realism_pattern(
        self,
        child: V3Child,
        duration: int,
        occupancy: dict[str, list[int]],
        assigned_dates: set[str],
        part: int,
        daycare_load_by_date: dict[str, int],
        *,
        pressure_first: bool,
        canonical_anchor: int,
    ) -> CandidatePattern | None:
        operating_start = self.config.operating_start_tick
        operating_end = self.config.operating_end_tick
        reference_duration = min(108, operating_end - operating_start)
        anchor_span = max(0, operating_end - operating_start - reference_duration)
        anchor = operating_start + self._seed_value(child.child_id, "arrival-anchor") % (
            anchor_span + 1
        )
        choices: list[tuple[tuple[object, ...], CandidatePattern]] = []
        for current_date in eligible_dates(child, self.config):
            if current_date in assigned_dates:
                continue
            latest_start = operating_end - duration
            if latest_start < operating_start:
                continue
            if canonical_anchor:
                target = {
                    1: (operating_start + latest_start) // 2,
                    2: operating_start,
                    3: latest_start,
                }[canonical_anchor]
                date_rank = 0
            else:
                jitter = self._seed_value(child.child_id, current_date, "jitter") % 13 - 6
                target = min(latest_start, max(operating_start, anchor + jitter))
                date_rank = self._seed_value(child.child_id, current_date, "date", str(part))
            for start in range(operating_start, latest_start + 1):
                end = start + duration
                segment = occupancy[current_date][start:end]
                if any(value >= self.config.capacity for value in segment):
                    continue
                pattern = CandidatePattern(
                    child_id=child.child_id,
                    date=current_date,
                    blocks=(TimeBlock(start, end),),
                    kind="daycare",
                )
                pressure = sum(segment)
                anchor_distance = abs(start - target)
                key = (
                    (
                        pressure,
                        daycare_load_by_date[current_date],
                        anchor_distance,
                        date_rank,
                        current_date,
                        start,
                    )
                    if pressure_first
                    else (
                        anchor_distance,
                        pressure,
                        daycare_load_by_date[current_date],
                        date_rank,
                        current_date,
                        start,
                    )
                )
                choices.append((key, pattern))
        return min(choices, key=lambda item: item[0])[1] if choices else None

    def _seed_value(self, *parts: str) -> int:
        material = "\x1f".join((self.config.realism_seed, *parts))
        return int.from_bytes(sha256(material.encode()).digest()[:8], "big")

    @staticmethod
    def _assignment_diffs(
        before: _Construction,
        after: _Construction,
        *,
        phase: str = "repair",
        iteration: int | None,
    ) -> tuple[VisualizationEvent, ...]:
        """Return only changes belonging to an accepted repair state.

        Assignments are unique per child/date. Exact survivors are removed first,
        then same-date changes are paired before cross-date moves. This gives a
        stable, compact diff even when a reorder rebuild changes several children.
        """

        before_by_child: dict[str, list[ScheduleAssignment]] = {}
        after_by_child: dict[str, list[ScheduleAssignment]] = {}
        for assignment in before.assignments:
            before_by_child.setdefault(assignment.child_id, []).append(assignment)
        for assignment in after.assignments:
            after_by_child.setdefault(assignment.child_id, []).append(assignment)

        events: list[VisualizationEvent] = []
        for child_id in sorted(set(before_by_child) | set(after_by_child)):
            old = sorted(before_by_child.get(child_id, ()), key=V3Scheduler._assignment_key)
            new = sorted(after_by_child.get(child_id, ()), key=V3Scheduler._assignment_key)

            unchanged = set(old) & set(new)
            old = [item for item in old if item not in unchanged]
            new = [item for item in new if item not in unchanged]

            pairs: list[tuple[ScheduleAssignment, ScheduleAssignment]] = []
            for old_item in tuple(old):
                same_date = next((item for item in new if item.date == old_item.date), None)
                if same_date is None:
                    continue
                pairs.append((old_item, same_date))
                old.remove(old_item)
                new.remove(same_date)
            while old and new:
                pairs.append((old.pop(0), new.pop(0)))

            for old_item, new_item in pairs:
                operation = (
                    "resize" if old_item.duration_ticks != new_item.duration_ticks else "move"
                )
                events.append(
                    VisualizationEvent(
                        phase=phase,  # type: ignore[arg-type]
                        operation=operation,
                        child_id=child_id,
                        from_date=old_item.date,
                        to_date=new_item.date,
                        from_blocks=old_item.blocks,
                        to_blocks=new_item.blocks,
                        before_shortfall_ticks=before.objective.total_shortfall_ticks,
                        after_shortfall_ticks=after.objective.total_shortfall_ticks,
                        iteration=iteration,
                    )
                )
            for old_item in old:
                events.append(
                    VisualizationEvent(
                        phase=phase,  # type: ignore[arg-type]
                        operation="remove",
                        child_id=child_id,
                        from_date=old_item.date,
                        to_date=None,
                        from_blocks=old_item.blocks,
                        to_blocks=(),
                        before_shortfall_ticks=before.objective.total_shortfall_ticks,
                        after_shortfall_ticks=after.objective.total_shortfall_ticks,
                        iteration=iteration,
                    )
                )
            for new_item in new:
                events.append(
                    VisualizationEvent(
                        phase=phase,  # type: ignore[arg-type]
                        operation="place",
                        child_id=child_id,
                        from_date=None,
                        to_date=new_item.date,
                        from_blocks=(),
                        to_blocks=new_item.blocks,
                        before_shortfall_ticks=before.objective.total_shortfall_ticks,
                        after_shortfall_ticks=after.objective.total_shortfall_ticks,
                        iteration=iteration,
                    )
                )
        return tuple(events)

    @staticmethod
    def _assignment_key(
        assignment: ScheduleAssignment,
    ) -> tuple[str, tuple[tuple[int, int], ...]]:
        return (
            assignment.date,
            tuple((block.start_tick, block.end_tick) for block in assignment.blocks),
        )

    def _reorder_lookahead_proposals(
        self,
        current: _Construction,
        order: tuple[str, ...],
        visited: set[tuple[str, ...]],
        budget: int,
    ) -> tuple[
        list[tuple[Objective, tuple[object, ...], tuple[str, ...], _Construction]],
        int,
        bool,
    ]:
        """Breadth-first search across equal-primary reorder plateaus.

        Reordering can merely transfer the same shortfall to another child. Those
        plateau states are never committed, but their newly short children define
        the next deterministic insertion neighbourhood. Only a construction with a
        strictly better complete Objective is returned to ``_repair`` for commit.
        """

        if budget <= 0:
            return [], 0, True
        baseline_primary = self._primary_objective(current.objective)
        queue = deque([(order, current, 0)])
        proposals: list[tuple[Objective, tuple[object, ...], tuple[str, ...], _Construction]] = []
        reconstructions = 0
        exhausted = False
        while queue:
            state_order, state, depth = queue.popleft()
            short_ids = sorted(
                (
                    child.child_id
                    for child in self.children
                    if state.scheduled[child.child_id] < child.claimed_ticks
                ),
                key=lambda child_id: (
                    -(self.child_map[child_id].claimed_ticks - state.scheduled[child_id]),
                    child_id,
                ),
            )
            for child_id, insertion_position, proposal_order in self._insertion_orders(
                state_order, short_ids
            ):
                if proposal_order in visited:
                    continue
                if reconstructions >= budget:
                    exhausted = True
                    break
                visited.add(proposal_order)
                candidate = self._construct(proposal_order)
                reconstructions += 1
                primary = self._primary_objective(candidate.objective)
                if candidate.objective < current.objective:
                    proposals.append(
                        (
                            candidate.objective,
                            (
                                0,
                                depth + 1,
                                child_id,
                                insertion_position,
                                *proposal_order,
                            ),
                            proposal_order,
                            candidate,
                        )
                    )
                if primary == baseline_primary:
                    queue.append((proposal_order, candidate, depth + 1))
            if exhausted:
                break
        return proposals, reconstructions, exhausted

    @staticmethod
    def _primary_objective(objective: Objective) -> tuple[int, int, int, int]:
        return (
            objective.hard_violations,
            objective.total_shortfall_ticks,
            objective.worst_shortfall_ticks,
            objective.daily_unique_deviation,
        )

    @staticmethod
    def _insertion_orders(
        order: tuple[str, ...], short_ids: list[str]
    ) -> Iterable[tuple[str, int, tuple[str, ...]]]:
        """Yield nearby insertion positions fairly across all short children.

        Intermediate positions can resize later children's greedy assignments in a
        way that moving the short child all the way to the front cannot. Each short
        child gets its nearest alternative before any gets a second one.
        """

        alternatives: list[list[tuple[str, int, tuple[str, ...]]]] = []
        for child_id in short_ids:
            current_position = order.index(child_id)
            remainder = tuple(item for item in order if item != child_id)
            positions = sorted(
                (position for position in range(len(order)) if position != current_position),
                key=lambda position: (abs(position - current_position), position),
            )
            alternatives.append(
                [
                    (
                        child_id,
                        position,
                        remainder[:position] + (child_id,) + remainder[position:],
                    )
                    for position in positions
                ]
            )

        for rank in range(max((len(items) for items in alternatives), default=0)):
            for items in alternatives:
                if rank < len(items):
                    yield items[rank]

    def _relocation_proposals(
        self,
        current: _Construction,
        short_ids: list[str],
        order: tuple[str, ...],
    ) -> tuple[
        list[tuple[Objective, tuple[object, ...], tuple[str, ...], _Construction]],
        bool,
    ]:
        """Move one blocking assignment, then fill a short child's freed capacity.

        This is deliberately a bounded one-hop neighbourhood: one existing assignment
        may move to another legal pattern of the same duration, and one short child may
        gain one new assignment.  Every returned construction is hard-valid and strictly
        improves the complete objective, so repair can never trade one child's shortfall
        for another's or cycle on an equal solution.
        """

        if not short_ids:
            return [], False
        occupancy = self._occupancy(current.assignments)
        assigned_dates: dict[str, set[str]] = {
            child_id: {
                assignment.date
                for assignment in current.assignments
                if assignment.child_id == child_id
            }
            for child_id in self.child_map
        }
        proposals: list[tuple[Objective, tuple[object, ...], tuple[str, ...], _Construction]] = []
        examined = 0
        search_limit = max(128, min(50_000, max(1, self.config.max_repair_iterations) * 512))

        for short_id in short_ids:
            short_child = self.child_map[short_id]
            remaining = short_child.claimed_ticks - current.scheduled[short_id]
            eligible = tuple(
                current_date
                for current_date in eligible_dates(short_child, self.config)
                if current_date not in assigned_dates[short_id]
            )
            maximum = max(
                (
                    min(remaining, max_daily_ticks(short_child, self.config, current_date))
                    for current_date in eligible
                ),
                default=0,
            )
            for duration in range(maximum, 0, -1):
                for current_date in eligible:
                    for insertion in enumerate_candidate_patterns(
                        short_child, self.config, current_date, duration
                    ):
                        examined += 1
                        if examined > search_limit:
                            return proposals, True
                        blockers = self._blocking_assignment_indexes(
                            current.assignments, occupancy, insertion
                        )
                        for blocker_index in blockers:
                            blocker = current.assignments[blocker_index]
                            blocker_child = self.child_map[blocker.child_id]
                            without_blocker = self._copy_occupancy(occupancy)
                            self._reserve_assignment(without_blocker, blocker, -1)
                            if not self._available(without_blocker, insertion):
                                continue
                            self._reserve(without_blocker, insertion, 1)
                            blocker_dates = assigned_dates[blocker.child_id] - {blocker.date}
                            for relocation_date in eligible_dates(blocker_child, self.config):
                                if relocation_date in blocker_dates:
                                    continue
                                for relocation in enumerate_candidate_patterns(
                                    blocker_child,
                                    self.config,
                                    relocation_date,
                                    blocker.duration_ticks,
                                ):
                                    examined += 1
                                    if examined > search_limit:
                                        return proposals, True
                                    if (
                                        relocation.date == blocker.date
                                        and relocation.blocks == blocker.blocks
                                    ):
                                        continue
                                    if not self._available(without_blocker, relocation):
                                        continue
                                    assignments = list(current.assignments)
                                    assignments.pop(blocker_index)
                                    assignments.extend(
                                        (
                                            ScheduleAssignment(
                                                insertion.child_id,
                                                insertion.date,
                                                insertion.blocks,
                                                insertion.kind,
                                            ),
                                            ScheduleAssignment(
                                                relocation.child_id,
                                                relocation.date,
                                                relocation.blocks,
                                                relocation.kind,
                                            ),
                                        )
                                    )
                                    canonical = self._canonical_assignments(assignments)
                                    scheduled = dict(current.scheduled)
                                    scheduled[short_id] += insertion.duration_ticks
                                    candidate = _Construction(
                                        canonical,
                                        scheduled,
                                        self._objective(canonical, scheduled),
                                    )
                                    if candidate.objective >= current.objective:
                                        continue
                                    if self._hard_violations(candidate.assignments):
                                        continue
                                    insertion_key = tuple(
                                        (block.start_tick, block.end_tick)
                                        for block in insertion.blocks
                                    )
                                    relocation_key = tuple(
                                        (block.start_tick, block.end_tick)
                                        for block in relocation.blocks
                                    )
                                    move_key: tuple[object, ...] = (
                                        1,
                                        short_id,
                                        insertion.date,
                                        insertion_key,
                                        blocker.child_id,
                                        blocker.date,
                                        relocation.date,
                                        relocation_key,
                                    )
                                    proposals.append(
                                        (candidate.objective, move_key, order, candidate)
                                    )
        return proposals, False

    def _occupancy(self, assignments: Iterable[ScheduleAssignment]) -> dict[str, list[int]]:
        occupancy = {
            current_date: [0] * self.config.operating_end_tick
            for current_date in sorted(self.config.open_dates)
        }
        for assignment in assignments:
            self._reserve_assignment(occupancy, assignment, 1)
        return occupancy

    def _blocking_assignment_indexes(
        self,
        assignments: tuple[ScheduleAssignment, ...],
        occupancy: dict[str, list[int]],
        pattern: CandidatePattern,
    ) -> tuple[int, ...]:
        saturated = {
            tick
            for block in pattern.blocks
            for tick in range(block.start_tick, block.end_tick)
            if occupancy[pattern.date][tick] >= self.config.capacity
        }
        if not saturated:
            return ()
        return tuple(
            index
            for index, assignment in enumerate(assignments)
            if assignment.date == pattern.date
            and any(
                tick in saturated
                for block in assignment.blocks
                for tick in range(block.start_tick, block.end_tick)
            )
        )

    @staticmethod
    def _copy_occupancy(
        occupancy: dict[str, list[int]],
    ) -> dict[str, list[int]]:
        return {current_date: ticks.copy() for current_date, ticks in occupancy.items()}

    @staticmethod
    def _reserve_assignment(
        occupancy: dict[str, list[int]], assignment: ScheduleAssignment, amount: int
    ) -> None:
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                occupancy[assignment.date][tick] += amount

    def _objective(
        self, assignments: tuple[ScheduleAssignment, ...], scheduled: dict[str, int]
    ) -> Objective:
        shortfalls = [
            max(0, child.claimed_ticks - scheduled[child.child_id]) for child in self.children
        ]
        unique = self._daily_unique_counts(assignments)
        target = self.config.daily_unique_target
        deviation = (
            sum(abs(unique.get(item, 0) - target) for item in self.config.open_dates)
            if target is not None
            else 0
        )
        canonical_key = tuple(
            (
                assignment.child_id,
                assignment.date,
                tuple((block.start_tick, block.end_tick) for block in assignment.blocks),
            )
            for assignment in assignments
        )
        return Objective(0, sum(shortfalls), max(shortfalls, default=0), deviation, canonical_key)

    def _hard_violations(self, assignments: tuple[ScheduleAssignment, ...]) -> tuple[str, ...]:
        violations: list[str] = []
        totals = dict.fromkeys(self.child_map, 0)
        seen: set[tuple[str, str]] = set()
        occupancy = {
            current_date: [0] * self.config.operating_end_tick
            for current_date in self.config.open_dates
        }
        for assignment in assignments:
            child = self.child_map.get(assignment.child_id)
            if child is None:
                violations.append(f"unknown_child:{assignment.child_id}")
                continue
            key = (assignment.child_id, assignment.date)
            if key in seen:
                violations.append(f"duplicate_child_date:{assignment.child_id}:{assignment.date}")
            seen.add(key)
            if assignment.date not in eligible_dates(child, self.config):
                violations.append(f"ineligible_date:{assignment.child_id}:{assignment.date}")
                continue
            windows = care_windows(child, self.config, assignment.date)
            for block in assignment.blocks:
                if not any(
                    start <= block.start_tick < block.end_tick <= end for start, end in windows
                ):
                    violations.append(f"illegal_window:{assignment.child_id}:{assignment.date}")
                for tick in range(block.start_tick, block.end_tick):
                    occupancy[assignment.date][tick] += 1
                    if occupancy[assignment.date][tick] > self.config.capacity:
                        violations.append(f"capacity:{assignment.date}:{tick}")
            totals[assignment.child_id] += assignment.duration_ticks
        for child_id, total in totals.items():
            if total > self.child_map[child_id].claimed_ticks:
                violations.append(f"overclaim:{child_id}")
        return tuple(sorted(set(violations)))

    def _available(self, occupancy: dict[str, list[int]], pattern: CandidatePattern) -> bool:
        return all(
            occupancy[pattern.date][tick] < self.config.capacity
            for block in pattern.blocks
            for tick in range(block.start_tick, block.end_tick)
        )

    @staticmethod
    def _reserve(occupancy: dict[str, list[int]], pattern: CandidatePattern, amount: int) -> None:
        for block in pattern.blocks:
            for tick in range(block.start_tick, block.end_tick):
                occupancy[pattern.date][tick] += amount

    @staticmethod
    def _canonical_assignments(
        assignments: Iterable[ScheduleAssignment],
    ) -> tuple[ScheduleAssignment, ...]:
        return tuple(
            sorted(
                assignments,
                key=lambda item: (
                    item.child_id,
                    item.date,
                    tuple((block.start_tick, block.end_tick) for block in item.blocks),
                ),
            )
        )

    @staticmethod
    def _daily_unique_counts(
        assignments: Iterable[ScheduleAssignment],
    ) -> dict[str, int]:
        children_by_date: dict[str, set[str]] = {}
        for assignment in assignments:
            children_by_date.setdefault(assignment.date, set()).add(assignment.child_id)
        return {
            current_date: len(child_ids) for current_date, child_ids in children_by_date.items()
        }

    @staticmethod
    def _trace(phase: str, action: str, **details: object) -> PhaseTrace:
        return PhaseTrace(
            phase,
            action,
            tuple(sorted((key, str(value)) for key, value in details.items())),
        )
