"""Opt-in destructive PostgreSQL proof for the 0029D release writer.

Run this suite only against a fresh disposable loopback cluster whose runtime
role was provisioned before migration and whose ``caresync`` database is at
head with ``bootstrap_basic_runtime_role.sql`` applied.  The global test guard
rejects retained ports 5432, 5433, and 5434.

The suite intentionally leaves committed release history in the disposable
database so its final assertion can prove that the D downgrade refuses before
DDL.  Drop the disposable database or cluster after the run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.api.basic import attendance
from app.api.basic.dependencies import BasicContext
from app.basic import family_release_checkout_service as checkout_service
from app.basic.family_release_checkout_repository import (
    ReleaseCheckoutRepositoryError,
    postgres_release_checkout_context_input_at,
    postgres_release_checkout_instant,
    postgres_release_checkout_replay,
)
from app.basic.family_release_checkout_schemas import ReleaseCheckoutCommand
from app.basic.family_release_context import compose_release_context
from app.basic.models import Organization, OrganizationMembership, Role, User
from app.basic.schemas import CheckOutRequest
from app.core.config import Settings
from app.db.session import Database
from tests.test_basic_postgres_family_authority_kernel import _set_context
from tests.test_basic_postgres_family_release_context import _seed_operational_gate

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
RUNTIME_ROLE = "caresync_basic_app"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
CURRENT_REVISION = "0029D_release_checkout_writer"
PREVIOUS_REVISION = "0029C_verified_release_checkout"

ACTIVATION_FUNCTION = "public.caresync_release_checkout_activation_enabled(uuid)"
REPLAY_FUNCTION = "public.caresync_release_checkout_replay(uuid)"
CONTEXT_FUNCTION = (
    "public.caresync_family_release_context_inputs_at("
    "uuid,uuid,timestamp with time zone)"
)
INSERT_FUNCTION = (
    "public.caresync_release_checkout_insert_snapshot("
    "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
    "integer,integer,text,text,text,text,timestamp with time zone,"
    "timestamp with time zone,text)"
)
INTERVAL_GUARD = "public.caresync_attendance_interval_verified_release_guard()"
SNAPSHOT_TIME_GUARD = "public.caresync_release_snapshot_commit_time_guard()"
CALLABLES = (ACTIVATION_FUNCTION, REPLAY_FUNCTION, CONTEXT_FUNCTION, INSERT_FUNCTION)
TRIGGER_ONLY = (INTERVAL_GUARD, SNAPSHOT_TIME_GUARD)

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    assert 1 <= port <= 65535
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=TEST_HOST,
        database_port=int(TEST_PORT or "0"),
        database_user=RUNTIME_ROLE,
        database_password="",
        database_name=TEST_DATABASE,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-release-checkout-proof-secret-32-bytes",
    )


def _migration_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": TEST_HOST,
            "DATABASE_PORT": str(TEST_PORT),
            "DATABASE_USER": "postgres",
            "DATABASE_PASSWORD": "",
            "DATABASE_NAME": TEST_DATABASE,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )
    return environment


def _alembic(action: str, revision: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=_migration_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _require_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _version(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM public.alembic_version")))


def _function_access(connection, signature: str) -> tuple[bool, bool, bool]:
    row = connection.execute(
        text(
            "SELECT procedure.prosecdef,"
            "COALESCE(pg_catalog.has_function_privilege("
            ":runtime,procedure.oid,'EXECUTE'),false) AS runtime_execute,"
            "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
            "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) AS acl "
            "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') AS public_execute "
            "FROM pg_catalog.pg_proc AS procedure "
            "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature)"
        ),
        {"runtime": RUNTIME_ROLE, "signature": signature},
    ).one()
    return bool(row.prosecdef), bool(row.runtime_execute), bool(row.public_execute)


def _seed_checkout_fixture(connection) -> dict[str, UUID]:
    ids = _seed_operational_gate(connection)
    connection.execute(
        text(
            "UPDATE public.users SET email_verified_at=statement_timestamp(),"
            "email_verification_method='test' WHERE id=:user_id"
        ),
        {"user_id": ids["user"]},
    )
    connection.execute(
        text(
            "UPDATE public.roles SET key='administrator',"
            "permissions='[\"attendance:record\",\"release:read\","
            "\"release:checkout\"]'::json WHERE id=:role_id"
        ),
        {"role_id": ids["role"]},
    )

    activation_id = uuid4()
    activation_operation_id = uuid4()
    _set_context(
        connection,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=activation_operation_id,
    )
    connection.execute(
        text(
            "INSERT INTO public.childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,"
            "target_id,request_hash,actor_user_id,facility_id,committed_version,outcome) "
            "VALUES (:id,:organization_id,:operation_id,"
            "'facility.release_checkout.activate','release_activation',"
            ":target_id,:request_hash,:actor_user_id,:facility_id,1,"
            "jsonb_build_object('action_route','/facilities/' || "
            "CAST(:facility_id AS text) || '/release-checkout'))"
        ),
        {
            "id": uuid4(),
            "organization_id": ids["organization"],
            "operation_id": activation_operation_id,
            "target_id": activation_id,
            "request_hash": "ab" * 32,
            "actor_user_id": ids["user"],
            "facility_id": ids["facility"],
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.facility_release_checkout_activations "
            "(id,organization_id,facility_id,activated_by_user_id,"
            "activated_by_membership_id,activated_by_role_id,activated_by_role_key,"
            "activation_operation_id,activation_policy_version) VALUES "
            "(:id,:organization_id,:facility_id,:user_id,:membership_id,:role_id,"
            "'administrator',:operation_id,'normal_verified_release_v1')"
        ),
        {
            "id": activation_id,
            "organization_id": ids["organization"],
            "facility_id": ids["facility"],
            "user_id": ids["user"],
            "membership_id": ids["membership"],
            "role_id": ids["role"],
            "operation_id": activation_operation_id,
        },
    )
    return ids


def _context(session, ids: dict[str, UUID], operation_id: UUID) -> BasicContext:
    _set_context(
        session,
        organization_id=ids["organization"],
        user_id=ids["user"],
        operation_id=operation_id,
    )
    return BasicContext(
        user=session.scalar(select(User).where(User.id == ids["user"])),
        organization=session.scalar(
            select(Organization).where(Organization.id == ids["organization"])
        ),
        membership=session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.id == ids["membership"]
            )
        ),
        role=session.scalar(select(Role).where(Role.id == ids["role"])),
    )


def _command(
    session,
    ids: dict[str, UUID],
    operation_id: UUID,
) -> ReleaseCheckoutCommand:
    decision_at = postgres_release_checkout_instant(session).astimezone(UTC)
    inputs = postgres_release_checkout_context_input_at(
        session,
        child_id=ids["child"],
        facility_id=ids["facility"],
        decision_at=decision_at,
    )
    release_context = compose_release_context(inputs)
    assert release_context.decision == "recipient_selection_available"
    assert len(release_context.eligible_recipients) == 1
    recipient = release_context.eligible_recipients[0]
    return ReleaseCheckoutCommand(
        schema_version="release-checkout-command-v1",
        client_operation_id=operation_id,
        requested_at=inputs.evaluated_at,
        child_id=ids["child"],
        facility_id=ids["facility"],
        expected_room_id=ids["room"],
        expected_attendance_day_id=ids["attendance_day"],
        expected_attendance_interval_id=ids["attendance_interval"],
        expected_staff_shift_id=ids["shift"],
        recipient_person_id=recipient.recipient_person_id,
        recipient_person_version_id=recipient.recipient_person_version_id,
        authorization_id=recipient.authorization_id,
        authorization_version=recipient.authorization_version,
        expected_authority_revision=release_context.authority_revision,
        expected_restriction_digest_sha256=(
            release_context.restriction_digest_sha256
        ),
        expected_decision_policy_version=release_context.decision_policy_version,
        verification_method="government_photo_id",
        verification_result="verified",
    )


def _release_counts(connection, organization_id: UUID) -> tuple[int, int, int, int, int]:
    return (
        int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.attendance_release_snapshots "
                    "WHERE organization_id=:organization_id"
                ),
                {"organization_id": organization_id},
            )
        ),
        int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.realtime_events "
                    "WHERE organization_id=:organization_id "
                    "AND event_type='attendance.release.checked_out' "
                    "AND entity_type='attendance_release'"
                ),
                {"organization_id": organization_id},
            )
        ),
        int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.childcare_command_receipts "
                    "WHERE organization_id=:organization_id "
                    "AND command_type='attendance.release.checkout'"
                ),
                {"organization_id": organization_id},
            )
        ),
        int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.attendance_events "
                    "WHERE organization_id=:organization_id AND event_type='check_out'"
                ),
                {"organization_id": organization_id},
            )
        ),
        int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE organization_id=:organization_id "
                    "AND action='child.release.checked_out'"
                ),
                {"organization_id": organization_id},
            )
        ),
    )


def test_01_empty_migration_roundtrip_catalog_acl_and_readiness_are_exact() -> None:
    admin = create_engine(_url("postgres"))
    database = Database(_settings())
    try:
        with admin.connect() as connection:
            assert _version(connection) == CURRENT_REVISION
            assert connection.scalar(
                text("SELECT count(*) FROM public.attendance_release_snapshots")
            ) == 0
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM public.childcare_command_receipts "
                    "WHERE command_type='attendance.release.checkout'"
                )
            ) == 0

        _require_success(_alembic("downgrade", PREVIOUS_REVISION))
        with admin.connect() as connection:
            assert _version(connection) == PREVIOUS_REVISION
            for signature in (*CALLABLES, *TRIGGER_ONLY):
                assert connection.scalar(
                    text("SELECT pg_catalog.to_regprocedure(:signature)"),
                    {"signature": signature},
                ) is None

        _require_success(_alembic("upgrade", CURRENT_REVISION))
        assert database.has_family_authority_release_context() is True
        assert database.has_family_release_checkout_foundation() is True
        assert database.has_family_release_checkout_runtime() is True

        with admin.connect() as connection:
            assert _version(connection) == CURRENT_REVISION
            for signature in CALLABLES:
                assert _function_access(connection, signature) == (True, True, False)
            for signature in TRIGGER_ONLY:
                assert _function_access(connection, signature) == (True, False, False)
            assert not connection.scalar(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    ":role,'public.facility_release_checkout_activations',"
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert connection.scalar(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    ":role,'public.attendance_release_snapshots','SELECT')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert not connection.scalar(
                text(
                    "SELECT pg_catalog.has_table_privilege("
                    ":role,'public.attendance_release_snapshots',"
                    "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                ),
                {"role": RUNTIME_ROLE},
            )

        with admin.begin() as connection:
            connection.execute(
                text(f"REVOKE EXECUTE ON FUNCTION {REPLAY_FUNCTION} FROM {RUNTIME_ROLE}")
            )
        assert database.has_family_release_checkout_runtime() is False
        with admin.begin() as connection:
            connection.execute(
                text(f"GRANT EXECUTE ON FUNCTION {REPLAY_FUNCTION} TO {RUNTIME_ROLE}")
            )
        assert database.has_family_release_checkout_runtime() is True
    finally:
        database.dispose()
        admin.dispose()


def test_02_atomic_rollback_commit_replay_guards_legacy_closure_and_refusal(
    monkeypatch,
) -> None:
    admin = create_engine(_url("postgres"))
    database = Database(_settings())
    with admin.begin() as connection:
        ids = _seed_checkout_fixture(connection)

    try:
        # An activated interval cannot be closed through the legacy write path
        # or by a direct table update without the same-transaction D bundle.
        with (
            pytest.raises(DBAPIError, match="requires one exact bundle"),
            admin.begin() as connection,
        ):
            connection.execute(
                text(
                    "UPDATE public.attendance_intervals "
                    "SET checked_out_at=clock_timestamp() WHERE id=:interval_id"
                ),
                {"interval_id": ids["attendance_interval"]},
            )

        legacy_operation_id = uuid4()
        with database.session_factory() as session:
            context = _context(session, ids, legacy_operation_id)
            request = SimpleNamespace(
                app=SimpleNamespace(
                    state=SimpleNamespace(
                        settings=SimpleNamespace(database_read_only=False),
                        family_release_checkout_foundation_present=True,
                        family_release_checkout_enabled=True,
                    )
                )
            )
            with pytest.raises(HTTPException) as legacy_rejected:
                attendance.check_out(
                    CheckOutRequest(
                        client_operation_id=legacy_operation_id,
                        child_id=ids["child"],
                        facility_id=ids["facility"],
                        occurred_at=None,
                    ),
                    request,
                    context,
                    session,
                )
            assert legacy_rejected.value.status_code == 409
            assert legacy_rejected.value.detail == {
                "code": "verified_release_checkout_required"
            }
            session.rollback()

        operation_id = uuid4()
        with database.session_factory() as session:
            context = _context(session, ids, operation_id)
            command = _command(session, ids, operation_id)

            original_commit = checkout_service._commit

            def fail_after_flush(failing_session, _context_value) -> None:
                failing_session.flush()
                raise checkout_service.ReleaseCheckoutServiceError(
                    code="injected_precommit_failure",
                    status_code=503,
                )

            monkeypatch.setattr(checkout_service, "_commit", fail_after_flush)
            with pytest.raises(
                checkout_service.ReleaseCheckoutServiceError,
                match="injected_precommit_failure",
            ):
                checkout_service.release_checkout(session, context, command)
            monkeypatch.setattr(checkout_service, "_commit", original_commit)

        with admin.connect() as connection:
            assert _release_counts(connection, ids["organization"]) == (0, 0, 0, 0, 0)
            assert connection.scalar(
                text("SELECT version FROM attendance_days WHERE id=:day_id"),
                {"day_id": ids["attendance_day"]},
            ) == 1
            assert connection.scalar(
                text(
                    "SELECT checked_out_at FROM attendance_intervals "
                    "WHERE id=:interval_id"
                ),
                {"interval_id": ids["attendance_interval"]},
            ) is None

        with database.session_factory() as session:
            context = _context(session, ids, operation_id)
            committed = checkout_service.release_checkout(session, context, command)
        assert committed.replayed is False
        assert committed.resource.client_operation_id == operation_id
        assert committed.resource.checked_out_at == committed.resource.committed_at

        # Protected reconciliation must outlive transient authorization and
        # operational eligibility.  Once an exact receipt exists, losing the
        # checkout permission or ending the shift cannot strand the mobile
        # client in an uncertain committed state.
        with admin.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.roles SET "
                    "permissions='[\"attendance:record\",\"release:read\"]'::json "
                    "WHERE id=:role_id"
                ),
                {"role_id": ids["role"]},
            )
            connection.execute(
                text(
                    "UPDATE public.staff_shifts SET status='closed',"
                    "clocked_out_at=clock_timestamp() WHERE id=:shift_id"
                ),
                {"shift_id": ids["shift"]},
            )

        with database.session_factory() as session:
            context = _context(session, ids, operation_id)
            replayed = checkout_service.release_checkout(session, context, command)
        assert replayed.replayed is True
        assert replayed.resource == committed.resource
        assert replayed.receipt == committed.receipt

        with admin.connect() as connection:
            assert _release_counts(connection, ids["organization"]) == (1, 1, 1, 1, 1)
            realtime = connection.execute(
                text(
                    "SELECT entity_id,payload->>'source',payload->>'facility_id' "
                    "FROM public.realtime_events "
                    "WHERE organization_id=:organization_id "
                    "AND event_type='attendance.release.checked_out' "
                    "AND entity_type='attendance_release'"
                ),
                {"organization_id": ids["organization"]},
            ).one()
            assert realtime == (
                committed.resource.release_id,
                "verified_release_checkout",
                str(ids["facility"]),
            )
            assert connection.scalar(
                text("SELECT version FROM attendance_days WHERE id=:day_id"),
                {"day_id": ids["attendance_day"]},
            ) == 2
            assert connection.scalar(
                text(
                    "SELECT checked_out_at FROM attendance_intervals "
                    "WHERE id=:interval_id"
                ),
                {"interval_id": ids["attendance_interval"]},
            ) == committed.resource.checked_out_at

        with database.session_factory() as session:
            _set_context(
                session,
                organization_id=ids["organization"],
                user_id=ids["user"],
                operation_id=uuid4(),
            )
            with pytest.raises(ReleaseCheckoutRepositoryError) as wrong_operation:
                postgres_release_checkout_replay(
                    session,
                    client_operation_id=operation_id,
                )
            assert wrong_operation.value.code == "release_checkout_forbidden"
            assert wrong_operation.value.status_code == 403
            session.rollback()

        with (
            pytest.raises(DBAPIError, match="interval is immutable"),
            admin.begin() as connection,
        ):
            connection.execute(
                text(
                    "UPDATE public.attendance_intervals "
                    "SET sequence=sequence+1 WHERE id=:interval_id"
                ),
                {"interval_id": ids["attendance_interval"]},
            )
        with (
            pytest.raises(DBAPIError, match="interval is immutable"),
            admin.begin() as connection,
        ):
            connection.execute(
                text("DELETE FROM attendance_intervals WHERE id=:interval_id"),
                {"interval_id": ids["attendance_interval"]},
            )
        with (
            pytest.raises(DBAPIError, match="snapshot is immutable"),
            admin.begin() as connection,
        ):
            connection.execute(
                text(
                    "UPDATE attendance_release_snapshots "
                    "SET recipient_display_name='Changed' WHERE id=:release_id"
                ),
                {"release_id": committed.resource.release_id},
            )

        refused = _alembic("downgrade", PREVIOUS_REVISION)
        assert refused.returncode != 0
        assert "0029D downgrade refused before DDL" in refused.stdout + refused.stderr
        with admin.connect() as connection:
            assert _version(connection) == CURRENT_REVISION
            assert connection.scalar(
                text("SELECT pg_catalog.to_regprocedure(:signature) IS NOT NULL"),
                {"signature": REPLAY_FUNCTION},
            ) is True
            assert _release_counts(connection, ids["organization"]) == (1, 1, 1, 1, 1)
    finally:
        database.dispose()
        admin.dispose()
