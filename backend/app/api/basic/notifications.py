"""Authenticated notification inbox, unread summary, and fixed preferences."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select, text, update

from app.api.basic.common import commit_or_conflict, ensure_writable
from app.api.basic.dependencies import BasicUser
from app.api.dependencies import SessionDependency
from app.basic.models import (
    NotificationDelivery,
    OrganizationMembership,
    PushSubscription,
    UserNotification,
    UserNotificationPreference,
)
from app.basic.notifications import emit_user_realtime_event, validate_notification_action

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hiring_enabled: bool
    credential_enabled: bool
    assignment_enabled: bool
    operations_enabled: bool
    push_enabled: bool = True


class PushSubscriptionUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    transport: Literal["expo", "web_push"]
    platform: Literal["android", "ios", "web"]
    delivery_address: str = Field(min_length=10, max_length=4096)
    organization_id: UUID | None = None
    web_push_public_key: str | None = Field(default=None, min_length=16, max_length=1024)
    web_push_auth_secret: str | None = Field(default=None, min_length=8, max_length=512)

    @model_validator(mode="after")
    def validate_transport(self):
        self.delivery_address = self.delivery_address.strip()
        if self.transport == "expo":
            if self.platform not in {"android", "ios"}:
                raise ValueError("Expo subscriptions require an Android or iOS platform")
            if not (
                self.delivery_address.startswith("ExpoPushToken[")
                or self.delivery_address.startswith("ExponentPushToken[")
            ) or not self.delivery_address.endswith("]"):
                raise ValueError("Invalid Expo push token")
            if self.web_push_public_key is not None or self.web_push_auth_secret is not None:
                raise ValueError("Expo subscriptions cannot include browser encryption keys")
        else:
            raise ValueError("Web Push delivery is not configured; use an Expo subscription")
        return self


def _row(value: UserNotification) -> dict:
    action = None
    try:
        validate_notification_action(
            organization_id=value.organization_id,
            action_path=value.action_path,
            action_entity_type=value.action_entity_type,
            action_entity_id=value.action_entity_id,
        )
    except ValueError:
        # Historical rows predate the closed action contract. Keep the ledger
        # readable, but never serialize malformed navigation as clickable.
        pass
    else:
        if value.action_path is not None:
            action = {
                "path": value.action_path,
                "entity_type": value.action_entity_type,
                "entity_id": value.action_entity_id,
            }
    return {
        "id": value.id,
        "organization_id": value.organization_id,
        "category": value.category,
        "severity": value.severity,
        "title": value.title,
        "body": value.body,
        "action": action,
        "created_at": value.created_at,
        "read_at": value.read_at,
    }


def _subscription_row(value: PushSubscription) -> dict:
    return {
        "id": value.id,
        "device_id": value.device_id,
        "organization_id": value.organization_id,
        "transport": value.transport,
        "platform": value.platform,
        "status": value.status,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "last_seen_at": value.last_seen_at,
        "revoked_at": value.revoked_at,
    }


def _validate_subscription_organization(
    session: SessionDependency,
    user_id: UUID,
    organization_id: UUID | None,
) -> None:
    if organization_id is None:
        return
    membership = session.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(403, "Active organization membership required")


def _cancel_subscription_deliveries(
    session: SessionDependency,
    subscription: PushSubscription,
    now: datetime,
) -> None:
    deliveries = list(
        session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.user_id == subscription.user_id,
                NotificationDelivery.subscription_id == subscription.id,
                NotificationDelivery.status.in_(("pending", "processing", "retry")),
            )
        )
    )
    for delivery in deliveries:
        delivery.status = "cancelled"
        delivery.cancelled_at = now
        delivery.claimed_at = None
        delivery.lease_expires_at = None


def _transfer_active_address(
    session: SessionDependency,
    *,
    user_id: UUID,
    device_id: UUID,
    transport: str,
    address_digest: str,
    now: datetime,
) -> None:
    """Make one provider address active for exactly one account/device.

    The address itself is the proof of possession. PostgreSQL uses a narrow
    transfer RLS policy plus an advisory transaction lock; SQLite performs the
    equivalent locked mutation directly.
    """

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"{transport}:{address_digest}"},
        )
        session.execute(
            text(
                "SELECT pg_catalog.set_config('app.push_transfer_transport', :value, true)"
            ),
            {"value": transport},
        )
        session.execute(
            text("SELECT pg_catalog.set_config('app.push_transfer_digest', :value, true)"),
            {"value": address_digest},
        )
        try:
            transfer_targets = select(PushSubscription.id).where(
                PushSubscription.transport == transport,
                PushSubscription.address_digest == address_digest,
                PushSubscription.status == "active",
                or_(
                    PushSubscription.user_id != user_id,
                    PushSubscription.device_id != device_id,
                ),
            )
            session.execute(
                update(NotificationDelivery)
                .where(
                    NotificationDelivery.subscription_id.in_(transfer_targets),
                    NotificationDelivery.status.in_(
                        ("pending", "processing", "retry")
                    ),
                )
                .values(
                    status="cancelled",
                    cancelled_at=now,
                    claimed_at=None,
                    lease_expires_at=None,
                    last_error_code="subscription_transferred",
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            session.execute(
                update(PushSubscription)
                .where(
                    PushSubscription.transport == transport,
                    PushSubscription.address_digest == address_digest,
                    PushSubscription.status == "active",
                    or_(
                        PushSubscription.user_id != user_id,
                        PushSubscription.device_id != device_id,
                    ),
                )
                .values(
                    status="revoked",
                    delivery_address=None,
                    web_push_public_key=None,
                    web_push_auth_secret=None,
                    revoked_at=now,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
        finally:
            session.execute(
                text(
                    "SELECT pg_catalog.set_config('app.push_transfer_transport', '', true)"
                )
            )
            session.execute(
                text("SELECT pg_catalog.set_config('app.push_transfer_digest', '', true)")
            )
        return

    previous = list(
        session.scalars(
            select(PushSubscription)
            .where(
                PushSubscription.transport == transport,
                PushSubscription.address_digest == address_digest,
                PushSubscription.status == "active",
                or_(
                    PushSubscription.user_id != user_id,
                    PushSubscription.device_id != device_id,
                ),
            )
            .with_for_update()
        )
    )
    for subscription in previous:
        _cancel_subscription_deliveries(session, subscription, now)
        subscription.status = "revoked"
        subscription.delivery_address = None
        subscription.web_push_public_key = None
        subscription.web_push_auth_secret = None
        subscription.revoked_at = now
        emit_user_realtime_event(
            session,
            user_id=subscription.user_id,
            organization_id=subscription.organization_id,
            event_type="push_subscription.updated",
            entity_type="push_subscription",
            entity_id=subscription.id,
            payload={"status": "revoked", "reason": "address_transferred"},
        )


@router.get("/push/capabilities")
def push_capabilities(request: Request, user: BasicUser):
    del user
    settings = request.app.state.settings
    expo_configured = bool(
        settings.push_delivery_enabled
        and settings.push_provider == "expo"
        and settings.expo_push_access_token.get_secret_value().strip()
    )
    return {
        "registration_enabled": True,
        "accepted_transports": ["expo"],
        "remote_delivery_enabled": expo_configured,
        "configured_remote_transports": ["expo"] if expo_configured else [],
        "provider_worker_required": True,
        "payload_contains_pii": False,
        "delivery_confirmation_semantics": "provider_handoff_not_device_or_user_receipt",
    }


@router.post("/push/subscriptions", status_code=201)
def upsert_push_subscription(
    payload: PushSubscriptionUpsert,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    _validate_subscription_organization(session, user.id, payload.organization_id)
    now = datetime.now(UTC)
    digest = hashlib.sha256(payload.delivery_address.encode("utf-8")).hexdigest()
    _transfer_active_address(
        session,
        user_id=user.id,
        device_id=payload.device_id,
        transport=payload.transport,
        address_digest=digest,
        now=now,
    )
    value = session.scalar(
        select(PushSubscription)
        .where(PushSubscription.user_id == user.id, PushSubscription.device_id == payload.device_id)
        .with_for_update()
    )
    created = value is None
    if value is None:
        value = PushSubscription(user_id=user.id, device_id=payload.device_id)
        session.add(value)
    value.organization_id = payload.organization_id
    value.transport = payload.transport
    value.platform = payload.platform
    value.delivery_address = payload.delivery_address
    value.address_digest = digest
    value.web_push_public_key = payload.web_push_public_key
    value.web_push_auth_secret = payload.web_push_auth_secret
    value.status = "active"
    value.last_seen_at = now
    value.revoked_at = None
    session.flush()
    emit_user_realtime_event(
        session,
        user_id=user.id,
        organization_id=value.organization_id,
        event_type="push_subscription.updated",
        entity_type="push_subscription",
        entity_id=value.id,
        payload={"status": "active"},
    )
    commit_or_conflict(session, "Push subscription conflicts with an existing device")
    return _subscription_row(value) | {"created": created}


@router.get("/push/subscriptions")
def list_push_subscriptions(
    user: BasicUser,
    session: SessionDependency,
    include_revoked: bool = False,
):
    statement = select(PushSubscription).where(PushSubscription.user_id == user.id)
    if not include_revoked:
        statement = statement.where(PushSubscription.status == "active")
    rows = list(session.scalars(statement.order_by(PushSubscription.updated_at.desc())))
    return {"items": [_subscription_row(row) for row in rows], "total": len(rows)}


@router.delete("/push/subscriptions/{subscription_id}")
def revoke_push_subscription(
    subscription_id: UUID,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    value = session.scalar(
        select(PushSubscription)
        .where(PushSubscription.id == subscription_id, PushSubscription.user_id == user.id)
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, "Push subscription not found")
    now = datetime.now(UTC)
    _cancel_subscription_deliveries(session, value, now)
    value.status = "revoked"
    value.delivery_address = None
    value.web_push_public_key = None
    value.web_push_auth_secret = None
    value.revoked_at = value.revoked_at or now
    emit_user_realtime_event(
        session,
        user_id=user.id,
        organization_id=value.organization_id,
        event_type="push_subscription.updated",
        entity_type="push_subscription",
        entity_id=value.id,
        payload={"status": "revoked"},
    )
    commit_or_conflict(session)
    return _subscription_row(value)


@router.post("/push/subscriptions/revoke-all")
def revoke_all_push_subscriptions(
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    rows = list(
        session.scalars(
            select(PushSubscription)
            .where(PushSubscription.user_id == user.id, PushSubscription.status == "active")
            .with_for_update()
        )
    )
    now = datetime.now(UTC)
    for value in rows:
        _cancel_subscription_deliveries(session, value, now)
        value.status = "revoked"
        value.delivery_address = None
        value.web_push_public_key = None
        value.web_push_auth_secret = None
        value.revoked_at = now
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="push_subscription.updated",
        entity_type="push_subscription",
        entity_id=None,
        payload={"status": "revoked", "scope": "all"},
    )
    commit_or_conflict(session)
    return {"revoked": len(rows), "revoked_at": now}


@router.get("/push/deliveries")
def list_push_deliveries(
    user: BasicUser,
    session: SessionDependency,
    status_filter: Literal[
        "pending",
        "processing",
        "retry",
        "receipt_pending",
        "sent",
        "dead",
        "cancelled",
        "suppressed",
    ]
    | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    statement = select(NotificationDelivery).where(NotificationDelivery.user_id == user.id)
    if status_filter is not None:
        statement = statement.where(NotificationDelivery.status == status_filter)
    rows = list(
        session.scalars(
            statement.order_by(NotificationDelivery.created_at.desc()).limit(limit)
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "notification_id": row.notification_id,
                "subscription_id": row.subscription_id,
                "organization_id": row.organization_id,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "receipt_attempt_count": row.receipt_attempt_count,
                "available_at": row.available_at,
                "delivered_at": row.delivered_at,
                "provider_confirmed_at": row.delivered_at,
                "delivery_confirmation": "provider_handoff",
                "cancelled_at": row.cancelled_at,
                "last_error_code": row.last_error_code,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.get("")
def list_notifications(
    user: BasicUser,
    session: SessionDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    unread_only: bool = False,
    category: Literal["hiring", "credential", "assignment", "operations", "system"] | None = None,
):
    filters = [UserNotification.user_id == user.id]
    if unread_only:
        filters.append(UserNotification.read_at.is_(None))
    if category:
        filters.append(UserNotification.category == category)
    total = session.scalar(select(func.count()).select_from(UserNotification).where(*filters)) or 0
    rows = list(
        session.scalars(
            select(UserNotification)
            .where(*filters)
            .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [_row(item) for item in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": page * page_size < total,
    }


@router.get("/summary")
def unread_summary(user: BasicUser, session: SessionDependency):
    rows = session.execute(
        select(UserNotification.category, func.count())
        .where(UserNotification.user_id == user.id, UserNotification.read_at.is_(None))
        .group_by(UserNotification.category)
    )
    by_category = {category: count for category, count in rows}
    return {"unread_total": sum(by_category.values()), "by_category": by_category}


@router.post("/items/{notification_id}/read")
def mark_read(
    notification_id: UUID,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    value = session.scalar(
        select(UserNotification)
        .where(UserNotification.id == notification_id, UserNotification.user_id == user.id)
        .with_for_update()
    )
    if value is None:
        raise HTTPException(404, "Notification not found")
    if value.read_at is None:
        value.read_at = datetime.now(UTC)
        emit_user_realtime_event(
            session,
            user_id=user.id,
            organization_id=value.organization_id,
            event_type="notification.read",
            entity_type="notification",
            entity_id=value.id,
            payload={"source": "notification_ledger"},
        )
    commit_or_conflict(session)
    return _row(value)


@router.post("/read-all")
def mark_all_read(
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    rows = list(
        session.scalars(
            select(UserNotification).where(
                UserNotification.user_id == user.id,
                UserNotification.read_at.is_(None),
            )
        )
    )
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    if rows:
        emit_user_realtime_event(
            session,
            user_id=user.id,
            event_type="notification.read_all",
            entity_type="notification",
            entity_id=None,
            payload={"count": len(rows)},
        )
    commit_or_conflict(session)
    return {"marked_read": len(rows), "read_at": now}


def _preference(session, user_id: UUID) -> UserNotificationPreference:
    value = session.get(UserNotificationPreference, user_id)
    if value is None:
        value = UserNotificationPreference(user_id=user_id)
        session.add(value)
        session.flush()
    return value


def _preference_row(value: UserNotificationPreference) -> dict:
    return {
        "hiring_enabled": value.hiring_enabled,
        "credential_enabled": value.credential_enabled,
        "assignment_enabled": value.assignment_enabled,
        "operations_enabled": value.operations_enabled,
        "push_enabled": value.push_enabled,
        "system_notifications_always_enabled": True,
        "updated_at": value.updated_at,
    }


@router.get("/preferences")
def get_preferences(user: BasicUser, session: SessionDependency):
    value = _preference(session, user.id)
    commit_or_conflict(session)
    return _preference_row(value)


@router.put("/preferences")
def put_preferences(
    payload: PreferenceUpdate,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    value = _preference(session, user.id)
    for key, setting in payload.model_dump().items():
        setattr(value, key, setting)
    disabled_categories = {
        category
        for category, enabled in {
            "hiring": payload.hiring_enabled,
            "credential": payload.credential_enabled,
            "assignment": payload.assignment_enabled,
            "operations": payload.operations_enabled,
        }.items()
        if not enabled
    }
    if not payload.push_enabled or disabled_categories:
        statement = (
            select(NotificationDelivery)
            .join(UserNotification, UserNotification.id == NotificationDelivery.notification_id)
            .where(
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.status.in_(("pending", "processing", "retry")),
            )
        )
        if payload.push_enabled:
            statement = statement.where(UserNotification.category.in_(disabled_categories))
        pending = list(session.scalars(statement))
    else:
        pending = []
    now = datetime.now(UTC)
    for delivery in pending:
        delivery.status = "suppressed"
        delivery.cancelled_at = now
        delivery.claimed_at = None
        delivery.lease_expires_at = None
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="notification.preferences_updated",
        entity_type="notification_preference",
        entity_id=user.id,
        payload={"source": "notification_preferences"},
    )
    commit_or_conflict(session)
    return _preference_row(value)
