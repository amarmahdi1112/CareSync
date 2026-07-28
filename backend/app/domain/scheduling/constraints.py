"""Hard and soft constraint validation for scheduling decisions."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.domain.scheduling.types import (
    CapacityState,
    ChildProfile,
    ScheduleEntry,
    TimeSlotInfo,
)


@dataclass(frozen=True, slots=True)
class ConstraintContext:
    child: ChildProfile
    date: str
    time_slot: TimeSlotInfo
    current_schedule: dict[str, list[ScheduleEntry]]
    capacity_state: CapacityState
    family_schedule: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    satisfied: bool
    score: float
    reason: str
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Constraint:
    id: str
    name: str
    type: Literal["hard", "soft"]
    weight: float
    validate: Callable[[ConstraintContext], ConstraintResult]


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    constraint_id: str
    constraint_name: str
    reason: str
    child_id: str
    date: str


@dataclass(frozen=True, slots=True)
class SoftConstraintDetail:
    constraint_id: str
    constraint_name: str
    score: float
    weight: float
    weighted_score: float


@dataclass(frozen=True, slots=True)
class ConstraintValidationResult:
    all_hard_satisfied: bool
    hard_violations: tuple[ConstraintViolation, ...]
    soft_score: float
    soft_details: tuple[SoftConstraintDetail, ...]
    overall_score: float


def _capacity(context: ConstraintContext) -> ConstraintResult:
    available = context.capacity_state.remaining_capacity > 0
    reason = (
        "Capacity available"
        if available
        else (
            "No capacity remaining "
            f"({context.capacity_state.used_capacity}/{context.capacity_state.total_capacity})"
        )
    )
    return ConstraintResult(available, 1 if available else 0, reason)


def _operating_hours(_context: ConstraintContext) -> ConstraintResult:
    return ConstraintResult(True, 1, "Within operating hours")


def _enrollment(context: ConstraintContext) -> ConstraintResult:
    enrolled_on = context.child.enrollment_date
    if not enrolled_on:
        return ConstraintResult(True, 1, "No enrollment date restriction")
    enrolled = date.fromisoformat(enrolled_on) <= date.fromisoformat(context.date)
    return ConstraintResult(
        enrolled,
        1 if enrolled else 0,
        "Child is enrolled" if enrolled else f"Child not yet enrolled (enrolls {enrolled_on})",
    )


def _sibling_coherence(context: ConstraintContext) -> ConstraintResult:
    same_day = context.date in context.family_schedule.get(context.child.family_id, [])
    return ConstraintResult(
        True,
        1 if same_day else 0.5,
        "Sibling scheduled on same day" if same_day else "No sibling scheduled on this day",
    )


def _minutes(value: str) -> int:
    hour, minute = (value.split(":") + ["0"])[:2]
    return int(hour) * 60 + int(minute)


def _preferred_time(context: ConstraintContext) -> ConstraintResult:
    preferred = (
        context.child.preferences.preferred_arrival_time
        if context.child.preferences
        else None
    )
    if not preferred:
        return ConstraintResult(True, 1, "No time preference set")
    difference = abs(_minutes(preferred) - _minutes(context.time_slot.start_time))
    score = max(0, 1 - difference / 120)
    reason = (
        "Matches preferred time"
        if difference == 0
        else f"{round(difference / 60)} hour(s) from preferred time"
    )
    return ConstraintResult(True, score, reason)


def _avoid_children(context: ConstraintContext) -> ConstraintResult:
    avoid = context.child.preferences.avoid_child_ids if context.child.preferences else ()
    conflicts = sum(
        any(entry.date == context.date for entry in context.current_schedule.get(child_id, []))
        for child_id in avoid
    )
    return ConstraintResult(
        True,
        1 if conflicts == 0 else max(0, 1 - conflicts * 0.3),
        (
            "No conflicts with avoided children"
            if conflicts == 0
            else f"{conflicts} avoided child(ren) on same day"
        ),
    )


def _fairness(_context: ConstraintContext) -> ConstraintResult:
    return ConstraintResult(True, 1, "Fairness check delegated")


BUILT_IN_CONSTRAINTS = {
    "capacity": Constraint("capacity", "Room Capacity", "hard", 1, _capacity),
    "operating_hours": Constraint(
        "operating_hours", "Operating Hours", "hard", 1, _operating_hours
    ),
    "enrollment": Constraint("enrollment", "Enrollment Status", "hard", 1, _enrollment),
    "sibling_coherence": Constraint(
        "sibling_coherence", "Sibling Coherence", "soft", 0.8, _sibling_coherence
    ),
    "preferred_time": Constraint(
        "preferred_time", "Preferred Schedule Time", "soft", 0.6, _preferred_time
    ),
    "avoid_children": Constraint(
        "avoid_children", "Child Separation", "soft", 0.7, _avoid_children
    ),
    "fairness": Constraint("fairness", "Fairness Priority", "soft", 0.9, _fairness),
}


class ConstraintEngine:
    def __init__(self, custom_constraints: Sequence[Constraint] = ()) -> None:
        self.constraints = [*BUILT_IN_CONSTRAINTS.values(), *custom_constraints]
        self.hard_constraints = [item for item in self.constraints if item.type == "hard"]
        self.soft_constraints = [item for item in self.constraints if item.type == "soft"]

    def validate(self, context: ConstraintContext) -> ConstraintValidationResult:
        violations: list[ConstraintViolation] = []
        for constraint in self.hard_constraints:
            result = constraint.validate(context)
            if not result.satisfied:
                violations.append(
                    ConstraintViolation(
                        constraint.id,
                        constraint.name,
                        result.reason,
                        context.child.id,
                        context.date,
                    )
                )
        details: list[SoftConstraintDetail] = []
        for constraint in self.soft_constraints:
            result = constraint.validate(context)
            details.append(
                SoftConstraintDetail(
                    constraint.id,
                    constraint.name,
                    result.score,
                    constraint.weight,
                    result.score * constraint.weight,
                )
            )
        total_weight = sum(item.weight for item in details)
        soft_score = (
            sum(item.weighted_score for item in details) / total_weight
            if total_weight
            else 1
        )
        hard_satisfied = not violations
        return ConstraintValidationResult(
            hard_satisfied,
            tuple(violations),
            soft_score,
            tuple(details),
            soft_score if hard_satisfied else 0,
        )

    def can_schedule(self, context: ConstraintContext) -> bool:
        return all(
            constraint.validate(context).satisfied
            for constraint in self.hard_constraints
        )

    def get_score(self, context: ConstraintContext) -> float:
        total_weight = sum(item.weight for item in self.soft_constraints)
        return (
            sum(item.validate(context).score * item.weight for item in self.soft_constraints)
            / total_weight
            if total_weight
            else 1
        )

    def get_constraints(self) -> tuple[Constraint, ...]:
        return tuple(self.constraints)
