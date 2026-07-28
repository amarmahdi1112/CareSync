"""REST claim-generation endpoints."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser
from app.domain.claims import (
    BehavioralProfileConfig,
    ClaimSimulator,
    ClaimSimulatorConfig,
    HourTiers,
    ProfileDistribution,
    SchoolBreakPeriod,
    SimulationChildInput,
)
from app.schemas.claims import ClaimSimulationRequest

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/simulate", response_model=None)
def simulate_claims(body: ClaimSimulationRequest, current_user: CurrentUser) -> dict[str, Any]:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The authenticated user must belong to an organization",
        )
    profiles = body.behavioral_profiles
    config = ClaimSimulatorConfig(
        organization_id=str(current_user.organization_id),
        month=body.month,
        year=body.year,
        capacity=body.capacity,
        operating_hours=body.operating_hours,
        school_break_periods=tuple(
            SchoolBreakPeriod(item.start, item.end, item.name) for item in body.school_break_periods
        ),
        holidays=tuple(body.holidays),
        hour_tiers=HourTiers(
            body.hour_tiers.full_time_monthly_target,
            body.hour_tiers.school_age_full_day_target,
            body.hour_tiers.school_age_part_day_target,
        ),
        behavioral_profiles={
            "consistent": BehavioralProfileConfig(
                profiles.consistent.probability, profiles.consistent.variance
            ),
            "variable": BehavioralProfileConfig(
                profiles.variable.probability, profiles.variable.variance
            ),
            "oftenAbsent": BehavioralProfileConfig(
                profiles.often_absent.probability, profiles.often_absent.variance
            ),
        },
        full_time_distribution=ProfileDistribution(
            body.full_time_distribution.consistent,
            body.full_time_distribution.variable,
            body.full_time_distribution.often_absent,
        ),
        school_age_distribution=ProfileDistribution(
            body.school_age_distribution.consistent,
            body.school_age_distribution.variable,
            body.school_age_distribution.often_absent,
        ),
        family_influence_factor=body.family_influence_factor,
        seed=body.seed,
        enable_fairness_optimization=body.enable_fairness_optimization,
        enable_sibling_coherence=body.enable_sibling_coherence,
        enable_audit_trail=body.enable_audit_trail,
        target_fairness_score=body.target_fairness_score,
        max_optimization_iterations=body.max_optimization_iterations,
    )
    children = [
        SimulationChildInput(
            id=item.id,
            name=item.name,
            birth_date=item.birth_date,
            family_id=item.family_id,
            enrollment_date=item.enrollment_date,
            age_group=item.age_group,
            age_in_months=item.age_in_months,
            age_in_years=item.age_in_years,
        )
        for item in body.children
    ]
    return asdict(ClaimSimulator(config).run(children))
