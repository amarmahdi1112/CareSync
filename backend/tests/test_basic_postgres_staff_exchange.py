"""Opt-in PostgreSQL proofs for staff exchange RLS and race serialization.

The suite is skipped unless ``BASIC_POSTGRES_TEST_PORT`` points at a disposable,
already-migrated PostgreSQL cluster. It must never target either retained CareSync port.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL

from app.core.config import Settings
from app.main import create_app
from tests.test_basic_staff_exchange import (
    PASSWORD,
    _create_posted_open_shift,
    _educator,
    _facility_tree,
    _headers,
    _offer,
    _opt_in_substitute,
    _published_acknowledged_schedule,
    _register,
)

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _settings() -> Settings:
    port = int(TEST_PORT or "0")
    assert port not in {5433, 5434}, "Legacy and live CareSync ports are forbidden"
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        database_port=port,
        database_user="caresync_basic_app",
        database_password="",
        database_name=os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-staff-exchange-secret-at-least-32-bytes",
    )


def _application(settings: Settings):
    application = create_app(settings)

    @event.listens_for(application.state.database.engine, "connect")
    def configure_timeouts(dbapi_connection, _connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '15s'")

    return application


def _scenario(client: TestClient, suffix: str = "pg"):
    owner = _register(client, f"{suffix}-{uuid4().hex}")
    owner_headers = _headers(owner)
    facility, room = _facility_tree(client, owner_headers, suffix.title())
    educators = [
        _educator(client, owner_headers, facility, room, name)
        for name in (f"{suffix}-ada", f"{suffix}-grace")
    ]
    return owner, owner_headers, educators, facility, room


def _manager(
    client: TestClient,
    owner_headers: dict[str, str],
    facility: dict,
    room: dict,
    suffix: str,
) -> dict:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    role = next(item for item in workspace.json()["roles"] if item["key"] == "administrator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"exchange-manager-{suffix}-{uuid4()}@example.test",
            "first_name": suffix.title(),
            "last_name": "Manager",
            "role_id": role["id"],
            "assigned_facility_ids": [],
            "assigned_room_ids": [],
        },
    )
    assert invitation.status_code == 201, invitation.text
    token = parse_qs(urlparse(invitation.json()["activation_url"]).fragment)["token"][0]
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": token, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _seed_each_exchange_projection(client: TestClient, suffix: str):
    owner, owner_headers, educators, facility, room = _scenario(client, suffix)
    rotation = client.post(
        "/api/v1/staff-exchange/rotations",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "name": "PostgreSQL rotation",
            "anchor_date": "2029-01-01",
            "cycle_weeks": 1,
            "slots": [
                {
                    "slot_id": str(uuid4()),
                    "cycle_week": 0,
                    "weekday": 0,
                    "staff_user_id": educators[0]["user"]["id"],
                    "room_id": room["id"],
                    "start_local": "08:00",
                    "end_local": "16:00",
                    "notes": None,
                }
            ],
        },
    )
    assert rotation.status_code == 201, rotation.text
    open_shift = _create_posted_open_shift(
        client,
        owner_headers,
        facility,
        room,
        datetime(2029, 2, 1, 15, 0, tzinfo=UTC),
    )
    interest = client.post(
        f"/api/v1/staff/self/exchange/open-shifts/{open_shift['id']}/interest",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "expected_updated_at": open_shift["updated_at"],
            "note": "Interested",
        },
    )
    assert interest.status_code == 201, interest.text
    _opt_in_substitute(client, educators[1], facility)
    schedule = _published_acknowledged_schedule(
        client,
        owner_headers,
        educators[0],
        facility,
        room,
        datetime(2029, 3, 1, 15, 0, tzinfo=UTC),
    )
    swap = client.post(
        "/api/v1/staff/self/exchange/swaps",
        headers=_headers(educators[0]),
        json={
            "client_operation_id": str(uuid4()),
            "kind": "cover",
            "requester_schedule_id": schedule["id"],
            "counterparty_membership_id": educators[1]["user"]["membership_id"],
            "counterparty_schedule_id": None,
            "note": "Coverage",
        },
    )
    assert swap.status_code == 201, swap.text
    return owner


def test_runtime_role_exchange_rls_grants_and_tenant_filtering() -> None:
    settings = _settings()
    application = _application(settings)
    with TestClient(application) as client:
        organizations = [
            _seed_each_exchange_projection(client, "first"),
            _seed_each_exchange_projection(client, "second"),
        ]

    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="caresync_basic_app",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    mutable_tables = (
        "staff_rotation_patterns",
        "staff_open_shifts",
        "staff_open_shift_engagements",
        "staff_substitute_profiles",
        "staff_shift_swap_requests",
    )
    with engine.connect() as connection:
        for table_name in mutable_tables:
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
            assert set(
                connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname=current_schema() AND tablename=:table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
            ) == {f"{table_name}_tenant"}
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = connection.execute(
                    text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                    {"table": table_name, "privilege": privilege},
                ).scalar_one()
                assert granted is (privilege in {"SELECT", "INSERT", "UPDATE"})
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user,'staff_workforce_events',:privilege)"
                ),
                {"privilege": privilege},
            ).scalar_one()
            assert granted is (privilege in {"SELECT", "INSERT"})
        swap_indexes = set(
            connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname=current_schema() "
                    "AND tablename='staff_shift_swap_requests'"
                )
            ).scalars()
        )
        assert {
            "ix_staff_shift_swaps_requester_sched",
            "ix_staff_shift_swaps_counterparty_sched",
        }.issubset(swap_indexes)

        for owner in organizations:
            connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": owner["user"]["id"]},
            )
            connection.execute(
                text("SELECT set_config('app.current_organization_id', :value, true)"),
                {"value": owner["user"]["organization_id"]},
            )
            for table_name in mutable_tables:
                assert (
                    connection.execute(text(f"SELECT count(*) FROM {table_name}")).scalar_one() == 1
                )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM staff_workforce_events "
                        "WHERE entity_type IN ('staff_rotation_pattern','staff_open_shift',"
                        "'staff_open_shift_engagement','staff_substitute_profile',"
                        "'staff_shift_swap')"
                    )
                ).scalar_one()
                >= 5
            )
            connection.rollback()
    engine.dispose()


def test_offer_creation_does_not_require_workforce_ledger_update() -> None:
    settings = _settings()
    application = _application(settings)
    with TestClient(application, raise_server_exceptions=False) as client:
        owner, owner_headers, educators, facility, room = _scenario(client, "offer-ledger")
        open_shift = _create_posted_open_shift(
            client,
            owner_headers,
            facility,
            room,
            datetime(2029, 3, 19, 14, 0, tzinfo=UTC),
        )
        _opt_in_substitute(client, educators[0], facility)
        offer, _ = _offer(client, owner_headers, open_shift, educators[0])
        assert offer["status"] == "pending"

    owner_engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="postgres",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    target_user_id = UUID(educators[0]["user"]["id"])
    with owner_engine.connect() as connection:
        target_event_id = connection.execute(
            text(
                "SELECT event.id FROM user_realtime_events AS event "
                "JOIN user_notifications AS notification ON notification.id=event.id "
                "WHERE event.user_id=:user_id AND event.event_type='notification.created' "
                "AND notification.action_entity_type='staff_open_shift_engagement' "
                "AND notification.action_entity_id=:entity_id"
            ),
            {"user_id": target_user_id, "entity_id": UUID(offer["id"])},
        ).scalar_one()
    owner_engine.dispose()

    runtime_engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="caresync_basic_app",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    with runtime_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE oid='user_realtime_events'::regclass"
                )
            ).scalar_one()
            is True
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": owner["user"]["id"]},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": owner["user"]["organization_id"]},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_realtime_events WHERE id=:id"),
                {"id": target_event_id},
            ).scalar_one()
            == 0
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(target_user_id)},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_realtime_events WHERE id=:id"),
                {"id": target_event_id},
            ).scalar_one()
            == 1
        )
        connection.rollback()
    runtime_engine.dispose()


def test_direct_offer_and_substitute_opt_out_are_serialized() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        _, owner_headers, educators, facility, room = _scenario(first_client, "optout-race")
        educator = educators[0]
        profile = _opt_in_substitute(first_client, educator, facility)
        open_shift = _create_posted_open_shift(
            first_client,
            owner_headers,
            facility,
            room,
            datetime(2029, 3, 26, 14, 0, tzinfo=UTC),
        )
        offer_body = {
            "client_operation_id": str(uuid4()),
            "staff_user_id": educator["user"]["id"],
            "source_interest_id": None,
            "note": "Concurrent direct offer",
            "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        }
        delete_body = {
            "client_operation_id": str(uuid4()),
            "expected_updated_at": profile["updated_at"],
        }
        barrier = Barrier(3)
        responses = {}
        failures = []

        def offer() -> None:
            try:
                barrier.wait(timeout=5)
                responses["offer"] = first_client.post(
                    f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/offers",
                    headers=owner_headers,
                    json=offer_body,
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        def opt_out() -> None:
            try:
                barrier.wait(timeout=5)
                responses["opt_out"] = second_client.request(
                    "DELETE",
                    f"/api/v1/staff/self/exchange/substitute-profiles/{facility['id']}",
                    headers=_headers(educator),
                    json=delete_body,
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        threads = [Thread(target=offer, daemon=True), Thread(target=opt_out, daemon=True)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()

        assert not failures
        assert responses["opt_out"].status_code == 200, responses["opt_out"].text
        assert responses["offer"].status_code in {201, 409}, responses["offer"].text
        assert all(response.status_code < 500 for response in responses.values())
        profiles = first_client.get(
            "/api/v1/staff/self/exchange/substitute-profiles",
            headers=_headers(educator),
        )
        assert profiles.status_code == 200, profiles.text
        canonical_profile = next(
            item for item in profiles.json()["items"] if item["facility_id"] == facility["id"]
        )
        assert canonical_profile["active"] is False
        engagements = first_client.get(
            f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/engagements",
            headers=owner_headers,
        )
        assert engagements.status_code == 200, engagements.text
        if responses["offer"].status_code == 201:
            assert engagements.json()["total"] == 1
            assert engagements.json()["items"][0]["status"] == "pending"
        else:
            assert responses["offer"].json()["detail"]["code"] == ("substitute_opt_in_required")
            assert engagements.json()["items"] == []


def test_concurrent_offer_acceptance_creates_exactly_one_assignment() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        _, owner_headers, educators, facility, room = _scenario(first_client, "accept-race")
        open_shift = _create_posted_open_shift(
            first_client,
            owner_headers,
            facility,
            room,
            datetime(2029, 4, 2, 14, 0, tzinfo=UTC),
        )
        offers = []
        for educator in educators:
            _opt_in_substitute(first_client, educator, facility)
            offer, _ = _offer(first_client, owner_headers, open_shift, educator)
            offers.append(offer)

        barrier = Barrier(3)
        responses = []
        failures = []

        def accept(client: TestClient, educator: dict, offer: dict) -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    client.post(
                        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
                        headers=_headers(educator),
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_updated_at": offer["updated_at"],
                            "note": "Accepted concurrently",
                        },
                    )
                )
            except Exception as error:  # pragma: no cover - diagnostic path
                failures.append(error)

        threads = [
            Thread(
                target=accept,
                args=(client, educator, offer),
                daemon=True,
            )
            for client, educator, offer in zip(
                (first_client, second_client), educators, offers, strict=True
            )
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()

        assert not failures
        assert sorted(response.status_code for response in responses) == [200, 409]
        engagements = first_client.get(
            f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/engagements",
            headers=owner_headers,
        )
        assert engagements.status_code == 200, engagements.text
        statuses = sorted(item["status"] for item in engagements.json()["items"])
        assert statuses == ["accepted", "superseded"]
        schedules = first_client.get(
            "/api/v1/staff-schedules",
            headers=owner_headers,
            params={
                "start_at": "2029-04-02T00:00:00Z",
                "end_at": "2029-04-03T00:00:00Z",
            },
        )
        assert schedules.status_code == 200, schedules.text
        generated = [
            item
            for item in schedules.json()["items"]
            if item["origin_type"] == "open_shift" and item["origin_id"] == open_shift["id"]
        ]
        assert len(generated) == 1
        assert generated[0]["status"] == "published"
        assert generated[0]["response_status"] == "acknowledged"


def test_offer_accept_and_manager_cancel_have_one_atomic_terminal_outcome() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        _, owner_headers, educators, facility, room = _scenario(first_client, "cancel-race")
        open_shift = _create_posted_open_shift(
            first_client,
            owner_headers,
            facility,
            room,
            datetime(2029, 4, 16, 14, 0, tzinfo=UTC),
        )
        _opt_in_substitute(first_client, educators[0], facility)
        offer, _ = _offer(first_client, owner_headers, open_shift, educators[0])
        barrier = Barrier(3)
        responses = []
        failures = []

        def accept() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    first_client.post(
                        f"/api/v1/staff/self/exchange/open-shift-offers/{offer['id']}/accept",
                        headers=_headers(educators[0]),
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_updated_at": offer["updated_at"],
                            "note": "Concurrent acceptance",
                        },
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        def cancel() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    second_client.post(
                        f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/cancel",
                        headers=owner_headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_updated_at": open_shift["updated_at"],
                            "reason": "Concurrent manager cancellation",
                        },
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        threads = [Thread(target=accept, daemon=True), Thread(target=cancel, daemon=True)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()

        assert not failures
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert all(response.status_code < 500 for response in responses)
        shifts = first_client.get(
            "/api/v1/staff-exchange/open-shifts",
            headers=owner_headers,
            params={
                "start_at": "2029-04-16T00:00:00Z",
                "end_at": "2029-04-17T00:00:00Z",
            },
        )
        assert shifts.status_code == 200, shifts.text
        canonical = next(item for item in shifts.json()["items"] if item["id"] == open_shift["id"])
        engagements = first_client.get(
            f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/engagements",
            headers=owner_headers,
        )
        assert engagements.status_code == 200, engagements.text
        canonical_offer = next(
            item for item in engagements.json()["items"] if item["id"] == offer["id"]
        )
        schedules = first_client.get(
            "/api/v1/staff-schedules",
            headers=owner_headers,
            params={
                "start_at": "2029-04-16T00:00:00Z",
                "end_at": "2029-04-17T00:00:00Z",
            },
        )
        generated = [
            item
            for item in schedules.json()["items"]
            if item["origin_type"] == "open_shift" and item["origin_id"] == open_shift["id"]
        ]
        if canonical["status"] == "filled":
            assert canonical_offer["status"] == "accepted"
            assert len(generated) == 1
        else:
            assert canonical["status"] == "cancelled"
            assert canonical_offer["status"] == "superseded"
            assert generated == []


def test_swap_approval_and_source_cancellation_never_partially_commit() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        _, owner_headers, educators, facility, room = _scenario(first_client, "swap-race")
        source = _published_acknowledged_schedule(
            first_client,
            owner_headers,
            educators[0],
            facility,
            room,
            datetime(2029, 5, 1, 14, 0, tzinfo=UTC),
        )
        swap = first_client.post(
            "/api/v1/staff/self/exchange/swaps",
            headers=_headers(educators[0]),
            json={
                "client_operation_id": str(uuid4()),
                "kind": "cover",
                "requester_schedule_id": source["id"],
                "counterparty_membership_id": educators[1]["user"]["membership_id"],
                "counterparty_schedule_id": None,
                "note": "Race proof",
            },
        )
        assert swap.status_code == 201, swap.text
        accepted = first_client.post(
            f"/api/v1/staff/self/exchange/swaps/{swap.json()['id']}/accept",
            headers=_headers(educators[1]),
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": swap.json()["updated_at"],
                "note": "Accepted",
            },
        )
        assert accepted.status_code == 200, accepted.text
        barrier = Barrier(3)
        responses = []
        failures = []

        def approve() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    first_client.post(
                        f"/api/v1/staff-exchange/swaps/{swap.json()['id']}/approve",
                        headers=owner_headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "expected_updated_at": accepted.json()["updated_at"],
                        },
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        def cancel_source() -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    second_client.post(
                        f"/api/v1/staff-schedules/{source['id']}/cancel",
                        headers=owner_headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "reason": "Concurrent manager cancellation",
                        },
                    )
                )
            except Exception as error:  # pragma: no cover
                failures.append(error)

        threads = [Thread(target=approve, daemon=True), Thread(target=cancel_source, daemon=True)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()

        assert not failures
        assert sorted(response.status_code for response in responses) == [200, 409]
        swaps = first_client.get(
            "/api/v1/staff-exchange/swaps",
            headers=owner_headers,
            params={
                "start_at": "2029-05-01T00:00:00Z",
                "end_at": "2029-05-02T00:00:00Z",
            },
        )
        assert swaps.status_code == 200, swaps.text
        canonical = next(item for item in swaps.json()["items"] if item["id"] == swap.json()["id"])
        if canonical["status"] == "approved":
            assert canonical["requester_replacement_schedule_id"] is not None
            assert canonical["counterparty_replacement_schedule_id"] is None
        else:
            assert canonical["status"] == "pending_manager"
            assert canonical["requester_replacement_schedule_id"] is None
            assert canonical["counterparty_replacement_schedule_id"] is None


def test_peer_manager_notifications_are_safe_refreshable_and_rls_private() -> None:
    settings = _settings()
    application = _application(settings)
    with TestClient(application, raise_server_exceptions=False) as client:
        owner, owner_headers, educators, facility, room = _scenario(client, "peer-manager")
        manager_a = _manager(client, owner_headers, facility, room, "manager-a")
        manager_b = _manager(client, owner_headers, facility, room, "manager-b")
        manager_a_headers = _headers(manager_a)

        _opt_in_substitute(client, educators[0], facility)
        open_shift = _create_posted_open_shift(
            client,
            manager_a_headers,
            facility,
            room,
            datetime(2030, 1, 7, 15, 0, tzinfo=UTC),
        )
        offer, _ = _offer(
            client,
            manager_a_headers,
            open_shift,
            educators[0],
            note="Private note must not reach peer managers",
        )
        withdrawn = client.post(
            f"/api/v1/staff-exchange/open-shift-engagements/{offer['id']}/withdraw",
            headers=manager_a_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": offer["updated_at"],
                "note": "Private withdrawal reason",
            },
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["status"] == "withdrawn"

        def pending_cover(start: datetime) -> dict:
            source = _published_acknowledged_schedule(
                client,
                owner_headers,
                educators[0],
                facility,
                room,
                start,
            )
            created = client.post(
                "/api/v1/staff/self/exchange/swaps",
                headers=_headers(educators[0]),
                json={
                    "client_operation_id": str(uuid4()),
                    "kind": "cover",
                    "requester_schedule_id": source["id"],
                    "counterparty_membership_id": educators[1]["user"]["membership_id"],
                    "counterparty_schedule_id": None,
                    "note": "Private educator request",
                },
            )
            assert created.status_code == 201, created.text
            accepted = client.post(
                f"/api/v1/staff/self/exchange/swaps/{created.json()['id']}/accept",
                headers=_headers(educators[1]),
                json={
                    "client_operation_id": str(uuid4()),
                    "expected_updated_at": created.json()["updated_at"],
                    "note": "Private peer response",
                },
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["status"] == "pending_manager"
            return accepted.json()

        approved_swap = pending_cover(datetime(2030, 2, 4, 15, 0, tzinfo=UTC))
        approved = client.post(
            f"/api/v1/staff-exchange/swaps/{approved_swap['id']}/approve",
            headers=manager_a_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": approved_swap["updated_at"],
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        rejected_swap = pending_cover(datetime(2030, 2, 11, 15, 0, tzinfo=UTC))
        rejected = client.post(
            f"/api/v1/staff-exchange/swaps/{rejected_swap['id']}/reject",
            headers=manager_a_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_updated_at": rejected_swap["updated_at"],
                "reason": "Private manager rationale",
            },
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"

        expected_notifications = {
            (
                "Open shift offer sent",
                "A manager sent an offer for an open shift.",
                "staff_open_shift_engagement",
                offer["id"],
            ),
            (
                "Shift offer withdrawn",
                "A manager withdrew an open shift offer.",
                "staff_open_shift_engagement",
                offer["id"],
            ),
            (
                "Shift exchange approved",
                "A manager approved a whole-shift exchange.",
                "staff_shift_swap",
                approved_swap["id"],
            ),
            (
                "Shift exchange not approved",
                "A manager rejected a proposed whole-shift exchange.",
                "staff_shift_swap",
                rejected_swap["id"],
            ),
        }
        inbox = client.get(
            "/api/v1/notifications",
            headers=_headers(manager_b),
            params={"category": "assignment", "page_size": 100},
        )
        assert inbox.status_code == 200, inbox.text
        visible = {
            (
                item["title"],
                item["body"],
                item["action"]["entity_type"],
                item["action"]["entity_id"],
            )
            for item in inbox.json()["items"]
            if item["action"] is not None
        }
        assert expected_notifications.issubset(visible)
        serialized = " ".join(f"{title} {body}" for title, body, _, _ in visible).lower()
        for private_value in (
            educators[0]["user"]["first_name"],
            educators[0]["user"]["email"],
            "private note",
            "private withdrawal",
            "private educator",
            "private peer",
            "private manager",
        ):
            assert private_value.lower() not in serialized

        engagement_refresh = client.get(
            f"/api/v1/staff-exchange/open-shifts/{open_shift['id']}/engagements",
            headers=_headers(manager_b),
        )
        assert engagement_refresh.status_code == 200, engagement_refresh.text
        assert engagement_refresh.json()["items"][0]["status"] == "withdrawn"
        swap_refresh = client.get(
            "/api/v1/staff-exchange/swaps",
            headers=_headers(manager_b),
            params={
                "start_at": "2030-02-01T00:00:00Z",
                "end_at": "2030-03-01T00:00:00Z",
            },
        )
        assert swap_refresh.status_code == 200, swap_refresh.text
        assert {item["status"] for item in swap_refresh.json()["items"]} >= {
            "approved",
            "rejected",
        }

    admin_engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="postgres",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    with admin_engine.connect() as connection:
        realtime_event_ids = list(
            connection.execute(
                text(
                    "SELECT event.id FROM user_realtime_events AS event "
                    "JOIN user_notifications AS notification ON notification.id=event.id "
                    "WHERE event.user_id=:user_id AND event.event_type='notification.created' "
                    "AND notification.title IN ('Open shift offer sent','Shift offer withdrawn',"
                    "'Shift exchange approved','Shift exchange not approved') "
                    "ORDER BY event.sequence_id"
                ),
                {"user_id": UUID(manager_b["user"]["id"])},
            ).scalars()
        )
        assert len(realtime_event_ids) == 4
    admin_engine.dispose()

    runtime_engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="caresync_basic_app",
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )
    with runtime_engine.connect() as connection:
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": manager_a["user"]["id"]},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": owner["user"]["organization_id"]},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_realtime_events WHERE id=ANY(:ids)"),
                {"ids": realtime_event_ids},
            ).scalar_one()
            == 0
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": manager_b["user"]["id"]},
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM user_realtime_events WHERE id=ANY(:ids)"),
                {"ids": realtime_event_ids},
            ).scalar_one()
            == 4
        )
        connection.rollback()
    runtime_engine.dispose()


def test_replacement_open_shift_and_swap_share_one_source_reservation() -> None:
    settings = _settings()
    first_application = _application(settings)
    second_application = _application(settings)
    with (
        TestClient(first_application, raise_server_exceptions=False) as first_client,
        TestClient(second_application, raise_server_exceptions=False) as second_client,
    ):
        _, owner_headers, educators, facility, room = _scenario(first_client, "source-reserve")

        def source_at(start: datetime) -> dict:
            return _published_acknowledged_schedule(
                first_client,
                owner_headers,
                educators[0],
                facility,
                room,
                start,
            )

        def create_open(client: TestClient, source: dict):
            return client.post(
                "/api/v1/staff-exchange/open-shifts",
                headers=owner_headers,
                json={
                    "client_operation_id": str(uuid4()),
                    "facility_id": facility["id"],
                    "room_id": room["id"],
                    "source_schedule_id": source["id"],
                    "scheduled_start_at": source["scheduled_start_at"],
                    "scheduled_end_at": source["scheduled_end_at"],
                    "public_note": "Whole shift replacement",
                },
            )

        def create_swap(client: TestClient, source: dict):
            return client.post(
                "/api/v1/staff/self/exchange/swaps",
                headers=_headers(educators[0]),
                json={
                    "client_operation_id": str(uuid4()),
                    "kind": "cover",
                    "requester_schedule_id": source["id"],
                    "counterparty_membership_id": educators[1]["user"]["membership_id"],
                    "counterparty_schedule_id": None,
                    "note": "Whole shift cover",
                },
            )

        open_first_source = source_at(datetime(2029, 6, 4, 14, 0, tzinfo=UTC))
        open_first = create_open(first_client, open_first_source)
        assert open_first.status_code == 201, open_first.text
        blocked_swap = create_swap(first_client, open_first_source)
        assert blocked_swap.status_code == 409, blocked_swap.text
        assert blocked_swap.json()["detail"]["code"] == "schedule_exchange_pending"

        swap_first_source = source_at(datetime(2029, 6, 11, 14, 0, tzinfo=UTC))
        swap_first = create_swap(first_client, swap_first_source)
        assert swap_first.status_code == 201, swap_first.text
        blocked_open = create_open(first_client, swap_first_source)
        assert blocked_open.status_code == 409, blocked_open.text
        assert blocked_open.json()["detail"]["code"] == "schedule_exchange_pending"

        concurrent_source = source_at(datetime(2029, 6, 18, 14, 0, tzinfo=UTC))
        barrier = Barrier(3)
        concurrent_responses = {}
        concurrent_failures = []

        def concurrent_open() -> None:
            try:
                barrier.wait(timeout=5)
                concurrent_responses["open"] = create_open(first_client, concurrent_source)
            except Exception as error:  # pragma: no cover
                concurrent_failures.append(error)

        def concurrent_swap() -> None:
            try:
                barrier.wait(timeout=5)
                concurrent_responses["swap"] = create_swap(second_client, concurrent_source)
            except Exception as error:  # pragma: no cover
                concurrent_failures.append(error)

        threads = [
            Thread(target=concurrent_open, daemon=True),
            Thread(target=concurrent_swap, daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()
        assert not concurrent_failures
        assert sorted(response.status_code for response in concurrent_responses.values()) == [
            201,
            409,
        ]
        rejected = next(
            response for response in concurrent_responses.values() if response.status_code == 409
        )
        assert rejected.json()["detail"]["code"] == "schedule_exchange_pending"

        terminal_source = source_at(datetime(2029, 6, 25, 14, 0, tzinfo=UTC))
        terminal_open = create_open(first_client, terminal_source)
        assert terminal_open.status_code == 201, terminal_open.text
        barrier = Barrier(3)
        terminal_responses = {}
        terminal_failures = []

        def cancel_existing() -> None:
            try:
                barrier.wait(timeout=5)
                terminal_responses["cancel"] = first_client.post(
                    f"/api/v1/staff-exchange/open-shifts/{terminal_open.json()['id']}/cancel",
                    headers=owner_headers,
                    json={
                        "client_operation_id": str(uuid4()),
                        "expected_updated_at": terminal_open.json()["updated_at"],
                        "reason": "Terminal race proof",
                    },
                )
            except Exception as error:  # pragma: no cover
                terminal_failures.append(error)

        def create_after_terminal() -> None:
            try:
                barrier.wait(timeout=5)
                terminal_responses["swap"] = create_swap(second_client, terminal_source)
            except Exception as error:  # pragma: no cover
                terminal_failures.append(error)

        threads = [
            Thread(target=cancel_existing, daemon=True),
            Thread(target=create_after_terminal, daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()
        assert not terminal_failures
        assert terminal_responses["cancel"].status_code == 200, terminal_responses["cancel"].text
        assert terminal_responses["swap"].status_code in {201, 409}, terminal_responses["swap"].text
        if terminal_responses["swap"].status_code == 409:
            assert terminal_responses["swap"].json()["detail"]["code"] == (
                "schedule_exchange_pending"
            )

        open_shifts = first_client.get(
            "/api/v1/staff-exchange/open-shifts",
            headers=owner_headers,
            params={
                "start_at": "2029-06-01T00:00:00Z",
                "end_at": "2029-07-01T00:00:00Z",
            },
        )
        assert open_shifts.status_code == 200, open_shifts.text
        swaps = first_client.get(
            "/api/v1/staff-exchange/swaps",
            headers=owner_headers,
            params={
                "start_at": "2029-06-01T00:00:00Z",
                "end_at": "2029-07-01T00:00:00Z",
            },
        )
        assert swaps.status_code == 200, swaps.text
        active_open_by_source = {
            item["source_schedule_id"]
            for item in open_shifts.json()["items"]
            if item["status"] in {"draft", "open"} and item["source_schedule_id"] is not None
        }
        pending_swap_by_source = {
            item["requester_schedule_id"]
            for item in swaps.json()["items"]
            if item["status"] in {"pending_counterparty", "pending_manager"}
        }
        for source in (open_first_source, swap_first_source, concurrent_source):
            assert (
                int(source["id"] in active_open_by_source)
                + int(source["id"] in pending_swap_by_source)
                == 1
            )
        terminal_projection = next(
            item for item in open_shifts.json()["items"] if item["id"] == terminal_open.json()["id"]
        )
        assert terminal_projection["status"] == "cancelled"
        assert terminal_source["id"] not in active_open_by_source
        assert (terminal_source["id"] in pending_swap_by_source) is (
            terminal_responses["swap"].status_code == 201
        )
