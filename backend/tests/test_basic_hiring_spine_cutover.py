"""Canonical hiring cutover, state ownership, and retained-data preflight proofs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.basic.hiring_lifecycle import (
    APPLICATION_STATUSES,
    INTERVIEW_STATUSES,
    JOB_STATUSES,
    OFFER_STATUSES,
    HiringLifecycleViolation,
    application_targets,
    require_application_transition,
    require_candidate_interview_decision,
    require_candidate_offer_decision,
    require_employer_offer_withdrawal,
    require_employer_proposal_decision,
    require_interview_request,
    require_job_transition,
    require_offer_creation,
    require_provisioning,
)
from app.basic.hiring_repository import (
    CanonicalHiringCutoverBlocked,
    assert_canonical_hiring_cutover_ready,
)
from app.basic.models import (
    AtsApplication,
    AtsCandidate,
    AtsCandidateInvitation,
    AtsJob,
    AtsOffer,
    BasicBase,
)
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"

EXPECTED_APPLICATION_TRANSITIONS = {
    "employer": {
        ("applied", "screening"),
        ("applied", "rejected"),
        ("screening", "interview"),
        ("screening", "rejected"),
        ("interview", "screening"),
        ("interview", "rejected"),
        ("offer", "rejected"),
    },
    "candidate": {
        ("applied", "withdrawn"),
        ("screening", "withdrawn"),
        ("interview", "withdrawn"),
        ("offer", "accepted"),
        ("offer", "rejected"),
        ("offer", "withdrawn"),
    },
}

EXPECTED_JOB_TRANSITIONS = {
    ("draft", "open"),
    ("draft", "closed"),
    ("open", "paused"),
    ("open", "closed"),
    ("paused", "open"),
    ("paused", "closed"),
}


@pytest.mark.parametrize(
    ("actor", "current", "target"),
    list(
        product(
            ("employer", "candidate"),
            sorted(APPLICATION_STATUSES),
            sorted(APPLICATION_STATUSES),
        )
    ),
)
def test_application_actor_state_matrix_is_exhaustive(actor, current, target):
    expected = (current, target) in EXPECTED_APPLICATION_TRANSITIONS[actor]
    assert (target in application_targets(actor, current)) is expected
    if expected:
        require_application_transition(actor, current, target)
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_application_transition(actor, current, target)
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("current", "target"),
    list(product(sorted(JOB_STATUSES), repeat=2)),
)
def test_job_state_matrix_is_exhaustive(current, target):
    if (current, target) in EXPECTED_JOB_TRANSITIONS:
        require_job_transition(current, target)
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_job_transition(current, target)
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("application_status", "offer_status", "decision"),
    list(product(sorted(APPLICATION_STATUSES), sorted(OFFER_STATUSES), ("accepted", "declined"))),
)
def test_candidate_offer_actor_state_matrix_is_exhaustive(
    application_status,
    offer_status,
    decision,
):
    expected = application_status == "offer" and offer_status == "sent"
    if expected:
        require_candidate_offer_decision(application_status, offer_status, decision)
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_candidate_offer_decision(application_status, offer_status, decision)
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("application_status", "offer_status"),
    list(product(sorted(APPLICATION_STATUSES), sorted(OFFER_STATUSES))),
)
def test_employer_offer_actor_state_matrix_is_exhaustive(application_status, offer_status):
    expected = application_status == "offer" and offer_status == "sent"
    if expected:
        require_employer_offer_withdrawal(application_status, offer_status)
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_employer_offer_withdrawal(application_status, offer_status)
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("application_status", "interview_status", "decision"),
    list(
        product(
            sorted(APPLICATION_STATUSES),
            sorted(INTERVIEW_STATUSES),
            ("confirmed", "declined", "proposed"),
        )
    ),
)
def test_candidate_interview_actor_state_matrix_is_exhaustive(
    application_status,
    interview_status,
    decision,
):
    expected = (
        application_status in {"screening", "interview"}
        and interview_status == "requested"
    )
    if expected:
        require_candidate_interview_decision(
            application_status,
            interview_status,
            decision,
        )
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_candidate_interview_decision(
                application_status,
                interview_status,
                decision,
            )
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("application_status", "interview_status", "has_proposal", "decision"),
    list(
        product(
            sorted(APPLICATION_STATUSES),
            sorted(INTERVIEW_STATUSES),
            (False, True),
            ("accepted", "declined", "countered"),
        )
    ),
)
def test_employer_interview_actor_state_matrix_is_exhaustive(
    application_status,
    interview_status,
    has_proposal,
    decision,
):
    expected = (
        application_status == "screening"
        and interview_status == "candidate_proposed"
        and has_proposal
    )
    if expected:
        require_employer_proposal_decision(
            application_status,
            interview_status,
            has_candidate_proposal=has_proposal,
            decision=decision,
        )
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_employer_proposal_decision(
                application_status,
                interview_status,
                has_candidate_proposal=has_proposal,
                decision=decision,
            )
        assert caught.value.status_code == 409


@pytest.mark.parametrize(
    ("application_status", "consent_status"),
    list(product(sorted(APPLICATION_STATUSES), ("requested", "accepted", "declined"))),
)
def test_interview_request_state_and_consent_matrix_is_exhaustive(
    application_status,
    consent_status,
):
    expected = application_status in {"applied", "screening"} and consent_status == "accepted"
    if expected:
        require_interview_request(application_status, consent_status)
    else:
        with pytest.raises(HiringLifecycleViolation) as caught:
            require_interview_request(application_status, consent_status)
        assert caught.value.status_code == 409


@pytest.mark.parametrize("application_status", sorted(APPLICATION_STATUSES))
def test_offer_creation_and_provisioning_state_matrix_is_exhaustive(application_status):
    if application_status in {"interview", "offer"}:
        require_offer_creation(application_status)
    else:
        with pytest.raises(HiringLifecycleViolation):
            require_offer_creation(application_status)

    if application_status == "accepted":
        require_provisioning(application_status)
    else:
        with pytest.raises(HiringLifecycleViolation):
            require_provisioning(application_status)


def _cutover_app(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="cutover-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return application


def test_cutover_preflight_fails_closed_with_deterministic_blocker_counts(tmp_path):
    application = _cutover_app(tmp_path)
    with TestClient(application) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "cutover-owner@example.test",
                "password": PASSWORD,
                "first_name": "Cutover",
                "last_name": "Owner",
                "organization_name": "Cutover Centre",
            },
        )
        assert registration.status_code == 201, registration.text
        owner_id = UUID(registration.json()["user"]["id"])
        organization_id = UUID(registration.json()["user"]["organization_id"])

    with application.state.database.session_factory() as session:
        job = AtsJob(
            organization_id=organization_id,
            title="Retained private flow",
            description="Preflight fixture",
            employment_type="full_time",
            requirements=[],
            created_by_user_id=owner_id,
        )
        candidate = AtsCandidate(
            organization_id=organization_id,
            email="unclaimed@example.test",
            first_name="Unclaimed",
            last_name="Candidate",
            created_by_user_id=owner_id,
        )
        session.add_all((job, candidate))
        session.flush()
        application_row = AtsApplication(
            organization_id=organization_id,
            job_id=job.id,
            candidate_id=candidate.id,
            source="private_invitation",
        )
        session.add(application_row)
        session.flush()
        invitation = AtsCandidateInvitation(
            organization_id=organization_id,
            application_id=application_row.id,
            token_digest="0" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=14),
            created_by_user_id=owner_id,
        )
        offer = AtsOffer(
            organization_id=organization_id,
            application_id=application_row.id,
            version=1,
            status="draft",
            position_title="Educator",
            terms="Preflight fixture",
            created_by_user_id=owner_id,
        )
        session.add_all((invitation, offer))
        session.flush()

        with pytest.raises(CanonicalHiringCutoverBlocked) as caught:
            assert_canonical_hiring_cutover_ready(session)
        assert str(caught.value) == (
            "Canonical hiring cutover blocked: "
            "pending_unclaimed_invitations=1, "
            "private_invitation_applications=1, "
            "draft_offers=1"
        )

        invitation.revoked_at = datetime.now(UTC)
        application_row.source = "marketplace_application"
        offer.status = "withdrawn"
        offer.terminal_at = datetime.now(UTC)
        session.flush()
        report = assert_canonical_hiring_cutover_ready(session)
        assert report.ready is True
