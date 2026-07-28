from datetime import UTC, date, datetime

import pytest

from app.domain.claims import (
    AgeCalculator,
    AgeRange,
    AgeRangeConfig,
    CareCategoryResolver,
    DaycareCalendar,
    SchoolBreakPeriod,
)


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        (date(2020, 1, 15), date(2024, 1, 15), 4),
        (date(2020, 6, 15), date(2024, 1, 15), 3),
        (date(2020, 2, 29), date(2024, 2, 28), 3),
        (date(2020, 12, 31), date(2024, 1, 1), 3),
        (date(2020, 3, 1), date(2024, 2, 29), 3),
    ],
)
def test_age_in_years_matches_legacy(birth: date, as_of: date, expected: int) -> None:
    assert AgeCalculator.get_age_in_years(birth, as_of) == expected


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        (date(2024, 1, 15), date(2024, 7, 15), 6),
        (date(2024, 1, 20), date(2024, 2, 15), 0),
        (date(2023, 11, 15), date(2024, 2, 15), 3),
        (date(2020, 1, 15), date(2024, 7, 15), 54),
    ],
)
def test_age_in_months_matches_legacy(birth: date, as_of: date, expected: int) -> None:
    assert AgeCalculator.get_age_in_months(birth, as_of) == expected


def test_age_calculator_rejects_future_birth_date_and_accepts_datetime() -> None:
    with pytest.raises(ValueError, match="future"):
        AgeCalculator.get_age_in_years(date(2025, 1, 15), date(2024, 1, 15))
    assert AgeCalculator.get_age_in_years(
        datetime(2020, 1, 15, tzinfo=UTC),
        datetime(2024, 1, 15, tzinfo=UTC),
    ) == 4


def test_care_category_uses_school_age_minimum() -> None:
    default = CareCategoryResolver()
    assert default.resolve(5.9) == "FullTime"
    assert default.resolve(6) == "SchoolAge"
    assert default.resolve(7, "Preschool") == "SchoolAge"

    custom = CareCategoryResolver(
        AgeRangeConfig(school_age=AgeRange(5, 12))
    )
    assert custom.resolve(4) == "FullTime"
    assert custom.resolve(5) == "SchoolAge"


def test_business_days_exclude_weekends_and_holidays() -> None:
    calendar = DaycareCalendar(["2024-01-16", "2024-01-17"])
    result = calendar.calculate_business_days(date(2024, 1, 15), date(2024, 1, 21))
    assert (result.total, result.breaks, result.regular) == (3, 0, 3)
    assert calendar.get_business_days_in_range(date(2024, 1, 15), date(2024, 1, 19)) == [
        "2024-01-15",
        "2024-01-18",
        "2024-01-19",
    ]


def test_school_breaks_are_inclusive_and_only_count_business_days() -> None:
    calendar = DaycareCalendar(
        school_breaks=[SchoolBreakPeriod("2024-01-13", "2024-01-18", "Winter Break")]
    )
    result = calendar.calculate_business_days(date(2024, 1, 13), date(2024, 1, 19))
    assert (result.total, result.breaks, result.regular) == (5, 4, 1)
    assert calendar.is_school_break(date(2024, 1, 13))
    assert calendar.is_school_break(date(2024, 1, 18))
    assert not calendar.is_school_break(date(2024, 1, 19))


def test_calendar_handles_month_year_and_empty_boundaries() -> None:
    calendar = DaycareCalendar()
    assert calendar.calculate_business_days(date(2024, 1, 1), date(2024, 1, 31)).total == 23
    assert calendar.calculate_business_days(date(2024, 2, 1), date(2024, 2, 29)).total == 21
    assert calendar.calculate_business_days(date(2024, 1, 15), date(2024, 1, 15)).total == 1
    assert calendar.calculate_business_days(date(2024, 1, 16), date(2024, 1, 15)).total == 0
