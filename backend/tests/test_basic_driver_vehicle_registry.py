"""Portable 0031 registry migration, immutability, and self-projection proofs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.basic.models import (
    OrganizationMembership,
    StaffDriverAuthorizationDecision,
    StaffDriverCapabilityVersion,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    TransportVehicle,
    TransportVehicleEvidenceVersion,
    TransportVehicleVersion,
    User,
)
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="driver-registry-test-secret-with-at-least-thirty-two-bytes",
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


def _register(client: TestClient) -> tuple[dict[str, str], dict]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "driver-owner@example.test",
            "password": "secure-password-123",
            "first_name": "Driver",
            "last_name": "Owner",
            "organization_name": "Transport Test Centre",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return {"Authorization": f"Bearer {auth['access_token']}"}, auth


def test_0031_is_absent_at_0030_and_complete_at_head(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, revision="0030_staff_screening_paths")
    database = Database(_settings(database_path))
    assert database.has_driver_vehicle_registry() is False
    database.dispose()

    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    database = Database(_settings(database_path))
    assert database.has_driver_vehicle_registry() is True
    database.dispose()


def test_0031_partial_trigger_set_fails_closed(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    database = Database(_settings(database_path))
    assert database.has_driver_vehicle_registry() is True
    database.dispose()

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER staff_driver_readiness_insert_guard")
    database = Database(_settings(database_path))
    with pytest.raises(RuntimeError, match="Partial or drifted 0031"):
        database.has_driver_vehicle_registry()
    database.dispose()


def test_retained_schema_advertises_no_registry_and_read_fails_closed(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, revision="0030_staff_screening_paths")
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers, _ = _register(client)
        self_response = client.get("/api/v1/staff/self", headers=headers)
        assert self_response.status_code == 200, self_response.text
        assert self_response.json()["driver_vehicle_registry"] == {
            "schema_version": None,
            "runtime_available": False,
            "self_service_available": False,
            "read_path": None,
            "operational_driver_ready": False,
            "dispatch_authorized": False,
        }
        registry = client.get("/api/v1/staff/self/transport-registry", headers=headers)
        assert registry.status_code == 503
        assert registry.json()["detail"] == {"code": "driver_vehicle_registry_unavailable"}


def test_0031_registry_is_append_only_and_self_projection_is_private(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    now = datetime.now(UTC).replace(microsecond=0)
    with TestClient(application) as client:
        headers, _ = _register(client)
        with application.state.database.session_factory() as session:
            user = session.query(User).filter_by(email="driver-owner@example.test").one()
            membership = session.query(OrganizationMembership).filter_by(user_id=user.id).one()
            reviewer = User(
                email="independent-reviewer@example.test",
                password_hash="not-used-by-this-migration-test",
                first_name="Independent",
                last_name="Reviewer",
                is_active=True,
            )
            session.add(reviewer)
            session.flush()
            session.add(
                OrganizationMembership(
                    organization_id=membership.organization_id,
                    user_id=reviewer.id,
                    role_id=membership.role_id,
                    status="active",
                    joined_at=now,
                )
            )
            session.commit()
            capability = StaffDriverCapabilityVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                version_number=1,
                status="declared",
                willing_to_drive=True,
                licence_jurisdiction="CA-AB",
                licence_class="5",
                vehicle_access="personal_vehicle",
                preferred_service_radius_km=25,
                source_kind="staff_self",
                effective_at=now,
                recorded_by_user_id=user.id,
            )
            session.add(capability)
            session.commit()

            qualification = StaffDriverQualificationVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                qualification_type="driver_licence",
                version_number=1,
                status="verified",
                jurisdiction="CA-AB",
                qualification_class="5",
                identifier_last4="1234",
                issue_date=date.today() - timedelta(days=365),
                expiry_date=date.today() + timedelta(days=365),
                evidence_reference_sha256="a" * 64,
                effective_at=now,
                recorded_by_user_id=user.id,
            )
            session.add(qualification)
            session.commit()

            first_aid_v1 = StaffDriverQualificationVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                qualification_type="first_aid",
                version_number=1,
                status="verified",
                jurisdiction="CA-AB",
                issue_date=date.today() - timedelta(days=30),
                expiry_date=date.today() + timedelta(days=365),
                evidence_reference_sha256="b" * 64,
                effective_at=now,
                recorded_by_user_id=user.id,
            )
            first_aid_v2 = StaffDriverQualificationVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                qualification_type="first_aid",
                version_number=2,
                status="rejected",
                jurisdiction="CA-AB",
                issue_date=date.today(),
                expiry_date=date.today() + timedelta(days=365),
                evidence_reference_sha256="c" * 64,
                effective_at=now,
                recorded_by_user_id=reviewer.id,
            )
            session.add_all([first_aid_v1, first_aid_v2])
            session.commit()

            session.add(
                StaffDriverAuthorizationDecision(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    decision_sequence=1,
                    capability_version_id=capability.id,
                    qualification_version_ids=[
                        str(first_aid_v1.id),
                        str(first_aid_v2.id),
                    ],
                    decision="needs_review",
                    reason_code="duplicate_qualification_lane",
                    authorization_valid_from=None,
                    authorization_valid_until=None,
                    reviewed_by_user_id=reviewer.id,
                    reviewed_at=now,
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            with pytest.raises(IntegrityError, match="authorization sequence or evidence"):
                session.commit()
            session.rollback()

            session.add(
                StaffDriverAuthorizationDecision(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    decision_sequence=1,
                    capability_version_id=capability.id,
                    qualification_version_ids=[
                        str(qualification.id),
                        str(first_aid_v1.id),
                    ],
                    decision="authorized",
                    reason_code="stale_qualification_lane",
                    authorization_valid_from=now,
                    authorization_valid_until=now + timedelta(days=180),
                    reviewed_by_user_id=reviewer.id,
                    reviewed_at=now,
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            with pytest.raises(IntegrityError, match="authorization sequence or evidence"):
                session.commit()
            session.rollback()

            self_review = StaffDriverAuthorizationDecision(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                decision_sequence=1,
                capability_version_id=capability.id,
                qualification_version_ids=[str(qualification.id)],
                decision="authorized",
                reason_code="employment_duties_reviewed",
                authorization_valid_from=now,
                authorization_valid_until=now + timedelta(days=180),
                reviewed_by_user_id=user.id,
                reviewed_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
            session.add(self_review)
            with pytest.raises(IntegrityError, match="authorization sequence or evidence"):
                session.commit()
            session.rollback()

            authorization = StaffDriverAuthorizationDecision(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                decision_sequence=1,
                capability_version_id=capability.id,
                qualification_version_ids=[str(qualification.id)],
                decision="authorized",
                reason_code="employment_duties_reviewed",
                authorization_valid_from=now,
                authorization_valid_until=now + timedelta(days=180),
                reviewed_by_user_id=reviewer.id,
                reviewed_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
            session.add(authorization)
            session.commit()

            session.add(
                StaffDriverAuthorizationDecision(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    decision_sequence=2,
                    capability_version_id=capability.id,
                    qualification_version_ids=[str(qualification.id)],
                    decision="authorized",
                    reason_code="invalid_overlong_window",
                    authorization_valid_from=now,
                    authorization_valid_until=now + timedelta(days=730),
                    reviewed_by_user_id=reviewer.id,
                    reviewed_at=now,
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            with pytest.raises(IntegrityError, match="authorization sequence or evidence"):
                session.commit()
            session.rollback()

            vehicle = TransportVehicle(
                organization_id=membership.organization_id,
                owner_kind="staff_personal",
                staff_owner_membership_id=membership.id,
                created_by_user_id=user.id,
            )
            session.add(vehicle)
            session.commit()
            vehicle_version = TransportVehicleVersion(
                organization_id=membership.organization_id,
                vehicle_id=vehicle.id,
                version_number=1,
                make="Toyota",
                model="Sienna",
                model_year=2022,
                color="Blue",
                plate_token="ABC123",
                plate_jurisdiction="CA-AB",
                passenger_capacity=7,
                child_passenger_capacity=6,
                wheelchair_accessible=False,
                effective_at=now,
                recorded_by_user_id=user.id,
            )
            session.add(vehicle_version)
            session.commit()
            evidence = TransportVehicleEvidenceVersion(
                organization_id=membership.organization_id,
                vehicle_id=vehicle.id,
                vehicle_version_id=vehicle_version.id,
                evidence_type="insurance",
                version_number=1,
                status="verified",
                issue_date=date.today() - timedelta(days=30),
                expiry_date=date.today() + timedelta(days=335),
                original_filename="insurance.pdf",
                media_type="application/pdf",
                byte_size=1024,
                content_sha256="b" * 64,
                ciphertext_sha256="c" * 64,
                storage_reference="transport/private/insurance.enc",
                encryption_key_id="transport-test-key",
                recorded_by_user_id=user.id,
            )
            session.add(evidence)
            session.commit()
            readiness = StaffDriverReadinessDecision(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                decision_sequence=1,
                capability_version_id=capability.id,
                authorization_decision_id=authorization.id,
                vehicle_id=vehicle.id,
                vehicle_version_id=vehicle_version.id,
                vehicle_evidence_version_ids=[str(evidence.id)],
                decision="incomplete",
                reason_codes=["dispatch_policy_not_activated"],
                evaluated_by_user_id=reviewer.id,
                evaluated_at=now,
                operational_driver_ready=False,
                dispatch_authorized=False,
            )
            session.add(readiness)
            session.commit()

            capability.status = "withdrawn"
            with pytest.raises(IntegrityError, match="immutable driver/vehicle fact"):
                session.commit()
            session.rollback()

            session.add(
                StaffDriverCapabilityVersion(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    version_number=3,
                    status="withdrawn",
                    willing_to_drive=False,
                    vehicle_access="none",
                    source_kind="staff_self",
                    effective_at=now + timedelta(minutes=1),
                    recorded_by_user_id=user.id,
                )
            )
            with pytest.raises(IntegrityError, match="capability sequence"):
                session.commit()
            session.rollback()

        staff_self = client.get("/api/v1/staff/self", headers=headers)
        assert staff_self.status_code == 200, staff_self.text
        marker = staff_self.json()["driver_vehicle_registry"]
        assert marker["schema_version"] == "0031"
        assert marker["runtime_available"] is True
        assert marker["self_service_available"] is True
        assert marker["operational_driver_ready"] is False
        assert marker["dispatch_authorized"] is False

        response = client.get("/api/v1/staff/self/transport-registry", headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        body = response.json()
        assert body["schema_version"] == "0031"
        assert body["driver_capability"]["status"] == "declared"
        assert body["qualifications"][0]["evidence_present"] is True
        assert body["authorizations"][0]["decision"] == "authorized"
        assert body["vehicles"][0]["current_version"]["make"] == "Toyota"
        assert body["vehicles"][0]["evidence"][0]["evidence_type"] == "insurance"
        assert body["latest_readiness_decision"]["decision"] == "incomplete"
        assert body["operational_driver_ready"] is False
        assert body["dispatch_authorized"] is False
        serialized = response.text
        assert "storage_reference" not in serialized
        assert "content_sha256" not in serialized
        assert "ciphertext_sha256" not in serialized
        assert "child_id" not in serialized
        assert "address" not in serialized


def test_active_vehicle_plate_is_unique_after_normalization_and_released_on_retirement(
    tmp_path, monkeypatch
):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    now = datetime.now(UTC).replace(microsecond=0)
    with TestClient(application) as client:
        _register(client)
        with application.state.database.session_factory() as session:
            user = session.query(User).filter_by(email="driver-owner@example.test").one()
            membership = session.query(OrganizationMembership).filter_by(user_id=user.id).one()
            first = TransportVehicle(
                organization_id=membership.organization_id,
                owner_kind="staff_personal",
                staff_owner_membership_id=membership.id,
                created_by_user_id=user.id,
                created_at=now,
            )
            second = TransportVehicle(
                organization_id=membership.organization_id,
                owner_kind="staff_personal",
                staff_owner_membership_id=membership.id,
                created_by_user_id=user.id,
                created_at=now,
            )
            session.add_all([first, second])
            session.commit()
            session.add(
                TransportVehicleVersion(
                    organization_id=membership.organization_id,
                    vehicle_id=first.id,
                    version_number=1,
                    make="Toyota",
                    model="Sienna",
                    model_year=2024,
                    plate_token="ABC 123",
                    plate_jurisdiction="CA-AB",
                    passenger_capacity=7,
                    child_passenger_capacity=6,
                    wheelchair_accessible=False,
                    effective_at=now,
                    recorded_by_user_id=user.id,
                )
            )
            session.commit()

            def duplicate_version():
                return TransportVehicleVersion(
                    organization_id=membership.organization_id,
                    vehicle_id=second.id,
                    version_number=1,
                    make="Honda",
                    model="Odyssey",
                    model_year=2024,
                    plate_token="a-b.c_123",
                    plate_jurisdiction="ca ab",
                    passenger_capacity=7,
                    child_passenger_capacity=6,
                    wheelchair_accessible=False,
                    effective_at=now,
                    recorded_by_user_id=user.id,
                )

            session.add(duplicate_version())
            with pytest.raises(IntegrityError, match="transport_vehicle_plate_conflict"):
                session.commit()
            session.rollback()

            first.retired_at = now + timedelta(seconds=1)
            first.retired_by_user_id = user.id
            first.retirement_reason_code = "replaced"
            session.commit()
            session.add(duplicate_version())
            session.commit()


def test_sqlite_authorization_guard_uses_edmonton_local_expiry_date(
    tmp_path, monkeypatch
):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    reviewed_at = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    with TestClient(application) as client:
        _register(client)
        with application.state.database.session_factory() as session:
            user = session.query(User).filter_by(email="driver-owner@example.test").one()
            membership = session.query(OrganizationMembership).filter_by(user_id=user.id).one()
            reviewer = User(
                email="dst-reviewer@example.test",
                password_hash="not-used-by-dst-test",
                first_name="DST",
                last_name="Reviewer",
                is_active=True,
            )
            session.add(reviewer)
            session.flush()
            session.add(
                OrganizationMembership(
                    organization_id=membership.organization_id,
                    user_id=reviewer.id,
                    role_id=membership.role_id,
                    status="active",
                    joined_at=reviewed_at,
                )
            )
            capability = StaffDriverCapabilityVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                version_number=1,
                status="declared",
                willing_to_drive=True,
                licence_jurisdiction="CA-AB",
                licence_class="5",
                vehicle_access="organization_vehicle_only",
                source_kind="staff_self",
                effective_at=reviewed_at,
                recorded_by_user_id=user.id,
            )
            qualification = StaffDriverQualificationVersion(
                organization_id=membership.organization_id,
                membership_id=membership.id,
                qualification_type="driver_licence",
                version_number=1,
                status="verified",
                jurisdiction="CA-AB",
                qualification_class="5",
                identifier_last4="1234",
                issue_date=date(2025, 7, 21),
                expiry_date=date(2026, 7, 21),
                evidence_reference_sha256="a" * 64,
                effective_at=reviewed_at,
                recorded_by_user_id=user.id,
            )
            session.add_all([capability, qualification])
            session.commit()
            session.add(
                StaffDriverAuthorizationDecision(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    decision_sequence=1,
                    capability_version_id=capability.id,
                    qualification_version_ids=[str(qualification.id)],
                    decision="authorized",
                    reason_code="local_date_still_valid",
                    authorization_valid_from=reviewed_at,
                    authorization_valid_until=datetime(2026, 7, 22, 5, 30, tzinfo=UTC),
                    reviewed_by_user_id=reviewer.id,
                    reviewed_at=reviewed_at,
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            session.commit()
            session.add(
                StaffDriverAuthorizationDecision(
                    organization_id=membership.organization_id,
                    membership_id=membership.id,
                    decision_sequence=2,
                    capability_version_id=capability.id,
                    qualification_version_ids=[str(qualification.id)],
                    decision="authorized",
                    reason_code="next_local_date_expired",
                    authorization_valid_from=reviewed_at,
                    authorization_valid_until=datetime(2026, 7, 22, 6, 0, tzinfo=UTC),
                    reviewed_by_user_id=reviewer.id,
                    reviewed_at=reviewed_at + timedelta(minutes=1),
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            with pytest.raises(IntegrityError, match="authorization sequence or evidence"):
                session.commit()
