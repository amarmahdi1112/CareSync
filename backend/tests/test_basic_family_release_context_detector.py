"""Portable fail-closed proofs for the 0029B runtime body detector."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.db.session import (
    _release_context_invalidation_definitions_are_hardened,
    _release_context_projection_definition_is_hardened,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _migration_module() -> ModuleType:
    migration_path = BACKEND_ROOT / "alembic/versions/0029B_release_context.py"
    spec = spec_from_file_location("release_context_detector_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _captured_statements(
    monkeypatch: pytest.MonkeyPatch,
    installer_name: str,
) -> list[str]:
    module = _migration_module()
    statements: list[str] = []

    def capture(statement: Any) -> None:
        statements.append(str(statement))

    monkeypatch.setattr(module.op, "execute", capture)
    getattr(module, installer_name)()
    return statements


def test_projection_body_detector_accepts_current_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _captured_statements(
        monkeypatch,
        "_install_postgres_projection",
    )
    assert _release_context_projection_definition_is_hardened(statements[0]) is True


def test_projection_body_detector_requires_one_common_operational_cte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _captured_statements(
        monkeypatch,
        "_install_postgres_projection",
    )[0]
    separate_actor_statement_shape = projection.replace(
        "WITH actor_scope AS (",
        "SELECT true INTO actor_scope_ready;\nWITH actor_identity AS (",
    ).replace("actor_scope.", "actor_identity.")
    assert (
        _release_context_projection_definition_is_hardened(
            separate_actor_statement_shape
        )
        is False
    )


def test_projection_body_detector_rejects_operational_gate_moved_outside_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = _captured_statements(
        monkeypatch,
        "_install_postgres_projection",
    )[0]
    weakened = projection.replace(
        "FROM public.membership_room_assignments AS assignment",
        "FROM public.unscoped_room_assignments AS assignment",
    ).replace(
        "SELECT head.revision",
        "IF false THEN\n"
        "  SELECT count(*) INTO exact_shift_count\n"
        "  FROM public.membership_room_assignments AS assignment;\n"
        "END IF;\nSELECT head.revision",
    )
    assert "public.membership_room_assignments" in weakened
    assert _release_context_projection_definition_is_hardened(weakened) is False


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            "current_setting('app.current_organization_id', true)",
            "current_setting('app.untrusted_organization_id', true)",
        ),
        ("'release:read'", "'families:read'"),
        ("public.staff_shifts", "public.shift_records"),
        ("clocked_out_at", "shift_finished_at"),
        ("public.attendance_intervals", "public.child_presence_intervals"),
        ("checked_out_at", "presence_finished_at"),
        ("public.membership_room_assignments", "public.room_memberships"),
        ("FOR SHARE", "FOR KEY SHARE"),
        ("'authority_revision'", "'authority_version'"),
        ("'supporting_evidence'", "'evidence_summary'"),
    ),
)
def test_projection_body_detector_rejects_missing_mandatory_boundary(
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
) -> None:
    projection = _captured_statements(
        monkeypatch,
        "_install_postgres_projection",
    )[0]
    assert old in projection
    weakened = projection.replace(old, new)
    assert _release_context_projection_definition_is_hardened(weakened) is False


@pytest.mark.parametrize(
    "unsafe_sql",
    (
        "INSERT INTO public.audit_events DEFAULT VALUES;",
        "UPDATE public.children SET is_active = false;",
        "SELECT confidential_reason FROM public.child_release_rules;",
        "SELECT * FROM public.family_authority_evidence_objects;",
        "SELECT * FROM public.attendance_release_snapshots;",
        "PERFORM pg_catalog.set_config('app.current_user_id', '', true);",
    ),
)
def test_projection_body_detector_rejects_writes_and_sensitive_sources(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_sql: str,
) -> None:
    projection = _captured_statements(
        monkeypatch,
        "_install_postgres_projection",
    )[0]
    assert (
        _release_context_projection_definition_is_hardened(
            projection.replace("RETURN result;", f"{unsafe_sql}\nRETURN result;")
        )
        is False
    )


def test_invalidation_detector_accepts_current_exact_generic_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _captured_statements(
        monkeypatch,
        "_install_postgres_invalidation",
    )
    assert (
        _release_context_invalidation_definitions_are_hardened(
            statements[0],
            statements[2],
        )
        is True
    )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("'child_authority_head', NULL", "'child_authority_head', NEW.child_id"),
        ("'scope', 'release_context'", "'scope', 'child'"),
        ("NEW.organization_id", "NULL"),
        ("UPDATE OF revision", "UPDATE"),
    ),
)
def test_invalidation_detector_rejects_identity_leaks_or_broad_trigger(
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
) -> None:
    statements = _captured_statements(
        monkeypatch,
        "_install_postgres_invalidation",
    )
    function_definition = statements[0]
    trigger_definition = statements[2]
    if old in function_definition:
        function_definition = function_definition.replace(old, new)
    else:
        assert old in trigger_definition
        trigger_definition = trigger_definition.replace(old, new)
    assert (
        _release_context_invalidation_definitions_are_hardened(
            function_definition,
            trigger_definition,
        )
        is False
    )
