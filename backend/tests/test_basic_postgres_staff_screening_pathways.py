"""Opt-in PostgreSQL 17 proof for the 0030 screening/RLS boundary.

The suite never provisions or drops a database. It runs only against an
explicit disposable loopback port and refuses the retained CareSync ports.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.api.basic.staff_screening import application_screening_reviews_accepted
from app.basic import staff_screening_vault
from app.basic.models import AtsApplication
from app.basic.security import set_rls_organization, set_rls_user
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
ADMIN_USER = os.getenv("BASIC_POSTGRES_TEST_ADMIN_USER", "postgres")
RUNTIME_ROLE = "caresync_basic_app"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)

TRIGGER_FUNCTIONS = (
    "sync_marketplace_job_screening_from_terms()",
    "sync_marketplace_job_screening_from_listing()",
    "caresync_0030_immutable_fact()",
    "caresync_0030_coverage_guard()",
    "caresync_0030_snapshot_guard()",
    "caresync_0030_share_insert_guard()",
    "caresync_0030_review_insert_guard()",
    "caresync_0030_document_guard()",
    "caresync_0030_offer_terms_insert_guard()",
    "caresync_0030_offer_terms_guard()",
    "caresync_0030_share_guard()",
    "caresync_0030_offer_ack_guard()",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}
    assert 1 <= port <= 65535
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _settings(tmp_path: Path) -> Settings:
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
        jwt_secret="postgres-screening-test-secret-with-at-least-thirty-two-bytes",
        staff_screening_vault_path=tmp_path / "screening-vault",
        staff_screening_vault_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
    )


def _headers(result: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {result['access_token']}"}


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 32), color=(245, 250, 255)).save(stream, format="PNG")
    return stream.getvalue()


def _job_payload(title: str) -> dict:
    return {
        "title": title,
        "description": "Transport support with employer verification before any assignment.",
        "employment_type": "part_time",
        "location": "Edmonton",
        "requirements": [],
        "openings": 1,
        "position_shape": "driver_only",
        "driving_requirement": "required",
        "vehicle_expectation": "either",
        "required_licence_jurisdiction": "CA-AB",
        "required_licence_class": "5",
        "minimum_driving_experience_months": 12,
        "service_area": "Edmonton",
        "service_windows": [],
        "mileage_policy": "Approved mileage is reimbursed after employer verification.",
        "driving_time_paid": True,
        "screening_conditions": ["No driving until operational authorization is complete"],
    }


def _set_context(connection, *, user_id: UUID, organization_id: UUID | None) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": str(user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": "" if organization_id is None else str(organization_id)},
    )


def _run_bootstrap(*, check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(PSQL),
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            TEST_HOST,
            "-p",
            str(TEST_PORT),
            "-U",
            ADMIN_USER,
            "-d",
            TEST_DATABASE,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _downgrade_attempt() -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": TEST_HOST,
            "DATABASE_PORT": str(TEST_PORT),
            "DATABASE_USER": ADMIN_USER,
            "DATABASE_PASSWORD": "",
            "DATABASE_NAME": TEST_DATABASE,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "0029D_release_checkout_writer",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_candidate_open_terms_apply_manager_scope_and_boundary_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        staff_screening_vault,
        "scan_private_object",
        lambda _path, _settings: SimpleNamespace(
            decision="clean",
            scanner_engine="test-scanner",
            scanner_version="1",
        ),
    )
    settings = _settings(tmp_path)
    database = Database(settings)
    assert database.has_staff_screening_pathways() is True
    database.dispose()

    application = create_app(settings)
    with TestClient(application) as client:
        suffix = uuid4().hex
        owner_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"screening-owner-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Screening",
                "last_name": "Owner",
                "organization_name": f"Screening Centre {suffix}",
            },
        )
        assert owner_response.status_code == 201, owner_response.text
        owner = owner_response.json()
        owner_headers = _headers(owner)

        open_job = client.post(
            "/api/v1/ats/jobs", headers=owner_headers, json=_job_payload("Open driver")
        )
        assert open_job.status_code == 201, open_job.text
        open_job = open_job.json()
        opened = client.post(
            f"/api/v1/ats/jobs/{open_job['id']}/status",
            headers=owner_headers,
            json={
                "status": "open",
                "expected_version": open_job["version"],
                "reason": "Public RLS proof",
            },
        )
        assert opened.status_code == 200, opened.text
        open_job = opened.json()

        draft_job = client.post(
            "/api/v1/ats/jobs", headers=owner_headers, json=_job_payload("Draft driver")
        )
        assert draft_job.status_code == 201, draft_job.text
        draft_job = draft_job.json()

        closed_job = client.post(
            "/api/v1/ats/jobs", headers=owner_headers, json=_job_payload("Closed driver")
        )
        assert closed_job.status_code == 201, closed_job.text
        closed_job = closed_job.json()
        closed_open = client.post(
            f"/api/v1/ats/jobs/{closed_job['id']}/status",
            headers=owner_headers,
            json={
                "status": "open",
                "expected_version": closed_job["version"],
                "reason": "Open before closure",
            },
        )
        assert closed_open.status_code == 200, closed_open.text
        closed = client.post(
            f"/api/v1/ats/jobs/{closed_job['id']}/status",
            headers=owner_headers,
            json={
                "status": "closed",
                "expected_version": closed_open.json()["version"],
                "reason": "No longer public",
            },
        )
        assert closed.status_code == 200, closed.text

        candidate_response = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": f"screening-candidate-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Rls",
                "last_name": "Candidate",
            },
        )
        assert candidate_response.status_code == 201, candidate_response.text
        candidate = candidate_response.json()
        candidate_headers = _headers(candidate)
        personal = client.patch(
            "/api/v1/marketplace/personal-profile",
            headers=candidate_headers,
            json={"date_of_birth": "1990-01-01", "phone": "+1 780 555 0111"},
        )
        assert personal.status_code == 200, personal.text
        profile = client.put(
            "/api/v1/marketplace/profile",
            headers=candidate_headers,
            json={
                "city": "Edmonton",
                "headline": "Childcare driver",
                "work_history": [{"employer": "Prior Centre", "role": "Driver"}],
                "discoverable": False,
            },
        )
        assert profile.status_code == 200, profile.text
        screening_profile = client.put(
            "/api/v1/marketplace/screening-profile",
            headers=candidate_headers,
            json={
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
        )
        assert screening_profile.status_code == 200, screening_profile.text
        screening_profile = screening_profile.json()
        assert screening_profile["operational_driver_ready"] is False

        upload = client.post(
            "/api/v1/marketplace/screening-documents",
            headers=candidate_headers,
            data={"declared_coverage": ('["criminal_record_check","vulnerable_sector_search"]')},
            files={"file": ("police-check.png", _png(), "image/png")},
        )
        assert upload.status_code == 201, upload.text
        document = upload.json()
        document_version_id = document["current_version"]["id"]
        confirmation = client.post(
            f"/api/v1/marketplace/screening-documents/{document['id']}/confirm",
            headers=candidate_headers,
            json={
                "expected_version": 1,
                "subject_name": "Rls Candidate",
                "issue_date": "2026-01-01",
                "expiry_date": "2030-01-01",
            },
        )
        assert confirmation.status_code == 200, confirmation.text
        work_history = client.post(
            "/api/v1/marketplace/onboarding/work-history/confirm-manual",
            headers=candidate_headers,
            json={"work_history": [{"employer": "Prior Centre", "role": "Driver"}]},
        )
        assert work_history.status_code == 200, work_history.text
        complete = client.post("/api/v1/marketplace/onboarding/complete", headers=candidate_headers)
        assert complete.status_code == 200, complete.text

        runtime = create_engine(_url(RUNTIME_ROLE))
        try:
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=UUID(candidate["user_id"]),
                    organization_id=None,
                )
                visible = set(
                    connection.execute(
                        text(
                            "SELECT job_id FROM ats_job_screening_terms "
                            "WHERE job_id=ANY(CAST(:ids AS uuid[]))"
                        ),
                        {
                            "ids": [
                                open_job["id"],
                                draft_job["id"],
                                closed_job["id"],
                            ]
                        },
                    ).scalars()
                )
                assert visible == {UUID(open_job["id"])}
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=UUID(owner["user"]["id"]),
                    organization_id=UUID(owner["user"]["organization_id"]),
                )
                visible = set(
                    connection.execute(
                        text(
                            "SELECT job_id FROM ats_job_screening_terms "
                            "WHERE job_id=ANY(CAST(:ids AS uuid[]))"
                        ),
                        {
                            "ids": [
                                open_job["id"],
                                draft_job["id"],
                                closed_job["id"],
                            ]
                        },
                    ).scalars()
                )
                assert visible == {
                    UUID(open_job["id"]),
                    UUID(draft_job["id"]),
                    UUID(closed_job["id"]),
                }
        finally:
            runtime.dispose()

        public_job = client.get(f"/api/v1/marketplace/jobs/{open_job['id']}")
        assert public_job.status_code == 200, public_job.text
        assert public_job.json()["vehicle_expectation"] == "either"
        apply = client.post(
            f"/api/v1/marketplace/jobs/{open_job['id']}/apply",
            headers=candidate_headers,
            json={
                "screening_schema_version": "0030",
                "screening_profile_version": screening_profile["version"],
                "acknowledged_job_terms_version": public_job.json()["structured_terms_version"],
                "document_version_ids": [document_version_id],
                "acknowledge_profile_snapshot": True,
                "acknowledge_screening_disclosure": True,
            },
        )
        assert apply.status_code == 200, apply.text
        application_id = UUID(apply.json()["application_id"])

        admin = create_engine(_url(ADMIN_USER))
        try:
            with admin.connect() as connection:
                facts = connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM ats_applications WHERE id=:application_id),"
                        "(SELECT count(*) FROM ats_application_screening_snapshots "
                        " WHERE application_id=:application_id),"
                        "(SELECT count(*) FROM staff_screening_application_shares "
                        " WHERE application_id=:application_id AND revoked_at IS NULL),"
                        "(SELECT count(*) FROM marketplace_application_links "
                        " WHERE application_id=:application_id)"
                    ),
                    {"application_id": application_id},
                ).one()
                assert facts == (1, 1, 1, 1)
        finally:
            admin.dispose()

        employer = client.get(
            f"/api/v1/ats/applications/{application_id}/screening",
            headers=owner_headers,
        )
        assert employer.status_code == 200, employer.text
        share_id = employer.json()["shares"][0]["id"]
        viewed = client.get(
            f"/api/v1/ats/applications/{application_id}/screening-shares/{share_id}/content",
            headers=owner_headers,
        )
        assert viewed.status_code == 200, viewed.text
        for requirement in ("criminal_record_check", "vulnerable_sector_search"):
            review = client.post(
                f"/api/v1/ats/applications/{application_id}/screening-shares/{share_id}/reviews",
                headers=owner_headers,
                json={
                    "requirement_class": requirement,
                    "decision": "accepted",
                    "reason_code": "source_reviewed",
                },
            )
            assert review.status_code == 201, review.text

        # Provisioning acquires the application write lock first, then uses
        # lock-only manager policies to stabilize the active share/document
        # rows without granting the manager mutation authority.
        with application.state.database.session_factory() as session:
            set_rls_user(session, UUID(owner["user"]["id"]))
            set_rls_organization(session, UUID(owner["user"]["organization_id"]))
            locked_application = session.scalar(
                select(AtsApplication).where(AtsApplication.id == application_id).with_for_update()
            )
            assert locked_application is not None
            assert application_screening_reviews_accepted(
                session,
                organization_id=UUID(owner["user"]["organization_id"]),
                application_id=application_id,
                lock_for_provisioning=True,
            )
            session.rollback()

        runtime = create_engine(_url(RUNTIME_ROLE))
        try:
            for statement, identifier in (
                (
                    "UPDATE staff_screening_application_shares "
                    "SET screening_profile_version=screening_profile_version WHERE id=:id",
                    share_id,
                ),
                (
                    "UPDATE staff_screening_documents SET status=status WHERE id=:id",
                    document["id"],
                ),
            ):
                with pytest.raises(DBAPIError), runtime.begin() as connection:
                    _set_context(
                        connection,
                        user_id=UUID(owner["user"]["id"]),
                        organization_id=UUID(owner["user"]["organization_id"]),
                    )
                    connection.execute(text(statement), {"id": identifier})
        finally:
            runtime.dispose()

        other_owner = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"other-owner-{suffix}@example.test",
                "password": "secure-password-123",
                "first_name": "Other",
                "last_name": "Owner",
                "organization_name": f"Other Centre {suffix}",
            },
        )
        assert other_owner.status_code == 201, other_owner.text
        cross_tenant = client.get(
            f"/api/v1/ats/applications/{application_id}/screening",
            headers=_headers(other_owner.json()),
        )
        assert cross_tenant.status_code == 404

    admin = create_engine(_url(ADMIN_USER))
    try:
        with admin.connect() as connection:
            hardened = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class WHERE oid=ANY(CAST(:tables AS regclass[])) "
                    "AND relrowsecurity AND relforcerowsecurity"
                ),
                {
                    "tables": [
                        "ats_job_screening_terms",
                        "marketplace_screening_profiles",
                        "ats_application_screening_snapshots",
                        "ats_offer_screening_terms",
                        "staff_screening_documents",
                        "staff_screening_document_versions",
                        "staff_screening_candidate_confirmations",
                        "staff_screening_application_shares",
                        "staff_screening_employer_reviews",
                        "ats_offer_acknowledgments",
                    ]
                },
            ).scalar_one()
            assert hardened == 10
            function_acl = connection.execute(
                text(
                    "SELECT expected.signature,"
                    "COALESCE(has_function_privilege(:runtime,procedure.oid,'EXECUTE'),false),"
                    "EXISTS (SELECT 1 FROM aclexplode(COALESCE("
                    "procedure.proacl,acldefault('f',procedure.proowner))) AS acl "
                    "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') "
                    "FROM unnest(CAST(:signatures AS text[])) AS expected(signature) "
                    "LEFT JOIN pg_proc AS procedure ON procedure.oid="
                    "to_regprocedure('public.' || expected.signature)"
                ),
                {"runtime": RUNTIME_ROLE, "signatures": list(TRIGGER_FUNCTIONS)},
            ).all()
            assert all(not runtime and not public for _name, runtime, public in function_acl)
            policy_expression = connection.execute(
                text(
                    "SELECT pg_get_expr(polqual,polrelid) FROM pg_policy "
                    "WHERE polrelid='ats_job_screening_terms'::regclass "
                    "AND polname='ats_job_screening_terms_read'"
                )
            ).scalar_one()
        with admin.begin() as connection:
            connection.execute(
                text(
                    "ALTER POLICY ats_job_screening_terms_read "
                    "ON ats_job_screening_terms USING (false)"
                )
            )

        drifted = Database(settings)
        try:
            with pytest.raises(RuntimeError, match="Partial or drifted 0030"):
                drifted.has_staff_screening_pathways()
        finally:
            drifted.dispose()
        refused = _run_bootstrap(check=False)
        assert refused.returncode != 0
        assert "complete 0030 staff-screening guard and RLS set" in refused.stderr

        with admin.begin() as connection:
            connection.execute(
                text(
                    "ALTER POLICY ats_job_screening_terms_read "
                    f"ON ats_job_screening_terms USING ({policy_expression})"
                )
            )
        _run_bootstrap(check=True)
        repaired = Database(settings)
        try:
            assert repaired.has_staff_screening_pathways() is True
        finally:
            repaired.dispose()

        downgrade = _downgrade_attempt()
        assert downgrade.returncode != 0
        assert "downgrade refused" in (downgrade.stdout + downgrade.stderr).lower()
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0030_staff_screening_paths"
            )
    finally:
        admin.dispose()
