"""Claim simulation request contracts."""

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SchoolBreakInput(CamelModel):
    start: str
    end: str
    name: str | None = None


class HourTiersInput(CamelModel):
    full_time_monthly_target: float = Field(110, gt=0)
    school_age_full_day_target: float = Field(9, gt=0)
    school_age_part_day_target: float = Field(4, gt=0)


class BehavioralProfileInput(CamelModel):
    probability: float = Field(ge=0, le=1)
    variance: float = Field(ge=0, le=1)


class BehavioralProfilesInput(CamelModel):
    consistent: BehavioralProfileInput = BehavioralProfileInput(probability=0.95, variance=0.1)
    variable: BehavioralProfileInput = BehavioralProfileInput(probability=0.8, variance=0.2)
    often_absent: BehavioralProfileInput = BehavioralProfileInput(probability=0.65, variance=0.15)


class ProfileDistributionInput(CamelModel):
    consistent: float = Field(ge=0)
    variable: float = Field(ge=0)
    often_absent: float = Field(ge=0)


class SimulationChildRequest(CamelModel):
    id: str
    name: str
    birth_date: str
    family_id: str | None = None
    enrollment_date: str | None = None
    age_group: str | None = None
    age_in_months: int | None = Field(None, ge=0)
    age_in_years: int | None = Field(None, ge=0)


class ClaimSimulationRequest(CamelModel):
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2200)
    capacity: int = Field(gt=0)
    operating_hours: float = Field(gt=0, le=24)
    children: list[SimulationChildRequest]
    school_break_periods: list[SchoolBreakInput] = []
    holidays: list[str] = []
    hour_tiers: HourTiersInput = HourTiersInput()
    behavioral_profiles: BehavioralProfilesInput = BehavioralProfilesInput()
    full_time_distribution: ProfileDistributionInput = ProfileDistributionInput(
        consistent=40, variable=35, often_absent=25
    )
    school_age_distribution: ProfileDistributionInput = ProfileDistributionInput(
        consistent=55, variable=30, often_absent=15
    )
    seed: str | None = None
    enable_fairness_optimization: bool = True
    enable_sibling_coherence: bool = True
    enable_audit_trail: bool = True
    target_fairness_score: int = Field(85, ge=0, le=100)
    max_optimization_iterations: int = Field(50, ge=0, le=1000)
    family_influence_factor: float = Field(0.3, ge=0, le=1)
