"""Focused fail-closed proofs for the additive 0030 staff-screening boundary."""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from alembic.config import Config
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.api.basic import staff_screening as staff_screening_api
from app.basic import staff_screening_vault
from app.basic.models import (
    AtsCandidate,
    BasicBase,
    MarketplaceOnboardingState,
    MarketplaceProfile,
    Organization,
    StaffScreeningDocument,
    User,
)
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _settings(database_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="staff-screening-test-secret-with-at-least-thirty-two-bytes",
        **overrides,
    )


def _migrate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    revision: str = "head",
) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def test_retained_0028_has_no_0030_capability(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, revision="0028_childcare_command_spine")
    vault_path = tmp_path / "staged-staff-screening-vault"
    settings = _settings(database_path, staff_screening_vault_path=vault_path)
    database = Database(settings)
    assert database.has_staff_screening_pathways() is False
    database.dispose()

    application = create_app(settings)
    with TestClient(application) as client:
        health = client.get("/api/v1/health")
        candidate = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": "retained-screening-capability@example.test",
                "password": "secure-password-123",
                "first_name": "Retained",
                "last_name": "Candidate",
            },
        )
        assert candidate.status_code == 201, candidate.text
        candidate_state = client.get(
            "/api/v1/marketplace/me",
            headers={"Authorization": f"Bearer {candidate.json()['access_token']}"},
        )

    assert application.state.staff_screening_evidence_upload_available is False
    assert health.json()["staff_screening_evidence_upload"] == "unavailable"
    assert candidate_state.status_code == 200, candidate_state.text
    assert candidate_state.json()["staff_screening_evidence_upload_available"] is False
    assert not vault_path.exists()


@pytest.mark.parametrize("environment", ["development", "test"])
def test_unversioned_sqlite_metadata_scaffold_keeps_0030_disabled(
    tmp_path,
    environment,
):
    settings = _settings(tmp_path / "caresync.db").model_copy(update={"environment": environment})
    database = Database(settings)
    BasicBase.metadata.create_all(database.engine)

    with database.engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='alembic_version')"
            ).scalar_one()
            == 0
        )
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE '%screening%'"
            ).scalar_one()
            == 0
        )

    assert database.has_staff_screening_pathways() is False
    database.dispose()

    application = create_app(settings)
    with TestClient(application):
        assert application.state.staff_screening_pathways_enabled is False


def test_unversioned_metadata_scaffold_is_not_allowed_in_production(tmp_path):
    settings = _settings(tmp_path / "caresync.db").model_copy(update={"environment": "production"})
    database = Database(settings)
    BasicBase.metadata.create_all(database.engine)

    with pytest.raises(RuntimeError, match="Partial or drifted 0030"):
        database.has_staff_screening_pathways()


def test_partial_unversioned_metadata_scaffold_still_fails_closed(tmp_path):
    settings = _settings(tmp_path / "caresync.db")
    database = Database(settings)
    BasicBase.metadata.create_all(database.engine)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE ats_offer_acknowledgments")

    with pytest.raises(RuntimeError, match="Partial or drifted 0030"):
        database.has_staff_screening_pathways()


def test_0030_readiness_detects_missing_enforcement_trigger(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    database = Database(_settings(database_path))
    assert database.has_staff_screening_pathways() is True
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER ats_offer_acknowledgments_guard")
    with pytest.raises(RuntimeError, match="Partial or drifted 0030"):
        database.has_staff_screening_pathways()
    with (
        pytest.raises(RuntimeError, match="Partial or drifted 0030"),
        TestClient(create_app(_settings(database_path))),
    ):
        pass


def test_0030_unavailable_evidence_pipeline_gates_only_upload_posts(
    tmp_path,
    monkeypatch,
):
    database_path = _migrate(tmp_path, monkeypatch)
    settings = _settings(
        database_path,
        staff_screening_vault_path=tmp_path / "staff-screening-vault",
        staff_screening_vault_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
    )
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _source, _settings: (_ for _ in ()).throw(
            staff_screening_vault.ScannerUnavailable("scanner diagnostic must not escape")
        ),
    )
    monkeypatch.setattr(
        staff_screening_api,
        "store_encrypted_screening_upload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled upload pipeline was entered")
        ),
    )

    application = create_app(settings)
    with TestClient(application) as client:
        candidate = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": "screening-upload-gate@example.test",
                "password": "secure-password-123",
                "first_name": "Screening",
                "last_name": "Candidate",
            },
        )
        assert candidate.status_code == 201, candidate.text
        headers = {"Authorization": f"Bearer {candidate.json()['access_token']}"}

        readable = client.get("/api/v1/marketplace/screening-documents", headers=headers)
        assert readable.status_code == 200, readable.text
        assert readable.json() == []
        candidate_state = client.get("/api/v1/marketplace/me", headers=headers)
        assert candidate_state.status_code == 200, candidate_state.text
        assert candidate_state.json()["staff_screening_evidence_upload_available"] is False

        for path in (
            "/api/v1/marketplace/screening-documents",
            f"/api/v1/marketplace/screening-documents/{UUID(int=9)}/versions",
        ):
            response = client.post(
                path,
                headers=headers,
                data={"declared_coverage": '["criminal_record_check"]'},
                files={"file": ("police-check.pdf", b"%PDF-1.4\n", "application/pdf")},
            )
            assert response.status_code == 503, response.text
            assert response.json() == {
                "detail": {"code": "staff_screening_evidence_upload_unavailable"}
            }

        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["staff_screening_evidence_upload"] == "unavailable"
        assert application.state.staff_screening_evidence_upload_available is False


def test_0030_ready_evidence_pipeline_is_reported_without_diagnostics(
    tmp_path,
    monkeypatch,
):
    database_path = _migrate(tmp_path, monkeypatch)
    settings = _settings(
        database_path,
        staff_screening_vault_path=tmp_path / "staff-screening-vault",
        staff_screening_vault_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
    )
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _source, _settings: SimpleNamespace(decision="clean"),
    )

    application = create_app(settings)
    with TestClient(application) as client:
        health = client.get("/api/v1/health")
        candidate = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": "screening-upload-ready@example.test",
                "password": "secure-password-123",
                "first_name": "Ready",
                "last_name": "Candidate",
            },
        )
        assert candidate.status_code == 201, candidate.text
        candidate_state = client.get(
            "/api/v1/marketplace/me",
            headers={"Authorization": f"Bearer {candidate.json()['access_token']}"},
        )

    assert health.status_code == 200
    assert health.json()["staff_screening_evidence_upload"] == "ready"
    assert application.state.staff_screening_evidence_upload_available is True
    assert candidate_state.status_code == 200, candidate_state.text
    assert candidate_state.json()["staff_screening_evidence_upload_available"] is True


@pytest.mark.parametrize("connection_invalidated", [False, True])
def test_screening_ciphertext_is_retained_only_when_commit_outcome_is_unknown(
    tmp_path,
    monkeypatch,
    connection_invalidated,
):
    settings = _settings(tmp_path / "caresync.db")
    stored = staff_screening_vault.StoredScreeningObject(
        storage_reference=(f"{UUID(int=1).hex}/{UUID(int=2).hex}/{UUID(int=3).hex}/v1.enc"),
        media_type="application/pdf",
        byte_size=12,
        content_sha256="a" * 64,
        ciphertext_sha256="b" * 64,
        original_filename="screening.pdf",
        encryption_key_id="local-v1",
        scanner_engine="test-scanner",
        scanner_version="test-scanner-1",
        scanned_at=datetime.now(UTC),
    )

    async def store(*_args, **_kwargs):
        return stored

    deleted: list[str] = []
    monkeypatch.setattr(staff_screening_api, "store_encrypted_screening_upload", store)
    monkeypatch.setattr(
        staff_screening_api,
        "delete_screening_object",
        lambda _settings, reference: deleted.append(reference),
    )
    monkeypatch.setattr(
        staff_screening_api,
        "_document_row",
        lambda _session, document: {"id": str(document.id)},
    )

    class CommitSession:
        def __init__(self) -> None:
            self.rollback_calls = 0

        def add(self, _value) -> None:
            return None

        def flush(self) -> None:
            return None

        def commit(self) -> None:
            raise DBAPIError(
                "COMMIT",
                {},
                RuntimeError("database response lost"),
                connection_invalidated=connection_invalidated,
            )

        def rollback(self) -> None:
            self.rollback_calls += 1

    session = CommitSession()
    operation = staff_screening_api._store_version(
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))),
        user=SimpleNamespace(id=UUID(int=1)),
        session=session,
        document=StaffScreeningDocument(
            id=UUID(int=2),
            user_id=UUID(int=1),
            status="candidate_review",
            current_version_number=1,
        ),
        version_number=1,
        coverage=["criminal_record_check"],
        file=UploadFile(BytesIO(b"%PDF-1.4\n"), filename="screening.pdf"),
    )

    if connection_invalidated:
        with pytest.raises(HTTPException) as caught:
            asyncio.run(operation)
        assert caught.value.status_code == 503
        assert caught.value.detail["code"] == "staff_screening_document_commit_unknown"
        assert caught.value.detail["document_id"] == str(UUID(int=2))
        assert caught.value.detail["version_id"]
        assert "Reload screening documents" in caught.value.detail["recovery"]
        assert session.rollback_calls == 0
        assert deleted == []
    else:
        with pytest.raises(DBAPIError):
            asyncio.run(operation)
        assert session.rollback_calls == 1
        assert deleted == [stored.storage_reference]


def _seed_snapshot_dependencies(connection: sqlite3.Connection) -> dict[str, str]:
    ids = {
        "user": "00000000000000000000000000000001",
        "organization": "00000000000000000000000000000002",
        "job": "00000000000000000000000000000003",
        "candidate": "00000000000000000000000000000004",
        "application": "00000000000000000000000000000005",
    }
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO users (id,email,password_hash,first_name,last_name,is_active) "
        "VALUES (?,?,?,?,?,1)",
        (ids["user"], "candidate@example.test", "hash", "Test", "Candidate"),
    )
    connection.execute(
        "INSERT INTO organizations (id,name,status,timezone,preferences) "
        "VALUES (?,?,'active','America/Edmonton','{}')",
        (ids["organization"], "Test Centre"),
    )
    connection.execute(
        "INSERT INTO ats_jobs "
        "(id,organization_id,title,description,employment_type,requirements,openings,"
        "status,created_by_user_id,version) VALUES (?,?,?,?,?,'[]',1,'draft',?,1)",
        (
            ids["job"],
            ids["organization"],
            "Educator",
            "Care for children",
            "full_time",
            ids["user"],
        ),
    )
    connection.execute(
        "INSERT INTO marketplace_screening_profiles "
        "(user_id,pathway,willing_to_drive,vehicle_access,candidate_provided,version) "
        "VALUES (?,'educator',0,'none',1,1)",
        (ids["user"],),
    )
    connection.execute(
        "INSERT INTO ats_job_screening_terms "
        "(job_id,organization_id,position_shape,driving_requirement,vehicle_expectation,"
        "minimum_driving_experience_months,service_windows,driving_time_paid,"
        "screening_conditions,version) "
        "VALUES (?,?,'educator_only','not_applicable','none',0,'[]',0,'[]',1)",
        (ids["job"], ids["organization"]),
    )
    connection.execute(
        "INSERT INTO ats_candidates "
        "(id,organization_id,email,first_name,last_name,status,created_by_user_id,"
        "claimed_user_id,onboarding_status,certification_verification_status,work_history) "
        "VALUES (?,?,?,?,?,'active',?,?,'complete','unverified','[]')",
        (
            ids["candidate"],
            ids["organization"],
            "candidate@example.test",
            "Test",
            "Candidate",
            ids["user"],
            ids["user"],
        ),
    )
    connection.execute(
        "INSERT INTO ats_applications "
        "(id,organization_id,job_id,candidate_id,status,version,source,"
        "candidate_consent_status) VALUES (?,?,?,?,'applied',1,"
        "'marketplace_application','accepted')",
        (ids["application"], ids["organization"], ids["job"], ids["candidate"]),
    )
    return ids


def test_sqlite_snapshot_guard_rejects_extra_json_keys(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    driver_snapshot = {
        "willing_to_drive": False,
        "licence_jurisdiction": None,
        "licence_jurisdiction_other": None,
        "licence_class": None,
        "vehicle_access": "none",
        "preferred_service_radius_km": None,
        "candidate_provided": True,
        "operational_driver_ready": False,
    }
    job_snapshot = {
        "position_shape": "educator_only",
        "driving_requirement": "not_applicable",
        "vehicle_expectation": "none",
        "required_licence_jurisdiction": None,
        "required_licence_jurisdiction_other": None,
        "required_licence_class": None,
        "minimum_driving_experience_months": 0,
        "service_area": None,
        "service_windows": [],
        "mileage_policy": None,
        "driving_time_paid": False,
        "screening_conditions": [],
    }
    with sqlite3.connect(database_path) as connection:
        ids = _seed_snapshot_dependencies(connection)
        forged = driver_snapshot | {"operational_driver_authorized": True}
        values = (
            ids["application"],
            ids["organization"],
            ids["user"],
            "educator",
            1,
            1,
            json.dumps(forged),
            json.dumps(job_snapshot),
        )
        with pytest.raises(sqlite3.IntegrityError, match="JSON shape is invalid"):
            connection.execute(
                "INSERT INTO ats_application_screening_snapshots "
                "(application_id,organization_id,candidate_user_id,pathway,"
                "screening_profile_version,job_terms_version,driver_declaration_snapshot,"
                "job_terms_snapshot) VALUES (?,?,?,?,?,?,?,?)",
                values,
            )
        connection.execute(
            "INSERT INTO ats_application_screening_snapshots "
            "(application_id,organization_id,candidate_user_id,pathway,"
            "screening_profile_version,job_terms_version,driver_declaration_snapshot,"
            "job_terms_snapshot) VALUES (?,?,?,?,?,?,?,?)",
            values[:-2] + (json.dumps(driver_snapshot), json.dumps(job_snapshot)),
        )
        offer_id = "00000000000000000000000000000006"
        connection.execute(
            "INSERT INTO ats_offers "
            "(id,organization_id,application_id,version,status,position_title,terms,"
            "created_by_user_id) VALUES (?,?,?,1,'draft','Driver','Terms',?)",
            (offer_id, ids["organization"], ids["application"], ids["user"]),
        )
        with pytest.raises(sqlite3.IntegrityError, match="exceed application disclosure"):
            connection.execute(
                "INSERT INTO ats_offer_screening_terms "
                "(offer_id,organization_id,offer_version,position_shape,"
                "driving_requirement,vehicle_expectation,required_licence_jurisdiction,"
                "required_licence_class,minimum_driving_experience_months,service_windows,"
                "mileage_policy,driving_time_paid,screening_conditions,terms_digest) "
                "VALUES (?,?,1,'driver_only','required','either','CA-AB','5',0,'[]',"
                "'Mileage policy',1,'[]',?)",
                (offer_id, ids["organization"], "a" * 64),
            )


def test_rejected_malware_scan_never_encrypts_upload(tmp_path, monkeypatch):
    settings = _settings(
        tmp_path / "caresync.db",
        staff_screening_vault_path=tmp_path / "staff-screening-vault",
    )
    monkeypatch.setattr(staff_screening_vault, "_key", lambda _settings: b"k" * 32)
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _path, _settings: SimpleNamespace(decision="rejected"),
    )
    upload = UploadFile(BytesIO(b"%PDF-1.4\nmalicious-test-object"), filename="check.pdf")
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            staff_screening_vault.store_encrypted_screening_upload(
                upload,
                settings=settings,
                user_id=__import__("uuid").UUID(int=1),
                document_id=__import__("uuid").UUID(int=2),
                version_id=__import__("uuid").UUID(int=3),
            )
        )
    assert error.value.status_code == 422
    assert error.value.detail == {"code": "screening_document_security_scan_rejected"}
    assert not list((tmp_path / "staff-screening-vault").rglob("*.enc"))
    assert not list((tmp_path / "staff-screening-vault").rglob(".screening-upload"))


def test_0030_rejects_manual_credential_edits_before_verified_candidate_can_go_stale(
    tmp_path, monkeypatch
):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        owner = client.post(
            "/api/v1/auth/register",
            json={
                "email": "screening-owner@example.test",
                "password": "secure-password-123",
                "first_name": "Screening",
                "last_name": "Owner",
                "organization_name": "Screening Centre",
            },
        )
        assert owner.status_code == 201, owner.text
        candidate = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": "verified-candidate@example.test",
                "password": "secure-password-123",
                "first_name": "Verified",
                "last_name": "Candidate",
            },
        ).json()
        personal = client.patch(
            "/api/v1/marketplace/personal-profile",
            headers={"Authorization": f"Bearer {candidate['access_token']}"},
            json={"date_of_birth": "1990-01-01", "phone": "+1 780 555 0123"},
        )
        assert personal.status_code == 200, personal.text
        candidate_user_id = UUID(candidate["user_id"])
        with application.state.database.session_factory() as session:
            owner_user = session.query(User).filter_by(email="screening-owner@example.test").one()
            organization = session.query(Organization).filter_by(name="Screening Centre").one()
            profile = session.get(MarketplaceProfile, candidate_user_id)
            assert profile is not None
            profile.certification_type = "Alberta Level 2"
            profile.certification_number = "AB-OLD"
            profile.certification_expiry_date = date(2028, 1, 1)
            profile.certification_verification_status = "unverified"
            session.add(
                AtsCandidate(
                    organization_id=organization.id,
                    email="verified-candidate@example.test",
                    first_name="Verified",
                    last_name="Candidate",
                    status="active",
                    created_by_user_id=owner_user.id,
                    claimed_user_id=candidate_user_id,
                    onboarding_status="complete",
                    certification_type="Alberta Level 2",
                    certification_number="AB-OLD",
                    certification_expiry_date=date(2028, 1, 1),
                    certification_verification_status="verified",
                    certification_verified_at=datetime.now(UTC),
                    certification_verified_by_user_id=owner_user.id,
                    work_history=[],
                )
            )
            session.commit()

        response = client.put(
            "/api/v1/marketplace/profile",
            headers={"Authorization": f"Bearer {candidate['access_token']}"},
            json={
                "city": "Edmonton",
                "headline": "Educator",
                "certification_type": "Alberta Level 3",
                "certification_number": "AB-NEW",
                "certification_expiry_date": "2029-01-01",
                "work_history": [],
                "discoverable": False,
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == ("credential_facts_require_document_workflow")
        with application.state.database.session_factory() as session:
            profile = session.get(MarketplaceProfile, candidate_user_id)
            connected = (
                session.query(AtsCandidate).filter_by(claimed_user_id=candidate_user_id).one()
            )
            assert profile is not None
            assert profile.certification_number == "AB-OLD"
            assert connected.certification_number == "AB-OLD"
            assert connected.certification_verification_status == "verified"


def test_0030_screening_profile_responses_keep_readiness_outside_driver_declaration(
    tmp_path, monkeypatch
):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        cases = (
            ("educator", {"pathway": "educator"}),
            (
                "driver",
                {
                    "pathway": "driver",
                    "driver_declaration": {
                        "willing_to_drive": True,
                        "licence_jurisdiction": "CA-AB",
                        "licence_class": "5",
                        "vehicle_access": "organization_vehicle_only",
                        "preferred_service_radius_km": 25,
                        "candidate_provided": True,
                    },
                },
            ),
        )
        for label, payload in cases:
            registration = client.post(
                "/api/v1/marketplace/auth/register",
                json={
                    "email": f"screening-{label}@example.test",
                    "password": "secure-password-123",
                    "first_name": label.title(),
                    "last_name": "Candidate",
                },
            )
            assert registration.status_code == 201, registration.text
            response = client.put(
                "/api/v1/marketplace/screening-profile",
                headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
                json=payload,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["operational_driver_ready"] is False
            assert "operational_driver_ready" not in body["driver_declaration"]


def test_same_pathway_screening_update_preserves_completed_onboarding(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        registration = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": "screening-renewal@example.test",
                "password": "secure-password-123",
                "first_name": "Renewal",
                "last_name": "Candidate",
            },
        )
        assert registration.status_code == 201, registration.text
        user_id = UUID(registration.json()["user_id"])
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        personal = client.patch(
            "/api/v1/marketplace/personal-profile",
            headers=headers,
            json={"date_of_birth": "1990-01-01", "phone": "+1 780 555 0123"},
        )
        assert personal.status_code == 200, personal.text
        initial = client.put(
            "/api/v1/marketplace/screening-profile",
            headers=headers,
            json={
                "pathway": "driver",
                "driver_declaration": {
                    "willing_to_drive": True,
                    "licence_jurisdiction": "CA-AB",
                    "licence_class": "5",
                    "vehicle_access": "organization_vehicle_only",
                    "preferred_service_radius_km": 20,
                    "candidate_provided": True,
                },
            },
        )
        assert initial.status_code == 200, initial.text
        onboarding = client.get("/api/v1/marketplace/onboarding", headers=headers)
        assert onboarding.status_code == 200, onboarding.text

        completed_at = datetime.now(UTC)
        with application.state.database.session_factory() as session:
            profile = session.get(MarketplaceProfile, user_id)
            state = session.get(MarketplaceOnboardingState, user_id)
            assert profile is not None and state is not None
            profile.onboarding_completed_at = completed_at
            state.status = "complete"
            state.current_step = "complete"
            state.completed_at = completed_at
            state.version += 1
            completed_state_version = state.version
            session.commit()

        updated = client.put(
            "/api/v1/marketplace/screening-profile",
            headers=headers,
            json={
                "pathway": "driver",
                "expected_version": initial.json()["version"],
                "driver_declaration": {
                    "willing_to_drive": True,
                    "licence_jurisdiction": "CA-AB",
                    "licence_class": "5",
                    "vehicle_access": "personal_vehicle",
                    "preferred_service_radius_km": 35,
                    "candidate_provided": True,
                },
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == initial.json()["version"] + 1
        with application.state.database.session_factory() as session:
            profile = session.get(MarketplaceProfile, user_id)
            state = session.get(MarketplaceOnboardingState, user_id)
            assert profile is not None and profile.onboarding_completed_at is not None
            assert state is not None and state.status == "complete"
            assert state.current_step == "complete"
            assert state.version == completed_state_version

        changed_pathway = client.put(
            "/api/v1/marketplace/screening-profile",
            headers=headers,
            json={
                "pathway": "educator",
                "expected_version": updated.json()["version"],
                "driver_declaration": {},
            },
        )
        assert changed_pathway.status_code == 200, changed_pathway.text
        with application.state.database.session_factory() as session:
            profile = session.get(MarketplaceProfile, user_id)
            state = session.get(MarketplaceOnboardingState, user_id)
            assert profile is not None and profile.onboarding_completed_at is None
            assert state is not None and state.status == "in_progress"
            assert state.current_step == "certificate"
