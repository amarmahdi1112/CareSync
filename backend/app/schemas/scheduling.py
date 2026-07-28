"""Scheduling request contracts."""

from datetime import date

from pydantic import Field, field_validator, model_validator

from app.schemas.claims import CamelModel


class OperatingHoursInput(CamelModel):
    start: int = Field(7, ge=0, le=23)
    end: int = Field(18, ge=1, le=24)


class ChildPreferencesInput(CamelModel):
    preferred_arrival_time: str | None = None
    preferred_departure_time: str | None = None
    preferred_days: list[int] = Field(default_factory=list)
    excluded_days: list[str] = Field(default_factory=list)
    start_time_1: str | None = None
    end_time_1: str | None = None
    start_time_2: str | None = None
    end_time_2: str | None = None
    friend_ids: list[str] = Field(default_factory=list)
    avoid_child_ids: list[str] = Field(default_factory=list)

    @field_validator("preferred_days")
    @classmethod
    def validate_weekdays(cls, values: list[int]) -> list[int]:
        if any(value < 0 or value > 6 for value in values):
            raise ValueError("preferred days must use 0 (Sunday) through 6 (Saturday)")
        return values

    @field_validator("excluded_days")
    @classmethod
    def validate_excluded_dates(cls, values: list[str]) -> list[str]:
        _validate_dates(values, "excluded days")
        return values

    @field_validator(
        "preferred_arrival_time",
        "preferred_departure_time",
        "start_time_1",
        "end_time_1",
        "start_time_2",
        "end_time_2",
    )
    @classmethod
    def validate_times(cls, value: str | None) -> str | None:
        return _validate_time(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> "ChildPreferencesInput":
        _validate_time_blocks(
            self.start_time_1, self.end_time_1, self.start_time_2, self.end_time_2
        )
        return self


class SchedulerChildInput(CamelModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    care_type: str = Field(pattern="^(Daycare|OSC)$")
    total_claimed_hours: float = Field(ge=0, le=10_000, allow_inf_nan=False)
    enrollment_date: str | None = None
    preferences: ChildPreferencesInput | None = None

    @field_validator("enrollment_date", mode="before")
    @classmethod
    def validate_enrollment_date(cls, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        normalized = str(value).strip()
        date.fromisoformat(normalized)
        return normalized


class ChildTimeOverrideInput(CamelModel):
    child_identifier: str = Field(min_length=1)
    days_of_week: list[int] = Field(default_factory=list)
    start_time_1: str | None = None
    end_time_1: str | None = None
    start_time_2: str | None = None
    end_time_2: str | None = None

    @field_validator("days_of_week")
    @classmethod
    def validate_weekdays(cls, values: list[int]) -> list[int]:
        if any(value < 0 or value > 6 for value in values):
            raise ValueError("override days must use 0 (Sunday) through 6 (Saturday)")
        return values

    @field_validator("start_time_1", "end_time_1", "start_time_2", "end_time_2")
    @classmethod
    def validate_times(cls, value: str | None) -> str | None:
        return _validate_time(value)

    @model_validator(mode="after")
    def validate_time_order(self) -> "ChildTimeOverrideInput":
        _validate_time_blocks(
            self.start_time_1, self.end_time_1, self.start_time_2, self.end_time_2
        )
        return self


class ScheduleGenerationRequest(CamelModel):
    open_days: list[str] = Field(min_length=1, max_length=366)
    capacity: int = Field(gt=0, le=10_000)
    operating_hours: OperatingHoursInput = OperatingHoursInput()
    school_off_days: list[str] = Field(default_factory=list, max_length=366)
    daily_capacity_min: int | None = Field(None, ge=0)
    daily_capacity_max: int | None = Field(None, ge=1)
    enable_predictions: bool = True
    enable_fairness_optimization: bool = True
    enable_sibling_coherence: bool = True
    enable_audit_trail: bool = True
    max_iterations: int = Field(100, ge=0, le=10_000)
    seed: str | None = None
    persist: bool = False
    source_claim_batch_id: str | None = Field(None, max_length=100)
    child_time_overrides: list[ChildTimeOverrideInput] = Field(
        default_factory=list, max_length=5_000
    )
    children: list[SchedulerChildInput] = Field(min_length=1, max_length=5_000)

    @field_validator("open_days", "school_off_days")
    @classmethod
    def validate_schedule_dates(cls, values: list[str]) -> list[str]:
        _validate_dates(values, "schedule dates")
        return values

    @model_validator(mode="after")
    def validate_configuration(self) -> "ScheduleGenerationRequest":
        if self.operating_hours.end <= self.operating_hours.start:
            raise ValueError("operating hours must end after they start")
        if len(set(self.open_days)) != len(self.open_days):
            raise ValueError("open days cannot contain duplicate dates")
        identifiers = [child.id for child in self.children]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("children cannot contain duplicate IDs")
        effective_max = self.daily_capacity_max
        if (
            self.daily_capacity_min is not None
            and effective_max is not None
            and self.daily_capacity_min > effective_max
        ):
            raise ValueError("daily capacity minimum cannot exceed the maximum")
        opening = self.operating_hours.start * 60
        closing = self.operating_hours.end * 60
        timed_values = [
            preferences for child in self.children if (preferences := child.preferences) is not None
        ]
        timed_values.extend(self.child_time_overrides)
        for value in timed_values:
            for time_value in (
                value.start_time_1,
                value.end_time_1,
                value.start_time_2,
                value.end_time_2,
            ):
                if time_value and not opening <= _minutes(time_value) <= closing:
                    raise ValueError("child time blocks must be within operating hours")
        return self


def _validate_dates(values: list[str], label: str) -> None:
    for value in values:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must contain valid ISO dates") from exc


def _validate_time(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("times must use HH:MM") from exc
    if len(hour_text) != 2 or len(minute_text) != 2 or not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("times must use valid 24-hour HH:MM values")
    return value


def _validate_time_blocks(
    start_1: str | None,
    end_1: str | None,
    start_2: str | None,
    end_2: str | None,
) -> None:
    if bool(start_1) != bool(end_1):
        raise ValueError("first session needs both a start and end time")
    if bool(start_2) != bool(end_2):
        raise ValueError("second session needs both a start and end time")
    if start_1 and end_1 and _minutes(end_1) <= _minutes(start_1):
        raise ValueError("first session must end after it starts")
    if start_2 and end_2 and _minutes(end_2) <= _minutes(start_2):
        raise ValueError("second session must end after it starts")
    if end_1 and start_2 and _minutes(start_2) < _minutes(end_1):
        raise ValueError("second session cannot overlap the first")


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)
