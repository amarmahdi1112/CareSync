"""Opt-in PostgreSQL 17 HTTP proof for 0030 educator provisioning.

This suite uses only an explicitly configured disposable loopback cluster. It
does not create, drop, migrate, bootstrap, or reset any database.
"""

from __future__ import annotations

import base64
import os
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.api.basic import marketplace_onboarding
from app.basic import staff_screening_vault
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
RUNTIME_ROLE = "caresync_basic_app"

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL 17 cluster",
)

Pathway = Literal["educator", "student_educator", "driver"]


def _port() -> int:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}
    assert 1 <= port <= 65535
    return port


def _url() -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=RUNTIME_ROLE,
        host=TEST_HOST,
        port=_port(),
        database=TEST_DATABASE,
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=TEST_HOST,
        database_port=_port(),
        database_user=RUNTIME_ROLE,
        database_password="",
        database_name=TEST_DATABASE,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-provisioning-secret-with-at-least-thirty-two-bytes",
        staff_screening_vault_path=tmp_path / "screening-vault",
        staff_screening_vault_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
    )


def _headers(result: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {result['access_token']}"}


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (640, 480), color=(245, 250, 255)).save(stream, format="PNG")
    return stream.getvalue()


def _educator_terms() -> dict:
    return {
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


def _driver_terms() -> dict:
    return {
        "position_shape": "driver_only",
        "driving_requirement": "required",
        "vehicle_expectation": "either",
        "required_licence_jurisdiction": "CA-AB",
        "required_licence_jurisdiction_other": None,
        "required_licence_class": "5",
        "minimum_driving_experience_months": 12,
        "service_area": "Edmonton",
        "service_windows": [],
        "mileage_policy": "Approved mileage is reimbursed.",
        "driving_time_paid": True,
        "screening_conditions": ["Operational transport authorization is separate"],
    }


def _register_owner(client: TestClient, suffix: str) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"provision-owner-{suffix}@example.test",
            "password": "secure-password-123",
            "first_name": "Provisioning",
            "last_name": "Owner",
            "organization_name": f"Provisioning Centre {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    owner = response.json()
    return owner, _headers(owner)


def _open_job(
    client: TestClient,
    owner_headers: dict[str, str],
    *,
    title: str,
    driver: bool = False,
) -> dict:
    structured = _driver_terms() if driver else _educator_terms()
    created = client.post(
        "/api/v1/ats/jobs",
        headers=owner_headers,
        json={
            "title": title,
            "description": "A consent-bound 0030 staffing position.",
            "employment_type": "full_time",
            "location": "Edmonton",
            "requirements": [],
            "openings": 1,
            **structured,
        },
    )
    assert created.status_code == 201, created.text
    opened = client.post(
        f"/api/v1/ats/jobs/{created.json()['id']}/status",
        headers=owner_headers,
        json={
            "status": "open",
            "expected_version": created.json()["version"],
            "reason": "Open PostgreSQL provisioning proof",
        },
    )
    assert opened.status_code == 200, opened.text
    return opened.json()


def _upload_police_check(
    client: TestClient,
    candidate_headers: dict[str, str],
    *,
    subject_name: str,
) -> str:
    uploaded = client.post(
        "/api/v1/marketplace/screening-documents",
        headers=candidate_headers,
        data={"declared_coverage": ('["criminal_record_check","vulnerable_sector_search"]')},
        files={"file": ("police-check.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    confirmed = client.post(
        f"/api/v1/marketplace/screening-documents/{document['id']}/confirm",
        headers=candidate_headers,
        json={
            "expected_version": document["current_version_number"],
            "subject_name": subject_name,
            "issue_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    return document["current_version"]["id"]


def _confirm_ece_certificate(
    client: TestClient,
    candidate_headers: dict[str, str],
) -> None:
    uploaded = client.post(
        "/api/v1/marketplace/onboarding/documents",
        headers=candidate_headers,
        data={"document_kind": "certificate"},
        files={"file": ("ece-certificate.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    analyzed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded.json()['id']}/analyze",
        headers=candidate_headers,
    )
    assert analyzed.status_code == 200, analyzed.text
    proposal = analyzed.json()["proposal"]
    assert proposal["required_fields_complete"] is True
    assert proposal["holder_name_mismatch"] is False
    expiry = date.today() + timedelta(days=3650)
    confirmed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded.json()['id']}/confirm-certificate",
        headers=candidate_headers,
        json={
            "certificate_type": "Alberta Level 2 ECE",
            "certificate_number": "948472",
            "expiry_date": expiry.isoformat(),
        },
    )
    assert confirmed.status_code == 200, confirmed.text


def _onboard_candidate(
    client: TestClient,
    *,
    suffix: str,
    pathway: Pathway,
) -> tuple[dict, dict[str, str], dict, str]:
    first_name = "Educator" if pathway == "educator" else pathway.split("_")[0].title()
    response = client.post(
        "/api/v1/marketplace/auth/register",
        json={
            "email": f"{pathway}-{suffix}@example.test",
            "password": "secure-password-123",
            "first_name": first_name,
            "last_name": "Candidate",
        },
    )
    assert response.status_code == 201, response.text
    candidate = response.json()
    headers = _headers(candidate)
    personal = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1990-01-01", "phone": "+1 780 555 0111"},
    )
    assert personal.status_code == 200, personal.text
    profile = client.put(
        "/api/v1/marketplace/profile",
        headers=headers,
        json={
            "city": "Edmonton",
            "headline": f"{pathway.replace('_', ' ').title()} applicant",
            "work_history": [],
            "discoverable": False,
        },
    )
    assert profile.status_code == 200, profile.text

    driver_declaration = (
        {
            "willing_to_drive": True,
            "licence_jurisdiction": "CA-AB",
            "licence_class": "5",
            "vehicle_access": "organization_vehicle_only",
            "preferred_service_radius_km": 25,
            "candidate_provided": True,
        }
        if pathway == "driver"
        else {}
    )
    screening = client.put(
        "/api/v1/marketplace/screening-profile",
        headers=headers,
        json={"pathway": pathway, "driver_declaration": driver_declaration},
    )
    assert screening.status_code == 200, screening.text
    assert screening.json()["screening_profile_complete"] is True

    document_version_id = _upload_police_check(
        client,
        headers,
        subject_name=f"{first_name} Candidate",
    )
    if pathway == "educator":
        _confirm_ece_certificate(client, headers)
    elif pathway == "student_educator":
        details = client.post(
            "/api/v1/marketplace/onboarding/student-details/confirm",
            headers=headers,
            json={
                "institution": "NorQuest College",
                "program": "Early Learning and Child Care",
                "expected_graduation_date": (date.today() + timedelta(days=730)).isoformat(),
            },
        )
        assert details.status_code == 200, details.text
    work = client.post(
        "/api/v1/marketplace/onboarding/work-history/confirm-manual",
        headers=headers,
        json={"work_history": []},
    )
    assert work.status_code == 200, work.text
    completed = client.post("/api/v1/marketplace/onboarding/complete", headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "complete"
    return candidate, headers, screening.json(), document_version_id


def _apply(
    client: TestClient,
    candidate_headers: dict[str, str],
    *,
    job_id: str,
    screening: dict,
    document_version_id: str,
) -> str:
    public = client.get(f"/api/v1/marketplace/jobs/{job_id}")
    assert public.status_code == 200, public.text
    applied = client.post(
        f"/api/v1/marketplace/jobs/{job_id}/apply",
        headers=candidate_headers,
        json={
            "screening_schema_version": "0030",
            "screening_profile_version": screening["version"],
            "acknowledged_job_terms_version": public.json()["structured_terms_version"],
            "document_version_ids": [document_version_id],
            "acknowledge_profile_snapshot": True,
            "acknowledge_screening_disclosure": True,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    return applied.json()["application_id"]


def _set_context(connection, *, user_id: str, organization_id: str) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": user_id},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": organization_id},
    )


def test_restricted_role_provisions_exactly_reviewed_educator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _path, _settings: SimpleNamespace(decision="clean"),
    )
    certificate_expiry = date.today() + timedelta(days=3650)
    monkeypatch.setattr(
        marketplace_onboarding,
        "run_local_ocr",
        lambda _path: {
            "engine": "opencv+paddleocr",
            "model": "PP-OCRv6_tiny",
            "vision": {"version": "4.10.0", "pipeline": "document-v1"},
            "lines": [
                {"text": "This confirms that", "confidence": 0.99},
                {"text": "Educator Candidate", "confidence": 0.99},
                {"text": "LEVEL 2 EARLY CHILDHOOD EDUCATOR", "confidence": 0.98},
                {"text": "Certificate Number: 948472", "confidence": 0.99},
                {"text": f"Expiry: {certificate_expiry.isoformat()}", "confidence": 0.98},
            ],
        },
    )
    settings = _settings(tmp_path)
    database = Database(settings)
    try:
        assert database.has_staff_screening_pathways() is True
        with database.engine.connect() as connection:
            identity = connection.execute(
                text("SELECT current_user, current_setting('server_version_num')::integer")
            ).one()
            assert identity[0] == RUNTIME_ROLE
            assert 170000 <= identity[1] < 180000
    finally:
        database.dispose()

    application = create_app(settings)
    with TestClient(application) as client:
        suffix = uuid4().hex
        owner, owner_headers = _register_owner(client, suffix)
        job = _open_job(
            client,
            owner_headers,
            title=f"Educator provisioning {suffix}",
        )
        candidate, candidate_headers, screening, document_version_id = _onboard_candidate(
            client, suffix=suffix, pathway="educator"
        )
        application_id = _apply(
            client,
            candidate_headers,
            job_id=job["id"],
            screening=screening,
            document_version_id=document_version_id,
        )

        workspace = client.get("/api/v1/ats/workspace", headers=owner_headers)
        assert workspace.status_code == 200, workspace.text
        application_row = next(
            row for row in workspace.json()["applications"] if row["id"] == application_id
        )
        candidate_id = application_row["candidate_id"]
        screening_stage = client.post(
            f"/api/v1/ats/applications/{application_id}/stage",
            headers=owner_headers,
            json={
                "status": "screening",
                "expected_version": application_row["version"],
                "reason": "Begin human screening review",
            },
        )
        assert screening_stage.status_code == 200, screening_stage.text

        employer_screening = client.get(
            f"/api/v1/ats/applications/{application_id}/screening",
            headers=owner_headers,
        )
        assert employer_screening.status_code == 200, employer_screening.text
        assert employer_screening.json()["snapshot"]["pathway"] == "educator"
        shares = employer_screening.json()["shares"]
        assert len(shares) == 1
        assert shares[0]["shared_version"]["id"] == document_version_id
        assert set(shares[0]["shared_version"]["declared_coverage"]) == {
            "criminal_record_check",
            "vulnerable_sector_search",
        }
        share_id = shares[0]["id"]
        viewed = client.get(
            f"/api/v1/ats/applications/{application_id}/screening-shares/{share_id}/content",
            headers=owner_headers,
        )
        assert viewed.status_code == 200, viewed.text
        assert viewed.content == _png()
        for requirement in ("criminal_record_check", "vulnerable_sector_search"):
            review = client.post(
                f"/api/v1/ats/applications/{application_id}/screening-shares/{share_id}/reviews",
                headers=owner_headers,
                json={
                    "requirement_class": requirement,
                    "decision": "accepted",
                    "reason_code": "source_reviewed",
                    "note": "Human reviewer inspected the exact shared source.",
                },
            )
            assert review.status_code == 201, review.text
            assert review.json()["decision"] == "accepted"

        credential = client.post(
            f"/api/v1/ats/candidates/{candidate_id}/certification-review",
            headers=owner_headers,
            json={
                "status": "verified",
                "reason": "Current Alberta ECE certificate inspected by employer",
            },
        )
        assert credential.status_code == 200, credential.text
        assert credential.json()["certification_verification_status"] == "verified"
        assert credential.json()["certification_expiry_date"] == certificate_expiry.isoformat()

        interview_stage = client.post(
            f"/api/v1/ats/applications/{application_id}/stage",
            headers=owner_headers,
            json={
                "status": "interview",
                "expected_version": screening_stage.json()["version"],
                "reason": "Interview completed successfully",
            },
        )
        assert interview_stage.status_code == 200, interview_stage.text
        offer = client.post(
            f"/api/v1/ats/applications/{application_id}/offers/send",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "position_title": "Early Childhood Educator",
                "start_date": (date.today() + timedelta(days=30)).isoformat(),
                "compensation": "$25/hour",
                "terms": "Educator-only employment; no transport duties.",
                "expires_at": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
                "expected_application_version": interview_stage.json()["version"],
                **_educator_terms(),
            },
        )
        assert offer.status_code == 201, offer.text
        offer = offer.json()
        assert offer["status"] == "sent"
        assert offer["position_shape"] == "educator_only"
        assert offer["driving_requirement"] == "not_applicable"
        assert len(offer["terms_digest"]) == 64

        accepted = client.post(
            f"/api/v1/marketplace/applications/{application_id}/offers/{offer['id']}/decision",
            headers=candidate_headers,
            json={
                "decision": "accepted",
                "acknowledged_offer_version": offer["version"],
                "acknowledged_terms_digest": offer["terms_digest"],
                "driver_terms_acknowledged": False,
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["application_status"] == "accepted"
        candidate_applications = client.get(
            "/api/v1/marketplace/applications", headers=candidate_headers
        )
        assert candidate_applications.status_code == 200, candidate_applications.text
        accepted_application = next(
            row for row in candidate_applications.json() if row["id"] == application_id
        )
        assert accepted_application["status"] == "accepted"

        provisioned = client.post(
            f"/api/v1/ats/applications/{application_id}/provision-staff",
            headers=owner_headers,
            json={
                "operation_id": str(uuid4()),
                "expected_version": accepted_application["version"],
            },
        )
        assert provisioned.status_code == 200, provisioned.text
        provisioned = provisioned.json()
        assert provisioned["application"]["status"] == "hired"
        assert provisioned["role_key"] == "educator"
        assert provisioned["assigned_room_ids"] == []
        assert provisioned["membership_created"] is True
        assert provisioned["user_id"] == candidate["user_id"]

        runtime = create_engine(_url())
        try:
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=owner["user"]["id"],
                    organization_id=owner["user"]["organization_id"],
                )
                exact_offer = connection.execute(
                    text(
                        "SELECT terms.position_shape,terms.driving_requirement,"
                        "ack.offer_version=terms.offer_version,"
                        "ack.terms_digest=terms.terms_digest,"
                        "ack.driver_terms_acknowledged "
                        "FROM ats_offer_screening_terms AS terms "
                        "JOIN ats_offer_acknowledgments AS ack "
                        "ON ack.organization_id=terms.organization_id "
                        "AND ack.offer_id=terms.offer_id WHERE terms.offer_id=:offer_id"
                    ),
                    {"offer_id": offer["id"]},
                ).one()
                assert exact_offer == (
                    "educator_only",
                    "not_applicable",
                    True,
                    True,
                    False,
                )
                membership = connection.execute(
                    text(
                        "SELECT role.key,membership.status,"
                        "(SELECT count(*) FROM membership_room_assignments AS assignment "
                        "WHERE assignment.organization_id=membership.organization_id "
                        "AND assignment.membership_id=membership.id "
                        "AND assignment.is_active=true) "
                        "FROM organization_memberships AS membership "
                        "JOIN roles AS role ON role.organization_id=membership.organization_id "
                        "AND role.id=membership.role_id WHERE membership.id=:membership_id"
                    ),
                    {"membership_id": provisioned["membership_id"]},
                ).one()
                assert membership == ("educator", "active", 0)
        finally:
            runtime.dispose()


@pytest.mark.parametrize(
    ("pathway", "driver_job", "expected_code"),
    [
        ("student_educator", False, "student_role_provisioning_not_available"),
        ("driver", True, "driver_role_provisioning_not_available"),
    ],
)
def test_restricted_role_blocks_pathways_without_dedicated_staff_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pathway: Pathway,
    driver_job: bool,
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _path, _settings: SimpleNamespace(decision="clean"),
    )
    settings = _settings(tmp_path)
    application = create_app(settings)
    with TestClient(application) as client:
        suffix = uuid4().hex
        _, owner_headers = _register_owner(client, suffix)
        job = _open_job(
            client,
            owner_headers,
            title=f"{pathway} provisioning boundary {suffix}",
            driver=driver_job,
        )
        candidate, candidate_headers, screening, document_version_id = _onboard_candidate(
            client,
            suffix=suffix,
            pathway=pathway,
        )
        application_id = _apply(
            client,
            candidate_headers,
            job_id=job["id"],
            screening=screening,
            document_version_id=document_version_id,
        )
        blocked = client.post(
            f"/api/v1/ats/applications/{application_id}/provision-staff",
            headers=owner_headers,
            json={"operation_id": str(uuid4()), "expected_version": 1},
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["detail"]["code"] == expected_code
        candidate_state = client.get("/api/v1/marketplace/me", headers=candidate_headers)
        assert candidate_state.status_code == 200, candidate_state.text
        assert candidate_state.json()["user_id"] == candidate["user_id"]
        assert candidate_state.json()["active_staff_memberships"] == []
