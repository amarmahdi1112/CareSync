"""Opt-in PostgreSQL certification for the 0033 synthetic billing ledger.

The suite is inert unless the caller supplies an administrative URL for a
disposable loopback cluster.  It never connects to retained CareSync ports and
creates/drops only the application-required ``caresync`` database on that
explicitly disposable cluster.
"""

from __future__ import annotations

import os
import subprocess
import sys
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app.basic.billing_schemas import (
    MANUAL_BILLING_REVIEW_ATTESTATION,
    PRIVATE_MANUAL_BILLING_LABEL,
)
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))
ADMIN_URL_TEXT = os.getenv("BASIC_POSTGRES_BILLING_LEDGER_TEST_URL")
DATABASE_NAME = "caresync"
PROTECTED_PORTS = {5432, 5433, 5434}
RUNTIME_ROLE = "caresync_basic_app"
CLUSTER_ROLES = (
    "caresync_transport_evidence_ingest",
    "caresync_transport_command_owner",
    RUNTIME_ROLE,
)


def _guard_admin_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0033 certification requires PostgreSQL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0033 certification requires a loopback host")
    if url.port is None or url.port in PROTECTED_PORTS or not 1 <= url.port <= 65535:
        raise RuntimeError("0033 certification refuses protected or invalid ports")
    if url.database != "postgres" or not url.username:
        raise RuntimeError("0033 certification URL must target postgres as an admin")
    return url


ADMIN_URL = _guard_admin_url(ADMIN_URL_TEXT) if ADMIN_URL_TEXT else None
pytestmark = pytest.mark.skipif(
    ADMIN_URL is None,
    reason="BASIC_POSTGRES_BILLING_LEDGER_TEST_URL must name a disposable cluster",
)


def _url(*, user: str | None = None, database: str = DATABASE_NAME) -> URL:
    assert ADMIN_URL is not None
    return URL.create(
        "postgresql+psycopg",
        username=user or ADMIN_URL.username,
        password=ADMIN_URL.password if user is None else None,
        host=ADMIN_URL.host,
        port=ADMIN_URL.port,
        database=database,
    )


def _migration() -> subprocess.CompletedProcess[str]:
    assert ADMIN_URL is not None
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": str(ADMIN_URL.host),
            "DATABASE_PORT": str(ADMIN_URL.port),
            "DATABASE_USER": str(ADMIN_URL.username),
            "DATABASE_PASSWORD": str(ADMIN_URL.password or ""),
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _bootstrap() -> subprocess.CompletedProcess[str]:
    assert ADMIN_URL is not None
    environment = os.environ.copy()
    if ADMIN_URL.password:
        environment["PGPASSWORD"] = str(ADMIN_URL.password)
    return subprocess.run(
        [
            str(PSQL),
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(ADMIN_URL.host),
            "-p",
            str(ADMIN_URL.port),
            "-U",
            str(ADMIN_URL.username),
            "-d",
            DATABASE_NAME,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _runtime_settings(
    *,
    billing_organization_id=None,
    manual_billing_organization_ids=None,
) -> Settings:
    assert ADMIN_URL is not None
    values = {
        "_env_file": None,
        "environment": ("development" if manual_billing_organization_ids is not None else "test"),
        "database_type": "postgres",
        "database_host": str(ADMIN_URL.host),
        "database_port": int(ADMIN_URL.port or 0),
        "database_user": RUNTIME_ROLE,
        "database_password": "",
        "database_name": DATABASE_NAME,
        "database_ssl": False,
        "database_read_only": False,
        "enable_advanced_routes": False,
        "jwt_secret": "billing-0033-postgres-test-secret-at-least-32-bytes",
    }
    if manual_billing_organization_ids is not None:
        values.update(
            {
                "billing_mode": "manual",
                "billing_manual_target_attestation": "PRIVATE_LOCAL_MANUAL_BILLING",
                "billing_manual_organization_ids": manual_billing_organization_ids,
            }
        )
    elif billing_organization_id is not None:
        values.update(
            {
                "billing_mode": "sandbox",
                "billing_sandbox_target_attestation": ("DISPOSABLE_CARESYNC_BILLING_SANDBOX"),
                "billing_sandbox_organization_ids": [billing_organization_id],
            }
        )
    return Settings(**values)


def _post(client: TestClient, path: str, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _prepare_and_execute(
    client: TestClient,
    headers: dict[str, str],
    *,
    command_type: str,
    path: str,
    payload: dict,
) -> dict:
    preparation = _post(
        client,
        "/api/v1/billing/commands/prepare",
        headers,
        {"command_type": command_type, "request_payload": payload},
    )
    assert preparation["exact_retry"] is False
    result = _post(client, path, headers, payload)
    assert result["command_type"] == command_type
    assert result["request_hash"] == preparation["request_hash"]
    assert result["exact_retry"] is False
    retry = _post(client, path, headers, payload)
    assert retry == {**result, "exact_retry": True}
    return result


def _attest_all_sources(engine, organization_id: UUID, actor_user_id: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.billing_seed_mode','synthetic_fixture',true)")
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id',:value,true)"),
            {"value": str(organization_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id',:value,true)"),
            {"value": str(actor_user_id)},
        )
        source_rows = [("organization", organization_id)]
        source_rows.extend(
            connection.execute(
                text(
                    "SELECT 'family',id FROM families WHERE organization_id=:org "
                    "UNION ALL SELECT 'guardian',id FROM guardians WHERE organization_id=:org "
                    "UNION ALL SELECT 'child',id FROM children WHERE organization_id=:org "
                    "UNION ALL SELECT 'enrollment',id FROM enrollments "
                    "WHERE organization_id=:org "
                    "UNION ALL SELECT 'facility',id FROM facilities "
                    "WHERE organization_id=:org "
                    "UNION ALL SELECT 'program',id FROM facility_programs "
                    "WHERE organization_id=:org"
                ),
                {"org": organization_id},
            )
        )
        for source_type, source_id in source_rows:
            connection.execute(
                text(
                    "INSERT INTO billing_sandbox_source_attestations "
                    "(id,organization_id,source_type,source_id,marker,reason_code,"
                    "attested_by_user_id,attested_at) VALUES "
                    "(:id,:org,:source_type,:source_id,'TEST_SYNTHETIC_ONLY',"
                    "'disposable_test_fixture',:actor,now())"
                ),
                {
                    "id": uuid4(),
                    "org": organization_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "actor": actor_user_id,
                },
            )


@pytest.fixture(scope="module")
def billing_database():
    assert ADMIN_URL is not None
    admin = create_engine(_url(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname=:name"),
            {"name": DATABASE_NAME},
        )
        occupied_roles = set(
            connection.execute(
                text("SELECT rolname FROM pg_roles WHERE rolname=ANY(CAST(:roles AS text[]))"),
                {"roles": list(CLUSTER_ROLES)},
            ).scalars()
        )
        if exists or occupied_roles:
            raise RuntimeError("0033 disposable database or role names are already occupied")
        connection.exec_driver_sql(f'CREATE DATABASE "{DATABASE_NAME}"')
    try:
        migrated = _migration()
        assert migrated.returncode == 0, migrated.stderr
        bootstrapped = _bootstrap()
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        yield create_engine(_url())
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": DATABASE_NAME},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"')
            for role in CLUSTER_ROLES:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        admin.dispose()


def test_migrate_bootstrap_restricted_startup_and_acl_repair(billing_database) -> None:
    database = Database(_runtime_settings())
    try:
        assert database.has_billing_ledger() is True
        database.assert_basic_runtime_identity()
    finally:
        database.dispose()

    # Re-running the parser and grant reconstruction must remain idempotent.
    rerun = _bootstrap()
    assert rerun.returncode == 0, rerun.stderr

    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "REVOKE INSERT ON public.billing_accounts FROM caresync_basic_app"
        )
    drifted = Database(_runtime_settings())
    try:
        with pytest.raises(RuntimeError, match="0033 billing ledger"):
            drifted.has_billing_ledger()
    finally:
        drifted.dispose()
    repaired = _bootstrap()
    assert repaired.returncode == 0, repaired.stderr
    certified = Database(_runtime_settings())
    try:
        assert certified.has_billing_ledger() is True
    finally:
        certified.dispose()


def test_local_schema_drift_certification_rejects_same_name_definition_changes(
    billing_database,
) -> None:
    def assert_rejected() -> None:
        database = Database(_runtime_settings())
        try:
            with pytest.raises(RuntimeError, match="0033 billing ledger"):
                database.has_billing_ledger()
        finally:
            database.dispose()

    def assert_certified() -> None:
        database = Database(_runtime_settings())
        try:
            assert database.has_billing_ledger() is True
        finally:
            database.dispose()

    with billing_database.begin() as connection:
        original_function = str(
            connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_functiondef("
                    "'public.caresync_0033_immutable_fact()'::pg_catalog.regprocedure)"
                )
            )
        )
        connection.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION public.caresync_0033_immutable_fact() "
            "RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public "
            "AS $$ BEGIN RETURN NEW; END $$"
        )
    assert_rejected()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(original_function)
    assert_certified()

    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "ALTER POLICY billing_accounts_0033_select ON public.billing_accounts USING (true)"
        )
    assert_rejected()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "ALTER POLICY billing_accounts_0033_select ON public.billing_accounts "
            "USING (organization_id=NULLIF(current_setting("
            "'app.current_organization_id',true),'')::uuid AND EXISTS ("
            "SELECT 1 FROM organization_memberships m JOIN roles r ON "
            "r.organization_id=m.organization_id AND r.id=m.role_id WHERE "
            "m.organization_id=NULLIF(current_setting("
            "'app.current_organization_id',true),'')::uuid AND "
            "m.user_id=NULLIF(current_setting('app.current_user_id',true),'')::uuid "
            "AND m.status='active' AND r.key IN ('owner','administrator') AND "
            "r.permissions::jsonb @> '[\"billing:read\"]'::jsonb))"
        )
    assert_certified()

    with billing_database.begin() as connection:
        original_trigger = str(
            connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_triggerdef(trigger.oid) "
                    "FROM pg_catalog.pg_trigger trigger WHERE trigger.tgrelid="
                    "'public.billing_accounts'::pg_catalog.regclass "
                    "AND trigger.tgname='billing_accounts_0033_immutable'"
                )
            )
        )
        connection.exec_driver_sql(
            "DROP TRIGGER billing_accounts_0033_immutable ON public.billing_accounts"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER billing_accounts_0033_immutable BEFORE INSERT ON "
            "public.billing_accounts FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_0033_immutable_fact()"
        )
    assert_rejected()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "DROP TRIGGER billing_accounts_0033_immutable ON public.billing_accounts"
        )
        connection.exec_driver_sql(original_trigger)
    assert_certified()

    with billing_database.begin() as connection:
        source_trigger = str(
            connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_triggerdef(trigger.oid) "
                    "FROM pg_catalog.pg_trigger trigger WHERE trigger.tgrelid="
                    "'public.families'::pg_catalog.regclass AND trigger.tgname="
                    "'families_0033_attested_source_immutable'"
                )
            )
        )
        connection.exec_driver_sql(
            "DROP TRIGGER families_0033_attested_source_immutable ON public.families"
        )
    assert_rejected()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(source_trigger)
    assert_certified()


def test_all_three_version_guards_accept_their_first_valid_version(
    billing_database,
) -> None:
    organization_id = uuid4()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TEMP TABLE billing_account_payer_versions "
            "(organization_id uuid,billing_account_id uuid,version_number integer)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER payer_version_guard BEFORE INSERT ON "
            "billing_account_payer_versions FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_0033_version_guard()"
        )
        connection.execute(
            text("INSERT INTO billing_account_payer_versions VALUES (:org,:root,1)"),
            {"org": organization_id, "root": uuid4()},
        )

        connection.exec_driver_sql(
            "CREATE TEMP TABLE billing_rate_plan_versions "
            "(organization_id uuid,rate_plan_id uuid,version_number integer,"
            "effective_from date)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER rate_version_guard BEFORE INSERT ON billing_rate_plan_versions "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_version_guard()"
        )
        connection.execute(
            text("INSERT INTO billing_rate_plan_versions VALUES (:org,:root,1,DATE '2026-01-01')"),
            {"org": organization_id, "root": uuid4()},
        )

        connection.exec_driver_sql(
            "CREATE TEMP TABLE billing_agreement_versions "
            "(organization_id uuid,agreement_id uuid,version_number integer,"
            "effective_from date)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER agreement_version_guard BEFORE INSERT ON "
            "billing_agreement_versions FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_0033_version_guard()"
        )
        connection.execute(
            text("INSERT INTO billing_agreement_versions VALUES (:org,:root,1,DATE '2026-01-01')"),
            {"org": organization_id, "root": uuid4()},
        )


def test_journal_validator_accepts_both_trigger_record_shapes(billing_database) -> None:
    organization_id = uuid4()
    journal_entry_id = uuid4()
    with billing_database.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TEMP TABLE billing_journal_entries (id uuid,organization_id uuid)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER journal_entry_shape AFTER INSERT ON billing_journal_entries "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_journal_validate()"
        )
        connection.execute(
            text("INSERT INTO billing_journal_entries VALUES (:id,:org)"),
            {"id": journal_entry_id, "org": organization_id},
        )
        connection.exec_driver_sql(
            "CREATE TEMP TABLE billing_journal_lines "
            "(id uuid,organization_id uuid,journal_entry_id uuid)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER journal_line_shape AFTER INSERT ON billing_journal_lines "
            "FOR EACH ROW EXECUTE FUNCTION public.caresync_0033_journal_validate()"
        )
        connection.execute(
            text("INSERT INTO billing_journal_lines VALUES (:id,:org,:entry)"),
            {"id": uuid4(), "org": organization_id, "entry": journal_entry_id},
        )


def test_runtime_cannot_mutate_or_seed_privileged_billing_state(
    billing_database,
) -> None:
    runtime = create_engine(_url(user=RUNTIME_ROLE))
    try:
        with runtime.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "INSERT INTO billing_sandbox_source_attestations "
                    "(id,organization_id,source_type,source_id,marker,reason_code,"
                    "attested_by_user_id,attested_at) VALUES "
                    "(:id,:org,'organization',:org,'SYNTHETIC_TEST_DATA',"
                    "'disposable_test_seed',:actor,now())"
                ),
                {"id": uuid4(), "org": uuid4(), "actor": uuid4()},
            )
        with runtime.begin() as connection, pytest.raises(DBAPIError):
            connection.exec_driver_sql("UPDATE billing_accounts SET status='open' WHERE false")
    finally:
        runtime.dispose()


def test_restricted_http_full_billing_chain_and_coherent_paging(
    billing_database,
) -> None:
    initial_app = create_app(_runtime_settings())
    suffix = uuid4().hex[:8]
    with TestClient(initial_app) as client:
        auth = _post(
            client,
            "/api/v1/auth/register",
            {},
            {
                "email": f"billing-owner-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Billing",
                "last_name": "Owner",
                "organization_name": f"Billing Sandbox {suffix}",
            },
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        organization_id = UUID(auth["user"]["organization_id"])
        actor_user_id = UUID(auth["user"]["id"])
        facility = _post(
            client,
            "/api/v1/facilities",
            headers,
            {"name": "Synthetic Centre", "licensed_capacity": 40, "status": "active"},
        )
        program = _post(
            client,
            "/api/v1/programs",
            headers,
            {
                "facility_id": facility["id"],
                "name": "Synthetic Daycare",
                "program_type": "daycare",
                "capacity": 40,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        room = _post(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Synthetic Room",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": "Synthetic Family",
                "primary_guardian": {
                    "first_name": "Primary",
                    "last_name": "Payer",
                    "relationship": "Parent",
                    "email": "primary-payer@example.test",
                    "cell_phone": "780-555-0101",
                },
                "secondary_guardian": {
                    "first_name": "Secondary",
                    "last_name": "Payer",
                    "relationship": "Parent",
                    "email": "secondary-payer@example.test",
                    "cell_phone": "780-555-0102",
                },
            },
        )
        primary = next(value for value in family["guardians"] if value["is_primary"])
        secondary = next(value for value in family["guardians"] if not value["is_primary"])
        child = _post(
            client,
            "/api/v1/children",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Synthetic",
                "last_name": "Child",
                "date_of_birth": "2023-01-01",
            },
        )
        local_today = datetime.now(ZoneInfo("America/Edmonton")).date()
        period_start = local_today.replace(day=1)
        period_end = local_today.replace(day=monthrange(local_today.year, local_today.month)[1])
        enrollment = _post(
            client,
            f"/api/v1/children/{child['id']}/enrollments",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": period_start.isoformat(),
            },
        )
        _post(
            client,
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": local_today.isoformat(),
            },
        )

    # The seeder's lock domain must block both source edits and authority
    # changes for the entire enumeration + attestation transaction.
    lock_connection = billing_database.connect()
    lock_transaction = lock_connection.begin()
    try:
        lock_connection.execute(
            text(
                "LOCK TABLE organizations,organization_memberships,roles,families,guardians,"
                "children,enrollments,facilities,facility_programs "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        for statement, parameters in (
            ("UPDATE families SET name=name WHERE id=:id", {"id": family["id"]}),
            ("UPDATE roles SET key=key WHERE organization_id=:org", {"org": organization_id}),
        ):
            with pytest.raises(DBAPIError), billing_database.begin() as contender:
                contender.execute(text("SET LOCAL lock_timeout='100ms'"))
                contender.execute(text(statement), parameters)
    finally:
        lock_transaction.rollback()
        lock_connection.close()

    # Invalid tenant timezone is never reported as write-ready.
    with billing_database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET timezone='Not/AZone' WHERE id=:id"),
            {"id": organization_id},
        )
    invalid_timezone_app = create_app(_runtime_settings(billing_organization_id=organization_id))
    with TestClient(invalid_timezone_app) as invalid_client:
        capability = invalid_client.get("/api/v1/billing/capability", headers=headers)
        assert capability.status_code == 200, capability.text
        assert capability.json()["runtime_available"] is False
        assert capability.json()["writes_available"] is False
        operation_id = str(uuid4())
        account_id = str(uuid4())
        guardian_id = str(uuid4())
        invoice_id = str(uuid4())
        payment_id = str(uuid4())
        agreement_id = str(uuid4())
        version_id = str(uuid4())
        open_payload = {
            "client_operation_id": operation_id,
            "family_id": family["id"],
            "payer_guardian_id": guardian_id,
        }
        blocked_writes = (
            (
                "/api/v1/billing/commands/prepare",
                {
                    "command_type": "account_open",
                    "request_payload": open_payload,
                },
            ),
            (
                f"/api/v1/billing/commands/{uuid4()}/finalize-absence",
                {
                    "expected_request_hash": "0" * 64,
                    "reason_code": "operator_confirmed_not_committed",
                },
            ),
            ("/api/v1/billing/accounts", open_payload),
            (
                f"/api/v1/billing/accounts/{account_id}/payer-assign",
                {
                    "client_operation_id": str(uuid4()),
                    "account_id": account_id,
                    "payer_guardian_id": guardian_id,
                    "expected_latest_payer_version_id": str(uuid4()),
                    "expected_latest_payer_version_number": 1,
                },
            ),
            (
                "/api/v1/billing/rate-plans",
                {
                    "client_operation_id": str(uuid4()),
                    "code": "INVALID-TZ-GATE",
                    "name": "Invalid timezone gate",
                    "program_type": "daycare",
                    "charge_kind": "core_care",
                    "facility_id": facility["id"],
                    "program_id": program["id"],
                    "billing_unit": "monthly_period",
                    "unit_amount_minor": 100,
                    "tax_rate_basis_points": 0,
                    "effective_from": period_start.isoformat(),
                },
            ),
            (
                "/api/v1/billing/agreements",
                {
                    "client_operation_id": str(uuid4()),
                    "account_id": account_id,
                    "child_id": child["id"],
                    "enrollment_id": enrollment["id"],
                    "rate_plan_version_id": version_id,
                    "billing_frequency": "monthly",
                    "effective_from": period_start.isoformat(),
                    "family_amount_minor_per_unit": 100,
                    "funding_amount_minor_per_unit": 0,
                    "reviewed": True,
                },
            ),
            (
                "/api/v1/billing/invoices/issue",
                {
                    "client_operation_id": str(uuid4()),
                    "account_id": account_id,
                    "issue_date": local_today.isoformat(),
                    "due_date": (local_today + timedelta(days=14)).isoformat(),
                    "service_period_start": period_start.isoformat(),
                    "service_period_end": period_end.isoformat(),
                    "agreements": [
                        {
                            "agreement_id": agreement_id,
                            "agreement_version_id": version_id,
                        }
                    ],
                },
            ),
            (
                "/api/v1/billing/payments",
                {
                    "client_operation_id": str(uuid4()),
                    "account_id": account_id,
                    "payer_guardian_id": guardian_id,
                    "amount_minor": 100,
                    "method": "e_transfer",
                    "received_at": datetime.now(UTC).isoformat(),
                    "external_reference": f"INVALID-TZ-{suffix}",
                },
            ),
            (
                "/api/v1/billing/allocations",
                {
                    "client_operation_id": str(uuid4()),
                    "payment_id": payment_id,
                    "invoice_id": invoice_id,
                    "amount_minor": 100,
                    "expected_payment_unapplied_minor": 100,
                    "expected_invoice_outstanding_minor": 100,
                },
            ),
            (
                "/api/v1/billing/credits",
                {
                    "client_operation_id": str(uuid4()),
                    "invoice_id": invoice_id,
                    "amount_minor": 100,
                    "expected_invoice_outstanding_minor": 100,
                    "reason_code": "invalid_timezone_gate",
                },
            ),
        )
        for path, body in blocked_writes:
            blocked = invalid_client.post(path, headers=headers, json=body)
            assert blocked.status_code == 503, (path, blocked.text)
            assert blocked.json()["detail"] == {"code": "billing_ledger_unavailable"}
    with billing_database.begin() as connection:
        connection.execute(
            text("UPDATE organizations SET timezone='America/Edmonton' WHERE id=:id"),
            {"id": organization_id},
        )

    _attest_all_sources(billing_database, organization_id, actor_user_id)
    billing_app = create_app(_runtime_settings(billing_organization_id=organization_id))
    with TestClient(billing_app) as client:
        frozen_source = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": family["version"],
                "name": "Should Not Change",
            },
        )
        assert frozen_source.status_code == 409, frozen_source.text
        capability = client.get("/api/v1/billing/capability", headers=headers)
        assert capability.status_code == 200, capability.text
        assert capability.json()["runtime_available"] is True
        assert capability.json()["writes_available"] is True
        account_payload = {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "payer_guardian_id": primary["id"],
        }
        account_receipt = _prepare_and_execute(
            client,
            headers,
            command_type="account_open",
            path="/api/v1/billing/accounts",
            payload=account_payload,
        )
        account_id = account_receipt["result_id"]
        detail = client.get(f"/api/v1/billing/accounts/{account_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        payer_version = detail.json()["account"]
        payer_payload = {
            "client_operation_id": str(uuid4()),
            "account_id": account_id,
            "payer_guardian_id": secondary["id"],
            "expected_latest_payer_version_id": payer_version["latest_payer_version_id"],
            "expected_latest_payer_version_number": payer_version["latest_payer_version_number"],
        }
        _prepare_and_execute(
            client,
            headers,
            command_type="account_payer_assign",
            path=f"/api/v1/billing/accounts/{account_id}/payer-assign",
            payload=payer_payload,
        )
        reassigned_detail = client.get(f"/api/v1/billing/accounts/{account_id}", headers=headers)
        assert reassigned_detail.status_code == 200, reassigned_detail.text
        reassigned_account = reassigned_detail.json()
        assert len(reassigned_account["payer_versions"]) == 2
        current_payer_version = reassigned_account["payer_versions"][-1]
        assert current_payer_version["payer_guardian_id"] == secondary["id"]
        rate_payload = {
            "client_operation_id": str(uuid4()),
            "code": "MONTHLY-CORE",
            "name": "Monthly Core Care",
            "program_type": "daycare",
            "charge_kind": "core_care",
            "facility_id": facility["id"],
            "program_id": program["id"],
            "billing_unit": "monthly_period",
            "unit_amount_minor": 10000,
            "tax_rate_basis_points": 0,
            "effective_from": period_start.isoformat(),
        }
        rate_receipt = _prepare_and_execute(
            client,
            headers,
            command_type="rate_version_publish",
            path="/api/v1/billing/rate-plans",
            payload=rate_payload,
        )
        rates = client.get("/api/v1/billing/rate-plans", headers=headers)
        assert rates.status_code == 200, rates.text
        rate = next(
            value for value in rates.json()["items"] if value["id"] == rate_receipt["result_id"]
        )
        agreement_payload = {
            "client_operation_id": str(uuid4()),
            "account_id": account_id,
            "child_id": child["id"],
            "enrollment_id": enrollment["id"],
            "rate_plan_version_id": rate["latest_version"]["id"],
            "billing_frequency": "monthly",
            "effective_from": period_start.isoformat(),
            "family_amount_minor_per_unit": 10000,
            "funding_amount_minor_per_unit": 0,
            "reviewed": True,
        }
        agreement_receipt = _prepare_and_execute(
            client,
            headers,
            command_type="agreement_establish",
            path="/api/v1/billing/agreements",
            payload=agreement_payload,
        )
        agreements = client.get("/api/v1/billing/agreements", headers=headers)
        assert agreements.status_code == 200, agreements.text
        agreement = next(
            value
            for value in agreements.json()["items"]
            if value["id"] == agreement_receipt["result_id"]
        )
        invoice_payload = {
            "client_operation_id": str(uuid4()),
            "account_id": account_id,
            "issue_date": local_today.isoformat(),
            "due_date": (local_today + timedelta(days=14)).isoformat(),
            "service_period_start": period_start.isoformat(),
            "service_period_end": period_end.isoformat(),
            "agreements": [
                {
                    "agreement_id": agreement["id"],
                    "agreement_version_id": agreement["latest_version"]["id"],
                }
            ],
        }
        invoice = _prepare_and_execute(
            client,
            headers,
            command_type="invoice_issue",
            path="/api/v1/billing/invoices/issue",
            payload=invoice_payload,
        )
        payment_payload = {
            "client_operation_id": str(uuid4()),
            "account_id": account_id,
            "payer_guardian_id": secondary["id"],
            "amount_minor": 10000,
            "method": "e_transfer",
            "received_at": datetime.now(UTC).isoformat(),
            "external_reference": f"PG0033-{suffix}-1",
        }
        payment = _prepare_and_execute(
            client,
            headers,
            command_type="payment_record",
            path="/api/v1/billing/payments",
            payload=payment_payload,
        )
        allocation_payload = {
            "client_operation_id": str(uuid4()),
            "payment_id": payment["result_id"],
            "invoice_id": invoice["result_id"],
            "amount_minor": 4000,
            "expected_payment_unapplied_minor": 10000,
            "expected_invoice_outstanding_minor": 10000,
        }
        allocation = _prepare_and_execute(
            client,
            headers,
            command_type="payment_allocate",
            path="/api/v1/billing/allocations",
            payload=allocation_payload,
        )
        credit_payload = {
            "client_operation_id": str(uuid4()),
            "invoice_id": invoice["result_id"],
            "amount_minor": 6000,
            "expected_invoice_outstanding_minor": 6000,
            "reason_code": "synthetic_test_adjustment",
        }
        credit = _prepare_and_execute(
            client,
            headers,
            command_type="credit_issue",
            path="/api/v1/billing/credits",
            payload=credit_payload,
        )
        document_path = f"/api/v1/billing/invoices/{invoice['result_id']}/document-preview"
        document_response = client.get(document_path, headers=headers)
        assert document_response.status_code == 200, document_response.text
        document = document_response.json()
        assert document["invoice_id"] == invoice["result_id"]
        assert document["invoice"]["status"] == "issued"
        assert document["invoice"]["invoice_number"].startswith("TEST-INV-")
        assert document["payer_snapshot"]["payer_version_id"] == current_payer_version["id"]
        assert document["settlement"] == {
            "currency": "CAD",
            "total_minor": 10000,
            "allocated_minor": 4000,
            "credits_minor": 6000,
            "outstanding_minor": 0,
        }
        assert document["allocations"][0]["id"] == allocation["result_id"]
        assert document["credits"][0]["id"] == credit["result_id"]
        assert len(document["canonical_sha256"]) == 64
        assert document_response.headers["cache-control"] == "private, no-store"

        workspace_response = client.get("/api/v1/billing/workspace", headers=headers)
        assert workspace_response.status_code == 200, workspace_response.text
        workspace = workspace_response.json()
        assert workspace["complete"] is True
        assert workspace["overview"]["outstanding_minor"] == 0
        assert workspace["overview"]["unapplied_payments_minor"] == 6000
        assert workspace["allocations"]["items"][0]["id"] == allocation["result_id"]
        assert workspace["allocations"]["items"][0]["payment_id"] == payment["result_id"]
        assert workspace["allocations"]["items"][0]["invoice_id"] == invoice["result_id"]
        assert workspace["credits"]["items"][0]["id"] == credit["result_id"]
        assert workspace["credits"]["items"][0]["invoice_id"] == invoice["result_id"]
        assert workspace["payer_versions"]["total"] == 2
        assert workspace["payer_versions"]["items"][-1]["id"] == current_payer_version["id"]
        issued_invoice = workspace["invoices"]["items"][0]
        assert issued_invoice["payer_guardian_id"] == secondary["id"]
        assert issued_invoice["billing_account_payer_version_id"] == current_payer_version["id"]
        assert len(workspace["allocations"]["items"][0]["request_hash"]) == 64
        assert len(workspace["credits"]["items"][0]["request_hash"]) == 64

        second_payment_payload = {
            **payment_payload,
            "client_operation_id": str(uuid4()),
            "amount_minor": 100,
            "external_reference": f"PG0033-{suffix}-2",
        }
        _prepare_and_execute(
            client,
            headers,
            command_type="payment_record",
            path="/api/v1/billing/payments",
            payload=second_payment_payload,
        )
        first_page_response = client.get("/api/v1/billing/workspace?page_size=1", headers=headers)
        assert first_page_response.status_code == 200, first_page_response.text
        first_page = first_page_response.json()
        assert first_page["complete"] is False
        assert first_page["paging"]["payments"]["has_more"] is True
        token = first_page["paging"]["snapshot_token"]
        second_page_response = client.get(
            "/api/v1/billing/workspace",
            headers=headers,
            params={
                "page_size": 1,
                "payments_offset": 1,
                "snapshot_token": token,
            },
        )
        assert second_page_response.status_code == 200, second_page_response.text
        second_page = second_page_response.json()
        assert second_page["paging"]["snapshot_token"] == token
        assert second_page["paging"]["payments"]["offset"] == 1
        assert second_page["paging"]["payments"]["returned"] == 1
        payer_page = client.get(
            "/api/v1/billing/workspace",
            headers=headers,
            params={
                "page_size": 1,
                "payer_versions_offset": 1,
                "snapshot_token": token,
            },
        )
        assert payer_page.status_code == 200, payer_page.text
        assert payer_page.json()["paging"]["payer_versions"]["offset"] == 1
        assert payer_page.json()["payer_versions"]["items"][0]["version_number"] == 2

        third_payment_payload = {
            **payment_payload,
            "client_operation_id": str(uuid4()),
            "amount_minor": 100,
            "external_reference": f"PG0033-{suffix}-3",
        }
        _prepare_and_execute(
            client,
            headers,
            command_type="payment_record",
            path="/api/v1/billing/payments",
            payload=third_payment_payload,
        )
        stale_page = client.get(
            "/api/v1/billing/workspace",
            headers=headers,
            params={"page_size": 1, "snapshot_token": token},
        )
        assert stale_page.status_code == 409, stale_page.text
        assert stale_page.json()["detail"]["code"] == "billing_workspace_snapshot_advanced"

        allocations = client.get(
            "/api/v1/billing/allocations",
            headers=headers,
            params={"account_id": account_id, "limit": 1},
        )
        assert allocations.status_code == 200, allocations.text
        assert allocations.json()["items"][0]["id"] == allocation["result_id"]
        credits = client.get(
            "/api/v1/billing/credits",
            headers=headers,
            params={"invoice_id": invoice["result_id"], "limit": 1},
        )
        assert credits.status_code == 200, credits.text
        assert credits.json()["items"][0]["id"] == credit["result_id"]

        absent_payload = {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "payer_guardian_id": primary["id"],
        }
        absent_preparation = _post(
            client,
            "/api/v1/billing/commands/prepare",
            headers,
            {"command_type": "account_open", "request_payload": absent_payload},
        )
        claim_path = (
            f"/api/v1/billing/commands/{absent_payload['client_operation_id']}/finalize-absence"
        )
        claim_body = {
            "expected_request_hash": absent_preparation["request_hash"],
            "reason_code": "operator_confirmed_not_committed",
        }
        absence_claim = _post(client, claim_path, headers, claim_body)
        assert absence_claim["exact_retry"] is False
        absence_retry = _post(client, claim_path, headers, claim_body)
        assert absence_retry == {**absence_claim, "exact_retry": True}

        command_status = client.get(
            f"/api/v1/billing/commands/{absent_payload['client_operation_id']}",
            headers=headers,
            params={"request_hash": absent_preparation["request_hash"]},
        )
        assert command_status.status_code == 404, command_status.text
        assert command_status.json()["detail"]["code"] == "billing_operation_finalized_absent"
        execute_after_claim = client.post(
            "/api/v1/billing/accounts", headers=headers, json=absent_payload
        )
        assert execute_after_claim.status_code == 409, execute_after_claim.text
        assert execute_after_claim.json()["detail"]["code"] == "billing_operation_finalized_absent"


def test_private_manual_mode_requires_owner_activation_and_uses_real_mutable_sources(
    billing_database,
) -> None:
    initial_app = create_app(_runtime_settings())
    suffix = uuid4().hex[:8]

    def register_tenant(
        client: TestClient,
        *,
        tenant: str,
    ) -> tuple[dict, dict[str, str], UUID, UUID, dict, dict]:
        auth = _post(
            client,
            "/api/v1/auth/register",
            {},
            {
                "email": f"manual-{tenant}-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Manual",
                "last_name": tenant.title(),
                "organization_name": f"Manual {tenant.title()} {suffix}",
            },
        )
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        family = _post(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": f"Real {tenant.title()} Family",
                "primary_guardian": {
                    "first_name": "Real",
                    "last_name": f"{tenant.title()} Payer",
                    "relationship": "Parent",
                    "email": f"real-{tenant}-{suffix}@example.test",
                    "cell_phone": "780-555-0123",
                },
            },
        )
        primary = next(value for value in family["guardians"] if value["is_primary"])
        return (
            auth,
            headers,
            UUID(auth["user"]["organization_id"]),
            UUID(auth["user"]["id"]),
            family,
            primary,
        )

    with TestClient(initial_app) as client:
        (
            _tenant_a_auth,
            tenant_a_headers,
            tenant_a_id,
            tenant_a_owner_id,
            tenant_a_family,
            tenant_a_primary,
        ) = register_tenant(client, tenant="alpha")
        (
            _tenant_b_auth,
            tenant_b_headers,
            tenant_b_id,
            tenant_b_owner_id,
            tenant_b_family,
            _tenant_b_primary,
        ) = register_tenant(client, tenant="beta")
        tenant_a_facility = _post(
            client,
            "/api/v1/facilities",
            tenant_a_headers,
            {"name": "Real Manual Centre", "licensed_capacity": 40, "status": "active"},
        )
        tenant_a_program = _post(
            client,
            "/api/v1/programs",
            tenant_a_headers,
            {
                "facility_id": tenant_a_facility["id"],
                "name": "Real Manual Daycare",
                "program_type": "daycare",
                "capacity": 40,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        tenant_a_room = _post(
            client,
            "/api/v1/rooms",
            tenant_a_headers,
            {
                "facility_id": tenant_a_facility["id"],
                "program_id": tenant_a_program["id"],
                "name": "Real Manual Room",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        tenant_a_child = _post(
            client,
            "/api/v1/children",
            tenant_a_headers,
            {
                "client_operation_id": str(uuid4()),
                "family_id": tenant_a_family["id"],
                "first_name": "Real",
                "last_name": "Manual Child",
                "date_of_birth": "2023-01-01",
            },
        )
        local_today = datetime.now(ZoneInfo("America/Edmonton")).date()
        period_start = local_today.replace(day=1)
        period_end = local_today.replace(day=monthrange(local_today.year, local_today.month)[1])
        tenant_a_enrollment = _post(
            client,
            f"/api/v1/children/{tenant_a_child['id']}/enrollments",
            tenant_a_headers,
            {
                "client_operation_id": str(uuid4()),
                "facility_id": tenant_a_facility["id"],
                "start_date": period_start.isoformat(),
            },
        )
        _post(
            client,
            f"/api/v1/enrollments/{tenant_a_enrollment['id']}/placement-approval",
            tenant_a_headers,
            {
                "client_operation_id": str(uuid4()),
                "expected_version": tenant_a_enrollment["version"],
                "room_id": tenant_a_room["id"],
                "effective_date": local_today.isoformat(),
            },
        )

    # PostgreSQL itself rejects an actor/context mismatch before the immutable
    # activation boundary can be created.
    with (
        pytest.raises(DBAPIError, match="manual billing activation boundary is invalid"),
        billing_database.begin() as connection,
    ):
        connection.execute(
            text("SELECT set_config('app.current_organization_id',:value,true)"),
            {"value": str(tenant_a_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id',:value,true)"),
            {"value": str(uuid4())},
        )
        membership_id = connection.scalar(
            text(
                "SELECT id FROM organization_memberships "
                "WHERE organization_id=:org AND user_id=:user"
            ),
            {"org": tenant_a_id, "user": tenant_a_owner_id},
        )
        connection.execute(
            text(
                "INSERT INTO billing_manual_activations "
                "(id,organization_id,activated_by_user_id,activated_by_membership_id,"
                "activation_policy_version,review_attestation,activated_at) VALUES "
                "(:id,:org,:user,:membership,'private_local_manual_billing_v1',"
                ":attestation,now())"
            ),
            {
                "id": uuid4(),
                "org": tenant_a_id,
                "user": tenant_a_owner_id,
                "membership": membership_id,
                "attestation": MANUAL_BILLING_REVIEW_ATTESTATION,
            },
        )

    # A direct SQL effect for an unactivated organization still reaches the
    # frozen 0033 validator and is rejected for missing source authorization.
    direct_operation_id = uuid4()
    direct_request_hash = "a" * 64
    with (
        pytest.raises(DBAPIError, match="organization is not synthetic-attested"),
        billing_database.begin() as connection,
    ):
        connection.execute(
            text("SELECT set_config('app.current_organization_id',:value,true)"),
            {"value": str(tenant_b_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id',:value,true)"),
            {"value": str(tenant_b_owner_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_billing_operation_id',:value,true)"),
            {"value": str(direct_operation_id)},
        )
        connection.execute(
            text(
                "INSERT INTO billing_command_preparations "
                "(id,organization_id,actor_user_id,client_operation_id,command_type,"
                "target_scope,request_hash,prepared_at) VALUES "
                "(:id,:org,:user,:operation,'account_open',:scope,:hash,now())"
            ),
            {
                "id": uuid4(),
                "org": tenant_b_id,
                "user": tenant_b_owner_id,
                "operation": direct_operation_id,
                "scope": tenant_b_family["id"],
                "hash": direct_request_hash,
            },
        )
        connection.exec_driver_sql(
            "CREATE TEMP TABLE pg_temp.billing_accounts "
            "(organization_id uuid,client_operation_id uuid,request_hash text,"
            "family_id uuid,payer_guardian_id uuid)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER manual_unactivated_probe AFTER INSERT ON "
            "pg_temp.billing_accounts FOR EACH ROW EXECUTE FUNCTION "
            "public.caresync_0036_bundle_validate()"
        )
        connection.execute(
            text(
                "INSERT INTO pg_temp.billing_accounts VALUES "
                "(:org,:operation,:hash,:family,:guardian)"
            ),
            {
                "org": tenant_b_id,
                "operation": direct_operation_id,
                "hash": direct_request_hash,
                "family": tenant_b_family["id"],
                "guardian": uuid4(),
            },
        )

    manual_app = create_app(
        _runtime_settings(
            manual_billing_organization_ids=[tenant_a_id, tenant_b_id],
        )
    )
    with TestClient(manual_app) as client:
        capability = client.get("/api/v1/billing/capability", headers=tenant_a_headers)
        assert capability.status_code == 200, capability.text
        assert capability.json() == {
            **capability.json(),
            "billing_mode": "manual",
            "sandbox": False,
            "provenance_label": PRIVATE_MANUAL_BILLING_LABEL,
            "writes_available": False,
            "manual_activation_required": True,
            "manual_activated": False,
            "processor_enabled": False,
            "money_movement_enabled": False,
            "automatic_issue_enabled": False,
            "tax_advice_enabled": False,
        }
        source_options = client.get("/api/v1/billing/source-options", headers=tenant_a_headers)
        assert source_options.status_code == 200, source_options.text
        assert source_options.json()["total"] == 1
        assert source_options.json()["items"][0]["id"] == tenant_a_family["id"]
        assert source_options.json()["items"][0]["guardians"][0]["id"] == tenant_a_primary["id"]
        assert all(
            item["organization_id"] == str(tenant_a_id) for item in source_options.json()["items"]
        )

        blocked_payload = {
            "client_operation_id": str(uuid4()),
            "family_id": tenant_a_family["id"],
            "payer_guardian_id": tenant_a_primary["id"],
        }
        blocked = client.post(
            "/api/v1/billing/commands/prepare",
            headers=tenant_a_headers,
            json={"command_type": "account_open", "request_payload": blocked_payload},
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == "billing_manual_activation_required"

        wrong_attestation = client.post(
            "/api/v1/billing/manual-activation",
            headers=tenant_a_headers,
            json={
                "activation_policy_version": "private_local_manual_billing_v1",
                "review_attestation": "I did not review it",
            },
        )
        assert wrong_attestation.status_code == 422, wrong_attestation.text
        activation_payload = {
            "activation_policy_version": "private_local_manual_billing_v1",
            "review_attestation": MANUAL_BILLING_REVIEW_ATTESTATION,
        }
        activation = client.post(
            "/api/v1/billing/manual-activation",
            headers=tenant_a_headers,
            json=activation_payload,
        )
        assert activation.status_code == 201, activation.text
        assert activation.json() == {
            **activation.json(),
            "billing_mode": "manual",
            "server_attested": True,
            "organization_allowlisted": True,
            "activated": True,
            "immutable": True,
            "processor_enabled": False,
            "money_movement_enabled": False,
            "automatic_issue_enabled": False,
            "delivery_enabled": False,
            "tax_advice_enabled": False,
        }
        activation_retry = client.post(
            "/api/v1/billing/manual-activation",
            headers=tenant_a_headers,
            json=activation_payload,
        )
        assert activation_retry.status_code == 201, activation_retry.text
        assert activation_retry.json() == activation.json()

        activated_capability = client.get("/api/v1/billing/capability", headers=tenant_a_headers)
        assert activated_capability.status_code == 200, activated_capability.text
        assert activated_capability.json()["writes_available"] is True
        assert activated_capability.json()["manual_activation_required"] is False
        assert activated_capability.json()["manual_activated"] is True

        with billing_database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE organization_memberships SET role_id=("
                    "SELECT id FROM roles WHERE organization_id=:org "
                    "AND key='administrator') WHERE organization_id=:org AND user_id=:user"
                ),
                {"org": tenant_a_id, "user": tenant_a_owner_id},
            )
        administrator_activation = client.post(
            "/api/v1/billing/manual-activation",
            headers=tenant_a_headers,
            json=activation_payload,
        )
        assert administrator_activation.status_code == 403, administrator_activation.text
        assert administrator_activation.json()["detail"]["code"] == "billing_owner_required"
        administrator_capability = client.get(
            "/api/v1/billing/capability", headers=tenant_a_headers
        )
        assert administrator_capability.status_code == 200, administrator_capability.text
        assert administrator_capability.json()["writes_available"] is True
        assert administrator_capability.json()["manual_activated"] is True

        account_payload = {
            "client_operation_id": str(uuid4()),
            "family_id": tenant_a_family["id"],
            "payer_guardian_id": tenant_a_primary["id"],
        }
        receipt = _prepare_and_execute(
            client,
            tenant_a_headers,
            command_type="account_open",
            path="/api/v1/billing/accounts",
            payload=account_payload,
        )
        assert receipt["billing_mode"] == "manual"
        assert receipt["sandbox"] is False
        assert receipt["provenance_label"] == PRIVATE_MANUAL_BILLING_LABEL

        rate_receipt = _prepare_and_execute(
            client,
            tenant_a_headers,
            command_type="rate_version_publish",
            path="/api/v1/billing/rate-plans",
            payload={
                "client_operation_id": str(uuid4()),
                "code": "MANUAL-MONTHLY-CORE",
                "name": "Manual Monthly Core Care",
                "program_type": "daycare",
                "charge_kind": "core_care",
                "facility_id": tenant_a_facility["id"],
                "program_id": tenant_a_program["id"],
                "billing_unit": "monthly_period",
                "unit_amount_minor": 12500,
                "tax_rate_basis_points": 0,
                "effective_from": period_start.isoformat(),
            },
        )
        rate_response = client.get("/api/v1/billing/rate-plans", headers=tenant_a_headers)
        assert rate_response.status_code == 200, rate_response.text
        manual_rate = next(
            value
            for value in rate_response.json()["items"]
            if value["id"] == rate_receipt["result_id"]
        )
        agreement_receipt = _prepare_and_execute(
            client,
            tenant_a_headers,
            command_type="agreement_establish",
            path="/api/v1/billing/agreements",
            payload={
                "client_operation_id": str(uuid4()),
                "account_id": receipt["result_id"],
                "child_id": tenant_a_child["id"],
                "enrollment_id": tenant_a_enrollment["id"],
                "rate_plan_version_id": manual_rate["latest_version"]["id"],
                "billing_frequency": "monthly",
                "effective_from": period_start.isoformat(),
                "family_amount_minor_per_unit": 12500,
                "funding_amount_minor_per_unit": 0,
                "reviewed": True,
            },
        )
        agreement_response = client.get("/api/v1/billing/agreements", headers=tenant_a_headers)
        assert agreement_response.status_code == 200, agreement_response.text
        manual_agreement = next(
            value
            for value in agreement_response.json()["items"]
            if value["id"] == agreement_receipt["result_id"]
        )
        invoice_receipt = _prepare_and_execute(
            client,
            tenant_a_headers,
            command_type="invoice_issue",
            path="/api/v1/billing/invoices/issue",
            payload={
                "client_operation_id": str(uuid4()),
                "account_id": receipt["result_id"],
                "issue_date": local_today.isoformat(),
                "due_date": (local_today + timedelta(days=14)).isoformat(),
                "service_period_start": period_start.isoformat(),
                "service_period_end": period_end.isoformat(),
                "agreements": [
                    {
                        "agreement_id": manual_agreement["id"],
                        "agreement_version_id": manual_agreement["latest_version"]["id"],
                    }
                ],
            },
        )
        invoice_response = client.get("/api/v1/billing/invoices", headers=tenant_a_headers)
        assert invoice_response.status_code == 200, invoice_response.text
        manual_invoice = next(
            value
            for value in invoice_response.json()["items"]
            if value["id"] == invoice_receipt["result_id"]
        )
        assert manual_invoice["invoice_number"].startswith("MANUAL-INV-")
        assert not manual_invoice["invoice_number"].startswith("TEST-INV-")
        assert manual_invoice["billing_mode"] == "manual"
        assert manual_invoice["provenance_label"] == PRIVATE_MANUAL_BILLING_LABEL

        renamed = client.patch(
            f"/api/v1/families/{tenant_a_family['id']}",
            headers=tenant_a_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": tenant_a_family["version"],
                "name": "Real Alpha Family Updated",
            },
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Real Alpha Family Updated"

        tenant_b_capability = client.get("/api/v1/billing/capability", headers=tenant_b_headers)
        assert tenant_b_capability.status_code == 200, tenant_b_capability.text
        assert tenant_b_capability.json()["writes_available"] is False
        assert tenant_b_capability.json()["manual_activation_required"] is True
        tenant_b_sources = client.get("/api/v1/billing/source-options", headers=tenant_b_headers)
        assert tenant_b_sources.status_code == 200, tenant_b_sources.text
        assert tenant_b_sources.json()["total"] == 1
        assert tenant_b_sources.json()["items"][0]["id"] == tenant_b_family["id"]

    with billing_database.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM billing_manual_activations WHERE organization_id=:org"),
                {"org": tenant_a_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM billing_sandbox_source_attestations "
                    "WHERE organization_id=:org"
                ),
                {"org": tenant_a_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM billing_source_authorizations_0036 "
                    "WHERE organization_id=:org"
                ),
                {"org": tenant_a_id},
            )
            >= 3
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM billing_source_authorizations_0036 "
                    "WHERE organization_id=:org"
                ),
                {"org": tenant_b_id},
            )
            == 0
        )

    with (
        pytest.raises(DBAPIError, match="manual billing activation is immutable"),
        billing_database.begin() as connection,
    ):
        connection.execute(
            text(
                "UPDATE billing_manual_activations SET activated_at=activated_at "
                "WHERE organization_id=:org"
            ),
            {"org": tenant_a_id},
        )


def test_readonly_batch_planner_preserves_postgres_rls_and_writes_no_billing_rows(
    billing_database,
) -> None:
    """0040 emits setup intents from tenant-bound snapshots without preparing them."""

    initial_app = create_app(_runtime_settings())
    tenants: list[dict[str, object]] = []
    with TestClient(initial_app) as client:
        for label in ("North", "South"):
            auth = _post(
                client,
                "/api/v1/auth/register",
                {},
                {
                    "email": f"batch-{label.casefold()}-{uuid4()}@example.test",
                    "password": "secure-password-123",
                    "first_name": label,
                    "last_name": "Owner",
                    "organization_name": f"{label} Batch Centre",
                },
            )
            headers = {"Authorization": f"Bearer {auth['access_token']}"}
            family = _post(
                client,
                "/api/v1/families",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "name": f"{label} Private Family",
                    "primary_guardian": {
                        "first_name": label,
                        "last_name": "Guardian",
                        "relationship": "Parent",
                        "email": f"{label.casefold()}-guardian@example.test",
                        "cell_phone": "780-555-0101",
                    },
                },
            )
            _post(
                client,
                "/api/v1/children",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": family["id"],
                    "first_name": label,
                    "last_name": "Child",
                    "date_of_birth": "2023-01-01",
                },
            )
            tenants.append(
                {
                    "auth": auth,
                    "headers": headers,
                    "family": family,
                    "organization_id": UUID(auth["user"]["organization_id"]),
                    "actor_user_id": UUID(auth["user"]["id"]),
                }
            )
    for tenant in tenants:
        _attest_all_sources(
            billing_database,
            tenant["organization_id"],
            tenant["actor_user_id"],
        )

    settings = _runtime_settings(
        billing_organization_id=tenants[0]["organization_id"]
    ).model_copy(
        update={
            "billing_sandbox_organization_ids": [
                tenant["organization_id"] for tenant in tenants
            ]
        }
    )

    def billing_counts() -> dict[str, int]:
        with billing_database.connect() as connection:
            names = list(
                connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname='public' AND tablename LIKE 'billing_%' "
                        "ORDER BY tablename"
                    )
                ).scalars()
            )
            return {
                name: int(
                    connection.scalar(text(f'SELECT count(*) FROM "{name}"')) or 0
                )
                for name in names
            }

    before = billing_counts()
    application = create_app(settings)
    with TestClient(application) as client:
        plans = []
        for tenant in tenants:
            response = client.get(
                "/api/v1/billing/readiness/batch-plan",
                headers=tenant["headers"],
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["counts"]["account_payer"] == 1
            assert payload["page"]["total"] == 1
            assert payload["items"][0]["family_id"] == tenant["family"]["id"]
            assert payload["items"][0]["family_name"] == tenant["family"]["name"]
            assert all(
                other["family"]["name"] not in str(payload)
                for other in tenants
                if other is not tenant
            )
            plans.append(payload)
        first_group = plans[0]["items"][0]
        preview = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=tenants[0]["headers"],
            json={
                "snapshot_token": plans[0]["snapshot_token"],
                "wave": "account_payer",
                "selections": [
                    {
                        "group_id": first_group["group_id"],
                        "client_operation_id": str(uuid4()),
                        "payer_guardian_id": first_group["payer_options"][0][
                            "guardian_id"
                        ],
                    }
                ],
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["intents"][0]["command_type"] == "account_open"
        cross_tenant = client.post(
            "/api/v1/billing/readiness/batch-plan/preview",
            headers=tenants[1]["headers"],
            json={
                "snapshot_token": plans[0]["snapshot_token"],
                "wave": "account_payer",
                "selections": [
                    {
                        "group_id": first_group["group_id"],
                        "client_operation_id": str(uuid4()),
                        "payer_guardian_id": first_group["payer_options"][0][
                            "guardian_id"
                        ],
                    }
                ],
            },
        )
        assert cross_tenant.status_code == 409, cross_tenant.text
        assert cross_tenant.json()["detail"]["code"] == (
            "billing_readiness_batch_snapshot_advanced"
        )
    assert billing_counts() == before
