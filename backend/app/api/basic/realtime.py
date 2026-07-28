"""Authenticated, resumable WebSocket delivery backed only by the database outbox."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select, update

from app.api.basic.common import commit_in_context, ensure_writable
from app.api.basic.dependencies import BasicContextDependency
from app.api.dependencies import SessionDependency
from app.basic.models import OrganizationMembership, RealtimeEvent, RealtimeTicket, User
from app.basic.security import (
    create_one_time_token,
    parse_one_time_token,
    set_rls_organization,
    set_rls_user,
    token_digest_matches,
)

router = APIRouter(prefix="/realtime", tags=["basic realtime"])
TICKET_TTL_SECONDS = 60
HEARTBEAT_SECONDS = 15
MAX_REPLAY = 500
POLL_SECONDS = 1.0
SEND_TIMEOUT_SECONDS = 5
MAX_CONNECTION_SECONDS = 1800


@router.post("/tickets", status_code=201)
def issue_ticket(
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
):
    ensure_writable(request)
    now = datetime.now(UTC)
    ticket = RealtimeTicket(
        organization_id=context.organization.id,
        user_id=context.user.id,
        membership_id=context.membership.id,
        token_digest="pending",
        auth_version=context.user.auth_version,
        expires_at=now + timedelta(seconds=TICKET_TTL_SECONDS),
    )
    session.add(ticket)
    session.flush()
    opaque, ticket.token_digest = create_one_time_token(context.organization.id, ticket.id)
    commit_in_context(session, context)
    return {
        "ticket": opaque,
        "expires_at": ticket.expires_at,
        "websocket_path": "/api/v1/realtime/ws",
        "max_replay": MAX_REPLAY,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        await asyncio.wait_for(websocket.send_json(payload), SEND_TIMEOUT_SECONDS)
    except TimeoutError:
        await websocket.close(code=1013, reason="Realtime consumer backpressure")
        raise WebSocketDisconnect(1013) from None
    except RuntimeError as exc:
        message = str(exc)
        if "TCPTransport closed=True" in message and "handler is closed" in message:
            raise WebSocketDisconnect(1006) from None
        raise


def _event_frame(event: RealtimeEvent) -> dict:
    return {
        "type": "event",
        "cursor": event.sequence_id,
        "event": {
            "id": str(event.id),
            "type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": str(event.entity_id) if event.entity_id else None,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload or {},
        },
    }


@router.websocket("/ws")
async def realtime_websocket(websocket: WebSocket, ticket: str, after: int = 0):
    await websocket.accept()
    if after < 0:
        await websocket.close(code=4408, reason="Invalid realtime cursor")
        return
    try:
        organization_id, ticket_id, digest = parse_one_time_token(ticket)
    except ValueError:
        await websocket.close(code=4401, reason="Invalid realtime ticket")
        return
    database = websocket.app.state.database
    user_id = None
    membership_id = None
    ticket_auth_version = None
    with database.session_factory() as session:
        set_rls_organization(session, organization_id)
        stored = session.scalar(
            select(RealtimeTicket)
            .where(
                RealtimeTicket.organization_id == organization_id,
                RealtimeTicket.id == ticket_id,
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
        set_rls_user(session, stored.user_id)
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id == stored.membership_id,
                OrganizationMembership.user_id == stored.user_id,
                OrganizationMembership.status == "active",
            )
        )
        if membership is None:
            await websocket.close(code=4403, reason="Realtime organization access is unavailable")
            return
        active_user = session.scalar(
            select(User.id).where(
                User.id == stored.user_id,
                User.is_active.is_(True),
                User.auth_version == stored.auth_version,
            )
        )
        if active_user is None:
            await websocket.close(code=4403, reason="Realtime user access was revoked")
            return
        user_id = stored.user_id
        membership_id = stored.membership_id
        ticket_auth_version = stored.auth_version
        consumed = session.execute(
            update(RealtimeTicket)
            .where(
                RealtimeTicket.organization_id == organization_id,
                RealtimeTicket.id == ticket_id,
                RealtimeTicket.token_digest == digest,
                RealtimeTicket.consumed_at.is_(None),
                RealtimeTicket.expires_at > now,
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
        set_rls_user(session, user_id)
        set_rls_organization(session, organization_id)
        replay = list(
            session.scalars(
                select(RealtimeEvent)
                .where(
                    RealtimeEvent.organization_id == organization_id,
                    RealtimeEvent.sequence_id > after,
                )
                .order_by(RealtimeEvent.sequence_id)
                .limit(MAX_REPLAY + 1)
            )
        )
        latest = (
            session.scalar(
                select(func.max(RealtimeEvent.sequence_id)).where(
                    RealtimeEvent.organization_id == organization_id
                )
            )
            or 0
        )
    if len(replay) > MAX_REPLAY:
        await _send(
            websocket,
            {
                "type": "reset_required",
                "reason": "replay_limit_exceeded",
                "requested_after": after,
                "resume_from": after,
                "latest_available_cursor": latest,
                "cursor_must_not_advance": True,
                "max_replay": MAX_REPLAY,
            },
        )
        await websocket.close(code=4408, reason="Realtime replay limit exceeded")
        return
    if after > latest:
        await _send(
            websocket,
            {
                "type": "reset_required",
                "reason": "cursor_ahead",
                "requested_after": after,
                "resume_from": latest,
                "latest_available_cursor": latest,
                "cursor_must_not_advance": True,
                "max_replay": MAX_REPLAY,
            },
        )
        await websocket.close(code=4408, reason="Realtime cursor is ahead of this stream")
        return
    cursor = after
    await _send(
        websocket,
        {
            "type": "ready",
            "organization_id": str(organization_id),
            "membership_id": str(membership_id),
            "cursor": cursor,
            "cursor_semantics": "last_emitted_event; persist only after local refresh succeeds",
            "heartbeat_seconds": HEARTBEAT_SECONDS,
            "max_replay": MAX_REPLAY,
        },
    )
    started = datetime.now(UTC)
    last_heartbeat = started
    try:
        while (datetime.now(UTC) - started).total_seconds() < MAX_CONNECTION_SECONDS:
            with database.session_factory() as session:
                set_rls_user(session, user_id)
                set_rls_organization(session, organization_id)
                active_membership = session.scalar(
                    select(OrganizationMembership.id).where(
                        OrganizationMembership.organization_id == organization_id,
                        OrganizationMembership.id == membership_id,
                        OrganizationMembership.user_id == user_id,
                        OrganizationMembership.status == "active",
                    )
                )
                active_identity = session.scalar(
                    select(User.id).where(
                        User.id == user_id,
                        User.is_active.is_(True),
                        User.auth_version == ticket_auth_version,
                    )
                )
            if active_membership is None or active_identity is None:
                await websocket.close(code=4403, reason="Realtime access was revoked")
                return
            if replay:
                pending, replay = replay, []
            else:
                with database.session_factory() as session:
                    set_rls_user(session, user_id)
                    set_rls_organization(session, organization_id)
                    active = session.scalar(
                        select(OrganizationMembership.id).where(
                            OrganizationMembership.organization_id == organization_id,
                            OrganizationMembership.id == membership_id,
                            OrganizationMembership.user_id == user_id,
                            OrganizationMembership.status == "active",
                        )
                    )
                    if active is None:
                        await websocket.close(code=4403, reason="Realtime access was revoked")
                        return
                    active_user = session.scalar(
                        select(User.id).where(
                            User.id == user_id,
                            User.is_active.is_(True),
                            User.auth_version == ticket_auth_version,
                        )
                    )
                    if active_user is None:
                        await websocket.close(
                            code=4403, reason="Realtime user access was revoked"
                        )
                        return
                    pending = list(
                        session.scalars(
                            select(RealtimeEvent)
                            .where(
                                RealtimeEvent.organization_id == organization_id,
                                RealtimeEvent.sequence_id > cursor,
                            )
                            .order_by(RealtimeEvent.sequence_id)
                            .limit(100)
                        )
                    )
            for event in pending:
                await _send(websocket, _event_frame(event))
                cursor = event.sequence_id
            now = datetime.now(UTC)
            if (now - last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
                await _send(
                    websocket,
                    {
                        "type": "heartbeat",
                        "cursor": cursor,
                        "server_time": now.isoformat(),
                    },
                )
                last_heartbeat = now
            await asyncio.sleep(POLL_SECONDS)
        await websocket.close(code=1000, reason="Realtime connection rotation")
    except WebSocketDisconnect:
        return
