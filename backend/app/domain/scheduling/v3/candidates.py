"""Canonical legal-pattern enumeration for the isolated V3 scheduler."""

from __future__ import annotations

from datetime import date

from .types import (
    DAYCARE,
    CandidatePattern,
    PatternKind,
    TimeBlock,
    V3Child,
    V3Config,
)

OSC_MORNING = (7 * 60 // 5, 8 * 60 // 5 + 30 // 5)
OSC_AFTERNOON = (15 * 60 // 5 + 30 // 5, 18 * 60 // 5)


def eligible_dates(child: V3Child, config: V3Config) -> tuple[str, ...]:
    """Return canonical dates on which the child may legally attend."""

    excluded = set(child.excluded_dates)
    enrolled = date.fromisoformat(child.enrollment_date) if child.enrollment_date else None
    return tuple(
        current_date
        for current_date in sorted(config.open_dates)
        if current_date not in excluded
        and (enrolled is None or date.fromisoformat(current_date) >= enrolled)
    )


def care_windows(
    child: V3Child, config: V3Config, current_date: str
) -> tuple[tuple[int, int], ...]:
    """Return hard legal windows in absolute five-minute ticks."""

    if child.care_type == DAYCARE or current_date in config.school_off_dates:
        return ((config.operating_start_tick, config.operating_end_tick),)
    result: list[tuple[int, int]] = []
    for raw_start, raw_end in (OSC_MORNING, OSC_AFTERNOON):
        start = max(raw_start, config.operating_start_tick)
        end = min(raw_end, config.operating_end_tick)
        if start < end:
            result.append((start, end))
    return tuple(result)


def pattern_kind(child: V3Child, config: V3Config, current_date: str) -> PatternKind:
    if child.care_type == DAYCARE:
        return "daycare"
    if current_date in config.school_off_dates:
        return "osc_school_off"
    return "osc_school"


def max_daily_ticks(child: V3Child, config: V3Config, current_date: str) -> int:
    return sum(end - start for start, end in care_windows(child, config, current_date))


def enumerate_candidate_patterns(
    child: V3Child,
    config: V3Config,
    current_date: str,
    duration_ticks: int,
) -> tuple[CandidatePattern, ...]:
    """Enumerate every legal pattern of one exact duration in canonical order."""

    if duration_ticks <= 0 or current_date not in eligible_dates(child, config):
        return ()
    windows = care_windows(child, config, current_date)
    if duration_ticks > sum(end - start for start, end in windows):
        return ()
    kind = pattern_kind(child, config, current_date)
    raw: set[tuple[tuple[int, int], ...]] = set()
    for start, end in windows:
        if duration_ticks <= end - start:
            for block_start in range(start, end - duration_ticks + 1):
                raw.add(((block_start, block_start + duration_ticks),))
    if len(windows) == 2:
        first_start, first_end = windows[0]
        second_start, second_end = windows[1]
        for first_duration in range(1, duration_ticks):
            second_duration = duration_ticks - first_duration
            if first_duration > first_end - first_start:
                continue
            if second_duration > second_end - second_start:
                continue
            for block_one_start in range(first_start, first_end - first_duration + 1):
                for block_two_start in range(second_start, second_end - second_duration + 1):
                    raw.add(
                        (
                            (block_one_start, block_one_start + first_duration),
                            (block_two_start, block_two_start + second_duration),
                        )
                    )
    return tuple(
        CandidatePattern(
            child_id=child.child_id,
            date=current_date,
            blocks=tuple(TimeBlock(start, end) for start, end in blocks),
            kind=kind,
        )
        for blocks in sorted(raw)
    )


def best_available_candidate_pattern(
    child: V3Child,
    config: V3Config,
    current_date: str,
    duration_ticks: int,
    occupancy: list[int],
) -> CandidatePattern | None:
    """Return the lowest-pressure available exact-duration pattern.

    This is equivalent to filtering :func:`enumerate_candidate_patterns` for
    capacity and selecting the minimum ``(pressure, block_key)``.  It avoids
    constructing the Cartesian product of every morning and afternoon start
    position: for each legal duration split, the two windows are independent,
    so their individually best intervals form that split's best pattern.
    """

    if duration_ticks <= 0 or current_date not in eligible_dates(child, config):
        return None
    windows = care_windows(child, config, current_date)
    if duration_ticks > sum(end - start for start, end in windows):
        return None

    choices: list[tuple[int, tuple[tuple[int, int], ...]]] = []
    for window in windows:
        block = _best_available_block(
            window,
            duration_ticks,
            occupancy,
            config.capacity,
        )
        if block is not None:
            pressure, start, end = block
            choices.append((pressure, ((start, end),)))

    if len(windows) == 2:
        first_length = windows[0][1] - windows[0][0]
        second_length = windows[1][1] - windows[1][0]
        first_duration_min = max(1, duration_ticks - second_length)
        first_duration_max = min(first_length, duration_ticks - 1)
        for first_duration in range(first_duration_min, first_duration_max + 1):
            second_duration = duration_ticks - first_duration
            first = _best_available_block(
                windows[0],
                first_duration,
                occupancy,
                config.capacity,
            )
            second = _best_available_block(
                windows[1],
                second_duration,
                occupancy,
                config.capacity,
            )
            if first is None or second is None:
                continue
            first_pressure, first_start, first_end = first
            second_pressure, second_start, second_end = second
            choices.append(
                (
                    first_pressure + second_pressure,
                    ((first_start, first_end), (second_start, second_end)),
                )
            )

    if not choices:
        return None
    _, blocks = min(choices, key=lambda item: (item[0], item[1]))
    return CandidatePattern(
        child_id=child.child_id,
        date=current_date,
        blocks=tuple(TimeBlock(start, end) for start, end in blocks),
        kind=pattern_kind(child, config, current_date),
    )


def _best_available_block(
    window: tuple[int, int],
    duration_ticks: int,
    occupancy: list[int],
    capacity: int,
) -> tuple[int, int, int] | None:
    """Return ``(pressure, start, end)`` for one deterministic interval."""

    window_start, window_end = window
    if duration_ticks <= 0 or duration_ticks > window_end - window_start:
        return None
    best: tuple[int, int, int] | None = None
    for start in range(window_start, window_end - duration_ticks + 1):
        end = start + duration_ticks
        segment = occupancy[start:end]
        if any(value >= capacity for value in segment):
            continue
        candidate = (sum(segment), start, end)
        if best is None or candidate < best:
            best = candidate
    return best
