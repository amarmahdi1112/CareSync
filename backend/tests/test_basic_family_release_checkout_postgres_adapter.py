"""Focused contract tests for the 0029D PostgreSQL service adapter."""

from __future__ import annotations

import inspect
from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest

from app.basic import family_release_checkout_service as service
from app.basic.family_release_checkout_repository import (
    ReleaseCheckoutRepositoryError,
    ReleaseSnapshotAppendInput,
    postgres_release_checkout_context_input_at,
    postgres_release_checkout_insert_snapshot,
    postgres_release_checkout_instant,
)
from tests.test_basic_family_release_checkout import COMMITTED_AT, _command, _response
from tests.test_basic_family_release_context import _context


class _MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class _PostgresSession:
    def __init__(self, *, scalar_values=(), row=None):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        self.scalar_values = list(scalar_values)
        self.row = row
        self.scalar_calls: list[tuple[str, dict | None]] = []
        self.execute_calls: list[tuple[str, dict | None]] = []

    def scalar(self, statement, values=None):
        self.scalar_calls.append((str(statement), values))
        return self.scalar_values.pop(0)

    def execute(self, statement, values=None):
        self.execute_calls.append((str(statement), values))
        return _MappingResult(self.row)


def _append_payload() -> ReleaseSnapshotAppendInput:
    command = _command()
    resource = _response(command).resource
    return ReleaseSnapshotAppendInput(
        release_id=resource.release_id,
        child_id=command.child_id,
        facility_id=command.facility_id,
        room_id=command.expected_room_id,
        attendance_day_id=command.expected_attendance_day_id,
        attendance_day_version=resource.attendance_day_version,
        attendance_interval_id=command.expected_attendance_interval_id,
        checkout_event_id=resource.checkout_event_id,
        staff_shift_id=command.expected_staff_shift_id,
        recipient_person_id=command.recipient_person_id,
        recipient_person_version_id=command.recipient_person_version_id,
        authorization_id=command.authorization_id,
        authorization_version=command.authorization_version,
        authority_revision=command.expected_authority_revision,
        restriction_digest_sha256=command.expected_restriction_digest_sha256,
        verification_method=command.verification_method,
        verification_result=command.verification_result,
        decision_policy_version=command.expected_decision_policy_version,
        decision_at=COMMITTED_AT,
        requested_at=command.requested_at,
        request_hash=resource.request_hash,
    )


def test_postgres_instant_uses_wall_clock_not_transaction_start() -> None:
    session = _PostgresSession(scalar_values=[COMMITTED_AT])

    assert postgres_release_checkout_instant(session) == COMMITTED_AT
    sql, values = session.scalar_calls[0]
    assert sql == "SELECT pg_catalog.clock_timestamp()"
    assert values is None
    assert "transaction_timestamp" not in sql


def test_writer_context_uses_exact_post_lock_instant_and_strict_input() -> None:
    expected = _context(evaluated_at=COMMITTED_AT)
    session = _PostgresSession(scalar_values=[expected.model_dump(mode="json")])

    actual = postgres_release_checkout_context_input_at(
        session,
        child_id=expected.child_id,
        facility_id=expected.facility_id,
        decision_at=COMMITTED_AT,
    )

    assert actual == expected
    sql, values = session.scalar_calls[0]
    assert "caresync_family_release_context_inputs_at" in sql
    assert sql.count("CAST(:") == 3
    assert values == {
        "child_id": str(expected.child_id),
        "facility_id": str(expected.facility_id),
        "decision_at": COMMITTED_AT,
    }


def test_snapshot_append_calls_exact_21_argument_contract_and_parses_public_row() -> None:
    payload = _append_payload()
    expected = _response(_command()).resource
    session = _PostgresSession(row=expected.model_dump(mode="python"))

    actual = postgres_release_checkout_insert_snapshot(session, payload)

    assert actual == expected
    sql, values = session.execute_calls[0]
    assert "caresync_release_checkout_insert_snapshot" in sql
    assert sql.count("CAST(:") == 21
    assert sql.index(":decision_at") < sql.index(":requested_at")
    assert set(values or {}) == set(ReleaseSnapshotAppendInput.model_fields)
    assert values["decision_at"] == COMMITTED_AT


def test_public_row_normalizes_postgres_timestamptz_values_to_utc() -> None:
    payload = _append_payload()
    expected = _response(_command()).resource
    row = expected.model_dump(mode="python")
    connection_timezone = timezone(-timedelta(hours=6))
    for field_name in ("requested_at", "checked_out_at", "committed_at"):
        row[field_name] = row[field_name].astimezone(connection_timezone)
    session = _PostgresSession(row=row)

    actual = postgres_release_checkout_insert_snapshot(session, payload)

    assert actual == expected
    assert actual.requested_at.utcoffset() == timedelta(0)
    assert actual.checked_out_at.utcoffset() == timedelta(0)
    assert actual.committed_at.utcoffset() == timedelta(0)


def test_snapshot_append_rejects_non_public_or_malformed_projection() -> None:
    payload = _append_payload()
    row = _response(_command()).resource.model_dump(mode="python")
    row["evidence_id"] = str(payload.release_id)
    session = _PostgresSession(row=row)

    with pytest.raises(ReleaseCheckoutRepositoryError) as captured:
        postgres_release_checkout_insert_snapshot(session, payload)

    assert captured.value.code == "family_authority_release_checkout_unavailable"
    assert captured.value.status_code == 503


def test_pg_service_orders_locks_clock_projection_append_and_interval_close() -> None:
    source = inspect.getsource(service._fresh_release_postgres)

    actor_lock = source.index("_revalidated_actor(session, context, lock=True)")
    family_lock = source.index("select(Family)")
    care_lock = source.index("care_records = _care_records_for_day")
    decision_clock = source.index("decision_at = _database_instant(session)")
    context_projection = source.index("postgres_release_checkout_context_input_at")
    day_flush = source.index("session.flush()")
    snapshot_append = source.index("postgres_release_checkout_insert_snapshot")
    interval_close = source.index("interval.checked_out_at = decision_at")
    commit = source.index("_commit(session, context)")

    assert (
        actor_lock
        < family_lock
        < care_lock
        < decision_clock
        < context_projection
        < day_flush
        < snapshot_append
        < interval_close
        < commit
    )
    assert "AttendanceEvent(" not in source
    assert "record_command(" not in source


def test_pg_exact_replay_uses_definer_projection_and_existing_receipt(monkeypatch) -> None:
    command = _command()
    committed = _response(command)
    receipt = SimpleNamespace(
        **committed.receipt.model_dump(mode="python", exclude={"action_route"}),
        outcome={"action_route": committed.receipt.action_route},
    )
    session = _PostgresSession()
    calls = []

    def projected(_session, *, client_operation_id):
        calls.append(client_operation_id)
        return committed.resource

    monkeypatch.setattr(service, "postgres_release_checkout_replay", projected)

    replay = service._replay(session, command=command, receipt=receipt)

    assert replay.replayed is True
    assert replay.resource == committed.resource
    assert replay.receipt == committed.receipt
    assert calls == [command.client_operation_id]
