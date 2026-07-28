import json
from dataclasses import asdict
from datetime import date, timedelta

from app.domain.scheduling.engine import SchedulerEngine
from app.domain.scheduling.types import (
    ChildProfile,
    OperatingHours,
    SchedulerConfig,
)
from app.domain.scheduling.v3 import DAYCARE, V3Child, V3Config, V3Scheduler, execute_v3_schedule


def _legacy_config(**values: object) -> SchedulerConfig:
    defaults: dict[str, object] = {
        "open_days": ("2026-01-05",),
        "capacity": 2,
        "operating_hours": OperatingHours(7, 18),
        "enable_predictions": False,
        "enable_fairness_optimization": False,
        "enable_sibling_coherence": False,
    }
    defaults.update(values)
    return SchedulerConfig(**defaults)  # type: ignore[arg-type]


def test_v3_visualization_contains_replay_and_certification_data() -> None:
    result = execute_v3_schedule(
        _legacy_config(),
        (ChildProfile("child", "Child Name", "family", "Daycare", 1),),
    )

    visualization = result.visualization
    assert visualization is not None
    assert visualization["version"] == 1
    assert visualization["tickMinutes"] == 5
    assert visualization["operatingWindow"] == (84, 216)
    assert visualization["phases"][-1]["phase"] == "complete"
    assert visualization["events"] == (
        {
            "sequence": 0,
            "phase": "construct",
            "operation": "place",
            "childId": "child",
            "fromDate": None,
            "toDate": "2026-01-05",
            "fromBlocks": (),
            "toBlocks": ((84, 96),),
            "beforeShortfallTicks": 12,
            "afterShortfallTicks": 0,
            "iteration": None,
        },
    )
    assert visualization["dailyCapacityPeaks"] == (
        {
            "date": "2026-01-05",
            "occupancy": 1,
            "firstTick": 84,
            "capacity": 2,
        },
    )
    assert visualization["children"] == (
        {
            "childId": "child",
            "childName": "Child Name",
            "requestedTicks": 12,
            "scheduledTicks": 12,
        },
    )
    assert visualization["certification"] == {
        "auditValid": True,
        "exactClaims": True,
        "feasible": True,
        "proven": True,
        "violationCodes": (),
        "reasons": (),
        "requestedTicks": 12,
        "scheduledTicks": 12,
    }
    assert not any(item.action == "v3_assignment_translated" for item in result.audit_trail)


def test_visualization_records_only_accepted_repair_diffs_deterministically() -> None:
    dates = ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04")
    eligible = {
        "a": {dates[0]},
        "b": {dates[1]},
        "c": {dates[2], dates[3]},
        "d": {dates[0], dates[2]},
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

    first = V3Scheduler(config, children).execute()
    second = V3Scheduler(config, reversed(children)).execute()
    repair = tuple(event for event in first.visualization_events if event.phase == "repair")

    assert first.visualization_events == second.visualization_events
    assert [
        (event.operation, event.child_id, event.from_date, event.to_date) for event in repair
    ] == [
        ("move", "c", "2026-01-03", "2026-01-04"),
        ("place", "d", None, "2026-01-03"),
    ]
    assert all(event.before_shortfall_ticks == 1 for event in repair)
    assert all(event.after_shortfall_ticks == 0 for event in repair)
    assert all(event.iteration == 0 for event in repair)

    replay: dict[tuple[str, str], tuple[tuple[int, int], ...]] = {}
    for event in first.visualization_events:
        if event.from_date is not None:
            replay.pop((event.child_id, event.from_date), None)
        if event.to_date is not None:
            replay[(event.child_id, event.to_date)] = tuple(
                (block.start_tick, block.end_tick) for block in event.to_blocks
            )
    expected = {
        (assignment.child_id, assignment.date): tuple(
            (block.start_tick, block.end_tick) for block in assignment.blocks
        )
        for assignment in first.assignments
    }
    assert replay == expected


def test_v2_leaves_visualization_unset() -> None:
    result = SchedulerEngine(_legacy_config(), ()).execute()

    assert result.algorithm_version == "2.1-safety"
    assert result.visualization is None


def test_real_sized_visualization_stays_below_session_storage_budget() -> None:
    open_days: list[str] = []
    current = date(2026, 1, 1)
    while len(open_days) < 22:
        if current.weekday() < 5:
            open_days.append(current.isoformat())
        current += timedelta(days=1)

    children = tuple(
        ChildProfile(f"osc-{index:03}", f"OSC {index}", f"of-{index}", "OSC", 88)
        for index in range(134)
    ) + tuple(
        ChildProfile(
            f"daycare-{index:03}",
            f"Daycare {index}",
            f"df-{index}",
            "Daycare",
            88,
        )
        for index in range(49)
    )
    result = execute_v3_schedule(
        _legacy_config(open_days=tuple(open_days), capacity=160, max_iterations=10),
        children,
    )

    assert len(result.entries) >= 3_200
    visualization_size = len(json.dumps(result.visualization, separators=(",", ":")).encode())
    complete_result_size = len(
        json.dumps(asdict(result), default=str, separators=(",", ":")).encode()
    )
    assert visualization_size < 2 * 1024 * 1024
    assert complete_result_size < 4 * 1024 * 1024
