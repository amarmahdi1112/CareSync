"""Claim-generation domain rules."""

from app.domain.claims.audit import AuditTrail
from app.domain.claims.calendar import BusinessDayCalculation, DaycareCalendar, SchoolBreakPeriod
from app.domain.claims.categories import AgeRange, AgeRangeConfig, CareCategoryResolver
from app.domain.claims.dates import AgeCalculator
from app.domain.claims.fairness import FairnessCalculator
from app.domain.claims.simulator import ClaimSimulator
from app.domain.claims.types import (
    BehavioralProfileConfig,
    CalculationDetails,
    CategoryCapacityConfig,
    ClaimSimulationResult,
    ClaimSimulatorConfig,
    FairnessMetrics,
    FairnessReport,
    HistoricalChildData,
    HourTiers,
    ProfileDistribution,
    ProjectedClaim,
    SimulationChildInput,
)

__all__ = [
    "AgeCalculator",
    "AgeRange",
    "AgeRangeConfig",
    "AuditTrail",
    "BusinessDayCalculation",
    "BehavioralProfileConfig",
    "CalculationDetails",
    "CategoryCapacityConfig",
    "CareCategoryResolver",
    "ClaimSimulationResult",
    "ClaimSimulator",
    "ClaimSimulatorConfig",
    "DaycareCalendar",
    "FairnessCalculator",
    "FairnessMetrics",
    "FairnessReport",
    "HistoricalChildData",
    "HourTiers",
    "ProfileDistribution",
    "ProjectedClaim",
    "SchoolBreakPeriod",
    "SimulationChildInput",
]
