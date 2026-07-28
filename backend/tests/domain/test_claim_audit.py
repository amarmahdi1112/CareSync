from app.domain.claims import AuditTrail
from app.domain.claims.types import AttendanceDecision


def test_audit_can_be_enabled_disabled_and_bounded() -> None:
    disabled = AuditTrail(False)
    disabled.log("simulation_start", "ignored")
    assert disabled.get_entries() == ()

    limited = AuditTrail(max_entries=2)
    for index in range(3):
        limited.log("hours_allocated", f"Entry {index}")
    assert [entry.message for entry in limited.get_entries()] == ["Entry 1", "Entry 2"]


def test_audit_records_lifecycle_and_decisions() -> None:
    audit = AuditTrail()
    audit.log_simulation_start(10, 20, {"capacity": 50})
    audit.log_day_start("2024-01-15", 200)
    audit.log_attendance_decision(
        AttendanceDecision(
            "child-1",
            "2024-01-15",
            "attend",
            "behavioral_profile",
            0.85,
            False,
            8,
        )
    )
    audit.log_hours_allocated("child-1", "2024-01-15", 8, 52)
    audit.log_day_end("2024-01-15", 1, 8)
    audit.log_simulation_end(1, 8, 10)
    assert len(audit.get_entries_by_type("simulation_start")) == 1
    assert len(audit.get_entries_for_child("child-1")) == 2
    assert len(audit.get_entries_for_date("2024-01-15")) == 2


def test_audit_explanation_summary_and_clear_match_legacy() -> None:
    audit = AuditTrail()
    audit.log_hours_allocated("child-1", "2024-01-15", 8, 52)
    audit.log_hours_allocated("child-1", "2024-01-16", 8, 44)
    audit.log_fairness_adjustment("child-1", "Boost", 16, 24)
    audit.log_capacity_exhausted("2024-01-17", "child-1", 8)
    audit.log_warning("warning")
    audit.log_error("error")
    explanation = audit.explain_claim("child-1")
    assert "Hours allocations: 2" in explanation
    assert "Fairness adjustments: 1" in explanation
    assert "added 8.0 hours" in explanation
    assert "No audit entries found" in audit.explain_claim("unknown")
    assert audit.get_summary()["warnings"] == 1
    assert audit.get_summary()["errors"] == 1
    audit.clear()
    assert audit.get_entries() == ()
