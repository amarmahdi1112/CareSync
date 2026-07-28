import pytest

from app.domain.scheduling.v3 import (
    DAYCARE,
    OSC,
    V3Child,
    V3Config,
    V3Scheduler,
    audit_schedule_result,
)


def _dates(count: int = 10) -> tuple[str, ...]:
    return tuple(f"2026-01-{day:02}" for day in range(5, 5 + count))


def test_exact_daycare_schedule_is_rebalanced_to_six_to_nine_hour_days() -> None:
    config = V3Config(open_dates=_dates(), capacity=2, realism_seed="stable-seed")
    children = (V3Child("b", DAYCARE, 300), V3Child("a", DAYCARE, 300))

    first = V3Scheduler(config, children).execute()
    second = V3Scheduler(config, reversed(children)).execute()

    assert first == second
    assert first.feasibility.feasible
    for child_id in ("a", "b"):
        assignments = [item for item in first.assignments if item.child_id == child_id]
        assert sum(item.duration_ticks for item in assignments) == 300
        assert sorted(item.duration_ticks for item in assignments) == [84, 108, 108]
        assert all(72 <= item.duration_ticks <= 108 for item in assignments)
        assert len({item.date for item in assignments}) == len(assignments)
        start_ticks = [item.blocks[0].start_tick for item in assignments]
        assert max(start_ticks) - min(start_ticks) <= 12
    realism = next(item for item in first.trace if item.phase == "daycare_realism")
    assert realism.action == "applied"
    assert ("max_daily_ticks", "108") in realism.details
    realism_events = [
        event for event in first.visualization_events if event.phase == "daycare_realism"
    ]
    assert realism_events
    assert {event.operation for event in realism_events} <= {
        "move",
        "resize",
        "place",
        "remove",
    }


def test_realism_seed_changes_daycare_variation_but_remains_reproducible() -> None:
    children = (V3Child("a", DAYCARE, 300), V3Child("b", DAYCARE, 300))

    alpha = V3Scheduler(
        V3Config(open_dates=_dates(), capacity=2, realism_seed="alpha"), children
    ).execute()
    alpha_again = V3Scheduler(
        V3Config(open_dates=_dates(), capacity=2, realism_seed="alpha"), children
    ).execute()
    beta = V3Scheduler(
        V3Config(open_dates=_dates(), capacity=2, realism_seed="beta"), children
    ).execute()

    assert alpha.assignments == alpha_again.assignments
    assert alpha.assignments != beta.assignments
    assert sorted(item.duration_ticks for item in alpha.assignments) == sorted(
        item.duration_ticks for item in beta.assignments
    )


def test_rebalancer_preserves_exclusions_osc_assignments_and_capacity() -> None:
    dates = _dates(6)
    children = (
        V3Child("daycare", DAYCARE, 264, excluded_dates=(dates[0], dates[1])),
        V3Child("osc", OSC, 96),
    )
    result = V3Scheduler(
        V3Config(open_dates=dates, capacity=1, realism_seed="mixed"),
        children,
    ).execute()

    assert result.feasibility.feasible
    daycare = [item for item in result.assignments if item.child_id == "daycare"]
    osc = [item for item in result.assignments if item.child_id == "osc"]
    assert sum(item.duration_ticks for item in daycare) == 264
    assert all(item.date not in {dates[0], dates[1]} for item in daycare)
    assert all(item.duration_ticks <= 108 for item in daycare)
    assert sum(item.duration_ticks for item in osc) == 96
    occupancy: dict[tuple[str, int], int] = {}
    for assignment in result.assignments:
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                key = (assignment.date, tick)
                occupancy[key] = occupancy.get(key, 0) + 1
    assert max(occupancy.values()) <= 1


def test_failed_realism_transaction_rolls_back_and_invalidates_feasibility() -> None:
    dates = _dates(2)
    result = V3Scheduler(
        V3Config(open_dates=dates, capacity=1, realism_seed="rollback"),
        (V3Child("daycare", DAYCARE, 250),),
    ).execute()

    assert not result.feasibility.feasible
    assert not result.feasibility.proven
    assert result.feasibility.reasons == ("DAYCARE_REALISM_PLACEMENT_FAILED",)
    assert [(item.date, item.duration_ticks) for item in result.assignments] == [
        (dates[0], 132),
        (dates[1], 118),
    ]
    realism = next(item for item in result.trace if item.phase == "daycare_realism")
    assert realism.action == "rolled_back"
    assert not any(event.phase == "daycare_realism" for event in result.visualization_events)


def test_realism_transaction_recomputes_and_rejects_tick_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = _dates(2)
    monkeypatch.setattr(
        V3Scheduler,
        "_daycare_duration_plan",
        lambda _self, _child: (100, 99),
    )

    result = V3Scheduler(
        V3Config(open_dates=dates, capacity=1, realism_seed="tick-loss"),
        (V3Child("daycare", DAYCARE, 200),),
    ).execute()

    assert not result.feasibility.feasible
    assert result.feasibility.reasons == ("DAYCARE_REALISM_PLACEMENT_FAILED",)
    assert sum(item.duration_ticks for item in result.assignments) == 200
    realism = next(item for item in result.trace if item.phase == "daycare_realism")
    assert realism.action == "rolled_back"
    assert ("reason", "transaction_validation_failed") in realism.details


def test_short_exact_daycare_schedule_is_certified_without_unnecessary_changes() -> None:
    result = V3Scheduler(
        V3Config(open_dates=_dates(1), capacity=1, realism_seed="short"),
        (V3Child("daycare", DAYCARE, 60),),
    ).execute()

    assert result.feasibility.feasible
    assert result.assignments[0].duration_ticks == 60
    realism = next(item for item in result.trace if item.phase == "daycare_realism")
    assert realism.action == "applied"
    assert ("reason", "already_within_bounds") in realism.details


@pytest.mark.parametrize("realism_seed", ("dense-fallback", "dense-a", "dense-b"))
def test_day_count_fallback_fits_dense_daycare_into_osc_midday_capacity(
    realism_seed: str,
) -> None:
    dates = _dates(10)
    children = tuple(V3Child(f"osc-{index}", OSC, 480) for index in range(6)) + tuple(
        V3Child(f"daycare-{index}", DAYCARE, 600) for index in range(10)
    )
    config = V3Config(
        open_dates=dates,
        capacity=8,
        realism_seed=realism_seed,
    )

    first = V3Scheduler(config, children).execute()
    second = V3Scheduler(config, reversed(children)).execute()

    assert first == second
    assert first.feasibility.feasible
    assert sum(item.duration_ticks for item in first.assignments) == sum(
        child.claimed_ticks for child in children
    )
    daycare = [item for item in first.assignments if item.child_id.startswith("daycare-")]
    assert all(item.duration_ticks <= 108 for item in daycare)
    for child in (f"daycare-{index}" for index in range(10)):
        durations = [item.duration_ticks for item in daycare if item.child_id == child]
        assert sum(duration < 72 for duration in durations) <= 1
        assert all(duration >= 72 for duration in durations if duration != min(durations))
    occupancy: dict[tuple[str, int], int] = {}
    for assignment in first.assignments:
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                key = (assignment.date, tick)
                occupancy[key] = occupancy.get(key, 0) + 1
    assert max(occupancy.values()) <= config.capacity
    realism = next(item for item in first.trace if item.phase == "daycare_realism")
    assert realism.action == "applied"
    assert int(dict(realism.details)["attempts"]) > 1
    audit = audit_schedule_result(first, children, config, require_exact_claims=True)
    assert audit.valid


def test_fallback_is_not_seed_dependent_for_constrained_mixed_fixture() -> None:
    dates = _dates(3)
    children = (
        V3Child("o0", OSC, 68),
        V3Child("o1", OSC, 97),
        V3Child("o2", OSC, 58),
        V3Child("d0", DAYCARE, 181, excluded_dates=(dates[2],)),
        V3Child("d1", DAYCARE, 108, excluded_dates=dates[:2]),
        V3Child("d2", DAYCARE, 108, excluded_dates=dates[:2]),
        V3Child("d3", DAYCARE, 123),
    )

    for seed in ("c10s0", "c10s1", "alpha", "beta"):
        config = V3Config(open_dates=dates, capacity=3, realism_seed=seed)
        result = V3Scheduler(config, children).execute()
        assert result.feasibility.feasible
        assert audit_schedule_result(
            result,
            children,
            config,
            require_exact_claims=True,
        ).valid


def test_canonical_rescue_handles_tight_exclusions_across_seeds() -> None:
    dates = _dates(5)
    children = (
        V3Child("d0", DAYCARE, 344),
        V3Child("d1", DAYCARE, 136, excluded_dates=(dates[0], dates[4])),
        V3Child("d2", DAYCARE, 194, excluded_dates=(dates[2], dates[3])),
        V3Child("d3", DAYCARE, 113, excluded_dates=dates[1:4]),
        V3Child("d4", DAYCARE, 214, excluded_dates=dates[:3]),
        V3Child("d5", DAYCARE, 388),
    )

    for seed in ("excluded_no_osc45s0", "excluded_no_osc45s1"):
        config = V3Config(open_dates=dates, capacity=3, realism_seed=seed)
        result = V3Scheduler(config, children).execute()
        assert result.feasibility.feasible
        assert audit_schedule_result(
            result,
            children,
            config,
            require_exact_claims=True,
        ).valid


def test_canonical_anchor_rescues_are_seed_independent_with_mixed_osc() -> None:
    dates = tuple(f"2026-03-0{day}" for day in range(2, 9))
    children = (
        V3Child("o0", OSC, 303),
        V3Child("o1", OSC, 277),
        V3Child("o2", OSC, 49),
        V3Child("d0", DAYCARE, 531, excluded_dates=(dates[2], dates[4])),
        V3Child("d1", DAYCARE, 206, excluded_dates=(dates[0], *dates[3:6])),
        V3Child("d2", DAYCARE, 482, excluded_dates=(dates[4], dates[6])),
        V3Child("d3", DAYCARE, 269, excluded_dates=(dates[0],)),
    )

    for index in range(8):
        config = V3Config(
            open_dates=dates,
            capacity=3,
            realism_seed=f"z41s{index}",
        )
        result = V3Scheduler(config, children).execute()
        assert result.feasibility.feasible
        assert audit_schedule_result(
            result,
            children,
            config,
            require_exact_claims=True,
        ).valid


def test_realism_handles_a_full_183_child_batch_exactly_and_within_capacity() -> None:
    dates = _dates(10)
    children = tuple(
        V3Child(f"child-{index:03}", DAYCARE, 300 + ((index * 37) % 300)) for index in range(183)
    )
    result = V3Scheduler(
        V3Config(open_dates=dates, capacity=140, realism_seed="stress-183"),
        children,
    ).execute()

    assert result.feasibility.feasible
    assert sum(item.duration_ticks for item in result.assignments) == sum(
        child.claimed_ticks for child in children
    )
    assert all(item.duration_ticks <= 108 for item in result.assignments)
    occupancy: dict[tuple[str, int], int] = {}
    for assignment in result.assignments:
        for block in assignment.blocks:
            for tick in range(block.start_tick, block.end_tick):
                key = (assignment.date, tick)
                occupancy[key] = occupancy.get(key, 0) + 1
    assert max(occupancy.values()) <= 140
