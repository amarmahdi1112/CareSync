"""Portable HTTP and service-boundary proofs for staged transport commands."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.api.basic import transport_registry as transport_api
from app.basic.family_evidence_vault import ScannerUnavailable
from app.basic.models import (
    OrganizationMembership,
    Role,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationEvidenceObject,
    StaffDriverQualificationVersion,
    TransportVehicle,
    TransportVehicleVersion,
    User,
)
from app.basic.security import create_access_token, hash_password
from app.basic.staff_screening_vault import StoredScreeningObject
from app.basic.transport_registry_command_schemas import (
    DriverAuthorizationCommand,
    DriverDeclarationCommand,
    PersonalVehicleCreateCommand,
    QualificationEvidenceFields,
    VehicleEvidenceFields,
)
from app.basic.transport_registry_commands import (
    AmbiguousTransportCommandCommit,
    TransportCommandResult,
    execute_transport_command,
)
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VALID_WITHDRAWAL = {
    "operation_id": str(uuid4()),
    "status": "withdrawn",
    "willing_to_drive": False,
    "licence_jurisdiction": None,
    "licence_jurisdiction_other": None,
    "licence_class": None,
    "vehicle_access": "none",
    "preferred_service_radius_km": None,
}
PRIVATE_WORKSPACE_KEYS = {
    "actor_user_id",
    "content_sha256",
    "ciphertext_sha256",
    "encryption_key_id",
    "recorded_by_user_id",
    "reviewed_by_user_id",
    "scan_fact_id",
    "scanned_at",
    "scanner_engine",
    "scanner_version",
    "storage_reference",
    "user_id",
}


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="transport-api-test-secret-with-at-least-thirty-two-bytes",
    )


def _migrate(tmp_path: Path, monkeypatch, revision: str = "head") -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def _register_owner(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "transport-owner@example.test",
            "password": "secure-password-123",
            "first_name": "Transport",
            "last_name": "Owner",
            "organization_name": "Transport API Centre",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _activate_staged_0032(application, *, evidence_ingest: bool) -> None:
    """Simulate a certified boundary while retaining portable SQLite facts."""

    application.state.settings.database_type = "postgres"
    application.state.transport_registry_commands_enabled = True
    application.state.transport_registry_evidence_ingest_available = evidence_ingest
    application.state.transport_registry_evidence_pipeline_available = evidence_ingest
    application.state.transport_evidence_session_factory = object() if evidence_ingest else None


def _create_staff(application, *, transport_read: bool) -> tuple[dict[str, str], UUID]:
    with application.state.database.session_factory() as session:
        owner = session.query(User).filter_by(email="transport-owner@example.test").one()
        owner_membership = session.query(OrganizationMembership).filter_by(user_id=owner.id).one()
        educator_role = (
            session.query(Role)
            .filter_by(organization_id=owner_membership.organization_id, key="educator")
            .one()
        )
        if transport_read:
            educator_role.permissions = [*educator_role.permissions, "transport:read"]
        staff = User(
            email="transport-educator@example.test",
            password_hash=hash_password("secure-password-456"),
            first_name="Transport",
            last_name="Educator",
            is_active=True,
            email_verified_at=datetime.now(UTC),
            email_verification_method="development_auto_verify",
        )
        session.add(staff)
        session.flush()
        membership = OrganizationMembership(
            organization_id=owner_membership.organization_id,
            user_id=staff.id,
            role_id=educator_role.id,
            status="active",
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        session.commit()
        token = create_access_token(staff, application.state.settings)
        return {"Authorization": f"Bearer {token}"}, membership.id


def _all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(map(_all_keys, value.values())), set())
    if isinstance(value, list):
        return set().union(*(map(_all_keys, value)), set())
    return set()


def _request_with_statement_count(application, request_call):
    statements: list[str] = []

    def count_statement(_connection, _cursor, statement, *_args):
        statements.append(statement)

    engine = application.state.database.engine
    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        response = request_call()
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
    return response, len(statements)


@pytest.mark.parametrize(
    ("revision", "expected_schema"),
    [
        ("0028_childcare_command_spine", None),
        ("0031_driver_vehicle_registry", "0031"),
        ("head", "0031"),
    ],
)
def test_retained_and_sqlite_runtimes_never_expose_commands(
    tmp_path,
    monkeypatch,
    revision,
    expected_schema,
):
    database_path = _migrate(tmp_path, monkeypatch, revision)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register_owner(client)
        marker = client.get("/api/v1/staff/self", headers=headers).json()["driver_vehicle_registry"]
        assert marker["schema_version"] == expected_schema
        if expected_schema is None:
            assert marker == {
                "schema_version": None,
                "runtime_available": False,
                "self_service_available": False,
                "read_path": None,
                "operational_driver_ready": False,
                "dispatch_authorized": False,
            }
        assert "declaration_path" not in marker
        assert marker["operational_driver_ready"] is False
        assert marker["dispatch_authorized"] is False

        command_response = client.post(
            "/api/v1/staff/self/transport-registry/declarations",
            headers=headers,
            json=VALID_WITHDRAWAL,
        )
        assert command_response.status_code == 503
        assert command_response.json()["detail"] == {
            "code": "transport_registry_commands_unavailable"
        }
        manager_capability = client.get(
            "/api/v1/staff/transport-registry/capability", headers=headers
        )
        assert manager_capability.status_code == 503
        assert manager_capability.json()["detail"] == {
            "code": "transport_registry_commands_unavailable"
        }


def test_exact_0031_0032_self_markers_and_six_key_manager_capability(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register_owner(client)
        legacy = client.get("/api/v1/staff/self", headers=headers).json()["driver_vehicle_registry"]
        assert legacy == {
            "schema_version": "0031",
            "runtime_available": True,
            "self_service_available": True,
            "read_path": "/api/v1/staff/self/transport-registry",
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }

        _activate_staged_0032(application, evidence_ingest=False)
        without_ingest = client.get("/api/v1/staff/self", headers=headers).json()[
            "driver_vehicle_registry"
        ]
        assert without_ingest == {
            "schema_version": "0032",
            "runtime_available": True,
            "self_service_available": True,
            "read_path": "/api/v1/staff/self/transport-registry",
            "declaration_path": ("/api/v1/staff/self/transport-registry/declarations"),
            "qualification_evidence_path": None,
            "personal_vehicle_path": ("/api/v1/staff/self/transport-registry/vehicles"),
            "vehicle_version_path_template": (
                "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/versions"
            ),
            "vehicle_retirement_path_template": (
                "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/retire"
            ),
            "vehicle_evidence_path_template": None,
            "evidence_upload_available": False,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }

        incomplete_capability = client.get(
            "/api/v1/staff/transport-registry/capability", headers=headers
        )
        assert incomplete_capability.status_code == 200
        assert incomplete_capability.json() == {
            "schema_version": "0032",
            "runtime_available": True,
            "manager_available": True,
            "workspace_path": "/api/v1/staff/transport-registry",
            "evidence_upload_available": False,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }

        application.state.transport_registry_evidence_ingest_available = True
        application.state.transport_evidence_session_factory = object()
        pipeline_missing = client.get("/api/v1/staff/self", headers=headers).json()[
            "driver_vehicle_registry"
        ]
        assert pipeline_missing == without_ingest
        assert (
            client.get("/api/v1/staff/transport-registry/capability", headers=headers).status_code
            == 200
        )

        application.state.transport_registry_evidence_pipeline_available = True
        application.state.transport_evidence_session_factory = None
        factory_missing = client.get("/api/v1/staff/self", headers=headers).json()[
            "driver_vehicle_registry"
        ]
        assert factory_missing == without_ingest
        assert (
            client.get("/api/v1/staff/transport-registry/capability", headers=headers).status_code
            == 200
        )

        application.state.transport_evidence_session_factory = object()
        capability = client.get("/api/v1/staff/transport-registry/capability", headers=headers)
        assert capability.status_code == 200, capability.text
        assert capability.json() == {
            "schema_version": "0032",
            "runtime_available": True,
            "manager_available": True,
            "workspace_path": "/api/v1/staff/transport-registry",
            "evidence_upload_available": True,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }

        enabled = client.get("/api/v1/staff/self", headers=headers).json()[
            "driver_vehicle_registry"
        ]
        assert enabled == {
            "schema_version": "0032",
            "runtime_available": True,
            "self_service_available": True,
            "read_path": "/api/v1/staff/self/transport-registry",
            "declaration_path": ("/api/v1/staff/self/transport-registry/declarations"),
            "qualification_evidence_path": (
                "/api/v1/staff/self/transport-registry/qualification-evidence"
            ),
            "personal_vehicle_path": ("/api/v1/staff/self/transport-registry/vehicles"),
            "vehicle_version_path_template": (
                "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/versions"
            ),
            "vehicle_retirement_path_template": (
                "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/retire"
            ),
            "vehicle_evidence_path_template": (
                "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/evidence"
            ),
            "evidence_upload_available": True,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }


def test_manager_workspace_and_capability_require_manage_permission(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        owner_headers = _register_owner(client)
        staff_headers, _ = _create_staff(application, transport_read=True)
        _activate_staged_0032(application, evidence_ingest=True)

        assert (
            client.get(
                "/api/v1/staff/transport-registry/capability",
                headers=staff_headers,
            ).status_code
            == 403
        )
        assert (
            client.get("/api/v1/staff/transport-registry", headers=staff_headers).status_code == 403
        )
        denied = client.post(
            "/api/v1/staff/transport-registry/vehicles",
            headers=staff_headers,
            json={
                "operation_id": str(uuid4()),
                "make": "Ford",
                "model": "Transit",
                "model_year": 2024,
                "color": "White",
                "plate_token": "SAFE123",
                "plate_jurisdiction": "CA-AB",
                "passenger_capacity": 10,
                "child_passenger_capacity": 8,
                "wheelchair_accessible": False,
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "Permission required"

        accepted = client.post(
            "/api/v1/staff/transport-registry/vehicles",
            headers=owner_headers,
            json={
                "operation_id": str(uuid4()),
                "make": "Ford",
                "model": "Transit",
                "model_year": 2024,
                "color": "White",
                "plate_token": "SAFE123",
                "plate_jurisdiction": "CA-AB",
                "passenger_capacity": 10,
                "child_passenger_capacity": 8,
                "wheelchair_accessible": False,
            },
        )
        assert accepted.status_code == 201, accepted.text
        assert accepted.headers["cache-control"] == "private, no-store"
        assert accepted.headers["pragma"] == "no-cache"
        body = accepted.json()
        assert body["operational_driver_ready"] is False
        assert body["dispatch_authorized"] is False
        with application.state.database.session_factory() as session:
            vehicle = session.get(TransportVehicle, UUID(body["result_id"]))
            assert vehicle.owner_kind == "organization"
            assert vehicle.staff_owner_membership_id is None


def test_self_commands_are_server_scoped_and_manager_routes_are_forbidden(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _register_owner(client)
        staff_headers, membership_id = _create_staff(application, transport_read=False)
        _activate_staged_0032(application, evidence_ingest=True)

        payload = {
            "operation_id": str(uuid4()),
            "status": "declared",
            "willing_to_drive": True,
            "licence_jurisdiction": "CA-AB",
            "licence_jurisdiction_other": None,
            "licence_class": "5",
            "vehicle_access": "organization_vehicle_only",
            "preferred_service_radius_km": 25,
        }
        accepted = client.post(
            "/api/v1/staff/self/transport-registry/declarations",
            headers=staff_headers,
            json=payload,
        )
        assert accepted.status_code == 201, accepted.text
        assert accepted.headers["cache-control"] == "private, no-store"
        assert accepted.headers["pragma"] == "no-cache"
        assert accepted.json()["operational_driver_ready"] is False
        assert accepted.json()["dispatch_authorized"] is False
        with application.state.database.session_factory() as session:
            fact = session.get(StaffDriverCapabilityVersion, UUID(accepted.json()["result_id"]))
            assert fact.membership_id == membership_id

        injected_scope = client.post(
            "/api/v1/staff/self/transport-registry/declarations",
            headers=staff_headers,
            json={**payload, "operation_id": str(uuid4()), "membership_id": str(uuid4())},
        )
        assert injected_scope.status_code == 422
        manager_denied = client.get(
            "/api/v1/staff/transport-registry/capability", headers=staff_headers
        )
        assert manager_denied.status_code == 403


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            DriverDeclarationCommand,
            {
                **VALID_WITHDRAWAL,
                "willing_to_drive": True,
            },
        ),
        (
            DriverDeclarationCommand,
            {
                **VALID_WITHDRAWAL,
                "status": "declared",
                "willing_to_drive": True,
                "vehicle_access": "personal_vehicle",
            },
        ),
        (
            DriverDeclarationCommand,
            {
                **VALID_WITHDRAWAL,
                "status": "declared",
                "willing_to_drive": True,
                "licence_jurisdiction": "OTHER",
                "licence_class": "5",
                "vehicle_access": "personal_vehicle",
            },
        ),
        (
            PersonalVehicleCreateCommand,
            {
                "operation_id": str(uuid4()),
                "make": "Toyota",
                "model": "Sienna",
                "model_year": 2024,
                "plate_token": "SAFE123",
                "plate_jurisdiction": "CA-AB",
                "passenger_capacity": 7,
                "child_passenger_capacity": 7,
                "wheelchair_accessible": False,
            },
        ),
        (
            DriverAuthorizationCommand,
            {
                "operation_id": str(uuid4()),
                "capability_version_id": str(uuid4()),
                "qualification_version_ids": [str(uuid4())] * 2,
                "decision": "authorized",
                "reason_code": "reviewed",
                "authorization_valid_from": datetime.now(UTC),
                "authorization_valid_until": datetime.now(UTC),
            },
        ),
        (
            QualificationEvidenceFields,
            {
                "operation_id": str(uuid4()),
                "qualification_type": "driver_licence",
                "jurisdiction": "CA-AB",
                "qualification_class": "5",
            },
        ),
        (
            VehicleEvidenceFields,
            {
                "operation_id": str(uuid4()),
                "evidence_type": "insurance",
            },
        ),
    ],
)
def test_command_schemas_reject_unsafe_or_incomplete_shapes(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_authorization_window_requires_explicit_timezones():
    with pytest.raises(ValidationError, match="require a timezone"):
        DriverAuthorizationCommand.model_validate(
            {
                "operation_id": str(uuid4()),
                "capability_version_id": str(uuid4()),
                "qualification_version_ids": [str(uuid4())],
                "decision": "authorized",
                "reason_code": "timezone_required",
                "authorization_valid_from": datetime(2026, 7, 21, 8, 0),
                "authorization_valid_until": datetime(2026, 7, 22, 8, 0),
            }
        )


@pytest.mark.parametrize(
    "private_key",
    [
        "actor_user_id",
        "content_sha256",
        "ciphertext_sha256",
        "encryption_key_id",
        "scanner_engine",
        "storage_reference",
    ],
)
def test_json_commands_reject_server_private_fields(tmp_path, monkeypatch, private_key):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register_owner(client)
        _activate_staged_0032(application, evidence_ingest=True)
        response = client.post(
            "/api/v1/staff/self/transport-registry/declarations",
            headers=headers,
            json={**VALID_WITHDRAWAL, private_key: "not-client-controlled"},
        )
        assert response.status_code == 422


def test_workspace_is_bounded_private_and_always_non_operational(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register_owner(client)
        with application.state.database.session_factory() as session:
            owner = session.query(User).filter_by(email="transport-owner@example.test").one()
            owner_membership = (
                session.query(OrganizationMembership).filter_by(user_id=owner.id).one()
            )
            educator_role = (
                session.query(Role)
                .filter_by(
                    organization_id=owner_membership.organization_id,
                    key="educator",
                )
                .one()
            )
            overflow_users = [
                User(
                    id=uuid4(),
                    email=f"transport-overflow-{index}@example.test",
                    password_hash="not-used-by-workspace-test",
                    first_name=f"Staff {index:03d}",
                    last_name="Zulu",
                    is_active=True,
                )
                for index in range(200)
            ]
            session.add_all(overflow_users)
            session.flush()
            session.add_all(
                [
                    OrganizationMembership(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        user_id=user.id,
                        role_id=educator_role.id,
                        status="active",
                        joined_at=datetime.now(UTC),
                    )
                    for user in overflow_users
                ]
            )
            effective_base = datetime.now(UTC) - timedelta(hours=1)
            session.add_all(
                [
                    StaffDriverCapabilityVersion(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        membership_id=owner_membership.id,
                        version_number=version,
                        status="declared",
                        willing_to_drive=True,
                        licence_jurisdiction="CA-AB",
                        licence_jurisdiction_other=None,
                        licence_class="5",
                        vehicle_access="organization_vehicle_only",
                        preferred_service_radius_km=20,
                        source_kind="manager_recorded",
                        source_screening_profile_version=None,
                        effective_at=effective_base + timedelta(minutes=version),
                        recorded_by_user_id=owner.id,
                    )
                    for version in range(1, 22)
                ]
            )
            session.add_all(
                [
                    StaffDriverQualificationVersion(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        membership_id=owner_membership.id,
                        qualification_type="first_aid",
                        version_number=version,
                        status="declared",
                        jurisdiction=None,
                        qualification_class=None,
                        identifier_last4=None,
                        issue_date=None,
                        expiry_date=None,
                        source_screening_document_version_id=None,
                        evidence_reference_sha256=None,
                        effective_at=effective_base + timedelta(minutes=version),
                        recorded_by_user_id=owner.id,
                    )
                    for version in range(1, 22)
                ]
            )
            special_vehicle_id = uuid4()
            session.add(
                TransportVehicle(
                    id=special_vehicle_id,
                    organization_id=owner_membership.organization_id,
                    owner_kind="organization",
                    staff_owner_membership_id=None,
                    created_by_user_id=owner.id,
                    created_at=datetime.now(UTC),
                )
            )
            session.add_all(
                [
                    TransportVehicle(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        owner_kind="organization",
                        staff_owner_membership_id=None,
                        created_by_user_id=owner.id,
                        created_at=datetime.now(UTC) - timedelta(days=1),
                    )
                    for _ in range(100)
                ]
            )
            session.add_all(
                [
                    TransportVehicleVersion(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        vehicle_id=special_vehicle_id,
                        version_number=version,
                        make="Toyota",
                        model="Sienna",
                        model_year=2024,
                        color="Blue",
                        plate_token="SAFE123",
                        plate_jurisdiction="CA-AB",
                        passenger_capacity=7,
                        child_passenger_capacity=6,
                        wheelchair_accessible=False,
                        effective_at=effective_base + timedelta(minutes=version),
                        recorded_by_user_id=owner.id,
                    )
                    for version in range(1, 22)
                ]
            )
            session.commit()
        _activate_staged_0032(application, evidence_ingest=True)
        response = client.get("/api/v1/staff/transport-registry", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["staff"]) == 200
        assert len(body["vehicles"]) == 100
        assert body["staff_truncated"] is True
        assert body["vehicles_truncated"] is True
        owner_record = next(
            row for row in body["staff"] if row["membership_id"] == str(owner_membership.id)
        )
        assert [row["version_number"] for row in owner_record["capabilities"]] == list(
            range(21, 1, -1)
        )
        assert owner_record["capabilities_truncated"] is True
        assert [
            row["version_number"]
            for row in owner_record["qualifications"]
            if row["qualification_type"] == "first_aid"
        ] == list(range(21, 1, -1))
        assert owner_record["qualification_types_truncated"] == ["first_aid"]
        assert owner_record["qualification_reviews_truncated"] is False
        assert owner_record["authorizations_truncated"] is False
        assert owner_record["readiness_truncated"] is False
        special_vehicle = next(
            row for row in body["vehicles"] if row["id"] == str(special_vehicle_id)
        )
        assert [row["version_number"] for row in special_vehicle["versions"]] == list(
            range(21, 1, -1)
        )
        assert special_vehicle["versions_truncated"] is True
        assert special_vehicle["evidence_types_truncated"] == []
        assert special_vehicle["evidence_reviews_truncated"] is False
        for staff in body["staff"]:
            assert len(staff["capabilities"]) <= 20
            for lane in {item["qualification_type"] for item in staff["qualifications"]}:
                assert (
                    sum(item["qualification_type"] == lane for item in staff["qualifications"])
                    <= 20
                )
            assert len(staff["qualification_reviews"]) <= 20
            assert len(staff["authorizations"]) <= 20
            assert len(staff["readiness"]) <= 20
        for vehicle in body["vehicles"]:
            assert len(vehicle["versions"]) <= 20
            for lane in {item["evidence_type"] for item in vehicle["evidence"]}:
                assert sum(item["evidence_type"] == lane for item in vehicle["evidence"]) <= 20
            assert len(vehicle["evidence_reviews"]) <= 20
        assert _all_keys(body).isdisjoint(PRIVATE_WORKSPACE_KEYS)
        assert body["operational_driver_ready"] is False
        assert body["dispatch_authorized"] is False


def test_registry_read_query_counts_are_constant_at_maximum_workspace_size(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    manager_query_cap = 16
    self_query_cap = 14

    with TestClient(application) as client:
        headers = _register_owner(client)
        with application.state.database.session_factory() as session:
            owner = session.query(User).filter_by(email="transport-owner@example.test").one()
            owner_membership = (
                session.query(OrganizationMembership).filter_by(user_id=owner.id).one()
            )
            effective_at = datetime.now(UTC) - timedelta(seconds=1)
            qualification_id = uuid4()
            content_sha256 = "a" * 64
            session.add(
                StaffDriverQualificationVersion(
                    id=qualification_id,
                    organization_id=owner_membership.organization_id,
                    membership_id=owner_membership.id,
                    qualification_type="first_aid",
                    version_number=1,
                    status="declared",
                    jurisdiction=None,
                    qualification_class=None,
                    identifier_last4=None,
                    issue_date=None,
                    expiry_date=None,
                    source_screening_document_version_id=None,
                    evidence_reference_sha256=content_sha256,
                    effective_at=effective_at,
                    recorded_by_user_id=owner.id,
                )
            )
            session.flush()
            session.add(
                StaffDriverQualificationEvidenceObject(
                    id=uuid4(),
                    organization_id=owner_membership.organization_id,
                    membership_id=owner_membership.id,
                    qualification_version_id=qualification_id,
                    original_filename="first-aid.pdf",
                    media_type="application/pdf",
                    byte_size=1024,
                    content_sha256=content_sha256,
                    ciphertext_sha256="b" * 64,
                    storage_reference=(
                        f"{owner.id.hex}/{owner_membership.id.hex}/{uuid4().hex}/v1.enc"
                    ),
                    encryption_key_id="test-key-v1",
                    scanner_engine="test-scanner",
                    scanner_version="1.0.0",
                    scanned_at=effective_at,
                    recorded_by_user_id=owner.id,
                )
            )
            first_vehicle_id = uuid4()
            session.add(
                TransportVehicle(
                    id=first_vehicle_id,
                    organization_id=owner_membership.organization_id,
                    owner_kind="staff_personal",
                    staff_owner_membership_id=owner_membership.id,
                    created_by_user_id=owner.id,
                    created_at=datetime.now(UTC),
                )
            )
            session.add(
                TransportVehicleVersion(
                    id=uuid4(),
                    organization_id=owner_membership.organization_id,
                    vehicle_id=first_vehicle_id,
                    version_number=1,
                    make="Toyota",
                    model="Sienna",
                    model_year=2024,
                    color="Blue",
                    plate_token="BATCH000",
                    plate_jurisdiction="CA-AB",
                    passenger_capacity=7,
                    child_passenger_capacity=6,
                    wheelchair_accessible=False,
                    effective_at=effective_at,
                    recorded_by_user_id=owner.id,
                )
            )
            session.commit()

        _activate_staged_0032(application, evidence_ingest=True)
        small_manager, small_manager_queries = _request_with_statement_count(
            application,
            lambda: client.get("/api/v1/staff/transport-registry", headers=headers),
        )
        small_self, small_self_queries = _request_with_statement_count(
            application,
            lambda: client.get("/api/v1/staff/self/transport-registry", headers=headers),
        )
        assert small_manager.status_code == 200, small_manager.text
        assert small_self.status_code == 200, small_self.text

        with application.state.database.session_factory() as session:
            owner = session.query(User).filter_by(email="transport-owner@example.test").one()
            owner_membership = (
                session.query(OrganizationMembership).filter_by(user_id=owner.id).one()
            )
            educator_role = (
                session.query(Role)
                .filter_by(
                    organization_id=owner_membership.organization_id,
                    key="educator",
                )
                .one()
            )
            overflow_users = [
                User(
                    id=uuid4(),
                    email=f"transport-batch-{index:03d}@example.test",
                    password_hash="not-used-by-query-count-test",
                    first_name=f"Batch {index:03d}",
                    last_name="Zulu",
                    is_active=True,
                )
                for index in range(199)
            ]
            session.add_all(overflow_users)
            session.flush()
            session.add_all(
                [
                    OrganizationMembership(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        user_id=user.id,
                        role_id=educator_role.id,
                        status="active",
                        joined_at=datetime.now(UTC),
                    )
                    for user in overflow_users
                ]
            )
            additional_vehicles = []
            additional_versions = []
            for index in range(99):
                vehicle_id = uuid4()
                personal = index < 50
                effective_at = datetime.now(UTC) - timedelta(minutes=index + 1)
                additional_vehicles.append(
                    TransportVehicle(
                        id=vehicle_id,
                        organization_id=owner_membership.organization_id,
                        owner_kind="staff_personal" if personal else "organization",
                        staff_owner_membership_id=(owner_membership.id if personal else None),
                        created_by_user_id=owner.id,
                        created_at=effective_at,
                    )
                )
                additional_versions.append(
                    TransportVehicleVersion(
                        id=uuid4(),
                        organization_id=owner_membership.organization_id,
                        vehicle_id=vehicle_id,
                        version_number=1,
                        make="Toyota",
                        model="Sienna",
                        model_year=2024,
                        color="Blue",
                        plate_token=f"BATCH{index + 1:03d}",
                        plate_jurisdiction="CA-AB",
                        passenger_capacity=7,
                        child_passenger_capacity=6,
                        wheelchair_accessible=False,
                        effective_at=effective_at,
                        recorded_by_user_id=owner.id,
                    )
                )
            session.add_all(additional_vehicles)
            session.add_all(additional_versions)
            session.commit()

        large_manager, large_manager_queries = _request_with_statement_count(
            application,
            lambda: client.get("/api/v1/staff/transport-registry", headers=headers),
        )
        large_self, large_self_queries = _request_with_statement_count(
            application,
            lambda: client.get("/api/v1/staff/self/transport-registry", headers=headers),
        )
        assert large_manager.status_code == 200, large_manager.text
        assert large_self.status_code == 200, large_self.text
        assert small_manager_queries == large_manager_queries
        assert large_manager_queries <= manager_query_cap
        assert small_self_queries == large_self_queries
        assert large_self_queries <= self_query_cap
        # Contract maxima remain 40,000 staff-history objects plus 12,000
        # vehicle-history objects; rank 21 is loaded only as a truncation sentinel.
        assert len(large_manager.json()["staff"]) == 200
        assert len(large_manager.json()["vehicles"]) == 100
        assert len(large_self.json()["vehicles"]) == 50
        assert large_self.json()["vehicles_truncated"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/staff/self/transport-registry",
        "/api/v1/staff/transport-registry/capability",
        "/api/v1/staff/transport-registry",
    ],
)
def test_self_and_manager_transport_responses_are_never_cacheable(tmp_path, monkeypatch, path):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register_owner(client)
        _activate_staged_0032(application, evidence_ingest=True)
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["vary"] == "Authorization, X-Organization-ID"


def _stored_object() -> StoredScreeningObject:
    return StoredScreeningObject(
        storage_reference=f"{uuid4().hex}/{uuid4().hex}/{uuid4().hex}/v1.enc",
        media_type="application/pdf",
        byte_size=1024,
        content_sha256="a" * 64,
        ciphertext_sha256="b" * 64,
        original_filename="licence.pdf",
        encryption_key_id="test-key-v1",
        scanner_engine="test-scanner",
        scanner_version="1.0.0",
        scanned_at=datetime.now(UTC),
    )


def test_pipeline_failure_is_stable_and_cannot_create_an_orphan(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    deleted: list[str] = []

    async def unavailable_pipeline(*_args, **_kwargs):
        raise ScannerUnavailable("secret scanner diagnostic and filesystem path")

    monkeypatch.setattr(transport_api, "store_encrypted_screening_upload", unavailable_pipeline)
    monkeypatch.setattr(
        transport_api,
        "delete_screening_object",
        lambda _settings, reference: deleted.append(reference),
    )
    with TestClient(application) as client:
        headers = _register_owner(client)
        _activate_staged_0032(application, evidence_ingest=True)
        response = client.post(
            "/api/v1/staff/self/transport-registry/qualification-evidence",
            headers=headers,
            data={
                "operation_id": str(uuid4()),
                "qualification_type": "first_aid",
            },
            files={"file": ("first-aid.pdf", b"%PDF-safe", "application/pdf")},
        )
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "transport_evidence_pipeline_unavailable"}}
    assert "secret scanner diagnostic" not in response.text
    assert deleted == []


def test_evidence_content_is_private_scoped_hardened_and_tamper_safe(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    stored = replace(
        _stored_object(),
        original_filename="licence résumé;\r\nX-Evil.pdf",
    )

    async def fake_store(*_args, **kwargs):
        return replace(
            stored,
            storage_reference=(
                f"{kwargs['user_id'].hex}/{kwargs['document_id'].hex}/{uuid4().hex}/v1.enc"
            ),
        )

    monkeypatch.setattr(transport_api, "store_encrypted_screening_upload", fake_store)
    with TestClient(application) as client:
        owner_headers = _register_owner(client)
        staff_headers, _ = _create_staff(application, transport_read=True)
        second_registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "other-transport-owner@example.test",
                "password": "secure-password-789",
                "first_name": "Other",
                "last_name": "Owner",
                "organization_name": "Other Transport Centre",
            },
        )
        assert second_registration.status_code == 201, second_registration.text
        other_headers = {"Authorization": (f"Bearer {second_registration.json()['access_token']}")}
        _activate_staged_0032(application, evidence_ingest=True)
        owner_self = client.get("/api/v1/staff/self", headers=owner_headers).json()
        owner_membership_id = owner_self["membership_id"]
        upload = client.post(
            "/api/v1/staff/self/transport-registry/qualification-evidence",
            headers=owner_headers,
            data={
                "operation_id": str(uuid4()),
                "qualification_type": "first_aid",
            },
            files={"file": ("first-aid.pdf", b"%PDF-safe", "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        qualification_id = upload.json()["result_id"]
        self_path = (
            "/api/v1/staff/self/transport-registry/qualification-evidence/"
            f"{qualification_id}/content"
        )
        manager_path = (
            f"/api/v1/staff/transport-registry/{owner_membership_id}/"
            f"qualification-evidence/{qualification_id}/content"
        )

        read_calls: list[dict] = []

        def read_private_object(**kwargs):
            read_calls.append(kwargs)
            return b"%PDF private transport evidence"

        monkeypatch.setattr(transport_api, "read_encrypted_screening_object", read_private_object)
        self_content = client.get(self_path, headers=owner_headers)
        assert self_content.status_code == 200, self_content.text
        assert self_content.content == b"%PDF private transport evidence"
        assert self_content.headers["cache-control"] == "private, no-store"
        assert self_content.headers["pragma"] == "no-cache"
        assert self_content.headers["x-content-type-options"] == "nosniff"
        assert self_content.headers["content-security-policy"] == "sandbox"
        assert self_content.headers["cross-origin-resource-policy"] == "same-origin"
        disposition = self_content.headers["content-disposition"]
        assert disposition.startswith("inline; filename*=UTF-8''")
        assert "\r" not in disposition
        assert "\n" not in disposition
        assert "%0D%0A" in disposition
        assert read_calls[-1]["expected_content_sha256"] == stored.content_sha256
        assert read_calls[-1]["expected_ciphertext_sha256"] == stored.ciphertext_sha256

        manager_content = client.get(manager_path, headers=owner_headers)
        assert manager_content.status_code == 200
        assert manager_content.headers["content-security-policy"] == "sandbox"
        assert manager_content.headers["cross-origin-resource-policy"] == "same-origin"

        with application.state.database.session_factory() as session:
            staff_self = client.get("/api/v1/staff/self", headers=staff_headers).json()
            reviewer_membership = (
                session.query(OrganizationMembership)
                .filter_by(id=UUID(staff_self["membership_id"]))
                .one()
            )
            reviewer_role = session.get(Role, reviewer_membership.role_id)
            reviewer_role.permissions = sorted(
                set(reviewer_role.permissions or []) | {"transport:manage"}
            )
            session.commit()
        review = client.post(
            f"/api/v1/staff/transport-registry/{owner_membership_id}/qualification-reviews",
            headers=staff_headers,
            json={
                "operation_id": str(uuid4()),
                "source_qualification_version_id": qualification_id,
                "decision": "verified",
                "reason_code": "reviewed_original",
            },
        )
        assert review.status_code == 201, review.text
        reviewed_qualification_id = review.json()["result_id"]
        with application.state.database.session_factory() as session:
            reviewer_membership = (
                session.query(OrganizationMembership)
                .filter_by(id=UUID(staff_self["membership_id"]))
                .one()
            )
            reviewer_role = session.get(Role, reviewer_membership.role_id)
            reviewer_role.permissions = [
                value for value in reviewer_role.permissions or [] if value != "transport:manage"
            ]
            session.commit()
        reviewed_self_path = (
            "/api/v1/staff/self/transport-registry/qualification-evidence/"
            f"{reviewed_qualification_id}/content"
        )
        reviewed_manager_path = (
            f"/api/v1/staff/transport-registry/{owner_membership_id}/"
            f"qualification-evidence/{reviewed_qualification_id}/content"
        )
        projection = client.get("/api/v1/staff/self/transport-registry", headers=owner_headers)
        assert projection.status_code == 200, projection.text
        current_qualification = next(
            item
            for item in projection.json()["qualifications"]
            if item["id"] == reviewed_qualification_id
        )
        assert current_qualification["content_path"] == reviewed_self_path
        assert client.get(reviewed_self_path, headers=owner_headers).status_code == 200
        assert client.get(reviewed_manager_path, headers=owner_headers).status_code == 200
        assert client.get(reviewed_self_path, headers=staff_headers).status_code == 404
        assert client.get(reviewed_manager_path, headers=other_headers).status_code == 404

        self_scope_denied = client.get(self_path, headers=staff_headers)
        assert self_scope_denied.status_code == 404
        read_only_manager_denied = client.get(manager_path, headers=staff_headers)
        assert read_only_manager_denied.status_code == 403
        other_tenant_denied = client.get(manager_path, headers=other_headers)
        assert other_tenant_denied.status_code == 404
        missing = client.get(
            self_path.replace(qualification_id, str(uuid4())),
            headers=owner_headers,
        )
        assert missing.status_code == 404

        def tampered_object(**_kwargs):
            raise RuntimeError("secret ciphertext digest and vault path")

        monkeypatch.setattr(transport_api, "read_encrypted_screening_object", tampered_object)
        tampered = client.get(self_path, headers=owner_headers)
        assert tampered.status_code == 503
        assert tampered.json() == {"detail": {"code": "transport_evidence_content_unavailable"}}
        assert "secret ciphertext" not in tampered.text


def _evidence_request_context():
    settings = SimpleNamespace(database_type="postgres", database_read_only=False)
    state = SimpleNamespace(
        settings=settings,
        transport_registry_commands_enabled=True,
        transport_registry_evidence_ingest_available=True,
        transport_registry_evidence_pipeline_available=True,
        transport_evidence_session_factory=object(),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        organization=SimpleNamespace(id=uuid4()),
    )
    return request, context


@pytest.mark.parametrize("outcome", ["definite_failure", "exact_retry", "committed"])
def test_evidence_object_cleanup_matches_repository_outcome(monkeypatch, outcome):
    stored = _stored_object()
    request, context = _evidence_request_context()
    deleted: list[str] = []

    async def fake_store(*_args, **_kwargs):
        return stored

    monkeypatch.setattr(transport_api, "store_encrypted_screening_upload", fake_store)
    monkeypatch.setattr(
        transport_api,
        "delete_screening_object",
        lambda _settings, reference: deleted.append(reference),
    )
    if outcome == "definite_failure":

        def repository(**_kwargs):
            raise RuntimeError("definite repository rejection")
    else:

        def repository(**_kwargs):
            return TransportCommandResult(
                client_operation_id=uuid4(),
                command_kind="qualification_evidence",
                result_kind="driver_qualification",
                result_id=uuid4(),
                committed_at=datetime.now(UTC),
                exact_retry=outcome == "exact_retry",
            )

    monkeypatch.setattr(transport_api, "execute_transport_command", repository)

    invocation = transport_api._execute_evidence(
        request=request,
        session=object(),
        context=context,
        command_kind="qualification_evidence",
        operation_id=uuid4(),
        public_payload={"membership_id": str(context.membership.id)},
        file=UploadFile(filename="licence.pdf", file=BytesIO(b"%PDF-safe")),
        document_id=context.membership.id,
    )
    if outcome == "definite_failure":
        with pytest.raises(RuntimeError, match="definite repository rejection"):
            asyncio.run(invocation)
        assert deleted == [stored.storage_reference]
    else:
        response = asyncio.run(invocation)
        assert response["operational_driver_ready"] is False
        assert response["dispatch_authorized"] is False
        assert deleted == ([stored.storage_reference] if outcome == "exact_retry" else [])


def test_ambiguous_evidence_commit_preserves_object_for_exact_retry(monkeypatch):
    stored = _stored_object()
    request, context = _evidence_request_context()
    deleted: list[str] = []

    async def fake_store(*_args, **_kwargs):
        return stored

    def ambiguous_repository(**_kwargs):
        raise AmbiguousTransportCommandCommit("connection lost after commit")

    monkeypatch.setattr(transport_api, "store_encrypted_screening_upload", fake_store)
    monkeypatch.setattr(transport_api, "execute_transport_command", ambiguous_repository)
    monkeypatch.setattr(
        transport_api,
        "delete_screening_object",
        lambda _settings, reference: deleted.append(reference),
    )
    with pytest.raises(HTTPException) as captured:
        asyncio.run(
            transport_api._execute_evidence(
                request=request,
                session=object(),
                context=context,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={"membership_id": str(context.membership.id)},
                file=UploadFile(filename="licence.pdf", file=BytesIO(b"%PDF-safe")),
                document_id=context.membership.id,
            )
        )
    assert captured.value.status_code == 503
    assert captured.value.detail["code"] == "transport_command_commit_unknown"
    assert deleted == []


def test_unknown_database_errors_are_mapped_without_leaking_sql(monkeypatch):
    raw_message = "SELECT secret_value FROM private_table password=hunter2"
    error = DBAPIError(raw_message, {}, RuntimeError(raw_message), False)

    def repository(*_args, **_kwargs):
        raise error

    rolled_back: list[bool] = []
    session = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        rollback=lambda: rolled_back.append(True),
    )
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        organization=SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr("app.basic.transport_registry_commands._execute_postgres", repository)
    with pytest.raises(HTTPException) as captured:
        execute_transport_command(
            session=session,
            context=context,
            command_kind="driver_declaration",
            operation_id=uuid4(),
            public_payload={"status": "withdrawn"},
        )
    assert captured.value.status_code == 503
    assert captured.value.detail == {"code": "transport_command_repository_unavailable"}
    assert raw_message not in str(captured.value.detail)
    assert rolled_back == [True]
