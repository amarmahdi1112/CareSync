import random

import pytest

from app.domain.scheduling.v3 import DAYCARE, OSC, V3Child, V3Config, V3Scheduler
from app.domain.scheduling.v3.candidates import (
    best_available_candidate_pattern,
    enumerate_candidate_patterns,
)


def _pattern_key(pattern: object, occupancy: list[int]) -> tuple[object, ...]:
    blocks = pattern.blocks  # type: ignore[attr-defined]
    return (
        sum(
            occupancy[tick] for block in blocks for tick in range(block.start_tick, block.end_tick)
        ),
        tuple((block.start_tick, block.end_tick) for block in blocks),
    )


@pytest.mark.parametrize(
    ("care_type", "school_off", "durations"),
    [
        (DAYCARE, False, (1, 12, 60, 132)),
        (OSC, False, (1, 12, 18, 24, 30, 40, 48)),
        (OSC, True, (1, 12, 60, 132)),
    ],
)
def test_direct_selector_matches_exhaustive_pattern_minimum(
    care_type: str,
    school_off: bool,
    durations: tuple[int, ...],
) -> None:
    current_date = "2026-01-05"
    config = V3Config(
        open_dates=(current_date,),
        school_off_dates=(current_date,) if school_off else (),
        capacity=3,
    )
    child = V3Child("child", care_type, 132)  # type: ignore[arg-type]
    randomizer = random.Random(20260714)

    for duration in durations:
        for _ in range(8):
            occupancy = [0] * config.operating_end_tick
            for tick in range(config.operating_start_tick, config.operating_end_tick):
                occupancy[tick] = randomizer.randrange(config.capacity + 1)
            exhaustive = tuple(
                pattern
                for pattern in enumerate_candidate_patterns(child, config, current_date, duration)
                if all(
                    occupancy[tick] < config.capacity
                    for block in pattern.blocks
                    for tick in range(block.start_tick, block.end_tick)
                )
            )
            expected = min(
                exhaustive,
                key=lambda pattern: _pattern_key(pattern, occupancy),
                default=None,
            )

            actual = best_available_candidate_pattern(
                child,
                config,
                current_date,
                duration,
                occupancy,
            )

            assert actual == expected


def test_partial_osc_selector_avoids_cartesian_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_date = "2026-01-05"
    config = V3Config(open_dates=(current_date,), capacity=2)
    child = V3Child("osc", OSC, 12)
    occupancy = [0] * config.operating_end_tick

    assert len(enumerate_candidate_patterns(child, config, current_date, 12)) == 3491

    def fail_if_exhaustive_enumerator_is_used(*args: object, **kwargs: object) -> object:
        raise AssertionError("direct selection must not enumerate every split placement")

    monkeypatch.setattr(
        "app.domain.scheduling.v3.candidates.enumerate_candidate_patterns",
        fail_if_exhaustive_enumerator_is_used,
    )
    monkeypatch.setattr(
        "app.domain.scheduling.v3.engine.enumerate_candidate_patterns",
        fail_if_exhaustive_enumerator_is_used,
    )

    selected = best_available_candidate_pattern(
        child,
        config,
        current_date,
        12,
        occupancy,
    )

    assert selected is not None
    assert selected.duration_ticks == 12

    result = V3Scheduler(config, (child,)).execute()
    assert result.feasibility.feasible
    assert result.scheduled_ticks_by_child == (("osc", 12),)
