"""Deterministic, fairness-aware V2 claim simulation engine."""

import math
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.domain.claims.audit import AuditTrail
from app.domain.claims.calendar import DaycareCalendar
from app.domain.claims.dates import AgeCalculator
from app.domain.claims.fairness import FairnessCalculator
from app.domain.claims.types import (
    AgeGroup,
    AttendanceDecision,
    BehavioralProfile,
    CalculationDetails,
    CapacityBottleneck,
    ClaimSimulationResult,
    ClaimSimulatorConfig,
    DailyUtilization,
    ProjectedClaim,
    SimulationChildInput,
    SimulationStats,
    UtilizationReport,
)
from app.domain.random import SeededRandom


def _round(value: float, places: int = 0) -> float:
    factor = 10**places
    return math.floor(value * factor + 0.5) / factor


@dataclass(slots=True)
class _ChildState:
    id: str
    name: str
    family_id: str
    care_category: str
    age_group: AgeGroup
    behavioral_profile: BehavioralProfile
    age_in_years: int
    age_in_months: int
    enrollment_date: str
    target_hours: float
    historical_debt: float
    base_hours_per_day: float = 8
    priority_score: float = 0
    scheduled_hours: float = 0
    scheduled_days: list[str] = field(default_factory=list)
    daily_hours: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    decisions: list[AttendanceDecision] = field(default_factory=list)


class ClaimSimulator:
    """Port of the private CareSync V2 claim simulator."""

    def __init__(self, config: ClaimSimulatorConfig) -> None:
        self.config = config
        self.calendar = DaycareCalendar(list(config.holidays), list(config.school_break_periods))
        self.seed = config.seed or f"v2-{config.year}-{config.month}"
        self.random = SeededRandom(self.seed)
        school_target = max(60, config.hour_tiers.school_age_full_day_target * 12)
        self.fairness = FairnessCalculator(
            max(100, config.hour_tiers.full_time_monthly_target),
            school_target,
            config.historical_data,
        )
        self.audit = AuditTrail(config.enable_audit_trail)
        self.children: dict[str, _ChildState] = {}
        self.daily_capacity: dict[str, float] = {}
        self.daily_consumed: dict[str, float] = {}
        self.category_capacity: dict[str, dict[AgeGroup, int]] = {}
        self.category_consumed: dict[str, dict[AgeGroup, int]] = {}
        self.bottlenecks: dict[str, dict[str, object]] = {}
        self.warnings: list[str] = []

    def run(self, child_inputs: list[SimulationChildInput]) -> ClaimSimulationResult:
        started = time.perf_counter()
        month_start = date(self.config.year, self.config.month, 1)
        month_end = date(
            self.config.year,
            self.config.month,
            monthrange(self.config.year, self.config.month)[1],
        )
        self._reset()
        self._initialize_children(child_inputs, month_start)
        business_days = self.calendar.get_business_days_in_range(month_start, month_end)
        self._initialize_capacity(business_days)
        self.audit.log_simulation_start(
            len(child_inputs),
            len(business_days),
            {
                "year": self.config.year,
                "month": self.config.month,
                "capacity": self.config.capacity,
                "fairnessEnabled": self.config.enable_fairness_optimization,
                "siblingCoherenceEnabled": self.config.enable_sibling_coherence,
            },
        )

        for current_date in business_days:
            self._process_day(current_date)

        iterations = 0
        if self.config.enable_fairness_optimization:
            iterations = self._optimize_for_fairness(business_days)

        claims = self._build_claims(len(business_days))
        fairness_report = self.fairness.generate_report(claims)
        utilization = self._build_utilization_report(business_days)
        elapsed_ms = (time.perf_counter() - started) * 1000
        total_hours = sum(claim.projected_hours for claim in claims)
        self.audit.log_simulation_end(len(claims), total_hours, elapsed_ms)

        return ClaimSimulationResult(
            batch_id=f"v2-{time.time_ns() // 1_000_000}",
            generated_at=datetime.now(UTC),
            seed=self.config.seed or "auto",
            claims=tuple(claims),
            fairness_report=fairness_report,
            utilization_report=utilization,
            audit_trail=self.audit.get_entries(),
            warnings=tuple(self.warnings),
            stats=SimulationStats(
                total_claims=len(claims),
                total_hours_projected=total_hours,
                children_simulated=len(self.children),
                average_hours_per_child=total_hours / len(claims) if claims else 0,
                days_with_capacity_issues=len(self.bottlenecks),
                optimization_iterations=iterations,
                fairness_score=fairness_report.overall_score,
                processing_time_ms=elapsed_ms,
            ),
        )

    def _reset(self) -> None:
        self.children.clear()
        self.daily_capacity.clear()
        self.daily_consumed.clear()
        self.category_capacity.clear()
        self.category_consumed.clear()
        self.bottlenecks.clear()
        self.warnings.clear()
        self.audit.clear()

    def _initialize_children(self, inputs: list[SimulationChildInput], month_start: date) -> None:
        historical = {item.child_id: item for item in self.config.historical_data}
        for item in inputs:
            if item.age_in_months is not None and item.age_in_years is not None:
                age_months, age_years = item.age_in_months, item.age_in_years
            else:
                birth_date = date.fromisoformat(item.birth_date)
                age_years = AgeCalculator.get_age_in_years(birth_date, month_start)
                age_months = AgeCalculator.get_age_in_months(birth_date, month_start)
            care_category = self._map_care_category(item.age_group, age_years)
            profile = self._assign_profile(item.id, care_category)
            behavior = self.config.behavioral_profiles[profile]
            target = self._calculate_target_hours(care_category, behavior.probability)
            history = historical.get(item.id)
            debt = (
                max(0, history.average_monthly_hours - history.previous_month_hours)
                if history
                else 0
            )
            child = _ChildState(
                id=item.id,
                name=item.name,
                family_id=item.family_id or item.id,
                care_category=care_category,
                age_group=self._determine_age_group(age_months),
                behavioral_profile=profile,
                age_in_years=age_years,
                age_in_months=age_months,
                enrollment_date=item.enrollment_date or "",
                target_hours=target,
                historical_debt=debt,
            )
            child.priority_score = self._priority_score(child)
            self.children[item.id] = child

    def _initialize_capacity(self, business_days: list[str]) -> None:
        daily_hours = self.config.capacity * self.config.operating_hours
        limits = self.config.category_capacity.limits
        for current_date in business_days:
            self.daily_capacity[current_date] = daily_hours
            self.daily_consumed[current_date] = 0
            if self.config.category_capacity.enabled:
                self.category_capacity[current_date] = {
                    "infant": limits.infant,
                    "toddler": limits.toddler,
                    "preschool": limits.preschool,
                    "schoolAge": limits.school_age,
                }
                self.category_consumed[current_date] = dict.fromkeys(
                    ("infant", "toddler", "preschool", "schoolAge"), 0
                )
        if self.config.category_capacity.enabled:
            self.audit.log(
                "category_capacity_init",
                "Per-category capacity initialized",
                {
                    "infant": limits.infant,
                    "toddler": limits.toddler,
                    "preschool": limits.preschool,
                    "schoolAge": limits.school_age,
                    "totalSlots": (
                        limits.infant + limits.toddler + limits.preschool + limits.school_age
                    ),
                },
            )

    def _process_day(self, current_date: str) -> None:
        is_break = self.calendar.is_school_break(date.fromisoformat(current_date))
        self.audit.log_day_start(current_date, self._remaining_capacity(current_date))
        family_attending: dict[str, bool] = {}
        children_scheduled = 0
        hours_allocated = 0.0
        for child in self._sorted_children(current_date):
            hours = self._try_schedule(child, current_date, is_break, family_attending)
            if hours is not None:
                children_scheduled += 1
                hours_allocated += hours
                family_attending[child.family_id] = True
        self.audit.log_day_end(current_date, children_scheduled, hours_allocated)

    def _sorted_children(self, current_date: str) -> list[_ChildState]:
        children = list(self.children.values())
        for child in children:
            child.priority_score = self._priority_score(child)
        if self.config.enable_sibling_coherence:
            families: dict[str, list[_ChildState]] = {}
            for child in children:
                families.setdefault(child.family_id, []).append(child)
            for siblings in families.values():
                has_scheduled_sibling = any(
                    current_date in child.daily_hours for child in siblings
                )
                if len(siblings) > 1 and has_scheduled_sibling:
                    for child in siblings:
                        if current_date not in child.daily_hours:
                            child.priority_score += 25
        return sorted(
            self.random.shuffle(children), key=lambda child: child.priority_score, reverse=True
        )

    def _try_schedule(
        self,
        child: _ChildState,
        current_date: str,
        is_school_break: bool,
        family_attending: dict[str, bool],
    ) -> float | None:
        if child.enrollment_date and child.enrollment_date > current_date:
            self._record_decision(child, current_date, "absent", "enrollment_date", 0, False)
            return None

        behavior = self.config.behavioral_profiles[child.behavioral_profile]
        probability = behavior.probability
        family_is_attending = family_attending.get(child.family_id, False)
        if family_is_attending and self.config.enable_sibling_coherence:
            probability = min(1, probability + self.config.family_influence_factor)
        if self.random.next() > probability:
            self._record_decision(
                child,
                current_date,
                "absent",
                "behavioral_profile",
                probability,
                family_is_attending,
            )
            return None

        remaining = self._remaining_capacity(current_date)
        if remaining <= 0:
            self.audit.log_capacity_exhausted(current_date, child.id, 0)
            self._record_bottleneck(current_date, child.id, 8)
            self._record_decision(
                child,
                current_date,
                "absent",
                "capacity_limit",
                probability,
                family_is_attending,
                audit=False,
            )
            return None
        if not self._has_category_capacity(current_date, child.age_group):
            self.audit.log(
                "category_capacity_exhausted",
                f"{child.age_group} capacity exhausted for {child.name}",
                {"childId": child.id, "date": current_date, "ageGroup": child.age_group},
            )
            self._record_bottleneck(current_date, child.id, 8)
            self._record_decision(
                child,
                current_date,
                "absent",
                "capacity_limit",
                probability,
                family_is_attending,
                audit=False,
            )
            return None

        hours = min(self._calculate_hours(child, is_school_break), remaining)
        child.daily_hours[current_date] = hours
        child.scheduled_hours += hours
        child.scheduled_days.append(current_date)
        self.daily_consumed[current_date] += hours
        if self.config.category_capacity.enabled:
            self.category_consumed[current_date][child.age_group] += 1
        reason = "family_coherence" if family_is_attending else "behavioral_profile"
        self._record_decision(
            child,
            current_date,
            "attend",
            reason,
            probability,
            family_is_attending,
            hours,
        )
        self.audit.log_hours_allocated(
            child.id, current_date, hours, child.target_hours - child.scheduled_hours
        )
        return hours

    def _record_decision(
        self,
        child: _ChildState,
        current_date: str,
        decision: str,
        reason: str,
        probability: float,
        family_influence: bool,
        hours: float | None = None,
        *,
        audit: bool = True,
    ) -> None:
        record = AttendanceDecision(
            child.id,
            current_date,
            decision,  # type: ignore[arg-type]
            reason,  # type: ignore[arg-type]
            probability,
            family_influence,
            hours,
        )
        child.decisions.append(record)
        if audit:
            self.audit.log_attendance_decision(record)

    def _calculate_hours(self, child: _ChildState, is_school_break: bool) -> float:
        if child.care_category == "FullTime":
            base = self.config.operating_hours
        elif is_school_break:
            base = self.config.hour_tiers.school_age_full_day_target
        else:
            base = self.config.hour_tiers.school_age_part_day_target
        profile = self.config.behavioral_profiles[child.behavioral_profile]
        variance = (self.random.next() - 0.5) * 2 * profile.variance
        minimum = 6 if child.care_category == "FullTime" else 3
        return _round(max(minimum, base * (1 + variance)), 2)

    def _priority_score(self, child: _ChildState) -> float:
        return self.fairness.calculate_priority_score(
            child.id,
            child.scheduled_hours,
            child.target_hours,
            child.care_category,  # type: ignore[arg-type]
        )

    def _optimize_for_fairness(self, business_days: list[str]) -> int:
        initial = self.fairness.generate_report(self._build_claims(len(business_days)))
        if initial.overall_score >= self.config.target_fairness_score:
            return 0
        self.audit.log_optimization_start(
            self.config.target_fairness_score, initial.overall_score
        )
        iteration = 0
        current_score = initial.overall_score
        improved = True
        while (
            improved
            and iteration < self.config.max_optimization_iterations
            and current_score < self.config.target_fairness_score
        ):
            improved = False
            iteration += 1
            report = self.fairness.generate_report(self._build_claims(len(business_days)))
            for child_id in report.underserved_children[:3]:
                if self._try_improve_child(child_id, business_days) > 0:
                    improved = True
            new_score = self.fairness.generate_report(
                self._build_claims(len(business_days))
            ).overall_score
            self.audit.log_optimization_iteration(
                iteration, new_score, new_score - current_score
            )
            current_score = new_score
        self.audit.log_optimization_end(
            iteration, current_score, current_score - initial.overall_score
        )
        return iteration

    def _try_improve_child(self, child_id: str, business_days: list[str]) -> float:
        child = self.children.get(child_id)
        if not child:
            return 0
        before = child.scheduled_hours
        deficit = child.target_hours - before
        if deficit <= 0:
            return 0
        added = 0.0
        for current_date in business_days:
            if current_date in child.daily_hours or self._remaining_capacity(current_date) <= 2:
                continue
            if added >= deficit:
                break
            hours = min(4, self._remaining_capacity(current_date), deficit - added)
            if hours < 2:
                continue
            child.daily_hours[current_date] = hours
            child.scheduled_hours += hours
            child.scheduled_days.append(current_date)
            self.daily_consumed[current_date] += hours
            added += hours
            self.audit.log_fairness_adjustment(
                child_id,
                f"Added {hours}h on {current_date} (fairness)",
                before,
                child.scheduled_hours,
            )
        return added

    def _build_claims(self, total_business_days: int) -> list[ProjectedClaim]:
        start = date(self.config.year, self.config.month, 1)
        last_day = monthrange(self.config.year, self.config.month)[1]
        end = date(self.config.year, self.config.month, last_day)
        breakdown = self.calendar.calculate_business_days(start, end)
        full_target = self.config.hour_tiers.full_time_monthly_target
        school_target = self.config.hour_tiers.school_age_full_day_target * 12
        caps = {
            "FullTime": (_round(full_target * 0.65), full_target),
            "SchoolAge": (_round(min(85, school_target) * 0.6), min(85, school_target)),
        }
        claims: list[ProjectedClaim] = []
        for child in self.children.values():
            total_hours = sum(child.daily_hours.values())
            attendance_days = len(child.daily_hours)
            enrollment = (
                date.fromisoformat(child.enrollment_date) if child.enrollment_date else None
            )
            is_prorated = enrollment is not None and enrollment > start
            effective_start = max(enrollment, start) if enrollment else start
            possible_days = max(1, math.ceil((end - effective_start).days))
            full_month_days = math.ceil((end - start).days)
            enrollment_ratio = possible_days / full_month_days if full_month_days else 1
            minimum, maximum = caps[child.care_category]
            enforce_minimum = not is_prorated and enrollment_ratio >= 0.8
            effective_minimum = minimum if enforce_minimum else minimum * enrollment_ratio
            effective_maximum = maximum * (
                enrollment_ratio if is_prorated or enrollment_ratio < 1 else 1
            )
            range_size = effective_maximum - effective_minimum
            if enforce_minimum and not effective_minimum <= total_hours <= effective_maximum:
                variance = self.random.next() * 0.15
                if child.behavioral_profile == "consistent":
                    position = 0.75 + self.random.next() * 0.25 - variance
                elif child.behavioral_profile == "variable":
                    position = 0.45 + self.random.next() * 0.35 - variance
                else:
                    position = 0.05 + self.random.next() * 0.35 - variance
                total_hours = effective_minimum + range_size * min(1, max(0, position))
            total_hours = max(0, min(effective_maximum, total_hours))
            capacity_limited = sum(
                decision.reason == "capacity_limit" for decision in child.decisions
            )
            claims.append(
                ProjectedClaim(
                    child_id=child.id,
                    child_name=child.name,
                    age_in_years=child.age_in_years,
                    age_in_months=child.age_in_months,
                    care_category=child.care_category,  # type: ignore[arg-type]
                    behavioral_profile=child.behavioral_profile,
                    is_prorated=is_prorated,
                    enrollment_date=child.enrollment_date,
                    projected_hours=_round(total_hours, 2),
                    projected_attendance_days=attendance_days,
                    base_hours_before_proration=_round(
                        child.base_hours_per_day * total_business_days, 2
                    ),
                    notes=tuple(child.notes),
                    daily_hours=dict(child.daily_hours),
                    calculation_details=CalculationDetails(
                        total_business_days=breakdown.total,
                        school_break_days=breakdown.breaks,
                        regular_school_days=breakdown.regular,
                        average_hours_per_day=(
                            _round(total_hours / attendance_days, 2) if attendance_days else 0
                        ),
                        capacity_limited_days=capacity_limited,
                    ),
                )
            )
        return claims

    def _build_utilization_report(self, business_days: list[str]) -> UtilizationReport:
        daily: list[DailyUtilization] = []
        for current_date in business_days:
            capacity = self.daily_capacity[current_date]
            consumed = self.daily_consumed[current_date]
            daily.append(
                DailyUtilization(
                    date=current_date,
                    utilized_hours=_round(consumed, 2),
                    capacity_hours=capacity,
                    utilization_percentage=(
                        int(_round(consumed / capacity * 100)) if capacity else 0
                    ),
                    attending_children_count=sum(
                        current_date in child.daily_hours for child in self.children.values()
                    ),
                )
            )
        total_capacity = sum(item.capacity_hours for item in daily)
        total_consumed = sum(item.utilized_hours for item in daily)
        ranked = sorted(daily, key=lambda item: item.utilization_percentage, reverse=True)
        bottlenecks = tuple(
            CapacityBottleneck(
                date=current_date,
                requested_hours=float(item["requested_hours"]),
                available_hours=float(item["available_hours"]),
                affected_children=tuple(item["affected_children"]),  # type: ignore[arg-type]
            )
            for current_date, item in self.bottlenecks.items()
        )
        return UtilizationReport(
            overall_utilization=_round(total_consumed / total_capacity, 2) if total_capacity else 0,
            daily_utilization=tuple(daily),
            peak_days=tuple(item.date for item in ranked[:3]),
            low_days=tuple(item.date for item in ranked[-3:]),
            average_children_per_day=(
                sum(item.attending_children_count for item in daily) / len(daily) if daily else 0
            ),
            capacity_bottlenecks=bottlenecks,
        )

    def _remaining_capacity(self, current_date: str) -> float:
        capacity = self.daily_capacity.get(current_date, 0)
        consumed = self.daily_consumed.get(current_date, 0)
        return max(0, capacity - consumed)

    def _has_category_capacity(self, current_date: str, age_group: AgeGroup) -> bool:
        if not self.config.category_capacity.enabled:
            return True
        consumed = self.category_consumed[current_date][age_group]
        capacity = self.category_capacity[current_date][age_group]
        return consumed < capacity

    def _record_bottleneck(self, current_date: str, child_id: str, requested: float) -> None:
        existing = self.bottlenecks.get(current_date)
        if existing:
            affected = existing["affected_children"]
            assert isinstance(affected, list)
            affected.append(child_id)
            return
        self.bottlenecks[current_date] = {
            "requested_hours": requested,
            "available_hours": self._remaining_capacity(current_date),
            "affected_children": [child_id],
        }

    @staticmethod
    def _determine_age_group(age_in_months: int) -> AgeGroup:
        if age_in_months < 18:
            return "infant"
        if age_in_months < 36:
            return "toddler"
        if age_in_months < 60:
            return "preschool"
        return "schoolAge"

    @staticmethod
    def _map_care_category(age_group: str | None, age_in_years: int) -> str:
        if age_group:
            normalized = age_group.lower().replace("-", "")
            if normalized == "schoolage":
                return "SchoolAge"
            if normalized in {"infant", "toddler", "preschool"}:
                return "FullTime"
        return "SchoolAge" if age_in_years >= 6.5 else "FullTime"

    def _assign_profile(self, child_id: str, care_category: str) -> BehavioralProfile:
        distribution = (
            self.config.school_age_distribution
            if care_category == "SchoolAge"
            else self.config.full_time_distribution
        )
        roll = self.random.hash_string(child_id + care_category) % 100
        if roll < distribution.consistent:
            return "consistent"
        if roll < distribution.consistent + distribution.variable:
            return "variable"
        return "oftenAbsent"

    def _calculate_target_hours(self, care_category: str, probability: float) -> float:
        minimum, maximum = (100, 150) if care_category == "FullTime" else (50, 85)
        normalized = max(0.5, min(1, probability))
        position = (normalized - 0.5) / 0.5
        variance = (self.random.next() - 0.5) * 0.1
        return _round(minimum + (maximum - minimum) * min(1, max(0, position + variance)))

    def explain_child(self, child_id: str) -> str:
        return self.audit.explain_claim(child_id)
