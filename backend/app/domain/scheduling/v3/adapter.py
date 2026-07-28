"""Explicit adapter from legacy scheduling contracts to the isolated V3 core."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from uuid import uuid4

from app.domain.random import SeededRandom
from app.domain.scheduling.fairness import FairnessCalculator
from app.domain.scheduling.types import (
    ChildPreferences,
    ChildProfile,
    DailyUtilization,
    ScheduleEntry,
    SchedulerConfig,
    ScheduleResult,
    SchedulerUtilizationReport,
    ScheduleStats,
    ScheduleWarning,
    SchedulingAuditEntry,
    SchedulingDecision,
    SchedulingGoals,
    TimeGap,
)

from .auditor import V3AuditReport, audit_schedule_result
from .engine import V3Scheduler
from .types import TICK_MINUTES, ScheduleAssignment, V3Child, V3Config, V3ScheduleResult

_TICKS_PER_HOUR = 60 // TICK_MINUTES
_ALGORITHM_VERSION = "3.0-isolated-adapter"


class V3LegacyAdapter:
    """Run V3 from legacy inputs and return a complete legacy result."""

    def __init__(self, config: SchedulerConfig, child_profiles: Iterable[ChildProfile]) -> None:
        self.legacy_config = config
        self.profiles = tuple(sorted(child_profiles, key=lambda child: child.id))
        identifiers = [child.id for child in self.profiles]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("child profiles cannot contain duplicate IDs")
        self._validate_unsupported_inputs()
        self.warnings: list[ScheduleWarning] = []
        self.normalized_profiles, self.v3_children = self._normalize_children()
        self.realism_seed = (
            config.seed
            or sha256(
                repr(
                    (
                        tuple(sorted(config.open_days)),
                        tuple(sorted(config.school_off_days)),
                        config.capacity,
                        config.operating_hours,
                        self.v3_children,
                    )
                ).encode()
            ).hexdigest()
        )
        self.v3_config = self._v3_config()
        self._append_informational_warnings()
        self.input_hash = self._input_hash()
        self.seed = config.seed or f"v3-{self.input_hash[:16]}"
        first_date = date.fromisoformat(self.v3_config.open_dates[0])
        self.audit_timestamp = datetime.combine(first_date, time.min, tzinfo=UTC)

    def execute(self) -> ScheduleResult:
        v3_result = V3Scheduler(self.v3_config, self.v3_children).execute()
        audit = audit_schedule_result(
            v3_result,
            self.v3_children,
            self.v3_config,
            require_exact_claims=v3_result.feasibility.feasible,
        )
        if not audit.valid:
            codes = ",".join(issue.code for issue in audit.violations)
            raise RuntimeError(f"V3 independent audit failed; refusing translation: {codes}")

        if not v3_result.feasibility.feasible:
            if "DAYCARE_REALISM_PLACEMENT_FAILED" in v3_result.feasibility.reasons:
                self._append_daycare_realism_warning_once(v3_result)
            else:
                self._append_incomplete_warning_once(v3_result, audit)
        entries = self._entries(v3_result.assignments)
        fairness = FairnessCalculator(
            self.normalized_profiles,
            SeededRandom(f"{self.seed}-fairness"),
        ).generate_report(entries)
        utilization = self._utilization(v3_result.assignments)
        audit_trail = self._audit_trail(v3_result, audit)
        stats = self._stats(entries, audit)
        visualization = self._visualization(v3_result, audit)
        return ScheduleResult(
            batch_id=f"v3-{uuid4()}",
            generated_at=datetime.now(UTC),
            seed=self.seed,
            algorithm_version=_ALGORITHM_VERSION,
            input_hash=self.input_hash,
            entries=entries,
            fairness_report=fairness,
            utilization_report=utilization,
            audit_trail=audit_trail,
            warnings=tuple(self.warnings),
            stats=stats,
            visualization=visualization,
        )

    def _validate_unsupported_inputs(self) -> None:
        unknown_school_off = set(self.legacy_config.school_off_days) - set(
            self.legacy_config.open_days
        )
        if unknown_school_off:
            values = ",".join(sorted(unknown_school_off))
            raise ValueError(f"school_off_days must be open_days for V3: {values}")
        if self.legacy_config.child_time_overrides:
            raise ValueError("V3 does not support child_time_overrides; refusing to drop them")
        hard_fields = (
            "start_time_1",
            "end_time_1",
            "start_time_2",
            "end_time_2",
        )
        affected = tuple(
            child.id
            for child in self.profiles
            if child.preferences
            and any(
                bool((getattr(child.preferences, field) or "").strip()) for field in hard_fields
            )
        )
        if affected:
            raise ValueError(
                "V3 does not support hard custom preference session blocks for: "
                + ",".join(affected)
            )

    def _normalize_children(
        self,
    ) -> tuple[tuple[ChildProfile, ...], tuple[V3Child, ...]]:
        normalized_profiles: list[ChildProfile] = []
        v3_children: list[V3Child] = []
        for profile in self.profiles:
            source_hours = Decimal(str(profile.total_claimed_hours))
            if not source_hours.is_finite() or source_hours < 0:
                raise ValueError(
                    f"total_claimed_hours must be finite and non-negative for {profile.id}"
                )
            raw_ticks = source_hours * _TICKS_PER_HOUR
            ticks = int(raw_ticks.to_integral_value(rounding=ROUND_HALF_UP))
            normalized_hours = Decimal(ticks) / Decimal(_TICKS_PER_HOUR)
            normalized_profiles.append(
                replace(profile, total_claimed_hours=float(normalized_hours))
            )
            preferences = profile.preferences or ChildPreferences()
            v3_children.append(
                V3Child(
                    child_id=profile.id,
                    care_type=profile.care_type,
                    claimed_ticks=ticks,
                    enrollment_date=profile.enrollment_date,
                    excluded_dates=tuple(sorted(preferences.excluded_days)),
                )
            )
            if raw_ticks != raw_ticks.to_integral_value():
                self.warnings.append(
                    ScheduleWarning(
                        severity="warning",
                        code="V3_CLAIM_NORMALIZED_TO_FIVE_MINUTES",
                        message=(
                            f"{profile.name} claim source={_decimal_text(source_hours)}h "
                            f"normalized={_decimal_text(normalized_hours, 6)}h "
                            f"({ticks} five-minute ticks) using ROUND_HALF_UP."
                        ),
                        affected_children=(profile.id,),
                        suggestion="Review the normalized claim before persistence.",
                    )
                )
        return tuple(normalized_profiles), tuple(v3_children)

    def _v3_config(self) -> V3Config:
        daily_target = (
            self.legacy_config.daily_capacity_max
            if self.legacy_config.daily_capacity_max is not None
            else self.legacy_config.daily_capacity_min
        )
        return V3Config(
            open_dates=tuple(sorted(self.legacy_config.open_days)),
            capacity=self.legacy_config.capacity,
            school_off_dates=tuple(sorted(self.legacy_config.school_off_days)),
            operating_start_tick=self.legacy_config.operating_hours.start * _TICKS_PER_HOUR,
            operating_end_tick=self.legacy_config.operating_hours.end * _TICKS_PER_HOUR,
            daily_unique_target=daily_target,
            max_repair_iterations=self.legacy_config.max_iterations,
            realism_seed=self.realism_seed,
        )

    def _append_informational_warnings(self) -> None:
        if (
            self.legacy_config.daily_capacity_min is not None
            or self.legacy_config.daily_capacity_max is not None
        ):
            source = (
                "daily_capacity_max"
                if self.legacy_config.daily_capacity_max is not None
                else "daily_capacity_min"
            )
            self.warnings.append(
                ScheduleWarning(
                    "info",
                    "V3_DAILY_UNIQUE_TARGET_MAPPED",
                    (
                        f"V3 mapped {source}={self.v3_config.daily_unique_target} to its "
                        "soft daily unique-child target; it is not a hard capacity limit."
                        + (
                            f" daily_capacity_min={self.legacy_config.daily_capacity_min} "
                            "is not separately enforced."
                            if self.legacy_config.daily_capacity_min is not None
                            and self.legacy_config.daily_capacity_max is not None
                            else ""
                        )
                    ),
                )
            )

        soft_children = tuple(
            profile.id
            for profile in self.profiles
            if _has_ignored_soft_preferences(profile.preferences)
        )
        if soft_children:
            self.warnings.append(
                ScheduleWarning(
                    "info",
                    "V3_SOFT_PREFERENCES_NOT_APPLIED",
                    (
                        "V3 did not use preferred arrival/departure, preferred weekdays, "
                        "friend, or avoidance preferences. Excluded dates remain enforced."
                    ),
                    affected_children=soft_children,
                )
            )

        enabled = tuple(
            name
            for name, value in (
                ("predictions", self.legacy_config.enable_predictions),
                ("fairness optimization", self.legacy_config.enable_fairness_optimization),
                ("sibling coherence", self.legacy_config.enable_sibling_coherence),
            )
            if value
        )
        if enabled:
            self.warnings.append(
                ScheduleWarning(
                    "info",
                    "V3_LEGACY_TOGGLES_NOT_APPLIED",
                    "V3 construction does not apply legacy toggles: " + ", ".join(enabled) + ".",
                )
            )
        if not self.legacy_config.enable_audit_trail:
            self.warnings.append(
                ScheduleWarning(
                    "info",
                    "V3_AUDIT_ALWAYS_ENABLED",
                    "V3 independent audit remains enabled even though legacy audit was disabled.",
                )
            )
        if self.legacy_config.goals != SchedulingGoals():
            self.warnings.append(
                ScheduleWarning(
                    "info",
                    "V3_LEGACY_GOALS_NOT_APPLIED",
                    "V3 does not apply legacy weighted optimization goals.",
                )
            )

    def _append_incomplete_warning_once(
        self, result: V3ScheduleResult, audit: V3AuditReport
    ) -> None:
        if any(item.code == "V3_INCOMPLETE_NOT_PERSISTABLE" for item in self.warnings):
            return
        short_ids = tuple(child_id for child_id, ticks in audit.shortfall_ticks_by_child if ticks)
        shortfall_ticks = sum(ticks for _, ticks in audit.shortfall_ticks_by_child)
        names = {profile.id: profile.name for profile in self.normalized_profiles}
        shortfall_details = ", ".join(
            f"{names.get(child_id, child_id)} ({_hours(ticks):.1f}h short)"
            for child_id, ticks in audit.shortfall_ticks_by_child
            if ticks
        )
        aggregate_reasons = tuple(
            reason
            for reason in result.feasibility.reasons
            if not reason.startswith("CHILD_WINDOW_SHORTAGE:")
        )
        reason_summary = (
            f"{len(short_ids)} child claim(s) exceed their eligible attendance windows: "
            f"{shortfall_details}"
        )
        if aggregate_reasons:
            reason_summary += ". Additional bounds: " + ", ".join(aggregate_reasons)
        saturated_dates = tuple(
            peak.date for peak in audit.capacity_peaks if peak.occupancy >= self.v3_config.capacity
        )
        self.warnings.append(
            ScheduleWarning(
                "critical",
                "V3_INCOMPLETE_NOT_PERSISTABLE",
                (
                    f"V3 schedule is incomplete by {shortfall_ticks} ticks "
                    f"({_hours(shortfall_ticks):.6f}h). {reason_summary}. "
                    "This result is identifiable as unsafe for persistence."
                ),
                affected_children=short_ids,
                affected_dates=saturated_dates,
                suggestion=(
                    "Do not persist; review the named claims and school-off dates, then regenerate."
                ),
            )
        )

    def _append_daycare_realism_warning_once(self, result: V3ScheduleResult) -> None:
        if any(
            item.code == "V3_DAYCARE_REALISM_NOT_PERSISTABLE" for item in self.warnings
        ):
            return
        rollback = next(
            (
                item
                for item in result.trace
                if item.phase == "daycare_realism" and item.action == "rolled_back"
            ),
            None,
        )
        details = dict(rollback.details) if rollback else {}
        child_id = details.get("child_id")
        names = {profile.id: profile.name for profile in self.normalized_profiles}
        child_label = names.get(child_id, child_id) if child_id else None
        context = f" The first blocked claim was {child_label}." if child_label else ""
        self.warnings.append(
            ScheduleWarning(
                "critical",
                "V3_DAYCARE_REALISM_NOT_PERSISTABLE",
                (
                    "V3 reached the exact raw claim total, but Daycare realism could not "
                    "relocate every tick into capacity-safe days of nine hours or less. "
                    "The reshaping transaction was rolled back and the raw allocation is "
                    f"diagnostic only; nothing may be persisted or exported.{context}"
                ),
                affected_children=(child_id,) if child_id else (),
                suggestion=(
                    "Add eligible open dates or capacity, adjust exclusions, then regenerate."
                ),
            )
        )

    def _entries(self, assignments: tuple[ScheduleAssignment, ...]) -> tuple[ScheduleEntry, ...]:
        names = {profile.id: profile.name for profile in self.normalized_profiles}
        entries: list[ScheduleEntry] = []
        for assignment in assignments:
            first = assignment.blocks[0]
            second = assignment.blocks[1] if len(assignment.blocks) == 2 else None
            entries.append(
                ScheduleEntry(
                    child_id=assignment.child_id,
                    date=assignment.date,
                    start_time=_time_text(first.start_tick),
                    end_time=_time_text(first.end_tick),
                    hours=_hours(assignment.duration_ticks),
                    decision=SchedulingDecision(
                        timestamp=self.audit_timestamp,
                        reason="v3_exact_tick_assignment",
                        constraints_satisfied=(
                            "independent_v3_audit",
                            "five_minute_tick_grid",
                            f"care_pattern:{assignment.kind}",
                        ),
                        alternatives_considered=0,
                        confidence_score=1,
                        notes=(
                            f"duration_ticks={assignment.duration_ticks}",
                            "translated_without_time_rounding",
                        ),
                    ),
                    start_time_2=_time_text(second.start_tick) if second else None,
                    end_time_2=_time_text(second.end_tick) if second else None,
                    child_name=names[assignment.child_id],
                )
            )
        return tuple(entries)

    def _audit_trail(
        self, result: V3ScheduleResult, audit: V3AuditReport
    ) -> tuple[SchedulingAuditEntry, ...]:
        entries = [
            SchedulingAuditEntry(
                timestamp=self.audit_timestamp,
                action=f"v3_{item.phase}_{item.action}",
                details=dict(item.details),
                reason="V3 deterministic phase trace",
            )
            for item in result.trace
        ]
        # Do not duplicate every assignment here. The visualization event stream
        # is replayable and substantially more compact; this trail retains phase
        # and certification summaries for legacy consumers.
        entries.append(
            SchedulingAuditEntry(
                timestamp=self.audit_timestamp,
                action="v3_independent_audit_passed",
                details={
                    "requestedTicks": audit.requested_ticks,
                    "scheduledTicks": audit.scheduled_ticks,
                    "shortfallTicksByChild": audit.shortfall_ticks_by_child,
                    "capacityPeaks": tuple(
                        (peak.date, peak.occupancy, peak.first_tick)
                        for peak in audit.capacity_peaks
                    ),
                },
                reason="Independent V3 audit accepted the result for translation",
            )
        )
        return tuple(entries)

    def _visualization(self, result: V3ScheduleResult, audit: V3AuditReport) -> dict[str, object]:
        """Build the compact public V3 explanation payload.

        The stream contains committed construction and accepted repair changes
        only. Candidate-search attempts are intentionally omitted because they can
        number in the tens of thousands and never changed the schedule.
        """

        names = {profile.id: profile.name for profile in self.normalized_profiles}
        requested = {child.child_id: child.claimed_ticks for child in self.v3_children}
        scheduled = dict(audit.scheduled_ticks_by_child)
        peaks = {peak.date: peak for peak in audit.capacity_peaks}
        events: list[dict[str, object]] = []
        for sequence, event in enumerate(result.visualization_events):
            events.append(
                {
                    "sequence": sequence,
                    "phase": event.phase,
                    "operation": event.operation,
                    "childId": event.child_id,
                    "fromDate": event.from_date,
                    "toDate": event.to_date,
                    "fromBlocks": tuple(
                        (block.start_tick, block.end_tick) for block in event.from_blocks
                    ),
                    "toBlocks": tuple(
                        (block.start_tick, block.end_tick) for block in event.to_blocks
                    ),
                    "beforeShortfallTicks": event.before_shortfall_ticks,
                    "afterShortfallTicks": event.after_shortfall_ticks,
                    "iteration": event.iteration,
                }
            )
        return {
            "version": 1,
            "tickMinutes": TICK_MINUTES,
            "capacity": self.v3_config.capacity,
            "operatingWindow": (
                self.v3_config.operating_start_tick,
                self.v3_config.operating_end_tick,
            ),
            "phases": tuple(
                {
                    "phase": item.phase,
                    "action": item.action,
                    "details": dict(item.details),
                }
                for item in result.trace
            ),
            "events": tuple(events),
            "dailyCapacityPeaks": tuple(
                {
                    "date": current_date,
                    "occupancy": peaks[current_date].occupancy if current_date in peaks else 0,
                    "firstTick": (
                        peaks[current_date].first_tick
                        if current_date in peaks
                        else self.v3_config.operating_start_tick
                    ),
                    "capacity": self.v3_config.capacity,
                }
                for current_date in self.v3_config.open_dates
            ),
            "children": tuple(
                {
                    "childId": child.child_id,
                    "childName": names[child.child_id],
                    "requestedTicks": requested[child.child_id],
                    "scheduledTicks": scheduled.get(child.child_id, 0),
                }
                for child in self.v3_children
            ),
            "certification": {
                "auditValid": audit.valid,
                "exactClaims": not audit.shortfall_ticks_by_child,
                "feasible": result.feasibility.feasible,
                "proven": result.feasibility.proven,
                "violationCodes": tuple(issue.code for issue in audit.violations),
                "reasons": result.feasibility.reasons,
                "requestedTicks": audit.requested_ticks,
                "scheduledTicks": audit.scheduled_ticks,
            },
        }

    def _utilization(
        self, assignments: tuple[ScheduleAssignment, ...]
    ) -> SchedulerUtilizationReport:
        start = self.v3_config.operating_start_tick
        end = self.v3_config.operating_end_tick
        capacity_ticks = (end - start) * self.v3_config.capacity
        daily: list[DailyUtilization] = []
        for current_date in self.v3_config.open_dates:
            occupancy = [0] * (end - start)
            children: set[str] = set()
            for assignment in assignments:
                if assignment.date != current_date:
                    continue
                children.add(assignment.child_id)
                for block in assignment.blocks:
                    for tick in range(block.start_tick, block.end_tick):
                        occupancy[tick - start] += 1
            used_ticks = sum(occupancy)
            peak = max(occupancy, default=0)
            peak_offset = next((index for index, value in enumerate(occupancy) if value == peak), 0)
            daily.append(
                DailyUtilization(
                    date=current_date,
                    day_of_week=date.fromisoformat(current_date).isoweekday() % 7,
                    capacity_hours=_hours(capacity_ticks),
                    scheduled_hours=_hours(used_ticks),
                    utilization=used_ticks / capacity_ticks if capacity_ticks else 0,
                    children_count=len(children),
                    peak_hour=_time_text(start + peak_offset),
                    gaps=_gaps(occupancy, start, self.v3_config.capacity),
                )
            )
        total_used = sum(item.scheduled_hours for item in daily)
        total_capacity = sum(item.capacity_hours for item in daily)
        peak_days = tuple(
            item.date for item in sorted(daily, key=lambda item: (-item.utilization, item.date))[:3]
        )
        low_days = tuple(
            item.date for item in sorted(daily, key=lambda item: (item.utilization, item.date))[:3]
        )
        return SchedulerUtilizationReport(
            overall_utilization=total_used / total_capacity if total_capacity else 0,
            daily_utilization=tuple(daily),
            peak_days=peak_days,
            low_days=low_days,
            average_children_per_day=(
                sum(item.children_count for item in daily) / len(daily) if daily else 0
            ),
            revenue_projection=0,
        )

    def _stats(self, entries: tuple[ScheduleEntry, ...], audit: V3AuditReport) -> ScheduleStats:
        total_hours = _hours(audit.scheduled_ticks)
        requested_hours = _hours(audit.requested_ticks)
        child_ids = {entry.child_id for entry in entries}
        unscheduled = sum(scheduled == 0 for _, scheduled in audit.scheduled_ticks_by_child)
        shortfall = _hours(sum(ticks for _, ticks in audit.shortfall_ticks_by_child))
        completion = total_hours / requested_hours * 100 if requested_hours else 100
        capacity_issue_dates = {
            peak.date
            for peak in audit.capacity_peaks
            if audit.shortfall_ticks_by_child and peak.occupancy >= self.v3_config.capacity
        }
        return ScheduleStats(
            total_entries=len(entries),
            total_hours_scheduled=total_hours,
            children_scheduled=len(child_ids),
            average_hours_per_child=(total_hours / len(child_ids) if child_ids else 0),
            days_with_capacity_issues=len(capacity_issue_dates),
            constraint_violations=len(audit.violations),
            optimization_score=completion,
            requested_children=len(self.v3_children),
            requested_hours=requested_hours,
            unscheduled_children=unscheduled,
            hours_shortfall=shortfall,
            completion_percentage=completion,
        )

    def _input_hash(self) -> str:
        canonical = (
            self.v3_config,
            self.v3_children,
            tuple(
                (
                    profile.id,
                    profile.name,
                    profile.family_id,
                    profile.total_claimed_hours,
                    _canonical_preferences(profile.preferences),
                )
                for profile in self.normalized_profiles
            ),
            self.legacy_config.enable_predictions,
            self.legacy_config.enable_fairness_optimization,
            self.legacy_config.enable_sibling_coherence,
            self.legacy_config.enable_audit_trail,
            self.legacy_config.goals,
        )
        return sha256(repr(canonical).encode()).hexdigest()


def execute_v3_schedule(
    config: SchedulerConfig, child_profiles: Iterable[ChildProfile]
) -> ScheduleResult:
    """Convenience entry point for the isolated V3-to-legacy adapter."""

    return V3LegacyAdapter(config, child_profiles).execute()


def _has_ignored_soft_preferences(preferences: ChildPreferences | None) -> bool:
    if preferences is None:
        return False
    return bool(
        preferences.preferred_arrival_time
        or preferences.preferred_departure_time
        or preferences.preferred_days
        or preferences.friend_ids
        or preferences.avoid_child_ids
    )


def _canonical_preferences(preferences: ChildPreferences | None) -> object:
    if preferences is None:
        return None
    return (
        preferences.preferred_arrival_time,
        preferences.preferred_departure_time,
        tuple(sorted(preferences.preferred_days)),
        tuple(sorted(preferences.excluded_days)),
        tuple(sorted(preferences.friend_ids)),
        tuple(sorted(preferences.avoid_child_ids)),
    )


def _gaps(occupancy: list[int], start_tick: int, capacity: int) -> tuple[TimeGap, ...]:
    gaps: list[TimeGap] = []
    gap_start: int | None = None
    for index, used in enumerate((*occupancy, capacity)):
        has_unused_capacity = used < capacity
        if has_unused_capacity and gap_start is None:
            gap_start = index
        elif not has_unused_capacity and gap_start is not None:
            if index - gap_start >= 6:
                unused_ticks = sum(capacity - value for value in occupancy[gap_start:index])
                gaps.append(
                    TimeGap(
                        start_time=_time_text(start_tick + gap_start),
                        end_time=_time_text(start_tick + index),
                        unused_capacity=_hours(unused_ticks),
                    )
                )
            gap_start = None
    return tuple(gaps)


def _time_text(tick: int) -> str:
    total_minutes = tick * TICK_MINUTES
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def _hours(ticks: int) -> float:
    return ticks / _TICKS_PER_HOUR


def _decimal_text(value: Decimal, places: int | None = None) -> str:
    if places is not None:
        value = value.quantize(Decimal(1).scaleb(-places))
    return format(value, "f").rstrip("0").rstrip(".") or "0"
