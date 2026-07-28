"""Public surface of the isolated V3 scheduling core."""

from .adapter import V3LegacyAdapter, execute_v3_schedule
from .auditor import (
    AuditViolation,
    CapacityPeak,
    V3AuditReport,
    audit_assignments,
    audit_schedule_result,
)
from .candidates import care_windows, eligible_dates, enumerate_candidate_patterns
from .engine import V3Scheduler
from .types import (
    DAYCARE,
    OSC,
    TICK_MINUTES,
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

__all__ = [
    "DAYCARE",
    "OSC",
    "TICK_MINUTES",
    "AuditViolation",
    "CandidatePattern",
    "CapacityPeak",
    "FeasibilityResult",
    "Objective",
    "PhaseTrace",
    "ScheduleAssignment",
    "TimeBlock",
    "V3Child",
    "V3Config",
    "V3AuditReport",
    "V3LegacyAdapter",
    "V3ScheduleResult",
    "V3Scheduler",
    "VisualizationEvent",
    "audit_assignments",
    "audit_schedule_result",
    "care_windows",
    "eligible_dates",
    "enumerate_candidate_patterns",
    "execute_v3_schedule",
]
