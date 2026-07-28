"""Fairness analysis for generated claim-hour distributions."""

import math
from collections.abc import Sequence

from app.domain.claims.categories import CareCategory
from app.domain.claims.types import (
    FairnessMetrics,
    FairnessReport,
    HistoricalChildData,
    ProjectedClaim,
)


def _javascript_round(value: float) -> int:
    return math.floor(value + 0.5)


class FairnessCalculator:
    def __init__(
        self,
        full_time_target: float = 110,
        school_age_target: float = 50,
        historical_data: Sequence[HistoricalChildData] = (),
    ) -> None:
        self.target_hours_by_category: dict[CareCategory, float] = {
            "FullTime": full_time_target,
            "SchoolAge": school_age_target,
        }
        self.historical_data = {item.child_id: item for item in historical_data}

    @staticmethod
    def calculate_gini_coefficient(hours: Sequence[float]) -> float:
        if len(hours) < 2:
            return 0
        sorted_hours = sorted(hours)
        count = len(sorted_hours)
        mean = sum(sorted_hours) / count
        if mean == 0:
            return 0
        numerator = sum(
            (2 * (index + 1) - count - 1) * value
            for index, value in enumerate(sorted_hours)
        )
        return numerator / (count * count * mean)

    @staticmethod
    def calculate_fairness_score(gini: float) -> int:
        return _javascript_round((1 - gini) * 100)

    def calculate_priority_score(
        self,
        child_id: str,
        current_hours: float,
        target_hours: float,
        care_category: CareCategory,
    ) -> float:
        score = max(0, (1 - current_hours / target_hours) * 50)
        historical = self.historical_data.get(child_id)
        if historical:
            deficit = historical.average_monthly_hours - historical.previous_month_hours
            if deficit > 0:
                score += min(25, deficit / 4)
        if care_category == "FullTime":
            score += 5
        return _javascript_round(score * 100) / 100

    def calculate_metrics(self, claims: Sequence[ProjectedClaim]) -> FairnessMetrics:
        if not claims:
            return FairnessMetrics(0, 100, 0, 0, 0, 0)

        hours = [claim.projected_hours for claim in claims]
        mean = sum(hours) / len(hours)
        gini = self.calculate_gini_coefficient(hours)
        variance = sum((value - mean) ** 2 for value in hours) / len(hours)
        standard_deviation = math.sqrt(variance)
        underserved = sum(
            claim.projected_hours < self.get_target_hours(claim.care_category) * 0.8
            for claim in claims
        )
        return FairnessMetrics(
            gini_coefficient=_javascript_round(gini * 1000) / 1000,
            fairness_score=self.calculate_fairness_score(gini),
            hours_standard_deviation=_javascript_round(standard_deviation * 100) / 100,
            coefficient_of_variation=(
                _javascript_round(standard_deviation / mean * 1000) / 1000 if mean > 0 else 0
            ),
            underserved_count=underserved,
            adequately_served_count=len(claims) - underserved,
        )

    def generate_report(self, claims: Sequence[ProjectedClaim]) -> FairnessReport:
        metrics = self.calculate_metrics(claims)
        underserved: list[str] = []
        overserved: list[str] = []
        for claim in claims:
            target = self.get_target_hours(claim.care_category)
            if claim.projected_hours < target * 0.8:
                underserved.append(claim.child_id)
            elif claim.projected_hours > target * 1.2:
                overserved.append(claim.child_id)

        recommendations: list[str] = []
        if metrics.gini_coefficient > 0.3:
            recommendations.append("High inequality detected. Consider capacity adjustments.")
        if len(underserved) > len(claims) * 0.2:
            recommendations.append(
                f"{len(underserved)} children are significantly below target hours."
            )
        if metrics.fairness_score < 70:
            recommendations.append(
                "Fairness score is low. Enable optimization for better distribution."
            )

        return FairnessReport(
            metrics=metrics,
            overall_score=metrics.fairness_score,
            underserved_children=tuple(underserved),
            overserved_children=tuple(overserved),
            recommendations=tuple(recommendations),
        )

    def get_target_hours(self, category: CareCategory) -> float:
        return self.target_hours_by_category.get(category, 80)
