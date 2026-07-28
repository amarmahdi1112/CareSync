from app.domain.claims import FairnessCalculator, HistoricalChildData, ProjectedClaim


def claim(child_id: str, hours: float, category: str = "FullTime") -> ProjectedClaim:
    return ProjectedClaim(
        child_id=child_id,
        child_name=f"Child {child_id}",
        age_in_years=4,
        age_in_months=48,
        care_category=category,  # type: ignore[arg-type]
        behavioral_profile="consistent",
        is_prorated=False,
        enrollment_date="",
        projected_hours=hours,
        projected_attendance_days=round(hours / 8),
        base_hours_before_proration=160,
    )


def test_gini_and_fairness_scores_match_legacy() -> None:
    calculator = FairnessCalculator()
    assert calculator.calculate_gini_coefficient([]) == 0
    assert calculator.calculate_gini_coefficient([100]) == 0
    assert calculator.calculate_gini_coefficient([100] * 5) == 0
    assert calculator.calculate_gini_coefficient([0, 0, 0, 0, 1000]) > 0.7
    assert calculator.calculate_fairness_score(0.25) == 75


def test_metrics_classify_children_against_category_targets() -> None:
    calculator = FairnessCalculator(110, 50)
    metrics = calculator.calculate_metrics([claim("1", 110), claim("2", 50), claim("3", 30)])
    assert metrics.underserved_count == 2
    assert metrics.adequately_served_count == 1
    assert metrics.coefficient_of_variation > 0
    assert calculator.calculate_metrics([]).fairness_score == 100


def test_report_and_priority_preserve_legacy_thresholds() -> None:
    calculator = FairnessCalculator(110, 50)
    report = calculator.generate_report([claim("1", 150), claim("2", 30), claim("3", 20)])
    assert report.overall_score < 70
    assert report.underserved_children == ("2", "3")
    assert report.overserved_children == ("1",)
    assert report.recommendations
    assert calculator.calculate_priority_score("1", 50, 110, "FullTime") > (
        calculator.calculate_priority_score("2", 110, 110, "FullTime")
    )


def test_historical_debt_boosts_priority() -> None:
    history = [HistoricalChildData("1", 80, 110, 6)]
    with_history = FairnessCalculator(historical_data=history)
    without_history = FairnessCalculator()
    assert with_history.calculate_priority_score("1", 50, 110, "FullTime") > (
        without_history.calculate_priority_score("1", 50, 110, "FullTime")
    )
