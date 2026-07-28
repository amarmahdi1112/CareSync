from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from starlette.websockets import WebSocketDisconnect

from app.basic.models import (
    BasicBase,
    Facility,
    MembershipRoomAssignment,
    NotificationDelivery,
    OrganizationMembership,
    Program,
    PushSubscription,
    Role,
    Room,
    User,
    UserNotification,
    UserNotificationPreference,
    UserRealtimeEvent,
)
from app.basic.notifications import (
    notify_organization_members,
    notify_user,
    validate_notification_action,
    validate_notification_action_path,
)
from app.basic.push import (
    PushProviderError,
    PushReceiptResult,
    PushSendResult,
    build_push_provider,
    deliver_pending_push_for_user,
)
from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct-password-123"


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="push-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application, settings


def _register(client, email="push-owner@example.test", organization="Push Centre"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Push",
            "last_name": "Owner",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _register_subscription(client, headers, *, device_id=None, token="one"):
    response = client.post(
        "/api/v1/notifications/push/subscriptions",
        headers=headers,
        json={
            "device_id": str(device_id or uuid4()),
            "transport": "expo",
            "platform": "android",
            "delivery_address": f"ExpoPushToken[{token}-abcdefghijklmnopqrstuvwxyz]",
        },
    )
    assert response.status_code == 201, response.text
    return response


def test_notification_actions_use_a_closed_internal_route_contract():
    exact_paths = {
        "/billing",
        "/jobs",
        "/shifts",
        "/shifts/time-off",
        "/staff-rota",
        "/staff/schedule",
        "/staff/self/exchange/open-shift-activity",
        "/staff/self/exchange/open-shifts",
        "/staff/self/exchange/swaps",
        "/transport-registry",
    }
    for path in exact_paths:
        validate_notification_action_path(path)
    identifier = "11111111-1111-4111-8111-111111111111"
    validate_notification_action_path(f"/jobs/applications/{identifier}")
    validate_notification_action_path(f"/children/{identifier}")

    for path in {
        "https://outside.example/jobs",
        "//outside.example/jobs",
        "/jobs?redirect=https://outside.example",
        "/shifts/../jobs",
        "/shifts#details",
        "/staff/self/exchange/open-shifts/extra",
    }:
        with pytest.raises(ValueError, match="supported internal destination"):
            validate_notification_action_path(path)

    organization_id = uuid4()
    application_id = uuid4()
    validate_notification_action(
        organization_id=organization_id,
        action_path=f"/jobs/applications/{application_id}",
        action_entity_type="application",
        action_entity_id=application_id,
    )
    validate_notification_action(
        organization_id=organization_id,
        action_path="/incidents",
        action_entity_type="incident_record",
        action_entity_id=uuid4(),
    )
    validate_notification_action(
        organization_id=organization_id,
        action_path="/staff/self/exchange/open-shifts",
        action_entity_type="staff_open_shift",
        action_entity_id=uuid4(),
    )
    for entity_type in {
        "staff_availability",
        "staff_time_off",
        "staff_rotation_pattern",
        "staff_open_shift",
        "staff_open_shift_engagement",
        "staff_substitute_profile",
        "staff_shift_swap",
    }:
        validate_notification_action(
            organization_id=organization_id,
            action_path="/staff-rota",
            action_entity_type=entity_type,
            action_entity_id=uuid4(),
        )
    validate_notification_action(
        organization_id=organization_id,
        action_path="/medications",
        action_entity_type="medication_plan",
        action_entity_id=uuid4(),
    )
    validate_notification_action(
        organization_id=organization_id,
        action_path="/transport-registry",
        action_entity_type="transport_registry",
        action_entity_id=uuid4(),
    )
    for entity_type in {
        "billing_account",
        "billing_rate_plan",
        "billing_agreement",
        "billing_invoice",
        "billing_payment",
        "billing_allocation",
        "billing_credit",
    }:
        validate_notification_action(
            organization_id=organization_id,
            action_path="/billing",
            action_entity_type=entity_type,
            action_entity_id=uuid4(),
        )
    with pytest.raises(ValueError, match="complete and organization-bound"):
        validate_notification_action(
            organization_id=None,
            action_path="/incidents",
            action_entity_type="incident_record",
            action_entity_id=uuid4(),
        )
    with pytest.raises(ValueError, match="not valid"):
        validate_notification_action(
            organization_id=organization_id,
            action_path="/incidents",
            action_entity_type="offer",
            action_entity_id=uuid4(),
        )
    with pytest.raises(ValueError, match="not valid"):
        validate_notification_action(
            organization_id=organization_id,
            action_path="/medications",
            action_entity_type="medication_administration",
            action_entity_id=uuid4(),
        )


def test_notification_ledger_serializes_only_complete_org_bound_actions(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client, "action-ledger@example.test", "Action Ledger")
    user_id = UUID(auth["user"]["id"])
    organization_id = UUID(auth["user"]["organization_id"])
    application_id = uuid4()
    offer_id = uuid4()
    incident_id = uuid4()
    schedule_id = uuid4()
    open_shift_id = uuid4()
    transport_registry_id = uuid4()
    actions = (
        (
            "application",
            f"/jobs/applications/{application_id}",
            "application",
            application_id,
        ),
        ("offer", f"/jobs/applications/{application_id}", "offer", offer_id),
        ("incident", "/incidents", "incident_record", incident_id),
        ("schedule", "/shifts", "staff_schedule", schedule_id),
        (
            "open-shift",
            "/staff/self/exchange/open-shifts",
            "staff_open_shift",
            open_shift_id,
        ),
        (
            "transport-registry",
            "/transport-registry",
            "transport_registry",
            transport_registry_id,
        ),
    )
    with application.state.database.session_factory() as session:
        for event_key, path, entity_type, entity_id in actions:
            notify_user(
                session,
                user_id=user_id,
                organization_id=organization_id,
                event_key=f"exact-action:{event_key}",
                category="hiring" if event_key in {"application", "offer"} else "operations",
                severity="info",
                title=event_key,
                body="Open the exact work item.",
                action_path=path,
                action_entity_type=entity_type,
                action_entity_id=entity_id,
            )
        session.add_all(
            [
                UserNotification(
                    user_id=user_id,
                    organization_id=organization_id,
                    event_key="legacy-unsafe-action",
                    category="system",
                    severity="warning",
                    title="legacy-unsafe",
                    body="Historical row",
                    action_path="https://outside.example/work",
                    action_entity_type="application",
                    action_entity_id=application_id,
                ),
                UserNotification(
                    user_id=user_id,
                    organization_id=organization_id,
                    event_key="legacy-incomplete-action",
                    category="system",
                    severity="warning",
                    title="legacy-incomplete",
                    body="Historical row",
                    action_path="/incidents",
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    by_title = {item["title"]: item for item in response.json()["items"]}
    for event_key, path, entity_type, entity_id in actions:
        assert by_title[event_key]["organization_id"] == str(organization_id)
        assert by_title[event_key]["action"] == {
            "path": path,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        }
    assert by_title["legacy-unsafe"]["action"] is None
    assert by_title["legacy-incomplete"]["action"] is None


def test_push_subscription_upsert_rotates_token_without_returning_secret_and_revokes(tmp_path):
    client, application, _ = _client(tmp_path)
    first, headers = _register(client)
    second, other_headers = _register(client, "other-push@example.test", "Other Push")
    del first, second
    capabilities = client.get("/api/v1/notifications/push/capabilities", headers=headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["remote_delivery_enabled"] is False
    assert capabilities.json()["payload_contains_pii"] is False
    device_id = uuid4()
    created = _register_subscription(client, headers, device_id=device_id, token="first")
    assert created.json()["created"] is True
    subscription_id = created.json()["id"]
    assert "delivery_address" not in created.json()
    assert "ExpoPushToken" not in json.dumps(created.json())

    rotated = _register_subscription(client, headers, device_id=device_id, token="rotated")
    assert rotated.json()["created"] is False
    assert rotated.json()["id"] == subscription_id
    listed = client.get("/api/v1/notifications/push/subscriptions", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert "ExpoPushToken" not in json.dumps(listed.json())
    assert (
        client.delete(
            f"/api/v1/notifications/push/subscriptions/{subscription_id}",
            headers=other_headers,
        ).status_code
        == 404
    )

    revoked = client.delete(
        f"/api/v1/notifications/push/subscriptions/{subscription_id}", headers=headers
    )
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    with application.state.database.session_factory() as session:
        stored = session.get(PushSubscription, UUID(subscription_id))
        assert stored.delivery_address is None
        assert stored.web_push_public_key is None
        assert stored.web_push_auth_secret is None


def test_push_address_transfers_to_latest_account_and_rejects_unsupported_web_push(tmp_path):
    client, application, _ = _client(tmp_path)
    first, first_headers = _register(client, "address-first@example.test", "Address One")
    _, second_headers = _register(client, "address-second@example.test", "Address Two")
    shared_token = "shared-installation"
    first_subscription = _register_subscription(
        client, first_headers, device_id=uuid4(), token=shared_token
    ).json()
    first_user_id = UUID(first["user"]["id"])
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=first_user_id,
            event_key="before-account-switch",
            category="system",
            severity="info",
            title="Account update",
            body="Open CareSync.",
        )
        session.commit()
        pending_id = session.scalar(
            select(NotificationDelivery.id).where(
                NotificationDelivery.notification_id == notification.id
            )
        )

    second_subscription = _register_subscription(
        client, second_headers, device_id=uuid4(), token=shared_token
    ).json()
    assert second_subscription["id"] != first_subscription["id"]
    assert (
        client.get("/api/v1/notifications/push/subscriptions", headers=first_headers).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/v1/notifications/push/subscriptions", headers=second_headers).json()[
            "total"
        ]
        == 1
    )
    with application.state.database.session_factory() as session:
        previous = session.get(PushSubscription, UUID(first_subscription["id"]))
        assert previous.status == "revoked"
        assert previous.delivery_address is None
        assert session.get(NotificationDelivery, pending_id).status == "cancelled"

    unsupported = client.post(
        "/api/v1/notifications/push/subscriptions",
        headers=second_headers,
        json={
            "device_id": str(uuid4()),
            "transport": "web_push",
            "platform": "web",
            "delivery_address": "https://push.example.test/subscription",
            "web_push_public_key": "public-key-material",
            "web_push_auth_secret": "auth-secret",
        },
    )
    assert unsupported.status_code == 422
    assert "not configured" in unsupported.text


def test_notification_enqueue_is_idempotent_generic_and_honors_preferences(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client)
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            organization_id=UUID(auth["user"]["organization_id"]),
            event_key="sensitive-business-event",
            category="assignment",
            severity="info",
            title="Named Child moved rooms",
            body="Private Person was assigned to Infant Room.",
            action_path="/staff",
            action_entity_type="organization_membership",
            action_entity_id=UUID(auth["user"]["membership_id"]),
        )
        first_id = notification.id
        notify_user(
            session,
            user_id=user_id,
            event_key="sensitive-business-event",
            category="assignment",
            severity="info",
            title="Duplicate",
            body="Duplicate",
        )
        session.commit()
        deliveries = list(
            session.scalars(
                select(NotificationDelivery).where(NotificationDelivery.notification_id == first_id)
            )
        )
        assert len(deliveries) == 1
        assert deliveries[0].status == "pending"
        assert deliveries[0].payload == {
            "type": "notification",
            "notification_id": str(first_id),
            "category": "assignment",
            "severity": "info",
        }
        assert "Private" not in json.dumps(deliveries[0].payload)

    preferences = client.put(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={
            "hiring_enabled": True,
            "credential_enabled": True,
            "assignment_enabled": False,
            "operations_enabled": True,
            "push_enabled": True,
        },
    )
    assert preferences.status_code == 200
    with application.state.database.session_factory() as session:
        prior = session.get(NotificationDelivery, deliveries[0].id)
        assert prior.status == "suppressed"
        second = notify_user(
            session,
            user_id=user_id,
            event_key="second-assignment",
            category="assignment",
            severity="warning",
            title="Access changed",
            body="Review access.",
        )
        session.commit()
        suppressed = session.scalar(
            select(NotificationDelivery).where(NotificationDelivery.notification_id == second.id)
        )
        assert suppressed.status == "suppressed"


def test_private_notification_realtime_is_scoped_single_use_and_auth_version_bound(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client)
    other, other_headers = _register(client, "private-other@example.test", "Private Other")
    _register_subscription(client, headers)
    _register_subscription(client, other_headers)

    issued = client.post("/api/v1/notifications/realtime/tickets", headers=headers)
    assert issued.status_code == 201, issued.text
    ticket = issued.json()["ticket"]
    with client.websocket_connect(
        f"/api/v1/notifications/realtime/ws?ticket={ticket}&after=0"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready" and ready["user_id"] == auth["user"]["id"]
        event = websocket.receive_json()
        assert event["event"]["type"] == "push_subscription.updated"
        assert event["event"]["payload"] == {"status": "active"}
        assert event["event"]["entity_id"] is not None
    with (
        pytest.raises(WebSocketDisconnect) as reused,
        client.websocket_connect(
            f"/api/v1/notifications/realtime/ws?ticket={ticket}&after=0"
        ) as websocket,
    ):
        websocket.receive_json()
    assert reused.value.code == 4401

    revoked_ticket = client.post(
        "/api/v1/notifications/realtime/tickets", headers=other_headers
    ).json()["ticket"]
    with application.state.database.session_factory() as session:
        user = session.get(User, UUID(other["user"]["id"]))
        user.auth_version += 1
        session.commit()
    with (
        pytest.raises(WebSocketDisconnect) as revoked,
        client.websocket_connect(
            f"/api/v1/notifications/realtime/ws?ticket={revoked_ticket}&after=0"
        ) as websocket,
    ):
        websocket.receive_json()
    assert revoked.value.code == 4403

    live_ticket = client.post("/api/v1/notifications/realtime/tickets", headers=headers).json()[
        "ticket"
    ]
    with application.state.database.session_factory() as session:
        latest = (
            session.scalar(
                select(func.max(UserRealtimeEvent.sequence_id)).where(
                    UserRealtimeEvent.user_id == UUID(auth["user"]["id"])
                )
            )
            or 0
        )
    with (
        pytest.raises(WebSocketDisconnect) as live_revoked,
        client.websocket_connect(
            f"/api/v1/notifications/realtime/ws?ticket={live_ticket}&after={latest}"
        ) as websocket,
    ):
        assert websocket.receive_json()["type"] == "ready"
        with application.state.database.session_factory() as session:
            user = session.get(User, UUID(auth["user"]["id"]))
            user.auth_version += 1
            session.commit()
        websocket.receive_json()
    assert live_revoked.value.code == 4403


def test_private_realtime_cursor_ahead_requires_explicit_checkpoint_replacement(tmp_path):
    client, _, _ = _client(tmp_path)
    _, headers = _register(client, "cursor-ahead-private@example.test", "Cursor Private")
    ticket = client.post("/api/v1/notifications/realtime/tickets", headers=headers).json()["ticket"]
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect(
            f"/api/v1/notifications/realtime/ws?ticket={ticket}&after=999999"
        ) as websocket,
    ):
        reset = websocket.receive_json()
        assert reset == {
            "type": "reset_required",
            "reason": "cursor_ahead",
            "requested_after": 999999,
            "resume_from": 0,
            "latest_available_cursor": 0,
            "cursor_must_not_advance": True,
            "max_replay": 500,
        }
        websocket.receive_json()
    assert closed.value.code == 4408


class _SuccessProvider:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return PushSendResult("provider-message")

    def receipt(self, provider_message_id):
        assert provider_message_id == "provider-message"
        return PushReceiptResult()


def test_push_worker_is_disabled_by_default_and_sends_only_generic_payload(tmp_path):
    client, application, settings = _client(tmp_path)
    auth, headers = _register(client)
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    assert build_push_provider(settings) is None
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="worker-test",
            category="system",
            severity="critical",
            title="Private title",
            body="Private body",
        )
        session.commit()
        before = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        disabled = deliver_pending_push_for_user(
            session, user_id=user_id, provider=None, now=datetime.now(UTC)
        )
        assert disabled.provider_disabled is True and before.status == "pending"
        provider = _SuccessProvider()
        result = deliver_pending_push_for_user(
            session, user_id=user_id, provider=provider, now=datetime.now(UTC)
        )
        session.commit()
        assert result.accepted == 1 and result.sent == 0 and result.selected == 1
        assert provider.messages[0].payload == before.payload
        assert provider.messages[0].payload.keys() == {
            "type",
            "notification_id",
            "category",
            "severity",
        }
        assert before.status == "receipt_pending"
        assert before.provider_message_id == "provider-message"
        confirmed = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=datetime.now(UTC) + timedelta(minutes=16),
        )
        assert confirmed.sent == 1 and confirmed.accepted == 0
        session.refresh(before)
        assert before.status == "sent" and before.delivered_at is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserRealtimeEvent)
                .where(UserRealtimeEvent.event_type == "notification.delivery_updated")
            )
            == 2
        )


class _InvalidReceiptProvider(_SuccessProvider):
    def receipt(self, provider_message_id):
        assert provider_message_id == "provider-message"
        raise PushProviderError(
            "DeviceNotRegistered",
            retryable=False,
            invalid_address=True,
        )


class _RateLimitedReceiptProvider(_SuccessProvider):
    def __init__(self):
        super().__init__()
        self.receipt_calls = 0

    def receipt(self, provider_message_id):
        self.receipt_calls += 1
        raise PushProviderError(
            "MessageRateExceeded",
            retryable=True,
            resend=True,
        )


def test_expo_ticket_is_not_delivered_until_receipt_and_invalid_receipt_scrubs_token(
    tmp_path,
):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client, "receipt-invalid@example.test", "Receipt Centre")
    user_id = UUID(auth["user"]["id"])
    registered = _register_subscription(client, headers)
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="receipt-invalid",
            category="system",
            severity="info",
            title="Generic",
            body="Generic",
        )
        session.commit()
        current = datetime.now(UTC) + timedelta(seconds=1)
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        provider = _InvalidReceiptProvider()
        accepted = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current,
        )
        assert accepted.accepted == 1 and accepted.sent == 0
        session.refresh(delivery)
        assert delivery.status == "receipt_pending"
        assert delivery.delivered_at is None
        receipt = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current + timedelta(minutes=16),
        )
        assert receipt.dead == 1 and receipt.invalidated == 1 and receipt.sent == 0
        session.refresh(delivery)
        subscription = session.get(PushSubscription, UUID(registered.json()["id"]))
        assert delivery.status == "dead" and delivery.delivered_at is None
        assert subscription.status == "invalid"
        assert subscription.delivery_address is None


def test_terminal_rate_limited_receipt_resends_instead_of_repolling_same_ticket(
    tmp_path,
):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client, "receipt-resend@example.test", "Resend Centre")
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="receipt-resend",
            category="system",
            severity="info",
            title="Generic",
            body="Generic",
        )
        session.commit()
        current = datetime.now(UTC) + timedelta(seconds=1)
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        provider = _RateLimitedReceiptProvider()
        first = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current,
        )
        assert first.accepted == 1 and len(provider.messages) == 1
        receipt = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current + timedelta(minutes=16),
        )
        assert receipt.retried == 1 and provider.receipt_calls == 1
        session.refresh(delivery)
        assert delivery.status == "retry"
        assert delivery.provider_message_id is None
        assert delivery.attempt_count == 1
        resent = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current + timedelta(minutes=17),
        )
        assert resent.accepted == 1
        assert len(provider.messages) == 2
        session.refresh(delivery)
        assert delivery.attempt_count == 2
        assert delivery.receipt_attempt_count == 0
        assert delivery.status == "receipt_pending"


def test_push_worker_reclaims_expired_durable_lease_without_holding_network_lock(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client)
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    current = datetime.now(UTC)
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="stale-lease",
            category="system",
            severity="info",
            title="Not sent to provider",
            body="Not sent to provider",
        )
        session.commit()
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        delivery.status = "processing"
        delivery.attempt_count = 1
        delivery.claimed_at = current - timedelta(minutes=5)
        delivery.lease_expires_at = current - timedelta(minutes=3)
        session.commit()

        provider = _SuccessProvider()
        result = deliver_pending_push_for_user(
            session, user_id=user_id, provider=provider, now=current
        )
        assert result.selected == 1 and result.accepted == 1
        confirmed = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            now=current + timedelta(minutes=16),
        )
        assert confirmed.sent == 1
        session.refresh(delivery)
        assert delivery.status == "sent"
        assert delivery.attempt_count == 2
        assert delivery.claimed_at is None and delivery.lease_expires_at is None
        statuses = list(
            session.scalars(
                select(UserRealtimeEvent.payload).where(
                    UserRealtimeEvent.user_id == user_id,
                    UserRealtimeEvent.entity_id == delivery.id,
                )
            )
        )
        assert {item["status"] for item in statuses} == {
            "retry",
            "receipt_pending",
            "sent",
        }


class _MutableClock:
    def __init__(self, current):
        self.current = current

    def __call__(self):
        return self.current

    def advance(self, value):
        self.current += value


class _LeaseInspectingProvider:
    def __init__(self, session_factory, clock):
        self.session_factory = session_factory
        self.clock = clock
        self.claims = []

    def send(self, message):
        with self.session_factory() as session:
            delivery = session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == UUID(message.payload["notification_id"])
                )
            )
            self.claims.append((delivery.claimed_at, delivery.lease_expires_at, self.clock()))
        if len(self.claims) == 1:
            self.clock.advance(timedelta(minutes=3))
        return PushSendResult(f"provider-message-{len(self.claims)}")

    def receipt(self, provider_message_id):
        return PushReceiptResult()


def test_each_claim_uses_fresh_clock_after_slow_provider_work(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client, "fresh-lease@example.test", "Fresh Lease Centre")
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    with application.state.database.session_factory() as session:
        for index in range(2):
            notify_user(
                session,
                user_id=user_id,
                event_key=f"fresh-lease-{index}",
                category="system",
                severity="info",
                title="Generic",
                body="Generic",
            )
        session.commit()
        started_at = datetime.now(UTC) + timedelta(seconds=1)
        clock = _MutableClock(started_at)
        provider = _LeaseInspectingProvider(
            application.state.database.session_factory,
            clock,
        )
        result = deliver_pending_push_for_user(
            session,
            user_id=user_id,
            provider=provider,
            limit=2,
            clock=clock,
        )
        assert result.accepted == 2 and len(provider.claims) == 2
        first_claimed, first_lease, first_observed = provider.claims[0]
        second_claimed, second_lease, second_observed = provider.claims[1]
        first_claimed = first_claimed.replace(tzinfo=UTC)
        first_lease = first_lease.replace(tzinfo=UTC)
        second_claimed = second_claimed.replace(tzinfo=UTC)
        second_lease = second_lease.replace(tzinfo=UTC)
        assert first_claimed == first_observed == started_at
        assert first_lease == first_claimed + timedelta(minutes=2)
        assert second_claimed == second_observed == started_at + timedelta(minutes=3)
        assert second_lease == second_claimed + timedelta(minutes=2)


def test_push_worker_rechecks_subscription_after_durable_claim(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client)
    user_id = UUID(auth["user"]["id"])
    registered = _register_subscription(client, headers)
    subscription_id = UUID(registered.json()["id"])
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="revoke-after-claim",
            category="system",
            severity="info",
            title="Generic",
            body="Generic",
        )
        session.commit()
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )

        def revoke_after_claim(_):
            with application.state.database.session_factory() as competing:
                subscription = competing.get(PushSubscription, subscription_id)
                subscription.status = "revoked"
                subscription.delivery_address = None
                subscription.revoked_at = datetime.now(UTC)
                competing.commit()

        event.listen(session, "after_commit", revoke_after_claim, once=True)
        provider = _SuccessProvider()
        result = deliver_pending_push_for_user(
            session, user_id=user_id, provider=provider, now=datetime.now(UTC)
        )
        assert result.selected == 1 and result.sent == 0
        assert provider.messages == []
        session.refresh(delivery)
        assert delivery.status == "cancelled"
        assert delivery.last_error_code == "subscription_unavailable"


def test_push_worker_rechecks_preferences_after_durable_claim(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, headers = _register(client)
    user_id = UUID(auth["user"]["id"])
    _register_subscription(client, headers)
    assert client.get("/api/v1/notifications/preferences", headers=headers).status_code == 200
    with application.state.database.session_factory() as session:
        notification = notify_user(
            session,
            user_id=user_id,
            event_key="preference-after-claim",
            category="operations",
            severity="info",
            title="Generic",
            body="Generic",
        )
        session.commit()
        delivery = session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )

        def disable_after_claim(_):
            with application.state.database.session_factory() as competing:
                preference = competing.get(UserNotificationPreference, user_id)
                preference.push_enabled = False
                competing.commit()

        event.listen(session, "after_commit", disable_after_claim, once=True)
        provider = _SuccessProvider()
        result = deliver_pending_push_for_user(
            session, user_id=user_id, provider=provider, now=datetime.now(UTC)
        )
        assert result.selected == 1 and result.sent == 0
        assert provider.messages == []
        session.refresh(delivery)
        assert delivery.status == "suppressed"
        assert delivery.last_error_code == "preference_disabled"


def test_role_notification_scope_excludes_unrelated_room_educator(tmp_path):
    client, application, _ = _client(tmp_path)
    auth, _ = _register(client)
    organization_id = UUID(auth["user"]["organization_id"])
    owner_id = UUID(auth["user"]["id"])
    with application.state.database.session_factory() as session:
        educator_role = session.scalar(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.key == "educator",
            )
        )
        facility = Facility(
            organization_id=organization_id,
            name="Scoped Centre",
            license_number="PUSH-SCOPE-001",
            status="active",
            licensed_capacity=20,
        )
        session.add(facility)
        session.flush()
        program = Program(
            organization_id=organization_id,
            facility_id=facility.id,
            name="Daycare",
            program_type="daycare",
            capacity=20,
        )
        session.add(program)
        session.flush()
        room_a = Room(
            organization_id=organization_id,
            facility_id=facility.id,
            program_id=program.id,
            name="Infant A",
            capacity=10,
        )
        room_b = Room(
            organization_id=organization_id,
            facility_id=facility.id,
            program_id=program.id,
            name="Infant B",
            capacity=10,
        )
        session.add_all([room_a, room_b])
        session.flush()
        educators = []
        for index, room in enumerate((room_a, room_b), start=1):
            user = User(
                email=f"scoped-educator-{index}@example.test",
                password_hash="not-used",
                first_name="Scoped",
                last_name=f"Educator {index}",
                email_verified_at=datetime.now(UTC),
                email_verification_method="test",
            )
            session.add(user)
            session.flush()
            membership = OrganizationMembership(
                organization_id=organization_id,
                user_id=user.id,
                role_id=educator_role.id,
                status="active",
                joined_at=datetime.now(UTC),
            )
            session.add(membership)
            session.flush()
            session.add(
                MembershipRoomAssignment(
                    organization_id=organization_id,
                    membership_id=membership.id,
                    facility_id=facility.id,
                    room_id=room.id,
                    created_by_user_id=owner_id,
                )
            )
            address = f"ExpoPushToken[scoped-{index}-abcdefghijklmnopqrstuvwxyz]"
            session.add(
                PushSubscription(
                    user_id=user.id,
                    device_id=uuid4(),
                    transport="expo",
                    platform="android",
                    delivery_address=address,
                    address_digest=hashlib.sha256(address.encode()).hexdigest(),
                    status="active",
                )
            )
            educators.append(user)
        session.flush()
        notify_organization_members(
            session,
            organization_id=organization_id,
            permission_keys={"medication:record"},
            event_key="room-scoped-medication",
            category="operations",
            title="Medication plan ready",
            body="Review the assigned-room medication workspace.",
            action_path="/medications",
            action_entity_type="medication_plan",
            action_entity_id=uuid4(),
            facility_id=facility.id,
            room_id=room_a.id,
        )
        session.commit()
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserNotification)
                .where(UserNotification.user_id == educators[0].id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(NotificationDelivery)
                .where(NotificationDelivery.user_id == educators[0].id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserNotification)
                .where(UserNotification.user_id == educators[1].id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(NotificationDelivery)
                .where(NotificationDelivery.user_id == educators[1].id)
            )
            == 0
        )
