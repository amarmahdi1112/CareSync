"""Executable lifecycle proofs for the 0030 candidate-consent boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from alembic import command
from app.basic.models import (
    AtsApplication,
    AtsApplicationScreeningSnapshot,
    AtsCandidate,
    AtsInterview,
    AtsJob,
    AtsJobScreeningTerms,
    AtsOffer,
    AtsOfferScreeningTerms,
    MarketplaceApplicationLink,
    MarketplaceScreeningProfile,
    OrganizationMembership,
    StaffScreeningApplicationShare,
    StaffScreeningCandidateConfirmation,
    StaffScreeningDocument,
    StaffScreeningDocumentVersion,
    User,
)
from app.basic.staff_screening_terms import (
    default_structured_terms,
    driver_declaration_snapshot,
    offer_terms_digest,
    structured_terms_from_model,
)
from app.core.config import Settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "secure-password-123"
ALBERTA_TIMEZONE = ZoneInfo("America/Edmonton")


def _alberta_today() -> date:
    return datetime.now(ALBERTA_TIMEZONE).date()


def _migrate(tmp_path: Path, monkeypatch, revision: str) -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def _app(database_path: Path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="screening-lifecycle-secret-with-at-least-thirty-two-bytes",
    )
    return create_app(settings)


def _register_owner(client: TestClient, email: str):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Owner",
            "last_name": "User",
            "organization_name": "Lifecycle Centre",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register_candidate(client: TestClient, email: str):
    response = client.post(
        "/api/v1/marketplace/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Candidate",
            "last_name": "User",
        },
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    personal = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1995-05-20", "phone": "+1 780 555 0199"},
    )
    assert personal.status_code == 200, personal.text
    return headers


def _seed_0030_application(
    application,
    *,
    owner_email: str,
    candidate_email: str,
    status: str,
    title: str,
    interview_status: str | None = None,
    with_share: bool = False,
    with_sent_offer: bool = False,
) -> dict[str, UUID | None]:
    now = datetime.now(UTC)
    with application.state.database.session_factory() as session:
        owner = session.scalar(select(User).where(User.email == owner_email))
        candidate_user = session.scalar(select(User).where(User.email == candidate_email))
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == owner.id,
                OrganizationMembership.status == "active",
            )
        )
        profile = session.get(MarketplaceScreeningProfile, candidate_user.id)
        if profile is None:
            profile = MarketplaceScreeningProfile(
                user_id=candidate_user.id,
                pathway="educator",
                willing_to_drive=False,
                licence_jurisdiction=None,
                licence_jurisdiction_other=None,
                licence_class=None,
                vehicle_access="none",
                preferred_service_radius_km=None,
                candidate_provided=True,
                version=1,
            )
            session.add(profile)
        job = AtsJob(
            organization_id=membership.organization_id,
            title=title,
            description="Lifecycle transition proof",
            employment_type="full_time",
            requirements=[],
            openings=1,
            status="open",
            published_at=now,
            created_by_user_id=owner.id,
            version=1,
        )
        candidate = session.scalar(
            select(AtsCandidate).where(
                AtsCandidate.organization_id == membership.organization_id,
                AtsCandidate.email == candidate_email,
            )
        )
        if candidate is None:
            candidate = AtsCandidate(
                organization_id=membership.organization_id,
                email=candidate_email,
                first_name="Candidate",
                last_name="User",
                status="active",
                created_by_user_id=owner.id,
                claimed_user_id=candidate_user.id,
                onboarding_status="complete",
                certification_verification_status="unverified",
                work_history=[],
            )
            session.add(candidate)
        session.add(job)
        session.flush()

        terms = AtsJobScreeningTerms(
            job_id=job.id,
            organization_id=membership.organization_id,
            **default_structured_terms(),
            version=1,
        )
        ats_application = AtsApplication(
            organization_id=membership.organization_id,
            job_id=job.id,
            candidate_id=candidate.id,
            status=status,
            version=1,
            source="marketplace_application",
            candidate_consent_status="accepted",
        )
        session.add_all((terms, ats_application))
        session.flush()

        snapshot = AtsApplicationScreeningSnapshot(
            application_id=ats_application.id,
            organization_id=membership.organization_id,
            candidate_user_id=candidate_user.id,
            pathway=profile.pathway,
            screening_profile_version=profile.version,
            job_terms_version=terms.version,
            driver_declaration_snapshot=driver_declaration_snapshot(profile),
            job_terms_snapshot=structured_terms_from_model(terms),
            candidate_acknowledged_at=now,
        )
        link = MarketplaceApplicationLink(
            user_id=candidate_user.id,
            organization_id=membership.organization_id,
            listing_id=job.id,
            application_id=ats_application.id,
            listing_title=job.title,
            organization_name="Lifecycle Centre",
            listing_location="Edmonton",
            employment_type=job.employment_type,
            published_at=now,
        )
        session.add_all((snapshot, link))
        session.flush()

        interview = None
        if interview_status is not None:
            interview = AtsInterview(
                organization_id=membership.organization_id,
                application_id=ats_application.id,
                scheduled_at=now + timedelta(days=7),
                timezone="America/Edmonton",
                location_or_link="https://meet.example.test/lifecycle",
                status=interview_status,
                created_by_user_id=owner.id,
                candidate_proposed_at=(
                    now + timedelta(days=8) if interview_status == "candidate_proposed" else None
                ),
                candidate_proposal_note=(
                    "Candidate-proposed time" if interview_status == "candidate_proposed" else None
                ),
            )
            session.add(interview)

        share = None
        if with_share:
            document = StaffScreeningDocument(
                user_id=candidate_user.id,
                status="uploaded",
                current_version_number=1,
            )
            session.add(document)
            session.flush()
            version_id = uuid4()
            version = StaffScreeningDocumentVersion(
                id=version_id,
                document_id=document.id,
                user_id=candidate_user.id,
                version_number=1,
                declared_coverage=[
                    "criminal_record_check",
                    "vulnerable_sector_search",
                ],
                original_filename="police-check.pdf",
                media_type="application/pdf",
                byte_size=128,
                content_sha256="a" * 64,
                ciphertext_sha256="b" * 64,
                storage_reference=(
                    f"{candidate_user.id.hex}/{document.id.hex}/{version_id.hex}/v1.enc"
                ),
                encryption_key_id="test-key-v1",
            )
            session.add(version)
            session.flush()
            session.add(
                StaffScreeningCandidateConfirmation(
                    document_version_id=version.id,
                    user_id=candidate_user.id,
                    subject_name="Candidate User",
                    account_name_snapshot="Candidate User",
                    subject_name_match=True,
                    mismatch_resolution="matched",
                    issue_date=_alberta_today(),
                    expiry_date=_alberta_today() + timedelta(days=365),
                    candidate_confirmed_at=now,
                )
            )
            session.flush()
            document.status = "confirmed"
            session.flush()
            share = StaffScreeningApplicationShare(
                candidate_user_id=candidate_user.id,
                organization_id=membership.organization_id,
                application_id=ats_application.id,
                document_version_id=version.id,
                screening_profile_version=profile.version,
                shared_at=now,
            )
            session.add(share)

        offer = None
        if with_sent_offer:
            offer = AtsOffer(
                organization_id=membership.organization_id,
                application_id=ats_application.id,
                version=1,
                status="sent",
                position_title="Educator",
                compensation="$25/hour",
                terms="Lifecycle test terms",
                sent_at=now,
                created_by_user_id=owner.id,
            )
            session.add(offer)
            session.flush()
            structured = default_structured_terms()
            session.add(
                AtsOfferScreeningTerms(
                    offer_id=offer.id,
                    organization_id=membership.organization_id,
                    offer_version=offer.version,
                    **structured,
                    terms_digest=offer_terms_digest(offer, structured, candidate_id=candidate.id),
                )
            )

        session.commit()
        return {
            "application": ats_application.id,
            "interview": interview.id if interview is not None else None,
            "share": share.id if share is not None else None,
            "offer": offer.id if offer is not None else None,
        }


def test_0030_withdrawal_and_terminal_states_are_fail_closed(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, "head")
    application = _app(database_path)
    owner_email = "lifecycle-owner@example.test"
    candidate_email = "lifecycle-candidate@example.test"
    with TestClient(application) as client:
        owner_headers = _register_owner(client, owner_email)
        candidate_headers = _register_candidate(client, candidate_email)

        legacy = client.post(
            "/api/v1/candidate/hiring/withdraw",
            headers=candidate_headers,
            json={"token": "x" * 32},
        )
        assert legacy.status_code == 404, legacy.text

        withdrawn = _seed_0030_application(
            application,
            owner_email=owner_email,
            candidate_email=candidate_email,
            status="screening",
            title="Withdrawal lifecycle",
            interview_status="requested",
            with_share=True,
        )
        manager_attempt = client.post(
            f"/api/v1/ats/applications/{withdrawn['application']}/stage",
            headers=owner_headers,
            json={
                "status": "withdrawn",
                "expected_version": 1,
                "reason": "Manager cannot withdraw candidate consent",
            },
        )
        assert manager_attempt.status_code == 403, manager_attempt.text

        candidate_withdrawal = client.post(
            f"/api/v1/marketplace/applications/{withdrawn['application']}/withdraw",
            headers=candidate_headers,
        )
        assert candidate_withdrawal.status_code == 200, candidate_withdrawal.text
        assert candidate_withdrawal.json()["status"] == "withdrawn"

        candidate_resurrection = client.post(
            f"/api/v1/marketplace/interviews/{withdrawn['interview']}/decision",
            headers=candidate_headers,
            json={"decision": "confirmed"},
        )
        assert candidate_resurrection.status_code == 409, candidate_resurrection.text

        rejected = _seed_0030_application(
            application,
            owner_email=owner_email,
            candidate_email=candidate_email,
            status="rejected",
            title="Rejected lifecycle",
            interview_status="candidate_proposed",
            with_sent_offer=True,
        )
        proposal_resurrection = client.post(
            f"/api/v1/ats/marketplace/interviews/{rejected['interview']}/proposal-decision",
            headers=owner_headers,
            json={"decision": "accepted"},
        )
        assert proposal_resurrection.status_code == 409, proposal_resurrection.text

        stale_offer = client.post(
            f"/api/v1/ats/offers/{rejected['offer']}/decision",
            headers=owner_headers,
            json={"decision": "withdrawn", "reason": "Stale terminal offer"},
        )
        assert stale_offer.status_code == 409, stale_offer.text

    with application.state.database.session_factory() as session:
        withdrawn_application = session.get(AtsApplication, withdrawn["application"])
        withdrawn_interview = session.get(AtsInterview, withdrawn["interview"])
        revoked_share = session.get(StaffScreeningApplicationShare, withdrawn["share"])
        rejected_application = session.get(AtsApplication, rejected["application"])
        rejected_interview = session.get(AtsInterview, rejected["interview"])
        unchanged_offer = session.get(AtsOffer, rejected["offer"])
        assert withdrawn_application.status == "withdrawn"
        assert withdrawn_application.version == 2
        assert withdrawn_interview.status == "requested"
        assert revoked_share.revoked_at is not None
        assert rejected_application.status == "rejected"
        assert rejected_application.version == 1
        assert rejected_interview.status == "candidate_proposed"
        assert unchanged_offer.status == "sent"
        assert unchanged_offer.terminal_at is None


def test_employer_withdrawn_offer_allows_new_atomic_immutable_versions(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, "head")
    application = _app(database_path)
    owner_email = "corrected-offer-owner@example.test"
    candidate_email = "corrected-offer-candidate@example.test"

    with TestClient(application) as client:
        owner_headers = _register_owner(client, owner_email)
        _register_candidate(client, candidate_email)
        seeded = _seed_0030_application(
            application,
            owner_email=owner_email,
            candidate_email=candidate_email,
            status="offer",
            title="Corrected offer lifecycle",
            with_sent_offer=True,
        )

        first_withdrawal = client.post(
            f"/api/v1/ats/offers/{seeded['offer']}/decision",
            headers=owner_headers,
            json={
                "decision": "withdrawn",
                "reason": "Correct the original employment terms",
            },
        )
        assert first_withdrawal.status_code == 200, first_withdrawal.text
        assert first_withdrawal.json()["status"] == "withdrawn"

        corrected = client.post(
            f"/api/v1/ats/applications/{seeded['application']}/offers/send",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_application_version": 2,
                "position_title": "Corrected Educator",
                "compensation": "$26/hour",
                "terms": "Corrected employment terms",
            },
        )
        assert corrected.status_code == 201, corrected.text
        assert corrected.json()["version"] == 2
        assert corrected.json()["status"] == "sent"
        corrected_offer_id = UUID(corrected.json()["id"])

        second_withdrawal = client.post(
            f"/api/v1/ats/offers/{corrected_offer_id}/decision",
            headers=owner_headers,
            json={
                "decision": "withdrawn",
                "reason": "Issue one final corrected version",
            },
        )
        assert second_withdrawal.status_code == 200, second_withdrawal.text
        assert second_withdrawal.json()["status"] == "withdrawn"

        final_offer = client.post(
            f"/api/v1/ats/applications/{seeded['application']}/offers/send",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_application_version": 4,
                "position_title": "Final Corrected Educator",
                "compensation": "$27/hour",
                "terms": "Final corrected employment terms",
            },
        )
        assert final_offer.status_code == 201, final_offer.text
        assert final_offer.json()["version"] == 3
        assert final_offer.json()["status"] == "sent"
        final_offer_id = UUID(final_offer.json()["id"])

    with application.state.database.session_factory() as session:
        retained_first = session.get(AtsOffer, seeded["offer"])
        retained_second = session.get(AtsOffer, corrected_offer_id)
        current_offer = session.get(AtsOffer, final_offer_id)
        retained_application = session.get(AtsApplication, seeded["application"])
        assert retained_first.status == "withdrawn"
        assert retained_first.version == 1
        assert retained_second.status == "withdrawn"
        assert retained_second.version == 2
        assert current_offer.status == "sent"
        assert current_offer.version == 3
        assert retained_application.status == "offer"
        assert retained_application.version == 5


def test_0028_does_not_remount_retired_private_hiring_routes(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch, "0028_childcare_command_spine")
    application = _app(database_path)
    with TestClient(application) as client:
        owner_headers = _register_owner(client, "legacy-owner@example.test")
        candidate_headers = _register_candidate(client, "legacy-candidate@example.test")
        invited = client.post(
            "/api/v1/ats/invitations",
            headers=owner_headers,
            json={},
        )
        claimed = client.post(
            "/api/v1/candidate/hiring/claim",
            headers=candidate_headers,
            json={"token": "x" * 32},
        )
        legacy_withdrawal = client.post(
            "/api/v1/candidate/hiring/withdraw",
            headers=candidate_headers,
            json={"token": "x" * 32},
        )
        assert invited.status_code == 404
        assert claimed.status_code == 404
        assert legacy_withdrawal.status_code == 404
