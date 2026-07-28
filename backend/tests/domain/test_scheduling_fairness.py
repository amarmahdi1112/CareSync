from datetime import UTC, datetime

from app.domain.random import SeededRandom
from app.domain.scheduling import (
    ChildProfile,
    FairnessCalculator,
    HistoricalAttendance,
    ScheduleEntry,
    SchedulingDecision,
)


def child(identifier: str, claimed: float = 100) -> ChildProfile:
    return ChildProfile(
        identifier, f"Child {identifier}", f"family-{identifier}", "Daycare", claimed
    )


def entry(identifier: str, hours: float) -> ScheduleEntry:
    return ScheduleEntry(
        identifier,
        "2024-01-15",
        "09:00",
        "17:00",
        hours,
        SchedulingDecision(datetime.now(UTC)),
    )


def test_equal_and_unequal_distributions() -> None:
    children = [child("1"), child("2"), child("3")]
    calculator = FairnessCalculator(children, SeededRandom("fairness"))
    equal = calculator.calculate_metrics([entry("1", 20), entry("2", 20), entry("3", 20)])
    unequal = calculator.calculate_metrics([entry("1", 50), entry("2", 10), entry("3", 10)])
    assert equal.gini_coefficient == 0
    assert unequal.gini_coefficient > 0.2
    assert unequal.min_hours_scheduled == 10
    assert unequal.max_hours_scheduled == 50


def test_report_detects_under_and_overserved_children() -> None:
    calculator = FairnessCalculator([child("1"), child("2"), child("3")])
    report = calculator.generate_report([entry("1", 30), entry("2", 5), entry("3", 25)])
    assert "2" in report.underserved_children
    assert "1" in report.overserved_children
    assert report.recommendations
    assert 0 <= report.overall_score <= 100


def test_zero_hours_history_and_priority() -> None:
    history = HistoricalAttendance(8, 0.9, 0.1, 0.05, 0.02, "08:00", "17:00", (90, 95, 88))
    children = [
        ChildProfile("1", "Scheduled", "f1", "Daycare", 100, historical_data=history),
        child("2"),
    ]
    calculator = FairnessCalculator(children, SeededRandom("priority"))
    assert calculator.get_priority_score("1", 0) > 0
    report = calculator.generate_report([entry("1", 50)])
    assert "2" in report.underserved_children
    assert calculator.calculate_metrics([]).average_hours_scheduled == 0


def test_fairness_compares_claim_fulfillment_not_absolute_hours() -> None:
    calculator = FairnessCalculator([child("small", 10), child("large", 100)])
    report = calculator.generate_report([entry("small", 10), entry("large", 100)])

    assert report.overall_score == 100
    assert report.underserved_children == ()
    assert report.overserved_children == ()
