"""Immutable, tick-based contracts for the isolated V3 scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

TICK_MINUTES = 5
TICKS_PER_DAY = 24 * 60 // TICK_MINUTES
DAYCARE = "Daycare"
OSC = "OSC"

CareType = Literal["Daycare", "OSC"]
PatternKind = Literal["daycare", "osc_school", "osc_school_off"]
VisualizationOperation = Literal["place", "move", "resize", "remove"]
_PATTERN_KINDS = {"daycare", "osc_school", "osc_school_off"}


def _valid_date(value: str, field: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must contain ISO dates: {value}") from exc


@dataclass(frozen=True, slots=True)
class V3Child:
    child_id: str
    care_type: CareType
    claimed_ticks: int
    enrollment_date: str | None = None
    excluded_dates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.child_id.strip():
            raise ValueError("child_id cannot be blank")
        if self.care_type not in {DAYCARE, OSC}:
            raise ValueError(f"unsupported care type: {self.care_type}")
        if isinstance(self.claimed_ticks, bool) or not isinstance(self.claimed_ticks, int):
            raise TypeError("claimed_ticks must be an integer")
        if self.claimed_ticks < 0:
            raise ValueError("claimed_ticks cannot be negative")
        if self.enrollment_date is not None:
            _valid_date(self.enrollment_date, "enrollment_date")
        if len(set(self.excluded_dates)) != len(self.excluded_dates):
            raise ValueError("excluded_dates cannot contain duplicates")
        for current_date in self.excluded_dates:
            _valid_date(current_date, "excluded_dates")


@dataclass(frozen=True, slots=True)
class V3Config:
    open_dates: tuple[str, ...]
    capacity: int
    school_off_dates: tuple[str, ...] = ()
    operating_start_tick: int = 7 * 60 // TICK_MINUTES
    operating_end_tick: int = 18 * 60 // TICK_MINUTES
    daily_unique_target: int | None = None
    max_repair_iterations: int = 100
    realism_seed: str = "v3-default"

    def __post_init__(self) -> None:
        if not self.open_dates:
            raise ValueError("open_dates cannot be empty")
        if len(set(self.open_dates)) != len(self.open_dates):
            raise ValueError("open_dates cannot contain duplicates")
        for current_date in self.open_dates:
            _valid_date(current_date, "open_dates")
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
            raise TypeError("capacity must be an integer")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if (
            isinstance(self.operating_start_tick, bool)
            or not isinstance(self.operating_start_tick, int)
            or isinstance(self.operating_end_tick, bool)
            or not isinstance(self.operating_end_tick, int)
        ):
            raise TypeError("operating tick bounds must be integers")
        if not 0 <= self.operating_start_tick < self.operating_end_tick <= TICKS_PER_DAY:
            raise ValueError("operating tick bounds are invalid")
        if len(set(self.school_off_dates)) != len(self.school_off_dates):
            raise ValueError("school_off_dates cannot contain duplicates")
        unknown_school_off = set(self.school_off_dates) - set(self.open_dates)
        if unknown_school_off:
            raise ValueError("school_off_dates must be open dates")
        if self.daily_unique_target is not None:
            if isinstance(self.daily_unique_target, bool) or not isinstance(
                self.daily_unique_target, int
            ):
                raise TypeError("daily_unique_target must be an integer")
            if self.daily_unique_target < 0:
                raise ValueError("daily_unique_target cannot be negative")
        if isinstance(self.max_repair_iterations, bool) or not isinstance(
            self.max_repair_iterations, int
        ):
            raise TypeError("max_repair_iterations must be an integer")
        if self.max_repair_iterations < 0:
            raise ValueError("max_repair_iterations cannot be negative")
        if not isinstance(self.realism_seed, str):
            raise TypeError("realism_seed must be a string")


@dataclass(frozen=True, slots=True, order=True)
class TimeBlock:
    start_tick: int
    end_tick: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_tick < self.end_tick <= TICKS_PER_DAY:
            raise ValueError("time block tick bounds are invalid")

    @property
    def duration_ticks(self) -> int:
        return self.end_tick - self.start_tick


@dataclass(frozen=True, slots=True)
class CandidatePattern:
    child_id: str
    date: str
    blocks: tuple[TimeBlock, ...]
    kind: PatternKind

    def __post_init__(self) -> None:
        if not self.child_id.strip():
            raise ValueError("child_id cannot be blank")
        _valid_date(self.date, "date")
        if self.kind not in _PATTERN_KINDS:
            raise ValueError(f"unsupported pattern kind: {self.kind}")
        _validate_blocks(self.blocks)

    @property
    def duration_ticks(self) -> int:
        return sum(block.duration_ticks for block in self.blocks)


@dataclass(frozen=True, slots=True)
class ScheduleAssignment:
    child_id: str
    date: str
    blocks: tuple[TimeBlock, ...]
    kind: PatternKind

    def __post_init__(self) -> None:
        if not self.child_id.strip():
            raise ValueError("child_id cannot be blank")
        _valid_date(self.date, "date")
        if self.kind not in _PATTERN_KINDS:
            raise ValueError(f"unsupported pattern kind: {self.kind}")
        _validate_blocks(self.blocks)

    @property
    def duration_ticks(self) -> int:
        return sum(block.duration_ticks for block in self.blocks)


def _validate_blocks(blocks: tuple[TimeBlock, ...]) -> None:
    if not blocks or len(blocks) > 2:
        raise ValueError("a pattern must contain one or two blocks")
    if tuple(sorted(blocks)) != blocks:
        raise ValueError("blocks must be in canonical order")
    if len(blocks) == 2 and blocks[1].start_tick < blocks[0].end_tick:
        raise ValueError("blocks cannot overlap")


@dataclass(frozen=True, slots=True, order=True)
class Objective:
    hard_violations: int
    total_shortfall_ticks: int
    worst_shortfall_ticks: int
    daily_unique_deviation: int
    canonical_key: tuple[tuple[str, str, tuple[tuple[int, int], ...]], ...]


@dataclass(frozen=True, slots=True)
class PhaseTrace:
    phase: str
    action: str
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FeasibilityResult:
    feasible: bool
    proven: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VisualizationEvent:
    """One accepted, replayable assignment change.

    Rejected search candidates are intentionally absent. Blocks remain integer
    tick pairs so the legacy adapter can serialize the stream compactly.
    """

    phase: Literal["construct", "repair", "daycare_realism"]
    operation: VisualizationOperation
    child_id: str
    from_date: str | None
    to_date: str | None
    from_blocks: tuple[TimeBlock, ...]
    to_blocks: tuple[TimeBlock, ...]
    before_shortfall_ticks: int
    after_shortfall_ticks: int
    iteration: int | None = None


@dataclass(frozen=True, slots=True)
class V3ScheduleResult:
    assignments: tuple[ScheduleAssignment, ...]
    feasibility: FeasibilityResult
    trace: tuple[PhaseTrace, ...]
    objective: Objective
    requested_ticks: int
    scheduled_ticks_by_child: tuple[tuple[str, int], ...]
    visualization_events: tuple[VisualizationEvent, ...] = ()
