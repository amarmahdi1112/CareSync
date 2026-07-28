"""Portable proofs for the explicit 0036 private/manual billing boundary."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.basic.billing import _invoice_number, _require_synthetic_sources
from app.basic.billing_schemas import (
    MANUAL_BILLING_REVIEW_ATTESTATION,
    PRIVATE_MANUAL_BILLING_LABEL,
    BillingCapabilityResponse,
    BillingInvoiceResponse,
)
from app.core.config import Settings
from app.db.session import Database

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "development",
        "database_type": "postgres",
        "database_host": "127.0.0.1",
        "database_port": 5434,
        "database_user": "caresync_basic_app",
        "database_password": "",
        "database_name": "caresync",
        "database_read_only": False,
        "billing_mode": "manual",
        "billing_manual_target_attestation": "PRIVATE_LOCAL_MANUAL_BILLING",
        "jwt_secret": "portable-manual-billing-secret-at-least-thirty-two-bytes",
    }
    values.update(overrides)
    return Settings(**values)


def _migrate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return database_path


def _seed_owner_and_organization(database_path: Path) -> dict[str, str]:
    values = {
        "organization_id": uuid4().hex,
        "role_id": uuid4().hex,
        "user_id": uuid4().hex,
        "membership_id": uuid4().hex,
    }
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO organizations(id,name,status,timezone,preferences) "
            "VALUES (?,'Manual Billing','active','America/Edmonton','{}')",
            (values["organization_id"],),
        )
        connection.execute(
            "INSERT INTO roles(id,organization_id,key,name,permissions,is_system) "
            "VALUES (?,?,'owner','Owner',?,1)",
            (
                values["role_id"],
                values["organization_id"],
                (
                    '["billing:adjust","billing:close","billing:issue","billing:manage",'
                    '"billing:payments","billing:read","billing:recover",'
                    '"transport:manage","transport:read"]'
                ),
            ),
        )
        connection.execute(
            "INSERT INTO users(id,email,password_hash,first_name,last_name,is_active,"
            "email_verified_at,email_verification_method,auth_version,created_at,updated_at) "
            "VALUES (?,'manual-owner@example.test','not-used','Manual','Owner',1,?,"
            "'development_auto',1,?,?)",
            (
                values["user_id"],
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role_id,status,"
            "created_at,updated_at) VALUES (?,?,?,?,'active',?,?)",
            (
                values["membership_id"],
                values["organization_id"],
                values["user_id"],
                values["role_id"],
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
    return values


def _insert_activation(database_path: Path, values: dict[str, str]) -> str:
    activation_id = uuid4().hex
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO billing_manual_activations(id,organization_id,"
            "activated_by_user_id,activated_by_membership_id,activation_policy_version,"
            "review_attestation,activated_at) VALUES (?,?,?,?,?,?,?)",
            (
                activation_id,
                values["organization_id"],
                values["user_id"],
                values["membership_id"],
                "private_local_manual_billing_v1",
                MANUAL_BILLING_REVIEW_ATTESTATION,
                datetime.now(UTC).isoformat(),
            ),
        )
    return activation_id


def test_manual_mode_requires_every_local_server_gate_and_an_explicit_allowlist() -> None:
    organization_id = uuid4()
    ready = _settings(billing_manual_organization_ids=[organization_id])
    assert ready.billing_manual_target_is_private_local is True
    assert ready.billing_organization_is_allowlisted(organization_id) is True
    assert ready.billing_organization_is_allowlisted(uuid4()) is False

    for overrides in (
        {"environment": "test"},
        {"environment": "production"},
        {"database_type": "sqlite"},
        {"database_read_only": True},
        {"database_host": "db.example.test"},
        {"billing_manual_target_attestation": ""},
    ):
        assert _settings(**overrides).billing_manual_target_is_private_local is False


def test_provenance_contract_rejects_manual_records_disguised_as_sandbox() -> None:
    manual_capability = BillingCapabilityResponse(
        organization_id=uuid4(),
        sandbox=False,
        provenance_label=PRIVATE_MANUAL_BILLING_LABEL,
        runtime_available=True,
        writes_available=False,
        billing_mode="manual",
        manual_activation_required=True,
        organization_timezone="America/Edmonton",
        organization_local_date="2026-07-22",
        server_time="2026-07-22T12:00:00Z",
    )
    assert manual_capability.processor_enabled is False
    assert manual_capability.money_movement_enabled is False
    assert manual_capability.automatic_issue_enabled is False
    assert manual_capability.tax_advice_enabled is False

    with pytest.raises(ValidationError, match="provenance"):
        BillingCapabilityResponse(
            organization_id=uuid4(),
            sandbox=True,
            provenance_label=PRIVATE_MANUAL_BILLING_LABEL,
            runtime_available=True,
            writes_available=True,
            billing_mode="manual",
            organization_timezone="America/Edmonton",
            organization_local_date="2026-07-22",
            server_time="2026-07-22T12:00:00Z",
        )

    assert "delivery_enabled" not in BillingInvoiceResponse.model_fields


def test_portable_activation_is_owner_bound_immutable_and_unfreezes_no_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = _migrate(tmp_path, monkeypatch)
    values = _seed_owner_and_organization(database_path)
    invoice_id = uuid4()
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        assert _invoice_number(
            session,
            UUID(values["organization_id"]),
            date(2026, 7, 22),
            invoice_id,
        ).startswith("TEST-INV-202607-")
    activation_id = _insert_activation(database_path, values)

    database = Database(
        Settings(
            _env_file=None,
            environment="test",
            database_type="sqlite",
            database_path=database_path,
            database_name="caresync",
            database_read_only=False,
            jwt_secret="portable-manual-boundary-secret-at-least-thirty-two-bytes",
        )
    )
    try:
        assert database.has_billing_ledger() is True
        assert database.has_billing_manual_activation_boundary() is True
    finally:
        database.dispose()

    try:
        with Session(engine) as session:
            manual_invoice_number = _invoice_number(
                session,
                UUID(values["organization_id"]),
                date(2026, 7, 22),
                invoice_id,
            )
            assert manual_invoice_number.startswith("MANUAL-INV-202607-")
            assert not manual_invoice_number.startswith("TEST-INV-")
            _require_synthetic_sources(
                session,
                UUID(values["organization_id"]),
                ("family", uuid4()),
            )
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE organizations SET name='Manual Billing Renamed' "
                f"WHERE id='{values['organization_id']}'"
            )
    finally:
        engine.dispose()

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE billing_manual_activations SET activated_at=activated_at WHERE id=?",
                (activation_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM billing_manual_activations WHERE id=?",
                (activation_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="invalid manual billing activation"):
            connection.execute(
                "INSERT INTO billing_manual_activations(id,organization_id,"
                "activated_by_user_id,activated_by_membership_id,activation_policy_version,"
                "review_attestation,activated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    values["organization_id"],
                    uuid4().hex,
                    values["membership_id"],
                    "private_local_manual_billing_v1",
                    MANUAL_BILLING_REVIEW_ATTESTATION,
                    datetime.now(UTC).isoformat(),
                ),
            )
