"""Static fail-closed proofs for the additive 0029D PostgreSQL writer."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.session import (
    _RELEASE_RESOURCE_TABLE_RESULT,
    _release_checkout_activation_immutability_is_hardened,
    _release_checkout_activation_projection_is_hardened,
    _release_checkout_interval_guard_is_hardened,
    _release_checkout_replay_projection_is_hardened,
    _release_checkout_snapshot_immutability_is_hardened,
    _release_checkout_snapshot_repository_is_hardened,
    _release_checkout_snapshot_time_guard_is_hardened,
    _release_context_projection_definition_is_hardened,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_postgres_readiness_catalog_queries_avoid_reserved_aliases() -> None:
    source = (BACKEND_ROOT / "app" / "db" / "session.py").read_text()
    assert "pg_constraint AS constraint " not in source
    assert "pg_constraint AS constraint_record" in source
    assert "constraint_record.conname" in source


def _load_revision(name: str, filename: str):
    path = BACKEND_ROOT / "alembic" / "versions" / filename
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capture(monkeypatch: pytest.MonkeyPatch, installer_name: str) -> list[str]:
    migration = _load_revision(
        f"writer_{installer_name}",
        "0029D_release_checkout_postgres_writer.py",
    )
    statements: list[str] = []
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: statements.append(str(statement)),
    )
    getattr(migration, installer_name)()
    return statements


def _function_statement(statements: list[str]) -> str:
    return next(statement for statement in statements if "CREATE FUNCTION" in statement)


def _trigger_statement(statements: list[str]) -> str:
    return next(statement for statement in statements if "CREATE TRIGGER" in statement)


def test_d_installers_match_all_readiness_hardening_detectors(monkeypatch) -> None:
    activation = _function_statement(_capture(monkeypatch, "_install_activation_projection"))
    replay = _function_statement(_capture(monkeypatch, "_install_replay_projection"))
    repository = _function_statement(_capture(monkeypatch, "_install_snapshot_repository"))
    snapshot_time_statements = _capture(monkeypatch, "_install_snapshot_time_guard")
    interval_statements = _capture(monkeypatch, "_install_interval_guard")

    assert _release_checkout_activation_projection_is_hardened(activation)
    assert _release_checkout_replay_projection_is_hardened(
        replay,
        _RELEASE_RESOURCE_TABLE_RESULT,
    )
    assert not _release_checkout_replay_projection_is_hardened(
        replay.replace("membership.status='active'", "membership.status<>'removed'"),
        _RELEASE_RESOURCE_TABLE_RESULT,
    )
    assert not _release_checkout_replay_projection_is_hardened(
        replay.replace(
            "AND actor.email_verified_at IS NOT NULL",
            "AND actor.email_verified_at IS NOT NULL "
            "AND permission.value='release:checkout'",
        ),
        _RELEASE_RESOURCE_TABLE_RESULT,
    )
    assert _release_checkout_snapshot_repository_is_hardened(
        repository,
        _RELEASE_RESOURCE_TABLE_RESULT,
    )
    assert _release_checkout_snapshot_time_guard_is_hardened(
        _function_statement(snapshot_time_statements),
        _trigger_statement(snapshot_time_statements),
    )
    assert _release_checkout_interval_guard_is_hardened(
        _function_statement(interval_statements),
        _trigger_statement(interval_statements),
    )


def test_replay_is_private_exact_recovery_not_fresh_authorization(monkeypatch) -> None:
    replay = _function_statement(_capture(monkeypatch, "_install_replay_projection"))

    assert "membership.status='active'" in replay
    assert "organization_record.status='active'" in replay
    assert "snapshot.actor_user_id=context_user_id" in replay
    assert "receipt.actor_user_id=context_user_id" in replay
    assert "context_operation_id<>requested_client_operation_id" in replay
    assert "permission.value=" not in replay
    assert "JOIN public.roles" not in replay
    assert "staff_shifts" not in replay
    assert _release_checkout_replay_projection_is_hardened(
        replay,
        _RELEASE_RESOURCE_TABLE_RESULT,
    )


def test_activation_projection_reports_facility_truth_not_caller_eligibility(
    monkeypatch,
) -> None:
    activation = _function_statement(_capture(monkeypatch, "_install_activation_projection"))

    assert "membership.status='active'" in activation
    assert "facility.id=requested_facility_id" in activation
    assert "facility.status='active'" in activation
    assert "activation.facility_id=facility.id" in activation
    assert "permission.value=" not in activation
    assert "JOIN public.roles" not in activation
    assert "staff_shifts" not in activation
    assert _release_checkout_activation_projection_is_hardened(activation)


def test_public_resource_order_and_writer_arity_are_exact(monkeypatch) -> None:
    migration = _load_revision("writer_contract", "0029D_release_checkout_postgres_writer.py")
    replay = _function_statement(_capture(monkeypatch, "_install_replay_projection"))
    repository = _function_statement(_capture(monkeypatch, "_install_snapshot_repository"))

    expected_signature = (
        "public.caresync_release_checkout_insert_snapshot("
        "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
        "integer,integer,text,text,text,text,timestamp with time zone,"
        "timestamp with time zone,text)"
    )
    assert migration.revision == "0029D_release_checkout_writer"
    assert len(migration.revision) <= 32
    assert expected_signature == migration.INSERT_FUNCTION
    assert " AS authorization\n" not in repository
    assert "authorization_record.basis_evidence_id" in repository
    assert "FOR SHARE OF authorization_record" in repository
    assert "requested_decision_at timestamp with time zone" in repository
    assert "requested_requested_at timestamp with time zone" in repository
    assert expected_signature.removeprefix(
        "public.caresync_release_checkout_insert_snapshot("
    ).removesuffix(")").count(",") == 20
    for definition in (replay, repository):
        assert definition.count("snapshot.recipient_person_id,") == 1
        assert definition.count("snapshot.recipient_person_version_id,") == 1
        assert (
            "snapshot.actor_membership_id,\n"
            "                 snapshot.recipient_person_id,\n"
            "                 snapshot.recipient_person_version_id,\n"
            "                 snapshot.recipient_display_name::text"
        ) in definition


@pytest.mark.parametrize(
    ("installer", "detector", "old", "new"),
    (
        (
            "_install_activation_projection",
            _release_checkout_activation_projection_is_hardened,
            "facility.status='active'",
            "facility.status='inactive'",
        ),
        (
            "_install_snapshot_repository",
            _release_checkout_snapshot_repository_is_hardened,
            "observed_after_locks := pg_catalog.clock_timestamp();",
            "observed_after_locks := decision_at;",
        ),
        (
            "_install_snapshot_repository",
            _release_checkout_snapshot_repository_is_hardened,
            "INSERT INTO public.attendance_events",
            "INSERT INTO public.realtime_events",
        ),
    ),
)
def test_callable_detector_rejects_authority_or_atomicity_drift(
    monkeypatch,
    installer,
    detector,
    old,
    new,
) -> None:
    definition = _function_statement(_capture(monkeypatch, installer))
    assert definition.count(old) == 1
    mutated = definition.replace(old, new, 1)
    if installer == "_install_activation_projection":
        assert not detector(mutated)
    else:
        assert not detector(mutated, _RELEASE_RESOURCE_TABLE_RESULT)


def test_trigger_detectors_reject_timing_or_same_transaction_drift(monkeypatch) -> None:
    snapshot_statements = _capture(monkeypatch, "_install_snapshot_time_guard")
    snapshot_function = _function_statement(snapshot_statements)
    snapshot_trigger = _trigger_statement(snapshot_statements)
    interval_statements = _capture(monkeypatch, "_install_interval_guard")
    interval_function = _function_statement(interval_statements)
    interval_trigger = _trigger_statement(interval_statements)

    assert not _release_checkout_snapshot_time_guard_is_hardened(
        snapshot_function,
        snapshot_trigger.replace("BEFORE INSERT", "AFTER INSERT"),
    )
    assert not _release_checkout_snapshot_time_guard_is_hardened(
        snapshot_function.replace(
            "AND receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid;",
            ";",
        ),
        snapshot_trigger,
    )
    assert not _release_checkout_interval_guard_is_hardened(
        interval_function.replace(
            "AND receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid",
            "AND receipt.xmin=receipt.xmin",
        ),
        interval_trigger,
    )
    assert not _release_checkout_interval_guard_is_hardened(
        interval_function,
        interval_trigger.replace("BEFORE DELETE OR UPDATE", "AFTER DELETE OR UPDATE"),
    )


def test_multi_event_detectors_require_pg_canonical_event_order(monkeypatch) -> None:
    c = _load_revision("writer_canonical_c", "0029C_verified_release_checkout.py")
    monkeypatch.setattr(
        c.op,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    activation_statements: list[str] = []
    monkeypatch.setattr(
        c.op,
        "execute",
        lambda statement: activation_statements.append(str(statement)),
    )
    c._install_activation_immutability()
    activation_function = _function_statement(activation_statements)
    activation_raw_trigger = _trigger_statement(activation_statements)
    activation_trigger = activation_raw_trigger.replace(
        "BEFORE UPDATE OR DELETE",
        "BEFORE DELETE OR UPDATE",
    )
    assert _release_checkout_activation_immutability_is_hardened(
        activation_function,
        activation_trigger,
    )
    assert not _release_checkout_activation_immutability_is_hardened(
        activation_function,
        activation_raw_trigger,
    )

    snapshot_statements: list[str] = []
    monkeypatch.setattr(
        c.op,
        "execute",
        lambda statement: snapshot_statements.append(str(statement)),
    )
    c._install_snapshot_immutability()
    snapshot_function = _function_statement(snapshot_statements)
    snapshot_raw_trigger = _trigger_statement(snapshot_statements)
    snapshot_trigger = snapshot_raw_trigger.replace(
        "BEFORE UPDATE OR DELETE",
        "BEFORE DELETE OR UPDATE",
    )
    assert _release_checkout_snapshot_immutability_is_hardened(
        snapshot_function,
        snapshot_trigger,
    )
    assert not _release_checkout_snapshot_immutability_is_hardened(
        snapshot_function,
        snapshot_raw_trigger,
    )


class _ScalarResult:
    def __init__(self, value: str) -> None:
        self.value = value

    def scalar_one_or_none(self) -> str:
        return self.value


class _DefinitionBind:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, definition: str) -> None:
        self.definition = definition
        self.executed: list[str] = []

    def execute(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(self.definition)

    def exec_driver_sql(self, statement: str) -> None:
        self.executed.append(statement)
        self.definition = statement


def test_receipt_guard_clock_patch_is_narrow_and_round_trips(monkeypatch) -> None:
    migration = _load_revision("writer_clock", "0029D_release_checkout_postgres_writer.py")
    original = (
        "CREATE FUNCTION public.caresync_childcare_operation_guard() RETURNS trigger "
        "LANGUAGE plpgsql AS $guard$ BEGIN "
        "NEW.committed_at := transaction_timestamp(); RETURN NEW; END $guard$"
    )
    bind = _DefinitionBind(original)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)

    migration._set_release_receipt_clock_contract(enabled=True)
    patched = bind.definition
    assert "NEW.command_type = 'attendance.release.checkout'" in patched
    assert "ck_release_checkout_receipt_time" in patched
    assert patched.count("NEW.committed_at := transaction_timestamp();") == 1

    migration._set_release_receipt_clock_contract(enabled=False)
    assert bind.definition == original


def test_context_at_clones_b_with_only_an_asserted_instant(monkeypatch) -> None:
    b = _load_revision("writer_context_b", "0029B_release_context.py")
    b_statements: list[str] = []
    monkeypatch.setattr(b.op, "execute", lambda statement: b_statements.append(str(statement)))
    b._install_postgres_projection()
    b_definition = _function_statement(b_statements)
    delimiter = "$projection$"
    source = b_definition.split(delimiter, 2)[1]
    assert source.count(
        "evaluated_at_value timestamptz := pg_catalog.statement_timestamp();"
    ) == 1

    d = _load_revision("writer_context_d", "0029D_release_checkout_postgres_writer.py")
    bind = _DefinitionBind(source)
    d_statements: list[str] = []
    monkeypatch.setattr(d.op, "get_bind", lambda: bind)
    monkeypatch.setattr(d.op, "execute", lambda statement: d_statements.append(str(statement)))
    d._install_writer_context_projection()
    context_at = _function_statement(d_statements)

    assert "evaluated_at_value timestamptz := requested_evaluated_at;" in context_at
    assert "statement_timestamp()" not in context_at
    assert "transaction_timestamp()" not in context_at
    assert _release_context_projection_definition_is_hardened(context_at)
