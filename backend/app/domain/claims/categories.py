"""Care-category rules preserved from the legacy claim-generation domain."""

from dataclasses import dataclass, field
from typing import Literal

CareCategory = Literal["FullTime", "SchoolAge"]


@dataclass(frozen=True, slots=True)
class AgeRange:
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class AgeRangeConfig:
    infant: AgeRange = field(default_factory=lambda: AgeRange(0, 1))
    toddler: AgeRange = field(default_factory=lambda: AgeRange(1, 3))
    preschool: AgeRange = field(default_factory=lambda: AgeRange(3, 5))
    kindergarten: AgeRange = field(default_factory=lambda: AgeRange(5, 6))
    school_age: AgeRange = field(default_factory=lambda: AgeRange(6, 12))


class CareCategoryResolver:
    """Resolve the billing category using the configured school-age boundary."""

    def __init__(self, age_ranges: AgeRangeConfig | None = None) -> None:
        self.age_ranges = age_ranges or AgeRangeConfig()

    def resolve(self, age_in_years: float, _age_group: str | None = None) -> CareCategory:
        if age_in_years >= self.age_ranges.school_age.minimum:
            return "SchoolAge"
        return "FullTime"
