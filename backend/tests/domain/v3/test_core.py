import pytest

from app.domain.scheduling.v3 import (
    DAYCARE,
    OSC,
    V3Child,
    V3Config,
    V3Scheduler,
    enumerate_candidate_patterns,
)


def test_candidate_patterns_use_exact_five_minute_ticks_and_care_windows() -> None:
    config = V3Config(
        open_dates=("2026-01-05", "2026-01-06"),
        school_off_dates=("2026-01-06",),
        capacity=2,
    )
    osc = V3Child("osc", OSC, 48)

    school = enumerate_candidate_patterns(osc, config, "2026-01-05", 48)
    school_off = enumerate_candidate_patterns(osc, config, "2026-01-06", 132)

    assert len(school) == 1
    assert [(block.start_tick, block.end_tick) for block in school[0].blocks] == [
        (84, 102),
        (186, 216),
    ]
    assert len(school_off) == 1
    assert (school_off[0].blocks[0].start_tick, school_off[0].blocks[0].end_tick) == (
        84,
        216,
    )


def test_scheduler_is_deterministic_exact_and_capacity_safe() -> None:
    config = V3Config(
        open_dates=("2026-01-06", "2026-01-05"),
        capacity=1,
        daily_unique_target=1,
    )
    children = [V3Child("b", DAYCARE, 100), V3Child("a", DAYCARE, 100)]

    first = V3Scheduler(config, children).execute()
    second = V3Scheduler(config, reversed(children)).execute()
    third = V3Scheduler(
        V3Config(
            open_dates=tuple(reversed(config.open_dates)),
            capacity=config.capacity,
            daily_unique_target=config.daily_unique_target,
        ),
        children,
    ).execute()

    assert first == second
    assert first == third
    assert first.feasibility.feasible
    assert first.scheduled_ticks_by_child == (("a", 100), ("b", 100))
    occupancy: dict[tuple[str, int], int] = {}
    for assignment in first.assignments:
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                key = (assignment.date, tick)
                occupancy[key] = occupancy.get(key, 0) + 1
    assert max(occupancy.values()) == 1
    assert [item.phase for item in first.trace] == [
        "canonicalize",
        "feasibility_preflight",
        "construct",
        "repair",
        "daycare_realism",
        "validate",
        "complete",
    ]


def test_daily_unique_target_is_soft_and_never_blocks_claim_fulfillment() -> None:
    config = V3Config(
        open_dates=("2026-01-05",),
        capacity=3,
        daily_unique_target=1,
    )
    result = V3Scheduler(
        config,
        [V3Child(str(index), DAYCARE, 12) for index in range(3)],
    ).execute()

    assert result.feasibility.feasible
    assert result.objective.daily_unique_deviation == 2
    assert sum(value for _, value in result.scheduled_ticks_by_child) == 36


def test_school_osc_and_school_off_osc_fit_exact_claims_without_overclaim() -> None:
    config = V3Config(
        open_dates=("2026-01-05", "2026-01-06"),
        school_off_dates=("2026-01-06",),
        capacity=2,
    )
    result = V3Scheduler(
        config,
        [V3Child("school", OSC, 48), V3Child("off", OSC, 132)],
    ).execute()

    assert result.feasibility.feasible
    assert result.scheduled_ticks_by_child == (("off", 132), ("school", 48))
    assert all(
        scheduled
        <= next(
            child.claimed_ticks
            for child in (
                V3Child("school", OSC, 48),
                V3Child("off", OSC, 132),
            )
            if child.child_id == child_id
        )
        for child_id, scheduled in result.scheduled_ticks_by_child
    )


def test_explicit_proven_infeasibility_and_integer_claim_contract() -> None:
    with pytest.raises(TypeError, match="integer"):
        V3Child("fractional", DAYCARE, 1.5)  # type: ignore[arg-type]

    result = V3Scheduler(
        V3Config(open_dates=("2026-01-05",), capacity=1),
        [V3Child("too-many", DAYCARE, 133)],
    ).execute()

    assert not result.feasibility.feasible
    assert result.feasibility.proven
    assert any(reason.startswith("CHILD_WINDOW_SHORTAGE") for reason in result.feasibility.reasons)
    assert result.scheduled_ticks_by_child == (("too-many", 132),)
    assert result.objective.total_shortfall_ticks == 1
    repair_trace = next(item for item in result.trace if item.phase == "repair")
    assert ("reason", "preflight_lower_bound_reached") in repair_trace.details


def test_preflight_lower_bound_adds_distinct_child_window_shortages() -> None:
    reasons = (
        "CHILD_WINDOW_SHORTAGE:ordinary:4",
        "CHILD_WINDOW_SHORTAGE:imported-claim:uuid:7",
        "GLOBAL_CAPACITY_SHORTAGE:8",
        "OSC_WINDOW_CAPACITY_SHORTAGE:9",
    )

    assert V3Scheduler._preflight_shortfall_lower_bound(reasons) == 11


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("capacity", True),
        ("operating_start_tick", 84.5),
        ("daily_unique_target", False),
        ("max_repair_iterations", 1.5),
    ),
)
def test_config_rejects_boolean_and_non_integer_numeric_fields(field: str, value: object) -> None:
    values: dict[str, object] = {
        "open_dates": ("2026-01-05",),
        "capacity": 1,
    }
    values[field] = value

    with pytest.raises(TypeError, match="integer"):
        V3Config(**values)  # type: ignore[arg-type]


def test_small_stress_case_fits_exactly_and_is_repeatable() -> None:
    config = V3Config(
        open_dates=("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"),
        capacity=5,
        max_repair_iterations=20,
    )
    children = [V3Child(f"child-{index:02d}", DAYCARE, 100) for index in range(20)]

    first = V3Scheduler(config, children).execute()
    second = V3Scheduler(config, list(reversed(children))).execute()

    assert first.feasibility.feasible
    assert first.assignments == second.assignments
    assert first.objective.total_shortfall_ticks == 0


def test_repair_relocates_a_flexible_assignment_for_a_constrained_child() -> None:
    dates = (
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    )
    eligible = {
        "a": {dates[0]},
        "b": {dates[1]},
        "c": {dates[2], dates[3]},
        "d": {dates[0], dates[2]},
    }
    children = [
        V3Child(
            child_id,
            DAYCARE,
            1,
            excluded_dates=tuple(item for item in dates if item not in child_dates),
        )
        for child_id, child_dates in eligible.items()
    ]
    config = V3Config(
        open_dates=dates,
        capacity=1,
        operating_start_tick=84,
        operating_end_tick=85,
    )

    result = V3Scheduler(config, children).execute()

    assert result.feasibility.feasible
    assert result.scheduled_ticks_by_child == (("a", 1), ("b", 1), ("c", 1), ("d", 1))
    assert {(item.child_id, item.date) for item in result.assignments} == {
        ("a", dates[0]),
        ("b", dates[1]),
        ("c", dates[3]),
        ("d", dates[2]),
    }


def test_repair_can_cross_a_plateau_and_resize_assignments() -> None:
    dates = (
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
    )
    children = (
        V3Child("a", DAYCARE, 110, excluded_dates=(dates[0], dates[3])),
        V3Child("b", DAYCARE, 20, excluded_dates=(dates[0], dates[2])),
        V3Child("c", DAYCARE, 110, excluded_dates=(dates[1],)),
    )
    config = V3Config(
        open_dates=dates,
        capacity=1,
        operating_start_tick=84,
        operating_end_tick=144,
    )

    result = V3Scheduler(config, children).execute()

    assert result.feasibility.feasible
    assert result.objective.total_shortfall_ticks == 0
    assert result.scheduled_ticks_by_child == (("a", 110), ("b", 20), ("c", 110))


def test_soft_daily_target_cannot_turn_a_feasible_schedule_incomplete() -> None:
    dates = (
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
    )
    children = (
        V3Child("a", DAYCARE, 80, excluded_dates=(dates[0],)),
        V3Child("b", DAYCARE, 100, excluded_dates=(dates[1], dates[3])),
        V3Child("c", DAYCARE, 60, excluded_dates=(dates[2],)),
    )
    base = dict(
        open_dates=dates,
        capacity=1,
        operating_start_tick=84,
        operating_end_tick=144,
    )

    without_target = V3Scheduler(V3Config(**base), children).execute()
    with_target = V3Scheduler(V3Config(**base, daily_unique_target=1), children).execute()

    assert without_target.feasibility.feasible
    assert with_target.feasibility.feasible
    assert with_target.objective.total_shortfall_ticks == 0


def test_preflight_proves_joint_osc_window_shortage() -> None:
    config = V3Config(
        open_dates=("2026-01-05", "2026-01-06", "2026-01-07"),
        capacity=1,
        max_repair_iterations=1,
    )
    result = V3Scheduler(
        config,
        (V3Child("a", OSC, 144), V3Child("b", OSC, 144)),
    ).execute()

    assert not result.feasibility.feasible
    assert result.feasibility.proven
    assert "OSC_WINDOW_CAPACITY_SHORTAGE:144" in result.feasibility.reasons


def test_disabled_repair_is_reported_as_unsearched_not_exhaustive() -> None:
    dates = ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04")
    children = (
        V3Child("a", DAYCARE, 1, excluded_dates=dates[1:]),
        V3Child("b", DAYCARE, 1, excluded_dates=(dates[0], dates[3])),
        V3Child("c", DAYCARE, 1, excluded_dates=(dates[0], dates[2])),
        V3Child("d", DAYCARE, 1, excluded_dates=(dates[1], dates[2])),
    )
    result = V3Scheduler(
        V3Config(
            open_dates=dates,
            capacity=1,
            operating_start_tick=84,
            operating_end_tick=85,
            max_repair_iterations=0,
        ),
        children,
    ).execute()

    assert not result.feasibility.feasible
    assert not result.feasibility.proven
    assert result.feasibility.reasons[0].startswith("SEARCH_BUDGET_EXHAUSTED:")
    repair_trace = next(item for item in result.trace if item.phase == "repair")
    assert ("reason", "disabled") in repair_trace.details


def test_repair_uses_a_bounded_plateau_chain_without_committing_the_plateau() -> None:
    dates = (
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    )
    eligible = {
        "a": {dates[0]},
        "b": {dates[1], dates[2]},
        "c": {dates[1], dates[3]},
        "d": {dates[0], dates[3]},
    }
    children = tuple(
        V3Child(
            child_id,
            DAYCARE,
            1,
            excluded_dates=tuple(item for item in dates if item not in child_dates),
        )
        for child_id, child_dates in eligible.items()
    )
    config = V3Config(
        open_dates=dates,
        capacity=1,
        operating_start_tick=84,
        operating_end_tick=85,
    )

    result = V3Scheduler(config, children).execute()

    assert result.feasibility.feasible
    assert {(item.child_id, item.date) for item in result.assignments} == {
        ("a", dates[0]),
        ("b", dates[2]),
        ("c", dates[1]),
        ("d", dates[3]),
    }
