"""Age calculations preserved from the legacy claim-generation domain."""

from datetime import date, datetime

DateLike = date | datetime


def _as_date(value: DateLike) -> date:
    return value.date() if isinstance(value, datetime) else value


class AgeCalculator:
    """Calculate completed years or months as of a specific calendar date."""

    @staticmethod
    def get_age_in_years(birth_date: DateLike, as_of_date: DateLike) -> int:
        birth = _as_date(birth_date)
        as_of = _as_date(as_of_date)
        if birth > as_of:
            message = f"Invalid birth date (future): {birth.isoformat()} > {as_of.isoformat()}"
            raise ValueError(message)

        age = as_of.year - birth.year
        if (as_of.month, as_of.day) < (birth.month, birth.day):
            age -= 1
        return age

    @staticmethod
    def get_age_in_months(birth_date: DateLike, as_of_date: DateLike) -> int:
        birth = _as_date(birth_date)
        as_of = _as_date(as_of_date)
        if birth > as_of:
            message = f"Invalid birth date (future): {birth.isoformat()} > {as_of.isoformat()}"
            raise ValueError(message)

        total_months = (as_of.year - birth.year) * 12 + as_of.month - birth.month
        if as_of.day < birth.day:
            total_months -= 1
        return total_months
