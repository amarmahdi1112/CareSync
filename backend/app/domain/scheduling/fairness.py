"""Equitable hour-distribution analysis for the V2 scheduler."""

import math
from collections.abc import Sequence

from app.domain.random import SeededRandom
from app.domain.scheduling.types import (
    ChildProfile,
    ScheduleEntry,
    SchedulingFairnessMetrics,
    SchedulingFairnessReport,
)


class FairnessCalculator:
    def __init__(
        self,
        children: Sequence[ChildProfile],
        random: SeededRandom | None = None,
    ) -> None:
        self.children = {child.id: child for child in children}
        self.random = random or SeededRandom("scheduler-fairness")
        self.historical_debt: dict[str, float] = {}
        for child in children:
            history = child.historical_data
            if history and history.monthly_hours_history:
                average = sum(history.monthly_hours_history) / len(history.monthly_hours_history)
                self.historical_debt[child.id] = max(
                    0, child.total_claimed_hours - average
                )

    def calculate_metrics(
        self, entries: Sequence[ScheduleEntry]
    ) -> SchedulingFairnessMetrics:
        hours_per_child = self._aggregate(entries)
        values = [hours_per_child.get(child_id, 0) for child_id in self.children]
        if not values:
            return SchedulingFairnessMetrics(0, 0, 0, 0, 0, 0, {}, {})
        sorted_values = sorted(values)
        average = sum(values) / len(values)
        fulfillment = [
            min(1, hours_per_child.get(child_id, 0) / child.total_claimed_hours)
            if child.total_claimed_hours > 0
            else 1
            for child_id, child in self.children.items()
        ]
        average_fulfillment = sum(fulfillment) / len(fulfillment)
        return SchedulingFairnessMetrics(
            gini_coefficient=self._gini(sorted(fulfillment)),
            standard_deviation=math.sqrt(
                sum((value - average_fulfillment) ** 2 for value in fulfillment)
                / len(fulfillment)
            ),
            min_hours_scheduled=sorted_values[0],
            max_hours_scheduled=sorted_values[-1],
            average_hours_scheduled=average,
            median_hours_scheduled=self._median(sorted_values),
            historical_debt_map=dict(self.historical_debt),
            priority_scores={
                child_id: self.get_priority_score(
                    child_id, hours_per_child.get(child_id, 0)
                )
                for child_id in self.children
            },
        )

    def generate_report(
        self, entries: Sequence[ScheduleEntry]
    ) -> SchedulingFairnessReport:
        metrics = self.calculate_metrics(entries)
        hours = self._aggregate(entries)
        fulfillment = {
            child_id: min(1, hours.get(child_id, 0) / child.total_claimed_hours)
            if child.total_claimed_hours > 0
            else 1
            for child_id, child in self.children.items()
        }
        fair_share = (
            sum(fulfillment.values()) / len(fulfillment) if fulfillment else 0
        )
        threshold = max(0.05, fair_share * 0.15)
        underserved = [
            child_id
            for child_id, value in fulfillment.items()
            if value < fair_share - threshold
        ]
        overserved = [
            child_id
            for child_id, value in fulfillment.items()
            if value > fair_share + threshold
        ]
        overall_score = math.floor((1 - metrics.gini_coefficient) * 100 + 0.5)
        return SchedulingFairnessReport(
            overall_score=overall_score,
            metrics=metrics,
            underserved_children=tuple(underserved),
            overserved_children=tuple(overserved),
            recommendations=tuple(
                self._recommendations(metrics, underserved, overserved, fair_share)
            ),
        )

    def get_priority_score(self, child_id: str, current_hours: float) -> float:
        child = self.children.get(child_id)
        if child is None:
            return 0
        claim_ratio = (
            1 - current_hours / child.total_claimed_hours
            if child.total_claimed_hours > 0
            else 1
        )
        score = claim_ratio * 40
        score += min(self.historical_debt.get(child_id, 0) / 20, 1) * 30
        attendance_rate = (
            child.historical_data.attendance_rate if child.historical_data else 0.8
        )
        score += attendance_rate * 20
        score += self.random.next() * 10
        return min(100, max(0, score))

    @staticmethod
    def _aggregate(entries: Sequence[ScheduleEntry]) -> dict[str, float]:
        result: dict[str, float] = {}
        for entry in entries:
            result[entry.child_id] = result.get(entry.child_id, 0) + entry.hours
        return result

    @staticmethod
    def _gini(sorted_values: list[float]) -> float:
        count = len(sorted_values)
        if not count:
            return 0
        total = sum(sorted_values)
        if total == 0:
            return 0
        weighted = sum(
            (index + 1) * value for index, value in enumerate(sorted_values)
        )
        value = 2 * weighted / (count * total) - (count + 1) / count
        return min(1, max(0, value))

    @staticmethod
    def _median(sorted_values: list[float]) -> float:
        middle = len(sorted_values) // 2
        if len(sorted_values) % 2 == 0:
            return (sorted_values[middle - 1] + sorted_values[middle]) / 2
        return sorted_values[middle]

    def _recommendations(
        self,
        metrics: SchedulingFairnessMetrics,
        underserved: list[str],
        overserved: list[str],
        fair_share: float,
    ) -> list[str]:
        recommendations: list[str] = []
        if metrics.gini_coefficient > 0.3:
            recommendations.append(
                f"High inequality detected (Gini: {metrics.gini_coefficient:.2f}). "
                "Consider rebalancing hours between children."
            )
        if underserved:
            names = [self.children[item].name for item in underserved[:3]]
            suffix = "..." if len(underserved) > 3 else ""
            recommendations.append(
                f"{len(underserved)} children are underserved: {', '.join(names)}{suffix}. "
                f"Average claim fulfillment: {fair_share * 100:.1f}%."
            )
        if overserved:
            recommendations.append(
                f"{len(overserved)} children have more than fair share. "
                "Consider redistributing to improve equity."
            )
        if metrics.standard_deviation > 0.15:
            recommendations.append(
                "High variance in claim fulfillment "
                f"(σ = {metrics.standard_deviation * 100:.1f}%). "
                "Aim for more consistent fulfillment."
            )
        if not recommendations:
            score = math.floor((1 - metrics.gini_coefficient) * 100 + 0.5)
            recommendations.append(
                f"Schedule is well-balanced. Fairness score: {score}/100."
            )
        return recommendations
