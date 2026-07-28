from app.domain.claims import (
    ClaimSimulator,
    ClaimSimulatorConfig,
    SimulationChildInput,
)


def config(**overrides: object) -> ClaimSimulatorConfig:
    values: dict[str, object] = {
        "organization_id": "org-1",
        "month": 1,
        "year": 2024,
        "capacity": 20,
        "operating_hours": 10,
    }
    values.update(overrides)
    return ClaimSimulatorConfig(**values)  # type: ignore[arg-type]


def children(count: int) -> list[SimulationChildInput]:
    return [
        SimulationChildInput(
            id=f"child-{index + 1}",
            name=f"Child {index + 1}",
            family_id=f"family-{index // 2 + 1}",
            birth_date="2020-01-01",
            age_group="preschool",
        )
        for index in range(count)
    ]


def test_simulation_is_deterministic_and_complete() -> None:
    first = ClaimSimulator(config(seed="test-seed-123")).run(children(5))
    second = ClaimSimulator(config(seed="test-seed-123")).run(children(5))
    assert [claim.projected_hours for claim in first.claims] == [
        claim.projected_hours for claim in second.claims
    ]
    assert len(first.claims) == 5
    assert first.stats.total_claims == 5
    assert first.stats.total_hours_projected > 0
    assert first.audit_trail
    assert first.utilization_report.daily_utilization
    assert 0 <= first.utilization_report.overall_utilization <= 1


def test_simulation_matches_compiled_legacy_golden_fixture() -> None:
    fixture = [
        SimulationChildInput(
            id=f"child-{index + 1}",
            name=f"Child {index + 1}",
            family_id=f"family-{index // 2 + 1}",
            birth_date="2020-01-01",
            enrollment_date="2024-01-01",
            age_group="preschool",
        )
        for index in range(5)
    ]
    result = ClaimSimulator(config(seed="test-seed-123", enable_audit_trail=False)).run(fixture)
    assert [item.projected_hours for item in result.claims] == [
        100.37,
        78.16,
        72.0,
        83.59,
        96.0,
    ]
    assert [item.behavioral_profile for item in result.claims] == [
        "variable",
        "oftenAbsent",
        "oftenAbsent",
        "oftenAbsent",
        "variable",
    ]
    assert [item.projected_attendance_days for item in result.claims] == [22, 19, 20, 20, 18]
    assert result.fairness_report.overall_score == 93
    assert result.stats.optimization_iterations == 0
    assert result.utilization_report.overall_utilization == 0.22


def test_simulation_respects_enrollment_and_care_category() -> None:
    inputs = [
        SimulationChildInput("young", "Young", "2022-01-01", enrollment_date="2024-01-01"),
        SimulationChildInput("late", "Late", "2020-01-01", enrollment_date="2024-01-15"),
        SimulationChildInput("school", "School", "2016-01-01"),
    ]
    result = ClaimSimulator(config(seed="enrollment")).run(inputs)
    claims = {claim.child_id: claim for claim in result.claims}
    assert claims["young"].care_category == "FullTime"
    assert claims["school"].care_category == "SchoolAge"
    assert claims["late"].is_prorated
    assert claims["late"].projected_attendance_days <= claims["young"].projected_attendance_days


def test_capacity_never_exceeds_one_hundred_percent() -> None:
    result = ClaimSimulator(config(capacity=3, seed="limited")).run(children(15))
    assert all(
        day.utilization_percentage <= 100
        for day in result.utilization_report.daily_utilization
    )
    assert result.utilization_report.capacity_bottlenecks
    assert result.stats.days_with_capacity_issues > 0


def test_disabled_features_and_empty_input() -> None:
    result = ClaimSimulator(
        config(
            enable_audit_trail=False,
            enable_fairness_optimization=False,
            enable_sibling_coherence=False,
        )
    ).run([])
    assert result.claims == ()
    assert result.audit_trail == ()
    assert result.stats.optimization_iterations == 0
    assert result.stats.total_claims == 0


def test_siblings_have_overlapping_schedules_and_explanation() -> None:
    inputs = [
        SimulationChildInput("c1", "Child 1", "2020-01-01", family_id="f1"),
        SimulationChildInput("c2", "Child 2", "2021-01-01", family_id="f1"),
    ]
    simulator = ClaimSimulator(config(seed="sibling-test"))
    result = simulator.run(inputs)
    overlap = set(result.claims[0].daily_hours) & set(result.claims[1].daily_hours)
    assert overlap
    assert "c1" in simulator.explain_child("c1")
