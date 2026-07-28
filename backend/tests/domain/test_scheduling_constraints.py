from datetime import UTC, datetime

from app.domain.scheduling import (
    CapacityState,
    ChildPreferences,
    ChildProfile,
    Constraint,
    ConstraintContext,
    ConstraintEngine,
    ConstraintResult,
    ScheduleEntry,
    SchedulingDecision,
    TimeSlotInfo,
)


def context(
    *,
    remaining: int = 50,
    enrollment_date: str | None = None,
    preferences: ChildPreferences | None = None,
    current_schedule: dict[str, list[ScheduleEntry]] | None = None,
    family_schedule: dict[str, list[str]] | None = None,
    start_time: str = "09:00",
) -> ConstraintContext:
    return ConstraintContext(
        ChildProfile(
            "child-1",
            "Test Child",
            "family-1",
            "Daycare",
            100,
            enrollment_date,
            preferences,
        ),
        "2024-01-15",
        TimeSlotInfo(start_time, "17:00", 5, 5),
        current_schedule or {},
        CapacityState("2024-01-15", 100, 100 - remaining, remaining, 50, ()),
        family_schedule or {},
    )


def test_hard_capacity_and_enrollment_constraints() -> None:
    engine = ConstraintEngine()
    assert engine.can_schedule(context())
    blocked = engine.validate(context(remaining=0))
    assert not blocked.all_hard_satisfied
    assert blocked.overall_score == 0
    assert not engine.can_schedule(context(enrollment_date="2024-02-01"))
    assert engine.can_schedule(context(enrollment_date="2024-01-01"))


def test_soft_time_sibling_and_avoidance_scores() -> None:
    engine = ConstraintEngine()
    exact = engine.validate(
        context(
            preferences=ChildPreferences(preferred_arrival_time="09:00"),
            family_schedule={"family-1": ["2024-01-15"]},
        )
    )
    off = engine.validate(
        context(
            preferences=ChildPreferences(
                preferred_arrival_time="09:00", avoid_child_ids=("avoid",)
            ),
            current_schedule={
                "avoid": [
                    ScheduleEntry(
                        "avoid",
                        "2024-01-15",
                        "09:00",
                        "17:00",
                        8,
                        SchedulingDecision(datetime.now(UTC)),
                    )
                ]
            },
            start_time="14:00",
        )
    )
    assert exact.all_hard_satisfied
    assert off.all_hard_satisfied
    assert exact.soft_score > off.soft_score
    assert off.soft_details


def test_custom_hard_constraint_is_enforced() -> None:
    custom = Constraint(
        "custom",
        "Custom Rule",
        "hard",
        1,
        lambda item: ConstraintResult(
            item.child.name != "Test Child", 0, "Custom validation"
        ),
    )
    engine = ConstraintEngine([custom])
    assert not engine.can_schedule(context())
    assert any(item.id == "custom" for item in engine.get_constraints())
