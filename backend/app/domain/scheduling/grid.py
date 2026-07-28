"""Fifteen-minute capacity grid used by the V2 scheduler."""

import math
from datetime import date

from app.domain.scheduling.types import (
    CapacityState,
    DailyUtilization,
    TimeGap,
    TimeSlotInfo,
)

SLOT_DURATION_MINUTES = 15
MINUTES_PER_HOUR = 60


class TimeSlotGrid:
    def __init__(
        self,
        schedule_date: str,
        capacity: int,
        start_hour: int = 7,
        end_hour: int = 18,
    ) -> None:
        if capacity < 0 or end_hour <= start_hour:
            raise ValueError("capacity must be non-negative and operating hours must be ordered")
        self.date = schedule_date
        self.capacity = capacity
        self.start_hour = start_hour
        self.end_hour = end_hour
        total_slots = (end_hour - start_hour) * MINUTES_PER_HOUR // SLOT_DURATION_MINUTES
        self.slots = [capacity] * total_slots
        self.occupants: list[set[str]] = [set() for _ in range(total_slots)]

    def _time_to_slot(self, value: str, *, round_up: bool = False) -> int:
        parts = value.split(":")
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        relative_minutes = (hours - self.start_hour) * MINUTES_PER_HOUR + minutes
        operation = math.ceil if round_up else math.floor
        return operation(relative_minutes / SLOT_DURATION_MINUTES)

    def _slot_to_time(self, slot: int) -> str:
        total_minutes = slot * SLOT_DURATION_MINUTES + self.start_hour * MINUTES_PER_HOUR
        return f"{total_minutes // MINUTES_PER_HOUR:02d}:{total_minutes % MINUTES_PER_HOUR:02d}"

    def is_available(self, start_time: str, end_time: str) -> bool:
        start_slot = self._time_to_slot(start_time)
        end_slot = self._time_to_slot(end_time, round_up=True)
        if start_slot < 0 or end_slot > len(self.slots) or end_slot <= start_slot:
            return False
        return all(
            self.slots[index] > 0
            for index in range(start_slot, end_slot)
        )

    def reserve(self, child_id: str, start_time: str, end_time: str) -> bool:
        if not self.is_available(start_time, end_time):
            return False
        start_slot = self._time_to_slot(start_time)
        end_slot = self._time_to_slot(end_time, round_up=True)
        if any(child_id in self.occupants[index] for index in range(start_slot, end_slot)):
            return False
        for index in range(start_slot, end_slot):
            self.slots[index] -= 1
            self.occupants[index].add(child_id)
        return True

    def release(self, child_id: str, start_time: str, end_time: str) -> None:
        for index in range(
            self._time_to_slot(start_time),
            self._time_to_slot(end_time, round_up=True),
        ):
            if 0 <= index < len(self.slots) and child_id in self.occupants[index]:
                self.slots[index] += 1
                self.occupants[index].remove(child_id)

    def find_best_block(
        self, duration_hours: float, preferred_start: str | None = None
    ) -> tuple[str, str] | None:
        slots_needed = math.ceil(duration_hours * MINUTES_PER_HOUR / SLOT_DURATION_MINUTES)
        raw_preferred_slot = self._time_to_slot(preferred_start) if preferred_start else 0
        preferred_slot = max(0, min(raw_preferred_slot, len(self.slots) - 1))
        candidates = [preferred_slot]
        for offset in range(1, len(self.slots)):
            if preferred_slot - offset >= 0:
                candidates.append(preferred_slot - offset)
            if preferred_slot + offset < len(self.slots):
                candidates.append(preferred_slot + offset)
        for start_slot in candidates:
            if start_slot < 0 or start_slot >= len(self.slots):
                continue
            end_slot = start_slot + slots_needed
            if end_slot <= len(self.slots) and all(
                self.slots[index] > 0 for index in range(start_slot, end_slot)
            ):
                return self._slot_to_time(start_slot), self._slot_to_time(end_slot)
        return None

    def find_max_block(self, start_time: str) -> tuple[str, float]:
        raw_start_slot = self._time_to_slot(start_time)
        start_slot = max(0, min(raw_start_slot, len(self.slots)))
        end_slot = start_slot
        while end_slot < len(self.slots) and self.slots[end_slot] > 0:
            end_slot += 1
        hours = (end_slot - start_slot) * SLOT_DURATION_MINUTES / MINUTES_PER_HOUR
        return self._slot_to_time(end_slot), hours

    def get_capacity_state(self) -> CapacityState:
        breakdown: list[TimeSlotInfo] = []
        total_used = 0
        for index, remaining in enumerate(self.slots):
            used = self.capacity - remaining
            total_used += used
            breakdown.append(
                TimeSlotInfo(
                    self._slot_to_time(index),
                    self._slot_to_time(index + 1),
                    remaining,
                    used,
                )
            )
        total_capacity = self.capacity * len(self.slots)
        return CapacityState(
            date=self.date,
            total_capacity=total_capacity,
            used_capacity=total_used,
            remaining_capacity=total_capacity - total_used,
            utilization_percentage=(
                total_used / total_capacity * 100 if total_capacity else 0
            ),
            slot_breakdown=tuple(breakdown),
        )

    def get_remaining_capacity_hours(self) -> float:
        return sum(self.slots) * SLOT_DURATION_MINUTES / MINUTES_PER_HOUR

    def get_peak_hour(self) -> str:
        maximum = 0
        peak_slot = 0
        for index, remaining in enumerate(self.slots):
            occupancy = self.capacity - remaining
            if occupancy > maximum:
                maximum = occupancy
                peak_slot = index
        return self._slot_to_time(peak_slot)

    def find_gaps(
        self, min_gap_minutes: int = 30, *, for_scavenging: bool = False
    ) -> tuple[TimeGap, ...]:
        gaps: list[TimeGap] = []
        minimum_slots = min_gap_minutes / SLOT_DURATION_MINUTES
        threshold = 1 if for_scavenging else self.capacity * 0.5
        gap_start: int | None = None
        for index, remaining in enumerate(self.slots):
            has_space = remaining >= threshold
            if has_space and gap_start is None:
                gap_start = index
            elif not has_space and gap_start is not None:
                if index - gap_start >= minimum_slots:
                    gaps.append(self._gap(gap_start, index))
                gap_start = None
        if gap_start is not None and len(self.slots) - gap_start >= minimum_slots:
            gaps.append(self._gap(gap_start, len(self.slots)))
        return tuple(gaps)

    def _gap(self, start_slot: int, end_slot: int) -> TimeGap:
        unused = sum(self.slots[start_slot:end_slot]) * SLOT_DURATION_MINUTES / MINUTES_PER_HOUR
        return TimeGap(
            self._slot_to_time(start_slot), self._slot_to_time(end_slot), unused
        )

    def get_daily_utilization(self) -> DailyUtilization:
        state = self.get_capacity_state()
        scheduled_hours = sum(
            (self.capacity - remaining) * SLOT_DURATION_MINUTES / MINUTES_PER_HOUR
            for remaining in self.slots
        )
        unique_children = set().union(*self.occupants) if self.occupants else set()
        schedule_date = date.fromisoformat(self.date)
        return DailyUtilization(
            date=self.date,
            day_of_week=schedule_date.isoweekday() % 7,
            capacity_hours=(
                len(self.slots) * self.capacity * SLOT_DURATION_MINUTES / MINUTES_PER_HOUR
            ),
            scheduled_hours=scheduled_hours,
            utilization=state.utilization_percentage / 100,
            children_count=len(unique_children),
            peak_hour=self.get_peak_hour(),
            gaps=self.find_gaps(),
        )

    def get_scheduled_children(self) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for occupants in self.occupants:
            for child_id in occupants:
                if child_id not in seen:
                    seen.add(child_id)
                    result.append(child_id)
        return tuple(result)
