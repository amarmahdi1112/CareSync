"""Portable default coverage for the synthetic-only 0033 billing ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from alembic import command
from app.basic.billing_schemas import (
    BillingCapabilityResponse,
    BillingInvoiceDocumentPreviewResponse,
)
from app.basic.models import BasicBase
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _settings(
    database_path: Path,
    *,
    billing_mode: str = "disabled",
    organization_id: UUID | None = None,
    organization_ids: list[UUID] | None = None,
) -> Settings:
    values = {
        "_env_file": None,
        "environment": "test",
        "database_type": "sqlite",
        "database_path": database_path,
        "database_name": "caresync",
        "database_read_only": False,
        "enable_advanced_routes": False,
        "billing_mode": billing_mode,
        "jwt_secret": "portable-billing-test-secret-with-at-least-thirty-two-bytes",
    }
    allowlisted_organizations = organization_ids or (
        [organization_id] if organization_id is not None else []
    )
    if allowlisted_organizations:
        values.update(
            {
                "billing_sandbox_target_attestation": ("DISPOSABLE_CARESYNC_BILLING_SANDBOX"),
                "billing_sandbox_organization_ids": allowlisted_organizations,
            }
        )
    return Settings(**values)


def test_source_attestation_seeder_locks_authority_and_sources_before_reading() -> None:
    source = (BACKEND_ROOT / "scripts" / "seed_billing_sandbox_sources.py").read_text(
        encoding="utf-8"
    )
    lock_position = source.index("LOCK TABLE public.organizations")
    first_eligibility_read = source.index("organization = session.scalar")
    assert lock_position < first_eligibility_read
    for relation in (
        "organization_memberships",
        "roles",
        "families",
        "guardians",
        "children",
        "enrollments",
        "facilities",
        "facility_programs",
    ):
        assert f"public.{relation}" in source[lock_position:first_eligibility_read]
    assert "IN SHARE ROW EXCLUSIVE MODE" in source[lock_position:first_eligibility_read]


def test_orm_created_sqlite_without_alembic_catalog_has_no_billing_capability(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "caresync.db"
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        BasicBase.metadata.create_all(engine)
    finally:
        engine.dispose()

    database = Database(_settings(database_path))
    try:
        assert database.has_billing_ledger() is False
    finally:
        database.dispose()

    # Once a database explicitly claims 0033, the same incomplete catalog is
    # rejected rather than silently downgraded to unavailable.
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES ('0033_billing_ledger')")
    claimed = Database(_settings(database_path))
    try:
        with pytest.raises(RuntimeError, match="0033 billing ledger"):
            claimed.has_billing_ledger()
    finally:
        claimed.dispose()


def _migrate(tmp_path: Path, monkeypatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_path


def _post(client: TestClient, path: str, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _register(client: TestClient, suffix: str) -> tuple[dict[str, str], dict]:
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
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth


def _create_family(client: TestClient, headers: dict[str, str], suffix: str) -> dict:
    return _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": f"Synthetic Family {suffix}",
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": "Payer",
                "relationship": "Parent",
                "email": f"primary-{suffix}@example.test",
                "cell_phone": "780-555-0101",
            },
        },
    )


def _sqlite_uuid(value: str | UUID) -> str:
    return UUID(str(value)).hex


def _insert_attestations(
    database_path: Path,
    *,
    organization_id: str,
    actor_user_id: str,
    sources: list[tuple[str, str]],
) -> None:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database_path) as connection:
        for source_type, source_id in sources:
            connection.execute(
                "INSERT INTO billing_sandbox_source_attestations "
                "(id,organization_id,source_type,source_id,marker,reason_code,"
                "attested_by_user_id,attested_at) VALUES "
                "(?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    _sqlite_uuid(organization_id),
                    source_type,
                    _sqlite_uuid(source_id),
                    "TEST_SYNTHETIC_ONLY",
                    "disposable_test_fixture",
                    _sqlite_uuid(actor_user_id),
                    now,
                ),
            )


def _insert_invoice_document_fixture(
    database_path: Path,
    *,
    organization_id: str,
    actor_user_id: str,
    family: dict,
) -> dict[str, str]:
    guardian = family["guardians"][0]
    account_id = str(uuid4())
    payer_version_id = str(uuid4())
    invoice_id = str(uuid4())
    payment_id = str(uuid4())
    allocation_id = str(uuid4())
    credit_id = str(uuid4())
    account_operation_id = str(uuid4())
    invoice_operation_id = str(uuid4())
    payment_operation_id = str(uuid4())
    allocation_operation_id = str(uuid4())
    credit_operation_id = str(uuid4())
    prepared_at = "2026-07-22 12:00:00.000000"
    issued_at = "2026-07-22 12:10:00.000000"
    allocated_at = "2026-07-22 12:20:00.000000"
    credited_at = "2026-07-22 12:30:00.000000"
    organization_key = _sqlite_uuid(organization_id)
    actor_key = _sqlite_uuid(actor_user_id)
    family_key = _sqlite_uuid(family["id"])
    guardian_key = _sqlite_uuid(guardian["id"])

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "UPDATE organizations SET legal_name=?,email=?,phone=? WHERE id=?",
            (
                "Synthetic Child Care Society",
                "billing@example.test",
                "780-555-0199",
                organization_key,
            ),
        )

    _insert_attestations(
        database_path,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        sources=[
            ("organization", organization_id),
            ("family", family["id"]),
            ("guardian", guardian["id"]),
        ],
    )

    preparations = (
        (
            account_operation_id,
            "account_open",
            family["id"],
            "a" * 64,
        ),
        (
            invoice_operation_id,
            "invoice_issue",
            account_id,
            "b" * 64,
        ),
        (
            payment_operation_id,
            "payment_record",
            account_id,
            "c" * 64,
        ),
        (
            allocation_operation_id,
            "payment_allocate",
            payment_id,
            "d" * 64,
        ),
        (
            credit_operation_id,
            "credit_issue",
            invoice_id,
            "e" * 64,
        ),
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for operation_id, command_type, target_scope, request_hash in preparations:
            connection.execute(
                "INSERT INTO billing_command_preparations "
                "(id,organization_id,actor_user_id,client_operation_id,command_type,"
                "target_scope,request_hash,prepared_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    organization_key,
                    actor_key,
                    _sqlite_uuid(operation_id),
                    command_type,
                    target_scope,
                    request_hash,
                    prepared_at,
                ),
            )
        connection.execute(
            "INSERT INTO billing_accounts "
            "(id,organization_id,family_id,payer_guardian_id,account_number,currency,status,"
            "opened_by_user_id,opened_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,'CAD','open',?,?,?,?)",
            (
                _sqlite_uuid(account_id),
                organization_key,
                family_key,
                guardian_key,
                "TEST-ACCOUNT-0001",
                actor_key,
                prepared_at,
                _sqlite_uuid(account_operation_id),
                "a" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_account_payer_versions "
            "(id,organization_id,billing_account_id,family_id,payer_guardian_id,"
            "version_number,assigned_by_user_id,assigned_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,1,?,?,?,?)",
            (
                _sqlite_uuid(payer_version_id),
                organization_key,
                _sqlite_uuid(account_id),
                family_key,
                guardian_key,
                actor_key,
                prepared_at,
                _sqlite_uuid(account_operation_id),
                "a" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_invoices "
            "(id,organization_id,billing_account_id,family_id,"
            "billing_account_payer_version_id,payer_guardian_id,invoice_number,status,"
            "currency,issue_date,due_date,service_period_start,service_period_end,"
            "family_name_snapshot,payer_name_snapshot,payer_email_snapshot,"
            "payer_address_snapshot,gross_subtotal_minor,funding_minor,subtotal_minor,"
            "tax_minor,total_minor,issued_by_user_id,issued_at,client_operation_id,"
            "request_hash) VALUES (?,?,?,?,?,?,'TEST-INV-0001','issued','CAD',"
            "'2026-07-22','2026-08-05','2026-08-01','2026-08-31',?,?,?,?,"
            "10000,0,10000,0,10000,?,?,?,?)",
            (
                _sqlite_uuid(invoice_id),
                organization_key,
                _sqlite_uuid(account_id),
                family_key,
                _sqlite_uuid(payer_version_id),
                guardian_key,
                family["name"],
                f"{guardian['first_name']} {guardian['last_name']}",
                guardian["email"],
                None,
                actor_key,
                issued_at,
                _sqlite_uuid(invoice_operation_id),
                "b" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_payments "
            "(id,organization_id,billing_account_id,family_id,payer_guardian_id,status,"
            "method,currency,amount_minor,external_reference,payer_name_snapshot,"
            "payer_email_snapshot,operator_confirmation_note,memo,received_at,"
            "recorded_by_user_id,recorded_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,'settled','e_transfer','CAD',4000,'TEST-TRANSFER-1',"
            "?,?,NULL,NULL,?,?,?,?,?)",
            (
                _sqlite_uuid(payment_id),
                organization_key,
                _sqlite_uuid(account_id),
                family_key,
                guardian_key,
                f"{guardian['first_name']} {guardian['last_name']}",
                guardian["email"],
                allocated_at,
                actor_key,
                allocated_at,
                _sqlite_uuid(payment_operation_id),
                "c" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_allocations "
            "(id,organization_id,billing_account_id,payment_id,invoice_id,amount_minor,"
            "allocated_by_user_id,allocated_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,?,2000,?,?,?,?)",
            (
                _sqlite_uuid(allocation_id),
                organization_key,
                _sqlite_uuid(account_id),
                _sqlite_uuid(payment_id),
                _sqlite_uuid(invoice_id),
                actor_key,
                allocated_at,
                _sqlite_uuid(allocation_operation_id),
                "d" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO billing_credits "
            "(id,organization_id,billing_account_id,invoice_id,status,currency,amount_minor,"
            "reason_code,note,issued_by_user_id,issued_at,client_operation_id,request_hash) "
            "VALUES (?,?,?,?,'issued','CAD',1000,'service_adjustment',?,?,?, ?,?)",
            (
                _sqlite_uuid(credit_id),
                organization_key,
                _sqlite_uuid(account_id),
                _sqlite_uuid(invoice_id),
                "Synthetic adjustment",
                actor_key,
                credited_at,
                _sqlite_uuid(credit_operation_id),
                "e" * 64,
            ),
        )
    return {
        "account_id": account_id,
        "payer_version_id": payer_version_id,
        "invoice_id": invoice_id,
        "payment_id": payment_id,
        "allocation_id": allocation_id,
        "credit_id": credit_id,
    }


def _billing_table_counts(database_path: Path) -> tuple[int, ...]:
    relations = (
        "billing_invoices",
        "billing_invoice_lines",
        "billing_payments",
        "billing_allocations",
        "billing_credits",
        "billing_command_preparations",
        "audit_events",
        "realtime_events",
    )
    with sqlite3.connect(database_path) as connection:
        return tuple(
            int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
            for relation in relations
        )


def _document_preview_fixture(
    tmp_path: Path,
    monkeypatch,
) -> tuple[Path, Settings, dict[str, str], dict[str, str], dict, dict[str, str]]:
    database_path = _migrate(tmp_path, monkeypatch)
    suffix = uuid4().hex[:8]
    with TestClient(create_app(_settings(database_path))) as client:
        owner_headers, owner = _register(client, f"owner-{suffix}")
        foreign_headers, foreign = _register(client, f"foreign-{suffix}")
        family = _create_family(client, owner_headers, suffix)
    document_ids = _insert_invoice_document_fixture(
        database_path,
        organization_id=owner["user"]["organization_id"],
        actor_user_id=owner["user"]["id"],
        family=family,
    )
    settings = _settings(
        database_path,
        billing_mode="shadow",
        organization_ids=[
            UUID(owner["user"]["organization_id"]),
            UUID(foreign["user"]["organization_id"]),
        ],
    )
    return (
        database_path,
        settings,
        owner_headers,
        foreign_headers,
        family,
        document_ids,
    )


def test_invoice_document_preview_is_authenticated_tenant_scoped_and_private(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        _database_path,
        settings,
        owner_headers,
        foreign_headers,
        _family,
        document_ids,
    ) = _document_preview_fixture(tmp_path, monkeypatch)
    path = f"/api/v1/billing/invoices/{document_ids['invoice_id']}/document-preview"
    with TestClient(create_app(settings)) as client:
        unauthenticated = client.get(path)
        assert unauthenticated.status_code == 401, unauthenticated.text

        foreign = client.get(path, headers=foreign_headers)
        assert foreign.status_code == 404, foreign.text
        assert foreign.json()["detail"] == {"code": "billing_invoice_not_found"}

        missing = client.get(
            f"/api/v1/billing/invoices/{uuid4()}/document-preview",
            headers=owner_headers,
        )
        assert missing.status_code == 404, missing.text
        assert missing.json()["detail"] == {"code": "billing_invoice_not_found"}

        response = client.get(path, headers=owner_headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["vary"] == "Authorization, X-Organization-ID"
        document = BillingInvoiceDocumentPreviewResponse.model_validate(response.json())
        assert document.read_only is True
        assert document.download_enabled is False
        assert document.delivery_enabled is False
        assert document.invoice.id == UUID(document_ids["invoice_id"])
        assert document.invoice.status == "issued"


def test_invoice_document_preview_digest_is_stable_and_get_is_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        database_path,
        settings,
        owner_headers,
        _foreign_headers,
        family,
        document_ids,
    ) = _document_preview_fixture(tmp_path, monkeypatch)
    path = f"/api/v1/billing/invoices/{document_ids['invoice_id']}/document-preview"
    before_counts = _billing_table_counts(database_path)
    with TestClient(create_app(settings)) as client:
        first = client.get(path, headers=owner_headers)
        second = client.get(path, headers=owner_headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert _billing_table_counts(database_path) == before_counts

    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["canonical_sha256"] == second_payload["canonical_sha256"]
    first_without_observation_time = {
        key: value for key, value in first_payload.items() if key != "generated_at"
    }
    second_without_observation_time = {
        key: value for key, value in second_payload.items() if key != "generated_at"
    }
    assert first_without_observation_time == second_without_observation_time

    canonical_payload = {
        key: value
        for key, value in first_payload.items()
        if key not in {"generated_at", "canonical_sha256"}
    }
    expected_digest = hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert first_payload["canonical_sha256"] == expected_digest
    assert first_payload["provenance_label"] == "TEST/SYNTHETIC — NOT A REAL INVOICE"
    assert first_payload["organization"] == {
        "id": first_payload["organization_id"],
        "display_name": f"Billing Sandbox owner-{family['name'].removeprefix('Synthetic Family ')}",
        "legal_name": "Synthetic Child Care Society",
        "email": "billing@example.test",
        "phone": "780-555-0199",
    }
    assert first_payload["payer_snapshot"]["payer_version_id"] == document_ids["payer_version_id"]
    assert first_payload["payer_snapshot"]["name"] == "Primary Payer"
    assert first_payload["settlement"] == {
        "currency": "CAD",
        "total_minor": 10000,
        "allocated_minor": 2000,
        "credits_minor": 1000,
        "outstanding_minor": 7000,
    }
    assert first_payload["allocations"] == [
        {
            "id": document_ids["allocation_id"],
            "payment_id": document_ids["payment_id"],
            "amount_minor": 2000,
            "allocated_at": "2026-07-22T12:20:00Z",
        }
    ]
    assert first_payload["credits"] == [
        {
            "id": document_ids["credit_id"],
            "amount_minor": 1000,
            "reason_code": "service_adjustment",
            "note": "Synthetic adjustment",
            "issued_at": "2026-07-22T12:30:00Z",
        }
    ]
    assert first_payload["data_through_at"] == "2026-07-22T12:30:00Z"


def test_capability_is_readable_but_writes_remain_disabled_in_shadow_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    suffix = uuid4().hex[:8]
    with TestClient(create_app(_settings(database_path))) as client:
        headers, auth = _register(client, suffix)
        disabled = client.get("/api/v1/billing/capability", headers=headers)
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["runtime_available"] is False
        assert disabled.json()["writes_available"] is False
        assert disabled.json()["billing_mode"] == "disabled"

    organization_id = UUID(auth["user"]["organization_id"])
    shadow = create_app(
        _settings(database_path, billing_mode="shadow", organization_id=organization_id)
    )
    with TestClient(shadow) as client:
        capability = client.get("/api/v1/billing/capability", headers=headers)
        assert capability.status_code == 200, capability.text
        assert capability.json()["runtime_available"] is True
        assert capability.json()["writes_available"] is False
        assert capability.json()["billing_mode"] == "shadow"
        blocked = client.post(
            "/api/v1/billing/commands/prepare",
            headers=headers,
            json={
                "command_type": "account_open",
                "request_payload": {
                    "client_operation_id": str(uuid4()),
                    "family_id": str(uuid4()),
                    "payer_guardian_id": str(uuid4()),
                },
            },
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"] == {"code": "billing_sandbox_writes_disabled"}


def test_source_attestation_requires_the_tenant_root_before_domain_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    suffix = uuid4().hex[:8]
    with TestClient(create_app(_settings(database_path))) as client:
        headers, auth = _register(client, suffix)
        family = _create_family(client, headers, suffix)

    organization_id = auth["user"]["organization_id"]
    actor_user_id = auth["user"]["id"]
    with pytest.raises(sqlite3.IntegrityError, match="invalid synthetic source"):
        _insert_attestations(
            database_path,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            sources=[("family", family["id"])],
        )

    guardian = family["guardians"][0]
    _insert_attestations(
        database_path,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        sources=[
            ("organization", organization_id),
            ("family", family["id"]),
            ("guardian", guardian["id"]),
        ],
    )
    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT count(*) FROM billing_sandbox_source_attestations"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="attested synthetic source"):
            connection.execute(
                "UPDATE families SET name=name WHERE id=?",
                (_sqlite_uuid(family["id"]),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="attested synthetic source"):
            connection.execute(
                "DELETE FROM guardians WHERE id=?",
                (_sqlite_uuid(guardian["id"]),),
            )
    assert count == 3


def test_capability_contract_requires_a_strict_write_readiness_boolean() -> None:
    payload = {
        "organization_id": str(uuid4()),
        "runtime_available": True,
        "writes_available": False,
        "billing_mode": "sandbox",
        "organization_timezone": "America/Edmonton",
        "organization_local_date": "2026-07-22",
        "server_time": "2026-07-22T12:00:00Z",
    }
    assert BillingCapabilityResponse.model_validate(payload).writes_available is False
    with pytest.raises(ValidationError):
        BillingCapabilityResponse.model_validate(
            {key: value for key, value in payload.items() if key != "writes_available"}
        )
    with pytest.raises(ValidationError):
        BillingCapabilityResponse.model_validate({**payload, "writes_available": "false"})


def test_sqlite_sandbox_keeps_reads_available_but_rejects_all_command_entry_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    suffix = uuid4().hex[:8]
    with TestClient(create_app(_settings(database_path))) as client:
        headers, auth = _register(client, suffix)
    organization_id = UUID(auth["user"]["organization_id"])
    sandbox_settings = _settings(
        database_path,
        billing_mode="sandbox",
        organization_id=organization_id,
    )
    assert sandbox_settings.billing_sandbox_target_is_disposable is False

    application = create_app(sandbox_settings)
    with TestClient(application) as client:
        capability = client.get("/api/v1/billing/capability", headers=headers)
        assert capability.status_code == 200, capability.text
        assert capability.json()["runtime_available"] is True
        assert capability.json()["writes_available"] is False
        assert application.state.billing_ledger_writes_enabled is False

        workspace = client.get("/api/v1/billing/workspace", headers=headers)
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["complete"] is True
        assert workspace.json()["overview"]["account_count"] == 0

        account_payload = {
            "client_operation_id": str(uuid4()),
            "family_id": str(uuid4()),
            "payer_guardian_id": str(uuid4()),
        }
        blocked_preparation = client.post(
            "/api/v1/billing/commands/prepare",
            headers=headers,
            json={
                "command_type": "account_open",
                "request_payload": account_payload,
            },
        )
        assert blocked_preparation.status_code == 409, blocked_preparation.text
        assert blocked_preparation.json()["detail"] == {"code": "billing_sandbox_writes_disabled"}

        blocked_command = client.post(
            "/api/v1/billing/accounts", headers=headers, json=account_payload
        )
        assert blocked_command.status_code == 409, blocked_command.text
        assert blocked_command.json()["detail"] == {"code": "billing_sandbox_writes_disabled"}

        blocked_recovery = client.post(
            f"/api/v1/billing/commands/{uuid4()}/finalize-absence",
            headers=headers,
            json={
                "expected_request_hash": "0" * 64,
                "reason_code": "operator_confirmed_not_committed",
            },
        )
        assert blocked_recovery.status_code == 409, blocked_recovery.text
        assert blocked_recovery.json()["detail"] == {"code": "billing_sandbox_writes_disabled"}


def test_disposable_target_authorization_requires_writable_postgres(tmp_path: Path) -> None:
    sqlite_settings = _settings(
        tmp_path / "caresync.db",
        billing_mode="sandbox",
        organization_id=uuid4(),
    )
    assert sqlite_settings.billing_sandbox_target_is_disposable is False

    common = {
        "_env_file": None,
        "environment": "test",
        "database_type": "postgres",
        "database_host": "127.0.0.1",
        "database_port": 55439,
        "database_user": "caresync_basic_app",
        "database_password": "",
        "database_name": "caresync",
        "database_ssl": False,
        "enable_advanced_routes": False,
        "billing_mode": "sandbox",
        "billing_sandbox_target_attestation": "DISPOSABLE_CARESYNC_BILLING_SANDBOX",
        "billing_sandbox_organization_ids": [uuid4()],
        "jwt_secret": "portable-billing-test-secret-with-at-least-thirty-two-bytes",
    }
    assert Settings(**common, database_read_only=False).billing_sandbox_target_is_disposable
    assert not Settings(**common, database_read_only=True).billing_sandbox_target_is_disposable
    assert not Settings(
        **{**common, "database_port": 5432}, database_read_only=False
    ).billing_sandbox_target_is_disposable


def test_sqlite_schema_consistency_rejects_missing_trigger_definition(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    database = Database(_settings(database_path))
    try:
        assert database.has_billing_ledger() is True
    finally:
        database.dispose()

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER billing_accounts_0033_immutable_update")
    drifted = Database(_settings(database_path))
    try:
        with pytest.raises(RuntimeError, match="0033 billing ledger"):
            drifted.has_billing_ledger()
    finally:
        drifted.dispose()
