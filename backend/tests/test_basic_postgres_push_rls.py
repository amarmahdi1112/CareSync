"""Opt-in PostgreSQL checks for private push/realtime RLS and trigger fan-out."""

from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.basic.notifications import notify_user
from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _register(client: TestClient, email: str, organization: str):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "Push",
            "last_name": "RLS",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    subscription = client.post(
        "/api/v1/notifications/push/subscriptions",
        headers=headers,
        json={
            "device_id": str(uuid4()),
            "transport": "expo",
            "platform": "android",
            "delivery_address": f"ExpoPushToken[{uuid4().hex}]",
        },
    )
    assert subscription.status_code == 201, subscription.text
    assert "delivery_address" not in subscription.json()
    ticket = client.post("/api/v1/notifications/realtime/tickets", headers=headers)
    assert ticket.status_code == 201, ticket.text
    return body, headers


def test_push_trigger_and_private_stream_are_user_scoped_under_runtime_role() -> None:
    host = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    database = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=host,
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=database,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-push-test-secret-at-least-32-bytes",
    )
    application = create_app(settings)
    run_id = uuid4().hex
    with TestClient(application) as client:
        first, _ = _register(
            client, f"push-rls-one+{run_id}@example.test", f"Push RLS One {run_id}"
        )
        second, _ = _register(
            client, f"push-rls-two+{run_id}@example.test", f"Push RLS Two {run_id}"
        )

    runtime_url = URL.create(
        "postgresql+psycopg",
        username="caresync_basic_app",
        host=host,
        port=int(TEST_PORT or "0"),
        database=database,
    )
    engine = create_engine(runtime_url)
    first_user = UUID(first["user"]["id"])
    first_org = UUID(first["user"]["organization_id"])
    second_user = UUID(second["user"]["id"])
    second_org = UUID(second["user"]["organization_id"])
    notification_id = uuid4()
    with engine.connect() as connection:
        expected_policies = {
            "notification_push_subscriptions": {
                "push_subscriptions_owner_select",
                "push_subscriptions_owner_insert",
                "push_subscriptions_owner_update",
                "push_subscriptions_address_transfer_select",
                "push_subscriptions_address_transfer",
            },
            "notification_deliveries": {
                "notification_deliveries_owner_select",
                "notification_deliveries_context_insert",
                "notification_deliveries_owner_update",
                "notification_deliveries_address_transfer_select",
                "notification_deliveries_address_transfer_update",
            },
            "user_realtime_events": {
                "user_realtime_events_owner_select",
                "user_realtime_events_context_insert",
            },
            "user_realtime_tickets": {"user_realtime_tickets_owner"},
        }
        for table_name, policies in expected_policies.items():
            assert (
                connection.execute(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE oid=CAST(:table_name AS regclass)"
                    ),
                    {"table_name": table_name},
                ).scalar_one()
                is True
            )
            assert (
                set(
                    connection.execute(
                        text(
                            "SELECT policyname FROM pg_policies "
                            "WHERE schemaname=current_schema() AND tablename=:table_name"
                        ),
                        {"table_name": table_name},
                    ).scalars()
                )
                == policies
            )
        for table_name in (
            "notification_push_subscriptions",
            "notification_deliveries",
            "user_realtime_tickets",
        ):
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                assert (
                    connection.execute(
                        text("SELECT has_table_privilege(current_user,:table_name,:privilege)"),
                        {"table_name": table_name, "privilege": privilege},
                    ).scalar_one()
                    is True
                )
            assert (
                connection.execute(
                    text("SELECT has_table_privilege(current_user,:table_name,'DELETE')"),
                    {"table_name": table_name},
                ).scalar_one()
                is False
            )
        for privilege, expected in (
            ("SELECT", True),
            ("INSERT", True),
            ("UPDATE", False),
            ("DELETE", False),
        ):
            assert (
                connection.execute(
                    text(
                        "SELECT has_table_privilege(current_user,'user_realtime_events',:privilege)"
                    ),
                    {"privilege": privilege},
                ).scalar_one()
                is expected
            )
        trigger_security = connection.execute(
            text(
                "SELECT prosecdef, proconfig FROM pg_proc "
                "WHERE oid='public.user_notification_enqueue_trigger()'::regprocedure"
            )
        ).one()
        assert trigger_security[0] is False
        assert "search_path=pg_catalog" in (trigger_security[1] or [])

        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM notification_push_subscriptions")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM user_realtime_tickets")).scalar_one() == 1
        )
        connection.execute(
            text(
                "INSERT INTO user_notifications "
                "(id,user_id,organization_id,event_key,category,severity,title,body,created_at) "
                "VALUES (:id,:user,:org,'push-rls-event','assignment','warning',"
                "'Private title','Private body',CURRENT_TIMESTAMP)"
            ),
            {"id": notification_id, "user": first_user, "org": first_org},
        )
        delivery = (
            connection.execute(
                text(
                    "SELECT status,payload FROM notification_deliveries "
                    "WHERE notification_id=:notification"
                ),
                {"notification": notification_id},
            )
            .mappings()
            .one()
        )
        payload = delivery["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert delivery["status"] == "pending"
        assert payload == {
            "type": "notification",
            "notification_id": str(notification_id),
            "category": "assignment",
            "severity": "warning",
        }
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM user_realtime_events "
                    "WHERE entity_id=:notification AND event_type='notification.created'"
                ),
                {"notification": notification_id},
            ).scalar_one()
            == 1
        )
        connection.commit()

        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(second_user)},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(second_org)},
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM notification_deliveries "
                    "WHERE notification_id=:notification"
                ),
                {"notification": notification_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_realtime_events WHERE entity_id=:notification"),
                {"notification": notification_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM notification_push_subscriptions")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM user_realtime_tickets")).scalar_one() == 1
        )
        connection.rollback()
    engine.dispose()


def test_cross_recipient_retry_and_push_address_transfer_work_for_nobypass_runtime() -> None:
    host = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    database = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=host,
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=database,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-push-transfer-test-at-least-32-bytes",
    )
    application = create_app(settings)
    run_id = uuid4().hex
    with TestClient(application) as client:
        first, first_headers = _register(
            client,
            f"push-transfer-one+{run_id}@example.test",
            f"Push Transfer One {run_id}",
        )
        second, second_headers = _register(
            client,
            f"push-transfer-two+{run_id}@example.test",
            f"Push Transfer Two {run_id}",
        )
        shared_token = f"ExpoPushToken[shared-postgres-{run_id}]"
        first_shared = client.post(
            "/api/v1/notifications/push/subscriptions",
            headers=first_headers,
            json={
                "device_id": str(uuid4()),
                "transport": "expo",
                "platform": "android",
                "delivery_address": shared_token,
            },
        )
        assert first_shared.status_code == 201, first_shared.text
        first_user = UUID(first["user"]["id"])
        first_org = UUID(first["user"]["organization_id"])
        with application.state.database.session_factory() as session:
            session.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": str(first_user)},
            )
            session.execute(
                text("SELECT set_config('app.current_organization_id', :value, true)"),
                {"value": str(first_org)},
            )
            before_transfer = notify_user(
                session,
                user_id=first_user,
                organization_id=first_org,
                event_key="before-token-transfer",
                category="system",
                severity="info",
                title="Generic title",
                body="Generic body",
            )
            pending_delivery_id = session.scalar(
                text(
                    "SELECT id FROM notification_deliveries "
                    "WHERE notification_id=:notification AND subscription_id=:subscription"
                ),
                {
                    "notification": before_transfer.id,
                    "subscription": UUID(first_shared.json()["id"]),
                },
            )
            assert pending_delivery_id is not None
            session.commit()
        second_shared = client.post(
            "/api/v1/notifications/push/subscriptions",
            headers=second_headers,
            json={
                "device_id": str(uuid4()),
                "transport": "expo",
                "platform": "android",
                "delivery_address": shared_token,
            },
        )
        assert second_shared.status_code == 201, second_shared.text

    runtime_url = URL.create(
        "postgresql+psycopg",
        username="caresync_basic_app",
        host=host,
        port=int(TEST_PORT or "0"),
        database=database,
    )
    engine = create_engine(runtime_url)
    second_user = UUID(second["user"]["id"])
    second_org = UUID(second["user"]["organization_id"])
    admin_engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="postgres",
            host=host,
            port=int(TEST_PORT or "0"),
            database=database,
        )
    )
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id,organization_id,user_id,role_id,status,joined_at,created_at,updated_at) "
                "SELECT gen_random_uuid(),:organization,:user,roles.id,'active',"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP "
                "FROM roles WHERE roles.organization_id=:organization "
                "AND roles.key='educator'"
            ),
            {"organization": first_org, "user": second_user},
        )
    admin_engine.dispose()
    with Session(engine) as session:
        session.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        session.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        created = notify_user(
            session,
            user_id=second_user,
            organization_id=first_org,
            event_key="cross-user-retry",
            category="assignment",
            severity="info",
            title="Generic title",
            body="Generic body",
        )
        notification_id = created.id
        assert (
            notify_user(
                session,
                user_id=second_user,
                organization_id=first_org,
                event_key="cross-user-retry",
                category="assignment",
                severity="info",
                title="Generic title",
                body="Generic body",
            )
            is None
        )
        session.commit()
    with Session(engine) as session:
        session.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        session.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        with pytest.raises(ProgrammingError):
            notify_user(
                session,
                user_id=second_user,
                organization_id=second_org,
                event_key="unauthorized-cross-tenant",
                category="system",
                severity="info",
                title="Must fail",
                body="Must fail",
            )
        session.rollback()
    with engine.connect() as connection:
        role_flags = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert role_flags == (False, False)
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(second_user)},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_notifications WHERE event_key='cross-user-retry'")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM notification_deliveries "
                    "WHERE notification_id=:notification"
                ),
                {"notification": notification_id},
            ).scalar_one()
            >= 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM notification_push_subscriptions "
                    "WHERE id=:subscription AND status='active'"
                ),
                {"subscription": UUID(second_shared.json()["id"])},
            ).scalar_one()
            == 1
        )
        connection.rollback()

        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        transferred = connection.execute(
            text(
                "SELECT status, delivery_address FROM notification_push_subscriptions "
                "WHERE id=:subscription"
            ),
            {"subscription": UUID(first_shared.json()["id"])},
        ).one()
        assert transferred == ("revoked", None)
        assert (
            connection.execute(
                text("SELECT status FROM notification_deliveries WHERE id=:delivery"),
                {"delivery": pending_delivery_id},
            ).scalar_one()
            == "cancelled"
        )
        connection.rollback()
    engine.dispose()
