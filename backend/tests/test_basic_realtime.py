import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from starlette.websockets import WebSocketDisconnect

from alembic import command
from app.api.basic.realtime import _send
from app.basic.models import BasicBase, RealtimeEvent, RealtimeTicket, User
from app.basic.security import parse_one_time_token
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_ACTIVATION_PREVIOUS_REVISION = "0029A1_family_evidence_vault"
AUTHORITY_ACTIVATION_REVISION = "0029A2_authority_activation"
NORMAL_RELEASE_PREVIOUS_REVISION = "0029B_release_context"


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="realtime-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client, email, organization):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Realtime",
            "last_name": "Owner",
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def _ticket(client, headers):
    response = client.post("/api/v1/realtime/tickets", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_realtime_send_normalizes_closed_uvloop_transport_disconnect():
    class ClosedTransportWebSocket:
        async def send_json(self, _payload):
            raise RuntimeError(
                "unable to perform operation on <TCPTransport closed=True reading=False>; "
                "the handler is closed"
            )

    with pytest.raises(WebSocketDisconnect) as closed:
        asyncio.run(_send(ClosedTransportWebSocket(), {"type": "heartbeat"}))

    assert closed.value.code == 1006


def test_realtime_send_does_not_mask_unrelated_runtime_errors():
    class BrokenWebSocket:
        async def send_json(self, _payload):
            raise RuntimeError("unexpected serialization failure")

    with pytest.raises(RuntimeError, match="unexpected serialization failure"):
        asyncio.run(_send(BrokenWebSocket(), {"type": "heartbeat"}))


def test_realtime_ticket_is_single_use_and_replay_is_tenant_scoped(tmp_path):
    client, application = _client(tmp_path)
    first, first_headers = _register(client, "first-realtime@example.test", "First")
    second, _ = _register(client, "second-realtime@example.test", "Second")
    first_org = UUID(first["user"]["organization_id"])
    second_org = UUID(second["user"]["organization_id"])
    with application.state.database.session_factory() as session:
        session.add_all(
            [
                RealtimeEvent(
                    organization_id=second_org,
                    event_type="other.changed",
                    entity_type="other",
                    entity_id=uuid4(),
                    payload={"source": "test"},
                ),
                RealtimeEvent(
                    organization_id=first_org,
                    event_type="job.created",
                    entity_type="job",
                    entity_id=uuid4(),
                    payload={"source": "ats_event"},
                ),
            ]
        )
        session.commit()
    issued = _ticket(client, first_headers)
    with client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after=0"
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready" and ready["organization_id"] == str(first_org)
        event = websocket.receive_json()
        assert event["type"] == "event" and event["event"]["type"] == "job.created"
        assert event["event"]["payload"] == {"source": "ats_event"}
        cursor = event["cursor"]
    replacement = _ticket(client, first_headers)
    with client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={replacement['ticket']}&after={cursor}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "ready"
    with pytest.raises(WebSocketDisconnect) as reused, client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after=0"
    ) as websocket:
        websocket.receive_json()
    assert reused.value.code == 4401


def test_realtime_ticket_expiry_and_membership_scope_fail_closed(tmp_path):
    client, application = _client(tmp_path)
    auth, headers = _register(client, "expired-realtime@example.test", "Expiry")
    issued = _ticket(client, headers)
    organization_id, ticket_id, _ = parse_one_time_token(issued["ticket"])
    with application.state.database.session_factory() as session:
        ticket = session.scalar(
            select(RealtimeTicket).where(
                RealtimeTicket.organization_id == organization_id,
                RealtimeTicket.id == ticket_id,
            )
        )
        ticket.created_at = datetime.now(UTC) - timedelta(seconds=120)
        ticket.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with pytest.raises(WebSocketDisconnect) as expired, client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after=0"
    ) as websocket:
        websocket.receive_json()
    assert expired.value.code == 4401

    active = _ticket(client, headers)
    with application.state.database.session_factory() as session:
        ticket = session.scalar(
            select(RealtimeTicket)
            .where(
                RealtimeTicket.token_digest != "",
                RealtimeTicket.organization_id == UUID(auth["user"]["organization_id"]),
                RealtimeTicket.consumed_at.is_(None),
            )
            .order_by(RealtimeTicket.created_at.desc())
        )
        from app.basic.models import OrganizationMembership

        membership = session.get(OrganizationMembership, ticket.membership_id)
        membership.status = "revoked"
        session.commit()
    with pytest.raises(WebSocketDisconnect) as revoked, client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={active['ticket']}&after=0"
    ) as websocket:
        websocket.receive_json()
    assert revoked.value.code == 4403


def test_realtime_replay_is_bounded_and_requires_reset(tmp_path):
    client, application = _client(tmp_path)
    auth, headers = _register(client, "reset-realtime@example.test", "Reset")
    organization_id = UUID(auth["user"]["organization_id"])
    with application.state.database.session_factory() as session:
        session.add_all(
            [
                RealtimeEvent(
                    organization_id=organization_id,
                    event_type="test.changed",
                    entity_type="test",
                    entity_id=uuid4(),
                    payload={"source": "test"},
                )
                for _ in range(501)
            ]
        )
        session.commit()
    issued = _ticket(client, headers)
    with client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after=0"
    ) as websocket:
        reset = websocket.receive_json()
        assert reset["type"] == "reset_required"
        assert reset["reason"] == "replay_limit_exceeded"
        assert reset["max_replay"] == 500
        assert reset["resume_from"] == 0
        assert reset["latest_available_cursor"] > 0
        assert reset["cursor_must_not_advance"] is True


def test_realtime_cursor_ahead_requires_checkpoint_replacement(tmp_path):
    client, application = _client(tmp_path)
    auth, headers = _register(client, "cursor-ahead@example.test", "Cursor Ahead")
    organization_id = UUID(auth["user"]["organization_id"])
    with application.state.database.session_factory() as session:
        latest = session.scalar(
            select(func.max(RealtimeEvent.sequence_id)).where(
                RealtimeEvent.organization_id == organization_id
            )
        ) or 0
    requested = latest + 1000
    issued = _ticket(client, headers)
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after={requested}"
    ) as websocket:
        reset = websocket.receive_json()
        assert reset["type"] == "reset_required"
        assert reset["reason"] == "cursor_ahead"
        assert reset["requested_after"] == requested
        assert reset["resume_from"] == latest
        assert reset["latest_available_cursor"] == latest
        assert reset["cursor_must_not_advance"] is True
        websocket.receive_json()
    assert closed.value.code == 4408


def test_realtime_open_connection_closes_after_auth_version_revocation(tmp_path):
    client, application = _client(tmp_path)
    auth, headers = _register(client, "live-auth-revoke@example.test", "Live Revoke")
    issued = _ticket(client, headers)
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={issued['ticket']}&after=0"
    ) as websocket:
        assert websocket.receive_json()["type"] == "ready"
        with application.state.database.session_factory() as session:
            user = session.get(User, UUID(auth["user"]["id"]))
            user.auth_version += 1
            session.commit()
        websocket.receive_json()
    assert closed.value.code == 4403


def test_realtime_migration_bridges_audit_and_ats_ledgers(tmp_path, monkeypatch):
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    organization_id = "11111111111111111111111111111111"
    audit_id = "22222222222222222222222222222222"
    ats_id = "33333333333333333333333333333333"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id,name,status,verification_status,timezone,preferences) "
                "VALUES (:id,'Realtime','active','pending','America/Edmonton','{}')"
            ),
            {"id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id,organization_id,action,entity_type,occurred_at,details) "
                "VALUES (:id,:org,'attendance.checked_in','attendance_day',CURRENT_TIMESTAMP,'{}')"
            ),
            {"id": audit_id, "org": organization_id},
        )
        confidential_authority_actions = (
            "family.authority.person.created",
            "child.release.authorization.granted",
            "child.consent.recorded",
            "organization.consent.policy.published",
        )
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id,organization_id,action,entity_type,entity_id,occurred_at,details) "
                "VALUES (:id,:org,:action,'confidential_authority',:entity_id,"
                "CURRENT_TIMESTAMP,'{}')"
            ),
            [
                {
                    "id": uuid4().hex,
                    "org": organization_id,
                    "action": action,
                    "entity_id": uuid4().hex,
                }
                for action in confidential_authority_actions
            ],
        )
        connection.execute(
            text(
                "INSERT INTO users (id,email,password_hash,first_name,last_name,is_active) "
                "VALUES ('44444444444444444444444444444444','trigger@example.test',"
                "'not-used','Trigger','Actor',1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO ats_events "
                "(id,organization_id,actor_user_id,event_type,entity_type,entity_id,occurred_at) "
                "VALUES (:id,:org,:user,'job.created','job',:entity,CURRENT_TIMESTAMP)"
            ),
            {
                "id": ats_id,
                "org": organization_id,
                "user": "44444444444444444444444444444444",
                "entity": "55555555555555555555555555555555",
            },
        )
        rows = (
            connection.execute(
                text(
                    "SELECT event_type, entity_type, payload FROM realtime_events "
                    "WHERE organization_id=:org ORDER BY sequence_id"
                ),
                {"org": organization_id},
            )
            .mappings()
            .all()
        )
        assert [row["event_type"] for row in rows] == [
            "attendance.checked_in",
            "job.created",
        ]
        assert all("details" not in row["payload"] for row in rows)
        assert connection.scalar(
            text(
                "SELECT count(*) FROM audit_events "
                "WHERE organization_id=:org AND action IN "
                "('family.authority.person.created',"
                "'child.release.authorization.granted',"
                "'child.consent.recorded',"
                "'organization.consent.policy.published')"
            ),
            {"org": organization_id},
        ) == len(confidential_authority_actions)
        assert connection.scalar(
            text(
                "SELECT count(*) FROM realtime_events "
                "WHERE organization_id=:org AND event_type IN "
                "('family.authority.person.created',"
                "'child.release.authorization.granted',"
                "'child.consent.recorded',"
                "'organization.consent.policy.published')"
            ),
            {"org": organization_id},
        ) == 0
    engine.dispose()
    command.check(config)
    command.downgrade(config, NORMAL_RELEASE_PREVIOUS_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_REVISION)
    command.downgrade(config, AUTHORITY_ACTIVATION_PREVIOUS_REVISION)
    command.downgrade(config, "0029A_family_authority_kernel")
    command.downgrade(config, "0028_childcare_command_spine")
    command.downgrade(config, "0010_staff_ops")
