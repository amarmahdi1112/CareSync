"""Business-day and school-break calculations for claim generation."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

DateLike = date | datetime


def _as_date(value: DateLike | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class SchoolBreakPeriod:
    start: date | str
    end: date | str
    name: str | None = None

    def contains(self, value: DateLike) -> bool:
        current = _as_date(value)
        return _as_date(self.start) <= current <= _as_date(self.end)


@dataclass(frozen=True, slots=True)
class BusinessDayCalculation:
    total: int
    breaks: int
    regular: int


class DaycareCalendar:
    """Encapsulate weekday, holiday, and school-break behavior."""

    def __init__(
        self,
        holidays: list[str] | tuple[str, ...] | None = None,
        school_breaks: list[SchoolBreakPeriod] | tuple[SchoolBreakPeriod, ...] | None = None,
    ) -> None:
        self.holidays = frozenset(holidays or ())
        self.school_breaks = tuple(school_breaks or ())

    def is_weekday(self, value: DateLike) -> bool:
        return _as_date(value).weekday() < 5

    def is_business_day(self, value: DateLike) -> bool:
        current = _as_date(value)
        return current.isoformat() not in self.holidays and self.is_weekday(current)

    def is_school_break(self, value: DateLike) -> bool:
        return any(period.contains(value) for period in self.school_breaks)

    def calculate_business_days(
        self, start_date: DateLike, end_date: DateLike
    ) -> BusinessDayCalculation:
        current = _as_date(start_date)
        end = _as_date(end_date)
        total = 0
        break_days = 0

        while current <= end:
            if self.is_business_day(current):
                total += 1
                if self.is_school_break(current):
                    break_days += 1
            current += timedelta(days=1)

        return BusinessDayCalculation(
            total=total,
            breaks=break_days,
            regular=total - break_days,
        )

    def get_business_days_in_range(self, start_date: DateLike, end_date: DateLike) -> list[str]:
        current = _as_date(start_date)
        end = _as_date(end_date)
        days: list[str] = []
        while current <= end:
            if self.is_business_day(current):
                days.append(current.isoformat())
            current += timedelta(days=1)
        return days
