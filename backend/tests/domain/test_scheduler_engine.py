import pytest

from app.domain.scheduling import (
    ChildPreferences,
    ChildProfile,
    ChildTimeOverride,
    OperatingHours,
    SchedulerConfig,
    SchedulerEngine,
)


def config(
    days: tuple[str, ...] = (
        "2024-01-15",
        "2024-01-16",
        "2024-01-17",
        "2024-01-18",
        "2024-01-19",
    ),
    **overrides: object,
) -> SchedulerConfig:
    values: dict[str, object] = {
        "open_days": days,
        "capacity": 10,
        "operating_hours": OperatingHours(7, 18),
        "seed": "scheduler-test",
        "max_iterations": 10,
    }
    values.update(overrides)
    return SchedulerConfig(**values)  # type: ignore[arg-type]


def child(
    identifier: str,
    claimed: float = 40,
    care_type: str = "Daycare",
    family: str | None = None,
) -> ChildProfile:
    return ChildProfile(
        identifier,
        f"Child {identifier}",
        family or f"family-{identifier}",
        care_type,  # type: ignore[arg-type]
        claimed,
    )


def test_scheduler_is_deterministic_and_respects_claimed_hours() -> None:
    children = [child("1", 20), child("2", 20)]
    first = SchedulerEngine(config(), children).execute()
    second = SchedulerEngine(config(), children).execute()
    first_shape = [
        (item.child_id, item.date, item.start_time, item.end_time, item.hours)
        for item in first.entries
    ]
    second_shape = [
        (item.child_id, item.date, item.start_time, item.end_time, item.hours)
        for item in second.entries
    ]
    assert first_shape == second_shape
    assert first.stats.total_entries == len(first.entries)
    assert first.stats.children_scheduled <= 2
    assert all(
        sum(item.hours for item in first.entries if item.child_id == profile.id)
        <= profile.total_claimed_hours + 0.01
        for profile in children
    )


def test_scheduler_matches_compiled_legacy_golden_fixture() -> None:
    result = SchedulerEngine(config(), [child("1", 20), child("2", 20)]).execute()
    assert [
        (item.child_id, item.date, item.start_time, item.end_time, item.hours)
        for item in result.entries
    ] == [
        ("1", "2024-01-15", "07:45", "11:45", 4.0),
        ("2", "2024-01-15", "07:45", "11:45", 4.0),
        ("2", "2024-01-16", "07:45", "11:45", 4.0),
        ("1", "2024-01-16", "08:15", "12:15", 4.0),
        ("1", "2024-01-17", "08:00", "12:00", 4.0),
        ("2", "2024-01-17", "07:30", "11:30", 4.0),
        ("2", "2024-01-18", "07:30", "11:30", 4.0),
        ("1", "2024-01-18", "08:00", "12:00", 4.0),
        ("2", "2024-01-19", "08:15", "12:15", 4.0),
        ("1", "2024-01-19", "08:00", "12:00", 4.0),
    ]
    assert result.stats.total_hours_scheduled == 40
    assert result.fairness_report.overall_score == 100
    assert result.utilization_report.overall_utilization == 0.07272727272727272


def test_scheduler_builds_fairness_utilization_decisions_and_audit() -> None:
    result = SchedulerEngine(config(), [child("1"), child("2"), child("3")]).execute()
    assert result.entries
    assert 0 <= result.fairness_report.overall_score <= 100
    assert len(result.utilization_report.daily_utilization) == 5
    assert result.stats.total_hours_scheduled > 0
    assert result.audit_trail
    assert result.entries[0].decision.reason
    assert result.entries[0].decision.confidence_score == 1


def test_scheduler_handles_osc_and_sibling_overlap() -> None:
    children = [
        child("daycare", 30),
        child("osc", 15, "OSC"),
        child("sibling", 30, family="family-daycare"),
    ]
    result = SchedulerEngine(config(), children).execute()
    daycare = [item for item in result.entries if item.child_id == "daycare"]
    osc = [item for item in result.entries if item.child_id == "osc"]
    sibling = [item for item in result.entries if item.child_id == "sibling"]
    assert daycare and osc and sibling
    assert sum(item.hours for item in osc) / len(osc) <= (
        sum(item.hours for item in daycare) / len(daycare)
    )
    assert set(item.date for item in daycare) & set(item.date for item in sibling)


def test_low_capacity_produces_warning_and_zero_hours_are_filtered() -> None:
    limited = config(
        days=("2024-01-15", "2024-01-16", "2024-01-17"),
        capacity=1,
    )
    result = SchedulerEngine(
        limited,
        [child("1", 100), child("2", 100), child("zero", 0)],
    ).execute()
    assert any("CAPACITY" in warning.code for warning in result.warnings)
    assert not [item for item in result.entries if item.child_id == "zero"]


def test_empty_children_disabled_audit_and_single_day() -> None:
    result = SchedulerEngine(config(days=("2024-01-15",), enable_audit_trail=False), []).execute()
    assert result.entries == ()
    assert result.stats.children_scheduled == 0
    assert result.audit_trail == ()
    assert len(result.utilization_report.daily_utilization) == 1


def test_scheduler_enforces_enrollment_and_excluded_dates() -> None:
    profile = ChildProfile(
        "enrolled",
        "Enrolled Child",
        "family-enrolled",
        "Daycare",
        12,
        "2024-01-17",
        ChildPreferences(excluded_days=("2024-01-18",)),
    )
    result = SchedulerEngine(config(), [profile]).execute()

    assert result.entries
    assert all(item.date >= "2024-01-17" for item in result.entries)
    assert all(item.date != "2024-01-18" for item in result.entries)


def test_small_osc_budget_never_reserves_or_reports_extra_hours() -> None:
    profile = child("osc-small", 0.5, "OSC")
    result = SchedulerEngine(
        config(days=("2024-01-15",), max_iterations=2),
        [profile],
    ).execute()

    assert result.entries

    def duration(start: str, end: str) -> float:
        start_hour, start_minute = map(int, start.split(":"))
        end_hour, end_minute = map(int, end.split(":"))
        return ((end_hour * 60 + end_minute) - (start_hour * 60 + start_minute)) / 60

    actual = sum(
        duration(item.start_time, item.end_time)
        + (
            duration(item.start_time_2, item.end_time_2)
            if item.start_time_2 and item.end_time_2
            else 0
        )
        for item in result.entries
    )
    assert actual == pytest.approx(result.stats.total_hours_scheduled)
    assert actual <= profile.total_claimed_hours


def test_subminute_osc_remainder_never_creates_a_zero_width_block() -> None:
    profile = ChildProfile(
        "osc-fractional",
        "Fractional OSC",
        "family-osc-fractional",
        "OSC",
        1.0125,
        preferences=ChildPreferences(
            start_time_1="07:00",
            end_time_1="08:00",
            start_time_2="15:00",
            end_time_2="16:00",
        ),
    )
    result = SchedulerEngine(
        config(days=("2024-01-15",), max_iterations=2),
        [profile],
    ).execute()

    assert result.entries
    assert all(entry.start_time < entry.end_time for entry in result.entries)
    assert all(
        not entry.start_time_2 or entry.start_time_2 < entry.end_time_2 for entry in result.entries
    )


def test_explicit_time_overrides_are_exact_and_not_randomly_dropped() -> None:
    overridden = ChildProfile(
        "overridden",
        "Overridden Child",
        "family-overridden",
        "OSC",
        3.5,
    )
    result = SchedulerEngine(
        config(
            days=("2024-01-15",),
            seed="0",
            child_time_overrides=(
                ChildTimeOverride(
                    "overridden",
                    start_time_1="07:00",
                    end_time_1="08:30",
                    start_time_2="15:00",
                    end_time_2="17:00",
                ),
            ),
        ),
        [overridden],
    ).execute()

    assert [
        (entry.start_time, entry.end_time, entry.start_time_2, entry.end_time_2)
        for entry in result.entries
    ] == [("07:00", "08:30", "15:00", "17:00")]


def test_daycare_override_is_not_moved_when_its_exact_block_is_full() -> None:
    blocker = child("blocker", 2)
    overridden = child("overridden", 2)
    result = SchedulerEngine(
        config(
            days=("2024-01-15",),
            capacity=1,
            seed="0",
            child_time_overrides=(
                ChildTimeOverride("blocker", start_time_1="10:00", end_time_1="12:00"),
                ChildTimeOverride("overridden", start_time_1="10:00", end_time_1="12:00"),
            ),
        ),
        [blocker, overridden],
    ).execute()

    entries = [entry for entry in result.entries if entry.child_id == "overridden"]
    assert not entries or all(
        (entry.start_time, entry.end_time) == ("10:00", "12:00") for entry in entries
    )


def test_scheduler_rejects_duplicate_children_and_reports_completion() -> None:
    with pytest.raises(ValueError, match="duplicate IDs"):
        SchedulerEngine(config(), [child("same"), child("same")])

    result = SchedulerEngine(config(), [child("one", 10), child("two", 10)]).execute()
    assert result.stats.requested_children == 2
    assert result.stats.requested_hours == 20
    assert result.stats.unscheduled_children == 0
    assert result.stats.hours_shortfall == pytest.approx(0)
    assert result.stats.completion_percentage == pytest.approx(100)


def test_daily_unique_child_target_is_distinct_from_simultaneous_capacity() -> None:
    engine = SchedulerEngine(
        config(capacity=2, daily_capacity_min=5, daily_capacity_max=10),
        [child("one")],
    )
    assert engine._effective_max() == 10
    assert engine._effective_min() == 5

    zero_minimum = SchedulerEngine(
        config(capacity=2, daily_capacity_min=0, daily_capacity_max=10),
        [child("one")],
    )
    assert zero_minimum._effective_min() == 0


def test_seeded_output_is_independent_of_input_child_order() -> None:
    children = [child("a", 20), child("b", 20), child("c", 20)]
    forward = SchedulerEngine(config(), children).execute()
    reverse = SchedulerEngine(config(), list(reversed(children))).execute()

    def shape(result):
        return [
            (entry.child_id, entry.date, entry.start_time, entry.end_time, entry.hours)
            for entry in result.entries
        ]

    assert shape(forward) == shape(reverse)
    assert forward.input_hash == reverse.input_hash


def test_time_overrides_are_exact_and_ambiguous_names_are_rejected() -> None:
    exact = SchedulerEngine(
        config(
            days=("2024-01-15",),
            child_time_overrides=(
                ChildTimeOverride("child-1", start_time_1="10:00", end_time_1="12:00"),
            ),
        ),
        [child("child-1", 2)],
    ).execute()
    assert [(entry.start_time, entry.end_time) for entry in exact.entries] == [("10:00", "12:00")]

    duplicate_names = [
        ChildProfile("one", "Same Name", "family-one", "Daycare", 4),
        ChildProfile("two", "Same Name", "family-two", "Daycare", 4),
    ]
    with pytest.raises(ValueError, match="ambiguous child time override"):
        SchedulerEngine(
            config(
                child_time_overrides=(
                    ChildTimeOverride("Same Name", start_time_1="09:00", end_time_1="11:00"),
                )
            ),
            duplicate_names,
        )
