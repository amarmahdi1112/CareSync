"""Candidate-owned realtime invalidations for the cross-tenant career workspace."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, or_, select, update

from app.api.basic.common import commit_or_conflict, ensure_writable
from app.api.basic.dependencies import CompleteMarketplaceUser
from app.api.dependencies import SessionDependency
from app.basic.models import (
    AtsCandidate,
    AtsInterview,
    AtsJob,
    AtsOffer,
    MarketplaceApplicationLink,
    MarketplaceCredentialDocument,
    MarketplaceInterest,
    MarketplaceJob,
    MarketplaceRealtimeTicket,
    OrganizationMembership,
    PublicJobCatalogEvent,
    RealtimeEvent,
    StaffScreeningApplicationShare,
    User,
)
from app.basic.security import (
    create_one_time_token,
    parse_one_time_token,
    set_rls_organization,
    set_rls_user,
    token_digest_matches,
)

router = APIRouter(prefix="/marketplace/realtime", tags=["candidate marketplace realtime"])
TICKET_TTL_SECONDS = 60
HEARTBEAT_SECONDS = 15
MAX_REPLAY = 500
POLL_SECONDS = 1.0
MAX_CONNECTION_SECONDS = 1800


@router.post("/tickets", status_code=201)
def issue_ticket(
    request: Request,
    user: CompleteMarketplaceUser,
    session: SessionDependency,
):
    ensure_writable(request)
    now = datetime.now(UTC)
    row = MarketplaceRealtimeTicket(
        user_id=user.id,
        token_digest="pending",
        auth_version=user.auth_version,
        expires_at=now + timedelta(seconds=TICKET_TTL_SECONDS),
    )
    session.add(row)
    session.flush()
    opaque, row.token_digest = create_one_time_token(user.id, row.id)
    commit_or_conflict(session)
    return {
        "ticket": opaque,
        "expires_at": row.expires_at,
        "websocket_path": "/api/v1/marketplace/realtime/ws",
        "max_replay": MAX_REPLAY,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _candidate_owned_scopes(
    session,
    user_id,
    *,
    screening_enabled: bool = False,
    legacy_public_jobs: bool = False,
) -> list[tuple[object, list]]:
    """Return only identity-proven tenant invalidation predicates.

    Marketplace realtime is deliberately an invalidation stream, not a second
    read model. Every tenant-private entity must be tied to the authenticated
    candidate by an owner/claim/link key before its organization event can
    enter this stream. Public listing invalidations are read separately from
    ``public_job_catalog_events``; they never expand tenant event visibility.

    Candidate-private profile/photo/onboarding events that have no tenant are
    carried by ``UserRealtimeEvent`` on the existing user-private realtime
    channel; its cursor is intentionally not mixed with this stream's
    ``RealtimeEvent`` sequence.
    """

    set_rls_user(session, user_id)
    links = list(
        session.scalars(
            select(MarketplaceApplicationLink).where(MarketplaceApplicationLink.user_id == user_id)
        )
    )
    interests = list(
        session.scalars(
            select(MarketplaceInterest).where(MarketplaceInterest.profile_user_id == user_id)
        )
    )
    memberships = list(
        session.scalars(
            select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        )
    )
    public_jobs = (
        list(
            session.execute(
                select(
                    MarketplaceJob.organization_id,
                    MarketplaceJob.listing_id,
                )
            )
        )
        if legacy_public_jobs
        else []
    )
    credential_ids = set(
        session.scalars(
            select(MarketplaceCredentialDocument.id).where(
                MarketplaceCredentialDocument.user_id == user_id
            )
        )
    )
    apps_by_org: dict = defaultdict(set)
    interests_by_org: dict = defaultdict(set)
    memberships_by_org: dict = defaultdict(set)
    public_jobs_by_org: dict = defaultdict(set)
    for link in links:
        apps_by_org[link.organization_id].add(link.application_id)
    for interest in interests:
        interests_by_org[interest.organization_id].add(interest.id)
    for membership in memberships:
        memberships_by_org[membership.organization_id].add(membership.id)
    for organization_id, listing_id in public_jobs:
        public_jobs_by_org[organization_id].add(listing_id)
    scopes = []
    organization_ids = (
        set(apps_by_org)
        | set(interests_by_org)
        | set(memberships_by_org)
        | set(public_jobs_by_org)
    )
    for organization_id in organization_ids:
        set_rls_organization(session, organization_id)
        application_ids = apps_by_org[organization_id]
        candidate_ids = set(
            session.scalars(
                select(AtsCandidate.id).where(
                    AtsCandidate.organization_id == organization_id,
                    AtsCandidate.claimed_user_id == user_id,
                )
            )
        )
        interview_ids = (
            set(
                session.scalars(
                    select(AtsInterview.id).where(AtsInterview.application_id.in_(application_ids))
                )
            )
            if application_ids
            else set()
        )
        offer_ids = (
            set(
                session.scalars(
                    select(AtsOffer.id).where(AtsOffer.application_id.in_(application_ids))
                )
            )
            if application_ids
            else set()
        )
        screening_share_ids = (
            set(
                session.scalars(
                    select(StaffScreeningApplicationShare.id).where(
                        StaffScreeningApplicationShare.organization_id == organization_id,
                        StaffScreeningApplicationShare.application_id.in_(application_ids),
                        StaffScreeningApplicationShare.candidate_user_id == user_id,
                    )
                )
            )
            if screening_enabled and application_ids
            else set()
        )
        owned = []
        if legacy_public_jobs:
            ever_public_job_ids = set(
                session.scalars(
                    select(AtsJob.id).where(
                        AtsJob.organization_id == organization_id,
                        AtsJob.published_at.is_not(None),
                    )
                )
            )
            public_job_ids = public_jobs_by_org[organization_id] | ever_public_job_ids
            if public_job_ids:
                owned.append(
                    (RealtimeEvent.entity_type == "job")
                    & RealtimeEvent.entity_id.in_(public_job_ids)
                    & (RealtimeEvent.event_type == "job.status_changed")
                )
        if application_ids:
            owned.append(
                (RealtimeEvent.entity_type == "application")
                & RealtimeEvent.entity_id.in_(application_ids)
            )
        if interview_ids:
            owned.append(
                (RealtimeEvent.entity_type == "interview")
                & RealtimeEvent.entity_id.in_(interview_ids)
            )
        if offer_ids:
            owned.append(
                (RealtimeEvent.entity_type == "offer") & RealtimeEvent.entity_id.in_(offer_ids)
            )
        if candidate_ids:
            owned.append(
                (RealtimeEvent.entity_type == "candidate")
                & RealtimeEvent.entity_id.in_(candidate_ids)
            )
        if credential_ids:
            owned.append(
                (RealtimeEvent.entity_type == "credential")
                & RealtimeEvent.entity_id.in_(credential_ids)
            )
        if screening_share_ids:
            owned.append(
                (RealtimeEvent.entity_type == "screening_share")
                & RealtimeEvent.entity_id.in_(screening_share_ids)
            )
        membership_ids = memberships_by_org[organization_id]
        if membership_ids:
            owned.append(
                (RealtimeEvent.entity_type == "organization_membership")
                & RealtimeEvent.entity_id.in_(membership_ids)
            )
        owned.append((RealtimeEvent.entity_type == "user") & (RealtimeEvent.entity_id == user_id))
        interest_ids = interests_by_org[organization_id]
        if interest_ids:
            owned.append(
                (RealtimeEvent.entity_type == "marketplace_interest")
                & RealtimeEvent.entity_id.in_(interest_ids)
            )
        if not owned:
            continue
        scopes.append((organization_id, owned))
    return scopes


def _candidate_events(
    session,
    user_id,
    after: int,
    limit: int,
    *,
    screening_enabled: bool = False,
    public_catalog_enabled: bool = False,
) -> list[RealtimeEvent | PublicJobCatalogEvent]:
    rows: list[RealtimeEvent | PublicJobCatalogEvent] = (
        list(
            session.scalars(
                select(PublicJobCatalogEvent)
                .where(PublicJobCatalogEvent.sequence_id > after)
                .order_by(PublicJobCatalogEvent.sequence_id)
                .limit(limit)
            )
        )
        if public_catalog_enabled
        else []
    )
    seen_sequences = {item.sequence_id for item in rows}
    for organization_id, owned in _candidate_owned_scopes(
        session,
        user_id,
        screening_enabled=screening_enabled,
        legacy_public_jobs=not public_catalog_enabled,
    ):
        set_rls_organization(session, organization_id)
        rows.extend(
            item
            for item in session.scalars(
                select(RealtimeEvent)
                .where(RealtimeEvent.sequence_id > after, or_(*owned))
                .order_by(RealtimeEvent.sequence_id)
                .limit(limit)
            )
            if item.sequence_id not in seen_sequences
        )
        seen_sequences.update(item.sequence_id for item in rows)
    return sorted(rows, key=lambda item: item.sequence_id)[:limit]


def _candidate_latest_cursor(
    session,
    user_id,
    *,
    screening_enabled: bool = False,
    public_catalog_enabled: bool = False,
) -> int:
    latest = (
        int(session.scalar(select(func.max(PublicJobCatalogEvent.sequence_id))) or 0)
        if public_catalog_enabled
        else 0
    )
    for organization_id, owned in _candidate_owned_scopes(
        session,
        user_id,
        screening_enabled=screening_enabled,
        legacy_public_jobs=not public_catalog_enabled,
    ):
        set_rls_organization(session, organization_id)
        value = session.scalar(select(func.max(RealtimeEvent.sequence_id)).where(or_(*owned)))
        latest = max(latest, int(value or 0))
    return latest


def _frame(event: RealtimeEvent | PublicJobCatalogEvent) -> dict:
    public_catalog_event = isinstance(event, PublicJobCatalogEvent)
    return {
        "type": "event",
        "cursor": event.sequence_id,
        "event": {
            "id": str(event.event_id if public_catalog_event else event.id),
            "type": event.event_type,
            "entity_type": "job" if public_catalog_event else event.entity_type,
            "entity_id": str(
                event.listing_id if public_catalog_event else event.entity_id
            )
            if (public_catalog_event or event.entity_id)
            else None,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": {"scope": "candidate_hiring"},
        },
    }


@router.websocket("/ws")
async def marketplace_realtime_websocket(websocket: WebSocket, ticket: str, after: int = 0):
    await websocket.accept()
    if after < 0:
        await websocket.close(code=4408, reason="Invalid realtime cursor")
        return
    try:
        user_id, ticket_id, digest = parse_one_time_token(ticket)
    except ValueError:
        await websocket.close(code=4401, reason="Invalid realtime ticket")
        return
    database = websocket.app.state.database
    screening_enabled = bool(
        getattr(websocket.app.state, "staff_screening_pathways_enabled", False)
    )
    public_catalog_enabled = bool(
        getattr(websocket.app.state, "public_job_catalog_outbox_enabled", False)
    )
    ticket_auth_version = None
    with database.session_factory() as session:
        set_rls_user(session, user_id)
        stored = session.scalar(
            select(MarketplaceRealtimeTicket)
            .where(
                MarketplaceRealtimeTicket.user_id == user_id,
                MarketplaceRealtimeTicket.id == ticket_id,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            stored is None
            or not token_digest_matches(stored.token_digest, digest)
            or stored.consumed_at is not None
            or _aware(stored.expires_at) <= now
        ):
            await websocket.close(code=4401, reason="Expired or consumed realtime ticket")
            return
        active_user = session.scalar(
            select(User.id).where(
                User.id == user_id,
                User.is_active.is_(True),
                User.auth_version == stored.auth_version,
            )
        )
        if active_user is None:
            await websocket.close(code=4403, reason="Marketplace realtime access was revoked")
            return
        ticket_auth_version = stored.auth_version
        consumed = session.execute(
            update(MarketplaceRealtimeTicket)
            .where(
                MarketplaceRealtimeTicket.id == ticket_id,
                MarketplaceRealtimeTicket.user_id == user_id,
                MarketplaceRealtimeTicket.token_digest == digest,
                MarketplaceRealtimeTicket.consumed_at.is_(None),
                MarketplaceRealtimeTicket.expires_at > now,
            )
            .values(consumed_at=now)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            session.rollback()
            await websocket.close(code=4401, reason="Expired or consumed realtime ticket")
            return
        session.commit()
    with database.session_factory() as session:
        replay = _candidate_events(
            session,
            user_id,
            after,
            MAX_REPLAY + 1,
            screening_enabled=screening_enabled,
            public_catalog_enabled=public_catalog_enabled,
        )
        latest = _candidate_latest_cursor(
            session,
            user_id,
            screening_enabled=screening_enabled,
            public_catalog_enabled=public_catalog_enabled,
        )
    if len(replay) > MAX_REPLAY:
        await websocket.send_json(
            {
                "type": "reset_required",
                "reason": "replay_limit_exceeded",
                "requested_after": after,
                "resume_from": after,
                "latest_available_cursor": latest,
                "cursor_must_not_advance": True,
                "max_replay": MAX_REPLAY,
            }
        )
        await websocket.close(code=4408, reason="Realtime replay limit exceeded")
        return
    if after > latest:
        await websocket.send_json(
            {
                "type": "reset_required",
                "reason": "cursor_ahead",
                "requested_after": after,
                "resume_from": latest,
                "latest_available_cursor": latest,
                "cursor_must_not_advance": True,
                "max_replay": MAX_REPLAY,
            }
        )
        await websocket.close(code=4408, reason="Realtime cursor is ahead of this stream")
        return
    cursor = after
    await websocket.send_json(
        {
            "type": "ready",
            "user_id": str(user_id),
            "cursor": cursor,
            "cursor_semantics": "last_emitted_event; persist only after local refresh succeeds",
            "heartbeat_seconds": HEARTBEAT_SECONDS,
            "max_replay": MAX_REPLAY,
        }
    )
    started = datetime.now(UTC)
    last_heartbeat = started
    try:
        while (datetime.now(UTC) - started).total_seconds() < MAX_CONNECTION_SECONDS:
            with database.session_factory() as session:
                set_rls_user(session, user_id)
                active_user = session.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.is_active.is_(True),
                        User.auth_version == ticket_auth_version,
                    )
                )
            if active_user is None:
                await websocket.close(code=4403, reason="Marketplace realtime access was revoked")
                return
            if replay:
                pending, replay = replay, []
            else:
                with database.session_factory() as session:
                    pending = _candidate_events(
                        session,
                        user_id,
                        cursor,
                        100,
                        screening_enabled=screening_enabled,
                        public_catalog_enabled=public_catalog_enabled,
                    )
            for event in pending:
                await websocket.send_json(_frame(event))
                cursor = event.sequence_id
            now = datetime.now(UTC)
            if (now - last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
                await websocket.send_json(
                    {"type": "heartbeat", "cursor": cursor, "server_time": now.isoformat()}
                )
                last_heartbeat = now
            await asyncio.sleep(POLL_SECONDS)
        await websocket.close(code=1000, reason="Realtime connection rotation")
    except WebSocketDisconnect:
        return
