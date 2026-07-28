from datetime import UTC, datetime

from app.domain.scheduling import (
    ChildProfile,
    ScheduleEntry,
    SchedulingDecision,
    SiblingCoherence,
)


def child(identifier: str, family: str, care_type: str = "Daycare") -> ChildProfile:
    return ChildProfile(
        identifier,
        f"Child {identifier}",
        family,
        care_type,  # type: ignore[arg-type]
        100,
    )


def entry(identifier: str, current_date: str) -> ScheduleEntry:
    return ScheduleEntry(
        identifier,
        current_date,
        "09:00",
        "17:00",
        8,
        SchedulingDecision(datetime.now(UTC)),
    )


def test_sibling_detection_dates_and_bonus() -> None:
    coherence = SiblingCoherence(
        [child("1", "family-1"), child("2", "family-1"), child("3", "family-2")]
    )
    schedule = {"2": [entry("2", "2024-01-15"), entry("2", "2024-01-17")]}
    assert coherence.get_siblings("1") == ("2",)
    assert coherence.get_siblings("3") == ()
    assert coherence.is_sibling_scheduled("1", "2024-01-15", schedule)
    assert coherence.get_sibling_scheduled_dates("1", schedule) == (
        "2024-01-15",
        "2024-01-17",
    )
    assert coherence.get_coherence_bonus("1", "2024-01-15", schedule) == 0.8


def test_complete_and_misaligned_family_analysis() -> None:
    children = [child("1", "family-1"), child("2", "family-1")]
    coherence = SiblingCoherence(children)
    schedule = {
        "1": [entry("1", "2024-01-15"), entry("1", "2024-01-16")],
        "2": [entry("2", "2024-01-15"), entry("2", "2024-01-17")],
    }
    result = coherence.analyze_coherence(schedule)
    assert result.family_breakdowns[0].shared_days == 1
    assert result.family_breakdowns[0].total_days == 3
    assert result.score == 1 / 3
    assert result.suggestions


def test_large_and_mixed_care_families() -> None:
    children = [
        child("1", "family-1"),
        child("2", "family-1", "OSC"),
        child("3", "family-1"),
    ]
    coherence = SiblingCoherence(children)
    family = coherence.get_families()[0]
    assert family.coherence_score == 0.8
    assert set(coherence.get_siblings("1")) == {"2", "3"}
    assert coherence.has_siblings("1")
    assert not SiblingCoherence([]).get_families()
