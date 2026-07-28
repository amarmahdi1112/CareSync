from dataclasses import replace

from app.domain.scheduling.v3.auditor import (
    audit_assignments,
    audit_schedule_result,
)
from app.domain.scheduling.v3.types import (
    FeasibilityResult,
    Objective,
    PhaseTrace,
    ScheduleAssignment,
    TimeBlock,
    V3Child,
    V3Config,
    V3ScheduleResult,
)


def _config(*, capacity: int = 2) -> V3Config:
    return V3Config(
        open_dates=("2026-06-01", "2026-06-02"),
        school_off_dates=("2026-06-02",),
        capacity=capacity,
    )


def _assignment(
    child_id: str,
    date: str,
    start: int,
    end: int,
    kind: str = "daycare",
) -> ScheduleAssignment:
    return ScheduleAssignment(child_id, date, (TimeBlock(start, end),), kind)  # type: ignore[arg-type]


def test_valid_exact_schedule_is_certified() -> None:
    children = (
        V3Child("daycare", "Daycare", 12),
        V3Child("osc", "OSC", 12),
    )
    assignments = (
        _assignment("daycare", "2026-06-01", 84, 96),
        _assignment("osc", "2026-06-01", 84, 96, "osc_school"),
    )

    report = audit_assignments(assignments, children, _config())

    assert report.valid
    assert report.violations == ()
    assert report.requested_ticks == 24
    assert report.scheduled_ticks == 24
    assert report.scheduled_ticks_by_child == (("daycare", 12), ("osc", 12))
    assert report.shortfall_ticks_by_child == ()
    assert report.overclaim_ticks_by_child == ()
    assert report.capacity_peaks[0].occupancy == 2


def test_auditor_finds_dates_windows_kind_duplicates_and_claim_errors() -> None:
    children = (
        V3Child("d", "Daycare", 10, excluded_dates=("2026-06-02",)),
        V3Child("o", "OSC", 6, enrollment_date="2026-06-02"),
    )
    assignments = (
        _assignment("d", "2026-06-02", 84, 90),
        _assignment("d", "2026-06-02", 90, 96),
        _assignment("o", "2026-06-01", 100, 106, "daycare"),
        _assignment("ghost", "2026-06-03", 84, 90),
    )

    report = audit_assignments(assignments, children, _config())
    codes = {violation.code for violation in report.violations}

    assert not report.valid
    assert {
        "BEFORE_ENROLLMENT",
        "CLAIM_EXCEEDED",
        "DATE_EXCLUDED",
        "DUPLICATE_CHILD_DATE",
        "ILLEGAL_TIME_BLOCKS",
        "KIND_MISMATCH",
        "UNKNOWN_CHILD",
    } <= codes


def test_capacity_is_recomputed_for_every_tick() -> None:
    children = tuple(V3Child(str(index), "Daycare", 3) for index in range(3))
    assignments = tuple(_assignment(str(index), "2026-06-01", 84, 87) for index in range(3))

    report = audit_assignments(assignments, children, _config(capacity=2))
    capacity_issues = [
        violation for violation in report.violations if violation.code == "CAPACITY_EXCEEDED"
    ]

    assert [(issue.tick, issue.actual) for issue in capacity_issues] == [
        (84, 3),
        (85, 3),
        (86, 3),
    ]
    assert report.capacity_peaks[0].first_tick == 84


def test_school_and_school_off_block_shapes_are_checked_independently() -> None:
    child = V3Child("osc", "OSC", 24)
    split = ScheduleAssignment(
        "osc",
        "2026-06-01",
        (TimeBlock(84, 90), TimeBlock(186, 192)),
        "osc_school",
    )
    invalid_off_split = ScheduleAssignment(
        "osc",
        "2026-06-02",
        (TimeBlock(84, 90), TimeBlock(100, 106)),
        "osc_school_off",
    )

    valid_report = audit_assignments((split,), (replace(child, claimed_ticks=12),), _config())
    invalid_report = audit_assignments((invalid_off_split,), (child,), _config())

    assert valid_report.valid
    assert "ILLEGAL_TIME_BLOCKS" in {issue.code for issue in invalid_report.violations}


def test_reconciliation_catches_tampered_result_metadata() -> None:
    child = V3Child("d", "Daycare", 6)
    assignment = _assignment("d", "2026-06-01", 84, 90)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(True, True),
        trace=(),
        objective=Objective(0, 0, 0, 0, ()),
        requested_ticks=999,
        scheduled_ticks_by_child=(("d", 5),),
    )

    report = audit_schedule_result(result, (child,), _config())
    codes = {violation.code for violation in report.violations}

    assert "REQUESTED_TICKS_MISMATCH" in codes
    assert "SCHEDULED_TICKS_MISMATCH" in codes


def test_reconciliation_catches_tampered_feasibility_and_objective() -> None:
    child = V3Child("d", "Daycare", 6)
    assignment = _assignment("d", "2026-06-01", 84, 90)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(False, False, ("SEARCH_EXHAUSTED:d",)),
        trace=(),
        objective=Objective(999, 999, 999, 999, ()),
        requested_ticks=6,
        scheduled_ticks_by_child=(("d", 6),),
    )

    report = audit_schedule_result(result, (child,), _config())
    codes = {violation.code for violation in report.violations}

    assert "FEASIBILITY_MISMATCH" in codes
    assert "OBJECTIVE_MISMATCH" in codes


def test_report_is_invariant_to_input_order() -> None:
    children = (V3Child("b", "Daycare", 4), V3Child("a", "Daycare", 4))
    assignments = (
        _assignment("b", "2026-06-01", 84, 88),
        _assignment("a", "2026-06-01", 84, 88),
    )

    first = audit_assignments(assignments, children, _config())
    second = audit_assignments(reversed(assignments), reversed(children), _config())

    assert first == second


def test_underfill_can_be_observed_without_failing_a_partial_schedule() -> None:
    child = V3Child("d", "Daycare", 10)
    assignment = _assignment("d", "2026-06-01", 84, 90)

    report = audit_assignments((assignment,), (child,), _config(), require_exact_claims=False)

    assert report.valid
    assert report.shortfall_ticks_by_child == (("d", 4),)


def test_final_daycare_realism_rejects_more_than_nine_hours_per_day() -> None:
    child = V3Child("d", "Daycare", 120)
    assignment = _assignment("d", "2026-06-01", 84, 204)
    canonical_key = (("d", "2026-06-01", ((84, 204),)),)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(False, True, ("DAYCARE_DAILY_DURATION_EXCEEDED",)),
        trace=(PhaseTrace("daycare_realism", "applied"),),
        objective=Objective(1, 0, 0, 0, canonical_key),
        requested_ticks=120,
        scheduled_ticks_by_child=(("d", 120),),
    )

    report = audit_schedule_result(result, (child,), _config())
    violation = next(
        issue for issue in report.violations if issue.code == "DAYCARE_DAILY_DURATION_EXCEEDED"
    )

    assert not report.valid
    assert violation.expected == 108
    assert violation.actual == 120
    assert "9 hours" in violation.message


def test_incomplete_pre_realism_diagnostic_does_not_fail_nine_hour_gate() -> None:
    child = V3Child("d", "Daycare", 132)
    assignment = _assignment("d", "2026-06-01", 84, 204)
    canonical_key = (("d", "2026-06-01", ((84, 204),)),)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(False, False, ("SEARCH_EXHAUSTED:d",)),
        trace=(),
        objective=Objective(0, 12, 12, 0, canonical_key),
        requested_ticks=132,
        scheduled_ticks_by_child=(("d", 120),),
    )

    report = audit_schedule_result(
        result,
        (child,),
        _config(),
        require_exact_claims=False,
    )

    assert report.valid
    assert report.shortfall_ticks_by_child == (("d", 12),)
    assert "DAYCARE_DAILY_DURATION_EXCEEDED" not in {
        issue.code for issue in report.violations
    }


def test_daycare_realism_rollback_is_an_independently_valid_infeasible_diagnostic() -> None:
    child = V3Child("d", "Daycare", 120)
    assignment = _assignment("d", "2026-06-01", 84, 204)
    canonical_key = (("d", "2026-06-01", ((84, 204),)),)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(
            False,
            False,
            ("DAYCARE_REALISM_PLACEMENT_FAILED",),
        ),
        trace=(PhaseTrace("daycare_realism", "rolled_back"),),
        objective=Objective(0, 0, 0, 0, canonical_key),
        requested_ticks=120,
        scheduled_ticks_by_child=(("d", 120),),
    )

    report = audit_schedule_result(result, (child,), _config())
    codes = {issue.code for issue in report.violations}

    assert report.valid
    assert "DAYCARE_DAILY_DURATION_EXCEEDED" not in codes
    assert "FEASIBILITY_MISMATCH" not in codes


def test_daycare_realism_rollback_cannot_claim_proven_infeasibility() -> None:
    child = V3Child("d", "Daycare", 120)
    assignment = _assignment("d", "2026-06-01", 84, 204)
    canonical_key = (("d", "2026-06-01", ((84, 204),)),)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(
            False,
            True,
            ("DAYCARE_REALISM_PLACEMENT_FAILED",),
        ),
        trace=(PhaseTrace("daycare_realism", "rolled_back"),),
        objective=Objective(0, 0, 0, 0, canonical_key),
        requested_ticks=120,
        scheduled_ticks_by_child=(("d", 120),),
    )

    report = audit_schedule_result(result, (child,), _config())

    assert not report.valid
    assert "FEASIBILITY_PROOF_MISMATCH" in {
        issue.code for issue in report.violations
    }


def test_daycare_realism_marker_does_not_change_osc_school_off_rules() -> None:
    child = V3Child("osc", "OSC", 132)
    assignment = _assignment("osc", "2026-06-02", 84, 216, "osc_school_off")
    canonical_key = (("osc", "2026-06-02", ((84, 216),)),)
    result = V3ScheduleResult(
        assignments=(assignment,),
        feasibility=FeasibilityResult(True, True),
        trace=(PhaseTrace("daycare_realism", "applied"),),
        objective=Objective(0, 0, 0, 0, canonical_key),
        requested_ticks=132,
        scheduled_ticks_by_child=(("osc", 132),),
    )

    report = audit_schedule_result(result, (child,), _config())

    assert report.valid
