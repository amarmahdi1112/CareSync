from app.domain.scheduling import TimeSlotGrid


def test_reservation_capacity_and_release() -> None:
    grid = TimeSlotGrid("2024-01-15", 1, 7, 18)
    initial = grid.get_remaining_capacity_hours()
    assert grid.reserve("child-1", "09:00", "12:00")
    assert grid.get_remaining_capacity_hours() == initial - 3
    assert not grid.reserve("child-2", "10:00", "11:00")
    grid.release("child-1", "09:00", "12:00")
    assert grid.get_remaining_capacity_hours() == initial


def test_best_and_max_blocks_match_legacy_search_order() -> None:
    grid = TimeSlotGrid("2024-01-15", 1, 9, 17)
    assert grid.find_best_block(3, "09:00") == ("09:00", "12:00")
    grid.reserve("child-1", "12:00", "17:00")
    assert grid.find_max_block("09:00") == ("12:00", 3)
    assert grid.find_best_block(1, "12:00") == ("11:00", "12:00")


def test_preferred_times_outside_operating_hours_are_safely_clamped() -> None:
    grid = TimeSlotGrid("2024-01-15", 2, 10, 12)
    assert grid.find_best_block(1, "08:00") == ("10:00", "11:00")
    assert grid.find_best_block(1, "15:00") == ("11:00", "12:00")
    assert grid.find_max_block("08:00") == ("12:00", 2)


def test_capacity_state_gaps_peak_and_daily_utilization() -> None:
    grid = TimeSlotGrid("2024-01-15", 10, 9, 12)
    for index in range(5):
        assert grid.reserve(f"child-{index}", "09:00", "12:00")
    state = grid.get_capacity_state()
    utilization = grid.get_daily_utilization()
    assert state.used_capacity == 60
    assert len(state.slot_breakdown) == 12
    assert utilization.utilization == 0.5
    assert utilization.children_count == 5
    assert utilization.day_of_week == 1
    assert grid.get_peak_hour() == "09:00"
    assert grid.find_gaps(30)


def test_boundaries_partial_slots_zero_width_and_scheduled_children() -> None:
    grid = TimeSlotGrid("2024-01-15", 2, 7, 18)
    assert grid.reserve("early", "07:00", "08:00")
    assert grid.reserve("late", "17:00", "18:00")
    assert not grid.is_available("10:00", "10:00")
    partial = TimeSlotGrid("2024-01-15", 1, 7, 18)
    assert partial.reserve("partial", "08:14", "08:16")
    assert not partial.is_available("08:00", "08:15")
    assert not partial.is_available("08:15", "08:30")
    assert not partial.reserve("partial", "08:00", "08:15")
    assert set(grid.get_scheduled_children()) == {"early", "late"}
