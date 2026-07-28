"""Typed values used by the claim simulation engine."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.domain.claims.calendar import SchoolBreakPeriod
from app.domain.claims.categories import CareCategory

BehavioralProfile = Literal["consistent", "variable", "oftenAbsent"]
AgeGroup = Literal["infant", "toddler", "preschool", "schoolAge"]
AuditEventType = Literal[
    "simulation_start",
    "simulation_end",
    "day_start",
    "day_end",
    "attendance_decision",
    "capacity_exhausted",
    "category_capacity_exhausted",
    "category_capacity_init",
    "hours_allocated",
    "sibling_coherence",
    "fairness_adjustment",
    "optimization_start",
    "optimization_iteration",
    "optimization_end",
    "warning",
    "error",
]
AttendanceReason = Literal[
    "behavioral_profile",
    "family_coherence",
    "capacity_limit",
    "enrollment_date",
    "override",
    "optimization",
]


@dataclass(frozen=True, slots=True)
class AttendanceDecision:
    child_id: str
    date: str
    decision: Literal["attend", "absent"]
    reason: AttendanceReason
    probability: float
    family_influence: bool
    hours_allocated: float | None = None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    timestamp: datetime
    event_type: AuditEventType
    message: str
    child_id: str | None = None
    date: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CalculationDetails:
    total_business_days: int
    school_break_days: int
    regular_school_days: int
    average_hours_per_day: float
    capacity_limited_days: int
    eligible_business_days: int | None = None


@dataclass(frozen=True, slots=True)
class ProjectedClaim:
    child_id: str
    child_name: str
    age_in_years: int
    age_in_months: int
    care_category: CareCategory
    behavioral_profile: BehavioralProfile
    is_prorated: bool
    enrollment_date: str
    projected_hours: float
    projected_attendance_days: int
    base_hours_before_proration: float
    notes: tuple[str, ...] = ()
    calculation_details: CalculationDetails | None = None
    proration_factor: float | None = None
    daily_hours: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HistoricalChildData:
    child_id: str
    previous_month_hours: float
    average_monthly_hours: float
    months_enrolled: int


@dataclass(frozen=True, slots=True)
class FairnessMetrics:
    gini_coefficient: float
    fairness_score: int
    hours_standard_deviation: float
    coefficient_of_variation: float
    underserved_count: int
    adequately_served_count: int


@dataclass(frozen=True, slots=True)
class FairnessReport:
    metrics: FairnessMetrics
    overall_score: int
    underserved_children: tuple[str, ...]
    overserved_children: tuple[str, ...]
    recommendations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BehavioralProfileConfig:
    probability: float
    variance: float


@dataclass(frozen=True, slots=True)
class ProfileDistribution:
    consistent: float
    variable: float
    often_absent: float


@dataclass(frozen=True, slots=True)
class HourTiers:
    full_time_monthly_target: float = 110
    school_age_full_day_target: float = 9
    school_age_part_day_target: float = 4


@dataclass(frozen=True, slots=True)
class SimulationChildInput:
    id: str
    name: str
    birth_date: str
    family_id: str | None = None
    enrollment_date: str | None = None
    age_group: str | None = None
    age_in_months: int | None = None
    age_in_years: int | None = None


@dataclass(frozen=True, slots=True)
class AgeGroupCapacity:
    infant: int = 8
    toddler: int = 12
    preschool: int = 20
    school_age: int = 30


@dataclass(frozen=True, slots=True)
class CategoryCapacityConfig:
    enabled: bool = True
    limits: AgeGroupCapacity = field(default_factory=AgeGroupCapacity)
    staff_count: int = 8


def default_behavioral_profiles() -> dict[BehavioralProfile, BehavioralProfileConfig]:
    return {
        "consistent": BehavioralProfileConfig(0.95, 0.1),
        "variable": BehavioralProfileConfig(0.8, 0.2),
        "oftenAbsent": BehavioralProfileConfig(0.65, 0.15),
    }


@dataclass(frozen=True, slots=True)
class ClaimSimulatorConfig:
    organization_id: str
    month: int
    year: int
    capacity: int
    operating_hours: float
    school_break_periods: tuple[SchoolBreakPeriod, ...] = ()
    holidays: tuple[str, ...] = ()
    hour_tiers: HourTiers = field(default_factory=HourTiers)
    behavioral_profiles: dict[BehavioralProfile, BehavioralProfileConfig] = field(
        default_factory=default_behavioral_profiles
    )
    full_time_distribution: ProfileDistribution = field(
        default_factory=lambda: ProfileDistribution(40, 35, 25)
    )
    school_age_distribution: ProfileDistribution = field(
        default_factory=lambda: ProfileDistribution(55, 30, 15)
    )
    family_influence_factor: float = 0.3
    seed: str | None = None
    enable_fairness_optimization: bool = True
    enable_sibling_coherence: bool = True
    enable_audit_trail: bool = True
    target_fairness_score: int = 85
    max_optimization_iterations: int = 50
    historical_data: tuple[HistoricalChildData, ...] = ()
    category_capacity: CategoryCapacityConfig = field(default_factory=CategoryCapacityConfig)

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")
        if self.capacity <= 0 or self.operating_hours <= 0:
            raise ValueError("capacity and operating_hours must be positive")


@dataclass(frozen=True, slots=True)
class DailyUtilization:
    date: str
    utilized_hours: float
    capacity_hours: float
    utilization_percentage: int
    attending_children_count: int


@dataclass(frozen=True, slots=True)
class CapacityBottleneck:
    date: str
    requested_hours: float
    available_hours: float
    affected_children: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UtilizationReport:
    overall_utilization: float
    daily_utilization: tuple[DailyUtilization, ...]
    peak_days: tuple[str, ...]
    low_days: tuple[str, ...]
    average_children_per_day: float
    capacity_bottlenecks: tuple[CapacityBottleneck, ...]


@dataclass(frozen=True, slots=True)
class SimulationStats:
    total_claims: int
    total_hours_projected: float
    children_simulated: int
    average_hours_per_child: float
    days_with_capacity_issues: int
    optimization_iterations: int
    fairness_score: int
    processing_time_ms: float


@dataclass(frozen=True, slots=True)
class ClaimSimulationResult:
    batch_id: str
    generated_at: datetime
    seed: str
    claims: tuple[ProjectedClaim, ...]
    fairness_report: FairnessReport
    utilization_report: UtilizationReport
    audit_trail: tuple[AuditEntry, ...]
    warnings: tuple[str, ...]
    stats: SimulationStats
