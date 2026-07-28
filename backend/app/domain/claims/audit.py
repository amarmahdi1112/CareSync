"""Explainable audit trail for claim-simulation decisions."""

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.domain.claims.types import (
    AttendanceDecision,
    AuditEntry,
    AuditEventType,
)


class AuditTrail:
    def __init__(self, enabled: bool = True, max_entries: int = 10_000) -> None:
        self.enabled = enabled
        self.max_entries = max_entries
        self._entries: list[AuditEntry] = []

    def _add_entry(
        self,
        event_type: AuditEventType,
        message: str,
        *,
        child_id: str | None = None,
        date: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        if len(self._entries) >= self.max_entries:
            self._entries.pop(0)
        self._entries.append(
            AuditEntry(
                timestamp=datetime.now(UTC),
                event_type=event_type,
                message=message,
                child_id=child_id,
                date=date,
                details=details,
            )
        )

    def log(
        self,
        event_type: AuditEventType,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._add_entry(event_type, message, details=details)

    def log_simulation_start(
        self, child_count: int, day_count: int, config: dict[str, Any]
    ) -> None:
        self.log(
            "simulation_start",
            "Simulation started",
            {"childCount": child_count, "dayCount": day_count, "config": config},
        )

    def log_simulation_end(
        self, total_claims: int, total_hours: float, processing_time_ms: float
    ) -> None:
        self.log(
            "simulation_end",
            "Simulation completed",
            {
                "totalClaims": total_claims,
                "totalHours": total_hours,
                "processingTimeMs": processing_time_ms,
            },
        )

    def log_day_start(self, date: str, remaining_capacity: float) -> None:
        self.log(
            "day_start",
            f"Processing {date}",
            {"date": date, "remainingCapacity": remaining_capacity},
        )

    def log_day_end(self, date: str, children_scheduled: int, hours_allocated: float) -> None:
        self.log(
            "day_end",
            f"Completed {date}",
            {
                "date": date,
                "childrenScheduled": children_scheduled,
                "hoursAllocated": hours_allocated,
            },
        )

    def log_attendance_decision(self, decision: AttendanceDecision) -> None:
        status = "Attending" if decision.decision == "attend" else "Absent"
        self._add_entry(
            "attendance_decision",
            f"{status}: {decision.reason}",
            child_id=decision.child_id,
            date=decision.date,
            details={
                "decision": decision.decision,
                "reason": decision.reason,
                "probability": decision.probability,
                "familyInfluence": decision.family_influence,
                "hoursAllocated": decision.hours_allocated,
            },
        )

    def log_capacity_exhausted(self, date: str, child_id: str, requested_hours: float) -> None:
        self._add_entry(
            "capacity_exhausted",
            f"Capacity exhausted on {date}",
            child_id=child_id,
            date=date,
            details={"date": date, "childId": child_id, "requestedHours": requested_hours},
        )

    def log_hours_allocated(
        self, child_id: str, date: str, hours: float, remaining_budget: float
    ) -> None:
        self._add_entry(
            "hours_allocated",
            f"Allocated {hours} hours",
            child_id=child_id,
            date=date,
            details={"hours": hours, "remainingBudget": remaining_budget},
        )

    def log_sibling_coherence(
        self, family_id: str, child_ids: list[str], date: str, influence: float
    ) -> None:
        self.log(
            "sibling_coherence",
            f"Family {family_id} coherence applied",
            {
                "familyId": family_id,
                "childIds": child_ids,
                "date": date,
                "influenceBoost": influence,
            },
        )

    def log_fairness_adjustment(
        self, child_id: str, action: str, before_hours: float, after_hours: float
    ) -> None:
        self._add_entry(
            "fairness_adjustment",
            action,
            child_id=child_id,
            details={
                "beforeHours": before_hours,
                "afterHours": after_hours,
                "delta": after_hours - before_hours,
            },
        )

    def log_optimization_start(self, target_score: int, current_score: int) -> None:
        self.log(
            "optimization_start",
            "Fairness optimization started",
            {"targetScore": target_score, "currentScore": current_score},
        )

    def log_optimization_iteration(
        self, iteration: int, current_score: int, improvement: float
    ) -> None:
        self.log(
            "optimization_iteration",
            f"Iteration {iteration}",
            {"iteration": iteration, "currentScore": current_score, "improvement": improvement},
        )

    def log_optimization_end(
        self, iterations: int, final_score: int, total_improvement: float
    ) -> None:
        self.log(
            "optimization_end",
            "Optimization completed",
            {
                "iterations": iterations,
                "finalScore": final_score,
                "totalImprovement": total_improvement,
            },
        )

    def log_warning(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.log("warning", message, details)

    def log_error(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.log("error", message, details)

    def get_entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    def get_entries_for_child(self, child_id: str) -> tuple[AuditEntry, ...]:
        return tuple(entry for entry in self._entries if entry.child_id == child_id)

    def get_entries_for_date(self, date: str) -> tuple[AuditEntry, ...]:
        return tuple(entry for entry in self._entries if entry.date == date)

    def get_entries_by_type(self, event_type: AuditEventType) -> tuple[AuditEntry, ...]:
        return tuple(entry for entry in self._entries if entry.event_type == event_type)

    def explain_claim(self, child_id: str) -> str:
        child_entries = self.get_entries_for_child(child_id)
        if not child_entries:
            return f"No audit entries found for child {child_id}"
        by_type = Counter(entry.event_type for entry in child_entries)
        lines = [
            f"Claim explanation for {child_id}:",
            f"- Attendance decisions: {by_type['attendance_decision']}",
            f"- Hours allocations: {by_type['hours_allocated']}",
            f"- Fairness adjustments: {by_type['fairness_adjustment']}",
            f"- Capacity issues: {by_type['capacity_exhausted']}",
        ]
        if by_type["capacity_exhausted"]:
            lines.append(f"\nCapacity was limited on {by_type['capacity_exhausted']} day(s).")
        if by_type["fairness_adjustment"]:
            total = sum(
                float((entry.details or {}).get("delta", 0))
                for entry in child_entries
                if entry.event_type == "fairness_adjustment"
            )
            lines.append(f"\nFairness adjustments added {total:.1f} hours.")
        return "\n".join(lines)

    def get_summary(self) -> dict[str, Any]:
        by_type = dict(Counter(entry.event_type for entry in self._entries))
        return {
            "totalEntries": len(self._entries),
            "byType": by_type,
            "warnings": by_type.get("warning", 0),
            "errors": by_type.get("error", 0),
        }

    def clear(self) -> None:
        self._entries.clear()
