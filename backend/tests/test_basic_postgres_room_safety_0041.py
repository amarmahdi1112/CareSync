"""Opt-in PostgreSQL 17 proof for the 0041 live room-safety boundary.

This gate owns one database on an explicitly supplied, dedicated loopback
cluster.  It never connects to a retained CareSync port and it refuses to use
an existing database or any pre-existing CareSync proof roles.

Example::

    BASIC_POSTGRES_ROOM_SAFETY_0041_TEST_URL=\
postgresql+psycopg://postgres@127.0.0.1:56555/postgres \
      ./scripts/uv.sh run pytest -q \
      tests/test_basic_postgres_room_safety_0041.py

The URL is deliberately opt-in.  The default backend suite collects this file
and skips it without touching PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))
ADMIN_URL_TEXT = os.getenv("BASIC_POSTGRES_ROOM_SAFETY_0041_TEST_URL")

# The application configuration deliberately accepts only its canonical
# database name.  Safety comes from the exact dedicated port, unused-database
# preflight, and test-owned cluster—not from inventing a non-runnable name.
DATABASE_NAME = "caresync"
PREVIOUS_REVISION = "0039_admissions_decision_spine"
CURRENT_REVISION = "0041_live_room_presence"
MIGRATION_ROLE = "caresync_0041_migration_owner"
MIGRATION_PASSWORD = "disposable-0041-migration-only"
RUNTIME_ROLE = "caresync_basic_app"
RUNTIME_PASSWORD = "disposable-0041-runtime-only"
TRANSPORT_OWNER_ROLE = "caresync_transport_command_owner"
TRANSPORT_INGEST_ROLE = "caresync_transport_evidence_ingest"
DISPOSABLE_PORT = 56555
PROTECTED_PORTS = {
    5432,
    5433,
    5434,
    56544,
    56546,
    56552,
    56553,
    56554,
    56641,
}

ROOM_SAFETY_TABLES = (
    "staff_room_presence_sessions",
    "staff_room_presence_events",
    "room_operational_exception_heads",
    "room_operational_exception_events",
)
DOWNGRADE_DEPENDENCY_TABLES = (
    "audit_events",
    "realtime_events",
    "user_notifications",
)
ROOM_SAFETY_FUNCTIONS = (
    "caresync_0041_presence_row_guard()",
    "caresync_0041_event_immutable_guard()",
    "caresync_0041_presence_event_guard()",
    "caresync_0041_presence_bundle_guard()",
    "caresync_0041_exception_head_guard()",
    "caresync_0041_exception_event_guard()",
    "caresync_0041_exception_bundle_guard()",
)
EXPECTED_UPDATE_COLUMNS = {
    "staff_room_presence_sessions": {
        "ended_at",
        "end_reason",
        "end_operation_id",
        "ended_by_user_id",
        "version",
        "updated_at",
    },
    "staff_room_presence_events": set(),
    "room_operational_exception_heads": {
        "state",
        "current_fingerprint_sha256",
        "current_evidence",
        "last_changed_at",
        "acknowledged_at",
        "acknowledged_by_user_id",
        "acknowledgement_reason",
        "resolved_at",
        "version",
        "updated_at",
    },
    "room_operational_exception_events": set(),
}
EXPECTED_TRIGGERS = {
    (
        "staff_room_presence_sessions",
        "staff_room_presence_sessions_row_guard",
        False,
        False,
    ),
    (
        "staff_room_presence_sessions",
        "staff_room_presence_sessions_bundle_guard",
        True,
        True,
    ),
    (
        "staff_room_presence_events",
        "staff_room_presence_events_insert_guard",
        False,
        False,
    ),
    (
        "staff_room_presence_events",
        "staff_room_presence_events_immutable",
        False,
        False,
    ),
    (
        "room_operational_exception_heads",
        "room_operational_exception_heads_row_guard",
        False,
        False,
    ),
    (
        "room_operational_exception_heads",
        "room_operational_exception_heads_bundle_guard",
        True,
        True,
    ),
    (
        "room_operational_exception_events",
        "room_operational_exception_events_insert_guard",
        False,
        False,
    ),
    (
        "room_operational_exception_events",
        "room_operational_exception_events_immutable",
        False,
        False,
    ),
}


def _guard_admin_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0041 acceptance requires PostgreSQL")
    if (url.host or "").strip().lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0041 acceptance requires a loopback host")
    if (
        url.port is None
        or url.port in PROTECTED_PORTS
        or url.port != DISPOSABLE_PORT
        or not 1 <= url.port <= 65535
    ):
        raise RuntimeError(
            "0041 acceptance requires its dedicated disposable port 56555"
        )
    if url.database != "postgres" or not url.username:
        raise RuntimeError(
            "0041 acceptance URL must target postgres as a cluster administrator"
        )
    return url


ADMIN_URL = _guard_admin_url(ADMIN_URL_TEXT) if ADMIN_URL_TEXT else None
pytestmark = pytest.mark.skipif(
    ADMIN_URL is None,
    reason=(
        "BASIC_POSTGRES_ROOM_SAFETY_0041_TEST_URL must name a fresh "
        "disposable loopback PostgreSQL 17 cluster on port 56555"
    ),
)


def _url(*, user: str | None = None, database: str = DATABASE_NAME) -> URL:
    assert ADMIN_URL is not None
    selected_user = user or str(ADMIN_URL.username)
    if selected_user == MIGRATION_ROLE:
        password = MIGRATION_PASSWORD
    elif selected_user == RUNTIME_ROLE:
        password = RUNTIME_PASSWORD
    else:
        password = ADMIN_URL.password
    return URL.create(
        "postgresql+psycopg",
        username=selected_user,
        password=password,
        host=ADMIN_URL.host,
        port=ADMIN_URL.port,
        database=database,
        query={"options": "-c client_encoding=UTF8"},
    )


def _migration_environment(*, destructive: bool = False) -> dict[str, str]:
    assert ADMIN_URL is not None
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": str(ADMIN_URL.host),
            "DATABASE_PORT": str(ADMIN_URL.port),
            "DATABASE_USER": MIGRATION_ROLE,
            "DATABASE_PASSWORD": MIGRATION_PASSWORD,
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
            "PGCLIENTENCODING": "UTF8",
        }
    )
    if destructive:
        environment["CARESYNC_ALLOW_0041_DESTRUCTIVE_DOWNGRADE"] = "1"
    else:
        environment.pop("CARESYNC_ALLOW_0041_DESTRUCTIVE_DOWNGRADE", None)
    return environment


def _alembic(
    action: str,
    revision: str,
    *,
    destructive: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=_migration_environment(destructive=destructive),
        text=True,
        capture_output=True,
        check=False,
    )


def _require_success(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _bootstrap() -> subprocess.CompletedProcess[str]:
    assert ADMIN_URL is not None
    environment = os.environ.copy()
    environment["PGCLIENTENCODING"] = "UTF8"
    if ADMIN_URL.password:
        environment["PGPASSWORD"] = str(ADMIN_URL.password)
    return subprocess.run(
        [
            str(PSQL),
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(ADMIN_URL.host),
            "-p",
            str(ADMIN_URL.port),
            "-U",
            str(ADMIN_URL.username),
            "-d",
            DATABASE_NAME,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _settings(
    *,
    user: str = RUNTIME_ROLE,
    password: str = RUNTIME_PASSWORD,
) -> Settings:
    assert ADMIN_URL is not None
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=str(ADMIN_URL.host),
        database_port=int(ADMIN_URL.port or 0),
        database_user=user,
        database_password=password,
        database_name=DATABASE_NAME,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-0041-room-safety-secret-at-least-32-bytes",
    )


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _post(
    client: TestClient,
    path: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _seed_source_tenant(
    client: TestClient,
    *,
    marker: str,
    room_count: int = 3,
) -> dict[str, object]:
    auth = _post(
        client,
        "/api/v1/auth/register",
        {},
        {
            "email": f"room-safety-{marker}@example.test",
            "password": "secure-password-123",
            "first_name": "Room",
            "last_name": marker.title(),
            "organization_name": f"0041 Source {marker.title()}",
        },
    )
    headers = _headers(auth)
    facility = _post(
        client,
        "/api/v1/facilities",
        headers,
        {
            "name": f"{marker.title()} Centre",
            "licensed_capacity": 60,
            "status": "active",
        },
    )
    program = _post(
        client,
        "/api/v1/programs",
        headers,
        {
            "facility_id": facility["id"],
            "name": f"{marker.title()} Daycare",
            "program_type": "daycare",
            "capacity": 60,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    rooms = [
        _post(
            client,
            "/api/v1/rooms",
            headers,
            {
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"{marker.title()} Room {index + 1}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        for index in range(room_count)
    ]
    family = _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": f"{marker.title()} Preserved Family",
        },
    )
    child = _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "first_name": f"Preserved{marker.title()}",
            "last_name": "Child",
            "date_of_birth": "2023-02-01",
        },
    )
    return {
        "auth": auth,
        "headers": headers,
        "facility": facility,
        "program": program,
        "rooms": rooms,
        "family": family,
        "child": child,
    }


def _workspace(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/staff/workspace", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _activation_secret(value: str) -> str:
    return parse_qs(urlparse(value).fragment)["token"][0]


def _invite_educator(
    client: TestClient,
    source: dict[str, object],
) -> dict:
    headers = source["headers"]
    assert isinstance(headers, dict)
    workspace = _workspace(client, headers)
    educator_role = next(
        role for role in workspace["roles"] if role["key"] == "educator"
    )
    facility = source["facility"]
    rooms = source["rooms"]
    assert isinstance(facility, dict)
    assert isinstance(rooms, list)
    invitation = _post(
        client,
        "/api/v1/staff/invitations",
        headers,
        {
            "email": f"room-safety-educator-{uuid4().hex[:8]}@example.test",
            "first_name": "Scoped",
            "last_name": "Educator",
            "role_id": educator_role["id"],
            "assigned_facility_ids": [facility["id"]],
            "assigned_room_ids": [room["id"] for room in rooms],
        },
    )
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={
            "token": _activation_secret(invitation["activation_url"]),
            "password": "secure-password-123",
        },
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _activate_release(client: TestClient, source: dict[str, object]) -> dict:
    headers = source["headers"]
    assert isinstance(headers, dict)
    status_response = client.get(
        "/api/v1/room-safety/release-reconciliation/status",
        headers=headers,
    )
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    operation_id = uuid4()
    activated = client.post(
        "/api/v1/room-safety/release-reconciliation",
        headers=headers,
        json={
            "client_operation_id": str(operation_id),
            "expected_active_facility_count": status["active_facility_count"],
            "expected_facility_set_sha256": status["facility_set_sha256"],
            "expected_facility_ids": status["missing_facility_ids"],
        },
    )
    assert activated.status_code == 200, activated.text
    replay = client.post(
        "/api/v1/room-safety/release-reconciliation",
        headers=headers,
        json={
            "client_operation_id": str(operation_id),
            "expected_active_facility_count": status["active_facility_count"],
            "expected_facility_set_sha256": status["facility_set_sha256"],
            "expected_facility_ids": status["missing_facility_ids"],
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    return activated.json()


def _parallel_post(
    settings: Settings,
    *,
    path: str,
    headers: dict[str, str],
    payloads: list[dict],
) -> list[tuple[int, dict]]:
    barrier = Barrier(len(payloads))

    def run(payload: dict) -> tuple[int, dict]:
        with TestClient(create_app(settings)) as client:
            barrier.wait(timeout=20)
            response = client.post(path, headers=headers, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        return list(executor.map(run, payloads))


def _set_context(
    connection,
    *,
    user_id: str,
    organization_id: str,
    operation_id: UUID | None = None,
    server_derived: bool = False,
) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": user_id},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": organization_id},
    )
    if operation_id is not None:
        connection.execute(
            text(
                "SELECT set_config("
                "'app.current_room_presence_operation_id',:value,true)"
            ),
            {"value": str(operation_id)},
        )
    if server_derived:
        connection.execute(
            text(
                "SELECT set_config("
                "'app.current_room_presence_server_derived','true',true)"
            )
        )


def _table_counts(connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {
        table_name: int(
            connection.scalar(
                text(f'SELECT count(*) FROM public."{table_name}"')
            )
            or 0
        )
        for table_name in tables
    }


def _source_tables(connection) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' AND tablename<>'alembic_version' "
                "ORDER BY tablename"
            )
        ).scalars()
    )


def _database_row_digest(connection, tables: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for table_name in tables:
        payload = connection.scalar(
            text(
                f"SELECT COALESCE("
                f"jsonb_agg(to_jsonb(source_row) "
                f"ORDER BY to_jsonb(source_row)::text),'[]'::jsonb)::text "
                f'FROM public."{table_name}" AS source_row'
            )
        )
        digest.update(table_name.encode())
        digest.update(b"\0")
        digest.update(str(payload).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _schema_fingerprint(connection) -> str:
    tables = list(ROOM_SAFETY_TABLES)
    parts: list[tuple] = []
    parts.extend(
        ("column", *row)
        for row in connection.execute(
            text(
                "SELECT table_name,column_name,data_type,udt_name,is_nullable,"
                "coalesce(column_default,'') FROM information_schema.columns "
                "WHERE table_schema='public' "
                "AND table_name=ANY(CAST(:tables AS text[])) "
                "ORDER BY table_name,ordinal_position"
            ),
            {"tables": tables},
        )
    )
    parts.extend(
        ("constraint", *row)
        for row in connection.execute(
            text(
                "SELECT relation.relname,constraint_record.conname,"
                "constraint_record.contype,constraint_record.condeferrable,"
                "constraint_record.condeferred,"
                "pg_catalog.pg_get_constraintdef(constraint_record.oid) "
                "FROM pg_catalog.pg_constraint AS constraint_record "
                "JOIN pg_catalog.pg_class AS relation "
                "ON relation.oid=constraint_record.conrelid "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid=relation.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND relation.relname=ANY(CAST(:tables AS text[])) "
                "ORDER BY relation.relname,constraint_record.conname"
            ),
            {"tables": tables},
        )
    )
    parts.extend(
        ("index", *row)
        for row in connection.execute(
            text(
                "SELECT table_record.relname,index_record.relname,"
                "pg_catalog.pg_get_indexdef(index_record.oid) "
                "FROM pg_catalog.pg_index AS index_link "
                "JOIN pg_catalog.pg_class AS index_record "
                "ON index_record.oid=index_link.indexrelid "
                "JOIN pg_catalog.pg_class AS table_record "
                "ON table_record.oid=index_link.indrelid "
                "WHERE table_record.relname=ANY(CAST(:tables AS text[])) "
                "ORDER BY table_record.relname,index_record.relname"
            ),
            {"tables": tables},
        )
    )
    parts.extend(
        ("trigger", *row)
        for row in connection.execute(
            text(
                "SELECT relation.relname,trigger.tgname,trigger.tgdeferrable,"
                "trigger.tginitdeferred,pg_catalog.pg_get_triggerdef(trigger.oid) "
                "FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS relation "
                "ON relation.oid=trigger.tgrelid "
                "WHERE relation.relname=ANY(CAST(:tables AS text[])) "
                "AND NOT trigger.tgisinternal "
                "ORDER BY relation.relname,trigger.tgname"
            ),
            {"tables": tables},
        )
    )
    parts.extend(
        ("policy", *row)
        for row in connection.execute(
            text(
                "SELECT tablename,policyname,permissive,roles::text,cmd,"
                "coalesce(qual,''),coalesce(with_check,'') "
                "FROM pg_catalog.pg_policies WHERE schemaname='public' "
                "AND tablename=ANY(CAST(:tables AS text[])) "
                "ORDER BY tablename,policyname"
            ),
            {"tables": tables},
        )
    )
    parts.extend(
        ("function", *row)
        for row in connection.execute(
            text(
                "SELECT procedure.proname,procedure.prosecdef,"
                "coalesce(procedure.proconfig::text,''),"
                "pg_catalog.pg_get_userbyid(procedure.proowner),"
                "pg_catalog.pg_get_functiondef(procedure.oid) "
                "FROM pg_catalog.pg_proc AS procedure "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid=procedure.pronamespace "
                "WHERE namespace.nspname='public' "
                "AND procedure.proname LIKE 'caresync_0041_%' "
                "ORDER BY procedure.proname"
            )
        )
    )
    return hashlib.sha256(
        json.dumps(parts, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _force_rls_snapshot(connection) -> dict[str, tuple[bool, bool]]:
    tables = (*ROOM_SAFETY_TABLES, *DOWNGRADE_DEPENDENCY_TABLES)
    return {
        row.relname: (row.relrowsecurity, row.relforcerowsecurity)
        for row in connection.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity "
                "FROM pg_catalog.pg_class "
                "WHERE relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(tables)},
        )
    }


def _assert_catalog_and_acl(connection) -> None:
    runtime_identity = connection.execute(
        text(
            "SELECT rolsuper,rolcreaterole,rolcreatedb,rolreplication,"
            "rolinherit,rolbypassrls,rolcanlogin,"
            "coalesce(array_to_string(rolconfig,','),'') AS configuration "
            "FROM pg_catalog.pg_roles WHERE rolname=:role"
        ),
        {"role": RUNTIME_ROLE},
    ).one()
    assert runtime_identity[:7] == (
        False,
        False,
        False,
        False,
        False,
        False,
        True,
    )
    assert "search_path=public, pg_catalog" in runtime_identity.configuration
    assert not connection.scalar(
        text(
            "SELECT has_database_privilege(:role,current_database(),'CREATE')"
        ),
        {"role": RUNTIME_ROLE},
    )
    assert not connection.scalar(
        text(
            "SELECT has_database_privilege("
            ":role,current_database(),'TEMPORARY')"
        ),
        {"role": RUNTIME_ROLE},
    )

    relation_security = {
        row.relname: (
            row.relrowsecurity,
            row.relforcerowsecurity,
            row.owner_name,
        )
        for row in connection.execute(
            text(
                "SELECT relation.relname,relation.relrowsecurity,"
                "relation.relforcerowsecurity,"
                "pg_catalog.pg_get_userbyid(relation.relowner) AS owner_name "
                "FROM pg_catalog.pg_class AS relation "
                "WHERE relation.relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(ROOM_SAFETY_TABLES)},
        )
    }
    assert relation_security == {
        table_name: (True, True, MIGRATION_ROLE)
        for table_name in ROOM_SAFETY_TABLES
    }

    policies = list(
        connection.execute(
            text(
                "SELECT tablename,policyname,cmd,qual,with_check "
                "FROM pg_catalog.pg_policies WHERE schemaname='public' "
                "AND tablename=ANY(CAST(:tables AS text[])) "
                "ORDER BY tablename,policyname"
            ),
            {"tables": list(ROOM_SAFETY_TABLES)},
        )
    )
    assert len(policies) == len(ROOM_SAFETY_TABLES)
    for policy in policies:
        assert policy.policyname == f"{policy.tablename}_tenant"
        assert policy.cmd == "ALL"
        for definition in (policy.qual, policy.with_check):
            rendered = str(definition)
            assert "app.current_organization_id" in rendered
            assert "app.current_user_id" in rendered
            assert "organization_memberships" in rendered
            assert "status" in rendered
            assert "active" in rendered

    triggers = {
        (
            row.relname,
            row.tgname,
            row.tgdeferrable,
            row.tginitdeferred,
        )
        for row in connection.execute(
            text(
                "SELECT relation.relname,trigger.tgname,"
                "trigger.tgdeferrable,trigger.tginitdeferred "
                "FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS relation "
                "ON relation.oid=trigger.tgrelid "
                "WHERE relation.relname=ANY(CAST(:tables AS text[])) "
                "AND NOT trigger.tgisinternal"
            ),
            {"tables": list(ROOM_SAFETY_TABLES)},
        )
    }
    assert triggers == EXPECTED_TRIGGERS

    for table_name in ROOM_SAFETY_TABLES:
        relation = f"public.{table_name}"
        assert connection.scalar(
            text("SELECT has_table_privilege(:role,:table,'SELECT')"),
            {"role": RUNTIME_ROLE, "table": relation},
        )
        assert connection.scalar(
            text("SELECT has_table_privilege(:role,:table,'INSERT')"),
            {"role": RUNTIME_ROLE, "table": relation},
        )
        assert not connection.scalar(
            text("SELECT has_table_privilege(:role,:table,'UPDATE')"),
            {"role": RUNTIME_ROLE, "table": relation},
        )
        update_columns = set(
            connection.execute(
                text(
                    "SELECT attribute.attname "
                    "FROM pg_catalog.pg_attribute AS attribute "
                    "WHERE attribute.attrelid=pg_catalog.to_regclass(:table) "
                    "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                    "AND pg_catalog.has_column_privilege("
                    ":role,attribute.attrelid,attribute.attnum,'UPDATE')"
                ),
                {"role": RUNTIME_ROLE, "table": relation},
            ).scalars()
        )
        assert update_columns == EXPECTED_UPDATE_COLUMNS[table_name]
        for forbidden in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not connection.scalar(
                text("SELECT has_table_privilege(:role,:table,:privilege)"),
                {
                    "role": RUNTIME_ROLE,
                    "table": relation,
                    "privilege": forbidden,
                },
            )
        public_acl_count = connection.scalar(
            text(
                "SELECT count(*) FROM pg_catalog.pg_class AS relation "
                "CROSS JOIN LATERAL pg_catalog.aclexplode("
                "COALESCE(relation.relacl,"
                "pg_catalog.acldefault('r',relation.relowner))) AS acl "
                "WHERE relation.oid=pg_catalog.to_regclass(:table) "
                "AND acl.grantee=0"
            ),
            {"table": relation},
        )
        assert public_acl_count == 0

    for signature in ROOM_SAFETY_FUNCTIONS:
        identity = connection.execute(
            text(
                "SELECT procedure.prosecdef,"
                "pg_catalog.pg_get_userbyid(procedure.proowner) AS owner_name,"
                "coalesce(procedure.proconfig::text,'') AS configuration "
                "FROM pg_catalog.pg_proc AS procedure "
                "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature)"
            ),
            {"signature": f"public.{signature}"},
        ).one()
        assert identity.prosecdef is True
        assert identity.owner_name == MIGRATION_ROLE
        assert "search_path=" in identity.configuration
        assert not connection.scalar(
            text(
                "SELECT has_function_privilege(:role,:function,'EXECUTE')"
            ),
            {"role": RUNTIME_ROLE, "function": f"public.{signature}"},
        )
        assert connection.scalar(
            text(
                "SELECT count(*) FROM pg_catalog.pg_proc AS procedure "
                "CROSS JOIN LATERAL pg_catalog.aclexplode("
                "COALESCE(procedure.proacl,"
                "pg_catalog.acldefault('f',procedure.proowner))) AS acl "
                "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature) "
                "AND acl.grantee=0"
            ),
            {"signature": f"public.{signature}"},
        ) == 0


def _assert_runtime_identity() -> None:
    database = Database(_settings())
    try:
        database.assert_basic_runtime_identity()
        assert database.has_live_room_presence_safety_board() is True
    finally:
        database.dispose()

    for user, password in (
        (MIGRATION_ROLE, MIGRATION_PASSWORD),
        (
            str(ADMIN_URL.username),
            str(ADMIN_URL.password or ""),
        ),
    ):
        wrong_identity = Database(_settings(user=user, password=password))
        try:
            with pytest.raises(RuntimeError):
                wrong_identity.assert_basic_runtime_identity()
        finally:
            wrong_identity.dispose()


def _assert_residue_absent(connection) -> None:
    assert connection.scalar(
        text(
            "SELECT count(*) FROM public.audit_events WHERE action IN "
            "('room_safety.release_reconciliation_facility_completed',"
            "'room_safety.release_reconciliation_completed',"
            "'staff_room_presence.started','staff_room_presence.moved',"
            "'staff_room_presence.ended','staff_room_presence.access_revoked',"
            "'room_operational_exception.acknowledged')"
        )
    ) == 0
    assert connection.scalar(
        text(
            "SELECT count(*) FROM public.realtime_events WHERE "
            "event_type LIKE 'staff_room_presence.%' OR "
            "event_type LIKE 'room_operational_exception.%'"
        )
    ) == 0
    assert connection.scalar(
        text(
            "SELECT count(*) FROM public.user_notifications WHERE "
            "event_key LIKE 'room-operational-exception:%' OR "
            "action_entity_type='room_operational_exception'"
        )
    ) == 0


def test_postgres_0041_room_safety_roundtrip_runtime_guards_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ADMIN_URL is not None
    monkeypatch.setenv("PGCLIENTENCODING", "UTF8")
    cluster = create_engine(
        _url(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    database_created = False
    created_roles: set[str] = set()
    database_admin = None
    runtime = None
    try:
        with cluster.connect() as connection:
            assert int(
                connection.scalar(text("SHOW server_version_num"))
            ) // 10000 == 17
            assert connection.scalar(
                text(
                    "SELECT rolsuper FROM pg_catalog.pg_roles "
                    "WHERE rolname=current_user"
                )
            )
            assert connection.scalar(
                text(
                    "SELECT 1 FROM pg_catalog.pg_database "
                    "WHERE datname=:database"
                ),
                {"database": DATABASE_NAME},
            ) is None, "0041 proof requires an unused disposable database name"
            occupied = set(
                connection.execute(
                    text(
                        "SELECT rolname FROM pg_catalog.pg_roles "
                        "WHERE rolname=ANY(CAST(:roles AS text[]))"
                    ),
                    {
                        "roles": [
                            MIGRATION_ROLE,
                            RUNTIME_ROLE,
                            TRANSPORT_OWNER_ROLE,
                            TRANSPORT_INGEST_ROLE,
                        ]
                    },
                ).scalars()
            )
            assert not occupied, (
                "0041 proof requires unused CareSync proof role names: "
                f"{sorted(occupied)}"
            )
            connection.exec_driver_sql(
                f"CREATE ROLE {MIGRATION_ROLE} LOGIN PASSWORD "
                f"'{MIGRATION_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOINHERIT NOBYPASSRLS"
            )
            created_roles.add(MIGRATION_ROLE)
            connection.exec_driver_sql(
                f'ALTER ROLE {MIGRATION_ROLE} SET search_path TO "$user", public'
            )
            connection.exec_driver_sql(
                f"CREATE DATABASE {DATABASE_NAME} OWNER {MIGRATION_ROLE}"
            )
            database_created = True

        database_admin = create_engine(_url())
        with database_admin.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            connection.execute(
                text(f"ALTER SCHEMA public OWNER TO {MIGRATION_ROLE}")
            )
            connection.execute(
                text(
                    f"CREATE SCHEMA {MIGRATION_ROLE} "
                    f"AUTHORIZATION {MIGRATION_ROLE}"
                )
            )
            role_security = connection.execute(
                text(
                    "SELECT rolsuper,rolcreaterole,rolcreatedb,rolreplication,"
                    "rolinherit,rolbypassrls FROM pg_catalog.pg_roles "
                    "WHERE rolname=:role"
                ),
                {"role": MIGRATION_ROLE},
            ).one()
            assert role_security == (False, False, False, False, False, False)

        # Build the retained lineage as the restricted owner.  The previously
        # certified 0033 immutable-source function deliberately keeps its
        # privileged owner, matching the existing PostgreSQL release proofs.
        _require_success(_alembic("upgrade", "0038_public_job_catalog_outbox"))
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                "ALTER FUNCTION "
                "public.caresync_0033_attested_source_immutable() "
                f"OWNER TO {ADMIN_URL.username}"
            )
        _require_success(_alembic("upgrade", PREVIOUS_REVISION))
        # The cluster preflight proved these names were unused, so any subset
        # created by a partially failing bootstrap belongs to this proof and
        # must be removed during cleanup.
        created_roles.update(
            {RUNTIME_ROLE, TRANSPORT_OWNER_ROLE, TRANSPORT_INGEST_ROLE}
        )
        first_bootstrap = _bootstrap()
        assert first_bootstrap.returncode == 0, (
            first_bootstrap.stdout + first_bootstrap.stderr
        )
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"
            )

        settings = _settings()
        with TestClient(create_app(settings)) as source_client:
            source_a = _seed_source_tenant(source_client, marker="alpha")
            source_b = _seed_source_tenant(source_client, marker="beta")

        with database_admin.connect() as connection:
            source_tables = _source_tables(connection)
            source_counts = _table_counts(connection, source_tables)
            source_digest = _database_row_digest(connection, source_tables)

        # Exact populated-source, empty-ledger roundtrip.  Every pre-0041 row
        # survives and a second upgrade produces an identical boundary.
        _require_success(_alembic("upgrade", CURRENT_REVISION))
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == CURRENT_REVISION
            assert _table_counts(connection, source_tables) == source_counts
            assert _database_row_digest(connection, source_tables) == source_digest
            assert _table_counts(connection, ROOM_SAFETY_TABLES) == {
                table_name: 0 for table_name in ROOM_SAFETY_TABLES
            }
            first_fingerprint = _schema_fingerprint(connection)
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_class AS relation "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname=:schema"
                ),
                {"schema": MIGRATION_ROLE},
            ) == 0

        _require_success(_alembic("downgrade", PREVIOUS_REVISION))
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == PREVIOUS_REVISION
            assert all(
                connection.scalar(
                    text("SELECT pg_catalog.to_regclass(:relation)"),
                    {"relation": f"public.{table_name}"},
                )
                is None
                for table_name in ROOM_SAFETY_TABLES
            )
            assert _table_counts(connection, source_tables) == source_counts
            assert _database_row_digest(connection, source_tables) == source_digest

        _require_success(_alembic("upgrade", CURRENT_REVISION))
        second_bootstrap = _bootstrap()
        assert second_bootstrap.returncode == 0, (
            second_bootstrap.stdout + second_bootstrap.stderr
        )
        third_bootstrap = _bootstrap()
        assert third_bootstrap.returncode == 0, (
            third_bootstrap.stdout + third_bootstrap.stderr
        )
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"
            )
            assert _schema_fingerprint(connection) == first_fingerprint
            assert _table_counts(connection, source_tables) == source_counts
            assert _database_row_digest(connection, source_tables) == source_digest
            _assert_catalog_and_acl(connection)
        _assert_runtime_identity()

        runtime = create_engine(_url(user=RUNTIME_ROLE))
        with TestClient(create_app(settings)) as client:
            educator = _invite_educator(client, source_a)
            _activate_release(client, source_a)
            _activate_release(client, source_b)

            facility = source_a["facility"]
            rooms = source_a["rooms"]
            owner_headers = source_a["headers"]
            assert isinstance(facility, dict)
            assert isinstance(rooms, list)
            assert isinstance(owner_headers, dict)
            educator_headers = _headers(educator)

            # An ambiguous clock-in remains valid while room operations are
            # gated until an explicit eligible room is selected.
            clock_operation = uuid4()
            clock_in = client.post(
                "/api/v1/staff/self/shifts/clock-in",
                headers=educator_headers,
                json={
                    "facility_id": facility["id"],
                    "operation_id": str(clock_operation),
                },
            )
            assert clock_in.status_code == 201, clock_in.text
            assert clock_in.json()["room_presence_required"] is True
            assert clock_in.json()["current_room_presence"] is None
            replayed_clock = client.post(
                "/api/v1/staff/self/shifts/clock-in",
                headers=educator_headers,
                json={
                    "facility_id": facility["id"],
                    "operation_id": str(clock_operation),
                },
            )
            assert replayed_clock.status_code == 201, replayed_clock.text
            assert replayed_clock.json()["id"] == clock_in.json()["id"]

            open_exceptions = client.get(
                "/api/v1/room-safety/exceptions",
                headers=owner_headers,
                params={"facility_id": facility["id"], "state": "open"},
            )
            assert open_exceptions.status_code == 200, open_exceptions.text
            unlocated = next(
                value
                for value in open_exceptions.json()["items"]
                if value["condition_code"]
                == "open_shift_staff_without_current_room"
            )

            # Even the database owner cannot resolve an episode without its
            # same-transaction immutable event.
            with pytest.raises(
                DBAPIError,
                match="room exception command bundle is incomplete",
            ), database_admin.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                    operation_id=uuid4(),
                    server_derived=True,
                )
                connection.execute(
                    text(
                        "UPDATE public.room_operational_exception_heads "
                        "SET state='resolved',resolved_at=now(),"
                        "last_changed_at=now(),version=version+1,updated_at=now() "
                        "WHERE id=:exception_id"
                    ),
                    {"exception_id": unlocated["id"]},
                )

            start_operation = uuid4()
            start_payload = {
                "client_operation_id": str(start_operation),
                "staff_shift_id": clock_in.json()["id"],
                "facility_id": facility["id"],
                "room_id": rooms[0]["id"],
            }
            started = client.post(
                "/api/v1/staff/self/room-presence/start",
                headers=educator_headers,
                json=start_payload,
            )
            assert started.status_code == 201, started.text
            assert started.json()["replayed"] is False
            first_session_id = started.json()["affected_session_id"]

            move_results = _parallel_post(
                settings,
                path="/api/v1/staff/self/room-presence/move",
                headers=educator_headers,
                payloads=[
                    {
                        "client_operation_id": str(uuid4()),
                        "expected_session_id": first_session_id,
                        "expected_version": 1,
                        "destination_room_id": rooms[1]["id"],
                        "reason": "Moving to the next assigned room.",
                    },
                    {
                        "client_operation_id": str(uuid4()),
                        "expected_session_id": first_session_id,
                        "expected_version": 1,
                        "destination_room_id": rooms[2]["id"],
                        "reason": "Moving to another assigned room.",
                    },
                ],
            )
            assert sorted(status for status, _body in move_results) == [200, 409]
            assert all(status < 500 for status, _body in move_results)

            current_presence = client.get(
                "/api/v1/staff/self/room-presence",
                headers=educator_headers,
            )
            assert current_presence.status_code == 200, current_presence.text
            current = current_presence.json()["current_presence"]
            assert current is not None
            assert current["version"] == 1
            assert current["room_id"] in {rooms[1]["id"], rooms[2]["id"]}

            # Forced RLS shows no 0041 rows without context, the owning tenant
            # sees its rows, and the other active tenant sees none.
            with runtime.begin() as connection:
                assert all(
                    connection.scalar(
                        text(f"SELECT count(*) FROM public.{table_name}")
                    )
                    == 0
                    for table_name in ROOM_SAFETY_TABLES
                )
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                )
                assert connection.scalar(
                    text(
                        "SELECT count(*) FROM "
                        "public.staff_room_presence_sessions"
                    )
                ) == 2
                assert connection.scalar(
                    text(
                        "SELECT count(*) FROM public.staff_room_presence_events"
                    )
                ) == 2
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_b["auth"]["user"]["id"],
                    organization_id=source_b["auth"]["user"]["organization_id"],
                )
                assert all(
                    connection.scalar(
                        text(f"SELECT count(*) FROM public.{table_name}")
                    )
                    == 0
                    for table_name in ROOM_SAFETY_TABLES
                )

            cross_tenant = client.get(
                "/api/v1/room-safety/live",
                headers=source_b["headers"],
                params={"facility_id": facility["id"]},
            )
            assert cross_tenant.status_code == 404, cross_tenant.text

            # Runtime ACLs and database guards independently reject deletion,
            # scope rewrite, duplicate/overlapping presence, unmatched close,
            # and immutable-event mutation.
            with pytest.raises(DBAPIError), runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=educator["user"]["id"],
                    organization_id=educator["user"]["organization_id"],
                )
                connection.execute(
                    text(
                        "DELETE FROM public.staff_room_presence_sessions "
                        "WHERE id=:session_id"
                    ),
                    {"session_id": current["id"]},
                )

            with pytest.raises(
                DBAPIError,
                match="invalid room presence terminal transition",
            ), database_admin.begin() as connection:
                _set_context(
                    connection,
                    user_id=educator["user"]["id"],
                    organization_id=educator["user"]["organization_id"],
                    operation_id=uuid4(),
                )
                connection.execute(
                    text(
                        "UPDATE public.staff_room_presence_sessions "
                        "SET room_id=:room_id WHERE id=:session_id"
                    ),
                    {
                        "room_id": rooms[0]["id"],
                        "session_id": current["id"],
                    },
                )

            with pytest.raises(
                DBAPIError,
                match="overlapping room presence is forbidden",
            ), database_admin.begin() as connection:
                overlap_operation = uuid4()
                _set_context(
                    connection,
                    user_id=educator["user"]["id"],
                    organization_id=educator["user"]["organization_id"],
                    operation_id=overlap_operation,
                )
                connection.execute(
                    text(
                        "INSERT INTO public.staff_room_presence_sessions "
                        "(id,organization_id,membership_id,staff_shift_id,"
                        "facility_id,room_id,source,started_at,"
                        "start_operation_id,started_by_user_id,version) VALUES "
                        "(:id,:organization_id,:membership_id,:staff_shift_id,"
                        ":facility_id,:room_id,'staff_selected',now(),"
                        ":operation_id,:actor_user_id,1)"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": educator["user"]["organization_id"],
                        "membership_id": educator["user"]["membership_id"],
                        "staff_shift_id": clock_in.json()["id"],
                        "facility_id": facility["id"],
                        "room_id": rooms[0]["id"],
                        "operation_id": overlap_operation,
                        "actor_user_id": educator["user"]["id"],
                    },
                )

            with pytest.raises(
                DBAPIError,
                match="room presence command bundle is incomplete",
            ), database_admin.begin() as connection:
                unmatched_operation = uuid4()
                _set_context(
                    connection,
                    user_id=educator["user"]["id"],
                    organization_id=educator["user"]["organization_id"],
                    operation_id=unmatched_operation,
                )
                connection.execute(
                    text(
                        "UPDATE public.staff_room_presence_sessions "
                        "SET ended_at=now(),end_reason='staff_ended',"
                        "end_operation_id=:operation_id,"
                        "ended_by_user_id=:actor_user_id,"
                        "version=2,updated_at=now() WHERE id=:session_id"
                    ),
                    {
                        "operation_id": unmatched_operation,
                        "actor_user_id": educator["user"]["id"],
                        "session_id": current["id"],
                    },
                )

            with pytest.raises(
                DBAPIError,
                match="0041 events are immutable",
            ), database_admin.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.staff_room_presence_events "
                        "SET result=result WHERE to_session_id=:session_id"
                    ),
                    {"session_id": current["id"]},
                )

            clock_out_operation = uuid4()
            clock_out_payload = {
                "facility_id": facility["id"],
                "operation_id": str(clock_out_operation),
            }
            clock_out = client.post(
                "/api/v1/staff/self/shifts/clock-out",
                headers=educator_headers,
                json=clock_out_payload,
            )
            assert clock_out.status_code == 200, clock_out.text
            assert clock_out.json()["status"] == "closed"
            clock_out_replay = client.post(
                "/api/v1/staff/self/shifts/clock-out",
                headers=educator_headers,
                json=clock_out_payload,
            )
            assert clock_out_replay.status_code == 200, clock_out_replay.text
            with database_admin.connect() as connection:
                terminal = connection.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE ended_at IS NULL),"
                        "count(*) FILTER (WHERE end_reason='clocked_out'),"
                        "count(*) FILTER (WHERE version=2) "
                        "FROM public.staff_room_presence_sessions "
                        "WHERE organization_id=:organization_id "
                        "AND membership_id=:membership_id"
                    ),
                    {
                        "organization_id": educator["user"]["organization_id"],
                        "membership_id": educator["user"]["membership_id"],
                    },
                ).one()
                assert terminal[0] == 0
                assert terminal[1] == 1
                assert terminal[2] == 2

        # A populated downgrade must refuse under the NOBYPASSRLS migration
        # owner and atomically restore FORCE RLS on both 0041 and dependency
        # tables.  Exact catalog and row evidence must remain unchanged.
        unrelated_audit_id = uuid4()
        with database_admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.audit_events "
                    "(id,organization_id,facility_id,actor_user_id,action,"
                    "entity_type,entity_id,occurred_at,details) VALUES "
                    "(:id,:organization_id,NULL,:actor_user_id,"
                    "'proof.unrelated','organization',:organization_id,"
                    ":occurred_at,CAST('{}' AS jsonb))"
                ),
                {
                    "id": unrelated_audit_id,
                    "organization_id": source_a["auth"]["user"][
                        "organization_id"
                    ],
                    "actor_user_id": source_a["auth"]["user"]["id"],
                    "occurred_at": datetime.now(UTC),
                },
            )
            populated_counts = _table_counts(connection, ROOM_SAFETY_TABLES)
            assert sum(populated_counts.values()) > 0
            populated_fingerprint = _schema_fingerprint(connection)
            force_before_refusal = _force_rls_snapshot(connection)
            assert force_before_refusal == {
                table_name: (True, True)
                for table_name in (
                    *ROOM_SAFETY_TABLES,
                    *DOWNGRADE_DEPENDENCY_TABLES,
                )
            }

        refused = _alembic("downgrade", PREVIOUS_REVISION)
        assert refused.returncode != 0
        assert (
            "0041 downgrade refused: live room presence or exception history exists"
            in refused.stdout + refused.stderr
        )
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == CURRENT_REVISION
            assert _table_counts(connection, ROOM_SAFETY_TABLES) == populated_counts
            assert _schema_fingerprint(connection) == populated_fingerprint
            assert _force_rls_snapshot(connection) == force_before_refusal

        # The destructive switch is exercised only inside this test-owned
        # database.  It removes 0041 residue while preserving unrelated facts.
        _require_success(
            _alembic(
                "downgrade",
                PREVIOUS_REVISION,
                destructive=True,
            )
        )
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == PREVIOUS_REVISION
            assert all(
                connection.scalar(
                    text("SELECT pg_catalog.to_regclass(:relation)"),
                    {"relation": f"public.{table_name}"},
                )
                is None
                for table_name in ROOM_SAFETY_TABLES
            )
            _assert_residue_absent(connection)
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE id=:event_id AND action='proof.unrelated'"
                ),
                {"event_id": unrelated_audit_id},
            ) == 1

        # External-residue-only history is also visible to the migration owner,
        # refuses safely, and is removed only with the disposable opt-in.
        _require_success(_alembic("upgrade", CURRENT_REVISION))
        bootstrap_after_cleanup = _bootstrap()
        assert bootstrap_after_cleanup.returncode == 0, (
            bootstrap_after_cleanup.stdout + bootstrap_after_cleanup.stderr
        )
        external_only_id = uuid4()
        with database_admin.begin() as connection:
            assert _table_counts(connection, ROOM_SAFETY_TABLES) == {
                table_name: 0 for table_name in ROOM_SAFETY_TABLES
            }
            connection.execute(
                text(
                    "INSERT INTO public.audit_events "
                    "(id,organization_id,facility_id,actor_user_id,action,"
                    "entity_type,entity_id,occurred_at,details) VALUES "
                    "(:id,:organization_id,NULL,:actor_user_id,"
                    "'room_safety.release_reconciliation_completed',"
                    "'organization',:organization_id,:occurred_at,"
                    "CAST('{}' AS jsonb))"
                ),
                {
                    "id": external_only_id,
                    "organization_id": source_a["auth"]["user"][
                        "organization_id"
                    ],
                    "actor_user_id": source_a["auth"]["user"]["id"],
                    "occurred_at": datetime.now(UTC),
                },
            )
            external_force_snapshot = _force_rls_snapshot(connection)

        external_refused = _alembic("downgrade", PREVIOUS_REVISION)
        assert external_refused.returncode != 0
        assert (
            "0041 downgrade refused: live room presence or exception history exists"
            in external_refused.stdout + external_refused.stderr
        )
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == CURRENT_REVISION
            assert _force_rls_snapshot(connection) == external_force_snapshot
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE id=:event_id"
                ),
                {"event_id": external_only_id},
            ) == 1

        _require_success(
            _alembic(
                "downgrade",
                PREVIOUS_REVISION,
                destructive=True,
            )
        )
        with database_admin.connect() as connection:
            _assert_residue_absent(connection)
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE id=:event_id"
                ),
                {"event_id": external_only_id},
            ) == 0

        # Leave the disposable database on the reviewed head and prove the
        # complete detector/bootstrap/runtime identity once more.
        _require_success(_alembic("upgrade", CURRENT_REVISION))
        final_bootstrap = _bootstrap()
        assert final_bootstrap.returncode == 0, (
            final_bootstrap.stdout + final_bootstrap.stderr
        )
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"
            )
            _assert_catalog_and_acl(connection)
        _assert_runtime_identity()
    finally:
        if runtime is not None:
            runtime.dispose()
        if database_admin is not None:
            database_admin.dispose()
        if database_created:
            with cluster.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_catalog.pg_terminate_backend(pid) "
                        "FROM pg_catalog.pg_stat_activity "
                        "WHERE datname=:database AND pid<>pg_backend_pid()"
                    ),
                    {"database": DATABASE_NAME},
                )
                connection.exec_driver_sql(
                    f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"'
                )
        with cluster.connect() as connection:
            for role_name in (
                TRANSPORT_INGEST_ROLE,
                TRANSPORT_OWNER_ROLE,
                RUNTIME_ROLE,
                MIGRATION_ROLE,
            ):
                if role_name in created_roles:
                    connection.exec_driver_sql(
                        f'DROP ROLE IF EXISTS "{role_name}"'
                    )
        cluster.dispose()
