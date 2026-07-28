from types import SimpleNamespace

import pytest

from app.domain.scheduling.types import (
    ChildPreferences,
    ChildProfile,
    ChildTimeOverride,
    OperatingHours,
    SchedulerConfig,
)
from app.domain.scheduling.v3 import V3LegacyAdapter, execute_v3_schedule
from app.domain.scheduling.v3 import adapter as adapter_module
from app.domain.scheduling.v3.types import (
    FeasibilityResult,
    Objective,
    PhaseTrace,
    ScheduleAssignment,
    TimeBlock,
    V3ScheduleResult,
)


def _config(**values: object) -> SchedulerConfig:
    defaults: dict[str, object] = {
        "open_days": ("2026-01-05",),
        "capacity": 1,
        "operating_hours": OperatingHours(7, 8),
        "enable_predictions": False,
        "enable_fairness_optimization": False,
        "enable_sibling_coherence": False,
    }
    defaults.update(values)
    return SchedulerConfig(**defaults)  # type: ignore[arg-type]


def _child(
    child_id: str = "child",
    hours: float = 1,
    *,
    care_type: str = "Daycare",
    preferences: ChildPreferences | None = None,
) -> ChildProfile:
    return ChildProfile(
        child_id,
        f"Name {child_id}",
        f"family-{child_id}",
        care_type,  # type: ignore[arg-type]
        hours,
        preferences=preferences,
    )


def test_adapter_normalizes_claims_and_translates_exact_five_minute_output() -> None:
    result = execute_v3_schedule(_config(), [_child(hours=0.125)])

    assert result.algorithm_version == "3.0-isolated-adapter"
    assert result.batch_id.startswith("v3-")
    assert len(result.input_hash) == 64
    assert [
        (
            entry.child_id,
            entry.child_name,
            entry.date,
            entry.start_time,
            entry.end_time,
            entry.hours,
        )
        for entry in result.entries
    ] == [("child", "Name child", "2026-01-05", "07:00", "07:10", pytest.approx(2 / 12))]
    warning = next(
        item for item in result.warnings if item.code == "V3_CLAIM_NORMALIZED_TO_FIVE_MINUTES"
    )
    assert "source=0.125h" in warning.message
    assert "normalized=0.166667h" in warning.message
    assert result.stats.requested_hours == pytest.approx(2 / 12)
    assert result.stats.total_hours_scheduled == pytest.approx(2 / 12)
    assert result.stats.completion_percentage == 100
    day = result.utilization_report.daily_utilization[0]
    assert day.scheduled_hours == pytest.approx(2 / 12)
    assert day.utilization == pytest.approx(2 / 12)
    assert day.peak_hour == "07:00"
    assert [(gap.start_time, gap.end_time, gap.unused_capacity) for gap in day.gaps] == [
        ("07:10", "08:00", pytest.approx(10 / 12))
    ]
    assert result.fairness_report.overall_score == 100
    assert result.entries[0].decision.timestamp.isoformat() == "2026-01-05T00:00:00+00:00"
    assert result.audit_trail[-1].action == "v3_independent_audit_passed"


def test_adapter_translates_split_osc_blocks_without_time_loss() -> None:
    result = execute_v3_schedule(
        _config(operating_hours=OperatingHours(7, 18)),
        [_child("osc", 4, care_type="OSC")],
    )

    assert len(result.entries) == 1
    entry = result.entries[0]
    assert (entry.start_time, entry.end_time) == ("07:00", "08:30")
    assert (entry.start_time_2, entry.end_time_2) == ("15:30", "18:00")
    assert entry.hours == 4


@pytest.mark.parametrize(
    ("config", "children", "match"),
    [
        (
            _config(school_off_days=("2026-01-06",)),
            (_child(),),
            "school_off_days must be open_days",
        ),
        (
            _config(child_time_overrides=(ChildTimeOverride("child", start_time_1="08:00"),)),
            (_child(),),
            "does not support child_time_overrides",
        ),
        (
            _config(),
            (_child(preferences=ChildPreferences(start_time_1="08:00", end_time_1="09:00")),),
            "hard custom preference session blocks",
        ),
    ],
)
def test_adapter_rejects_legacy_hard_inputs_instead_of_dropping_them(
    config: SchedulerConfig,
    children: tuple[ChildProfile, ...],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        V3LegacyAdapter(config, children)


def test_adapter_marks_incomplete_results_critical_and_not_persistable() -> None:
    result = execute_v3_schedule(_config(), [_child(hours=2)])

    warning = next(item for item in result.warnings if item.code == "V3_INCOMPLETE_NOT_PERSISTABLE")
    assert warning.severity == "critical"
    assert "unsafe for persistence" in warning.message
    assert "Name child (1.0h short)" in warning.message
    assert "CHILD_WINDOW_SHORTAGE" not in warning.message
    assert warning.affected_children == ("child",)
    assert result.stats.requested_hours == 2
    assert result.stats.total_hours_scheduled == 1
    assert result.stats.hours_shortfall == 1
    assert result.stats.completion_percentage == 50


def test_adapter_marks_failed_daycare_realism_as_a_distinct_exact_diagnostic() -> None:
    result = execute_v3_schedule(
        _config(
            open_days=("2026-01-05", "2026-01-06"),
            operating_hours=OperatingHours(7, 18),
        ),
        [_child(hours=250 / 12)],
    )

    warning = next(
        item
        for item in result.warnings
        if item.code == "V3_DAYCARE_REALISM_NOT_PERSISTABLE"
    )
    assert warning.severity == "critical"
    assert "exact raw claim total" in warning.message
    assert "Name child" in warning.message
    assert warning.affected_children == ("child",)
    assert not any(
        item.code == "V3_INCOMPLETE_NOT_PERSISTABLE" for item in result.warnings
    )
    assert result.stats.completion_percentage == 100
    assert result.stats.hours_shortfall == 0
    assert result.visualization["certification"]["feasible"] is False
    assert result.visualization["certification"]["reasons"] == (
        "DAYCARE_REALISM_PLACEMENT_FAILED",
    )


def test_adapter_warns_when_soft_legacy_inputs_are_not_applied() -> None:
    result = execute_v3_schedule(
        _config(daily_capacity_min=1, daily_capacity_max=2),
        [
            _child(
                preferences=ChildPreferences(
                    preferred_arrival_time="08:00",
                    preferred_days=(1,),
                )
            )
        ],
    )

    codes = {warning.code for warning in result.warnings}
    assert "V3_DAILY_UNIQUE_TARGET_MAPPED" in codes
    assert "V3_SOFT_PREFERENCES_NOT_APPLIED" in codes


def test_adapter_refuses_translation_when_independent_audit_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter_module,
        "audit_schedule_result",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=False,
            violations=(SimpleNamespace(code="CAPACITY_EXCEEDED"),),
        ),
    )

    with pytest.raises(RuntimeError, match="independent audit failed.*CAPACITY_EXCEEDED"):
        execute_v3_schedule(_config(), [_child()])


def test_adapter_refuses_final_daycare_assignment_over_nine_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = ScheduleAssignment(
        "child",
        "2026-01-05",
        (TimeBlock(84, 204),),
        "daycare",
    )
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(False, True, ("DAYCARE_DAILY_DURATION_EXCEEDED",)),
        trace=(PhaseTrace("daycare_realism", "applied"),),
        objective=Objective(1, 0, 0, 0, (("child", "2026-01-05", ((84, 204),)),)),
        requested_ticks=120,
        scheduled_ticks_by_child=(("child", 120),),
    )
    monkeypatch.setattr(adapter_module.V3Scheduler, "execute", lambda _self: result)

    with pytest.raises(
        RuntimeError,
        match="independent audit failed.*DAYCARE_DAILY_DURATION_EXCEEDED",
    ):
        execute_v3_schedule(
            _config(operating_hours=OperatingHours(7, 18)),
            [_child(hours=10)],
        )


def test_adapter_is_deterministic_across_input_child_order() -> None:
    children = [_child("b"), _child("a")]
    config = _config(capacity=2)

    first = execute_v3_schedule(config, children)
    second = execute_v3_schedule(config, reversed(children))

    def stable_shape(result):
        return (
            result.seed,
            result.algorithm_version,
            result.input_hash,
            result.entries,
            result.fairness_report,
            result.utilization_report,
            result.audit_trail,
            result.warnings,
            result.stats,
        )

    assert stable_shape(first) == stable_shape(second)


def test_adapter_hash_is_invariant_to_set_like_input_order() -> None:
    dates = ("2026-01-05", "2026-01-06")
    first = execute_v3_schedule(
        _config(open_days=dates),
        [
            _child(
                preferences=ChildPreferences(
                    excluded_days=(dates[1],),
                    preferred_days=(2, 1),
                    friend_ids=("z", "a"),
                )
            )
        ],
    )
    second = execute_v3_schedule(
        _config(open_days=tuple(reversed(dates))),
        [
            _child(
                preferences=ChildPreferences(
                    excluded_days=(dates[1],),
                    preferred_days=(1, 2),
                    friend_ids=("a", "z"),
                )
            )
        ],
    )

    assert first.input_hash == second.input_hash
