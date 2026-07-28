"""Authenticated, resumable, user-private notification invalidations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select, update

from app.api.basic.common import commit_or_conflict, ensure_writable
from app.api.basic.dependencies import BasicUser
from app.api.dependencies import SessionDependency
from app.basic.models import User, UserRealtimeEvent, UserRealtimeTicket
from app.basic.security import (
    create_one_time_token,
    parse_one_time_token,
    set_rls_user,
    token_digest_matches,
)

router = APIRouter(prefix="/notifications/realtime", tags=["notification realtime"])
TICKET_TTL_SECONDS = 60
HEARTBEAT_SECONDS = 15
POLL_SECONDS = 1.0
SEND_TIMEOUT_SECONDS = 5
MAX_REPLAY = 500
MAX_CONNECTION_SECONDS = 1800
SAFE_PAYLOAD_KEYS = frozenset({"source", "status", "scope", "count", "category", "severity"})


@router.post("/tickets", status_code=201)
def issue_notification_realtime_ticket(
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    now = datetime.now(UTC)
    ticket = UserRealtimeTicket(
        user_id=user.id,
        token_digest="pending",
        auth_version=user.auth_version,
        expires_at=now + timedelta(seconds=TICKET_TTL_SECONDS),
    )
    session.add(ticket)
    session.flush()
    opaque, ticket.token_digest = create_one_time_token(user.id, ticket.id)
    commit_or_conflict(session)
    return {
        "ticket": opaque,
        "expires_at": ticket.expires_at,
        "websocket_path": "/api/v1/notifications/realtime/ws",
        "max_replay": MAX_REPLAY,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _safe_payload(payload: dict | None) -> dict:
    return {
        key: value
        for key, value in (payload or {}).items()
        if key in SAFE_PAYLOAD_KEYS and isinstance(value, str | int | bool)
    }


def _frame(event: UserRealtimeEvent) -> dict:
    return {
        "type": "event",
        "cursor": event.sequence_id,
        "event": {
            "id": str(event.id),
            "type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": str(event.entity_id) if event.entity_id else None,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": _safe_payload(event.payload),
        },
    }


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        await asyncio.wait_for(websocket.send_json(payload), SEND_TIMEOUT_SECONDS)
    except TimeoutError:
        await websocket.close(code=1013, reason="Realtime consumer backpressure")
        raise WebSocketDisconnect(1013) from None


@router.websocket("/ws")
async def notification_realtime_websocket(websocket: WebSocket, ticket: str, after: int = 0):
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
    with database.session_factory() as session:
        set_rls_user(session, user_id)
        stored = session.scalar(
            select(UserRealtimeTicket)
            .where(UserRealtimeTicket.user_id == user_id, UserRealtimeTicket.id == ticket_id)
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
            await websocket.close(code=4403, reason="Notification realtime access was revoked")
            return
        consumed = session.execute(
            update(UserRealtimeTicket)
            .where(
                UserRealtimeTicket.user_id == user_id,
                UserRealtimeTicket.id == ticket_id,
                UserRealtimeTicket.token_digest == digest,
                UserRealtimeTicket.consumed_at.is_(None),
                UserRealtimeTicket.expires_at > now,
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
        replay = list(
            session.scalars(
                select(UserRealtimeEvent)
                .where(
                    UserRealtimeEvent.user_id == user_id,
                    UserRealtimeEvent.sequence_id > after,
                )
                .order_by(UserRealtimeEvent.sequence_id)
                .limit(MAX_REPLAY + 1)
            )
        )
        latest = (
            session.scalar(
                select(func.max(UserRealtimeEvent.sequence_id)).where(
                    UserRealtimeEvent.user_id == user_id
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
            "user_id": str(user_id),
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
            if replay:
                pending, replay = replay, []
            else:
                with database.session_factory() as session:
                    set_rls_user(session, user_id)
                    active_user = session.scalar(
                        select(User.id).where(
                            User.id == user_id,
                            User.is_active.is_(True),
                            User.auth_version == stored.auth_version,
                        )
                    )
                    if active_user is None:
                        await websocket.close(
                            code=4403, reason="Notification realtime access was revoked"
                        )
                        return
                    pending = list(
                        session.scalars(
                            select(UserRealtimeEvent)
                            .where(
                                UserRealtimeEvent.user_id == user_id,
                                UserRealtimeEvent.sequence_id > cursor,
                            )
                            .order_by(UserRealtimeEvent.sequence_id)
                            .limit(100)
                        )
                    )
            for event in pending:
                await _send(websocket, _frame(event))
                cursor = event.sequence_id
            now = datetime.now(UTC)
            if (now - last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
                await _send(
                    websocket,
                    {"type": "heartbeat", "cursor": cursor, "server_time": now.isoformat()},
                )
                last_heartbeat = now
            await asyncio.sleep(POLL_SECONDS)
        await websocket.close(code=1000, reason="Realtime connection rotation")
    except WebSocketDisconnect:
        return
