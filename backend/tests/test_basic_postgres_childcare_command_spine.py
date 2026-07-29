"""Opt-in PostgreSQL proofs for the 0028 childcare command spine.

The suite requires an explicitly disposable, already migrated cluster with the
0028 runtime bootstrap applied. Live CareSync ports are rejected.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from threading import Event, Thread
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.basic.security import hash_password
from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
ALBERTA_TIMEZONE = ZoneInfo("America/Edmonton")
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _alberta_today() -> date:
    return datetime.now(ALBERTA_TIMEZONE).date()


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert port not in {5432, 5433, 5434}, "Local and live CareSync ports are forbidden"
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        port=port,
        database=os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1"),
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync"),
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-childcare-command-spine-secret-32-bytes",
    )


def _set_context(
    connection, user_id: UUID, organization_id: UUID, operation_id: UUID | None = None
):
    connection.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"),
        {"value": str(user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id', :value, true)"),
        {"value": str(organization_id)},
    )
    if operation_id is not None:
        connection.execute(
            text("SELECT set_config('app.current_childcare_operation_id', :value, true)"),
            {"value": str(operation_id)},
        )


def _register(client: TestClient) -> tuple[dict, dict[str, str]]:
    identifier = uuid4().hex
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"spine-pg-{identifier}@example.com",
            "password": "correct-password-123",
            "first_name": "Postgres",
            "last_name": "Owner",
            "organization_name": f"Postgres Spine {identifier}",
        },
    )
    assert response.status_code == 201, response.text
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def _post_success(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _second_actor(
    admin_engine, client: TestClient, organization_id: UUID
) -> tuple[UUID, dict[str, str]]:
    user_id = uuid4()
    email = f"spine-second-{uuid4().hex}@example.com"
    password = "correct-password-123"
    with admin_engine.begin() as connection:
        role_id = connection.execute(
            text(
                "SELECT id FROM roles WHERE organization_id=:organization_id "
                "AND key='administrator'"
            ),
            {"organization_id": organization_id},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,first_name,last_name,is_active,auth_version,"
                "email_verified_at,email_verification_method) "
                "VALUES (:id,:email,:password_hash,'Second','Actor',true,1,now(),'test_fixture')"
            ),
            {"id": user_id, "email": email, "password_hash": hash_password(password)},
        )
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id,organization_id,user_id,role_id,status) "
                "VALUES (:id,:organization_id,:user_id,:role_id,'active')"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "user_id": user_id,
                "role_id": role_id,
            },
        )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _insert_receipt(
    connection,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
    target_id: UUID,
) -> None:
    connection.execute(
        text(
            "INSERT INTO childcare_command_receipts "
            "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
            "request_hash,actor_user_id,committed_version,outcome) "
            "VALUES (:id,:organization_id,:operation_id,'family.update','family',"
            ":target_id,:request_hash,:actor_user_id,1,CAST(:outcome AS json))"
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "operation_id": operation_id,
            "target_id": target_id,
            "request_hash": uuid4().hex * 2,
            "actor_user_id": actor_user_id,
            "outcome": json.dumps({"action_route": f"/families/{target_id}"}),
        },
    )


def _insert_claim(
    connection,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
) -> None:
    connection.execute(
        text(
            "INSERT INTO childcare_command_claims "
            "(id,organization_id,client_operation_id,actor_user_id) "
            "VALUES (:id,:organization_id,:operation_id,:actor_user_id)"
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "operation_id": operation_id,
            "actor_user_id": actor_user_id,
        },
    )


def _insert_proof(
    connection,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    operation_id: UUID,
) -> None:
    connection.execute(
        text(
            "INSERT INTO childcare_command_reconciliation_proofs "
            "(id,organization_id,client_operation_id,actor_user_id) "
            "VALUES (:id,:organization_id,:operation_id,:actor_user_id)"
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "operation_id": operation_id,
            "actor_user_id": actor_user_id,
        },
    )


def test_runtime_receipts_temporal_guards_and_writer_reconciliation() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url("caresync_basic_app"))
    application = create_app(_settings())
    with TestClient(application) as client:
        # A brand-new tenant has no facilities; the typed empty facility-date
        # expression must still return a bounded empty child directory.
        auth, owner_headers = _register(client)
        assert client.get("/api/v1/children/directory", headers=owner_headers).status_code == 200
        owner_id = UUID(auth["user"]["id"])
        organization_id = UUID(auth["user"]["organization_id"])
        operation_id = uuid4()
        family_payload = {
            "client_operation_id": str(operation_id),
            "name": f"Temporal PG {uuid4().hex}",
            "primary_guardian": {
                "first_name": "Original",
                "last_name": "Guardian",
                "cell_phone": "780-555-0100",
            },
            "emergency_contacts": [
                {
                    "first_name": "Original",
                    "last_name": "Contact",
                    "relationship": "Aunt",
                    "cell_phone": "780-555-0101",
                }
            ],
        }
        family_response = client.post(
            "/api/v1/families", headers=owner_headers, json=family_payload
        )
        assert family_response.status_code == 201, family_response.text
        family = family_response.json()
        family_id = UUID(family["id"])

        second_id, second_headers = _second_actor(
            admin_engine,
            client,
            organization_id,
        )
        with admin_engine.connect() as connection:
            before = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM families WHERE organization_id=:organization_id "
                    "AND name=:name), "
                    "(SELECT count(*) FROM audit_events WHERE organization_id=:organization_id "
                    "AND entity_type='family' AND entity_id=:family_id)"
                ),
                {
                    "organization_id": organization_id,
                    "name": family_payload["name"],
                    "family_id": family_id,
                },
            ).one()
        private_reuse = client.post("/api/v1/families", headers=second_headers, json=family_payload)
        assert private_reuse.status_code == 404, private_reuse.text
        assert (
            client.get(
                f"/api/v1/childcare-commands/{operation_id}", headers=second_headers
            ).status_code
            == 404
        )
        with admin_engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM families WHERE organization_id=:organization_id "
                    "AND name=:name), "
                    "(SELECT count(*) FROM audit_events WHERE organization_id=:organization_id "
                    "AND entity_type='family' AND entity_id=:family_id)"
                ),
                {
                    "organization_id": organization_id,
                    "name": family_payload["name"],
                    "family_id": family_id,
                },
            ).one()
        assert after == before

        with runtime_engine.begin() as connection:
            _set_context(connection, second_id, organization_id)
            assert (
                connection.execute(
                    text("SELECT count(*) FROM childcare_command_receipts")
                ).scalar_one()
                == 0
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, second_id, organization_id)
            connection.execute(
                text(
                    "INSERT INTO childcare_command_receipts "
                    "(id,organization_id,client_operation_id,command_type,target_type,"
                    "target_id,request_hash,actor_user_id,committed_version,outcome) "
                    "VALUES (:id,:organization_id,:operation_id,'family.create','family',"
                    ":family_id,:request_hash,:owner_id,1,'{}'::json)"
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "operation_id": uuid4(),
                    "family_id": family_id,
                    "request_hash": "a" * 64,
                    "owner_id": owner_id,
                },
            )

        with admin_engine.connect() as connection:
            original_guardian_id = connection.execute(
                text(
                    "SELECT id FROM guardians WHERE organization_id=:organization_id "
                    "AND family_id=:family_id AND retired_at IS NULL AND is_primary"
                ),
                {"organization_id": organization_id, "family_id": family_id},
            ).scalar_one()
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id)
            connection.execute(
                text("UPDATE guardians SET first_name='Forged' WHERE id=:id"),
                {"id": original_guardian_id},
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id)
            connection.execute(
                text(
                    "INSERT INTO emergency_contacts "
                    "(id,organization_id,family_id,first_name,last_name,relationship,"
                    "cell_phone,authorized_pickup) "
                    "VALUES (:id,:organization_id,:family_id,'Forged','Contact','Aunt',"
                    "'780-555-0111',false)"
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "family_id": family_id,
                },
            )

        replace_operation = uuid4()
        replace = client.put(
            f"/api/v1/families/{family_id}/guardians/primary",
            headers=owner_headers,
            json={
                "client_operation_id": str(replace_operation),
                "expected_version": family["version"],
                "guardian": {
                    "first_name": "Replacement",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0102",
                },
            },
        )
        assert replace.status_code == 200, replace.text
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, replace_operation)
            connection.execute(
                text(
                    "UPDATE guardians SET retired_at=now(), "
                    "retired_operation_id=:operation_id WHERE id=:id"
                ),
                {"operation_id": replace_operation, "id": original_guardian_id},
            )

        contact_operation = uuid4()
        contacts = client.put(
            f"/api/v1/families/{family_id}/emergency-contacts",
            headers=owner_headers,
            json={
                "client_operation_id": str(contact_operation),
                "expected_version": replace.json()["version"],
                "emergency_contacts": [
                    {
                        "first_name": "Replacement",
                        "last_name": "Contact",
                        "relationship": "Uncle",
                        "cell_phone": "780-555-0103",
                    }
                ],
            },
        )
        assert contacts.status_code == 200, contacts.text
        with admin_engine.connect() as connection:
            current_contact_id = connection.execute(
                text(
                    "SELECT id FROM emergency_contacts "
                    "WHERE organization_id=:organization_id AND family_id=:family_id "
                    "AND retired_at IS NULL"
                ),
                {"organization_id": organization_id, "family_id": family_id},
            ).scalar_one()
        forged_timestamp_contact = uuid4()
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, contact_operation)
            connection.execute(
                text(
                    "INSERT INTO emergency_contacts "
                    "(id,organization_id,family_id,first_name,last_name,relationship,cell_phone,"
                    "authorized_pickup,created_operation_id,created_at,updated_at) "
                    "VALUES (:id,:organization_id,:family_id,'Timestamp','Contact','Aunt',"
                    "'780-555-0104',false,:operation_id,'2100-01-01','2100-01-01')"
                ),
                {
                    "id": forged_timestamp_contact,
                    "organization_id": organization_id,
                    "family_id": family_id,
                    "operation_id": contact_operation,
                },
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, contact_operation)
            connection.execute(
                text(
                    "UPDATE emergency_contacts SET retired_at=now(), "
                    "retired_operation_id=:operation_id WHERE id=:id"
                ),
                {"operation_id": contact_operation, "id": current_contact_id},
            )

        # The runtime role can create temporary relations by default. The
        # trigger must bind its receipt authority to public, not a pg_temp
        # relation that an application session controls.
        with admin_engine.connect() as connection:
            trigger_settings = connection.execute(
                text(
                    "SELECT proconfig FROM pg_proc "
                    "WHERE oid='caresync_childcare_contact_retirement_guard()'::regprocedure"
                )
            ).scalar_one()
            assert trigger_settings == ["search_path=pg_catalog, public"]
        with admin_engine.begin() as connection:
            connection.execute(text("GRANT TEMPORARY ON DATABASE caresync TO caresync_basic_app"))
        try:
            with runtime_engine.connect() as connection:
                with connection.begin():
                    connection.execute(
                        text(
                            "CREATE TEMP TABLE childcare_command_receipts ("
                            "organization_id uuid, client_operation_id uuid, actor_user_id uuid, "
                            "committed_at timestamptz, target_type text, target_id uuid, "
                            "command_type text) ON COMMIT PRESERVE ROWS"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO pg_temp.childcare_command_receipts "
                            "(organization_id,client_operation_id,actor_user_id,committed_at,"
                            "target_type,target_id,command_type) VALUES "
                            "(:organization_id,:operation_id,:owner_id,transaction_timestamp(),"
                            "'family',:family_id,'family.emergency_contacts.replace')"
                        ),
                        {
                            "organization_id": organization_id,
                            "operation_id": contact_operation,
                            "owner_id": owner_id,
                            "family_id": family_id,
                        },
                    )
                    assert (
                        connection.execute(
                            text("SELECT count(*) FROM pg_temp.childcare_command_receipts")
                        ).scalar_one()
                        == 1
                    )
                with pytest.raises(DBAPIError), connection.begin():
                    _set_context(connection, owner_id, organization_id, contact_operation)
                    connection.execute(
                        text(
                            "INSERT INTO public.emergency_contacts "
                            "(id,organization_id,family_id,first_name,last_name,relationship,"
                            "cell_phone,authorized_pickup,created_operation_id) "
                            "VALUES (:id,:organization_id,:family_id,'Temp','Shadow','Aunt',"
                            "'780-555-0199',false,:operation_id)"
                        ),
                        {
                            "id": uuid4(),
                            "organization_id": organization_id,
                            "family_id": family_id,
                            "operation_id": contact_operation,
                        },
                    )
                with connection.begin():
                    connection.execute(text("DROP TABLE pg_temp.childcare_command_receipts"))
        finally:
            with admin_engine.begin() as connection:
                connection.execute(
                    text("REVOKE TEMPORARY ON DATABASE caresync FROM caresync_basic_app")
                )

        timestamp_operation = uuid4()
        with runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, timestamp_operation)
            connection.execute(
                text(
                    "INSERT INTO childcare_command_receipts "
                    "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                    "request_hash,actor_user_id,committed_version,outcome,committed_at) "
                    "VALUES (:receipt_id,:organization_id,:operation_id,"
                    "'family.emergency_contacts.replace','family',:family_id,:request_hash,"
                    ":owner_id,99,'{}'::json,'2100-01-01')"
                ),
                {
                    "receipt_id": uuid4(),
                    "organization_id": organization_id,
                    "operation_id": timestamp_operation,
                    "family_id": family_id,
                    "request_hash": "c" * 64,
                    "owner_id": owner_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO emergency_contacts "
                    "(id,organization_id,family_id,first_name,last_name,relationship,cell_phone,"
                    "authorized_pickup,created_operation_id,created_at,updated_at) "
                    "VALUES (:id,:organization_id,:family_id,'Timestamp','Contact','Aunt',"
                    "'780-555-0104',false,:operation_id,'2100-01-01','2100-01-01')"
                ),
                {
                    "id": forged_timestamp_contact,
                    "organization_id": organization_id,
                    "family_id": family_id,
                    "operation_id": timestamp_operation,
                },
            )
            assert connection.execute(
                text(
                    "SELECT xmin = pg_current_xact_id()::text::xid "
                    "FROM public.childcare_command_receipts "
                    "WHERE organization_id=:organization_id "
                    "AND client_operation_id=:operation_id"
                ),
                {
                    "organization_id": organization_id,
                    "operation_id": timestamp_operation,
                },
            ).scalar_one()
            created_at = connection.execute(
                text("SELECT created_at FROM emergency_contacts WHERE id=:id"),
                {"id": forged_timestamp_contact},
            ).scalar_one()
            assert created_at < datetime(2100, 1, 1, tzinfo=UTC)
            connection.execute(
                text(
                    "UPDATE emergency_contacts SET retired_at='2100-01-01', "
                    "retired_operation_id=:operation_id WHERE id=:id"
                ),
                {"operation_id": timestamp_operation, "id": forged_timestamp_contact},
            )
            retired_at = connection.execute(
                text("SELECT retired_at FROM emergency_contacts WHERE id=:id"),
                {"id": forged_timestamp_contact},
            ).scalar_one()
            assert retired_at < datetime(2100, 1, 1, tzinfo=UTC)

        # Reconciliation takes the same advisory transaction lock as writers.
        journal_operation = uuid4()
        writer_ready = Event()
        release_writer = Event()
        reader_done = Event()
        response_box: list[object] = []

        def writer() -> None:
            with runtime_engine.begin() as connection:
                _set_context(connection, owner_id, organization_id, journal_operation)
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
                    {"value": f"{organization_id}:{journal_operation}"},
                )
                connection.execute(
                    text(
                        "INSERT INTO childcare_command_receipts "
                        "(id,organization_id,client_operation_id,command_type,target_type,"
                        "target_id,request_hash,actor_user_id,committed_version,outcome) "
                        "VALUES (:id,:organization_id,:operation_id,'family.update','family',"
                        ":family_id,:request_hash,:owner_id,99,CAST(:outcome AS json))"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": organization_id,
                        "operation_id": journal_operation,
                        "family_id": family_id,
                        "request_hash": "b" * 64,
                        "owner_id": owner_id,
                        "outcome": json.dumps({"action_route": f"/families/{family_id}"}),
                    },
                )
                writer_ready.set()
                assert release_writer.wait(timeout=5)

        def reader() -> None:
            assert writer_ready.wait(timeout=5)
            response_box.append(
                client.get(
                    f"/api/v1/childcare-commands/{journal_operation}",
                    headers=owner_headers,
                )
            )
            reader_done.set()

        writer_thread = Thread(target=writer, daemon=True)
        reader_thread = Thread(target=reader, daemon=True)
        writer_thread.start()
        reader_thread.start()
        assert writer_ready.wait(timeout=5)
        assert not reader_done.wait(timeout=0.25)
        release_writer.set()
        writer_thread.join(timeout=8)
        reader_thread.join(timeout=8)
        assert not writer_thread.is_alive() and not reader_thread.is_alive()
        assert response_box[0].status_code == 200
        assert response_box[0].json()["client_operation_id"] == str(journal_operation)

    runtime_engine.dispose()
    admin_engine.dispose()


def test_postgres_daily_reconciliation_limit_rolls_back_losing_charge() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url("caresync_basic_app"), pool_size=10, max_overflow=10)
    application = create_app(_settings())
    with TestClient(application) as client:
        auth, owner_headers = _register(client)
        owner_id = UUID(auth["user"]["id"])
        organization_id = UUID(auth["user"]["organization_id"])
        family = _post_success(
            client,
            "/api/v1/families",
            owner_headers,
            {"client_operation_id": str(uuid4()), "name": "Daily Budget Boundary"},
        )
        family_id = UUID(family["id"])
        actor_id, actor_headers = _second_actor(admin_engine, client, organization_id)
        operations = (uuid4(), uuid4())
        for operation_id in operations:
            with runtime_engine.begin() as connection:
                _set_context(connection, owner_id, organization_id, operation_id)
                _insert_receipt(
                    connection,
                    organization_id=organization_id,
                    actor_user_id=owner_id,
                    operation_id=operation_id,
                    target_id=family_id,
                )

        with admin_engine.begin() as connection:
            hour_start, day_start = connection.execute(
                text(
                    "SELECT "
                    "date_trunc('hour', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', "
                    "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
                )
            ).one()
            connection.execute(
                text(
                    "INSERT INTO public.childcare_command_reconciliation_budgets "
                    "(organization_id,actor_user_id,window_kind,window_started_at,"
                    "operation_count) VALUES "
                    "(:organization_id,:actor_user_id,'day',:day_start,499)"
                ),
                {
                    "organization_id": organization_id,
                    "actor_user_id": actor_id,
                    "day_start": day_start,
                },
            )

        ready = (Event(), Event())
        begin_race = Event()
        outcomes: dict[UUID, str] = {}

        def reconcile(operation_id: UUID, ready_event: Event) -> None:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(connection, actor_id, organization_id, operation_id)
                    ready_event.set()
                    assert begin_race.wait(timeout=8)
                    _insert_proof(
                        connection,
                        organization_id=organization_id,
                        actor_user_id=actor_id,
                        operation_id=operation_id,
                    )
                outcomes[operation_id] = "committed"
            except DBAPIError:
                outcomes[operation_id] = "rate_limited"

        threads = [
            Thread(target=reconcile, args=(operation, signal), daemon=True)
            for operation, signal in zip(operations, ready, strict=True)
        ]
        for thread in threads:
            thread.start()
        assert all(signal.wait(timeout=8) for signal in ready)
        begin_race.set()
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        assert list(outcomes.values()).count("committed") == 1
        assert list(outcomes.values()).count("rate_limited") == 1
        rejected_operation = next(
            operation for operation, outcome in outcomes.items() if outcome == "rate_limited"
        )

        def budget_snapshot() -> tuple[int, int, int, int]:
            with admin_engine.connect() as connection:
                return connection.execute(
                    text(
                        "SELECT "
                        "coalesce((SELECT operation_count FROM "
                        " public.childcare_command_reconciliation_budgets "
                        " WHERE organization_id=:organization_id "
                        " AND actor_user_id=:actor_user_id AND window_kind='hour' "
                        " AND window_started_at=:hour_start),0), "
                        "(SELECT operation_count FROM "
                        " public.childcare_command_reconciliation_budgets "
                        " WHERE organization_id=:organization_id "
                        " AND actor_user_id=:actor_user_id AND window_kind='day' "
                        " AND window_started_at=:day_start), "
                        "(SELECT count(*) FROM "
                        " public.childcare_command_reconciliation_budget_entries "
                        " WHERE organization_id=:organization_id "
                        " AND actor_user_id=:actor_user_id), "
                        "(SELECT count(*) FROM "
                        " public.childcare_command_reconciliation_proofs "
                        " WHERE organization_id=:organization_id "
                        " AND actor_user_id=:actor_user_id)"
                    ),
                    {
                        "organization_id": organization_id,
                        "actor_user_id": actor_id,
                        "hour_start": hour_start,
                        "day_start": day_start,
                    },
                ).one()

        assert budget_snapshot() == (1, 500, 1, 1)
        for _ in range(2):
            limited = client.get(
                f"/api/v1/childcare-commands/{rejected_operation}",
                headers=actor_headers,
            )
            assert limited.status_code == 429
            assert limited.json() == {"detail": {"code": "operation_reconciliation_rate_limited"}}
            assert budget_snapshot() == (1, 500, 1, 1)

    runtime_engine.dispose()
    admin_engine.dispose()


def test_postgres_runtime_grant_drift_cannot_mutate_childcare_history() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url("caresync_basic_app"))
    operation_id = uuid4()
    application = create_app(_settings())
    with TestClient(application) as client:
        auth, headers = _register(client)
        family_response = client.post(
            "/api/v1/families",
            headers=headers,
            json={
                "client_operation_id": str(operation_id),
                "name": "Immutable PostgreSQL History",
                "primary_guardian": {
                    "first_name": "History",
                    "last_name": "Guardian",
                    "cell_phone": "780-555-0188",
                },
            },
        )
        assert family_response.status_code == 201, family_response.text
        family_id = UUID(family_response.json()["id"])
        owner_id = UUID(auth["user"]["id"])
        organization_id = UUID(auth["user"]["organization_id"])

    with admin_engine.begin() as connection:
        connection.execute(
            text(
                "GRANT UPDATE, DELETE ON TABLE public.childcare_command_receipts "
                "TO caresync_basic_app"
            )
        )
        connection.execute(text("GRANT DELETE ON TABLE public.guardians TO caresync_basic_app"))
    try:
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, operation_id)
            connection.execute(
                text(
                    "UPDATE public.childcare_command_receipts "
                    "SET outcome=json_build_object('tampered', true) "
                    "WHERE organization_id=:organization_id "
                    "AND client_operation_id=:operation_id"
                ),
                {
                    "organization_id": organization_id,
                    "operation_id": operation_id,
                },
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, operation_id)
            connection.execute(
                text(
                    "DELETE FROM public.childcare_command_receipts "
                    "WHERE organization_id=:organization_id "
                    "AND client_operation_id=:operation_id"
                ),
                {
                    "organization_id": organization_id,
                    "operation_id": operation_id,
                },
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, operation_id)
            connection.execute(
                text(
                    "DELETE FROM public.guardians WHERE organization_id=:organization_id "
                    "AND family_id=:family_id"
                ),
                {
                    "organization_id": organization_id,
                    "family_id": family_id,
                },
            )
        with (
            pytest.raises(RuntimeError, match="forbidden effective database privileges"),
            TestClient(create_app(_settings())),
        ):
            pass
        with admin_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.childcare_command_receipts "
                        "WHERE organization_id=:organization_id "
                        "AND client_operation_id=:operation_id"
                    ),
                    {
                        "organization_id": organization_id,
                        "operation_id": operation_id,
                    },
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.guardians "
                        "WHERE organization_id=:organization_id AND family_id=:family_id"
                    ),
                    {
                        "organization_id": organization_id,
                        "family_id": family_id,
                    },
                ).scalar_one()
                == 1
            )
    finally:
        with admin_engine.begin() as connection:
            connection.execute(
                text(
                    "REVOKE UPDATE, DELETE ON TABLE public.childcare_command_receipts "
                    "FROM caresync_basic_app"
                )
            )
            connection.execute(
                text("REVOKE DELETE ON TABLE public.guardians FROM caresync_basic_app")
            )
        runtime_engine.dispose()
        admin_engine.dispose()

    with TestClient(create_app(_settings())) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_postgres_reconciliation_get_and_post_orderings(monkeypatch) -> None:
    from app.api.basic import childcare_command_receipts as receipt_api
    from app.basic import childcare_commands

    application = create_app(_settings())
    with TestClient(application) as client:
        _, headers = _register(client)

        get_first_operation = uuid4()
        reader_locked = Event()
        release_reader = Event()
        post_done = Event()
        get_first_responses: dict[str, object] = {}
        original_reader_lock = receipt_api.lock_client_operation

        def delayed_reader_lock(session, organization_id, client_operation_id):
            original_reader_lock(session, organization_id, client_operation_id)
            if client_operation_id == get_first_operation:
                reader_locked.set()
                assert release_reader.wait(timeout=8)

        monkeypatch.setattr(
            receipt_api,
            "lock_client_operation",
            delayed_reader_lock,
        )

        def reconcile_first() -> None:
            get_first_responses["get"] = client.get(
                f"/api/v1/childcare-commands/{get_first_operation}",
                headers=headers,
            )

        def post_after_reader() -> None:
            assert reader_locked.wait(timeout=8)
            get_first_responses["post"] = client.post(
                "/api/v1/families",
                headers=headers,
                json={
                    "client_operation_id": str(get_first_operation),
                    "name": "Postgres GET Must Win",
                },
            )
            post_done.set()

        reader_thread = Thread(target=reconcile_first, daemon=True)
        post_thread = Thread(target=post_after_reader, daemon=True)
        reader_thread.start()
        post_thread.start()
        assert reader_locked.wait(timeout=8)
        assert not post_done.wait(timeout=0.25)
        release_reader.set()
        reader_thread.join(timeout=10)
        post_thread.join(timeout=10)
        assert not reader_thread.is_alive() and not post_thread.is_alive()
        assert get_first_responses["get"].status_code == 404
        assert get_first_responses["get"].json()["detail"]["code"] == "operation_finalized_absent"
        assert get_first_responses["post"].status_code == 409
        assert get_first_responses["post"].json()["detail"]["code"] == "operation_finalized_absent"

        monkeypatch.setattr(
            receipt_api,
            "lock_client_operation",
            original_reader_lock,
        )
        post_first_operation = uuid4()
        writer_locked = Event()
        release_writer = Event()
        reader_done = Event()
        post_first_responses: dict[str, object] = {}
        original_writer_lock = childcare_commands.lock_client_operation

        def delayed_writer_lock(session, organization_id, client_operation_id):
            original_writer_lock(session, organization_id, client_operation_id)
            if client_operation_id == post_first_operation:
                writer_locked.set()
                assert release_writer.wait(timeout=8)

        monkeypatch.setattr(
            childcare_commands,
            "lock_client_operation",
            delayed_writer_lock,
        )

        def post_first() -> None:
            post_first_responses["post"] = client.post(
                "/api/v1/families",
                headers=headers,
                json={
                    "client_operation_id": str(post_first_operation),
                    "name": "Postgres POST Must Win",
                },
            )

        def reconcile_after_writer() -> None:
            assert writer_locked.wait(timeout=8)
            post_first_responses["get"] = client.get(
                f"/api/v1/childcare-commands/{post_first_operation}",
                headers=headers,
            )
            reader_done.set()

        post_thread = Thread(target=post_first, daemon=True)
        reader_thread = Thread(target=reconcile_after_writer, daemon=True)
        post_thread.start()
        reader_thread.start()
        assert writer_locked.wait(timeout=8)
        assert not reader_done.wait(timeout=0.25)
        release_writer.set()
        post_thread.join(timeout=10)
        reader_thread.join(timeout=10)
        assert not post_thread.is_alive() and not reader_thread.is_alive()
        assert post_first_responses["post"].status_code == 201
        assert post_first_responses["get"].status_code == 200
        assert post_first_responses["get"].json()["client_operation_id"] == str(
            post_first_operation
        )


def test_postgres_batch_placement_flushes_each_receipt_under_its_operation_context() -> None:
    application = create_app(_settings())
    with TestClient(application) as client:
        auth, headers = _register(client)
        family = _post_success(
            client,
            "/api/v1/families",
            headers,
            {
                "client_operation_id": str(uuid4()),
                "name": f"Batch Placement {uuid4().hex}",
            },
        )
        facility = _post_success(
            client,
            "/api/v1/facilities",
            headers,
            {
                "name": f"Batch Facility {uuid4().hex}",
                "status": "active",
                "licensed_capacity": 100,
            },
        )
        program = _post_success(
            client,
            "/api/v1/programs",
            headers,
            {
                "facility_id": facility["id"],
                "name": "Daycare",
                "program_type": "daycare",
                "capacity": 100,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        room = _post_success(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": "Batch Room",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        start_date = _alberta_today() + timedelta(days=5)
        enrollments: list[dict] = []
        for index in range(2):
            child = _post_success(
                client,
                "/api/v1/children",
                headers,
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": family["id"],
                    "first_name": f"Batch {index}",
                    "last_name": "Child",
                    "date_of_birth": "2024-01-01",
                },
            )
            enrollments.append(
                _post_success(
                    client,
                    f"/api/v1/children/{child['id']}/enrollments",
                    headers,
                    {
                        "client_operation_id": str(uuid4()),
                        "facility_id": facility["id"],
                        "start_date": start_date.isoformat(),
                    },
                )
            )

        placement_operations = [uuid4(), uuid4()]
        payload = {
            "placements": [
                {
                    "enrollment_id": enrollment["id"],
                    "client_operation_id": str(operation_id),
                    "expected_version": 1,
                    "room_id": room["id"],
                    "effective_date": start_date.isoformat(),
                }
                for enrollment, operation_id in zip(
                    reversed(enrollments), placement_operations, strict=True
                )
            ]
        }
        approved = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json=payload,
        )
        assert approved.status_code == 200, approved.text
        assert [row["replayed"] for row in approved.json()["approvals"]] == [False, False]

        replayed = client.post(
            "/api/v1/room-placement-approvals/batch",
            headers=headers,
            json=payload,
        )
        assert replayed.status_code == 200, replayed.text
        assert [row["replayed"] for row in replayed.json()["approvals"]] == [True, True]

        organization_id = UUID(auth["user"]["organization_id"])
        admin_engine = create_engine(_url("postgres"))
        try:
            with admin_engine.connect() as connection:
                receipts = connection.execute(
                    text(
                        "SELECT client_operation_id, actor_user_id "
                        "FROM childcare_command_receipts "
                        "WHERE organization_id=:organization_id "
                        "AND client_operation_id IN (:first_operation,:second_operation)"
                    ),
                    {
                        "organization_id": organization_id,
                        "first_operation": placement_operations[0],
                        "second_operation": placement_operations[1],
                    },
                ).all()
            assert {row.client_operation_id for row in receipts} == set(placement_operations)
            assert {row.actor_user_id for row in receipts} == {UUID(auth["user"]["id"])}
        finally:
            admin_engine.dispose()


def test_postgres_terminal_ledgers_proofs_context_and_atomic_budget() -> None:
    admin_engine = create_engine(_url("postgres"))
    runtime_engine = create_engine(_url("caresync_basic_app"), pool_size=20, max_overflow=20)
    application = create_app(_settings())
    with TestClient(application) as client:
        auth, owner_headers = _register(client)
        organization_id = UUID(auth["user"]["organization_id"])
        owner_id = UUID(auth["user"]["id"])
        family_operation = uuid4()
        family_response = client.post(
            "/api/v1/families",
            headers=owner_headers,
            json={
                "client_operation_id": str(family_operation),
                "name": f"Ledger Guard {uuid4().hex}",
            },
        )
        assert family_response.status_code == 201, family_response.text
        family_id = UUID(family_response.json()["id"])
        second_id, second_headers = _second_actor(admin_engine, client, organization_id)

        claim_first_operation = uuid4()
        with runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, claim_first_operation)
            _insert_claim(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=claim_first_operation,
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, claim_first_operation)
            _insert_receipt(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=claim_first_operation,
                target_id=family_id,
            )

        receipt_first_operation = uuid4()
        with runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, receipt_first_operation)
            _insert_receipt(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=receipt_first_operation,
                target_id=family_id,
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, receipt_first_operation)
            _insert_claim(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=receipt_first_operation,
            )

        context_operation = uuid4()
        forged_operation = uuid4()
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, context_operation)
            _insert_receipt(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=forged_operation,
                target_id=family_id,
            )

        no_authority_operation = uuid4()
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, no_authority_operation)
            _insert_proof(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=no_authority_operation,
            )
        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, receipt_first_operation)
            _insert_proof(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=receipt_first_operation,
            )

        with runtime_engine.begin() as connection:
            _set_context(connection, second_id, organization_id, receipt_first_operation)
            _insert_proof(
                connection,
                organization_id=organization_id,
                actor_user_id=second_id,
                operation_id=receipt_first_operation,
            )
        actor_relative = client.get(
            f"/api/v1/childcare-commands/{receipt_first_operation}",
            headers=second_headers,
        )
        assert actor_relative.status_code == 404
        assert actor_relative.json()["detail"]["actor_user_id"] == str(second_id)

        claim_and_proof_operation = uuid4()
        with runtime_engine.begin() as connection:
            _set_context(connection, owner_id, organization_id, claim_and_proof_operation)
            _insert_claim(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=claim_and_proof_operation,
            )
            _insert_proof(
                connection,
                organization_id=organization_id,
                actor_user_id=owner_id,
                operation_id=claim_and_proof_operation,
            )
        with admin_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM childcare_command_reconciliation_budget_entries "
                        "WHERE organization_id=:organization_id "
                        "AND actor_user_id=:actor_user_id "
                        "AND client_operation_id=:operation_id"
                    ),
                    {
                        "organization_id": organization_id,
                        "actor_user_id": owner_id,
                        "operation_id": claim_and_proof_operation,
                    },
                ).scalar_one()
                == 1
            )

        with pytest.raises(DBAPIError), runtime_engine.begin() as connection:
            _set_context(connection, second_id, organization_id, receipt_first_operation)
            connection.execute(
                text(
                    "UPDATE childcare_command_reconciliation_proofs "
                    "SET finalized_at=now() WHERE organization_id=:organization_id "
                    "AND actor_user_id=:actor_user_id "
                    "AND client_operation_id=:operation_id"
                ),
                {
                    "organization_id": organization_id,
                    "actor_user_id": second_id,
                    "operation_id": receipt_first_operation,
                },
            )

        concurrent_operation = uuid4()
        claim_ready = Event()
        receipt_ready = Event()
        start = Event()
        concurrent_results: list[str] = []

        def race_claim() -> None:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(connection, owner_id, organization_id, concurrent_operation)
                    claim_ready.set()
                    assert start.wait(timeout=8)
                    _insert_claim(
                        connection,
                        organization_id=organization_id,
                        actor_user_id=owner_id,
                        operation_id=concurrent_operation,
                    )
                concurrent_results.append("claim")
            except DBAPIError:
                concurrent_results.append("claim_rejected")

        def race_receipt() -> None:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(connection, owner_id, organization_id, concurrent_operation)
                    receipt_ready.set()
                    assert start.wait(timeout=8)
                    _insert_receipt(
                        connection,
                        organization_id=organization_id,
                        actor_user_id=owner_id,
                        operation_id=concurrent_operation,
                        target_id=family_id,
                    )
                concurrent_results.append("receipt")
            except DBAPIError:
                concurrent_results.append("receipt_rejected")

        claim_thread = Thread(target=race_claim, daemon=True)
        receipt_thread = Thread(target=race_receipt, daemon=True)
        claim_thread.start()
        receipt_thread.start()
        assert claim_ready.wait(timeout=8) and receipt_ready.wait(timeout=8)
        start.set()
        claim_thread.join(timeout=10)
        receipt_thread.join(timeout=10)
        assert not claim_thread.is_alive() and not receipt_thread.is_alive()
        assert len([value for value in concurrent_results if "rejected" not in value]) == 1
        assert len([value for value in concurrent_results if "rejected" in value]) == 1
        with admin_engine.connect() as connection:
            ledger_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM childcare_command_receipts "
                    " WHERE organization_id=:organization_id "
                    " AND client_operation_id=:operation_id), "
                    "(SELECT count(*) FROM childcare_command_claims "
                    " WHERE organization_id=:organization_id "
                    " AND client_operation_id=:operation_id), "
                    "(SELECT count(*) FROM childcare_command_slots "
                    " WHERE organization_id=:organization_id "
                    " AND client_operation_id=:operation_id)"
                ),
                {
                    "organization_id": organization_id,
                    "operation_id": concurrent_operation,
                },
            ).one()
        assert ledger_counts[0] + ledger_counts[1] == 1
        assert ledger_counts[2] == 1

        budget_actor_id, budget_actor_headers = _second_actor(
            admin_engine,
            client,
            organization_id,
        )
        budget_operations = (uuid4(), uuid4())
        for operation_id in budget_operations:
            with runtime_engine.begin() as connection:
                _set_context(connection, owner_id, organization_id, operation_id)
                _insert_receipt(
                    connection,
                    organization_id=organization_id,
                    actor_user_id=owner_id,
                    operation_id=operation_id,
                    target_id=family_id,
                )
        with admin_engine.begin() as connection:
            hour_start, day_start = connection.execute(
                text(
                    "SELECT "
                    "date_trunc('hour', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', "
                    "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
                )
            ).one()
            for kind, started_at in (("hour", hour_start), ("day", day_start)):
                connection.execute(
                    text(
                        "INSERT INTO childcare_command_reconciliation_budgets "
                        "(organization_id,actor_user_id,window_kind,window_started_at,"
                        "operation_count) VALUES "
                        "(:organization_id,:actor_user_id,:kind,:started_at,119)"
                    ),
                    {
                        "organization_id": organization_id,
                        "actor_user_id": budget_actor_id,
                        "kind": kind,
                        "started_at": started_at,
                    },
                )

        first_ready = Event()
        second_ready = Event()
        start_budget_race = Event()
        budget_results: dict[UUID, str] = {}

        def insert_budgeted_proof(operation_id: UUID, ready: Event) -> None:
            try:
                with runtime_engine.begin() as connection:
                    _set_context(connection, budget_actor_id, organization_id, operation_id)
                    ready.set()
                    assert start_budget_race.wait(timeout=8)
                    _insert_proof(
                        connection,
                        organization_id=organization_id,
                        actor_user_id=budget_actor_id,
                        operation_id=operation_id,
                    )
                budget_results[operation_id] = "committed"
            except DBAPIError:
                budget_results[operation_id] = "rate_limited"

        first_thread = Thread(
            target=insert_budgeted_proof,
            args=(budget_operations[0], first_ready),
            daemon=True,
        )
        second_thread = Thread(
            target=insert_budgeted_proof,
            args=(budget_operations[1], second_ready),
            daemon=True,
        )
        first_thread.start()
        second_thread.start()
        assert first_ready.wait(timeout=8) and second_ready.wait(timeout=8)
        start_budget_race.set()
        first_thread.join(timeout=10)
        second_thread.join(timeout=10)
        assert list(budget_results.values()).count("committed") == 1
        assert list(budget_results.values()).count("rate_limited") == 1
        committed_operation = next(
            operation for operation, result in budget_results.items() if result == "committed"
        )
        rejected_operation = next(
            operation for operation, result in budget_results.items() if result == "rate_limited"
        )
        repeated = client.get(
            f"/api/v1/childcare-commands/{committed_operation}",
            headers=budget_actor_headers,
        )
        assert repeated.status_code == 404
        assert repeated.json()["detail"]["code"] == "operation_finalized_absent"
        limited = client.get(
            f"/api/v1/childcare-commands/{rejected_operation}",
            headers=budget_actor_headers,
        )
        assert limited.status_code == 429
        assert limited.json() == {"detail": {"code": "operation_reconciliation_rate_limited"}}
        with admin_engine.connect() as connection:
            hour_count = connection.execute(
                text(
                    "SELECT operation_count FROM childcare_command_reconciliation_budgets "
                    "WHERE organization_id=:organization_id "
                    "AND actor_user_id=:actor_user_id AND window_kind='hour' "
                    "AND window_started_at=:window_started_at"
                ),
                {
                    "organization_id": organization_id,
                    "actor_user_id": budget_actor_id,
                    "window_started_at": hour_start,
                },
            ).scalar_one()
            proof_count = connection.execute(
                text(
                    "SELECT count(*) FROM childcare_command_reconciliation_proofs "
                    "WHERE organization_id=:organization_id "
                    "AND actor_user_id=:actor_user_id"
                ),
                {
                    "organization_id": organization_id,
                    "actor_user_id": budget_actor_id,
                },
            ).scalar_one()
        assert hour_count == 120
        assert proof_count == 1

    runtime_engine.dispose()
    admin_engine.dispose()
