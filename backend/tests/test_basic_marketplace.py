from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.basic.marketplace_realtime import (
    _candidate_events,
    _candidate_latest_cursor,
)
from app.basic.models import (
    AtsCandidate,
    AtsJob,
    BasicBase,
    MarketplaceCredentialDocument,
    MarketplaceDocumentAnalysis,
    MarketplaceJob,
    PublicJobCatalogEvent,
    RealtimeEvent,
    User,
)
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="marketplace-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _owner(client, email, organization):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Owner",
            "last_name": "User",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def _candidate(client, email):
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
    data = response.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    personal = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1995-05-20", "phone": "+1 780 555 0199"},
    )
    assert personal.status_code == 200, personal.text
    return data, headers


def _complete_student(client, headers):
    selected = client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=headers,
        json={"candidate_type": "student"},
    )
    assert selected.status_code == 200, selected.text
    details = client.post(
        "/api/v1/marketplace/onboarding/student-details/confirm",
        headers=headers,
        json={
            "institution": "NorQuest College",
            "program": "Early Learning and Child Care",
            "expected_graduation_date": "2028-06-30",
        },
    )
    assert details.status_code == 200, details.text
    completed = client.post("/api/v1/marketplace/onboarding/complete", headers=headers)
    assert completed.status_code == 200, completed.text


def _listing(client, application, headers, title="Educator"):
    created = client.post(
        "/api/v1/ats/jobs",
        headers=headers,
        json={
            "title": title,
            "description": "Support children and families",
            "employment_type": "full_time",
            "location": "Edmonton",
            "requirements": [],
        },
    ).json()
    opened = client.post(
        f"/api/v1/ats/jobs/{created['id']}/status",
        headers=headers,
        json={"status": "open", "expected_version": created["version"], "reason": "Recruiting"},
    )
    assert opened.status_code == 200, opened.text
    row = opened.json()
    with application.state.database.session_factory() as session:
        session.add(
            MarketplaceJob(
                listing_id=UUID(row["id"]),
                organization_id=UUID(row["organization_id"]),
                title=row["title"],
                description=row["description"],
                employment_type=row["employment_type"],
                location=row["location"],
                openings=row["openings"],
                organization_name="Test Centre",
                published_at=datetime.fromisoformat(row["published_at"].replace("Z", "+00:00")),
            )
        )
        session.commit()
    return row


def test_global_marketplace_apply_consent_offer_and_staff_transition(tmp_path):
    client, application = _client(tmp_path)
    owner, owner_headers = _owner(client, "market-owner@example.test", "Market Centre")
    job = _listing(client, application, owner_headers)
    candidate, candidate_headers = _candidate(client, "global-candidate@example.test")
    profile = client.put(
        "/api/v1/marketplace/profile",
        headers=candidate_headers,
        json={
            "city": "Edmonton",
            "headline": "Experienced educator",
            "bio": "Child-led practice",
            "certification_type": "Alberta Level 2",
            "certification_number": "AB-22",
            "certification_expiry_date": "2028-01-01",
            "work_history": [{"employer": "Previous Centre", "role": "Educator"}],
            "discoverable": True,
        },
    )
    assert profile.status_code == 200 and profile.json()["discoverable"] is True
    _complete_student(client, candidate_headers)
    assert client.get(f"/api/v1/marketplace/jobs/{job['id']}").status_code == 200
    first = client.post(f"/api/v1/marketplace/jobs/{job['id']}/apply", headers=candidate_headers)
    assert first.status_code == 200, first.text
    retry = client.post(f"/api/v1/marketplace/jobs/{job['id']}/apply", headers=candidate_headers)
    assert (
        retry.status_code == 200
        and retry.json()["application_id"] == first.json()["application_id"]
        and retry.json()["created"] is False
    )
    application_id = first.json()["application_id"]
    application_history = client.get("/api/v1/marketplace/applications", headers=candidate_headers)
    assert application_history.status_code == 200, application_history.text
    assert application_history.json()[0]["job"] == {
        "id": job["id"],
        "title": "Educator",
        "organization_name": "Test Centre",
        "location": "Edmonton",
        "employment_type": "full_time",
        "published_at": job["published_at"],
    }
    workspace = client.get("/api/v1/ats/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    incoming = next(
        item for item in workspace.json()["applications"] if item["id"] == application_id
    )
    assert (
        incoming["source"] == "marketplace_application"
        and incoming["candidate_consent_status"] == "accepted"
    )
    projected = next(
        item for item in workspace.json()["candidates"] if item["id"] == incoming["candidate_id"]
    )
    assert projected["candidate_type"] == "student"
    assert projected["institution"] == "NorQuest College"
    assert projected["program"] == "Early Learning and Child Care"
    assert projected["expected_graduation_date"] == "2028-06-30"
    assert projected["phone"] == "+1 780 555 0199"
    search = client.get("/api/v1/ats/marketplace/candidates?city=Edmonton", headers=owner_headers)
    assert search.status_code == 200 and search.json()[0]["user_id"] == candidate["user_id"]
    assert "phone" not in search.json()[0] and "date_of_birth" not in search.json()[0]
    interview = client.post(
        f"/api/v1/ats/marketplace/applications/{application_id}/interviews",
        headers=owner_headers,
        json={
            "scheduled_at": "2026-08-01T16:00:00Z",
            "location_or_link": "https://meet.example.test/interview",
        },
    )
    assert interview.status_code == 201, interview.text
    assert interview.json()["timezone"] == "America/Edmonton"
    candidate_inbox = client.get("/api/v1/notifications", headers=candidate_headers)
    assert candidate_inbox.status_code == 200, candidate_inbox.text
    assert candidate_inbox.json()["items"][0]["title"] == "Interview requested"
    confirmed = client.post(
        f"/api/v1/marketplace/interviews/{interview.json()['id']}/decision",
        headers=candidate_headers,
        json={"decision": "confirmed"},
    )
    assert confirmed.status_code == 200 and confirmed.json()["application_status"] == "interview"
    owner_inbox = client.get("/api/v1/notifications", headers=owner_headers)
    assert owner_inbox.status_code == 200, owner_inbox.text
    assert owner_inbox.json()["items"][0]["title"] == "Candidate responded to interview"
    current = next(
        item
        for item in client.get("/api/v1/ats/workspace", headers=owner_headers).json()[
            "applications"
        ]
        if item["id"] == application_id
    )
    pre_offer_projection = client.get(
        "/api/v1/marketplace/applications",
        headers=candidate_headers,
    )
    assert pre_offer_projection.status_code == 200, pre_offer_projection.text
    assert pre_offer_projection.json()[0]["offers"] == []
    operation_id = "70000000-0000-0000-0000-000000000001"
    atomic_payload = {
        "client_operation_id": operation_id,
        "position_title": "Educator",
        "start_date": "2026-09-01",
        "compensation": "$25/hour",
        "terms": "Full-time",
        "expected_application_version": current["version"],
    }
    sent = client.post(
        f"/api/v1/ats/applications/{application_id}/offers/send",
        headers=owner_headers,
        json=atomic_payload,
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["client_operation_id"] == operation_id

    retry = client.post(
        f"/api/v1/ats/applications/{application_id}/offers/send",
        headers=owner_headers,
        json=atomic_payload,
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["id"] == sent.json()["id"]
    assert retry.json()["version"] == sent.json()["version"]
    conflicting_retry = client.post(
        f"/api/v1/ats/applications/{application_id}/offers/send",
        headers=owner_headers,
        json={**atomic_payload, "terms": "A different command"},
    )
    assert conflicting_retry.status_code == 409, conflicting_retry.text
    published_versions = [
        item
        for item in client.get("/api/v1/ats/workspace", headers=owner_headers).json()["offers"]
        if item["application_id"] == application_id and item["status"] == "sent"
    ]
    assert [item["id"] for item in published_versions] == [sent.json()["id"]]
    accepted = client.post(
        f"/api/v1/marketplace/applications/{application_id}/offers/{sent.json()['id']}/decision",
        headers=candidate_headers,
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200 and accepted.json()["application_status"] == "accepted"
    accepted_app = next(
        item
        for item in client.get("/api/v1/ats/workspace", headers=owner_headers).json()[
            "applications"
        ]
        if item["id"] == application_id
    )
    provisioned = client.post(
        f"/api/v1/ats/applications/{application_id}/provision-staff",
        headers=owner_headers,
        json={
            "operation_id": "90000000-0000-0000-0000-000000000001",
            "expected_version": accepted_app["version"],
        },
    )
    assert provisioned.status_code == 200 and provisioned.json()["membership_created"] is True
    me = client.get("/api/v1/marketplace/me", headers=candidate_headers)
    assert me.status_code == 200
    assert (
        me.json()["active_staff_memberships"][0]["membership_id"]
        == provisioned.json()["membership_id"]
    )
    assert me.json()["staff_session_uses_same_access_token"] is True
    preferences = client.put(
        "/api/v1/notifications/preferences",
        headers=candidate_headers,
        json={
            "hiring_enabled": True,
            "credential_enabled": False,
            "assignment_enabled": True,
            "operations_enabled": True,
        },
    )
    assert preferences.status_code == 200, preferences.text
    assert preferences.json()["credential_enabled"] is False
    assert preferences.json()["system_notifications_always_enabled"] is True

    with application.state.database.session_factory() as session:
        listing = session.get(MarketplaceJob, UUID(job["id"]))
        session.delete(listing)
        session.commit()
    assert client.get(f"/api/v1/marketplace/jobs/{job['id']}").status_code == 404
    retained = client.get("/api/v1/marketplace/applications", headers=candidate_headers)
    assert retained.status_code == 200, retained.text
    assert retained.json()[0]["job"]["title"] == "Educator"
    assert retained.json()[0]["job"]["organization_name"] == "Test Centre"


def test_employer_interest_creates_no_application_until_candidate_consents(tmp_path):
    client, application = _client(tmp_path)
    _, owner_headers = _owner(client, "interest-owner@example.test", "Interest Centre")
    job = _listing(client, application, owner_headers, "OSC Educator")
    candidate, candidate_headers = _candidate(client, "interest-candidate@example.test")
    client.put(
        "/api/v1/marketplace/profile",
        headers=candidate_headers,
        json={
            "city": "Calgary",
            "headline": "OSC educator",
            "bio": None,
            "certification_type": None,
            "certification_number": None,
            "certification_expiry_date": None,
            "work_history": [],
            "discoverable": True,
        },
    )
    _complete_student(client, candidate_headers)
    before = len(client.get("/api/v1/ats/workspace", headers=owner_headers).json()["applications"])
    interest = client.post(
        "/api/v1/ats/marketplace/interests",
        headers=owner_headers,
        json={
            "profile_user_id": candidate["user_id"],
            "job_id": job["id"],
            "message": "Would you like to interview?",
        },
    )
    assert interest.status_code == 201, interest.text
    assert (
        len(client.get("/api/v1/ats/workspace", headers=owner_headers).json()["applications"])
        == before
    )
    accepted = client.post(
        f"/api/v1/marketplace/interests/{interest.json()['id']}/decision",
        headers=candidate_headers,
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200 and accepted.json()["application_id"]
    apps = client.get("/api/v1/ats/workspace", headers=owner_headers).json()["applications"]
    linked = next(item for item in apps if item["id"] == accepted.json()["application_id"])
    assert (
        linked["source"] == "employer_interest" and linked["candidate_consent_status"] == "accepted"
    )


def test_candidate_realtime_and_interview_time_negotiation(tmp_path):
    client, application = _client(tmp_path)
    _, owner_headers = _owner(client, "live-owner@example.test", "Live Centre")
    job = _listing(client, application, owner_headers, "Live Educator")
    candidate, candidate_headers = _candidate(client, "live-candidate@example.test")
    assert (
        client.put(
            "/api/v1/marketplace/profile",
            headers=candidate_headers,
            json={
                "city": "Edmonton",
                "headline": "Student educator",
                "bio": None,
                "certification_type": None,
                "certification_number": None,
                "certification_expiry_date": None,
                "work_history": [],
                "discoverable": False,
            },
        ).status_code
        == 200
    )
    _complete_student(client, candidate_headers)
    applied = client.post(f"/api/v1/marketplace/jobs/{job['id']}/apply", headers=candidate_headers)
    assert applied.status_code == 200, applied.text
    application_id = applied.json()["application_id"]
    request = client.post(
        f"/api/v1/ats/marketplace/applications/{application_id}/interviews",
        headers=owner_headers,
        json={
            "scheduled_at": "2026-08-01T16:00:00Z",
            "location_or_link": "https://meet.example.test/live",
        },
    )
    assert request.status_code == 201, request.text
    with application.state.database.session_factory() as session:
        session.add(
            RealtimeEvent(
                organization_id=UUID(applied.json()["organization_id"]),
                event_type="marketplace.interview_requested",
                entity_type="interview",
                entity_id=UUID(request.json()["id"]),
                payload={"source": "ats_event"},
            )
        )
        session.commit()
    issued = client.post("/api/v1/marketplace/realtime/tickets", headers=candidate_headers)
    assert issued.status_code == 201, issued.text
    with client.websocket_connect(
        f"/api/v1/marketplace/realtime/ws?ticket={issued.json()['ticket']}&after=0"
    ) as websocket:
        assert websocket.receive_json()["type"] == "ready"
        observed = []
        observed_cursor = 0
        while "marketplace.interview_requested" not in observed:
            frame = websocket.receive_json()
            if frame["type"] == "event":
                assert frame["event"]["payload"] == {"scope": "candidate_hiring"}
                observed.append(frame["event"]["type"])
                observed_cursor = frame["cursor"]
        assert "marketplace.interview_requested" in observed
    ahead = client.post("/api/v1/marketplace/realtime/tickets", headers=candidate_headers).json()
    requested_cursor = observed_cursor + 100000
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect(
            f"/api/v1/marketplace/realtime/ws?ticket={ahead['ticket']}&after={requested_cursor}"
        ) as websocket,
    ):
        reset = websocket.receive_json()
        assert reset["type"] == "reset_required"
        assert reset["reason"] == "cursor_ahead"
        assert reset["requested_after"] == requested_cursor
        assert reset["resume_from"] == reset["latest_available_cursor"]
        assert reset["latest_available_cursor"] < requested_cursor
        assert reset["cursor_must_not_advance"] is True
        websocket.receive_json()
    assert closed.value.code == 4408
    proposed = client.post(
        f"/api/v1/marketplace/interviews/{request.json()['id']}/decision",
        headers=candidate_headers,
        json={
            "decision": "proposed",
            "proposed_at": "2026-08-02T18:30:00Z",
            "note": "Available after work.",
        },
    )
    assert proposed.status_code == 200, proposed.text
    workspace = client.get("/api/v1/ats/workspace", headers=owner_headers).json()
    interview = next(item for item in workspace["interviews"] if item["id"] == request.json()["id"])
    assert interview["status"] == "candidate_proposed"
    assert interview["candidate_proposal_note"] == "Available after work."
    accepted = client.post(
        f"/api/v1/ats/marketplace/interviews/{interview['id']}/proposal-decision",
        headers=owner_headers,
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "confirmed"
    candidate_app = next(
        item
        for item in client.get("/api/v1/marketplace/applications", headers=candidate_headers).json()
        if item["id"] == application_id
    )
    assert candidate_app["status"] == "interview"
    assert candidate_app["interviews"][0]["scheduled_at"].startswith("2026-08-02T18:30:00")
    live_ticket = client.post(
        "/api/v1/marketplace/realtime/tickets", headers=candidate_headers
    ).json()
    with (
        pytest.raises(WebSocketDisconnect) as revoked,
        client.websocket_connect(
            f"/api/v1/marketplace/realtime/ws?ticket={live_ticket['ticket']}&after=0"
        ) as websocket,
    ):
        assert websocket.receive_json()["type"] == "ready"
        with application.state.database.session_factory() as session:
            user = session.get(User, UUID(candidate["user_id"]))
            user.auth_version += 1
            session.commit()
        while True:
            websocket.receive_json()
    assert revoked.value.code == 4403


def test_candidate_realtime_expands_only_public_and_exact_owned_entities(tmp_path):
    client, application = _client(tmp_path)
    _, first_owner_headers = _owner(client, "scope-owner-a@example.test", "Scope A")
    _, second_owner_headers = _owner(client, "scope-owner-b@example.test", "Scope B")
    first_job = _listing(client, application, first_owner_headers, "Public A")
    second_job = _listing(client, application, second_owner_headers, "Public B")
    draft_job = client.post(
        "/api/v1/ats/jobs",
        headers=first_owner_headers,
        json={
            "title": "Private draft",
            "description": "This draft must never enter the candidate stream",
            "employment_type": "full_time",
            "location": "Edmonton",
            "requirements": [],
        },
    )
    assert draft_job.status_code == 201, draft_job.text

    first_candidate, first_headers = _candidate(client, "scope-candidate-a@example.test")
    second_candidate, second_headers = _candidate(client, "scope-candidate-b@example.test")
    for headers in (first_headers, second_headers):
        profile = client.put(
            "/api/v1/marketplace/profile",
            headers=headers,
            json={
                "city": "Edmonton",
                "headline": "Student educator",
                "bio": None,
                "certification_type": None,
                "certification_number": None,
                "certification_expiry_date": None,
                "work_history": [],
                "discoverable": False,
            },
        )
        assert profile.status_code == 200, profile.text
    _complete_student(client, first_headers)
    _complete_student(client, second_headers)
    first_application = client.post(
        f"/api/v1/marketplace/jobs/{first_job['id']}/apply",
        headers=first_headers,
    )
    second_application = client.post(
        f"/api/v1/marketplace/jobs/{first_job['id']}/apply",
        headers=second_headers,
    )
    assert first_application.status_code == 200, first_application.text
    assert second_application.status_code == 200, second_application.text

    first_user_id = UUID(first_candidate["user_id"])
    second_user_id = UUID(second_candidate["user_id"])
    first_organization_id = UUID(first_job["organization_id"])
    second_organization_id = UUID(second_job["organization_id"])
    now = datetime.now(UTC)
    with application.state.database.session_factory() as session:
        first_candidate_id = session.scalar(
            select(AtsCandidate.id).where(
                AtsCandidate.organization_id == first_organization_id,
                AtsCandidate.claimed_user_id == first_user_id,
            )
        )
        second_candidate_id = session.scalar(
            select(AtsCandidate.id).where(
                AtsCandidate.organization_id == first_organization_id,
                AtsCandidate.claimed_user_id == second_user_id,
            )
        )
        assert first_candidate_id is not None
        assert second_candidate_id is not None

        analysis = MarketplaceDocumentAnalysis(
            user_id=first_user_id,
            document_kind="certificate",
            status="confirmed",
            mime_type="image/jpeg",
            file_size_bytes=1,
            page_count=1,
            content_sha256="a" * 64,
            raw_document_retained=False,
        )
        session.add(analysis)
        session.flush()
        credential = MarketplaceCredentialDocument(
            user_id=first_user_id,
            analysis_id=analysis.id,
            version_number=1,
            content_type="image/jpeg",
            image_bytes=b"x",
            size_bytes=1,
            sha256="a" * 64,
            status="confirmed",
            is_current=True,
            holder_name="Candidate User",
            certificate_type="Alberta Level 1",
            certificate_number="SAFE-1",
            confirmed_at=now,
        )
        session.add(credential)
        session.flush()

        # Emulate the projection trigger after a public listing is closed.
        # The candidate still owns an application link, and AtsJob.published_at
        # remains the durable proof that its status invalidation is public.
        first_public_projection = session.get(MarketplaceJob, UUID(first_job["id"]))
        assert first_public_projection is not None
        session.delete(first_public_projection)
        first_job_source = session.get(AtsJob, UUID(first_job["id"]))
        assert first_job_source is not None and first_job_source.published_at is not None
        first_job_source.status = "closed"
        first_job_source.closed_at = now

        visible = [
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="job.status_changed",
                entity_type="job",
                entity_id=UUID(first_job["id"]),
            ),
            RealtimeEvent(
                organization_id=second_organization_id,
                event_type="job.status_changed",
                entity_type="job",
                entity_id=UUID(second_job["id"]),
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="candidate.updated",
                entity_type="candidate",
                entity_id=first_candidate_id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="user.updated",
                entity_type="user",
                entity_id=first_user_id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="marketplace.credential_updated",
                entity_type="credential",
                entity_id=credential.id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="application.stage_changed",
                entity_type="application",
                entity_id=UUID(first_application.json()["application_id"]),
            ),
        ]
        excluded = [
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="job.status_changed",
                entity_type="job",
                entity_id=UUID(draft_job.json()["id"]),
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="candidate.updated",
                entity_type="candidate",
                entity_id=second_candidate_id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="marketplace.profile_updated",
                entity_type="marketplace_profile",
                entity_id=first_user_id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="marketplace.profile_updated",
                entity_type="marketplace_profile",
                entity_id=second_user_id,
            ),
            RealtimeEvent(
                organization_id=first_organization_id,
                event_type="application.stage_changed",
                entity_type="application",
                entity_id=UUID(second_application.json()["application_id"]),
            ),
        ]
        session.add_all([*visible, *excluded])
        session.flush()
        session.add_all(
            [
                PublicJobCatalogEvent(
                    sequence_id=visible[0].sequence_id,
                    event_id=visible[0].id,
                    listing_id=UUID(first_job["id"]),
                    event_type="job.status_changed",
                    public_status="closed",
                    listing_version=first_job_source.version,
                    occurred_at=visible[0].occurred_at,
                ),
                PublicJobCatalogEvent(
                    sequence_id=visible[1].sequence_id,
                    event_id=visible[1].id,
                    listing_id=UUID(second_job["id"]),
                    event_type="job.status_changed",
                    public_status="open",
                    listing_version=second_job["version"],
                    occurred_at=visible[1].occurred_at,
                ),
            ]
        )
        session.commit()
        visible_ids = {row.id for row in visible}
        excluded_ids = {row.id for row in excluded}
        visible_cursor = max(row.sequence_id for row in visible)

    with application.state.database.session_factory() as session:
        events = _candidate_events(
            session,
            first_user_id,
            0,
            100,
            public_catalog_enabled=True,
        )
        candidate_event_ids = {
            row.event_id if isinstance(row, PublicJobCatalogEvent) else row.id for row in events
        }
        assert candidate_event_ids == visible_ids
        assert not (candidate_event_ids & excluded_ids)
        assert (
            _candidate_latest_cursor(
                session,
                first_user_id,
                public_catalog_enabled=True,
            )
            == visible_cursor
        )
        assert all(
            row.sequence_id > visible_cursor
            for row in _candidate_events(
                session,
                first_user_id,
                visible_cursor,
                100,
                public_catalog_enabled=True,
            )
        )
