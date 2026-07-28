"""Explicit push-provider boundary and retry-safe delivery worker primitives.

No provider is created unless delivery is enabled and complete provider
configuration is present. HTTP request handlers never call this module's worker.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.basic.models import (
    NotificationDelivery,
    PushSubscription,
    UserNotificationPreference,
    UserRealtimeEvent,
)
from app.basic.security import set_rls_user
from app.core.config import Settings

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPT_URL = "https://exp.host/--/api/v2/push/getReceipts"
SAFE_PAYLOAD_KEYS = frozenset({"type", "notification_id", "category", "severity"})
MAX_ATTEMPTS = 5
MAX_RECEIPT_ATTEMPTS = 20
RECEIPT_INITIAL_DELAY = timedelta(minutes=15)


@dataclass(frozen=True)
class PushMessage:
    transport: str
    platform: str
    delivery_address: str
    web_push_public_key: str | None
    web_push_auth_secret: str | None
    payload: dict[str, str]


@dataclass(frozen=True)
class PushSendResult:
    provider_message_id: str | None = None


@dataclass(frozen=True)
class PushReceiptResult:
    provider_handoff_confirmed: bool = True


@dataclass(frozen=True)
class DeliveryBatchResult:
    selected: int
    accepted: int
    sent: int
    retried: int
    dead: int
    invalidated: int
    provider_disabled: bool = False


class PushProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = True,
        invalid_address: bool = False,
        resend: bool = False,
    ):
        super().__init__(code)
        self.code = code[:80]
        self.retryable = retryable
        self.invalid_address = invalid_address
        self.resend = resend


class PushProvider(Protocol):
    def send(self, message: PushMessage) -> PushSendResult: ...

    def receipt(self, provider_message_id: str) -> PushReceiptResult: ...


def _validated_payload(payload: dict) -> dict[str, str]:
    if set(payload) != SAFE_PAYLOAD_KEYS or payload.get("type") != "notification":
        raise PushProviderError("unsafe_payload", retryable=False)
    values = {key: str(value) for key, value in payload.items()}
    if any(len(value) > 100 for value in values.values()):
        raise PushProviderError("unsafe_payload", retryable=False)
    return values


class ExpoPushProvider:
    """Minimal Expo adapter; instantiated only by explicit worker configuration."""

    def __init__(self, access_token: str, timeout_seconds: float = 10.0) -> None:
        if not access_token.strip():
            raise ValueError("Expo push access token is required")
        self._access_token = access_token
        self._timeout_seconds = timeout_seconds

    def send(self, message: PushMessage) -> PushSendResult:
        if message.transport != "expo":
            raise PushProviderError("unsupported_transport", retryable=False)
        payload = _validated_payload(message.payload)
        request = Request(
            EXPO_PUSH_URL,
            data=json.dumps(
                {
                    "to": message.delivery_address,
                    "title": "CareSync update",
                    "body": "Open CareSync to review an update.",
                    "data": payload,
                    "sound": "default",
                    "priority": "high",
                    "collapseId": payload["notification_id"],
                }
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                parsed = json.loads(response.read(64 * 1024))
        except HTTPError as error:
            retryable = error.code == 429 or error.code >= 500
            raise PushProviderError(f"http_{error.code}", retryable=retryable) from None
        except (OSError, TimeoutError, URLError, ValueError, json.JSONDecodeError):
            raise PushProviderError("provider_unavailable", retryable=True) from None
        result = parsed.get("data") if isinstance(parsed, dict) else None
        if isinstance(result, list):
            result = result[0] if result else None
        if not isinstance(result, dict):
            raise PushProviderError("invalid_provider_response", retryable=True)
        if result.get("status") == "ok":
            provider_id = result.get("id")
            if not provider_id:
                raise PushProviderError("missing_provider_ticket", retryable=True)
            return PushSendResult(str(provider_id)[:255])
        error_code = str((result.get("details") or {}).get("error") or "provider_rejected")
        raise PushProviderError(
            error_code,
            retryable=error_code in {"MessageRateExceeded"},
            invalid_address=error_code == "DeviceNotRegistered",
            resend=error_code == "MessageRateExceeded",
        )

    def receipt(self, provider_message_id: str) -> PushReceiptResult:
        request = Request(
            EXPO_RECEIPT_URL,
            data=json.dumps({"ids": [provider_message_id]}).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                parsed = json.loads(response.read(64 * 1024))
        except HTTPError as error:
            retryable = error.code == 429 or error.code >= 500
            raise PushProviderError(f"receipt_http_{error.code}", retryable=retryable) from None
        except (OSError, TimeoutError, URLError, ValueError, json.JSONDecodeError):
            raise PushProviderError("receipt_provider_unavailable", retryable=True) from None
        data = parsed.get("data") if isinstance(parsed, dict) else None
        result = data.get(provider_message_id) if isinstance(data, dict) else None
        if result is None:
            raise PushProviderError("receipt_not_ready", retryable=True)
        if not isinstance(result, dict):
            raise PushProviderError("invalid_receipt_response", retryable=True)
        if result.get("status") == "ok":
            return PushReceiptResult()
        error_code = str((result.get("details") or {}).get("error") or "receipt_rejected")
        raise PushProviderError(
            error_code,
            retryable=error_code in {"MessageRateExceeded"},
            invalid_address=error_code == "DeviceNotRegistered",
            resend=error_code == "MessageRateExceeded",
        )


def build_push_provider(settings: Settings) -> PushProvider | None:
    """Return no provider unless an operator intentionally enables complete config."""

    token = settings.expo_push_access_token.get_secret_value().strip()
    if (
        not settings.push_delivery_enabled
        or settings.push_provider == "disabled"
        or not token
    ):
        return None
    if settings.push_provider == "expo":
        return ExpoPushProvider(token, settings.push_provider_timeout_seconds)
    return None


def _retry_at(now: datetime, attempt_count: int) -> datetime:
    return now + timedelta(seconds=min(3600, 30 * (2 ** max(0, attempt_count - 1))))


def _receipt_retry_at(now: datetime, attempt_count: int) -> datetime:
    return now + timedelta(seconds=min(900, 15 * (2 ** max(0, attempt_count - 1))))


def _set_user_context(session: Session, user_id: UUID) -> None:
    set_rls_user(session, user_id)


def _preference_allows(
    session: Session,
    user_id: UUID,
    category: str,
) -> bool:
    preference = session.get(UserNotificationPreference, user_id, populate_existing=True)
    if preference is None:
        return True
    if not preference.push_enabled:
        return False
    field = {
        "hiring": "hiring_enabled",
        "credential": "credential_enabled",
        "assignment": "assignment_enabled",
        "operations": "operations_enabled",
    }.get(category)
    return True if field is None else bool(getattr(preference, field))


def _delivery_event(session: Session, delivery: NotificationDelivery) -> None:
    session.add(
        UserRealtimeEvent(
            user_id=delivery.user_id,
            organization_id=delivery.organization_id,
            event_type="notification.delivery_updated",
            entity_type="notification_delivery",
            entity_id=delivery.id,
            payload={"status": delivery.status},
        )
    )


def _invalidate_subscription(
    session: Session,
    delivery: NotificationDelivery,
    current: datetime,
) -> None:
    subscription = session.get(
        PushSubscription,
        delivery.subscription_id,
        populate_existing=True,
    )
    if subscription is None:
        return
    subscription.status = "invalid"
    subscription.delivery_address = None
    subscription.web_push_public_key = None
    subscription.web_push_auth_secret = None
    subscription.revoked_at = current


def deliver_pending_push_for_user(
    session: Session,
    *,
    user_id: UUID,
    provider: PushProvider | None,
    limit: int = 50,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> DeliveryBatchResult:
    """Deliver one user's outbox under that user's RLS context.

    A caller must set ``app.current_user_id`` before invoking this function on
    PostgreSQL. Passing ``None`` is a safe no-op and never mutates the outbox.
    """

    if provider is None:
        return DeliveryBatchResult(0, 0, 0, 0, 0, 0, provider_disabled=True)
    if now is not None and clock is not None:
        raise ValueError("Pass either now or clock, not both")
    if clock is None:
        clock = (lambda: now) if now is not None else (lambda: datetime.now(UTC))
    batch_limit = max(1, min(limit, 250))
    accepted = sent = retried = dead = invalidated = 0
    selected = 0

    # A crashed worker leaves a durable lease. Reclaim only after it expires.
    current = clock()
    _set_user_context(session, user_id)
    stale = list(
        session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.status == "processing",
                NotificationDelivery.lease_expires_at <= current,
            )
        )
    )
    for delivery in stale:
        receipt_claim = delivery.provider_message_id is not None
        delivery.status = "receipt_pending" if receipt_claim else "retry"
        delivery.available_at = current
        delivery.claimed_at = None
        delivery.lease_expires_at = None
        delivery.last_error_code = (
            "receipt_lease_expired" if receipt_claim else "lease_expired"
        )
        _delivery_event(session, delivery)
    if stale:
        session.commit()

    while selected < batch_limit:
        current = clock()
        _set_user_context(session, user_id)
        statement = (
            select(NotificationDelivery, PushSubscription)
            .join(PushSubscription, PushSubscription.id == NotificationDelivery.subscription_id)
            .where(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.status.in_(
                    ("pending", "retry", "receipt_pending")
                ),
                NotificationDelivery.available_at <= current,
            )
            .order_by(NotificationDelivery.available_at, NotificationDelivery.created_at)
            .limit(1)
        )
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        row = session.execute(statement).first()
        if row is None:
            break
        delivery, subscription = row
        selected += 1
        if delivery.status == "receipt_pending":
            if not delivery.provider_message_id:
                delivery.status = "dead"
                delivery.last_error_code = "missing_provider_ticket"
                dead += 1
                _delivery_event(session, delivery)
                session.commit()
                continue
            delivery.status = "processing"
            delivery.claimed_at = current
            delivery.lease_expires_at = current + timedelta(minutes=2)
            delivery.receipt_attempt_count += 1
            provider_message_id = delivery.provider_message_id
            session.commit()

            receipt_error: PushProviderError | None = None
            try:
                provider.receipt(provider_message_id)
            except PushProviderError as error:
                receipt_error = error
            except Exception:
                receipt_error = PushProviderError(
                    "receipt_provider_error", retryable=True
                )

            finalized_at = clock()
            _set_user_context(session, user_id)
            finalized = session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.id == delivery.id,
                    NotificationDelivery.user_id == user_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if finalized is None or finalized.status != "processing":
                session.rollback()
                continue
            finalized.claimed_at = None
            finalized.lease_expires_at = None
            if receipt_error is None:
                # Expo receipts confirm provider handoff to FCM/APNs, not that a
                # device displayed the notification or a person read it.
                finalized.status = "sent"
                finalized.delivered_at = finalized_at
                finalized.last_error_code = None
                sent += 1
            else:
                finalized.last_error_code = receipt_error.code
                if receipt_error.invalid_address:
                    _invalidate_subscription(session, finalized, finalized_at)
                    finalized.status = "dead"
                    dead += 1
                    invalidated += 1
                elif receipt_error.resend:
                    finalized.provider_message_id = None
                    if finalized.attempt_count < MAX_ATTEMPTS:
                        finalized.status = "retry"
                        finalized.available_at = _retry_at(
                            finalized_at,
                            finalized.attempt_count,
                        )
                        retried += 1
                    else:
                        finalized.status = "dead"
                        dead += 1
                elif (
                    receipt_error.retryable
                    and finalized.receipt_attempt_count < MAX_RECEIPT_ATTEMPTS
                ):
                    finalized.status = "receipt_pending"
                    finalized.available_at = _receipt_retry_at(
                        finalized_at,
                        finalized.receipt_attempt_count,
                    )
                    retried += 1
                else:
                    finalized.status = "dead"
                    dead += 1
            _delivery_event(session, finalized)
            session.commit()
            continue

        category = str(delivery.payload.get("category", "system"))
        if subscription.status != "active" or subscription.delivery_address is None:
            delivery.status = "cancelled"
            delivery.cancelled_at = current
            delivery.last_error_code = "subscription_unavailable"
            _delivery_event(session, delivery)
            session.commit()
            continue
        if not _preference_allows(session, user_id, category):
            delivery.status = "suppressed"
            delivery.cancelled_at = current
            delivery.last_error_code = "preference_disabled"
            _delivery_event(session, delivery)
            session.commit()
            continue

        # Claim and commit before any remote call so the lease is durable and no
        # database lock is held during provider latency.
        delivery.status = "processing"
        delivery.claimed_at = current
        delivery.lease_expires_at = current + timedelta(minutes=2)
        delivery.attempt_count += 1
        session.commit()

        # Re-read the endpoint and preferences immediately before dispatch. A
        # concurrent logout/revoke can cancel the claimed row between commits.
        _set_user_context(session, user_id)
        claimed = session.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_subscription = session.scalar(
            select(PushSubscription)
            .where(
                PushSubscription.id == delivery.subscription_id,
                PushSubscription.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if claimed is None or claimed.status != "processing":
            session.rollback()
            continue
        if (
            current_subscription is None
            or current_subscription.status != "active"
            or current_subscription.delivery_address is None
        ):
            claimed.status = "cancelled"
            claimed.cancelled_at = current
            claimed.claimed_at = None
            claimed.lease_expires_at = None
            claimed.last_error_code = "subscription_unavailable"
            _delivery_event(session, claimed)
            session.commit()
            continue
        if not _preference_allows(session, user_id, category):
            claimed.status = "suppressed"
            claimed.cancelled_at = current
            claimed.claimed_at = None
            claimed.lease_expires_at = None
            claimed.last_error_code = "preference_disabled"
            _delivery_event(session, claimed)
            session.commit()
            continue
        message = PushMessage(
            transport=current_subscription.transport,
            platform=current_subscription.platform,
            delivery_address=current_subscription.delivery_address,
            web_push_public_key=current_subscription.web_push_public_key,
            web_push_auth_secret=current_subscription.web_push_auth_secret,
            payload=_validated_payload(claimed.payload),
        )
        session.commit()

        provider_result: PushSendResult | None = None
        provider_error: PushProviderError | None = None
        try:
            provider_result = provider.send(message)
        except PushProviderError as error:
            provider_error = error
        except Exception:
            provider_error = PushProviderError("provider_error", retryable=True)

        _set_user_context(session, user_id)
        finalized = session.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery.id,
                NotificationDelivery.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if finalized is None or finalized.status != "processing":
            session.rollback()
            continue
        finalized.claimed_at = None
        finalized.lease_expires_at = None
        finalized_at = clock()
        if provider_error is None and (
            provider_result is None or not provider_result.provider_message_id
        ):
            provider_error = PushProviderError(
                "missing_provider_ticket", retryable=True
            )
        if provider_error is None:
            finalized.status = "receipt_pending"
            finalized.available_at = finalized_at + RECEIPT_INITIAL_DELAY
            finalized.provider_message_id = provider_result.provider_message_id
            finalized.receipt_attempt_count = 0
            finalized.last_error_code = None
            accepted += 1
        else:
            finalized.last_error_code = provider_error.code
            if provider_error.invalid_address:
                _invalidate_subscription(session, finalized, finalized_at)
                finalized.status = "dead"
                dead += 1
                invalidated += 1
            elif provider_error.retryable and finalized.attempt_count < MAX_ATTEMPTS:
                finalized.status = "retry"
                finalized.available_at = _retry_at(
                    finalized_at, finalized.attempt_count
                )
                retried += 1
            else:
                finalized.status = "dead"
                dead += 1
        _delivery_event(session, finalized)
        session.commit()
    return DeliveryBatchResult(
        selected,
        accepted,
        sent,
        retried,
        dead,
        invalidated,
    )
