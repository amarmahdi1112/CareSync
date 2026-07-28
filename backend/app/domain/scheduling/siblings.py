"""Family and sibling schedule-coherence analysis."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.scheduling.types import ChildProfile, ScheduleEntry


@dataclass(frozen=True, slots=True)
class FamilyGroup:
    family_id: str
    child_ids: tuple[str, ...]
    coherence_score: float


@dataclass(frozen=True, slots=True)
class FamilyCoherenceReport:
    family_id: str
    child_ids: tuple[str, ...]
    child_names: tuple[str, ...]
    coherence_score: float
    shared_days: int
    total_days: int
    misaligned_days: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoherenceSuggestion:
    family_id: str
    description: str
    impact: float
    action: Literal["add", "move", "swap"]
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CoherenceResult:
    score: float
    family_breakdowns: tuple[FamilyCoherenceReport, ...]
    suggestions: tuple[CoherenceSuggestion, ...]


class SiblingCoherence:
    def __init__(self, children: Sequence[ChildProfile]) -> None:
        self.children = {child.id: child for child in children}
        self.child_to_family = {child.id: child.family_id for child in children}
        grouped: dict[str, list[ChildProfile]] = {}
        for child in children:
            grouped.setdefault(child.family_id, []).append(child)
        self.families = {
            family_id: FamilyGroup(
                family_id,
                tuple(child.id for child in family_children),
                self._family_importance(family_children),
            )
            for family_id, family_children in grouped.items()
            if len(family_children) > 1
        }

    def get_family_id(self, child_id: str) -> str | None:
        return self.child_to_family.get(child_id)

    def get_siblings(self, child_id: str) -> tuple[str, ...]:
        family = self.families.get(self.child_to_family.get(child_id, ""))
        if family is None:
            return ()
        return tuple(item for item in family.child_ids if item != child_id)

    def is_sibling_scheduled(
        self, child_id: str, current_date: str, schedule: dict[str, list[ScheduleEntry]]
    ) -> bool:
        return any(
            any(entry.date == current_date for entry in schedule.get(sibling, []))
            for sibling in self.get_siblings(child_id)
        )

    def get_sibling_scheduled_dates(
        self, child_id: str, schedule: dict[str, list[ScheduleEntry]]
    ) -> tuple[str, ...]:
        dates = {
            entry.date
            for sibling in self.get_siblings(child_id)
            for entry in schedule.get(sibling, [])
        }
        return tuple(sorted(dates))

    def get_coherence_bonus(
        self, child_id: str, current_date: str, schedule: dict[str, list[ScheduleEntry]]
    ) -> float:
        family = self.families.get(self.child_to_family.get(child_id, ""))
        siblings = self.get_siblings(child_id)
        if family is None or not siblings:
            return 0
        scheduled = sum(
            any(entry.date == current_date for entry in schedule.get(sibling, []))
            for sibling in siblings
        )
        return scheduled / len(siblings) * family.coherence_score

    def analyze_coherence(
        self,
        schedule: dict[str, list[ScheduleEntry]],
        child_profiles: dict[str, ChildProfile] | None = None,
    ) -> CoherenceResult:
        profiles = child_profiles or self.children
        reports: list[FamilyCoherenceReport] = []
        suggestions: list[CoherenceSuggestion] = []
        for family in self.families.values():
            child_dates = {
                child_id: {entry.date for entry in schedule.get(child_id, [])}
                for child_id in family.child_ids
            }
            all_dates = set().union(*child_dates.values()) if child_dates else set()
            shared = 0
            misaligned: list[str] = []
            for current_date in all_dates:
                present = sum(current_date in dates for dates in child_dates.values())
                if present == len(family.child_ids):
                    shared += 1
                elif present:
                    misaligned.append(current_date)
            score = shared / len(all_dates) if all_dates else 1
            report = FamilyCoherenceReport(
                family.family_id,
                family.child_ids,
                tuple(profiles.get(item, self.children[item]).name for item in family.child_ids),
                score,
                shared,
                len(all_dates),
                tuple(sorted(misaligned)),
            )
            reports.append(report)
            if score < 0.7 and misaligned:
                suggestions.append(
                    CoherenceSuggestion(
                        family.family_id,
                        (
                            f"Family {family.family_id} has {len(misaligned)} days where "
                            "siblings are not scheduled together"
                        ),
                        0.7 - score,
                        "move",
                        {
                            "misalignedDays": sorted(misaligned)[:3],
                            "childIds": list(family.child_ids),
                        },
                    )
                )
        overall = sum(item.coherence_score for item in reports) / len(reports) if reports else 1
        return CoherenceResult(
            overall,
            tuple(reports),
            tuple(sorted(suggestions, key=lambda item: item.impact, reverse=True)),
        )

    def get_families(self) -> tuple[FamilyGroup, ...]:
        return tuple(self.families.values())

    def has_siblings(self, child_id: str) -> bool:
        return bool(self.get_siblings(child_id))

    @staticmethod
    def _family_importance(children: Sequence[ChildProfile]) -> float:
        importance = 0.8
        if len(children) >= 3:
            importance = min(1, importance + 0.1)
        if len({child.care_type for child in children}) > 1:
            importance -= 0.1
        return max(0.5, importance)
