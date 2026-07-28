"""Core values produced by the scheduling engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

CareType = Literal["Daycare", "OSC"]


@dataclass(frozen=True, slots=True)
class ChildPreferences:
    preferred_arrival_time: str | None = None
    preferred_departure_time: str | None = None
    preferred_days: tuple[int, ...] = ()
    excluded_days: tuple[str, ...] = ()
    start_time_1: str | None = None
    end_time_1: str | None = None
    start_time_2: str | None = None
    end_time_2: str | None = None
    friend_ids: tuple[str, ...] = ()
    avoid_child_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalAttendance:
    average_hours_per_day: float
    attendance_rate: float
    late_arrival_rate: float
    early_departure_rate: float
    no_show_rate: float
    typical_arrival_time: str
    typical_departure_time: str
    monthly_hours_history: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class ChildProfile:
    id: str
    name: str
    family_id: str
    care_type: CareType
    total_claimed_hours: float
    enrollment_date: str | None = None
    preferences: ChildPreferences | None = None
    historical_data: HistoricalAttendance | None = None


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    timestamp: datetime
    reason: str = "capacity_available"
    constraints_satisfied: tuple[str, ...] = ()
    constraints_violated: tuple[str, ...] = ()
    alternatives_considered: int = 0
    confidence_score: float = 1
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    child_id: str
    date: str
    start_time: str
    end_time: str
    hours: float
    decision: SchedulingDecision
    start_time_2: str | None = None
    end_time_2: str | None = None
    child_name: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulingFairnessMetrics:
    gini_coefficient: float
    standard_deviation: float
    min_hours_scheduled: float
    max_hours_scheduled: float
    average_hours_scheduled: float
    median_hours_scheduled: float
    historical_debt_map: dict[str, float]
    priority_scores: dict[str, float]


@dataclass(frozen=True, slots=True)
class SchedulingFairnessReport:
    overall_score: int
    metrics: SchedulingFairnessMetrics
    underserved_children: tuple[str, ...]
    overserved_children: tuple[str, ...]
    recommendations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchedulingGoals:
    target_utilization: float = 0.85
    fairness_weight: float = 0.3
    revenue_weight: float = 0.2
    parent_satisfaction_weight: float = 0.25
    sibling_coherence_weight: float = 0.25


@dataclass(frozen=True, slots=True)
class OperatingHours:
    start: int = 7
    end: int = 18


@dataclass(frozen=True, slots=True)
class ChildTimeOverride:
    child_identifier: str
    days_of_week: tuple[int, ...] = ()
    start_time_1: str | None = None
    end_time_1: str | None = None
    start_time_2: str | None = None
    end_time_2: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    open_days: tuple[str, ...]
    capacity: int
    operating_hours: OperatingHours = OperatingHours()
    school_off_days: tuple[str, ...] = ()
    daily_capacity_min: int | None = None
    daily_capacity_max: int | None = None
    goals: SchedulingGoals = SchedulingGoals()
    enable_predictions: bool = True
    enable_fairness_optimization: bool = True
    enable_sibling_coherence: bool = True
    enable_audit_trail: bool = True
    max_iterations: int = 100
    seed: str | None = None
    child_time_overrides: tuple[ChildTimeOverride, ...] = ()

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if not self.open_days:
            raise ValueError("at least one open day is required")
        if len(set(self.open_days)) != len(self.open_days):
            raise ValueError("open days cannot contain duplicates")
        for current_date in self.open_days:
            date.fromisoformat(current_date)
        if self.operating_hours.end <= self.operating_hours.start:
            raise ValueError("operating hours must be ordered")
        if self.daily_capacity_min is not None and self.daily_capacity_min < 0:
            raise ValueError("daily capacity minimum cannot be negative")
        if self.daily_capacity_max is not None and self.daily_capacity_max <= 0:
            raise ValueError("daily capacity maximum must be positive")
        if (
            self.daily_capacity_min is not None
            and self.daily_capacity_max is not None
            and self.daily_capacity_min > self.daily_capacity_max
        ):
            raise ValueError("daily capacity minimum cannot exceed the maximum")


@dataclass(frozen=True, slots=True)
class ScheduleWarning:
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str
    affected_children: tuple[str, ...] = ()
    affected_dates: tuple[str, ...] = ()
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulingAuditEntry:
    timestamp: datetime
    action: str
    details: dict[str, Any]
    reason: str
    child_id: str | None = None
    date: str | None = None


@dataclass(frozen=True, slots=True)
class SchedulerUtilizationReport:
    overall_utilization: float
    daily_utilization: tuple[DailyUtilization, ...]
    peak_days: tuple[str, ...]
    low_days: tuple[str, ...]
    average_children_per_day: float
    revenue_projection: float


@dataclass(frozen=True, slots=True)
class ScheduleStats:
    total_entries: int
    total_hours_scheduled: float
    children_scheduled: int
    average_hours_per_child: float
    days_with_capacity_issues: int
    constraint_violations: int
    optimization_score: float
    requested_children: int
    requested_hours: float
    unscheduled_children: int
    hours_shortfall: float
    completion_percentage: float


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    batch_id: str
    generated_at: datetime
    seed: str
    algorithm_version: str
    input_hash: str
    entries: tuple[ScheduleEntry, ...]
    fairness_report: SchedulingFairnessReport
    utilization_report: SchedulerUtilizationReport
    audit_trail: tuple[SchedulingAuditEntry, ...]
    warnings: tuple[ScheduleWarning, ...]
    stats: ScheduleStats
    # V3 exposes a compact, JSON-serializable explanation stream for the
    # interactive scheduler visualizer. V2 deliberately leaves this unset.
    visualization: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TimeSlotInfo:
    start_time: str
    end_time: str
    remaining_capacity: int
    current_occupancy: int


@dataclass(frozen=True, slots=True)
class CapacityState:
    date: str
    total_capacity: int
    used_capacity: int
    remaining_capacity: int
    utilization_percentage: float
    slot_breakdown: tuple[TimeSlotInfo, ...]


@dataclass(frozen=True, slots=True)
class TimeGap:
    start_time: str
    end_time: str
    unused_capacity: float


@dataclass(frozen=True, slots=True)
class DailyUtilization:
    date: str
    day_of_week: int
    capacity_hours: float
    scheduled_hours: float
    utilization: float
    children_count: int
    peak_hour: str
    gaps: tuple[TimeGap, ...]
