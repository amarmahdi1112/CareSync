"""Deterministic V2 daycare and OSC scheduling pipeline."""

import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.domain.random import SeededRandom
from app.domain.scheduling.fairness import FairnessCalculator
from app.domain.scheduling.grid import TimeSlotGrid
from app.domain.scheduling.siblings import SiblingCoherence
from app.domain.scheduling.types import (
    ChildPreferences,
    ChildProfile,
    ChildTimeOverride,
    DailyUtilization,
    ScheduleEntry,
    SchedulerConfig,
    ScheduleResult,
    SchedulerUtilizationReport,
    ScheduleStats,
    ScheduleWarning,
    SchedulingAuditEntry,
    SchedulingDecision,
)


@dataclass(slots=True)
class _ChildState:
    profile: ChildProfile
    scheduled_hours: float = 0
    scheduled_days: list[str] | None = None

    def __post_init__(self) -> None:
        self.scheduled_days = []


class SchedulerAuditTrail:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.entries: list[SchedulingAuditEntry] = []

    def log(
        self,
        action: str,
        reason: str,
        details: dict[str, Any] | None = None,
        *,
        child_id: str | None = None,
        schedule_date: str | None = None,
    ) -> None:
        if self.enabled:
            self.entries.append(
                SchedulingAuditEntry(
                    datetime.now(UTC),
                    action,
                    details or {},
                    reason,
                    child_id,
                    schedule_date,
                )
            )

    def get_entries(self) -> tuple[SchedulingAuditEntry, ...]:
        return tuple(self.entries)


class SchedulerEngine:
    """Capacity-aware scheduling for continuous daycare and split-shift OSC care."""

    def __init__(self, config: SchedulerConfig, child_profiles: list[ChildProfile]) -> None:
        self.config = config
        self.seed = config.seed or f"v2-scheduler-{time.time_ns()}"
        self.random = SeededRandom(self.seed)
        identifiers = [child.id for child in child_profiles]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("child profiles cannot contain duplicate IDs")
        active = sorted(
            (child for child in child_profiles if child.total_claimed_hours > 0.1),
            key=lambda child: child.id,
        )
        self.input_hash = sha256(repr((config, active)).encode()).hexdigest()
        self.children = {child.id: _ChildState(child) for child in active}
        self.grids = {
            current_date: TimeSlotGrid(
                current_date,
                config.capacity,
                config.operating_hours.start,
                config.operating_hours.end,
            )
            for current_date in config.open_days
        }
        self.entries: list[ScheduleEntry] = []
        self.schedule_map: dict[str, list[ScheduleEntry]] = {}
        self.warnings: list[ScheduleWarning] = []
        self.audit = SchedulerAuditTrail(config.enable_audit_trail)
        self.siblings = SiblingCoherence(active)
        self.override_targets: dict[ChildTimeOverride, str] = {}
        for override in config.child_time_overrides:
            identifier = self._normalize_identifier(override.child_identifier)
            matches = {
                child.id
                for child in active
                if self._normalize_identifier(child.id) == identifier
                or self._normalize_identifier(child.name) == identifier
            }
            if len(matches) != 1:
                reason = "unknown" if not matches else "ambiguous"
                raise ValueError(
                    f"{reason} child time override identifier: {override.child_identifier}"
                )
            self.override_targets[override] = matches.pop()
        self.fairness = FairnessCalculator(active, SeededRandom(f"{self.seed}-fairness"))

    def execute(self) -> ScheduleResult:
        self.audit.log("execute_start", "Starting scheduling execution")
        self._check_capacity()
        assignments = self._distribute_days()
        self._schedule_assigned_days(assignments)
        if self.config.enable_fairness_optimization:
            self._fill_shortfalls()
        self._warn_for_daily_targets()
        self._warn_for_shortfalls()
        self._validate_invariants()
        self.audit.log(
            "execute_complete",
            "Scheduling execution completed",
            {"entriesCreated": len(self.entries), "warningsGenerated": len(self.warnings)},
        )
        return self._build_result()

    def _effective_max(self) -> int:
        # The daily target is a unique-child limit, while `capacity` is the
        # simultaneous room limit enforced independently by the time-slot grid.
        return self.config.daily_capacity_max or self.config.capacity

    def _effective_min(self) -> int:
        if self.config.daily_capacity_min is not None:
            return self.config.daily_capacity_min
        return math.floor(self._effective_max() * 0.7)

    def _check_capacity(self) -> None:
        total_days = len(self.config.open_days)
        child_days_needed = sum(
            math.ceil(
                state.profile.total_claimed_hours / (3 if state.profile.care_type == "OSC" else 7)
            )
            for state in self.children.values()
        )
        available = self._effective_max() * total_days
        if child_days_needed > available:
            shortage = child_days_needed - available
            self.warnings.append(
                ScheduleWarning(
                    "critical",
                    "CAPACITY_INSUFFICIENT",
                    (
                        f"Total child-days needed ({child_days_needed}) exceeds available "
                        f"slots ({available}). {shortage} more slots needed."
                    ),
                    suggestion="Increase daily capacity or add more open days",
                )
            )
        requested_hours = sum(state.profile.total_claimed_hours for state in self.children.values())
        capacity_hours = (
            self.config.capacity
            * (self.config.operating_hours.end - self.config.operating_hours.start)
            * total_days
        )
        if requested_hours > capacity_hours:
            shortage = requested_hours - capacity_hours
            self.warnings.append(
                ScheduleWarning(
                    "critical",
                    "CAPACITY_HOURS_INSUFFICIENT",
                    (
                        f"Requested care ({requested_hours:.1f}h) exceeds physical room "
                        f"capacity ({capacity_hours:.1f}h) by {shortage:.1f}h."
                    ),
                    suggestion="Increase room capacity, operating hours, or open days",
                )
            )

    def _distribute_days(self) -> dict[str, set[str]]:
        assignments = {child_id: set() for child_id in self.children}
        day_counts = dict.fromkeys(self.config.open_days, 0)
        total_days = len(self.config.open_days)
        maximum = self._effective_max()
        requirements = [
            (
                state.profile.id,
                min(
                    len(self._eligible_days(state.profile)),
                    math.ceil(
                        state.profile.total_claimed_hours
                        / (3 if state.profile.care_type == "OSC" else 7)
                    ),
                ),
            )
            for state in self.children.values()
        ]
        requirements.sort(key=lambda item: (-item[1], item[0]))
        available = maximum * total_days
        needed = sum(days for _, days in requirements)
        scale = min(1, available / needed) if needed else 1
        for child_id, days_needed in requirements:
            profile = self.children[child_id].profile
            count = max(1, math.floor(days_needed * scale + 0.5))
            eligible = self._eligible_days(profile)

            def preference_key(
                current_date: str,
                profile: ChildProfile = profile,
                child_id: str = child_id,
            ) -> tuple[int, int, int, int, str]:
                preferences = profile.preferences or ChildPreferences()
                day_of_week = date.fromisoformat(current_date).isoweekday() % 7
                avoid_conflicts = sum(
                    current_date in assignments.get(avoid_id, set())
                    for avoid_id in preferences.avoid_child_ids
                )
                # During distribution entries do not exist yet, so use the
                # assignments already made for earlier siblings.
                if self.config.enable_sibling_coherence:
                    assigned_siblings = self.siblings.get_siblings(child_id)
                    sibling_match = any(
                        current_date in assignments.get(sibling_id, set())
                        for sibling_id in assigned_siblings
                    )
                    has_assigned_sibling = any(
                        assignments.get(sibling_id) for sibling_id in assigned_siblings
                    )
                    sibling_penalty = int(has_assigned_sibling and not sibling_match)
                else:
                    sibling_penalty = 0
                preferred_penalty = int(
                    bool(preferences.preferred_days)
                    and day_of_week not in preferences.preferred_days
                )
                friend_penalty = int(
                    any(assignments.get(friend_id) for friend_id in preferences.friend_ids)
                    and not any(
                        current_date in assignments.get(friend_id, set())
                        for friend_id in preferences.friend_ids
                    )
                )
                return (
                    avoid_conflicts,
                    sibling_penalty + friend_penalty,
                    preferred_penalty,
                    day_counts[current_date],
                    current_date,
                )

            ordered = sorted(
                eligible,
                key=preference_key,
            )
            for current_date in ordered:
                if len(assignments[child_id]) >= count:
                    break
                if day_counts[current_date] < maximum:
                    assignments[child_id].add(current_date)
                    day_counts[current_date] += 1

        # Match the legacy balancing pass: raise low-load days toward the configured
        # floor by adding children with the fewest assigned days first.
        minimum = self._effective_min()
        for current_date in self.config.open_days:
            candidates = sorted(assignments, key=lambda child_id: len(assignments[child_id]))
            for child_id in candidates:
                if day_counts[current_date] >= min(minimum, maximum):
                    break
                if current_date in assignments[child_id]:
                    continue
                if current_date not in self._eligible_days(self.children[child_id].profile):
                    continue
                assignments[child_id].add(current_date)
                day_counts[current_date] += 1
        self.audit.log(
            "phase1_complete",
            "Day distribution complete",
            {"childCount": len(requirements), "scaleFactor": scale},
        )
        return assignments

    def _schedule_assigned_days(self, assignments: dict[str, set[str]]) -> None:
        budgets = {
            child_id: self.children[child_id].profile.total_claimed_hours / len(days)
            for child_id, days in assignments.items()
            if days
        }
        for current_date in self.config.open_days:
            states = [
                self.children[child_id]
                for child_id, assigned in assignments.items()
                if current_date in assigned
            ]
            for state in self.random.shuffle(states):
                budget = min(
                    budgets.get(state.profile.id, 8),
                    state.profile.total_claimed_hours - state.scheduled_hours,
                )
                if budget <= 0:
                    continue
                if state.profile.care_type == "OSC":
                    hours = self._schedule_osc(state, current_date, budget)
                else:
                    hours = self._schedule_daycare(state, current_date, budget)
                if hours:
                    state.scheduled_hours += hours
                    assert state.scheduled_days is not None
                    state.scheduled_days.append(current_date)
        self.audit.log(
            "phase3_complete",
            "Time scheduling complete",
            {"totalEntries": len(self.entries)},
        )

    def _schedule_daycare(self, state: _ChildState, current_date: str, budget: float) -> float:
        child = state.profile
        grid = self.grids[current_date]
        target = min(
            budget,
            self.config.operating_hours.end - self.config.operating_hours.start,
        )
        override = self._time_override(child, current_date)
        preferences = override or child.preferences or ChildPreferences()
        preferred = preferences.start_time_1 or preferences.preferred_arrival_time or "08:00"
        preferred_end = preferences.end_time_1 or preferences.preferred_departure_time
        if override and override.start_time_1 and override.end_time_1:
            # A manual override is a constraint, not a preference. Never silently
            # move it to another time when the requested block is unavailable.
            block_start = override.start_time_1
            block_end = override.end_time_1
        else:
            start = self._add_variance(preferred, 30, minimum=0)
            block = grid.find_best_block(target, start)
            if block is None:
                self._capacity_warning(child, current_date)
                return 0
            block_start, block_end = block
        if preferred_end and self._minutes(block_end) > self._minutes(preferred_end):
            block_end = preferred_end
        available_hours = self._hours(block_start, block_end)
        hours = min(available_hours, budget)
        if hours <= 0:
            self.warnings.append(
                ScheduleWarning(
                    "warning",
                    "INVALID_TIME_WINDOW",
                    f"No valid care window remains for {child.name} on {current_date}",
                    (child.id,),
                    (current_date,),
                    "Review the child's preferred arrival and departure times",
                )
            )
            return 0
        if available_hours > hours:
            block_end = self._time(self._minutes(block_start) + hours * 60)
            hours = self._hours(block_start, block_end)
        if hours <= 0 or not grid.is_available(block_start, block_end):
            self._capacity_warning(child, current_date)
            return 0
        if not grid.reserve(child.id, block_start, block_end):
            return 0
        self._add_entry(child, current_date, block_start, block_end, hours)
        return hours

    def _schedule_osc(self, state: _ChildState, current_date: str, budget: float) -> float:
        if current_date in self.config.school_off_days:
            return self._schedule_daycare(state, current_date, min(budget, 9))
        child = state.profile
        grid = self.grids[current_date]
        override = self._time_override(child, current_date)
        preferences = override or child.preferences or ChildPreferences()
        random_value = self.random.next()
        morning = (
            bool(override.start_time_1 and override.end_time_1) if override else random_value < 0.95
        )
        afternoon = (
            bool(override.start_time_2 and override.end_time_2) if override else random_value > 0.05
        )
        day_of_week = date.fromisoformat(current_date).isoweekday() % 7
        first_start = first_end = second_start = second_end = ""
        if morning:
            arrival_minute = math.floor(self.random.next() * 45)
            departure_minute = 20 + math.floor(self.random.next() * 16)
            first_start = preferences.start_time_1 or f"07:{arrival_minute:02d}"
            first_end = preferences.end_time_1 or f"08:{departure_minute:02d}"
        if afternoon:
            if preferences.start_time_2:
                second_start = preferences.start_time_2
            elif day_of_week == 4:
                second_start = f"14:{30 + math.floor(self.random.next() * 25):02d}"
            else:
                minute = math.floor(self.random.next() * 30)
                second_start = f"{15 + minute // 60:02d}:{minute % 60:02d}"
            if preferences.end_time_2:
                second_end = preferences.end_time_2
            else:
                departure = self.random.next()
                second_end = (
                    "17:55" if departure < 0.5 else ("17:45" if departure < 0.8 else "18:00")
                )
        remaining = budget
        if morning:
            morning_hours = self._hours(first_start, first_end)
            if morning_hours <= 0:
                morning = False
            elif morning_hours > remaining:
                first_end = self._time(self._minutes(first_start) + remaining * 60)
                if self._minutes(first_end) <= self._minutes(first_start):
                    morning = False
                remaining = 0
            else:
                remaining -= morning_hours
        if afternoon:
            if remaining <= 0.01:
                afternoon = False
            else:
                afternoon_hours = self._hours(second_start, second_end)
                if afternoon_hours <= 0:
                    afternoon = False
                elif afternoon_hours > remaining:
                    second_end = self._time(self._minutes(second_start) + remaining * 60)
                    if self._minutes(second_end) <= self._minutes(second_start):
                        afternoon = False
                    remaining = 0
                else:
                    remaining -= afternoon_hours
        if not morning and not afternoon:
            return 0
        if morning and afternoon and self._minutes(second_start) < self._minutes(first_end):
            self.warnings.append(
                ScheduleWarning(
                    "warning",
                    "OVERLAPPING_TIME_BLOCKS",
                    f"Overlapping OSC time blocks were rejected for {child.name} on {current_date}",
                    (child.id,),
                    (current_date,),
                    "Review the child time override",
                )
            )
            return 0
        if morning and not grid.is_available(first_start, first_end):
            return 0
        if afternoon and not grid.is_available(second_start, second_end):
            return 0
        raw_hours = (self._hours(first_start, first_end) if morning else 0) + (
            self._hours(second_start, second_end) if afternoon else 0
        )
        if raw_hours <= 0:
            return 0
        if morning and not grid.reserve(child.id, first_start, first_end):
            return 0
        if afternoon and not grid.reserve(child.id, second_start, second_end):
            if morning:
                grid.release(child.id, first_start, first_end)
            return 0
        decision = self._decision("capacity_available", ("capacity", "osc_split_shift"))
        entry = ScheduleEntry(
            child.id,
            current_date,
            first_start if morning else second_start,
            first_end if morning else second_end,
            raw_hours,
            decision,
            second_start if morning and afternoon else None,
            second_end if morning and afternoon else None,
            child.name,
        )
        self._record_entry(entry)
        return raw_hours

    def _fill_shortfalls(self) -> None:
        maximum = self._effective_max()
        for _iteration in range(self.config.max_iterations):
            progress = False
            day_children = self._day_children()
            ordered = sorted(
                self.children.values(),
                key=lambda state: state.profile.total_claimed_hours - state.scheduled_hours,
                reverse=True,
            )
            for state in ordered:
                shortage = state.profile.total_claimed_hours - state.scheduled_hours
                if shortage <= 0.01:
                    continue
                for current_date in self.config.open_days:
                    if state.profile.id in day_children[current_date]:
                        continue
                    if len(day_children[current_date]) >= maximum:
                        continue
                    if current_date not in self._eligible_days(state.profile):
                        continue
                    target = min(
                        shortage,
                        4 if state.profile.care_type == "OSC" else 11.5,
                    )
                    if state.profile.care_type == "OSC":
                        hours = self._schedule_osc(state, current_date, target)
                    else:
                        hours = self._schedule_daycare(state, current_date, target)
                    if not hours:
                        continue
                    state.scheduled_hours += hours
                    assert state.scheduled_days is not None
                    state.scheduled_days.append(current_date)
                    day_children[current_date].add(state.profile.id)
                    progress = True
                    break
            if not progress:
                break

    def _warn_for_shortfalls(self) -> None:
        short = [
            state
            for state in self.children.values()
            if state.profile.total_claimed_hours - state.scheduled_hours > 0.5
        ]
        if not short:
            return
        shortage = sum(state.profile.total_claimed_hours - state.scheduled_hours for state in short)
        self.warnings.append(
            ScheduleWarning(
                "critical",
                "HOURS_NOT_MET",
                (
                    f"{len(short)} children did not receive full claimed hours; "
                    f"shortage {shortage:.1f}h"
                ),
                tuple(state.profile.id for state in short),
                suggestion="Increase daily capacity or add more operating days",
            )
        )

    def _warn_for_daily_targets(self) -> None:
        minimum = self._effective_min()
        if minimum <= 0:
            return
        day_children = self._day_children()
        missed = tuple(
            current_date
            for current_date, children in day_children.items()
            if len(children) < minimum
        )
        if missed:
            self.warnings.append(
                ScheduleWarning(
                    "warning",
                    "DAILY_TARGET_NOT_MET",
                    (
                        f"{len(missed)} open day(s) are below the daily target of "
                        f"{minimum} children."
                    ),
                    affected_dates=missed,
                    suggestion="Review demand, exclusions, and daily child targets",
                )
            )

    def _build_result(self) -> ScheduleResult:
        fairness = self.fairness.generate_report(self.entries)
        utilization = self._utilization()
        total_hours = sum(entry.hours for entry in self.entries)
        child_ids = {entry.child_id for entry in self.entries}
        requested_hours = sum(state.profile.total_claimed_hours for state in self.children.values())
        hours_shortfall = sum(
            max(0, state.profile.total_claimed_hours - state.scheduled_hours)
            for state in self.children.values()
        )
        optimization_score = max(
            0,
            min(
                100,
                100
                - len(self.warnings) * 2
                - sum(
                    min(
                        5,
                        max(0, state.profile.total_claimed_hours - state.scheduled_hours) / 10,
                    )
                    for state in self.children.values()
                ),
            ),
        )
        capacity_issue_dates = {
            warning_date
            for warning in self.warnings
            if "CAPACITY" in warning.code
            for warning_date in warning.affected_dates
        }
        return ScheduleResult(
            f"v2-{uuid4()}",
            datetime.now(UTC),
            self.seed,
            "2.1-safety",
            self.input_hash,
            tuple(self.entries),
            fairness,
            utilization,
            self.audit.get_entries(),
            tuple(self.warnings),
            ScheduleStats(
                len(self.entries),
                total_hours,
                len(child_ids),
                total_hours / len(child_ids) if child_ids else 0,
                len(capacity_issue_dates),
                sum(
                    warning.code in {"INVALID_TIME_WINDOW", "OVERLAPPING_TIME_BLOCKS"}
                    for warning in self.warnings
                ),
                optimization_score,
                len(self.children),
                requested_hours,
                len(self.children) - len(child_ids),
                hours_shortfall,
                (total_hours / requested_hours * 100) if requested_hours else 100,
            ),
        )

    def _utilization(self) -> SchedulerUtilizationReport:
        daily: list[DailyUtilization] = []
        operating_hours = self.config.operating_hours.end - self.config.operating_hours.start
        capacity_hours = operating_hours * self.config.capacity
        for current_date in self.config.open_days:
            entries = [entry for entry in self.entries if entry.date == current_date]
            scheduled = sum(entry.hours for entry in entries)
            children = {entry.child_id for entry in entries}
            daily.append(
                DailyUtilization(
                    current_date,
                    date.fromisoformat(current_date).isoweekday() % 7,
                    capacity_hours,
                    scheduled,
                    scheduled / capacity_hours if capacity_hours else 0,
                    len(children),
                    self.grids[current_date].get_peak_hour(),
                    self.grids[current_date].find_gaps(),
                )
            )
        total_scheduled = sum(item.scheduled_hours for item in daily)
        total_capacity = sum(item.capacity_hours for item in daily)
        ranked = sorted(daily, key=lambda item: item.utilization, reverse=True)
        return SchedulerUtilizationReport(
            total_scheduled / total_capacity if total_capacity else 0,
            tuple(daily),
            tuple(item.date for item in ranked[:3]),
            tuple(item.date for item in ranked[-3:]),
            sum(item.children_count for item in daily) / len(daily) if daily else 0,
            0,
        )

    def _add_entry(
        self,
        child: ChildProfile,
        current_date: str,
        start: str,
        end: str,
        hours: float,
        reason: str = "capacity_available",
    ) -> None:
        self._record_entry(
            ScheduleEntry(
                child.id,
                current_date,
                start,
                end,
                hours,
                self._decision(reason, ("capacity",)),
                child_name=child.name,
            )
        )

    def _record_entry(self, entry: ScheduleEntry) -> None:
        self.entries.append(entry)
        self.schedule_map.setdefault(entry.child_id, []).append(entry)
        self.audit.log(
            "schedule_decision",
            "scheduled",
            {"hours": entry.hours},
            child_id=entry.child_id,
            schedule_date=entry.date,
        )

    @staticmethod
    def _decision(reason: str, satisfied: tuple[str, ...]) -> SchedulingDecision:
        return SchedulingDecision(datetime.now(UTC), reason, satisfied)

    def _capacity_warning(self, child: ChildProfile, current_date: str) -> None:
        if any(
            warning.code == "CAPACITY_EXHAUSTED"
            and warning.affected_children == (child.id,)
            and warning.affected_dates == (current_date,)
            for warning in self.warnings
        ):
            return
        self.warnings.append(
            ScheduleWarning(
                "warning",
                "CAPACITY_EXHAUSTED",
                f"No capacity available for {child.name} on {current_date}",
                (child.id,),
                (current_date,),
                "Consider extending hours or increasing capacity",
            )
        )

    def _day_children(self) -> dict[str, set[str]]:
        result = {current_date: set() for current_date in self.config.open_days}
        for entry in self.entries:
            result[entry.date].add(entry.child_id)
        return result

    def _eligible_days(self, child: ChildProfile) -> tuple[str, ...]:
        excluded = set(child.preferences.excluded_days if child.preferences else ())
        enrolled_on = None
        if child.enrollment_date:
            try:
                enrolled_on = date.fromisoformat(child.enrollment_date)
            except ValueError as exc:
                raise ValueError(
                    f"invalid enrollment date for {child.name}: {child.enrollment_date}"
                ) from exc
        return tuple(
            current_date
            for current_date in self.config.open_days
            if current_date not in excluded
            and (enrolled_on is None or date.fromisoformat(current_date) >= enrolled_on)
        )

    def _validate_invariants(self) -> None:
        opening = self.config.operating_hours.start * 60
        closing = self.config.operating_hours.end * 60
        seen_child_days: set[tuple[str, str]] = set()
        totals = dict.fromkeys(self.children, 0.0)
        for entry in self.entries:
            if entry.child_id not in self.children:
                raise RuntimeError(f"schedule contains unknown child {entry.child_id}")
            if entry.date not in self.grids:
                raise RuntimeError(f"schedule contains closed date {entry.date}")
            child_day = (entry.child_id, entry.date)
            if child_day in seen_child_days:
                raise RuntimeError(
                    f"schedule contains duplicate attendance for {entry.child_id} on {entry.date}"
                )
            seen_child_days.add(child_day)
            blocks = [(entry.start_time, entry.end_time)]
            if entry.start_time_2 or entry.end_time_2:
                if not entry.start_time_2 or not entry.end_time_2:
                    raise RuntimeError("schedule contains an incomplete second time block")
                blocks.append((entry.start_time_2, entry.end_time_2))
            actual_hours = 0.0
            previous_end = None
            for start, end in blocks:
                start_minutes = self._minutes(start)
                end_minutes = self._minutes(end)
                if start_minutes < opening or end_minutes > closing or end_minutes <= start_minutes:
                    raise RuntimeError(
                        f"schedule contains invalid operating-hour block {start}-{end}"
                    )
                if previous_end is not None and start_minutes < previous_end:
                    raise RuntimeError("schedule contains overlapping time blocks")
                actual_hours += (end_minutes - start_minutes) / 60
                previous_end = end_minutes
            if abs(actual_hours - entry.hours) > 0.02:
                raise RuntimeError(
                    f"reported hours do not match time blocks for {entry.child_id} on {entry.date}"
                )
            totals[entry.child_id] += actual_hours
        for child_id, total in totals.items():
            claimed = self.children[child_id].profile.total_claimed_hours
            if total > claimed + 0.02:
                raise RuntimeError(
                    f"schedule exceeds claimed hours for {child_id}: {total:.2f} > {claimed:.2f}"
                )
        for grid in self.grids.values():
            if any(remaining < 0 for remaining in grid.slots):
                raise RuntimeError(f"schedule exceeds room capacity on {grid.date}")
            if any(len(occupants) > grid.capacity for occupants in grid.occupants):
                raise RuntimeError(f"schedule exceeds room occupancy on {grid.date}")

    def _time_override(self, child: ChildProfile, current_date: str) -> ChildPreferences | None:
        day_of_week = date.fromisoformat(current_date).isoweekday() % 7
        matches = [
            item
            for item in self.config.child_time_overrides
            if self.override_targets.get(item) == child.id
        ]
        selected = next(
            (item for item in matches if item.days_of_week and day_of_week in item.days_of_week),
            None,
        ) or next((item for item in matches if not item.days_of_week), None)
        if selected is None:
            return None
        base = child.preferences or ChildPreferences()
        return ChildPreferences(
            preferred_arrival_time=base.preferred_arrival_time,
            preferred_departure_time=base.preferred_departure_time,
            preferred_days=base.preferred_days,
            excluded_days=base.excluded_days,
            start_time_1=selected.start_time_1 or base.start_time_1,
            end_time_1=selected.end_time_1 or base.end_time_1,
            start_time_2=selected.start_time_2 or base.start_time_2,
            end_time_2=selected.end_time_2 or base.end_time_2,
            friend_ids=base.friend_ids,
            avoid_child_ids=base.avoid_child_ids,
        )

    @staticmethod
    def _normalize_identifier(value: str) -> str:
        return " ".join(value.casefold().split())

    def _add_variance(self, value: str, maximum: int, *, minimum: int) -> str:
        variance = math.floor((self.random.next() - 0.5) * 2 * maximum)
        return self._time(max(minimum, self._minutes(value) + variance))

    @staticmethod
    def _minutes(value: str) -> int:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)

    @staticmethod
    def _time(minutes: float) -> str:
        rounded = math.floor(minutes)
        return f"{rounded // 60:02d}:{rounded % 60:02d}"

    def _hours(self, start: str, end: str) -> float:
        return max(0, (self._minutes(end) - self._minutes(start)) / 60)

    def get_audit_trail(self) -> SchedulerAuditTrail:
        return self.audit
